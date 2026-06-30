"""Inference/Fusion Layer

Combines Model A and Model B outputs, showing both individually plus a combined verdict.
No silent averaging - always shows both model outputs.
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class InferenceFusion:
    """Fuses predictions from Model A and Model B"""
    
    def __init__(self):
        self.agreement_threshold = 0.7  # Confidence threshold for high agreement
    
    def fuse_predictions(self, model_a_result: Dict, model_b_result: Dict) -> Dict:
        """
        Fuse predictions from both models
        
        Args:
            model_a_result: {"class": "Unsafe", "confidence": 0.78, "source": "..."}
            model_b_result: {"class": "Moderate", "confidence": 0.61, "source": "..."}
            
        Returns:
            Combined prediction with agreement indicator
        """
        # Validate inputs
        if not model_a_result or not model_b_result:
            logger.warning("[Fusion] Missing model predictions")
            return self._fallback_fusion(model_a_result, model_b_result)
        
        class_a = model_a_result.get('class')
        class_b = model_b_result.get('class')
        conf_a = model_a_result.get('confidence', 0.5)
        conf_b = model_b_result.get('confidence', 0.5)
        
        # Check if models agree
        if class_a == class_b:
            verdict = class_a
            agreement = "high"
            combined_confidence = (conf_a + conf_b) / 2
            agreement_message = "✓ Both models agree"
        else:
            # Models disagree - weight by confidence
            if conf_a >= conf_b:
                verdict = class_a
            else:
                verdict = class_b
            
            # Calculate agreement level based on confidence difference
            confidence_diff = abs(conf_a - conf_b)
            if confidence_diff < 0.2:
                agreement = "low"
                agreement_message = "⚠ Models disagree — see individual results"
            else:
                agreement = "moderate"
                agreement_message = "⚠ Models disagree — weighted by confidence"
            
            combined_confidence = max(conf_a, conf_b) - (confidence_diff * 0.5)
        
        return {
            'model_a': model_a_result,
            'model_b': model_b_result,
            'combined_verdict': verdict,
            'agreement': agreement,
            'agreement_message': agreement_message,
            'combined_confidence': round(combined_confidence, 3)
        }
    
    def _fallback_fusion(self, model_a_result: Optional[Dict], model_b_result: Optional[Dict]) -> Dict:
        """Return fallback fusion when one or both models are unavailable"""
        if model_a_result and not model_b_result:
            return {
                'model_a': model_a_result,
                'model_b': {
                    'class': 'Moderate',
                    'confidence': 0.5,
                    'source': 'Model B unavailable',
                    'model': 'Model B (Satellite Spectral)'
                },
                'combined_verdict': model_a_result.get('class', 'Moderate'),
                'agreement': 'unknown',
                'agreement_message': '⚠ Model B unavailable — using Model A only',
                'combined_confidence': model_a_result.get('confidence', 0.5) * 0.8
            }
        elif model_b_result and not model_a_result:
            return {
                'model_a': {
                    'class': 'Moderate',
                    'confidence': 0.5,
                    'source': 'Model A unavailable',
                    'model': 'Model A (CPCB Ground-Truth)'
                },
                'model_b': model_b_result,
                'combined_verdict': model_b_result.get('class', 'Moderate'),
                'agreement': 'unknown',
                'agreement_message': '⚠ Model A unavailable — using Model B only',
                'combined_confidence': model_b_result.get('confidence', 0.5) * 0.8
            }
        else:
            return {
                'model_a': {
                    'class': 'Moderate',
                    'confidence': 0.5,
                    'source': 'Model A unavailable',
                    'model': 'Model A (CPCB Ground-Truth)'
                },
                'model_b': {
                    'class': 'Moderate',
                    'confidence': 0.5,
                    'source': 'Model B unavailable',
                    'model': 'Model B (Satellite Spectral)'
                },
                'combined_verdict': 'Moderate',
                'agreement': 'unknown',
                'agreement_message': '⚠ Both models unavailable — using default',
                'combined_confidence': 0.3
            }
    
    def get_explanation(self, result: Dict) -> str:
        """Generate explanation text for the fusion result"""
        model_a_source = result.get('model_a', {}).get('source', 'CPCB historical patterns')
        model_b_source = result.get('model_b', {}).get('source', 'Sentinel-2 spectral indices')
        
        explanation = (
            f"Model A uses {model_a_source} for this river body. "
            f"Model B uses {model_b_source} independent of ground measurements. "
            f"Agreement between both increases confidence in the verdict."
        )
        
        return explanation
