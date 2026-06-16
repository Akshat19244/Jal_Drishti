"""
JalDrishti Configuration
FIX: CSV_PATH now resolves relative paths from the PROJECT ROOT (jal drishti/),
     not from wherever you launch Python. So 'india_research_full.csv' in .env
     correctly finds <project_root>/india_research_full.csv regardless of CWD.
"""
import os
from dotenv import load_dotenv

# Load .env from project root (one level up from backend/)
_PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(_PROJECT_ROOT, '.env'))


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'jaldrishti-dev-key')
    DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'
    PORT = int(os.getenv('PORT', 5000))

    # FIX: resolve CSV_PATH relative to project root, not CWD
    _csv_raw = os.getenv('CSV_PATH', 'india_research_full.csv')
    if os.path.isabs(_csv_raw):
        CSV_PATH = _csv_raw
    else:
        CSV_PATH = os.path.normpath(os.path.join(_PROJECT_ROOT, _csv_raw))

    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'anthropic')
    LLM_API_KEY = os.getenv('LLM_API_KEY', '')

    REPORT_DIR = os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.getenv('REPORT_DIR', 'reports'))
    )

    FRONTEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
