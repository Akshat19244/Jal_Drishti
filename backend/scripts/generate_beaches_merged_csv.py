"""
JalDrishti — Beaches Merged CSV Generator

Creates a combined CSV of CPCB ground-truth data + GEE satellite indices
for Indian beach/coastal stations only.

Output columns:
  CPCB: Station_Name, State, District, Basin, Date, Year, Latitude, Longitude,
        pH, DO, BOD, COD, EC, Temperature, Turbidity, Fecal_Coliform,
        Total_Coliform, Nitrate, TDS, Safety, WQI
  GEE:  CDOM, Turbidity_Index, Chlorophyll_a, Kd490, Sat_Source

Usage:
    cd backend
    python scripts/generate_beaches_merged_csv.py
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import Config

_BEACH_KEYWORDS = [
    'beach', 'coast', 'sea', 'shore', 'marine',
    'port', 'creek', 'harbour', 'harbor', 'bay',
    'mandvi', 'alang', 'somnath', 'diu', 'porbandar',
    'juhu', 'marina', 'puri', 'kovalam', 'goa',
    'visakhapatnam', 'digha', 'chandipur', 'calangute',
    'vasco', 'candolim', 'baga', 'baina', 'rushikonda',
    'estuary', 'backwater', 'gulf', 'lagoon',
    'thane creek', 'panvel', 'bassein', 'versova', 'worli',
    'kakinada', 'paradip', 'mangalore', 'kochi',
    'alappuzha', 'kozhikode', 'veli', 'vembanad',
    'daman', 'pondicherry', 'lakshadweep'
]

_CPCB_COLS = [
    'Station_Name', 'State', 'District', 'Basin',
    'Date', 'Year', 'Latitude', 'Longitude',
    'pH', 'DO', 'BOD', 'COD', 'EC', 'Temperature',
    'Turbidity', 'Fecal_Coliform', 'Total_Coliform',
    'Nitrate', 'TDS', 'Safety', 'WQI'
]

_SAT_COLS = ['CDOM', 'Turbidity_Index', 'Chlorophyll_a', 'Kd490']


def _proxy_satellite_params(do, bod):
    do = float(do) if not pd.isna(do) and do else 7.0
    bod = float(bod) if not pd.isna(bod) and bod else 5.0
    return {
        'CDOM': round(max(0.0, min(1.0, (10 - do) / 10)), 4),
        'Turbidity_Index': round(max(0.0, min(1.0, (bod - 3) / 7)), 4),
        'Chlorophyll_a': round(max(0.0, min(5.0, bod / 2)), 4),
        'Kd490': round(max(0.0, min(1.0, bod / 10)), 4),
    }


def main():
    print("=" * 60)
    print("JalDrishti — Beaches Merged CSV Generator")
    print("=" * 60)

    csv_path = Config.CSV_PATH
    print(f"\n[1/5] Loading CPCB data from: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=True)
    print(f"      Loaded {len(df):,} rows")

    print("\n[2/5] Filtering to beach/coastal stations...")
    name_lower = df['Station_Name'].str.lower().fillna('')
    beach_mask = name_lower.str.contains('|'.join(_BEACH_KEYWORDS), na=False)
    beach_df = df[beach_mask].copy()
    print(f"      Found {len(beach_df):,} beach rows")

    if beach_df.empty:
        coast_mask = (
            df['Latitude'].notna() & df['Longitude'].notna()
            & (df['Longitude'] > 68) & (df['Longitude'] < 90)
            & (df['Latitude'] > 8) & (df['Latitude'] < 24)
        )
        beach_df = df[coast_mask].sample(min(5000, len(df[coast_mask]))).copy()
        print(f"      Using {len(beach_df):,} coastal proxy rows")

    if 'WQI' not in beach_df.columns:
        print("\n[3/5] Computing WQI for beach records...")
        do = beach_df['DO'].astype('float32')
        bod = beach_df['BOD'].astype('float32')
        ph = beach_df['pH'].astype('float32')
        tur = beach_df['Turbidity'].astype('float32')
        fco = beach_df['Fecal_Coliform'].astype('float32')

        do_score = (1 - do.clip(upper=8) / 8) * 100
        bod_score = (bod / 30 * 100).clip(upper=100)
        ph_score = ((ph - 7).abs() * 25).clip(upper=100)
        tur_score = (tur / 200 * 100).clip(upper=100)
        fco_score = (np.log10(fco.clip(lower=0) + 1) / 6 * 100).clip(upper=100)

        w_do = do.notna().astype('float32') * 0.25
        w_bod = bod.notna().astype('float32') * 0.25
        w_ph = ph.notna().astype('float32') * 0.15
        w_tur = tur.notna().astype('float32') * 0.15
        w_fco = fco.notna().astype('float32') * 0.20

        total_w = w_do + w_bod + w_ph + w_tur + w_fco
        weighted = (
            do_score.fillna(0) * w_do + bod_score.fillna(0) * w_bod
            + ph_score.fillna(0) * w_ph + tur_score.fillna(0) * w_tur
            + fco_score.fillna(0) * w_fco
        )
        beach_df['WQI'] = (weighted / total_w.replace(0, float('nan'))).round(1).fillna(50.0)

    print("\n[4/5] Adding satellite water quality indices...")

    gee = None
    try:
        from services.gee_service import GEEService
        gee = GEEService()
        if gee.is_available():
            print("      Google Earth Engine available — trying live data (max 30 queries)")
        else:
            print("      GEE not available — using proxy estimates")
            gee = None
    except Exception as e:
        print(f"      GEE init failed ({e}) — using proxy estimates")
        gee = None

    beach_df['CDOM'] = np.nan
    beach_df['Turbidity_Index'] = np.nan
    beach_df['Chlorophyll_a'] = np.nan
    beach_df['Kd490'] = np.nan
    beach_df['Sat_Source'] = 'proxy'

    stations = beach_df[['Station_Name', 'Latitude', 'Longitude']].drop_duplicates()
    station_sat_cache = {}
    gee_fetched = 0
    gee_failures = 0
    MAX_GEE_ATTEMPTS = 30

    for idx, (_, st_row) in enumerate(stations.iterrows()):
        st_name = str(st_row['Station_Name'])
        lat = st_row['Latitude']
        lon = st_row['Longitude']
        if pd.isna(lat) or pd.isna(lon):
            continue

        st_data = beach_df[beach_df['Station_Name'] == st_name]
        do_mean = st_data['DO'].mean() if 'DO' in st_data.columns else 7
        bod_mean = st_data['BOD'].mean() if 'BOD' in st_data.columns else 5

        sat_vals = None

        # Try GEE for first N stations only (fail-fast if too many failures)
        if gee is not None and gee_failures < 5 and gee_fetched < MAX_GEE_ATTEMPTS:
            try:
                bbox = [lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5]
                start = '2022-01-01'
                end = '2022-12-31'
                indices = gee.get_water_quality_indices(bbox, start, end)
                if indices:
                    cdom = indices.get('cdom', {}).get('mean', None)
                    ndti = indices.get('ndti', {}).get('mean', None)
                    chlor = indices.get('chlorophyll', {}).get('mean', None)
                    kd490 = indices.get('kd490', {}).get('mean', None)
                    has_data = any(
                        v is not None and not np.isnan(v) and float(v) > 0.001
                        for v in [cdom, ndti, chlor, kd490]
                    )
                    if has_data:
                        sat_vals = {
                            'CDOM': float(cdom) if cdom is not None and not np.isnan(cdom) else None,
                            'Turbidity_Index': float(ndti) if ndti is not None and not np.isnan(ndti) else None,
                            'Chlorophyll_a': float(chlor) if chlor is not None and not np.isnan(chlor) else None,
                            'Kd490': float(kd490) if kd490 is not None and not np.isnan(kd490) else None,
                            'Sat_Source': 'gee'
                        }
                        gee_fetched += 1
                    else:
                        gee_failures += 1
                else:
                    gee_failures += 1
            except Exception:
                gee_failures += 1

        if sat_vals is None:
            sat_vals = _proxy_satellite_params(do_mean, bod_mean)
            sat_vals['Sat_Source'] = 'proxy'

        station_sat_cache[st_name] = sat_vals

        if (idx + 1) % 50 == 0:
            print(f"      Processed {idx + 1}/{len(stations)} stations (GEE: {gee_fetched}, fails: {gee_failures})")

    for st_name, sat_vals in station_sat_cache.items():
        mask = beach_df['Station_Name'] == st_name
        for col in ['CDOM', 'Turbidity_Index', 'Chlorophyll_a', 'Kd490']:
            beach_df.loc[mask, col] = sat_vals.get(col, np.nan)
        beach_df.loc[mask, 'Sat_Source'] = sat_vals.get('Sat_Source', 'proxy')

    print(f"      GEE data fetched for {gee_fetched}/{len(stations)} stations")

    print("\n[5/5] Preparing output CSV...")
    available_cols = [c for c in _CPCB_COLS if c in beach_df.columns]
    output_cols = available_cols + _SAT_COLS + ['Sat_Source']
    output_df = beach_df[output_cols].copy()

    if 'Date' in output_df.columns:
        try:
            parsed_a = pd.to_datetime(output_df['Date'], format='%d-%m-%Y %H:%M', errors='coerce')
            parsed_b = pd.to_datetime(output_df['Date'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            output_df['Date_Parsed'] = parsed_a.fillna(parsed_b)
            output_df['Date'] = output_df['Date_Parsed'].dt.strftime('%Y-%m-%d')
            output_df = output_df.drop(columns=['Date_Parsed'])
        except Exception:
            pass

    output_df = output_df.sort_values(['State', 'Station_Name', 'Year']).reset_index(drop=True)

    output_path = os.path.join(os.path.dirname(csv_path), 'india_beaches_merged.csv')
    output_df.to_csv(output_path, index=False)

    print(f"\n{'=' * 60}")
    print(f"Done! Output saved to: {output_path}")
    print(f"   Rows: {len(output_df):,}")
    print(f"   Columns: {len(output_cols)} ({', '.join(output_cols)})")
    print(f"   Stations: {output_df['Station_Name'].nunique()}")
    print(f"   States: {output_df['State'].nunique()}")
    print(f"   Years: {int(output_df['Year'].min())}–{int(output_df['Year'].max())}")
    print(f"   Satellite source: {output_df['Sat_Source'].value_counts().to_dict()}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
