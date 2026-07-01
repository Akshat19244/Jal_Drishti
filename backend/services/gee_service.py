"""Google Earth Engine Service for Satellite Water Quality Indices

Replaces the Sentinel Hub Processing API with GEE's free Sentinel-2 Level-2A access.
Calculates inland water quality indices at 10-20m resolution:
- NDWI (Normalized Difference Water Index)
- NDCI (Normalized Difference Chlorophyll Index)
- NDTI (Normalized Difference Turbidity Index)
- CDOM (Colored Dissolved Organic Matter proxy)
- Chlorophyll-a (Red-Edge based)
- Kd490 (Light Attenuation)

Usage:
    1. pip install earthengine-api
    2. Run once: earthengine authenticate
    3. Service auto-detects availability and falls back to proxy data when GEE is not initialized.
"""

import os
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# CPCB / spectral-index threshold limits for exceedance detection
EXCEEDANCE_LIMITS = {
    'cdom':         {'low': 0.3,  'high': 0.6,  'unit': 'ratio'},
    'turbidity':    {'low': 0.4,  'high': 0.7,  'unit': 'ratio'},
    'chlorophyll':  {'low': 0.3,  'high': 0.5,  'unit': 'ratio'},
    'kd490':        {'low': 0.2,  'high': 0.4,  'unit': 'm-1'},
    'ndwi':         {'low': -0.3, 'high': 0.3,  'unit': 'ratio'},
    'ndci':         {'low': -0.1, 'high': 0.2,  'unit': 'ratio'},
    'ndti':         {'low': 0.1,  'high': 0.4,  'unit': 'ratio'},
}


class GEEService:
    """Fetch water quality indices from Google Earth Engine Sentinel-2 imagery.

    Singleton – shares one ee.Initialize() across the process.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        GEEService._initialized = True

        self.available = False
        self.initialization_error = None

        try:
            import ee
            import json
            project = os.getenv('GEE_PROJECT', '')
            service_account_key = os.getenv('GEE_SERVICE_ACCOUNT_KEY', '')
            if service_account_key:
                credentials = ee.ServiceAccountCredentials(None, key_data=service_account_key)
                ee.Initialize(credentials, project=project)
            elif project:
                ee.Initialize(project=project)
            else:
                ee.Initialize()
            self.ee = ee
            self.available = True
            logger.info(f"[GEE] Google Earth Engine initialized (project={project or 'default'})")
        except Exception as e:
            self.initialization_error = str(e)
            logger.warning(f"[GEE] Earth Engine not available: {e}")
            logger.warning("[GEE] To enable live satellite data:")
            logger.warning("[GEE] 1. Create a Cloud Project: https://console.cloud.google.com/")
            logger.warning("[GEE] 2. Enable Earth Engine API")
            logger.warning("[GEE] 3. Set GEE_PROJECT=<your-project-id> in .env")
            logger.warning("[GEE] 4. For Render: set GEE_SERVICE_ACCOUNT_KEY (JSON key string)")
            logger.warning("[GEE] Or run: earthengine set_project <your-project-id>")

    def is_available(self) -> bool:
        return self.available

    def get_water_quality_indices(self, bbox: List[float],
                                  start_date: str, end_date: str,
                                  max_cloud_cover: int = 30) -> Dict:
        """Get mean spectral indices for a bounding box from Sentinel-2.

        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat]
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            max_cloud_cover: Max cloud cover percentage filter

        Returns:
            Dict with keys: ndwi, ndci, ndti, cdom, chlorophyll, kd490
                    Each value is a dict: {mean, min, max, std, count}
        """
        if not self.available:
            raise RuntimeError(f"GEE not initialized: {self.initialization_error}")

        try:
            aoi = self.ee.Geometry.Rectangle(bbox)
            s2 = (self.ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(aoi)
                  .filterDate(start_date, end_date)
                  .filter(self.ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud_cover)))

            count = s2.size().getInfo()
            if count == 0:
                logger.warning(f"[GEE] No Sentinel-2 scenes found for bbox {bbox} in {start_date}–{end_date}")
                raise ValueError("No scenes found")

            image = s2.median()

            ndwi = image.normalizedDifference(['B3', 'B8']).rename('ndwi')
            ndci = image.normalizedDifference(['B5', 'B4']).rename('ndci')
            ndti = image.normalizedDifference(['B4', 'B3']).rename('ndti')
            cdom_img = image.select('B2').divide(image.select('B4').add(0.001)).rename('cdom')
            chlor_img = image.normalizedDifference(['B5', 'B4']).rename('chlorophyll')
            kd490_img = image.select('B3').divide(image.select('B2').add(0.001)).multiply(0.5).rename('kd490')

            fused = image.addBands([ndwi, ndci, ndti, cdom_img, chlor_img, kd490_img])

            band_names = ['ndwi', 'ndci', 'ndti', 'cdom', 'chlorophyll', 'kd490']

            stats = fused.select(band_names).reduceRegion(
                reducer=self.ee.Reducer.mean().combine(
                    self.ee.Reducer.minMax(), sharedInputs=True
                ).combine(
                    self.ee.Reducer.stdDev(), sharedInputs=True
                ),
                geometry=aoi,
                scale=20,
                maxPixels=1e9,
                bestEffort=True
            ).getInfo()

            result = {}
            for band in band_names:
                mean_val = stats.get(f'{band}_mean', 0.0)
                min_val = stats.get(f'{band}_min', 0.0)
                max_val = stats.get(f'{band}_max', 0.0)
                std_val = stats.get(f'{band}_stdDev', 0.0)
                count_val = stats.get(f'{band}_count', 0)

                if mean_val is None or np.isnan(mean_val):
                    mean_val = 0.0

                result[band] = {
                    'mean': float(mean_val),
                    'min': 0.0 if (min_val is None or np.isnan(min_val)) else float(min_val),
                    'max': 0.0 if (max_val is None or np.isnan(max_val)) else float(max_val),
                    'std': float(std_val) if (std_val is not None and not np.isnan(std_val)) else 0.0,
                    'count': int(count_val) if count_val else 0,
                }

            logger.info(f"[GEE] Extracted indices for bbox {bbox}: "
                        f"NDWI={result['ndwi']['mean']:.3f}, "
                        f"CDOM={result['cdom']['mean']:.3f}, "
                        f"Turbidity={result['ndti']['mean']:.3f}")
            return result

        except Exception as e:
            logger.error(f"[GEE] Failed to get indices for bbox {bbox}: {e}")
            raise

    def get_exceedance_status(self, param: str, value: float) -> Dict:
        """Check if a parameter value exceeds safe limits.

        Returns:
            {'status': 'safe'|'moderate'|'exceeded', 'limit': L, 'unit': str}
        """
        limits = EXCEEDANCE_LIMITS.get(param, {'low': 0.3, 'high': 0.6, 'unit': 'ratio'})
        if value <= limits['low']:
            return {'status': 'safe', 'limit': limits['high'], 'unit': limits['unit']}
        elif value <= limits['high']:
            return {'status': 'moderate', 'limit': limits['high'], 'unit': limits['unit']}
        else:
            return {'status': 'exceeded', 'limit': limits['high'], 'unit': limits['unit']}

    def _generate_synthetic_indices(self) -> Dict:
        """Return synthetic/no-data placeholder indices."""
        bands = ['ndwi', 'ndci', 'ndti', 'cdom', 'chlorophyll', 'kd490']
        return {
            b: {'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0, 'count': 0}
            for b in bands
        }


def get_exceedance_style(param: str, value: float) -> Dict:
    """Return Leaflet-compatible style dict based on parameter exceedance."""
    limits = EXCEEDANCE_LIMITS.get(param, {'low': 0.3, 'high': 0.6})
    if value <= limits['low']:
        return {'color': '#16A34A', 'fillColor': '#16A34A', 'fillOpacity': 0.7, 'radius': 7}
    elif value <= limits['high']:
        return {'color': '#D97706', 'fillColor': '#D97706', 'fillOpacity': 0.7, 'radius': 8}
    else:
        return {'color': '#DC2626', 'fillColor': '#DC2626', 'fillOpacity': 0.8, 'radius': 10}
