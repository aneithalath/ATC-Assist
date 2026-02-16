import pandas as pd
from datetime import datetime
import sys

input_path = 'weather_data/kphx_weather.csv'
output_path = 'weather_data/kphx_weather_filtered.csv'

# Define allowed dates as strings
allowed_dates = [
    '2025-08-01',
    '2025-09-01',
    '2025-10-01',
    '2025-11-01',
    '2025-12-01',
    '2026-01-01',
]

try:
    df = pd.read_csv(input_path, dtype=str)
    print(f"Rows before filtering: {len(df)}")
    df['valid'] = pd.to_datetime(df['valid'], errors='coerce')
    # Only keep rows where the date part of 'valid' is in allowed_dates
    df_filtered = df[df['valid'].dt.strftime('%Y-%m-%d').isin(allowed_dates)]
    print(f"Rows after filtering: {len(df_filtered)}")
    df_filtered.to_csv(output_path, index=False)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
