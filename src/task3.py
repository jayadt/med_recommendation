import pandas as pd
import pyodbc

from core.normalizer import MedicationNormalizer
from core.recommendation_system import DrugRecommender
from core.prepare_data import prepare_df, get_age_bucket_list, extract_top_icd10s


def task_3_create_recommendations(
    conn: pyodbc.Connection,
    recommender: DrugRecommender
):
    """
    Reads patient history and creates drug recommendations
    NUKES the rows of the old table and replaces it.
    
    INDEX & PRIMARY KEY: doctor, ICD10, age group, 
    Extra Column: Kemenkes ID.
    """

    history_query = """
        SELECT
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
        AND v.visit_date IS NOT NULL;
    """

    history_df = pd.read_sql(history_query, conn)
    history_df = prepare_df(history_df)
    
    selected_icd10s = extract_top_icd10s(history_df)

    active_doctors_query = """
        SELECT id
        FROM doctors 
        WHERE is_active = 1
    """ 

    active_doctors = pd.read_sql(active_doctors_query, conn)["id"].tolist()
    age_bucket_list = get_age_bucket_list()

    recommendations_df = recommender.create_recommendations(
        history_df,
        icd10_list=selected_icd10s,
        doctor_list=active_doctors,
        age_bucket_list=age_bucket_list
    )

    # Replace recommendation data
    rows = list(
        recommendations_df.itertuples(index=False, name=None)
    )
    if not rows:
        raise ValueError("No recommendation rows generated")
    cursor = conn.cursor()
    
    try:
        cursor.execute("TRUNCATE TABLE recommendation_table")

        cursor.fast_executemany = True
        cursor.executemany(
            """
            INSERT INTO recommendation_table
            (doctor_id, icd10_id, age_group, kemenkes_id, rank_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()