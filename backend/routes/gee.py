"""Google Earth Engine Data-Points Route

Returns per-beach satellite water quality indices (CDOM, Turbidity, Chlorophyll, Kd490)
for display as data points on the Leaflet map, with exceedance limit checks.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from services.data_service import DataService
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

gee_bp = Blueprint('gee', __name__)

# Beach/coastal keywords matching the logic in DataService.get_beaches()
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


@gee_bp.route('/api/gee/data-points', methods=['GET'])
def get_gee_data_points():
    """Get per-beach satellite indices for map overlay.

    Query params:
        parameter: cdom | turbidity | chlorophyll | kd490 (default: cdom)
        date: YYYY-MM-DD (optional, defaults to recent)

    Returns list of data points with coordinates, value, status, exceedance info.
    """
    parameter = request.args.get('parameter', 'cdom')
    date_str = request.args.get('date')

    valid_params = ['cdom', 'turbidity', 'chlorophyll', 'kd490']
    if parameter not in valid_params:
        return jsonify({'success': False, 'error': f'Invalid parameter. Use: {valid_params}'}), 400

    try:
        ds = DataService()
        df = ds.df

        # Filter to beach/coastal stations only
        name_lower = df['Station_Name'].str.lower().fillna('')
        beach_mask = name_lower.str.contains('|'.join(_BEACH_KEYWORDS), na=False)
        beach_df = df[beach_mask & df['Latitude'].notna() & df['Longitude'].notna()]

        if beach_df.empty:
            # Return mock beaches if none found
            mock_beaches = ds._generate_mock_beaches()
            beach_df = pd.DataFrame(mock_beaches)

        # Group by station to get unique beach locations
        beach_data = beach_df.groupby(['Station_Name', 'State'], observed=True).agg({
            'Latitude': 'mean',
            'Longitude': 'mean'
        }).dropna().reset_index()

        if beach_data.empty:
            return jsonify({'success': False, 'error': 'No beach data available'}), 404

        # Try GEE for satellite data
        from services.gee_service import GEEService, EXCEEDANCE_LIMITS, get_exceedance_style
        gee = GEEService()

        if not date_str:
            date_str = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        data_points = []
        param_gee_name = parameter
        if parameter == 'turbidity':
            param_gee_name = 'ndti'

        for _, row in beach_data.iterrows():
            lat, lon = row['Latitude'], row['Longitude']
            if pd.isna(lat) or pd.isna(lon):
                continue

            beach_name = str(row['Station_Name'])
            bbox = [lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5]

            value = 0.0
            source = 'proxy'

            if gee.is_available():
                try:
                    start = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
                    end = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
                    indices = gee.get_water_quality_indices(bbox, start, end)
                    vals = indices.get(param_gee_name, {})
                    val = vals.get('mean', 0.0)
                    if val is not None and not np.isnan(val) and val > 0.0:
                        value = float(val)
                        source = 'gee'
                except Exception as e:
                    logger.debug(f"[GEE] No data for {beach_name}: {e}")

            if source == 'proxy':
                value = _get_beach_proxy_value(df, beach_name, parameter)

            exceedance = gee.get_exceedance_status(parameter, value)
            style = get_exceedance_style(parameter, value)

            data_points.append({
                'name': beach_name,
                'lat': float(lat),
                'lon': float(lon),
                'value': round(value, 4),
                'parameter': parameter,
                'status': exceedance['status'],
                'limit': exceedance['limit'],
                'unit': exceedance['unit'],
                'source': source,
                'style': style
            })

        return jsonify({
            'success': True,
            'data': {
                'points': data_points,
                'total': len(data_points),
                'date': date_str,
                'parameter': parameter,
                'source': 'gee' if gee.is_available() else 'proxy'
            }
        })

    except Exception as e:
        logger.error(f"[GEE] Failed to get data points: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_beach_proxy_value(df, beach_name, parameter):
    """Generate a proxy value for a beach based on CPCB data correlations."""
    beach_data = df[df['Station_Name'].str.lower() == beach_name.lower()]
    if beach_data.empty:
        # Fall back to any coastal data
        name_lower = df['Station_Name'].str.lower().fillna('')
        mask = name_lower.str.contains('|'.join(_BEACH_KEYWORDS), na=False)
        beach_data = df[mask]

    do = beach_data['DO'].mean() if 'DO' in beach_data.columns else 7
    bod = beach_data['BOD'].mean() if 'BOD' in beach_data.columns else 5

    proxy_map = {
        'cdom': max(0.0, min(1.0, (10 - do) / 10)),
        'turbidity': max(0.0, min(1.0, (bod - 3) / 7)),
        'chlorophyll': max(0.0, min(5.0, bod / 2)),
        'kd490': max(0.0, min(1.0, bod / 10)),
    }
    return proxy_map.get(parameter, 0.0)
