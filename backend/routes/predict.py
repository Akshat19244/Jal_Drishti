"""
Predict API — /api/predict
Handles ML predictions for water quality parameters.
"""
from flask import Blueprint, request, jsonify
from services.ml_service import MLService

predict_bp = Blueprint('predict', __name__)

@predict_bp.route('/api/predict', methods=['POST'])
def predict_water_quality():
    """
    POST /api/predict
    Expects JSON: { "state": "Gujarat", "station": "Sabarmati-1", "parameter": "DO" }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No JSON payload provided'}), 400
        
    state = data.get('state')
    station = data.get('station')
    parameter = data.get('parameter')
    
    if not state or not station or not parameter:
        return jsonify({'success': False, 'error': 'state, station, and parameter are required'}), 400
        
    try:
        ml_service = MLService()
        result = ml_service.predict(state, station, parameter)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
