import re
import pandas as pd
from rapidfuzz import process, fuzz

class MedicationNormalizer:
    # --- 1. Regex Compilations for Parsing ---
    SPLIT_PATTERN = re.compile(r"\s*-\s*")
    JML_PATTERN = re.compile(r"\[jml:\s*([\d.]+)\]", re.IGNORECASE)
    INSTR_PATTERN = re.compile(r"\((.*?)\)\s*$")
    SEP_PATTERN = re.compile(r'[/+_\-]')
    PACKAGING_PATTERN = re.compile(
        r'\b(KAPLET|TAB|TABLET|KAPSUL|INJEKSI|SYRUP|SIRUP|'
        r'BLISTER|STRIP|BOTOL|AMPUL|VIAL|SALEP|CREAM|KRIM|KAP|'
        r'KALENG|DUS|BOX|TUBE|SACHET|SACS)\b',
        re.IGNORECASE
    )
    DOSAGE_PATTERN = re.compile(r'\d+([.,]\d+)?\s*(MG|ML|GR|G|IU|%)\b', re.IGNORECASE)
    NUMBER_PATTERN = re.compile(r'\b\d+([.,]\d+)?\b')
    WS_PATTERN = re.compile(r'\s+')
    GARBAGE = {"1)", "1", "]", ""}

    # --- 2. Configuration & Reference Data ---
    FUZZY_THRESHOLD = 80
    def __init__(self, kemenkes_df, normalization_df, admin_df):
        # Initialize the memoization cache
        self._cache = {}
        
        # Standardize Reference Casing
        kemenkes_df["drug_name"] = kemenkes_df["drug_name"].str.upper()
        kemenkes_df["international_name"] = kemenkes_df["international_name"].str.upper()
        normalization_df["source"] = normalization_df["source"].str.upper()
        normalization_df["target"] = normalization_df["target"].str.upper()

        # Build Ground Truth Maps
        self.gt = kemenkes_df["international_name"].dropna().unique().tolist()
        self.gt_map = dict(zip(kemenkes_df["drug_name"].dropna(), kemenkes_df["international_name"].dropna()))
        self.gt_alias_map = dict(zip(normalization_df["source"].dropna(), normalization_df["target"].dropna()))

        # NEW: Map International Name to its Therapy Subsubclass
        class_df = kemenkes_df.dropna(subset=["international_name", "therapy_subclass"])
        # Assuming 'class_df' also contains the 'id' column
        self.gt_map = dict(zip(
            class_df["international_name"], 
            zip(class_df["id"], class_df["therapy_subclass"])
        ))

        self.admin_keywords = admin_df["keyword"].dropna().unique().tolist()

    # --- 3. Parsing and Preprocessing ---
    @classmethod
    def _preprocess_string(cls, raw_med):
        clean_name = cls.JML_PATTERN.sub("", raw_med)
        clean_name = cls.INSTR_PATTERN.sub("", clean_name)
        clean_name = clean_name.upper()
        clean_name = cls.SEP_PATTERN.sub(' ', clean_name)
        clean_name = cls.PACKAGING_PATTERN.sub('', clean_name)
        clean_name = cls.DOSAGE_PATTERN.sub('', clean_name)
        clean_name = cls.NUMBER_PATTERN.sub('', clean_name)
        clean_name = cls.WS_PATTERN.sub(' ', clean_name).strip()
        return clean_name

    # --- 4. Matching Logic ---
    def match_medication(self, drug_clean):
        if not drug_clean or drug_clean in self.GARBAGE:
            return None

        # TIER 1: Prefix / Exact Checks
        for truth in self.gt:
            if drug_clean.startswith(truth): return truth
        for source, target in self.gt_map.items():
            if drug_clean.startswith(source): return target
        for source, target in self.gt_alias_map.items():
            if drug_clean.startswith(source): return target

        # TIER 2-4: Fuzzy Matches
        best_gt = process.extractOne(drug_clean, self.gt, scorer=fuzz.token_set_ratio)
        if best_gt and best_gt[1] >= self.FUZZY_THRESHOLD: return best_gt[0]

        best_indo = process.extractOne(drug_clean, self.gt_map.keys(), scorer=fuzz.token_set_ratio)
        if best_indo and best_indo[1] >= self.FUZZY_THRESHOLD: return self.gt_map[best_indo[0]]

        best_alias = process.extractOne(drug_clean, self.gt_alias_map.keys(), scorer=fuzz.token_set_ratio)
        if best_alias and best_alias[1] >= self.FUZZY_THRESHOLD: return self.gt_alias_map[best_alias[0]]

        # TIER 5: Admin / Non-Medication Items
        for keyword in self.admin_keywords:
            if keyword in drug_clean: return "Admin"

        best_admin = process.extractOne(drug_clean, self.admin_keywords, scorer=fuzz.token_set_ratio)
        if best_admin and best_admin[1] >= self.FUZZY_THRESHOLD: return "Admin"

        # TIER 6: Unmatched
        return "Unhandled"

    # --- 5. Main Processing Function ---
    def process_record(self, drug_name) -> tuple:
            """Returns a tuple: (standardized_name, therapy_class)."""
            if not isinstance(drug_name, str):
                return None, "Unknown Class"

            raw_med = drug_name.strip()
            if not raw_med:
                return None, "Unknown Class"


            clean_name = self._preprocess_string(raw_med)
            
            if clean_name in self._cache:
                return self._cache[clean_name]

            if not clean_name or clean_name in self.GARBAGE:
                result = (None, "Unknown Class")
                return result

            standardized_name = self.match_medication(clean_name)

            # Determine the class based on the matched standardized name
            if standardized_name in self.gt_map:
                med_id, med_type = self.gt_map[standardized_name]
            elif standardized_name == "Admin":
                med_id = None
                med_type = "Admin"
            else:
                med_id = None
                med_type = "Unknown Class" # For unhandled/fallback items

            # Fallback to cleaned string if unhandled
            if not standardized_name or standardized_name == "Unhandled":
                standardized_name = clean_name 

            result = (med_id, standardized_name, med_type)
            
            # Save the final result to the cache before returning
            self._cache[clean_name] = result
            
            return result
        
