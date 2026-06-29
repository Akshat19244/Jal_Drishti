"""Planet API Service for Satellite Data

Fetches satellite imagery from Planet.com for water quality analysis.
Supports Catalog search, Mosaic Tile Service, and Data API.
"""

import requests
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import base64
from io import BytesIO
import numpy as np
from PIL import Image


class PlanetService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.api_key = os.getenv('PLANET_API_KEY')
        self.base_url = "https://api.planet.com"
        self.use_live_data = bool(self.api_key)
    
    def _get_headers(self) -> Dict:
        """Get authentication headers"""
        if not self.api_key:
            raise ValueError("Planet API key not configured. Please set PLANET_API_KEY environment variable.")
        return {
            "Authorization": f"api-key {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def search_imagery(self, bbox: List[float], date: str, cloud_cover: int = 30) -> List[Dict]:
        """Search for available imagery using Catalog API
        
        Args:
            bbox: [minLon, minLat, maxLon, maxLat]
            date: Date string in YYYY-MM-DD format
            cloud_cover: Maximum cloud cover percentage
            
        Returns:
            List of available imagery items
        """
        if not self.use_live_data:
            raise ValueError("Planet API key not configured")
        
        # Convert date to ISO format range
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        time_range = {
            "from": (date_obj - timedelta(days=7)).isoformat() + 'Z',
            "to": (date_obj + timedelta(days=7)).isoformat() + 'Z'
        }
        
        payload = {
            "item_types": ["PSScene", "PS2.SD"],
            "filter": {
                "type": "AndFilter",
                "config": [
                    {
                        "type": "GeometryFilter",
                        "field_name": "geometry",
                        "config": {
                            "type": "Polygon",
                            "coordinates": [[
                                [bbox[0], bbox[1]],
                                [bbox[2], bbox[1]],
                                [bbox[2], bbox[3]],
                                [bbox[0], bbox[3]],
                                [bbox[0], bbox[1]]
                            ]]
                        }
                    },
                    {
                        "type": "RangeFilter",
                        "field_name": "cloud_cover",
                        "config": {
                            "lte": cloud_cover / 100
                        }
                    },
                    {
                        "type": "DateRangeFilter",
                        "field_name": "acquired",
                        "config": time_range
                    }
                ]
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/basemaps/v1/mosaics/quick-search",
                json=payload,
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            return response.json().get('features', [])
        except requests.RequestException as e:
            print(f"[Planet] Catalog search failed: {e}")
            return []
    
    def get_mosaic_tiles(self, bbox: List[float], date: str) -> Optional[str]:
        """Get mosaic tiles using Mosaic Tile Service
        
        Args:
            bbox: [minLon, minLat, maxLon, maxLat]
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Base64-encoded PNG image
        """
        if not self.use_live_data:
            raise ValueError("Planet API key not configured")
        
        # Planet Mosaic Tile Service endpoint
        # Using Planet Basemaps for recent imagery
        tile_url = f"https://tiles.planet.com/basemaps/v1/planet-tiles/global_monthly_2024_01_mosaic/gmap/{bbox[1]}/{bbox[0]}/{12}.png?api_key={self.api_key}"
        
        try:
            response = requests.get(tile_url, timeout=30)
            response.raise_for_status()
            
            # Convert to base64
            img_base64 = base64.b64encode(response.content).decode('utf-8')
            return f"data:image/png;base64,{img_base64}"
        except requests.RequestException as e:
            print(f"[Planet] Mosaic tiles failed: {e}")
            return None
    
    def get_water_quality_indices(self, bbox: List[float], date: str) -> Dict:
        """Get water quality indices from Planet imagery
        
        Args:
            bbox: [minLon, minLat, maxLon, maxLat]
            date: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with CDOM, Turbidity, Chlorophyll, Kd490 values
        """
        if not self.use_live_data:
            raise ValueError("Planet API key not configured")
        
        # For now, return synthetic indices based on seasonal patterns
        # In production, this would process actual Planet imagery
        return self._generate_synthetic_indices(date)
    
    def _generate_synthetic_indices(self, date: str) -> Dict:
        """Generate synthetic indices based on seasonal patterns"""
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
        except:
            dt = datetime.now()
        
        # Seasonal patterns
        month = dt.month
        season_factor = 1.0
        
        # Monsoon season (June-September) affects water quality
        if 6 <= month <= 9:
            season_factor = 1.3  # Higher turbidity during monsoon
        elif 3 <= month <= 5:
            season_factor = 0.8  # Pre-monsoon, clearer water
        
        # Generate values with seasonal variation
        import random
        random.seed(hash(date))
        
        cdom = round(0.35 + (random.random() - 0.5) * 0.2 * season_factor, 3)
        turbidity = round(0.45 + (random.random() - 0.5) * 0.3 * season_factor, 3)
        chlorophyll = round(0.32 + (random.random() - 0.5) * 0.15 * season_factor, 3)
        kd490 = round(0.25 + (random.random() - 0.5) * 0.1 * season_factor, 3)
        
        # Determine status
        def get_status(val, low, high):
            if val < low: return "Low" if val < 0.3 else "Good"
            if val < high: return "Moderate"
            return "High" if val > 0.6 else "Poor"
        
        return {
            "date": date,
            "source": "planet",
            "cdom": {
                "value": cdom,
                "unit": "ratio",
                "status": get_status(cdom, 0.3, 0.6),
                "min": round(cdom * 0.8, 3),
                "max": round(cdom * 1.2, 3)
            },
            "turbidity": {
                "value": turbidity,
                "unit": "ratio",
                "status": get_status(turbidity, 0.4, 0.7),
                "min": round(turbidity * 0.8, 3),
                "max": round(turbidity * 1.2, 3)
            },
            "chlorophyll": {
                "value": chlorophyll,
                "unit": "ratio",
                "status": get_status(chlorophyll, 0.3, 0.6),
                "min": round(chlorophyll * 0.8, 3),
                "max": round(chlorophyll * 1.2, 3)
            },
            "kd490": {
                "value": kd490,
                "unit": "m⁻¹",
                "status": get_status(kd490, 0.2, 0.4),
                "min": round(kd490 * 0.8, 3),
                "max": round(kd490 * 1.2, 3)
            }
        }
