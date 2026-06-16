"""
Report Generator — PDF, CSV, and JSON report creation.
FIX 1: _generate_json used fillna('') on a DataFrame with Categorical columns (State, Basin etc.)
        which crashes in pandas >= 2.x. Now converts categoricals to str first.
FIX 2: get_report_data returns a raw DataFrame which isn't JSON serializable — route.py now
        never tries to json.dumps the df directly; it calls generate() instead.
"""
import os
import uuid
import json
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

from config import Config


class ReportGenerator:
    def __init__(self):
        self.report_dir = Config.REPORT_DIR
        os.makedirs(self.report_dir, exist_ok=True)

    def generate(self, data_df, params, fmt='pdf'):
        report_id = str(uuid.uuid4())[:12]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        scope_label = f"{params.get('scope','report')}_{params.get('scope_value','all')}".replace(' ','_').replace('/','_')

        if fmt == 'pdf':
            filename = f"JalDrishti_{scope_label}_{timestamp}.pdf"
            filepath = os.path.join(self.report_dir, filename)
            self._generate_pdf(data_df, params, filepath)
        elif fmt == 'csv':
            filename = f"JalDrishti_{scope_label}_{timestamp}.csv"
            filepath = os.path.join(self.report_dir, filename)
            self._generate_csv(data_df, filepath)
        elif fmt == 'json':
            filename = f"JalDrishti_{scope_label}_{timestamp}.json"
            filepath = os.path.join(self.report_dir, filename)
            self._generate_json(data_df, params, filepath)
        else:
            raise ValueError(f"Unsupported format: {fmt}")

        return {
            'report_id': report_id,
            'filename': filename,
            'path': filepath,
            'format': fmt,
            'size': os.path.getsize(filepath),
            'generated_at': datetime.now().isoformat()
        }

    def _safe_df(self, data_df):
        """Convert Categorical columns to str so fillna/to_dict work safely in pandas 2.x."""
        df = data_df.copy()
        for col in df.columns:
            if hasattr(df[col], 'cat'):
                df[col] = df[col].astype(str)
        return df

    def _generate_csv(self, data_df, filepath):
        self._safe_df(data_df).to_csv(filepath, index=False)

    def _generate_json(self, data_df, params, filepath):
        """FIX: Convert categoricals before fillna to avoid pandas 2.x Categorical TypeError."""
        df = self._safe_df(data_df)
        records = df.fillna('').to_dict(orient='records')
        # Make values JSON-safe
        clean = []
        for row in records:
            clean.append({k: (v if not isinstance(v, float) or v == v else None) for k, v in row.items()})
        report = {
            'metadata': {
                'title': 'JalDrishti Water Quality Report',
                'scope': params.get('scope', 'all'),
                'scope_value': params.get('scope_value', 'all'),
                'start_year': params.get('start_year'),
                'end_year': params.get('end_year'),
                'generated_at': datetime.now().isoformat(),
                'total_records': len(clean),
                'disclaimer': 'For research/demonstration purposes. CPCB/CWC data. ISRO SAC · SRTD/RTMG/MISA.'
            },
            'data': clean
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)

    def _generate_pdf(self, data_df, params, filepath):
        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            rightMargin=20*mm, leftMargin=20*mm,
            topMargin=20*mm, bottomMargin=20*mm
        )
        styles = getSampleStyleSheet()

        def style(name, **kw):
            return ParagraphStyle(name, parent=styles['Normal'], **kw)

        title_s   = style('T', fontSize=22, spaceAfter=4, textColor=colors.HexColor('#1a1a2e'), fontName='Helvetica-Bold')
        sub_s     = style('S', fontSize=11, spaceAfter=16, textColor=colors.HexColor('#4a4a6a'))
        head_s    = style('H', fontSize=13, spaceBefore=14, spaceAfter=7, textColor=colors.HexColor('#2255CC'), fontName='Helvetica-Bold')
        body_s    = style('B', fontSize=9, leading=14, textColor=colors.HexColor('#333333'))
        disc_s    = style('D', fontSize=7, textColor=colors.HexColor('#888888'), fontName='Helvetica-Oblique', leading=10)

        els = []

        # Title page
        els += [
            Spacer(1, 50),
            Paragraph("JalDrishti", title_s),
            Paragraph("Water Quality Intelligence Platform — ISRO SAC", sub_s),
            HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2255CC'), spaceAfter=18),
            Paragraph(f"<b>Scope:</b> {params.get('scope','').title()} — {params.get('scope_value','All')}", body_s),
            Paragraph(f"<b>Period:</b> {params.get('start_year','All')} – {params.get('end_year','All')}", body_s),
            Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%d %B %Y, %H:%M IST')}", body_s),
            Paragraph(f"<b>Records:</b> {len(data_df):,}", body_s),
            Spacer(1, 24),
            Paragraph("For research/demonstration purposes. Data sourced from CPCB/CWC monitoring network. "
                      "ISRO Space Applications Centre · SRTD/RTMG/MISA Division · Ahmedabad.", disc_s),
            PageBreak(),
        ]

        # Parameter summary table
        els.append(Paragraph("Parameter Summary", head_s))
        pcols = [c for c in ['DO','BOD','pH','Turbidity','Fecal_Coliform','EC','TDS','WQI'] if c in data_df.columns]
        tdata = [['Parameter','Mean','Median','Min','Max','Std']]
        for col in pcols:
            s = data_df[col].dropna()
            if len(s):
                tdata.append([col, f"{s.mean():.2f}", f"{s.median():.2f}", f"{s.min():.2f}", f"{s.max():.2f}", f"{s.std():.2f}"])
        if len(tdata) > 1:
            t = Table(tdata, colWidths=[85,65,65,65,65,65])
            t.setStyle(self._table_style(colors.HexColor('#2255CC')))
            els.append(t)

        els.append(Spacer(1, 18))

        # WQI breakdown
        els.append(Paragraph("WQI Classification Breakdown", head_s))
        if 'WQI' in data_df.columns:
            from services.wqi_calculator import classify_wqi
            counts = data_df['WQI'].apply(classify_wqi).value_counts()
            total = len(data_df)
            wd = [['Class','Count','%']]
            for cls in ['Excellent','Good','Moderate','Poor','Critical']:
                n = counts.get(cls, 0)
                wd.append([cls, str(n), f"{n/total*100:.1f}%" if total else '0%'])
            t = Table(wd, colWidths=[120,100,100])
            t.setStyle(self._table_style(colors.HexColor('#2255CC')))
            els.append(t)

        els.append(Spacer(1, 18))

        # Safety distribution
        els.append(Paragraph("Safety Distribution", head_s))
        if 'Safety' in data_df.columns:
            sc = data_df['Safety'].value_counts()
            total = len(data_df)
            sd = [['Status','Count','%']]
            for st in ['Safe','Unsafe']:
                n = int(sc.get(st, 0))
                sd.append([st, str(n), f"{n/total*100:.1f}%" if total else '0%'])
            t = Table(sd, colWidths=[120,100,100])
            t.setStyle(self._table_style(colors.HexColor('#C8960C')))
            els.append(t)

        els.append(Spacer(1, 18))

        # CPCB compliance
        els.append(Paragraph("CPCB Compliance Assessment", head_s))
        standards = {
            'DO':            ('≥ 6.0 mg/L',     lambda v: v >= 6),
            'BOD':           ('≤ 3.0 mg/L',     lambda v: v <= 3),
            'pH':            ('6.5–8.5',         lambda v: 6.5 <= v <= 8.5),
            'Fecal_Coliform':('≤ 500 MPN/100mL', lambda v: v <= 500),
            'Turbidity':     ('≤ 10 NTU',        lambda v: v <= 10),
        }
        cd = [['Parameter','CPCB Standard','Dataset Avg','Compliance']]
        for param, (std, chk) in standards.items():
            if param in data_df.columns:
                avg = data_df[param].mean()
                if pd.notna(avg):
                    cd.append([param, std, f"{avg:.2f}", '✓ PASS' if chk(avg) else '✗ FAIL'])
        if len(cd) > 1:
            t = Table(cd, colWidths=[100,110,80,80])
            t.setStyle(self._table_style(colors.HexColor('#1a1a2e')))
            els.append(t)

        doc.build(els)

    def _table_style(self, header_color):
        return TableStyle([
            ('BACKGROUND',   (0,0), (-1,0),  header_color),
            ('TEXTCOLOR',    (0,0), (-1,0),  colors.white),
            ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',     (0,0), (-1,-1), 8),
            ('ALIGN',        (1,0), (-1,-1), 'CENTER'),
            ('GRID',         (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('TOPPADDING',   (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ])


report_generator = ReportGenerator()
