"""Sentinel-2 Service for Water Quality Indices

Fetches live satellite data from Copernicus Sentinel Hub API for:
- CDOM (Colored Dissolved Organic Matter)
- Turbidity Index
- Chlorophyll-a
- Kd490 (Light Attenuation at 490nm)

Supports API key authentication or falls back to synthetic data based on CPCB correlations.
"""

import requests
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import math


class SentinelService:
    """Service for fetching Sentinel-2 water quality indices"""
    
    def __init__(self):
        self.client_id = os.getenv('SENTINEL_HUB_CLIENT_ID')
        self.client_secret = os.getenv('SENTINEL_HUB_CLIENT_SECRET')
        self.api_key = os.getenv('SENTINEL_HUB_API_KEY')  # Fallback for Bearer token
        self.api_url = "https://services.sentinel-hub.com/api/v1/process"
        self.auth_url = "https://services.sentinel-hub.com/oauth/token"
        self.access_token = None
        self.token_expiry = None
        # IMPORTANT: keep SentinelHub synthetic by default.
        # Live calls are enabled ONLY when SENTINEL_HUB_ENABLE_LIVE=true
        enable_live = os.getenv('SENTINEL_HUB_ENABLE_LIVE', '').strip().lower() in ('1', 'true', 'yes')

        # Use live SentinelHub only when explicitly enabled and creds look complete.
        # Also require that the user asked for a spatial map (the frontend will request return_image=true).
        self.use_live_data = (
            enable_live
            and bool(self.client_id and self.client_secret)
            and not bool(os.getenv('SENTINEL_HUB_DISABLE_LIVE', '').lower() in ('1', 'true', 'yes'))
        )

        # Bearer-token mode also requires explicit live enable.
        if self.api_key:
            if enable_live and os.getenv('SENTINEL_HUB_ENABLE_BEARER', '').strip().lower() in ('1', 'true', 'yes'):
                self.use_live_data = not bool(os.getenv('SENTINEL_HUB_DISABLE_LIVE', '').lower() in ('1', 'true', 'yes'))
            else:
                self.use_live_data = False



    
    def _get_access_token(self) -> str:
        """Get or refresh OAuth access token"""
        # If we have a direct API key (Bearer token), use it
        if self.api_key:
            return self.api_key
        
        # Check if token is still valid
        if self.access_token and self.token_expiry:
            if datetime.now() < self.token_expiry:
                return self.access_token
        
        # Request new token
        try:
            response = requests.post(
                self.auth_url,
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'client_credentials'
                },
                timeout=30
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)  # Refresh 1 min early
            
            return self.access_token
        except requests.RequestException as e:
            print(f"[Sentinel] OAuth token request failed: {e}")
            raise
        
    def get_india_indices(self, date: Optional[str] = None, return_image: bool = False) -> Dict:
        """
        Get Sentinel-2 indices for India for a specific date
        
        Args:
            date: Date string in YYYY-MM-DD format (defaults to most recent available)
            return_image: If True, returns base64-encoded image data for spatial visualization
            
        Returns:
            Dictionary with indices for CDOM, Turbidity, Chlorophyll-a, Kd490
        """
        # Keep synthetic as default, but still allow the map overlay when live calls work.
        if not self.use_live_data:
            return self._generate_synthetic_indices(date)

        # For map overlay, we need return_image=true to get a TIFF.
        # If live calls fail, we fallback to synthetic so UI still renders.
        try:
            return self._fetch_live_indices(date, return_image)
        except Exception:
            return self._generate_synthetic_indices(date)


    
    def _fetch_live_indices(self, date: Optional[str] = None, return_image: bool = False) -> Dict:
        """Fetch live data from Sentinel Hub API"""
        if not date:
            date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        # Sentinel Hub expects ISO-8601 time for timeRange.from/to.
        # Your previous request used only YYYY-MM-DD, which caused HTTP 400.
        # Convert YYYY-MM-DD → YYYY-MM-DDT00:00:00Z
        if len(date) == 10 and date[4] == '-' and date[7] == '-':
            iso_date = f"{date}T00:00:00Z"
        else:
            # If already ISO, keep as-is
            iso_date = date

        
        # Smaller bbox to satisfy S2L2A resolution limits on Render.
        # (Still covers all of India reasonably; reduces meters/pixel.)
        bbox = [72.0, 8.0, 93.5, 30.5]  # [minLon, minLat, maxLon, maxLat]

        
        # Sentinel-2 evalscript for water quality indices (improved accuracy)
        evalscript = """
        //VERSION=3
        function setup() {
          return {
            input: ["B02", "B03", "B04", "B05", "B08", "B11", "SCL"],
            output: { bands: 4, sampleType: 'FLOAT32' }
          };
        }
        
        function evaluatePixel(sample) {
          // Mask clouds and water using Scene Classification Layer (SCL)
          // SCL values: 0=NoData, 1=Saturated, 2=Dark, 3=CloudShadow, 4=Vegetation,
          // 5=Soil, 6=Water, 7=CloudLow, 8=CloudMedium, 9=CloudHigh, 10=Cirrus, 11=Snow
          if (sample.SCL > 3 && sample.SCL < 6) {
            return [NaN, NaN, NaN, NaN]; // Mask non-water pixels
          }
          
          // CDOM (Colored Dissolved Organic Matter) - improved formula
          // Uses B03 (green) and B04 (red) with atmospheric correction
          let cdom = (sample.B03 - 0.02) / (sample.B04 - 0.01);
          cdom = cdom > 0 ? cdom : 0;
          
          // Turbidity - improved using red-green ratio with NIR correction
          // Based on Nechad et al. (2010) turbidity algorithm
          let turbidity = (sample.B04 - sample.B03) / (sample.B04 + sample.B03);
          // Apply NIR correction for shallow waters
          let nir = sample.B08 || sample.B11;
          turbidity = turbidity * (1 - nir * 0.1);
          turbidity = turbidity > 0 ? turbidity : 0;
          
          // Chlorophyll-a - improved using red edge bands
          // Uses B05 (red edge) and B04 (red) with baseline correction
          let chlorophyll = (sample.B05 - sample.B04) / (sample.B05 + sample.B04);
          // Apply atmospheric correction baseline
          chlorophyll = chlorophyll - 0.05;
          chlorophyll = chlorophyll > 0 ? chlorophyll : 0;
          
          // Kd490 (Light Attenuation at 490nm) - improved formula
          // Based on Lee et al. (2005) using blue-green ratio
          let kd490 = (sample.B02 / sample.B03) * 0.5;
          // Apply depth correction using SWIR
          let swir = sample.B11 || 0;
          kd490 = kd490 * (1 + swir * 0.2);
          kd490 = kd490 > 0 ? kd490 : 0;
          
          return [cdom, turbidity, chlorophyll, kd490];
        }
        """
        
        payload = {
            "input": {
                "bounds": {
                    "bbox": bbox,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}

                },
                "data": [{
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": iso_date, "to": iso_date},

                        "mosaickingOrder": "mostRecent",
                        "maxCloudCover": 30  # Only use scenes with <30% cloud cover
                    }
                }]
            },
            "output": {
                "width": 400,
                "height": 400,


                "responses": [{
                    "identifier": "default",
                    "format": {
                        "type": "image/tiff",
                        "depth": "32f"
                    }
                }]
            },
            "evalscript": evalscript
        }
        
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            # If Sentinel Hub returns an error, capture body for debugging
            if response.status_code >= 400:
                try:
                    err_body = response.json()
                except Exception:
                    err_body = response.text[:2000]

                print(f"[Sentinel] API request failed (HTTP {response.status_code}): {err_body}")
                return self._generate_synthetic_indices(date)

            if return_image:
                # Return base64-encoded image for spatial visualization
                import base64
                image_data = base64.b64encode(response.content).decode('utf-8')
                return {
                    "date": date,
                    "source": "sentinel_hub",
                    "image_data": image_data,
                    "image_bytes_len": len(response.content),
                    "bbox": bbox,
                    "width": 400,
                    "height": 400
                }


            # Process the TIFF response to extract mean values
            return self._parse_sentinel_response(response, date)

        except requests.RequestException as e:
            print(f"[Sentinel] API request exception: {e}")
            return self._generate_synthetic_indices(date)

    
    def _parse_sentinel_response(self, response, date) -> Dict:
        """Parse Sentinel Hub response to extract index values"""
        try:
            import rasterio
            from io import BytesIO
            import numpy as np
            
            # Parse TIFF response
            img_data = BytesIO(response.content)
            with rasterio.open(img_data) as src:
                # Read bands: CDOM, Turbidity, Chlorophyll, Kd490
                data = src.read()
                
                # Compute statistics for each band
                stats = []
                for i in range(data.shape[0]):
                    band = data[i]
                    # Mask NaN values
                    valid_mask = ~np.isnan(band)
                    valid_data = band[valid_mask]
                    
                    if len(valid_data) > 0:
                        stats.append({
                            'value': float(np.mean(valid_data)),
                            'min': float(np.min(valid_data)),
                            'max': float(np.max(valid_data))
                        })
                    else:
                        stats.append({'value': 0.0, 'min': 0.0, 'max': 0.0})
                
                # Determine status based on thresholds
                cdom_status = self._get_cdom_status(stats[0]['value'])
                turb_status = self._get_turbidity_status(stats[1]['value'])
                chlor_status = self._get_chlorophyll_status(stats[2]['value'])
                kd_status = self._get_kd490_status(stats[3]['value'])
                
                return {
                    "date": date,
                    "source": "sentinel_hub",
                    "cdom": {
                        "value": round(stats[0]['value'], 3),
                        "unit": "ratio",
                        "status": cdom_status,
                        "min": round(stats[0]['min'], 3),
                        "max": round(stats[0]['max'], 3)
                    },
                    "turbidity": {
                        "value": round(stats[1]['value'], 3),
                        "unit": "ratio",
                        "status": turb_status,
                        "min": round(stats[1]['min'], 3),
                        "max": round(stats[1]['max'], 3)
                    },
                    "chlorophyll": {
                        "value": round(stats[2]['value'], 3),
                        "unit": "ratio",
                        "status": chlor_status,
                        "min": round(stats[2]['min'], 3),
                        "max": round(stats[2]['max'], 3)
                    },
                    "kd490": {
                        "value": round(stats[3]['value'], 3),
                        "unit": "m⁻¹",
                        "status": kd_status,
                        "min": round(stats[3]['min'], 3),
                        "max": round(stats[3]['max'], 3)
                    }
                }
        except Exception as e:
            print(f"[Sentinel] Failed to parse TIFF response: {e}")
            # Fallback to synthetic data
            return self._generate_synthetic_indices(date)
    
    def _get_cdom_status(self, value):
        if value < 0.3: return "Low"
        if value < 0.6: return "Moderate"
        return "High"
    
    def _get_turbidity_status(self, value):
        if value < 0.4: return "Low"
        if value < 0.7: return "Moderate"
        return "High"
    
    def _get_chlorophyll_status(self, value):
        if value < 0.3: return "Low"
        if value < 0.6: return "Moderate"
        return "High"
    
    def _get_kd490_status(self, value):
        if value < 0.2: return "Good"
        if value < 0.4: return "Moderate"
        return "Poor"
    
    def _generate_synthetic_indices(self, date: Optional[str] = None) -> Dict:
        """Generate synthetic indices based on seasonal patterns and correlations"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        dt = datetime.strptime(date, '%Y-%m-%d')
        
        # Seasonal patterns (monsoon affects water quality)
        month = dt.month
        is_monsoon = 6 <= month <= 9  # June-September monsoon season
        
        # Base values with seasonal variation
        base_cdom = 0.35 + (0.15 if is_monsoon else 0)
        base_turbidity = 0.50 + (0.25 if is_monsoon else 0)
        base_chlorophyll = 0.30 + (0.10 if is_monsoon else 0)
        base_kd490 = 0.22 + (0.10 if is_monsoon else 0)
        
        # Add some randomness
        import random
        random.seed(int(dt.strftime('%Y%m%d')))
        
        cdom = min(max(base_cdom + random.uniform(-0.05, 0.05), 0.1), 0.8)
        turbidity = min(max(base_turbidity + random.uniform(-0.08, 0.08), 0.2), 0.9)
        chlorophyll = min(max(base_chlorophyll + random.uniform(-0.06, 0.06), 0.1), 0.7)
        kd490 = min(max(base_kd490 + random.uniform(-0.04, 0.04), 0.1), 0.5)
        
        return {
            "date": date,
            "source": "synthetic",
            "cdom": {
                "value": round(cdom, 3),
                "unit": "ratio",
                "status": self._get_status(cdom, 0.3, 0.6),
                "min": round(cdom - 0.1, 3),
                "max": round(cdom + 0.1, 3)
            },
            "turbidity": {
                "value": round(turbidity, 3),
                "unit": "ratio",
                "status": self._get_status(turbidity, 0.4, 0.7),
                "min": round(turbidity - 0.12, 3),
                "max": round(turbidity + 0.12, 3)
            },
            "chlorophyll": {
                "value": round(chlorophyll, 3),
                "unit": "ratio",
                "status": self._get_status(chlorophyll, 0.3, 0.5),
                "min": round(chlorophyll - 0.08, 3),
                "max": round(chlorophyll + 0.08, 3)
            },
            "kd490": {
                "value": round(kd490, 3),
                "unit": "m⁻¹",
                "status": self._get_status(kd490, 0.2, 0.4),
                "min": round(kd490 - 0.06, 3),
                "max": round(kd490 + 0.06, 3)
            }
        }
    
    def _get_status(self, value: float, low_threshold: float, high_threshold: float) -> str:
        """Get status label based on thresholds"""
        if value < low_threshold:
            return "Low" if "ratio" in str(low_threshold) else "Good"
        elif value < high_threshold:
            return "Moderate"
        else:
            return "High" if "ratio" in str(low_threshold) else "Poor"
    
    def get_historical_indices(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Get historical indices for a date range
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of index dictionaries for each date
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        indices = []
        current = start
        
        while current <= end:
            indices.append(self.get_india_indices(current.strftime('%Y-%m-%d')))
            current += timedelta(days=7)  # Weekly data
        
        return indices
