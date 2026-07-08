"""
Alerts API — /api/alerts
Smart alert generation based on CPCB threshold breaches.
"""
import pandas as pd
from flask import Blueprint, request, jsonify
from services.data_service import DataService
from utils.cache import TTLCache

alerts_bp = Blueprint('alerts', __name__)
cache = TTLCache()


@alerts_bp.route('/api/alerts', methods=['GET'])
def get_alerts():
    """
    GET /api/alerts?state=Gujarat&year=2024&sort=severity&limit=50
    Returns ranked alert list based on parameter thresholds.
    """
    state = request.args.get('state', 'Gujarat')
    year = request.args.get('year', None)
    sort_by = request.args.get('sort', 'severity')
    limit = int(request.args.get('limit', 50))
    
    cache_key = f"alerts_{state}_{year}_{sort_by}_{limit}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        alerts = ds.get_alerts(state=state, year=year)
        
        # Sort options
        if sort_by == 'severity':
            alerts.sort(key=lambda x: x.get('severity_score', 0), reverse=True)
        elif sort_by == 'parameter':
            alerts.sort(key=lambda x: x.get('parameter', ''))
        elif sort_by == 'date':
            alerts.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # Limit results
        alerts = alerts[:limit]
        
        # Group by severity for summary
        severity_counts = {'Critical': 0, 'Warning': 0, 'Info': 0}
        for alert in alerts:
            severity = alert.get('severity', 'Info')
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        result = {
            'alerts': alerts,
            'summary': severity_counts,
            'total': len(alerts)
        }
        cache.set(cache_key, result, ttl=300)
        
        return jsonify({
            'success': True,
            'data': result,
            'meta': {
                'state': state,
                'year': year or 'all',
                'sort': sort_by
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@alerts_bp.route('/api/alerts/summary', methods=['GET'])
def get_alerts_summary():
    """
    GET /api/alerts/summary?state=all
    Quick summary of alert counts by severity and state.
    """
    state = request.args.get('state', 'all')
    
    cache_key = f"alerts_summary_{state}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        
        if state == 'all':
            # All-India summary
            all_states = ds.get_unique_states()
            summary = {}
            total_critical = 0
            total_warning = 0
            
            for st in all_states:
                alerts = ds.get_alerts(state=st, year=None)
                critical = sum(1 for a in alerts if a.get('severity') == 'Critical')
                warning = sum(1 for a in alerts if a.get('severity') == 'Warning')
                
                summary[st] = {
                    'critical': critical,
                    'warning': warning,
                    'total': len(alerts)
                }
                total_critical += critical
                total_warning += warning
            
            result = {
                'by_state': summary,
                'india_total': {
                    'critical': total_critical,
                    'warning': total_warning
                }
            }
        else:
            # Single state summary
            alerts = ds.get_alerts(state=state, year=None)
            critical = sum(1 for a in alerts if a.get('severity') == 'Critical')
            warning = sum(1 for a in alerts if a.get('severity') == 'Warning')
            
            result = {
                'state': state,
                'critical': critical,
                'warning': warning,
                'total': len(alerts)
            }
        
        cache.set(cache_key, result, ttl=600)
        
        return jsonify({
            'success': True,
            'data': result,
            'meta': {'state': state}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@alerts_bp.route('/api/alerts/timeline', methods=['GET'])
def get_alerts_timeline():
    """
    GET /api/alerts/timeline?state=Gujarat&parameter=BOD&days=30
    Historical alert timeline for a parameter.
    """
    state = request.args.get('state', 'Gujarat')
    parameter = request.args.get('parameter', 'BOD')
    
    cache_key = f"alerts_timeline_{state}_{parameter}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        data = ds.get_state_data(state)
        
        if data.empty:
            return jsonify({'success': False, 'error': f'State not found: {state}'}), 404

        # Get latest reading per station per month
        data['YearMonth'] = data['Date_Parsed'].dt.to_period('M')
        
        timeline = []
        for period in sorted(data['YearMonth'].dropna().unique()):
            period_data = data[data['YearMonth'] == period]
            param_vals = period_data[parameter].dropna()
            
            if len(param_vals) > 0:
                # Collect station-level info for this period
                station_entries = []
                for _, row in period_data.iterrows():
                    pv = row.get(parameter)
                    if pd.notna(pv):
                        station_entries.append({
                            'station': row.get('Station_Name', row.get('Station', 'Unknown')),
                            'water_body_type': row.get('Water_Body_Type', 'River'),
                            'basin': row.get('Basin', ''),
                            'value': round(float(pv), 2)
                        })
                # Pick the station with the highest value for this period
                worst_entry = max(station_entries, key=lambda x: x['value']) if station_entries else {}
                station_names = list(set(e['station'] for e in station_entries))
                timeline.append({
                    'date': str(period),
                    'avg': round(float(param_vals.mean()), 2),
                    'min': round(float(param_vals.min()), 2),
                    'max': round(float(param_vals.max()), 2),
                    'count': int(len(param_vals)),
                    'parameter': parameter,
                    'station': ', '.join(station_names[:3]) + (f' +{len(station_names)-3} more' if len(station_names) > 3 else ''),
                    'water_body_type': worst_entry.get('water_body_type', 'River'),
                    'basin': worst_entry.get('basin', '')
                })
        
        result = {
            'state': state,
            'parameter': parameter,
            'timeline': timeline[-12:] if len(timeline) > 12 else timeline  # Last 12 months
        }
        cache.set(cache_key, result, ttl=600)
        
        return jsonify({
            'success': True,
            'data': result,
            'meta': {'state': state, 'parameter': parameter}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
