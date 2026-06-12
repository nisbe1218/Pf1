"""
Mapping entre les noms de features du projet ML (HD-478) et les champs du modèle Patient.
Utilisé pour l'interprétabilité et la documentation — le pipeline de prédiction utilise
directement les noms de champs plateforme via extract_features_from_patient() de views.py.
"""
import numpy as np

# ── Mapping : nom feature ML → champ Patient Django ──────────────────────────
PLATFORM_FIELD_MAP = {
    # Biologie
    'albumine_basale':              'biologie_albumine_g_l',
    'calcium_basale':               'biologie_calcium_corrige_mg_l',
    'pth_basale':                   'biologie_pth_pg_ml',
    'ferritine_basale':             'biologie_ferritine_ng_ml',
    'sodium_basal':                 'biologie_sodium_mmol_l',
    # Dialyse numériques
    'seances_par_semaine':          'dialyse_seances_par_semaine',
    # Démographie
    'age_annees':                   'demographie_age_ans',
    # Charlson
    'Charlson':                     'icc_charlson',
}

# Champs binaires oui/non (ou 0/1) à convertir via _to_binary
BINARY_FIELD_MAP = {
    'liste_attente_transplantation':      'dialyse_statut_liste_attente_transplantation',
    'information_transplantation_donnee': 'dialyse_information_transplantation_donnee',
    'maladie_renale_hereditaire':         'irc_maladie_renale_hereditaire',
    # du_residuelle → dialyse_statut_fonction_renale_residuelle (import Excel direct)
    # ou extra_data['du_residuelle'] (colonne dynamique legacy)
    'du_residuelle':                      'dialyse_statut_fonction_renale_residuelle',
}

# Couverture médicale : variable catégorielle 0–3 stockée en texte dans la plateforme
COUVERTURE_MEDICALE_CODES = {
    'auto_paiement': 0.0,
    'ramed':         1.0,
    'amo':           2.0,
    'autre_assurance_publique': 3.0,
}

# Encoding ordinal de l'étiologie MRC (classé par fréquence dans la cohorte)
ETIOLOGIE_MRC_CODES = {
    'nephropathie_indeterminee':      1,
    'nephropathie_diabetique':        2,
    'glomerulonephrite_membraneuse':  3,
    'vascularite_anca':               4,
    'uropathie_obstructive':          5,
    'nephroangiosclerose':            6,
    'amylose_myelome':                7,
    'maladie_renale_polykystique':    8,
    'nephropathie_lupique':           9,
    'nephropathie_a_iga':             10,
    'autre':                          11,
}

# Features détectées par recherche de mots-clés dans les champs texte
KEYWORD_FEATURES = {
    'hemodialyse': {
        'field': 'dialyse_modalite_actuelle',
        'keywords': ['hemodialyse', 'hémodialyse', 'hd', 'hemodiafiltration'],
        'fallback_field': 'dialyse_modalite_initiale',
    },
    'dyspnee': {
        'field': 'presentation_symptomes',
        'keywords': ['dyspnee', 'dyspnée', 'essoufflement', 'detresse respiratoire'],
    },
    'oedemes_surcharge': {
        'field': 'presentation_symptomes',
        'keywords': ['oedeme', 'œdème', 'surcharge', 'edeme'],
    },
    'crise_convulsive': {
        'field': 'complication_liste',
        'keywords': ['convulsion', 'epilepsie', 'épilepsie', 'crise'],
    },
    'douleur_abdominale': {
        'field': 'presentation_symptomes',
        'keywords': ['douleur abdominale', 'douleurs abdominales', 'abdominal'],
    },
    'evenement_cardiovasculaire': {
        'field': 'complication_liste',
        'keywords': ['cardiovasculaire', 'infarctus', 'avc', 'ictus', 'coronaire'],
    },
    'hypertension': {
        'field': 'comorbidite_liste',
        'keywords': ['hypertension', 'hta'],
    },
    'cardiopathie': {
        'field': 'comorbidite_liste',
        'keywords': ['cardiopathie', 'insuffisance cardiaque', 'cardiomyopathie'],
    },
}

# 24 features cliniques du projet ML
FEATURES_CLINIQUES = [
    'fistule_arterioveineuse_creee', 'couverture_medicale', 'albumine_basale',
    'calcium_basale', 'admission_cathetere_tunnellise', 'annee_inclusion',
    'ferritine_basale', 'seances_par_semaine', 'nombre_hospitalisations',
    'du_residuelle', 'crise_convulsive', 'pth_basale', 'etiologie_mrc',
    'douleur_abdominale', 'diabete', 'evenement_cardiovasculaire', 'dyspnee',
    'oedemes_surcharge', 'hemodialyse', 'liste_attente_transplantation',
    'maladie_renale_hereditaire', 'information_transplantation_donnee',
    'hypertension', 'cardiopathie',
]

# 8 features d'interaction
FEATURES_INTERACTION = [
    'age_x_charlson', 'dyspnee_x_oedeme', 'sodium_lt130', 'charlson_x_hosp',
    'hypert_x_cardio', 'albumine_x_hosp', 'albumine_lt35', 'age_x_cardio',
]

ALL_FEATURES = FEATURES_CLINIQUES + FEATURES_INTERACTION


def _get_field(patient, field_name):
    """Lit un champ du Patient (direct ou dans extra_data)."""
    val = getattr(patient, field_name, None)
    if (val is None or val == '') and hasattr(patient, 'extra_data') and isinstance(patient.extra_data, dict):
        val = patient.extra_data.get(field_name)
    return val


def _to_float(value):
    if value is None or value == '':
        return None
    try:
        return float(str(value).replace(',', '.').strip())
    except (ValueError, TypeError):
        return None


def _to_binary(value):
    """Convertit oui/non/1/0 en float binaire. Retourne None si inconnu."""
    if value is None or value == '':
        return None
    s = str(value).strip().lower()
    if s in ('oui', 'yes', '1', 'true', 'vrai'):
        return 1.0
    if s in ('non', 'no', '0', 'false', 'faux'):
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _keyword_present(patient, feature_name):
    """Détecte une feature binaire : extra_data en priorité, puis mots-clés dans le texte."""
    # Priorité 1 : valeur binaire directe depuis extra_data (import Excel colonne directe)
    ed = getattr(patient, 'extra_data', None) or {}
    if isinstance(ed, dict):
        direct = ed.get(feature_name)
        if direct is not None and direct != '':
            v = _to_binary(direct)
            if v is not None:
                return v

    cfg = KEYWORD_FEATURES.get(feature_name)
    if not cfg:
        return None
    raw = _get_field(patient, cfg['field']) or ''
    if not raw and cfg.get('fallback_field'):
        raw = _get_field(patient, cfg['fallback_field']) or ''
    text = str(raw).lower()
    return 1.0 if any(kw in text for kw in cfg['keywords']) else 0.0


def _get_nombre_hospitalisations(patient):
    """
    Lit complication_nombre_hospitalisations.
    Gère les valeurs textuelles 'oui'→1, 'non'→0, et les entiers.
    """
    raw = _get_field(patient, 'complication_nombre_hospitalisations')
    if raw is None or raw == '':
        return None
    s = str(raw).strip().lower()
    if s == 'non':
        return 0.0
    if s == 'oui':
        return 1.0
    return _to_float(raw)


def _get_fistule(patient):
    """Détecte la création d'une FAV depuis dialyse_type_acces_initial."""
    val = _get_field(patient, 'dialyse_type_acces_initial') or ''
    return 1.0 if 'fistule' in str(val).lower() else 0.0


def _get_catheter_tunnellise(patient):
    """Détecte un cathéter tunnellisé depuis dialyse_type_acces_initial."""
    val = _get_field(patient, 'dialyse_type_acces_initial') or ''
    return 1.0 if 'tunnellise' in str(val).lower() or 'tunnelise' in str(val).lower() else 0.0


def _get_etiologie_mrc(patient):
    """Encode l'étiologie MRC en valeur ordinale."""
    raw = _get_field(patient, 'irc_etiologie_principale')
    if not raw:
        return None
    key = str(raw).strip().lower()
    return float(ETIOLOGIE_MRC_CODES.get(key, ETIOLOGIE_MRC_CODES['autre']))


def _get_diabete(patient):
    """
    Détecte le diabète depuis :
    1. comorbidite_statut_diabete (oui/non)
    2. irc_etiologie_principale == 'nephropathie_diabetique'
    3. comorbidite_liste avec mots-clés
    """
    # Source 1 : champ dédié
    statut = _get_field(patient, 'comorbidite_statut_diabete')
    if statut:
        val = _to_binary(statut)
        if val is not None:
            return val

    # Source 2 : étiologie rénale diabétique
    etiologie = _get_field(patient, 'irc_etiologie_principale') or ''
    if 'diabetique' in str(etiologie).lower() or 'diabète' in str(etiologie).lower():
        return 1.0

    # Source 3 : comorbidite_liste
    comorbidites = _get_field(patient, 'comorbidite_liste') or ''
    text = str(comorbidites).lower()
    if any(kw in text for kw in ['diabete', 'diabète', 'diabetes', 'dbt']):
        return 1.0

    return 0.0


def extract_features_for_patient(patient):
    """
    Extrait les 32 features (24 cliniques + 8 interactions) depuis un objet Patient.
    Mappe les noms du projet ML vers les champs réels de la plateforme.

    Returns:
        dict: {feature_name: value_or_None}
    """
    features = {}

    for feat in FEATURES_CLINIQUES:
        # Couverture médicale : catégorielle 0–3 (auto_paiement/ramed/amo/autre)
        if feat == 'couverture_medicale':
            raw = _get_field(patient, 'demographie_couverture_sociale')
            if raw is None or raw == '':
                features[feat] = None
            else:
                s = str(raw).strip().lower()
                # Texte décodé → nombre
                if s in COUVERTURE_MEDICALE_CODES:
                    features[feat] = COUVERTURE_MEDICALE_CODES[s]
                else:
                    features[feat] = _to_float(raw)
            continue

        # Champs numériques directs
        if feat in PLATFORM_FIELD_MAP:
            raw = _get_field(patient, PLATFORM_FIELD_MAP[feat])
            features[feat] = _to_float(raw)

        # Champs binaires oui/non
        elif feat in BINARY_FIELD_MAP:
            if feat == 'du_residuelle':
                # Priorité 1 : extra_data['du_residuelle'] (valeur 0/1 directe depuis import Excel)
                ed_val = (getattr(patient, 'extra_data', None) or {}).get('du_residuelle')
                if ed_val is not None and ed_val != '':
                    features[feat] = _to_binary(ed_val)
                else:
                    # Priorité 2 : champ structuré dialyse_statut_fonction_renale_residuelle
                    raw = _get_field(patient, BINARY_FIELD_MAP[feat])
                    features[feat] = _to_binary(raw)
            else:
                raw = _get_field(patient, BINARY_FIELD_MAP[feat])
                features[feat] = _to_binary(raw)

        # Champs à logique spéciale
        elif feat == 'fistule_arterioveineuse_creee':
            features[feat] = _get_fistule(patient)

        elif feat == 'admission_cathetere_tunnellise':
            features[feat] = _get_catheter_tunnellise(patient)

        elif feat == 'nombre_hospitalisations':
            features[feat] = _get_nombre_hospitalisations(patient)

        elif feat == 'etiologie_mrc':
            features[feat] = _get_etiologie_mrc(patient)

        elif feat == 'diabete':
            features[feat] = _get_diabete(patient)

        elif feat == 'annee_inclusion':
            # Le modèle a été entraîné sur un encodage ordinal : 0=2020, 1=2021, ..., 4=2024
            # Priorité : extra_data['annee_inclusion'] (valeur directe du Excel si importée)
            # puis dialyse_date_debut pour dériver l'année
            ed_val = (getattr(patient, 'extra_data', None) or {}).get('annee_inclusion')
            if ed_val is not None and ed_val != '':
                v = _to_float(ed_val)
                # Si la valeur est déjà un ordinal 0-4 on la garde, sinon on convertit
                features[feat] = v if (v is not None and 0 <= v <= 10) else (float(v - 2020) if v and v > 2000 else v)
            else:
                raw = _get_field(patient, 'dialyse_date_debut') or _get_field(patient, 'date_evaluation_initiale')
                if raw:
                    try:
                        from datetime import date, datetime
                        if isinstance(raw, (date, datetime)):
                            features[feat] = float(raw.year - 2020)
                        else:
                            year = int(str(raw)[:4])
                            features[feat] = float(year - 2020) if 1990 <= year <= 2050 else None
                    except Exception:
                        features[feat] = None
                else:
                    features[feat] = None

        elif feat in KEYWORD_FEATURES:
            features[feat] = _keyword_present(patient, feat)

        else:
            features[feat] = None

    # Variables pour les interactions
    age = _to_float(_get_field(patient, 'demographie_age_ans') or _get_field(patient, 'age'))
    charlson = _to_float(_get_field(patient, 'icc_charlson'))
    sodium = _to_float(_get_field(patient, 'biologie_sodium_mmol_l'))
    albumine = features.get('albumine_basale')
    dyspnee = features.get('dyspnee')
    oedemes = features.get('oedemes_surcharge')
    hosp = features.get('nombre_hospitalisations')
    hypert = features.get('hypertension')
    cardio = features.get('cardiopathie')

    def safe_mult(a, b):
        if a is not None and b is not None:
            try:
                return float(a * b)
            except Exception:
                return None
        return None

    features['age_x_charlson'] = safe_mult(age, charlson)
    features['dyspnee_x_oedeme'] = safe_mult(dyspnee, oedemes)
    features['sodium_lt130'] = (1.0 if sodium < 130 else 0.0) if sodium is not None else None
    features['charlson_x_hosp'] = safe_mult(charlson, hosp)
    features['hypert_x_cardio'] = safe_mult(hypert, cardio)
    features['albumine_x_hosp'] = safe_mult(albumine, hosp)
    features['albumine_lt35'] = (1.0 if albumine < 35 else 0.0) if albumine is not None else None
    features['age_x_cardio'] = safe_mult(age, cardio)

    return features


def get_feature_order():
    """Ordre exact des 32 features pour le modèle ML."""
    return ALL_FEATURES


def features_dict_to_dataframe(features_dict):
    """
    Convertit un dict de features en DataFrame pandas dans l'ordre correct.
    À utiliser avec un modèle entraîné sur les noms de features ML (pas plateforme).
    """
    import pandas as pd
    feature_order = get_feature_order()
    row = {f: features_dict.get(f, np.nan) for f in feature_order}
    return pd.DataFrame([row], columns=feature_order)


def features_dict_to_array(features_dict):
    """
    Convertit un dict de features en numpy array shape (1, 32) dans l'ordre correct.
    Remplace les None par np.nan pour imputation par le pipeline.
    """
    feature_order = get_feature_order()
    arr = np.array([[features_dict.get(f, np.nan) for f in feature_order]], dtype=np.float64)
    return arr
