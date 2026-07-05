"""
JalDrishti — Beaches Satellite Data CSV Generator
Creates a CSV of CPCB + satellite water quality indices for Indian beaches.
No GEE dependency — uses CPCB-correlated proxy estimates (same methodology as the website's fallback).
"""

import os, sys, pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import Config

_BEACH_KW = 'beach|coast|sea|shore|marine|port|creek|harbour|harbor|bay|mandvi|alang|somnath|diu|porbandar|juhu|marina|puri|kovalam|goa|visakhapatnam|digha|chandipur|calangute|vasco|candolim|baga|baina|rushikonda|estuary|backwater|gulf|lagoon|thane creek|panvel|bassein|versova|worli|kakinada|paradip|mangalore|kochi|alappuzha|kozhikode|veli|vembanad|daman|pondicherry|lakshadweep'

CPCB_COLS = ['Station_Name','State','District','Basin','Date','Year','Latitude','Longitude',
             'pH','DO','BOD','COD','EC','Temperature','Turbidity','Fecal_Coliform',
             'Total_Coliform','Nitrate','TDS','Safety','WQI']
SAT_COLS = ['CDOM','Turbidity_Index','Chlorophyll_a','Kd490']

print("="*60)
print("JalDrishti — Beaches Satellite CSV Generator")
print("="*60)

csv_path = Config.CSV_PATH
print(f"\n[1] Loading CPCB data: {csv_path}")
df = pd.read_csv(csv_path, low_memory=True)
print(f"    {len(df):,} rows loaded")

print("\n[2] Filtering beach stations...")
mask = df['Station_Name'].str.lower().fillna('').str.contains(_BEACH_KW, na=False)
beach = df[mask].copy()
if beach.empty:
    print("    No beach keywords found — using coastal lat/lon filter")
    beach = df[(df['Latitude'].notna()) & (df['Longitude'].notna())
               & (df['Longitude'] > 68) & (df['Longitude'] < 90)
               & (df['Latitude'] > 8) & (df['Latitude'] < 24)].copy()
print(f"    {len(beach):,} beach rows")

print("\n[3] Computing WQI...")
if 'WQI' not in beach.columns:
    for c in ['DO','BOD','pH','Turbidity','Fecal_Coliform']:
        beach[c] = pd.to_numeric(beach[c], errors='coerce')
    do, bod, ph, tur, fco = [beach[c].fillna(beach[c].median()) for c in ['DO','BOD','pH','Turbidity','Fecal_Coliform']]
    ds = (1-do.clip(upper=8)/8)*100
    bs = (bod/30*100).clip(upper=100)
    ps = ((ph-7).abs()*25).clip(upper=100)
    ts = (tur/200*100).clip(upper=100)
    fs = (np.log10(fco.clip(lower=0)+1)/6*100).clip(upper=100)
    tw = (~beach[['DO','BOD','pH','Turbidity','Fecal_Coliform']].isna()).astype(float) @ [0.25,0.25,0.15,0.15,0.20]
    wgt = (ds.fillna(0)*0.25+bs.fillna(0)*0.25+ps.fillna(0)*0.15+ts.fillna(0)*0.15+fs.fillna(0)*0.20)
    beach['WQI'] = (wgt/tw.replace(0,np.nan)).round(1).fillna(50.0)

print("\n[4] Adding satellite parameters (proxy from CPCB DO/BOD)...")
do_mean = beach.groupby('Station_Name')['DO'].transform('mean').fillna(7.0)
bod_mean = beach.groupby('Station_Name')['BOD'].transform('mean').fillna(5.0)
beach['CDOM'] = ((10-do_mean)/10).clip(0,1).round(4)
beach['Turbidity_Index'] = ((bod_mean-3)/7).clip(0,1).round(4)
beach['Chlorophyll_a'] = (bod_mean/2).clip(0,5).round(4)
beach['Kd490'] = (bod_mean/10).clip(0,1).round(4)
beach['Sat_Source'] = 'proxy'

# Save: merged version
avail = [c for c in CPCB_COLS if c in beach.columns]
merged = beach[avail + SAT_COLS + ['Sat_Source']].copy()
if 'Date' in merged.columns:
    merged['Date'] = pd.to_datetime(merged['Date'], errors='coerce').dt.strftime('%Y-%m-%d')
merged = merged.sort_values(['State','Station_Name','Year']).reset_index(drop=True)

out = os.path.join(os.path.dirname(csv_path), 'india_beaches_merged.csv')
merged.to_csv(out, index=False)

# Save: satellite-only version (1 row per beach with avg satellite values)
sat_only = beach.groupby(['Station_Name','State','District','Basin','Latitude','Longitude'], observed=True).agg(
    CDOM=('CDOM','mean'), Turbidity_Index=('Turbidity_Index','mean'),
    Chlorophyll_a=('Chlorophyll_a','mean'), Kd490=('Kd490','mean'),
    Sat_Source=('Sat_Source','first')
).reset_index()
sat_only = sat_only.round(4)
sat_out = os.path.join(os.path.dirname(csv_path), 'india_beaches_satellite_only.csv')
sat_only.to_csv(sat_out, index=False)

print(f"\n{'='*60}")
print(f"Done! Files created:")
print(f"   1. {out}")
print(f"      Merged CPCB + Satellite: {len(merged):,} rows, {len(avail)+len(SAT_COLS)+1} columns")
print(f"   2. {sat_out}")
print(f"      Satellite-only (1 row/beach): {len(sat_only)} beaches")
print(f"      Stations: {merged['Station_Name'].nunique()} | States: {merged['State'].nunique()}")
print(f"      Years: {int(merged['Year'].min())}–{int(merged['Year'].max())}")
print(f"{'='*60}")
