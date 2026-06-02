"""
Endpoint de prédiction de mortalité à 1 an — SVM Linéaire entraîné sur données plateforme
"""
import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from patients.models import Patient
from .views import (
    get_model_path,
    get_features_path,
    load_feature_metadata,
    ensure_trained_models,
    MODEL_DIRECTORY,
)
from .models.feature_mapping import extract_features_for_patient as svm_extract_features

LAST_MORTALITE_CACHE = MODEL_DIRECTORY / 'last_mortalite.json'
PATIENT_PREDICTIONS_CACHE = MODEL_DIRECTORY / 'patient_predictions.json'


def _save_last_prediction(payload: dict):
    """Persiste la prédiction : globale (last) + par patient.
    Sauvegarde uniquement les champs légers (pas feature_values pour éviter les types non-sérialisables)."""
    KEEP_KEYS = {
        'success', 'patient_id', 'patient_id_plateforme', 'patient_name',
        'probabilite_deces', 'score_risque', 'niveau_risque', 'risque_relatif',
        'seuil_youden', 'seuil_spec90', 'recommendation', 'features_missing',
        'auc_cv', 'model_version', 'factors',
    }
    try:
        slim = {k: v for k, v in payload.items() if k in KEEP_KEYS}
        slim['cached_at'] = datetime.utcnow().isoformat()
        data = json.dumps(slim, ensure_ascii=False)
        # Dernière globale
        LAST_MORTALITE_CACHE.write_text(data, encoding='utf-8')
        # Par patient
        store = {}
        if PATIENT_PREDICTIONS_CACHE.exists():
            try:
                store = json.loads(PATIENT_PREDICTIONS_CACHE.read_text(encoding='utf-8'))
            except Exception:
                store = {}
        store[str(slim.get('patient_id', ''))] = slim
        PATIENT_PREDICTIONS_CACHE.write_text(json.dumps(store, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def _build_svm_factors(pipeline, feature_keys):
    """Extrait les top-5 facteurs depuis un CalibratedClassifierCV wrappant un Pipeline (imputer→transformer→clf)."""
    coef_list = []

    if hasattr(pipeline, 'calibrated_classifiers_'):
        for cal in pipeline.calibrated_classifiers_:
            base = getattr(cal, 'estimator', None)
            if base is None:
                continue
            clf = base.named_steps.get('clf') if hasattr(base, 'named_steps') else None
            if clf is not None and hasattr(clf, 'coef_'):
                c = clf.coef_
                coef_list.append(c[0] if c.ndim > 1 else c)
    elif hasattr(pipeline, 'named_steps'):
        clf = pipeline.named_steps.get('clf')
        if clf is not None and hasattr(clf, 'coef_'):
            c = clf.coef_
            coef_list.append(c[0] if c.ndim > 1 else c)

    if not coef_list or len(coef_list[0]) != len(feature_keys):
        return []

    weights = np.mean(coef_list, axis=0)
    factors = sorted(
        [{'label': k, 'weight': round(float(w), 4)} for k, w in zip(feature_keys, weights)],
        key=lambda x: abs(x['weight']),
        reverse=True,
    )
    return factors[:5]


class PredictMortalitePatientView(APIView):
    """
    GET /predictions/patient/<patient_id>/mortalite/

    Prédiction SVM Linéaire de mortalité à 1 an pour un patient.
    Utilise mortalite_svm.joblib avec les features de la plateforme.
    """

    def post(self, request, patient_id):
        """
        POST /predictions/patient/<patient_id>/mortalite/
        Body: { "features": { "albumine_basale": 42, "diabete": 1, ... } }
        Simulation : valeurs envoyées remplacent celles de la base.
        """
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            return Response({"error": f"Patient {patient_id} non trouvé"}, status=status.HTTP_404_NOT_FOUND)

        model_path = get_model_path('mortalite', 'svm')
        features_path = get_features_path('mortalite', 'svm')
        if not model_path.exists():
            trained, error = ensure_trained_models('mortalite', None)
            if not trained:
                return Response({"error": error or "Modèle SVM non disponible."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if features_path.exists():
            metadata = joblib.load(features_path)
            if not isinstance(metadata, dict):
                metadata = {'feature_keys': metadata, 'threshold': 0.368}
        else:
            metadata = {'feature_keys': [], 'threshold': 0.368}
        feature_keys = metadata.get('feature_keys', [])
        threshold    = metadata.get('threshold', 0.368)
        auc_value    = metadata.get('metrics', {}).get('auc', metadata.get('auc_roc', 0.0))

        if not feature_keys:
            return Response({"error": "Métadonnées du modèle introuvables."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            pipeline = joblib.load(model_path)
        except Exception as e:
            return Response({"error": f"Erreur chargement modèle: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Valeurs de base du patient + override par les valeurs envoyées
        raw_feat = svm_extract_features(patient)
        override = request.data.get('features', {})
        for k, v in override.items():
            if v is not None and v != '':
                try:
                    raw_feat[k] = float(v)
                except (ValueError, TypeError):
                    pass

        row = {k: (v if v is not None else np.nan) for k, v in raw_feat.items()}
        missing_count = sum(1 for v in row.values() if isinstance(v, float) and np.isnan(v))
        input_df = pd.DataFrame([row], columns=feature_keys)

        try:
            proba = float(pipeline.predict_proba(input_df)[:, 1][0])
        except Exception as e:
            return Response({"error": f"Erreur de prédiction: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        score = round(proba * 100, 1)
        base_rate = 0.199
        risque_relatif = round(proba / base_rate, 1) if base_rate > 0 else None

        # ── Calibration isotonique ──────────────────────────────────────────
        iso_path = MODEL_DIRECTORY / 'iso_calibrator.joblib'
        proba_calibrated = proba
        if iso_path.exists():
            try:
                iso = joblib.load(iso_path)
                proba_calibrated = float(iso.predict([proba])[0])
            except Exception:
                proba_calibrated = proba

        # Zones cliniques sur probabilité calibrée (seuils 10% / 40%)
        if proba_calibrated < 0.10:
            niveau = 'Faible'
        elif proba_calibrated < 0.40:
            niveau = 'Modéré'
        else:
            niveau = 'Élevé'

        factors = _build_svm_factors(pipeline, feature_keys)

        feature_values = []
        for k in feature_keys:
            v = raw_feat.get(k)
            is_missing = v is None or (isinstance(v, float) and np.isnan(v))
            feature_values.append({'key': k, 'value': None if is_missing else (round(float(v), 3) if isinstance(v, float) else v), 'missing': is_missing})

        return Response({
            "success": True,
            "simulation": True,
            "patient_id": patient_id,
            "probabilite_deces": round(proba, 4),
            "score_risque": score,
            "niveau_risque": niveau,
            "risque_relatif": risque_relatif,
            "seuil_youden": round(t_youden, 3),
            "seuil_spec90": round(t_spec90, 3),
            "features_missing": missing_count,
            "feature_values": feature_values,
            "factors": factors,
            "auc_cv": round(auc_value, 4) if auc_value else 0.0,
        })

    def get(self, request, patient_id):
        # ── Charger le patient ──────────────────────────────────────────────
        try:
            patient = Patient.objects.get(pk=patient_id)
        except Patient.DoesNotExist:
            return Response(
                {"error": f"Patient {patient_id} non trouvé"},
                status=status.HTTP_404_NOT_FOUND
            )

        # ── Charger le modèle SVM ───────────────────────────────────────────
        model_path = get_model_path('mortalite', 'svm')
        features_path = get_features_path('mortalite', 'svm')

        if not model_path.exists():
            trained, error = ensure_trained_models('mortalite', None)
            if not trained:
                return Response(
                    {"error": error or "Modèle SVM non disponible. Lancez d'abord l'entraînement."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

        if features_path.exists():
            metadata = joblib.load(features_path)
            if not isinstance(metadata, dict):
                metadata = {'feature_keys': metadata, 'threshold': 0.368}
        else:
            metadata = {'feature_keys': [], 'threshold': 0.368}
        feature_keys = metadata.get('feature_keys', [])
        threshold = metadata.get('threshold', 0.368)
        auc_value = metadata.get('metrics', {}).get('auc', metadata.get('auc_roc', 0.0))

        if not feature_keys:
            return Response(
                {"error": "Métadonnées du modèle SVM introuvables."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        try:
            pipeline = joblib.load(model_path)
        except Exception as e:
            return Response(
                {"error": f"Erreur chargement modèle: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # ── Extraire les 32 features SVM via le mapping ML→plateforme ──────
        raw_feat = svm_extract_features(patient)
        row = {k: (v if v is not None else np.nan) for k, v in raw_feat.items()}
        missing_count = sum(1 for v in row.values() if isinstance(v, float) and np.isnan(v))
        input_df = pd.DataFrame([row], columns=feature_keys)

        # ── Prédiction ──────────────────────────────────────────────────────
        try:
            proba = float(pipeline.predict_proba(input_df)[:, 1][0])
        except Exception as e:
            return Response(
                {"error": f"Erreur de prédiction: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        score = round(proba * 100, 1)
        base_rate = 0.199
        risque_relatif = round(proba / base_rate, 1) if base_rate > 0 else None

        # ── Calibration isotonique ──────────────────────────────────────────
        iso_path = MODEL_DIRECTORY / 'iso_calibrator.joblib'
        proba_calibrated = proba
        if iso_path.exists():
            try:
                iso = joblib.load(iso_path)
                proba_calibrated = float(iso.predict([proba])[0])
            except Exception:
                proba_calibrated = proba

        # Zones cliniques sur probabilité calibrée (seuils 10% / 40%)
        mort_rates = metadata.get('iso_mortality_rates', {'Faible': 5.1, 'Modéré': 29.1, 'Élevé': 55.6})
        if proba_calibrated < 0.10:
            niveau = 'Faible'
            recommendation = f"Zone Faible — mortalité observée : {mort_rates.get('Faible', 5.1)} % (cohorte HD-478). Le modèle ne détecte pas de signal de risque élevé. Suivi standard recommandé."
        elif proba_calibrated < 0.40:
            niveau = 'Modéré'
            recommendation = f"Zone Modérée — mortalité observée : {mort_rates.get('Modéré', 29.1)} % (cohorte HD-478). Signal de risque intermédiaire détecté. Surveillance renforcée et réévaluation clinique recommandées."
        else:
            niveau = 'Élevé'
            recommendation = f"Zone Élevée — mortalité observée : {mort_rates.get('Élevé', 55.6)} % (cohorte HD-478). Risque majeur détecté. Prise en charge prioritaire et discussion multidisciplinaire urgente."

        factors = _build_svm_factors(pipeline, feature_keys)

        # Liste ordonnée des valeurs de features pour affichage
        feature_values = []
        for k in feature_keys:
            v = raw_feat.get(k)
            is_missing = v is None or (isinstance(v, float) and np.isnan(v))
            feature_values.append({
                'key': k,
                'value': None if is_missing else (round(float(v), 3) if isinstance(v, float) else v),
                'missing': is_missing,
            })

        result = {
            "success": True,
            "patient_id": patient_id,
            "patient_id_plateforme": patient.id_patient or f"PAT-{patient.pk:06d}",
            "patient_name": f"{patient.prenom or ''} {patient.nom or ''}".strip(),
            "probabilite_deces": round(proba, 4),
            "probabilite_calibree": round(proba_calibrated, 4),
            "score_risque": score,
            "niveau_risque": niveau,
            "risque_relatif": risque_relatif,
            "seuil_faible_modere": 0.10,
            "seuil_modere_eleve": 0.40,
            "recommendation": recommendation,
            "features_missing": missing_count,
            "feature_values": feature_values,
            "factors": factors,
            "model_version": "SVM Linéaire v1",
            "auc_cv": round(auc_value, 4) if auc_value else 0.0,
        }
        _save_last_prediction(result)
        return Response(result, status=status.HTTP_200_OK)


class LatestMortaliteView(APIView):
    """
    GET /predictions/latest-mortalite/
    Retourne la dernière prédiction mortalité exécutée dans le système.
    """
    def get(self, request):
        if not LAST_MORTALITE_CACHE.exists():
            return Response({"detail": "Aucune prédiction disponible."}, status=status.HTTP_404_NOT_FOUND)
        try:
            data = json.loads(LAST_MORTALITE_CACHE.read_text(encoding='utf-8'))
            return Response(data, status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Erreur lecture cache."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StoredPatientMortaliteView(APIView):
    """
    GET /predictions/stored-mortalite/<patient_id>/
    Retourne la prédiction mortalité déjà lancée pour ce patient (sans relancer le modèle).
    404 si aucune prédiction n'a encore été lancée pour ce patient.
    """
    def get(self, request, patient_id):
        if not PATIENT_PREDICTIONS_CACHE.exists():
            return Response({"detail": "Aucune prédiction disponible."}, status=status.HTTP_404_NOT_FOUND)
        try:
            store = json.loads(PATIENT_PREDICTIONS_CACHE.read_text(encoding='utf-8'))
            data = store.get(str(patient_id))
            if not data:
                return Response({"detail": "Aucune prédiction pour ce patient."}, status=status.HTTP_404_NOT_FOUND)
            return Response(data, status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Erreur lecture cache."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
