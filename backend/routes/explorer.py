"""
Explorer API — /api/explorer
Three-view interface: state-wise choropleth, paginated station table, river basins.
"""
from flask import Blueprint, request, jsonify
from services.data_service import DataService
from utils.cache import TTLCache

explorer_bp = Blueprint('explorer', __name__)
cache = TTLCache()


@explorer_bp.route('/api/explorer', methods=['GET'])
def get_explorer():
    """
    GET /api/explorer?view=state|station|river
    Multi-view endpoint for explorer section.
    """
    view = request.args.get('view', 'state')
    
    # State view
    if view == 'state':
        return get_explorer_state()
    
    # Station table view
    elif view == 'station':
        return get_explorer_station()
    
    # River/basin view
    elif view == 'river':
        return get_explorer_river()
    
    else:
        return jsonify({'success': False, 'error': f'Unknown view: {view}'}), 400


@explorer_bp.route('/api/explorer/state', methods=['GET'])
def get_explorer_state():
    """
    GET /api/explorer/state
    State-wise WQI averages for choropleth visualization.
    """
    cache_key = "explorer_state"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        states = ds.get_explorer_state_view()
        cache.set(cache_key, states, ttl=600)
        
        return jsonify({
            'success': True,
            'data': states,
            'meta': {
                'view': 'state',
                'state_count': len(states)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@explorer_bp.route('/api/explorer/station', methods=['GET'])
def get_explorer_station():
    """
    GET /api/explorer/station?page=1&limit=50&search=Sabar&state=all&basin=Ganga&sort=wqi&order=desc
    Paginated station table with search, filter, and sort.
    """
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    search = request.args.get('search', None)
    state = request.args.get('state', 'all')
    basin = request.args.get('basin', None)
    sort_by = request.args.get('sort', 'wqi')
    sort_order = request.args.get('order', 'desc')
    
    # Validate pagination
    if page < 1 or limit < 1:
        return jsonify({'success': False, 'error': 'Invalid page/limit'}), 400

    cache_key = f"explorer_station_{page}_{limit}_{search}_{state}_{basin}_{sort_by}_{sort_order}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        stations, total = ds.get_explorer_station_view(
            page=page,
            limit=limit,
            search=search,
            state=state,
            basin=basin,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        result = {
            'stations': stations,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit
            }
        }
        cache.set(cache_key, result, ttl=300)
        
        return jsonify({
            'success': True,
            'data': result,
            'meta': {
                'view': 'station',
                'search': search,
                'state': state,
                'basin': basin or 'all'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@explorer_bp.route('/api/explorer/river', methods=['GET'])
def get_explorer_river():
    """
    GET /api/explorer/river
    Basin-grouped stations for accordion view with WQI trends.
    """
    cache_key = "explorer_river"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        basins = ds.get_explorer_river_view()
        cache.set(cache_key, basins, ttl=600)
        
        return jsonify({
            'success': True,
            'data': basins,
            'meta': {
                'view': 'river',
                'basin_count': len(basins)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@explorer_bp.route('/api/explorer/state/<state_name>', methods=['GET'])
def get_state_detail(state_name):
    """
    GET /api/explorer/state/Gujarat
    Detailed state view with top polluted stations + sparklines.
    """
    cache_key = f"explorer_state_{state_name}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        data = ds.get_state_data(state_name)
        
        if data.empty:
            return jsonify({'success': False, 'error': f'State not found: {state_name}'}), 404

        from services.data_service import _safe_round as _sr, _safe_float as _sf
        import math as _math

        def _sane(v):
            try:
                f = float(v)
                return None if (_math.isnan(f) or _math.isinf(f)) else round(f, 2)
            except Exception:
                return None

        # State-level stats
        state_stats = {
            'state': state_name,
            'stations': int(data['Station_Name'].nunique()),
            'wqi_avg': _sane(data['WQI'].mean()),
            'wqi_class': ds.df[ds.df['State'] == state_name]['WQI_Class'].mode()[0] if not data.empty else 'Unknown',
            'do_avg': _sane(data['DO'].mean()),
            'bod_avg': _sane(data['BOD'].mean()),
            'fcol_avg': _sane(data['Fecal_Coliform'].mean()),
        }


        # Top 5 worst stations
        worst = data.groupby('Station_Name', observed=True).agg({
            'WQI': 'mean',
            'BOD': 'mean',
            'DO': 'mean',
            'Fecal_Coliform': 'mean',
            'District': 'first',
        }).sort_values('WQI', ascending=False).head(5)

        worst_stations = []
        for idx, (name, row) in enumerate(worst.iterrows()):
            worst_stations.append({
                'rank': idx + 1,
                'name': str(name),
                'district': str(row['District']),
                'wqi': round(float(row['WQI']), 2),
                'bod': round(float(row['BOD']), 2),
                'do': round(float(row['DO']), 2),
                'fcol': round(float(row['Fecal_Coliform']), 2),
            })

        result = {
            'stats': state_stats,
            'worst_stations': worst_stations
        }
        cache.set(cache_key, result, ttl=600)
        
        return jsonify({
            'success': True,
            'data': result,
            'meta': {'state': state_name}
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
