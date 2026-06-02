import os
import re
from datetime import date, datetime, timedelta

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('MKL_NUM_THREADS', '1')
import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    AdaBoostClassifier,
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.impute import KNNImputer, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    RandomizedSearchCV,
    RepeatedStratifiedKFold,
    StratifiedKFold,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import FunctionTransformer, Pipeline
from sklearn.preprocessing import OneHotEncoder, PowerTransformer, StandardScaler
from sklearn.svm import LinearSVC, SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils import resample

from patients.models import Patient

try:
    from predictions.models import PredictionLog
    PREDICTION_LOG_AVAILABLE = True
except ImportError:
    PREDICTION_LOG_AVAILABLE = False

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    from catboost import CatBoostClassifier
    CATBOOST_AVAILABLE = True
except ImportError:
    CATBOOST_AVAILABLE = False

try:
    from lightgbm import LGBMClassifier
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

MODEL_DIRECTORY = settings.BASE_DIR / 'predictions' / 'models'
MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)

# ── Toutes les features possibles reconnues par le système ───────────────────
# Ces clés correspondent exactement aux noms de champs envoyés par le frontend.
ALL_KNOWN_FEATURES = [
    # Démographie
    'age', 'sexe', 'demographie_age_ans', 'demographie_sexe',
    'demographie_statut_matrimonial', 'demographie_mode_vie',
    'demographie_zone_residence', 'demographie_distance_centre_km',
    'demographie_couverture_sociale', 'demographie_statut_professionnel',
    'demographie_niveau_education', 'demographie_tabagisme', 'demographie_alcool',
    # Comorbidités
    'comorbidite_statut_diabete', 'comorbidite_liste', 'comorbidite_autre',
    'comorbidite_exposition_toxique', 'comorbidite_antecedents_medicaments_nephrotoxiques',
    # Biologie
    'biologie_creatinine_mg_l', 'biologie_dfg_mdrd_ml_min_1_73m2',
    'biologie_albumine_g_l', 'biologie_crp_mg_l', 'biologie_plaquettes_g_l',
    'biologie_hemoglobine_g_dl', 'biologie_uree_g_l', 'biologie_hba1c_pct',
    'biologie_leucocytes_g_l', 'biologie_bicarbonates_mmol_l',
    'biologie_calcium_corrige_mg_l', 'biologie_phosphore_mg_l',
    'biologie_pth_pg_ml', 'biologie_ferritine_ng_ml',
    'biologie_saturation_transferrine_pct', 'biologie_vitamine_d_ng_ml',
    'biologie_proteinurie_g_24h', 'biologie_potassium_mmol_l',
    'biologie_sodium_mmol_l', 'biologie_hbsag', 'biologie_vhc', 'biologie_vih',
    'risk_crp_eleve', 'risk_phosphore_eleve', 'risk_calcium_eleve', 'risk_wbc_eleve',
    'risk_edema', 'risk_esa_absent', 'risk_late_referral', 'risk_low_bmi',
    'risk_marital_non_marie', 'risk_ps_severe', 'risk_chf', 'risk_pvd',
    'risk_cancer', 'risk_copd', 'risk_egfr_paradox', 'doietal_risk_score',
    # Présentation clinique
    'presentation_tas_mmhg', 'presentation_tad_mmhg',
    'presentation_frequence_cardiaque_bpm', 'presentation_temperature_c',
    'presentation_poids_kg', 'presentation_taille_cm',
    'presentation_statut_diurese', 'presentation_volume_urinaire_ml_j',
    'presentation_autonomie_fonctionnelle', 'presentation_symptomes',
    'presentation_notes_examen_clinique',
    # IRC
    'irc_etiologie_principale', 'irc_etiologie_secondaire',
    'irc_maladie_renale_hereditaire', 'irc_antecedents_familiaux_renaux',
    'irc_statut_biopsie_renale', 'irc_resultat_biopsie_renale',
    'irc_connue_avant_dialyse', 'irc_contexte_debut_dialyse',
    'irc_duree_suivi_predialytique_mois', 'irc_source_adressage',
    'irc_preference_therapie_renale', 'irc_niveau_comprehension_patient',
    # Dialyse
    'dialyse_modalite_actuelle', 'dialyse_modalite_initiale',
    'dialyse_seances_par_semaine', 'dialyse_duree_seance_min',
    'dialyse_debit_sanguin_ml_min', 'dialyse_debit_dialysat_ml_min',
    'dialyse_potassium_dialysat_mmol_l', 'dialyse_calcium_dialysat_mmol_l',
    'dialyse_type_anticoagulation', 'dialyse_statut_fonction_renale_residuelle',
    'dialyse_type_acces_initial', 'dialyse_site_acces_initial',
    'dialyse_type_regime_dp', 'dialyse_nombre_echanges_dp_jour',
    'dialyse_volume_stase_dp_ml', 'dialyse_jours_entre_catheter_et_fav',
    'dialyse_acces_admission_tunnelise', 'dialyse_acces_admission_femoral',
    'dialyse_acces_admission_fav', 'dialyse_acces_admission_peritoneale',
    'dialyse_statut_liste_attente_transplantation',
    # Qualité dialyse
    'qualite_spktv', 'qualite_urr_pct', 'qualite_prise_poids_interdialytique_kg',
    'qualite_taux_ultrafiltration_ml_kg_h', 'qualite_tas_predialyse_mmhg',
    'qualite_tas_postdialyse_mmhg', 'qualite_poids_sec_kg',
    'qualite_seances_manquees_30j', 'qualite_seances_raccourcies_30j',
    'qualite_hypotensions_intradialytiques_30j', 'qualite_observance_declaree_patient',
    # Imagerie
    'imagerie_taille_reins', 'imagerie_echogenicite_renale', 'imagerie_hydronephrose',
    'imagerie_kystes_renaux', 'imagerie_lithiase', 'imagerie_radiographie_thorax',
    'imagerie_fevg_pct', 'imagerie_hypertrophie_ventriculaire_gauche',
    'imagerie_valvulopathie', 'imagerie_autres_resultats',
    # Complications
    'complication_liste', 'complication_motifs_hospitalisation',
    'complication_nombre_hospitalisations', 'complication_jours_hospitalisation',
    'complication_changement_modalite_dialyse',
    # Devenir
    'devenir_statut', 'devenir_cause_deces', 'devenir_date_deces',
    'devenir_date_transplantation', 'devenir_delai_deces_jours',
    'devenir_qualite_vie', 'devenir_categorie_pronostique',
]

# Features numériques connues — utilisé pour le preprocessing dynamique
NUMERIC_FEATURE_SUFFIXES = [
    '_mg_l', '_g_l', '_g_dl', '_mmol_l', '_ml_min', '_ml_min_1_73m2',
    '_mmhg', '_bpm', '_c', '_kg', '_cm', '_ml_j', '_mois', '_km',
    '_pct', '_pg_ml', '_ng_ml', '_g_24h', '_jours', '_j',
    '_par_semaine', '_min', '_seances', '_hospitalisations',
]
ALWAYS_NUMERIC = {'age', 'demographie_age_ans', 'demographie_distance_centre_km'}
ALWAYS_CATEGORICAL = {'sexe', 'demographie_sexe'}

DERIVED_FEATURE_KEYS = {
    'risk_crp_eleve', 'risk_phosphore_eleve', 'risk_calcium_eleve', 'risk_wbc_eleve',
    'risk_edema', 'risk_esa_absent', 'risk_late_referral', 'risk_low_bmi',
    'risk_marital_non_marie', 'risk_ps_severe', 'risk_chf', 'risk_pvd',
    'risk_cancer', 'risk_copd', 'risk_egfr_paradox', 'doietal_risk_score',
}

CLINICAL_RISK_SOURCE_KEYS = [
    'biologie_crp_mg_l', 'biologie_phosphore_mg_l', 'biologie_calcium_corrige_mg_l',
    'biologie_leucocytes_g_l', 'biologie_albumine_g_l', 'biologie_dfg_mdrd_ml_min_1_73m2',
    'irc_duree_suivi_predialytique_mois', 'presentation_poids_kg', 'presentation_taille_cm',
    'demographie_statut_matrimonial', 'presentation_autonomie_fonctionnelle',
    'presentation_symptomes', 'presentation_notes_examen_clinique',
    'comorbidite_liste', 'comorbidite_autre', 'traitement_medicaments_renaux_actuels',
]

# ── Recommandations de modèles par type de prédiction ────────────────────────
RECOMMENDATIONS = {
    'mortalite': [
        'random_forest',
        'extra_trees',
        'gradient_boosting',
        'adaboost',
    ] + (['xgboost'] if XGBOOST_AVAILABLE else []) + (['lightgbm'] if LIGHTGBM_AVAILABLE else []) + (['catboost'] if CATBOOST_AVAILABLE else []),
    'coagulation': ['logistic_regression', 'svm', 'gradient_boosting'],
}

MORTALITY_LEAKAGE_FEATURES = {
    'devenir_statut', 'devenir_cause_deces', 'devenir_date_deces',
    'devenir_date_transplantation', 'devenir_delai_deces_jours',
    'devenir_qualite_vie', 'devenir_categorie_pronostique',
}

COAGULATION_LEAKAGE_FEATURES = {
    'complication_liste', 'complication_motifs_hospitalisation',
    'presentation_symptomes', 'presentation_notes_examen_clinique',
}


def filter_feature_keys_for_training(target_type, feature_keys):
    """Retourne les features valides pour l'entraînement sans fuite de données."""
    keys = [k for k in feature_keys if k in ALL_KNOWN_FEATURES]
    if target_type == 'mortalite':
        keys = [k for k in keys if k not in MORTALITY_LEAKAGE_FEATURES]
    elif target_type == 'coagulation':
        keys = [k for k in keys if k not in COAGULATION_LEAKAGE_FEATURES]
    return keys

# ── Mots-clés pour la détection des complications de coagulation ─────────────
KEYWORDS_COAGULATION = re.compile(
    r'hemorrag|thromb|thrombo|saign|ecchym|hematome|coagul|embol|infarct',
    re.IGNORECASE,
)

def find_best_threshold(y_true, y_prob):
    """Trouve le seuil de classification qui maximise le F1 sur y_prob."""
    if y_prob is None or len(np.unique(y_true)) < 2:
        return 0.5

    thresholds = np.linspace(0.01, 0.99, 99)
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in thresholds:
        y_pred = (y_prob >= threshold).astype(int)
        f1_val = f1_score(y_true, y_pred, zero_division=0)
        if f1_val > best_f1:
            best_f1 = f1_val
            best_threshold = threshold
    return best_threshold


# ── Catalogue des modèles disponibles ────────────────────────────────────────
def get_model_map(scale_pos_weight=None):
    model_map = {
        'random_forest': RandomForestClassifier(
            n_estimators=200, random_state=42, class_weight='balanced_subsample', n_jobs=1
        ),
        'gradient_boosting': GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.05, max_depth=4, subsample=0.9, random_state=42
        ),
        'logistic_regression': LogisticRegression(
            max_iter=2000, solver='saga', class_weight='balanced', C=0.5
        ),
        'svm': SVC(
            C=0.01, kernel='linear', class_weight='balanced', probability=False, random_state=42, max_iter=5000
        ),
        'decision_tree': DecisionTreeClassifier(
            max_depth=6, random_state=42, class_weight='balanced', min_samples_leaf=5
        ),
    }
    model_map['extra_trees'] = ExtraTreesClassifier(
        n_estimators=200, random_state=42, class_weight='balanced_subsample', n_jobs=1
    )
    model_map['adaboost'] = AdaBoostClassifier(
        estimator=DecisionTreeClassifier(max_depth=2, class_weight='balanced'),
        n_estimators=150,
        random_state=42,
    )
    if XGBOOST_AVAILABLE:
        xgb_params = {
            'n_estimators': 200,
            'learning_rate': 0.05,
            'max_depth': 4,
            'eval_metric': 'logloss',
            'random_state': 42,
            'use_label_encoder': False,
        }
        if scale_pos_weight is not None:
            xgb_params['scale_pos_weight'] = scale_pos_weight
        model_map['xgboost'] = XGBClassifier(**xgb_params)
    if CATBOOST_AVAILABLE:
        cat_params = {
            'iterations': 200,
            'learning_rate': 0.05,
            'depth': 4,
            'random_state': 42,
            'verbose': 0,
        }
        if scale_pos_weight is not None:
            cat_params['class_weights'] = [scale_pos_weight, 1] if scale_pos_weight > 1 else [1, 1 / scale_pos_weight]
        model_map['catboost'] = CatBoostClassifier(**cat_params)
    if LIGHTGBM_AVAILABLE:
        lgbm_params = {
            'n_estimators': 200,
            'learning_rate': 0.05,
            'num_leaves': 31,
            'random_state': 42,
            'class_weight': 'balanced',
            'n_jobs': 1,
        }
        if scale_pos_weight is not None:
            lgbm_params['scale_pos_weight'] = scale_pos_weight
        model_map['lightgbm'] = LGBMClassifier(**lgbm_params)
    return model_map


def tune_estimator(estimator, param_distributions, X_train, y_train, numeric_features, categorical_features):
    pipeline = get_pipeline(estimator, numeric_features, categorical_features)
    n_splits = max(2, min(5, min(np.bincount(y_train))))
    search = RandomizedSearchCV(
        pipeline,
        param_distributions,
        n_iter=20,
        scoring='average_precision',
        cv=RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=3, random_state=42),
        n_jobs=1,
        random_state=42,
        verbose=0,
    )
    with joblib.parallel_backend('threading'):
        search.fit(X_train, y_train)
    return search.best_estimator_, search.best_params_, float(search.best_score_)


def _map_encoded_name_to_raw(encoded_name, categorical_features):
    if encoded_name.startswith('numeric__'):
        return encoded_name.split('__', 1)[1]
    if encoded_name.startswith('categorical__'):
        raw = encoded_name.split('__', 1)[1]
        for fk in sorted(categorical_features, key=len, reverse=True):
            if raw.startswith(fk + '_'):
                return fk
        return raw
    return encoded_name


def select_informative_features(X, y, numeric_features, categorical_features, max_features=25):
    """Sélectionne les features les plus importantes avant l'entraînement final."""
    if X.shape[1] <= max_features:
        return list(X.columns)

    selector_pipeline = get_pipeline(
        RandomForestClassifier(n_estimators=120, random_state=42, class_weight='balanced', n_jobs=1),
        numeric_features,
        categorical_features,
    )
    selector_pipeline.fit(X, y)
    encoded_names = get_feature_names_out(selector_pipeline.named_steps['preprocessor'])
    importances = selector_pipeline.named_steps['classifier'].feature_importances_

    raw_importances = {}
    for name, value in zip(encoded_names, importances):
        raw_name = _map_encoded_name_to_raw(name, categorical_features)
        raw_importances[raw_name] = raw_importances.get(raw_name, 0.0) + float(value)

    selected = [name for name, _ in sorted(raw_importances.items(), key=lambda item: item[1], reverse=True)][:max_features]
    return selected if selected else list(X.columns)[:max_features]


def tune_xgboost(X_train, y_train, numeric_features, categorical_features, scale_pos_weight=None):
    """Optimise les hyperparamètres pour XGBoost si disponible."""
    if not XGBOOST_AVAILABLE:
        raise ValueError('XGBoost non disponible dans l\'environnement.')

    param_distributions = {
        'classifier__n_estimators': [100, 150, 200, 250],
        'classifier__learning_rate': [0.01, 0.03, 0.05],
        'classifier__max_depth': [3, 4, 5, 6],
        'classifier__subsample': [0.7, 0.8, 0.9, 1.0],
        'classifier__colsample_bytree': [0.7, 0.8, 0.9, 1.0],
        'classifier__gamma': [0, 1, 3],
        'classifier__min_child_weight': [1, 3, 5],
    }
    xgb_estimator = XGBClassifier(
        eval_metric='logloss',
        random_state=42,
        use_label_encoder=False,
        scale_pos_weight=scale_pos_weight if scale_pos_weight is not None else 1,
    )
    search = RandomizedSearchCV(
        get_pipeline(xgb_estimator, numeric_features, categorical_features),
        param_distributions,
        n_iter=12,
        scoring='roc_auc',
        cv=StratifiedKFold(n_splits=min(5, min(np.bincount(y_train))), shuffle=True, random_state=42),
        n_jobs=1,
        random_state=42,
        verbose=0,
    )
    with joblib.parallel_backend('threading'):
        search.fit(X_train, y_train)
    return search.best_estimator_, search.best_params_, float(search.best_score_)


# ── Détection dynamique du type de feature ───────────────────────────────────

def is_numeric_feature(key):
    """Détermine si une clé de feature est numérique selon son suffixe ou son nom."""
    if key in ALWAYS_NUMERIC:
        return True
    if key in ALWAYS_CATEGORICAL:
        return False
    return any(key.endswith(suffix) for suffix in NUMERIC_FEATURE_SUFFIXES)


def classify_features(feature_keys):
    """Sépare dynamiquement les features numériques et catégorielles."""
    numeric = [k for k in feature_keys if is_numeric_feature(k)]
    categorical = [k for k in feature_keys if not is_numeric_feature(k)]
    return numeric, categorical


# ── Normalisation des valeurs ─────────────────────────────────────────────────

def normalize_value(value, is_numeric=True):
    """Normalise une valeur brute vers float ou str selon son type attendu."""
    if value is None:
        return np.nan
    if is_numeric:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(',', '.').replace(' ', '')
        if text == '':
            return np.nan
        try:
            return float(text)
        except ValueError:
            return np.nan
    else:
        text = str(value).strip().lower()
        return text if text else 'inconnu'


def normalize_sexe(value):
    """Normalise le sexe vers M/F/O."""
    if value is None:
        return 'inconnu'
    v = str(value).strip().upper()
    if v in ('M', 'MASCULIN', 'HOMME', 'MALE', '0'):
        return 'M'
    if v in ('F', 'FEMININ', 'FEMME', 'FEMALE', '1'):
        return 'F'
    if v in ('O', 'AUTRE', 'OTHER', '2'):
        return 'O'
    return 'inconnu'


def normalize_boolean_text(value):
    """Normalise oui/non/vrai/faux."""
    if value is None:
        return 'non'
    v = str(value).strip().lower()
    if v in ('oui', 'true', '1', 'yes', 'vrai'):
        return 'oui'
    return 'non'


def parse_numeric_value(value):
    if value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(',', '.').replace(' ', '')
    if text == '':
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def parse_text_value(value):
    if value is None:
        return ''
    return str(value).strip().lower()


def text_matches_any(value, tokens):
    normalized = parse_text_value(value)
    if not normalized:
        return False
    return any(token in normalized for token in tokens)


def compute_clinical_risk_indicators(raw_values):
    """Calcule des features dérivées utiles pour la mortalité à 1 an."""
    values = {key: raw_values.get(key) for key in CLINICAL_RISK_SOURCE_KEYS}
    crp = parse_numeric_value(values.get('biologie_crp_mg_l'))
    phosphate = parse_numeric_value(values.get('biologie_phosphore_mg_l'))
    calcium = parse_numeric_value(values.get('biologie_calcium_corrige_mg_l'))
    wbc = parse_numeric_value(values.get('biologie_leucocytes_g_l'))
    albumin = parse_numeric_value(values.get('biologie_albumine_g_l'))
    egfr = parse_numeric_value(values.get('biologie_dfg_mdrd_ml_min_1_73m2'))
    predialysis_months = parse_numeric_value(values.get('irc_duree_suivi_predialytique_mois'))
    weight = parse_numeric_value(values.get('presentation_poids_kg'))
    height = parse_numeric_value(values.get('presentation_taille_cm'))

    marital = parse_text_value(values.get('demographie_statut_matrimonial'))
    autonomy = parse_text_value(values.get('presentation_autonomie_fonctionnelle'))
    symptoms = ' '.join([
        parse_text_value(values.get('presentation_symptomes')),
        parse_text_value(values.get('presentation_notes_examen_clinique')),
    ]).strip()
    comorbidity = ' '.join([
        parse_text_value(values.get('comorbidite_liste')),
        parse_text_value(values.get('comorbidite_autre')),
    ]).strip()
    treatment = parse_text_value(values.get('traitement_medicaments_renaux_actuels'))

    risk_chf = text_matches_any(comorbidity, [
        'chf', 'insuffisance cardiaque', 'insuffisance cardiaque congestive', 'heart failure',
    ])
    risk_pvd = text_matches_any(comorbidity, [
        'artériopathie périphérique', 'arteriopathie peripherique', 'pvd',
        'maladie artérielle périphérique', 'maladie arterielle peripherique',
    ])
    risk_cancer = text_matches_any(comorbidity, [
        'cancer', 'néoplasie', 'neoplasie', 'tumeur', 'tumeur maligne', 'metastase',
    ])
    risk_copd = text_matches_any(comorbidity, [
        'copd', 'bpco', 'bronchopneumopathie', 'maladie pulmonaire obstructive',
    ])
    risk_edema = text_matches_any(symptoms, [
        'œdème', 'oedeme', 'edema', 'surcharge hydrique', 'oedème généralisé',
    ])
    risk_ps_severe = (
        text_matches_any(autonomy, ['ps 3', 'ps3', 'ps 4', 'ps4', 'alit', 'allong', 'aide pour marcher', 'dépend', 'depend'])
        or text_matches_any(symptoms, ['coma', 'comateux'])
    )
    has_esa = text_matches_any(treatment, [
        'esa', 'érythropo', 'erythropo', 'epo', 'darbepoetin', 'darbepoétine',
    ])
    risk_esa_absent = 1 if treatment and not has_esa else 0

    risk_crp_eleve = 1 if not np.isnan(crp) and crp > 10 else 0
    risk_phosphore_eleve = 1 if not np.isnan(phosphate) and phosphate > 2.0 else 0
    risk_calcium_eleve = 1 if not np.isnan(calcium) and calcium > 8.5 else 0
    risk_wbc_eleve = 1 if not np.isnan(wbc) and wbc > 11.0 else 0
    risk_late_referral = 1 if not np.isnan(predialysis_months) and predialysis_months < 3 else 0
    risk_low_bmi = 0
    if not np.isnan(weight) and not np.isnan(height) and height > 0:
        bmi = weight / ((height / 100) ** 2)
        risk_low_bmi = 1 if bmi < 20 else 0
    risk_marital_non_marie = 1 if text_matches_any(marital, ['célibataire', 'celibataire', 'divorcé', 'divorce', 'veuf', 'veuve', 'séparé', 'separe']) else 0
    risk_egfr_paradox = 1 if not np.isnan(egfr) and egfr > 7.0 else 0

    cci_points = 3 if risk_chf or risk_cancer else 2 if risk_pvd or risk_copd else 0
    ps_points = 3 if risk_ps_severe else 1 if text_matches_any(autonomy, ['ps 1', 'ps1', 'ps 2', 'ps2', 'semi autonome', 'semi-autonome', 'mobilité']) else 0
    calcium_points = 2 if risk_calcium_eleve else 0
    esa_points = 2 if risk_esa_absent else 0
    albumin_points = 1 if not np.isnan(albumin) and albumin < 3.5 else 0
    egfr_points = 1 if risk_egfr_paradox else 0

    known_components = sum(
        1 for value in [albumin, egfr, calcium, crp, phosphate, predialysis_months, weight, height]
        if not np.isnan(value)
    )
    doietal_risk_score = np.nan
    if known_components > 0 or cci_points > 0 or ps_points > 0:
        doietal_risk_score = float(cci_points + ps_points + calcium_points + esa_points + albumin_points + egfr_points)

    return {
        'risk_crp_eleve': float(risk_crp_eleve),
        'risk_phosphore_eleve': float(risk_phosphore_eleve),
        'risk_calcium_eleve': float(risk_calcium_eleve),
        'risk_wbc_eleve': float(risk_wbc_eleve),
        'risk_edema': float(risk_edema),
        'risk_esa_absent': float(risk_esa_absent),
        'risk_late_referral': float(risk_late_referral),
        'risk_low_bmi': float(risk_low_bmi),
        'risk_marital_non_marie': float(risk_marital_non_marie),
        'risk_ps_severe': float(risk_ps_severe),
        'risk_chf': float(risk_chf),
        'risk_pvd': float(risk_pvd),
        'risk_cancer': float(risk_cancer),
        'risk_copd': float(risk_copd),
        'risk_egfr_paradox': float(risk_egfr_paradox),
        'doietal_risk_score': doietal_risk_score,
    }


def compute_selected_data_risk_score(payload):
    """Retourne un score de risque normalisé sur 0-100 basé uniquement sur les variables sélectionnées."""
    crp = parse_numeric_value(payload.get('biologie_crp_mg_l'))
    phosphate = parse_numeric_value(payload.get('biologie_phosphore_mg_l'))
    calcium = parse_numeric_value(payload.get('biologie_calcium_corrige_mg_l'))
    albumin = parse_numeric_value(payload.get('biologie_albumine_g_l'))
    wbc = parse_numeric_value(payload.get('biologie_leucocytes_g_l'))
    egfr = parse_numeric_value(payload.get('biologie_dfg_mdrd_ml_min_1_73m2'))
    months = parse_numeric_value(payload.get('irc_duree_suivi_predialytique_mois'))
    weight = parse_numeric_value(payload.get('presentation_poids_kg'))
    height = parse_numeric_value(payload.get('presentation_taille_cm'))
    age = parse_numeric_value(payload.get('age') or payload.get('demographie_age_ans'))

    autonomy = parse_text_value(payload.get('presentation_autonomie_fonctionnelle'))
    symptoms = ' '.join([
        parse_text_value(payload.get('presentation_symptomes')),
        parse_text_value(payload.get('presentation_notes_examen_clinique')),
    ]).strip()
    comorbidity = ' '.join([
        parse_text_value(payload.get('comorbidite_liste')),
        parse_text_value(payload.get('comorbidite_autre')),
    ]).strip()
    treatment = parse_text_value(payload.get('traitement_medicaments_renaux_actuels'))
    marital_status = parse_text_value(payload.get('demographie_statut_matrimonial'))

    def present(key):
        value = payload.get(key)
        return value is not None and str(value).strip() != ''

    def evaluate(condition, weight, present_flag=True):
        nonlocal score, max_score
        if not present_flag:
            return
        max_score += weight
        if condition:
            score += weight

    score = 0.0
    max_score = 0.0

    evaluate(not np.isnan(crp) and crp > 10, 10, present('biologie_crp_mg_l'))
    evaluate(not np.isnan(phosphate) and phosphate > 2.0, 8, present('biologie_phosphore_mg_l'))
    evaluate(not np.isnan(calcium) and calcium > 8.5, 7, present('biologie_calcium_corrige_mg_l'))
    evaluate(not np.isnan(albumin) and albumin < 3.5, 12, present('biologie_albumine_g_l'))
    evaluate(not np.isnan(wbc) and wbc > 11.0, 8, present('biologie_leucocytes_g_l'))
    evaluate(not np.isnan(egfr) and egfr > 7.0, 8, present('biologie_dfg_mdrd_ml_min_1_73m2'))
    evaluate(not np.isnan(months) and months < 3, 9, present('irc_duree_suivi_predialytique_mois'))
    evaluate(not np.isnan(age) and age >= 75, 5, present('age') or present('demographie_age_ans'))
    if not np.isnan(weight) and not np.isnan(height) and height > 0:
        bmi = weight / ((height / 100) ** 2)
        evaluate(bmi < 20, 8, present('presentation_poids_kg') and present('presentation_taille_cm'))
    evaluate(text_matches_any(autonomy, ['ps 3', 'ps3', 'ps 4', 'ps4', 'alit', 'allong', 'aide pour marcher', 'dépend', 'depend']), 14, present('presentation_autonomie_fonctionnelle'))
    evaluate(text_matches_any(symptoms, ['coma', 'comateux']), 16, present('presentation_symptomes') or present('presentation_notes_examen_clinique'))
    evaluate(text_matches_any(comorbidity, ['chf', 'insuffisance cardiaque', 'cancer', 'bpco', 'bronchopneumopathie', 'artériopathie périphérique', 'arteriopathie peripherique', 'pvd']), 10, present('comorbidite_liste') or present('comorbidite_autre'))
    evaluate(treatment and not text_matches_any(treatment, ['esa', 'érythropo', 'erythropo', 'epo', 'darbepoetin', 'darbepoétine']), 6, present('traitement_medicaments_renaux_actuels'))
    evaluate(text_matches_any(marital_status, ['célibataire', 'celibataire', 'divorcé', 'divorce', 'veuf', 'veuve', 'séparé', 'separe']), 4, present('demographie_statut_matrimonial'))

    if max_score == 0:
        return None

    normalized_score = round((score / max_score) * 100, 1)
    if normalized_score < 20:
        category = 'Très faible'
    elif normalized_score < 40:
        category = 'Faible'
    elif normalized_score < 60:
        category = 'Modéré'
    elif normalized_score < 80:
        category = 'Élevé'
    else:
        category = 'Très élevé'

    return {'score': normalized_score, 'category': category}


def expand_feature_keys_with_clinical_indicators(feature_keys):
    keys = set(feature_keys)
    if 'biologie_crp_mg_l' in keys:
        keys.add('risk_crp_eleve')
    if 'biologie_phosphore_mg_l' in keys:
        keys.add('risk_phosphore_eleve')
    if 'biologie_calcium_corrige_mg_l' in keys:
        keys.add('risk_calcium_eleve')
    if 'biologie_leucocytes_g_l' in keys:
        keys.add('risk_wbc_eleve')
    if 'biologie_dfg_mdrd_ml_min_1_73m2' in keys:
        keys.add('risk_egfr_paradox')
        keys.add('doietal_risk_score')
    if 'biologie_albumine_g_l' in keys:
        keys.add('doietal_risk_score')
    if 'presentation_poids_kg' in keys and 'presentation_taille_cm' in keys:
        keys.add('risk_low_bmi')
    if 'irc_duree_suivi_predialytique_mois' in keys:
        keys.add('risk_late_referral')
        keys.add('doietal_risk_score')
    if 'presentation_autonomie_fonctionnelle' in keys or 'presentation_symptomes' in keys or 'presentation_notes_examen_clinique' in keys:
        keys.add('risk_ps_severe')
        keys.add('risk_edema')
        keys.add('doietal_risk_score')
    if 'comorbidite_liste' in keys or 'comorbidite_autre' in keys:
        keys.update({'risk_chf', 'risk_pvd', 'risk_cancer', 'risk_copd'})
        keys.add('doietal_risk_score')
    if 'traitement_medicaments_renaux_actuels' in keys:
        keys.add('risk_esa_absent')
        keys.add('doietal_risk_score')
    if 'demographie_statut_matrimonial' in keys:
        keys.add('risk_marital_non_marie')
    return sorted(keys)


# ── Extraction des features depuis le payload frontend ───────────────────────

def extract_features_from_payload(payload, feature_keys):
    """
    Extrait et normalise les features depuis le dict envoyé par le frontend.
    Seules les clés présentes dans feature_keys sont extraites.
    La détection numérique/catégorielle est dynamique selon le nom de la clé.
    """
    row = {}
    for key in feature_keys:
        if key in DERIVED_FEATURE_KEYS:
            continue
        value = payload.get(key)
        if key in ('sexe', 'demographie_sexe'):
            row[key] = normalize_sexe(value)
        elif key == 'comorbidite_statut_diabete':
            row[key] = normalize_boolean_text(value)
        elif is_numeric_feature(key):
            row[key] = normalize_value(value, is_numeric=True)
        else:
            row[key] = normalize_value(value, is_numeric=False)

    derived = compute_clinical_risk_indicators(payload)
    for key in feature_keys:
        if key in DERIVED_FEATURE_KEYS:
            row[key] = derived.get(key, np.nan)

    return row


# ── Extraction des features depuis un objet Patient ORM ──────────────────────

def extract_features_from_patient(patient, feature_keys):
    """Extrait les features depuis un objet ORM Patient selon les clés demandées."""
    row = {}
    raw_values = {}
    for source_key in CLINICAL_RISK_SOURCE_KEYS:
        value = getattr(patient, source_key, None)
        if value is None and hasattr(patient, 'extra_data') and isinstance(patient.extra_data, dict):
            value = patient.extra_data.get(source_key)
        raw_values[source_key] = value

    for key in feature_keys:
        if key in DERIVED_FEATURE_KEYS:
            continue
        value = getattr(patient, key, None)
        if value is None and hasattr(patient, 'extra_data') and isinstance(patient.extra_data, dict):
            value = patient.extra_data.get(key)
        if key in ('sexe', 'demographie_sexe'):
            row[key] = normalize_sexe(value)
        elif key == 'comorbidite_statut_diabete':
            row[key] = normalize_boolean_text(value)
        elif is_numeric_feature(key):
            row[key] = normalize_value(value, is_numeric=True)
        else:
            row[key] = normalize_value(value, is_numeric=False)

    derived = compute_clinical_risk_indicators(raw_values)
    for key in feature_keys:
        if key in DERIVED_FEATURE_KEYS:
            row[key] = derived.get(key, np.nan)

    return row


# ── Labels de prédiction ──────────────────────────────────────────────────────

def mortality_label(patient):
    """Retourne 1 si le patient est décédé dans les 365 jours suivant le début de dialyse.

    Priorité de vérification :
    1. extra_data.delai_jusquau_deces_jours (importé depuis Excel, source de vérité)
    2. devenir_date_deces - dialyse_date_debut (calcul depuis dates)
    3. devenir_statut seul (sans contrainte 1 an — fallback dégradé)
    """
    is_dead = False
    status = getattr(patient, 'devenir_statut', None)
    if status is not None:
        normalized_status = str(status).strip().lower()
        if 'dece' in normalized_status or 'décédé' in normalized_status:
            is_dead = True

    if not is_dead:
        return 0

    # Source 1 — délai en jours stocké directement depuis le fichier Excel
    extra = getattr(patient, 'extra_data', None) or {}
    delai = extra.get('delai_jusquau_deces_jours')
    if delai is not None:
        try:
            return 1 if int(float(str(delai))) <= 365 else 0
        except (ValueError, TypeError):
            pass

    # Source 2 — calcul depuis devenir_date_deces et dialyse_date_debut
    death_date_raw = getattr(patient, 'devenir_date_deces', None)
    dialyse_start_raw = getattr(patient, 'dialyse_date_debut', None)

    if death_date_raw and dialyse_start_raw:
        def _parse_dt(raw):
            if isinstance(raw, datetime):
                return raw
            if isinstance(raw, date):
                return datetime.combine(raw, datetime.min.time())
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(str(raw).strip(), fmt)
                except ValueError:
                    pass
            try:
                return datetime.fromisoformat(str(raw).strip())
            except Exception:
                return None

        dt_death = _parse_dt(death_date_raw)
        dt_start = _parse_dt(dialyse_start_raw)
        if dt_death and dt_start:
            return 1 if dt_death <= dt_start + timedelta(days=365) else 0

    # Source 3 — fallback : décédé sans contrainte temporelle connue → compté comme décès à 1 an
    return 1


def coagulation_label(patient):
    """Détecte les complications hémorragiques/thrombotiques par regex sur texte libre."""
    fields = [
        getattr(patient, 'complication_liste', ''),
        getattr(patient, 'complication_motifs_hospitalisation', ''),
        getattr(patient, 'presentation_symptomes', ''),
        getattr(patient, 'presentation_notes_examen_clinique', ''),
    ]
    text = ' '.join(str(v) for v in fields if v)
    return 1 if KEYWORDS_COAGULATION.search(text) else 0


# ── Validation des patients pour l'entraînement ──────────────────────────────

def is_valid_patient_for_training(features, numeric_keys):
    """Vérifie qu'un patient a assez de valeurs numériques non manquantes."""
    non_missing = [
        v for k, v in features.items()
        if k in numeric_keys and not (isinstance(v, float) and np.isnan(v))
    ]
    required = max(1, len(numeric_keys) // 3)
    return len(non_missing) >= required


# ── Construction du dataset depuis la base ────────────────────────────────────

def build_dataset(target_type, feature_keys):
    """Construit le DataFrame d'entraînement depuis les patients en base."""
    patients = Patient.objects.all()
    rows = []
    labels = []
    label_fn = mortality_label if target_type == 'mortalite' else coagulation_label
    numeric_keys, _ = classify_features(feature_keys)

    for patient in patients:
        features = extract_features_from_patient(patient, feature_keys)
        if not is_valid_patient_for_training(features, numeric_keys):
            continue
        label = label_fn(patient)
        rows.append(features)
        labels.append(label)

    if not rows:
        return pd.DataFrame(), np.array([], dtype=int)

    df = pd.DataFrame(rows, columns=feature_keys)
    y = np.array(labels, dtype=int)
    return df, y


# ── Pipeline de prétraitement dynamique ──────────────────────────────────────

def cast_to_string(X):
    return X.astype(str)


def get_preprocessor(numeric_features, categorical_features):
    """Construit un ColumnTransformer adapté aux features présentes."""
    transformers = []

    if numeric_features:
        numeric_transformer = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('power', PowerTransformer(method='yeo-johnson')),
            ('scaler', StandardScaler()),
        ])
        transformers.append(('numeric', numeric_transformer, numeric_features))

    if categorical_features:
        categorical_transformer = Pipeline([
            ('cast', FunctionTransformer(cast_to_string, validate=False)),
            ('imputer', SimpleImputer(strategy='constant', fill_value='inconnu')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False, drop='if_binary')),
        ])
        transformers.append(('categorical', categorical_transformer, categorical_features))

    return ColumnTransformer(
        transformers=transformers,
        remainder='drop',
        sparse_threshold=0,
    )


def get_svm_preprocessor(numeric_features, categorical_features):
    """Construit un ColumnTransformer optimisé pour SVM avec KNN imputation."""
    transformers = []

    if numeric_features:
        numeric_transformer = Pipeline([
            ('imputer', KNNImputer(n_neighbors=3)),
            ('power', PowerTransformer(method='yeo-johnson')),
            ('scaler', StandardScaler()),
        ])
        transformers.append(('numeric', numeric_transformer, numeric_features))

    if categorical_features:
        categorical_transformer = Pipeline([
            ('cast', FunctionTransformer(cast_to_string, validate=False)),
            ('imputer', SimpleImputer(strategy='constant', fill_value='inconnu')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False, drop='if_binary')),
        ])
        transformers.append(('categorical', categorical_transformer, categorical_features))

    return ColumnTransformer(
        transformers=transformers,
        remainder='drop',
        sparse_threshold=0,
    )


def get_pipeline(estimator, numeric_features, categorical_features):
    """Construit un Pipeline complet prétraitement + classifieur."""
    return Pipeline([
        ('preprocessor', get_preprocessor(numeric_features, categorical_features)),
        ('classifier', estimator),
    ])


def get_svm_pipeline(estimator, numeric_features, categorical_features):
    """Construit un Pipeline optimisé pour SVM avec KNN imputation."""
    return Pipeline([
        ('preprocessor', get_svm_preprocessor(numeric_features, categorical_features)),
        ('classifier', estimator),
    ])


def tune_random_forest(X_train, y_train, numeric_features, categorical_features):
    """Recherche d'hyperparamètres pour améliorer le RandomForest."""
    param_distributions = {
        'classifier__n_estimators': [100, 150, 200, 250],
        'classifier__max_depth': [4, 6, 8, None],
        'classifier__min_samples_leaf': [1, 2, 4, 6],
        'classifier__max_features': ['sqrt', 'log2', 0.7],
        'classifier__class_weight': ['balanced', None],
    }
    search = RandomizedSearchCV(
        get_pipeline(RandomForestClassifier(random_state=42), numeric_features, categorical_features),
        param_distributions,
        n_iter=10,
        scoring='roc_auc',
        cv=StratifiedKFold(n_splits=min(5, min(np.bincount(y_train))), shuffle=True, random_state=42),
        n_jobs=1,
        random_state=42,
        verbose=0,
    )
    search.fit(X_train, y_train)
    return search.best_estimator_, search.best_params_, float(search.best_score_)


# ── Chemins des modèles sauvegardés ──────────────────────────────────────────

def get_model_path(target_type, model_name):
    return MODEL_DIRECTORY / f'{target_type}_{model_name}.joblib'


def get_best_path(target_type):
    return MODEL_DIRECTORY / f'{target_type}_best.joblib'


def get_features_path(target_type, model_name):
    """Sauvegarde les metadata de features utilisées lors de l'entraînement d'un modèle."""
    return MODEL_DIRECTORY / f'{target_type}_{model_name}_features.joblib'


def get_best_features_path(target_type):
    return MODEL_DIRECTORY / f'{target_type}_best_features.joblib'


def load_feature_metadata(path):
    if not path.exists():
        return {'feature_keys': [], 'threshold': 0.5, 'metrics': None}
    data = joblib.load(path)
    if isinstance(data, dict):
        return {
            'feature_keys': data.get('feature_keys', []),
            'threshold': data.get('threshold', 0.5),
            'class_distribution': data.get('class_distribution'),
            'metrics': data.get('metrics'),
        }
    return {'feature_keys': data, 'threshold': 0.5, 'metrics': None}


def ensure_trained_models(prediction_type, feature_keys=None):
    """Entraîne et sauvegarde un modèle si aucun modèle pré-entraîné n'existe encore."""
    try:
        train_models(prediction_type, feature_keys)
        return True, None
    except ValueError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f'Erreur interne lors de l\'entraînement automatique : {str(exc)}'


# ── Sélection du meilleur modèle ─────────────────────────────────────────────

def select_best_model(results):
    """Choisit le modèle le plus robuste sur le compromis précision / rappel.

    Priorise F1, puis PR AUC, puis AUC pour favoriser des modèles plus équilibrés.
    """
    return max(
        results,
        key=lambda item: (
            item['f1'] if item['f1'] is not None else -1.0,
            item['pr_auc'] if item['pr_auc'] is not None else -1.0,
            item['auc'] if item['auc'] is not None else -1.0,
            item['precision'] if item['precision'] is not None else -1.0,
        ),
    )


# ── Entraînement complet ──────────────────────────────────────────────────────

def train_models(target_type, feature_keys=None):
    """
    Entraîne tous les modèles disponibles sur les données patients.
    Si feature_keys est fourni, seules ces variables sont utilisées.
    Sinon, toutes les features connues sont tentées.
    Retourne un rapport de métriques et sauvegarde les modèles.
    """
    if feature_keys is None:
        feature_keys = ALL_KNOWN_FEATURES

    feature_keys = filter_feature_keys_for_training(target_type, feature_keys)
    feature_keys = expand_feature_keys_with_clinical_indicators(feature_keys)
    if not feature_keys:
        raise ValueError(
            'Aucune feature valide disponible pour l\'entraînement. '
            'Les variables sélectionnées semblent être des informations de sortie ou de complication.'
        )

    X, y = build_dataset(target_type, feature_keys)

    if X.empty:
        raise ValueError('Aucun patient valide trouvé pour l\'entraînement.')
    unique_labels, counts = np.unique(y, return_counts=True)
    if len(unique_labels) < 2:
        label_info = ', '.join(f'{int(label)}:{int(count)}' for label, count in zip(unique_labels, counts))
        raise ValueError(
            f'Toutes les étiquettes sont identiques ({label_info}). Impossible d\'entraîner un modèle de classification. '
            'Ajoutez des patients avec des événements positifs et négatifs pour ce type de prédiction.'
        )
    if len(y) < 20:
        raise ValueError(
            f'Seulement {len(y)} patients valides. Un minimum de 20 est requis pour l\'entraînement.'
        )

    numeric_features, categorical_features = classify_features(feature_keys)

    if len(feature_keys) > 30:
        selected_feature_keys = select_informative_features(
            X, y, numeric_features, categorical_features, max_features=25,
        )
        if len(selected_feature_keys) < len(feature_keys):
            feature_keys = selected_feature_keys
            X = X[feature_keys]
            numeric_features, categorical_features = classify_features(feature_keys)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    minority_count = int(np.min(counts))
    if minority_count < 5:
        raise ValueError(
            f'Trop peu d\'exemples dans la classe minoritaire ({minority_count}). '
            'Au moins 5 exemples sont requis pour un entraînement plus fiable.'
        )

    class_distribution = dict(zip([int(label) for label in unique_labels], [int(count) for count in counts]))
    should_oversample = False
    if len(unique_labels) == 2:
        maj_class = 0 if class_distribution.get(0, 0) > class_distribution.get(1, 0) else 1
        min_class = 1 - maj_class
        if class_distribution[min_class] * 2 < class_distribution[maj_class]:
            should_oversample = True

    report = []
    trained_pipelines = []
    best_score = -1.0
    best_model_instance = None
    best_model_name = None
    best_feature_metadata = None

    scale_pos_weight = None
    if len(unique_labels) == 2 and class_distribution.get(1, 0) > 0 and class_distribution.get(0, 0) > 0:
        scale_pos_weight = float(class_distribution.get(0, 0)) / float(class_distribution.get(1, 0))
        if scale_pos_weight < 1.0:
            scale_pos_weight = 1.0

    X_train_fit, y_train_fit = X_train, y_train
    if should_oversample:
        minority_class = min(class_distribution, key=class_distribution.get)
        majority_class = max(class_distribution, key=class_distribution.get)
        X_train_min = X_train[y_train == minority_class]
        y_train_min = y_train[y_train == minority_class]
        X_train_maj = X_train[y_train == majority_class]
        y_train_maj = y_train[y_train == majority_class]

        X_train_min_upsampled = resample(
            X_train_min,
            replace=True,
            n_samples=len(X_train_maj),
            random_state=42,
        )
        y_train_min_upsampled = np.full(len(X_train_maj), minority_class)

        X_train_fit = pd.concat([X_train_maj, X_train_min_upsampled], ignore_index=True)
        y_train_fit = np.concatenate([y_train_maj, y_train_min_upsampled])

        idx = np.random.RandomState(42).permutation(len(y_train_fit))
        X_train_fit = X_train_fit.iloc[idx].reset_index(drop=True)
        y_train_fit = y_train_fit[idx]

    model_map = get_model_map(scale_pos_weight=scale_pos_weight)

    for name, estimator in model_map.items():
        try:
            if name == 'random_forest':
                param_distributions = {
                    'classifier__n_estimators': [100, 150, 200, 250],
                    'classifier__max_depth': [4, 6, 8, None],
                    'classifier__min_samples_leaf': [1, 2, 4, 6],
                    'classifier__max_features': ['sqrt', 'log2', 0.7],
                    'classifier__class_weight': ['balanced', None],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'extra_trees':
                param_distributions = {
                    'classifier__n_estimators': [100, 150, 200, 250],
                    'classifier__max_depth': [4, 6, 8, None],
                    'classifier__min_samples_split': [2, 4, 6],
                    'classifier__max_features': ['sqrt', 'log2', 0.7],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'adaboost':
                param_distributions = {
                    'classifier__n_estimators': [50, 100, 150, 200],
                    'classifier__learning_rate': [0.01, 0.05, 0.1, 0.2],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'gradient_boosting':
                param_distributions = {
                    'classifier__n_estimators': [100, 150, 200, 250],
                    'classifier__learning_rate': [0.01, 0.03, 0.05, 0.1],
                    'classifier__max_depth': [3, 4, 5, 6],
                    'classifier__subsample': [0.7, 0.8, 0.9, 1.0],
                    'classifier__max_features': ['sqrt', 'log2', 0.7],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'logistic_regression':
                param_distributions = {
                    'classifier__C': [0.01, 0.05, 0.1, 0.5, 1.0, 2.0],
                    'classifier__penalty': ['l2'],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'svm':
                # SVM uses 32 engineered features (24 clinical + 8 interaction terms)
                from .models.feature_mapping import (
                    extract_features_for_patient as _svm_extract,
                    get_feature_order as _svm_feature_order,
                )
                svm_feature_keys = _svm_feature_order()
                label_fn_svm = mortality_label if target_type == 'mortalite' else coagulation_label
                svm_rows = []
                svm_labels = []
                for _pat in Patient.objects.all():
                    _feat = _svm_extract(_pat)
                    svm_rows.append({k: (v if v is not None else np.nan) for k, v in _feat.items()})
                    svm_labels.append(label_fn_svm(_pat))
                if not svm_rows:
                    report.append({
                        'model': name, 'error': 'Aucun patient pour SVM',
                        'accuracy': None, 'precision': None, 'recall': None, 'f1': None,
                        'pr_auc': None, 'auc': None, 'cv_pr_auc_mean': None, 'cv_pr_auc_std': None,
                        'cv_auc_mean': None, 'cv_auc_std': None,
                        'n_train': None, 'n_test': None, 'feature_keys': svm_feature_keys,
                    })
                    continue
                X_svm = pd.DataFrame(svm_rows, columns=svm_feature_keys)
                y_svm = np.array(svm_labels, dtype=int)
                valid_svm = X_svm.notna().sum(axis=1) >= max(1, len(svm_feature_keys) // 3)
                X_svm = X_svm[valid_svm].reset_index(drop=True)
                y_svm = y_svm[valid_svm]
                svm_unique, svm_counts = np.unique(y_svm, return_counts=True)
                if len(svm_unique) < 2 or len(y_svm) < 20:
                    report.append({
                        'model': name,
                        'error': f'Données insuffisantes ({len(y_svm)} patients, {len(svm_unique)} classes)',
                        'accuracy': None, 'precision': None, 'recall': None, 'f1': None,
                        'pr_auc': None, 'auc': None, 'cv_pr_auc_mean': None, 'cv_pr_auc_std': None,
                        'cv_auc_mean': None, 'cv_auc_std': None,
                        'n_train': None, 'n_test': None, 'feature_keys': svm_feature_keys,
                    })
                    continue
                svm_class_dist = {int(l): int(c) for l, c in zip(svm_unique, svm_counts)}
                X_svm_train, X_svm_test, y_svm_train, y_svm_test = train_test_split(
                    X_svm, y_svm, test_size=0.25, random_state=42, stratify=y_svm
                )
                # All SVM features are numeric floats
                # CalibratedClassifierCV(sigmoid) calibrates probabilities via 5-fold Platt scaling
                _base_svm = get_svm_pipeline(estimator, svm_feature_keys, [])
                svm_pipeline = CalibratedClassifierCV(_base_svm, method='sigmoid', cv=5)
                svm_pipeline.fit(X_svm_train, y_svm_train)
                y_prob_svm = svm_pipeline.predict_proba(X_svm_test)[:, 1]
                svm_threshold = find_best_threshold(y_svm_test, y_prob_svm)
                y_pred_svm = (y_prob_svm >= svm_threshold).astype(int)
                svm_has_both = len(np.unique(y_svm_test)) > 1
                svm_auc = float(roc_auc_score(y_svm_test, y_prob_svm)) if svm_has_both else None
                svm_pr_auc = float(average_precision_score(y_svm_test, y_prob_svm)) if svm_has_both else None
                svm_f1 = float(f1_score(y_svm_test, y_pred_svm, zero_division=0))
                svm_prec = float(precision_score(y_svm_test, y_pred_svm, zero_division=0))
                svm_rec = float(recall_score(y_svm_test, y_pred_svm, zero_division=0))
                svm_acc = float(accuracy_score(y_svm_test, y_pred_svm))
                # Calcul des seuils ROC depuis les données de test
                svm_t_youden, svm_t_spec90 = svm_threshold, svm_threshold
                if svm_has_both:
                    from sklearn.metrics import roc_curve as _roc_curve
                    _fpr, _tpr, _thr = _roc_curve(y_svm_test, y_prob_svm)
                    _j = _tpr - _fpr
                    svm_t_youden = float(_thr[int(np.argmax(_j))])
                    _mask90 = _fpr <= 0.10
                    if _mask90.any():
                        svm_t_spec90 = float(_thr[int(np.where(_mask90)[0][np.argmax(_tpr[_mask90])])])
                svm_meta = {
                    'feature_keys': svm_feature_keys,
                    'threshold': svm_threshold,
                    'threshold_youden': svm_t_youden,
                    'threshold_spec90': svm_t_spec90,
                    'class_distribution': svm_class_dist,
                    'metrics': {
                        'auc': svm_auc, 'pr_auc': svm_pr_auc, 'f1': svm_f1,
                        'precision': svm_prec, 'recall': svm_rec,
                        'n_train': len(X_svm_train), 'n_test': len(X_svm_test),
                    },
                }
                joblib.dump(svm_pipeline, get_model_path(target_type, name))
                joblib.dump(svm_meta, get_features_path(target_type, name))
                svm_score = svm_pr_auc if svm_pr_auc is not None else svm_auc if svm_auc is not None else svm_f1
                if svm_score is not None and svm_score > best_score:
                    best_score = svm_score
                    best_model_instance = svm_pipeline
                    best_model_name = name
                    best_feature_metadata = svm_meta
                report.append({
                    'model': name,
                    'accuracy': round(svm_acc, 4),
                    'precision': round(svm_prec, 4),
                    'recall': round(svm_rec, 4),
                    'f1': round(svm_f1, 4),
                    'pr_auc': round(svm_pr_auc, 4) if svm_pr_auc is not None else None,
                    'auc': round(svm_auc, 4) if svm_auc is not None else None,
                    'cv_pr_auc_mean': None, 'cv_pr_auc_std': None,
                    'cv_auc_mean': None, 'cv_auc_std': None,
                    'threshold': round(svm_threshold, 3),
                    'class_distribution': svm_class_dist,
                    'scale_pos_weight': None,
                    'n_train': len(X_svm_train),
                    'n_test': len(X_svm_test),
                    'feature_keys': svm_feature_keys,
                })
                continue
            elif name == 'xgboost':
                param_distributions = {
                    'classifier__n_estimators': [100, 150, 200, 250],
                    'classifier__learning_rate': [0.01, 0.03, 0.05, 0.1],
                    'classifier__max_depth': [3, 4, 5, 6],
                    'classifier__subsample': [0.7, 0.8, 0.9, 1.0],
                    'classifier__colsample_bytree': [0.7, 0.8, 0.9, 1.0],
                    'classifier__gamma': [0, 1, 3],
                    'classifier__min_child_weight': [1, 3, 5],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'catboost':
                param_distributions = {
                    'classifier__iterations': [100, 150, 200, 250],
                    'classifier__learning_rate': [0.01, 0.03, 0.05],
                    'classifier__depth': [4, 6, 8],
                    'classifier__l2_leaf_reg': [1, 3, 5],
                    'classifier__border_count': [32, 64],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            elif name == 'lightgbm':
                param_distributions = {
                    'classifier__n_estimators': [100, 150, 200, 250],
                    'classifier__learning_rate': [0.01, 0.03, 0.05],
                    'classifier__num_leaves': [31, 50, 70],
                    'classifier__subsample': [0.7, 0.8, 0.9],
                    'classifier__colsample_bytree': [0.7, 0.8, 0.9],
                }
                pipeline, best_params, best_search_score = tune_estimator(
                    estimator, param_distributions, X_train_fit, y_train_fit, numeric_features, categorical_features,
                )
            else:
                pipeline = get_pipeline(estimator, numeric_features, categorical_features)
                pipeline.fit(X_train_fit, y_train_fit)
                best_params = None
                best_search_score = None

            y_pred = pipeline.predict(X_test)

            y_prob = None
            if hasattr(pipeline, 'predict_proba'):
                y_prob = pipeline.predict_proba(X_test)[:, 1]
            elif hasattr(pipeline, 'decision_function'):
                raw = pipeline.decision_function(X_test)
                y_prob = 1 / (1 + np.exp(-raw))

            optimal_threshold = find_best_threshold(y_test, y_prob)
            if y_prob is not None:
                y_pred = (y_prob >= optimal_threshold).astype(int)

            accuracy = float(accuracy_score(y_test, y_pred))
            prec = float(precision_score(y_test, y_pred, zero_division=0))
            rec = float(recall_score(y_test, y_pred, zero_division=0))
            f1 = float(f1_score(y_test, y_pred, zero_division=0))

            has_both_classes = len(np.unique(y_test)) > 1
            pr_auc = (
                float(average_precision_score(y_test, y_prob))
                if y_prob is not None and has_both_classes else None
            )
            auc = (
                float(roc_auc_score(y_test, y_prob))
                if y_prob is not None and has_both_classes else None
            )

            # Validation croisée pour un score plus fiable
            n_splits = max(2, min(5, min(np.bincount(y))))
            with joblib.parallel_backend('threading'):
                cv_pr_scores = cross_val_score(
                    get_pipeline(estimator, numeric_features, categorical_features),
                    X, y, cv=RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=2, random_state=42),
                    scoring='average_precision',
                    n_jobs=1,
                )
                cv_auc_scores = cross_val_score(
                    get_pipeline(estimator, numeric_features, categorical_features),
                    X, y, cv=RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=2, random_state=42),
                    scoring='roc_auc',
                    n_jobs=1,
                )
            cv_pr_auc_mean = float(np.mean(cv_pr_scores))
            cv_pr_auc_std = float(np.std(cv_pr_scores))
            cv_auc_mean = float(np.mean(cv_auc_scores))
            cv_auc_std = float(np.std(cv_auc_scores))

            score = pr_auc if pr_auc is not None else auc if auc is not None else f1
            if score > best_score:
                best_score = score
                best_model_instance = pipeline
                best_model_name = name
                best_feature_metadata = {
                    'feature_keys': feature_keys,
                    'threshold': optimal_threshold,
                    'class_distribution': class_distribution,
                }

            trained_pipelines.append({
                'name': name,
                'pipeline': pipeline,
                'metrics': {
                    'accuracy': accuracy,
                    'precision': prec,
                    'recall': rec,
                    'f1': f1,
                    'pr_auc': pr_auc,
                    'auc': auc,
                    'cv_pr_auc_mean': cv_pr_auc_mean,
                    'cv_pr_auc_std': cv_pr_auc_std,
                    'cv_auc_mean': cv_auc_mean,
                    'cv_auc_std': cv_auc_std,
                    'threshold': optimal_threshold,
                },
            })

            row = {
                'model': name,
                'accuracy': round(accuracy, 4),
                'precision': round(prec, 4),
                'recall': round(rec, 4),
                'f1': round(f1, 4),
                'pr_auc': round(pr_auc, 4) if pr_auc is not None else None,
                'auc': round(auc, 4) if auc is not None else None,
                'cv_pr_auc_mean': round(cv_pr_auc_mean, 4),
                'cv_pr_auc_std': round(cv_pr_auc_std, 4),
                'cv_auc_mean': round(cv_auc_mean, 4),
                'cv_auc_std': round(cv_auc_std, 4),
                'threshold': round(optimal_threshold, 3),
                'class_distribution': class_distribution,
                'scale_pos_weight': round(scale_pos_weight, 4) if scale_pos_weight is not None else None,
                'n_train': len(X_train),
                'n_test': len(X_test),
                'feature_keys': feature_keys,
            }
            row['metrics'] = {
                'accuracy': row['accuracy'],
                'precision': row['precision'],
                'recall': row['recall'],
                'f1': row['f1'],
                'pr_auc': row['pr_auc'],
                'auc': row['auc'],
                'cv_pr_auc_mean': row['cv_pr_auc_mean'],
                'cv_pr_auc_std': row['cv_pr_auc_std'],
                'cv_auc_mean': row['cv_auc_mean'],
                'cv_auc_std': row['cv_auc_std'],
                'threshold': row['threshold'],
                'class_distribution': row['class_distribution'],
                'n_train': row['n_train'],
                'n_test': row['n_test'],
            }
            if name in ('random_forest', 'extra_trees', 'adaboost', 'xgboost', 'catboost', 'lightgbm'):
                row['search_score'] = round(best_search_score, 4)
                row['search_params'] = best_params
            report.append(row)

            # Sauvegarder le modèle entraîné et ses métadonnées de features avec les métriques.
            model_path = get_model_path(target_type, name)
            joblib.dump(pipeline, model_path)
            joblib.dump(
                {
                    'feature_keys': feature_keys,
                    'threshold': optimal_threshold,
                    'class_distribution': class_distribution,
                    'metrics': row['metrics'],
                },
                get_features_path(target_type, name),
            )

        except Exception as exc:
            report.append({
                'model': name,
                'error': str(exc),
                'accuracy': None,
                'precision': None,
                'recall': None,
                'f1': None,
                'pr_auc': None,
                'auc': None,
                'cv_auc_mean': None,
                'cv_auc_std': None,
                'n_train': None,
                'n_test': None,
                'feature_keys': feature_keys,
            })

    # Construire un classifieur d'ensemble soft voting si plusieurs bons modèles sont disponibles.
    if len(trained_pipelines) >= 3:
        voting_estimators = [
            (item['name'], item['pipeline'])
            for item in sorted(
                trained_pipelines,
                key=lambda item: (
                    item['metrics']['pr_auc'] if item['metrics']['pr_auc'] is not None else -1.0,
                    item['metrics']['auc'] if item['metrics']['auc'] is not None else -1.0,
                ),
                reverse=True,
            )[:3]
            if hasattr(item['pipeline'], 'predict_proba')
        ]
        if len(voting_estimators) >= 2:
            try:
                voting_clf = VotingClassifier(
                    estimators=voting_estimators,
                    voting='soft',
                    n_jobs=1,
                )
                voting_clf.fit(X_train_fit, y_train_fit)
                y_pred_vote = voting_clf.predict(X_test)
                y_prob_vote = voting_clf.predict_proba(X_test)[:, 1]
                optimal_threshold_vote = find_best_threshold(y_test, y_prob_vote)
                vote_pr_auc = float(average_precision_score(y_test, y_prob_vote)) if len(np.unique(y_test)) > 1 else None
                vote_auc = float(roc_auc_score(y_test, y_prob_vote)) if len(np.unique(y_test)) > 1 else None
                vote_score = vote_pr_auc if vote_pr_auc is not None else vote_auc if vote_auc is not None else float(f1_score(y_test, y_pred_vote, zero_division=0))
                if vote_score > best_score:
                    best_score = vote_score
                    best_model_instance = voting_clf
                    best_model_name = 'voting_ensemble'
                    best_feature_metadata = {
                        'feature_keys': feature_keys,
                        'threshold': optimal_threshold_vote,
                        'class_distribution': class_distribution,
                        'metrics': {
                            'accuracy': None,
                            'precision': None,
                            'recall': None,
                            'f1': None,
                            'pr_auc': vote_pr_auc,
                            'auc': vote_auc,
                            'cv_pr_auc_mean': None,
                            'cv_pr_auc_std': None,
                            'cv_auc_mean': None,
                            'cv_auc_std': None,
                            'threshold': optimal_threshold_vote,
                            'class_distribution': class_distribution,
                            'n_train': len(X_train),
                            'n_test': len(X_test),
                        },
                    }
                    model_path = get_model_path(target_type, best_model_name)
                    joblib.dump(voting_clf, model_path)
                    joblib.dump(
                        best_feature_metadata,
                        get_features_path(target_type, best_model_name),
                    )
            except Exception:
                pass

    if best_model_instance is not None:
        joblib.dump(best_model_instance, get_best_path(target_type))
        joblib.dump(best_feature_metadata or {
            'feature_keys': feature_keys,
            'threshold': 0.5,
            'class_distribution': class_distribution,
        }, get_best_features_path(target_type))

    return report, best_model_name


# ── Interprétabilité des résultats ────────────────────────────────────────────

def get_feature_names_out(preprocessor):
    """Récupère les noms des features après encodage."""
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
        return []


def extract_importances(pipeline, feature_names):
    """Extrait les importances de features du classifieur du pipeline."""
    estimator = pipeline.named_steps.get('classifier')
    if estimator is None:
        return []

    if hasattr(estimator, 'feature_importances_'):
        importances = estimator.feature_importances_
    elif hasattr(estimator, 'coef_'):
        coef = estimator.coef_
        importances = np.mean(np.abs(coef), axis=0) if coef.ndim > 1 else np.abs(coef[0])
    elif hasattr(estimator, 'calibrated_classifiers_'):
        # CalibratedClassifierCV wrapping LinearSVC
        coefs = []
        for clf in estimator.calibrated_classifiers_:
            base = clf.estimator if hasattr(clf, 'estimator') else getattr(clf, 'base_estimator', None)
            if base is not None and hasattr(base, 'coef_'):
                coefs.append(np.abs(base.coef_[0]))
        if coefs:
            importances = np.mean(coefs, axis=0)
        else:
            return []
    else:
        return []

    if len(importances) != len(feature_names):
        return []

    total = np.sum(importances)
    if total == 0:
        return []

    ranked = sorted(
        [
            {'label': name, 'weight': float(round((value / total) * 100, 1))}
            for name, value in zip(feature_names, importances)
        ],
        key=lambda item: item['weight'],
        reverse=True,
    )
    return ranked[:6]


def build_interpretation(pipeline, feature_keys):
    """
    Construit l'interprétabilité à partir des importances du modèle.
    Mappe les noms encodés vers des noms lisibles.
    """
    preprocessor = pipeline.named_steps.get('preprocessor')
    if preprocessor is None:
        return []

    encoded_names = get_feature_names_out(preprocessor)
    if not encoded_names:
        return []

    raw_importances = extract_importances(pipeline, encoded_names)
    if not raw_importances:
        return []

    # Mapping nom encodé → nom de feature original
    result = []
    for item in raw_importances:
        raw_name = item['label']
        readable_name = raw_name

        if raw_name.startswith('numeric__'):
            readable_name = raw_name.split('__', 1)[1]
        elif raw_name.startswith('categorical__'):
            suffix = raw_name.split('__', 1)[1]
            # suffix is like "sexe_M" or "comorbidite_statut_diabete_oui"
            # On cherche la feature d'origine dans feature_keys
            matched = None
            for fk in sorted(feature_keys, key=len, reverse=True):
                if suffix.startswith(fk):
                    category = suffix[len(fk):].lstrip('_')
                    readable_name = f'{fk}={category}' if category else fk
                    matched = fk
                    break
            if matched is None:
                readable_name = suffix

        result.append({'label': readable_name, 'weight': item['weight']})

    return result[:5]


# ── Vues API ──────────────────────────────────────────────────────────────────

class PredictionTrainView(APIView):
    """
    POST /predictions/train/
    Body: { "prediction_type": "mortalite"|"coagulation", "feature_keys": [...] (optionnel) }

    Entraîne tous les modèles ML disponibles sur les données patients.
    Si feature_keys est fourni, seules ces variables sont utilisées.
    Retourne le rapport de métriques et le meilleur modèle.
    """
    def post(self, request):
        target_type = request.data.get('prediction_type')
        if target_type not in ('mortalite', 'coagulation'):
            return Response(
                {'error': 'prediction_type doit être "mortalite" ou "coagulation".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        feature_keys = request.data.get('feature_keys')
        if feature_keys is not None:
            if not isinstance(feature_keys, list) or len(feature_keys) == 0:
                return Response(
                    {'error': 'feature_keys doit être une liste non vide.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            unknown = [k for k in feature_keys if k not in ALL_KNOWN_FEATURES]
            if unknown:
                return Response(
                    {'error': f'Features inconnues : {unknown}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            feature_keys = filter_feature_keys_for_training(target_type, feature_keys)
            if not feature_keys:
                return Response(
                    {'error': 'Aucune feature valide disponible pour l\'entraînement après filtrage des variables de sortie.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            report, best_model_name = train_models(target_type, feature_keys)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {'error': f'Erreur interne lors de l\'entraînement : {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        best = select_best_model(report) if report else None

        return Response(
            {
                'status': 'trained',
                'prediction_type': target_type,
                'best_model': best_model_name,
                'best_metrics': best,
                'report': report,
                'feature_keys_used': feature_keys or ALL_KNOWN_FEATURES,
            },
            status=status.HTTP_200_OK,
        )


class PredictionPredictView(APIView):
    """
    POST /predictions/predict/
    Body: {
        "prediction_type": "mortalite"|"coagulation",
        "model": "random_forest"|"auto"|...,
        "features": { "age": 58, "biologie_creatinine_mg_l": 145, ... }
    }

    Effectue une prédiction ML en utilisant exactement les features envoyées.
    Le modèle doit avoir été entraîné au préalable avec ces mêmes features.
    En mode "auto", le meilleur modèle entraîné est utilisé.
    """
    def post(self, request):
        prediction_type = request.data.get('prediction_type')
        selected_model_name = request.data.get('model', 'auto')
        features_payload = request.data.get('features', {})

        # ── Validation des entrées ────────────────────────────────────────────
        if prediction_type not in ('mortalite', 'coagulation'):
            return Response(
                {'error': 'prediction_type doit être "mortalite" ou "coagulation".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not features_payload or not isinstance(features_payload, dict):
            return Response(
                {'error': 'Le champ "features" est requis et doit être un dictionnaire non vide.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Vérifier que les features envoyées sont connues du système
        payload_feature_keys = list(features_payload.keys())
        unknown_features = [k for k in payload_feature_keys if k not in ALL_KNOWN_FEATURES]
        if unknown_features:
            return Response(
                {'error': f'Features non reconnues : {unknown_features}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload_feature_keys = filter_feature_keys_for_training(prediction_type, payload_feature_keys)
        if not payload_feature_keys:
            return Response(
                {'error': 'Aucune feature valide disponible pour la prédiction après filtrage des variables de sortie.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Chargement du modèle ──────────────────────────────────────────────
        if selected_model_name in ('auto', '', None):
            best_path = get_best_path(prediction_type)
            best_features_path = get_best_features_path(prediction_type)
            feature_keys_trained = []
            if best_path.exists() and best_features_path.exists():
                feature_metadata = load_feature_metadata(best_features_path)
                feature_keys_trained = feature_metadata['feature_keys']

            if not best_path.exists() or not feature_keys_trained:
                trained, error_msg = ensure_trained_models(prediction_type, payload_feature_keys)
                if not trained:
                    return Response(
                        {'error': error_msg or 'Aucun modèle entraîné trouvé et l\'entraînement automatique a échoué.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                feature_metadata = load_feature_metadata(best_features_path) if best_features_path.exists() else {'feature_keys': payload_feature_keys, 'threshold': 0.5}
                feature_keys_trained = feature_metadata['feature_keys']

            trained_raw_keys = [k for k in feature_keys_trained if k not in DERIVED_FEATURE_KEYS]
            if set(trained_raw_keys) != set(payload_feature_keys):
                trained, error_msg = ensure_trained_models(prediction_type, payload_feature_keys)
                if not trained:
                    return Response(
                        {'error': error_msg or 'Impossible d\'entraîner un modèle compatible avec les features envoyées.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                feature_metadata = load_feature_metadata(best_features_path) if best_features_path.exists() else {'feature_keys': payload_feature_keys, 'threshold': 0.5}
                feature_keys_trained = feature_metadata['feature_keys']

            pipeline = joblib.load(best_path)
            model_label = 'best'
        else:
            model_map = get_model_map()
            if selected_model_name not in model_map:
                return Response(
                    {'error': f'Modèle "{selected_model_name}" non reconnu. Modèles disponibles : {list(model_map.keys())}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            model_path = get_model_path(prediction_type, selected_model_name)
            features_path = get_features_path(prediction_type, selected_model_name)
            if not model_path.exists() or not features_path.exists():
                trained, error_msg = ensure_trained_models(prediction_type, payload_feature_keys)
                if not trained:
                    return Response(
                        {'error': error_msg or f'Le modèle "{selected_model_name}" n\'a pas encore été entraîné et l\'entraînement automatique a échoué.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
            feature_metadata = load_feature_metadata(features_path) if features_path.exists() else {'feature_keys': payload_feature_keys, 'threshold': 0.5}
            feature_keys_trained = feature_metadata['feature_keys']
            trained_raw_keys = [k for k in feature_keys_trained if k not in DERIVED_FEATURE_KEYS]
            if set(trained_raw_keys) != set(payload_feature_keys):
                trained, error_msg = ensure_trained_models(prediction_type, payload_feature_keys)
                if not trained:
                    return Response(
                        {'error': error_msg or 'Impossible d\'entraîner un modèle compatible avec les features envoyées.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )
                feature_metadata = load_feature_metadata(features_path) if features_path.exists() else {'feature_keys': payload_feature_keys, 'threshold': 0.5}
                feature_keys_trained = feature_metadata['feature_keys']
            pipeline = joblib.load(model_path)
            model_label = selected_model_name

        # ── Préparation des données de prédiction ─────────────────────────────
        raw_feature_keys = [k for k in feature_keys_trained if k not in DERIVED_FEATURE_KEYS]
        if not any(k in features_payload for k in raw_feature_keys):
            return Response(
                {
                    'error': (
                        'Aucune des features brutes envoyées ne correspond aux features d\'entraînement du modèle. '
                        f'Features entraînement : {feature_keys_trained}. '
                        f'Features reçues : {list(features_payload.keys())}.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        row = extract_features_from_payload(features_payload, feature_keys_trained)
        doi_score = row.get('doietal_risk_score')
        doi_score = float(round(doi_score, 2)) if isinstance(doi_score, float) and not np.isnan(doi_score) else None
        doi_category = None
        if doi_score is not None:
            if doi_score <= 4:
                doi_category = 'Faible'
            elif doi_score <= 6:
                doi_category = 'Modéré'
            elif doi_score <= 8:
                doi_category = 'Élevé'
            else:
                doi_category = 'Très élevé'

        selected_data_risk = compute_selected_data_risk_score(features_payload)
        input_df = pd.DataFrame([row], columns=feature_keys_trained)

        # ── Prédiction ────────────────────────────────────────────────────────
        try:
            probability = float(pipeline.predict_proba(input_df)[:, 1][0])
        except AttributeError:
            # Fallback pour modèles sans predict_proba (ex. LinearSVC brut)
            try:
                raw = float(pipeline.decision_function(input_df)[0])
                probability = float(1 / (1 + np.exp(-raw)))
            except Exception as exc:
                return Response(
                    {'error': f'Erreur lors de la prédiction : {str(exc)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as exc:
            return Response(
                {'error': f'Erreur lors de la prédiction : {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        score = round(float(np.clip(probability * 100, 0, 100)), 1)
        risk_level = 'Faible' if score <= 30 else 'Modéré' if score <= 70 else 'Élevé'
        factors = build_interpretation(pipeline, feature_keys_trained)

        # ── Recommandation clinique ────────────────────────────────────────────
        if risk_level == 'Élevé':
            recommendation = (
                'Risque élevé détecté : surveillance intensive recommandée, '
                'adaptation thérapeutique urgente et consultation spécialisée.'
            )
        elif risk_level == 'Modéré':
            recommendation = (
                'Risque modéré : suivi renforcé, optimisation des paramètres cliniques '
                'et réévaluation à court terme.'
            )
        else:
            recommendation = (
                'Risque faible : maintien du suivi standard avec contrôle périodique.'
            )

        # ── Sauvegarde dans l'historique ──────────────────────────────────────
        patient_id = features_payload.get('id_patient') or features_payload.get('age', 'inconnu')
        if PREDICTION_LOG_AVAILABLE:
            try:
                PredictionLog.objects.create(
                    patient_id=str(patient_id),
                    prediction_type=prediction_type,
                    model=model_label,
                    score=score,
                    risk_level=risk_level,
                    features_used=feature_keys_trained,
                )
            except Exception:
                pass  # Ne pas bloquer la réponse si la sauvegarde échoue

        return Response(
            {
                'prediction_type': prediction_type,
                'model': model_label,
                'score': score,
                'probability': round(probability, 4),
                'risk_level': risk_level,
                'recommendation': recommendation,
                'factors': factors,
                'features_used': feature_keys_trained,
                'n_features': len(feature_keys_trained),
                'doietal_risk_score': doi_score,
                'doietal_risk_category': doi_category,
                'selected_data_risk_score': selected_data_risk.get('score') if selected_data_risk else None,
                'selected_data_risk_category': selected_data_risk.get('category') if selected_data_risk else None,
            },
            status=status.HTTP_200_OK,
        )


class PredictionHistoryView(APIView):
    """
    GET /predictions/history/?days=30
    Retourne l'historique des prédictions sur la période demandée.
    """
    def get(self, request):
        if not PREDICTION_LOG_AVAILABLE:
            # Retour propre avec liste vide si le modèle n'existe pas encore
            return Response([], status=status.HTTP_200_OK)

        try:
            period_days = int(request.query_params.get('days', 30))
            if period_days <= 0:
                period_days = 30
        except (ValueError, TypeError):
            period_days = 30

        cutoff = datetime.now() - timedelta(days=period_days)
        logs = (
            PredictionLog.objects
            .filter(created_at__gte=cutoff)
            .order_by('-created_at')
            .values(
                'id',
                'patient_id',
                'prediction_type',
                'model',
                'score',
                'risk_level',
                'created_at',
            )
        )
        return Response(list(logs), status=status.HTTP_200_OK)


class PredictionMetricsView(APIView):
    """
    GET /predictions/metrics/?prediction_type=mortalite
    Retourne les métriques des modèles entraînés pour un type de prédiction.
    """
    def get(self, request):
        prediction_type = request.query_params.get('prediction_type')
        if prediction_type not in ('mortalite', 'coagulation'):
            return Response(
                {'error': 'prediction_type doit être "mortalite" ou "coagulation".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        model_map = get_model_map()
        metrics = {}
        for name in model_map:
            model_path = get_model_path(prediction_type, name)
            features_path = get_features_path(prediction_type, name)
            if model_path.exists():
                metadata = load_feature_metadata(features_path) if features_path.exists() else {'feature_keys': [], 'threshold': 0.5, 'class_distribution': None, 'metrics': None}
                metrics[name] = {
                    'trained': True,
                    'feature_count': len(metadata['feature_keys']),
                    'feature_keys': metadata['feature_keys'],
                    'threshold': metadata.get('threshold', 0.5),
                    'class_distribution': metadata.get('class_distribution'),
                    'metrics': metadata.get('metrics'),
                }
            else:
                metrics[name] = {'trained': False}

        return Response({'prediction_type': prediction_type, 'models': metrics}, status=status.HTTP_200_OK)


class PredictionPatientView(APIView):
    """
    POST /predictions/predict-patient/
    Body: {
        "prediction_type": "mortalite"|"coagulation",
        "patient_id": <int>
    }

    Effectue une prédiction automatique pour un patient.
    Extrait automatiquement toutes les features disponibles depuis la base de données
    et utilise le modèle SVM Linéaire entraîné.
    """
    def post(self, request):
        prediction_type = request.data.get('prediction_type')
        patient_id = request.data.get('patient_id')

        # ── Validation des entrées ────────────────────────────────────────────
        if prediction_type not in ('mortalite', 'coagulation'):
            return Response(
                {'error': 'prediction_type doit être "mortalite" ou "coagulation".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not patient_id:
            return Response(
                {'error': 'patient_id est requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Chargement du patient ─────────────────────────────────────────────
        try:
            patient = Patient.objects.get(id=patient_id)
        except Patient.DoesNotExist:
            return Response(
                {'error': f'Patient avec ID {patient_id} non trouvé.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── Chargement du modèle SVM ──────────────────────────────────────────
        best_path = get_best_path(prediction_type)
        best_features_path = get_best_features_path(prediction_type)

        if not best_path.exists() or not best_features_path.exists():
            trained, error_msg = ensure_trained_models(prediction_type, None)
            if not trained:
                return Response(
                    {'error': error_msg or 'Aucun modèle entraîné trouvé et l\'entraînement automatique a échoué.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        feature_metadata = load_feature_metadata(best_features_path) if best_features_path.exists() else {'feature_keys': ALL_KNOWN_FEATURES, 'threshold': 0.5}
        feature_keys_trained = feature_metadata['feature_keys']

        try:
            pipeline = joblib.load(best_path)
        except Exception as exc:
            return Response(
                {'error': f'Erreur lors du chargement du modèle : {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Extraction des features depuis le patient ──────────────────────────
        row = extract_features_from_patient(patient, feature_keys_trained)
        doi_score = row.get('doietal_risk_score')
        doi_score = float(round(doi_score, 2)) if isinstance(doi_score, float) and not np.isnan(doi_score) else None
        doi_category = None
        if doi_score is not None:
            if doi_score <= 4:
                doi_category = 'Faible'
            elif doi_score <= 6:
                doi_category = 'Modéré'
            elif doi_score <= 8:
                doi_category = 'Élevé'
            else:
                doi_category = 'Très élevé'

        input_df = pd.DataFrame([row], columns=feature_keys_trained)

        # ── Prédiction ────────────────────────────────────────────────────────
        try:
            probability = float(pipeline.predict_proba(input_df)[:, 1][0])
        except AttributeError:
            # Fallback pour modèles sans predict_proba
            try:
                raw = float(pipeline.decision_function(input_df)[0])
                probability = float(1 / (1 + np.exp(-raw)))
            except Exception as exc:
                return Response(
                    {'error': f'Erreur lors de la prédiction : {str(exc)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as exc:
            return Response(
                {'error': f'Erreur lors de la prédiction : {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        score = round(float(np.clip(probability * 100, 0, 100)), 1)
        risk_level = 'Faible' if score <= 30 else 'Modéré' if score <= 70 else 'Élevé'
        factors = build_interpretation(pipeline, feature_keys_trained)

        # ── Recommandation clinique ────────────────────────────────────────────
        if risk_level == 'Élevé':
            recommendation = (
                'Risque élevé détecté : surveillance intensive recommandée, '
                'adaptation thérapeutique urgente et consultation spécialisée.'
            )
        elif risk_level == 'Modéré':
            recommendation = (
                'Risque modéré : suivi renforcé, optimisation des paramètres cliniques '
                'et réévaluation à court terme.'
            )
        else:
            recommendation = (
                'Risque faible : maintien du suivi standard avec contrôle périodique.'
            )

        # ── Sauvegarde dans l'historique ──────────────────────────────────────
        if PREDICTION_LOG_AVAILABLE:
            try:
                PredictionLog.objects.create(
                    patient_id=str(patient_id),
                    prediction_type=prediction_type,
                    model='svm_linear',
                    score=score,
                    risk_level=risk_level,
                    features_used=feature_keys_trained,
                )
            except Exception:
                pass  # Ne pas bloquer la réponse si la sauvegarde échoue

        return Response(
            {
                'prediction_type': prediction_type,
                'model': 'svm_linear',
                'patient_id': patient_id,
                'score': score,
                'probability': round(probability, 4),
                'risk_level': risk_level,
                'recommendation': recommendation,
                'factors': factors,
                'features_used': feature_keys_trained,
                'n_features': len(feature_keys_trained),
                'doietal_risk_score': doi_score,
                'doietal_risk_category': doi_category,
            },
            status=status.HTTP_200_OK,
        )