"""NASA OceanColor Web Service for Satellite Water Quality Data

Fetches satellite data from NASA OB.DAAC via the official File Search HTTP POST API:
- Chlorophyll-a (chlor_a band)     → MODISA_L3m_CHL_chlor_a_9km
- Turbidity proxy (Kd_490 band)    → MODISA_L3m_KD490_Kd_490_9km
- CDOM (adg_443_giop absorption)   → MODISA_L3m_IOP_adg_443_giop_9km

Uses MODIS-Aqua sensor, Level-3 mapped (L3m) products.
File Search API: POST https://oceandata.sci.gsfc.nasa.gov/file_search
"""

import requests
import os
import xarray as xr
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

FILE_SEARCH_URL = "https://oceandata.sci.gsfc.nasa.gov/file_search"

# Map parameter names to product suite IDs and NetCDF variable names
PRODUCT_SUITES = {
    'chlorophyll': {'prod_id': 'CHL', 'var': 'chlor_a'},
    'turbidity':   {'prod_id': 'KD',  'var': 'Kd_490'},
    'cdom':        {'prod_id': 'IOP', 'var': 'adg_443'},
}

# (post-search filtering uses var name from PRODUCT_SUITES)


class NASAOceanColorService:
    """Service for fetching and processing NASA OceanColor Web data via OB.DAAC File Search API"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.api_key = os.getenv('NASA_APPKEY', '').strip()
        self.use_live_data = bool(self.api_key)
        self._api_broken = False  # becomes True after first 404/error

        self.parameter_bands = {k: v['var'] for k, v in PRODUCT_SUITES.items()}

        if not self.api_key:
            logger.warning("[NASA] NASA_APPKEY not configured. Service will use synthetic data.")

    # ─── File Search (POST) ───────────────────────────────────────

    def search_files(self, start_date: str, end_date: str, bbox: List[float],
                     parameters: List[str]) -> List[Dict]:
        """Search MODIS-Aqua L3m files via OB.DAAC POST API (one search per product).

        Args:
            start_date: YYYY-MM-DD
            end_date:   YYYY-MM-DD
            bbox:       [minLon, minLat, maxLon, maxLat]
            parameters: e.g. ['chlorophyll', 'turbidity']

        Returns:
            List of dicts with keys: 'filename', 'download_url', 'product_type'
        """
        if not self.api_key:
            raise ValueError("NASA_APPKEY not configured.")

        all_results = []
        sdate = f"{start_date} 00:00:00"
        edate = f"{end_date} 23:59:59"

        for param in parameters:
            suite = PRODUCT_SUITES.get(param)
            if not suite:
                continue

            payload = {
                'sensor_id': 7,
                'prod_id': suite['prod_id'],
                'sdate': sdate,
                'edate': edate,
                'results_as_file': 1,
                'addurl': 1,
            }

            logger.info(f"[NASA] POST search {suite['prod_id']}: {start_date}–{end_date}")
            try:
                resp = requests.post(FILE_SEARCH_URL, data=payload, timeout=60)
                resp.raise_for_status()
                lines = resp.text.strip().splitlines()

                if not lines or lines[0].strip() == 'No Results Found':
                    logger.warning(f"[NASA] No results for {suite['prod_id']}")
                    continue

                var_name = suite['var']
                for line in lines:
                    line = line.strip()
                    if not line or 'L3m' not in line:
                        continue
                    if var_name not in Path(line).stem:
                        continue
                    all_results.append({
                        'filename': Path(line).name,
                        'download_url': line,
                        'product_type': param,
                    })
            except requests.RequestException as e:
                logger.error(f"[NASA] Search failed for {suite['prod_id']}: {e}")
                if hasattr(e, 'response') and e.response is not None and e.response.status_code in (404, 401, 403, 500):
                    self._api_broken = True
                    logger.warning("[NASA] File Search API error – will use synthetic data for future calls")
                raise

        logger.info(f"[NASA] Found {len(all_results)} matching L3m files total")
        return all_results

    # ─── Download ─────────────────────────────────────────────────

    def download_file(self, download_url: str, output_path: str, chunk_size: int = 8192) -> str:
        """Download a NetCDF file authenticated via appkey query param."""
        if not self.api_key:
            raise ValueError("NASA_APPKEY not configured.")

        auth_url = f"{download_url}?appkey={self.api_key}"

        logger.info(f"[NASA] Downloading: {Path(download_url).name}")

        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            with requests.get(auth_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
            logger.info(f"[NASA] Downloaded to: {output_path}")
            return output_path
        except requests.RequestException as e:
            logger.error(f"[NASA] Download failed: {e}")
            raise

    # ─── Parse NetCDF ─────────────────────────────────────────────

    def parse_netcdf(self, file_path: str, bbox: Optional[List[float]] = None) -> Dict[str, np.ndarray]:
        """Parse NetCDF and extract parameter arrays, optionally subset by bbox.

        Uses xarray with spatial indexing (lat/lon slice) for subsetting.
        Falls back to rioxarray.clip_box if available for stricter bounding.
        """
        logger.info(f"[NASA] Parsing NetCDF: {file_path}")
        try:
            ds = xr.open_dataset(file_path)
            result = {}
            var_mapping = {
                'chlor_a': 'chlorophyll',
                'Kd_490': 'turbidity',
                'adg_443': 'cdom'
            }

            # Try rioxarray for proper spatial clip if available
            use_rio = False
            try:
                import rioxarray  # noqa: F401
                ds = ds.rio.write_crs("EPSG:4326")
                use_rio = True
            except ImportError:
                pass

            for nasa_var, param_name in var_mapping.items():
                if nasa_var not in ds:
                    continue
                arr = ds[nasa_var]

                if bbox:
                    if use_rio:
                        try:
                            arr = arr.rio.clip_box(
                                minx=bbox[0], miny=bbox[1],
                                maxx=bbox[2], maxy=bbox[3]
                            )
                        except Exception:
                            use_rio = False  # fall through to slice

                    if not use_rio and 'lat' in ds and 'lon' in ds:
                        lat_vals = ds.lat.values
                        lat_is_desc = lat_vals[0] > lat_vals[-1] if len(lat_vals) > 1 else False
                        if lat_is_desc:
                            lat_slice = slice(bbox[3], bbox[1])
                        else:
                            lat_slice = slice(bbox[1], bbox[3])
                        lon_vals = ds.lon.values
                        lon_is_desc = lon_vals[0] > lon_vals[-1] if len(lon_vals) > 1 else False
                        if lon_is_desc:
                            lon_slice = slice(bbox[2], bbox[0])
                        else:
                            lon_slice = slice(bbox[0], bbox[2])
                        arr = arr.sel(lat=lat_slice, lon=lon_slice)

                result[param_name] = np.nan_to_num(arr.values, nan=0.0)
                logger.info(f"[NASA] Extracted {param_name}: shape={arr.shape}")

            ds.close()
            if not result:
                raise ValueError("No valid parameters found in NetCDF")
            return result

        except Exception as e:
            logger.error(f"[NASA] NetCDF parse failed: {e}")
            raise ValueError(f"Failed to parse NetCDF: {e}")

    # ─── High-level convenience ───────────────────────────────────

    def _score_file(self, f: Dict) -> int:
        """Score a file: higher = better. Prefer 4km, non-NRT, daily."""
        name = f['filename']
        score = 0
        if '4km' in name:
            score += 3
        elif '9km' in name:
            score += 1
        if 'NRT' not in name:
            score += 2
        if '.DAY.' in name:
            score += 1
        return score

    def get_water_quality_indices(self, bbox: List[float], date: str,
                                  parameters: Optional[List[str]] = None,
                                  max_retries_per_product: int = 3) -> Dict:
        """Search → download → parse → stats for a date + location.

        Tries up to `max_retries_per_product` files per product type, then falls back to synthetic.
        """
        if parameters is None:
            parameters = ['chlorophyll', 'turbidity', 'cdom']

        if not self.use_live_data or self._api_broken:
            return self._generate_synthetic_indices(date, parameters)

        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            start = (date_obj - timedelta(days=3)).strftime('%Y-%m-%d')
            end = (date_obj + timedelta(days=3)).strftime('%Y-%m-%d')

            files = self.search_files(start, end, bbox, parameters)
            if not files:
                logger.warning("[NASA] No files found, using synthetic")
                return self._generate_synthetic_indices(date, parameters)

            # Group files by product_type, pick best per group
            by_type = defaultdict(list)
            for f in files:
                by_type[f['product_type']].append(f)

            result = {
                'date': date,
                'source': 'nasa_ocean_color',
                'bbox': bbox,
                'parameters': {}
            }

            temp_dir = Path("temp/nasa")
            temp_dir.mkdir(parents=True, exist_ok=True)
            downloaded = []

            for param, group in by_type.items():
                scored = [(self._score_file(f), f) for f in group]
                scored.sort(key=lambda x: -x[0])

                param_added = False
                attempts = 0
                for _, best in scored:
                    if attempts >= max_retries_per_product:
                        logger.info(f"[NASA] Max retries ({max_retries_per_product}) reached for {param}, stopping")
                        break
                    download_url = best.get('download_url')
                    if not download_url:
                        continue

                    unique_name = f"{best['product_type']}_{best['filename']}"
                    file_path = temp_dir / unique_name

                    try:
                        attempts += 1
                        self.download_file(download_url, str(file_path))
                        downloaded.append(file_path)
                        data_arrays = self.parse_netcdf(str(file_path), bbox)

                        for param_name, array in data_arrays.items():
                            valid = array[array > 0]
                            if len(valid) > 0:
                                result['parameters'][param_name] = {
                                    'mean': float(np.mean(valid)),
                                    'min': float(np.min(valid)),
                                    'max': float(np.max(valid)),
                                    'std': float(np.std(valid)),
                                    'count': int(len(valid)),
                                }
                                param_added = True
                            else:
                                logger.info(f"[NASA] No valid pixels in {best['filename']}, trying next")
                        if param_added:
                            break
                    except Exception as e:
                        logger.warning(f"[NASA] Failed to process {param} (attempt {attempts}): {e}")
                        continue
                    finally:
                        if not param_added:
                            try:
                                file_path.unlink()
                                downloaded.remove(file_path)
                            except Exception:
                                pass

                if not param_added:
                    result['parameters'][param] = {
                        'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0, 'count': 0
                    }

            # Cleanup
            for fp in downloaded:
                try:
                    fp.unlink()
                except Exception:
                    pass

            if not result['parameters']:
                logger.warning("[NASA] No parameters extracted, using synthetic")
                return self._generate_synthetic_indices(date, parameters)

            return result

        except Exception as e:
            logger.error(f"[NASA] Failed to get indices: {e}")
            return self._generate_synthetic_indices(date, parameters)

    def _generate_synthetic_indices(self, date: str, parameters: List[str]) -> Dict:
        """Generate synthetic indices based on seasonal patterns."""
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
        except Exception:
            dt = datetime.now()

        month = dt.month
        season_factor = 1.3 if 6 <= month <= 9 else (0.8 if 3 <= month <= 5 else 1.0)

        import random
        random.seed(abs(hash(date)))

        result = {
            'date': date,
            'source': 'nasa_synthetic',
            'bbox': [72.0, 8.0, 93.5, 30.5],
            'parameters': {}
        }
        ranges = {
            'chlorophyll': (0.1, 2.0),
            'turbidity': (0.01, 0.5),
            'cdom': (0.001, 0.1)
        }
        for param in parameters:
            if param in ranges:
                lo, hi = ranges[param]
                mean_val = (lo + hi) / 2 * season_factor
                result['parameters'][param] = {
                    'mean': round(mean_val + (random.random() - 0.5) * 0.2, 4),
                    'min': round(lo, 4),
                    'max': round(hi, 4),
                    'std': round((hi - lo) / 4, 4),
                    'count': random.randint(1000, 5000)
                }
        return result
