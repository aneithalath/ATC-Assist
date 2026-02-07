"""
train_controller.py
Top-level orchestrator for PHX Local Controller AI training pipeline.
Steps 3–6: Trace processing, feature construction, model training, and output.
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Step 3: Trace Processing Engine
# Step 4: Feature Construction
# Step 5: Machine Learning Model
# Step 6: Training Outputs


import pandas as pd
import glob
import importlib.util

def load_operations():
    ops_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'operations_data')
    all_ops = []
    for csv_path in glob.glob(os.path.join(ops_dir, '*.csv')):
        df = pd.read_csv(csv_path)
        # Defensive: ensure required columns
        required = {'time','icao','operation','airport','flight','runway','ac_type','elev'}
        if not required.issubset(df.columns):
            continue
        # Parse time
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        df = df[df['time'].notna()]
        all_ops.extend(df.to_dict('records'))
    return all_ops

def setup_logger():
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, 'training_log.txt')
    logger = logging.getLogger('phx_local_controller')
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path, mode='w')
    fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(fh)
    return logger

def main():
    print("PHX Local Controller AI Training Pipeline")
    logger = setup_logger()
    # Step 3: Load operations and process traces
    print("Loading operations data...")
    ops = load_operations()
    print(f"Loaded {len(ops)} operations")
    logger.info(f"Loaded {len(ops)} operations")
    # Import trace_processor and runways
    trace_mod_path = os.path.join(os.path.dirname(__file__), 'trace_processor.py')
    spec = importlib.util.spec_from_file_location('trace_processor', trace_mod_path)
    trace_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trace_mod)
    runways_path = os.path.join(os.path.dirname(__file__), 'runways.py')
    runways_spec = importlib.util.spec_from_file_location('runways', runways_path)
    runways_mod = importlib.util.module_from_spec(runways_spec)
    runways_spec.loader.exec_module(runways_mod)
    weather_csv = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'weather_data', 'kphx_weather_filtered.csv')
    print("Processing traces and constructing features (Step 3 & 4)...")
    traces = trace_mod.run_trace_processing(ops, logger, runways_mod.RUNWAYS, weather_csv)
    print(f"Processed {sum(len(v) for v in traces.values())} aircraft states with features")
    logger.info(f"Processed {sum(len(v) for v in traces.values())} aircraft states with features")
    # Save a small sample for debug
    sample = []
    for v in traces.values():
        sample.extend(v[:5])
        if len(sample) >= 50:
            break
    pd.DataFrame(sample).to_csv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'feature_sample.csv'), index=False)
    print("Feature construction complete. Sample saved to logs/feature_sample.csv")

if __name__ == "__main__":
    main()
