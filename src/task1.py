import pandas as pd
import pyodbc

def task_1_update_kemenkes(conn: pyodbc.Connection, kemenkes_df: pd.DataFrame):
    """
    Creates or updates the Kemenkes table using a staging -> MERGE approach.
    
    - New IDs are inserted.
    - Existing IDs are updated.
    - IDs are never modified.
    - Names are not modified unless explicitly included in the UPDATE.
    - Deletes are avoided; use is_inactive instead.
    """
    cursor = conn.cursor()
    
    try:
        # 1. Safely create temporary staging table
        # Added PRIMARY KEY to speed up the MERGE statement
        cursor.execute("""
            IF OBJECT_ID('tempdb..#kemenkes_stg') IS NOT NULL 
                DROP TABLE #kemenkes_stg;
                
            CREATE TABLE #kemenkes_stg (
                id INT PRIMARY KEY,
                drug_name NVARCHAR(255),
                international_name NVARCHAR(255),
                therapy_subclass NVARCHAR(255),
                is_inactive BIT
            );
        """)

        # 2. Prepare data for pyodbc
        # Included is_inactive in the dataframe slice
        kemenkes_df['is_inactive'] = kemenkes_df['is_inactive'].fillna(0).astype(int)
        
        df_clean = kemenkes_df[[
            'id', 'drug_name', 'international_name', 'therapy_subclass', 'is_inactive'
        ]].where(pd.notnull(kemenkes_df), None)
        
        df_clean = df_clean.astype(object)
        df_clean = df_clean.where(pd.notnull(df_clean), None)
        rows = df_clean.values.tolist()

        # 3. Bulk insert into staging table
        cursor.fast_executemany = True
        cursor.executemany(
            """
            INSERT INTO #kemenkes_stg 
            (id, drug_name, international_name, therapy_subclass, is_inactive) 
            VALUES (?, ?, ?, ?, ?)
            """,
            rows
        )

        # 4. Perform MERGE operation
        # Included is_inactive in the update checks and insert
        cursor.execute("""
            MERGE kemenkes AS T
            USING #kemenkes_stg AS S ON T.id = S.id
            WHEN MATCHED AND (
                ISNULL(T.drug_name, '') <> ISNULL(S.drug_name, '') OR
                ISNULL(T.international_name, '') <> ISNULL(S.international_name, '') OR
                ISNULL(T.therapy_subclass, '') <> ISNULL(S.therapy_subclass, '') OR
                ISNULL(T.is_inactive, 0) <> ISNULL(S.is_inactive, 0)
            )
            THEN UPDATE SET 
                T.drug_name = S.drug_name, 
                T.international_name = S.international_name,
                T.therapy_subclass = S.therapy_subclass,
                T.is_inactive = S.is_inactive
            WHEN NOT MATCHED BY TARGET
            THEN INSERT (id, drug_name, international_name, therapy_subclass, is_inactive) 
            VALUES (S.id, S.drug_name, S.international_name, S.therapy_subclass, ISNULL(S.is_inactive, 0));
        """)

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()