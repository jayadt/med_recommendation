import pandas as pd
import pyodbc
from core.normalizer import MedicationNormalizer

def task_2_map_new_drugs(
    conn: pyodbc.Connection,
    normalizer: MedicationNormalizer,
    force_recalculate=False
):
    """
    Fetches unmapped drugs, applies fuzzy matching, and updates the database.
    """
    cursor = conn.cursor()

    try:

        # 2. Load unmapped drugs
        if force_recalculate:
            query = "SELECT id, name FROM pharmacy_products"
        else:
            query = "SELECT id, name FROM pharmacy_products WHERE kemenkes_id IS NULL"

        unmapped_drugs = pd.read_sql(query, conn)

        if unmapped_drugs.empty:
            return

        # 3. Apply fuzzy matching
        unmapped_drugs["kemenkes_id"] = unmapped_drugs["name"].apply(
            lambda x: normalizer.process_record(x)[0]
        )

        # 4. Remove rows with no match
        # matched_drugs = unmapped_drugs.dropna(subset=["kemenkes_id"])
        matched_drugs = unmapped_drugs
        if matched_drugs.empty:
            return
        
        # 5. Update database in batches
        rows = [
            (None if pd.isna(kemenkes_id) else kemenkes_id, id_)
            for kemenkes_id, id_ in unmapped_drugs[
                ["kemenkes_id", "id"]
            ].itertuples(index=False, name=None)
        ]

        cursor.fast_executemany = True
        # Make sure the table name matches the one you added the column to!
        cursor.executemany(
            "UPDATE pharmacy_products SET kemenkes_id = ? WHERE id = ?",
            rows
        )
        conn.commit()

    except Exception as e:
        conn.rollback()  
        raise e          
    finally:
        cursor.close()