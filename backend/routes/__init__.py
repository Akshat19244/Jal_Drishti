# Routes package
from routes.timeline import timeline_bp
from routes.stations import stations_bp
from routes.explorer import explorer_bp
from routes.alerts import alerts_bp
from routes.report import report_bp
from routes.chat import chat_bp
from routes.beaches import beaches_bp
from routes.live import live_bp

__all__ = [
    'timeline_bp', 'stations_bp', 'explorer_bp', 'alerts_bp',
    'report_bp', 'chat_bp', 'beaches_bp', 'live_bp'
]
