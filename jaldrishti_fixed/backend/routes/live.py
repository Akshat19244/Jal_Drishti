"""
Live Stream API — /api/live/stream
Server-Sent Events (SSE) for real-time station data updates with synthetic readings.
Every 30 seconds, picks 1-2 random stations and generates simulated new readings.
"""
from flask import Blueprint, Response
import random
import time
import json
from datetime import datetime
from services.data_service import DataService
from services.wqi_calculator import calculate_wqi, classify_wqi

live_bp = Blueprint('live', __name__)


@live_bp.route('/api/live/stream', methods=['GET'])
def stream_live():
    """
    GET /api/live/stream
    SSE endpoint that streams synthetic readings every 30 seconds.
    Client should listen with EventSource and handle 'reading' events.
    """
    def event_generator():
        try:
            ds = DataService()
            
            # Get all stations for random selection
            all_stations = ds.df.drop_duplicates('Station_Name')[
                ['Station_Name', 'State', 'Basin', 'Latitude', 'Longitude', 
                 'DO', 'BOD', 'pH', 'Turbidity', 'Fecal_Coliform']
            ].to_dict('records')
            
            if not all_stations:
                yield f"data: {json.dumps({'error': 'No stations found'})}\n\n"
                return
            
            while True:
                try:
                    # Pick 1-2 random stations
                    count = random.randint(1, 2)
                    selected = random.sample(all_stations, min(count, len(all_stations)))
                    
                    for station in selected:
                        # Generate synthetic reading (±10% noise)
                        noise_factor = random.uniform(0.9, 1.1)
                        
                        reading = {
                            'timestamp': datetime.now().isoformat(),
                            'station_name': station['Station_Name'],
                            'state': station['State'],
                            'basin': station['Basin'],
                            'lat': float(station['Latitude']) if station['Latitude'] else None,
                            'lng': float(station['Longitude']) if station['Longitude'] else None,
                            'do': round(float(station['DO']) * noise_factor, 2) if station['DO'] else None,
                            'bod': round(float(station['BOD']) * noise_factor, 2) if station['BOD'] else None,
                            'ph': round(float(station['pH']) + random.uniform(-0.5, 0.5), 2) if station['pH'] else None,
                            'turbidity': round(float(station['Turbidity']) * noise_factor, 2) if station['Turbidity'] else None,
                            'fcol': round(float(station['Fecal_Coliform']) * noise_factor, 2) if station['Fecal_Coliform'] else None,
                        }
                        
                        # Calculate WQI for synthetic reading
                        reading['wqi'] = calculate_wqi(
                            do=reading['do'],
                            bod=reading['bod'],
                            ph=reading['ph'],
                            turbidity=reading['turbidity'],
                            fcol=reading['fcol']
                        )
                        reading['wqi_class'] = classify_wqi(reading['wqi'])
                        
                        # Send SSE event
                        yield f"event: update\ndata: {json.dumps(reading)}\n\n"
                    
                    # Wait 30 seconds before next batch
                    time.sleep(30)
                
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    break
        
        except Exception as e:
            print(f"[SSE Error] {e}")
            yield f"data: {json.dumps({'error': 'Stream error'})}\n\n"
    
    # Return SSE response
    return Response(
        event_generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@live_bp.route('/api/live/test', methods=['GET'])
def test_live():
    """
    GET /api/live/test
    Quick test endpoint to verify SSE is working.
    """
    def test_stream():
        for i in range(3):
            data = {
                'index': i,
                'timestamp': datetime.now().isoformat(),
                'message': f'Test message {i+1}'
            }
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)
    
    return Response(
        test_stream(),
        mimetype='text/event-stream'
    )
