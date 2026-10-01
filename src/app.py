import streamlit as st
import os
import datetime
import json
import pandas as pd
import subprocess
import time
import sys

st.set_page_config(page_title="Clinic Pipeline Diagnostics", layout="wide")

st.title("Clinic Pipeline Diagnostics Dashboard")

# 1. Setup paths based on today's date
timestamp = datetime.datetime.now().strftime("%Y%m%d")
failed_file_path = f"logs/failed_clinics_{timestamp}.txt"
logs_dir = "logs"

# Ensure logs directory exists
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

# --- TOP SECTION: PIPELINE CONTROLS ---
st.header("1. Pipeline Controls")

col1, col2 = st.columns([1, 3])

with col1:
    # Check if a failed clinics file exists for TODAY
    if os.path.exists(failed_file_path):
        run_btn = st.button("▶ Run Pipeline (Retry Failed Clinics)", type="primary")
        cmd = [sys.executable, "src/tasks.py", "--failed_run_file", failed_file_path]
        st.caption(f"Will retry clinics listed in `failed_clinics_{timestamp}.txt`")
    else:
        run_btn = st.button("▶ Run Pipeline (All Clinics)", type="primary")
        cmd = [sys.executable, "src/tasks.py"]
        st.caption("Will run the master list of all clinics.")

with col2:
    st.code(" ".join(cmd), language="bash")

# --- TERMINAL OUTPUT ---
if run_btn:
    st.subheader("Terminal Output")
    terminal_container = st.empty()

    with st.spinner("Pipeline is running..."):
        # Track start time
        start_time = time.time()
        
        # Run the script and capture output live
        process = subprocess.run(cmd)
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        
        if process.returncode == 0:
            st.success(f"Pipeline execution finished successfully in {elapsed_time:.2f} seconds!")
        else:
            st.error(f"Pipeline finished with exit code {process.returncode} after {elapsed_time:.2f} seconds.")
            
        time.sleep(2) # Brief pause so the user can see the processing time message
        st.rerun() # Refresh the UI to load the newly generated JSON report

st.divider()

# --- BOTTOM SECTION: DIAGNOSTICS DASHBOARD ---
st.header("2. Evaluation Report")

# Find all CSV reports in the logs folder
available_reports = [f for f in os.listdir(logs_dir) if f.startswith("raw_metrics_") and f.endswith(".csv")]
available_reports.sort(reverse=True) # Newest first

def evaluate_clinic(row):
    """Applies thresholds to a row and returns a tuple: (score, primary_issue_dict, all_large_warnings_count)"""
    score = 0
    warnings = []
    
    # 1. Name Coverage Rules
    if pd.isna(row['name_coverage']):
        warnings.append({"metric": "Name Coverage", "severity": "LARGE", "value": "NULL"})
        score += 5
    elif row['name_coverage'] < 0.25:
        warnings.append({"metric": "Name Coverage", "severity": "LARGE", "value": row['name_coverage']})
        score += 5
    elif row['name_coverage'] <= 0.40:
        warnings.append({"metric": "Name Coverage", "severity": "SMALL", "value": row['name_coverage']})
        score += 1
        
    # 2. Volume Coverage Rules
    if pd.isna(row['volume_coverage']):
        warnings.append({"metric": "Volume Coverage", "severity": "LARGE", "value": "NULL"})
        score += 5
    elif row['volume_coverage'] < 0.60:
        warnings.append({"metric": "Volume Coverage", "severity": "LARGE", "value": row['volume_coverage']})
        score += 5
    elif row['volume_coverage'] <= 0.70:
        warnings.append({"metric": "Volume Coverage", "severity": "MEDIUM", "value": row['volume_coverage']})
        score += 3
    elif row['volume_coverage'] <= 0.80:
        warnings.append({"metric": "Volume Coverage", "severity": "SMALL", "value": row['volume_coverage']})
        score += 1
        
    # 3. Recommendation Coverage Rules
    if pd.isna(row['recommendation_coverage']):
        warnings.append({"metric": "Rec Coverage", "severity": "LARGE", "value": "NULL"})
        score += 5
    elif row['recommendation_coverage'] <= 0.65:
        warnings.append({"metric": "Rec Coverage", "severity": "LARGE", "value": row['recommendation_coverage']})
        score += 5
    elif row['recommendation_coverage'] <= 0.75:
        warnings.append({"metric": "Rec Coverage", "severity": "MEDIUM", "value": row['recommendation_coverage']})
        score += 3
    elif row['recommendation_coverage'] <= 0.85:
        warnings.append({"metric": "Rec Coverage", "severity": "SMALL", "value": row['recommendation_coverage']})
        score += 1
        
    # 4. Recommendation Quality (Useful %) Rules
    if pd.isna(row['recommendation_quality']):
        warnings.append({"metric": "Rec Quality (Useful)", "severity": "LARGE", "value": "NULL"})
        score += 5
    elif row['recommendation_quality'] <= 0.80:
        warnings.append({"metric": "Rec Quality (Useful)", "severity": "LARGE", "value": row['recommendation_quality']})
        score += 5
    elif row['recommendation_quality'] <= 0.90:
        warnings.append({"metric": "Rec Quality (Useful)", "severity": "MEDIUM", "value": row['recommendation_quality']})
        score += 3
    elif row['recommendation_quality'] <= 0.95:
        warnings.append({"metric": "Rec Quality (Useful)", "severity": "SMALL", "value": row['recommendation_quality']})
        score += 1

    primary_issue = warnings[0] if warnings else None
    large_warnings = sum(1 for w in warnings if w['severity'] == 'LARGE')
    
    return pd.Series([score, primary_issue, large_warnings])


def highlight_metrics(row):
    """Pandas Styler function to color code metrics based on severity thresholds."""
    # Define semi-transparent colors that look good in both light and dark mode
    RED = 'background-color: rgba(255, 75, 75, 0.3)'
    ORANGE = 'background-color: rgba(255, 165, 0, 0.3)'
    YELLOW = 'background-color: rgba(255, 255, 0, 0.3)'
    GREEN = 'background-color: rgba(75, 255, 75, 0.3)'
    
    styles = [''] * len(row)
    
    for i, col in enumerate(row.index):
        val = row[col]
        color = ''
        
        # We only style the metric columns
        if col == 'name_coverage':
            if pd.isna(val) or val < 0.25: color = RED
            elif val <= 0.40: color = YELLOW
            else: color = GREEN
            
        elif col == 'volume_coverage':
            if pd.isna(val) or val < 0.60: color = RED
            elif val <= 0.70: color = ORANGE
            elif val <= 0.80: color = YELLOW
            else: color = GREEN
            
        elif col == 'recommendation_coverage':
            if pd.isna(val) or val <= 0.65: color = RED
            elif val <= 0.75: color = ORANGE
            elif val <= 0.85: color = YELLOW
            else: color = GREEN
            
        elif col == 'recommendation_quality':
            if pd.isna(val) or val <= 0.80: color = RED
            elif val <= 0.90: color = ORANGE
            elif val <= 0.95: color = YELLOW
            else: color = GREEN
            
        styles[i] = color
        
    return styles


if not available_reports:
    st.info("No raw metrics CSV found. Run the pipeline to generate one.")
else:
    selected_report = st.selectbox("Select Report to View:", available_reports, index=0)
    report_path = os.path.join(logs_dir, selected_report)
    
    # Extract the timestamp to check for corresponding failed clinics
    selected_timestamp = selected_report.replace("raw_metrics_", "").replace(".csv", "")
    matching_failed_file = f"logs/failed_clinics_{selected_timestamp}.txt"
    
    # Load and clean data
    df = pd.read_csv(report_path)
    # Deduplicate in case a pipeline restart caused duplicate appended rows for a clinic
    df = df.drop_duplicates(subset=['db_name'], keep='last')
    
    # Apply evaluation logic
    df[['criticality_score', 'primary_issue', 'large_warnings_count']] = df.apply(evaluate_clinic, axis=1)
    
    # Calculate summary stats
    failed_count = 0
    if os.path.exists(matching_failed_file):
        with open(matching_failed_file, 'r') as f:
            failed_count = len([line for line in f if line.strip()])
            
    clinics_with_warnings = len(df[df['criticality_score'] > 0])
    perfect_clinics = len(df[df['criticality_score'] == 0])
    total_large_warnings = int(df['large_warnings_count'].sum())
    
    st.subheader("Summary Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Attempted Clinics", len(df))
    c2.metric("Pipeline Failures", failed_count)
    c3.metric("Perfect Clinics", perfect_clinics)
    c4.metric("Clinics w/ Warnings", clinics_with_warnings)
    c5.metric("Total LARGE Warnings", total_large_warnings)
    
    st.write("") # Spacing
    
    col_crit, col_dense = st.columns([1, 2])
    
    with col_crit:
        st.subheader("Most Critical to Look At")
        
        # Filter for issues and sort by score descending
        df_issues = df[df['criticality_score'] > 0].sort_values(by='criticality_score', ascending=False)
        
        if not df_issues.empty:
            crit_display = []
            # Grab top 15 highest scores
            for _, row in df_issues.head(15).iterrows():
                issue = row['primary_issue']
                # Check if the value is our "NULL" string or a float we can format
                display_value = issue['value'] if isinstance(issue['value'], str) else round(issue['value'], 3)
                
                crit_display.append({
                    "Clinic DB": row['db_name'],
                    "Score": row['criticality_score'],
                    "Primary Metric": issue['metric'],
                    "Severity": issue['severity'],
                    "Value": display_value
                })
            st.dataframe(pd.DataFrame(crit_display), width='stretch', hide_index=True)
        else:
            st.success("No critical warnings to display!")
            
    with col_dense:
        st.subheader("All Enriched Clinic Metrics")
        
        if not df.empty:
            # Prepare clean dense table (drop the helper columns we used for summary)
            dense_df = df.drop(columns=['primary_issue', 'large_warnings_count'])
            # Sort by criticality score descending so worst offenders are on top here too
            dense_df = dense_df.sort_values(by='criticality_score', ascending=False)
            
            # Format floats to percentages for cleaner viewing
            format_dict = {
                'name_coverage': '{:.1%}',
                'volume_coverage': '{:.1%}',
                'recommendation_coverage': '{:.1%}',
                'recommendation_quality': '{:.1%}'
            }
            
            # Apply the style function to the dataframe
            styled_df = (
                dense_df.style
                .apply(highlight_metrics, axis=1)
                .format(format_dict, na_rep="NULL")
            )
            
            st.dataframe(
                styled_df, 
                width='stretch', 
                hide_index=True
            )
        else:
            st.info("No dense data available.")