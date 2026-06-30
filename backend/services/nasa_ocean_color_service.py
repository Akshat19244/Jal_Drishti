"""NASA OceanColor Web Service for Satellite Water Quality Data

Fetches satellite data from NASA OB.DAAC API for:
- Chlorophyll-a (chlor_a band)
- Turbidity proxy (Kd_490 band)
- CDOM (adg_443_giop absorption band)

Uses MODIS-Aqua sensor data processed to Level-3 mapped products.
"""

import requests
import os
import xarray as xr
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

# Configure logging
logger = logging.getLogger(__name__)


class NASAOceanColorService:
    """Service for fetching and processing NASA OceanColor Web data"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.api_key = os.getenv('NASA_APPKEY')
        self.base_url = "https://oceandata.sci.gsfc.nasa.gov"
        self.use_live_data = bool(self.api_key)
        
        # Supported parameters and their band names
        self.parameter_bands = {
            'chlorophyll': 'chlor_a',
            'turbidity': 'Kd_490',
            'cdom': 'adg_443_giop'
        }
        
        # Sensor configuration
        self.sensor = 'aqua'  # MODIS-Aqua
        self.dtype = 'L3m'    # Level-3 mapped product
        
        if not self.api_key:
            logger.warning("[NASA] NASA_APPKEY not configured. Service will use synthetic data.")
    
    def _validate_credentials(self) -> None:
        """Validate that API credentials are configured"""
        if not self.api_key:
            raise ValueError(
                "NASA API key not configured. Please set NASA_APPKEY environment variable. "
                "Get your key from: https://urs.earthdata.nasa.gov/"
            )
    
    def _build_search_url(self, start_date: str, end_date: str, bbox: List[float], 
                          parameters: List[str]) -> str:
        """Build the NASA file search URL
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            bbox: Bounding box [minLon, minLat, maxLon, maxLat]
            parameters: List of parameter names (e.g., ['chlorophyll', 'turbidity'])
            
        Returns:
            Complete search URL
        """
        # Map parameter names to NASA product names
        product_map = {
            'chlorophyll': 'MODISA_L3m_CHL_chlor_a_9km',
            'turbidity': 'MODISA_L3m_KD490_Kd_490_9km',
            'cdom': 'MODISA_L3m_IOP_adg_443_giop_9km'
        }
        
        # Build product list
        products = [product_map.get(p, '') for p in parameters if p in product_map]
        if not products:
            raise ValueError(f"No valid parameters. Supported: {list(product_map.keys())}")
        
        # NASA OceanColor Web API search endpoint
        # Correct URL format for NASA OB.DAAC
        search_url = (
            f"{self.base_url}/ob/search/"
            f"?sensor={self.sensor}"
            f"&dtype={self.dtype}"
            f"&products={','.join(products)}"
            f"&dateRange={start_date},{end_date}"
            f"&bbox={','.join(map(str, bbox))}"
            f"&outputFormat=json"
        )
        
        return search_url
    
    def search_files(self, start_date: str, end_date: str, bbox: List[float], 
                    parameters: List[str]) -> List[Dict]:
        """Search for available NASA data files
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            bbox: Bounding box [minLon, minLat, maxLon, maxLat]
            parameters: List of parameter names
            
        Returns:
            List of file metadata dictionaries
            
        Raises:
            ValueError: If credentials are missing or parameters are invalid
            requests.RequestException: If API request fails
        """
        self._validate_credentials()
        
        search_url = self._build_search_url(start_date, end_date, bbox, parameters)
        logger.info(f"[NASA] Searching files: {search_url}")
        
        try:
            response = requests.get(search_url, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            files = data.get('files', [])
            
            if not files:
                logger.warning(f"[NASA] No files found for date range {start_date} to {end_date}")
            
            logger.info(f"[NASA] Found {len(files)} files")
            return files
            
        except requests.RequestException as e:
            logger.error(f"[NASA] Search request failed: {e}")
            raise
        except ValueError as e:
            logger.error(f"[NASA] Invalid JSON response: {e}")
            raise
    
    def download_file(self, filename: str, output_path: str, chunk_size: int = 8192) -> str:
        """Download a NetCDF file from NASA OceanColor Web
        
        Args:
            filename: Name of the file to download
            output_path: Local path to save the file
            chunk_size: Download chunk size in bytes
            
        Returns:
            Path to the downloaded file
            
        Raises:
            ValueError: If credentials are missing
            requests.RequestException: If download fails
        """
        self._validate_credentials()
        
        download_url = f"{self.base_url}/ob/getfile/{filename}?appkey={self.api_key}"
        logger.info(f"[NASA] Downloading: {filename}")
        
        try:
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Stream download to prevent memory issues
            with requests.get(download_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
            
            logger.info(f"[NASA] Downloaded to: {output_path}")
            return output_path
            
        except requests.RequestException as e:
            logger.error(f"[NASA] Download failed for {filename}: {e}")
            raise
        except IOError as e:
            logger.error(f"[NASA] File write failed: {e}")
            raise
    
    def parse_netcdf(self, file_path: str, bbox: Optional[List[float]] = None) -> Dict[str, np.ndarray]:
        """Parse NetCDF file and extract parameter arrays
        
        Args:
            file_path: Path to the NetCDF file
            bbox: Optional bounding box [minLon, minLat, maxLon, maxLat] for spatial subsetting
            
        Returns:
            Dictionary mapping parameter names to numpy arrays
            
        Raises:
            ValueError: If file is corrupted or missing required variables
        """
        logger.info(f"[NASA] Parsing NetCDF: {file_path}")
        
        try:
            # Open NetCDF file with xarray
            ds = xr.open_dataset(file_path)
            
            # Extract available parameters
            result = {}
            
            # Map NASA variable names to our parameter names
            var_mapping = {
                'chlor_a': 'chlorophyll',
                'Kd_490': 'turbidity',
                'adg_443_giop': 'cdom'
            }
            
            for nasa_var, param_name in var_mapping.items():
                if nasa_var in ds:
                    data_array = ds[nasa_var]
                    
                    # Apply spatial subsetting if bbox provided
                    if bbox and 'lat' in ds and 'lon' in ds:
                        lat_min, lat_max = bbox[1], bbox[3]
                        lon_min, lon_max = bbox[0], bbox[2]
                        
                        # Subset to bounding box
                        data_array = data_array.sel(
                            lat=slice(lat_min, lat_max),
                            lon=slice(lon_min, lon_max)
                        )
                    
                    # Convert to numpy array, handling NaN values
                    array = data_array.values
                    result[param_name] = np.nan_to_num(array, nan=0.0)
                    
                    logger.info(f"[NASA] Extracted {param_name}: shape={array.shape}")
            
            ds.close()
            
            if not result:
                raise ValueError("No valid parameters found in NetCDF file")
            
            return result
            
        except Exception as e:
            logger.error(f"[NASA] NetCDF parsing failed: {e}")
            raise ValueError(f"Failed to parse NetCDF file: {e}")
    
    def get_water_quality_indices(self, bbox: List[float], date: str, 
                                  parameters: Optional[List[str]] = None) -> Dict:
        """Get water quality indices for a specific date and location
        
        Args:
            bbox: Bounding box [minLon, minLat, maxLon, maxLat]
            date: Date string in YYYY-MM-DD format
            parameters: List of parameters to fetch (default: all)
            
        Returns:
            Dictionary with water quality indices and metadata
        """
        if parameters is None:
            parameters = ['chlorophyll', 'turbidity', 'cdom']
        
        if not self.use_live_data:
            logger.warning("[NASA] Using synthetic data (no API key)")
            return self._generate_synthetic_indices(date, parameters)
        
        try:
            # Search for files (use 7-day window around target date)
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            start_date = (date_obj - timedelta(days=3)).strftime('%Y-%m-%d')
            end_date = (date_obj + timedelta(days=3)).strftime('%Y-%m-%d')
            
            files = self.search_files(start_date, end_date, bbox, parameters)
            
            if not files:
                logger.warning(f"[NASA] No files found, using synthetic data")
                return self._generate_synthetic_indices(date, parameters)
            
            # Download and parse the first available file
            file_info = files[0]
            filename = file_info.get('filename')
            
            if not filename:
                raise ValueError("No filename in file metadata")
            
            # Create temporary download path
            temp_dir = Path("temp/nasa")
            temp_dir.mkdir(parents=True, exist_ok=True)
            file_path = temp_dir / filename
            
            # Download file
            self.download_file(filename, str(file_path))
            
            # Parse NetCDF
            data_arrays = self.parse_netcdf(str(file_path), bbox)
            
            # Calculate statistics for each parameter
            result = {
                'date': date,
                'source': 'nasa_ocean_color',
                'bbox': bbox,
                'parameters': {}
            }
            
            for param_name, array in data_arrays.items():
                valid_data = array[array > 0]  # Exclude zeros/invalid
                
                if len(valid_data) > 0:
                    result['parameters'][param_name] = {
                        'mean': float(np.mean(valid_data)),
                        'min': float(np.min(valid_data)),
                        'max': float(np.max(valid_data)),
                        'std': float(np.std(valid_data)),
                        'count': int(len(valid_data))
                    }
                else:
                    result['parameters'][param_name] = {
                        'mean': 0.0,
                        'min': 0.0,
                        'max': 0.0,
                        'std': 0.0,
                        'count': 0
                    }
            
            # Clean up downloaded file
            try:
                file_path.unlink()
            except:
                pass
            
            return result
            
        except Exception as e:
            logger.error(f"[NASA] Failed to get indices: {e}")
            return self._generate_synthetic_indices(date, parameters)
    
    def _generate_synthetic_indices(self, date: str, parameters: List[str]) -> Dict:
        """Generate synthetic water quality indices based on seasonal patterns"""
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
        except:
            dt = datetime.now()
        
        # Seasonal patterns
        month = dt.month
        season_factor = 1.0
        
        # Monsoon season affects water quality
        if 6 <= month <= 9:
            season_factor = 1.3
        elif 3 <= month <= 5:
            season_factor = 0.8
        
        # Generate values with seasonal variation
        import random
        random.seed(hash(date))
        
        result = {
            'date': date,
            'source': 'nasa_synthetic',
            'bbox': [72.0, 8.0, 93.5, 30.5],
            'parameters': {}
        }
        
        param_ranges = {
            'chlorophyll': (0.1, 2.0),
            'turbidity': (0.01, 0.5),
            'cdom': (0.001, 0.1)
        }
        
        for param in parameters:
            if param in param_ranges:
                min_val, max_val = param_ranges[param]
                mean_val = (min_val + max_val) / 2 * season_factor
                result['parameters'][param] = {
                    'mean': round(mean_val + (random.random() - 0.5) * 0.2, 4),
                    'min': round(min_val, 4),
                    'max': round(max_val, 4),
                    'std': round((max_val - min_val) / 4, 4),
                    'count': random.randint(1000, 5000)
                }
        
        return result
