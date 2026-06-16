"""
Stations API — /api/stations
FIX: Moved 'import pandas as pd' to top of file (was at bottom, causing NameError in search endpoint).
"""
import pandas as pd
from flask import Blueprint, request, jsonify
from services.data_service import DataService
from utils.cache import TTLCache

stations_bp = Blueprint('stations', __name__)
cache = TTLCache()


@stations_bp.route('/api/stations', methods=['GET'])
def get_stations():
    state = request.args.get('state', 'all')
    basin = request.args.get('basin', None)
    year  = request.args.get('year', None)
    state_filter = request.args.get('state_filter', None)
    if state_filter and state_filter not in ('all',''):
        state = state_filter

    cache_key = f"stations_{state}_{basin}_{year}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        stations = ds.get_stations(state=state, basin=basin, year=year)
        cache.set(cache_key, stations, ttl=300)
        return jsonify({
            'success': True, 'data': stations,
            'meta': {'count': len(stations), 'state': state, 'basin': basin or 'all', 'year': year or 'all'}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@stations_bp.route('/api/stations/all-india', methods=['GET'])
def get_all_india_stations():
    year = request.args.get('year', None)
    cache_key = f"stations_all_india_{year}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})
    try:
        ds = DataService()
        stations = ds.get_stations(state='all', basin=None, year=year)
        cache.set(cache_key, stations, ttl=300)
        return jsonify({
            'success': True, 'data': stations,
            'meta': {'count': len(stations), 'view': 'all-india', 'year': year or 'all'}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@stations_bp.route('/api/stations/namo-gangu', methods=['GET'])
def get_namo_gangu():
    cache_key = "stations_namo_gangu"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})
    try:
        ds = DataService()
        summary = ds.get_namo_gangu_summary()
        cache.set(cache_key, summary, ttl=600)
        return jsonify({
            'success': True, 'data': summary,
            'meta': {'mode': 'namo-gangu', 'basin': 'Ganga'}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@stations_bp.route('/api/stations/search', methods=['GET'])
def search_stations():
    query = request.args.get('q', '')
    state = request.args.get('state', 'all')
    limit = int(request.args.get('limit', 20))

    if not query or len(query) < 2:
        return jsonify({'success': False, 'error': 'Query too short (min 2 chars)'}), 400

    try:
        ds = DataService()
        data = ds.get_state_data(state)
        mask = data['Station_Name'].str.contains(query, case=False, na=False)
        matches = data[mask]['Station_Name'].unique()

        results = []
        for station_name in matches[:limit]:
            row = data[data['Station_Name'] == station_name].iloc[0]
            results.append({
                'name': str(station_name),
                'state': str(row['State']),
                'district': str(row['District']),
                'basin': str(row['Basin']),
                'wqi': round(float(row['WQI']), 2) if pd.notna(row['WQI']) else None,
            })
        return jsonify({'success': True, 'data': results, 'meta': {'query': query, 'count': len(results)}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@stations_bp.route('/api/filters', methods=['GET'])
def get_filters():
    """
    GET /api/filters
    Returns all states, basins, and water body types for dynamic dropdown population.
    """
    cache_key = "filters_all"
    from utils.cache import TTLCache
    _c = TTLCache()
    cached = _c.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})
    try:
        ds = DataService()
        result = {
            'states':            ds.get_unique_states(),
            'basins':            ds.get_unique_basins(),
            'water_body_types':  ds.get_all_water_body_filters(),
        }
        _c.set(cache_key, result, ttl=3600)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
