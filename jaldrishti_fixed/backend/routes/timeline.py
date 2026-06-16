"""
Timeline API — /api/timeline
Returns station-level aggregated data for a given year + data coverage.
"""
from flask import Blueprint, request, jsonify
from services.data_service import data_service
from utils.cache import cache

timeline_bp = Blueprint('timeline', __name__)


@timeline_bp.route('/api/timeline', methods=['GET'])
def get_timeline():
    """
    GET /api/timeline?year=2020&state=Gujarat
    Returns station data for a year + coverage histogram.
    """
    year = request.args.get('year', 'all')
    state = request.args.get('state', 'all')

    cache_key = f"timeline_{year}_{state}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        result = data_service.get_timeline_data(year=year, state=state)
        cache.set(cache_key, result, ttl=300)

        return jsonify({
            'success': True,
            'data': result,
            'meta': {
                'year': year,
                'state': state,
                'station_count': len(result.get('stations', []))
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@timeline_bp.route('/api/timeline/years', methods=['GET'])
def get_years():
    """GET /api/timeline/years — List all available years."""
    try:
        years = data_service.get_unique_years()
        return jsonify({'success': True, 'data': years})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@timeline_bp.route('/api/timeline/coverage', methods=['GET'])
def get_timeline_coverage():
    """GET /api/timeline/coverage — Get station count per year for coverage."""
    import pandas as pd
    state = request.args.get('state', 'all')
    cache_key = f"timeline_coverage_{state}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'coverage': cached})
    try:
        state_data = data_service.get_state_data(state)
        coverage = state_data.groupby('Year')['Station_Name'].nunique().to_dict()
        coverage = {str(int(k)): int(v) for k, v in coverage.items() if pd.notna(k)}
        cache.set(cache_key, coverage, ttl=300)
        return jsonify({'success': True, 'coverage': coverage})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@timeline_bp.route('/api/timeline/trend', methods=['GET'])
def get_timeline_trend():
    """GET /api/timeline/trend — Get average WQI per year for trend chart."""
    cache_key = "timeline_trend"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})
    try:
        if not hasattr(data_service, '_wqi_trend') or data_service._wqi_trend is None:
            trend_df = data_service.df.groupby('Year')['WQI'].mean().dropna().sort_index()
            data_service._wqi_trend = {str(int(y)): round(float(w), 2) for y, w in trend_df.items()}
        return jsonify({'success': True, 'data': data_service._wqi_trend})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
