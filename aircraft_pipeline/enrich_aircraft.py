import pandas as pd
import numpy as np
import os
import random

def load_data():
    # Load cleaned OpenSky data
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    opensky_path = os.path.join(project_root, 'flight_data', 'opensky_phx_clean.parquet')
    df = pd.read_parquet(opensky_path)
    # Fill missing callsign
    df['callsign'] = df['callsign'].fillna('DUMMY')

    # Load ICAO24 to type_code
    icao24_path = os.path.join(project_root, 'flight_data', 'aircraft_data', 'icao24_data.csv')
    icao24_df = pd.read_csv(icao24_path)
    icao24_map = dict(zip(icao24_df['icao24'], icao24_df['typecode']))

    # Load aircraft model dimensions
    aircraft_path = os.path.join(project_root, 'flight_data', 'aircraft_data', 'aircraft_data.csv')
    aircraft_df = pd.read_csv(aircraft_path)
    aircraft_df['FAA_Designator'] = aircraft_df['FAA_Designator'].astype(str)
    aircraft_dim_map = aircraft_df.set_index('FAA_Designator')[['Wingspan_ft_with_winglets_sharklets', 'Length_ft']].to_dict('index')
    return df, icao24_map, aircraft_dim_map

def enrich(df, icao24_map, aircraft_dim_map):
    # Attach aircraft_model
    df['aircraft_model'] = df['icao24'].map(icao24_map).fillna('UNKNOWN_MODEL')
    # Attach dimensions
    wingspan_m = []
    length_m = []
    has_dimensions = []
    for model in df['aircraft_model']:
        dims = aircraft_dim_map.get(model)
        if dims:
            ws_ft = dims['Wingspan_ft_with_winglets_sharklets']
            len_ft = dims['Length_ft']
            ws_m = ws_ft * 0.3048 if pd.notnull(ws_ft) else np.nan
            len_m = len_ft * 0.3048 if pd.notnull(len_ft) else np.nan
            wingspan_m.append(ws_m)
            length_m.append(len_m)
            has_dimensions.append(True)
        else:
            wingspan_m.append(np.nan)
            length_m.append(np.nan)
            has_dimensions.append(False)
    df['wingspan_m'] = wingspan_m
    df['length_m'] = length_m
    df['has_dimensions'] = has_dimensions
    return df

def label_ground_state(df):
    small_threshold = 0.5
    df['is_grounded'] = df['onground']
    df['is_stationary'] = (df['onground']) & (df['velocity'] < small_threshold)
    df['is_likely_taxiing'] = (df['onground']) & (df['velocity'] >= small_threshold)
    return df

def anonymize_callsigns(df):
    # List of fake airline prefixes (3 letters each)
    fake_airlines = [
        "ZET", "QPX", "LVR", "MKN", "HXP", "VOR",
        "TQN", "RYS", "XAL", "PNK", "JUV", "KLY"
    ]

    used_callsigns = set()
    flight_number = 100  # starting point

    callsigns = []

    for _ in range(len(df)):
        # pick random prefix
        prefix = random.choice(fake_airlines)

        # increment flight number by random 1,2,3
        step = random.choice([1,2,3])
        flight_number += step

        candidate = f"{prefix}{flight_number}"

        # unlikely but check uniqueness
        while candidate in used_callsigns:
            flight_number += step
            candidate = f"{prefix}{flight_number}"

        used_callsigns.add(candidate)
        callsigns.append(candidate)

    df["callsign"] = callsigns
    return df

def main():
    df, icao24_map, aircraft_dim_map = load_data()
    df = enrich(df, icao24_map, aircraft_dim_map)
    df = label_ground_state(df)
    df = anonymize_callsigns(df)
    # Save enriched data
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, 'flight_data', 'processed_data', 'enriched_aircraft.csv')
    df.to_csv(output_path, index=False)
    print(f"Enriched data saved to {output_path}")
    print(f"Total aircraft processed: {len(df)}")
    print(f"% with known models: {100 * (df['aircraft_model'] != 'UNKNOWN_MODEL').mean():.2f}")
    print(f"% grounded: {100 * df['is_grounded'].mean():.2f}")
    print(f"Count missing dimensions: {(~df['has_dimensions']).sum()}")

if __name__ == "__main__":
    main()
