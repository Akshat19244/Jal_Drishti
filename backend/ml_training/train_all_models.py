"""Train All Models Script

Trains Model A (CPCB) and Model B (Satellite) for all parameters.
Run this script offline to generate model artifacts.

Usage:
    python backend/ml_training/train_all_models.py
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from services.model_a_cpcb import ModelACPCB
from services.model_b_satellite import ModelBSatellite
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Train all models"""
    logger.info("=" * 60)
    logger.info("Starting Model Training Pipeline")
    logger.info("=" * 60)
    
    # CSV path (in project root, one level up from backend/)
    csv_path = backend_dir.parent / "india_research_full.csv"
    
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        logger.info("Please ensure india_research_full.csv is in the backend directory")
        return
    
    # Train Model A
    logger.info("\n" + "=" * 60)
    logger.info("Training Model A: CPCB Ground-Truth Classifier")
    logger.info("=" * 60)
    
    try:
        model_a = ModelACPCB()
        model_a.train_all_models(str(csv_path))
        logger.info("Model A training completed successfully")
    except Exception as e:
        logger.error(f"Model A training failed: {e}")
    
    # Train Model B
    logger.info("\n" + "=" * 60)
    logger.info("Training Model B: Satellite Spectral Classifier")
    logger.info("=" * 60)
    
    try:
        model_b = ModelBSatellite()
        # Uses GEE (Sentinel-2) -> NASA Ocean Color -> proxy fallback chain.
        # earthengine authenticate required for live GEE data.
        model_b.train_all_models(str(csv_path), use_real_satellite=True)
        logger.info("Model B training completed successfully")
    except Exception as e:
        logger.error(f"Model B training failed: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("Model Training Pipeline Completed")
    logger.info("=" * 60)
    logger.info(f"Model artifacts saved to: {backend_dir / 'ml_models'}")


if __name__ == '__main__':
    main()
