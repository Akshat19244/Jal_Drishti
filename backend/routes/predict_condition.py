"""Water Quality Condition Prediction Routes

Dual-model classification system using:
- Model A: CPCB Ground-Truth Classifier
- Model B: Satellite Spectral Classifier
- Inference Fusion Layer
"""

from flask import Blueprint, jsonify, request
from services.model_a_cpcb import ModelACPCB
from services.model_b_satellite import ModelBSatellite
from services.inference_fusion import InferenceFusion
from services.data_service import DataService
import logging

logger = logging.getLogger(__name__)

predict_condition_bp = Blueprint('predict_condition', __name__, url_prefix='/api/predict-condition')


@predict_condition_bp.route('/', methods=['POST'])
def predict_condition():
    """Predict water quality condition using dual-model system
    
    Request JSON:
        {
            "river_body": "Sabarmati",
            "parameter": "DO"
        }
        
    Response JSON:
        {
            "river_body": "Sabarmati",
            "parameter": "DO",
            "model_a": {
                "class": "Unsafe",
                "confidence": 0.78,
                "source": "CPCB historical patterns",
                "model": "Model A (CPCB Ground-Truth)"
            },
            "model_b": {
                "class": "Unsafe",
                "confidence": 0.65,
                "source": "Sentinel-2 spectral indices (proxy)",
                "model": "Model B (Satellite Spectral)",
                "data_source": "proxy"
            },
            "combined_verdict": "Unsafe",
            "agreement": "high",
            "agreement_message": "✓ Both models agree",
            "combined_confidence": 0.715,
            "explanation": "Model A uses..."
        }
    """
    try:
        data = request.get_json()
        river_body = data.get('river_body')
        parameter = data.get('parameter')
        
        if not river_body or not parameter:
            return jsonify({
                'success': False,
                'error': 'Missing required fields: river_body and parameter'
            }), 400
        
        logger.info(f"[Predict] River: {river_body}, Parameter: {parameter}")
        
        # Initialize models
        model_a = ModelACPCB()
        model_b = ModelBSatellite()
        fusion = InferenceFusion()
        
        # Load CPCB data for training/inference
        data_service = DataService()
        cpcb_df = data_service.df
        
        # Get predictions from both models
        model_a_result = model_a.predict(river_body, parameter, cpcb_df)
        model_b_result = model_b.predict(river_body, parameter, cpcb_df)
        
        # Fuse predictions
        fused_result = fusion.fuse_predictions(model_a_result, model_b_result)
        fused_result['river_body'] = river_body
        fused_result['parameter'] = parameter
        fused_result['explanation'] = fusion.get_explanation(fused_result)
        
        return jsonify({
            'success': True,
            'data': fused_result
        })
        
    except Exception as e:
        logger.error(f"[Predict] Prediction failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@predict_condition_bp.route('/river-bodies', methods=['GET'])
def get_river_bodies():
    """Get list of available river bodies for prediction"""
    try:
        data_service = DataService()
        df = data_service.df
        
        # Get unique river bodies
        if 'River_Body' in df.columns:
            river_bodies = sorted(df['River_Body'].dropna().unique().tolist())
        elif 'Basin' in df.columns:
            river_bodies = sorted(df['Basin'].dropna().unique().tolist())
        else:
            river_bodies = []
        
        return jsonify({
            'success': True,
            'data': {
                'river_bodies': river_bodies,
                'total': len(river_bodies)
            }
        })
        
    except Exception as e:
        logger.error(f"[Predict] Failed to get river bodies: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@predict_condition_bp.route('/parameters', methods=['GET'])
def get_parameters():
    """Get list of available parameters for prediction"""
    parameters = ['DO', 'BOD', 'pH', 'FC', 'EC', 'Nitrate', 'Turbidity']
    
    return jsonify({
        'success': True,
        'data': {
            'parameters': parameters,
            'total': len(parameters)
        }
    })
