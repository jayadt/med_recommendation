import re
import pandas as pd
from collections import defaultdict

from core.normalizer import MedicationNormalizer

PEDIATRIC = 1
ADULT_SENIOR = 2
UNKNOWN = -1

def get_age_bucket_list():
    return [PEDIATRIC, ADULT_SENIOR]


def get_age_bucket(age_val):
    if pd.isna(age_val) or age_val == -1:
        return UNKNOWN

    age_val = float(age_val)

    if age_val < 12:
        return PEDIATRIC

    return ADULT_SENIOR

def prepare_df(df):

    df = (
        df.groupby(
            ["id", "visit_date", "doctor_id", "age", "diagnose"],
            dropna=False,
            as_index=False
        )
        .agg(
            secondary_diagnoses=(
                "secondary_diagnose",
                lambda x: x.dropna().unique().tolist()
            ),
            medication_data=(
                "pharmacy_product_name",
                lambda x: x.tolist()
            ),
            medication_ids=(
                "pharmacy_product_id",
                lambda x: x.tolist()
            ),
            kemenkes_ids=(
                "kemenkes_id",
                lambda x: x.tolist()
            )
        )
    )

    df = df.dropna(subset=["diagnose"])

    df["visit_date"] = pd.to_datetime(df["visit_date"])
    df = df.sort_values("visit_date").reset_index(drop=True)

    df["age_bucket"] = df["age"].apply(get_age_bucket)

    def split_medications(row):
        kemenkes_ids = []
        unmapped_ids = []
        unmapped_names = []

        for product_id, product_name, kemenkes_id in zip(
            row["medication_ids"],
            row["medication_data"],
            row["kemenkes_ids"]
        ):
            if pd.notna(kemenkes_id) and kemenkes_id != -999:
                kemenkes_ids.append(kemenkes_id)
            else:
                if pd.notna(product_id):
                    unmapped_ids.append(product_id)

                if pd.notna(product_name):
                    unmapped_names.append(product_name)

        return kemenkes_ids, unmapped_ids, unmapped_names

    (
        df["kemenkes_id_list"],
        df["unmapped_id_list"],
        df["unmapped_name_list"],
    ) = zip(*df.apply(split_medications, axis=1))

    return df

def extract_top_icd10s(df, num=20):
    return df["diagnose"].value_counts().head(num).index.tolist()