"""
Beach Water Quality Classification Service
Trains a RandomForestClassifier on india_beaches_merged.csv to classify
beach water as Safe/Unsafe for swimming using physico-chemical + satellite features.
Provides detailed, human-readable explanations for every prediction.
"""
import os
import json
import math
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, roc_auc_score
from sklearn.preprocessing import LabelEncoder
from datetime import datetime

FEATURE_COLS = [
    'pH', 'DO', 'BOD', 'COD', 'EC', 'Temperature', 'Turbidity',
    'Fecal_Coliform', 'Total_Coliform', 'Nitrate', 'TDS',
    'CDOM', 'Turbidity_Index', 'Chlorophyll_a', 'Kd490',
]

CPCB_LIMITS = {
    'pH':               {'safe': (6.5, 8.5),       'unit': '',           'label': 'pH Level'},
    'DO':               {'safe': (6.0, 999),       'unit': 'mg/L',       'label': 'Dissolved Oxygen'},
    'BOD':              {'safe': (0, 3.0),          'unit': 'mg/L',       'label': 'Biochemical Oxygen Demand'},
    'Fecal_Coliform':   {'safe': (0, 500),          'unit': 'MPN/100mL',  'label': 'Fecal Coliform'},
    'Turbidity':        {'safe': (0, 10),           'unit': 'NTU',        'label': 'Turbidity'},
    'EC':               {'safe': (0, 1500),         'unit': 'uS/cm',      'label': 'Electrical Conductivity'},
    'Nitrate':          {'safe': (0, 45),           'unit': 'mg/L',       'label': 'Nitrate'},
    'TDS':              {'safe': (0, 500),          'unit': 'mg/L',       'label': 'Total Dissolved Solids'},
}

PARAM_EXPLANATIONS = {
    'Fecal_Coliform': 'Fecal coliform bacteria indicates sewage contamination. High levels mean higher risk of waterborne diseases like gastroenteritis.',
    'BOD': 'BOD measures organic pollution. High BOD means decomposing organic matter consumes oxygen, harming aquatic life and indicating sewage/industrial waste.',
    'DO': 'Dissolved oxygen is essential for aquatic life. Low DO (<4 mg/L) creates hypoxic conditions harmful to fish and indicates pollution.',
    'pH': 'pH outside the neutral range (6.5-8.5) harms aquatic life and indicates pollution. Extreme pH suggests industrial discharge or acid deposition.',
    'Turbidity': 'Turbidity measures water cloudiness. High turbidity blocks sunlight, harms aquatic plants, and can carry pathogens.',
    'EC': 'Conductivity measures dissolved salts. High EC indicates saline intrusion or industrial discharge.',
    'Nitrate': 'High nitrates cause algal blooms (eutrophication) which deplete oxygen and release toxins.',
    'TDS': 'Total dissolved solids affect taste and safety. Very high TDS can indicate pollution or salinity.',
}


class BeachPredictService:
    _instance = None
    _model = None
    _features = None
    _label_encoder = None
    _station_data = None
    _feature_importance = None
    _metrics = None
    _csv_path = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is not None:
            return
        self._locate_csv()
        self._train_model()

    def _locate_csv(self):
        candidates = [
            os.path.normpath(r'C:\Users\aksha\Downloads\jaldrishti_fixed (1)\jaldrishti_fixed\india_beaches_merged.csv'),
            os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'india_beaches_merged.csv')),
            os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'india_beaches_merged.csv')),
        ]
        for p in candidates:
            if os.path.exists(p):
                self._csv_path = p
                return
        raise FileNotFoundError(f"india_beaches_merged.csv not found. Tried: {candidates}")

    def _train_model(self):
        print(f"[BeachPredict] Loading data from {self._csv_path}")
        df = pd.read_csv(self._csv_path, low_memory=False)

        df = df.dropna(subset=FEATURE_COLS + ['Safety'], how='any').copy()

        self._station_data = df.groupby('Station_Name').agg({
            'State': 'first', 'Latitude': 'mean', 'Longitude': 'mean',
            **{c: 'mean' for c in FEATURE_COLS},
            'Safety': lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Safe',
            'Year': lambda x: f"{int(x.min())}-{int(x.max())}" if x.notna().any() else 'N/A',
        }).reset_index()

        X = df[FEATURE_COLS].astype(float)
        le = LabelEncoder()
        y = le.fit_transform(df['Safety'])

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        model = RandomForestClassifier(
            n_estimators=300, max_depth=18, min_samples_split=5,
            min_samples_leaf=2, class_weight='balanced',
            random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1] if len(le.classes_) == 2 else model.predict_proba(X_test).max(axis=1)

        cv_scores = cross_val_score(model, X_train, y_train, cv=5)

        self._model = model
        self._features = X.columns.tolist()
        self._label_encoder = le

        importance = sorted(zip(self._features, model.feature_importances_), key=lambda x: -x[1])
        self._feature_importance = [{'feature': f, 'importance': round(v, 4)} for f, v in importance]

        self._metrics = {
            'accuracy': round(accuracy_score(y_test, y_pred), 3),
            'precision': round(precision_score(y_test, y_pred, pos_label=le.transform(['Safe'])[0] if 'Safe' in le.classes_ else 0), 3),
            'recall': round(recall_score(y_test, y_pred, pos_label=le.transform(['Safe'])[0] if 'Safe' in le.classes_ else 0), 3),
            'f1_score': round(f1_score(y_test, y_pred, pos_label=le.transform(['Safe'])[0] if 'Safe' in le.classes_ else 0), 3),
            'cv_mean': round(float(cv_scores.mean()), 3),
            'cv_std': round(float(cv_scores.std()), 3),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'safe_samples': int((y == 0).sum()),
            'unsafe_samples': int((y == 1).sum()) if len(le.classes_) == 2 else int((y == 1).sum()),
        }

        cm = confusion_matrix(y_test, y_pred)
        self._metrics['confusion_matrix'] = cm.tolist()
        self._metrics['confusion_labels'] = le.classes_.tolist()

        print(f"[BeachPredict] Model trained. Accuracy: {self._metrics['accuracy']:.1%}, "
              f"CV: {self._metrics['cv_mean']:.1%} +/- {self._metrics['cv_std']:.1%}")

    def get_stations(self):
        stations = []
        for _, row in self._station_data.iterrows():
            stations.append({
                'name': row['Station_Name'],
                'state': row['State'],
                'lat': self._safe_float(row['Latitude']),
                'lng': self._safe_float(row['Longitude']),
                'year_range': row['Year'],
            })
        return sorted(stations, key=lambda x: x['name'])

    def get_status(self):
        return {
            'model_ready': True,
            'stations': len(self._station_data),
            'features': self._features,
            'metrics': self._metrics,
            'top_features': self._feature_importance[:5],
            'classes': self._label_encoder.classes_.tolist() if self._label_encoder else [],
        }

    def predict(self, station_name):
        matches = self._station_data[self._station_data['Station_Name'].str.lower() == station_name.lower()]
        if matches.empty:
            return None

        station = matches.iloc[0]

        input_vec = {f: self._safe_float(station[f]) or 0.0 for f in FEATURE_COLS}
        X_input = pd.DataFrame([input_vec])[self._features]

        safe_idx = self._label_encoder.transform(['Safe'])[0] if 'Safe' in self._label_encoder.classes_ else 0
        probs = self._model.predict_proba(X_input)[0]
        pred_class_idx = self._model.predict(X_input)[0]
        pred_label = self._label_encoder.inverse_transform([pred_class_idx])[0]
        confidence = float(probs[pred_class_idx])
        safe_probability = float(probs[safe_idx]) if safe_idx < len(probs) else 0.0

        swimming_score = round(safe_probability * 100, 1)

        param_contributions = self._compute_param_contributions(input_vec, pred_label)
        top_contributors = sorted(param_contributions, key=lambda x: abs(x['impact_score']), reverse=True)[:3]

        return {
            'station_name': str(station['Station_Name']),
            'state': str(station['State']),
            'classification': pred_label,
            'confidence': round(confidence, 3),
            'swimming_suitability_score': swimming_score,
            'safe_probability': round(safe_probability, 3),
            'suitability_label': self._get_suitability_label(swimming_score),
            'suitability_color': self._get_suitability_color(swimming_score),
            'top_contributors': top_contributors,
            'parameter_breakdown': param_contributions,
            'feature_importance': self._feature_importance[:10],
            'interpretation': self._generate_interpretation(pred_label, swimming_score, top_contributors, input_vec),
            'station_summary': {
                'state': str(station['State']),
                'year_range': str(station['Year']),
            },
        }

    def _compute_param_contributions(self, input_vec, pred_label):
        results = []
        base_prob = self._model.predict_proba(pd.DataFrame([{f: 0.0 for f in self._features}]))[0]
        base_idx = 0 if pred_label == self._label_encoder.inverse_transform([0])[0] else 1

        for col in FEATURE_COLS:
            val = input_vec.get(col, 0.0)
            limits = CPCB_LIMITS.get(col, None)
            status = 'unknown'
            if limits:
                lo, hi = limits['safe']
                if lo <= val <= hi:
                    status = 'safe'
                elif val < lo:
                    status = 'low'
                else:
                    status = 'high'

            perturbed = {f: input_vec.get(f, 0.0) for f in self._features}
            perturbed[col] = 0.0
            prob_without = self._model.predict_proba(pd.DataFrame([perturbed]))[0][base_idx]
            impact = float(probs[base_idx] - prob_without) if (probs := self._model.predict_proba(pd.DataFrame([input_vec]))[0]) is not None else 0.0

            results.append({
                'parameter': col,
                'label': CPCB_LIMITS.get(col, {}).get('label', col),
                'value': self._safe_round(val, 2),
                'unit': CPCB_LIMITS.get(col, {}).get('unit', ''),
                'status': status,
                'impact_score': round(impact, 3),
                'explanation': PARAM_EXPLANATIONS.get(col, ''),
            })
        return results

    def _generate_interpretation(self, pred_label, score, top_contributors, input_vec):
        if pred_label == 'Safe':
            lines = [
                f"This beach is classified as SAFE for swimming with a suitability score of {score}/100.",
                "",
                "Key reasons for this classification:",
            ]
            for tc in top_contributors[:3]:
                val = input_vec.get(tc['parameter'], 0)
                lines.append(f"  - {tc['label']} at {self._safe_round(val, 2)} {tc.get('unit', '')} is within safe limits.")
            lines.append("")
            lines.append("The water quality meets CPCB bathing water standards. Swimming and other")
            lines.append("water contact activities are generally considered safe.")
        else:
            lines = [
                f"This beach is classified as UNSAFE for swimming with a suitability score of {score}/100.",
                "",
                "Key concerns identified:",
            ]
            for tc in top_contributors[:3]:
                val = input_vec.get(tc['parameter'], 0)
                limits = CPCB_LIMITS.get(tc['parameter'], {}).get('safe', ('N/A', 'N/A'))
                lines.append(f"  - {tc['label']} at {self._safe_round(val, 2)} {tc.get('unit', '')} exceeds the safe limit.")
                if tc['parameter'] in PARAM_EXPLANATIONS:
                    lines.append(f"    {PARAM_EXPLANATIONS[tc['parameter']]}")
            lines.append("")
            lines.append("Water contact activities are not recommended. Higher levels of pollutants")
            lines.append("increase health risks for swimmers. Further investigation recommended.")
        return "\n".join(lines)

    def _get_suitability_label(self, score):
        if score >= 80: return "Excellent"
        if score >= 60: return "Good"
        if score >= 40: return "Moderate"
        if score >= 20: return "Poor"
        return "Very Poor"

    def _get_suitability_color(self, score):
        if score >= 80: return "#16A34A"
        if score >= 60: return "#65A30D"
        if score >= 40: return "#D97706"
        if score >= 20: return "#EA580C"
        return "#DC2626"

    def _safe_float(self, v):
        if v is None:
            return None
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (ValueError, TypeError):
            return None

    def _safe_round(self, v, d=2):
        f = self._safe_float(v)
        if f is None:
            return None
        return round(f, d)

beach_predict_service = BeachPredictService()
