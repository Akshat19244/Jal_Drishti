"""
WQI Calculator and CPCB Threshold Engine.
Matches the existing frontend WQI formula exactly.
"""
import math
import pandas as pd


# ─── CPCB THRESHOLDS ────────────────────────────────────────────

THRESHOLDS = {
    'BOD': {'warning': 10, 'critical': 30, 'unit': 'mg/L'},
    'DO': {'warning': 4, 'critical': 2, 'unit': 'mg/L', 'inverted': True},  # lower = worse
    'Fecal_Coliform': {'warning': 200, 'critical': 500, 'unit': 'MPN/100mL'},
    'pH': {'low_warning': 6, 'high_warning': 9, 'unit': ''},
    'Turbidity': {'warning': 50, 'critical': 100, 'unit': 'NTU'},
    'EC': {'warning': 2000, 'critical': 3000, 'unit': 'µS/cm'},
    'Total_Coliform': {'warning': 500, 'critical': 5000, 'unit': 'MPN/100mL'},
}


def calculate_wqi(do=None, bod=None, ph=None, turbidity=None, fcol=None):
    """
    Calculate Water Quality Index using weighted sub-scores.
    Matches the existing frontend JS formula exactly.

    Weights:
        DO: 0.25, BOD: 0.25, pH: 0.15, Turbidity: 0.15, FColi: 0.20

    Returns:
        float: WQI score (0-100, lower = better)
    """
    score = 0.0
    total_weight = 0.0

    # DO sub-index (higher DO = better, so invert)
    if do is not None and not _is_nan(do):
        do_score = max(0, min(100, (1 - do / 8) * 100))
        score += do_score * 0.25
        total_weight += 0.25

    # BOD sub-index (higher = worse)
    if bod is not None and not _is_nan(bod):
        bod_score = min(100, (bod / 30) * 100)
        score += bod_score * 0.25
        total_weight += 0.25

    # pH sub-index (deviation from 7)
    if ph is not None and not _is_nan(ph):
        ph_score = min(100, abs(ph - 7) * 25)
        score += ph_score * 0.15
        total_weight += 0.15

    # Turbidity sub-index
    if turbidity is not None and not _is_nan(turbidity):
        turb_score = min(100, (turbidity / 200) * 100)
        score += turb_score * 0.15
        total_weight += 0.15

    # Fecal Coliform sub-index (log scale)
    if fcol is not None and not _is_nan(fcol):
        fcol_score = min(100, (math.log10(fcol + 1) / 6) * 100)
        score += fcol_score * 0.20
        total_weight += 0.20

    if total_weight > 0:
        return round(score / total_weight * 10) / 10
    return 50.0


def classify_wqi(wqi_score):
    """Classify WQI score into category."""
    if wqi_score is None or _is_nan(wqi_score):
        return 'Unknown'
    if wqi_score <= 25:
        return 'Excellent'
    elif wqi_score <= 50:
        return 'Good'
    elif wqi_score <= 75:
        return 'Moderate'
    elif wqi_score <= 90:
        return 'Poor'
    else:
        return 'Critical'


def wqi_color(wqi_score):
    """Get color hex for WQI score."""
    if wqi_score is None or _is_nan(wqi_score):
        return '#6B645C'
    if wqi_score <= 25:
        return '#16A34A'
    elif wqi_score <= 50:
        return '#65A30D'
    elif wqi_score <= 75:
        return '#D97706'
    elif wqi_score <= 90:
        return '#EA580C'
    else:
        return '#DC2626'


def check_thresholds(row):
    """
    Check a station's readings against CPCB thresholds.
    Returns list of alert dicts with severity info.

    Alert severity scoring:
        Critical: 80-100 (parameter > critical threshold)
        Warning:  40-79  (parameter > warning threshold)
        Info:     10-39  (parameter approaching threshold)
    """
    alerts = []

    # BOD check
    bod = _safe_val(row, 'BOD')
    if bod is not None:
        if bod > 30:
            alerts.append({
                'parameter': 'BOD',
                'value': round(bod, 2),
                'threshold': 30,
                'severity': 'Critical',
                'severity_score': min(100, int(50 + (bod - 30) / 30 * 50)),
                'message': f'BOD at {bod:.1f} mg/L — exceeds CPCB critical limit of 30 mg/L',
                'unit': 'mg/L'
            })
        elif bod > 10:
            alerts.append({
                'parameter': 'BOD',
                'value': round(bod, 2),
                'threshold': 10,
                'severity': 'Warning',
                'severity_score': int(40 + (bod - 10) / 20 * 40),
                'message': f'BOD at {bod:.1f} mg/L — exceeds CPCB warning of 10 mg/L',
                'unit': 'mg/L'
            })

    # DO check (inverted — lower = worse)
    do = _safe_val(row, 'DO')
    if do is not None:
        if do < 2:
            alerts.append({
                'parameter': 'DO',
                'value': round(do, 2),
                'threshold': 4,
                'severity': 'Critical',
                'severity_score': min(100, int(80 + (2 - do) * 10)),
                'message': f'DO at {do:.1f} mg/L — severe hypoxia, CPCB min is 4 mg/L',
                'unit': 'mg/L'
            })
        elif do < 4:
            alerts.append({
                'parameter': 'DO',
                'value': round(do, 2),
                'threshold': 4,
                'severity': 'Warning',
                'severity_score': int(40 + (4 - do) / 2 * 40),
                'message': f'DO at {do:.1f} mg/L — below CPCB minimum of 4 mg/L',
                'unit': 'mg/L'
            })

    # Fecal Coliform check
    fcol = _safe_val(row, 'Fecal_Coliform')
    if fcol is not None:
        if fcol > 500:
            severity_score = min(100, int(60 + math.log10(max(fcol / 500, 1)) * 20))
            alerts.append({
                'parameter': 'Fecal Coliform',
                'value': round(fcol, 0),
                'threshold': 500,
                'severity': 'Critical',
                'severity_score': severity_score,
                'message': f'Fecal Coliform at {fcol:,.0f} MPN/100mL — {fcol/500:.0f}× CPCB limit',
                'unit': 'MPN/100mL'
            })
        elif fcol > 200:
            alerts.append({
                'parameter': 'Fecal Coliform',
                'value': round(fcol, 0),
                'threshold': 200,
                'severity': 'Warning',
                'severity_score': int(40 + (fcol - 200) / 300 * 30),
                'message': f'Fecal Coliform at {fcol:,.0f} MPN/100mL — approaching CPCB limit',
                'unit': 'MPN/100mL'
            })

    # pH check (out of range)
    ph = _safe_val(row, 'pH')
    if ph is not None:
        if ph < 6 or ph > 9:
            alerts.append({
                'parameter': 'pH',
                'value': round(ph, 2),
                'threshold': '6.0–9.0',
                'severity': 'Warning',
                'severity_score': int(40 + abs(ph - 7.5) * 10),
                'message': f'pH at {ph:.2f} — outside CPCB range of 6.0–9.0',
                'unit': ''
            })

    # Turbidity check
    turb = _safe_val(row, 'Turbidity')
    if turb is not None:
        if turb > 100:
            alerts.append({
                'parameter': 'Turbidity',
                'value': round(turb, 1),
                'threshold': 100,
                'severity': 'Warning',
                'severity_score': min(100, int(50 + (turb - 100) / 100 * 30)),
                'message': f'Turbidity at {turb:.0f} NTU — exceeds 100 NTU warning level',
                'unit': 'NTU'
            })

    return alerts


# ─── HELPERS ─────────────────────────────────────────────────────

def _is_nan(val):
    """Check if value is NaN (handles pandas NA)."""
    try:
        if pd.isna(val):
            return True
    except (ValueError, TypeError):
        pass
    try:
        return math.isnan(val)
    except (TypeError, ValueError):
        return False


def _safe_val(row, col):
    """Safely extract a numeric value from a row."""
    try:
        val = row.get(col) if hasattr(row, 'get') else row[col]
        if pd.isna(val):
            return None
        return float(val)
    except (KeyError, TypeError, ValueError):
        return None
