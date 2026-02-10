"""
train_controller.py
Top-level orchestrator for PHX Local Controller AI training pipeline.
Steps 3–6: Trace processing, feature construction, model training, and output.
"""
import os
import sys
import logging
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Step 3: Trace Processing Engine
# Step 4: Feature Construction
# Step 5: Machine Learning Model
# Step 6: Training Outputs


import pandas as pd
import glob

def load_operations():
    ops_dir = os.path.join(PROJECT_ROOT, 'operations_data')
    all_ops = []
    for csv_path in glob.glob(os.path.join(ops_dir, '*.csv')):
        df = pd.read_csv(csv_path)
        # Defensive: ensure required columns
        required = {'time','icao','operation','airport','flight','runway','ac_type','elev'}
        if not required.issubset(df.columns):
            continue
        # Parse time
        df['time'] = pd.to_datetime(df['time'], errors='coerce', utc=True)
        df = df[df['time'].notna()]
        all_ops.extend(df.to_dict('records'))
    return all_ops

def setup_logger():
    logs_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, 'training_log.txt')
    logger = logging.getLogger('phx_local_controller')
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

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
    if len(ops) == 0:
        raise RuntimeError("No valid operations loaded. Check operations_data CSV schema.")
    print(f"Loaded {len(ops)} operations")
    logger.info(f"Loaded {len(ops)} operations")

    # Import trace_processor and runways
    from scripts.trace_processor import run_trace_processing
    from runways import RUNWAYS
    weather_csv = os.path.join(PROJECT_ROOT, 'weather_data', 'kphx_weather_filtered.csv')
    feature_csv = os.path.join(PROJECT_ROOT, 'logs', 'feature.csv')

    USE_CACHED_FEATURES = False # set True only when debugging
    if USE_CACHED_FEATURES and os.path.exists(feature_csv):
        print("Loading cached features from logs/feature.csv (skipping Steps 3 & 4)...")
        df = pd.read_csv(feature_csv)
        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
        df = df[df['timestamp'].notna()]
        print("Loaded cached features from logs/feature.csv")
    else:
        print("Processing traces and constructing features (Step 3 & 4)...")
        traces = run_trace_processing(ops, logger, RUNWAYS, weather_csv)
        print(f"Processed {sum(len(v) for v in traces.values())} aircraft states with features")
        logger.info(f"Processed {sum(len(v) for v in traces.values())} aircraft states with features")
        # Flatten features for ML
        all_features = []
        for v in traces.values():
            all_features.extend(v)
        # Check if any vertical_rate_fpm is None
        none_count = sum(1 for feat in all_features if feat.get('vertical_rate_fpm') is None)
        if none_count > 0:
            print(f"Warning: {none_count} states have missing vertical_rate_fpm")

        df = pd.DataFrame(all_features)
        # Drop unknown operations to keep labels clean
        df = df[df["operation"].isin(["landing", "takeoff"])]

        REQUIRED_TRACE_COLUMNS = {
            'timestamp', 'runway', 'aircraft_category', 'operation',
            'distance_to_tower_nm', 'altitude_agl_ft',
            'ground_speed_knots', 'heading_deg',
            'wind_along_runway', 'wind_cross_runway',
            'time_of_day', 'runway_alignment_error',
            'weather_tmpf', 'weather_relh',
            'weather_drct', 'weather_sknt'
        }

        missing = REQUIRED_TRACE_COLUMNS - set(df.columns)
        if missing:
            raise RuntimeError(f"Missing required feature columns: {missing}")
        
        df.to_csv(feature_csv, index=False)
        print("Full features saved to logs/feature.csv")
    print("Preparing runway label encoding...")
    # Runway assignment label (categorical)
    RUNWAY_IDS = sorted(r['id'] for r in RUNWAYS)
    runway2idx = {r: i for i, r in enumerate(RUNWAY_IDS)}

    print("Validating runway values in data...")
    # Validate runway values in data
    df = df[df['runway'].notna()]
    unknown = set(df['runway'].unique()) - set(RUNWAY_IDS)
    if unknown:
        raise RuntimeError(f"Unknown runway IDs in data: {unknown}")

    print("Encoding runway labels...")
    df['runway_label'] = df['runway'].map(runway2idx)
    # Active runway config label (binary vector over all runways, ±15min window)
    print("Computing active runway vectors (±15min window)...")
    df['dt'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.sort_values('dt')
    active_vectors = []

    # Vectorized active runway computation (15-min window)
    df = df.sort_values('dt').reset_index(drop=True)
    active_vectors = []

    # Convert timestamps to numeric for faster comparison
    ts_values = df['dt'].values.astype('datetime64[ns]')
    runway_values = df['runway'].values

    # Precompute for each row the start of the 15-min window
    start_window = ts_values - np.timedelta64(15, 'm')

    # Keep a running index of start of window
    start_idx = 0
    N = len(df)

    for i in range(N):
        # Move start_idx forward until df['dt'][start_idx] >= start_window[i]
        while start_idx < N and ts_values[start_idx] < start_window[i]:
            start_idx += 1
        # All rows from start_idx up to i are in the 15-min window
        window_runways = set(runway_values[start_idx:i])
        vec = [1 if r in window_runways else 0 for r in RUNWAY_IDS]
        active_vectors.append(vec)

    df['active_runways'] = active_vectors

    print("Preparing feature columns for ML...")
    # Features for ML
    feature_cols = [
        'distance_to_tower_nm','altitude_agl_ft','ground_speed_knots','heading_deg',
        'wind_along_runway','wind_cross_runway','time_of_day','runway_alignment_error','vertical_rate_fpm',
        'weather_tmpf','weather_relh','weather_drct','weather_sknt', 'operation'
    ]
    # Encode aircraft_category
    print("Encoding aircraft_category features...")
    df['aircraft_category'] = df['aircraft_category'].astype('category')
    for cat in df['aircraft_category'].cat.categories:
        df[f'ac_cat_{cat}'] = (df['aircraft_category'] == cat).astype(int)
        feature_cols.append(f'ac_cat_{cat}')
    # Encode operation
    print("Encoding operation features...")
    df['operation'] = df['operation'].astype('category')
    for op in df['operation'].cat.categories:
        df[f'op_{op}'] = (df['operation'] == op).astype(int)
        feature_cols.append(f'op_{op}')
    feature_cols.remove('operation')

    # Features that may legitimately be missing (ADS-B / weather)
    ALLOW_MISSING = {
        'heading_deg',
        'vertical_rate_fpm',
        'wind_along_runway',
        'wind_cross_runway',
        'weather_tmpf',
        'weather_relh',
        'weather_drct',
        'weather_sknt',
        'runway_alignment_error'
    }

    print("Converting all features to numeric...")
    # Convert all features to numeric, coerce errors
    for col in feature_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # Convert weather_drct to float if possible
    if 'weather_drct' in df:
        df['weather_drct'] = pd.to_numeric(df['weather_drct'], errors='coerce')

    print("Handling missing values...")
    # Handle missing values systematically
    for col in feature_cols:
        if col in ALLOW_MISSING:
            # Add missingness indicator
            miss_col = f"{col}_missing"
            df[miss_col] = df[col].isna().astype(int)
            feature_cols.append(miss_col)

            # Impute with median (computed on available data)
            median = df[col].median()
            if pd.isna(median):
                median = 0.0  # absolute fallback
            df[col] = df[col].fillna(median)
        else:
            # Critical feature: must exist
            df = df[df[col].notna()]

    print("Splitting train/test by day (no leakage)...")
    # Step 5: Train/test split by day (no leakage)
    df['date'] = df['dt'].dt.date
    days = sorted(df['date'].unique())
    split = int(0.8 * len(days))
    train_days, test_days = days[:split], days[split:]
    train_df = df[df['date'].isin(train_days)]
    test_df = df[df['date'].isin(test_days)]
    if train_df.empty or test_df.empty:
        raise RuntimeError("Train or test set is empty after split")
    print(f"Train set: {len(train_df)} rows, Test set: {len(test_df)} rows")
    
    print("Preparing PyTorch tensors and dataloaders...")
    # Prepare tensors
    import torch
    import torch.nn as nn
    import torch.optim as optim

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu') # It will be CPU for this device

    # TensorDatasets & DataLoaders for batching
    train_dataset = torch.utils.data.TensorDataset(
        torch.tensor(train_df[feature_cols].values, dtype=torch.float32),
        torch.tensor(train_df['runway_label'].values, dtype=torch.long)
    )
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=1024, shuffle=True, num_workers=0, pin_memory=False)

    test_dataset = torch.utils.data.TensorDataset(
        torch.tensor(test_df[feature_cols].values, dtype=torch.float32),
        torch.tensor(test_df['runway_label'].values, dtype=torch.long)
    )
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=1024, shuffle=False, num_workers=0, pin_memory=False)

    print("Defining neural network model...")
    # Model
    class FeedforwardNN(nn.Module):
        def __init__(self, in_dim, out_dim):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, 64), nn.ReLU(),
                nn.Linear(64, 32), nn.ReLU(),
                nn.Linear(32, out_dim)
            )
        def forward(self, x):
            return self.net(x)

    model = FeedforwardNN(len(feature_cols), len(RUNWAY_IDS)).to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()

    print("Starting training loop...")
    # Training loop
    for epoch in range(10):
        model.train()
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            out = model(X_batch)
            loss = criterion(out, y_batch)
            loss.backward()
            optimizer.step()
        LOG_EVERY = 1
        if epoch % LOG_EVERY == 0:
            print(f"Epoch {epoch}: last batch loss={loss.item():.4f}")

    print("Evaluating model on test set...")
    # Evaluation
    model.eval()
    all_preds, all_labels, all_confs = [], [], []
    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            logits = model(X_batch)
            preds = torch.argmax(torch.softmax(logits, dim=1), dim=1)
            confs = torch.max(torch.softmax(logits, dim=1), dim=1)[0]
            all_preds.append(preds)
            all_labels.append(y_batch)
            all_confs.append(confs)

    y_test_tensor = torch.cat(all_labels)
    preds_tensor = torch.cat(all_preds)
    confs_tensor = torch.cat(all_confs)

    correct = (preds_tensor == y_test_tensor).sum().item()
    acc = correct / len(y_test_tensor)
    uncertain = (confs_tensor < 0.6).sum().item()

    print(f"Test accuracy: {acc*100:.2f}%")
    print(f"Uncertain outputs: {uncertain} / {len(y_test_tensor)}")
    logger.info(f"Test accuracy: {acc*100:.2f}%")
    logger.info(f"Uncertain outputs: {uncertain} / {len(y_test_tensor)}")

    print("Saving model and label mapping...")
    # Save model
    models_dir = os.path.join(PROJECT_ROOT, 'models')
    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, 'phx_local_controller.pt')
    torch.save(model.state_dict(), model_path)
    
    import json
    mapping_path = os.path.join(models_dir, 'runway_label_map.json')
    with open(mapping_path, 'w') as f:
        json.dump(runway2idx, f, indent=2)

    logger.info(f"Runway label map saved to {mapping_path}")

    print(f"Model saved to {model_path}")
    logger.info(f"Model saved to {model_path}")
    # Save a small CSV sample
    print("Saving ML sample to logs/ml_sample.csv...")
    sample = test_df.head(50)
    sample.to_csv(os.path.join(PROJECT_ROOT, 'logs', 'ml_sample.csv'), index=False)
    print("ML sample saved to logs/ml_sample.csv")

if __name__ == "__main__":
    main()
