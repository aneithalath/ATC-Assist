"""
Filter all operations CSV files in operations_data/ to only contain PHX (KPHX) airport operations and required columns.

Usage:
    # Activate virtual environment (Windows)
    venv\Scripts\activate

    # Install dependencies if missing
    pip install pandas

    # Run the script
    python scripts/filter_operations_phx.py
"""
import os
import pandas as pd

# Directory containing the CSV files
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'operations_data')
REQUIRED_COLUMNS = [
    'time',
    'icao',
    'operation',
    'airport',
    'flight',
    'runway',
    'ac_type',
    'elev',
]
PHX_CODES = {'PHX', 'KPHX'}

def process_file(filepath):
    try:
        df = pd.read_csv(filepath, dtype=str)
        orig_count = len(df)
        # Defensive: lowercase columns
        df.columns = [c.strip() for c in df.columns]
        # Only keep required columns that exist
        keep_cols = [col for col in REQUIRED_COLUMNS if col in df.columns]
        df = df[keep_cols]
        # Drop rows with missing or null icao
        df = df[df['icao'].notna() & (df['icao'].str.strip() != '')]
        # Convert icao to lowercase
        df['icao'] = df['icao'].str.lower()
        # Defensive: airport field may have whitespace or case issues
        df['airport'] = df['airport'].str.strip().str.upper()
        df = df[df['airport'].isin(PHX_CODES)]
        # Trim whitespace from runway
        if 'runway' in df.columns:
            df['runway'] = df['runway'].astype(str).str.strip()
        # Parse time as datetime, drop rows with invalid time
        df['time'] = pd.to_datetime(df['time'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
        df = df[df['time'].notna()]
        # Drop rows where time < 00:02:00 or time > 23:58:00
        # Extract time part as string (after datetime conversion)
        df_time_str = df['time'].dt.strftime('%H:%M:%S')
        mask = (df_time_str >= '00:02:00') & (df_time_str <= '23:58:00')
        df = df[mask]
        # Write back to same file, index=False
        df.to_csv(filepath, index=False)
        print(f"{os.path.basename(filepath)}: {orig_count} -> {len(df)} rows")
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        raise

def main():
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.csv'):
            fpath = os.path.join(DATA_DIR, fname)
            process_file(fpath)

if __name__ == "__main__":
    main()
