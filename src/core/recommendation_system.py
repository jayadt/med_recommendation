import numpy as np
import pandas as pd
import itertools

DECAY_HALF_LIFE=365
MIN_SAMPLES=10
THRESHOLD=0.075

class DrugRecommender:
    def __init__(
        self,
    ):        
        self.decay_half_life = DECAY_HALF_LIFE
        self.min_samples = MIN_SAMPLES
        self.threshold = THRESHOLD
     
    @staticmethod   
    def _filter_with_smart_fallback(df, icd10, doctor_name="all", patient_age_bucket=None, min_samples=10, max_days=None):
        base_df = df.copy()


        # 0. Date constraint
        if max_days is not None:
            cutoff = base_df['visit_date'].max() - pd.Timedelta(days=max_days)
            base_df = base_df[base_df['visit_date'] >= cutoff]

        if len(base_df) == 0: return base_df

        # Feature Engineering
        # ==========================================
        # LEVEL 1: Hyper-Specific (Doc + ICD10 + Age)
        # ==========================================
        mask_l1 = (base_df["diagnose"] == icd10) & (base_df["age_bucket"] == patient_age_bucket)
        if doctor_name != "all":
            mask_l1 &= (base_df["doctor_id"] == doctor_name)

        level_1 = base_df[mask_l1]
        if len(level_1) >= min_samples:
            return level_1

        # ==========================================
        # LEVEL 2: Drop Doctor (Any Doc + ICD10 + Age)
        # ==========================================
        mask_l2 = (base_df["diagnose"] == icd10) & (base_df["age_bucket"] == patient_age_bucket)
        level_2 = base_df[mask_l2]
        if len(level_2) >= min_samples:
            return level_2

        # ==========================================
        # LEVEL 3: Drop Age (Any Doc + ICD10) -> The old baseline
        # ==========================================
        level_3 = base_df[base_df["diagnose"] == icd10]
        return level_3

    @staticmethod
    def _apply_rank_decay(df, half_life):
        """
        Applies an exponential decay weight based on recency.
        half_life: the number of rows it takes for the weight to drop by 50%.
        """
        if len(df) == 0:
            return df
        df = df.copy()
        
        ranks = np.arange(len(df))
        # Weight formula: 0.5 ^ (rank / half_life)
        df.loc[:,'weight'] = 0.5 ** (ranks / half_life)
        return df

    @staticmethod
    def _calc_confidence(mask, weights=None):
        """Helper to calculate mean or weighted mean."""
        if weights is None or "weight" not in weights:
            return mask.mean()
        # Weighted mean: sum(mask * weight) / sum(weight)
        return (mask * weights["weight"]).sum() / weights["weight"].sum()

    def _calculate_medication_confidences(self, subset, column):

        if len(subset) == 0:
            return []

        weights = subset[["weight"]] if "weight" in subset.columns else None

        unique_medications = set(
            medication
            for medications in subset[column]
            for medication in medications
            if pd.notna(medication)
        )

        results = []

        for medication in unique_medications:
            medication_mask = subset[column].map(
                lambda x: medication in x
            )

            confidence = self._calc_confidence(
                medication_mask,
                weights
            )

            results.append({
                "medication": medication,
                "confidence": confidence
            })

        return results

    def get_recommendations(self, subset, max_drugs=5):

        confidence_results = self._calculate_medication_confidences(
            subset,
            "kemenkes_id_list"
        )

        valid_drugs = [
            item
            for item in confidence_results
            if item["confidence"] >= self.threshold
        ]

        valid_drugs.sort(
            key=lambda x: x["confidence"],
            reverse=True
        )

        return [
            item["medication"]
            for item in valid_drugs[:max_drugs]
        ]

    # Evaluation
    def get_unmapped_recommendations(self, subset):

        confidence_results = self._calculate_medication_confidences(
            subset,
            "unmapped_id_list"
        )

        confidence_results.sort(
            key=lambda x: x["confidence"],
            reverse=True
        )

        return confidence_results

    def fit_predict(self, train_df, target_icd10, target_doctor, target_age_bucket):
        # 1. Filter with fallback
        subset = self._filter_with_smart_fallback(
            train_df,
            icd10=target_icd10,
            doctor_name=target_doctor,
            patient_age_bucket=target_age_bucket,
            min_samples=self.min_samples
        )

        # 2. Apply weights
        if self.decay_half_life:
            subset = self._apply_rank_decay(subset, half_life=self.decay_half_life)

        # 3. Calculate and return
        return self.get_recommendations(subset)
    
    def create_recommendations(
        self,
        train_df,
        icd10_list,
        doctor_list,
        age_bucket_list
    ):
        """
        Generate recommendations for every doctor × diagnosis × age combination
        and return a flattened DataFrame ready to be pushed to SQL.
        """

        results = []

        combinations = itertools.product(
            doctor_list,
            icd10_list,
            age_bucket_list
        )

        for doctor, icd10, age in combinations:

            recommendations = self.fit_predict(
                train_df=train_df,
                target_icd10=icd10,
                target_doctor=doctor,
                target_age_bucket=age
            )

            if not recommendations:
                continue

            for rank, drug_id in enumerate(recommendations, start=1):
                results.append({
                    "doctor_id": doctor,
                    "diagnose": icd10,
                    "age_bucket": age,
                    "kemenkes_id": drug_id,
                    "rank_order": rank
                })

        if not results:
            return pd.DataFrame(columns=[
                "doctor_id",
                "diagnose",
                "age_bucket",
                "kemenkes_id",
                "rank_order"
            ])

        return pd.DataFrame(results)
