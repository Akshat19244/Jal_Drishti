"""Google Earth Engine Data-Points Route

Returns per-river-body satellite water quality indices (CDOM, Turbidity, Chlorophyll, Kd490)
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


@gee_bp.route('/api/gee/data-points', methods=['GET'])
def get_gee_data_points():
    """Get per-river-body satellite indices for map overlay.

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

        # Get unique river bodies with coordinates
        group_col = 'River_Body' if 'River_Body' in df.columns else 'Basin'
        river_data = df.groupby(group_col).agg({
            'Latitude': 'mean',
            'Longitude': 'mean'
        }).dropna().reset_index()

        if river_data.empty:
            return jsonify({'success': False, 'error': 'No river body data available'}), 404

        # Try GEE for satellite data
        from services.gee_service import GEEService, EXCEEDANCE_LIMITS, get_exceedance_style
        gee = GEEService()

        if not date_str:
            date_str = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        data_points = []
        param_gee_name = parameter
        if parameter == 'turbidity':
            param_gee_name = 'ndti'

        for _, row in river_data.iterrows():
            lat, lon = row['Latitude'], row['Longitude']
            if pd.isna(lat) or pd.isna(lon):
                continue

            river_name = row[group_col]
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
                    logger.debug(f"[GEE] No data for {river_name}: {e}")

            if source == 'proxy':
                value = _get_proxy_value(df, river_name, parameter)

            exceedance = gee.get_exceedance_status(parameter, value)
            style = get_exceedance_style(parameter, value)

            data_points.append({
                'river_name': river_name,
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


def _get_proxy_value(df, river_name, parameter):
    """Generate a proxy value for a river body based on CPCB data correlations."""
    group_col = 'River_Body' if 'River_Body' in df.columns else 'Basin'
    river_data = df[df[group_col] == river_name]
    if river_data.empty:
        return 0.0

    do = river_data['DO'].mean() if 'DO' in river_data.columns else 7
    bod = river_data['BOD'].mean() if 'BOD' in river_data.columns else 5

    proxy_map = {
        'cdom': max(0.0, min(1.0, (10 - do) / 10)),
        'turbidity': max(0.0, min(1.0, (bod - 3) / 7)),
        'chlorophyll': max(0.0, min(5.0, bod / 2)),
        'kd490': max(0.0, min(1.0, bod / 10)),
    }
    return proxy_map.get(parameter, 0.0)
