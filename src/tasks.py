import argparse
import os
import datetime
import logging
import pandas as pd
import pyodbc
import warnings
import csv
import time  

from core.normalizer import MedicationNormalizer
from core.recommendation_system import DrugRecommender
from task0 import task_0_setup_tables
from task1 import task_1_update_kemenkes
from task2 import task_2_map_new_drugs
from task3 import task_3_create_recommendations
from task4 import task_4_diagnostics_evaluation, ClinicMetrics

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

warnings.filterwarnings(
    "ignore", 
    category=UserWarning, 
    message="^pandas only supports SQLAlchemy connectable.*"
)

# Day-based timestamp
timestamp = datetime.datetime.now().strftime("%Y%m%d")

# Set up logging to append to a daily log file
logging.basicConfig(
    filename=f'logs/pipeline_run_{timestamp}.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

BASE_CONN_STR = (
    "DRIVER={{ODBC Driver 18 for SQL Server}};"
    "SERVER=localhost;"
    "DATABASE={db_name};"
    "UID=DoctorTool_Dev;"
    "PWD=123456;"
    "TrustServerCertificate=yes;"
)

def get_clinic_databases(conn):
    query = """
        SELECT name FROM sys.databases 
    """
    result = conn.execute(query)
    # return ["drtoolisi_dev", "drtoolisi_devfake"]
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run drug recommendations pipeline across clinics.")
    parser.add_argument(
        '--failed_run_file',
        type=str,
        help="Path to a text file containing a list of failed databases (one per line) to retry."
    )
    args = parser.parse_args()

    # 1. Determine which databases to process
    if args.failed_run_file:
        if os.path.exists(args.failed_run_file):
            with open(args.failed_run_file, 'r') as f:
                clinic_dbs = [line.strip() for line in f.readlines() if line.strip()]
            print(f"Loaded {len(clinic_dbs)} databases to retry from {args.failed_run_file}")
        else:
            print(f"Error: The file {args.failed_run_file} does not exist.")
            exit(1)
    else:
        clinic_dbs = get_clinic_databases()
        print(f"Loaded {len(clinic_dbs)} databases from master list.")

    if not clinic_dbs:
        print("No databases to process. Exiting.")
        exit(0)

    # 2. Initialize models
    print("Initializing models and loading global data...")
    kemenkes_df = pd.read_excel('data/kemenkes.xlsx')
    normalization_df = pd.read_excel('data/normalization.xlsx')
    admin_df = pd.read_excel('data/admin.xlsx')

    normalizer = MedicationNormalizer(kemenkes_df, normalization_df, admin_df)
    recommender = DrugRecommender()

    failed_clinics = []

    # 3. Setup Daily CSV (Write header ONLY if it's the first run of the day)
    raw_metrics_file = f"logs/raw_metrics_{timestamp}.csv"
    if not os.path.exists(raw_metrics_file):
        with open(raw_metrics_file, 'w', newline='') as f:
            writer = csv.writer(f)
            # Added processing_time_sec to header
            writer.writerow(['db_name', 'name_coverage', 'volume_coverage', 'recommendation_coverage', 'recommendation_quality', 'processing_time_sec'])
            
    print(f"Metrics will be appended to: {raw_metrics_file}")
    print("Starting pipeline execution...")

    # 4. Loop through target databases
    for db_name in clinic_dbs:
        print(f"Processing {db_name}...")
        conn_str = BASE_CONN_STR.format(db_name=db_name)
        start_time = time.time()  # Start tracking latency
        
        try:
            conn = pyodbc.connect(conn_str)
            
            task_0_setup_tables(conn)
            task_1_update_kemenkes(conn, kemenkes_df)            
            task_2_map_new_drugs(conn, normalizer, force_recalculate=False)
            task_3_create_recommendations(conn, recommender)
            
            clinic_metrics = task_4_diagnostics_evaluation(conn, recommender, db_name)
            
            processing_time = round(time.time() - start_time, 2)  # Calculate success latency
            
            # APPEND-ORIENTED SAVE
            with open(raw_metrics_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    clinic_metrics.db_name,
                    clinic_metrics.name_coverage,
                    clinic_metrics.volume_coverage,
                    clinic_metrics.recommendation_coverage,
                    clinic_metrics.recommendation_quality,
                    processing_time  # Save latency
                ])
            
            logging.info(f"SUCCESS: {db_name} (Time: {processing_time}s)")
            
        except Exception as e:
            processing_time = round(time.time() - start_time, 2)  # Calculate failure latency
            logging.error(f"FAILED: {db_name} - Error: {e} (Time: {processing_time}s)")
            failed_clinics.append(db_name)
            
        finally:
            if 'conn' in locals():
                try:
                    conn.close()
                except:
                    pass
                
    # 5. Handle Failures & Output
    success_count = len(clinic_dbs) - len(failed_clinics)
    print(f"\nRun complete. {success_count} succeeded, {len(failed_clinics)} failed.")

    # 7. Update the Failed Clinics file
    failed_file_path = f"logs/failed_clinics_{timestamp}.txt"
    if failed_clinics:
        # Overwrite the file with only the current remaining failures
        with open(failed_file_path, 'w') as f:
            for db in failed_clinics:
                f.write(f"{db}\n")
                
        print(f"Remaining failed databases saved to: {failed_file_path}")
        print(f"To retry, run:\npython run_tasks.py --failed_run_file {failed_file_path}")
    else:
        # If there are 0 failures, delete the file if it exists from a previous run today
        if os.path.exists(failed_file_path):
            os.remove(failed_file_path)
            print("All clinics have been processed successfully! Failed clinics file cleared.")