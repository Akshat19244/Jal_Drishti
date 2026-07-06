"""Google Earth Engine Data-Points Route

Returns per-beach satellite water quality indices (CDOM, Turbidity, Chlorophyll, Kd490)
for display as data points on the Leaflet map, with exceedance limit checks.

Uses a SINGLE batch GEE query (reduceRegions) instead of per-beach queries —
this means 1 GEE API call instead of N, making it fast for all beaches.

ONLY live Landsat 8/9 satellite data is used — no CSV/proxy fallback.
If GEE returns no data for a beach, that beach is excluded.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from services.data_service import DataService, is_near_coast
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

gee_bp = Blueprint('gee', __name__)

_BEACH_KEYWORDS = [
    'beach', 'coast', 'sea', 'shore', 'marine',
    'port', 'creek', 'harbour', 'harbor', 'bay',
    'mandvi', 'alang', 'somnath', 'diu', 'porbandar',
    'juhu', 'marina', 'puri', 'kovalam', 'goa',
    'visakhapatnam', 'digha', 'chandipur', 'calangute',
    'vasco', 'candolim', 'baga', 'baina', 'rushikonda',
    'estuary', 'backwater', 'gulf', 'lagoon',
    'thane creek', 'panvel', 'bassein', 'versova', 'worli',
    'kakinada', 'paradip', 'mangalore', 'kochi',
    'alappuzha', 'kozhikode', 'veli', 'vembanad',
    'daman', 'pondicherry', 'lakshadweep',
]


@gee_bp.route('/api/gee/data-points', methods=['GET'])
def get_gee_data_points():
    """Get per-beach satellite indices for map overlay.

    Returns ALL 4 water quality indices (CDOM, Turbidity, Chlorophyll, Kd490)
    for each beach point using a single batch GEE query.

    Query params:
        date: YYYY-MM-DD (optional, defaults to recent)

    Returns list of data points each containing all 4 indices with value/status.
    """
    date_str = request.args.get('date')

    try:
        ds = DataService()
        df = ds.df

        name_lower = df['Station_Name'].str.lower().fillna('')
        beach_mask = name_lower.str.contains('|'.join(_BEACH_KEYWORDS), na=False)
        beach_df = df[beach_mask & df['Latitude'].notna() & df['Longitude'].notna()].copy()

        # Remove points in landlocked areas
        if not beach_df.empty:
            geo_mask = beach_df.apply(
                lambda r: is_near_coast(r['Latitude'], r['Longitude'], r['State']),
                axis=1
            )
            removed = int((~geo_mask).sum())
            if removed:
                logger.info(f"[GEE] Removed {removed} inland points far from coast")
            beach_df = beach_df[geo_mask]

        if beach_df.empty:
            return jsonify({'success': False, 'error': 'No beach data available'}), 404

        beach_data = beach_df.groupby(['Station_Name', 'State'], observed=True).agg({
            'Latitude': 'mean',
            'Longitude': 'mean',
        }).dropna().reset_index()

        if beach_data.empty:
            return jsonify({'success': False, 'error': 'No beach data available'}), 404

        from services.gee_service import GEEService
        gee = GEEService()

        if not gee.is_available():
            return jsonify({
                'success': False,
                'error': 'Google Earth Engine is not initialized. Live Landsat data unavailable.',
            }), 503

        ee = gee.ee

        if not date_str:
            date_str = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        # Build a single FeatureCollection from all beach points
        features = []
        for _, row in beach_data.iterrows():
            lat, lon = row['Latitude'], row['Longitude']
            if pd.notna(lat) and pd.notna(lon):
                feat = ee.Feature(
                    ee.Geometry.Point([float(lon), float(lat)]),
                    {
                        'name': str(row['Station_Name']),
                        'state': str(row['State']),
                        'lat': float(lat),
                        'lon': float(lon),
                    },
                )
                features.append(feat)

        beach_fc = ee.FeatureCollection(features)

        data_points = []
        used_year = None
        status_priority = {'safe': 0, 'moderate': 1, 'exceeded': 2}

        # Build date configs from the requested date: narrow window → full year → prior years
        try:
            req_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            req_date = datetime.now() - timedelta(days=5)

        req_yr = str(req_date.year)
        window_start = (req_date - timedelta(days=15)).strftime('%Y-%m-%d')
        window_end = (req_date + timedelta(days=15)).strftime('%Y-%m-%d')
        yr_start = f'{req_date.year}-01-01'
        yr_end = f'{req_date.year}-12-31'

        date_configs = [
            (f'{req_yr} window', window_start, window_end),
            (f'{req_yr}',       yr_start,       yr_end),
        ]
        for fallback_yr in range(req_date.year - 1, req_date.year - 4, -1):
            date_configs.append((str(fallback_yr), f'{fallback_yr}-01-01', f'{fallback_yr}-12-31'))

        for label, start_date, end_date in date_configs:
            for coll_name in ['LANDSAT/LC08/C02/T1_L2', 'LANDSAT/LC09/C02/T1_L2']:
                try:
                    logger.info(f"[GEE] Batch query: {coll_name} {label} over {len(features)} beaches")
                    coll = (
                        ee.ImageCollection(coll_name)
                        .filterBounds(beach_fc)
                        .filterDate(start_date, end_date)
                        .filter(ee.Filter.lte('CLOUD_COVER', 70))
                    )

                    count = coll.size().getInfo()
                    if count == 0:
                        logger.debug(f"[GEE] No scenes for {coll_name} in {yr_label}")
                        continue

                    image = coll.median()

                    ndti = image.normalizedDifference(['SR_B4', 'SR_B3']).rename('ndti')
                    cdom_img = image.select('SR_B2').divide(image.select('SR_B4').add(0.001)).rename('cdom')
                    chlor_img = image.normalizedDifference(['SR_B5', 'SR_B4']).rename('chlorophyll')
                    kd490_img = image.select('SR_B3').divide(image.select('SR_B2').add(0.001)).multiply(0.5).rename('kd490')

                    all_bands = image.addBands([ndti, cdom_img, chlor_img, kd490_img])
                    band_names = ['ndti', 'cdom', 'chlorophyll', 'kd490']

                    sampled = all_bands.select(band_names).sampleRegions(
                        collection=beach_fc,
                        scale=30,
                    )

                    result = sampled.getInfo()

                    # Debug: log first few raw GEE values
                    if result and 'features' in result:
                        for i, feat in enumerate(result['features'][:3]):
                            p = feat.get('properties', {})
                            logger.info(f"[GEE] RAW sample #{i}: name={p.get('name')} "
                                        f"ndti={p.get('ndti')} cdom={p.get('cdom')} "
                                        f"chlor={p.get('chlorophyll')} kd490={p.get('kd490')}")

                    if not result or 'features' not in result:
                        continue

                    for feat in result['features']:
                        props = feat.get('properties', {})
                        name = props.get('name', 'Unknown')
                        lat = props.get('lat')
                        lon = props.get('lon')
                        if lat is None or lon is None:
                            continue

                        def safe_val(v):
                            if v is None:
                                return None
                            try:
                                fv = float(v)
                                if np.isnan(fv):
                                    return None
                                return fv
                            except (TypeError, ValueError):
                                return None

                        raw_ndti = safe_val(props.get('ndti'))
                        raw_cdom = safe_val(props.get('cdom'))
                        raw_chlor = safe_val(props.get('chlorophyll'))
                        raw_kd490 = safe_val(props.get('kd490'))

                        has_data = any(v is not None and v > 0 for v in [raw_ndti, raw_cdom, raw_chlor, raw_kd490])
                        if not has_data:
                            continue

                        param_values = {
                            'cdom': raw_cdom,
                            'turbidity': raw_ndti,
                            'chlorophyll': raw_chlor,
                            'kd490': raw_kd490,
                        }

                        result_indices = {}
                        for user_param, val in param_values.items():
                            ex = gee.get_exceedance_status(user_param, val)
                            result_indices[user_param] = {
                                'value': round(val, 4),
                                'status': ex['status'],
                                'limit': ex['limit'],
                                'unit': ex['unit'],
                            }

                        worst_status = max(
                            (result_indices[p]['status'] for p in result_indices),
                            key=lambda s: status_priority.get(s, 0),
                        )

                        if worst_status == 'exceeded':
                            style = {'color': '#DC2626', 'fillColor': '#DC2626', 'fillOpacity': 0.8, 'radius': 10}
                        elif worst_status == 'moderate':
                            style = {'color': '#D97706', 'fillColor': '#D97706', 'fillOpacity': 0.7, 'radius': 8}
                        else:
                            style = {'color': '#16A34A', 'fillColor': '#16A34A', 'fillOpacity': 0.7, 'radius': 7}

                        data_points.append({
                            'name': name,
                            'lat': float(lat),
                            'lon': float(lon),
                            'indices': result_indices,
                            'overall_status': worst_status,
                            'source': 'landsat',
                            'satellite': 'landsat',
                            'data_year': label.split()[0],
                            'style': style,
                        })

                    used_year = label
                    if data_points:
                        logger.info(f"[GEE] Got data for {len(data_points)} beaches from {coll_name} {label}")
                        break

                except Exception as e:
                    logger.debug(f"[GEE] Batch query failed for {coll_name} {label}: {e}")
                    continue

            if data_points:
                break

        if not data_points:
            return jsonify({
                'success': False,
                'error': 'No live Landsat data available for any beach. GEE returned no valid pixels.',
            }), 404

        return jsonify({
            'success': True,
            'data': {
                'points': data_points,
                'total': len(data_points),
                'date': date_str,
                'source': 'landsat',
                'satellite': 'landsat',
                'data_year': used_year,
                'resolution': '30m',
                'description': f'Landsat 8/9 live data ({used_year})',
            },
        })

    except Exception as e:
        logger.error(f"[GEE] Failed to get data points: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
