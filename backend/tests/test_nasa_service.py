"""Unit Tests for NASA OceanColor Web Service

Tests for NASAOceanColorService including:
- API authentication validation
- URL building
- File search
- Download streaming
- NetCDF parsing
- Error handling
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import numpy as np
import xarray as xr

from services.nasa_ocean_color_service import NASAOceanColorService


class TestNASAOceanColorService:
    """Test suite for NASA OceanColor Web Service"""
    
    @pytest.fixture
    def service(self):
        """Create service instance for testing"""
        # Temporarily set API key for tests
        original_key = os.getenv('NASA_APPKEY')
        os.environ['NASA_APPKEY'] = 'test_api_key_12345'
        service = NASAOceanColorService()
        if original_key:
            os.environ['NASA_APPKEY'] = original_key
        else:
            os.environ.pop('NASA_APPKEY', None)
        return service
    
    @pytest.fixture
    def mock_response(self):
        """Create mock response object"""
        mock = Mock()
        mock.status_code = 200
        mock.json.return_value = {'files': [{'filename': 'test.nc'}]}
        mock.raise_for_status = Mock()
        return mock
    
    def test_singleton_pattern(self, service):
        """Test that service follows singleton pattern"""
        service2 = NASAOceanColorService()
        assert service is service2
    
    def test_validate_credentials_success(self, service):
        """Test credential validation with valid key"""
        service.api_key = 'valid_key'
        # Should not raise exception
        service._validate_credentials()
    
    def test_validate_credentials_failure(self, service):
        """Test credential validation with missing key"""
        service.api_key = None
        with pytest.raises(ValueError, match="NASA API key not configured"):
            service._validate_credentials()
    
    def test_build_search_url(self, service):
        """Test search URL building"""
        start_date = '2024-01-01'
        end_date = '2024-01-07'
        bbox = [72.0, 8.0, 93.5, 30.5]
        parameters = ['chlorophyll', 'turbidity']
        
        url = service._build_search_url(start_date, end_date, bbox, parameters)
        
        assert 'sensor=aqua' in url
        assert 'dtype=L3m' in url
        assert 'dateRange=2024-01-01,2024-01-07' in url
        assert 'bbox=72.0,8.0,93.5,30.5' in url
        assert 'outputFormat=json' in url
    
    def test_build_search_url_invalid_parameter(self, service):
        """Test search URL building with invalid parameter"""
        with pytest.raises(ValueError, match="No valid parameters"):
            service._build_search_url(
                '2024-01-01', '2024-01-07',
                [72.0, 8.0, 93.5, 30.5],
                ['invalid_param']
            )
    
    @patch('requests.get')
    def test_search_files_success(self, mock_get, service, mock_response):
        """Test successful file search"""
        mock_get.return_value = mock_response
        
        files = service.search_files(
            '2024-01-01', '2024-01-07',
            [72.0, 8.0, 93.5, 30.5],
            ['chlorophyll']
        )
        
        assert len(files) == 1
        assert files[0]['filename'] == 'test.nc'
        mock_get.assert_called_once()
    
    @patch('requests.get')
    def test_search_files_no_results(self, mock_get, service):
        """Test file search with no results"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'files': []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        files = service.search_files(
            '2024-01-01', '2024-01-07',
            [72.0, 8.0, 93.5, 30.5],
            ['chlorophyll']
        )
        
        assert len(files) == 0
    
    @patch('requests.get')
    def test_search_files_api_error(self, mock_get, service):
        """Test file search with API error"""
        mock_get.side_effect = Exception("API Error")
        
        with pytest.raises(Exception, match="API Error"):
            service.search_files(
                '2024-01-01', '2024-01-07',
                [72.0, 8.0, 93.5, 30.5],
                ['chlorophyll']
            )
    
    @patch('requests.get')
    @patch('builtins.open', create=True)
    def test_download_file_success(self, mock_open, mock_get, service):
        """Test successful file download with streaming"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.iter_content = Mock(return_value=[b'test data chunk'])
        mock_get.return_value = mock_response
        
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        output_path = service.download_file('test.nc', 'temp/test.nc')
        
        assert output_path == 'temp/test.nc'
        mock_get.assert_called_once()
        mock_file.write.assert_called()
    
    @patch('requests.get')
    def test_download_file_error(self, mock_get, service):
        """Test file download with error"""
        mock_get.side_effect = Exception("Download failed")
        
        with pytest.raises(Exception, match="Download failed"):
            service.download_file('test.nc', 'temp/test.nc')
    
    @patch('xarray.open_dataset')
    def test_parse_netcdf_success(self, mock_xr, service):
        """Test successful NetCDF parsing"""
        # Create mock dataset
        mock_ds = MagicMock()
        mock_ds.__contains__ = lambda self, key: key in ['chlor_a', 'lat', 'lon']
        
        # Mock data array
        mock_data = MagicMock()
        mock_data.values = np.array([[1.0, 2.0], [3.0, 4.0]])
        mock_ds.__getitem__ = Mock(return_value=mock_data)
        
        # Mock selection
        mock_data.sel = Mock(return_value=mock_data)
        
        mock_xr.return_value = mock_ds
        
        result = service.parse_netcdf('test.nc')
        
        assert 'chlorophyll' in result
        assert isinstance(result['chlorophyll'], np.ndarray)
        mock_xr.assert_called_once_with('test.nc')
    
    @patch('xarray.open_dataset')
    def test_parse_netcdf_with_bbox(self, mock_xr, service):
        """Test NetCDF parsing with bounding box subsetting"""
        mock_ds = MagicMock()
        mock_ds.__contains__ = lambda self, key: key in ['chlor_a', 'lat', 'lon']
        
        mock_data = MagicMock()
        mock_data.values = np.array([[1.0, 2.0], [3.0, 4.0]])
        mock_ds.__getitem__ = Mock(return_value=mock_data)
        mock_data.sel = Mock(return_value=mock_data)
        
        mock_xr.return_value = mock_ds
        
        bbox = [72.0, 8.0, 93.5, 30.5]
        result = service.parse_netcdf('test.nc', bbox)
        
        mock_data.sel.assert_called()
    
    @patch('xarray.open_dataset')
    def test_parse_netcdf_invalid_file(self, mock_xr, service):
        """Test NetCDF parsing with invalid file"""
        mock_xr.side_effect = Exception("Invalid NetCDF")
        
        with pytest.raises(ValueError, match="Failed to parse NetCDF"):
            service.parse_netcdf('invalid.nc')
    
    def test_generate_synthetic_indices(self, service):
        """Test synthetic data generation"""
        result = service._generate_synthetic_indices('2024-01-15', ['chlorophyll', 'turbidity'])
        
        assert 'date' in result
        assert 'source' in result
        assert 'parameters' in result
        assert 'chlorophyll' in result['parameters']
        assert 'turbidity' in result['parameters']
        assert result['source'] == 'nasa_synthetic'
    
    def test_get_water_quality_indices_without_api_key(self, service):
        """Test getting indices without API key (synthetic fallback)"""
        service.api_key = None
        service.use_live_data = False
        
        result = service.get_water_quality_indices(
            [72.0, 8.0, 93.5, 30.5],
            '2024-01-15',
            ['chlorophyll']
        )
        
        assert result['source'] == 'nasa_synthetic'
        assert 'parameters' in result
    
    @patch.object(NASAOceanColorService, 'search_files')
    @patch.object(NASAOceanColorService, 'download_file')
    @patch.object(NASAOceanColorService, 'parse_netcdf')
    def test_get_water_quality_indices_with_api_key(self, mock_parse, mock_download, 
                                                     mock_search, service):
        """Test getting indices with valid API key"""
        mock_search.return_value = [{'filename': 'test.nc'}]
        mock_download.return_value = 'temp/test.nc'
        mock_parse.return_value = {
            'chlorophyll': np.array([[1.0, 2.0], [3.0, 4.0]])
        }
        
        result = service.get_water_quality_indices(
            [72.0, 8.0, 93.5, 30.5],
            '2024-01-15',
            ['chlorophyll']
        )
        
        assert 'parameters' in result
        mock_search.assert_called_once()
        mock_download.assert_called_once()
        mock_parse.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
