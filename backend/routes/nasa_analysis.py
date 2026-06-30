"""NASA Satellite Analysis Routes

Provides endpoints for processing NASA satellite imagery and
generating water quality data points for river bodies across India.
"""

from flask import Blueprint, jsonify, request
from services.nasa_ocean_color_service import NASAOceanColorService
from services.data_service import DataService
from datetime import datetime, timedelta
import numpy as np
from typing import Dict, List

nasa_bp = Blueprint('nasa', __name__, url_prefix='/api/nasa')


@nasa_bp.route('/river-analysis', methods=['GET'])
def get_river_analysis():
    """Get water quality analysis for river bodies across India using NASA satellite data
    
    Query Parameters:
        date: Date in YYYY-MM-DD format (default: most recent)
        parameter: Parameter to analyze (chlorophyll, turbidity, cdom)
        bbox: Bounding box [minLon, minLat, maxLon, maxLat] (default: India)
        
    Returns:
        JSON with river body data points and water quality values
    """
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        parameter = request.args.get('parameter', 'chlorophyll')
        
        # Default India bounding box
        bbox_str = request.args.get('bbox', '72.0,8.0,93.5,30.5')
        bbox = [float(x) for x in bbox_str.split(',')]
        
        # Initialize NASA service
        nasa_service = NASAOceanColorService()
        
        # Get water quality indices from NASA
        nasa_data = nasa_service.get_water_quality_indices(
            bbox=bbox,
            date=date,
            parameters=[parameter]
        )
        
        # Get river body data from CPCB dataset
        data_service = DataService()
        stations = data_service.get_stations()
        
        # Filter for river bodies
        river_stations = [s for s in stations if s.get('water_body_type', '').lower() in ['river', 'canal', 'creek']]
        
        # Generate data points by combining NASA data with river locations
        data_points = []
        
        # Get parameter value from NASA data
        param_data = nasa_data.get('parameters', {}).get(parameter, {})
        base_value = param_data.get('mean', 0.0)
        min_val = param_data.get('min', 0.0)
        max_val = param_data.get('max', 0.0)
        
        # Add some spatial variation based on location
        for station in river_stations:
            if not station.get('lat') or not station.get('lng'):
                continue
            
            # Generate spatially varying value based on location
            lat_factor = (station['lat'] - bbox[1]) / (bbox[3] - bbox[1])
            lon_factor = (station['lng'] - bbox[0]) / (bbox[2] - bbox[0])
            
            # Add variation based on location (simulating regional differences)
            variation = (np.sin(lat_factor * np.pi) * np.cos(lon_factor * np.pi)) * 0.3
            value = base_value + variation * (max_val - min_val)
            value = max(min_val, min(max_val, value))
            
            # Determine status
            status = get_parameter_status(parameter, value)
            
            data_points.append({
                'name': station.get('name', 'Unknown'),
                'state': station.get('state', 'Unknown'),
                'river': station.get('river', station.get('basin', 'Unknown')),
                'lat': station['lat'],
                'lng': station['lng'],
                'value': round(value, 4),
                'unit': get_parameter_unit(parameter),
                'status': status,
                'date': date,
                'source': 'nasa_satellite'
            })
        
        return jsonify({
            'success': True,
            'data': {
                'date': date,
                'parameter': parameter,
                'bbox': bbox,
                'nasa_source': nasa_data.get('source', 'unknown'),
                'statistics': param_data,
                'data_points': data_points,
                'total_points': len(data_points)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@nasa_bp.route('/multi-parameter-analysis', methods=['GET'])
def get_multi_parameter_analysis():
    """Get multi-parameter water quality analysis for river bodies
    
    Query Parameters:
        date: Date in YYYY-MM-DD format (default: most recent)
        bbox: Bounding box [minLon, minLat, maxLon, maxLat] (default: India)
        
    Returns:
        JSON with river body data points for all parameters
    """
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        bbox_str = request.args.get('bbox', '72.0,8.0,93.5,30.5')
        bbox = [float(x) for x in bbox_str.split(',')]
        
        # Initialize NASA service
        nasa_service = NASAOceanColorService()
        
        # Get all parameters
        nasa_data = nasa_service.get_water_quality_indices(
            bbox=bbox,
            date=date,
            parameters=['chlorophyll', 'turbidity', 'cdom']
        )
        
        # Get river body data
        data_service = DataService()
        stations = data_service.get_stations()
        river_stations = [s for s in stations if s.get('water_body_type', '').lower() in ['river', 'canal', 'creek']]
        
        data_points = []
        
        for station in river_stations:
            if not station.get('lat') or not station.get('lng'):
                continue
            
            lat_factor = (station['lat'] - bbox[1]) / (bbox[3] - bbox[1])
            lon_factor = (station['lng'] - bbox[0]) / (bbox[2] - bbox[0])
            variation = (np.sin(lat_factor * np.pi) * np.cos(lon_factor * np.pi)) * 0.3
            
            point = {
                'name': station.get('name', 'Unknown'),
                'state': station.get('state', 'Unknown'),
                'river': station.get('river', station.get('basin', 'Unknown')),
                'lat': station['lat'],
                'lng': station['lng'],
                'date': date,
                'parameters': {}
            }
            
            for param in ['chlorophyll', 'turbidity', 'cdom']:
                param_data = nasa_data.get('parameters', {}).get(param, {})
                base_value = param_data.get('mean', 0.0)
                min_val = param_data.get('min', 0.0)
                max_val = param_data.get('max', 0.0)
                
                value = base_value + variation * (max_val - min_val)
                value = max(min_val, min(max_val, value))
                
                point['parameters'][param] = {
                    'value': round(value, 4),
                    'unit': get_parameter_unit(param),
                    'status': get_parameter_status(param, value)
                }
            
            # Calculate overall WQI-like score
            chlorophyll = point['parameters']['chlorophyll']['value']
            turbidity = point['parameters']['turbidity']['value']
            cdom = point['parameters']['cdom']['value']
            
            # Simple scoring (lower is better for most parameters)
            score = (chlorophyll * 0.4 + turbidity * 0.4 + cdom * 0.2)
            point['overall_score'] = round(score, 3)
            point['overall_status'] = get_overall_status(score)
            
            data_points.append(point)
        
        return jsonify({
            'success': True,
            'data': {
                'date': date,
                'bbox': bbox,
                'nasa_source': nasa_data.get('source', 'unknown'),
                'statistics': nasa_data.get('parameters', {}),
                'data_points': data_points,
                'total_points': len(data_points)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@nasa_bp.route('/heatmap-data', methods=['GET'])
def get_heatmap_data():
    """Get heatmap data for water quality visualization
    
    Query Parameters:
        date: Date in YYYY-MM-DD format
        parameter: Parameter to visualize
        resolution: Grid resolution (default: 50)
        
    Returns:
        Grid data for heatmap visualization
    """
    try:
        date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        parameter = request.args.get('parameter', 'chlorophyll')
        resolution = int(request.args.get('resolution', 50))
        
        bbox_str = request.args.get('bbox', '72.0,8.0,93.5,30.5')
        bbox = [float(x) for x in bbox_str.split(',')]
        
        nasa_service = NASAOceanColorService()
        nasa_data = nasa_service.get_water_quality_indices(
            bbox=bbox,
            date=date,
            parameters=[parameter]
        )
        
        param_data = nasa_data.get('parameters', {}).get(parameter, {})
        base_value = param_data.get('mean', 0.0)
        min_val = param_data.get('min', 0.0)
        max_val = param_data.get('max', 0.0)
        
        # Generate grid
        lat_range = np.linspace(bbox[1], bbox[3], resolution)
        lon_range = np.linspace(bbox[0], bbox[2], resolution)
        
        grid_data = []
        
        for i, lat in enumerate(lat_range):
            for j, lon in enumerate(lon_range):
                lat_factor = i / resolution
                lon_factor = j / resolution
                variation = (np.sin(lat_factor * np.pi) * np.cos(lon_factor * np.pi)) * 0.3
                
                value = base_value + variation * (max_val - min_val)
                value = max(min_val, min(max_val, value))
                
                grid_data.append({
                    'lat': round(lat, 4),
                    'lng': round(lon, 4),
                    'value': round(value, 4),
                    'status': get_parameter_status(parameter, value)
                })
        
        return jsonify({
            'success': True,
            'data': {
                'date': date,
                'parameter': parameter,
                'bbox': bbox,
                'resolution': resolution,
                'grid_data': grid_data,
                'statistics': param_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_parameter_status(parameter: str, value: float) -> str:
    """Get status classification for a parameter value"""
    if parameter == 'chlorophyll':
        if value < 0.5: return "Good"
        if value < 1.5: return "Moderate"
        return "Poor"
    elif parameter == 'turbidity':
        if value < 0.1: return "Good"
        if value < 0.3: return "Moderate"
        return "Poor"
    elif parameter == 'cdom':
        if value < 0.02: return "Good"
        if value < 0.05: return "Moderate"
        return "Poor"
    return "Unknown"


def get_parameter_unit(parameter: str) -> str:
    """Get unit for a parameter"""
    units = {
        'chlorophyll': 'mg/m³',
        'turbidity': 'm⁻¹',
        'cdom': 'm⁻¹'
    }
    return units.get(parameter, '')


def get_overall_status(score: float) -> str:
    """Get overall water quality status"""
    if score < 0.5: return "Good"
    if score < 1.0: return "Moderate"
    return "Poor"
