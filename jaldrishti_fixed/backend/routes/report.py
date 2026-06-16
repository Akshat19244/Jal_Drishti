"""
Report API — /api/report
FIX: report_id was a random UUID that never appeared in the filename,
     so /download always returned 404. Now the filename itself IS the report_id.
"""
import os
from flask import Blueprint, request, jsonify, send_file
from services.data_service import DataService
from services.report_generator import ReportGenerator

report_bp = Blueprint('report', __name__)

@report_bp.route('/api/report/generate', methods=['POST'])
def generate_report():
    try:
        params = request.get_json() or {}
        scope        = params.get('scope', 'state')
        scope_value  = params.get('scope_value', 'Gujarat')
        fmt          = params.get('format', 'csv').lower()
        start_year   = params.get('start_year')
        end_year     = params.get('end_year')
        parameters   = params.get('parameters', ['DO','BOD','pH'])

        if fmt not in ('csv','json','pdf'):
            return jsonify({'success': False, 'error': f'Invalid format: {fmt}'}), 400

        ds = DataService()
        data_df = ds.get_report_data(scope, scope_value, start_year, end_year, parameters)

        if data_df is None or len(data_df) == 0:
            return jsonify({'success': False, 'error': 'No data found for given filters'}), 404

        rg = ReportGenerator()
        info = rg.generate(data_df=data_df, params=params, fmt=fmt)

        # FIX: return the filename (without extension) as report_id
        # so /download/<report_id> can reliably find the file
        report_id = info['filename']   # e.g. "JalDrishti_state_Gujarat_20260611_120000.csv"

        return jsonify({
            'success': True,
            'data': {
                'report_id': report_id,
                'filename':  info['filename'],
                'format':    fmt,
                'size':      info['size'],
                'rows':      len(data_df),
                'generated_at': info['generated_at']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@report_bp.route('/api/report/download/<path:report_id>', methods=['GET'])
def download_report(report_id):
    """
    GET /api/report/download/JalDrishti_state_Gujarat_20260611_120000.csv
    FIX: report_id IS the filename now, so lookup is always exact.
    """
    try:
        rg = ReportGenerator()
        file_path = os.path.join(rg.report_dir, report_id)

        if not os.path.exists(file_path):
            # Fallback: partial match (backwards compat)
            for fname in os.listdir(rg.report_dir):
                if report_id in fname:
                    file_path = os.path.join(rg.report_dir, fname)
                    report_id = fname
                    break
            else:
                return jsonify({'success': False, 'error': 'Report not found'}), 404

        if report_id.endswith('.pdf'):
            mime = 'application/pdf'
        elif report_id.endswith('.csv'):
            mime = 'text/csv'
        elif report_id.endswith('.json'):
            mime = 'application/json'
        else:
            mime = 'application/octet-stream'

        return send_file(
            file_path,
            mimetype=mime,
            as_attachment=True,
            download_name=report_id
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
