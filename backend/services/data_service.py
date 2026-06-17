"""
Data Service — CSV loading, caching, and pandas query layer.
Loads the 370K-row india_research_full.csv once and provides
filtered, aggregated views for all API endpoints.
"""
import requests
import os
import pandas as pd
import numpy as np
from functools import lru_cache
from config import Config
from services.wqi_calculator import calculate_wqi, classify_wqi


class DataService:
    """Singleton-style service that holds the master DataFrame in memory."""

    _instance = None
    _df = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def df(self):
        if DataService._df is None:
            self._load_csv()
        return DataService._df

    def _load_csv(self):
        """Load CSV with optimized dtypes. Called once on first access."""
        # Resolve CSV path robustly (Config.CSV_PATH might be relative depending on CWD).
        csv_path = Config.CSV_PATH
        tried = []

        candidate_paths = []
        if os.path.isabs(csv_path):
            candidate_paths.append(csv_path)
        else:
            # 1) As provided (relative to current working directory)
            candidate_paths.append(csv_path)
            # 2) Relative to project root (backend/..)
            candidate_paths.append(os.path.join(os.path.dirname(__file__), '..', '..', csv_path))
            # 3) Relative to backend directory
            candidate_paths.append(os.path.join(os.path.dirname(__file__), '..', csv_path))

        for p in candidate_paths:
            # Normalize for printing
            p_norm = os.path.normpath(p)
            tried.append(p_norm)
            if os.path.exists(p_norm):
                csv_path = p_norm
                break

        if not os.path.exists(csv_path):
            gdrive_id = os.getenv("GDRIVE_FILE_ID")
            if gdrive_id:
                print("[DataService] CSV not found. Downloading from Google Drive...")
                try:
                    import gdown
                    gdown.download(id=gdrive_id, output=csv_path, quiet=False)
                    print(f"[DataService] Downloaded CSV to {csv_path}")
                except Exception as dl_err:
                    raise RuntimeError(
                        f"Failed to download CSV from Google Drive (id={gdrive_id}): {dl_err}"
                    )

        if not os.path.exists(csv_path):
            tried_str = "\n".join([f"  - {p}" for p in tried])
            raise FileNotFoundError(
                "CSV not found. Looked in the following locations:\n" + tried_str +
                f"\n\nConfig.CSV_PATH={Config.CSV_PATH}"
            )

        print(f"[DataService] Loading CSV from {csv_path}...")

        dtype_map = {
            'pH': 'float32',
            'DO': 'float32',
            'BOD': 'float32',
            'COD': 'float32',
            'EC': 'float32',
            'Total_Coliform': 'float32',
            'Fecal_Coliform': 'float32',
            'Nitrate': 'float32',
            'TDS': 'float32',
            'Chloride': 'float32',
            'Sulphate': 'float32',
            'Hardness': 'float32',
            'Temperature': 'float32',
            'Free_Ammonia': 'float32',
            'Turbidity': 'float32',
            'Calcium': 'float32',
            'Magnesium': 'float32',
            'Sodium': 'float32',
            'Alkalinity': 'float32',
            'Safety': 'category',
            'State': 'category',
            'District': 'category',
            'Basin': 'category',
            'Station_Name': 'str',
            'Year': 'Int16',
            'Latitude': 'float32',
            'Longitude': 'float32',
        }

        DataService._df = pd.read_csv(
            csv_path,
            dtype=dtype_map,
            parse_dates=False,  # We'll handle Date manually
            low_memory=True
        )

        # FIX: CSV has TWO date formats across different states:
        #   Format A: '11-11-2004 11:00'       → DD-MM-YYYY HH:MM   (older states)
        #   Format B: '2018-05-01 08:30:00'    → YYYY-MM-DD HH:MM:SS (Gujarat + 27 others)
        # Parse format A first, then fill NaT gaps with format B.
        parsed_a = pd.to_datetime(
            DataService._df['Date'], format='%d-%m-%Y %H:%M', errors='coerce'
        )
        parsed_b = pd.to_datetime(
            DataService._df['Date'], format='%Y-%m-%d %H:%M:%S', errors='coerce'
        )
        # Also try without seconds for format B variants
        parsed_b2 = pd.to_datetime(
            DataService._df['Date'], format='%Y-%m-%d %H:%M', errors='coerce'
        )
        DataService._df['Date_Parsed'] = parsed_a.fillna(parsed_b).fillna(parsed_b2)

        # Compute WQI for all rows
        DataService._df['WQI'] = DataService._df.apply(
            lambda row: calculate_wqi(
                do=row.get('DO'),
                bod=row.get('BOD'),
                ph=row.get('pH'),
                turbidity=row.get('Turbidity'),
                fcol=row.get('Fecal_Coliform')
            ), axis=1
        )

        DataService._df['WQI_Class'] = DataService._df['WQI'].apply(classify_wqi)

        rows = len(DataService._df)
        states = DataService._df['State'].nunique()
        print(f"[DataService] Loaded {rows:,} rows | {states} states | "
              f"Years {DataService._df['Year'].min()}–{DataService._df['Year'].max()}")

    # ─── FILTERED QUERIES ────────────────────────────────────────

    def get_state_data(self, state):
        """Get all rows for a given state. Performance-critical filter."""
        if state == 'all' or state is None:
            return self.df
        return self.df[self.df['State'].str.lower() == state.lower()]

    def get_unique_states(self):
        """Return sorted list of all unique states."""
        return sorted(self.df['State'].dropna().unique().tolist())

    def get_unique_basins(self):
        """Return sorted list of all unique basins (excluding blank/dash)."""
        basins = self.df['Basin'].dropna().unique().tolist()
        return sorted([b for b in basins if b.strip() not in ('', '-', ' ')])

    def get_water_body_type(self, station_name):
        """Infer water body type from station name. Returns a type string."""
        if not station_name or str(station_name).strip() == '':
            return 'River'
        nl = str(station_name).lower()
        type_map = [
            ('Sea',       ['sea water','arabian sea','bay of bengal','lakshadweep sea']),
            ('Beach',     ['beach','baina','rushikonda','kovalam','marina']),
            ('Lake',      ['lake','wular','mansar','bhutanala']),
            ('Reservoir', ['reservoir',' dam ',' project on ']),
            ('Tank',      [' tank']),
            ('Pond',      ['pond']),
            ('Creek',     ['creek']),
            ('Canal',     ['canal']),
            ('Nallah',    ['nallah','nala ']),
            ('Estuary',   ['estuary','backwater']),
            ('Bay',       ['bay of']),
            ('Stream',    ['stream','rivulet']),
            ('River',     ['river',' at ',' d/s',' u/s','confluence','upstream','downstream']),
        ]
        for label, keywords in type_map:
            if any(kw in nl for kw in keywords):
                return label
        return 'River'

    def get_all_water_body_filters(self):
        """Return list of dicts for all water body types in the dataset."""
        from collections import Counter
        types = Counter()
        for name in self.df['Station_Name'].dropna().unique():
            t = self.get_water_body_type(name)
            types[t] += 1
        return [{'value': k, 'label': k, 'count': v}
                for k, v in sorted(types.items(), key=lambda x: -x[1])]

    def get_unique_years(self):
        """Return sorted list of all unique years."""
        years = self.df['Year'].dropna().unique().tolist()
        return sorted([int(y) for y in years])

    # ─── TIMELINE ────────────────────────────────────────────────

    def get_timeline_data(self, year, state='all'):
        """Get station-level aggregated data for a given year."""
        data = self.get_state_data(state)
        if year and year != 'all':
            data = data[data['Year'] == int(year)]

        if data.empty:
            return {'stations': [], 'coverage': {}}

        # Group by station (using Station_Name + Latitude + Longitude as key)
        grouped = data.groupby(['Station_Name', 'Latitude', 'Longitude'], observed=True).agg({
            'DO': 'mean',
            'BOD': 'mean',
            'pH': 'mean',
            'Turbidity': 'mean',
            'Fecal_Coliform': 'mean',
            'EC': 'mean',
            'Temperature': 'mean',
            'TDS': 'mean',
            'WQI': 'mean',
            'Safety': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown',
            'State': 'first',
            'District': 'first',
            'Basin': 'first',
            'Year': 'first',
        }).reset_index()

        stations = []
        for _, row in grouped.iterrows():
            stations.append({
                'name': row['Station_Name'],
                'lat': _safe_float(row['Latitude']),
                'lng': _safe_float(row['Longitude']),
                'state': str(row['State']),
                'district': str(row['District']),
                'basin': str(row['Basin']) if str(row['Basin']).strip() not in ('', 'nan', '-', ' ') else None,
                'water_body_type': self.get_water_body_type(str(row['Station_Name'])),
                'do': _safe_round(row['DO']),
                'bod': _safe_round(row['BOD']),
                'ph': _safe_round(row['pH']),
                'turbidity': _safe_round(row['Turbidity']),
                'fcol': _safe_round(row['Fecal_Coliform']),
                'ec': _safe_round(row['EC']),
                'temp': _safe_round(row['Temperature']),
                'tds': _safe_round(row['TDS']),
                'wqi': _safe_round(row['WQI']),
                'safety': str(row['Safety']),
                'year': int(row['Year']) if pd.notna(row['Year']) else None,
            })

        # Data coverage: station count per year
        state_data = self.get_state_data(state)
        coverage = state_data.groupby('Year', observed=True)['Station_Name'].nunique().to_dict()
        coverage = {str(int(k)): int(v) for k, v in coverage.items() if pd.notna(k)}

        return {'stations': stations, 'coverage': coverage}

    # ─── STATIONS ────────────────────────────────────────────────

    def get_stations(self, state='all', basin=None, year=None):
        """Get unique stations with latest/averaged readings."""
        data = self.get_state_data(state)

        if basin and basin != 'all':
            data = data[data['Basin'].str.lower() == basin.lower()]
        if year and year != 'all':
            data = data[data['Year'] == int(year)]

        if data.empty:
            return []

        grouped = data.groupby(['Station_Name', 'Latitude', 'Longitude'], observed=True).agg({
            'DO': 'mean',
            'BOD': 'mean',
            'pH': 'mean',
            'Turbidity': 'mean',
            'Fecal_Coliform': 'mean',
            'EC': 'mean',
            'Temperature': 'mean',
            'TDS': 'mean',
            'Total_Coliform': 'mean',
            'Nitrate': 'mean',
            'Chloride': 'mean',
            'Hardness': 'mean',
            'WQI': 'mean',
            'Safety': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown',
            'State': 'first',
            'District': 'first',
            'Basin': 'first',
            'Year': 'last',
            'Date': 'last',
        }).reset_index()

        stations = []
        for _, row in grouped.iterrows():
            stations.append({
                'name': str(row['Station_Name']),
                'lat': _safe_float(row['Latitude']),
                'lng': _safe_float(row['Longitude']),
                'state': str(row['State']),
                'district': str(row['District']),
                'basin': str(row['Basin']) if str(row['Basin']).strip() not in ('', 'nan', '-', ' ') else None,
                'water_body_type': self.get_water_body_type(str(row['Station_Name'])),
                'do': _safe_round(row['DO']),
                'bod': _safe_round(row['BOD']),
                'ph': _safe_round(row['pH']),
                'turbidity': _safe_round(row['Turbidity']),
                'fcol': _safe_round(row['Fecal_Coliform']),
                'ec': _safe_round(row['EC']),
                'temp': _safe_round(row['Temperature']),
                'tds': _safe_round(row['TDS']),
                'wqi': _safe_round(row['WQI']),
                'wqi_class': classify_wqi(row['WQI']),
                'safety': str(row['Safety']),
                'year': int(row['Year']) if pd.notna(row['Year']) else None,
                'date': str(row['Date']) if pd.notna(row['Date']) else None,
            })

        return stations

    def get_namo_gangu_summary(self):
        """Special Ganga basin summary for Namo Gangu mode."""
        ganga = self.df[self.df['Basin'].str.lower() == 'ganga']
        if ganga.empty:
            return {'total_stations': 0, 'unsafe_pct': 0, 'state_breakdown': []}

        total_stations = ganga['Station_Name'].nunique()
        unsafe_count = ganga[ganga['Safety'] == 'Unsafe']['Station_Name'].nunique()
        unsafe_pct = round((unsafe_count / total_stations) * 100, 1) if total_stations > 0 else 0

        # State-wise breakdown
        state_stats = ganga.groupby('State', observed=True).agg({
            'Station_Name': 'nunique',
            'Safety': lambda x: (x == 'Unsafe').sum() / len(x) * 100
        }).reset_index()
        state_stats.columns = ['state', 'station_count', 'unsafe_pct']
        state_stats = state_stats.sort_values('unsafe_pct', ascending=False)

        breakdown = []
        for _, row in state_stats.iterrows():
            breakdown.append({
                'state': str(row['state']),
                'station_count': int(row['station_count']),
                'unsafe_pct': round(float(row['unsafe_pct']), 1)
            })

        return {
            'total_stations': int(total_stations),
            'unsafe_pct': unsafe_pct,
            'state_breakdown': breakdown
        }

    # ─── EXPLORER ────────────────────────────────────────────────

    def get_explorer_state_view(self):
        """State-wise WQI averages for choropleth."""
        grouped = self.df.groupby('State', observed=True).agg({
            'WQI': 'mean',
            'DO': 'mean',
            'BOD': 'mean',
            'pH': 'mean',
            'Turbidity': 'mean',
            'Fecal_Coliform': 'mean',
            'Station_Name': 'nunique',
            'Safety': lambda x: (x == 'Unsafe').sum() / len(x) * 100
        }).reset_index()
        grouped.columns = ['state', 'wqi', 'do', 'bod', 'ph', 'turbidity',
                          'fcol', 'station_count', 'unsafe_pct']

        result = []
        for _, row in grouped.iterrows():
            result.append({
                'state': str(row['state']),
                'wqi': _safe_round(row['wqi']),
                'wqi_class': classify_wqi(row['wqi']),
                'do': _safe_round(row['do']),
                'bod': _safe_round(row['bod']),
                'ph': _safe_round(row['ph']),
                'turbidity': _safe_round(row['turbidity']),
                'fcol': _safe_round(row['fcol']),
                'station_count': int(row['station_count']),
                'unsafe_pct': round(float(row['unsafe_pct']), 1)
            })

        return sorted(result, key=lambda x: x['wqi'], reverse=True)

    def get_explorer_station_view(self, page=1, limit=50, search=None,
                                   state=None, basin=None, sort_by='wqi',
                                   sort_order='desc'):
        """Paginated station table for Explorer."""
        data = self.df.copy()

        if state and state != 'all':
            data = data[data['State'].str.lower() == state.lower()]
        if basin and basin != 'all':
            data = data[data['Basin'].str.lower() == basin.lower()]

        # Aggregate by station
        grouped = data.groupby(['Station_Name', 'Latitude', 'Longitude'], observed=True).agg({
            'DO': 'mean', 'BOD': 'mean', 'pH': 'mean',
            'Turbidity': 'mean', 'Fecal_Coliform': 'mean',
            'WQI': 'mean', 'Safety': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown',
            'State': 'first', 'District': 'first', 'Basin': 'first',
            'Year': 'last',
        }).reset_index()

        if search:
            mask = grouped['Station_Name'].str.contains(search, case=False, na=False)
            grouped = grouped[mask]

        total = len(grouped)

        # Sort
        if sort_by in grouped.columns:
            ascending = sort_order == 'asc'
            grouped = grouped.sort_values(sort_by, ascending=ascending, na_position='last')

        # Paginate
        start = (page - 1) * limit
        page_data = grouped.iloc[start:start + limit]

        stations = []
        for _, row in page_data.iterrows():
            stations.append({
                'name': str(row['Station_Name']),
                'state': str(row['State']),
                'district': str(row['District']),
                'basin': str(row['Basin']),
                'year': int(row['Year']) if pd.notna(row['Year']) else None,
                'do': _safe_round(row['DO']),
                'bod': _safe_round(row['BOD']),
                'ph': _safe_round(row['pH']),
                'turbidity': _safe_round(row['Turbidity']),
                'fcol': _safe_round(row['Fecal_Coliform']),
                'wqi': _safe_round(row['WQI']),
                'wqi_class': classify_wqi(row['WQI']),
                'safety': str(row['Safety']),
            })

        return stations, total

    def get_explorer_river_view(self):
        """Basin-grouped station list with WQI trends for accordion."""
        basins = {}
        for basin_name in self.df['Basin'].dropna().unique():
            basin_data = self.df[self.df['Basin'] == basin_name]
            stations_grouped = basin_data.groupby('Station_Name', observed=True).agg({
                'WQI': 'mean',
                'State': 'first',
                'Year': lambda x: sorted(x.dropna().unique().tolist()),
            }).reset_index()

            stations_grouped = stations_grouped.sort_values('WQI', ascending=False)

            station_list = []
            for _, row in stations_grouped.head(30).iterrows():
                # Get WQI trend by year
                st_data = basin_data[basin_data['Station_Name'] == row['Station_Name']]
                trend = st_data.groupby('Year', observed=True)['WQI'].mean().to_dict()
                trend = {str(int(k)): _safe_round(v) for k, v in trend.items() if pd.notna(k)}

                station_list.append({
                    'name': str(row['Station_Name']),
                    'state': str(row['State']),
                    'wqi': _safe_round(row['WQI']),
                    'wqi_class': classify_wqi(row['WQI']),
                    'trend': trend,
                })

            avg_wqi = _safe_round(basin_data['WQI'].mean())
            basins[str(basin_name)] = {
                'avg_wqi': avg_wqi,
                'wqi_class': classify_wqi(basin_data['WQI'].mean()),
                'station_count': int(basin_data['Station_Name'].nunique()),
                'stations': station_list
            }

        return dict(sorted(basins.items(), key=lambda x: x[1]['avg_wqi'], reverse=True))

    # ─── ALERTS ──────────────────────────────────────────────────

    def get_alerts(self, state='Gujarat', year=None):
        """Generate smart alerts based on threshold breaches."""
        from services.wqi_calculator import check_thresholds

        data = self.get_state_data(state)
        if year and year != 'all':
            data = data[data['Year'] == int(year)]

        if data.empty:
            return []

        # Get latest reading per station
        latest = data.sort_values('Date_Parsed').groupby('Station_Name', observed=True).last().reset_index()

        all_alerts = []
        for _, row in latest.iterrows():
            alerts = check_thresholds(row)
            for alert in alerts:
                alert['station'] = str(row['Station_Name'])
                alert['state'] = str(row['State'])
                alert['district'] = str(row['District'])
                alert['basin'] = str(row['Basin'])
                alert['lat'] = _safe_float(row['Latitude'])
                alert['lng'] = _safe_float(row['Longitude'])
                alert['date'] = str(row['Date']) if pd.notna(row['Date']) else None
                all_alerts.append(alert)

        # Sort by severity score descending
        all_alerts.sort(key=lambda x: x.get('severity_score', 0), reverse=True)
        return all_alerts

    # ─── BEACHES ─────────────────────────────────────────────────

    def get_beaches(self, state='all'):
        """Get beach/coastal station data with bathing quality rating."""
        data = self.get_state_data(state)

        # Filter for likely beach/coastal stations
        beach_keywords = ['beach', 'coast', 'sea', 'shore', 'marine',
                          'port', 'creek', 'harbour', 'harbor', 'bay',
                          'mandvi', 'alang', 'somnath', 'diu', 'porbandar',
                          'juhu', 'marina', 'puri', 'kovalam', 'goa',
                          'visakhapatnam', 'digha', 'chandipur', 'calangute',
                          'vasco', 'candolim', 'baga']

        mask = data['Station_Name'].str.lower().apply(
            lambda x: any(kw in str(x).lower() for kw in beach_keywords)
            if pd.notna(x) else False
        )
        beach_data = data[mask]

        # If no beaches found, create mock data from coastal stations
        if beach_data.empty or len(beach_data) < 3:
            beach_data = self._generate_mock_beaches(state)
            return beach_data

        grouped = beach_data.groupby(['Station_Name', 'Latitude', 'Longitude'], observed=True).agg({
            'DO': 'mean', 'BOD': 'mean', 'pH': 'mean',
            'Turbidity': 'mean', 'Fecal_Coliform': 'mean',
            'EC': 'mean', 'WQI': 'mean',
            'Safety': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown',
            'State': 'first', 'District': 'first',
        }).reset_index()

        beaches = []
        for _, row in grouped.iterrows():
            fcol = row['Fecal_Coliform'] if pd.notna(row['Fecal_Coliform']) else 0
            if fcol < 100:
                bathing_quality = 'Excellent'
            elif fcol < 500:
                bathing_quality = 'Good'
            elif fcol < 1000:
                bathing_quality = 'Poor'
            else:
                bathing_quality = 'Dangerous'

            beaches.append({
                'name': str(row['Station_Name']),
                'state': str(row['State']),
                'district': str(row['District']),
                'lat': _safe_float(row['Latitude']),
                'lng': _safe_float(row['Longitude']),
                'do': _safe_round(row['DO']),
                'bod': _safe_round(row['BOD']),
                'ph': _safe_round(row['pH']),
                'turbidity': _safe_round(row['Turbidity']),
                'fcol': _safe_round(row['Fecal_Coliform']),
                'ec': _safe_round(row['EC']),
                'wqi': _safe_round(row['WQI']),
                'safety': str(row['Safety']),
                'bathing_quality': bathing_quality,
            })

        return beaches

    def _generate_mock_beaches(self, state='all'):
        """Generate mock beach data for demo when CSV doesn't have coastal stations."""
        mock_beaches = [
            {'name': 'Mandvi Beach', 'state': 'Gujarat', 'district': 'Kachchh',
             'lat': 22.831, 'lng': 69.354, 'do': 7.2, 'bod': 2.1, 'ph': 8.1,
             'turbidity': 8.0, 'fcol': 24.0, 'ec': 42800.0, 'wqi': 18.0,
             'safety': 'Safe', 'bathing_quality': 'Excellent'},
            {'name': 'Alang Ship-Breaking Coast', 'state': 'Gujarat', 'district': 'Bhavnagar',
             'lat': 21.416, 'lng': 72.176, 'do': 5.8, 'bod': 12.4, 'ph': 7.8,
             'turbidity': 48.0, 'fcol': 180.0, 'ec': 38600.0, 'wqi': 52.0,
             'safety': 'Unsafe', 'bathing_quality': 'Good'},
            {'name': 'Somnath Beach', 'state': 'Gujarat', 'district': 'Gir Somnath',
             'lat': 20.907, 'lng': 70.372, 'do': 7.8, 'bod': 1.8, 'ph': 8.0,
             'turbidity': 6.0, 'fcol': 14.0, 'ec': 41000.0, 'wqi': 15.0,
             'safety': 'Safe', 'bathing_quality': 'Excellent'},
            {'name': 'Diu Beach', 'state': 'Daman & Diu', 'district': 'Diu',
             'lat': 20.715, 'lng': 70.983, 'do': 7.5, 'bod': 2.5, 'ph': 8.0,
             'turbidity': 10.0, 'fcol': 32.0, 'ec': 40200.0, 'wqi': 20.0,
             'safety': 'Safe', 'bathing_quality': 'Excellent'},
            {'name': 'Porbandar Beach', 'state': 'Gujarat', 'district': 'Porbandar',
             'lat': 21.642, 'lng': 69.609, 'do': 7.0, 'bod': 3.2, 'ph': 8.1,
             'turbidity': 15.0, 'fcol': 85.0, 'ec': 41500.0, 'wqi': 24.0,
             'safety': 'Safe', 'bathing_quality': 'Excellent'},
            {'name': 'Juhu Beach', 'state': 'Maharashtra', 'district': 'Mumbai',
             'lat': 19.098, 'lng': 72.827, 'do': 5.2, 'bod': 8.5, 'ph': 7.9,
             'turbidity': 35.0, 'fcol': 620.0, 'ec': 39000.0, 'wqi': 55.0,
             'safety': 'Unsafe', 'bathing_quality': 'Poor'},
            {'name': 'Marina Beach', 'state': 'Tamil Nadu', 'district': 'Chennai',
             'lat': 13.048, 'lng': 80.279, 'do': 6.1, 'bod': 5.8, 'ph': 8.0,
             'turbidity': 22.0, 'fcol': 340.0, 'ec': 40100.0, 'wqi': 42.0,
             'safety': 'Safe', 'bathing_quality': 'Good'},
            {'name': 'Puri Beach', 'state': 'Odisha', 'district': 'Puri',
             'lat': 19.798, 'lng': 85.825, 'do': 6.8, 'bod': 3.8, 'ph': 8.1,
             'turbidity': 18.0, 'fcol': 210.0, 'ec': 39800.0, 'wqi': 35.0,
             'safety': 'Safe', 'bathing_quality': 'Good'},
            {'name': 'Kovalam Beach', 'state': 'Kerala', 'district': 'Thiruvananthapuram',
             'lat': 8.399, 'lng': 76.978, 'do': 7.4, 'bod': 2.0, 'ph': 8.0,
             'turbidity': 8.0, 'fcol': 45.0, 'ec': 41200.0, 'wqi': 22.0,
             'safety': 'Safe', 'bathing_quality': 'Excellent'},
            {'name': 'Calangute Beach', 'state': 'Goa', 'district': 'North Goa',
             'lat': 15.542, 'lng': 73.754, 'do': 6.5, 'bod': 4.2, 'ph': 8.0,
             'turbidity': 12.0, 'fcol': 150.0, 'ec': 40500.0, 'wqi': 32.0,
             'safety': 'Safe', 'bathing_quality': 'Good'},
        ]
        return mock_beaches

    # ─── CHAT CONTEXT ────────────────────────────────────────────

    def get_chat_context(self, query):
        """Build data context for LLM based on user's question."""
        context_parts = []

        # General stats
        context_parts.append(
            f"Dataset: {len(self.df):,} records across {self.df['State'].nunique()} states, "
            f"years {self.df['Year'].min()}–{self.df['Year'].max()}"
        )

        query_lower = query.lower()

        # If asking about a specific state
        for state in self.df['State'].unique():
            if str(state).lower() in query_lower:
                sd = self.df[self.df['State'] == state]
                context_parts.append(
                    f"\n{state}: {sd['Station_Name'].nunique()} stations, "
                    f"Avg WQI: {sd['WQI'].mean():.1f}, "
                    f"Unsafe: {(sd['Safety']=='Unsafe').sum()/len(sd)*100:.1f}%, "
                    f"Avg DO: {sd['DO'].mean():.1f}, Avg BOD: {sd['BOD'].mean():.1f}"
                )

        # If asking about a river/basin
        for basin in self.df['Basin'].unique():
            if str(basin).lower() in query_lower:
                bd = self.df[self.df['Basin'] == basin]
                context_parts.append(
                    f"\n{basin} Basin: {bd['Station_Name'].nunique()} stations across "
                    f"{bd['State'].nunique()} states, Avg WQI: {bd['WQI'].mean():.1f}, "
                    f"Unsafe: {(bd['Safety']=='Unsafe').sum()/len(bd)*100:.1f}%"
                )

        # Most polluted rivers
        if 'pollut' in query_lower or 'worst' in query_lower or 'most' in query_lower:
            top = self.df.groupby('Basin', observed=True)['WQI'].mean().nlargest(10)
            context_parts.append("\nMost polluted basins (by avg WQI):")
            for basin, wqi_val in top.items():
                context_parts.append(f"  {basin}: WQI {wqi_val:.1f}")

        # CPCB standards reference
        if 'standard' in query_lower or 'safe' in query_lower or 'limit' in query_lower:
            context_parts.append(
                "\nCPCB Standards: DO ≥ 6 mg/L (Class A), BOD ≤ 3 mg/L (Class B), "
                "pH 6.5–8.5, Fecal Coliform ≤ 500 MPN/100mL, Turbidity ≤ 10 NTU (drinking)"
            )

        return "\n".join(context_parts)

    # ─── REPORT DATA ─────────────────────────────────────────────

    def get_report_data(self, scope, scope_value, start_year, end_year, parameters):
        """Get filtered data for report generation."""
        data = self.df.copy()

        # Filter by scope
        if scope == 'station':
            data = data[data['Station_Name'].str.contains(scope_value, case=False, na=False)]
        elif scope == 'district':
            data = data[data['District'].str.lower() == scope_value.lower()]
        elif scope == 'state':
            data = data[data['State'].str.lower() == scope_value.lower()]
        elif scope == 'basin':
            data = data[data['Basin'].str.lower() == scope_value.lower()]

        # Filter by year range
        if start_year:
            data = data[data['Year'] >= int(start_year)]
        if end_year:
            data = data[data['Year'] <= int(end_year)]

        # Select parameters
        base_cols = ['Station_Name', 'State', 'District', 'Basin', 'Year',
                     'Date', 'Latitude', 'Longitude', 'Safety', 'WQI']
        param_cols = [p for p in parameters if p in data.columns]
        cols = base_cols + param_cols

        return data[cols]

    # ─── LIVE FEED ───────────────────────────────────────────────

    def get_random_station_reading(self):
        """Pick a random station and generate a synthetic reading with ±10% noise."""
        import random

        # Get unique stations with their average readings
        sample = self.df.sample(1).iloc[0]

        def add_noise(val, pct=0.1):
            if pd.isna(val) or val == 0:
                return val
            noise = val * random.uniform(-pct, pct)
            return round(float(val + noise), 2)

        return {
            'station': str(sample['Station_Name']),
            'state': str(sample['State']),
            'district': str(sample['District']),
            'basin': str(sample['Basin']),
            'lat': _safe_float(sample['Latitude']),
            'lng': _safe_float(sample['Longitude']),
            'do': add_noise(sample['DO']),
            'bod': add_noise(sample['BOD']),
            'ph': add_noise(sample['pH'], 0.02),
            'turbidity': add_noise(sample['Turbidity']),
            'fcol': add_noise(sample['Fecal_Coliform']),
            'ec': add_noise(sample['EC']),
            'wqi': _safe_round(calculate_wqi(
                do=sample['DO'], bod=sample['BOD'], ph=sample['pH'],
                turbidity=sample['Turbidity'], fcol=sample['Fecal_Coliform']
            )),
            'safety': str(sample['Safety']),
        }


# ─── HELPERS ─────────────────────────────────────────────────────

import math as _math


def _safe_float(val):
    """Convert to float, returning None for NaN or Infinity (not valid JSON)."""
    if pd.isna(val):
        return None
    f = float(val)
    if _math.isinf(f) or _math.isnan(f):
        return None
    return round(f, 6)


def _safe_round(val, decimals=2):
    """Round to N decimals, returning None for NaN or Infinity (not valid JSON)."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if _math.isinf(f) or _math.isnan(f):
        return None
    return round(f, decimals)



# Singleton instance
data_service = DataService()
