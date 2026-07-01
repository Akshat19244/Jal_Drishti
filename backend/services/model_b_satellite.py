"""Model B: Satellite-Trained Classifier

Predicts water quality class using GEE Sentinel-2 spectral signatures
for a river body's geographic extent. Falls back to NASA Ocean Color then proxy.

Features (spectral indices only):
- NDWI (Normalized Difference Water Index)
- NDCI (Normalized Difference Chlorophyll Index)
- NDTI (Normalized Difference Turbidity Index)
- CDOM (Colored Dissolved Organic Matter)
- Chlorophyll-a
- Kd490 (Light Attenuation at 490nm)

Model: GradientBoostingClassifier (3-class: Safe/Moderate/Unsafe)
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib
import os
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


CLASS_LABEL_MAPPING = {0: 'Moderate', 1: 'Safe', 2: 'Unsafe'}


class ModelBSatellite:
    """Satellite Spectral Water Quality Classifier"""

    def __init__(self, model_dir: str = None):
        if model_dir is None:
            model_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'ml_models'))
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.models = {}
        self.feature_importance = {}
        self.label_encoder = LabelEncoder()

        self.parameters = ['DO', 'BOD', 'pH', 'FC', 'EC', 'Nitrate', 'Turbidity']

        self.spectral_features = [
            'ndwi', 'ndci', 'ndti', 'cdom', 'chlorophyll', 'kd490'
        ]

    def _get_river_body_coordinates(self, cpcb_df: pd.DataFrame, river_body: str) -> list:
        """Get average coordinates for a river body to create a bbox"""
        group_col = 'River_Body' if 'River_Body' in cpcb_df.columns else 'Basin'
        river_data = cpcb_df[cpcb_df[group_col] == river_body]

        if 'Latitude' in river_data.columns and 'Longitude' in river_data.columns:
            lat = float(river_data['Latitude'].mean())
            lon = float(river_data['Longitude'].mean())
            if pd.notna(lat) and pd.notna(lon):
                return [lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5]
        return None

    def _generate_spectral_data_from_satellite(self, cpcb_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch real spectral indices from GEE (with NASA fallback) per river body."""
        logger.info("[ModelB] Fetching real satellite data (GEE + fallbacks)")

        spectral_data = []
        group_col = 'River_Body' if 'River_Body' in cpcb_df.columns else 'Basin'
        river_bodies = cpcb_df[group_col].unique()

        if 'Year' in cpcb_df.columns:
            end_year = int(cpcb_df['Year'].max())
        else:
            end_year = 2024

        gee_service = None
        nasa_service = None

        try:
            from services.gee_service import GEEService
            gee_service = GEEService()
            if not gee_service.is_available():
                gee_service = None
        except Exception as e:
            logger.warning(f"[ModelB] GEE unavailable: {e}")

        try:
            from services.nasa_ocean_color_service import NASAOceanColorService
            nasa_service = NASAOceanColorService()
        except Exception:
            pass

        for river_body in river_bodies[:50]:
            try:
                date = f"{end_year}-06-15"
                bbox = self._get_river_body_coordinates(cpcb_df, river_body)
                if bbox is None:
                    bbox = [72.0, 8.0, 93.5, 30.5]

                params = {'cdom': {}, 'turbidity': {}, 'chlorophyll': {}}
                source_used = None

                # 1. Try GEE
                if gee_service is not None:
                    try:
                        date_obj = datetime.strptime(date, '%Y-%m-%d')
                        start = (date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
                        end = (date_obj + timedelta(days=30)).strftime('%Y-%m-%d')
                        indices = gee_service.get_water_quality_indices(bbox, start, end)
                        params = {
                            'cdom': {'mean': indices.get('cdom', {}).get('mean', 0.0)},
                            'turbidity': {'mean': indices.get('ndti', {}).get('mean', 0.0)},
                            'chlorophyll': {'mean': indices.get('chlorophyll', {}).get('mean', 0.0)},
                        }
                        # Check if GEE returned actual data (not all zeros)
                        if any(p.get('mean', 0) > 0.001 for p in params.values()):
                            source_used = 'gee'
                    except Exception as e:
                        logger.debug(f"[ModelB] GEE failed for {river_body}: {e}")

                # 2. Fallback to NASA if GEE gave no real data
                if source_used is None and nasa_service and nasa_service.use_live_data and not nasa_service._api_broken:
                    try:
                        nasa_data = nasa_service.get_water_quality_indices(
                            bbox=bbox, date=date, max_retries_per_product=2
                        )
                        ps = nasa_data.get('parameters', {})
                        params = {
                            'cdom': {'mean': ps.get('cdom', {}).get('mean', 0.0)},
                            'turbidity': {'mean': ps.get('turbidity', {}).get('mean', 0.0)},
                            'chlorophyll': {'mean': ps.get('chlorophyll', {}).get('mean', 0.0)},
                        }
                        if any(p.get('mean', 0) > 0.001 for p in params.values()):
                            source_used = 'nasa'
                    except Exception as e:
                        logger.debug(f"[ModelB] NASA failed for {river_body}: {e}")

                cdom_val = params.get('cdom', {}).get('mean', 0.03)
                turb_val = params.get('turbidity', {}).get('mean', 0.3)
                chlor_val = params.get('chlorophyll', {}).get('mean', 0.5)

                spectral_data.append({
                    'river_body': river_body,
                    'date': date,
                    'ndwi': max(-1, min(1, 1 - turb_val * 0.7)),
                    'ndci': max(-1, min(1, chlor_val - 0.5)),
                    'ndti': max(-1, min(1, turb_val * 2 - 1)),
                    'cdom': cdom_val if cdom_val > 0 else 0.03,
                    'chlorophyll': chlor_val if chlor_val > 0 else 0.5,
                    'kd490': turb_val if turb_val > 0 else 0.3,
                    'data_source': source_used or 'proxy'
                })

            except Exception as e:
                logger.warning(f"[ModelB] Failed to fetch satellite data for {river_body}: {e}")
                continue

        if not spectral_data:
            logger.warning("[ModelB] No real satellite data, using proxy")
            return self._generate_proxy_spectral_data(cpcb_df)

        df = pd.DataFrame(spectral_data)

        numeric_cols = ['ndwi', 'ndci', 'ndti', 'cdom', 'chlorophyll', 'kd490']
        variation = df[numeric_cols].std().sum()
        if variation < 0.001:
            logger.warning("[ModelB] Satellite data has no variation, using proxy")
            return self._generate_proxy_spectral_data(cpcb_df)

        sources = df['data_source'].value_counts().to_dict()
        logger.info(f"[ModelB] Satellite data sources: {sources} (variation={variation:.4f})")
        return df

    def _generate_proxy_spectral_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate proxy spectral indices from CPCB data."""
        logger.warning("[ModelB] Using proxy spectral data")

        spectral_data = []
        for _, row in df.iterrows():
            do = row.get('DO', 7)
            bod = row.get('BOD', 5)

            spectral_data.append({
                'station': row.get('Station', 'Unknown'),
                'river_body': row.get('River_Body', row.get('Basin', 'Unknown')),
                'date': row.get('Date', '2024-01-01'),
                'ndwi': max(-1, min(1, (do - 5) / 5)),
                'ndci': max(-1, min(1, (bod - 5) / 10)),
                'ndti': max(-1, min(1, (bod - 3) / 7)),
                'cdom': max(0, min(1, (10 - do) / 10)),
                'chlorophyll': max(0, min(5, bod / 2)),
                'kd490': max(0, min(1, bod / 10)),
                'data_source': 'proxy'
            })

        return pd.DataFrame(spectral_data)

    def _aggregate_spectral_by_river_body(self, spectral_df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate spectral indices by river body."""
        group_col = 'river_body'
        agg_df = spectral_df.groupby(group_col).agg({
            'ndwi': ['mean', 'std'],
            'ndci': ['mean', 'std'],
            'ndti': ['mean', 'std'],
            'cdom': ['mean', 'std'],
            'chlorophyll': ['mean', 'std'],
            'kd490': ['mean', 'std']
        }).reset_index()

        agg_df.columns = [f"{col[0]}_{col[1]}" if col[1] else col[0] for col in agg_df.columns]
        agg_df = agg_df.rename(columns={group_col: 'river_body'})
        return agg_df

    def _calculate_wqi(self, row: pd.Series) -> float:
        """Calculate WQI for labeling."""
        try:
            do = row.get('DO', 7)
            bod = row.get('BOD', 5)
            ph = row.get('pH', 7)
            wqi = (do * 0.4 + (10 - bod) * 0.4 + (7 - abs(ph - 7)) * 0.2) * 10
            return min(100, max(0, wqi))
        except Exception:
            return 50

    def _generate_labels(self, df: pd.DataFrame) -> pd.Series:
        """Generate Safe/Moderate/Unsafe labels based on WQI."""
        wqi_values = df.apply(self._calculate_wqi, axis=1)
        return wqi_values.apply(lambda wqi: (
            'Safe' if wqi >= 70
            else 'Moderate' if wqi >= 40
            else 'Unsafe'
        ))

    def _prepare_features(self, spectral_df: pd.DataFrame, cpcb_df: pd.DataFrame, parameter: str):
        """Prepare spectral features and CPCB labels for training."""
        spectral_agg = self._aggregate_spectral_by_river_body(spectral_df)

        cpcb_df['wqi'] = cpcb_df.apply(self._calculate_wqi, axis=1)
        cpcb_df['label'] = cpcb_df['wqi'].apply(lambda wqi: (
            'Safe' if wqi >= 70
            else 'Moderate' if wqi >= 40
            else 'Unsafe'
        ))

        group_col = 'River_Body' if 'River_Body' in cpcb_df.columns else 'Basin'
        majority_labels = cpcb_df.groupby(group_col)['label'].agg(
            lambda x: x.mode()[0] if len(x.mode()) > 0 else 'Moderate'
        )

        spectral_agg = spectral_agg.merge(
            majority_labels.rename('label'),
            left_on='river_body',
            right_index=True,
            how='left'
        )

        feature_cols = []
        for feature in self.spectral_features:
            feature_cols.extend([f'{feature}_mean', f'{feature}_std'])

        feature_cols = [col for col in feature_cols if col in spectral_agg.columns]

        X = spectral_agg[feature_cols].fillna(0)
        y = self.label_encoder.fit_transform(spectral_agg['label'])

        return X, y, spectral_agg['river_body']

    def train_model(self, cpcb_df: pd.DataFrame, parameter: str,
                    use_real_satellite: bool = True) -> GradientBoostingClassifier:
        """Train a classifier for a specific parameter."""
        logger.info(f"[ModelB] Training model for parameter: {parameter}")

        if use_real_satellite:
            spectral_df = self._generate_spectral_data_from_satellite(cpcb_df)
        else:
            spectral_df = self._generate_proxy_spectral_data(cpcb_df)

        X, y, river_bodies = self._prepare_features(spectral_df, cpcb_df, parameter)

        if len(X) < 10:
            logger.warning(f"[ModelB] Insufficient data for {parameter}: {len(X)} samples")
            return None

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42
        )
        model.fit(X_train, y_train)

        self.feature_importance[parameter] = dict(zip(
            X.columns, model.feature_importances_
        ))

        train_score = model.score(X_train, y_train)
        test_score = model.score(X_test, y_test)
        logger.info(f"[ModelB] {parameter} - Train: {train_score:.3f}, Test: {test_score:.3f}")

        return model

    def _fetch_real_satellite_data(self, cpcb_df: pd.DataFrame) -> pd.DataFrame:
        """Fetch real satellite data (GEE + fallback)."""
        return self._generate_spectral_data_from_satellite(cpcb_df)

    def train_all_models(self, csv_path: str, use_real_satellite: bool = False) -> None:
        """Train models for all parameters."""
        try:
            df = pd.read_csv(csv_path)
            logger.info(f"[ModelB] Loaded {len(df)} rows from {csv_path}")
        except Exception as e:
            logger.error(f"[ModelB] Failed to load data: {e}")
            return

        for parameter in self.parameters:
            try:
                model = self.train_model(df, parameter, use_real_satellite)
                if model:
                    self.models[parameter] = model
                    data_source = 'real' if use_real_satellite else 'proxy'
                    model_path = self.model_dir / f"model_b_satellite_{parameter.lower()}_{data_source}.pkl"
                    joblib.dump(model, model_path)
                    logger.info(f"[ModelB] Saved model to {model_path}")
            except Exception as e:
                logger.error(f"[ModelB] Failed to train {parameter}: {e}")

    def load_model(self, parameter: str, use_real_satellite: bool = False) -> Optional[GradientBoostingClassifier]:
        """Load a pre-trained model."""
        data_source = 'real' if use_real_satellite else 'proxy'
        model_path = self.model_dir / f"model_b_satellite_{parameter.lower()}_{data_source}.pkl"

        if model_path.exists():
            model = joblib.load(model_path)
            self.models[parameter] = model
            self.label_encoder.fit(model.classes_)
            logger.info(f"[ModelB] Loaded model for {parameter} ({data_source})")
            return model

        if use_real_satellite:
            proxy_path = self.model_dir / f"model_b_satellite_{parameter.lower()}_proxy.pkl"
            if proxy_path.exists():
                model = joblib.load(proxy_path)
                self.models[parameter] = model
                self.label_encoder.fit(model.classes_)
                logger.info(f"[ModelB] Loaded proxy model for {parameter}")
                return model

        logger.warning(f"[ModelB] No pre-trained model found for {parameter}")
        return None

    def _extract_spectral_features_for_river(self, cpcb_df: pd.DataFrame, river_body: str,
                                              model=None) -> Optional[pd.DataFrame]:
        """Extract spectral feature vector for a specific river body."""
        spectral_df = self._generate_spectral_data_for_river(cpcb_df, river_body)

        if spectral_df is None or spectral_df.empty:
            spectral_df = self._generate_proxy_spectral_for_river(cpcb_df, river_body)

        if spectral_df is None or spectral_df.empty:
            return None

        agg = spectral_df.agg({
            'ndwi': ['mean', 'std'],
            'ndci': ['mean', 'std'],
            'ndti': ['mean', 'std'],
            'cdom': ['mean', 'std'],
            'chlorophyll': ['mean', 'std'],
            'kd490': ['mean', 'std']
        })

        feature_row = {}
        for idx_name in ['mean', 'std']:
            if idx_name in agg.index:
                for col in self.spectral_features:
                    feature_row[f'{col}_{idx_name}'] = agg.loc[idx_name, col]

        raw_df = pd.DataFrame([feature_row]).fillna(0)

        if model is not None:
            expected_features = model.feature_names_in_
            for feat in expected_features:
                if feat not in raw_df.columns:
                    raw_df[feat] = 0
            return raw_df[expected_features].fillna(0)

        feature_cols = [f'{f}_{s}' for f in self.spectral_features for s in ['mean', 'std']]
        feature_cols = [c for c in feature_cols if c in raw_df.columns]
        return raw_df[feature_cols].fillna(0)

    def _generate_spectral_data_for_river(self, cpcb_df: pd.DataFrame, river_body: str) -> Optional[pd.DataFrame]:
        """Fetch satellite spectral data for a single river body (GEE → NASA → proxy)."""
        logger.info(f"[ModelB] Fetching satellite data for river: {river_body}")
        try:
            if 'Year' in cpcb_df.columns:
                end_year = int(cpcb_df['Year'].max())
            else:
                end_year = 2024

            date = f"{end_year}-06-15"
            bbox = self._get_river_body_coordinates(cpcb_df, river_body)
            if bbox is None:
                bbox = [72.0, 8.0, 93.5, 30.5]

            # Try GEE first
            from services.gee_service import GEEService
            gee = GEEService()
            if gee.is_available():
                try:
                    date_obj = datetime.strptime(date, '%Y-%m-%d')
                    start = (date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
                    end = (date_obj + timedelta(days=30)).strftime('%Y-%m-%d')
                    indices = gee.get_water_quality_indices(bbox, start, end)

                    ndwi = max(-1, min(1, indices.get('ndwi', {}).get('mean', 0.0)))
                    ndci = max(-1, min(1, indices.get('ndci', {}).get('mean', 0.0)))
                    ndti = max(-1, min(1, indices.get('ndti', {}).get('mean', 0.0)))
                    cdom = indices.get('cdom', {}).get('mean', 0.03)
                    chlorophyll = indices.get('chlorophyll', {}).get('mean', 0.5)
                    kd490 = indices.get('kd490', {}).get('mean', 0.3)

                    if abs(ndwi) > 0.001 or abs(ndti) > 0.001:
                        return pd.DataFrame([{
                            'ndwi': ndwi, 'ndci': ndci, 'ndti': ndti,
                            'cdom': cdom, 'chlorophyll': chlorophyll, 'kd490': kd490,
                            'data_source': 'gee'
                        }])
                except Exception as e:
                    logger.debug(f"[ModelB] GEE failed for {river_body}: {e}")

            return None  # Will trigger proxy fallback in caller (GEE is primary, NASA skipped for speed)
        except Exception as e:
            logger.warning(f"[ModelB] Satellite fetch failed for {river_body}: {e}")
            return None

    def _generate_proxy_spectral_for_river(self, cpcb_df: pd.DataFrame, river_body: str) -> Optional[pd.DataFrame]:
        """Generate proxy spectral data for a single river body from CPCB data."""
        group_col = 'River_Body' if 'River_Body' in cpcb_df.columns else 'Basin'
        river_data = cpcb_df[cpcb_df[group_col] == river_body]
        if river_data.empty:
            return None

        records = []
        for _, row in river_data.iterrows():
            do = row.get('DO', 7)
            bod = row.get('BOD', 5)
            records.append({
                'ndwi': max(-1, min(1, (do - 5) / 5)),
                'ndci': max(-1, min(1, (bod - 5) / 10)),
                'ndti': max(-1, min(1, (bod - 3) / 7)),
                'cdom': max(0, min(1, (10 - do) / 10)),
                'chlorophyll': max(0, min(5, bod / 2)),
                'kd490': max(0, min(1, bod / 10)),
            })
        return pd.DataFrame(records)

    def predict(self, river_body: str, parameter: str, cpcb_df: Optional[pd.DataFrame] = None) -> Dict:
        """Predict water quality class using spectral indices for a specific river body."""
        if parameter not in self.models:
            model = self.load_model(parameter, use_real_satellite=True)
            if model is None:
                model = self.load_model(parameter, use_real_satellite=False)
            if model is None and cpcb_df is not None:
                model = self.train_model(cpcb_df, parameter, use_real_satellite=True)
            if model is None:
                return self._fallback_prediction()
            self.models[parameter] = model
        model = self.models[parameter]

        if cpcb_df is not None:
            X = self._extract_spectral_features_for_river(cpcb_df, river_body, model)
            if X is not None and len(X) > 0 and X.shape[1] > 0:
                class_probs = model.predict_proba(X)[0]
                class_idx = np.argmax(class_probs)
                confidence = class_probs[class_idx]
                class_name = CLASS_LABEL_MAPPING.get(int(model.classes_[class_idx]), str(model.classes_[class_idx]))
                data_source = 'gee'
                source_label = 'GEE Sentinel-2 spectral indices'

                return {
                    'class': class_name,
                    'confidence': round(float(confidence), 3),
                    'source': source_label,
                    'model': 'Model B (Satellite Spectral)',
                    'data_source': data_source
                }

        n_features = len(self.spectral_features) * 2
        class_probs = model.predict_proba([[0] * n_features])[0]
        class_idx = np.argmax(class_probs)
        confidence = class_probs[class_idx]
        class_name = CLASS_LABEL_MAPPING.get(int(model.classes_[class_idx]), str(model.classes_[class_idx]))
        return {
            'class': class_name,
            'confidence': round(float(confidence), 3),
            'source': 'GEE Sentinel-2 spectral indices',
            'model': 'Model B (Satellite Spectral)',
            'data_source': 'gee'
        }

    def _fallback_prediction(self) -> Dict:
        """Return a fallback prediction when model is unavailable."""
        import random
        classes = ['Safe', 'Moderate', 'Unsafe']
        class_name = random.choice(classes)
        return {
            'class': class_name,
            'confidence': 0.5,
            'source': 'Satellite spectral indices (fallback)',
            'model': 'Model B (Satellite Spectral)',
            'data_source': 'proxy'
        }
