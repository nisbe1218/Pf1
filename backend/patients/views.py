import unicodedata
import re
import uuid
import json
import ast
import os
import io
import logging
from datetime import datetime, timedelta
from http.client import RemoteDisconnected
from urllib import request as urllib_request
from urllib import error as urllib_error

import numpy as np
import pandas as pd
from django.db import connection
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.http import HttpResponse
from openpyxl import Workbook, load_workbook
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdminOrChefService, CanViewPatients
from rest_framework.permissions import AllowAny
from audit.models import AuditLog

from .models import Patient, PatientFormField, PatientFormTemplate
from .serializers import PatientFormTemplateSerializer, PatientSerializer
from .preprocess_rag import _env_int, build_medical_rag_context, build_rag_context, estimate_route


logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, datetime):
            return obj.isoformat()
        obj_module = getattr(obj.__class__, '__module__', '')
        if obj_module.startswith('numpy'):
            if hasattr(obj, 'tolist'):
                try:
                    return obj.tolist()
                except Exception:
                    pass
            if hasattr(obj, 'item'):
                try:
                    return obj.item()
                except Exception:
                    pass
            return str(obj)
        return super().default(obj)


def _safe_json_value(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return None if value != value else value

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]

    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()

    if isinstance(value, pd.Series):
        return [_safe_json_value(item) for item in value.tolist()]

    if isinstance(value, pd.DataFrame):
        return [_safe_json_value(row) for row in value.to_dict(orient='records')]

    value_module = getattr(value.__class__, '__module__', '')
    if value_module.startswith('numpy'):
        if hasattr(value, 'tolist'):
            try:
                return _safe_json_value(value.tolist())
            except Exception:
                pass
        if hasattr(value, 'item'):
            try:
                return _safe_json_value(value.item())
            except Exception:
                pass

    if hasattr(value, 'to_pydatetime'):
        try:
            return value.to_pydatetime().isoformat()
        except Exception:
            pass

    if hasattr(value, 'isoformat'):
        try:
            return value.isoformat()
        except Exception:
            pass

    if hasattr(value, 'to_dict'):
        try:
            return _safe_json_value(value.to_dict())
        except Exception:
            pass

    return str(value)


# ============================================================
# FONCTIONS UTILITAIRES DE BASE
# ============================================================

def normalize_header(value):
    text = unicodedata.normalize('NFKD', str(value).strip().lower())
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')


def _format_patient_audit_value(value):
    if value in [None, '']:
        return '-'
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(value)
    return str(value)


def _describe_patient_changes(before_data, after_data, max_changes=5):
    changes = []
    before_data = before_data or {}
    after_data = after_data or {}

    keys = sorted(set(before_data.keys()) | set(after_data.keys()))
    for key in keys:
        if key in {'id', 'created_at', 'updated_at'}:
            continue
        before_value = _format_patient_audit_value(before_data.get(key))
        after_value = _format_patient_audit_value(after_data.get(key))
        if before_value == after_value:
            continue
        changes.append(f"{key}: {before_value} -> {after_value}")
        if len(changes) >= max_changes:
            break

    if not changes:
        return "aucun champ notable modifié"

    remaining = max(0, len(keys) - len(changes))
    suffix = f" (+{remaining} autre(s) champ(s))" if remaining > 0 else ''
    return '; '.join(changes) + suffix


# Plage raisonnable de serial Excel : du 01/01/1990 au 31/12/2099
_EXCEL_SERIAL_MIN = 32874   # 01/01/1990
_EXCEL_SERIAL_MAX = 73050   # 31/12/2099
_EXCEL_EPOCH = datetime(1899, 12, 30)


def excel_serial_to_date_iso(value):
    """Convertit un serial Excel (entier) en chaîne ISO YYYY-MM-DD, ou None si hors plage."""
    try:
        ival = int(float(value))
        if _EXCEL_SERIAL_MIN <= ival <= _EXCEL_SERIAL_MAX:
            return (_EXCEL_EPOCH + timedelta(days=ival)).date().isoformat()
    except (ValueError, TypeError):
        pass
    return None


def convert_excel_value(value):
    if pd.isna(value):
        return None

    if hasattr(value, 'item') and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except Exception:
            pass

    # Objet datetime/date pandas ou Python
    if hasattr(value, 'to_pydatetime'):
        return value.to_pydatetime().date().isoformat()

    if hasattr(value, 'date') and not isinstance(value, str):
        try:
            return value.date().isoformat()
        except Exception:
            return str(value)

    # Entier ou flottant
    if isinstance(value, (int, float)):
        fval = float(value)
        if fval != fval:  # NaN
            return None
        if fval.is_integer():
            ival = int(fval)
            # Essayer la conversion serial Excel avant de retourner l'entier brut
            date_iso = excel_serial_to_date_iso(ival)
            if date_iso:
                return date_iso
            return ival
        return fval

    if hasattr(value, 'isoformat') and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass

    # Chaîne : tenter de détecter un serial ou une date texte
    if isinstance(value, str):
        stripped = value.strip()
        # Chaîne purement numérique → tester serial Excel
        if stripped.isdigit():
            date_iso = excel_serial_to_date_iso(int(stripped))
            if date_iso:
                return date_iso
        return stripped

    return value


def normalize_type(value):
    normalized = normalize_header(value).replace('_', ' ')
    TYPE_MAP = {
        'texte libre court': 'text_short',
        'texte libre long': 'text_long',
        'liste a choix unique': 'single_choice',
        'liste a choix multiple': 'multiple_choice',
        'selecteur de date': 'date',
        'nombre entier': 'integer',
        'nombre decimal': 'decimal',
        'oui/non': 'boolean',
        'genere automatiquement': 'auto',
    }
    return TYPE_MAP.get(normalized, 'text_short')


def parse_flexible_date(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    parsed = parse_date(text)
    if parsed:
        return parsed.isoformat()

    for dayfirst in [True, False]:
        try:
            dt = pd.to_datetime(text, errors='coerce', dayfirst=dayfirst)
            if pd.notna(dt):
                return dt.date().isoformat()
        except Exception:
            continue

    return None


def normalize_age_value(value):
    if value in [None, '']:
        return None

    try:
        age_value = int(float(str(value).strip()))
        if age_value < 0:
            return None
        return age_value
    except Exception:
        return None


def derive_age_from_date_of_birth(date_iso):
    if not date_iso:
        return None

    birth_date = parse_date(str(date_iso))
    if not birth_date:
        return None

    today = timezone.localdate()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age if age >= 0 else None


def derive_date_of_birth_from_age(age_value):
    normalized_age = normalize_age_value(age_value)
    if normalized_age is None:
        return None
    target_year = timezone.localdate().year - normalized_age
    return f"{target_year}-01-01"


def normalize_sex_values(value):
    if value is None:
        return None, None

    value_str = str(value).strip().lower()

    if value_str in ['1', '1.0']:
        return 'M', 'homme'
    if value_str in ['0', '0.0']:
        return 'F', 'femme'

    normalized = normalize_header(value_str)
    if normalized in ['m', 'male', 'masculin', 'homme', 'man']:
        return 'M', 'homme'
    if normalized in ['f', 'female', 'feminin', 'femme', 'woman']:
        return 'F', 'femme'
    if normalized in ['i', 'intersex', 'intersexe']:
        return 'O', 'intersexe'
    if normalized in ['unknown', 'inconnu', 'na', 'n_a', 'none', 'null', '', '9', '9.0']:
        return 'O', 'inconnu'
    return 'O', 'inconnu'


# ============================================================
# DÉCODAGE DES VALEURS NUMÉRIQUES CODÉES
# ============================================================

# Tables de correspondance complètes (issues du fichier Excel de référence)
_DECODE_MAPS = {
    # Démographie
    'sexe': {1: 'homme', 0: 'femme'},
    'demographie_sexe': {1: 'homme', 0: 'femme'},
    'couverture_sociale': {
        0: 'auto_paiement',
        1: 'ramed',
        2: 'amo',
        3: 'autre_assurance_publique',
    },
    'couverture_medicale': {
        0: 'auto_paiement',
        1: 'ramed',
        2: 'amo',
        3: 'autre_assurance_publique',
    },
    'demographie_couverture_sociale': {
        0: 'auto_paiement',
        1: 'ramed',
        2: 'amo',
        3: 'autre_assurance_publique',
    },

    # IRC / étiologie
    'etiologie_mrc': {
        1: 'nephropathie_diabetique',
        2: 'nephropathie_indeterminee',
        3: 'vascularite_anca',
        4: 'maladie_renale_polykystique',
        5: 'nephroangiosclerose',
        6: 'uropathie_obstructive',
        7: 'nephropathie_lupique',
        8: 'glomerulonephrite_membraneuse',
        9: 'nephropathie_a_iga',
        10: 'lgm_hsf',
        11: 'amylose_myelome',
        12: 'gn_crescentique',
        13: 'syndrome_hemolytique_et_uremique',
        14: 'glomerulopathie_c3',
        15: 'necrose_corticale',
    },
    'irc_etiologie_principale': {
        1: 'nephropathie_diabetique',
        2: 'nephropathie_indeterminee',
        3: 'vascularite_anca',
        4: 'maladie_renale_polykystique',
        5: 'nephroangiosclerose',
        6: 'uropathie_obstructive',
        7: 'nephropathie_lupique',
        8: 'glomerulonephrite_membraneuse',
        9: 'nephropathie_a_iga',
        10: 'lgm_hsf',
        11: 'amylose_myelome',
        12: 'gn_crescentique',
        13: 'syndrome_hemolytique_et_uremique',
        14: 'glomerulopathie_c3',
        15: 'necrose_corticale',
    },
    'groupe_etiologie_mrc': {
        1: 'diabete',
        2: 'nephroangiosclerose',
        3: 'polykystose',
        4: 'uropathie_obstructive',
        5: 'lupus',
        6: 'vascularite',
        7: 'autre_glomerulaire',
        8: 'autre',
        9: 'indeterminee',
    },

    # Dialyse
    'type_acces_initial': {
        1: 'cathetere_femoral',
        2: 'cathetere_tunnellise',
        3: 'fistule_arterioveineuse',
        4: 'cathetere_peritoneal',
    },
    'dialyse_type_acces_initial': {
        1: 'cathetere_femoral',
        2: 'cathetere_tunnellise',
        3: 'fistule_arterioveineuse',
        4: 'cathetere_peritoneal',
    },
    'fistule_arterioveineuse': {1: 'oui', 0: 'non'},
    'fistule_arterioveineuse_c': {1: 'oui', 0: 'non'},
    'groupe_jours_entre_cathetere': {
        0: 'pas_d_intervalle',
        1: '0_30_jours',
        2: '31_181_jours',
        3: 'plus_de_180_jours',
    },
    'dialyse_jours_entre_catheter_et_fav': {
        0: 'pas_d_intervalle',
        1: '0_30_jours',
        2: '31_181_jours',
        3: 'plus_de_180_jours',
    },

    # Statut diurèse
    'statut_diurese': {1: 'anurique', 2: 'diurese_preservee'},
    'presentation_statut_diurese': {1: 'anurique', 2: 'diurese_preservee'},

    # Devenir / décès
    'deces': {1: 'oui', 0: 'non', 9: 'inconnu'},
    'cause_deces': {
        1: 'cardiovasculaire',
        2: 'infection',
        3: 'hemorragique',
        4: 'autre',
        5: 'indeterminee',
    },
    'devenir_cause_deces': {
        1: 'cardiovasculaire',
        2: 'infection',
        3: 'hemorragique',
        4: 'autre',
        5: 'indeterminee',
    },
}

# Colonnes déjà fusionnées dans comorbidite_liste — ne doivent jamais apparaître
# comme colonnes séparées dans la structure de la plateforme
_COLUMNS_FUSED_INTO_COMORBIDITE_LISTE = {
    'exposition_toxique',
    'comorbidite_exposition_toxique',
    'antecedents_medicaments_nephrotoxiques',
    'comorbidite_antecedents_medicaments_nephrotoxiques',
}

# Colonnes booléennes simples (1 → oui, 0 → non)
_BOOLEAN_COLUMNS = {
    'hypertension', 'cardiopathie', 'hemodialyse', 'dialyse_peritoneale',
    'debut_dialyse_urgence', 'debut_dialyse_planifie',
    'cause_deces_cardiaque', 'cause_deces_infectieuse',
    'irc_maladie_renale_hereditaire', 'irc_antecedents_familiaux_renaux',
    'irc_connue_avant_dialyse',
    'dialyse_information_transplantation_donnee',
    'irc_themes_education_therapeutique',
    'biopsie_renale', 'maladie_renale_hereditaire',
    'uropathie_obstructive', 'goutte', 'exposition_toxique',
    'antecedents_medicaments_nephrotoxiques',
    'asthenie', 'douleur_abdominale', 'nausees', 'prurit',
    'asymptomatique', 'trouble_conscience',
    'infection', 'trouble_electrolytique', 'evenement_cardiovasculaire',
    'hemorragie', 'dysfonction_acces', 'crise_convulsive',
    'information_transplantation', 'information_transplantation_donnee',
    'liste_attente_transplantation', 'transplantation_renale',
    'immunisation_transfusion_sanguine', 'bilan_pretransplantation',
    'debut_dialyse_urgence', 'debut_dialyse_planifie',
    'changement_hd_vers_dp', 'changement_dp_vers_hd',
}

def is_binary_column(column_data):
    """
    Détermine si une colonne est binaire (contient uniquement 0/1 et variantes).
    column_data: liste des valeurs de la colonne (non None)
    Retourne True si toutes les valeurs non vides sont 0 ou 1 (ou 0.0/1.0)
    """
    if not column_data:
        return False
    
    for value in column_data:
        if value is None or value == '':
            continue
        
        try:
            # Convertir en float pour gérer 0.0 et 1.0
            num_value = float(value)
            if num_value not in (0.0, 1.0):
                return False
        except (ValueError, TypeError):
            # Si ce n'est pas un nombre, ce n'est pas binaire
            return False
    
    return True
def decode_numeric_value(column_name, value):
    """Convertit les valeurs numériques codées en libellés textuels."""
    if value is None or value == '':
        return value

    col = normalize_header(str(column_name))

    # Chercher dans les tables de décodage
    decode_map = _DECODE_MAPS.get(col)
    if decode_map:
        try:
            return decode_map.get(int(float(value)), value)
        except (ValueError, TypeError):
            return value

    # Colonnes booléennes simples
    if col in _BOOLEAN_COLUMNS:
        try:
            val_int = int(float(value))
            return 'oui' if val_int == 1 else 'non'
        except (ValueError, TypeError):
            return value

    # Détection générique : si la valeur est strictement 0 ou 1 (entier), convertir en oui/non
    try:
        val_str = str(value).strip()
        if val_str in ('0', '1'):
            return 'oui' if val_str == '1' else 'non'
    except Exception:
        pass

    return value


def extract_charlson_score(value):
    """Extrait le score Charlson d'une valeur potentiellement mal formatée."""
    if value is None or value == '':
        return None

    str_value = str(value).strip()

    try:
        return int(float(str_value))
    except (ValueError, TypeError):
        pass

    numbers = re.findall(r'\d+', str_value)
    if numbers:
        return int(numbers[0])

    return None


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    normalized = normalize_header(value)
    return normalized in ['1', 'true', 'yes', 'oui', 'y']


def _is_falsey(value):
    if isinstance(value, bool):
        return not value
    normalized = normalize_header(value)
    return normalized in ['0', 'false', 'no', 'non', 'aucun', 'none', 'null', 'na', 'n_a', '']


def _pg_quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _pg_quote_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


# ============================================================
# CHARGEMENT AUTOMATIQUE DU MAPPING DEPUIS column_mapping.json
# ============================================================

def load_column_mapping():
    """Charge le mapping depuis le fichier JSON."""
    mapping_file = os.path.join(os.path.dirname(__file__), 'column_mapping.json')
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping_list = json.load(f)

        column_mapping = {}
        for item in mapping_list:
            main_key = normalize_header(item['main'])
            platform_key = normalize_header(item['platform'])
            transformation = item['transformation']

            if transformation == 'direct':
                transform_type = 'direct'
            elif transformation == 'calcul (age → date naissance estimée)':
                transform_type = 'calcul_age_to_birthdate'
            elif transformation in [
                'fusion (urgence/planifié → contexte)',
                'fusion (hd/dp → modalité)',
                'fusion (cardiaque/infectieux → cause)',
                'fusion (hd→dp / dp→hd → changement)',
            ]:
                transform_type = transformation
            elif 'fusion' in transformation or 'inclus dans' in transformation:
                transform_type = transformation
            else:
                transform_type = 'direct'

            column_mapping[main_key] = {
                'platform': platform_key,
                'type': transform_type,
                'original_main': item['main'],
                'original_platform': item['platform'],
            }

        return column_mapping
    except Exception as e:
        print(f"Erreur chargement mapping: {e}")
        return get_default_mapping()


def get_default_mapping():
    """Mapping par défaut — couvre les colonnes les plus fréquentes."""
    return {
        'identifiant_patient': {'platform': 'id_patient', 'type': 'direct'},
        'sexe': {'platform': 'demographie_sexe', 'type': 'direct'},
        'age_annees': {'platform': 'demographie_date_naissance', 'type': 'calcul_age_to_birthdate'},
        'distance_au_centre': {'platform': 'demographie_distance_centre_km', 'type': 'direct'},
        'etiologie_mrc': {'platform': 'irc_etiologie_principale', 'type': 'direct'},
        'charlson': {'platform': 'icc_charlson', 'type': 'direct'},
        'icc_charlson': {'platform': 'icc_charlson', 'type': 'direct'},
        # --- Dates de dialyse (variantes de nommage) ---
        'date_debut_dialyse': {'platform': 'dialyse_date_debut', 'type': 'direct'},
        'date_debut': {'platform': 'dialyse_date_debut', 'type': 'direct'},
        'dialyse_date_debut': {'platform': 'dialyse_date_debut', 'type': 'direct'},
        'date_demarrage_dialyse': {'platform': 'dialyse_date_debut', 'type': 'direct'},
        'debut_dialyse': {'platform': 'dialyse_date_debut', 'type': 'direct'},
        # --- Comorbidités ---
        'hypertension': {'platform': 'comorbidite_liste', 'type': 'fusion (valeurs multiples → liste)'},
        'cardiopathie': {'platform': 'comorbidite_liste', 'type': 'fusion (valeurs multiples → liste)'},
        # --- Dialyse modalité ---
        'hemodialyse': {'platform': 'dialyse_modalite_initiale', 'type': 'fusion (hd/dp → modalité)'},
        'dialyse_peritoneale': {'platform': 'dialyse_modalite_initiale', 'type': 'fusion (hd/dp → modalité)'},
        # --- Contexte début dialyse ---
        'debut_dialyse_urgence': {'platform': 'irc_contexte_debut_dialyse', 'type': 'fusion (urgence/planifié → contexte)'},
        'debut_dialyse_planifie': {'platform': 'irc_contexte_debut_dialyse', 'type': 'fusion (urgence/planifié → contexte)'},
        # --- Devenir ---
        'deces': {'platform': 'devenir_statut', 'type': 'inclus dans statut devenir'},
        'cause_deces_cardiaque': {'platform': 'devenir_cause_deces', 'type': 'fusion (cardiaque/infectieux → cause)'},
        'cause_deces_infectieuse': {'platform': 'devenir_cause_deces', 'type': 'fusion (cardiaque/infectieux → cause)'},
    }


# Charger le mapping au démarrage
COLUMN_MAPPING = load_column_mapping()

SECTION_PREFIX_MAP = {
    'demographie_': 'demographie_data',
    'irc_': 'irc_data',
    'comorbidite_': 'comorbidite_data',
    'presentation_': 'presentation_data',
    'biologie_': 'biologie_data',
    'imagerie_': 'imagerie_data',
    'dialyse_': 'dialyse_data',
    'qualite_': 'qualite_data',
    'complication_': 'complication_data',
    'traitement_': 'traitement_data',
    'devenir_': 'devenir_data',
}

TEMPLATE_KEYWORDS = {
    'texte libre court',
    'texte libre long',
    'liste a choix unique',
    'liste a choix multiple',
    'selecteur de date',
    'nombre entier',
    'oui/non',
    'genere automatiquement',
}

FIXED_CLASSEUR_TEMPLATE_NAMES = [
    'template',
    'template_patients_hd',
    'plateform_donnees_complete',
    'classeur1',
    'Main',
]

AUTO_INCREMENT_FIELD_PREFIX = {
    'id_patient': 'PAT',
    'id_enregistrement_source': 'SRC',
}

POSTGRES_MODEL_FIELD_MAP = {
    'id_patient': 'id_patient',
    'id_enregistrement_source': 'id_enregistrement_source',
    'id_site': 'id_site',
    'statut_inclusion': 'statut_inclusion',
    'statut_consentement': 'statut_consentement',
    'utilisateur_saisie': 'utilisateur_saisie',
    'derniere_mise_a_jour': 'derniere_mise_a_jour',
    'date_evaluation_initiale': 'date_evaluation_initiale',
    'nom': 'nom',
    'prenom': 'prenom',
    'age': 'age',
    'sexe': 'sexe',
    'maladie': 'maladie',
    'telephone': 'telephone',
    'adresse': 'adresse',
    'date_naissance': 'date_naissance',
    'date_admission': 'date_admission',
    'icc_charlson': 'icc_charlson',
}

POSTGRES_SECTION_BUCKETS = [
    ('demographie_', 'demographie_data'),
    ('irc_', 'irc_data'),
    ('comorbidite_', 'comorbidite_data'),
    ('presentation_', 'presentation_data'),
    ('biologie_', 'biologie_data'),
    ('imagerie_', 'imagerie_data'),
    ('dialyse_', 'dialyse_data'),
    ('qualite_', 'qualite_data'),
    ('complication_', 'complication_data'),
    ('traitement_', 'traitement_data'),
    ('devenir_', 'devenir_data'),
]


def refresh_postgres_flat_view(template=None):
    if template is None:
        template = PatientFormTemplate.objects.filter(name__iexact='template').order_by('-id').first()
        if template is None:
            template = PatientFormTemplate.objects.order_by('-id').first()

    if template is None:
        return

    keys = [
        key for key in template.fields.order_by('order', 'id').values_list('key', flat=True)
        if key and not key.startswith('unnamed')
    ]
    if not keys:
        return

    fixed_keys = [
        'id_patient', 'nom', 'prenom', 'age', 'sexe', 'maladie',
        'telephone', 'adresse', 'date_naissance', 'date_admission',
        'id_enregistrement_source', 'id_site', 'statut_inclusion',
        'statut_consentement', 'date_evaluation_initiale',
        'utilisateur_saisie', 'derniere_mise_a_jour',
    ]

    select_parts = ['p.id AS id']
    for key in fixed_keys:
        if key in POSTGRES_MODEL_FIELD_MAP:
            select_parts.append(f"p.{POSTGRES_MODEL_FIELD_MAP[key]} AS {_pg_quote_identifier(key)}")

    for key in keys:
        if key in fixed_keys:
            continue
        if key in POSTGRES_MODEL_FIELD_MAP:
            expr = f"p.{POSTGRES_MODEL_FIELD_MAP[key]}"
        else:
            bucket = None
            for prefix, column_name in POSTGRES_SECTION_BUCKETS:
                if key.startswith(prefix):
                    bucket = column_name
                    break

            if bucket:
                expr = f"p.{bucket} ->> {_pg_quote_literal(key)}"
            else:
                expr = f"p.extra_data ->> {_pg_quote_literal(key)}"

        select_parts.append(f"{expr} AS {_pg_quote_identifier(key)}")

    sql_create = (
        'CREATE VIEW public.patients_plateforme_flat AS '
        'SELECT ' + ', '.join(select_parts) + ' FROM patients_patient p'
    )

    with connection.cursor() as cursor:
        # DROP obligatoire : CREATE OR REPLACE ne peut pas renommer des colonnes existantes
        cursor.execute('DROP VIEW IF EXISTS public.patients_plateforme_flat CASCADE')
        cursor.execute(sql_create)


def get_active_template():
    template = None
    for template_name in FIXED_CLASSEUR_TEMPLATE_NAMES:
        template = (
            PatientFormTemplate.objects.filter(name__iexact=template_name).order_by('-id').first()
            or PatientFormTemplate.objects.filter(sheet_name__iexact=template_name).order_by('-id').first()
        )
        if template:
            break
    if not template:
        template = PatientFormTemplate.objects.order_by('-id').first()
    return template


def is_schema_template_sheet(worksheet):
    if worksheet.max_row < 2:
        return False

    type_cells = [worksheet.cell(2, col_index).value for col_index in range(1, worksheet.max_column + 1)]
    normalized_types = {
        normalize_header(cell).replace('_', ' ')
        for cell in type_cells
        if cell is not None and str(cell).strip()
    }
    return bool(normalized_types.intersection(TEMPLATE_KEYWORDS))


def create_or_update_template(worksheet, source_file_name):
    template_name = (worksheet.title if worksheet else None) or 'Patient Schema'
    template, _ = PatientFormTemplate.objects.update_or_create(
        name=template_name,
        defaults={
            'source_file_name': source_file_name or template_name,
            'sheet_name': worksheet.title if worksheet else template_name,
        },
    )
    return template


def parse_schema_from_template_sheet(worksheet, source_file_name):
    template = create_or_update_template(worksheet, source_file_name)
    template.fields.all().delete()

    created_fields = []
    for column_index in range(1, worksheet.max_column + 1):
        header = worksheet.cell(1, column_index).value
        type_label = worksheet.cell(2, column_index).value
        if not header:
            continue

        choices = []
        for row_index in range(3, worksheet.max_row + 1):
            value = worksheet.cell(row_index, column_index).value
            if value is not None and str(value).strip():
                choices.append(str(value).strip())

        field_type = normalize_type(type_label)
        created_fields.append(
            PatientFormField(
                template=template,
                key=normalize_header(header),
                label=str(header).strip(),
                field_type=field_type,
                order=column_index,
                choices=choices,
                source_hint=str(type_label or ''),
                is_required=field_type not in ['auto'],
            )
        )

    PatientFormField.objects.bulk_create(created_fields)
    try:
        refresh_postgres_flat_view(template)
    except Exception:
        pass
    return template, len(created_fields)


def upsert_template_from_headers(headers, worksheet, source_file_name, create_fields=True):
    template = None
    for template_name in FIXED_CLASSEUR_TEMPLATE_NAMES:
        template = (
            PatientFormTemplate.objects.filter(name__iexact=template_name).order_by('-id').first()
            or PatientFormTemplate.objects.filter(sheet_name__iexact=template_name).order_by('-id').first()
        )
        if template:
            break

    if template is None:
        template = create_or_update_template(worksheet, source_file_name)
    else:
        if source_file_name:
            template.source_file_name = source_file_name
        if worksheet and getattr(worksheet, 'title', None):
            template.sheet_name = worksheet.title
        template.save(update_fields=['source_file_name', 'sheet_name'])

    if not create_fields:
        try:
            refresh_postgres_flat_view(template)
        except Exception:
            pass
        return template

    existing_fields = {field.key: field for field in template.fields.all()}

    for index, header in enumerate(headers, start=1):
        if not header:
            continue

        header_str = str(header).strip()
        if not header_str or header_str.lower().startswith('unnamed'):
            continue

        key = normalize_header(header_str)
        if not key or key.startswith('unnamed') or key in existing_fields:
            continue

        # Ne jamais créer de champ pour les colonnes fusionnées dans comorbidite_liste
        if key in _COLUMNS_FUSED_INTO_COMORBIDITE_LISTE:
            continue

        PatientFormField.objects.create(
            template=template,
            key=key,
            label=str(header).strip(),
            field_type='text_short',
            order=index,
            choices=[],
            source_hint='auto_detected_from_data_import',
            is_required=False,
        )

    try:
        refresh_postgres_flat_view(template)
    except Exception:
        pass

    return template


def build_patient_payload(row):
    # DEBUG: afficher les colonnes une seule fois
    if not hasattr(build_patient_payload, '_cols_printed'):
        print("=== COLONNES DU FICHIER EXCEL ===")
        for i, col in enumerate(row.keys()):
            print(f'  {i}: "{col}"')
        build_patient_payload._cols_printed = True

    payload = {'extra_data': {}}

    # Initialiser les structures par section
    payload.setdefault('demographie_data', {})
    payload.setdefault('irc_data', {})
    payload.setdefault('comorbidite_data', {})
    payload.setdefault('presentation_data', {})
    payload.setdefault('biologie_data', {})
    payload.setdefault('dialyse_data', {})
    payload.setdefault('complication_data', {})
    payload.setdefault('devenir_data', {})

    comorbidite_list = []
    presentation_list = []
    complication_list = []

    contexte_dialyse = None
    modalite_dialyse = None
    date_transplantation = None
    cause_deces_value = None
    deces_statut = None
    changement_modalite = False
    age_value = None
    age_column_found = False

    # PARCOURIR TOUTES LES COLONNES
    for column_name, raw_value in row.items():
        value = convert_excel_value(raw_value)
        if value is None:
            continue

        # Décodage numérique AVANT toute autre logique
        value = decode_numeric_value(column_name, value)
        normalized = normalize_header(column_name)

        # === DÉTECTION DE L'ÂGE ===
        if not age_column_found and (
            'age' in normalized
            or normalized in ('ans', 'years', 'age_annees')
        ):
            age_value = normalize_age_value(value)
            if age_value is not None and 0 < age_value < 120:
                payload['age'] = age_value
                payload['demographie_data']['demographie_age_ans'] = age_value
                date_estimee = derive_date_of_birth_from_age(age_value)
                if date_estimee:
                    payload['demographie_data']['demographie_date_naissance'] = date_estimee
                    # Marquer que la date est estimée (calculée depuis l'âge, pas saisie réelle)
                    payload['extra_data']['demographie_date_naissance_estimee'] = True
                age_column_found = True
                print(f"Âge détecté: '{column_name}' = {age_value} ans")
            continue

        # === DÉTECTION CHARLSON ===
        col_name_lower = str(column_name).lower().strip()
        is_charlson = (
            col_name_lower in ['charlson', 'icc_charlson', 'icccharlson', 'score_charlson']
            or str(column_name).strip() in ['Charlson', 'ICC_Charlson', 'ICC_CHARLSON']
            or 'charlson' in col_name_lower
        )

        if is_charlson:
            charlson_val = extract_charlson_score(value)
            if charlson_val is not None:
                payload['icc_charlson'] = str(charlson_val)
                print(f"✅ CHARLSON CAPTURÉ: '{column_name}' → {charlson_val}")
            else:
                print(f"⚠️ Colonne Charlson trouvée mais valeur non extraite: '{raw_value}'")

        # === COLONNES ACCÈS DIALYSE (binaire 0/1 → dialyse_type_acces_initial) ===
        if normalized == 'fistule_arterioveineuse_creee':
            if _is_truthy(value):
                payload.setdefault('dialyse_data', {})['dialyse_type_acces_initial'] = 'fistule_arterioveineuse'
                payload['dialyse_type_acces_initial'] = 'fistule_arterioveineuse'
            continue

        if normalized == 'admission_cathetere_tunnellise':
            # Ne pas écraser si déjà défini comme fistule
            if _is_truthy(value) and payload.get('dialyse_type_acces_initial') != 'fistule_arterioveineuse':
                payload.setdefault('dialyse_data', {})['dialyse_type_acces_initial'] = 'cathetere_tunnellise'
                payload['dialyse_type_acces_initial'] = 'cathetere_tunnellise'
            elif not _is_truthy(value) and 'dialyse_type_acces_initial' not in payload:
                payload.setdefault('dialyse_data', {})['dialyse_type_acces_initial'] = 'cathetere_femoral'
                payload['dialyse_type_acces_initial'] = 'cathetere_femoral'
            continue

        # === DÉLAI DÉCÈS → extra_data ===
        if normalized == 'delai_jusquau_deces_jours':
            try:
                payload['extra_data']['delai_jusquau_deces_jours'] = int(float(str(value)))
            except (ValueError, TypeError):
                pass
            continue

        # === DIABÈTE → comorbidite_statut_diabete ===
        if normalized == 'diabete':
            bin_val = 'oui' if _is_truthy(value) else 'non'
            payload['comorbidite_statut_diabete'] = bin_val
            payload.setdefault('comorbidite_data', {})['comorbidite_statut_diabete'] = bin_val
            continue

        # === COLONNES DÉJÀ FUSIONNÉES DANS comorbidite_liste → IGNORER ===
        # (traitées via le mapping fusion, ne doivent pas créer de colonne séparée)
        if normalized in _COLUMNS_FUSED_INTO_COMORBIDITE_LISTE:
            # La fusion est gérée plus bas via COLUMN_MAPPING si la valeur est truthy
            pass

        # === MAPPING STANDARD ===
        mapping = COLUMN_MAPPING.get(normalized)

        if mapping:
            platform_field = mapping['platform']
            transform_type = mapping['type']

            if transform_type == 'direct':
                section_target = None
                for prefix, section_bucket in SECTION_PREFIX_MAP.items():
                    if platform_field.startswith(prefix):
                        section_target = section_bucket
                        break

                if section_target:
                    payload[section_target][platform_field] = value
                else:
                    payload[platform_field] = value

            elif transform_type == 'calcul_age_to_birthdate':
                if not age_column_found:
                    age_value = normalize_age_value(value)
                    if age_value is not None and 0 < age_value < 120:
                        payload['age'] = age_value
                        payload['demographie_data']['demographie_age_ans'] = age_value
                        date_estimee = derive_date_of_birth_from_age(age_value)
                        if date_estimee:
                            payload['demographie_data']['demographie_date_naissance'] = date_estimee
                            # Marquer que la date est estimée (calculée depuis l'âge, pas saisie réelle)
                            payload['extra_data']['demographie_date_naissance_estimee'] = True
                        age_column_found = True

            elif transform_type == 'fusion (urgence/planifié → contexte)':
                if _is_truthy(value):
                    contexte_dialyse = 'debut_en_urgence' if 'urgence' in normalized else 'debut_planifie'

            elif transform_type == 'fusion (hd/dp → modalité)':
                if _is_truthy(value):
                    modalite_dialyse = 'hemodialyse' if 'hemodialyse' in normalized else 'dialyse_peritoneale'

            elif transform_type == 'partiel (oui/non → date)':
                if _is_truthy(value):
                    date_transplantation = timezone.now().date().isoformat()

            elif transform_type == 'fusion (valeurs multiples → liste)' and platform_field == 'comorbidite_liste':
                if _is_truthy(value):
                    label = normalized.replace('_', ' ')
                    if label not in comorbidite_list:
                        comorbidite_list.append(label)
                        print(f"Comorbidité: {label}")

            elif 'symptome' in transform_type.lower() or (
                transform_type == 'fusion (valeurs multiples → liste)'
                and platform_field == 'presentation_symptomes'
            ):
                if _is_truthy(value):
                    label = normalized.replace('_', ' ')
                    if label not in presentation_list:
                        presentation_list.append(label)

            elif 'complication' in transform_type.lower() or (
                transform_type == 'fusion (valeurs multiples → liste)'
                and platform_field == 'complication_liste'
            ):
                if _is_truthy(value):
                    label = normalized.replace('_', ' ')
                    if label not in complication_list:
                        complication_list.append(label)

            elif 'inclus dans thèmes éducation' in transform_type:
                # Ces colonnes sont maintenant ignorées et iront dans extra_data
                # car elles n'ont plus d'entrée dans column_mapping.json
                # On ne fait rien ici, elles seront capturées par le else
                pass

            elif transform_type == 'fusion (cardiaque/infectieux → cause)':
                if _is_truthy(value):
                    if 'cardiaque' in normalized:
                        cause_deces_value = 'cardiovasculaire'
                    elif 'infectieuse' in normalized:
                        cause_deces_value = 'infection'

            elif transform_type == 'inclus dans statut devenir' and platform_field == 'devenir_statut':
                deces_statut = value

            elif 'changement' in transform_type.lower():
                if _is_truthy(value):
                    changement_modalite = True
        else:
            # Colonnes déjà fusionnées → ne jamais créer de colonne séparée
            if normalized in _COLUMNS_FUSED_INTO_COMORBIDITE_LISTE:
                pass
            else:
                # Colonnes non mappées → extra_data (devient une colonne dynamique)
                payload['extra_data'][normalized] = value
                # Mémoriser les noms de colonnes dynamiques pour le rapport d'import
                payload.setdefault('_dynamic_columns_detected', set()).add(normalized)
                print(f"🆕 Colonne dynamique ajoutée: '{column_name}' = {value}")

    # ── Appliquer les fusions ──────────────────────────────────────────────
    if comorbidite_list:
        payload['comorbidite_data']['comorbidite_liste'] = ', '.join(comorbidite_list)

    if presentation_list:
        payload['presentation_data']['presentation_symptomes'] = ', '.join(presentation_list)

    if complication_list:
        payload['complication_data']['complication_liste'] = ', '.join(complication_list)

    if contexte_dialyse:
        payload['irc_data']['irc_contexte_debut_dialyse'] = contexte_dialyse

    if modalite_dialyse:
        payload['dialyse_data']['dialyse_modalite_initiale'] = modalite_dialyse

    if date_transplantation:
        payload['devenir_data']['devenir_date_transplantation'] = date_transplantation

    if cause_deces_value:
        payload['devenir_data']['devenir_cause_deces'] = cause_deces_value

    if deces_statut is not None:
        payload['devenir_data']['devenir_statut'] = (
            'decede' if _is_truthy(deces_statut) else 'vivant_sous_dialyse'
        )

    if changement_modalite:
        payload['complication_data']['complication_changement_modalite_dialyse'] = 'oui'

    # ── Normalisation du sexe ─────────────────────────────────────────────
    if 'demographie_sexe' in payload['demographie_data']:
        dem_sexe = payload['demographie_data']['demographie_sexe']
        patient_sex, demo_sex = normalize_sex_values(dem_sexe)
        if patient_sex:
            payload['sexe'] = patient_sex
        if demo_sex:
            payload['demographie_data']['demographie_sexe'] = demo_sex

    # ── Récapitulatif ────────────────────────────────────────────────────
    if age_column_found:
        print(f"✓ Âge: {age_value} ans")

    if 'icc_charlson' in payload:
        print(f"✅ CHARLSON DANS LE PAYLOAD: {payload['icc_charlson']}")
    else:
        print("❌ Score Charlson NON trouvé dans ce fichier")

    return payload


def ensure_required_identity_fields(payload):
    extra_data = payload.get('extra_data') or {}
    identifier = payload.get('id_patient') or extra_data.get('id_patient')

    if not payload.get('id_patient') and identifier:
        payload['id_patient'] = str(identifier)

    nom_value = payload.get('nom')
    if nom_value is None or str(nom_value).strip() == '':
        payload['nom'] = 'Import_Automatique'

    _BOOL_VALUES = {'oui', 'non', 'yes', 'no', 'true', 'false', '1', '0'}
    prenom_value = payload.get('prenom')
    prenom_str = str(prenom_value).strip().lower() if prenom_value is not None else ''
    if not prenom_str or prenom_str in _BOOL_VALUES:
        payload['prenom'] = f"Patient_{payload.get('id_patient', '000')}"

    payload['extra_data'] = extra_data
    return payload


def _extract_numeric_suffix(value):
    """Extrait le dernier bloc de chiffres d'une chaîne (après le dernier tiret ou caractère non-numérique)."""
    if value is None:
        return None
    text = str(value).strip()
    
    # Chercher le dernier bloc de chiffres consécutifs
    digits = ''
    for char in reversed(text):
        if char.isdigit():
            digits = char + digits
        elif digits:
            # On a trouvé un bloc de chiffres, arrêter
            break
    
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def generate_next_incremental_identifier(model_field, prefix):
    max_number = 0
    for current_value in Patient.objects.values_list(model_field, flat=True):
        numeric_value = _extract_numeric_suffix(current_value)
        if numeric_value and numeric_value > max_number:
            max_number = numeric_value
    next_number = max_number + 1
    return f"{prefix}{next_number:06d}"


def generate_next_numeric_patient_id(auto_increment_state=None):
    if auto_increment_state is not None:
        auto_increment_state['id_patient'] = auto_increment_state.get('id_patient', 0) + 1
        return str(auto_increment_state['id_patient'])
    max_number = 0
    for current_value in Patient.objects.values_list('id_patient', flat=True):
        numeric_value = _extract_numeric_suffix(current_value)
        if numeric_value and numeric_value > max_number:
            max_number = numeric_value
    return str(max_number + 1)


def initialize_auto_increment_state():
    state = {}
    for model_field in AUTO_INCREMENT_FIELD_PREFIX:
        max_number = 0
        for current_value in Patient.objects.values_list(model_field, flat=True):
            numeric_value = _extract_numeric_suffix(current_value)
            if numeric_value and numeric_value > max_number:
                max_number = numeric_value
        state[model_field] = max_number
    return state


def resolve_entry_user_label(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'system_import'
    for attr in ['username', 'email']:
        value = getattr(user, attr, None)
        if value:
            return str(value)
    return str(getattr(user, 'id', 'system_import'))


def ensure_incremental_identifiers(payload, auto_increment_state=None, force_generated=False):
    if force_generated:
        patient_id = generate_next_numeric_patient_id(auto_increment_state=auto_increment_state)
        payload['id_patient'] = patient_id
        
        # Générer id_enregistrement_source basé sur id_patient pour assurer la synchronisation
        patient_num = _extract_numeric_suffix(patient_id)
        if patient_num is not None:
            payload['id_enregistrement_source'] = (
                f"{AUTO_INCREMENT_FIELD_PREFIX['id_enregistrement_source']}{patient_num:06d}"
            )
        else:
            # Fallback si extraction échoue
            payload['id_enregistrement_source'] = generate_next_incremental_identifier(
                'id_enregistrement_source',
                AUTO_INCREMENT_FIELD_PREFIX['id_enregistrement_source'],
            )
        return payload
    if not payload.get('id_patient'):
        payload['id_patient'] = generate_next_numeric_patient_id(auto_increment_state=auto_increment_state)
    return payload


def apply_automatic_schema_fields(payload, auto_increment_state=None, current_user=None):
    template = PatientFormTemplate.objects.order_by('-id').first()
    if not template:
        return payload
    extra_data = payload.get('extra_data') or {}
    for field in template.fields.filter(field_type='auto'):
        if field.key in ['id_patient', 'id_enregistrement_source']:
            continue
    payload['extra_data'] = extra_data

    if 'utilisateur_saisie' not in payload:
        payload['utilisateur_saisie'] = resolve_entry_user_label(current_user)
    if 'derniere_mise_a_jour' not in payload:
        payload['derniere_mise_a_jour'] = timezone.now().isoformat()
    if 'date_evaluation_initiale' not in payload:
        payload['date_evaluation_initiale'] = timezone.now().date().isoformat()

    return payload


PREPROCESS_SESSION_DIR = os.path.join(os.path.dirname(__file__), 'preprocess_sessions')
CRITICAL_PREPROCESS_KEYS = ['nom', 'prenom', 'id_patient']


def _ensure_preprocess_session_dir():
    os.makedirs(PREPROCESS_SESSION_DIR, exist_ok=True)


def _preprocess_session_path(session_id):
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '', str(session_id or ''))
    return os.path.join(PREPROCESS_SESSION_DIR, f'{safe_id}.json')


def _save_preprocess_session(session_payload):
    _ensure_preprocess_session_dir()
    session_id = session_payload.get('id') or uuid.uuid4().hex
    session_payload['id'] = session_id
    session_payload['updated_at'] = timezone.now().isoformat()
    session_path = _preprocess_session_path(session_id)
    tmp_path = session_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as handle:
        json.dump(_safe_json_value(session_payload), handle, ensure_ascii=False)
    os.replace(tmp_path, session_path)
    return session_payload


def _load_preprocess_session(session_id):
    session_path = _preprocess_session_path(session_id)
    if not os.path.exists(session_path):
        return None
    import time as _time
    for attempt in range(3):
        try:
            with open(session_path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except (json.JSONDecodeError, ValueError):
            if attempt < 2:
                _time.sleep(0.1)
    return None


def _append_preprocess_event(session_payload, event_type, event_data=None):
    if not isinstance(session_payload, dict):
        return session_payload
    events = session_payload.get('event_log')
    if not isinstance(events, list):
        events = []
    event = {
        'timestamp': timezone.now().isoformat(),
        'event_type': str(event_type or 'unknown_event'),
    }
    if isinstance(event_data, dict):
        event.update(_safe_json_value(event_data))
    events.append(event)
    session_payload['event_log'] = events
    return session_payload


def _iter_preprocess_sessions():
    _ensure_preprocess_session_dir()
    for file_name in os.listdir(PREPROCESS_SESSION_DIR):
        if not file_name.endswith('.json'):
            continue
        path = os.path.join(PREPROCESS_SESSION_DIR, file_name)
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                yield payload
        except Exception:
            continue


def _to_json_compatible(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


def _dataframe_to_rows(dataframe):
    rows = []
    for _, row in dataframe.iterrows():
        payload = {}
        for column in dataframe.columns:
            payload[str(column)] = _to_json_compatible(row[column])
        rows.append(payload)
    return rows


def _rows_to_dataframe(rows, columns=None):
    if not rows:
        return pd.DataFrame(columns=columns or [])
    dataframe = pd.DataFrame(rows)
    if columns:
        for column in columns:
            if column not in dataframe.columns:
                dataframe[column] = None
        dataframe = dataframe[columns]
    return dataframe


def _read_uploaded_dataframe(uploaded_file):
    source_file_name = getattr(uploaded_file, 'name', 'uploaded_file')
    lower_name = str(source_file_name).lower()

    if lower_name.endswith('.csv'):
        uploaded_file.seek(0)
        dataframe = pd.read_csv(uploaded_file)
    elif lower_name.endswith('.xls'):
        uploaded_file.seek(0)
        dataframe = pd.read_excel(uploaded_file, engine='xlrd')
    else:
        uploaded_file.seek(0)
        dataframe = pd.read_excel(uploaded_file, parse_dates=True)

    dataframe = dataframe.loc[:, ~dataframe.columns.astype(str).str.match(r'^(Unnamed|unnamed)(:.*)?$')]
    return dataframe, source_file_name


# ─── Anomaly candidate detection constants ────────────────────────────────────
# Used inside _build_technical_profile to surface rare aberrant values that
# never appear in the 5-sample snapshot shown to the LLM.
import re as _re_anomaly
import json as _json_rules

_MEDICAL_DOMAIN_RULES_PATH = os.path.join(os.path.dirname(__file__), 'medical_domain_rules.json')
try:
    with open(_MEDICAL_DOMAIN_RULES_PATH, 'r', encoding='utf-8') as _f:
        _MEDICAL_DOMAIN_RULES = _json_rules.load(_f)
except Exception:
    _MEDICAL_DOMAIN_RULES = {'numeric_ranges': {}, 'categorical_codes': {}}

_ANOMALY_EXCEL_DATE_ARTIFACTS = {
    '0/1/1900', '1/0/1900', '00/01/1900', '01/00/1900',
    '0/0/1900', '1/1/1900', '01/01/1900', '00/00/1900',
    '0-1-1900', '1-0-1900', '00-01-1900', '01-00-1900',
    '1900-01-00', '1900-00-01', '1900-01-01',
    # pandas converts Excel serial 0 → Timestamp('1899-12-30') → ISO "1899-12-30"
    '1899-12-30', '1899-12-31', '1899-12-29',
    # pandas/openpyxl sometimes produce these for corrupt/zero date cells
    '1900-01-00 00:00:00', '1899-12-30 00:00:00',
}
_ANOMALY_YEAR_TYPO_RE = _re_anomaly.compile(r'\b([3-9]\d{3}|21\d{2})\b')
_ANOMALY_FUTURE_YEAR_RE = _re_anomaly.compile(r'\b(20[3-9]\d|2[1-9]\d{2})\b')
# Dates before 1920 in a modern medical dataset = Excel artifact or data error
_ANOMALY_ANCIENT_DATE_RE = _re_anomaly.compile(r'^(18\d{2}|19[01]\d)[-/]')

_ANOMALY_DISGUISED_MISSING = frozenset({
    'n/a', 'na', 'nan', '?', '-', '--', '---', 'null', 'none', 'nil',
    'inconnu', 'inconnu(e)', 'nd', 'nr', 'nc', 'nsp', 'nrp',
    'non renseigne', 'non renseigné', 'non disponible', 'non évalué',
    'non evalue', 'non applicable', 'néant', 'neant', 'absent',
    '#n/a', '#na', '#ref!', '#value!', '#num!', '#div/0!',
    'manquant', 'missing', 'unknown', 'aucun', 'aucune',
    'a préciser', 'en cours', 'void', '.', '/', '',
})

# Values that are invalid in binary (0/1) columns — "X", "x", "*", etc.
_ANOMALY_INVALID_IN_BINARY = frozenset({'x', 'X', '*', 'X ', ' X', 'xx', 'XX'})

# Decimal comma: "1,5" or "-1,5" or "1 234,56" (French locale numbers)
_ANOMALY_DECIMAL_COMMA_RE = _re_anomaly.compile(r'^-?\d[\d\s]*,\d+$')
# Pure numeric string in object column: "25.5", "100", "-3.14"
_ANOMALY_NUMERIC_STR_RE = _re_anomaly.compile(r'^-?\d+(\.\d+)?$')
# HTML/special char debris
_ANOMALY_HTML_RE = _re_anomaly.compile(r'&[a-z]+;|<[a-z/][^>]*>', _re_anomaly.IGNORECASE)
# Mixed Excel artefact: values like "1;(1/2024)", "2;(3/2023)" — number + semicolon + parenthesised date/fraction
_ANOMALY_MIXED_SEMICOLON_RE = _re_anomaly.compile(r'^\d+\s*;\s*\(.*\)$')

# Boolean text tokens (French + English) — if mixed with 0/1 numeric → incoherent
_ANOMALY_BOOL_TEXT = frozenset({
    'oui', 'non', 'o', 'n', 'true', 'false', 'yes', 'no', 'vrai', 'faux',
    'positif', 'negatif', 'pos', 'neg', 'present', 'absent',
})
_ANOMALY_BOOL_NUM = frozenset({'0', '1'})

# Date format families — multiple families in same column = format_date_mixte
_ANOMALY_DATE_FMT = [
    ('dmy_slash', _re_anomaly.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')),
    ('ymd_dash',  _re_anomaly.compile(r'^\d{4}-\d{2}-\d{2}$')),
    ('dmy_dash',  _re_anomaly.compile(r'^\d{1,2}-\d{1,2}-\d{4}$')),
    ('dmy_dot',   _re_anomaly.compile(r'^\d{1,2}\.\d{1,2}\.\d{4}$')),
]

# Column name keywords that imply non-negative values
# ── SVM mortalité feature validation ─────────────────────────────────────────
# Exact features expected by mortalite_svm.joblib — validated post-correction
# to ensure the LLM did not introduce new errors on prediction-critical columns.
_SVM_MORTALITE_FEATURES = {
    # numeric (min, max)
    'albumine_basale':              (15, 60),
    'calcium_basale':               (60, 150),
    'ferritine_basale':             (5, 5000),
    'pth_basale':                   (5, 5000),
    'du_residuelle':                (0, 5000),
    'seances_par_semaine':          (1, 7),
    'nombre_hospitalisations':      (0, 100),
    'annee_inclusion':              (1990, 2030),
    'etiologie_mrc':                (1, 15),
    'couverture_medicale':          (0, 3),
    # binary (only 0 or 1 allowed)
    'fistule_arterioveineuse_creee':     'binary',
    'admission_cathetere_tunnellise':    'binary',
    'crise_convulsive':                  'binary',
    'douleur_abdominale':               'binary',
    'diabete':                          'binary',
    'evenement_cardiovasculaire':        'binary',
    'dyspnee':                          'binary',
    'oedemes_surcharge':                'binary',
    'hemodialyse':                      'binary',
    'liste_attente_transplantation':     'binary',
    'maladie_renale_hereditaire':        'binary',
    'information_transplantation_donnee':'binary',
    'hypertension':                     'binary',
    'cardiopathie':                     'binary',
}

_ANOMALY_NONNEG_KEYWORDS = (
    'age', 'poids', 'taille', 'imc', 'bmi', 'score', 'glycemie',
    'tension', 'frequence', 'duree', 'pression', 'hemoglobine',
    'cholesterol', 'creatinine', 'glucose', 'uree', 'albumine',
)

# Mojibake: UTF-8 bytes mis-decoded as Latin-1/cp1252.
# Ã©=é, Ã¨=è, â€™=', â€œ=", Ã =à  etc.
_ANOMALY_MOJIBAKE_RE = _re_anomaly.compile(r"Ã[^\s]|â€")

# Cross-column analysis keywords
_ANOMALY_AGE_KEYWORDS     = ('age', 'age_patient', 'age_ans', 'annee_age')
_ANOMALY_BIRTH_KEYWORDS   = ('naissance', 'birth', 'dob', 'date_nais', 'annee_naiss')
_ANOMALY_NAME_KEYWORDS    = ('nom', 'prenom', 'name', 'first_name', 'last_name', 'patient_name')
_ANOMALY_ID_KEYWORDS      = ('patient_id', 'id_patient', 'numero_patient', 'code_patient', 'identifiant')
# ──────────────────────────────────────────────────────────────────────────────


def _build_technical_profile(dataframe):
    columns_profile = []
    numeric_columns_profile = []
    categorical_columns_profile = []
    total_rows = int(len(dataframe.index))
    total_columns = int(len(dataframe.columns))
    total_cells = total_rows * total_columns
    missing_cells = int(dataframe.isna().sum().sum()) if total_cells else 0
    duplicate_rows = int(dataframe.duplicated().sum()) if total_rows else 0
    duplicate_ratio = round((duplicate_rows / total_rows) * 100, 2) if total_rows else 0.0

    for column in dataframe.columns:
        series = dataframe[column]
        non_null_series = series.dropna()
        missing_count = int(series.isna().sum())
        non_null_count = int(series.notna().sum())
        # Collect diverse samples: head + mid + tail to expose rare/aberrant values
        n = len(non_null_series)
        sample_indices = list(dict.fromkeys(
            [0, 1, n // 4, n // 2, 3 * n // 4, n - 1]
        )) if n > 3 else list(range(n))
        raw_samples = non_null_series.astype(str).iloc[sample_indices].tolist()
        sample_values = list(dict.fromkeys(raw_samples))[:5]

        # Scan ALL unique values for anomaly candidates invisible in 5-sample snapshots.
        # Each candidate is surfaced to the LLM with its detected anomaly type.
        anomaly_candidates = []
        _is_numeric_col = pd.api.types.is_numeric_dtype(series)
        _col_lower = str(column).lower()
        if n > 0:
            _decimal_comma_count = 0
            _bool_text_seen = False
            _bool_num_seen = False
            _date_formats_seen = set()
            _numeric_str_count = 0
            _has_html = False
            _has_space = False
            _has_mojibake = False
            _ancient_date_count = 0
            _unique_vals = non_null_series.astype(str).unique()[:500]

            for _v in _unique_vals:
                _vs = _v.strip()
                _vsl = _vs.lower()

                # 1. Excel date base artifacts (includes pandas ISO output of serial 0)
                if _vs in _ANOMALY_EXCEL_DATE_ARTIFACTS:
                    anomaly_candidates.append({'value': _v, 'type': 'artefact_excel'})
                # 1b. Dates before 1920 in any column — likely Excel artifact or data error
                elif _ANOMALY_ANCIENT_DATE_RE.match(_vs):
                    _ancient_date_count += 1

                # 2. Year typo (3023 instead of 2023, 2124 instead of 2024)
                elif _ANOMALY_YEAR_TYPO_RE.search(_vs):
                    anomaly_candidates.append({'value': _v, 'type': 'annee_incorrecte'})

                # 3. Disguised missing values
                elif _vsl in _ANOMALY_DISGUISED_MISSING:
                    anomaly_candidates.append({'value': _v, 'type': 'manquant_deguise'})

                # 4. HTML/special character debris in text fields
                elif not _is_numeric_col and _ANOMALY_HTML_RE.search(_vs):
                    _has_html = True

                # 4b. Mixed Excel artefact: "1;(1/2024)" — number + semicolon + parenthesised fragment
                elif _ANOMALY_MIXED_SEMICOLON_RE.match(_vs):
                    anomaly_candidates.append({'value': _v, 'type': 'artefact_excel_mixte'})

                # 5. Decimal comma in non-numeric column (French locale: "1,5")
                if not _is_numeric_col and _ANOMALY_DECIMAL_COMMA_RE.match(_vs):
                    _decimal_comma_count += 1

                # 6. Numeric string stored in object column
                if not _is_numeric_col and _ANOMALY_NUMERIC_STR_RE.match(_vs) and len(_vs) > 0:
                    _numeric_str_count += 1

                # 7. Boolean token tracking (to detect mixed encoding)
                if not _is_numeric_col:
                    if _vsl in _ANOMALY_BOOL_TEXT:
                        _bool_text_seen = True
                    elif _vs in _ANOMALY_BOOL_NUM:
                        _bool_num_seen = True

                # 8. Date format tracking (to detect mixed formats in date columns)
                for _fmt_name, _fmt_re in _ANOMALY_DATE_FMT:
                    if _fmt_re.match(_vs):
                        _date_formats_seen.add(_fmt_name)
                        break

                # 9. Leading/trailing whitespace
                if _v != _vs:
                    _has_space = True

                # 10. Mojibake: UTF-8 bytes mis-decoded as Latin-1 (Ã©=é, â€™=')
                if not _is_numeric_col and not _has_mojibake and _ANOMALY_MOJIBAKE_RE.search(_vs):
                    _has_mojibake = True

            # Aggregate anomalies — added once per column (not per value)
            if _ancient_date_count > 0:
                anomaly_candidates.append({
                    'value': f'{_ancient_date_count} date(s) avant 1920 (artefact Excel probable, serial date 0 = 1899-12-30)',
                    'type': 'artefact_excel',
                    'count': _ancient_date_count,
                })
            if _decimal_comma_count > 0:
                anomaly_candidates.append({
                    'value': f'{_decimal_comma_count} valeur(s) ex: "{_unique_vals[0]}"',
                    'type': 'separateur_decimal',
                    'count': _decimal_comma_count,
                })
            if _bool_text_seen and _bool_num_seen:
                anomaly_candidates.append({
                    'value': 'mix oui/non et 0/1 dans la meme colonne',
                    'type': 'booleen_incoherent',
                })
            if len(_date_formats_seen) > 1:
                anomaly_candidates.append({
                    'value': f'formats detectes: {sorted(_date_formats_seen)}',
                    'type': 'format_date_mixte',
                })
            total_unique = len(_unique_vals)
            if (not _is_numeric_col and total_unique > 0
                    and _numeric_str_count / max(total_unique, 1) > 0.7):
                anomaly_candidates.append({
                    'value': f'{_numeric_str_count}/{total_unique} valeurs sont des nombres en texte',
                    'type': 'valeur_numerique_texte',
                })
            if _has_html:
                anomaly_candidates.append({
                    'value': 'caracteres HTML ou speciaux detectes',
                    'type': 'caractere_special',
                })
            if _has_space:
                anomaly_candidates.append({
                    'value': 'espaces parasites en debut/fin de valeur',
                    'type': 'espace_parasite',
                })
            if _has_mojibake:
                anomaly_candidates.append({
                    'value': 'caracteres mojibake detectes (ex: Ã© au lieu de é, â€™ au lieu de \')',
                    'type': 'mojibake',
                })
        # ── Structural column checks ────────────────────────────────────────────
        _col_l = str(column).lower()

        # 1. Completely empty column (100% missing)
        if total_rows > 0 and missing_count == total_rows:
            anomaly_candidates.append({
                'value': '100% des valeurs sont manquantes',
                'type': 'colonne_vide',
            })

        # 2. Constant column (single unique non-null value) or near-constant (>98%)
        elif n > 0:
            _n_unique = len(set(_unique_vals)) if n > 0 else 0
            _BINARY_VALUES = {'0', '1', '0.0', '1.0', 'true', 'false'}
            _is_binary_col = set(str(v).strip().lower() for v in _unique_vals).issubset(_BINARY_VALUES)
            if _n_unique == 1 and not _is_binary_col:
                anomaly_candidates.append({
                    'value': f'valeur unique: "{_unique_vals[0]}"',
                    'type': 'colonne_constante',
                })
            elif n >= 50 and _n_unique >= 1:
                _top_count = int(non_null_series.astype(str).value_counts().iloc[0])
                _top_pct = round(_top_count / n * 100, 1)
                if _top_pct >= 98:
                    _top_val = non_null_series.astype(str).value_counts().index[0]
                    anomaly_candidates.append({
                        'value': f'"{_top_val}" = {_top_pct}% des valeurs (quasi-constante)',
                        'type': 'colonne_quasi_constante',
                    })

        # 3. ID / key column with missing values (critical: no patient should be unidentifiable)
        _id_kws = ('_id', 'id_', 'identifiant', 'numero_patient', 'code_patient',
                   'patient_id', 'id_patient', 'num_patient')
        if missing_count > 0 and any(kw in _col_l for kw in _id_kws):
            anomaly_candidates.append({
                'value': f'{missing_count} identifiant(s) manquant(s) — patient(s) non identifiable(s)',
                'type': 'id_manquant',
            })
        # ────────────────────────────────────────────────────────────────────────

        # ── Medical domain checks (column-level) ────────────────────────────────
        _col_l_med = str(column).lower()

        # A. "X" / "x" invalid values in binary/education columns
        if not _is_numeric_col and n > 0:
            _x_count = int(non_null_series.astype(str).str.strip().str.upper().isin(['X']).sum())
            if _x_count > 0:
                anomaly_candidates.append({
                    'value': f'{_x_count} valeur(s) "X" (valeur invalide pour colonne binaire 0/1)',
                    'type': 'valeur_invalide_x',
                    'count': _x_count,
                })

        # B. seances_par_semaine = 0 (impossible for active dialysis patient)
        if 'seances' in _col_l_med and n > 0:
            _zero_seances = int((non_null_series.astype(str).str.strip() == '0').sum())
            if _zero_seances > 0:
                anomaly_candidates.append({
                    'value': f'{_zero_seances} patient(s) avec seances=0 (impossible si dialyse active)',
                    'type': 'valeur_aberrante',
                    'count': _zero_seances,
                })
            _x_seances = int(non_null_series.astype(str).str.strip().str.upper().isin(['X']).sum())
            if _x_seances > 0:
                anomaly_candidates.append({
                    'value': f'{_x_seances} valeur(s) "X" dans seances_par_semaine',
                    'type': 'valeur_invalide_x',
                    'count': _x_seances,
                })

        # C. biopsie_renale = 2 (only 0/1 expected)
        if 'biopsie' in _col_l_med and _is_numeric_col and n > 0:
            _bio_vals = pd.to_numeric(series, errors='coerce').dropna()
            _invalid_bio = _bio_vals[~_bio_vals.isin([0, 1, 0.0, 1.0])]
            if not _invalid_bio.empty:
                anomaly_candidates.append({
                    'value': f'valeurs hors 0/1: {sorted(_invalid_bio.unique().tolist())} ({len(_invalid_bio)} cas)',
                    'type': 'valeur_aberrante',
                    'count': len(_invalid_bio),
                })

        # D. Calcium mixed units: if most values >15 (mg/L ~40-120) but some <15 (mmol/L)
        if 'calcium' in _col_l_med and _is_numeric_col and n > 0:
            _ca_vals = pd.to_numeric(series, errors='coerce').dropna()
            if not _ca_vals.empty and _ca_vals.median() > 15:
                _ca_low = _ca_vals[_ca_vals < 15]
                if not _ca_low.empty:
                    anomaly_candidates.append({
                        'value': f'{len(_ca_low)} valeur(s) < 15 (probablement en mmol/L alors que la colonne est en mg/L): {_ca_low.tolist()}',
                        'type': 'unite_melangee',
                        'count': len(_ca_low),
                    })
            # Calcium > 130 mg/L is physiologically impossible
            if not _ca_vals.empty:
                _ca_high = _ca_vals[_ca_vals > 130]
                if not _ca_high.empty:
                    anomaly_candidates.append({
                        'value': f'{len(_ca_high)} valeur(s) > 130 mg/L (impossible biologiquement): {_ca_high.tolist()}',
                        'type': 'valeur_aberrante',
                        'count': len(_ca_high),
                    })

        # E. Bicarbonates impossible values (>40 mmol/L = severe alkalosis impossible)
        if 'bicarbonate' in _col_l_med and _is_numeric_col and n > 0:
            _hco3 = pd.to_numeric(series, errors='coerce').dropna()
            if not _hco3.empty:
                _hco3_high = _hco3[_hco3 > 40]
                if not _hco3_high.empty:
                    anomaly_candidates.append({
                        'value': f'{len(_hco3_high)} valeur(s) > 40 mmol/L (alcalose impossible): {_hco3_high.tolist()}',
                        'type': 'valeur_aberrante',
                        'count': len(_hco3_high),
                    })

        # F. Creatinine too low for dialysis patient (<50 mg/L)
        if 'creatinine' in _col_l_med and 'mg' in _col_l_med and _is_numeric_col and n > 0:
            _cr_vals = pd.to_numeric(series, errors='coerce').dropna()
            _cr_low = _cr_vals[_cr_vals < 50]
            if not _cr_low.empty:
                anomaly_candidates.append({
                    'value': f'{len(_cr_low)} valeur(s) < 50 mg/L (trop bas pour patient dialysé): {_cr_low.tolist()}',
                    'type': 'valeur_aberrante',
                    'count': len(_cr_low),
                })

        # G. Albumine critically low (<15 g/L)
        if 'albumine' in _col_l_med and _is_numeric_col and n > 0:
            _alb = pd.to_numeric(series, errors='coerce').dropna()
            _alb_low = _alb[_alb < 15]
            if not _alb_low.empty:
                anomaly_candidates.append({
                    'value': f'{len(_alb_low)} valeur(s) < 15 g/L (dénutrition sévère extrême, vérifier): {_alb_low.tolist()}',
                    'type': 'valeur_aberrante',
                    'count': len(_alb_low),
                })

        # H. Sodium impossible values
        if 'sodium' in _col_l_med and _is_numeric_col and n > 0:
            _na = pd.to_numeric(series, errors='coerce').dropna()
            _na_low = _na[_na < 110]
            if not _na_low.empty:
                anomaly_candidates.append({
                    'value': f'{len(_na_low)} valeur(s) < 110 mmol/L (incompatible avec la vie): {_na_low.tolist()}',
                    'type': 'valeur_aberrante',
                    'count': len(_na_low),
                })

        # I. liste_attente_transplantation invalid text
        if 'liste_attente' in _col_l_med and not _is_numeric_col and n > 0:
            _lat_invalids = [str(v) for v in non_null_series.unique()
                             if str(v).strip() not in ('0', '1', '0.0', '1.0')]
            if _lat_invalids:
                anomaly_candidates.append({
                    'value': f'valeurs invalides (attendu 0 ou 1): {_lat_invalids[:5]}',
                    'type': 'valeur_aberrante',
                    'count': len(_lat_invalids),
                })
        # ── End medical domain checks ────────────────────────────────────────────

        anomaly_candidates = anomaly_candidates[:20]

        column_profile = {
            'column': str(column),
            'dtype': str(series.dtype),
            'non_null_count': non_null_count,
            'missing_count': missing_count,
            'missing_pct': round((missing_count / total_rows) * 100, 2) if total_rows else 0.0,
            'sample_values': sample_values,
        }
        if anomaly_candidates:
            column_profile['anomaly_candidates'] = anomaly_candidates
        columns_profile.append(column_profile)

        if pd.api.types.is_numeric_dtype(series):
            numeric_series = pd.to_numeric(series, errors='coerce').dropna()
            if not numeric_series.empty:
                # Detect binary columns (only 0 and 1) — skip IQR/sentinel/negative checks for them
                _unique_numeric = set(numeric_series.unique())
                _is_binary_numeric = _unique_numeric.issubset({0, 1, 0.0, 1.0})
                if _is_binary_numeric:
                    outlier_count = 0
                    sentinel_counts = {}
                else:
                    q1 = float(numeric_series.quantile(0.25))
                    q3 = float(numeric_series.quantile(0.75))
                    iqr = q3 - q1
                    lower_bound = q1 - (1.5 * iqr)
                    upper_bound = q3 + (1.5 * iqr)
                    outlier_count = int(((numeric_series < lower_bound) | (numeric_series > upper_bound)).sum())
                    # Detect sentinel/coded values used as missing (e.g. 999, -1, -99)
                    common_sentinels = (-1, -99, -999, 999, 9999, 99999)
                    sentinel_counts = {
                        str(int(s)): int((numeric_series == s).sum())
                        for s in common_sentinels
                        if int((numeric_series == s).sum()) > 0
                    }
                numeric_columns_profile.append({
                    'column': str(column),
                    'count': int(numeric_series.count()),
                    'mean': round(float(numeric_series.mean()), 4),
                    'std': round(float(numeric_series.std(ddof=0)), 4) if numeric_series.count() > 1 else 0.0,
                    'min': round(float(numeric_series.min()), 4),
                    'q1': round(float(numeric_series.quantile(0.25)), 4) if not _is_binary_numeric else 0.0,
                    'median': round(float(numeric_series.median()), 4),
                    'q3': round(float(numeric_series.quantile(0.75)), 4) if not _is_binary_numeric else 1.0,
                    'max': round(float(numeric_series.max()), 4),
                    'outlier_count': outlier_count,
                    'sentinel_counts': sentinel_counts,
                    **(({'is_binary': True}) if _is_binary_numeric else {}),
                })

                # Detect impossible negative values — skip for binary columns
                _col_l = str(column).lower()
                if (not _is_binary_numeric
                        and float(numeric_series.min()) < 0
                        and any(kw in _col_l for kw in _ANOMALY_NONNEG_KEYWORDS)):
                    _neg_vals = numeric_series[numeric_series < 0].head(3).tolist()
                    _neg_str = ', '.join(str(v) for v in _neg_vals)
                    _existing = column_profile.get('anomaly_candidates') or []
                    _existing.append({
                        'value': f'valeurs negatives: {_neg_str}',
                        'type': 'valeur_negative_impossible',
                    })
                    column_profile['anomaly_candidates'] = _existing[:12]

                # Detect future dates stored as year numbers (year column with val > 2030)
                if 'annee' in _col_l or 'year' in _col_l:
                    _future = numeric_series[numeric_series > 2030]
                    if not _future.empty:
                        _existing = column_profile.get('anomaly_candidates') or []
                        _existing.append({
                            'value': f'annees futures: {_future.head(3).tolist()}',
                            'type': 'date_future',
                        })
                        column_profile['anomaly_candidates'] = _existing[:12]
        else:
            top_values = non_null_series.astype(str).value_counts().head(5)
            categorical_columns_profile.append({
                'column': str(column),
                'unique_count': int(non_null_series.astype(str).nunique()),
                'top_values': [
                    {'value': str(index), 'count': int(count)}
                    for index, count in top_values.items()
                ],
            })

    # ── Cross-column analysis ──────────────────────────────────────────────────
    cross_column_issues = []
    import datetime as _dt
    _current_year = _dt.datetime.now().year
    _all_col_lower = {str(c).lower(): str(c) for c in dataframe.columns}

    # 1. Age vs date-of-birth coherence
    _age_col = next(
        (orig for lw, orig in _all_col_lower.items()
         if any(lw == kw or lw.startswith(kw + '_') for kw in _ANOMALY_AGE_KEYWORDS)),
        None,
    )
    _birth_col = next(
        (orig for lw, orig in _all_col_lower.items()
         if any(kw in lw for kw in _ANOMALY_BIRTH_KEYWORDS)),
        None,
    )
    if _age_col and _birth_col:
        try:
            _birth_years = pd.to_datetime(dataframe[_birth_col], errors='coerce').dt.year
            _ages = pd.to_numeric(dataframe[_age_col], errors='coerce')
            _calc_age = _current_year - _birth_years
            _inconsistent = int(((_calc_age - _ages).abs() > 2).sum())
            if _inconsistent > 0:
                cross_column_issues.append({
                    'type': 'incoherence_age_date',
                    'columns': [_age_col, _birth_col],
                    'inconsistent_rows': _inconsistent,
                    'explanation': (
                        f'{_inconsistent} ligne(s) ont un age incohérent avec la date de naissance '
                        f'(écart > 2 ans entre {_age_col} et année calculée depuis {_birth_col}). '
                        f'La date de naissance est généralement plus fiable.'
                    ),
                })
        except Exception:
            pass

    # 2. Patient duplicates on identity columns
    _id_candidates = [
        orig for lw, orig in _all_col_lower.items()
        if any(kw in lw for kw in _ANOMALY_NAME_KEYWORDS + _ANOMALY_ID_KEYWORDS)
    ]
    if len(_id_candidates) >= 2 and total_rows > 1:
        try:
            _dup_mask = dataframe[_id_candidates].astype(str).duplicated(keep=False)
            _dup_count = int(_dup_mask.sum())
            if _dup_count > 0:
                cross_column_issues.append({
                    'type': 'doublons_patients',
                    'columns': _id_candidates,
                    'duplicate_rows': _dup_count,
                    'explanation': (
                        f'{_dup_count} ligne(s) semblent être des doublons patients '
                        f'(valeurs identiques sur {_id_candidates}). '
                        f'Vérification manuelle recommandée avant fusion.'
                    ),
                })
        except Exception:
            pass

    # ── Medical coherence rules (hemodialysis domain) ─────────────────────────
    def _col(name):
        """Return the actual column object from dataframe if it exists (case-insensitive)."""
        for c in dataframe.columns:
            if str(c).lower().replace(' ', '_') == name.lower().replace(' ', '_'):
                return c
        return None

    def _series(name):
        c = _col(name)
        return dataframe[c] if c is not None else None

    try:
        # Rule 1 — debut_dialyse_urgence=1 AND debut_dialyse_planifie=1 (mutually exclusive)
        s_urg = _series('debut_dialyse_urgence')
        s_pla = _series('debut_dialyse_planifie')
        if s_urg is not None and s_pla is not None:
            _mask = (pd.to_numeric(s_urg, errors='coerce') == 1) & (pd.to_numeric(s_pla, errors='coerce') == 1)
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('debut_dialyse_urgence'), _col('debut_dialyse_planifie')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont debut_dialyse_urgence=1 ET debut_dialyse_planifie=1 simultanément. '
                        f'Ces deux colonnes sont mutuellement exclusives — un démarrage est soit urgent soit planifié. '
                        f'Vérifier et corriger l\'une des deux valeurs.'
                    ),
                })

        # Rule 2 — deces=1 but date_deces is null
        s_dec = _series('deces')
        s_ddate = _series('date_deces')
        if s_dec is not None and s_ddate is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 1) & s_ddate.isna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('date_deces')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=1 mais date_deces est manquante. '
                        f'La date du décès doit être renseignée pour tout patient décédé.'
                    ),
                })

        # Rule 3 — deces=1 but cause_deces is null
        s_cause = _series('cause_deces')
        if s_dec is not None and s_cause is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 1) & s_cause.isna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('cause_deces')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=1 mais cause_deces est manquante. '
                        f'La cause du décès doit être documentée.'
                    ),
                })

        # Rule 4 — seances_par_semaine=0 with hemodialyse=1
        s_seances = _series('seances_par_semaine')
        s_hd = _series('hemodialyse')
        if s_seances is not None and s_hd is not None:
            _mask = (s_seances.astype(str).str.strip() == '0') & (pd.to_numeric(s_hd, errors='coerce') == 1)
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('seances_par_semaine'), _col('hemodialyse')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont seances_par_semaine=0 alors que hemodialyse=1. '
                        f'Un patient en hémodialyse active doit avoir au moins 2-3 séances/semaine.'
                    ),
                })

        # Rule 5 — dialyse_peritoneale=1 AND fistule_arterioveineuse=1 (incoherent)
        s_dp = _series('dialyse_peritoneale')
        s_fav = _series('fistule_arterioveineuse')
        if s_dp is not None and s_fav is not None:
            _mask = (pd.to_numeric(s_dp, errors='coerce') == 1) & (pd.to_numeric(s_fav, errors='coerce') == 1)
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('dialyse_peritoneale'), _col('fistule_arterioveineuse')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont dialyse_peritoneale=1 ET fistule_arterioveineuse=1. '
                        f'La FAV est spécifique à l\'hémodialyse — incohérent avec dialyse péritonéale.'
                    ),
                })

        # Rule 6 — deces=0 (vivant) but date_deces is filled
        if s_dec is not None and s_ddate is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 0) & s_ddate.notna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('date_deces')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=0 (vivant) mais une date_deces est renseignée. '
                        f'Si le patient est vivant, date_deces doit être vide.'
                    ),
                })

        # Rule 6b — deces=9 (inconnu) but date_deces is filled (contradictory)
        if s_dec is not None and s_ddate is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 9) & s_ddate.notna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('date_deces')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=9 (statut inconnu) mais une date_deces est renseignée. '
                        f'Si le statut de décès est inconnu, la date de décès ne devrait pas être renseignée. '
                        f'Vérifier si le statut doit être corrigé à 1 (décédé) ou si la date doit être supprimée.'
                    ),
                })

        # Rule 7 — delai_jusquau_deces_jours filled but deces=0
        s_delai = _series('delai_jusquau_deces_jours')
        if s_dec is not None and s_delai is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 0) & s_delai.notna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('delai_jusquau_deces_jours')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=0 mais delai_jusquau_deces_jours est renseigné.'
                    ),
                })

        # Rule 7b — deces=9 (inconnu) but delai_jusquau_deces_jours is filled
        if s_dec is not None and s_delai is not None:
            _mask = (pd.to_numeric(s_dec, errors='coerce') == 9) & s_delai.notna()
            _n = int(_mask.sum())
            if _n > 0:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('deces'), _col('delai_jusquau_deces_jours')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont deces=9 (statut inconnu) mais delai_jusquau_deces_jours est renseigné. '
                        f'Un délai de décès ne peut pas être calculé si le statut de décès est inconnu.'
                    ),
                })

        # Rule 8 — hemodialyse=0 AND dialyse_peritoneale=0 AND transplantation=0 (no treatment)
        s_trans = _series('transplantation')
        if s_hd is not None and s_dp is not None and s_trans is not None:
            _mask = (
                (pd.to_numeric(s_hd, errors='coerce') == 0) &
                (pd.to_numeric(s_dp, errors='coerce') == 0) &
                (pd.to_numeric(s_trans, errors='coerce') == 0)
            )
            _n = int(_mask.sum())
            if _n > 5:
                cross_column_issues.append({
                    'type': 'contradiction_logique',
                    'columns': [_col('hemodialyse'), _col('dialyse_peritoneale'), _col('transplantation')],
                    'inconsistent_rows': _n,
                    'explanation': (
                        f'{_n} patient(s) ont hemodialyse=0, dialyse_peritoneale=0 et transplantation=0 '
                        f'simultanément. Ces patients n\'ont aucun traitement de suppléance renseigné — à vérifier.'
                    ),
                })

    except Exception:
        pass
    # ── End medical coherence rules ───────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────

    # ── Medical domain validation (ranges + valid categorical codes) ──────────
    _domain_numeric = _MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}
    _domain_categorical = _MEDICAL_DOMAIN_RULES.get('categorical_codes') or {}

    # Build a lookup: lowercase col name → column profile dict (for fast access)
    _col_profile_map = {str(cp.get('column') or cp.get('name') or '').lower(): cp for cp in columns_profile}

    for _col_name in dataframe.columns:
        _col_key = str(_col_name).lower()
        _cp = _col_profile_map.get(_col_key)
        if _cp is None:
            continue

        # ── Numeric range validation ─────────────────────────────────────────
        _rule = _domain_numeric.get(_col_name) or _domain_numeric.get(_col_key)
        if _rule:
            _num_series = pd.to_numeric(dataframe[_col_name], errors='coerce').dropna()
            if not _num_series.empty:
                _rmin, _rmax = _rule.get('min'), _rule.get('max')
                _unit = _rule.get('unit', '')
                _ctx = _rule.get('context', '')
                _existing = list(_cp.get('anomaly_candidates') or [])
                if _rmin is not None:
                    _below = _num_series[_num_series < _rmin]
                    if not _below.empty:
                        _existing.append({
                            'value': (
                                f'{len(_below)} valeur(s) < {_rmin} {_unit} '
                                f'(impossible pour {_ctx}): {_below.head(3).tolist()}'
                            ),
                            'type': 'valeur_aberrante',
                            'count': int(len(_below)),
                        })
                if _rmax is not None:
                    _above = _num_series[_num_series > _rmax]
                    if not _above.empty:
                        _existing.append({
                            'value': (
                                f'{len(_above)} valeur(s) > {_rmax} {_unit} '
                                f'(impossible pour {_ctx}): {_above.head(3).tolist()}'
                            ),
                            'type': 'valeur_aberrante',
                            'count': int(len(_above)),
                        })
                if _existing:
                    _cp['anomaly_candidates'] = _existing[:12]

        # ── Categorical code validation ───────────────────────────────────────
        _cat_rule = _domain_categorical.get(_col_name) or _domain_categorical.get(_col_key)
        if _cat_rule:
            _valid_codes = set(str(k) for k in (_cat_rule.get('codes') or {}).keys())
            _note = _cat_rule.get('note', '')
            _code_labels = _cat_rule.get('codes') or {}
            # Store domain metadata on column profile so LLM prompt sees it
            _cp['domain_metadata'] = {
                'valid_codes': _code_labels,
                'note': _note,
            }
            # Detect values outside valid codes.
            # Normalize float codes: "4.0" → "4" so valid integer codes stored as floats
            # (common in pandas after CSV import) are not falsely flagged as invalid.
            def _norm_cat_code(v):
                s = str(v).strip()
                try:
                    f = float(s)
                    if f == int(f):
                        return str(int(f))
                except (ValueError, TypeError):
                    pass
                return s
            _str_series = dataframe[_col_name].dropna().apply(_norm_cat_code)
            _invalid_mask = ~_str_series.isin(_valid_codes)
            _invalid_vals = _str_series[_invalid_mask]
            if not _invalid_vals.empty:
                _vc = _invalid_vals.value_counts()
                _existing = list(_cp.get('anomaly_candidates') or [])
                for _bad_val, _bad_cnt in _vc.head(5).items():
                    _existing.append({
                        'value': (
                            f'code invalide "{_bad_val}" ({_bad_cnt} occurrence(s)) — '
                            f'codes valides: {list(_valid_codes)}'
                        ),
                        'type': 'code_invalide',
                        'count': int(_bad_cnt),
                    })
                _cp['anomaly_candidates'] = _existing[:12]
    # ── End medical domain validation ─────────────────────────────────────────

    profile = {
        'rows': total_rows,
        'columns': total_columns,
        'total_cells': total_cells,
        'missing_cells': missing_cells,
        'missing_pct': round((missing_cells / total_cells) * 100, 2) if total_cells else 0.0,
        'duplicate_rows': duplicate_rows,
        'duplicate_pct': duplicate_ratio,
        'column_names': [str(column) for column in dataframe.columns.tolist()],
        'columns_profile': columns_profile,
        'numeric_columns_profile': numeric_columns_profile,
        'categorical_columns_profile': categorical_columns_profile,
        'preview_rows': _dataframe_to_rows(dataframe.head(3)),
    }
    if cross_column_issues:
        profile['cross_column_issues'] = cross_column_issues
    return profile


def _get_section_prefix_for_column(column_name):
    normalized = normalize_header(column_name)
    for prefix, section_name in SECTION_PREFIX_MAP.items():
        if normalized.startswith(prefix):
            return section_name
    return 'generic_data'


def _build_preprocess_chunks(dataframe, technical_profile, max_rows_per_chunk=40):
    """
    Build semantic chunks for LLM analysis.

    Goals:
    - Chunk by sections (column groups) using SECTION_PREFIX_MAP.
    - Preserve patient coherence when a patient identifier column is present.
    - Limit chunk size by rows and by estimated characters (env: CHUNK_MAX_CHARS).
    - Expose chunk metadata useful for later merge/merge-intelligent logic.
    """
    chunks = []
    total_rows = int(len(dataframe.index))
    columns = [str(column) for column in dataframe.columns.tolist()]

    # Configurable limits
    try:
        max_chars = int(os.environ.get('CHUNK_MAX_CHARS', '4000'))
    except Exception:
        max_chars = 4000
    try:
        max_rows = int(os.environ.get('CHUNK_MAX_ROWS', str(max_rows_per_chunk)))
    except Exception:
        max_rows = max_rows_per_chunk

    # Heuristic: detect patient identifier column to keep patient rows together
    patient_id_col = None
    id_candidates = [c for c in columns if any(token in c.lower() for token in ('patient', 'patient_id', 'id_patient', 'id', 'nid', 'no_patient', 'numero'))]
    if id_candidates:
        # prefer exact patient_id-like names
        for cand in id_candidates:
            try:
                unique_count = int(dataframe[cand].nunique(dropna=True))
                if unique_count > 0 and unique_count < max(2, total_rows // 2):
                    patient_id_col = cand
                    break
            except Exception:
                continue

    # Group columns by section prefix
    grouped_columns = {}
    for column in columns:
        grouped_columns.setdefault(_get_section_prefix_for_column(column), []).append(column)

    def _estimate_row_chars(row_series):
        try:
            return sum(len(str(v or '')) for v in row_series.tolist())
        except Exception:
            return 0

    for section_name, section_columns in grouped_columns.items():
        if not section_columns:
            continue
        section_frame = dataframe[section_columns]
        row_indices = list(section_frame.index)

        if patient_id_col and patient_id_col in dataframe.columns:
            # Build groups of contiguous rows per patient id to preserve coherence
            groups = []
            current_group = {'start': None, 'end': None, 'rows': [], 'chars': 0, 'patient_id': None}
            for idx in row_indices:
                pid = dataframe.at[idx, patient_id_col] if patient_id_col in dataframe.columns else None
                if current_group['patient_id'] is None:
                    current_group['patient_id'] = pid
                    current_group['start'] = idx
                if pid != current_group['patient_id'] and current_group['rows']:
                    current_group['end'] = current_group['rows'][-1]
                    groups.append(current_group)
                    current_group = {'start': idx, 'end': None, 'rows': [], 'chars': 0, 'patient_id': pid}
                # add row
                row_series = section_frame.loc[idx] if idx in section_frame.index else section_frame.iloc[0:0]
                rchars = _estimate_row_chars(row_series)
                current_group['rows'].append(idx)
                current_group['chars'] += rchars
            if current_group['rows']:
                current_group['end'] = current_group['rows'][-1]
                groups.append(current_group)

            # Build chunks by aggregating patient groups until limits reached
            current_chunk = None
            for grp in groups:
                if current_chunk is None:
                    current_chunk = {'rows': [], 'chars': 0, 'start': grp['start'], 'end': grp['end']}
                # If adding this group would exceed limits and current_chunk not empty, flush
                if (len(current_chunk['rows']) + len(grp['rows']) > max_rows) or (current_chunk['chars'] + grp['chars'] > max_chars and current_chunk['rows']):
                    # flush
                    start_idx = current_chunk['start']
                    end_idx = current_chunk['end']
                    chunk_frame = section_frame.loc[current_chunk['rows']]
                    chunks.append({
                        'chunk_id': f'{section_name}:rows:{start_idx}-{end_idx}',
                        'kind': 'row_batch',
                        'section': section_name,
                        'columns': section_columns,
                        'rows_range': [int(start_idx), int(end_idx)],
                        'row_count': int(len(current_chunk['rows'])),
                        'preview_rows': _dataframe_to_rows(chunk_frame.head(3)),
                        'estimated_chars': int(current_chunk['chars']),
                        'patient_id_column': patient_id_col,
                    })
                    current_chunk = {'rows': [], 'chars': 0, 'start': grp['start'], 'end': grp['end']}

                # Add group to current chunk (may exceed limits if a single patient is huge)
                current_chunk['rows'].extend(grp['rows'])
                current_chunk['chars'] += grp['chars']
                current_chunk['end'] = grp['end']

            if current_chunk and current_chunk['rows']:
                start_idx = current_chunk['start']
                end_idx = current_chunk['end']
                chunk_frame = section_frame.loc[current_chunk['rows']]
                chunks.append({
                    'chunk_id': f'{section_name}:rows:{start_idx}-{end_idx}',
                    'kind': 'row_batch',
                    'section': section_name,
                    'columns': section_columns,
                    'rows_range': [int(start_idx), int(end_idx)],
                    'row_count': int(len(current_chunk['rows'])),
                    'preview_rows': _dataframe_to_rows(chunk_frame.head(3)),
                    'estimated_chars': int(current_chunk['chars']),
                    'patient_id_column': patient_id_col,
                })
        else:
            # No patient id: simple row-based chunking with char-limit enforcement
            start_ptr = 0
            indices = row_indices
            n = len(indices)
            while start_ptr < n:
                end_ptr = min(start_ptr + max_rows, n)
                chunk_indices = indices[start_ptr:end_ptr]
                # tighten if estimated chars exceed max_chars
                chars = 0
                for i, idx in enumerate(chunk_indices):
                    row_series = section_frame.loc[idx]
                    chars += _estimate_row_chars(row_series)
                    if chars > max_chars:
                        # cut here
                        chunk_indices = chunk_indices[:i+1]
                        end_ptr = start_ptr + i + 1
                        break

                start_idx = chunk_indices[0]
                end_idx = chunk_indices[-1]
                chunk_frame = section_frame.loc[chunk_indices]
                chunks.append({
                    'chunk_id': f'{section_name}:rows:{start_idx}-{end_idx}',
                    'kind': 'row_batch',
                    'section': section_name,
                    'columns': section_columns,
                    'rows_range': [int(start_idx), int(end_idx)],
                    'row_count': int(len(chunk_frame.index)),
                    'preview_rows': _dataframe_to_rows(chunk_frame.head(3)),
                    'estimated_chars': int(chars),
                })
                start_ptr = end_ptr

    if not chunks:
        chunks.append({
            'chunk_id': 'generic:empty',
            'kind': 'fallback',
            'section': 'generic_data',
            'columns': columns,
            'rows_range': [0, 0],
            'row_count': 0,
            'preview_rows': [],
            'estimated_chars': 0,
        })

    # Attach chunk summary into technical_profile for visibility
    technical_profile['chunk_count'] = len(chunks)
    technical_profile['chunks'] = [
        {
            'chunk_id': chunk['chunk_id'],
            'kind': chunk.get('kind'),
            'section': chunk.get('section'),
            'row_count': chunk.get('row_count'),
            'columns_count': len(chunk.get('columns', [])),
            'estimated_chars': int(chunk.get('estimated_chars') or 0),
        }
        for chunk in chunks
    ]
    return chunks


def _build_retrieval_context(dataframe, chunks, technical_profile, stage_name='diagnostic', max_chunks=4, progress_callback=None):
    return build_rag_context(
        dataframe,
        chunks,
        technical_profile,
        stage_name=stage_name,
        max_chunks=max_chunks,
        progress_callback=progress_callback,
    )


def _determine_preprocess_route(technical_profile):
    return estimate_route(technical_profile)


def _strip_json_wrappers(response_text):
    text = str(response_text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


def _extract_balanced_json_candidate(response_text):
    text = str(response_text or '')
    start_index = None
    stack = []
    in_string = False
    escape_next = False

    for index, character in enumerate(text):
        if start_index is None:
            if character in '{[':
                start_index = index
                stack.append(character)
            continue

        if in_string:
            if escape_next:
                escape_next = False
                continue
            if character == '\\':
                escape_next = True
                continue
            if character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
            continue

        if character in '{[':
            stack.append(character)
            continue

        if character in '}]' and stack:
            opening = stack[-1]
            if (opening == '{' and character == '}') or (opening == '[' and character == ']'):
                stack.pop()
                if not stack:
                    return text[start_index:index + 1]

    return None


def _repair_json_text(response_text):
    text = _strip_json_wrappers(response_text)
    if not text:
        return None

    # Helper: extract a candidate starting at pos (returns substring and max depth)
    def _extract_from(text, start_pos):
        stack = []
        in_string = False
        escape = False
        max_depth = 0
        for i in range(start_pos, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch in '{[':
                stack.append(ch)
                max_depth = max(max_depth, len(stack))
                continue
            if ch in '}]' and stack:
                opening = stack[-1]
                if (opening == '{' and ch == '}') or (opening == '[' and ch == ']'):
                    stack.pop()
                    if not stack:
                        return text[start_pos:i + 1], max_depth, True
        # not balanced: return until end with depth info
        return text[start_pos:], max_depth, False

    candidates = []
    # full text as first candidate
    candidates.append({'text': text, 'source': 'full', 'depth': 0, 'balanced': False})

    # find all '{' or '[' positions and extract candidates
    for idx, ch in enumerate(text):
        if ch in '{[':
            sub, depth, balanced = _extract_from(text, idx)
            candidates.append({'text': sub.strip(), 'source': f'pos_{idx}', 'depth': depth, 'balanced': balanced})

    # De-duplicate by text
    seen = set()
    uniq_candidates = []
    for c in candidates:
        t = c['text']
        if not t or t in seen:
            continue
        seen.add(t)
        uniq_candidates.append(c)

    best_result = None
    best_score = -1.0

    original_len = len(re.sub(r"\s+","", text)) or 1

    def try_parse(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    def _auto_close_and_parse(s):
        """Try to recover truncated JSON by closing dangling string/brackets."""
        if not s:
            return None

        variants = [s]

        # If we likely ended inside a string token, first close the quote.
        quote_count = len(re.findall(r'(?<!\\)"', s))
        if quote_count % 2 == 1:
            variants.append(s + '"')

        # If likely ended after a separator, also try trimming at the last comma.
        last_comma = s.rfind(',')
        if last_comma > 0:
            variants.append(s[:last_comma])

        for base in variants:
            stack = []
            in_string = False
            escape = False
            for ch in base:
                if in_string:
                    if escape:
                        escape = False
                    elif ch == '\\':
                        escape = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                    continue
                if ch in '{[':
                    stack.append(ch)
                elif ch in '}]' and stack:
                    if (stack[-1] == '{' and ch == '}') or (stack[-1] == '[' and ch == ']'):
                        stack.pop()

            closers = []
            while stack:
                opener = stack.pop()
                closers.append('}' if opener == '{' else ']')

            attempt = base + ''.join(closers)
            attempt = re.sub(r',\s*([}\]])', r'\1', attempt)
            parsed = try_parse(attempt)
            if parsed is not None:
                return parsed, attempt

        return None

    for c in uniq_candidates:
        cand = c['text']
        # 1) try direct parse
        parsed = try_parse(cand)
        if parsed is not None:
            plen = len(re.sub(r"\s+","", cand))
            base_score = min(1.0, plen / original_len)
            method = 'direct_parse'
            is_partial = (plen < original_len)
            depth_factor = min(1.0, float(c.get('depth', 0)) / 10.0)
            # critical keys presence
            CRITICAL_KEYS = ('dataset_summary', 'medical_analysis', 'corrections_applied')
            keys_found = 0
            if isinstance(parsed, dict):
                for k in CRITICAL_KEYS:
                    if k in parsed and parsed[k]:
                        keys_found += 1
            keys_score = keys_found / max(1, len(CRITICAL_KEYS))
            # final weighted score
            score = round(min(1.0, 0.6 * base_score + 0.25 * depth_factor + 0.15 * keys_score), 3)
            meta = {'recovery_score': score, 'method_used': method, 'is_partial': is_partial, 'depth': c.get('depth', 0), 'keys_found': keys_found}
            best_result = (parsed, meta) if score > best_score else best_result
            best_score = max(best_score, score)
            if score == 1.0:
                break

        # 2) try removing trailing fragments (trim) progressively at sensible breakpoints
        trimmed = None
        trim_points = [m.start() for m in re.finditer(r'[\}\]\",]', cand)]
        # include full length as last resort
        trim_points.append(len(cand) - 1)
        # iterate trimming to the last sensible point
        for tp in reversed(trim_points):
            if tp < max(10, len(cand) // 10):
                break
            sub = cand[:tp + 1]
            sub = re.sub(r',\s*([}\]])', r'\1', sub)
            parsed = try_parse(sub)
            if parsed is not None:
                plen = len(re.sub(r"\s+","", sub))
                score = min(1.0, plen / original_len)
                method = 'trim_trailing'
                is_partial = True
                meta = {'recovery_score': round(score, 3), 'method_used': method, 'is_partial': is_partial}
                if score > best_score:
                    best_result = (parsed, meta)
                    best_score = score
                trimmed = True
                break

        if trimmed:
            continue

        # 3) try auto-closing based on unmatched openers
        opens = cand.count('{') + cand.count('[')
        closes = cand.count('}') + cand.count(']')
        needed = opens - closes
        if needed > 0:
            auto = _auto_close_and_parse(cand)
            if auto is not None:
                parsed, attempt = auto
                plen = len(re.sub(r"\s+", "", attempt))
                base_score = min(1.0, plen / original_len)
                depth_factor = min(1.0, float(c.get('depth', 0)) / 10.0)
                keys_found = 0
                if isinstance(parsed, dict):
                    for k in ('dataset_summary', 'medical_analysis', 'corrections_applied'):
                        if k in parsed and parsed[k]:
                            keys_found += 1
                keys_score = keys_found / 3.0
                score = round(min(1.0, 0.6 * base_score + 0.25 * depth_factor + 0.15 * keys_score), 3)
                method = 'auto_close'
                is_partial = True
                meta = {'recovery_score': score, 'method_used': method, 'is_partial': is_partial, 'depth': c.get('depth', 0), 'keys_found': keys_found}
                if score > best_score:
                    best_result = (parsed, meta)
                    best_score = score
                continue

        # 4) attempt python literal fallback (single quotes, None/True/False)
        try:
            py_cand = re.sub(r"\bnull\b", 'None', cand, flags=re.IGNORECASE)
            py_cand = re.sub(r"\btrue\b", 'True', py_cand, flags=re.IGNORECASE)
            py_cand = re.sub(r"\bfalse\b", 'False', py_cand, flags=re.IGNORECASE)
            parsed_py = ast.literal_eval(py_cand)
            if parsed_py is not None:
                plen = len(re.sub(r"\s+","", cand))
                base_score = min(1.0, plen / original_len)
                depth_factor = min(1.0, float(c.get('depth', 0)) / 10.0)
                keys_found = 0
                if isinstance(parsed_py, dict):
                    for k in ('dataset_summary', 'medical_analysis', 'corrections_applied'):
                        if k in parsed_py and parsed_py[k]:
                            keys_found += 1
                keys_score = keys_found / 3.0
                score = round(min(1.0, 0.6 * base_score + 0.25 * depth_factor + 0.15 * keys_score), 3)
                method = 'python_literal'
                is_partial = True
                meta = {'recovery_score': score, 'method_used': method, 'is_partial': is_partial, 'depth': c.get('depth', 0), 'keys_found': keys_found}
                if score > best_score:
                    best_result = (parsed_py, meta)
                    best_score = score
        except Exception:
            pass

    # If we found a result, normalize return to dict and attach metadata
    if best_result is not None:
        parsed_obj, meta = best_result

        # Determine structure type
        if isinstance(parsed_obj, list):
            structure_type = 'array_root'
        elif isinstance(parsed_obj, dict):
            structure_type = 'object'
        else:
            structure_type = 'mixed'

        # Compute domain score with presence + completeness checks
        CRITICAL_KEYS = ('dataset_summary', 'medical_analysis', 'corrections_applied')
        presence_score = 0.0
        completeness_score = 0.0

        def _dataset_summary_complete(ds):
            if not isinstance(ds, dict):
                return 0.0
            # require at least one of these fields to be present and non-empty
            for key in ('rows', 'columns', 'missing_cells', 'missing_pct'):
                if key in ds and ds[key] not in (None, {}, [], ''):
                    return 1.0
            return 0.0

        def _medical_analysis_complete(ma):
            if not isinstance(ma, dict):
                return 0.0
            # prefer explicit detected anomalies or a non-trivial summary
            issues = ma.get('issues')
            if isinstance(issues, (list, tuple)) and len(issues) > 0:
                return 1.0
            summary = ma.get('summary') or ''
            try:
                if isinstance(summary, str) and len(summary.strip()) >= 20:
                    return 1.0
            except Exception:
                pass
            # fallback: any other non-empty key indicates some analysis
            for k, v in ma.items():
                if k in ('issues', 'summary'):
                    continue
                if v not in (None, {}, [], ''):
                    return 1.0
            return 0.0

        def _corrections_applied_complete(ca):
            # must be explicitly present and a list (empty list acceptable)
            return 1.0 if isinstance(ca, list) else 0.0

        if isinstance(parsed_obj, dict):
            # presence: count keys that exist (regardless of truthiness)
            present = 0
            for k in CRITICAL_KEYS:
                if k in parsed_obj:
                    present += 1
            presence_score = present / float(len(CRITICAL_KEYS))

            # completeness per-key
            ds_comp = _dataset_summary_complete(parsed_obj.get('dataset_summary'))
            ma_comp = _medical_analysis_complete(parsed_obj.get('medical_analysis'))
            ca_comp = _corrections_applied_complete(parsed_obj.get('corrections_applied'))
            completeness_score = (ds_comp + ma_comp + ca_comp) / float(len(CRITICAL_KEYS))

        elif isinstance(parsed_obj, list):
            # for array roots, evaluate items that are dicts
            items = [it for it in parsed_obj if isinstance(it, dict)]
            if not items:
                presence_score = 0.0
                completeness_score = 0.0
            else:
                pres_values = []
                comp_values = []
                for it in items:
                    present = 0
                    for k in CRITICAL_KEYS:
                        if k in it:
                            present += 1
                    pres_values.append(present / float(len(CRITICAL_KEYS)))

                    ds_comp = _dataset_summary_complete(it.get('dataset_summary'))
                    ma_comp = _medical_analysis_complete(it.get('medical_analysis'))
                    ca_comp = _corrections_applied_complete(it.get('corrections_applied'))
                    comp_values.append((ds_comp + ma_comp + ca_comp) / float(len(CRITICAL_KEYS)))

                presence_score = sum(pres_values) / len(pres_values)
                completeness_score = sum(comp_values) / len(comp_values)

        # combine presence and completeness into domain_score
        presence_score = round(float(presence_score), 3)
        completeness_score = round(float(completeness_score), 3)
        domain_score = round(min(1.0, 0.5 * presence_score + 0.5 * completeness_score), 3)

        # Compute structure score
        depth_factor = min(1.0, float(meta.get('depth', 0)) / 10.0)
        parsed_valid = 1.0 if isinstance(parsed_obj, (dict, list)) else 0.0
        # penalize cases where method indicates no recovery
        method_used = meta.get('method_used', '') or ''
        if 'no_recovery' in method_used:
            parsed_valid = 0.0
        structure_score = round(min(1.0, 0.7 * parsed_valid + 0.3 * depth_factor), 3)

        # Final combined score (structure/domain split)
        domain_score = round(float(domain_score), 3)
        final_score = round(min(1.0, 0.4 * structure_score + 0.6 * domain_score), 3)

        # Domain gate: stricter medical rule
        # enforce a minimum domain_score threshold for trusting outputs
        domain_gate = domain_score >= 0.4

        # Annotate meta with presence/completeness breakdown
        meta.update({
            'structure_type': structure_type,
            'structure_score': structure_score,
            'domain_score': domain_score,
            'presence_score': presence_score,
            'completeness_score': completeness_score,
            'recovery_score': final_score,
            'domain_gate': domain_gate,
        })

        # set failure_type: hard if domain gate not satisfied
        meta['failure_type'] = 'hard' if not domain_gate else 'soft'

        # special handling for arrays: wrap results but require domain inspection
        if structure_type == 'array_root':
            wrapped = {'results': parsed_obj}
            # annotate method
            meta['method_used'] = meta.get('method_used', '') + '|array_root_wrapped'
            wrapped.update(meta)
            wrapped['trusted'] = bool(domain_gate)
            return wrapped

        # ensure dict and inject missing critical keys if needed
        if isinstance(parsed_obj, dict):
            injected = False
            if 'dataset_summary' not in parsed_obj:
                parsed_obj['dataset_summary'] = {}
                injected = True
            if 'medical_analysis' not in parsed_obj:
                parsed_obj['medical_analysis'] = {}
                injected = True
            if 'corrections_applied' not in parsed_obj:
                parsed_obj['corrections_applied'] = []
                injected = True
            if injected:
                meta['method_used'] = meta.get('method_used', '') + '|structure_injected'
                meta['is_partial'] = True
            parsed_obj.update(meta)
            # If domain gate failed, mark not trusted explicitly
            if not domain_gate:
                parsed_obj['trusted'] = False
            else:
                parsed_obj['trusted'] = True
            return parsed_obj

        # fallback non-dict non-list
        out = {'recovered_non_dict': parsed_obj}
        out.update(meta)
        return out

    # Nothing worked: return structured minimal fallback with low score
    excerpt = (text[:1000] + '...') if len(text) > 1000 else text
    return {
        'recovery_status': 'failed_partial_parse',
        'raw_excerpt': excerpt,
        'reason': 'truncated_llm_output',
        'recovery_score': 0.0,
        'method_used': 'no_recovery',
        'is_partial': True,
        'failure_type': 'hard',
        'domain_gate': False,
        'trusted': False,
    }


def _parse_llm_analysis_response(raw_response):
    def _default_preprocess_llm_output():
        return {
            'dataset_summary': {},
            'medical_analysis': {},
            'missing_values_analysis': {},
            'outliers_analysis': {},
            'duplicate_analysis': {},
            'corrections_applied': [],
            'suspect_values': [],
            'remaining_risks': [],
            'recommendations': [],
            'cleaned_dataset_preview': [],
            'processing_statistics': {},
            'quality_score': {},
            'summary': '',
            'issues': [],
            'correction_plan': {},
            'corrected_preview_rows': [],
            'column_assessment': [],
            'limitations': [],
            'raw_response': None,
        }

    if isinstance(raw_response, dict):
        merged = _default_preprocess_llm_output()
        merged.update(raw_response)
        return merged

    response_text = str(raw_response or '').strip()
    if not response_text:
        default_output = _default_preprocess_llm_output()
        default_output['summary'] = 'Le modele n a retourne aucun contenu exploitable.'
        default_output['limitations'] = ['Reponse vide du modele.']
        return default_output

    parsed = _repair_json_text(response_text)
    if parsed is not None:
        merged = _default_preprocess_llm_output()
        merged.update(parsed)
        merged['raw_response'] = response_text
        return merged

    # Dernier recours: tenter de récupérer uniquement la première structure JSON fermée.
    extracted = _extract_balanced_json_candidate(response_text)
    if extracted:
        parsed = _repair_json_text(extracted)
        if parsed is not None:
            merged = _default_preprocess_llm_output()
            merged.update(parsed)
            return merged

    # Rescue truncated responses: try to extract a partial "issues" array even when
    # the outer JSON object was cut off mid-stream.
    import re as _re_rescue
    _issues_match = _re_rescue.search(r'"issues"\s*:\s*(\[.*)', response_text, _re_rescue.DOTALL)
    if _issues_match:
        _raw_arr = _issues_match.group(1)
        # Try progressively shorter suffixes to find a parseable list
        for _end in range(len(_raw_arr), max(2, len(_raw_arr) - 500), -1):
            try:
                _partial = json.loads(_raw_arr[:_end])
                if isinstance(_partial, list) and _partial:
                    partial_output = _default_preprocess_llm_output()
                    partial_output['issues'] = [i for i in _partial if isinstance(i, dict)]
                    partial_output['summary'] = 'Réponse tronquée — issues partiellement récupérées.'
                    partial_output['limitations'] = ['Réponse LLM tronquée, JSON partiel récupéré.']
                    partial_output['raw_response'] = response_text
                    partial_output['is_partial'] = True
                    return partial_output
            except (json.JSONDecodeError, ValueError):
                continue

    fallback_output = _default_preprocess_llm_output()
    fallback_output['summary'] = response_text[:1200]
    fallback_output['limitations'] = ['Le modele a repondu, mais le JSON est invalide.']
    fallback_output['raw_response'] = response_text
    fallback_output['failure_type'] = 'hard'
    fallback_output['domain_gate'] = False
    fallback_output['trusted'] = False
    fallback_output['structure_type'] = 'invalid_json'
    fallback_output['structure_score'] = 0.0
    fallback_output['domain_score'] = 0.0
    fallback_output['presence_score'] = 0.0
    fallback_output['completeness_score'] = 0.0
    fallback_output['recovery_score'] = 0.0
    fallback_output['method_used'] = 'fallback_invalid_json'
    fallback_output['is_partial'] = True
    return fallback_output


def _build_llm_payload(dataframe, technical_profile):
    max_preview_rows = int(os.environ.get('OLLAMA_PREVIEW_ROWS', '3'))
    max_column_samples = int(os.environ.get('OLLAMA_COLUMN_SAMPLES', '1'))
    max_columns = int(os.environ.get('OLLAMA_MAX_COLUMNS', '40'))
    max_value_chars = int(os.environ.get('OLLAMA_MAX_VALUE_CHARS', '50'))

    def _llm_compact_value(value):
        normalized = _to_json_compatible(value)
        if isinstance(normalized, str) and len(normalized) > max_value_chars:
            return normalized[:max_value_chars] + '...'
        return normalized

    selected_columns = [str(column) for column in list(dataframe.columns)[:max_columns]]
    selected_df = dataframe[selected_columns] if selected_columns else dataframe

    preview_rows = _dataframe_to_rows(selected_df.head(max_preview_rows))
    for row in preview_rows:
        if isinstance(row, dict):
            for key in list(row.keys()):
                row[key] = _llm_compact_value(row.get(key))

    column_samples = {
        str(column): [
            _llm_compact_value(value)
            for value in selected_df[column].dropna().head(max_column_samples).tolist()
        ]
        for column in selected_df.columns
    }

    compact_columns_profile = []
    for column_meta in technical_profile.get('columns_profile', []):
        column_name = str(column_meta.get('name') or column_meta.get('column') or '')
        if column_name not in selected_columns:
            continue
        compact_columns_profile.append({
            'name': column_name,
            'dtype': column_meta.get('dtype'),
            'missing_count': column_meta.get('missing_count'),
            'missing_ratio': column_meta.get('missing_ratio', column_meta.get('missing_pct')),
            'unique_values': column_meta.get('unique_values', column_meta.get('non_null_count')),
        })

    compact_profile = {
        'rows': technical_profile.get('rows'),
        'columns': technical_profile.get('columns'),
        'missing_cells': technical_profile.get('missing_cells'),
        'missing_pct': technical_profile.get('missing_pct'),
        'duplicate_rows': technical_profile.get('duplicate_rows'),
        'duplicate_pct': technical_profile.get('duplicate_pct'),
        'columns_profile': compact_columns_profile,
        'numeric_columns_profile': technical_profile.get('numeric_columns_profile', [])[:12],
        'categorical_columns_profile': technical_profile.get('categorical_columns_profile', [])[:12],
        'preview_rows': technical_profile.get('preview_rows', [])[:max_preview_rows],
    }

    return {
        'pack_type': 'structured_analysis_pack',
        'technical_profile': compact_profile,
        'preview_rows': preview_rows,
        'column_samples': column_samples,
        'meta': {
            'selected_columns_count': len(selected_columns),
            'total_columns_count': int(len(dataframe.columns)),
            'preview_rows_count': len(preview_rows),
            'column_samples_per_column': max_column_samples,
        },
    }


def _shrink_llm_payload(payload, max_columns=20, max_preview_rows=2, max_samples_per_column=1):
    if not isinstance(payload, dict):
        return payload

    shrunk = json.loads(json.dumps(payload, default=str))

    technical_profile = shrunk.get('technical_profile') or {}
    columns_profile = technical_profile.get('columns_profile') or []
    selected_column_names = [
        str(item.get('name'))
        for item in columns_profile[:max_columns]
        if isinstance(item, dict) and item.get('name')
    ]

    technical_profile['columns_profile'] = columns_profile[:max_columns]
    technical_profile['numeric_columns_profile'] = (technical_profile.get('numeric_columns_profile') or [])[:max_columns]
    technical_profile['categorical_columns_profile'] = (technical_profile.get('categorical_columns_profile') or [])[:max_columns]
    technical_profile['preview_rows'] = (technical_profile.get('preview_rows') or [])[:max_preview_rows]

    preview_rows = shrunk.get('preview_rows') or []
    shrunk['preview_rows'] = preview_rows[:max_preview_rows]

    column_samples = shrunk.get('column_samples') or {}
    if selected_column_names:
        filtered_samples = {
            name: (column_samples.get(name) or [])[:max_samples_per_column]
            for name in selected_column_names
        }
    else:
        filtered_samples = {
            str(name): (values or [])[:max_samples_per_column]
            for name, values in list(column_samples.items())[:max_columns]
        }
    shrunk['column_samples'] = filtered_samples

    meta = shrunk.get('meta') or {}
    meta['selected_columns_count'] = len(filtered_samples)
    meta['preview_rows_count'] = len(shrunk['preview_rows'])
    meta['column_samples_per_column'] = max_samples_per_column
    shrunk['meta'] = meta

    return shrunk


def _estimate_tokens_from_text(text):
    try:
        s = str(text or '')
        return max(1, int(len(s) / 4))
    except Exception:
        return 1


def _estimate_prompt_and_rag_tokens(payload_for_prompt, retrieval_context):
    try:
        payload_text = json.dumps(payload_for_prompt, ensure_ascii=False, default=str)
    except Exception:
        payload_text = str(payload_for_prompt)
    try:
        rag_text = json.dumps(retrieval_context or {}, ensure_ascii=False, default=str)
    except Exception:
        rag_text = str(retrieval_context)
    return _estimate_tokens_from_text(payload_text), _estimate_tokens_from_text(rag_text)


def _shrink_prompt_for_budget(payload_for_prompt, retrieval_context, available_tokens):
    """
    Reduce prompt payload and retrieval_context to fit within available_tokens.
    Reduction order (priority): history -> retrieved_chunks (RAG secondary) -> column_samples -> preview_rows -> descriptive text
    """
    # Work on copies to avoid mutating caller unexpectedly
    try:
        payload = json.loads(json.dumps(payload_for_prompt, default=str, ensure_ascii=False))
    except Exception:
        payload = dict(payload_for_prompt or {})
    try:
        rag = json.loads(json.dumps(retrieval_context or {}, default=str, ensure_ascii=False))
    except Exception:
        rag = dict(retrieval_context or {})

    def current_tokens():
        p_t, r_t = _estimate_prompt_and_rag_tokens(payload, rag)
        return p_t + r_t

    # Quick no-op
    if current_tokens() <= available_tokens:
        return payload, rag

    # 1) Trim history (oldest first)
    history = payload.get('history') or []
    if isinstance(history, list) and history:
        while history and current_tokens() > available_tokens:
            history.pop(0)
        payload['history'] = history
        if current_tokens() <= available_tokens:
            return payload, rag

    # 2) Reduce retrieved_chunks (RAG secondary) - drop less important chunks first
    retrieved = rag.get('retrieved_chunks') or []
    if isinstance(retrieved, list) and retrieved:
        # keep at least top-1
        while len(retrieved) > 1 and current_tokens() > available_tokens:
            retrieved.pop(-1)
        rag['retrieved_chunks'] = retrieved
        if current_tokens() <= available_tokens:
            return payload, rag

    # 3) Reduce column_samples: drop less helpful columns
    column_samples = payload.get('column_samples') or {}
    if isinstance(column_samples, dict) and column_samples:
        cols = list(column_samples.keys())
        # drop columns from the end until we fit
        while cols and current_tokens() > available_tokens:
            col = cols.pop(-1)
            column_samples.pop(col, None)
        payload['column_samples'] = column_samples
        if current_tokens() <= available_tokens:
            return payload, rag

    # 4) Reduce preview_rows
    preview = payload.get('preview_rows') or []
    if isinstance(preview, list) and preview:
        while preview and current_tokens() > available_tokens:
            preview.pop(-1)
        payload['preview_rows'] = preview
        if current_tokens() <= available_tokens:
            return payload, rag

    # 5) Remove section_fusion and descriptive summaries
    if 'section_fusion' in rag:
        rag.pop('section_fusion', None)
        if current_tokens() <= available_tokens:
            return payload, rag

    # 6) Aggressively truncate chunk summaries in retrieved_chunks
    if isinstance(retrieved, list) and retrieved:
        for i in range(len(retrieved)):
            if current_tokens() <= available_tokens:
                break
            chunk = retrieved[i]
            # keep only minimal fields
            minimal = {
                'chunk_id': chunk.get('chunk_id'),
                'section': chunk.get('section'),
                'row_count': chunk.get('row_count')
            }
            retrieved[i] = minimal
        rag['retrieved_chunks'] = retrieved
        if current_tokens() <= available_tokens:
            return payload, rag

    # If still too big, as a last resort remove rag entirely
    if current_tokens() > available_tokens:
        rag = {'retrieval_policy': 'none', 'retrieved_chunks': []}

    return payload, rag


def _validate_preprocess_llm_output(analysis_result, stage_name, available_columns=None):
    """
    Strict server-side validation for LLM output.
    Returns (is_valid, validation_status, issues).
    """
    available_columns = [str(column) for column in (available_columns or [])]
    issues = []

    if not isinstance(analysis_result, dict):
        issues.append('Resultat LLM non dictionnaire.')
        return False, {
            'chunk_valid': False,
            'schema_valid': False,
            'merge_safe': False,
            'medical_confidence': None,
            'stage': stage_name,
            'issues': issues,
        }, issues

    def _require_type(field_name, expected_type):
        value = analysis_result.get(field_name)
        if not isinstance(value, expected_type):
            issues.append(f'Champ {field_name} invalide ou manquant (type attendu: {expected_type.__name__}).')
            return False
        return True

    def _require_list(field_name):
        return _require_type(field_name, list)

    def _require_dict(field_name):
        return _require_type(field_name, dict)

    def _check_numeric_range(path, value, min_value=None, max_value=None):
        if value is None:
            return True
        if not isinstance(value, (int, float)):
            issues.append(f'Champ numerique invalide: {path}.')
            return False
        if min_value is not None and value < min_value:
            issues.append(f'Champ {path} hors borne minimale {min_value}.')
            return False
        if max_value is not None and value > max_value:
            issues.append(f'Champ {path} hors borne maximale {max_value}.')
            return False
        return True

    schema_ok = True
    is_pass2 = stage_name.startswith('pass2') or stage_name.startswith('single_pass')

    if is_pass2:
        # Pass2 only returns {summary, correction_plan} — skip full pass1 schema
        if not isinstance(analysis_result.get('summary'), str):
            issues.append('Champ summary invalide ou manquant (string attendu).')
            schema_ok = False
        if analysis_result.get('correction_plan') is not None and not isinstance(analysis_result.get('correction_plan'), dict):
            issues.append('Champ correction_plan invalide (dict attendu).')
            schema_ok = False
    else:
        schema_ok &= _require_dict('dataset_summary')
        schema_ok &= _require_dict('medical_analysis')
        schema_ok &= _require_dict('missing_values_analysis')
        schema_ok &= _require_dict('outliers_analysis')
        schema_ok &= _require_dict('duplicate_analysis')
        schema_ok &= _require_list('corrections_applied')
        schema_ok &= _require_list('suspect_values')
        schema_ok &= _require_list('remaining_risks')
        schema_ok &= _require_list('recommendations')
        schema_ok &= _require_list('cleaned_dataset_preview')
        schema_ok &= _require_dict('processing_statistics')
        schema_ok &= _require_dict('quality_score')

        if not isinstance(analysis_result.get('summary'), str):
            issues.append('Champ summary invalide ou manquant (string attendu).')
            schema_ok = False

        if analysis_result.get('correction_plan') is not None and not isinstance(analysis_result.get('correction_plan'), dict):
            issues.append('Champ correction_plan invalide (dict attendu).')
            schema_ok = False

    if not schema_ok:
        return False, {
            'chunk_valid': False,
            'schema_valid': False,
            'merge_safe': False,
            'medical_confidence': None,
            'stage': stage_name,
            'issues': issues,
        }, issues

    dataset_summary = analysis_result.get('dataset_summary') or {}
    processing_statistics = analysis_result.get('processing_statistics') or {}
    quality_score = analysis_result.get('quality_score') or {}
    medical_analysis = analysis_result.get('medical_analysis') or {}
    correction_plan = analysis_result.get('correction_plan') or {}

    business_ok = True
    for key in ['rows', 'row_count', 'duplicate_rows']:
        if key in dataset_summary:
            business_ok &= _check_numeric_range(f'dataset_summary.{key}', dataset_summary.get(key), 0, None)
    for key in ['rows_processed', 'columns_processed', 'chunk_count']:
        if key in processing_statistics:
            business_ok &= _check_numeric_range(f'processing_statistics.{key}', processing_statistics.get(key), 0, None)

    if 'value' in quality_score:
        business_ok &= _check_numeric_range('quality_score.value', quality_score.get('value'), 0, 100)
    if 'confidence' in quality_score:
        business_ok &= _check_numeric_range('quality_score.confidence', quality_score.get('confidence'), 0.0, 1.0)

    if 'confidence' in medical_analysis:
        business_ok &= _check_numeric_range('medical_analysis.confidence', medical_analysis.get('confidence'), 0.0, 1.0)
    if 'medical_confidence' in analysis_result:
        business_ok &= _check_numeric_range('medical_confidence', analysis_result.get('medical_confidence'), 0.0, 1.0)

    merge_safe = True
    # For pass2, available_columns reflects only the compact pack (≤20 cols).
    # LLM may reference any column from the diagnostic — skip existence check for pass2.
    strict_column_check = available_columns and not is_pass2

    if correction_plan:
        required_plan_fields = [
            'rename_columns', 'drop_columns', 'value_mappings', 'fill_missing',
            'type_casts', 'parse_dates', 'trim_whitespace_columns', 'default_values',
        ]
        for field_name in required_plan_fields:
            value = correction_plan.get(field_name)
            expected = dict if field_name in {'rename_columns', 'value_mappings', 'fill_missing', 'type_casts', 'default_values'} else list
            if not isinstance(value, expected):
                issues.append(f'Champ correction_plan.{field_name} invalide (type {expected.__name__} attendu).')
                merge_safe = False

        # Medical safety policy: never auto-drop columns from LLM plans.
        if correction_plan.get('drop_columns'):
            issues.append('Champ correction_plan.drop_columns non autorise (desactive pour securite medicale).')
            merge_safe = False

        rename_columns = correction_plan.get('rename_columns') or {}
        drop_columns = correction_plan.get('drop_columns') or []
        allowed_type_cast_targets = {
            'numeric', 'number', 'float', 'decimal',
            'integer', 'int',
            'date', 'datetime',
            'string', 'text',
        }
        allowed_fill_strategies = {
            'constant', 'mode', 'mean', 'median', 'forward_fill', 'backward_fill'
        }
        if isinstance(rename_columns, dict):
            rename_targets = [str(value) for value in rename_columns.values() if value not in [None, '']]
            if len(rename_targets) != len(set(rename_targets)):
                issues.append('Conflit de renommage: plusieurs colonnes sources ciblent le meme nom.')
                merge_safe = False
            if strict_column_check:
                for source_name, target_name in rename_columns.items():
                    source_name = str(source_name)
                    target_name = str(target_name)
                    if source_name in drop_columns:
                        issues.append(f'Conflit merge: {source_name} est a la fois renomme et supprime.')
                        merge_safe = False
                    if target_name in available_columns and target_name != source_name:
                        issues.append(f'Conflit merge: cible de renommage deja existante ({target_name}).')
                        merge_safe = False

        if strict_column_check and isinstance(rename_columns, dict):
            for source_name in rename_columns.keys():
                if str(source_name) not in available_columns:
                    issues.append(f'Renommage invalide: colonne source introuvable ({source_name}).')
                    merge_safe = False

        type_casts = correction_plan.get('type_casts') or {}
        if isinstance(type_casts, dict):
            for column_name, target_type in type_casts.items():
                if strict_column_check and str(column_name) not in available_columns:
                    issues.append(f'type_casts invalide: colonne introuvable ({column_name}).')
                    merge_safe = False
                if str(target_type).lower() not in allowed_type_cast_targets:
                    issues.append(f'type_casts invalide: type non autorise ({target_type}) pour {column_name}.')
                    merge_safe = False

        parse_dates = correction_plan.get('parse_dates') or []
        if isinstance(parse_dates, list):
            for column_name in parse_dates:
                if strict_column_check and str(column_name) not in available_columns:
                    issues.append(f'parse_dates invalide: colonne introuvable ({column_name}).')
                    merge_safe = False

        fill_missing = correction_plan.get('fill_missing') or {}
        if isinstance(fill_missing, dict):
            for column_name, strategy_spec in fill_missing.items():
                if strict_column_check and str(column_name) not in available_columns:
                    issues.append(f'fill_missing invalide: colonne introuvable ({column_name}).')
                    merge_safe = False
                    continue
                if isinstance(strategy_spec, dict):
                    strategy_name = str(strategy_spec.get('strategy', '')).lower()
                    if strategy_name and strategy_name not in allowed_fill_strategies:
                        issues.append(f'fill_missing invalide: strategie non autorisee ({strategy_name}) pour {column_name}.')
                        merge_safe = False
                    if strategy_name == 'constant' and 'value' not in strategy_spec:
                        issues.append(f'fill_missing invalide: strategy constant sans value pour {column_name}.')
                        merge_safe = False
                elif isinstance(strategy_spec, (str, int, float, bool)) or strategy_spec is None:
                    # scalar default accepted for backward compatibility
                    pass
                else:
                    issues.append(f'fill_missing invalide: specification non supportee pour {column_name}.')
                    merge_safe = False

    if 'limitations' in analysis_result and not isinstance(analysis_result.get('limitations'), list):
        issues.append('Champ limitations invalide (liste attendue).')
        schema_ok = False

    # Derive a normalized medical confidence if not explicitly given.
    medical_confidence = None
    if isinstance(medical_analysis.get('confidence'), (int, float)):
        medical_confidence = float(medical_analysis.get('confidence'))
    elif isinstance(quality_score.get('confidence'), (int, float)):
        medical_confidence = float(quality_score.get('confidence'))
    elif isinstance(quality_score.get('value'), (int, float)):
        medical_confidence = max(0.0, min(1.0, float(quality_score.get('value')) / 100.0))

    if medical_confidence is not None:
        business_ok &= _check_numeric_range('derived_medical_confidence', medical_confidence, 0.0, 1.0)

    valid = schema_ok and business_ok and merge_safe
    validation_status = {
        'chunk_valid': bool(valid),
        'schema_valid': bool(schema_ok),
        'merge_safe': bool(valid and merge_safe),
        'medical_confidence': medical_confidence,
        'stage': stage_name,
        'issues': issues,
        'business_valid': bool(business_ok),
        'available_columns': available_columns[:60],
    }
    return valid, validation_status, issues


def _compute_normalization_severity_score(normalization_notes):
    if not isinstance(normalization_notes, list) or not normalization_notes:
        return 0

    major_markers = (
        'invalid_',
        'non_dict_',
        'coercion_failed',
        'forced_empty',
    )
    major_count = 0
    for note in normalization_notes:
        text = str(note)
        if any(marker in text for marker in major_markers):
            major_count += 1

    if major_count >= 3 or len(normalization_notes) >= 8:
        return 3
    if major_count >= 1:
        return 2
    return 1


def _normalize_correction_plan(analysis_result, available_columns=None):
    """
    Try to coerce and normalize the `correction_plan` structure returned by the LLM
    into the expected schema. This is defensive: the LLM may return slightly
    different types or small structural deviations (strings, lists of pairs,
    etc.). We attempt best-effort conversions so valid plans aren't rejected
    by strict validation.
    """
    if not isinstance(analysis_result, dict):
        return analysis_result

    original_cp = analysis_result.get('correction_plan')
    cp = analysis_result.get('correction_plan')
    if cp is None:
        analysis_result['correction_plan'] = {}
        analysis_result['normalization_notes'] = []
        analysis_result['normalization_severity_score'] = 0
        return analysis_result

    normalization_notes = []

    # If correction_plan is a JSON string, try to parse it
    if isinstance(cp, str):
        try:
            parsed = json.loads(cp)
            if isinstance(parsed, dict):
                cp = parsed
                normalization_notes.append('parsed_correction_plan_json_string')
        except Exception:
            # leave as-is and continue coercions
            cp = {}
            normalization_notes.append('invalid_correction_plan_json_string_replaced_with_empty')

    if not isinstance(cp, dict):
        # replace with empty dict to avoid validation hard-failure
        cp = {}
        normalization_notes.append('non_dict_correction_plan_replaced_with_empty')

    # Ensure expected top-level keys exist with proper types
    expected = {
        'rename_columns': dict,
        'drop_columns': list,
        'value_mappings': dict,
        'fill_missing': dict,
        'type_casts': dict,
        'parse_dates': list,
        'trim_whitespace_columns': list,
        'default_values': dict,
        'unit_conversions': dict,
    }

    normalized = {}
    for key, typ in expected.items():
        val = cp.get(key)
        if val is None:
            normalized[key] = {} if typ is dict else []
            continue

        # If val is a JSON string, try parse
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                val = parsed
                normalization_notes.append(f'{key}_parsed_from_json_string')
            except Exception:
                # fallback: wrap single values into list/dict
                if typ is list:
                    val = [val]
                    normalization_notes.append(f'{key}_wrapped_string_into_list')
                elif typ is dict:
                    val = {}
                    normalization_notes.append(f'{key}_invalid_string_replaced_with_empty_dict')

        # If val is list but dict expected, try convert list of pairs
        if typ is dict and isinstance(val, list):
            try:
                conv = {}
                for item in val:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        k = str(item[0])
                        v = item[1]
                        conv[k] = v
                val = conv
                normalization_notes.append(f'{key}_list_pairs_coerced_to_dict')
            except Exception:
                val = {}
                normalization_notes.append(f'{key}_list_coercion_failed_replaced_with_empty_dict')

        # If val is dict but list expected, convert keys to list
        if typ is list and isinstance(val, dict):
            try:
                # choose values if list-like, else keys
                list_val = []
                for k, v in val.items():
                    if isinstance(v, (list, tuple)):
                        list_val.extend(v)
                    else:
                        list_val.append(k)
                val = list_val
                normalization_notes.append(f'{key}_dict_coerced_to_list')
            except Exception:
                val = []
                normalization_notes.append(f'{key}_dict_coercion_failed_replaced_with_empty_list')

        # Final type guard
        if typ is dict and not isinstance(val, dict):
            val = {}
            normalization_notes.append(f'{key}_invalid_type_replaced_with_empty_dict')
        if typ is list and not isinstance(val, list):
            val = [val] if val is not None else []
            normalization_notes.append(f'{key}_invalid_type_wrapped_into_list')

        # If we have available_columns, filter column lists/maps to known columns
        if available_columns:
            try:
                cols = [str(c) for c in available_columns]
                if isinstance(val, dict):
                    original_keys = list(val.keys())
                    filtered = {}
                    for k, v in val.items():
                        if str(k) in cols:
                            filtered[str(k)] = v
                        else:
                            # try normalized match
                            for c in cols:
                                if normalize_header(c) == normalize_header(k):
                                    filtered[c] = v
                                    break
                    val = filtered
                    if set(str(k) for k in original_keys) != set(str(k) for k in val.keys()):
                        normalization_notes.append(f'{key}_filtered_to_available_columns')
                elif isinstance(val, list):
                    original_len = len(val)
                    filtered = []
                    for item in val:
                        try:
                            name = str(item)
                        except Exception:
                            continue
                        if name in cols:
                            filtered.append(name)
                        else:
                            for c in cols:
                                if normalize_header(c) == normalize_header(name):
                                    filtered.append(c)
                                    break
                    val = filtered
                    if len(val) != original_len:
                        normalization_notes.append(f'{key}_list_filtered_to_available_columns')
            except Exception:
                pass

        # Normalize type_casts: convert pandas-style types to accepted simple types
        if key == 'type_casts' and isinstance(val, dict):
            _type_cast_map = {
                'datetime64': 'datetime', 'datetime64[ns]': 'datetime',
                'int64': 'integer', 'int32': 'integer', 'int16': 'integer', 'int8': 'integer',
                'uint8': 'integer', 'uint16': 'integer', 'uint32': 'integer',
                'float64': 'numeric', 'float32': 'numeric', 'float16': 'numeric',
                'object': 'string', 'str': 'string', 'category': 'string',
                'bool': 'integer',
            }
            _allowed_types = {'numeric', 'number', 'float', 'decimal', 'integer', 'int', 'date', 'datetime', 'string', 'text'}
            # Conversion factors for medical unit conversions (from_unit -> to_unit -> factor)
            _unit_conversion_factors = {
                ('mg/dl', 'mmol/l'): {
                    'phosphore': 0.3229, 'phosphorus': 0.3229, 'phosphore_basale': 0.3229,
                    'calcium': 0.2495, 'calcium_basale': 0.2495,
                    'glucose': 0.0555, 'glycemie': 0.0555,
                    'cholesterol': 0.0259, 'triglycerides': 0.0113,
                    'default': 0.0555,
                },
                ('g/dl', 'g/l'): {'default': 10.0},
                ('mg/dl', 'umol/l'): {
                    'creatinine': 88.42, 'creatinine_basale': 88.42,
                    'uree': 0.357, 'default': 88.42,
                },
                ('mg/dl', 'µmol/l'): {
                    'creatinine': 88.42, 'creatinine_basale': 88.42, 'default': 88.42,
                },
            }
            normalized_tc = {}
            unit_conversions = analysis_result.get('correction_plan', {}).get('unit_conversions') or {}
            for col_n, ttype in val.items():
                type_str = str(ttype).lower().strip().split('[')[0]
                mapped = _type_cast_map.get(type_str, type_str)
                if mapped != str(ttype).lower().strip():
                    normalization_notes.append('type_casts_pandas_type_normalized')
                if mapped in _allowed_types:
                    normalized_tc[col_n] = mapped
                else:
                    # Try to interpret as a unit conversion pattern: "X to Y" or "X → Y"
                    import re as _re
                    unit_match = _re.match(
                        r'([a-z0-9µu°/]+)\s*(?:to|->|→|vers)\s*([a-z0-9µu°/]+)',
                        mapped.replace(' ', '').lower()
                    )
                    if unit_match:
                        from_unit = unit_match.group(1).replace('μ', 'µ')
                        to_unit = unit_match.group(2).replace('μ', 'µ')
                        conv_key = (from_unit, to_unit)
                        if conv_key in _unit_conversion_factors:
                            col_lower = str(col_n).lower()
                            factors = _unit_conversion_factors[conv_key]
                            factor = factors.get(col_lower, factors.get('default'))
                            if factor:
                                unit_conversions[col_n] = {
                                    'from_unit': from_unit,
                                    'to_unit': to_unit,
                                    'factor': factor,
                                }
                                normalization_notes.append(f'type_casts_unit_conversion_detected:{col_n}:{from_unit}->{to_unit}')
                            else:
                                normalization_notes.append(f'type_casts_unit_conversion_unknown_factor_skipped:{col_n}')
                        else:
                            normalization_notes.append(f'type_casts_unit_conversion_unsupported_skipped:{col_n}:{mapped}')
                    else:
                        normalization_notes.append(f'type_casts_invalid_type_skipped:{mapped}')
            val = normalized_tc
            if unit_conversions:
                normalized['unit_conversions'] = unit_conversions

        # Normalize fill_missing: convert string strategies to {"strategy": ...} dicts
        if key == 'fill_missing' and isinstance(val, dict):
            for col_n in list(val.keys()):
                spec = val[col_n]
                if isinstance(spec, str) and spec:
                    val[col_n] = {'strategy': spec}
                    normalization_notes.append('fill_missing_string_strategy_normalized')

        if key == 'drop_columns' and val:
            # Safety policy: never drop columns automatically in medical preprocessing.
            normalization_notes.append('drop_columns_forced_empty_by_medical_policy')
            val = []

        normalized[key] = val

    analysis_result['correction_plan'] = normalized
    dedup_notes = list(dict.fromkeys(normalization_notes))
    analysis_result['normalization_notes'] = dedup_notes
    analysis_result['normalization_severity_score'] = _compute_normalization_severity_score(dedup_notes)

    # Log normalization deltas for traceability/audit of LLM output stability.
    if original_cp != normalized:
        logger.info(
            'LLM correction_plan normalized',
            extra={
                'normalization_notes': dedup_notes[:20],
                'normalization_severity_score': analysis_result.get('normalization_severity_score', 0),
                'original_correction_plan': original_cp,
                'normalized_correction_plan': normalized,
            },
        )
    return analysis_result


def _ollama_urlopen_wall_clock(req, wall_timeout):
    """
    Enforces a true wall-clock deadline on an Ollama HTTP request.

    With stream=False, Ollama buffers the entire response before sending any
    bytes — the urllib socket timeout fires on any read idle gap, which kills
    slow-but-active generation. Solution: use wall_timeout as the socket
    timeout too (one coherent deadline) and rely on the ThreadPoolExecutor
    future's .result(timeout=N) as the outer hard cap. shutdown(wait=False)
    means we never block waiting for a still-running thread after the deadline.
    """
    import concurrent.futures as _cf
    def _do():
        with urllib_request.urlopen(req, timeout=wall_timeout) as _resp:
            return _resp.read().decode('utf-8')
    _executor = _cf.ThreadPoolExecutor(max_workers=1)
    _fut = _executor.submit(_do)
    _executor.shutdown(wait=False)
    try:
        return _fut.result(timeout=wall_timeout)
    except _cf.TimeoutError:
        raise TimeoutError(f'Ollama wall-clock timeout after {wall_timeout}s')


def _get_ollama_candidate_bases():
    configured_base = str(os.environ.get('OLLAMA_BASE_URL', '') or os.environ.get('OLLAMA_URL', '')).rstrip('/')
    fallback_base = str(os.environ.get('OLLAMA_FALLBACK_URL', '')).rstrip('/')
    running_in_docker = os.path.exists('/.dockerenv')
    default_base = 'http://ollama:11434' if running_in_docker else 'http://127.0.0.1:11434'

    candidate_bases = []
    for base in [configured_base, fallback_base, default_base]:
        normalized_base = str(base).rstrip('/')
        if normalized_base and normalized_base not in candidate_bases:
            candidate_bases.append(normalized_base)
    return candidate_bases


def _check_ollama_health(timeout_seconds=8):
    endpoint_errors = []
    for ollama_base in _get_ollama_candidate_bases():
        ollama_endpoint = f'{ollama_base}/api/tags'
        req = urllib_request.Request(ollama_endpoint, method='GET')
        try:
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                body = response.read().decode('utf-8')
            payload = json.loads(body)
            models = payload.get('models') if isinstance(payload, dict) else []
            model_names = []
            if isinstance(models, list):
                model_names = [item.get('name') for item in models if isinstance(item, dict) and item.get('name')]
            return {
                'connected': True,
                'base_url': ollama_base,
                'endpoint': ollama_endpoint,
                'models_count': len(model_names),
                'models': model_names[:20],
                'errors': [],
            }
        except urllib_error.HTTPError as error:
            error_body = ''
            try:
                error_body = error.read().decode('utf-8')
            except Exception:
                error_body = ''
            endpoint_errors.append(f'{ollama_endpoint} -> HTTP {error.code}: {error_body or str(error)}')
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            endpoint_errors.append(f'{ollama_endpoint} -> {error}')

    return {
        'connected': False,
        'base_url': None,
        'endpoint': None,
        'models_count': 0,
        'models': [],
        'errors': endpoint_errors,
    }


def _build_deterministic_analysis_fallback(dataframe, technical_profile, reason_message):
    rows_count = int(len(dataframe.index))
    issues = []
    recommendations = []
    suspect_values = []
    cleaned_dataset_preview = _dataframe_to_rows(dataframe.head(5))

    missing_pct = float(technical_profile.get('missing_pct') or 0.0)
    duplicate_rows = int(technical_profile.get('duplicate_rows') or 0)

    if missing_pct > 0:
        issues.append({
            'severity': 'warning',
            'category': 'missing_values',
            'column': '*',
            'rows': max(1, int(round(rows_count * (missing_pct / 100.0)))) if rows_count else 0,
            'explanation': f'Taux de valeurs manquantes detecte: {round(missing_pct, 2)}%.',
        })
        recommendations.append('Completer les valeurs manquantes par strategie deterministe (median/mode).')

    if duplicate_rows > 0:
        issues.append({
            'severity': 'warning',
            'category': 'duplicates',
            'column': '*',
            'rows': duplicate_rows,
            'explanation': f'{duplicate_rows} ligne(s) dupliquee(s) detectee(s).',
        })
        recommendations.append('Verifier et dedoublonner les lignes identiques avant integration.')

    outlier_total = 0
    for numeric_meta in technical_profile.get('numeric_columns_profile', []):
        outlier_total += int(numeric_meta.get('outlier_count') or 0)
    if outlier_total > 0:
        issues.append({
            'severity': 'info',
            'category': 'outliers',
            'column': '*',
            'rows': outlier_total,
            'explanation': f'{outlier_total} valeur(s) numerique(s) potentiellement aberrante(s) detectee(s) (regle IQR).',
        })
        recommendations.append('Examiner les valeurs numeriques extremes avant validation clinique.')

    fill_missing = {}
    trim_columns = []
    parse_dates = []

    for column_meta in technical_profile.get('columns_profile', []):
        column_name = str(column_meta.get('column') or '')
        if not column_name:
            continue
        missing_count = int(column_meta.get('missing_count') or 0)
        dtype_name = str(column_meta.get('dtype') or '').lower()
        if missing_count > 0:
            if 'int' in dtype_name or 'float' in dtype_name:
                fill_missing[column_name] = {'strategy': 'median'}
            else:
                fill_missing[column_name] = {'strategy': 'mode'}
        if dtype_name in {'object', 'string'}:
            trim_columns.append(column_name)
        lowered = column_name.lower()
        if 'date' in lowered or 'naissance' in lowered or 'visite' in lowered:
            parse_dates.append(column_name)

    correction_plan = {
        'fill_missing': fill_missing,
        'parse_dates': parse_dates[:15],
        'type_casts': {},
        'trim_whitespace_columns': trim_columns[:20],
    }

    if not recommendations:
        recommendations.append('Dataset globalement stable selon les controles deterministes locaux.')

    quality_score = max(5, min(100, int(round(100 - (missing_pct * 0.5) - (duplicate_rows * 2) - min(outlier_total, 20)))))

    return {
        'dataset_summary': {
            'rows': int(len(dataframe.index)),
            'columns': int(len(dataframe.columns)),
            'column_names': [str(column) for column in dataframe.columns],
            'missing_cells': int(technical_profile.get('missing_cells') or 0),
            'missing_pct': float(missing_pct),
            'duplicate_rows': int(technical_profile.get('duplicate_rows') or 0),
        },
        'medical_analysis': {
            'summary': 'Analyse locale deterministe sans LLM.',
            'flags': [],
            'notes': [reason_message],
        },
        'missing_values_analysis': {
            'missing_pct': float(missing_pct),
            'strategy': 'deterministic_local',
            'columns': [
                {
                    'column': str(column_meta.get('column') or ''),
                    'missing_count': int(column_meta.get('missing_count') or 0),
                    'missing_pct': float(column_meta.get('missing_pct') or 0.0),
                }
                for column_meta in technical_profile.get('columns_profile', [])[:20]
            ],
        },
        'outliers_analysis': {
            'count': int(outlier_total),
            'method': 'iqr_local',
        },
        'duplicate_analysis': {
            'duplicate_rows': int(duplicate_rows),
            'method': 'exact_duplicate_rows',
        },
        'corrections_applied': [],
        'suspect_values': suspect_values,
        'remaining_risks': list(dict.fromkeys([item['explanation'] for item in issues]))[:5],
        'recommendations': recommendations[:5],
        'cleaned_dataset_preview': cleaned_dataset_preview,
        'processing_statistics': {
            'mode': 'deterministic_fallback',
            'rows_processed': rows_count,
            'columns_processed': int(len(dataframe.columns)),
            'analysis_source': 'pandas',
            'chunks_count': technical_profile.get('chunk_count', 0),
        },
        'quality_score': {
            'value': quality_score,
            'scale': '0-100',
        },
        'quality_score_value': quality_score,
        'summary': 'Analyse realisee via fallback deterministe local (Pandas) suite a indisponibilite LLM.',
        'issues': issues[:6],
        'recommendations': recommendations[:5],
        'correction_plan': correction_plan,
        'corrected_preview_rows': [],
        'column_assessment': [],
        'limitations': [
            'LLM indisponible: fallback deterministe applique.',
            reason_message,
        ],
        'analysis_pack': {
            'pack_type': 'structured_analysis_pack',
            'technical_profile': technical_profile,
            'preview_rows': _dataframe_to_rows(dataframe.head(3)),
            'column_samples': {},
            'meta': {
                'selected_columns_count': int(len(dataframe.columns)),
                'total_columns_count': int(len(dataframe.columns)),
                'preview_rows_count': min(3, int(len(dataframe.index))),
                'column_samples_per_column': 0,
            },
        },
        'model_used': 'deterministic_fallback',
        'attempt': 'fallback_local',
        'stage': 'pass1_diagnostic',
        'second_pass': {'status': 'skipped_fallback'},
        'route': {'mode': 'deterministic', 'label': 'deterministic_only', 'reason': reason_message},
        'pipeline': {
            'stage': 'deterministic_only',
            'chunks_count': technical_profile.get('chunk_count', 0),
            'retrieval': 'skipped',
        },
    }


def _build_preprocess_instruction_block():
    return (
        'Tu es un systeme expert de pretraitement intelligent de donnees medicales specialise en nephrologie, dialyse et analyse clinique. '
        'Tu dois raisonner comme un expert Big Data, un Data Engineer, un Data Scientist medical, un specialiste qualite des donnees et un nephrologue clinique senior. '
        'Analyse l ensemble du dataset, detecte les erreurs, identifie les incoherences medicales, corrige uniquement les anomalies fiables, standardise les donnees et produis une version finale propre. '
        'Tu ne dois jamais halluciner des donnees, inventer des valeurs medicales, modifier silencieusement des donnees critiques ni supprimer automatiquement des donnees importantes. '
        'Si une valeur est ambigue, marque-la comme suspecte, explique pourquoi et reduis le niveau de confiance. '
        'Toutes les sorties doivent etre compactes, deterministes et strictement en JSON valide, sans markdown, sans commentaires et sans texte externe.'
    )


def _is_correction_plan_empty(correction_plan):
    if not isinstance(correction_plan, dict):
        return True
    for value in correction_plan.values():
        if isinstance(value, dict) and value:
            return False
        if isinstance(value, list) and len(value) > 0:
            return False
        if value not in [None, '', [], {}]:
            return False
    return True


_EXCEL_DATE_ARTIFACTS = {
    '0/1/1900', '1/0/1900', '00/01/1900', '01/00/1900',
    '0/0/1900', '1/1/1900', '01/01/1900', '00/00/1900',
    '0-1-1900', '1-0-1900', '00-01-1900', '01-00-1900',
    '1900-01-00', '1900-00-01', '1900-01-01',
    '1899-12-30', '1899-12-31', '1899-12-29',
    '1900-01-00 00:00:00', '1899-12-30 00:00:00',
}


def _build_deterministic_correction_plan(technical_profile):
    technical_profile = technical_profile if isinstance(technical_profile, dict) else {}
    fill_missing = {}
    trim_columns = []
    parse_dates = []
    type_casts = {}
    value_mappings = {}
    drop_columns = []

    import re as _re
    # Captures years clearly wrong in 2026 context:
    # 2100-2999 (2[1-9]\d{2}) and 3000-9999 ([3-9]\d{3})
    _year_re = _re.compile(r'\b((?:2[1-9]\d{2}|[3-9]\d{3}))\b')

    for column_meta in technical_profile.get('columns_profile', []):
        column_name = str(column_meta.get('name') or column_meta.get('column') or '')
        if not column_name:
            continue
        dtype_name = str(column_meta.get('dtype') or '').lower()
        missing_count = int(column_meta.get('missing_count') or 0)
        lowered = column_name.lower()
        sample_values = column_meta.get('sample_values') or column_meta.get('unique_values') or []

        # Empty or constant columns → propose drop (no analytical value)
        _ac_types = {ac.get('type') for ac in (column_meta.get('anomaly_candidates') or [])}
        if 'colonne_vide' in _ac_types or 'colonne_constante' in _ac_types:
            drop_columns.append(column_name)
            continue

        if missing_count > 0:
            if 'int' in dtype_name or 'float' in dtype_name:
                fill_missing[column_name] = {'strategy': 'median'}
            else:
                fill_missing[column_name] = {'strategy': 'mode'}

        if dtype_name in {'object', 'string'}:
            trim_columns.append(column_name)

        if 'date' in lowered or 'naissance' in lowered or 'visite' in lowered:
            parse_dates.append(column_name)

        if 'int' in dtype_name:
            type_casts[column_name] = 'integer'
        elif 'float' in dtype_name:
            type_casts[column_name] = 'numeric'

        # ── Value-level corrections driven by anomaly_candidates + sample scan ──
        col_mappings = {}
        _vals_to_scan = list(sample_values if isinstance(sample_values, list) else [])

        # Collect per-value anomaly candidates (artefact_excel, annee_incorrecte,
        # manquant_deguise). Aggregate-type candidates (separateur_decimal, etc.)
        # are handled below after the loop.
        _has_decimal_comma = False
        _has_numeric_text = False
        _has_bool_incoherent = False
        for _ac in (column_meta.get('anomaly_candidates') or []):
            _ac_type = str(_ac.get('type', ''))
            _acv = str(_ac.get('value', '')).strip()
            if _ac_type == 'separateur_decimal':
                _has_decimal_comma = True
            elif _ac_type == 'valeur_numerique_texte':
                _has_numeric_text = True
            elif _ac_type == 'booleen_incoherent':
                _has_bool_incoherent = True
            elif _acv and _acv not in _vals_to_scan:
                _vals_to_scan.append(_acv)

        for val in _vals_to_scan:
            val_str = str(val).strip()
            # Excel date artifacts → null
            if val_str in _EXCEL_DATE_ARTIFACTS:
                col_mappings[val_str] = None
            # Disguised missing → null
            elif val_str.lower() in _ANOMALY_DISGUISED_MISSING and val_str:
                col_mappings[val_str] = None
            # Year typos: 3023→2023, 4056→2056, 2124→2024, 2213→2013
            m = _year_re.search(val_str)
            if m:
                wrong_year = m.group(1)
                if int(wrong_year) > 2026:
                    corrected = val_str.replace(wrong_year, '20' + wrong_year[-2:])
                    if corrected != val_str:
                        col_mappings[val_str] = corrected

        # Decimal comma separator: build mapping "1,5" → "1.5" from the full column
        # (only viable for non-numeric dtype columns)
        if _has_decimal_comma and dtype_name in ('object', 'string', ''):
            import re as _re2
            _dc_re = _re2.compile(r'^(-?\d[\d\s]*),(\d+)$')
            for _raw_val in (column_meta.get('sample_values') or []):
                _m = _dc_re.match(str(_raw_val).strip())
                if _m:
                    _fixed = _m.group(1).replace(' ', '') + '.' + _m.group(2)
                    col_mappings[str(_raw_val).strip()] = _fixed

        # Numeric-as-text: schedule type cast to numeric
        if _has_numeric_text and dtype_name in ('object', 'string', ''):
            type_casts[column_name] = 'numeric'
            trim_columns.append(column_name)

        # Boolean incoherent: normalize oui/non + 0/1 mix → 0/1 integer
        if _has_bool_incoherent:
            col_mappings.update({
                'oui': 1, 'non': 0,
                'yes': 1, 'no': 0,
                'true': 1, 'false': 0,
                'o': 1, 'n': 0,
                'OUI': 1, 'NON': 0,
                'YES': 1, 'NO': 0,
                'TRUE': 1, 'FALSE': 0,
                '1': 1, '0': 0,
            })
            type_casts[column_name] = 'integer'

        if col_mappings:
            value_mappings[column_name] = col_mappings

    return {
        'rename_columns': {},
        'drop_columns': drop_columns,
        'value_mappings': value_mappings,
        'fill_missing': fill_missing,
        'type_casts': type_casts,
        'parse_dates': parse_dates[:15],
        'trim_whitespace_columns': trim_columns[:20],
        'default_values': {},
    }


def _merge_correction_plans(primary_plan, supplemental_plan):
    primary_plan = primary_plan if isinstance(primary_plan, dict) else {}
    supplemental_plan = supplemental_plan if isinstance(supplemental_plan, dict) else {}

    merged = {
        'rename_columns': dict(primary_plan.get('rename_columns') or {}),
        'drop_columns': list(primary_plan.get('drop_columns') or []),
        'value_mappings': dict(primary_plan.get('value_mappings') or {}),
        'fill_missing': dict(primary_plan.get('fill_missing') or {}),
        'type_casts': dict(primary_plan.get('type_casts') or {}),
        'parse_dates': list(primary_plan.get('parse_dates') or []),
        'trim_whitespace_columns': list(primary_plan.get('trim_whitespace_columns') or []),
        'default_values': dict(primary_plan.get('default_values') or {}),
    }

    def _merge_dict_bucket(key):
        extra = supplemental_plan.get(key) or {}
        if isinstance(extra, dict):
            for item_key, item_value in extra.items():
                merged[key].setdefault(item_key, item_value)

    def _merge_list_bucket(key):
        extra = supplemental_plan.get(key) or []
        if isinstance(extra, list):
            for item in extra:
                if item not in merged[key]:
                    merged[key].append(item)

    _merge_dict_bucket('rename_columns')
    _merge_dict_bucket('value_mappings')
    _merge_dict_bucket('fill_missing')
    _merge_dict_bucket('type_casts')
    _merge_dict_bucket('default_values')
    _merge_list_bucket('parse_dates')
    _merge_list_bucket('trim_whitespace_columns')

    # Never let a supplemental plan reintroduce automatic deletions in medical preprocessing.
    merged['drop_columns'] = []
    return merged


def _call_ollama_qwen_analysis(dataframe, technical_profile, progress_callback=None,
                               precomputed_chunks=None, precomputed_retrieval_context=None):
    def _safe_num_predict(value, default_value, minimum_value):
        try:
            parsed_value = int(value)
        except Exception:
            parsed_value = int(default_value)
        return max(int(minimum_value), parsed_value)

    route = _determine_preprocess_route(technical_profile)
    if route.get('mode') == 'deterministic':
        route = {
            'mode': 'balanced',
            'label': 'llm_only',
            'reason': 'LLM-only mode: no deterministic pandas fallback.',
            'primary_model': os.environ.get('OLLAMA_PREPROCESS_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct')),
            'fallback_model': os.environ.get('OLLAMA_FALLBACK_MODEL', 'qwen2.5:3b-instruct'),
            'primary_timeout_seconds': _env_int('OLLAMA_PRIMARY_TIMEOUT_SECONDS', min(_env_int('OLLAMA_TIMEOUT_SECONDS', 420), 180)),
            'fallback_timeout_seconds': _env_int('OLLAMA_FALLBACK_TIMEOUT_SECONDS', _env_int('OLLAMA_TIMEOUT_SECONDS', 420)),
            'primary_num_predict': _env_int('OLLAMA_NUM_PREDICT', 32),
            'fallback_num_predict': _env_int('OLLAMA_RETRY_NUM_PREDICT', 24),
            'clinical_complexity_score': 0,
        }

    rag_max_chunks = int(os.environ.get('RAG_MAX_CHUNKS', '3'))

    # Use pre-computed chunks/retrieval from tasks.py if provided (avoids double embedding)
    if precomputed_chunks is not None and precomputed_retrieval_context is not None:
        chunks = precomputed_chunks
        retrieval_context = precomputed_retrieval_context
    else:
        chunks = _build_preprocess_chunks(dataframe, technical_profile)
        retrieval_context = _build_retrieval_context(
            dataframe, chunks, technical_profile,
            stage_name='diagnostic',
            max_chunks=rag_max_chunks,
            progress_callback=progress_callback,
        )

    technical_profile['chunk_count'] = len(chunks)
    technical_profile['chunks'] = retrieval_context.get('chunk_summaries', [])
    technical_profile['retrieved_chunks'] = retrieval_context.get('retrieved_chunks', [])

    # Pass-2 dedicated retrieval: re-query with stage='correction' to surface the most
    # correction-relevant chunks (different query vector than diagnostic stage)
    retrieval_context_pass2 = _build_retrieval_context(
        dataframe, chunks, technical_profile,
        stage_name='correction',
        max_chunks=rag_max_chunks,
        progress_callback=None,
    )

    model_name = route.get('primary_model') or os.environ.get('OLLAMA_PREPROCESS_MODEL', os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct'))
    timeout_seconds = int(os.environ.get('OLLAMA_TIMEOUT_SECONDS', '420'))
    primary_timeout_seconds = int(route.get('primary_timeout_seconds') or int(os.environ.get('OLLAMA_PRIMARY_TIMEOUT_SECONDS', str(min(timeout_seconds, 180)))))
    fallback_model = route.get('fallback_model') or os.environ.get('OLLAMA_FALLBACK_MODEL', 'qwen2.5:3b-instruct')
    fallback_timeout_seconds = int(route.get('fallback_timeout_seconds') or int(os.environ.get('OLLAMA_FALLBACK_TIMEOUT_SECONDS', str(timeout_seconds))))
    retry_max_columns = int(os.environ.get('OLLAMA_RETRY_MAX_COLUMNS', '12'))
    retry_preview_rows = int(os.environ.get('OLLAMA_RETRY_PREVIEW_ROWS', '1'))
    min_pass1_predict = _env_int('OLLAMA_MIN_PASS1_NUM_PREDICT', 512)
    min_retry_predict = _env_int('OLLAMA_MIN_RETRY_NUM_PREDICT', 384)
    min_pass2_predict = _env_int('OLLAMA_MIN_PASS2_NUM_PREDICT', 1500)

    primary_num_predict = _safe_num_predict(
        route.get('primary_num_predict') or os.environ.get('OLLAMA_NUM_PREDICT', '32'),
        512,
        min_pass1_predict,
    )
    retry_num_predict = _safe_num_predict(
        route.get('fallback_num_predict') or os.environ.get('OLLAMA_RETRY_NUM_PREDICT', '24'),
        384,
        min_retry_predict,
    )


    route['primary_num_predict'] = primary_num_predict
    route['fallback_num_predict'] = retry_num_predict
    candidate_bases = _get_ollama_candidate_bases()

    prompt_payload = _build_llm_payload(dataframe, technical_profile)
    prompt_payload['rag'] = {
        'chunk_count': len(chunks),
        'retrieved_chunks': retrieval_context.get('retrieved_chunks', []),
        'retrieved_chunks_count': retrieval_context.get('retrieved_chunks_count', 0),
        'section_fusion': retrieval_context.get('section_fusion', []),
        'vector_store': retrieval_context.get('vector_store', {}),
    }
    # Enforce a strict context budget to avoid Ollama truncation/hallucinations.
    try:
        max_context_tokens = int(os.environ.get('MAX_CONTEXT_TOKENS', '4096'))
    except Exception:
        max_context_tokens = 4096
    try:
        system_prompt_tokens = int(os.environ.get('SYSTEM_PROMPT_TOKENS', '600'))
    except Exception:
        system_prompt_tokens = 600
    try:
        reserved_output_tokens = int(os.environ.get('CONTEXT_OUTPUT_TOKENS', '800'))
    except Exception:
        reserved_output_tokens = 800
    try:
        retry_margin_tokens = int(os.environ.get('CONTEXT_RETRY_MARGIN', '300'))
    except Exception:
        retry_margin_tokens = 300

    available_input_tokens = max(128, max_context_tokens - system_prompt_tokens - reserved_output_tokens - retry_margin_tokens)

    # Estimate tokens and shrink payload/retrieval_context if needed
    before_payload_toks, before_rag_toks = _estimate_prompt_and_rag_tokens(prompt_payload, retrieval_context)
    before_total = before_payload_toks + before_rag_toks
    if before_total > available_input_tokens:
        new_payload, new_rag = _shrink_prompt_for_budget(prompt_payload, retrieval_context, available_input_tokens)
        prompt_payload = new_payload
        prompt_payload['rag'] = new_rag
        # record budget decisions
        technical_profile.setdefault('context_budget', {})
        technical_profile['context_budget'].update({
            'max_context_tokens': max_context_tokens,
            'system_prompt_tokens': system_prompt_tokens,
            'reserved_output_tokens': reserved_output_tokens,
            'retry_margin_tokens': retry_margin_tokens,
            'available_input_tokens': available_input_tokens,
            'before_total_input_tokens': before_total,
            'after_total_input_tokens': _estimate_prompt_and_rag_tokens(prompt_payload, prompt_payload.get('rag'))[0] + _estimate_prompt_and_rag_tokens(prompt_payload, prompt_payload.get('rag'))[1],
            'shrunk': True,
        })
    else:
        technical_profile.setdefault('context_budget', {})
        technical_profile['context_budget'].update({
            'max_context_tokens': max_context_tokens,
            'system_prompt_tokens': system_prompt_tokens,
            'reserved_output_tokens': reserved_output_tokens,
            'retry_margin_tokens': retry_margin_tokens,
            'available_input_tokens': available_input_tokens,
            'before_total_input_tokens': before_total,
            'after_total_input_tokens': before_total,
            'shrunk': False,
        })
    def _notify_progress(message):
        if callable(progress_callback):
            try:
                progress_callback(message)
            except Exception:
                pass

    def _build_single_pass_prompt(payload_for_prompt, strict=False, explicit_anomaly_hint=''):
        # Extract column names to build medical RAG reference context
        _col_names = []
        _tp = payload_for_prompt.get('technical_profile') if isinstance(payload_for_prompt, dict) else None
        if isinstance(_tp, dict):
            for _c in (_tp.get('columns_with_issues') or _tp.get('columns_profile') or []):
                _name = _c.get('col') or _c.get('name') or _c.get('column') or ''
                if _name:
                    _col_names.append(str(_name))
        if not _col_names and isinstance(payload_for_prompt, dict):
            for _c in (payload_for_prompt.get('columns_with_issues') or []):
                _name = _c.get('col') or _c.get('name') or _c.get('column') or ''
                if _name:
                    _col_names.append(str(_name))
        _medical_ref = build_medical_rag_context(_col_names)

        # Build LOINC reference block — official codes + ranges for matched columns
        _loinc_ref = ''
        try:
            from .loinc_mapper import build_loinc_context_for_prompt as _build_loinc_ctx
            _loinc_ref = _build_loinc_ctx(_col_names, max_entries=10)
        except Exception:
            _loinc_ref = ''

        # Format RAG chunks: include column_semantics (value distributions, disguised missing,
        # outlier values) so the LLM can detect semantic issues, not just statistical ones.
        _rag_block = ''
        _rag_corr = payload_for_prompt.get('rag_correction') if isinstance(payload_for_prompt, dict) else None
        if isinstance(_rag_corr, dict):
            _rc_chunks = _rag_corr.get('retrieved_chunks') or []
            if _rc_chunks:
                _rag_parts = []
                for _chunk in _rc_chunks[:3]:
                    if not isinstance(_chunk, dict):
                        continue
                    _chunk_lines = []
                    _summary = _chunk.get('deterministic_summary') or ''
                    if _summary:
                        _chunk_lines.append(_summary[:200])
                    # Include per-column semantic signals from the enriched chunk
                    _col_sem = _chunk.get('column_semantics') or {}
                    for _cname, _cinfo in list(_col_sem.items())[:6]:
                        if not isinstance(_cinfo, dict):
                            continue
                        _signals = []
                        if _cinfo.get('disguised_missing'):
                            _tokens = list(_cinfo['disguised_missing'].keys())[:3]
                            _signals.append(f'manquants_deguises={_tokens}')
                        if _cinfo.get('value_distribution'):
                            _vals = list(_cinfo['value_distribution'].keys())[:5]
                            _signals.append(f'valeurs={_vals}')
                        if _cinfo.get('outlier_values'):
                            _signals.append(f'outliers={_cinfo["outlier_values"][:3]}')
                        if _cinfo.get('numeric_stats'):
                            _ns = _cinfo['numeric_stats']
                            _signals.append(f'min={_ns.get("min")},max={_ns.get("max")},med={_ns.get("median")}')
                        if _signals:
                            _chunk_lines.append(f'  {_cname}: {" | ".join(_signals)}')
                    if _chunk_lines:
                        _rag_parts.append('\n'.join(_chunk_lines))
                if _rag_parts:
                    _rag_block = (
                        'Contexte RAG - donnees reelles du dataset (utilise ces informations pour detecter '
                        'les problemes semantiques en plus des problemes statistiques):\n'
                        + '\n---\n'.join(_rag_parts) + '\n'
                    )

        # Inject real column data into prompt when available
        _csv_instruction = ''
        if _data_columns:
            _n_vals = len(next(iter(_data_columns.values()), []))
            _col_list = ', '.join(list(_data_columns.keys())[:10])
            _csv_instruction = (
                f'ROLE: Tu es le SEUL detecteur d anomalies. Pandas t a seulement envoye les donnees brutes sans pre-analyse. '
                f'DONNEES REELLES: {_n_vals} patients, colonnes de ce batch: {_col_list}... '
                f'Le champ "data_columns" contient la liste complete des valeurs reelles de chaque colonne. '
                f'Chaque liste est indexee: index 0 = patient_id[0], index 1 = patient_id[1], etc. '
                f'TON TRAVAIL — detecte dans chaque colonne: '
                f'(a) Cellules vides ou null (valeur = "" ou manquante). '
                f'(b) Valeurs de mauvais format ("X", "N/A", "1;(1/2024)", texte dans colonne numerique). '
                f'(c) Valeurs aberrantes medicalement (creatinine < 50 mg/L pour dialyse, calcium < 15 dans colonne mg/L, bicarbonates > 40 ou < 8, albumine < 15, sodium < 110, seances = 0 avec patient dialyse). '
                f'(d) Valeurs illogiques (biopsie_renale = 2, seances_par_semaine = 0 ou "X"). '
                f'(e) Unites melangees (calcium: la plupart ~70-100 mais certaines valeurs ~5-9 = mauvaise unite). '
                f'(f) Incoherences entre colonnes si plusieurs colonnes liees sont dans ce batch. '
                f'Pour chaque anomalie: cite la valeur exacte + son index dans la liste. '
                f'NE SIGNALE PAS les colonnes binaires (is_binary=true) comme aberrantes. '
            )

        prompt = (
            _build_preprocess_instruction_block() + ' '
            + (_csv_instruction if _csv_instruction else '')
            + 'Retourne UNIQUEMENT un JSON valide et court. '
            'Detecte TOUS les types de problemes suivants — chaque categorie doit produire '
            'une entree issues ET une correction dans correction_plan: '

            '(1) VALEURS MANQUANTES ET MASQUEES: '
            'valeur_manquante: NaN/null reels → fill_missing avec strategy=median (numerique) ou mode (categoriel). '
            'manquant_deguise: "N/A","?","-","inconnu","nd","ND","neant","void","." stockes comme texte → value_mappings vers null. '
            'valeur_sentinelle: -1,-99,-999,999,9999 utilises pour coder le manquant → value_mappings vers null. '

            '(2) PROBLEMES DE FORMAT ET D ENCODAGE: '
            'separateur_decimal: "1,5" au lieu de "1.5" (virgule fr) → value_mappings {"1,5":"1.5"}. '
            'valeur_numerique_texte: colonne dtype=object dont toutes les valeurs sont des nombres → type_casts vers numeric. '
            'encodage_incoherent: meme signification, formats differents ("M"/"Masculin"/"MALE", "oui"/"1"/"true") → value_mappings pour normaliser. '
            'booleen_incoherent: mix de texte bool et 0/1 dans la meme colonne → value_mappings {"oui":1,"non":0,"true":1,"false":0,"o":1,"n":0}. '
            'casse_incoherente: meme valeur en casses differentes ("male","Male","MALE") → value_mappings pour tout normaliser. '
            'espace_parasite: espaces en debut/fin → trim_whitespace_columns. '
            'caractere_special: &amp; <br/> caracteres HTML/speciaux dans les valeurs → value_mappings pour nettoyer. '
            'mojibake: encodage corrompu, caracteres Ã©/Ã¨/â€™ au lieu de é/è/\' → signaler severity=critical, impossible a corriger automatiquement (relire le fichier avec le bon encodage). '

            '(3) PROBLEMES DE DATES: '
            'artefact_excel: "0/1/1900","01/01/1900" dans colonne numerique → value_mappings vers null. '
            'annee_incorrecte: "12/12/3023"→"12/12/2023", "15/01/2124"→"15/01/2024" → value_mappings. '
            'format_date_mixte: "01/01/2023" et "2023-01-01" dans la meme colonne → parse_dates. '
            'date_future: date avec annee > 2030 dans un dataset medical actuel → signaler en issues severity=warning. '
            'colonne_date: colonne date stockee en string → parse_dates. '

            '(4) PROBLEMES DE VALEURS ABERRANTES ET LOGIQUES: '
            'valeur_aberrante: outlier statistique (IQR) → signaler en issues, ne pas corriger automatiquement sauf evidence. '
            'valeur_negative_impossible: age/poids/taille/imc/score < 0 → value_mappings vers null. '
            'contradiction_logique: incohérence médicale entre colonnes → issues severity=critical, exemples: '
            'debut_dialyse_urgence=1 ET debut_dialyse_planifie=1 (mutuellement exclusifs), '
            'deces=1 sans date_deces, deces=0 avec date_deces renseignee, '
            'seances_par_semaine=0 avec hemodialyse=1, dialyse_peritoneale=1 avec fistule_arterioveineuse=1. '
            'unite_melangee: ex calcium_basale: valeurs 40-120 en mg/L mais 2 valeurs 5.8 et 8.0 en mmol/L dans la meme colonne → '
            'issues severity=critical + value_mappings: multiplier les valeurs mmol/L par 4 pour convertir en mg/L. '
            'valeur_invalide_x: valeur "X" ou "x" dans une colonne binaire 0/1 ou numérique → '
            'signaler en issues severity=warning, value_mappings vers null (X signifie non évalué/inconnu). '

            '(5) STRUCTURE ET NOMMAGE: '
            'type_incorrect: mauvais dtype pour le champ (ex: age en float alors que entier attendu) → type_casts. '
            'colonne_redondante: nom_complet + prenom + nom dans le meme dataset → issues severity=info. '
            'type_mixte: valeur texte isolee dans colonne numerique → value_mappings vers null. '
            'colonne_vide: 100% des valeurs manquantes → drop_columns severity=warning. '
            'colonne_constante: une seule valeur unique dans toute la colonne → drop_columns severity=info (aucune information). '
            'colonne_quasi_constante: >98% meme valeur → issues severity=info (faible variance, potentiellement inutile). '
            'id_manquant: colonne identifiant patient avec valeurs nulles → issues severity=critical (patient non identifiable). '

            '(6) PROBLEMES INTER-COLONNES (champ cross_column_issues): '
            'incoherence_age_date: age dans la colonne age ne correspond pas à l annee calculee depuis date_naissance → '
            'signaler severity=warning sur les deux colonnes, la date de naissance est generalement plus fiable. '
            'doublons_patients: plusieurs lignes ont les memes valeurs sur les colonnes identite (nom, prenom, id) → '
            'signaler severity=warning, ne pas supprimer automatiquement, necessite verification manuelle. '
            'Si cross_column_issues est present dans le dataset, créer une issue pour chaque element avec la colonne principale concernee. '

            'CHAMP CRITIQUE anomaly_candidates: si une colonne contient ce champ, ces valeurs ont ete detectees '
            'en scannant TOUT le fichier — elles sont garanties problematiques meme si rares (1 occurrence sur 500). '
            'Tu DOIS toutes traiter dans correction_plan selon leur type: '
            'artefact_excel → value_mappings vers null, '
            'annee_incorrecte → corriger le siecle (ex 3023→2023) dans value_mappings, '
            'manquant_deguise → value_mappings vers null, '
            'separateur_decimal → value_mappings remplacer virgule par point, '
            'valeur_negative_impossible → value_mappings vers null, '
            'booleen_incoherent → normaliser oui/non/true/false → 1/0 dans value_mappings, '
            'format_date_mixte → ajouter la colonne dans parse_dates, '
            'valeur_numerique_texte → ajouter dans type_casts avec target_type numeric, '
            'espace_parasite → ajouter dans trim_whitespace_columns, '
            'colonne_constante ou colonne_quasi_constante → signaler en issue severity=info, '
            'valeur_aberrante ou unite_melangee → signaler en issue et corriger si possible (value_mappings vers null si valeur unique impossible), '
            'code_invalide → signaler en issue severity=warning et corriger dans value_mappings si la bonne valeur est deductible, sinon mettre null, '
            'mojibake ou caractere_special → signaler en issue severity=warning uniquement. '
            'CHAMPS min/max/outlier_count/sentinels: utilise ces statistiques pour detecter valeurs impossibles. '
            'Si min ou max est hors normes medicales, signaler comme valeur_aberrante. '
            'Si sentinels contient 999 ou -1, ces valeurs sont probablement des manquants deguises → null. '
            'CHAMP samples: exemples de valeurs reelles de la colonne. '
            'Utilise samples pour detecter formats incohérents (dates, casses, unites). '
            'CHAMP domain_metadata: contient valid_codes (codes valides et leur signification) et note. '
            'RESPECTER ABSOLUMENT les valid_codes — ne JAMAIS corriger ou remplacer une valeur qui est dans valid_codes. '
            'Si domain_metadata.note dit "ne pas corriger", ne toucher a cette valeur sous aucun pretexte. '
            'Exemple: deces=9 signifie "inconnu" selon domain_metadata — c est valide, ne pas remplacer par null. '
            'Exemple: couverture_medicale=0 signifie "auto_paiement" — c est valide, ne pas traiter comme manquant. '

            'REGLES IMPORTANTES: '
            'COLONNES BINAIRES (is_binary=true ou valeurs uniquement {0,1}): '
            'La valeur 0 signifie NON/ABSENT et 1 signifie OUI/PRESENT — ce sont des valeurs VALIDES, pas des manquants. '
            'Ne JAMAIS signaler valeur_manquante pour une colonne binaire : 0 n est pas un manquant. '
            'Ne JAMAIS signaler valeur_negative_impossible ni valeur_aberrante pour 0 ou 1. '
            'Ne pas signaler colonne_constante ni colonne_quasi_constante pour les colonnes binaires. '
            'Une colonne binaire avec uniquement des 0 signifie que tous les patients ont la valeur NON — c est une information clinique valide. '
            'Le but est un correction_plan non vide et exploitable. '
            'Ne reponds jamais par {} si des anomalies existent. '
            'Si tu hesites, choisis la correction prudente. '

            'Schema JSON attendu: '
            '{"summary":"resume global",'
            '"issues":[{'
            '"severity":"critical|warning|info",'
            '"category":"valeur_manquante|manquant_deguise|valeur_sentinelle|separateur_decimal|valeur_numerique_texte|encodage_incoherent|booleen_incoherent|casse_incoherente|espace_parasite|caractere_special|mojibake|artefact_excel|annee_incorrecte|format_date_mixte|date_future|colonne_date|valeur_aberrante|valeur_negative_impossible|contradiction_logique|unite_melangee|type_incorrect|colonne_redondante|type_mixte|incoherence_age_date|doublons_patients|colonne_vide|colonne_constante|colonne_quasi_constante|id_manquant|valeur_invalide_x",'
            '"column":"nom_colonne",'
            '"explanation":"description avec exemples de valeurs",'
            '"suggested_correction":{"valeur_originale":"valeur_corrigee"}'
            '}],'
            '"correction_plan":{'
            '"rename_columns":{},"drop_columns":[],"value_mappings":{},'
            '"fill_missing":{},"type_casts":{},"parse_dates":[],'
            '"trim_whitespace_columns":[],"default_values":{}},'
            '"correction_justifications":{"nom_colonne":"raison concise: probleme detecte (ex: format date mixte dd/mm/yyyy et yyyy-mm-dd, 18% valeurs manquantes, valeurs sentinelles 999/-1), correction appliquee et impact"}} '
        )
        if _loinc_ref:
            prompt += _loinc_ref + ' '
        if _rag_block:
            prompt += _rag_block
        if _medical_ref:
            prompt += _medical_ref + ' '
        prompt += 'Dataset: ' + json.dumps(payload_for_prompt, ensure_ascii=False, default=str)
        if explicit_anomaly_hint:
            prompt += ' ' + explicit_anomaly_hint
        if strict:
            prompt += (
                ' OBLIGATOIRE: ne renvoie pas de correction_plan vide. '
                'Remplis les champs applicables sans ajouter de texte hors JSON. '
            )
        return prompt

    def _run_stage(stage_name, primary_prompt, fallback_prompt, primary_pack, fallback_pack, primary_predict, fallback_predict):
        attempts = [
            {
                'label': 'primary',
                'model': model_name,
                'timeout_seconds': primary_timeout_seconds,
                'num_predict': primary_predict,
                'analysis_pack': primary_pack,
                'prompt': primary_prompt,
            }
        ]

        if fallback_model and fallback_model != model_name:
            attempts.append(
                {
                    'label': 'fallback',
                    'model': fallback_model,
                    'timeout_seconds': fallback_timeout_seconds,
                    'num_predict': fallback_predict,
                    'analysis_pack': fallback_pack,
                    'prompt': fallback_prompt,
                }
            )

        stage_errors = []
        for attempt in attempts:
            estimated_prompt_tokens = max(1, len(str(attempt.get('prompt') or '')) // 4)
            logger.info(
                '[OLLAMA CALL] stage=%s label=%s model=%s prompt_estimated_tokens=%s budget_max=%s available_input_tokens=%s num_predict=%s',
                stage_name,
                attempt['label'],
                attempt['model'],
                estimated_prompt_tokens,
                available_input_tokens,
                available_input_tokens,
                attempt['num_predict'],
            )
            num_ctx = _env_int('OLLAMA_NUM_CTX', 16384)
            request_payload = {
                'model': attempt['model'],
                'prompt': attempt['prompt'],
                'stream': False,
                'format': 'json',
                'options': {
                    'temperature': 0.1,
                    'num_predict': attempt['num_predict'],
                    'num_ctx': num_ctx,
                },
            }
            request_data = json.dumps(request_payload).encode('utf-8')

            for ollama_base in candidate_bases:
                ollama_endpoint = f'{ollama_base}/api/generate'
                req = urllib_request.Request(
                    ollama_endpoint,
                    data=request_data,
                    headers={'Content-Type': 'application/json'},
                    method='POST',
                )

                try:
                    body = _ollama_urlopen_wall_clock(req, wall_timeout=attempt['timeout_seconds'])
                    payload = json.loads(body)
                    raw_response = payload.get('response', '{}')
                    parsed_response = _parse_llm_analysis_response(raw_response)
                    # If the model returned invalid JSON, attempt targeted JSON-only retries.
                    json_retry_limit = int(os.environ.get('OLLAMA_JSON_RETRIES', '2'))
                    json_retry_prompt_suffix = (
                        ' REGENERATE ONLY valid JSON now. DO NOT include any explanation or markdown. '
                        'Return strictly the JSON object matching the required structure. '
                        'If you cannot produce valid JSON, return an empty JSON object {}.'
                    )
                    def _is_invalid_json_result(resp):
                        if not isinstance(resp, dict):
                            return True
                        # limitations may include localized strings indicating invalid JSON
                        lim = resp.get('limitations') or []
                        for item in lim:
                            if not isinstance(item, str):
                                continue
                            s = item.lower()
                            # common patterns mentioning JSON invalidity
                            if 'json' in s and ('invalide' in s or 'invalid' in s or 'non valide' in s):
                                return True
                            if 'le modele a repondu' in s and 'json' in s:
                                return True

                        # If parsing failed to populate expected keys, consider it invalid
                        # correction_plan presence counts as signal (pass2 only returns summary + correction_plan)
                        if (not resp.get('dataset_summary') and not resp.get('medical_analysis')
                                and not resp.get('summary') and not resp.get('correction_plan')):
                            return True
                        return False

                    if _is_invalid_json_result(parsed_response) and json_retry_limit > 0:
                        # use the smaller fallback prompt payload if available
                        regen_base_prompt = attempt.get('prompt')
                        regen_prompt = None
                        try:
                            prev_raw = str(raw_response or '')
                            regen_prompt = (_build_preprocess_instruction_block() + json_retry_prompt_suffix + ' Previous model output: ' + json.dumps({'prev_response': prev_raw}, ensure_ascii=False))
                        except Exception:
                            regen_prompt = (_build_preprocess_instruction_block() + json_retry_prompt_suffix)

                        for retry_idx in range(json_retry_limit):
                            retry_payload = {
                                'model': attempt['model'],
                                'prompt': regen_prompt,
                                'stream': False,
                                'format': 'json',
                                'options': {
                                    'temperature': 0.0,
                                    'num_predict': max(1, int(attempt.get('num_predict', 1) // 2)),
                                },
                            }
                            retry_data = json.dumps(retry_payload).encode('utf-8')
                            try:
                                # Recreate the Request per-retry to ensure the new body is sent
                                retry_req = urllib_request.Request(
                                    ollama_endpoint,
                                    data=retry_data,
                                    headers={'Content-Type': 'application/json'},
                                    method='POST',
                                )
                                retry_body = _ollama_urlopen_wall_clock(retry_req, wall_timeout=attempt['timeout_seconds'])
                                retry_payload_json = json.loads(retry_body)
                                retry_raw = retry_payload_json.get('response', '{}')
                                retry_parsed = _parse_llm_analysis_response(retry_raw)
                                if not _is_invalid_json_result(retry_parsed):
                                    parsed_response = retry_parsed
                                    raw_response = retry_raw
                                    break
                            except Exception:
                                continue
                    available_columns = []
                    try:
                        analysis_pack = attempt.get('analysis_pack') or {}
                        if isinstance(analysis_pack, dict) and isinstance(analysis_pack.get('technical_profile'), dict):
                            technical_profile = analysis_pack.get('technical_profile') or {}
                        elif isinstance(analysis_pack, dict) and isinstance(analysis_pack.get('analysis_pack'), dict):
                            technical_profile = (analysis_pack.get('analysis_pack') or {}).get('technical_profile') or {}
                        else:
                            technical_profile = {}
                        available_columns = [
                            str(column.get('name') or column.get('column') or '')
                            for column in (technical_profile.get('columns_profile') or [])
                            if isinstance(column, dict)
                        ]
                        available_columns = [column for column in available_columns if column]
                    except Exception:
                        available_columns = []

                    # Normalize the correction_plan structure (defensive):
                    parsed_response = _normalize_correction_plan(parsed_response, available_columns)

                    is_valid, validation_status, validation_issues = _validate_preprocess_llm_output(
                        parsed_response,
                        stage_name=stage_name,
                        available_columns=available_columns,
                    )
                    if not is_valid:
                        stage_errors.append(
                            f"[{stage_name}:{attempt['label']}:{attempt['model']}] validation serveur stricte rejetee: {', '.join(validation_issues[:6])}"
                        )
                        continue

                    # Guardrail: plan stages must return an actionable correction plan.
                    if stage_name.startswith('pass2') or stage_name.startswith('single_pass'):
                        diagnostic = attempt.get('analysis_pack', {}).get('diagnostic', {}) if isinstance(attempt.get('analysis_pack'), dict) else {}
                        has_diagnostic_signals = bool(diagnostic.get('issues')) or bool(diagnostic.get('summary'))
                        if has_diagnostic_signals and _is_correction_plan_empty(parsed_response.get('correction_plan')):
                            stage_errors.append(
                                f"[{stage_name}:{attempt['label']}:{attempt['model']}] correction_plan vide rejete (plan actionnable requis)."
                            )
                            continue

                    parsed_response['validation_status'] = validation_status
                    parsed_response['analysis_pack'] = attempt['analysis_pack']
                    parsed_response['model_used'] = attempt['model']
                    parsed_response['attempt'] = attempt['label']
                    parsed_response['stage'] = stage_name
                    return parsed_response
                except urllib_error.HTTPError as error:
                    error_body = ''
                    try:
                        error_body = error.read().decode('utf-8')
                    except Exception:
                        error_body = ''
                    stage_errors.append(
                        f"[{stage_name}:{attempt['label']}:{attempt['model']}] {ollama_endpoint} -> HTTP {error.code}: {error_body or str(error)}"
                    )
                except (urllib_error.URLError, RemoteDisconnected, ConnectionError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as error:
                    stage_errors.append(
                        f"[{stage_name}:{attempt['label']}:{attempt['model']}] {ollama_endpoint} -> {error}"
                    )

        error_summary = '; '.join(stage_errors) if stage_errors else 'Aucune reponse recue'
        lower_errors = error_summary.lower()
        limitations = []
        if 'timed out' in lower_errors or 'timeout' in lower_errors:
            limitations.append(
                f'Delai depasse: Ollama n a pas repondu dans la fenetre configured (primary={primary_timeout_seconds}s, fallback={fallback_timeout_seconds}s, plafond={timeout_seconds}s).'
            )
        if 'connection refused' in lower_errors or 'errno 111' in lower_errors:
            limitations.append(
                'Connexion refusee: l URL Ollama ciblee n est pas joignable depuis le backend. Verifier OLLAMA_URL et le reseau Docker.'
            )
        if '405' in lower_errors or 'method not allowed' in lower_errors:
            limitations.append('Methode invalide detectee: /api/generate doit etre appele en POST.')
        if not limitations:
            limitations.append('Aucun diagnostic automatique supplementaire disponible.')

        return {
            'unavailable': True,
            'summary': f'Analyse LLM indisponible ({stage_name}): {error_summary}',
            'issues': [],
            'recommendations': [],
            'correction_plan': {},
            'corrected_preview_rows': [],
            'column_assessment': [],
            'limitations': limitations,
            'analysis_pack': primary_pack,
            'model_used': model_name,
            'stage': stage_name,
            'validation_status': {
                'chunk_valid': False,
                'schema_valid': False,
                'merge_safe': False,
                'medical_confidence': None,
                'stage': stage_name,
                'issues': limitations,
            },
        }

    # Scale num_predict with dataset size: ~15 tokens per column for correction_plan JSON
    total_cols = int(technical_profile.get('columns') or len(technical_profile.get('columns_profile', [])))
    dynamic_min_predict = min_pass2_predict + max(0, (total_cols - 50) * 15)
    single_pass_predict = max(primary_num_predict, dynamic_min_predict)
    single_retry_predict = max(retry_num_predict, dynamic_min_predict)

    # ── Batch LLM analysis: process ALL priority columns split into batches ──
    batch_size = int(os.environ.get('LLM_BATCH_SIZE', '25'))
    rag_correction_context = {
        'retrieved_chunks': retrieval_context_pass2.get('retrieved_chunks', []),
        'retrieval_policy': retrieval_context_pass2.get('retrieval_policy', ''),
    }
    compact_retry_payload = _shrink_llm_payload(
        prompt_payload,
        max_columns=20,
        max_preview_rows=0,
        max_samples_per_column=0,
    )

    # Extract ALL priority columns without cap — same detection logic as _build_full_column_payload
    def _extract_all_priority_cols(tp):
        num_stats = {}
        for nc in (tp.get('numeric_columns_profile') or []):
            col_name = str(nc.get('name') or nc.get('column') or '')
            if col_name:
                num_stats[col_name] = {
                    'min': nc.get('min'), 'max': nc.get('max'),
                    'outlier_count': nc.get('outlier_count'),
                    'sentinel_counts': nc.get('sentinel_counts') or {},
                    'is_binary': bool(nc.get('is_binary')),
                }
        priority_cols = []   # all columns — minimal metadata only, LLM detects anomalies from real values
        clean_cols = []      # unused but kept for compatibility

        for col in (tp.get('columns_profile') or []):
            col_name = str(col.get('name') or col.get('column') or '')
            missing_pct_raw = col.get('missing_pct') or col.get('missing_ratio') or 0
            missing_ratio = col.get('missing_ratio')
            try:
                missing_val = float(missing_pct_raw)
                if missing_ratio is not None and missing_val <= 1.0:
                    missing_val *= 100
            except Exception:
                missing_val = 0
            dtype_str = str(col.get('dtype') or '').lower()
            stats = num_stats.get(col_name, {})

            entry = {
                'col': col_name,
                'type': str(col.get('dtype') or ''),
            }
            if missing_val > 0:
                entry['missing_pct'] = round(missing_val, 1)
            if stats.get('is_binary'):
                entry['is_binary'] = True

            # Domain metadata (valid codes, note) — tells LLM exactly what values are valid
            domain_meta = col.get('domain_metadata')
            if domain_meta:
                entry['domain_metadata'] = domain_meta

            # Send ALL anomaly candidates — pre-scanned from 100% of rows by Python
            # Field name matches prompt instruction: anomaly_candidates
            anomaly_candidates = col.get('anomaly_candidates') or []
            if anomaly_candidates:
                entry['anomaly_candidates'] = anomaly_candidates[:8]

            # Add numeric stats (min/max/outliers/sentinels) for aberrant value detection
            if not stats.get('is_binary'):
                if stats.get('min') is not None:
                    entry['min'] = stats['min']
                if stats.get('max') is not None:
                    entry['max'] = stats['max']
                if stats.get('outlier_count'):
                    entry['outlier_count'] = stats['outlier_count']
                if stats.get('sentinel_counts'):
                    entry['sentinels'] = stats['sentinel_counts']

            # Add sample unique values for non-numeric columns (helps LLM see actual format)
            if dtype_str in ('object', 'string', 'category') and col.get('sample_values'):
                entry['samples'] = col['sample_values'][:5]

            priority_cols.append(entry)

        return priority_cols

    all_priority_cols = _extract_all_priority_cols(technical_profile)
    col_batches = [all_priority_cols[i:i + batch_size] for i in range(0, len(all_priority_cols), batch_size)]
    if not col_batches:
        col_batches = [[]]

    # Build set of binary columns for post-LLM filtering
    _binary_col_names = {
        str(c.get('col') or c.get('name') or '')
        for c in all_priority_cols
        if c.get('is_binary')
    }
    # Binary columns with 0% actual missing (Python-confirmed) — LLM must not flag as missing
    _col_missing_pct = {
        str(col.get('column') or col.get('name') or ''): col.get('missing_pct', 0)
        for col in (technical_profile.get('columns_profile') or [])
    }
    _binary_no_missing = {
        col for col in _binary_col_names
        if _col_missing_pct.get(col, 1) == 0
    }
    # False positive categories that must never appear on binary columns
    _BINARY_FALSE_POSITIVE_CATS = {
        'valeur_negative_impossible', 'valeur_aberrante',
        'colonne_constante', 'colonne_quasi_constante',
    }

    # ── Warmup: ensure Ollama model is loaded before first batch ──
    _notify_progress('Chargement du modèle LLM...')
    for _wb in candidate_bases:
        try:
            _warmup_payload = json.dumps({
                'model': model_name,
                'prompt': 'OK',
                'stream': False,
                'options': {'num_predict': 1, 'num_ctx': 512},
            }).encode('utf-8')
            _req = urllib_request.Request(
                f'{_wb}/api/generate',
                data=_warmup_payload,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib_request.urlopen(_req, timeout=60) as _r:
                _r.read()
            logger.info('[WARMUP] Ollama model ready on %s', _wb)
            break
        except Exception as _e:
            logger.warning('[WARMUP] %s: %s', _wb, _e)

    # ── Run LLM on each batch and merge results ──
    merged_issues_all = []
    _seen_issue_keys = set()  # (column, category) pairs already in merged_issues_all
    merged_plan = {}
    merged_justifications = {}
    merged_summaries = []
    batch_limitations = []
    last_result = None
    strict_retry_performed = False
    any_batch_failed = False

    for batch_idx, batch_cols in enumerate(col_batches):
        batch_total = len(col_batches)
        n_priority = sum(1 for c in batch_cols if not c.get('clean'))
        n_clean = sum(1 for c in batch_cols if c.get('clean'))
        _notify_progress(
            f'Analyse LLM batch {batch_idx + 1}/{batch_total} '
            f'({n_priority} problématiques + {n_clean} propres)...'
        )

        _cross_col = technical_profile.get('cross_column_issues') or []

        # ── Build column-indexed value lists for this batch ─────────────────────
        # Send each column as an indexed list: {patient_id: [...], col_name: [...]}
        # This format is more efficient and easier for LLM to scan than CSV rows.
        # Only include columns that exist in the dataframe.
        _batch_col_names = [c['col'] for c in batch_cols if c.get('col')]
        _id_col = next(
            (str(c) for c in dataframe.columns
             if any(kw in str(c).lower() for kw in ('identifiant', 'patient_id', 'id_patient', 'num_patient'))),
            None
        )
        _data_csv = ''
        _data_columns = {}
        try:
            if _id_col and _id_col in dataframe.columns:
                _data_columns['patient_id'] = dataframe[_id_col].fillna('').tolist()
            for _cn in _batch_col_names:
                if _cn in dataframe.columns:
                    _col_vals = dataframe[_cn].fillna('').tolist()
                    # Compact serialization: round floats to 1 decimal, truncate long strings
                    _col_vals = [
                        round(v, 1) if isinstance(v, float) else
                        str(v)[:12] if not isinstance(v, (int, str, bool, type(None))) else
                        str(v)[:12] if isinstance(v, str) and len(str(v)) > 12 else v
                        for v in _col_vals
                    ]
                    # Send ALL rows — LLM is the primary anomaly detector
                    _data_columns[_cn] = _col_vals
        except Exception:
            _data_columns = {}

        # No sampling — send all rows. Compact CSV string to reduce tokens.
        if _data_columns:
            # Serialize as compact CSV strings per column (saves ~30% tokens vs JSON arrays)
            _compact = {k: ','.join(str(v) for v in vals) for k, vals in _data_columns.items()}
            _data_csv = json.dumps(_compact, ensure_ascii=False)
        # ── End column data build ────────────────────────────────────────────────

        batch_payload = {
            'technical_profile': {
                'rows': technical_profile.get('rows'),
                'columns': technical_profile.get('columns'),
                'missing_pct_global': technical_profile.get('missing_pct'),
                'duplicate_rows': technical_profile.get('duplicate_rows'),
                'columns_with_issues': batch_cols,
                'total_columns': len(technical_profile.get('columns_profile') or []),
                'columns_with_issues_count': n_priority,
                'clean_columns_count': n_clean,
                'batch_info': {
                    'batch': batch_idx + 1,
                    'total_batches': batch_total,
                    'note': 'Les colonnes avec clean=true semblent propres statistiquement mais peuvent contenir des valeurs illogiques — analyser les vraies valeurs dans data_csv.',
                },
                **(({'cross_column_issues': _cross_col}) if _cross_col else {}),
            },
            'rag_correction': rag_correction_context,
            **(({'data_columns': _data_columns}) if _data_columns else {}),
        }

        # Apply budget check to each batch prompt — avoid truncation
        _batch_prompt_raw = _build_single_pass_prompt(batch_payload, strict=True)
        _batch_tokens = max(1, len(_batch_prompt_raw) // 4)
        if _batch_tokens > available_input_tokens:
            # Trim rag_correction retrieved_chunks to reduce prompt size
            _trimmed_rc = {
                'retrieved_chunks': (rag_correction_context.get('retrieved_chunks') or [])[:1],
                'retrieval_policy': rag_correction_context.get('retrieval_policy', ''),
            }
            batch_payload['rag_correction'] = _trimmed_rc
            _batch_prompt_raw = _build_single_pass_prompt(batch_payload, strict=True)

        batch_result = _run_stage(
            stage_name=f'batch_{batch_idx + 1}_of_{batch_total}',
            primary_prompt=_batch_prompt_raw,
            fallback_prompt=_build_single_pass_prompt(compact_retry_payload, strict=True),
            primary_pack=batch_payload,
            fallback_pack=compact_retry_payload,
            primary_predict=single_pass_predict,
            fallback_predict=single_retry_predict,
        )

        if batch_result.get('unavailable'):
            any_batch_failed = True
            batch_limitations.extend(batch_result.get('limitations') or [])
            continue

        # Retry uniquement si le LLM n'a produit ni plan ni issues (réponse vide)
        batch_plan = batch_result.get('correction_plan') if isinstance(batch_result.get('correction_plan'), dict) else {}
        batch_issues = batch_result.get('issues') if isinstance(batch_result.get('issues'), list) else []
        plan_empty = _is_correction_plan_empty(batch_plan)
        issues_empty = len(batch_issues) == 0

        # Retry uniquement si le LLM était indisponible ou a renvoyé un JSON invalide
        _lims = ' '.join(str(l) for l in (batch_result.get('limitations') or []))
        need_retry = bool(batch_result.get('unavailable')) or 'invalide' in _lims.lower() or 'invalid' in _lims.lower()
        if need_retry:
            strict_retry_performed = True
            _notify_progress(f'Batch {batch_idx + 1}/{batch_total} : approfondissement de l\'analyse...')
            retry_result = _run_stage(
                stage_name=f'batch_{batch_idx + 1}_retry_strict',
                primary_prompt=_build_single_pass_prompt(batch_payload, strict=True),
                fallback_prompt=_build_single_pass_prompt(compact_retry_payload, strict=True),
                primary_pack=batch_payload,
                fallback_pack=compact_retry_payload,
                primary_predict=single_pass_predict,
                fallback_predict=single_retry_predict,
            )
            if not retry_result.get('unavailable'):
                batch_result = retry_result

        # Accumulate results from this batch
        batch_plan = batch_result.get('correction_plan') if isinstance(batch_result.get('correction_plan'), dict) else {}

        # If the plan is empty but issues were detected, build a minimal correction plan
        # from the issues themselves (3b model often skips the correction_plan step)
        if _is_correction_plan_empty(batch_plan):
            auto_fill = {}
            auto_mappings = {}
            auto_casts = {}
            auto_trim = []
            auto_dates = []
            for iss in (batch_result.get('issues') or []):
                if not isinstance(iss, dict):
                    continue
                col = iss.get('column', '')
                cat = iss.get('category', '')
                if not col:
                    continue
                suggested = iss.get('suggested_correction') or iss.get('correction')

                if cat in ('valeur_manquante', 'valeur_sentinelle'):
                    auto_fill[col] = {'strategy': 'mode'}

                elif cat in (
                    'manquant_deguise', 'encodage_incoherent', 'valeur_aberrante',
                    'artefact_excel', 'annee_incorrecte', 'type_mixte',
                    'booleen_incoherent', 'casse_incoherente', 'separateur_decimal',
                    'valeur_negative_impossible', 'unite_melangee', 'caractere_special',
                    'valeur_invalide_x',
                ):
                    if isinstance(suggested, dict) and suggested:
                        flat = {k: v for k, v in suggested.items() if not isinstance(v, (dict, list))}
                        if flat:
                            if col in auto_mappings:
                                auto_mappings[col].update(flat)
                            else:
                                auto_mappings[col] = flat

                elif cat == 'valeur_numerique_texte':
                    auto_casts[col] = 'numeric'
                    if col not in auto_trim:
                        auto_trim.append(col)

                elif cat in ('colonne_date', 'format_date_mixte'):
                    if col not in auto_dates:
                        auto_dates.append(col)

                elif cat == 'espace_parasite':
                    if col not in auto_trim:
                        auto_trim.append(col)

                elif cat == 'type_incorrect':
                    if isinstance(suggested, dict):
                        for k, v in suggested.items():
                            if v in ('integer', 'numeric', 'float', 'string'):
                                auto_casts[col] = v

                # Structural issues: empty/constant columns → propose drop
                elif cat in ('colonne_vide', 'colonne_constante'):
                    if col not in (batch_plan.get('drop_columns') or []):
                        batch_plan.setdefault('drop_columns', []).append(col)

                # Flag-only issues: require human decision
                elif cat in ('doublons_patients', 'incoherence_age_date', 'mojibake',
                             'colonne_quasi_constante', 'id_manquant'):
                    pass  # signaled in issues; correction requires human review

            if auto_fill:
                batch_plan['fill_missing'] = auto_fill
            if auto_mappings:
                batch_plan['value_mappings'] = auto_mappings
            if auto_casts:
                batch_plan['type_casts'] = auto_casts
            if auto_trim:
                batch_plan['trim_whitespace_columns'] = auto_trim
            if auto_dates:
                batch_plan['parse_dates'] = auto_dates

        # New batch takes precedence over accumulation — each batch owns its columns;
        # swapping args ensures a later batch can override an earlier one for shared columns
        # (e.g. cross-column issues now included in every batch).
        merged_plan = _merge_correction_plans(batch_plan, merged_plan)
        batch_justifications = batch_result.get('correction_justifications') or {}
        if isinstance(batch_justifications, dict):
            merged_justifications.update(batch_justifications)
        raw_batch_issues = batch_result.get('issues') if isinstance(batch_result.get('issues'), list) else []
        for issue in raw_batch_issues:
            if not isinstance(issue, dict):
                continue
            if not issue.get('column') or not issue.get('explanation'):
                continue
            # Filter false positives: binary columns must never generate these categories
            col_name = str(issue.get('column') or '')
            cat = str(issue.get('category') or '')
            if col_name in _binary_col_names and cat in _BINARY_FALSE_POSITIVE_CATS:
                continue
            # valeur_manquante on a binary column with 0% real missing = LLM confusing 0 with null
            if col_name in _binary_no_missing and cat in ('valeur_manquante', 'valeur_sentinelle'):
                continue
            # Dedup: skip if this exact (column, category) pair already reported
            _issue_key = (col_name, cat)
            if _issue_key in _seen_issue_keys:
                continue
            _seen_issue_keys.add(_issue_key)
            merged_issues_all.append(issue)
        if batch_result.get('summary'):
            merged_summaries.append(str(batch_result['summary']))
        if last_result is None:
            last_result = batch_result

    # Synthesize a single result object for the return block
    if last_result is None:
        last_result = {
            'unavailable': True,
            'summary': '',
            'issues': [],
            'correction_plan': {},
            'limitations': batch_limitations,
            'model_used': model_name,
            'attempt': 'primary',
            'validation_status': {},
            'normalization_notes': [],
            'normalization_severity_score': 0,
        }

    all_llm_unavailable = any_batch_failed and last_result.get('unavailable')
    correction_plan = merged_plan  # LLM plan only — no deterministic fallback
    if all_llm_unavailable:
        llm_status = 'unavailable'
        limitations = list(dict.fromkeys(
            batch_limitations + ['LLM indisponible: aucune correction generee.']
        ))
    else:
        llm_status = 'retried' if strict_retry_performed else 'ok'
        limitations = list(dict.fromkeys(
            batch_limitations + (last_result.get('limitations') if isinstance(last_result.get('limitations'), list) else [])
        ))

    llm_issues = merged_issues_all

    return {
        'summary': ' | '.join(merged_summaries) if merged_summaries else '',
        'issues': llm_issues,
        'recommendations': [],
        'correction_plan': correction_plan,
        'correction_justifications': merged_justifications,
        'llm_proposed_correction_plan': merged_plan,
        'corrected_preview_rows': [],
        'column_assessment': [],
        'limitations': limitations,
        'analysis_pack': prompt_payload,
        'model_used': last_result.get('model_used'),
        'attempt': last_result.get('attempt'),
        'llm_status': llm_status,
        'normalization_notes': last_result.get('normalization_notes', []),
        'normalization_severity_score': last_result.get('normalization_severity_score', 0),
        'second_pass': {
            'status': llm_status,
            'strict_retry': strict_retry_performed,
            'model_used': last_result.get('model_used'),
            'attempt': last_result.get('attempt'),
            'batches_total': len(col_batches),
            'batches_failed': sum(1 for _ in batch_limitations),
        },
        'validation_status': last_result.get('validation_status') or {},
        'validation_status_pass2': {},
        'route': route,
        'section_analyses': retrieval_context.get('section_fusion', []),
        'rag_context': retrieval_context,
        'pipeline': {
            'stage': 'batched_correction',
            'batches_total': len(col_batches),
            'total_columns_analysed': len(all_priority_cols),
            'priority_columns': sum(1 for c in all_priority_cols if not c.get('clean')),
            'clean_columns_included': sum(1 for c in all_priority_cols if c.get('clean')),
            'chunks_count': len(chunks),
            'retrieved_chunks_count': retrieval_context.get('retrieved_chunks_count', 0),
            'retrieval': retrieval_context.get('retrieval_policy'),
            'vector_store': retrieval_context.get('vector_store', {}),
        },
    }


def _resolve_llm_column_name(column_name, rename_map, available_columns):
    if column_name in available_columns:
        return column_name
    if column_name in rename_map:
        renamed = rename_map[column_name]
        if renamed in available_columns:
            return renamed
    normalized_target = normalize_header(column_name)
    for candidate in available_columns:
        if normalize_header(candidate) == normalized_target:
            return candidate
    return None


def _apply_llm_fill_strategy(series, strategy_spec):
    if strategy_spec in [None, '']:
        return series
    if not isinstance(strategy_spec, dict):
        return series.fillna(strategy_spec)

    strategy = str(strategy_spec.get('strategy', '')).lower()
    value = strategy_spec.get('value')

    if strategy == 'constant':
        return series.fillna(value)
    if strategy == 'mode':
        mode_values = series.mode(dropna=True)
        if not mode_values.empty:
            return series.fillna(mode_values.iloc[0])
        return series
    if strategy == 'mean':
        numeric = pd.to_numeric(series, errors='coerce')
        if numeric.notna().any():
            return series.fillna(float(numeric.mean()))
        return series
    if strategy == 'median':
        numeric = pd.to_numeric(series, errors='coerce')
        if numeric.notna().any():
            return series.fillna(float(numeric.median()))
        return series
    if strategy == 'forward_fill':
        return series.ffill()
    if strategy == 'backward_fill':
        return series.bfill()

    return series.fillna(value)


def _llm_report_values_equal(before_value, after_value):
    try:
        before_is_missing = pd.isna(before_value)
        after_is_missing = pd.isna(after_value)
        if bool(before_is_missing) and bool(after_is_missing):
            return True
    except Exception:
        pass
    return str(before_value) == str(after_value)


def _count_series_changes(before_series, after_series):
    changed_count = 0
    for before_value, after_value in zip(before_series.tolist(), after_series.tolist()):
        if not _llm_report_values_equal(before_value, after_value):
            changed_count += 1
    return changed_count


def _run_bio_value_correction_pass(dataframe, progress_callback=None):
    """
    For each biological column matched via LOINC (primary) or medical_kb (fallback),
    extract all unique values, ask the LLM which ones are aberrant and how to correct
    them, then return a value_mappings dict covering every row in the dataset.

    LOINC matching provides authoritative reference ranges and official source citations.
    medical_kb is used as fallback when no LOINC code is found.
    """
    from .preprocess_rag import _load_medical_kb
    from .loinc_mapper import match_column_to_loinc, get_reference_range, validate_value_against_loinc

    def _notify(msg):
        try:
            if progress_callback:
                progress_callback(msg)
        except Exception:
            pass

    documents = _load_medical_kb()
    if not documents:
        return {}, []

    model_name = os.environ.get('OLLAMA_PREPROCESS_MODEL') or os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b-instruct')
    num_ctx = _env_int('OLLAMA_NUM_CTX', 16384)
    candidate_bases = _get_ollama_candidate_bases()
    timeout_seconds = _env_int('OLLAMA_BIO_TIMEOUT_SECONDS', 300)

    col_names = list(dataframe.columns)
    all_value_mappings = {}
    all_applied = []

    for doc in documents:
        patterns = [str(p).lower() for p in doc.get('patterns', [])]
        matched_col = None
        for col in col_names:
            col_lower = col.lower()
            if any(pat in col_lower or col_lower in pat for pat in patterns):
                matched_col = col
                break
        if not matched_col:
            continue

        series = dataframe[matched_col]
        numeric_series = pd.to_numeric(series, errors='coerce')
        unique_vals = sorted([v for v in numeric_series.dropna().unique().tolist()])
        if not unique_vals:
            continue

        # Try LOINC match first — provides authoritative ranges and source citations
        loinc_entry = match_column_to_loinc(matched_col)
        loinc_ref = get_reference_range(loinc_entry, population='dialysis') if loinc_entry else None

        # Build bounds: LOINC takes priority over KB
        if loinc_entry:
            impossible_above = loinc_entry.get('impossible_above')
            impossible_below = loinc_entry.get('impossible_below')
            critical_high = loinc_ref.get('critical_high') if loinc_ref else doc.get('critical_high')
            critical_low = loinc_ref.get('critical_low') if loinc_ref else None
            normal_low = loinc_ref.get('low') if loinc_ref else (doc.get('normal') or [None, None])[0]
            normal_high = loinc_ref.get('high') if loinc_ref else (doc.get('normal') or [None, None])[1]
            unit = loinc_entry.get('unit', doc.get('unit', ''))
            label = loinc_entry.get('component', doc.get('label', matched_col))
            loinc_code = loinc_entry.get('loinc_code', '')
            loinc_source = loinc_ref.get('source', 'LOINC') if loinc_ref else 'LOINC'
        else:
            impossible_above = doc.get('impossible_above')
            impossible_below = doc.get('impossible_below')
            critical_high = doc.get('critical_high')
            critical_low = None
            normal_low = (doc.get('normal') or [None, None])[0]
            normal_high = (doc.get('normal') or [None, None])[1]
            unit = doc.get('unit', '')
            label = doc.get('label', matched_col)
            loinc_code = None
            loinc_source = 'medical_kb'

        # Only call LLM if suspicious values exist
        def _is_suspicious(v, _imp_above=impossible_above, _imp_below=impossible_below, _crit_high=critical_high):
            if _imp_above is not None and v > _imp_above:
                return True
            if _imp_below is not None and v < _imp_below:
                return True
            if _crit_high is not None and v > _crit_high * 3:
                return True
            return False

        suspicious = [v for v in unique_vals if _is_suspicious(v)]
        if not suspicious:
            continue

        loinc_info = f' [LOINC {loinc_code}, source: {loinc_source}]' if loinc_code else ' [source: medical_kb]'
        _notify(f'Correction biologique LOINC : {matched_col}{loinc_info} ({len(suspicious)} valeur(s) suspecte(s))...')

        notes = doc.get('notes', '')
        errors = doc.get('common_errors', [])
        unit_conversions = (loinc_entry.get('unit_conversions', []) if loinc_entry else [])

        prompt = (
            f'Tu es un expert en nephrologie. Analyse les valeurs de la colonne "{matched_col}" '
            f'({label}, unite officielle LOINC: {unit}'
            + (f', LOINC {loinc_code}' if loinc_code else '')
            + f'). '
            f'Plage normale ({loinc_source}): {normal_low}-{normal_high} {unit}. '
        )
        if critical_high is not None:
            prompt += f'Seuil critique haut: {critical_high}. '
        if critical_low is not None:
            prompt += f'Seuil critique bas: {critical_low}. '
        if impossible_above is not None:
            prompt += f'Valeur physiologiquement impossible au-dessus de: {impossible_above}. '
        if unit_conversions:
            prompt += 'Conversions d\'unites connues: ' + '; '.join(c.get('note', '') for c in unit_conversions[:3]) + '. '
        if notes:
            prompt += f'Note clinique: {notes} '
        if errors:
            prompt += f'Erreurs courantes: {"; ".join(errors)}. '
        prompt += (
            f'Voici toutes les valeurs uniques non-nulles presentes dans le dataset: {unique_vals}. '
            f'Valeurs suspectes identifiees statistiquement: {suspicious}. '
            'Pour chaque valeur aberrante ou biologiquement impossible, propose la valeur corrigee ET explique brievement pourquoi (ex: zero en trop, erreur unite, valeur impossible). '
            'Si une valeur est simplement elevee mais cliniquement plausible en dialyse, ne la corrige pas. '
            'Reponds UNIQUEMENT avec un JSON: {"corrections": {"valeur_erronee": {"valeur_corrigee": valeur_ou_null, "raison": "explication courte"}, ...}} '
            'Si aucune correction n\'est necessaire: {"corrections": {}}'
        )

        request_payload = {
            'model': model_name,
            'prompt': prompt,
            'stream': False,
            'format': 'json',
            'options': {'temperature': 0.05, 'num_predict': 512, 'num_ctx': num_ctx},
        }
        request_data = json.dumps(request_payload).encode('utf-8')

        corrections = {}
        bio_reasons = {}
        for ollama_base in candidate_bases:
            try:
                req = urllib_request.Request(
                    f'{ollama_base}/api/generate',
                    data=request_data,
                    headers={'Content-Type': 'application/json'},
                    method='POST',
                )
                body = _ollama_urlopen_wall_clock(req, wall_timeout=timeout_seconds)
                raw = json.loads(body).get('response', '{}')
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                except json.JSONDecodeError:
                    # Attempt to recover truncated JSON by closing the object
                    try:
                        raw_fixed = raw.strip().rstrip(',').rstrip('"').rstrip(':')
                        if not raw_fixed.endswith('}'):
                            raw_fixed += '}'
                        if not raw_fixed.endswith('}}'):
                            raw_fixed += '}'
                        parsed = json.loads(raw_fixed)
                    except Exception:
                        parsed = {}
                corrections_raw = parsed.get('corrections') if isinstance(parsed, dict) else {}
                if not isinstance(corrections_raw, dict):
                    corrections_raw = {}
                # Support both flat {val: corrected} and nested {val: {valeur_corrigee: ..., raison: ...}}
                corrections = {}
                for _rk, _rv in corrections_raw.items():
                    if isinstance(_rv, dict):
                        corrections[_rk] = _rv.get('valeur_corrigee')
                        bio_reasons[_rk] = str(_rv.get('raison', ''))
                    else:
                        corrections[_rk] = _rv
                break
            except Exception as exc:
                logger.warning('[BIO_PASS] %s col=%s error=%s', ollama_base, matched_col, exc)
                continue

        if not corrections:
            continue

        # Convert keys to match actual dtype in the series
        typed_corrections = {}
        for raw_key, corrected_val in corrections.items():
            try:
                numeric_key = float(str(raw_key))
                # Try int key too if values are integers
                int_key = int(numeric_key) if numeric_key == int(numeric_key) else None
                for candidate in ([numeric_key, int_key, str(raw_key), raw_key] if int_key is not None
                                  else [numeric_key, str(raw_key), raw_key]):
                    if candidate is None:
                        continue
                    typed_corrections[candidate] = corrected_val
            except Exception:
                typed_corrections[raw_key] = corrected_val

        # Guard: reject bio corrections that move a valid in-range value out of range
        # (e.g. phosphore_basale=32 mg/L is valid [10-200], LLM must not map it to 1034)
        _bio_num_domain = ((_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(matched_col)
                           or (_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(matched_col.lower()))
        if _bio_num_domain:
            _bio_min = _bio_num_domain.get('min')
            _bio_max = _bio_num_domain.get('max')
            if _bio_min is not None and _bio_max is not None:
                _guarded = {}
                for _bk, _bv in typed_corrections.items():
                    try:
                        _bk_f = float(str(_bk))
                        if _bio_min <= _bk_f <= _bio_max:
                            # Source already valid — only allow if target also in range
                            _is_null_bv = _bv is None or (isinstance(_bv, float) and np.isnan(_bv))
                            if _is_null_bv:
                                continue  # Don't nullify a valid value
                            try:
                                if not (_bio_min <= float(str(_bv)) <= _bio_max):
                                    continue  # Target out of range — reject
                            except (ValueError, TypeError):
                                pass
                    except (ValueError, TypeError):
                        pass
                    _guarded[_bk] = _bv
                typed_corrections = _guarded

        if typed_corrections:
            before_series = dataframe[matched_col].copy()
            replaced = dataframe[matched_col].replace(typed_corrections)
            cells_changed = _count_series_changes(before_series, replaced)
            all_value_mappings[matched_col] = typed_corrections
            # Build human-readable justification from per-value reasons returned by the LLM
            _bio_justif_parts = []
            for _bk, _bv in typed_corrections.items():
                try:
                    _bk_f = float(str(_bk))
                    _bk_str = str(int(_bk_f)) if _bk_f == int(_bk_f) else str(_bk)
                except (ValueError, TypeError):
                    _bk_str = str(_bk)
                _reason = bio_reasons.get(str(_bk)) or bio_reasons.get(_bk_str) or ''
                if _reason:
                    _bio_justif_parts.append(_reason)
            _bio_justification = ' | '.join(dict.fromkeys(_bio_justif_parts)) or 'Correction biologique (valeur hors plage physiologique)'
            all_applied.append({
                'action': 'bio_value_correction',
                'count': len(typed_corrections),
                'cells_changed': cells_changed,
                'details': {
                    'columns': [{
                        'column': matched_col,
                        'cells_changed': cells_changed,
                        'corrections': {str(k): v for k, v in typed_corrections.items()},
                        'loinc_code': loinc_code,
                        'loinc_source': loinc_source,
                        'reference_range': {'low': normal_low, 'high': normal_high, 'unit': unit},
                        'justification': _bio_justification,
                    }]
                },
            })
            logger.info('[BIO_PASS] col=%s loinc=%s corrections=%s cells_changed=%s', matched_col, loinc_code, typed_corrections, cells_changed)

    return all_value_mappings, all_applied


def _run_llm_flagged_corrections(dataframe, llm_issues, already_corrected_columns=None, progress_callback=None):
    """
    For columns flagged by the LLM as critical/warning but NOT covered by the bio KB,
    ask the LLM to CLASSIFY each suspicious value before deciding whether to correct it:
      - "error"        : clear data entry error (sentinel, typo, biologically impossible) → correct
      - "extreme_real" : extreme but clinically plausible for a critically ill patient   → keep, flag only
      - "uncertain"    : context insufficient to decide                                   → keep, flag only
    Only "error" values are auto-corrected.
    Fallback (LLM unavailable): only correct obvious sentinel values (9999, -1, -99, -999, 99999).
    """
    # Sentinel values that are always errors regardless of context (0 is NOT a sentinel — it means absent/no)
    _SENTINEL_VALUES = {9999.0, 99999.0, 999.0, -1.0, -99.0, -999.0}

    def _notify(msg):
        try:
            if progress_callback:
                progress_callback(msg)
        except Exception:
            pass

    already_corrected = set(already_corrected_columns or [])

    # Collect numeric columns with statistically extreme values that were flagged
    target_columns = {}
    for issue in (llm_issues or []):
        if not isinstance(issue, dict):
            continue
        col = issue.get('column')
        if not col or col in already_corrected or col not in dataframe.columns:
            continue
        severity = str(issue.get('severity', '')).lower()
        if severity not in ('critical', 'warning', 'error'):
            continue
        series = dataframe[col]
        numeric_series = pd.to_numeric(series, errors='coerce')
        valid_count = numeric_series.notna().sum()
        if valid_count < 3:
            continue
        q1 = numeric_series.quantile(0.25)
        q3 = numeric_series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lower = q1 - 3 * iqr
        upper = q3 + 3 * iqr
        suspicious = [
            float(v) for v in numeric_series.dropna().unique().tolist()
            if v < lower or v > upper
        ]
        if not suspicious:
            continue
        median_val = float(numeric_series.median())
        # Include a few representative normal values so LLM can judge context
        normal_sample = sorted([
            float(v) for v in numeric_series.dropna().tolist()
            if lower <= v <= upper
        ])
        normal_sample = normal_sample[:3] + normal_sample[-3:] if len(normal_sample) > 6 else normal_sample
        target_columns[col] = {
            'explanation': issue.get('explanation', ''),
            'suspicious': suspicious,
            'median': median_val,
            'normal_sample': normal_sample,
        }
        already_corrected.add(col)

    if not target_columns:
        return {}, [], set()

    _notify(f"Analyse LLM de {len(target_columns)} colonne(s) suspecte(s) avant correction...")

    # Build prompt: LLM must identify the likely data-entry mistake and reconstruct the intended value
    col_desc_parts = []
    for col, info in target_columns.items():
        col_desc_parts.append(
            f'Colonne "{col}": valeurs_normales={info["normal_sample"]}, '
            f'mediane={info["median"]:.2f}, '
            f'valeurs_suspectes={info["suspicious"]}. '
            f'Probleme: {info["explanation"]}'
        )
    col_desc = '\n'.join(col_desc_parts)

    prompt = (
        'Tu es expert en données médicales. Analyse ces valeurs suspectes et détermine la cause probable de chaque anomalie. '
        'Raisonne ainsi pour chaque valeur suspecte:\n'
        '1. Compare la valeur suspecte aux valeurs normales de la colonne.\n'
        '2. Détermine si c\'est une erreur de saisie logique:\n'
        '   - Chiffre en trop: 200 → 20 (zéro ajouté par erreur)\n'
        '   - Virgule oubliée: 555 → 5.55 ou 55.5 (choisir la plus proche de la médiane)\n'
        '   - Facteur x10 ou x100: 120 → 12 si la médiane est ~12\n'
        '   - Valeur codée sans signification: 9999, -1, -99, 999 → remplacer par médiane\n'
        '   - Valeur biologiquement impossible: reconstruire selon le contexte\n'
        '3. Si c\'est une valeur extrême mais cliniquement possible pour un patient critique → ne pas corriger.\n'
        '4. Si tu ne peux pas déduire logiquement la valeur voulue → utilise null.\n'
        'Classification:\n'
        '- "error": erreur de saisie identifiable avec valeur_corrigee reconstruite logiquement\n'
        '- "extreme_real": valeur extreme mais médicalement plausible\n'
        '- "uncertain": impossible à déterminer\n'
        'Reponds UNIQUEMENT en JSON:\n'
        '{"analyses": {"nom_colonne": {"valeur_suspecte_en_string": {"classification": "error"|"extreme_real"|"uncertain", '
        '"valeur_corrigee": nombre_ou_null, "raison": "ex: zero en trop, mediane=X"}}}}\n'
        f'Colonnes:\n{col_desc}'
    )

    model_name = os.environ.get('OLLAMA_PREPROCESS_MODEL') or os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct')
    num_ctx = _env_int('OLLAMA_NUM_CTX', 4096)
    candidate_bases = _get_ollama_candidate_bases()
    request_payload = {
        'model': model_name,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {'temperature': 0.0, 'num_predict': 512, 'num_ctx': num_ctx},
    }
    request_data = json.dumps(request_payload).encode('utf-8')

    llm_analyses = {}
    for ollama_base in candidate_bases:
        try:
            req = urllib_request.Request(
                f'{ollama_base}/api/generate',
                data=request_data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            body = _ollama_urlopen_wall_clock(req, wall_timeout=120)
            raw = json.loads(body).get('response', '{}')
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            llm_analyses = parsed.get('analyses') if isinstance(parsed, dict) else {}
            if not isinstance(llm_analyses, dict):
                llm_analyses = {}
            break
        except Exception as exc:
            logger.warning('[LLM_FLAGGED] %s error=%s', ollama_base, exc)
            continue

    all_value_mappings = {}
    all_applied = []
    all_flagged_only = []  # values LLM said are extreme_real or uncertain
    knn_columns = set()    # columns where NaN was set — need KNN imputation

    for col, info in target_columns.items():
        col_analyses = llm_analyses.get(col) if isinstance(llm_analyses.get(col), dict) else {}

        typed_corrections = {}
        flagged_kept = []

        for suspicious_val in info['suspicious']:
            val_key = str(int(suspicious_val)) if suspicious_val == int(suspicious_val) else str(suspicious_val)
            analysis = col_analyses.get(val_key) or col_analyses.get(str(suspicious_val)) or {}
            classification = str(analysis.get('classification', '')).lower()
            raison = analysis.get('raison', '')
            corrected_val = analysis.get('valeur_corrigee')

            if classification == 'error':
                if corrected_val is not None:
                    # LLM reconstructed the intended value (e.g. 200→20) — use it
                    _add_typed_key(typed_corrections, suspicious_val, corrected_val)
                    logger.info('[LLM_FLAGGED] CORRECTED col=%s val=%s -> %s reason=%s', col, suspicious_val, corrected_val, raison)
                else:
                    # LLM confirmed error but couldn't estimate → nullify for KNN imputation
                    _add_typed_key(typed_corrections, suspicious_val, float('nan'))
                    knn_columns.add(col)
                    logger.info('[LLM_FLAGGED] NULLIFIED col=%s val=%s (KNN will impute) reason=%s', col, suspicious_val, raison)
            elif classification in ('extreme_real', 'uncertain'):
                # Keep value as-is, record it as flagged for manual review
                flagged_kept.append({'value': suspicious_val, 'classification': classification, 'raison': raison})
                logger.info('[LLM_FLAGGED] KEPT col=%s val=%s classification=%s reason=%s', col, suspicious_val, classification, raison)
            else:
                # LLM did not classify — sentinels → NaN for KNN, others → keep
                if suspicious_val in _SENTINEL_VALUES:
                    _add_typed_key(typed_corrections, suspicious_val, float('nan'))
                    knn_columns.add(col)
                    logger.info('[LLM_FLAGGED] SENTINEL_NULLIFIED col=%s val=%s -> NaN (KNN imputation)', col, suspicious_val)
                else:
                    flagged_kept.append({'value': suspicious_val, 'classification': 'uncertain', 'raison': 'Non classifié par le LLM — conservé par précaution'})

        if typed_corrections:
            before_series = dataframe[col].copy()
            replaced = dataframe[col].replace(typed_corrections)
            cells_changed = _count_series_changes(before_series, replaced)
            all_value_mappings[col] = typed_corrections
            all_applied.append({
                'action': 'llm_value_correction',
                'count': len(typed_corrections),
                'cells_changed': cells_changed,
                'details': {
                    'columns': [{
                        'column': col,
                        'cells_changed': cells_changed,
                        'corrections': {str(k): v for k, v in typed_corrections.items()},
                        'explanation': info.get('explanation', ''),
                        'kept_as_real': flagged_kept,
                    }]
                },
            })

        if flagged_kept and not typed_corrections:
            # Column only has extreme_real/uncertain values → record as flagged, no correction
            all_flagged_only.append({'col': col, 'kept': flagged_kept})

    # If LLM was completely unavailable (no analyses at all), nullify sentinels for KNN imputation
    if not llm_analyses and target_columns:
        _notify("LLM indisponible — sentinelles nullifiées pour imputation KNN.")
        for col, info in target_columns.items():
            typed_corrections = {}
            for v in info['suspicious']:
                if v in _SENTINEL_VALUES:
                    _add_typed_key(typed_corrections, v, float('nan'))
                    knn_columns.add(col)
            if typed_corrections:
                before_series = dataframe[col].copy()
                replaced = dataframe[col].replace(typed_corrections)
                cells_changed = _count_series_changes(before_series, replaced)
                all_value_mappings[col] = typed_corrections
                all_applied.append({
                    'action': 'llm_value_correction',
                    'count': len(typed_corrections),
                    'cells_changed': cells_changed,
                    'details': {
                        'columns': [{
                            'column': col,
                            'cells_changed': cells_changed,
                            'corrections': {str(k): None for k in typed_corrections},
                            'explanation': info.get('explanation', '') + ' [sentinelle nullifiée → imputation KNN]',
                            'kept_as_real': [],
                            'knn_imputation_pending': True,
                        }]
                    },
                })

    return all_value_mappings, all_applied, list(knn_columns)


def _run_model_imputation(dataframe, columns_to_impute, n_neighbors=5, progress_callback=None):
    """
    Fill NaN values (set by aberrant value replacement) using KNN imputation.

    KNN estimates each missing value from the k most similar patients based on
    all other numeric columns — more contextual than a global median.

    Returns (imputed_df, imputed_report) where imputed_report lists imputed cells
    flagged as needs_review=True.
    """
    import numpy as np

    def _notify(msg):
        try:
            if progress_callback:
                progress_callback(msg)
        except Exception:
            pass

    if not columns_to_impute:
        return dataframe, []

    try:
        from sklearn.impute import KNNImputer
    except ImportError:
        _notify("scikit-learn non disponible — imputation KNN ignorée.")
        return dataframe, []

    # Only numeric columns can be imputed by KNN
    numeric_cols = list(dataframe.select_dtypes(include=[np.number]).columns)
    target_cols = [c for c in columns_to_impute if c in numeric_cols]
    if not target_cols:
        return dataframe, []

    _notify(f"Imputation KNN ({len(target_cols)} colonne(s) avec valeurs aberrantes nullifiées)...")

    # Snapshot: which cells are NaN before imputation
    df_numeric = dataframe[numeric_cols].copy()
    was_nan_before = df_numeric[target_cols].isnull()

    k = max(1, min(n_neighbors, len(dataframe) - 1))
    imputer = KNNImputer(n_neighbors=k)
    try:
        imputed_array = imputer.fit_transform(df_numeric)
    except Exception as exc:
        _notify(f"Imputation KNN échouée: {exc}")
        return dataframe, []

    df_imputed = pd.DataFrame(imputed_array, columns=numeric_cols, index=dataframe.index)

    result_df = dataframe.copy()
    imputed_report = []

    for col in target_cols:
        imputed_mask = was_nan_before[col]
        if not imputed_mask.any():
            continue
        result_df[col] = df_imputed[col]
        imputed_count = int(imputed_mask.sum())
        sample_imputed = [
            round(float(df_imputed.loc[idx, col]), 4)
            for idx in dataframe.index[imputed_mask][:5]
        ]
        imputed_report.append({
            'column': col,
            'imputed_count': imputed_count,
            'method': f'KNN (k={k})',
            'sample_values': sample_imputed,
            'needs_review': True,
            'note': 'Valeur estimée par similarité avec les autres patients — à vérifier',
        })
        _notify(f"KNN: {col} — {imputed_count} valeur(s) imputée(s)")

    return result_df, imputed_report


def _add_typed_key(corrections_dict, numeric_val, corrected_val):
    """Add a numeric value and its int/str variants as keys in corrections_dict.
    corrected_val must be a scalar (int, float, None). If the LLM returned a dict or list,
    extract the first numeric value found, otherwise skip.
    """
    # Guard: pandas Series.replace cannot accept dict/list as replacement value
    if isinstance(corrected_val, dict):
        # Try to extract a numeric value from common LLM response patterns
        corrected_val = (
            corrected_val.get('valeur_corrigee')
            or corrected_val.get('value')
            or corrected_val.get('suggestion')
            or corrected_val.get('corrected')
            or None
        )
    if isinstance(corrected_val, (list, tuple)):
        corrected_val = corrected_val[0] if corrected_val else None
    if corrected_val is not None and not isinstance(corrected_val, (int, float)):
        try:
            corrected_val = float(corrected_val)
        except (ValueError, TypeError):
            corrected_val = None  # drop uncoercible values

    try:
        float_key = float(numeric_val)
        int_key = int(float_key) if float_key == int(float_key) else None
        candidates = [float_key, int_key, str(int_key) if int_key is not None else None, str(float_key)]
        for candidate in candidates:
            if candidate is not None:
                corrections_dict[candidate] = corrected_val
    except Exception:
        corrections_dict[numeric_val] = corrected_val


def _apply_llm_correction_plan(dataframe, llm_analysis):
    if not isinstance(llm_analysis, dict):
        return dataframe.copy(), []

    correction_plan = llm_analysis.get('correction_plan') or {}
    if not isinstance(correction_plan, dict):
        return dataframe.copy(), []

    correction_justifications = llm_analysis.get('correction_justifications') or {}
    if not isinstance(correction_justifications, dict):
        correction_justifications = {}

    corrected = dataframe.copy()
    applied_actions = []

    def _get_justification(col_name):
        return correction_justifications.get(str(col_name), '')

    # ── Pre-pass: replace Excel serial-0 date artifacts with null (deterministic) ──
    # pandas converts Excel date serial 0 → Timestamp('1899-12-30') → ISO "1899-12-30".
    # These are guaranteed data entry errors — remove unconditionally before LLM passes.
    _excel_artifact_strings = set(_ANOMALY_EXCEL_DATE_ARTIFACTS) | {
        '1899-12-30', '1899-12-31', '1899-12-29',
        '1900-01-00 00:00:00', '1899-12-30 00:00:00',
    }
    _artifact_cells_changed = 0
    _artifact_cols = []
    for _col in corrected.columns:
        _before = corrected[_col].copy()
        corrected[_col] = corrected[_col].apply(
            lambda v: None if (isinstance(v, str) and v.strip() in _excel_artifact_strings) else v
        )
        _changed = _count_series_changes(_before, corrected[_col])
        if _changed > 0:
            _artifact_cells_changed += _changed
            _artifact_cols.append({'column': str(_col), 'cells_changed': _changed,
                                    'justification': 'Artefact Excel détecté (serial date 0 = 1899-12-30) — valeur invalide remplacée par null'})
    if _artifact_cols:
        applied_actions.append({
            'action': 'excel_artifact_cleanup',
            'count': len(_artifact_cols),
            'cells_changed': _artifact_cells_changed,
            'details': {'columns': _artifact_cols},
        })
    # ── End pre-pass ──

    # ── Pre-pass: replace "X"/"x" with NaN in numeric/binary columns (deterministic) ──
    # "X" is always invalid in:
    #   - binary columns (0/1): cannot determine if X=0 or X=1 → null + KNN
    #   - numeric columns (>60% numeric values): X is a placeholder for missing → null + KNN
    # "X" is NOT replaced in text/categorical columns where it may be a legitimate value.
    _x_cols_changed = 0
    _x_col_details = []
    _INVALID_X_VALS = {'x', 'X', 'X ', ' X', 'xx', 'XX', '*'}

    import pandas as _pd_x
    for _col in corrected.columns:
        _series = corrected[_col]
        _non_null = _series.dropna()
        if len(_non_null) == 0:
            continue
        _str_vals = _non_null.astype(str).str.strip()
        _has_x = _str_vals.isin(_INVALID_X_VALS).any()
        if not _has_x:
            continue

        # Check if column is numeric or binary
        _non_x_vals = _str_vals[~_str_vals.isin(_INVALID_X_VALS)]
        _numeric_count = 0
        for _v in _non_x_vals:
            try:
                float(_v)
                _numeric_count += 1
            except (ValueError, TypeError):
                pass

        _numeric_ratio = _numeric_count / len(_non_x_vals) if len(_non_x_vals) > 0 else 0
        _is_numeric_or_binary = _numeric_ratio >= 0.6  # at least 60% numeric values

        if _is_numeric_or_binary:
            _before = corrected[_col].copy()
            corrected[_col] = corrected[_col].apply(
                lambda v: None if (isinstance(v, str) and v.strip() in _INVALID_X_VALS) else v
            )
            _changed = _count_series_changes(_before, corrected[_col])
            if _changed > 0:
                _x_cols_changed += _changed
                _x_col_details.append({
                    'column': str(_col),
                    'cells_changed': _changed,
                    'justification': 'Valeur "X" invalide dans colonne numérique/binaire — nullifiée puis estimée par imputation KNN (k=5 patients similaires)',
                })

    if _x_col_details:
        applied_actions.append({
            'action': 'invalid_x_cleanup',
            'count': len(_x_col_details),
            'cells_changed': _x_cols_changed,
            'details': {'columns': _x_col_details},
        })
    # ── End pre-pass X ──

    # ── Pre-pass: global decimal comma normalization (French locale "1,5" → "1.5") ──
    # Applied unconditionally on all object columns — the regex is narrow enough to only
    # match values that look exactly like numbers written with a comma decimal separator.
    # This is a deterministic fix: "2,3" and "2.3" in the same column both become 2.3.
    import re as _re_dc_fix
    _dc_fix_pat = _re_dc_fix.compile(r'^(-?\d[\d\s]*),(\d+)$')

    def _fix_dc(v):
        if not isinstance(v, str):
            return v
        _m = _dc_fix_pat.match(v.strip())
        if _m:
            return _m.group(1).replace(' ', '') + '.' + _m.group(2)
        return v

    _dc_total_changed = 0
    _dc_col_details = []
    for _col in corrected.columns:
        if not (corrected[_col].dtype == object or pd.api.types.is_string_dtype(corrected[_col])):
            continue
        _uniq = corrected[_col].dropna().unique()
        if not any(_dc_fix_pat.match(str(v).strip()) for v in _uniq[:200]):
            continue
        _before_dc = corrected[_col].copy()
        corrected[_col] = corrected[_col].apply(_fix_dc)
        _dc_changed = _count_series_changes(_before_dc, corrected[_col])
        if _dc_changed > 0:
            _dc_total_changed += _dc_changed
            _dc_col_details.append({
                'column': str(_col),
                'cells_changed': _dc_changed,
                'justification': 'Séparateur décimal virgule (notation française) → point normalisé automatiquement',
            })
    if _dc_col_details:
        applied_actions.append({
            'action': 'decimal_comma_fix',
            'count': len(_dc_col_details),
            'cells_changed': _dc_total_changed,
            'details': {'columns': _dc_col_details},
        })
    # ── End decimal comma pre-pass ──

    rename_columns = correction_plan.get('rename_columns') or {}
    rename_map = {}
    if isinstance(rename_columns, dict):
        rename_map = {str(source): str(target) for source, target in rename_columns.items() if source and target}
        if rename_map:
            existing_renames = {source: target for source, target in rename_map.items() if source in corrected.columns}
            if existing_renames:
                corrected = corrected.rename(columns=existing_renames)
                applied_actions.append({
                    'action': 'rename_columns',
                    'count': len(existing_renames),
                    'details': {
                        'columns': [
                            {'from': source, 'to': target,
                             'justification': f"Colonne '{source}' renommée en '{target}' pour correspondre à la nomenclature attendue."}
                            for source, target in existing_renames.items()
                        ],
                    },
                })

    available_columns = list(corrected.columns)

    drop_columns = correction_plan.get('drop_columns') or []
    if isinstance(drop_columns, list):
        columns_requested = [column for column in drop_columns if column in available_columns]
        if columns_requested:
            # Safety policy: column deletion from LLM plans is intentionally disabled.
            applied_actions.append({
                'action': 'drop_columns_skipped',
                'count': len(columns_requested),
                'reason': 'disabled_for_medical_safety',
                'details': {
                    'columns': [str(column) for column in columns_requested],
                    'message': 'Suppression ignoree par securite medicale.',
                },
            })

    trim_columns = correction_plan.get('trim_whitespace_columns') or []
    if isinstance(trim_columns, list):
        trimmed_count = 0
        trimmed_details = []
        total_cells_changed = 0
        for column_name in trim_columns:
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved:
                continue
            if corrected[resolved].dtype != object and not pd.api.types.is_string_dtype(corrected[resolved]):
                continue
            before_series = corrected[resolved].copy()
            corrected[resolved] = corrected[resolved].apply(lambda value: value.strip() if isinstance(value, str) else value)
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            trimmed_count += 1
            total_cells_changed += cells_changed
            _trim_justif = _get_justification(resolved) or (
                f"Espaces parasites détectés dans '{resolved}' — {cells_changed} cellule(s) normalisée(s) (suppression des espaces en début/fin de chaîne)."
            )
            trimmed_details.append({'column': resolved, 'cells_changed': cells_changed, 'justification': _trim_justif})
        if trimmed_count:
            applied_actions.append({
                'action': 'trim_whitespace',
                'count': trimmed_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': trimmed_details},
            })

    value_mappings = correction_plan.get('value_mappings') or {}
    if isinstance(value_mappings, dict):
        mapping_count = 0
        mapping_details = []
        total_cells_changed = 0
        for column_name, mapping in value_mappings.items():
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved or not isinstance(mapping, dict):
                continue
            # Filter out nested dict/list values — Series.replace only accepts scalars
            # Convert None → np.nan so Series.replace actually nullifies the cell
            flat_mapping = {
                k: (np.nan if v is None else v)
                for k, v in mapping.items()
                if not isinstance(v, (dict, list))
            }
            # Guard 1: never let the LLM overwrite a valid categorical code defined in domain rules
            _cat_domain = ((_MEDICAL_DOMAIN_RULES.get('categorical_codes') or {}).get(resolved)
                           or (_MEDICAL_DOMAIN_RULES.get('categorical_codes') or {}).get(resolved.lower()))
            if _cat_domain:
                _valid_code_strs = set(str(k) for k in (_cat_domain.get('codes') or {}).keys())
                flat_mapping = {
                    k: v for k, v in flat_mapping.items()
                    if str(k) not in _valid_code_strs
                }
            # Guard 2: protect valid in-range numeric values from being remapped.
            # Blocks two bad LLM behaviors:
            #   (a) null-ifying a valid value: seances_par_semaine=3 → null  (3 is valid, range 1-7)
            #   (b) moving a valid value out of range: phosphore_basale=49 → 1564.92  (49 is valid, 1564 is not)
            _num_domain_vm = ((_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(resolved)
                              or (_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(resolved.lower()))
            if _num_domain_vm:
                _vm_min = _num_domain_vm.get('min')
                _vm_max = _num_domain_vm.get('max')
                if _vm_min is not None and _vm_max is not None:
                    _filtered_vm = {}
                    for _k, _v in flat_mapping.items():
                        _is_null_target = _v is None or (isinstance(_v, float) and np.isnan(_v))
                        try:
                            _k_float = float(str(_k))
                            if _vm_min <= _k_float <= _vm_max:
                                # Source is already valid — only allow if target is also in range
                                if _is_null_target:
                                    continue  # (a) don't null-ify a valid value
                                try:
                                    _v_float = float(str(_v))
                                    if not (_vm_min <= _v_float <= _vm_max):
                                        continue  # (b) target is out of range — block
                                except (ValueError, TypeError):
                                    pass
                        except (ValueError, TypeError):
                            pass
                        _filtered_vm[_k] = _v
                    flat_mapping = _filtered_vm
            if not flat_mapping:
                continue
            before_series = corrected[resolved].copy()
            corrected[resolved] = corrected[resolved].replace(flat_mapping)
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            mapping_count += 1
            total_cells_changed += cells_changed
            _vm_llm = _get_justification(resolved)
            if not _vm_llm:
                _vm_examples = ', '.join(
                    f'"{k}"→"{v}"' for k, v in list(flat_mapping.items())[:2]
                )
                _vm_llm = (
                    f"{len(flat_mapping)} valeur(s) normalisée(s) dans '{resolved}'"
                    + (f" (ex : {_vm_examples})" if _vm_examples else '')
                    + f" — {cells_changed} cellule(s) modifiée(s)."
                )
            mapping_details.append({
                'column': resolved,
                'cells_changed': cells_changed,
                'mapping': mapping,
                'justification': _vm_llm,
            })
        if mapping_count:
            applied_actions.append({
                'action': 'value_mappings',
                'count': mapping_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': mapping_details},
            })

    type_casts = correction_plan.get('type_casts') or {}
    if isinstance(type_casts, dict):
        cast_count = 0
        cast_details = []
        total_cells_changed = 0
        for column_name, target_type in type_casts.items():
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved:
                continue
            before_series = corrected[resolved].copy()
            target = str(target_type).lower()
            if target in {'numeric', 'number', 'float', 'decimal'}:
                corrected[resolved] = pd.to_numeric(corrected[resolved], errors='coerce')
            elif target in {'integer', 'int'}:
                numeric = pd.to_numeric(corrected[resolved], errors='coerce')
                corrected[resolved] = numeric.round().astype('Int64')
            elif target in {'date', 'datetime'}:
                parsed = pd.to_datetime(corrected[resolved], errors='coerce', dayfirst=True)
                corrected[resolved] = parsed.dt.date
            elif target in {'string', 'text'}:
                corrected[resolved] = corrected[resolved].astype('string')
            else:
                continue
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            cast_count += 1
            total_cells_changed += cells_changed
            _type_labels = {
                'numeric': 'numérique (float)', 'number': 'numérique (float)', 'float': 'numérique (float)',
                'decimal': 'numérique (float)', 'integer': 'entier (int)', 'int': 'entier (int)',
                'date': 'date', 'datetime': 'date', 'string': 'texte', 'text': 'texte',
            }
            _cast_justif = _get_justification(resolved) or (
                f"Colonne '{resolved}' stockée avec un type incorrect — convertie en {_type_labels.get(target, target)}"
                f" pour permettre l'analyse numérique ({cells_changed} cellule(s) affectée(s))."
            )
            cast_details.append({
                'column': resolved,
                'target_type': str(target_type),
                'cells_changed': cells_changed,
                'justification': _cast_justif,
            })
        if cast_count:
            applied_actions.append({
                'action': 'type_casts',
                'count': cast_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': cast_details},
            })

    unit_conversions = correction_plan.get('unit_conversions') or {}
    if isinstance(unit_conversions, dict):
        conv_count = 0
        conv_details = []
        total_cells_changed = 0
        for column_name, spec in unit_conversions.items():
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved or not isinstance(spec, dict):
                continue
            factor = spec.get('factor')
            if not factor:
                continue
            # Guard: if ≥50% of non-null values are already within the valid domain range,
            # the column is not in the wrong unit — skip this conversion to avoid corrupting data.
            _num_domain_uc = ((_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(resolved)
                              or (_MEDICAL_DOMAIN_RULES.get('numeric_ranges') or {}).get(resolved.lower()))
            if _num_domain_uc:
                _uc_min = _num_domain_uc.get('min')
                _uc_max = _num_domain_uc.get('max')
                if _uc_min is not None and _uc_max is not None:
                    _uc_numeric = pd.to_numeric(corrected[resolved], errors='coerce').dropna()
                    if len(_uc_numeric) > 0:
                        _in_range_count = int(((_uc_numeric >= _uc_min) & (_uc_numeric <= _uc_max)).sum())
                        if _in_range_count / len(_uc_numeric) >= 0.5:
                            continue  # Values already in valid range — reject unit conversion
            before_series = corrected[resolved].copy()
            numeric_col = pd.to_numeric(corrected[resolved], errors='coerce')
            corrected[resolved] = (numeric_col * factor).round(4)
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            conv_count += 1
            total_cells_changed += cells_changed
            _uc_from = spec.get('from_unit', '?')
            _uc_to = spec.get('to_unit', '?')
            _uc_justif = _get_justification(resolved) or (
                f"Unité mixte détectée dans '{resolved}' : valeurs en {_uc_from} converties en {_uc_to}"
                f" (facteur ×{factor}) — {cells_changed} cellule(s) recalculée(s)."
            )
            conv_details.append({
                'column': resolved,
                'from_unit': _uc_from,
                'to_unit': _uc_to,
                'factor': factor,
                'cells_changed': cells_changed,
                'justification': _uc_justif,
            })
        if conv_count:
            applied_actions.append({
                'action': 'unit_conversions',
                'count': conv_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': conv_details},
            })

    parse_dates = correction_plan.get('parse_dates') or []
    if isinstance(parse_dates, list):
        parsed_count = 0
        parsed_details = []
        total_cells_changed = 0
        for column_name in parse_dates:
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved:
                continue
            source_series = corrected[resolved]
            # Guard: skip binary columns (0/1) — pd.to_datetime(1) = 1970-01-01 (epoch)
            non_null_vals = source_series.dropna()
            if len(non_null_vals) > 0:
                try:
                    unique_numeric = set(pd.to_numeric(non_null_vals, errors='coerce').dropna().unique())
                    if unique_numeric.issubset({0, 1, 0.0, 1.0}):
                        continue
                except Exception:
                    pass
            parsed_series = pd.to_datetime(source_series, errors='coerce', dayfirst=True)
            non_null_source = int(source_series.notna().sum())
            non_null_parsed = int(parsed_series.notna().sum())
            # Avoid destructive date coercion when the parse confidence is too low.
            if non_null_source > 0 and non_null_parsed < max(1, int(non_null_source * 0.8)):
                continue
            before_series = corrected[resolved].copy()
            corrected[resolved] = parsed_series.dt.date
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            parsed_count += 1
            total_cells_changed += cells_changed
            _date_justif = _get_justification(resolved) or (
                f"Dates dans '{resolved}' stockées en texte — converties au format date standard"
                f" ({non_null_parsed}/{non_null_source} valeurs parsées avec succès)."
            )
            parsed_details.append({
                'column': resolved,
                'cells_changed': cells_changed,
                'parsed_values': non_null_parsed,
                'source_values': non_null_source,
                'justification': _date_justif,
            })
        if parsed_count:
            applied_actions.append({
                'action': 'parse_dates',
                'count': parsed_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': parsed_details},
            })

    # Columns where auto-fill is medically prohibited (values encode clinical outcomes
    # that cannot be inferred/invented — would produce false clinical data).
    _NEVER_AUTOFILL_MEDICAL = frozenset({
        'delai_jusquau_deces_jours', 'cause_deces', 'date_deces', 'delai_deces',
        'date_naissance', 'date_debut_dialyse', 'annee_inclusion',
    })

    fill_missing = correction_plan.get('fill_missing') or {}
    if isinstance(fill_missing, dict):
        filled_count = 0
        fill_details = []
        total_cells_changed = 0
        for column_name, strategy_spec in fill_missing.items():
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved:
                continue
            if resolved in _NEVER_AUTOFILL_MEDICAL or resolved.lower() in _NEVER_AUTOFILL_MEDICAL:
                continue  # Medical safety: cannot auto-invent clinical outcome values
            # Guard: reject non-numeric constant fill on numeric columns (e.g. LLM proposes "x")
            if isinstance(strategy_spec, dict) and strategy_spec.get('strategy') == 'constant':
                fill_val = strategy_spec.get('value')
                if fill_val is not None and pd.api.types.is_numeric_dtype(corrected[resolved]):
                    try:
                        float(str(fill_val))
                    except (ValueError, TypeError):
                        continue
            elif not isinstance(strategy_spec, dict):
                if strategy_spec is None:
                    # None means "fill needed, no strategy specified" → promote to mode
                    strategy_spec = {'strategy': 'mode'}
                elif pd.api.types.is_numeric_dtype(corrected[resolved]):
                    # Guard: reject non-numeric bare values on numeric columns (e.g. LLM proposes "x")
                    try:
                        float(str(strategy_spec))
                    except (ValueError, TypeError):
                        continue
            before_series = corrected[resolved].copy()
            corrected[resolved] = _apply_llm_fill_strategy(corrected[resolved], strategy_spec)
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            filled_count += 1
            total_cells_changed += cells_changed
            _fill_llm = _get_justification(resolved)
            if not _fill_llm:
                _strat = strategy_spec.get('strategy') if isinstance(strategy_spec, dict) else str(strategy_spec or 'auto')
                _strat_labels = {
                    'median': 'la médiane de la colonne',
                    'mean': 'la moyenne de la colonne',
                    'mode': 'la valeur la plus fréquente (mode)',
                    'knn': 'KNN (k=5 patients similaires)',
                    'ffill': 'propagation avant (ffill)',
                    'bfill': 'propagation arrière (bfill)',
                    'constant': f"la constante '{strategy_spec.get('value') if isinstance(strategy_spec, dict) else strategy_spec}'",
                }
                _fill_llm = (
                    f"Valeurs manquantes dans '{resolved}' estimées par {_strat_labels.get(_strat, _strat)}"
                    f" — {cells_changed} cellule(s) comblée(s)."
                )
            fill_details.append({
                'column': resolved,
                'strategy': strategy_spec,
                'cells_changed': cells_changed,
                'justification': _fill_llm,
            })
        if filled_count:
            applied_actions.append({
                'action': 'fill_missing',
                'count': filled_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': fill_details},
            })

    default_values = correction_plan.get('default_values') or {}
    if isinstance(default_values, dict):
        default_count = 0
        default_details = []
        total_cells_changed = 0
        for column_name, default_value in default_values.items():
            resolved = _resolve_llm_column_name(str(column_name), rename_map, available_columns)
            if not resolved:
                continue
            if resolved in _NEVER_AUTOFILL_MEDICAL or resolved.lower() in _NEVER_AUTOFILL_MEDICAL:
                continue  # Medical safety: cannot auto-invent clinical outcome values
            before_series = corrected[resolved].copy()
            corrected[resolved] = corrected[resolved].fillna(default_value)
            cells_changed = _count_series_changes(before_series, corrected[resolved])
            default_count += 1
            total_cells_changed += cells_changed
            _dv_justif = _get_justification(resolved) or (
                f"Valeurs nulles dans '{resolved}' remplacées par la valeur par défaut '{default_value}'"
                f" — {cells_changed} cellule(s) comblée(s)."
            )
            default_details.append({
                'column': resolved,
                'default_value': default_value,
                'cells_changed': cells_changed,
                'justification': _dv_justif,
            })
        if default_count:
            applied_actions.append({
                'action': 'default_values',
                'count': default_count,
                'cells_changed': total_cells_changed,
                'details': {'columns': default_details},
            })

    return corrected, applied_actions


LLM_FOLLOWUP_REQUIRED_MESSAGE = 'Sortie LLM partielle ou non fiable; passe 2 requise pour proposer un plan de correction.'



def _sanitize_llm_limitations(limitations, suppress_invalid_json=False, suppress_followup=False):
    cleaned = []
    for limitation in limitations if isinstance(limitations, list) else []:
        text = str(limitation)
        lowered = text.lower()
        if suppress_followup and text == LLM_FOLLOWUP_REQUIRED_MESSAGE:
            continue
        if suppress_invalid_json and 'json' in lowered and ('invalide' in lowered or 'invalid' in lowered or 'non valide' in lowered):
            continue
        cleaned.append(limitation)
    return list(dict.fromkeys(cleaned))


def _is_llm_followup_trigger_issue(issue):
    if not isinstance(issue, dict):
        return False
    message = str(issue.get('message') or issue.get('explanation') or '')
    return bool(issue.get('internal_trigger')) or message == LLM_FOLLOWUP_REQUIRED_MESSAGE


def _normalize_preprocess_issue(issue):
    if not isinstance(issue, dict):
        return None
    normalized = dict(issue)
    message = str(normalized.get('message') or normalized.get('explanation') or '').strip()
    if message:
        normalized['message'] = message
    normalized.setdefault('type', 'generic_issue')
    normalized.setdefault('category', 'general')
    normalized.setdefault('severity', 'info')
    if 'ui_visible' not in normalized:
        normalized['ui_visible'] = not bool(normalized.get('internal_trigger'))
    return normalized


def _partition_preprocess_issues(issues):
    normalized_issues = []
    for issue in issues or []:
        normalized = _normalize_preprocess_issue(issue)
        if normalized is not None:
            normalized_issues.append(normalized)
    visible_issues = [issue for issue in normalized_issues if bool(issue.get('ui_visible', True))]
    internal_issues = [issue for issue in normalized_issues if not bool(issue.get('ui_visible', True))]
    # Single-source-of-truth invariant:
    # all_issues must always be the union of visible + internal issues.
    all_issues = [*visible_issues, *internal_issues]
    return all_issues, visible_issues, internal_issues


def _compute_llm_confidence_contract(llm_analysis, visible_issues, internal_issues):
    llm_analysis = llm_analysis if isinstance(llm_analysis, dict) else {}
    validation_status = llm_analysis.get('validation_status') if isinstance(llm_analysis.get('validation_status'), dict) else {}
    validation_status_pass2 = llm_analysis.get('validation_status_pass2') if isinstance(llm_analysis.get('validation_status_pass2'), dict) else {}
    second_pass = llm_analysis.get('second_pass') if isinstance(llm_analysis.get('second_pass'), dict) else {}

    confidence_candidates = []
    for key in ('domain_score', 'recovery_score', 'medical_confidence'):
        value = llm_analysis.get(key)
        if isinstance(value, (int, float)):
            confidence_candidates.append(float(value))
    quality_score = llm_analysis.get('quality_score')
    if isinstance(quality_score, (int, float)):
        confidence_candidates.append(max(0.0, min(1.0, float(quality_score) / 100.0)))

    if confidence_candidates:
        confidence_score = max(0.0, min(1.0, sum(confidence_candidates) / len(confidence_candidates)))
    else:
        confidence_score = 0.0

    if validation_status and not bool(validation_status.get('schema_valid', False)):
        confidence_score = min(confidence_score, 0.35)
    if second_pass.get('status') == 'failed':
        confidence_score = min(confidence_score, 0.35)
    if llm_analysis.get('unavailable'):
        confidence_score = min(confidence_score, 0.2)

    visible_count = len(visible_issues)
    internal_count = len(internal_issues)
    if confidence_score < 0.35 or visible_count > 0 or second_pass.get('status') == 'failed':
        risk_level = 'high'
    elif confidence_score < 0.7 or internal_count > 0:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    requires_review = (
        risk_level != 'low'
        or not bool(validation_status.get('schema_valid', False))
        or not bool(validation_status.get('merge_safe', False))
        or bool(validation_status_pass2 and validation_status_pass2.get('issues'))
    )

    return {
        'confidence_score': round(confidence_score, 3),
        'risk_level': risk_level,
        'requires_review': bool(requires_review),
    }


def _validate_svm_features_post_correction(corrected_df):
    """
    After all corrections are applied, verify that SVM prediction features
    are within valid bounds. Catches cases where the LLM introduced new errors.
    Returns a dict: {feature: issue_description} for any problematic feature.
    """
    problems = {}
    missing = []
    col_lower_map = {str(c).lower(): str(c) for c in corrected_df.columns}

    for feature, rule in _SVM_MORTALITE_FEATURES.items():
        actual_col = col_lower_map.get(feature.lower())
        if actual_col is None:
            missing.append(feature)
            continue

        series = corrected_df[actual_col]
        num_series = pd.to_numeric(series, errors='coerce').dropna()
        if num_series.empty:
            continue

        if rule == 'binary':
            invalid = num_series[~num_series.isin([0, 1, 0.0, 1.0])]
            if not invalid.empty:
                problems[feature] = (
                    f'colonne binaire contient valeurs invalides après correction: '
                    f'{invalid.head(3).tolist()} ({len(invalid)} ligne(s))'
                )
        else:
            rmin, rmax = rule
            below = num_series[num_series < rmin]
            above = num_series[num_series > rmax]
            msgs = []
            if not below.empty:
                msgs.append(f'{len(below)} valeur(s) < {rmin}: {below.head(2).tolist()}')
            if not above.empty:
                msgs.append(f'{len(above)} valeur(s) > {rmax}: {above.head(2).tolist()}')
            if msgs:
                problems[feature] = ' | '.join(msgs)

    return {'problems': problems, 'missing_features': missing}


def _build_preprocess_report(dataframe, technical_profile, llm_analysis=None, corrected_df=None, applied_actions=None):
    llm_analysis = llm_analysis or {}
    corrected_df = corrected_df if isinstance(corrected_df, pd.DataFrame) else dataframe
    applied_actions = applied_actions or []

    issues = llm_analysis.get('issues') if isinstance(llm_analysis, dict) else []
    if not isinstance(issues, list):
        issues = []
    issues = [
        issue for issue in issues
        if not _is_llm_followup_trigger_issue(issue)
    ]
    all_issues, visible_issues, internal_issues = _partition_preprocess_issues(issues)
    confidence_contract = _compute_llm_confidence_contract(llm_analysis, visible_issues, internal_issues)

    severity_count = {'critical': 0, 'warning': 0, 'info': 0}
    for item in visible_issues:
        severity = str(item.get('severity', 'info')).lower()
        severity_count[severity] = severity_count.get(severity, 0) + 1

    quality_score = llm_analysis.get('quality_score') if isinstance(llm_analysis, dict) else None
    if not isinstance(quality_score, (int, float)):
        # Base score from LLM issues
        raw_score = 100 - (severity_count.get('critical', 0) * 15) - (severity_count.get('warning', 0) * 6) - (severity_count.get('info', 0) * 2)
        # Add penalty from technical profile (missing values, duplicates, outliers)
        tp = technical_profile if isinstance(technical_profile, dict) else {}
        missing_pct = float(tp.get('missing_pct') or 0)
        duplicate_rows = int(tp.get('duplicate_rows') or 0)
        total_rows = max(1, int(tp.get('row_count') or len(dataframe.index)))
        total_cols = max(1, int(tp.get('columns') or len(dataframe.columns)))
        outlier_total = sum(
            int(c.get('outlier_count') or 0)
            for c in (tp.get('columns_with_issues') or tp.get('columns_profile') or [])
            if isinstance(c, dict)
        )
        type_error_cols = sum(
            1 for c in (tp.get('columns_with_issues') or [])
            if isinstance(c, dict) and c.get('type_issue')
        )
        raw_score -= missing_pct * 0.4
        raw_score -= min(20, (duplicate_rows / total_rows) * 100 * 0.5)
        raw_score -= min(10, outlier_total * 0.5)
        raw_score -= type_error_cols * 3

        # Penalty from applied corrections (Python pre-passes + LLM corrections)
        # A high ratio of corrected cells indicates poor original data quality
        if applied_actions is not None:
            total_cells = total_rows * total_cols
            corrected_cells = sum(
                int(a.get('cells_changed') or 0)
                for a in (applied_actions or [])
                if isinstance(a, dict)
            )
            correction_ratio = corrected_cells / total_cells if total_cells > 0 else 0
            # 0-1%: no penalty | 1-5%: -5 to -15 | 5-10%: -15 to -25 | >10%: -25 to -35
            raw_score -= min(35, correction_ratio * 250)

        quality_score = max(5, min(100, int(round(raw_score))))
    else:
        quality_score = max(0, min(100, int(round(float(quality_score)))))

    recommendations = []
    for recommendation in (llm_analysis.get('recommendations') or []):
        recommendation_text = str(recommendation)
        if recommendation_text not in recommendations:
            recommendations.append(recommendation_text)

    if not recommendations:
        recommendations.append('Aucune recommandation fournie par le modele.')

    corrected_preview_rows = _dataframe_to_rows(corrected_df.head(20))

    # Post-correction validation: SVM features must be clean
    svm_validation = _validate_svm_features_post_correction(corrected_df)
    svm_problems = svm_validation.get('problems') or {}
    svm_missing = svm_validation.get('missing_features') or []
    # Add SVM problems as critical issues in the report
    for feat, desc in svm_problems.items():
        visible_issues.append({
            'column': feat,
            'category': 'feature_prediction_invalide',
            'severity': 'critical',
            'explanation': (
                f'[ALERTE PRÉDICTION] La feature SVM "{feat}" est encore invalide après correction: '
                f'{desc}. Ce problème va fausser la prédiction de mortalité — correction manuelle requise.'
            ),
        })

    return {
        'summary': {
            'rows': int(len(dataframe.index)),
            'columns': int(len(dataframe.columns)),
            'quality_score': quality_score,
            'total_issues': len(visible_issues),
            'severity_count': severity_count,
            'corrected_rows': int(len(corrected_df.index)),
            'applied_corrections_count': len(applied_actions),
            'internal_issues_count': len(internal_issues),
        },
        'dataset_profile': technical_profile,
        'issues': visible_issues,
        'internal_issues': internal_issues,
        'all_issues': all_issues,
        'recommendations': recommendations,
        'correction_plan': llm_analysis.get('correction_plan') or {},
        'normalization_notes': (llm_analysis.get('normalization_notes') if isinstance(llm_analysis, dict) else []) or [],
        'normalization_severity_score': int((llm_analysis.get('normalization_severity_score') if isinstance(llm_analysis, dict) else 0) or 0),
        'applied_corrections': applied_actions,
        'svm_feature_validation': {
            'problems': svm_problems,
            'missing_features': svm_missing,
            'ok': not svm_problems and not svm_missing,
        },
        'llm_analysis': llm_analysis,
        'corrected_preview_rows': corrected_preview_rows,
        'llm_preview_rows': llm_analysis.get('corrected_preview_rows') if isinstance(llm_analysis, dict) else [],
        'analysis_pack': llm_analysis.get('analysis_pack') if isinstance(llm_analysis, dict) else None,
        'llm_internal_status': {
            'has_internal_warnings': len(internal_issues) > 0,
            'internal_issues_count': len(internal_issues),
            'llm_status': str(llm_analysis.get('llm_status') or 'ok') if isinstance(llm_analysis, dict) else 'ok',
            'second_pass': (llm_analysis.get('second_pass') if isinstance(llm_analysis, dict) else {}) or {},
            'validation_status': (llm_analysis.get('validation_status') if isinstance(llm_analysis, dict) else {}) or {},
            'validation_status_pass2': (llm_analysis.get('validation_status_pass2') if isinstance(llm_analysis, dict) else {}) or {},
            'normalization_notes': (llm_analysis.get('normalization_notes') if isinstance(llm_analysis, dict) else []) or [],
            'normalization_severity_score': int(llm_analysis.get('normalization_severity_score', 0)) if isinstance(llm_analysis, dict) else 0,
            'raw_response_present': bool(str(llm_analysis.get('raw_response') or '').strip()) if isinstance(llm_analysis, dict) else False,
            'raw_response_snippet': (str(llm_analysis.get('raw_response') or '')[:300] if isinstance(llm_analysis, dict) else ''),
            'raw_response_length': len(str(llm_analysis.get('raw_response') or '')) if isinstance(llm_analysis, dict) else 0,
            'confidence_contract': confidence_contract,
            # Guardrail: debug/internal metadata must never drive control flow.
            'control_flow_source': 'backend_orchestrator_only',
        },
    }


def _integrate_dataframe_into_patients(dataframe, request_user=None, source_file_name='preprocessed_dataset'):
    headers = list(dataframe.columns)
    template = upsert_template_from_headers(headers, None, source_file_name, create_fields=False)

    created_count = 0
    row_errors = []
    auto_increment_state = initialize_auto_increment_state()
    all_dynamic_columns = {}
    existing_template_keys = set(template.fields.values_list('key', flat=True)) if template else set()

    for header in headers:
        header_str = str(header).strip()
        if not header_str:
            continue
        normalized = normalize_header(header_str)
        if not normalized or normalized in existing_template_keys:
            continue
        if normalized in _COLUMNS_FUSED_INTO_COMORBIDITE_LISTE or normalized in COLUMN_MAPPING:
            continue
        all_dynamic_columns.setdefault(normalized, header_str)

    for index, row in dataframe.iterrows():
        payload = build_patient_payload(row)
        detected = payload.pop('_dynamic_columns_detected', set())
        for norm_key in detected:
            if norm_key not in all_dynamic_columns:
                original_name = next(
                    (str(h).strip() for h in headers if normalize_header(str(h).strip()) == norm_key),
                    norm_key,
                )
                all_dynamic_columns[norm_key] = original_name

        payload = apply_automatic_schema_fields(
            payload,
            auto_increment_state=auto_increment_state,
            current_user=request_user,
        )
        payload = ensure_required_identity_fields(payload)
        payload = ensure_incremental_identifiers(
            payload,
            auto_increment_state=auto_increment_state,
            force_generated=True,
        )

        serializer = PatientSerializer(data=payload)
        if serializer.is_valid():
            serializer.save()
            created_count += 1
        else:
            row_errors.append({'row': index + 2, 'errors': serializer.errors})

    dynamic_columns_info = []
    if all_dynamic_columns and template:
        existing_keys = set(template.fields.values_list('key', flat=True))
        new_fields = []
        for norm_key, original_name in all_dynamic_columns.items():
            if norm_key in existing_keys:
                template.fields.filter(key=norm_key).update(source_hint='dynamic_column')
            else:
                new_fields.append(
                    PatientFormField(
                        template=template,
                        key=norm_key,
                        label=original_name,
                        field_type='text_short',
                        order=10000 + len(new_fields),
                        choices=[],
                        source_hint='dynamic_column',
                        import_file=source_file_name or '',
                        is_required=False,
                    )
                )
            dynamic_columns_info.append({
                'key': norm_key,
                'label': original_name,
                'is_new': norm_key not in existing_keys,
            })

        if new_fields:
            PatientFormField.objects.bulk_create(new_fields)

    if created_count > 0 or all_dynamic_columns:
        try:
            refresh_postgres_flat_view(template)
        except Exception:
            pass

    template_data = PatientFormTemplateSerializer(template).data
    status_code = status.HTTP_201_CREATED if created_count else status.HTTP_200_OK
    return {
        'mode': 'data',
        'template': template_data,
        'fields_created': len(template_data.get('fields', [])),
        'patients_created': created_count,
        'errors': row_errors,
        'dynamic_columns': dynamic_columns_info,
        'dynamic_columns_count': len(dynamic_columns_info),
        'new_dynamic_columns_count': sum(1 for c in dynamic_columns_info if c.get('is_new')),
    }, status_code


# ============================================================
# VUES API
# ============================================================

class PatientListCreateView(APIView):
    permission_classes = [CanViewPatients]

    def get_queryset(self, request):
        queryset = Patient.objects.all()
        search = request.query_params.get('search', '').strip()
        id_patient = request.query_params.get('id_patient', '').strip()
        sexe = request.query_params.get('sexe', '').strip()
        age_min = request.query_params.get('age_min', '').strip()
        age_max = request.query_params.get('age_max', '').strip()
        date_naissance = request.query_params.get('date_naissance', '').strip()
        statut_inclusion = request.query_params.get('statut_inclusion', '').strip()
        infection = request.query_params.get('infection', '').strip().lower()
        hemorrhage = request.query_params.get('hemorrhage', '').strip().lower()
        avf_created = request.query_params.get('avf_created', '').strip().lower()

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(prenom__icontains=search) |
                Q(id_patient__icontains=search) | Q(maladie__icontains=search) |
                Q(telephone__icontains=search) | Q(adresse__icontains=search)
            )
        if id_patient:
            queryset = queryset.filter(id_patient__icontains=id_patient)
        if sexe:
            queryset = queryset.filter(sexe__iexact=sexe)
        if age_min:
            queryset = queryset.filter(age__gte=age_min)
        if age_max:
            queryset = queryset.filter(age__lte=age_max)
        if date_naissance:
            queryset = queryset.filter(date_naissance=date_naissance)
        if statut_inclusion:
            queryset = queryset.filter(statut_inclusion__icontains=statut_inclusion)

        return queryset

    def get(self, request):
        serializer = PatientSerializer(self.get_queryset(request), many=True)
        return Response(serializer.data)

    def post(self, request):
        before_data = None
        payload = request.data.copy()
        payload = apply_automatic_schema_fields(payload, current_user=request.user)
        payload = ensure_incremental_identifiers(payload)
        serializer = PatientSerializer(data=payload)
        if serializer.is_valid():
            patient = serializer.save()
            AuditLog.objects.create(
                utilisateur=request.user if request.user.is_authenticated else None,
                action=f"CREATION_PATIENT: patient {patient.id_patient or patient.id} cree",
                entite='Patient',
                entite_id=patient.id,
                adresse_ip=request.META.get('REMOTE_ADDR'),
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PatientExportExcelView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = 'patients'

        headers = [
            'id_patient', 'nom', 'prenom', 'age', 'sexe',
            'demographie_sexe', 'demographie_age_ans', 'demographie_date_naissance',
            'irc_etiologie_principale', 'dialyse_modalite_initiale', 'dialyse_date_debut',
            'devenir_statut', 'devenir_date_deces', 'devenir_cause_deces',
        ]
        worksheet.append(headers)

        for patient in Patient.objects.all():
            row = [
                patient.id_patient, patient.nom, patient.prenom, patient.age, patient.sexe,
                patient.demographie_sexe, patient.demographie_age_ans,
                patient.demographie_date_naissance,
                patient.irc_etiologie_principale, patient.dialyse_modalite_initiale,
                patient.dialyse_date_debut,
                patient.devenir_statut, patient.devenir_date_deces, patient.devenir_cause_deces,
            ]
            worksheet.append(row)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="patients_export.xlsx"'
        workbook.save(response)
        return response


class PatientDetailView(APIView):
    permission_classes = [CanViewPatients]

    def get_object(self, pk):
        return get_object_or_404(Patient, pk=pk)

    def get(self, request, pk):
        serializer = PatientSerializer(self.get_object(pk))
        return Response(serializer.data)

    def put(self, request, pk):
        patient = self.get_object(pk)
        before_data = PatientSerializer(patient).data
        serializer = PatientSerializer(patient, data=request.data, partial=True)
        if serializer.is_valid():
            updated_patient = serializer.save()
            after_data = PatientSerializer(updated_patient).data
            AuditLog.objects.create(
                utilisateur=request.user if request.user.is_authenticated else None,
                action=f"MODIFICATION_PATIENT: {_describe_patient_changes(before_data, after_data)}",
                entite='Patient',
                entite_id=updated_patient.id,
                adresse_ip=request.META.get('REMOTE_ADDR'),
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        patient = self.get_object(pk)
        before_data = PatientSerializer(patient).data
        serializer = PatientSerializer(patient, data=request.data, partial=True)
        if serializer.is_valid():
            updated_patient = serializer.save()
            after_data = PatientSerializer(updated_patient).data
            AuditLog.objects.create(
                utilisateur=request.user if request.user.is_authenticated else None,
                action=f"MODIFICATION_PATIENT: {_describe_patient_changes(before_data, after_data)}",
                entite='Patient',
                entite_id=updated_patient.id,
                adresse_ip=request.META.get('REMOTE_ADDR'),
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        patient = self.get_object(pk)
        AuditLog.objects.create(
            utilisateur=request.user if request.user.is_authenticated else None,
            action=f"SUPPRESSION_PATIENT: patient {patient.id_patient or patient.id} supprime",
            entite='Patient',
            entite_id=patient.id,
            adresse_ip=request.META.get('REMOTE_ADDR'),
        )
        patient.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PatientBulkPurgeView(APIView):
    permission_classes = [IsAdminOrChefService]

    def delete(self, request):
        deleted_count, _ = Patient.objects.all().delete()

        # After all patients are gone, remove dynamic columns that no longer
        # have any data behind them (all extra_data keys are now absent).
        removed_keys = []
        try:
            template = get_active_template()
            if template:
                dynamic_fields = template.fields.filter(
                    source_hint__in=['dynamic_column', 'auto_detected_from_data_import']
                )
                removed_keys = list(dynamic_fields.values_list('key', flat=True))
                if removed_keys:
                    dynamic_fields.delete()
                    try:
                        refresh_postgres_flat_view(template)
                    except Exception:
                        pass
        except Exception:
            pass

        return Response({
            'deleted_count': deleted_count,
            'dynamic_columns_removed': len(removed_keys),
            'removed_keys': removed_keys,
        }, status=status.HTTP_200_OK)


class DynamicColumnRequestView(APIView):
    """
    POST   /patients/dynamic-columns/requests/          → soumettre une demande (tous rôles)
    GET    /patients/dynamic-columns/requests/          → lister les demandes (chef/admin)
    POST   /patients/dynamic-columns/requests/<id>/     → approuver ou rejeter (chef/admin)
    GET    /patients/dynamic-columns/requests/pending-count/ → badge compteur
    """
    permission_classes = [CanViewPatients]

    def get(self, request, request_id=None):
        from .models import DynamicColumnRequest
        from django.utils import timezone as tz

        role_name = str(getattr(getattr(request.user, 'role', None), 'nom', '') or '')

        # Badge compteur — accessible à tous les chefs/admins
        if request.query_params.get('count') == '1':
            if role_name not in ('super_admin', 'chef_service'):
                return Response({'pending': 0})
            return Response({'pending': DynamicColumnRequest.objects.filter(status='pending').count()})

        if role_name not in ('super_admin', 'chef_service'):
            return Response({'error': 'Accès réservé.'}, status=status.HTTP_403_FORBIDDEN)

        qs = DynamicColumnRequest.objects.select_related('submitted_by', 'reviewed_by')
        filter_status = request.query_params.get('status', 'pending')
        if filter_status != 'all':
            qs = qs.filter(status=filter_status)

        data = []
        for r in qs[:100]:
            data.append({
                'id': r.id,
                'action': r.action,
                'column_key': r.column_key,
                'column_label': r.column_label,
                'field_type': r.field_type,
                'submitted_by': str(getattr(r.submitted_by, 'username', '') or ''),
                'submitted_at': r.submitted_at.isoformat() if r.submitted_at else None,
                'status': r.status,
                'reviewed_by': str(getattr(r.reviewed_by, 'username', '') or ''),
                'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else None,
                'comment': r.comment,
            })
        return Response({'results': data, 'count': len(data)})

    def post(self, request, request_id=None):
        from .models import DynamicColumnRequest
        from django.utils import timezone as tz

        role_name = str(getattr(getattr(request.user, 'role', None), 'nom', '') or '')

        # Approuver / Rejeter
        if request_id is not None:
            if role_name not in ('super_admin', 'chef_service'):
                return Response({'error': 'Accès réservé.'}, status=status.HTTP_403_FORBIDDEN)
            try:
                col_req = DynamicColumnRequest.objects.get(pk=request_id)
            except DynamicColumnRequest.DoesNotExist:
                return Response({'error': 'Demande introuvable.'}, status=status.HTTP_404_NOT_FOUND)
            if col_req.status != 'pending':
                return Response({'error': 'Demande déjà traitée.'}, status=status.HTTP_400_BAD_REQUEST)

            action = str(request.data.get('action', ''))
            comment = str(request.data.get('comment', ''))

            if action == 'approve':
                # Appliquer l'action réelle
                template = get_active_template()
                if col_req.action == 'add':
                    if template and not template.fields.filter(key=col_req.column_key).exists():
                        PatientFormField.objects.create(
                            template=template,
                            key=col_req.column_key,
                            label=col_req.column_label or col_req.column_key,
                            field_type=col_req.field_type,
                            order=10000,
                            choices=[],
                            source_hint='dynamic_column',
                            import_file='manuel',
                            is_required=False,
                        )
                        try:
                            refresh_postgres_flat_view(template)
                        except Exception:
                            pass
                elif col_req.action == 'delete':
                    if template:
                        field = template.fields.filter(key=col_req.column_key).first()
                        if field:
                            for patient in Patient.objects.filter(extra_data__has_key=col_req.column_key):
                                patient.extra_data.pop(col_req.column_key, None)
                                patient.save(update_fields=['extra_data'])
                            field.delete()
                            try:
                                refresh_postgres_flat_view(template)
                            except Exception:
                                pass
                col_req.status = 'approved'
            elif action == 'reject':
                col_req.status = 'rejected'
            else:
                return Response({'error': 'action doit être "approve" ou "reject".'}, status=status.HTTP_400_BAD_REQUEST)

            col_req.reviewed_by = request.user
            col_req.reviewed_at = tz.now()
            col_req.comment = comment
            col_req.save()
            return Response({'id': col_req.id, 'status': col_req.status})

        # Soumettre une nouvelle demande
        action = str(request.data.get('action', ''))
        column_key = normalize_header(str(request.data.get('column_key', '')).strip())
        column_label = str(request.data.get('column_label', '')).strip()
        field_type = str(request.data.get('field_type', 'text_short'))

        if action not in ('add', 'delete'):
            return Response({'error': 'action doit être "add" ou "delete".'}, status=status.HTTP_400_BAD_REQUEST)
        if not column_key:
            return Response({'error': 'column_key est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        # Empêcher les doublons de demandes en attente
        if DynamicColumnRequest.objects.filter(
            action=action, column_key=column_key, status='pending'
        ).exists():
            return Response({'error': 'Une demande identique est déjà en attente.'}, status=status.HTTP_400_BAD_REQUEST)

        col_req = DynamicColumnRequest.objects.create(
            action=action,
            column_key=column_key,
            column_label=column_label,
            field_type=field_type,
            submitted_by=request.user,
        )
        return Response({
            'id': col_req.id,
            'status': col_req.status,
            'message': f'Demande soumise. En attente de validation par le chef de service.',
        }, status=status.HTTP_201_CREATED)


class PatientDynamicColumnManageView(APIView):
    """
    POST   /patients/dynamic-columns/        → créer une colonne dynamique manuelle
    DELETE /patients/dynamic-columns/<key>/  → supprimer une colonne + effacer ses données
    """
    permission_classes = [IsAdminOrChefService]

    def post(self, request):
        raw_key = str(request.data.get('key', '')).strip()
        label    = str(request.data.get('label', '')).strip()
        field_type = str(request.data.get('field_type', 'text_short'))

        key = normalize_header(raw_key)
        if not key:
            return Response({'error': 'Le nom de la colonne est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        template = get_active_template()
        if not template:
            return Response({'error': 'Aucun template actif.'}, status=status.HTTP_404_NOT_FOUND)

        if template.fields.filter(key=key).exists():
            return Response({'error': f'La colonne "{key}" existe déjà.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed_types = {'text_short', 'text_long', 'integer', 'decimal', 'boolean', 'date', 'single_choice'}
        if field_type not in allowed_types:
            field_type = 'text_short'

        field = PatientFormField.objects.create(
            template=template,
            key=key,
            label=label or raw_key,
            field_type=field_type,
            order=10000,
            choices=[],
            source_hint='dynamic_column',
            import_file='manuel',
            is_required=False,
        )
        try:
            refresh_postgres_flat_view(template)
        except Exception:
            pass

        return Response({
            'id': field.id,
            'key': field.key,
            'label': field.label,
            'field_type': field.field_type,
            'source_hint': field.source_hint,
            'import_file': field.import_file,
        }, status=status.HTTP_201_CREATED)

    def delete(self, request, key):
        template = get_active_template()
        if not template:
            return Response({'error': 'Aucun template actif.'}, status=status.HTTP_404_NOT_FOUND)

        field = template.fields.filter(
            key=key,
            source_hint__in=['dynamic_column', 'auto_detected_from_data_import'],
        ).first()
        if not field:
            return Response({'error': f'Colonne dynamique "{key}" introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        # Effacer la valeur de cette colonne dans tous les extra_data patients
        patients_updated = 0
        for patient in Patient.objects.filter(extra_data__has_key=key):
            patient.extra_data.pop(key, None)
            patient.save(update_fields=['extra_data'])
            patients_updated += 1

        field.delete()
        try:
            refresh_postgres_flat_view(template)
        except Exception:
            pass

        return Response({'deleted': key, 'patients_updated': patients_updated})


class PatientDynamicColumnsCleanupView(APIView):
    permission_classes = [IsAdminOrChefService]

    def post(self, request):
        template = get_active_template()
        if not template:
            return Response(
                {
                    'template_found': False,
                    'removed_count': 0,
                    'removed_keys': [],
                },
                status=status.HTTP_200_OK,
            )

        dynamic_fields = template.fields.filter(
            source_hint__in=['dynamic_column', 'auto_detected_from_data_import']
        )
        if not dynamic_fields.exists():
            return Response(
                {
                    'template_found': True,
                    'removed_count': 0,
                    'removed_keys': [],
                },
                status=status.HTTP_200_OK,
            )

        used_extra_keys = set()
        for extra_payload in Patient.objects.values_list('extra_data', flat=True):
            if isinstance(extra_payload, dict):
                used_extra_keys.update(extra_payload.keys())

        stale_fields_qs = dynamic_fields.exclude(key__in=used_extra_keys)
        removed_keys = list(stale_fields_qs.values_list('key', flat=True))
        removed_count = len(removed_keys)
        if removed_count > 0:
            stale_fields_qs.delete()
            try:
                refresh_postgres_flat_view(template)
            except Exception:
                pass

        return Response(
            {
                'template_found': True,
                'removed_count': removed_count,
                'removed_keys': removed_keys,
            },
            status=status.HTTP_200_OK,
        )


class PatientPreprocessAnalyzeView(APIView):
    permission_classes = [CanViewPatients]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        from patients.tasks import analyze_preprocess_async
        import tempfile

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'Fichier CSV/Excel requis.'}, status=status.HTTP_400_BAD_REQUEST)

        # Créer un ID unique pour cette session
        session_id = uuid.uuid4().hex
        source_file_name = uploaded_file.name

        # Sauvegarder le fichier temporairement
        try:
            temp_dir = '/tmp/preprocess'
            os.makedirs(temp_dir, exist_ok=True)
            temp_file_path = os.path.join(temp_dir, f'{session_id}_{source_file_name}')
            with open(temp_file_path, 'wb') as temp_file:
                for chunk in uploaded_file.chunks():
                    temp_file.write(chunk)
        except Exception as error:
            return Response({'error': f'Erreur lors de la sauvegarde du fichier: {error}'}, status=status.HTTP_400_BAD_REQUEST)

        # Initialiser la session avec statut "pending"
        session = {
            'id': session_id,
            'created_at': timezone.now().isoformat(),
            'created_by': resolve_entry_user_label(request.user),
            'source_file_name': source_file_name,
            'columns': [],
            'original_rows': [],
            'corrected_rows': [],
            'report': {},
            'change_log': [],
            'status': 'pending',
            'error': None,
            'progress_message': 'Initialisation du traitement...',
            'event_log': [],
        }
        _append_preprocess_event(
            session,
            event_type='analysis_requested',
            event_data={
                'status': 'pending',
                'source_file_name': source_file_name,
                'use_llm': str(request.data.get('use_llm', 'true')).lower() not in ['0', 'false', 'no', 'non'],
            },
        )
        _save_preprocess_session(session)

        # Dispatcher la task Celery de manière asynchrone
        try:
            task_result = analyze_preprocess_async.delay(
                session_id=session_id,
                file_path=temp_file_path,
                user_id=request.user.id,
                use_llm=str(request.data.get('use_llm', 'true')).lower() not in ['0', 'false', 'no', 'non']
            )
            queued_session = _load_preprocess_session(session_id) or session
            queued_session['celery_task_id'] = task_result.id
            _append_preprocess_event(
                queued_session,
                event_type='analysis_dispatched',
                event_data={'status': 'pending'},
            )
            _save_preprocess_session(queued_session)
        except Exception as error:
            print(f"Erreur lors du lancement de la task Celery: {error}")
            session['status'] = 'error'
            session['error'] = f'Erreur Celery: {error}'
            _save_preprocess_session(session)
            return Response({'error': f'Erreur lors du lancement du traitement: {error}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                'preprocess_id': session_id,
                'status': 'pending',
                'message': 'Analyse en cours... Veuillez vérifier le statut.',
                'source_file_name': source_file_name,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PatientPreprocessStatusView(APIView):
    """Track the status of an ongoing preprocessing job."""
    permission_classes = [CanViewPatients]

    def get(self, request, preprocess_id):
        try:
            session = _load_preprocess_session(preprocess_id)
        except Exception:
            return Response({'error': 'Session non trouvée.'}, status=status.HTTP_404_NOT_FOUND)

        if session is None:
            return Response({'error': 'Session non trouvée.'}, status=status.HTTP_404_NOT_FOUND)

        if session.get('status') == 'completed':
            report = session.get('report', {})
            llm_internal_status = report.get('llm_internal_status', {}) if isinstance(report, dict) else {}
            return Response(
                {
                    'preprocess_id': preprocess_id,
                    'status': 'completed',
                    'report': report,
                    'columns': session.get('columns', []),
                    'row_count': len(session.get('corrected_rows', [])),
                    'original_preview_rows': session.get('original_rows', [])[:20],
                    'preview_rows': session.get('corrected_rows', [])[:20],
                    'corrected_preview_rows': report.get('corrected_preview_rows', [])[:20],
                    'dataset_profile': {'columns': len(session.get('columns', [])), 'rows': len(session.get('corrected_rows', []))},
                    'source_file_name': session.get('source_file_name'),
                    'llm_internal_status': llm_internal_status,
                    'event_log_tail': (session.get('event_log') or [])[-20:],
                },
                status=status.HTTP_200_OK,
            )
        elif session.get('status') == 'error':
            return Response(
                {
                    'preprocess_id': preprocess_id,
                    'status': 'error',
                    'error': session.get('error', 'Erreur inconnue'),
                    'message': f"Erreur lors de l'analyse: {session.get('error')}",
                },
                status=status.HTTP_200_OK,
            )
        else:  # pending or in_progress
            # Detect stale sessions: if updated_at > PREPROCESS_TIMEOUT_MINUTES ago, mark as error
            try:
                timeout_minutes = int(os.environ.get('PREPROCESS_TIMEOUT_MINUTES', '30'))
                updated_at_str = session.get('updated_at') or session.get('created_at')
                if updated_at_str:
                    from django.utils.dateparse import parse_datetime
                    updated_at = parse_datetime(updated_at_str)
                    if updated_at and (timezone.now() - updated_at).total_seconds() > timeout_minutes * 60:
                        return Response(
                            {
                                'preprocess_id': preprocess_id,
                                'status': 'error',
                                'error': 'Le worker a été interrompu (redémarrage ou timeout). Veuillez relancer l\'analyse.',
                                'message': 'Analyse interrompue — relancez le fichier.',
                            },
                            status=status.HTTP_200_OK,
                        )
            except Exception:
                pass
            return Response(
                {
                    'preprocess_id': preprocess_id,
                    'status': session.get('status', 'pending'),
                    'progress_message': session.get('progress_message', 'Traitement en cours...'),
                    'message': 'Analyse en cours, veuillez patienter...',
                    'event_log_tail': (session.get('event_log') or [])[-20:],
                },
                status=status.HTTP_200_OK,
            )


class PatientPreprocessHealthView(APIView):
    # Allow unauthenticated access so the UI can display Ollama status before login
    permission_classes = [AllowAny]

    def get(self, request):
        timeout_seconds = int(os.environ.get('OLLAMA_HEALTH_TIMEOUT_SECONDS', '8'))
        health = _check_ollama_health(timeout_seconds=timeout_seconds)
        model_name = os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b-instruct')
        if health.get('connected'):
            return Response(
                {
                    'connected': True,
                    'configured_model': model_name,
                    'base_url': health.get('base_url'),
                    'endpoint': health.get('endpoint'),
                    'models_count': health.get('models_count', 0),
                    'models': health.get('models', []),
                    'message': 'Ollama connecté.',
                },
                status=status.HTTP_200_OK,
            )

        errors = health.get('errors') or []
        return Response(
            {
                'connected': False,
                'configured_model': model_name,
                'base_url': None,
                'endpoint': None,
                'models_count': 0,
                'models': [],
                'message': 'Ollama indisponible depuis le backend.',
                'errors': errors,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class PatientPreprocessMetricsTimelineView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request):
        try:
            window_days = max(1, int(request.query_params.get('days', '30')))
        except Exception:
            window_days = 30

        now = timezone.now()
        window_start = now - timedelta(days=window_days)

        timeline = {}
        totals = {
            'sessions_count': 0,
            'completed_count': 0,
            'error_count': 0,
            'pending_count': 0,
            'pass2_required_count': 0,
            'pass2_failed_count': 0,
            'visible_issues_total': 0,
            'internal_issues_total': 0,
        }

        for session in _iter_preprocess_sessions():
            created_at_raw = session.get('created_at')
            created_at = parse_datetime(created_at_raw) if isinstance(created_at_raw, str) else None
            if created_at is None:
                continue
            if timezone.is_naive(created_at):
                created_at = timezone.make_aware(created_at, timezone.get_current_timezone())
            if created_at < window_start:
                continue

            day_key = created_at.date().isoformat()
            bucket = timeline.setdefault(
                day_key,
                {
                    'date': day_key,
                    'sessions_count': 0,
                    'completed_count': 0,
                    'error_count': 0,
                    'pending_count': 0,
                    'pass2_required_count': 0,
                    'pass2_failed_count': 0,
                    'visible_issues_total': 0,
                    'internal_issues_total': 0,
                    'confidence_score_sum': 0.0,
                    'confidence_score_count': 0,
                    'risk_low_count': 0,
                    'risk_medium_count': 0,
                    'risk_high_count': 0,
                    'events_count': 0,
                },
            )

            totals['sessions_count'] += 1
            bucket['sessions_count'] += 1

            session_status = str(session.get('status') or 'pending').lower()
            if session_status == 'completed':
                totals['completed_count'] += 1
                bucket['completed_count'] += 1
            elif session_status == 'error':
                totals['error_count'] += 1
                bucket['error_count'] += 1
            else:
                totals['pending_count'] += 1
                bucket['pending_count'] += 1

            report = session.get('report') if isinstance(session.get('report'), dict) else {}
            summary = report.get('summary') if isinstance(report.get('summary'), dict) else {}
            llm_internal = report.get('llm_internal_status') if isinstance(report.get('llm_internal_status'), dict) else {}
            confidence_contract = llm_internal.get('confidence_contract') if isinstance(llm_internal.get('confidence_contract'), dict) else {}

            visible_issues_count = int(summary.get('total_issues') or 0)
            internal_issues_count = int(summary.get('internal_issues_count') or 0)
            totals['visible_issues_total'] += visible_issues_count
            totals['internal_issues_total'] += internal_issues_count
            bucket['visible_issues_total'] += visible_issues_count
            bucket['internal_issues_total'] += internal_issues_count

            second_pass = llm_internal.get('second_pass') if isinstance(llm_internal.get('second_pass'), dict) else {}
            second_pass_status = str(second_pass.get('status') or '').lower()
            if second_pass_status in {'completed', 'failed'}:
                totals['pass2_required_count'] += 1
                bucket['pass2_required_count'] += 1
            if second_pass_status == 'failed':
                totals['pass2_failed_count'] += 1
                bucket['pass2_failed_count'] += 1

            confidence_score = confidence_contract.get('confidence_score')
            if isinstance(confidence_score, (int, float)):
                bucket['confidence_score_sum'] += float(confidence_score)
                bucket['confidence_score_count'] += 1

            risk_level = str(confidence_contract.get('risk_level') or '').lower()
            if risk_level == 'low':
                bucket['risk_low_count'] += 1
            elif risk_level == 'medium':
                bucket['risk_medium_count'] += 1
            elif risk_level == 'high':
                bucket['risk_high_count'] += 1

            events = session.get('event_log')
            if isinstance(events, list):
                bucket['events_count'] += len(events)

        timeline_points = []
        for day_key in sorted(timeline.keys()):
            point = timeline[day_key]
            if point['confidence_score_count'] > 0:
                point['confidence_score_avg'] = round(point['confidence_score_sum'] / point['confidence_score_count'], 4)
            else:
                point['confidence_score_avg'] = None
            point.pop('confidence_score_sum', None)
            point.pop('confidence_score_count', None)
            timeline_points.append(point)

        return Response(
            {
                'window_days': window_days,
                'window_start': window_start.isoformat(),
                'window_end': now.isoformat(),
                'totals': totals,
                'timeline': timeline_points,
                'governance': {
                    'control_metric_policy': 'No metric should influence decision flow unless explicitly declared as control metric.',
                    'confidence_contract_policy': 'confidence_score is NOT a correctness guarantee and must not be used alone for clinical decisions.',
                },
            },
            status=status.HTTP_200_OK,
        )


class PatientPreprocessSessionView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                'preprocess_id': session.get('id'),
                'source_file_name': session.get('source_file_name'),
                'report': session.get('report', {}),
                'columns': session.get('columns', []),
                'row_count': len(session.get('corrected_rows', [])),
                'preview_rows': session.get('corrected_rows', [])[:50],
                'change_log': session.get('change_log', [])[-20:],
                'event_log_tail': (session.get('event_log') or [])[-50:],
            },
            status=status.HTTP_200_OK,
        )


class PatientPreprocessRowsView(APIView):
    permission_classes = [CanViewPatients]

    def post(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        row_payload = request.data.get('row') or {}
        columns = session.get('columns', [])
        row = {column: row_payload.get(column) for column in columns}

        for key, value in row_payload.items():
            if key not in row:
                row[key] = value
                if key not in columns:
                    columns.append(key)

        session.setdefault('corrected_rows', []).append(row)
        session['columns'] = columns
        session.setdefault('change_log', []).append(
            {
                'timestamp': timezone.now().isoformat(),
                'user': resolve_entry_user_label(request.user),
                'action': 'create_row',
                'row_index': len(session['corrected_rows']) - 1,
            }
        )
        _save_preprocess_session(session)
        return Response({'row_count': len(session['corrected_rows'])}, status=status.HTTP_200_OK)


class PatientPreprocessRowDetailView(APIView):
    permission_classes = [CanViewPatients]

    def patch(self, request, session_id, row_index):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        rows = session.get('corrected_rows', [])
        if row_index < 0 or row_index >= len(rows):
            return Response({'error': 'Index de ligne invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        row_payload = request.data.get('row') or {}
        current_row = rows[row_index]
        for key, value in row_payload.items():
            current_row[key] = value
            if key not in session.get('columns', []):
                session['columns'].append(key)

        session.setdefault('change_log', []).append(
            {
                'timestamp': timezone.now().isoformat(),
                'user': resolve_entry_user_label(request.user),
                'action': 'update_row',
                'row_index': row_index,
            }
        )
        _save_preprocess_session(session)
        return Response({'row': current_row}, status=status.HTTP_200_OK)

    def delete(self, request, session_id, row_index):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        rows = session.get('corrected_rows', [])
        if row_index < 0 or row_index >= len(rows):
            return Response({'error': 'Index de ligne invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        rows.pop(row_index)
        session.setdefault('change_log', []).append(
            {
                'timestamp': timezone.now().isoformat(),
                'user': resolve_entry_user_label(request.user),
                'action': 'delete_row',
                'row_index': row_index,
            }
        )
        _save_preprocess_session(session)
        return Response({'row_count': len(rows)}, status=status.HTTP_200_OK)


class PatientPreprocessExportView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request, session_id):
        from openpyxl.styles import PatternFill, Font, Alignment
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        source = str(request.query_params.get('source', 'corrected')).lower()
        original_rows = session.get('original_rows', [])
        rows_key = 'original_rows' if source == 'original' else 'corrected_rows'
        rows = session.get(rows_key, [])
        columns = session.get('columns', [])
        dataframe = _rows_to_dataframe(rows, columns=columns)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            dataframe.to_excel(writer, index=False, sheet_name='Données')

            ws = writer.sheets['Données']

            # Style header row
            header_fill = PatternFill(start_color='0A2B3E', end_color='0A2B3E', fill_type='solid')
            header_font = Font(bold=True, color='FFFFFF', size=10)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # Highlight changed cells (corrected version only)
            if source == 'corrected' and original_rows:
                corrected_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
                corrected_font = Font(bold=True, color='B45309', size=10)
                orig_df = _rows_to_dataframe(original_rows, columns=columns)
                cols_list = list(dataframe.columns)
                for row_idx in range(len(dataframe)):
                    for col_idx, col in enumerate(cols_list):
                        if col in orig_df.columns and row_idx < len(orig_df):
                            orig_val = orig_df.iloc[row_idx][col]
                            new_val = dataframe.iloc[row_idx][col]
                            if str(orig_val) != str(new_val):
                                cell = ws.cell(row=row_idx + 2, column=col_idx + 1)
                                cell.fill = corrected_fill
                                cell.font = corrected_font

            # Add a second sheet: corrections summary
            report = session.get('report', {})
            issues = report.get('all_issues') or report.get('issues') or []
            issue_by_col = {i.get('column'): i for i in issues if i.get('column')}

            if source == 'corrected' and original_rows:
                ws2 = writer.book.create_sheet('Corrections')
                headers2 = ['N° Ligne', 'ID Patient', 'Colonne', 'Valeur originale', 'Valeur corrigée', 'Type', 'Justification']
                ws2.append(headers2)
                for cell in ws2[1]:
                    cell.fill = header_fill
                    cell.font = header_font

                id_col = next(
                    (k for k in (original_rows[0].keys() if original_rows else [])
                     if any(kw in str(k).lower() for kw in ('id', 'identifiant', 'patient'))),
                    None,
                )
                orig_df2 = _rows_to_dataframe(original_rows, columns=columns)
                cols_list2 = list(dataframe.columns)
                for row_idx in range(len(dataframe)):
                    for col in cols_list2:
                        if col in orig_df2.columns and row_idx < len(orig_df2):
                            orig_val = orig_df2.iloc[row_idx][col]
                            new_val = dataframe.iloc[row_idx][col]
                            if str(orig_val) != str(new_val):
                                issue = issue_by_col.get(col, {})
                                patient_id = original_rows[row_idx].get(id_col, '') if id_col and row_idx < len(original_rows) else ''
                                ws2.append([
                                    row_idx + 1,
                                    patient_id,
                                    col,
                                    orig_val,
                                    new_val,
                                    issue.get('category') or issue.get('type') or 'correction',
                                    issue.get('explanation') or 'Correction automatique',
                                ])
                                cell_new = ws2.cell(row=ws2.max_row, column=5)
                                cell_new.fill = corrected_fill
                                cell_new.font = corrected_font

        buffer.seek(0)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="preprocess_{session_id}_{source}.xlsx"'
        return response


class PatientPreprocessCellCorrectionsView(APIView):
    """Return per-cell diff between original and corrected rows with justifications."""
    permission_classes = [CanViewPatients]

    def get(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        original_rows = session.get('original_rows', [])
        corrected_rows = session.get('corrected_rows', original_rows)
        report = session.get('report', {})

        issues = report.get('all_issues') or report.get('issues') or []
        issue_by_col = {}
        for issue in issues:
            col = issue.get('column')
            if col and col not in issue_by_col:
                issue_by_col[col] = issue

        # Build correction lookups from applied_corrections action details.
        justification_by_col = {}
        action_details_by_col = {}
        for action in (report.get('applied_corrections') or []):
            action_name = action.get('action') or 'correction'
            for col_detail in (action.get('details', {}).get('columns') or []):
                if not isinstance(col_detail, dict):
                    continue
                col_name = col_detail.get('column') or col_detail.get('from') or col_detail.get('name') or ''
                justif = col_detail.get('justification', '')
                if col_name and justif and col_name not in justification_by_col:
                    justification_by_col[col_name] = justif
                if col_name:
                    action_details_by_col.setdefault(col_name, []).append({
                        'action': action_name,
                        **col_detail,
                    })

        def _is_missing_value(value):
            if value is None:
                return True
            try:
                return bool(pd.isna(value))
            except Exception:
                return False

        def _normalize_decimal_text(value):
            if isinstance(value, str):
                stripped = value.strip()
                if re.match(r'^-?\d[\d\s]*,\d+$', stripped):
                    return stripped.replace(' ', '').replace(',', '.')
            return value

        def _coerce_float(value):
            if _is_missing_value(value):
                return None
            try:
                return float(str(_normalize_decimal_text(value)).strip())
            except (ValueError, TypeError):
                return None

        def _values_match(left, right):
            if _is_missing_value(left) and _is_missing_value(right):
                return True
            left_num = _coerce_float(left)
            right_num = _coerce_float(right)
            if left_num is not None and right_num is not None:
                return abs(left_num - right_num) < 1e-9
            return str(left).strip() == str(right).strip()

        def _match_mapping_detail(col, old_val, new_val):
            for detail in action_details_by_col.get(col, []):
                mapping = detail.get('mapping') or detail.get('corrections') or {}
                if not isinstance(mapping, dict):
                    continue
                for source, target in mapping.items():
                    if _values_match(source, old_val) and _values_match(target, new_val):
                        return detail
                    if _values_match(source, old_val) and _is_missing_value(target):
                        return detail
            return None

        def _infer_cell_type(col, old_val, new_val, issue):
            matched_detail = _match_mapping_detail(col, old_val, new_val)
            if matched_detail:
                return matched_detail.get('action') or issue.get('category') or 'correction'
            old_text = str(old_val).strip() if old_val is not None else ''
            if old_text in {'x', 'X', 'xx', 'XX', '*'}:
                return 'valeur_invalide_x'
            if isinstance(old_val, str) and re.match(r'^-?\d[\d\s]*,\d+$', old_val.strip()):
                return 'separateur_decimal'
            if _is_missing_value(old_val) and not _is_missing_value(new_val):
                return 'knn_imputation'
            if _values_match(old_val, new_val) and str(old_val).strip() != str(new_val).strip():
                return 'normalisation_type'
            if col in justification_by_col:
                details = action_details_by_col.get(col) or []
                return (details[0].get('action') if details else None) or issue.get('category') or 'correction'
            return issue.get('category') or issue.get('type') or 'correction'

        def _infer_cell_justification(col, old_val, new_val, issue):
            matched_detail = _match_mapping_detail(col, old_val, new_val)
            if matched_detail:
                return (
                    matched_detail.get('justification')
                    or matched_detail.get('explanation')
                    or f'Correction automatique appliquee: {old_val} -> {new_val}.'
                )

            old_text = str(old_val).strip() if old_val is not None else ''
            if old_text in {'x', 'X', 'xx', 'XX', '*'}:
                return (
                    f'Valeur "{old_text}" invalide pour cette colonne numerique/binaire: '
                    'elle a ete retiree puis estimee par KNN a partir des patients similaires.'
                )

            if isinstance(old_val, str) and re.match(r'^-?\d[\d\s]*,\d+$', old_val.strip()):
                return (
                    'Separateur decimal francais detecte: la virgule a ete remplacee '
                    'par un point, sans modification clinique de la valeur.'
                )

            if _is_missing_value(old_val) and not _is_missing_value(new_val):
                return (
                    'Valeur manquante estimee par imputation KNN '
                    'a partir des variables disponibles chez les patients similaires.'
                )

            if _values_match(old_val, new_val) and str(old_val).strip() != str(new_val).strip():
                return (
                    'Format numerique normalise: la valeur clinique est conservee, '
                    'seul le typage a ete corrige pour permettre l analyse.'
                )

            action_justification = justification_by_col.get(col)
            if action_justification:
                return action_justification
            return issue.get('explanation') or 'Correction automatique.'

        id_col = next(
            (k for k in (original_rows[0].keys() if original_rows else [])
             if any(kw in str(k).lower() for kw in ('id', 'identifiant', 'patient'))),
            None,
        )

        cell_corrections = []
        for row_idx, (orig_row, corr_row) in enumerate(zip(original_rows, corrected_rows)):
            for col in orig_row:
                old_val = orig_row.get(col)
                new_val = corr_row.get(col)
                if old_val is None and new_val is None:
                    continue
                if str(old_val) != str(new_val):
                    issue = issue_by_col.get(col, {})
                    cell_corrections.append({
                        'row': row_idx + 1,
                        'patient_id': orig_row.get(id_col, row_idx + 1) if id_col else row_idx + 1,
                        'column': col,
                        'old_value': old_val,
                        'new_value': new_val,
                        'type': _infer_cell_type(col, old_val, new_val, issue),
                        'severity': issue.get('severity') or 'warning',
                        'justification': _infer_cell_justification(col, old_val, new_val, issue),
                    })

        # Also include flagged issues (no correction applied) that aren't in cell_corrections
        corrected_cols = {c['column'] for c in cell_corrections}
        flagged = []
        for issue in issues:
            col = issue.get('column')
            if col and col not in corrected_cols:
                flagged.append({
                    'row': None,
                    'patient_id': None,
                    'column': col,
                    'old_value': None,
                    'new_value': None,
                    'type': issue.get('category') or 'anomalie',
                    'severity': issue.get('severity') or 'warning',
                    'justification': issue.get('explanation') or justification_by_col.get(col) or '—',
                    'flagged_only': True,
                })

        return Response({
            'total_corrections': len(cell_corrections),
            'total_flagged': len(flagged),
            'corrections': cell_corrections,
            'flagged': flagged,
        })


class PatientPreprocessApplyOverridesView(APIView):
    """Apply manual user overrides to corrected_rows in the session."""
    permission_classes = [CanViewPatients]

    def post(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        overrides = request.data.get('overrides', [])
        if not isinstance(overrides, list):
            return Response({'error': 'overrides doit être une liste.'}, status=status.HTTP_400_BAD_REQUEST)

        corrected_rows = session.get('corrected_rows') or session.get('original_rows') or []
        manual_overrides = session.get('manual_overrides', {})

        applied = 0
        for ov in overrides:
            row_idx = ov.get('row')
            col = ov.get('column')
            new_val = ov.get('new_value')
            if row_idx is None or not col:
                continue
            row_idx = int(row_idx) - 1  # convert 1-based to 0-based
            if 0 <= row_idx < len(corrected_rows):
                corrected_rows[row_idx][col] = new_val
                manual_overrides[f'{row_idx + 1}_{col}'] = new_val
                applied += 1

        session['corrected_rows'] = corrected_rows
        session['manual_overrides'] = manual_overrides
        _save_preprocess_session(session)

        return Response({'applied': applied, 'total_overrides': len(manual_overrides)})


class PatientPreprocessIntegrateView(APIView):
    permission_classes = [CanViewPatients]

    def post(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session de pretraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        source = str(request.data.get('source', 'corrected')).lower()
        rows_key = 'original_rows' if source == 'original' else 'corrected_rows'
        rows = session.get(rows_key, [])
        columns = session.get('columns', [])
        dataframe = _rows_to_dataframe(rows, columns=columns)

        result_payload, result_status = _integrate_dataframe_into_patients(
            dataframe,
            request_user=request.user,
            source_file_name=session.get('source_file_name') or f'preprocess_{session_id}.xlsx',
        )
        result_payload['preprocess_id'] = session_id
        result_payload['integration_source'] = source
        result_payload['quality_score'] = session.get('report', {}).get('summary', {}).get('quality_score')
        return Response(result_payload, status=result_status)


class PatientPreprocessCancelView(APIView):
    permission_classes = [CanViewPatients]

    def post(self, request, session_id):
        session = _load_preprocess_session(session_id)
        if session:
            session['status'] = 'error'
            session['error'] = 'Analyse annulée par l\'utilisateur.'
            _save_preprocess_session(session)
        try:
            from config.celery import app as celery_app
            # Terminate the running task if we have its ID
            task_id = (session or {}).get('celery_task_id')
            if task_id:
                celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
            # Also revoke all reserved (prefetched) tasks for this user
            inspect = celery_app.control.inspect()
            reserved = inspect.reserved() or {}
            for worker_tasks in reserved.values():
                for t in worker_tasks:
                    celery_app.control.revoke(t['id'], terminate=False)
            # Purge anything still in Redis queue
            celery_app.control.purge()
        except Exception:
            pass
        return Response({'status': 'cancelled'}, status=status.HTTP_200_OK)


class PatientPreprocessSubmitValidationView(APIView):
    """Submit preprocessing result for chief/admin validation before integration."""
    permission_classes = [CanViewPatients]

    def post(self, request, session_id):
        from .models import PreprocessValidationRequest
        session = _load_preprocess_session(session_id)
        if not session:
            return Response({'error': 'Session introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        if session.get('status') != 'completed':
            return Response({'error': 'Analyse non terminée.'}, status=status.HTTP_400_BAD_REQUEST)

        source = str(request.data.get('source', 'corrected')).lower()
        report = session.get('report', {})
        summary = report.get('summary', {})

        vr = PreprocessValidationRequest.objects.create(
            session_id=session_id,
            source=source,
            source_file_name=session.get('source_file_name', ''),
            submitted_by=request.user,
            rows_count=summary.get('rows') or 0,
            columns_count=summary.get('columns') or 0,
            quality_score=summary.get('quality_score'),
        )
        AuditLog.objects.create(
            utilisateur=request.user,
            action=f"PREPROCESSING_SUBMITTED: {session.get('source_file_name','')} ({summary.get('rows',0)} lignes, score={summary.get('quality_score','?')})",
            entite='PreprocessValidation',
            entite_id=vr.id,
            adresse_ip=request.META.get('REMOTE_ADDR'),
        )
        return Response({'validation_id': vr.id, 'status': 'pending'}, status=status.HTTP_201_CREATED)


class PatientPreprocessValidationListView(APIView):
    """List pending validation requests — chef_service and super_admin only."""
    permission_classes = [CanViewPatients]

    def get(self, request):
        from .models import PreprocessValidationRequest
        from django.utils import timezone as tz

        role_name = str(getattr(getattr(request.user, 'role', None), 'nom', '') or '')
        if role_name not in ('super_admin', 'chef_service'):
            return Response({'error': 'Accès réservé au chef de service et à l\'administrateur.'}, status=status.HTTP_403_FORBIDDEN)

        qs = PreprocessValidationRequest.objects.select_related('submitted_by', 'reviewed_by')
        filter_status = request.query_params.get('status', 'pending')
        if filter_status != 'all':
            qs = qs.filter(status=filter_status)

        data = []
        for vr in qs[:50]:
            data.append({
                'id': vr.id,
                'session_id': vr.session_id,
                'source': vr.source,
                'source_file_name': vr.source_file_name,
                'submitted_by': str(getattr(vr.submitted_by, 'username', '') or ''),
                'submitted_at': vr.submitted_at.isoformat() if vr.submitted_at else None,
                'status': vr.status,
                'rows_count': vr.rows_count,
                'columns_count': vr.columns_count,
                'quality_score': vr.quality_score,
                'reviewed_by': str(getattr(vr.reviewed_by, 'username', '') or ''),
                'reviewed_at': vr.reviewed_at.isoformat() if vr.reviewed_at else None,
                'comment': vr.comment,
            })
        return Response({'results': data, 'count': len(data)})


class PatientPreprocessValidationDetailView(APIView):
    """Preview data mapped to platform structure + approve/reject."""
    permission_classes = [CanViewPatients]

    def get(self, request, validation_id):
        """Return preview of data mapped to Patient columns."""
        from .models import PreprocessValidationRequest
        try:
            vr = PreprocessValidationRequest.objects.get(id=validation_id)
        except PreprocessValidationRequest.DoesNotExist:
            return Response({'error': 'Validation introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        session = _load_preprocess_session(vr.session_id)
        if not session:
            return Response({'error': 'Session de prétraitement introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        rows_key = 'original_rows' if vr.source == 'original' else 'corrected_rows'
        rows = session.get(rows_key) or session.get('corrected_rows') or []
        columns = session.get('columns', [])
        preview = rows

        report = session.get('report', {})
        issues = report.get('issues', []) or report.get('all_issues', [])
        cross_issues = (report.get('dataset_profile') or {}).get('cross_column_issues', [])

        # Compute cell-level diff between original and corrected rows
        modifications = []
        original_rows = session.get('original_rows') or []
        corrected_rows = session.get('corrected_rows') or []
        if original_rows and corrected_rows and vr.source != 'original':
            for row_idx, (orig, corr) in enumerate(zip(original_rows, corrected_rows)):
                for col in columns:
                    ov = orig.get(col)
                    cv = corr.get(col)
                    ov_str = '' if ov is None else str(ov).strip()
                    cv_str = '' if cv is None else str(cv).strip()
                    if ov_str != cv_str:
                        modifications.append({
                            'row': row_idx + 1,
                            'column': col,
                            'original': ov_str if ov_str != '' else None,
                            'corrected': cv_str if cv_str != '' else None,
                        })

        return Response({
            'id': vr.id,
            'session_id': vr.session_id,
            'source': vr.source,
            'source_file_name': vr.source_file_name,
            'status': vr.status,
            'submitted_by': str(getattr(vr.submitted_by, 'username', '') or ''),
            'submitted_at': vr.submitted_at.isoformat() if vr.submitted_at else None,
            'rows_count': vr.rows_count,
            'columns_count': vr.columns_count,
            'quality_score': vr.quality_score,
            'columns': columns,
            'preview_rows': preview,
            'issues_count': len(issues),
            'cross_column_issues': cross_issues[:10],
            'comment': vr.comment,
            'modifications': modifications,
            'modifications_count': len(modifications),
        })

    def post(self, request, validation_id):
        """Approve or reject the validation request."""
        from .models import PreprocessValidationRequest
        from django.utils import timezone as tz

        role_name = str(getattr(getattr(request.user, 'role', None), 'nom', '') or '')
        if role_name not in ('super_admin', 'chef_service'):
            return Response({'error': 'Accès réservé au chef de service et à l\'administrateur.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            vr = PreprocessValidationRequest.objects.get(id=validation_id)
        except PreprocessValidationRequest.DoesNotExist:
            return Response({'error': 'Validation introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        if vr.status != 'pending':
            return Response({'error': f'Cette demande est déjà {vr.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        action = str(request.data.get('action', '')).lower()
        comment = str(request.data.get('comment', ''))

        if action == 'approve':
            session = _load_preprocess_session(vr.session_id)
            if not session:
                return Response({'error': 'Session introuvable.'}, status=status.HTTP_404_NOT_FOUND)

            rows_key = 'original_rows' if vr.source == 'original' else 'corrected_rows'
            rows = session.get(rows_key) or session.get('corrected_rows') or []
            columns = session.get('columns', [])
            dataframe = _rows_to_dataframe(rows, columns=columns)

            result_payload, result_status = _integrate_dataframe_into_patients(
                dataframe,
                request_user=request.user,
                source_file_name=vr.source_file_name or f'preprocess_{vr.session_id[:8]}.xlsx',
            )
            vr.status = 'approved'
            vr.reviewed_by = request.user
            vr.reviewed_at = tz.now()
            vr.comment = comment
            vr.save()
            # Notifier le soumetteur via l'audit log
            if vr.submitted_by:
                reviewer_name = f"{getattr(request.user, 'prenom', '')} {getattr(request.user, 'nom', '')}".strip() or request.user.email
                AuditLog.objects.create(
                    utilisateur=vr.submitted_by,
                    action=f"PREPROCESSING_APPROVED: {vr.source_file_name or 'fichier'} validé et intégré par {reviewer_name}{' — ' + comment if comment else ''}",
                    entite='PreprocessValidation',
                    entite_id=vr.id,
                    adresse_ip=request.META.get('REMOTE_ADDR'),
                )
            result_payload['validation_id'] = vr.id
            return Response(result_payload, status=result_status)

        elif action == 'reject':
            vr.status = 'rejected'
            vr.reviewed_by = request.user
            vr.reviewed_at = tz.now()
            vr.comment = comment
            vr.save()
            # Notifier le soumetteur via l'audit log
            if vr.submitted_by:
                reviewer_name = f"{getattr(request.user, 'prenom', '')} {getattr(request.user, 'nom', '')}".strip() or request.user.email
                AuditLog.objects.create(
                    utilisateur=vr.submitted_by,
                    action=f"PREPROCESSING_REJECTED: {vr.source_file_name or 'fichier'} refusé par {reviewer_name}{' — ' + comment if comment else ''}",
                    entite='PreprocessValidation',
                    entite_id=vr.id,
                    adresse_ip=request.META.get('REMOTE_ADDR'),
                )
            return Response({'validation_id': vr.id, 'status': 'rejected'})

        return Response({'error': 'Action invalide. Utilisez "approve" ou "reject".'}, status=status.HTTP_400_BAD_REQUEST)


class PatientImportExcelView(APIView):
    permission_classes = [CanViewPatients]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        excel_file = request.FILES.get('file')
        if not excel_file:
            return Response({'error': 'Fichier Excel requis'}, status=status.HTTP_400_BAD_REQUEST)

        source_file_name = getattr(excel_file, 'name', '')
        lower_name = str(source_file_name).lower()
        worksheet = None
        dataframe = None

        if lower_name.endswith('.xls'):
            try:
                excel_file.seek(0)
                dataframe = pd.read_excel(excel_file, engine='xlrd')
            except Exception as error:
                return Response(
                    {'error': f'Impossible de lire le fichier Excel (.xls): {error}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            try:
                excel_file.seek(0)
                workbook = load_workbook(excel_file, data_only=False)
            except Exception as error:
                return Response(
                    {'error': f'Impossible de lire le fichier Excel: {error}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            worksheet = workbook[workbook.sheetnames[0]]

            if is_schema_template_sheet(worksheet):
                template, fields_created = parse_schema_from_template_sheet(worksheet, source_file_name)
                template_data = PatientFormTemplateSerializer(template).data
                return Response(
                    {
                        'mode': 'schema',
                        'template': template_data,
                        'fields_created': fields_created,
                        'patients_created': 0,
                        'errors': [],
                    },
                    status=status.HTTP_201_CREATED,
                )

            try:
                excel_file.seek(0)
                # parse_dates=True aide pandas à reconnaître les colonnes de dates
                dataframe = pd.read_excel(excel_file, parse_dates=True)
            except Exception as error:
                return Response(
                    {'error': f'Impossible de lire les donnees du fichier Excel: {error}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if dataframe is not None:
            dataframe = dataframe.loc[
                :, ~dataframe.columns.astype(str).str.match(r'^(Unnamed|unnamed)(:.*)?$')
            ]

        # ── Role-based import gate ────────────────────────────────────────────
        _role_name = str(getattr(getattr(request.user, 'role', None), 'nom', '') or '')
        _can_self_import = _role_name in ('super_admin', 'chef_service')

        if not _can_self_import:
            from .models import PreprocessValidationRequest
            _columns = list(dataframe.columns)
            _rows = dataframe.astype(object).where(pd.notnull(dataframe), None).to_dict(orient='records')
            _session_id = uuid.uuid4().hex
            _session = {
                'id': _session_id,
                'status': 'completed',
                'source_file_name': source_file_name,
                'columns': _columns,
                'corrected_rows': _rows,
                'original_rows': _rows,
                'report': {'summary': {'rows': len(_rows), 'columns': len(_columns), 'quality_score': None}},
            }
            _save_preprocess_session(_session)
            _vr = PreprocessValidationRequest.objects.create(
                session_id=_session_id,
                source='direct_import',
                source_file_name=source_file_name,
                submitted_by=request.user,
                rows_count=len(_rows),
                columns_count=len(_columns),
                quality_score=None,
            )
            AuditLog.objects.create(
                utilisateur=request.user,
                action=f"IMPORT_PENDING_VALIDATION: {source_file_name} ({len(_rows)} lignes) soumis pour validation",
                entite='PreprocessValidation',
                entite_id=_vr.id,
                adresse_ip=request.META.get('REMOTE_ADDR'),
            )
            return Response({
                'mode': 'pending_validation',
                'validation_id': _vr.id,
                'patients_created': 0,
                'rows_count': len(_rows),
                'source_file_name': source_file_name,
            }, status=status.HTTP_201_CREATED)

        headers = list(dataframe.columns)
        template = upsert_template_from_headers(headers, worksheet, source_file_name, create_fields=False)

        created_count = 0
        row_errors = []
        auto_increment_state = initialize_auto_increment_state()
        # Accumuler toutes les colonnes dynamiques rencontrées sur l'ensemble des lignes
        # Pré-détecter les colonnes non-mappées/non-fixes à partir des headers
        all_dynamic_columns = {}  # normalized_key -> original_column_name
        if template:
            existing_template_keys = set(template.fields.values_list('key', flat=True))
        else:
            existing_template_keys = set()

        for h in headers:
            try:
                header_str = str(h).strip()
            except Exception:
                continue
            if not header_str:
                continue
            norm = normalize_header(header_str)
            if not norm:
                continue
            # Ne pas créer si déjà présent dans le template
            if norm in existing_template_keys:
                continue
            # Ne jamais créer de champ pour les colonnes fusionnées
            if norm in _COLUMNS_FUSED_INTO_COMORBIDITE_LISTE:
                continue
            # Si la colonne est mappée dans COLUMN_MAPPING, ce n'est pas une dynamique
            if norm in COLUMN_MAPPING:
                continue
            # Pré-enregistrer comme colonne dynamique (sera marquée/créée plus tard)
            all_dynamic_columns.setdefault(norm, header_str)

        for index, row in dataframe.iterrows():
            payload = build_patient_payload(row)

            # Récupérer les colonnes dynamiques détectées pour cette ligne
            detected = payload.pop('_dynamic_columns_detected', set())
            for norm_key in detected:
                if norm_key not in all_dynamic_columns:
                    # Chercher le nom original dans les headers du dataframe
                    original_name = next(
                        (str(h).strip() for h in headers
                         if normalize_header(str(h).strip()) == norm_key),
                        norm_key,
                    )
                    all_dynamic_columns[norm_key] = original_name

            payload = apply_automatic_schema_fields(
                payload, auto_increment_state=auto_increment_state, current_user=request.user
            )
            payload = ensure_required_identity_fields(payload)
            payload = ensure_incremental_identifiers(
                payload, auto_increment_state=auto_increment_state, force_generated=True
            )

            serializer = PatientSerializer(data=payload)
            if serializer.is_valid():
                serializer.save()
                created_count += 1
            else:
                row_errors.append({'row': index + 2, 'errors': serializer.errors})
                print(f"ERREUR ligne {index + 2}: {serializer.errors}")

        # ── Enregistrer les colonnes dynamiques dans le template ──────────────
        dynamic_columns_info = []
        if all_dynamic_columns and template:
            existing_keys = set(template.fields.values_list('key', flat=True))
            new_fields = []
            for norm_key, original_name in all_dynamic_columns.items():
                if norm_key in existing_keys:
                    # Déjà connue : mettre à jour le source_hint pour marquer comme dynamique
                    template.fields.filter(key=norm_key).update(
                        source_hint='dynamic_column'
                    )
                else:
                    new_fields.append(
                        PatientFormField(
                            template=template,
                            key=norm_key,
                            label=original_name,
                            field_type='text_short',
                            order=10000 + len(new_fields),
                            choices=[],
                            source_hint='dynamic_column',
                            is_required=False,
                        )
                    )
                dynamic_columns_info.append({
                    'key': norm_key,
                    'label': original_name,
                    'is_new': norm_key not in existing_keys,
                })

            if new_fields:
                PatientFormField.objects.bulk_create(new_fields)
                print(f"✅ {len(new_fields)} nouvelle(s) colonne(s) dynamique(s) enregistrée(s): "
                      f"{[f.key for f in new_fields]}")

        if created_count > 0 or all_dynamic_columns:
            try:
                refresh_postgres_flat_view(template)
            except Exception as e:
                print(f"Erreur rafraîchissement vue: {e}")

        template_data = PatientFormTemplateSerializer(template).data
        status_code = status.HTTP_201_CREATED if created_count else status.HTTP_200_OK

        print(f"\n{'='*80}")
        print(f"IMPORT TERMINÉ: {created_count} patients créés, {len(row_errors)} erreurs")
        print(f"Colonnes dynamiques: {list(all_dynamic_columns.keys())}")
        print(f"{'='*80}\n")

        return Response(
            {
                'mode': 'data',
                'template': template_data,
                'fields_created': len(template_data.get('fields', [])),
                'patients_created': created_count,
                'errors': row_errors,
                'dynamic_columns': dynamic_columns_info,
                'dynamic_columns_count': len(dynamic_columns_info),
                'new_dynamic_columns_count': sum(1 for c in dynamic_columns_info if c.get('is_new')),
            },
            status=status_code,
        )


class PatientSchemaView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request):
        template = get_active_template()
        if not template:
            return Response({'template': None})

        # Supprimer définitivement les colonnes déjà fusionnées dans comorbidite_liste
        template.fields.filter(key__in=_COLUMNS_FUSED_INTO_COMORBIDITE_LISTE).delete()

        return Response({'template': PatientFormTemplateSerializer(template).data})


class PatientPlateformeFlatView(APIView):
    permission_classes = [CanViewPatients]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM patients_plateforme_flat')
            columns = [col[0] for col in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return Response(rows)
