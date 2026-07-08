"""
JalDrishti Backend — Flask REST API
FIX: CORS now allows all origins (file:// + localhost variants for opening index.html directly).
FIX: DataService singleton is initialized once; blueprints import it without re-loading CSV.
"""
import os
import sys
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from services.data_service import DataService


def create_app():
    app = Flask(__name__, static_folder='../frontend', static_url_path='')
    app.config.from_object(Config)

    # FIX: Allow all origins so the HTML file works when opened directly from disk
    CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type"]}})

    # Initialize DataService (loads CSV once)
    try:
        print("[app.py] Initializing DataService...")
        ds = DataService()
        print(f"[app.py] DataService ready — {len(ds.df):,} rows loaded")
    except Exception as e:
        print(f"[ERROR] Failed to load CSV: {e}")
        sys.exit(1)

    # Register blueprints
    from routes.timeline import timeline_bp
    from routes.stations import stations_bp
    from routes.explorer import explorer_bp
    from routes.alerts import alerts_bp
    from routes.report import report_bp
    from routes.chat import chat_bp
    from routes.beaches import beaches_bp
    from routes.live import live_bp
    from routes.predict import predict_bp
    from routes.sentinel import sentinel_bp
    from routes.nasa_analysis import nasa_bp
    from routes.predict_condition import predict_condition_bp
    from routes.gee import gee_bp
    from routes.beach_predict import beach_predict_bp

    for bp in [timeline_bp, stations_bp, explorer_bp, alerts_bp, report_bp, chat_bp, beaches_bp, live_bp, predict_bp, sentinel_bp, nasa_bp, predict_condition_bp, gee_bp, beach_predict_bp]:
        app.register_blueprint(bp)

    @app.route('/api/health', methods=['GET'])
    def health():
        ds = DataService()
        return jsonify({
            'success': True, 'status': 'ok',
            'rows': len(ds.df),
            'states': int(ds.df['State'].nunique()),
            'years': f"{int(ds.df['Year'].min())}–{int(ds.df['Year'].max())}"
        })

    @app.route('/', methods=['GET'])
    @app.route('/index.html', methods=['GET'])
    def serve_frontend():
        idx = os.path.join(Config.FRONTEND_DIR, 'index.html')
        try:
            with open(idx, 'r', encoding='utf-8') as f:
                return f.read(), 200, {'Content-Type': 'text/html'}
        except FileNotFoundError:
            return jsonify({'success': False, 'error': 'frontend/index.html not found'}), 404

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal(e):
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    return app


if __name__ == '__main__':
    app = create_app()
    print(f"\n[JalDrishti] Starting on http://localhost:{Config.PORT}")
    print(f"[JalDrishti] Open frontend: http://localhost:{Config.PORT}/")
    print(f"[JalDrishti] Health check: http://localhost:{Config.PORT}/api/health")
    print(f"[JalDrishti] CSV: {Config.CSV_PATH}\n")
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG, threaded=True)
