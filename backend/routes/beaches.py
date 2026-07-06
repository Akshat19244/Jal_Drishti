"""
Beaches API — /api/beaches
Extended: now includes PathoWatch-style coastal heatmap data.
"""
import math
from flask import Blueprint, request, jsonify
from services.data_service import DataService, is_near_coast
from utils.cache import TTLCache

beaches_bp = Blueprint('beaches', __name__)
cache = TTLCache()


@beaches_bp.route('/api/beaches', methods=['GET'])
def get_beaches():
    state = request.args.get('state', 'all')
    cache_key = f"beaches_{state}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})
    try:
        ds = DataService()
        beaches = ds.get_beaches(state=state)
        summary = _make_summary(beaches)
        result = {'beaches': beaches, 'summary': summary, 'total': len(beaches)}
        cache.set(cache_key, result, ttl=600)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@beaches_bp.route('/api/beaches/heatmap', methods=['GET'])
def get_beach_heatmap():
    """
    GET /api/beaches/heatmap?year=2024
    Returns coastal monitoring points with fcol values for PathoWatch-style heatmap.
    Each point: {lat, lng, fcol, safety, station, state}
    """
    year = request.args.get('year', None)
    cache_key = f"beaches_heatmap_{year}"
    cached = cache.get(cache_key)
    if cached:
        return jsonify({'success': True, 'data': cached})

    try:
        ds = DataService()
        df = ds.df.copy()

        # Coastal stations: sea, bay, creek, beach, estuary, gulf, backwater
        # Expanded: all station types near coast/water bodies with FColi data
        coastal_kw = ['sea water','bay of bengal','arabian sea','creek','beach',
                      'estuary','backwater','gulf','coastal','lagoon','baina',
                      'rushikonda','kovalam','marina','juhu','puri','goa',
                      'daman','diu','lakshadweep','pondicherry','port',
                      'thane creek','panvel','bassein','versova','worli',
                      'kakinada','paradip','visakhapatnam','mangalore',
                      'kochi','alappuzha','kozhikode','veli','vembanad']
        name_lower = df['Station_Name'].str.lower().fillna('')
        coast_mask = name_lower.str.contains('|'.join(coastal_kw), na=False)
        coast_df = df[coast_mask & df['Latitude'].notna() & df['Fecal_Coliform'].notna()].copy()

        # Remove points in landlocked areas
        if not coast_df.empty:
            geo_mask = coast_df.apply(
                lambda r: is_near_coast(r['Latitude'], r['Longitude'], r['State']),
                axis=1
            )
            coast_df = coast_df[geo_mask]

        if year and str(year) != 'all':
            coast_df = coast_df[coast_df['Year'] == int(year)]

        # Average by station
        grp = coast_df.groupby(['Station_Name','State','Latitude','Longitude'], observed=True).agg(
            fcol=('Fecal_Coliform','mean'),
            do=('DO','mean'),
            bod=('BOD','mean'),
            ph=('pH','mean'),
            turbidity=('Turbidity','mean'),
        ).reset_index()

        points = []
        for _, r in grp.iterrows():
            fcol = round(float(r['fcol']), 1)
            # PathoWatch classification
            if fcol < 100:
                safety = 'safe'
                color = '#16A34A'
            elif fcol < 500:
                safety = 'suspicious'
                color = '#EAB308'
            else:
                safety = 'contaminated'
                color = '#DC2626'

            points.append({
                'lat':     round(float(r['Latitude']), 6),
                'lng':     round(float(r['Longitude']), 6),
                'fcol':    fcol,
                'safety':  safety,
                'color':   color,
                'station': str(r['Station_Name']),
                'state':   str(r['State']),
                'do':      round(float(r['do']), 2) if not math.isnan(r['do']) else None,
                'bod':     round(float(r['bod']), 2) if not math.isnan(r['bod']) else None,
                'ph':      round(float(r['ph']), 2)  if not math.isnan(r['ph'])  else None,
            })

        # Summary counts
        summary = {
            'total': len(points),
            'safe':         sum(1 for p in points if p['safety'] == 'safe'),
            'suspicious':   sum(1 for p in points if p['safety'] == 'suspicious'),
            'contaminated': sum(1 for p in points if p['safety'] == 'contaminated'),
        }

        result = {'points': points, 'summary': summary, 'year': year or 'all'}
        cache.set(cache_key, result, ttl=600)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _make_summary(beaches):
    s = {}
    for b in beaches:
        q = b.get('bathing_quality', 'Unknown')
        s[q] = s.get(q, 0) + 1
    return s
