from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from core.recommendation_system import DrugRecommender

import pandas as pd
from typing import Tuple
from core.prepare_data import prepare_df

@dataclass
class ClinicMetrics:
    db_name: str
    name_coverage: float
    volume_coverage: float
    recommendation_coverage: float
    recommendation_quality: float  

def fetch_name_coverage(conn) -> float:
    query = """
        SELECT 
            COUNT(id) AS total_products,
            COUNT(CASE WHEN kemenkes_id IS NOT NULL AND kemenkes_id != '' THEN id END) AS covered_products
        FROM pharmacy_products
    """
    cursor = conn.cursor()
    cursor.execute(query)
    row = cursor.fetchone()
    
    return float(row.covered_products) / float(row.total_products) if row and row.total_products > 0 else 0.0

def fetch_volume_coverage(conn) -> float:
    # INNER JOIN is faster, and we only need rows that actually exist in patient_medications
    query = """
        SELECT 
            COUNT(pm.id) AS total_volume,
            COUNT(CASE WHEN pp.kemenkes_id IS NOT NULL AND pp.kemenkes_id != '' THEN pm.id END) AS covered_volume
        FROM patient_medications pm
        JOIN pharmacy_products pp ON pm.pharmacy_product_id = pp.id
    """
    cursor = conn.cursor()
    cursor.execute(query)
    row = cursor.fetchone()
    
    return float(row.covered_volume) / float(row.total_volume) if row and row.total_volume > 0 else 0.0

def fetch_recommendation_quality(conn, recommender:  DrugRecommender, test_size=200, max_history=100000) -> Tuple[float, float]:
    """
    Zero-leakage static evaluation aligned with the new Task 3 bulk recommendation architecture.
    Returns: (recommendation_coverage, useless_pct)
    """
    
    # 1. Fetch capped history matching Task 3's query EXACTLY, just limited for speed
    query = f"""
        WITH RecentHistory AS (
            SELECT TOP {max_history}
                v.id,
                v.visit_date,
                v.doctor_id,
                DATEDIFF(YEAR, p.birth_date, v.visit_date) AS age,

                vs.working_icd10_id AS diagnose,
                vod.icd10_id AS secondary_diagnose,

                pp.id AS pharmacy_product_id,
                pp.name AS pharmacy_product_name,
                pp.kemenkes_id

            FROM visits AS v

            JOIN patients AS p
                ON p.id = v.patient_id

            JOIN visit_services AS vs
                ON vs.visit_id = v.id
                AND vs.visit_service_type_id <> 13

            LEFT JOIN visit_other_diagnoses AS vod
                ON vod.visit_service_id = vs.id

            JOIN visit_prescriptions AS vp
                ON vp.visit_service_id = vs.id

            JOIN patient_medications AS pm
                ON pm.visit_prescription_id = vp.id

            JOIN pharmacy_products AS pp
                ON pp.id = pm.pharmacy_product_id

            WHERE v.doctor_id IS NOT NULL
            AND p.birth_date IS NOT NULL
            AND v.visit_date IS NOT NULL
            AND pp.kemenkes_id IS NOT NULL
            AND pp.kemenkes_id != ''

            ORDER BY v.visit_date DESC
        )

        SELECT *
        FROM RecentHistory
        ORDER BY visit_date ASC;
    """
    raw_df = pd.read_sql(query, conn)
    
    df = prepare_df(raw_df)

    if len(df) < 50:
        return 0.0, 1.0

    # 3. Each row is already one visit after prepare_df()
    visit_actuals = df[
        [
            "id",
            "visit_date",
            "doctor_id",
            "diagnose",
            "age_bucket",
            "kemenkes_id_list",
        ]
    ].copy()

    total_visits = len(visit_actuals)

    actual_test_size = (
        test_size
        if total_visits > test_size
        else max(1, int(total_visits * 0.2))
    )

    # 4. Chronological train/test split
    test_visits = visit_actuals.iloc[-actual_test_size:].copy()

    cutoff_date = test_visits.iloc[0]["visit_date"]

    train_df = df[
        df["visit_date"] < cutoff_date
    ].copy()

    # 5. Dimensions required by bulk recommender
    test_icd10s = test_visits["diagnose"].unique().tolist()
    test_doctors = test_visits["doctor_id"].unique().tolist()
    test_age_buckets = test_visits["age_bucket"].unique().tolist()

    # 6. Generate recommendations using TRAINING DATA ONLY
    recs_df = recommender.create_recommendations(
        train_df,
        icd10_list=test_icd10s,
        doctor_list=test_doctors,
        age_bucket_list=test_age_buckets,
    )

    if not recs_df.empty:
        rec_dict = (
            recs_df
            .groupby(
                ["doctor_id", "diagnose", "age_bucket"]
            )["kemenkes_id"]
            .apply(set)
            .to_dict()
        )
    else:
        rec_dict = {}

    covered_count = 0
    useless_count = 0

    # 7. Evaluate each test visit
    for _, row in test_visits.iterrows():

        scenario_key = (
            row["doctor_id"],
            row["diagnose"],
            row["age_bucket"],
        )

        actual_meds = set(row["kemenkes_id_list"])

        recommended_meds = rec_dict.get(scenario_key, set())

        if recommended_meds:
            covered_count += 1

        if not actual_meds.intersection(recommended_meds):
            useless_count += 1

    coverage_pct = covered_count / actual_test_size
    useless_pct = useless_count / actual_test_size

    return coverage_pct, useless_pct

def task_4_diagnostics_evaluation(conn, recommender: DrugRecommender, db_name: str) -> ClinicMetrics:
    """
    Evaluates a single clinic using its active database connection.
    Returns a dense ClinicMetrics object containing raw values.
    """
    # 1. Coverage by Name (Fetch from DB using conn)
    name_cov = fetch_name_coverage(conn)
        
    # 2. Coverage by Volume (Fetch from DB using conn)
    vol_cov = fetch_volume_coverage(conn)
        
    # 4. Recommendation Quality / Last 4 Weeks Useless % (Fetch from DB)
    rec_cov, useless_pct = fetch_recommendation_quality(conn, recommender)
    rec_qual = 1 - useless_pct
    return ClinicMetrics(
        db_name=db_name,
        name_coverage=name_cov,
        volume_coverage=vol_cov,
        recommendation_coverage=rec_cov,
        recommendation_quality=rec_qual
    )