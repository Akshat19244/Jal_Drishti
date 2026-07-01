"""Satellite Water Quality Indices Service (GEE-powered)

Replaces the deprecated Sentinel Hub Processing API with Google Earth Engine.
Calculates inland water quality indices at 10-20m resolution from Sentinel-2 Level-2A.

Fallback chain:
    1. Google Earth Engine (Sentinel-2)
    2. NASA OceanColor (MODIS Aqua)
    3. Synthetic data (seasonal patterns)
"""

import os
import logging
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from io import BytesIO
from PIL import Image

logger = logging.getLogger(__name__)


# Shared in-memory cache for generated map PNGs (keyed by date)
_map_png_cache: Dict[str, bytes] = {}


class SentinelService:
    """Service for fetching satellite water quality indices via GEE + fallbacks."""

    def __init__(self):
        self.gee_available = False
        self.gee_service = None

        try:
            from services.gee_service import GEEService
            self.gee_service = GEEService()
            self.gee_available = self.gee_service.is_available()
        except Exception as e:
            logger.warning(f"[Sentinel] GEE service init failed: {e}")

        self.use_nasa = bool(os.getenv('NASA_APPKEY'))

    def get_india_indices(self, date: Optional[str] = None, return_image: bool = False) -> Dict:
        """Get water quality indices for India.

        Fallback chain: GEE → NASA → Synthetic
        """
        if not date:
            date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        bbox = [72.0, 8.0, 93.5, 30.5]  # India bbox

        # 1. Try GEE (primary)
        if self.gee_available:
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                start = (date_obj - timedelta(days=15)).strftime('%Y-%m-%d')
                end = (date_obj + timedelta(days=15)).strftime('%Y-%m-%d')
                gee_data = self.gee_service.get_water_quality_indices(bbox, start, end)
                if gee_data:
                    result = self._convert_gee_format(gee_data, date, 'gee')
                    if return_image:
                        result.update(self._generate_map_image(date, gee_data, bbox))
                    return result
            except Exception as e:
                logger.warning(f"[Sentinel] GEE failed: {e}, trying NASA fallback")

        # 2. Try NASA OceanColor (fallback)
        if self.use_nasa:
            try:
                from services.nasa_ocean_color_service import NASAOceanColorService
                nasa = NASAOceanColorService()
                if nasa.use_live_data and not nasa._api_broken:
                    nasa_data = nasa.get_water_quality_indices(
                        bbox, date, ['chlorophyll', 'turbidity', 'cdom']
                    )
                    result = self._convert_nasa_format(nasa_data)
                    if return_image:
                        gee_fallback = self._make_fallback_indices(date)
                        result.update(self._generate_map_image(date, gee_fallback, bbox))
                    return result
            except Exception as e:
                logger.warning(f"[Sentinel] NASA fallback also failed: {e}")

        # 3. Final fallback: synthetic
        return self._generate_synthetic_indices(date, return_image)

    def _convert_gee_format(self, gee_data: Dict, date: str, source: str) -> Dict:
        """Convert GEE format to standard output format."""
        def get_status(param, value):
            from services.gee_service import EXCEEDANCE_LIMITS
            limits = EXCEEDANCE_LIMITS.get(param, {'low': 0.3, 'high': 0.6})
            if value <= limits['low']:
                return "Low" if param != 'kd490' else "Good"
            elif value <= limits['high']:
                return "Moderate"
            else:
                return "High" if param != 'kd490' else "Poor"

        cdom_val = gee_data.get('cdom', {}).get('mean', 0.0)
        turb_val = gee_data.get('ndti', {}).get('mean', 0.0)
        chlor_val = gee_data.get('chlorophyll', {}).get('mean', 0.0)
        kd_val = gee_data.get('kd490', {}).get('mean', 0.0)

        return {
            'date': date,
            'source': source,
            'cdom': {
                'value': round(cdom_val, 3),
                'unit': 'ratio',
                'status': get_status('cdom', cdom_val),
                'min': round(gee_data.get('cdom', {}).get('min', 0.0), 3),
                'max': round(gee_data.get('cdom', {}).get('max', 0.0), 3)
            },
            'turbidity': {
                'value': round(turb_val, 3),
                'unit': 'ratio',
                'status': get_status('turbidity', turb_val),
                'min': round(gee_data.get('ndti', {}).get('min', 0.0), 3),
                'max': round(gee_data.get('ndti', {}).get('max', 0.0), 3)
            },
            'chlorophyll': {
                'value': round(chlor_val, 3),
                'unit': 'ratio',
                'status': get_status('chlorophyll', chlor_val),
                'min': round(gee_data.get('chlorophyll', {}).get('min', 0.0), 3),
                'max': round(gee_data.get('chlorophyll', {}).get('max', 0.0), 3)
            },
            'kd490': {
                'value': round(kd_val, 3),
                'unit': 'm-1',
                'status': get_status('kd490', kd_val),
                'min': round(gee_data.get('kd490', {}).get('min', 0.0), 3),
                'max': round(gee_data.get('kd490', {}).get('max', 0.0), 3)
            }
        }

    def _convert_nasa_format(self, nasa_data: Dict) -> Dict:
        """Convert NASA OceanColor format to our standard format."""
        params = nasa_data.get('parameters', {})

        def get_status(value, param):
            from services.gee_service import EXCEEDANCE_LIMITS
            limits = EXCEEDANCE_LIMITS.get(param, {'low': 0.3, 'high': 0.6})
            if value <= limits['low']:
                return "Low"
            elif value <= limits['high']:
                return "Moderate"
            return "High"

        cdom_val = params.get('cdom', {}).get('mean', 0.0)
        turb_val = params.get('turbidity', {}).get('mean', 0.0)
        chlor_val = params.get('chlorophyll', {}).get('mean', 0.0)

        ndti_val = max(0, min(1, turb_val * 2 - 1)) if turb_val > 0 else 0.0

        return {
            'date': nasa_data['date'],
            'source': 'nasa_ocean_color',
            'cdom': {
                'value': round(cdom_val, 3),
                'unit': 'm-1',
                'status': get_status(cdom_val, 'cdom'),
                'min': round(params.get('cdom', {}).get('min', 0.0), 3),
                'max': round(params.get('cdom', {}).get('max', 0.0), 3)
            },
            'turbidity': {
                'value': round(ndti_val, 3),
                'unit': 'ratio',
                'status': get_status(ndti_val, 'turbidity'),
                'min': round(max(0, params.get('turbidity', {}).get('min', 0.0) * 2 - 1), 3),
                'max': round(min(1, params.get('turbidity', {}).get('max', 0.0) * 2 - 1), 3)
            },
            'chlorophyll': {
                'value': round(chlor_val, 3),
                'unit': 'mg/m3',
                'status': get_status(chlor_val, 'chlorophyll'),
                'min': round(params.get('chlorophyll', {}).get('min', 0.0), 3),
                'max': round(params.get('chlorophyll', {}).get('max', 0.0), 3)
            },
            'kd490': {
                'value': round(ndti_val * 0.4, 3),
                'unit': 'm-1',
                'status': get_status(ndti_val * 0.4, 'kd490'),
                'min': round(max(0, params.get('turbidity', {}).get('min', 0.0) * 0.8), 3),
                'max': round(min(1, params.get('turbidity', {}).get('max', 0.0) * 0.8), 3)
            }
        }

    def _make_fallback_indices(self, date: str) -> Dict:
        """Return zero-valued indices for map image generation."""
        return {b: {'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0, 'count': 0}
                for b in ['ndwi', 'ndci', 'ndti', 'cdom', 'chlorophyll', 'kd490']}

    def _generate_map_image(self, date: str, indices: Dict, bbox: List[float]) -> Dict:
        """Generate a simple spatial visualization PNG."""
        try:
            w_syn, h_syn = 400, 400

            lat_grid = np.linspace(0, 1, h_syn, dtype=np.float32)[:, None]
            lon_grid = np.linspace(0, 1, w_syn, dtype=np.float32)[None, :]
            coast = 1.0 - np.minimum(np.abs(lon_grid - 0.45), np.abs(lat_grid - 0.5)) * 1.5
            coast = np.clip(coast, 0.3, 1.0)

            seed_val = int(datetime.strptime(date, '%Y-%m-%d').strftime('%Y%m%d'))
            rs = np.random.RandomState(seed_val)
            noise_small = rs.uniform(0.85, 1.15, (h_syn // 8 + 1, w_syn // 8 + 1)).astype(np.float32)
            noise = np.array(Image.fromarray(noise_small).resize((w_syn, h_syn), Image.BILINEAR))

            cdom_val = indices.get('cdom', {}).get('mean', 0.3)
            turb_val = indices.get('ndti', {}).get('mean', 0.4)
            chlor_val = indices.get('chlorophyll', {}).get('mean', 0.3)
            kd_val = indices.get('kd490', {}).get('mean', 0.2)

            val = (cdom_val * 0.4 + turb_val * 0.3 + chlor_val * 0.2 + kd_val * 0.1)
            arr = val * coast * noise
            arr = np.clip(arr, 0.0, 1.0)

            norm = (arr * 255).clip(0, 255).astype(np.uint8)
            r = np.clip(norm * 4, 0, 255).astype(np.uint8)
            g = np.clip(norm * 4 - 255, 0, 255).astype(np.uint8)
            b = np.clip(255 - norm * 4, 0, 255).astype(np.uint8)
            rgb = np.stack([r, g, b], axis=2)

            img = Image.fromarray(rgb, 'RGB')
            png_buf = BytesIO()
            img.save(png_buf, format='PNG')
            _map_png_cache[date] = png_buf.getvalue()

            return {
                "image_url": f"/api/sentinel/map.png?date={date}",
                "image_bytes_len": len(png_buf.getvalue()),
                "bbox": bbox,
                "width": w_syn,
                "height": h_syn
            }
        except Exception as e:
            logger.warning(f"[Sentinel] Failed to generate map image: {e}")
            return {}

    def _generate_synthetic_indices(self, date: Optional[str] = None, return_image: bool = False) -> Dict:
        """Generate synthetic indices based on seasonal patterns."""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        dt = datetime.strptime(date, '%Y-%m-%d')
        month = dt.month
        is_monsoon = 6 <= month <= 9

        base_cdom = 0.35 + (0.15 if is_monsoon else 0)
        base_turbidity = 0.50 + (0.25 if is_monsoon else 0)
        base_chlorophyll = 0.30 + (0.10 if is_monsoon else 0)
        base_kd490 = 0.22 + (0.10 if is_monsoon else 0)

        import random
        random.seed(int(dt.strftime('%Y%m%d')))

        cdom = min(max(base_cdom + random.uniform(-0.05, 0.05), 0.1), 0.8)
        turbidity = min(max(base_turbidity + random.uniform(-0.08, 0.08), 0.2), 0.9)
        chlorophyll = min(max(base_chlorophyll + random.uniform(-0.06, 0.06), 0.1), 0.7)
        kd490 = min(max(base_kd490 + random.uniform(-0.04, 0.04), 0.1), 0.5)

        def get_status(value, low_threshold, high_threshold):
            if value < low_threshold:
                return "Low"
            elif value < high_threshold:
                return "Moderate"
            else:
                return "High"

        result = {
            "date": date,
            "source": "synthetic",
            "cdom": {
                "value": round(cdom, 3),
                "unit": "ratio",
                "status": get_status(cdom, 0.3, 0.6),
                "min": round(cdom - 0.1, 3),
                "max": round(cdom + 0.1, 3)
            },
            "turbidity": {
                "value": round(turbidity, 3),
                "unit": "ratio",
                "status": get_status(turbidity, 0.4, 0.7),
                "min": round(turbidity - 0.12, 3),
                "max": round(turbidity + 0.12, 3)
            },
            "chlorophyll": {
                "value": round(chlorophyll, 3),
                "unit": "ratio",
                "status": get_status(chlorophyll, 0.3, 0.5),
                "min": round(chlorophyll - 0.08, 3),
                "max": round(chlorophyll + 0.08, 3)
            },
            "kd490": {
                "value": round(kd490, 3),
                "unit": "m-1",
                "status": get_status(kd490, 0.2, 0.4),
                "min": round(kd490 - 0.06, 3),
                "max": round(kd490 + 0.06, 3)
            }
        }

        if return_image:
            bbox_syn = [72.0, 8.0, 93.5, 30.5]
            w_syn, h_syn = 400, 400
            lat_grid = np.linspace(0, 1, h_syn, dtype=np.float32)[:, None]
            lon_grid = np.linspace(0, 1, w_syn, dtype=np.float32)[None, :]
            coast = 1.0 - np.minimum(np.abs(lon_grid - 0.45), np.abs(lat_grid - 0.5)) * 1.5
            coast = np.clip(coast, 0.3, 1.0)
            seed_val = int(dt.strftime('%Y%m%d'))
            rs = np.random.RandomState(seed_val)
            noise_small = rs.uniform(0.85, 1.15, (h_syn // 8 + 1, w_syn // 8 + 1)).astype(np.float32)
            noise = np.array(Image.fromarray(noise_small).resize((w_syn, h_syn), Image.BILINEAR))
            val = (cdom * 0.4 + turbidity * 0.3 + chlorophyll * 0.2 + kd490 * 0.1)
            arr = val * coast * noise
            arr = np.clip(arr, 0.0, 1.0)
            norm = (arr * 255).clip(0, 255).astype(np.uint8)
            r = np.clip(norm * 4, 0, 255).astype(np.uint8)
            g = np.clip(norm * 4 - 255, 0, 255).astype(np.uint8)
            b = np.clip(255 - norm * 4, 0, 255).astype(np.uint8)
            rgb = np.stack([r, g, b], axis=2)
            img = Image.fromarray(rgb, 'RGB')
            png_buf = BytesIO()
            img.save(png_buf, format='PNG')
            _map_png_cache[date] = png_buf.getvalue()
            result["image_url"] = f"/api/sentinel/map.png?date={date}"
            result["image_bytes_len"] = len(png_buf.getvalue())
            result["bbox"] = bbox_syn
            result["width"] = w_syn
            result["height"] = h_syn

        return result

    @staticmethod
    def get_map_png(date: str) -> Optional[bytes]:
        return _map_png_cache.get(date)

    def get_historical_indices(self, start_date: str, end_date: str) -> List[Dict]:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        indices = []
        current = start
        while current <= end:
            indices.append(self.get_india_indices(current.strftime('%Y-%m-%d')))
            current += timedelta(days=7)
        return indices
