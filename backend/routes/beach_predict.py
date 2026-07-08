"""
Beach Water Quality Classification API
Predicts if a beach is safe for swimming using ML trained on india_beaches_merged.csv
Provides detailed, interpretable results for non-technical users.
"""
from flask import Blueprint, request, jsonify
from services.beach_predict_service import beach_predict_service

beach_predict_bp = Blueprint('beach_predict', __name__)


@beach_predict_bp.route('/api/beach-predict/stations', methods=['GET'])
def get_beach_stations():
    """GET /api/beach-predict/stations — List all available beach stations for prediction."""
    try:
        stations = beach_predict_service.get_stations()
        return jsonify({'success': True, 'data': stations, 'total': len(stations)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@beach_predict_bp.route('/api/beach-predict/status', methods=['GET'])
def get_model_status():
    """GET /api/beach-predict/status — Model performance metrics and feature importance."""
    try:
        status = beach_predict_service.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@beach_predict_bp.route('/api/beach-predict', methods=['POST'])
def predict_beach():
    """
    POST /api/beach-predict
    Body: { "station": "Juhu Beach" }
    Returns beach swimming classification with detailed parameter analysis.
    """
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({'success': False, 'error': 'No JSON payload'}), 400

        station = payload.get('station', '').strip()
        if not station:
            return jsonify({'success': False, 'error': 'station name is required'}), 400

        result = beach_predict_service.predict(station)
        if result is None:
            return jsonify({
                'success': False,
                'error': f'Station "{station}" not found in beach database'
            }), 404

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
