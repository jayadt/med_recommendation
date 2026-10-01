# Medical Drug Recommendation Pipeline
A Python-based batch processing pipeline that standardizes medication records and generates age- and ICD-10-specific drug recommendations across a multi-tenant SQL Server architecture (1,300+ isolated clinic databases).

The pipeline ensures all isolated tenant databases synchronize with a master national drug registry (Kemenkes) and utilizes fuzzy matching to normalize unstructured prescribing data before generating analytical recommendation tables.

## Installation & Setup
### Prerequisites
**Core Frameworks & Tools:**
- Python 3.12.3
- `pandas`
- `pyodbc`
- `argparse`
- `openpyxl`

ODBC Driver 18 for SQL Server (Must be installed at the OS level)

### 1. Clone & Environment Setup
Open your terminal and run the following commands to create and activate a virtual environment:


```sh
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
venv\scripts\activate

# Activate virtual environment (Mac/Linux)
source venv/bin/activate
```
### 2. Install Dependencies
Install the required packages:

```sh
pip install -r requirements.txt
```

### . Environment Variables & Data Prep
Ensure you have the required base configuration data in the data/ directory:

`data/kemenkes.xlsx`

`data/normalization.xlsx`

`data/admin.xlsx`

###  Running the Pipeline
The pipeline is designed to be executed via the CLI. Because it operates on a Database-per-Tenant architecture, the master script iterates through the fleet of clinic databases sequentially.

### UI Helper (Recommended)

`streamlit run src/app.py`

This web app has buttons to run the tasks below  

### Standard Run
To run the pipeline across all configured clinic databases:

`python run_tasks.py`

### Retry Failed Runs
If the pipeline encounters an error . A text file of failed databases is automatically generated in the logs/ directory.

To re-run the pipeline only for the databases that previously failed:

`python run_tasks.py --failed_run_file logs/failed_clinics_20260928.txt`


## Explanation
### Pipeline Stages
The pipeline executes three sequential tasks per database. If a task fails, the database transaction is rolled back, the error is bubbled up to the master loop, and subsequent tasks for that specific clinic are skipped.

### Task 0: Setup Tables (src.task0): 
setup the tables 

### Task 1: Update Kemenkes (src.task1): 
Synchronizes the clinic's local drug dictionary with the national master list. Uses Temp table staging -> MERGE. Inserts new, updates existing. Never deletes.

### Task 2: Map New Drugs (src.task2): Identifies 
historical drugs lacking a kemenkes_id and applies fuzzy matching via MedicationNormalizer. Uses Batch UPDATE via executemany.

### Task 3: Create Recommendations (src.task3): 
Aggregates historical prescribing patterns grouped by doctor, ICD-10 code, and age bucket to build a recommendation index. Uses TRUNCATE -> Batch INSERT. Nukes and replaces permanent analytics table.

### Task 4: Evaluation Diagnostics (src.task4): 
Runs numbers on evaluation

Logging
The system writes logs to the logs/ directory to maintain an audit trail of multi-tenant execution.

logs/pipeline_run.log : Standard execution log. Contains initialization events, SUCCESS and FAILED markers.

logs/failed_clinics_<date>_.txt : A flat text file containing exactly one database name per line. Generated automatically if any databases fail during a run. Used directly as an input for --failed_run_file.

Project Layout
medical_recommendation_engine/
├── run_tasks.py                  # CLI entrypoint + tenant iteration loop
├── requirements.txt
├── src/                          # Task execution modules
│   ├── task1.py                  # Kemenkes sync logic
│   ├── task2.py                  # Unmapped drug fuzzy matching
│   └── task3.py                  # Recommendation generation & table replacement
├── core/                         # Business logic & AI algorithms
│   ├── normalizer.py             # MedicationNormalizer (fuzzy matching)
│   ├── recommendation_system.py  # DrugRecommender logic
│   └── prepare_data.py           # DataFrame prep, age buckets, top ICD10 extract
├── data/                         # Global reference data (Excel)
│   ├── kemenkes.xlsx

│   ├── normalization.xlsx
│   └── admin.xlsx
└── logs/                         # Audit and failure tracking (Gitignored)
├── pipeline_run.log
└── failed_clinics_*.txt