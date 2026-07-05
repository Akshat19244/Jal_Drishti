"""
JalDrishti — Beaches Satellite Data CSV Generator (GEE-only, no proxy)

Creates a CSV of CPCB + real GEE Landsat water quality indices for Indian beaches.
- Uses Landsat 8/9 Collection 2 Level-2 (preferred for coastal areas)
- NO proxy/synthetic data — only real satellite values
- Stations without satellite data get NaN for satellite columns

Usage:
    cd backend
    python scripts/generate_beaches_csv.py
"""

import os, sys, json, time
import pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import Config

_BEACH_KW = 'beach|coast|sea|shore|marine|port|creek|harbour|harbor|bay|mandvi|alang|somnath|diu|porbandar|juhu|marina|puri|kovalam|goa|visakhapatnam|digha|chandipur|calangute|vasco|candolim|baga|baina|rushikonda|estuary|backwater|gulf|lagoon|thane creek|panvel|bassein|versova|worli|kakinada|paradip|mangalore|kochi|alappuzha|kozhikode|veli|vembanad|daman|pondicherry|lakshadweep'

CPCB_COLS = ['Station_Name','State','District','Basin','Date','Year','Latitude','Longitude',
             'pH','DO','BOD','COD','EC','Temperature','Turbidity','Fecal_Coliform',
             'Total_Coliform','Nitrate','TDS','Safety','WQI']
SAT_COLS = ['CDOM','Turbidity_Index','Chlorophyll_a','Kd490']

print("="*60)
print("JalDrishti - Beaches Satellite CSV Generator (GEE only)")
print("="*60)

csv_path = Config.CSV_PATH
cache_path = os.path.join(os.path.dirname(__file__), '..', 'gee_beach_cache.json')

print(f"\n[1] Loading CPCB data: {csv_path}")
df = pd.read_csv(csv_path, low_memory=True)
print(f"    {len(df):,} rows")

print("\n[2] Filtering beach stations...")
mask = df['Station_Name'].str.lower().fillna('').str.contains(_BEACH_KW, na=False)
beach = df[mask].copy()
if beach.empty:
    beach = df[(df['Latitude'].notna()) & (df['Longitude'].notna())
               & (df['Longitude'] > 68) & (df['Longitude'] < 90)
               & (df['Latitude'] > 8) & (df['Latitude'] < 24)].copy()
print(f"    {len(beach):,} beach rows")

print("\n[3] Computing WQI...")
for c in ['DO','BOD','pH','Turbidity','Fecal_Coliform']:
    beach[c] = pd.to_numeric(beach[c], errors='coerce')
do, bod, ph, tur, fco = [beach[c].fillna(beach[c].median()) for c in ['DO','BOD','pH','Turbidity','Fecal_Coliform']]
ds = (1-do.clip(upper=8)/8)*100; bs = (bod/30*100).clip(upper=100)
ps = ((ph-7).abs()*25).clip(upper=100); ts = (tur/200*100).clip(upper=100)
fs = (np.log10(fco.clip(lower=0)+1)/6*100).clip(upper=100)
tw = (~beach[['DO','BOD','pH','Turbidity','Fecal_Coliform']].isna()).astype(float) @ [0.25,0.25,0.15,0.15,0.20]
wgt = (ds.fillna(0)*0.25+bs.fillna(0)*0.25+ps.fillna(0)*0.15+ts.fillna(0)*0.15+fs.fillna(0)*0.20)
beach['WQI'] = (wgt/tw.replace(0,np.nan)).round(1).fillna(50.0)

print("\n[4] Fetching satellite data from GEE (Landsat 8/9 only)...")

# Init GEE
gee = None
gee_ok = False
try:
    from services.gee_service import GEEService
    gee = GEEService()
    gee_ok = gee.is_available()
    if gee_ok:
        print("    GEE initialized. Attempting Landsat 8/9 for each beach station...")
    else:
        print("    GEE not available - satellite columns will be NaN")
except Exception as e:
    print(f"    GEE init failed: {e}")

# Load cache if exists
sat_cache = {}
if os.path.exists(cache_path):
    try:
        with open(cache_path, 'r') as f:
            sat_cache = json.load(f)
        print(f"    Loaded cache: {len(sat_cache)} stations")
    except Exception:
        sat_cache = {}

stations = beach[['Station_Name', 'Latitude', 'Longitude']].drop_duplicates()
print(f"    Unique beach stations: {len(stations)}")

# Init satellite columns to NaN
beach['CDOM'] = np.nan
beach['Turbidity_Index'] = np.nan
beach['Chlorophyll_a'] = np.nan
beach['Kd490'] = np.nan
beach['Sat_Source'] = None

# Apply cached values first
for st_name, sv in sat_cache.items():
    m = beach['Station_Name'] == st_name
    for c in SAT_COLS:
        beach.loc[m, c] = sv.get(c, np.nan)
    beach.loc[m, 'Sat_Source'] = sv.get('Sat_Source', None)

gee_fetched = sum(1 for v in sat_cache.values() if v.get('CDOM') is not None and not np.isnan(v.get('CDOM', np.nan)))
gee_fail = sum(1 for v in sat_cache.values() if v.get('CDOM') is None or np.isnan(v.get('CDOM', np.nan)))
MAX_STATIONS = 149  # process all unique beach stations
total_attempts = gee_fetched + gee_fail

for idx, (_, st_row) in enumerate(stations.iterrows()):
    st_name = str(st_row['Station_Name'])
    lat, lon = st_row['Latitude'], st_row['Longitude']
    if pd.isna(lat) or pd.isna(lon):
        continue

    # Skip if already in cache
    if st_name in sat_cache:
        continue

    if total_attempts >= MAX_STATIONS:
        break

    sat_vals = {'CDOM': None, 'Turbidity_Index': None, 'Chlorophyll_a': None, 'Kd490': None, 'Sat_Source': None}

    if gee_ok:
        # Small bbox: 0.2 degree around station
        bbox = [lon-0.1, lat-0.1, lon+0.1, lat+0.1]
        # Try 2022 first, then 2023, then 2021
        for s, e in [('2022-01-01','2022-12-31'), ('2023-01-01','2023-12-31'), ('2021-01-01','2021-12-31')]:
            try:
                indices = gee._get_landsat_indices(bbox, s, e, max_cloud_cover=70)
                cdom = indices.get('cdom', {}).get('mean', 0)
                ndti = indices.get('ndti', {}).get('mean', 0)
                chlor = indices.get('chlorophyll', {}).get('mean', 0)
                kd490 = indices.get('kd490', {}).get('mean', 0)
                vals = [cdom, ndti, chlor, kd490]
                if any(v is not None and not np.isnan(v) and float(v) != 0.0 for v in vals):
                    sat_vals = {
                        'CDOM': float(cdom) if cdom is not None and not np.isnan(cdom) else None,
                        'Turbidity_Index': float(ndti) if ndti is not None and not np.isnan(ndti) else None,
                        'Chlorophyll_a': float(chlor) if chlor is not None and not np.isnan(chlor) else None,
                        'Kd490': float(kd490) if kd490 is not None and not np.isnan(kd490) else None,
                        'Sat_Source': 'landsat',
                    }
                    gee_fetched += 1
                    total_attempts += 1
                    break
            except Exception:
                continue
        else:
            # No data found for any year
            gee_fail += 1
            total_attempts += 1

    sat_cache[st_name] = sat_vals

    if (idx+1) % 5 == 0:
        print(f"    [{idx+1}/{len(stations)}] success={gee_fetched} fail={gee_fail}", flush=True)
    if (idx+1) % 10 == 0:
        try:
            with open(cache_path, 'w') as f:
                json.dump(sat_cache, f, indent=2)
        except Exception:
            pass

# Save cache
try:
    with open(cache_path, 'w') as f:
        json.dump(sat_cache, f, indent=2)
    print(f"    Cache saved: {cache_path}")
except Exception as e:
    print(f"    Cache save failed: {e}")

# Apply all cached values
for st_name, sv in sat_cache.items():
    m = beach['Station_Name'] == st_name
    for c in SAT_COLS:
        if sv.get(c) is not None and not np.isnan(sv.get(c, np.nan)):
            beach.loc[m, c] = float(sv[c])
    if sv.get('Sat_Source'):
        beach.loc[m, 'Sat_Source'] = sv['Sat_Source']

print(f"    Done: {gee_fetched} stations with satellite data, {gee_fail} without")

print("\n[5] Saving CSVs...")
avail = [c for c in CPCB_COLS if c in beach.columns]
merged = beach[avail + SAT_COLS + ['Sat_Source']].copy()
if 'Date' in merged.columns:
    merged['Date'] = pd.to_datetime(merged['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
merged = merged.sort_values(['State','Station_Name','Year']).reset_index(drop=True)

out = os.path.join(os.path.dirname(csv_path), 'india_beaches_merged.csv')
merged.to_csv(out, index=False)

# Satellite-only: 1 row per beach station with real satellite data
has_data = beach['CDOM'].notna() & (beach['CDOM'] != 0)
sat_only = beach[has_data].groupby(
    ['Station_Name','State','District','Basin','Latitude','Longitude'],
    observed=True, dropna=False
).agg(
    CDOM=('CDOM','mean'), Turbidity_Index=('Turbidity_Index','mean'),
    Chlorophyll_a=('Chlorophyll_a','mean'), Kd490=('Kd490','mean'),
    Sat_Source=('Sat_Source','first')
).reset_index().round(4)
sat_out = os.path.join(os.path.dirname(csv_path), 'india_beaches_satellite_only.csv')
sat_only.to_csv(sat_out, index=False)

print(f"\n{'='*60}")
print(f"Done! Files:")
print(f"  1. {out}")
print(f"     {len(merged):,} rows")
print(f"     Stations: {merged['Station_Name'].nunique()} | States: {merged['State'].nunique()}")
print(f"  2. {sat_out}")
print(f"     {len(sat_only)} beaches WITH real satellite data")
src_cnt = beach['Sat_Source'].dropna().value_counts().to_dict() if beach['Sat_Source'].notna().any() else {}
print(f"     Sources: {src_cnt}")
print(f"  Cache: {cache_path} ({len(sat_cache)} stations)")
print(f"{'='*60}")
