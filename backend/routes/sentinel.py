"""Sentinel-2 Routes

API endpoints for fetching Sentinel-2 satellite water quality indices
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import os

sentinel_bp = Blueprint('sentinel', __name__)


@sentinel_bp.route('/api/sentinel/indices', methods=['GET'])
def get_sentinel_indices():
    """
    Get Sentinel-2 water quality indices for India
    
    Query params:
        date: Date in YYYY-MM-DD format (optional, defaults to most recent)
        return_image: If 'true', returns base64-encoded image for spatial visualization
    """
    from services.sentinel_service import SentinelService
    
    try:
        date = request.args.get('date')
        return_image = request.args.get('return_image', '').lower() == 'true'
        sentinel_service = SentinelService()
        indices = sentinel_service.get_india_indices(date, return_image)
        
        return jsonify({
            'success': True,
            'data': indices
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sentinel_bp.route('/api/sentinel/historical', methods=['GET'])
def get_sentinel_historical():
    """
    Get historical Sentinel-2 indices for a date range
    
    Query params:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    from services.sentinel_service import SentinelService
    
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date are required'
            }), 400
        
        sentinel_service = SentinelService()
        indices = sentinel_service.get_historical_indices(start_date, end_date)
        
        return jsonify({
            'success': True,
            'data': indices
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@sentinel_bp.route('/api/sentinel/status', methods=['GET'])
def get_sentinel_status():
    """
    Get Sentinel-2 service status and configuration
    """
    api_key = os.getenv('SENTINEL_HUB_API_KEY')
    use_live_data = bool(api_key)
    
    return jsonify({
        'success': True,
        'data': {
            'live_data_enabled': use_live_data,
            'api_configured': bool(api_key),
            'api_provider': 'Copernicus Sentinel Hub' if use_live_data else 'Synthetic (CPCB correlations)',
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    })
