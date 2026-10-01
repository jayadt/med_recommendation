import pyodbc


def task_0_setup_tables(conn: pyodbc.Connection):
    """
    Checks, sets up, creates, or alters tables required for the drug recommendation pipeline.
    Designed to run weekly; uses IF NOT EXISTS logic to ensure safe, idempotent execution.
    """
    cursor = conn.cursor()
    
    try:
        # 1. Setup kemenkes (Task 1)
        cursor.execute("""
            IF OBJECT_ID('kemenkes', 'U') IS NULL
            BEGIN
                CREATE TABLE kemenkes (
                    id INT PRIMARY KEY,
                    drug_name NVARCHAR(255),
                    international_name NVARCHAR(255),
                    therapy_subclass NVARCHAR(255),
                    is_inactive BIT DEFAULT 0
                );
            END
        """)

        # # 2. Setup age_group (Task 3)
        # cursor.execute("""
        #     IF OBJECT_ID('age_group', 'U') IS NULL
        #     BEGIN
        #         CREATE TABLE age_group (
        #             id INT PRIMARY KEY,
        #             name NVARCHAR(50) NOT NULL,
        #             min_age INT NOT NULL,
        #             max_age INT NOT NULL,
        #             CONSTRAINT CK_age_group_age_range
        #                 CHECK (min_age >= 0 AND max_age >= min_age),
        #             CONSTRAINT UQ_age_group_name
        #                 UNIQUE (name)
        #         );
        #     END
        # """)

        # Seed default age groups if they do not already exist. (Task 3)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1
                FROM age_group
                WHERE id = 1
            )
            BEGIN
                INSERT INTO age_group (id, name, min_age, max_age)
                VALUES (1, 'Pediatric', 0, 11);
            END

            IF NOT EXISTS (
                SELECT 1
                FROM age_group
                WHERE id = 2
            )
            BEGIN
                INSERT INTO age_group (id, name, min_age, max_age)
                VALUES (2, 'Adult/Senior', 12, 999);
            END
        """)

        # 3. Append to existing pharmacy_products (Task 2)
        cursor.execute("""
            IF COL_LENGTH('pharmacy_products', 'kemenkes_id') IS NULL
            BEGIN
                ALTER TABLE pharmacy_products ADD kemenkes_id INT NULL;
            END
        """)

        # 4. Setup recommendation_table (Task 3)
        cursor.execute("""
            IF OBJECT_ID('recommendation_table', 'U') IS NULL
            BEGIN
                CREATE TABLE recommendation_table (
                    doctor_id INT,
                    icd10_id INT,
                    age_group INT,
                    kemenkes_id INT,
                    rank_order INT,
                    PRIMARY KEY (
                        doctor_id,
                        icd10_id,
                        age_group,
                        kemenkes_id,
                        rank_order
                    )
                );
            END
        """)

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()