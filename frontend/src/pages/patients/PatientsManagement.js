import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputAdornment,
  InputLabel,
  LinearProgress,
  Slider,
  Paper,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import AddCircleOutlineOutlinedIcon from '@mui/icons-material/AddCircleOutlineOutlined';
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import ClearOutlinedIcon from '@mui/icons-material/ClearOutlined';
import FilterListOutlinedIcon from '@mui/icons-material/FilterListOutlined';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import AppSidebar from '../../components/common/AppSidebar';
import { useLocation, useNavigate } from 'react-router-dom';
import { useLanguage } from '../../context/LanguageContext';
import Preprocessing from '../preprocessing/Preprocessing';
import { Bar, Bubble, Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';
import defaultSchemaTemplate from '../../Data_platform_schema.json';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Legend);

// Ici seulement, place la fonction utilitaire :
function normalizeIdEnregistrement(id) {
  if (!id) return '';
  const num = String(id).replace(/\D/g, '').padStart(6, '0');
  return `SRC-${num}`;
}

const getNumericPatientId = (value) => {
  if (value === null || value === undefined) {
    return Number.MAX_SAFE_INTEGER;
  }

  const normalized = String(value).trim();
  if (!normalized) {
    return Number.MAX_SAFE_INTEGER;
  }

  const numericOnly = normalized.match(/^\d+$/);
  if (numericOnly) {
    return Number.parseInt(numericOnly[0], 10);
  }

  const trailingDigits = normalized.match(/(\d+)$/);
  if (trailingDigits) {
    return Number.parseInt(trailingDigits[1], 10);
  }

  return Number.MAX_SAFE_INTEGER;
};

const emptyForm = {
  id: null,
  id_patient: '',
  id_enregistrement_source: '',
  nom: '',
  prenom: '',
  age: '',
  sexe: '',
  maladie: '',
  date_naissance: '',
};

const emptyFilters = {
  search: '',
  id_patient: '',
  sexe: '',
  age_min: '',
  age_max: '',
  date_naissance: '',
  statut_inclusion: '',
  infection: '',
  hemorrhage: '',
  avf_created: '',
};

const sexLabels = {
  M: 'Homme',
  F: 'Femme',
  O: 'Inconnu',
};

const normalizeSexDisplay = (rawValue) => {
  if (rawValue === null || rawValue === undefined || rawValue === '') {
    return rawValue;
  }

  const normalized = String(rawValue).trim().toLowerCase();
  if (['1', 'm', 'male', 'masculin', 'homme', 'man'].includes(normalized)) {
    return 'Homme';
  }
  if (['0', 'f', 'female', 'feminin', 'femme', 'woman'].includes(normalized)) {
    return 'Femme';
  }
  if (['i', 'intersex', 'intersexe'].includes(normalized)) {
    return 'Intersexe';
  }
  if (['9', 'o', 'other', 'autre', 'unknown', 'inconnu', 'na', 'n/a', 'none', 'null'].includes(normalized)) {
    return 'Inconnu';
  }

  return rawValue;
};

const BOOLEAN_TRUE_VALUES = ['1', 'true', 'yes', 'oui', 'y'];
const BOOLEAN_FALSE_VALUES = ['0', 'false', 'no', 'non', 'n'];

const toBooleanDisplay = (rawValue) => {
  if (rawValue === null || rawValue === undefined || rawValue === '') {
    return rawValue;
  }

  const normalized = String(rawValue).trim().toLowerCase();
  if (BOOLEAN_TRUE_VALUES.includes(normalized)) {
    return 'Oui';
  }
  if (BOOLEAN_FALSE_VALUES.includes(normalized)) {
    return 'Non';
  }

  return rawValue;
};

const isNoResponseValue = (value) => {
  if (value === null || value === undefined || value === '') {
    return true;
  }

  const normalized = String(value).trim().toLowerCase();
  return normalized === '' || normalized === 'x' || normalized === '-';
};

const isPositiveClinicalValue = (value) => {
  if (isNoResponseValue(value)) {
    return false;
  }

  const normalized = String(value).trim().toLowerCase();
  if (BOOLEAN_FALSE_VALUES.includes(normalized)) {
    return false;
  }
  if (['absent', 'negative', 'negatif', 'no'].includes(normalized)) {
    return false;
  }
  return true;
};


const toMonthKey = (rawDate) => {
  const parsed = toDateOrNull(rawDate);
  if (!parsed) {
    return null;
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  return `${year}-${month}`;
};

function toDateOrNull(rawDate) {
  const parsed = new Date(String(rawDate || ''));
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

const monthKeyToLabel = (monthKey) => {
  const [year, month] = String(monthKey).split('-');
  return `${month}/${year}`;
};

const PATIENT_FIELD_MAP = {
  nom: 'nom',
  prenom: 'prenom',
  age: 'age',
  sexe: 'sexe',
  maladie: 'maladie',
  telephone: 'telephone',
  adresse: 'adresse',
  date_naissance: 'date_naissance',
  date_admission: 'date_admission',
  id_patient: 'id_patient',
  id_enregistrement_source: 'id_enregistrement_source',
  id_site: 'id_site',
  statut_inclusion: 'statut_inclusion',
  statut_consentement: 'statut_consentement',
  date_evaluation_initiale: 'date_evaluation_initiale',
  utilisateur_saisie: 'utilisateur_saisie',
  derniere_mise_a_jour: 'derniere_mise_a_jour',
};

const normalizeSchemaTemplate = (rawTemplate) => ({
  fields: (rawTemplate?.fields || []).map((field) => ({
    ...field,
    label: field.label || String(field.key).replace(/_/g, ' '),
    order: field.index ?? 0,
    choices: field.possible_values || [],
  })),
});

const DEFAULT_SCHEMA_TEMPLATE = normalizeSchemaTemplate(defaultSchemaTemplate);

const FIXED_BASE_COLUMNS = [
  { key: 'id_patient', label: 'id_patient' },
  { key: 'nom', label: 'nom' },
  { key: 'prenom', label: 'prenom' },
  // patient_id masqué volontairement
];

const SECTION_FIELD_MAP = {
  demographie_: 'demographie_data',
  irc_: 'irc_data',
  comorbidite_: 'comorbidite_data',
  presentation_: 'presentation_data',
  biologie_: 'biologie_data',
  imagerie_: 'imagerie_data',
  dialyse_: 'dialyse_data',
  qualite_: 'qualite_data',
  complication_: 'complication_data',
  traitement_: 'traitement_data',
  devenir_: 'devenir_data',
};

// ─────────────────────────────────────────────────────────────────
// Schéma complet de la plateforme (structure fixe invariable)
// Ordre : FIXED → SECTION → KEYS → FIELD_META → FALLBACK
// ─────────────────────────────────────────────────────────────────

const DEFAULT_PATIENT_COLUMN_KEYS = [
  // ── Identité du patient (toujours en tête) ──────────────────────
  'nom',
  'prenom',
  // ── Identifiants & statuts (ordre JSON index 1-8) ───────────────
  'id_patient',
  'id_enregistrement_source',
  'id_site',
  'statut_inclusion',
  'statut_consentement',
  'date_evaluation_initiale',
  'utilisateur_saisie',
  'derniere_mise_a_jour',
  // ── Démographie (index 9-19) ────────────────────────────────────
  'demographie_sexe',
  'demographie_date_naissance',
  'demographie_age_ans',
  'demographie_statut_matrimonial',
  'demographie_zone_residence',
  'demographie_distance_centre_km',
  'demographie_couverture_sociale',
  'demographie_mode_vie',
  'demographie_statut_professionnel',
  'demographie_niveau_education',
  'demographie_tabagisme',
  'demographie_alcool',
  // ── IRC (index 20-32) ───────────────────────────────────────────
  'irc_date_premier_contact_nephrologique',
  'irc_etiologie_principale',
  'irc_etiologie_secondaire',
  'irc_maladie_renale_hereditaire',
  'irc_antecedents_familiaux_renaux',
  'irc_statut_biopsie_renale',
  'irc_resultat_biopsie_renale',
  'irc_connue_avant_dialyse',
  'irc_source_adressage',
  'irc_contexte_debut_dialyse',
  'irc_themes_education_therapeutique',
  'irc_niveau_comprehension_patient',
  'irc_preference_therapie_renale',
  // ── Comorbidités (index 33-36) ──────────────────────────────────
  'comorbidite_statut_diabete',
  'icc_charlson',
  'comorbidite_liste',
  'comorbidite_autre',
  // ── Présentation clinique (index 37-50) ─────────────────────────
  'presentation_date_episode',
  'presentation_lieu_debut',
  'presentation_raisons_debut',
  'presentation_symptomes',
  'presentation_tas_mmhg',
  'presentation_tad_mmhg',
  'presentation_frequence_cardiaque_bpm',
  'presentation_temperature_c',
  'presentation_poids_kg',
  'presentation_taille_cm',
  'presentation_statut_diurese',
  'presentation_volume_urinaire_ml_j',
  'presentation_autonomie_fonctionnelle',
  'presentation_notes_examen_clinique',
  // ── Biologie (index 51-72) ──────────────────────────────────────
  'biologie_date_prelevement',
  'biologie_uree_g_l',
  'biologie_creatinine_mg_l',
  'biologie_hemoglobine_g_dl',
  'biologie_leucocytes_g_l',
  'biologie_plaquettes_g_l',
  'biologie_albumine_g_l',
  'biologie_crp_mg_l',
  'biologie_sodium_mmol_l',
  'biologie_potassium_mmol_l',
  'biologie_bicarbonates_mmol_l',
  'biologie_calcium_corrige_mg_l',
  'biologie_phosphore_mg_l',
  'biologie_pth_pg_ml',
  'biologie_ferritine_ng_ml',
  'biologie_saturation_transferrine_pct',
  'biologie_vitamine_d_ng_ml',
  'biologie_proteinurie_g_24h',
  'biologie_hba1c_pct',
  'biologie_hbsag',
  'biologie_vhc',
  'biologie_vih',
  // ── Imagerie (index 73-84) ──────────────────────────────────────
  'imagerie_date_echographie_renale',
  'imagerie_taille_reins',
  'imagerie_echogenicite_renale',
  'imagerie_hydronephrose',
  'imagerie_kystes_renaux',
  'imagerie_lithiase',
  'imagerie_radiographie_thorax',
  'imagerie_date_echocardiographie',
  'imagerie_fevg_pct',
  'imagerie_hypertrophie_ventriculaire_gauche',
  'imagerie_valvulopathie',
  'imagerie_autres_resultats',
  // ── Dialyse (index 85-104) ──────────────────────────────────────
  'dialyse_date_debut',
  'dialyse_modalite_initiale',
  'dialyse_modalite_actuelle',
  'dialyse_type_acces_initial',
  'dialyse_site_acces_initial',
  'dialyse_date_creation_acces',
  'dialyse_date_premiere_utilisation_acces',
  'dialyse_seances_par_semaine',
  'dialyse_duree_seance_min',
  'dialyse_debit_sanguin_ml_min',
  'dialyse_debit_dialysat_ml_min',
  'dialyse_potassium_dialysat_mmol_l',
  'dialyse_calcium_dialysat_mmol_l',
  'dialyse_type_anticoagulation',
  'dialyse_statut_fonction_renale_residuelle',
  'dialyse_type_regime_dp',
  'dialyse_nombre_echanges_dp_jour',
  'dialyse_volume_stase_dp_ml',
  'dialyse_information_transplantation_donnee',
  'dialyse_statut_liste_attente_transplantation',
  // ── Qualité de dialyse (index 105-116) ──────────────────────────
  'qualite_date_evaluation',
  'qualite_spktv',
  'qualite_urr_pct',
  'qualite_prise_poids_interdialytique_kg',
  'qualite_taux_ultrafiltration_ml_kg_h',
  'qualite_tas_predialyse_mmhg',
  'qualite_tas_postdialyse_mmhg',
  'qualite_poids_sec_kg',
  'qualite_seances_manquees_30j',
  'qualite_seances_raccourcies_30j',
  'qualite_hypotensions_intradialytiques_30j',
  'qualite_observance_declaree_patient',
  // ── Traitement (index 126-127) ───────────────────────────────────
  'traitement_medicaments_renaux_actuels',
  'traitement_autres_notes',
  // ── Complications (index 117-125) ───────────────────────────────
  'complication_debut_periode_suivi',
  'complication_fin_periode_suivi',
  'complication_liste',
  'complication_date_premier_evenement',
  'complication_nombre_hospitalisations',
  'complication_jours_hospitalisation',
  'complication_motifs_hospitalisation',
  'complication_changement_modalite_dialyse',
  'complication_autres_notes',
  // ── Devenir (index 128-135) ─────────────────────────────────────
  'devenir_date_dernier_suivi',
  'devenir_statut',
  'devenir_date_deces',
  'devenir_cause_deces',
  'devenir_date_transplantation',
  'devenir_qualite_vie',
  'devenir_categorie_pronostique',
  'devenir_notes',
];

// Champs en lecture seule / générés automatiquement (affichés mais non éditables)
const AUTO_FIELD_KEYS = new Set([
  'id_patient', 'utilisateur_saisie', 'derniere_mise_a_jour',
]);

// Labels lisibles par section pour chaque champ de la plateforme
const FIELD_LABEL_MAP = {
  id_patient: 'ID Patient',
  nom: 'Nom',
  prenom: 'Prénom',
  id_enregistrement_source: 'ID Enregistrement Source',
  id_site: 'ID Site',
  statut_inclusion: 'Statut Inclusion',
  statut_consentement: 'Statut Consentement',
  utilisateur_saisie: 'Utilisateur Saisie',
  derniere_mise_a_jour: 'Dernière Mise à Jour',
  date_evaluation_initiale: 'Date Évaluation Initiale',
  demographie_sexe: 'Sexe',
  demographie_date_naissance: 'Date de Naissance',
  demographie_age_ans: 'Âge (ans)',
  demographie_statut_matrimonial: 'Statut Matrimonial',
  demographie_mode_vie: 'Mode de Vie',
  demographie_zone_residence: 'Zone de Résidence',
  demographie_distance_centre_km: 'Distance Centre (km)',
  demographie_couverture_sociale: 'Couverture Sociale',
  demographie_statut_professionnel: 'Statut Professionnel',
  demographie_niveau_education: "Niveau d'Éducation",
  demographie_tabagisme: 'Tabagisme',
  demographie_alcool: 'Alcool',
  irc_date_premier_contact_nephrologique: 'Date Premier Contact Néphro.',
  irc_etiologie_principale: 'Étiologie Principale',
  irc_etiologie_secondaire: 'Étiologie Secondaire',
  irc_maladie_renale_hereditaire: 'Maladie Rénale Héréditaire',
  irc_antecedents_familiaux_renaux: 'Antécédents Familiaux Rénaux',
  irc_statut_biopsie_renale: 'Statut Biopsie Rénale',
  irc_resultat_biopsie_renale: 'Résultat Biopsie Rénale',
  irc_connue_avant_dialyse: 'IRC Connue Avant Dialyse',
  irc_source_adressage: "Source d'Adressage",
  irc_contexte_debut_dialyse: 'Contexte Début Dialyse',
  irc_themes_education_therapeutique: 'Éducation Thérapeutique',
  irc_niveau_comprehension_patient: 'Niveau Compréhension Patient',
  irc_preference_therapie_renale: 'Préférence Thérapie Rénale',
  comorbidite_statut_diabete: 'Statut Diabète',
  icc_charlson: 'Score Charlson',
  comorbidite_liste: 'Liste Comorbidités',
  comorbidite_autre: 'Autre Comorbidité',
  comorbidite_exposition_toxique: 'Exposition Toxique',
  comorbidite_antecedents_medicaments_nephrotoxiques: 'Antécédents Médicaments Néphrotoxiques',
  presentation_date_episode: 'Date Episode',
  presentation_lieu_debut: 'Lieu Début',
  presentation_raisons_debut: 'Raisons Début',
  presentation_symptomes: 'Symptômes',
  presentation_tas_mmhg: 'TAS (mmHg)',
  presentation_tad_mmhg: 'TAD (mmHg)',
  presentation_frequence_cardiaque_bpm: 'Fréquence Cardiaque (bpm)',
  presentation_temperature_c: 'Température (°C)',
  presentation_poids_kg: 'Poids (kg)',
  presentation_taille_cm: 'Taille (cm)',
  presentation_statut_diurese: 'Statut Diurèse',
  presentation_volume_urinaire_ml_j: 'Volume Urinaire (mL/j)',
  presentation_autonomie_fonctionnelle: 'Autonomie Fonctionnelle',
  presentation_notes_examen_clinique: 'Notes Examen Clinique',
  biologie_date_prelevement: 'Date Prélèvement',
  biologie_creatinine_mg_l: 'Créatinine (mg/L)',
  biologie_uree_g_l: 'Urée (g/L)',
  biologie_hemoglobine_g_dl: 'Hémoglobine (g/dL)',
  biologie_hba1c_pct: 'HbA1c (%)',
  biologie_leucocytes_g_l: 'Leucocytes (G/L)',
  biologie_plaquettes_g_l: 'Plaquettes (G/L)',
  biologie_albumine_g_l: 'Albumine (g/L)',
  biologie_crp_mg_l: 'CRP (mg/L)',
  biologie_sodium_mmol_l: 'Sodium (mmol/L)',
  biologie_potassium_mmol_l: 'Potassium (mmol/L)',
  biologie_bicarbonates_mmol_l: 'Bicarbonates (mmol/L)',
  biologie_calcium_corrige_mg_l: 'Calcium Corrigé (mg/L)',
  biologie_phosphore_mg_l: 'Phosphore (mg/L)',
  biologie_pth_pg_ml: 'PTH (pg/mL)',
  biologie_ferritine_ng_ml: 'Ferritine (ng/mL)',
  biologie_saturation_transferrine_pct: 'Saturation Transferrine (%)',
  biologie_vitamine_d_ng_ml: 'Vitamine D (ng/mL)',
  biologie_proteinurie_g_24h: 'Protéinurie (g/24h)',
  biologie_hbsag: 'HBsAg',
  biologie_vhc: 'VHC',
  biologie_vih: 'VIH',
  imagerie_date_echographie_renale: 'Date Échographie Rénale',
  imagerie_taille_reins: 'Taille des Reins',
  imagerie_echogenicite_renale: 'Échogénicité Rénale',
  imagerie_hydronephrose: 'Hydronéphrose',
  imagerie_kystes_renaux: 'Kystes Rénaux',
  imagerie_lithiase: 'Lithiase',
  imagerie_radiographie_thorax: 'Radiographie Thorax',
  imagerie_date_echocardiographie: 'Date Échocardiographie',
  imagerie_fevg_pct: 'FEVG (%)',
  imagerie_hypertrophie_ventriculaire_gauche: 'Hypertrophie Ventriculaire Gauche',
  imagerie_valvulopathie: 'Valvulopathie',
  imagerie_autres_resultats: 'Autres Résultats Imagerie',
  dialyse_date_debut: 'Date Début Dialyse',
  dialyse_modalite_initiale: 'Modalité Initiale',
  dialyse_modalite_actuelle: 'Modalité Actuelle',
  dialyse_type_acces_initial: 'Type Accès Initial',
  dialyse_site_acces_initial: 'Site Accès Initial',
  dialyse_date_creation_acces: 'Date Création Accès',
  dialyse_date_premiere_utilisation_acces: "Date 1ère Utilisation Accès",
  dialyse_seances_par_semaine: 'Séances par Semaine',
  dialyse_duree_seance_min: 'Durée Séance (min)',
  dialyse_debit_sanguin_ml_min: 'Débit Sanguin (mL/min)',
  dialyse_debit_dialysat_ml_min: 'Débit Dialysat (mL/min)',
  dialyse_potassium_dialysat_mmol_l: 'Potassium Dialysat (mmol/L)',
  dialyse_calcium_dialysat_mmol_l: 'Calcium Dialysat (mmol/L)',
  dialyse_type_anticoagulation: 'Type Anticoagulation',
  dialyse_statut_fonction_renale_residuelle: 'Statut Fonction Rénale Résiduelle',
  dialyse_type_regime_dp: 'Type Régime DP',
  dialyse_nombre_echanges_dp_jour: 'Nombre Échanges DP/Jour',
  dialyse_volume_stase_dp_ml: 'Volume Stase DP (mL)',
  dialyse_information_transplantation_donnee: 'Info Transplantation Donnée',
  dialyse_statut_liste_attente_transplantation: 'Statut Liste Attente Transplantation',
  qualite_date_evaluation: 'Date Évaluation Qualité',
  qualite_spktv: 'Sp Kt/V',
  qualite_urr_pct: 'URR (%)',
  qualite_prise_poids_interdialytique_kg: 'Prise de Poids Interdialytique (kg)',
  qualite_taux_ultrafiltration_ml_kg_h: 'Taux Ultrafiltration (mL/kg/h)',
  qualite_tas_predialyse_mmhg: 'TAS Pré-dialyse (mmHg)',
  qualite_tas_postdialyse_mmhg: 'TAS Post-dialyse (mmHg)',
  qualite_poids_sec_kg: 'Poids Sec (kg)',
  qualite_seances_manquees_30j: 'Séances Manquées (30j)',
  qualite_seances_raccourcies_30j: 'Séances Raccourcies (30j)',
  qualite_hypotensions_intradialytiques_30j: 'Hypotensions Intradialytiques (30j)',
  qualite_observance_declaree_patient: 'Observance Déclarée Patient',
  traitement_medicaments_renaux_actuels: 'Médicaments Rénaux Actuels',
  traitement_autres_notes: 'Autres Notes Traitement',
  complication_debut_periode_suivi: 'Début Période Suivi',
  complication_fin_periode_suivi: 'Fin Période Suivi',
  complication_liste: 'Liste Complications',
  complication_date_premier_evenement: 'Date Premier Événement',
  complication_nombre_hospitalisations: 'Nombre Hospitalisations',
  complication_jours_hospitalisation: 'Jours Hospitalisation',
  complication_motifs_hospitalisation: 'Motifs Hospitalisation',
  complication_changement_modalite_dialyse: 'Changement Modalité Dialyse',
  complication_autres_notes: 'Autres Notes Complications',
  devenir_date_dernier_suivi: 'Date Dernier Suivi',
  devenir_statut: 'Statut Devenir',
  devenir_date_deces: 'Date Décès',
  devenir_cause_deces: 'Cause Décès',
  devenir_date_transplantation: 'Date Transplantation',
  devenir_qualite_vie: 'Qualité de Vie',
  devenir_categorie_pronostique: 'Catégorie Pronostique',
  devenir_notes: 'Notes Devenir',
};

// Champs de type date
const DATE_FIELD_KEYS = new Set([
  'date_evaluation_initiale', 'derniere_mise_a_jour',
  'demographie_date_naissance',
  'irc_date_premier_contact_nephrologique',
  'presentation_date_episode',
  'biologie_date_prelevement',
  'imagerie_date_echographie_renale', 'imagerie_date_echocardiographie',
  'dialyse_date_debut', 'dialyse_date_creation_acces', 'dialyse_date_premiere_utilisation_acces',
  'qualite_date_evaluation',
  'complication_debut_periode_suivi', 'complication_fin_periode_suivi', 'complication_date_premier_evenement',
  'devenir_date_dernier_suivi', 'devenir_date_deces', 'devenir_date_transplantation',
]);

// Champs numériques
const NUMERIC_FIELD_KEYS = new Set([
  'demographie_age_ans', 'demographie_distance_centre_km',
  'icc_charlson',
  'presentation_tas_mmhg', 'presentation_tad_mmhg', 'presentation_frequence_cardiaque_bpm',
  'presentation_temperature_c', 'presentation_poids_kg', 'presentation_taille_cm',
  'presentation_volume_urinaire_ml_j',
  'biologie_creatinine_mg_l', 'biologie_uree_g_l',
  'biologie_hemoglobine_g_dl', 'biologie_hba1c_pct', 'biologie_leucocytes_g_l',
  'biologie_plaquettes_g_l', 'biologie_albumine_g_l', 'biologie_crp_mg_l',
  'biologie_sodium_mmol_l', 'biologie_potassium_mmol_l', 'biologie_bicarbonates_mmol_l',
  'biologie_calcium_corrige_mg_l', 'biologie_phosphore_mg_l', 'biologie_pth_pg_ml',
  'biologie_ferritine_ng_ml', 'biologie_saturation_transferrine_pct', 'biologie_vitamine_d_ng_ml',
  'biologie_proteinurie_g_24h',
  'imagerie_fevg_pct',
  'dialyse_seances_par_semaine', 'dialyse_duree_seance_min',
  'dialyse_debit_sanguin_ml_min', 'dialyse_debit_dialysat_ml_min',
  'dialyse_potassium_dialysat_mmol_l', 'dialyse_calcium_dialysat_mmol_l',
  'dialyse_nombre_echanges_dp_jour', 'dialyse_volume_stase_dp_ml',
  'qualite_spktv', 'qualite_urr_pct', 'qualite_prise_poids_interdialytique_kg',
  'qualite_taux_ultrafiltration_ml_kg_h', 'qualite_tas_predialyse_mmhg', 'qualite_tas_postdialyse_mmhg',
  'qualite_poids_sec_kg', 'qualite_seances_manquees_30j', 'qualite_seances_raccourcies_30j',
  'qualite_hypotensions_intradialytiques_30j',
  'complication_nombre_hospitalisations', 'complication_jours_hospitalisation',
]);

// Champs avec liste de choix — valeurs exactes issues de Data_platform_schema.json
const CHOICE_FIELD_MAP = {
  // Identifiants & statuts
  statut_inclusion: ['depiste', 'en_suivi', 'inclus', 'retire', 'termine'],
  statut_consentement: ['consenti', 'en_attente', 'non_applicable', 'refuse'],
  // Démographie
  demographie_sexe: ['femme', 'homme', 'inconnu', 'intersexe'],
  demographie_statut_matrimonial: ['celibataire', 'divorce', 'inconnu', 'marie', 'veuf'],
  demographie_zone_residence: [
    'agadir', 'autre_ville_du_maroc', 'beni_mellal', 'casablanca', 'dakhla',
    'el_jadida', 'errachidia', 'fes', 'guelmim', 'hors_maroc', 'kenitra',
    'khouribga', 'ksar_el_kebir', 'laayoune', 'larache', 'marrakech', 'meknes',
    'mohammedia', 'nador', 'ouarzazate', 'oujda', 'rabat', 'safi', 'sale',
    'settat', 'tanger', 'taza', 'tetouan',
  ],
  demographie_couverture_sociale: ['amo', 'assistance_publique', 'assurance_militaire', 'assurance_privee', 'auto_paiement', 'autre', 'inconnu'],
  demographie_mode_vie: ['avec_famille', 'inconnu', 'institutionnalise', 'sans_abri', 'seul'],
  demographie_statut_professionnel: ['au_foyer', 'employe', 'etudiant', 'incapacite', 'inconnu', 'retraite', 'sans_emploi'],
  demographie_niveau_education: ['aucun', 'inconnu', 'lycee', 'primaire', 'secondaire', 'universitaire'],
  demographie_tabagisme: ['actuel', 'ancien', 'inconnu', 'jamais'],
  demographie_alcool: ['ancien', 'inconnu', 'jamais', 'occasionnel', 'regulier'],
  // IRC
  irc_etiologie_principale: [
    'amylose_ou_myelome', 'autre', 'glomerulonephrite_chronique', 'indeterminee',
    'nephrite_interstitielle', 'nephrite_lupique', 'nephroangiosclerose_hypertensive',
    'nephropathie_diabetique', 'polykystose_renale', 'uropathie_obstructive', 'vascularite',
  ],
  irc_maladie_renale_hereditaire: ['non', 'oui'],
  irc_antecedents_familiaux_renaux: ['non', 'oui'],
  irc_statut_biopsie_renale: ['en_attente', 'inconnu', 'non_realisee', 'realisee_concluante', 'realisee_non_concluante'],
  irc_connue_avant_dialyse: ['non', 'oui'],
  irc_source_adressage: ['autre', 'autre_specialite', 'medecine_interne', 'nephrologue', 'soins_primaires', 'urgences'],
  irc_contexte_debut_dialyse: ['debut_en_urgence', 'debut_non_planifie_en_hospitalisation', 'debut_planifie', 'inconnu', 'transfert_entrant'],
  irc_themes_education_therapeutique: ['non', 'oui'],
  irc_niveau_comprehension_patient: ['bonne', 'excellente', 'faible', 'inconnu', 'partielle'],
  irc_preference_therapie_renale: ['dialyse_peritoneale', 'hemodialyse', 'indecis', 'refus', 'transplantation'],
  // Comorbidités
  comorbidite_statut_diabete: ['aucun', 'inconnu', 'secondaire', 'type_1', 'type_2'],
  // comorbidite_liste → multiple_choice, géré séparément
  // Présentation
  presentation_lieu_debut: ['consultation_externe', 'reanimation', 'service_hospitalisation', 'transfert_autre_centre', 'urgences'],
  // presentation_raisons_debut → multiple_choice
  // presentation_symptomes → multiple_choice
  presentation_statut_diurese: ['anurique', 'diurese_preservee', 'inconnu', 'oligurique'],
  presentation_autonomie_fonctionnelle: ['alitete', 'autonome', 'dependant', 'inconnu', 'partiellement_dependant'],
  // Biologie
  biologie_hbsag: ['inconnu', 'negatif', 'positif'],
  biologie_vhc: ['inconnu', 'negatif', 'positif'],
  biologie_vih: ['inconnu', 'negatif', 'positif'],
  // Imagerie
  imagerie_taille_reins: ['asymetriques', 'augmentes', 'non_rapporte', 'normaux', 'petits'],
  imagerie_echogenicite_renale: ['augmentee', 'non_rapporte', 'normale', 'tres_augmentee'],
  imagerie_hydronephrose: ['non', 'oui'],
  imagerie_kystes_renaux: ['non', 'oui'],
  imagerie_lithiase: ['non', 'oui'],
  imagerie_hypertrophie_ventriculaire_gauche: ['non', 'oui'],
  // Dialyse
  dialyse_modalite_initiale: ['dialyse_peritoneale', 'hemodialyse', 'hemofiltration', 'hybride', 'inconnu'],
  dialyse_modalite_actuelle: ['dialyse_peritoneale', 'hemodialyse', 'hemofiltration', 'hybride', 'inconnu'],
  dialyse_type_acces_initial: ['autre', 'cathetere_non_tunnellise', 'cathetere_peritoneal', 'cathetere_tunnellise', 'fistule_arterioveineuse', 'greffon_arterioveineux'],
  dialyse_site_acces_initial: ['abdomen_dp', 'autre', 'femorale', 'fistule_avant_bras', 'fistule_bras', 'jugulaire_interne_droite', 'jugulaire_interne_gauche', 'sous_claviere'],
  dialyse_type_anticoagulation: ['autre', 'citrate', 'heparine_bas_poids_moleculaire', 'heparine_non_fractionnee', 'sans_anticoagulation'],
  dialyse_statut_fonction_renale_residuelle: ['anurique', 'diurese_preservee', 'inconnu', 'oligurique'],
  dialyse_type_regime_dp: ['autre', 'dpa', 'dpca', 'dpi', 'non_applicable'],
  dialyse_information_transplantation_donnee: ['non', 'oui'],
  dialyse_statut_liste_attente_transplantation: ['bilan_en_cours', 'inscrit', 'non_eligible', 'non_evalue', 'refuse', 'temporairement_inactif'],
  // Qualité
  qualite_observance_declaree_patient: ['bonne', 'inconnu', 'mauvaise', 'partielle'],
  // Complications
  complication_changement_modalite_dialyse: ['aucun', 'autre', 'changement_temporaire', 'dialyse_peritoneale_vers_hemodialyse', 'hemodialyse_vers_dialyse_peritoneale'],
  // complication_liste → multiple_choice
  // complication_motifs_hospitalisation → multiple_choice
  // Devenir
  devenir_statut: ['decede', 'perdu_de_vue', 'recuperation_fonction_renale', 'transfere_sortant', 'transplante', 'vivant_sous_dialyse'],
  devenir_cause_deces: ['autre', 'cancer', 'cardiovasculaire', 'hemorragie', 'inconnue', 'infection', 'mort_subite'],
};

// Champs texte long (multiline) — depuis JSON field_type "texte libre long"
const TEXT_LONG_FIELD_KEYS = new Set([
  'irc_resultat_biopsie_renale',
  'comorbidite_autre',
  'presentation_notes_examen_clinique',
  'imagerie_radiographie_thorax',
  'imagerie_autres_resultats',
  'complication_autres_notes',
  'traitement_autres_notes',
  'devenir_notes',
]);

// Champs à choix multiples — depuis JSON field_type "liste à choix multiple"
const MULTIPLE_CHOICE_FIELD_MAP = {
  comorbidite_liste: [
    'antecedent_nephrotoxiques', 'autre', 'cardiopathie', 'exposition_toxique',
    'goutte', 'hypertension_arterielle', 'maladie_renale_hereditaire', 'uropathie_obstructive',
  ],
  presentation_raisons_debut: [
    'acidose_metabolique', 'autre', 'evenement_cardiovasculaire', 'hyperkaliemie',
    'infection', 'initiation_planifiee', 'probleme_acces', 'surcharge_hydrique', 'symptomes_uremiques',
  ],
  presentation_symptomes: [
    'anorexie', 'asthenie', 'asymptomatique', 'autre', 'douleur_abdominale',
    'dyspnee', 'nausees_ou_vomissements', 'oedemes', 'prurit', 'troubles_neurologiques',
  ],
  traitement_medicaments_renaux_actuels: [
    'antiagregant_ou_anticoagulant', 'antihypertenseur', 'ase', 'autre', 'bicarbonate',
    'calcimimetique', 'chelateur_du_phosphore', 'diuretique', 'fer_iv', 'fer_oral', 'vitamine_d',
  ],
  complication_liste: [
    'autre', 'crise_convulsive', 'dysfonction_acces', 'evenement_cardiovasculaire',
    'hemorragie', 'hypotension', 'infection', 'peritonite', 'thrombose', 'trouble_hydroelectrolytique',
  ],
  complication_motifs_hospitalisation: [
    'autre', 'evenement_cardiovasculaire', 'hemorragie', 'infection',
    'probleme_acces', 'procedure_planifiee', 'surcharge_hydrique', 'trouble_metabolique',
  ],
};

// Schéma complet généré statiquement — ne dépend d'aucune constante définie après
const FALLBACK_SCHEMA_FIELDS = DEFAULT_PATIENT_COLUMN_KEYS
  .map((key, index) => {
    if (AUTO_FIELD_KEYS.has(key)) {
      return { key, id: `fb-${index}`, label: FIELD_LABEL_MAP[key] || key, field_type: 'auto', choices: [], order: index, source_hint: '' };
    }
    let field_type = 'text';
    let choices = [];
    if (DATE_FIELD_KEYS.has(key)) {
      field_type = 'date';
    } else if (NUMERIC_FIELD_KEYS.has(key)) {
      field_type = 'decimal';
    } else if (MULTIPLE_CHOICE_FIELD_MAP[key]) {
      field_type = 'multiple_choice';
      choices = MULTIPLE_CHOICE_FIELD_MAP[key];
    } else if (CHOICE_FIELD_MAP[key]) {
      field_type = 'single_choice';
      choices = CHOICE_FIELD_MAP[key];
    } else if (TEXT_LONG_FIELD_KEYS.has(key)) {
      field_type = 'text_long';
    }
    return {
      key,
      id: `fb-${index}`,
      label: FIELD_LABEL_MAP[key] || key.replace(/_/g, ' '),
      field_type,
      choices,
      order: index,
      source_hint: '',
    };
  });

// Groupement des champs par catégorie
const groupFieldsByCategory = (fields) => {
  const categories = {
    identite:    { label: 'Identité du patient',              fields: [], order: 0 },
    identifiant: { label: 'Identifiants & Statuts',           fields: [], order: 1 },
    demographie: { label: 'Démographie',                      fields: [], order: 2 },
    irc:         { label: 'IRC (Insuffisance Rénale Chronique)', fields: [], order: 3 },
    comorbidite: { label: 'Comorbidités',                         fields: [], order: 4 },
    presentation:{ label: 'Présentation clinique',                fields: [], order: 5 },
    biologie:    { label: 'Biologie',                             fields: [], order: 6 },
    imagerie:    { label: 'Imagerie',                             fields: [], order: 7 },
    dialyse:     { label: 'Dialyse',                              fields: [], order: 8 },
    qualite:     { label: 'Qualité des soins',                    fields: [], order: 9 },
    traitement:  { label: 'Traitements',                          fields: [], order: 10 },
    complication:{ label: 'Complications',                         fields: [], order: 11 },
    devenir:     { label: 'Devenir du patient',                   fields: [], order: 12 },
  };

  // Champs identité patient (nom, prenom) — toujours en tête
  const IDENTITE_KEYS = new Set(['nom', 'prenom']);

  // Champs identifiants & statuts (hors nom/prenom)
  const IDENTIFIANT_KEYS = new Set([
    'id_patient', 'id_enregistrement_source', 'id_site',
    'statut_inclusion', 'statut_consentement', 'date_evaluation_initiale',
    'utilisateur_saisie', 'derniere_mise_a_jour',
  ]);

  const categoryPrefixes = {
    demographie: ['demographie_'],
    irc:         ['irc_'],
    comorbidite: ['comorbidite_', 'icc_'],
    presentation:['presentation_'],
    biologie:    ['biologie_'],
    imagerie:    ['imagerie_'],
    dialyse:     ['dialyse_', 'transplantation_', 'immunologie_'],
    qualite:     ['qualite_', 'education_'],
    traitement:  ['traitement_'],
    complication:['complication_'],
    devenir:     ['devenir_'],
  };

  fields.forEach(field => {
    const key = field.key;

    // 1. Identité en premier
    if (IDENTITE_KEYS.has(key)) {
      categories.identite.fields.push(field);
      return;
    }
    // 2. Identifiants & statuts
    if (IDENTIFIANT_KEYS.has(key)) {
      categories.identifiant.fields.push(field);
      return;
    }
    // 3. Sections par préfixe
    for (const [category, keywords] of Object.entries(categoryPrefixes)) {
      if (keywords.some(kw => key.startsWith(kw))) {
        categories[category].fields.push(field);
        return;
      }
    }
    // 4. Fallback : identifiants si pas trouvé ailleurs
    categories.identifiant.fields.push(field);
  });

  return Object.values(categories)
    .filter(cat => cat.fields.length > 0)
    .sort((a, b) => a.order - b.order);
};

const SIMILAR_SCHEMA_FALLBACK_MAP = {
  demographie_sexe: 'sexe',
  demographie_age_ans: 'age',
  demographie_date_naissance: 'date_naissance',
  irc_etiologie_principale: 'maladie',
};

const EXTRA_DATA_FALLBACK_KEYS = {
  demographie_sexe: ['sex', 'gender', 'sexe'],
  demographie_date_naissance: ['date_of_birth', 'birth_date', 'naissance'],
  irc_etiologie_principale: ['ckd_etiology', 'diagnostic'],
  id_patient: ['patient_id'],
  age: ['age_years'],
};

const EXPLICIT_BIRTH_DATE_KEYS = [
  'date_of_birth', 'birth_date', 'dob', 'birthdate',
  'date_birth', 'naissance', 'demographie_date_naissance', 'date_naissance',
];

const safeStringify = (value) => {
  if (value === null || value === undefined || value === '') {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  return JSON.stringify(value);
};

const escapeCsvCell = (value) => {
  return String(value)
    .replaceAll('"', '""');
};

const extractApiMessage = (requestError, fallbackMessage) => {
  if (!requestError?.response) {
    return 'Connexion API impossible. Verifiez que le backend Django est demarre et accessible sur http://localhost:8000/api/.';
  }

  const status = requestError?.response?.status;
  const data = requestError?.response?.data;

  if (typeof data === 'string') {
    if (status === 404) {
      return 'Endpoint patients introuvable. Redémarrez le backend Django.';
    }
    if (status === 401 || status === 403) {
      return 'Accès refusé à l’API patients pour ce compte.';
    }
    return data;
  }

  const message = data?.error
    || data?.detail
    || (data ? Object.values(data)[0] : null);

  return message || fallbackMessage;
};

const shouldDisplayBirthYearOnly = (patient, rawValue) => {
  if (!rawValue || !patient) {
    return false;
  }

  // Cas 1 — flag explicite posé par le backend lors de l'import depuis un âge
  if (patient?.extra_data?.demographie_date_naissance_estimee === true) {
    return true;
  }

  const date = new Date(String(rawValue));
  if (Number.isNaN(date.getTime())) {
    return false;
  }

  // Cas 2 — heuristique : date au 01/01 avec année cohérente avec l'âge,
  // et aucune vraie date de naissance explicite dans extra_data
  const age = Number(patient?.age);
  if (!Number.isFinite(age) || age < 0) {
    return false;
  }

  const hasExplicitBirthDate = EXPLICIT_BIRTH_DATE_KEYS.some((key) => {
    const value = patient?.extra_data?.[key];
    return value !== undefined && value !== null && String(value).trim() !== '';
  });
  if (hasExplicitBirthDate) {
    return false;
  }

  const today = new Date();
  const expectedYear = today.getFullYear() - Math.trunc(age);
  const isJanFirst = date.getMonth() === 0 && date.getDate() === 1;
  return isJanFirst && date.getFullYear() === expectedYear;
};

const formatBirthDateDisplay = (patient, schemaKey, rawValue) => {
  if (!['date_naissance', 'demographie_date_naissance'].includes(schemaKey)) {
    return rawValue;
  }

  if (!rawValue) {
    return rawValue;
  }

  if (shouldDisplayBirthYearOnly(patient, rawValue)) {
    // Afficher seulement l'année — la date complète est une estimation depuis l'âge
    return String(rawValue).slice(0, 4);
  }

  return rawValue;
};

// Composant principal
function PatientsManagement() {
  const INITIAL_DYNAMIC_COLUMNS_LIMIT = 20;
  const INITIAL_ROWS_LIMIT = 100;
  const { user } = useContext(AuthContext);
  const { language, t } = useLanguage();
  const roleLabel = useMemo(() => {
    if (!user?.role) return 'Utilisateur';
    const mapping = {
      super_admin: 'Super Administrateur',
      chef_service: 'Chef de service',
      professeur: 'Professeur',
      resident: 'Résident',
    };
    return mapping[user.role] || 'Utilisateur';
  }, [user?.role]);
  const validatorPhrase = `Vous, en tant que ${roleLabel.toLowerCase()},`;
  const navigate = useNavigate();
  const location = useLocation();
  const fileInputRef = useRef(null);
  const [patients, setPatients] = useState([]);
  const [schemaTemplate, setSchemaTemplate] = useState(null);
  const [schemaAnswers, setSchemaAnswers] = useState({});
  const [form, setForm] = useState(emptyForm);
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [extraDataValues, setExtraDataValues] = useState({});
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [purging, setPurging] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [importDynamicColumns, setImportDynamicColumns] = useState(null); // { columns: [], newCount: int }
  const [insertValidationStatus, setInsertValidationStatus] = useState(() => {
    try {
      const saved = localStorage.getItem('patients_insert_validation_status');
      return saved ? JSON.parse(saved) : { status: 'idle', approvedBy: null, requestedBy: null, timestamp: null, pendingIds: [] };
    } catch {
      return { status: 'idle', approvedBy: null, requestedBy: null, timestamp: null, pendingIds: [] };
    }
  });
  // Default to showing a limited number of rows to avoid large initial DOMs
  const [showAllRows, setShowAllRows] = useState(false);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  // Toggle visibility for the compact filter panel
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [selectedPatientIds, setSelectedPatientIds] = useState([]);
  const [deletingSelection, setDeletingSelection] = useState(false);
  const [rejectingInsertion, setRejectingInsertion] = useState(false);
  const [mainSection, setMainSection] = useState('data_patient');
  const [activeTab, setActiveTab] = useState('gestion');
  const [analysisView, setAnalysisView] = useState('synthese');
  const [profile3dAngle, setProfile3dAngle] = useState(35);

  useEffect(() => {
    try {
      localStorage.setItem('patients_insert_validation_status', JSON.stringify(insertValidationStatus));
    } catch {
      // ignore storage errors
    }
  }, [insertValidationStatus]);

  useEffect(() => {
    if (location.pathname.startsWith('/modele-ai')) {
      setMainSection('modele_ai');
      return;
    }
    setMainSection('data_patient');
  }, [location.pathname]);

  const isValidationPending = insertValidationStatus.status === 'pending';
  const isValidationValidated = insertValidationStatus.status === 'validated';
  const canValidateInsertion = ['chef_service', 'super_admin'].includes(user?.role);
  const canPurgeImportedData = ['chef_service', 'super_admin'].includes(user?.role);
  const formattedValidationTimestamp = insertValidationStatus.timestamp
    ? new Date(insertValidationStatus.timestamp).toLocaleString('fr-FR')
    : null;

  useEffect(() => {
    const validIdSet = new Set(patients.map((patient) => getPatientUniqueId(patient)));
    setSelectedPatientIds((current) => current.filter((id) => validIdSet.has(id)));
  }, [patients]);

  const schemaFieldKeySet = useMemo(() => {
    return new Set((schemaTemplate?.fields || []).map((field) => field.key));
  }, [schemaTemplate]);

  const extraColumns = useMemo(() => {
    const keys = new Set();
    patients.forEach((patient) => {
      Object.keys(patient.extra_data || {}).forEach((key) => keys.add(key));
    });
    return Array.from(keys).filter((key) => !schemaFieldKeySet.has(key) && !key.toLowerCase().startsWith('unnamed'));
  }, [patients, schemaFieldKeySet]);

  // Colonnes extra_data dans le formulaire : seulement si insertion validée
  const formDynamicExtraColumns = useMemo(() => {
    if (insertValidationStatus.status !== 'validated') return [];
    const keys = new Set();
    Object.keys(extraDataValues || {}).forEach((key) => {
      // Exclure les clés de validation interne
      if (key.startsWith('insertion_validation_')) return;
      if (!schemaFieldKeySet.has(key) && !key.toLowerCase().startsWith('unnamed')) {
        keys.add(key);
      }
    });
    return Array.from(keys).sort((a, b) => a.localeCompare(b));
  }, [extraDataValues, schemaFieldKeySet, insertValidationStatus.status]);

  const getPatientUniqueId = (patient) => {
    return patient?.id ?? patient?.id_patient ?? patient?.id_enregistrement_source ?? '';
  };

  const flattenPatientRow = (patient) => {
    const flat = { ...patient };
    if (patient?.extra_data && typeof patient.extra_data === 'object') {
      Object.entries(patient.extra_data).forEach(([key, value]) => {
        if (key !== 'id' && key !== 'id_patient') {
          flat[key] = value;
        }
      });
    }

    Object.values(SECTION_FIELD_MAP).forEach((sectionField) => {
      if (patient?.[sectionField] && typeof patient[sectionField] === 'object') {
        Object.entries(patient[sectionField]).forEach(([key, value]) => {
          if (key !== 'id' && key !== 'id_patient') {
            flat[key] = value;
          }
        });
      }
    });

    return flat;
  };

  const filteredPatients = useMemo(() => {
    const idTerm = String(appliedFilters.id_patient || '').trim().toLowerCase();
    const nameTerm = String(appliedFilters.search || '').trim().toLowerCase();
    const sexTerm = String(appliedFilters.sexe || '').trim().toLowerCase();
    const ageMin = appliedFilters.age_min === '' ? null : Number(appliedFilters.age_min);
    const ageMax = appliedFilters.age_max === '' ? null : Number(appliedFilters.age_max);

    return patients.filter((patient) => {
      const flat = flattenPatientRow(patient);
      const patientIdValue = String(flat.id_patient ?? patient.id_patient ?? '').toLowerCase();
      const nomValue = String(flat.nom ?? patient.nom ?? '').toLowerCase();
      const prenomValue = String(flat.prenom ?? patient.prenom ?? '').toLowerCase();
      const sexeValue = String(flat.sexe ?? flat.demographie_sexe ?? patient.sexe ?? '').toLowerCase();
      const ageRawValue = flat.age ?? flat.demographie_age_ans ?? patient.age;
      const ageValue = ageRawValue === '' || ageRawValue === null || ageRawValue === undefined
        ? null
        : Number(ageRawValue);

      if (idTerm && !patientIdValue.includes(idTerm)) {
        return false;
      }

      if (nameTerm && !nomValue.includes(nameTerm) && !prenomValue.includes(nameTerm)) {
        return false;
      }

      if (sexTerm && sexeValue !== sexTerm) {
        return false;
      }

      if (ageMin !== null && Number.isFinite(ageMin)) {
        if (ageValue === null || !Number.isFinite(ageValue) || ageValue < ageMin) {
          return false;
        }
      }

      if (ageMax !== null && Number.isFinite(ageMax)) {
        if (ageValue === null || !Number.isFinite(ageValue) || ageValue > ageMax) {
          return false;
        }
      }

      return true;
    });
  }, [appliedFilters, patients]);

  const visiblePatients = useMemo(() => {
    if (showAllRows) {
      return filteredPatients;
    }
    return filteredPatients.slice(0, INITIAL_ROWS_LIMIT);
  }, [filteredPatients, showAllRows]);

  const tableSchemaFields = useMemo(() => {
    const fields = schemaTemplate?.fields || DEFAULT_SCHEMA_TEMPLATE.fields;
    // On masque la colonne patient_id (identifiant externe)
    return [...fields].filter((field) => field.key !== 'patient_id').sort((a, b) => (a.order || 0) - (b.order || 0));
  }, [schemaTemplate]);

  const fixedBaseColumns = useMemo(() => {
    return FIXED_BASE_COLUMNS;
  }, []);

  // Colonnes dynamiques dans le tableau : visibles dès qu'elles existent dans le schéma
  const dynamicColumnKeys = useMemo(() => {
    const fields = schemaTemplate?.fields || [];
    return new Set(
      fields
        .filter((f) => f.source_hint === 'dynamic_column')
        .map((f) => f.key)
    );
  }, [schemaTemplate]);











  const tableDisplaySchemaFields = useMemo(() => {
    const fixedKeys = new Set(FIXED_BASE_COLUMNS.map((column) => column.key));
    return tableSchemaFields.filter((field) => !fixedKeys.has(field.key));
  }, [tableSchemaFields]);

  const columnLabelMap = useMemo(() => {
    const map = {};
    tableSchemaFields.forEach((f) => { if (f.label) map[f.key] = f.label; });
    return map;
  }, [tableSchemaFields]);

  const patientColumnKeys = useMemo(() => {
    const orderedKeys = Array.from(DEFAULT_PATIENT_COLUMN_KEYS);
    const seenKeys = new Set(orderedKeys);

    // Ajouter toutes les colonnes du schema non fixes.
    // Important: certaines anciennes colonnes importees peuvent ne pas avoir
    // source_hint='dynamic_column' mais doivent quand meme etre visibles.
    tableDisplaySchemaFields.forEach((field) => {
      if (!seenKeys.has(field.key)) {
        seenKeys.add(field.key);
        orderedKeys.push(field.key);
      }
    });

    return orderedKeys;
  }, [tableDisplaySchemaFields]);

  const orderedSchemaFieldsForForm = useMemo(() => {
    const schemaFieldMap = new Map(tableSchemaFields.map((field) => [field.key, field]));
    return patientColumnKeys
      .map((key) => schemaFieldMap.get(key))
      .filter(Boolean);
  }, [patientColumnKeys, tableSchemaFields]);

  // Champs fixes du schéma plateforme (non dynamiques)
  // Un champ est "fixe" s'il fait partie des colonnes natives de la plateforme
  // (DEFAULT_PATIENT_COLUMN_KEYS) OU s'il n'a pas source_hint='dynamic_column'.
  // Si le schéma JSON est vide, on utilise FALLBACK_SCHEMA_FIELDS qui couvre
  // tous les champs de DEFAULT_PATIENT_COLUMN_KEYS avec types et labels corrects.
  const fixedSchemaFieldsForForm = useMemo(() => {
    const platformKeys = new Set(DEFAULT_PATIENT_COLUMN_KEYS);
    const filtered = orderedSchemaFieldsForForm.filter((field) => {
      if (field.source_hint === 'dynamic_column') return false;
      if (field.source_hint && field.source_hint !== '' && !platformKeys.has(field.key)) return false;
      return true;
    });
    // Si moins de la moitié des champs de la plateforme sont présents dans le schéma chargé,
    // on utilise le fallback complet pour garantir l'affichage de tous les champs.
    const expectedTotal = DEFAULT_PATIENT_COLUMN_KEYS.length;
    const filteredCount = filtered.length;
    if (filteredCount < expectedTotal * 0.5) {
      return FALLBACK_SCHEMA_FIELDS;
    }
    return filtered;
  }, [orderedSchemaFieldsForForm]);

  // Champs dynamiques du schéma (colonnes importées automatiquement non connues de la plateforme)
  // Colonnes dynamiques : visibles dans les formulaires d'ajout ET de modification dès qu'elles
  // existent dans le schéma (indépendamment du statut de validation de l'insertion en cours).
  const dynamicSchemaFieldsForForm = useMemo(() => {
    const platformKeys = new Set(DEFAULT_PATIENT_COLUMN_KEYS);
    return orderedSchemaFieldsForForm.filter((field) => {
      if (field.source_hint === 'dynamic_column') return true;
      // Champ avec source_hint (vient de l'API) mais absent des colonnes natives
      if (field.source_hint && field.source_hint !== '' && !platformKeys.has(field.key)) return true;
      return false;
    });
  }, [orderedSchemaFieldsForForm]);

  const selectedVisibleCount = useMemo(() => {
    const visibleIdSet = new Set(visiblePatients.map((patient) => getPatientUniqueId(patient)));
    return selectedPatientIds.filter((id) => visibleIdSet.has(id)).length;
  }, [selectedPatientIds, visiblePatients]);

  const allVisibleSelected = visiblePatients.length > 0 && selectedVisibleCount === visiblePatients.length;

  const selectedPatientsCountLabel = selectedPatientIds.length > 1
    ? `${selectedPatientIds.length} lignes selectionnees`
    : selectedPatientIds.length === 1
      ? '1 ligne selectionnee'
      : 'Aucune ligne selectionnee';

  const getSectionFieldBySchemaKey = (schemaKey) => {
    const sectionPrefix = Object.keys(SECTION_FIELD_MAP).find((prefix) => schemaKey.startsWith(prefix));
    if (!sectionPrefix) {
      return null;
    }
    return SECTION_FIELD_MAP[sectionPrefix];
  };

  const schemaBooleanFieldKeys = useMemo(() => {
    const keys = new Set();
    tableSchemaFields.forEach((field) => {
      const choices = (field.choices || []).map((choice) => String(choice).trim().toLowerCase());
      const hasOuiNonChoices = choices.length > 0 && choices.every((choice) => ['oui', 'non'].includes(choice));
      if (field.field_type === 'boolean' || hasOuiNonChoices) {
        keys.add(field.key);
      }
    });
    return keys;
  }, [tableSchemaFields]);

  const extraBinaryColumnKeys = useMemo(() => {
    const keys = new Set();
    // Heuristique plus stricte : requiert au moins `minSamples` valeurs non vides
    // et un pourcentage `threshold` de valeurs binaires (oui/non) pour éviter
    // de marquer à tort des colonnes contenant des suffixes ou des valeurs mixtes.
    const minSamples = 3;
    const threshold = 0.85; // 85%

    extraColumns.forEach((columnKey) => {
      let nonEmptyCount = 0;
      let binaryMatchCount = 0;

      for (const patient of patients) {
        const raw = patient?.extra_data?.[columnKey];
        if (raw === null || raw === undefined || raw === '') continue;

        nonEmptyCount += 1;
        const normalized = String(raw).trim().toLowerCase();
        if (BOOLEAN_TRUE_VALUES.includes(normalized) || BOOLEAN_FALSE_VALUES.includes(normalized)) {
          binaryMatchCount += 1;
        }
        // small optimisation: stop early if we have many samples
        if (nonEmptyCount >= 50) break;
      }

      if (nonEmptyCount >= minSamples && (binaryMatchCount / nonEmptyCount) >= threshold) {
        keys.add(columnKey);
      }
    });
    // Debug: log candidate columns and ratios in development to help trace false-positives
    if (process.env.NODE_ENV !== 'production') {
      const debugArr = [];
      extraColumns.forEach((columnKey) => {
        let nonEmpty = 0;
        let binary = 0;
        for (const p of patients) {
          const raw = p?.extra_data?.[columnKey];
          if (raw === null || raw === undefined || raw === '') continue;
          nonEmpty += 1;
          const normalized = String(raw).trim().toLowerCase();
          if (BOOLEAN_TRUE_VALUES.includes(normalized) || BOOLEAN_FALSE_VALUES.includes(normalized)) binary += 1;
          if (nonEmpty >= 50) break;
        }
        if (nonEmpty > 0) debugArr.push({ columnKey, nonEmpty, binary, ratio: +(binary / nonEmpty).toFixed(3) });
      });
      // Small, readable console output
      console.debug('[PatientsManagement] extraBinaryColumnKeys debug', debugArr.filter(d => d.nonEmpty >= 1).slice(0, 200));
    }
    return keys;
  }, [extraColumns, patients]);

  const formatSchemaValue = (schemaKey, value) => {
    if (schemaBooleanFieldKeys.has(schemaKey)) {
      return toBooleanDisplay(value);
    }
    return value;
  };

  const formatExtraValue = (columnKey, value) => {
    if (extraBinaryColumnKeys.has(columnKey)) {
      return toBooleanDisplay(value);
    }
    return value;
  };

  const resolveTableCellValue = (patient, schemaKey) => {
    if (patient?.[schemaKey] !== undefined && patient?.[schemaKey] !== null && patient?.[schemaKey] !== '') {
      const raw = patient[schemaKey];
      if (schemaKey === 'sexe' || schemaKey === 'demographie_sexe') {
        return normalizeSexDisplay(sexLabels[raw] || raw);
      }
      return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, raw));
    }

    const mappedField = PATIENT_FIELD_MAP[schemaKey];
    if (mappedField) {
      const raw = patient?.[mappedField];
      if (schemaKey === 'sexe' || schemaKey === 'demographie_sexe') {
        return normalizeSexDisplay(sexLabels[raw] || raw);
      }
      return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, raw));
    }

    const sectionPrefix = Object.keys(SECTION_FIELD_MAP).find((prefix) => schemaKey.startsWith(prefix));
    if (sectionPrefix) {
      const sectionField = SECTION_FIELD_MAP[sectionPrefix];
      const valueFromSection = patient?.[sectionField]?.[schemaKey];
      if (valueFromSection !== undefined && valueFromSection !== null && valueFromSection !== '') {
        if (schemaKey === 'demographie_sexe') {
          return normalizeSexDisplay(valueFromSection);
        }
        return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, valueFromSection));
      }
    }

    const fallbackField = SIMILAR_SCHEMA_FALLBACK_MAP[schemaKey];
    if (fallbackField) {
      const fallbackRaw = patient?.[fallbackField];
      if (fallbackRaw !== undefined && fallbackRaw !== null && fallbackRaw !== '') {
        if (fallbackField === 'sexe' || schemaKey === 'demographie_sexe') {
          return normalizeSexDisplay(sexLabels[fallbackRaw] || fallbackRaw);
        }
        return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, fallbackRaw));
      }
    }

    const extraFallbackKeys = EXTRA_DATA_FALLBACK_KEYS[schemaKey] || [];
    for (const candidateKey of extraFallbackKeys) {
      const candidateValue = patient?.extra_data?.[candidateKey];
      if (candidateValue !== undefined && candidateValue !== null && candidateValue !== '') {
        if (schemaKey === 'demographie_sexe' || schemaKey === 'sexe') {
          return normalizeSexDisplay(candidateValue);
        }
        return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, candidateValue));
      }
    }

    const raw = patient?.extra_data?.[schemaKey] ?? patient?.extra_data?.[schemaKey.replaceAll('_', ' ')] ?? null;
    return formatBirthDateDisplay(patient, schemaKey, formatSchemaValue(schemaKey, raw));
  };

  const getEditableFieldValue = (patient, field) => {
    if (!patient || !field?.key) {
      return field?.field_type === 'multiple_choice' ? [] : '';
    }

    const schemaKey = field.key;
    let value;

    // 1. Try PATIENT_FIELD_MAP
    if (PATIENT_FIELD_MAP[schemaKey] && patient[PATIENT_FIELD_MAP[schemaKey]] !== undefined) {
      value = patient[PATIENT_FIELD_MAP[schemaKey]];
    }
    // 2. Try direct patient key
    else if (patient[schemaKey] !== undefined && patient[schemaKey] !== null && patient[schemaKey] !== '') {
      value = patient[schemaKey];
    }
    // 3. Try SECTION_FIELD_MAP (e.g., comorbidite_liste from comorbidite_data)
    else {
      const sectionPrefix = Object.keys(SECTION_FIELD_MAP).find((prefix) => schemaKey.startsWith(prefix));
      if (sectionPrefix) {
        const sectionField = SECTION_FIELD_MAP[sectionPrefix];
        const valueFromSection = patient?.[sectionField]?.[schemaKey];
        if (valueFromSection !== undefined && valueFromSection !== null && valueFromSection !== '') {
          value = valueFromSection;
        }
      }
    }

    // 4. Try SIMILAR_SCHEMA_FALLBACK_MAP
    if (value === undefined) {
      const fallbackField = SIMILAR_SCHEMA_FALLBACK_MAP[schemaKey];
      if (fallbackField) {
        const fallbackValue = patient?.[fallbackField];
        if (fallbackValue !== undefined && fallbackValue !== null && fallbackValue !== '') {
          value = fallbackValue;
        }
      }
    }

    // 5. Try EXTRA_DATA_FALLBACK_KEYS
    if (value === undefined) {
      const extraFallbackKeys = EXTRA_DATA_FALLBACK_KEYS[schemaKey] || [];
      for (const candidateKey of extraFallbackKeys) {
        const candidateValue = patient?.extra_data?.[candidateKey];
        if (candidateValue !== undefined && candidateValue !== null && candidateValue !== '') {
          value = candidateValue;
          break;
        }
      }
    }

    // 6. Try extra_data with direct key or with key replacement
    if (value === undefined) {
      const extraValue = patient?.extra_data?.[schemaKey] ?? patient?.extra_data?.[schemaKey.replaceAll('_', ' ')];
      if (extraValue !== undefined && extraValue !== null && extraValue !== '') {
        value = extraValue;
      }
    }

    // Convert string arrays or JSON to proper array format for multiple_choice fields
    if (field.field_type === 'multiple_choice') {
      const normalizeChoiceToken = (rawToken) => String(rawToken || '')
        .trim()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, '_');

      const normalizeMultipleChoiceValues = (rawValues) => {
        const validChoices = new Set((field.choices || []).map((choice) => String(choice).toLowerCase()));
        return rawValues
          .map((item) => {
            const token = normalizeChoiceToken(item);
            if (!token) return null;
            return validChoices.has(token) ? token : null;
          })
          .filter((item) => item);
      };

      if (Array.isArray(value)) {
        return normalizeMultipleChoiceValues(value);
      }
      if (typeof value === 'string' && value.trim()) {
        // Try parsing as JSON array first
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed)) {
            return normalizeMultipleChoiceValues(parsed);
          }
        } catch (e) {
          // Not JSON, try delimiter-separated values
        }
        // Support comma, semicolon and pipe delimiters from import files.
        return normalizeMultipleChoiceValues(value.split(/[,;|]/));
      }
      return [];
    }

    return value ?? '';
  };

  const analysisSummary = useMemo(() => {
    // Skip heavy analysis when the user is not viewing the Analyse tab.
    if (activeTab !== 'analyse') {
      return {
        totalPatients: patients.length,
        averageAge: '-',
        medianAge: '-',
        inclusionCount: 0,
        averageCompleteness: 0,
        recentActivityCount: 0,
        highBurdenPatients: 0,
        sexCounts: [],
        inclusionCounts: [],
        ageBands: [],
        topEtiologies: [],
        topComorbidities: [],
        monthlyInclusions: [],
        monthlyComplications: [],
        etiologyInclusionGrouped: { labels: [], datasets: [] },
        ageSexDistribution: [],
        topComorbidityCombinations: [],
        profile3dPoints: [],
        weakestColumns: [],
        strongestSections: [],
      };
    }
    const totalPatients = patients.length;
    const ageValues = patients
      .map((patient) => Number(patient?.age))
      .filter((age) => Number.isFinite(age) && age >= 0);

    const sortedAgeValues = [...ageValues].sort((a, b) => a - b);
    const medianAge = sortedAgeValues.length
      ? (() => {
          const middle = Math.floor(sortedAgeValues.length / 2);
          if (sortedAgeValues.length % 2 === 0) {
            return ((sortedAgeValues[middle - 1] + sortedAgeValues[middle]) / 2).toFixed(1);
          }
          return sortedAgeValues[middle].toFixed(1);
        })()
      : '-';

    const averageAge = ageValues.length
      ? (ageValues.reduce((acc, age) => acc + age, 0) / ageValues.length).toFixed(1)
      : '-';

    const sexCountsMap = { Homme: 0, Femme: 0, Inconnu: 0 };
    patients.forEach((patient) => {
      const normalizedSex = normalizeSexDisplay(sexLabels[patient?.sexe] || patient?.sexe || 'Inconnu');
      if (normalizedSex === 'Homme') {
        sexCountsMap.Homme += 1;
      } else if (normalizedSex === 'Femme') {
        sexCountsMap.Femme += 1;
      } else {
        sexCountsMap.Inconnu += 1;
      }
    });

    const inclusionMap = {};
    patients.forEach((patient) => {
      const raw = resolveTableCellValue(patient, 'statut_inclusion');
      if (isNoResponseValue(raw)) {
        return;
      }
      const key = String(raw).trim();
      inclusionMap[key] = (inclusionMap[key] || 0) + 1;
    });

    const ageBandsMap = {
      '0-20': 0,
      '21-40': 0,
      '41-60': 0,
      '61-80': 0,
      '81+': 0,
    };

    ageValues.forEach((age) => {
      if (age <= 20) {
        ageBandsMap['0-20'] += 1;
      } else if (age <= 40) {
        ageBandsMap['21-40'] += 1;
      } else if (age <= 60) {
        ageBandsMap['41-60'] += 1;
      } else if (age <= 80) {
        ageBandsMap['61-80'] += 1;
      } else {
        ageBandsMap['81+'] += 1;
      }
    });

    const etiologyMap = {};
    patients.forEach((patient) => {
      const etiologyValue = resolveTableCellValue(patient, 'irc_etiologie_principale');
      if (isNoResponseValue(etiologyValue)) {
        return;
      }
      const key = String(etiologyValue).trim();
      etiologyMap[key] = (etiologyMap[key] || 0) + 1;
    });

    const monthlyInclusionMap = {};
    const monthlyComplicationMap = {};
    const etiologyInclusionMap = {};

    patients.forEach((patient) => {
      // Prefer an explicit evaluation/admission date, but fall back to
      // the record creation timestamp so we still show monthly trends
      // when `statut_inclusion` is not filled by imports.
      const monthKey = [
        patient?.date_evaluation_initiale,
        patient?.date_admission,
        patient?.created_at,
        patient?.derniere_mise_a_jour,
        patient?.date_naissance,
      ]
        .map((candidateDate) => toMonthKey(candidateDate))
        .find(Boolean);

      const inclusionValueRaw = resolveTableCellValue(patient, 'statut_inclusion');
      const inclusionLabel = isNoResponseValue(inclusionValueRaw) ? 'Non renseigne' : String(inclusionValueRaw).trim();

      const etiologyRaw = resolveTableCellValue(patient, 'irc_etiologie_principale');
      const etiologyLabel = isNoResponseValue(etiologyRaw) ? 'Non renseignee' : String(etiologyRaw).trim();

      if (!etiologyInclusionMap[etiologyLabel]) {
        etiologyInclusionMap[etiologyLabel] = {};
      }
      etiologyInclusionMap[etiologyLabel][inclusionLabel] = (etiologyInclusionMap[etiologyLabel][inclusionLabel] || 0) + 1;

      if (monthKey) {
        // Count the patient for monthly inclusions whenever we have a
        // usable month key. This makes the chart represent monthly
        // patient additions even when `statut_inclusion` is not set.
        monthlyInclusionMap[monthKey] = (monthlyInclusionMap[monthKey] || 0) + 1;

        if (!monthlyComplicationMap[monthKey]) {
          monthlyComplicationMap[monthKey] = {
            documented: 0,
            hospitalizations: 0,
            hospitalizationDays: 0,
          };
        }

        const complicationList = String(patient?.complication_liste || '').trim();
        const hospitalizationCount = Number(String(patient?.complication_nombre_hospitalisations || '').replace(',', '.'));
        const hospitalizationDays = Number(String(patient?.complication_jours_hospitalisation || '').replace(',', '.'));

        if (complicationList) {
          monthlyComplicationMap[monthKey].documented += 1;
        }
        if (Number.isFinite(hospitalizationCount) && hospitalizationCount > 0) {
          monthlyComplicationMap[monthKey].hospitalizations += hospitalizationCount;
        }
        if (Number.isFinite(hospitalizationDays) && hospitalizationDays > 0) {
          monthlyComplicationMap[monthKey].hospitalizationDays += hospitalizationDays;
        }
      }
    });

    const comorbidityFieldMap = new Map();

    tableDisplaySchemaFields
      .filter((field) => field.key.startsWith('comorbidite_'))
      .forEach((field) => {
        comorbidityFieldMap.set(field.key, {
          key: field.key,
          label: field.label,
          getValue: (patient) => resolveTableCellValue(patient, field.key),
        });
      });

    patients.forEach((patient) => {
      Object.keys(patient?.comorbidite_data || {}).forEach((key) => {
        if (!comorbidityFieldMap.has(key)) {
          comorbidityFieldMap.set(key, {
            key,
            label: key,
            getValue: (p) => p?.comorbidite_data?.[key],
          });
        }
      });

      Object.keys(patient?.extra_data || {}).forEach((key) => {
        const normalized = String(key).toLowerCase();
        if ((normalized.startsWith('comorbidite_') || normalized.includes('comorbid')) && !comorbidityFieldMap.has(key)) {
          comorbidityFieldMap.set(key, {
            key,
            label: key,
            getValue: (p) => p?.extra_data?.[key],
          });
        }
      });
    });

    const comorbidityFields = Array.from(comorbidityFieldMap.values());
    const comorbidityMap = {};
    const comorbidityCombinationMap = {};
    const profile3dPoints = [];
    const recentActivityThresholdMs = 90 * 24 * 60 * 60 * 1000;
    const nowTs = Date.now();
    let recentActivityCount = 0;
    let highBurdenPatients = 0;

    const extractComorbidityLabels = (patient) => {
      const labels = new Set();

      const rawList = patient?.comorbidite_liste;
      if (typeof rawList === 'string' && rawList.trim()) {
        rawList
          .split(/[,;/|+]/)
          .map((item) => item.trim())
          .filter(Boolean)
          .forEach((item) => labels.add(item));
      }

      comorbidityFields.forEach((field) => {
        const rawValue = field.getValue(patient);
        if (isPositiveClinicalValue(rawValue)) {
          labels.add(field.label);
        }
      });

      return Array.from(labels).sort((a, b) => a.localeCompare(b));
    };

    comorbidityFields.forEach((field) => {
      let count = 0;

      patients.forEach((patient) => {
        const rawValue = field.getValue(patient);
        if (isNoResponseValue(rawValue)) {
          return;
        }

        const normalized = String(rawValue).trim().toLowerCase();
        const isExplicitFalse = BOOLEAN_FALSE_VALUES.includes(normalized) || ['absent', 'negative', 'negatif'].includes(normalized);
        if (!isExplicitFalse) {
          count += 1;
        }
      });

      if (count > 0) {
        comorbidityMap[field.label] = count;
      }
    });

    patients.forEach((patient) => {
      const positives = extractComorbidityLabels(patient);

      const age = Number(patient?.age);
      if (Number.isFinite(age) && age >= 0) {
        const complicationCount = [
          patient?.complication_liste,
          patient?.complication_nombre_hospitalisations,
          patient?.complication_jours_hospitalisation,
          patient?.complication_date_premier_evenement,
        ].some((value) => !isNoResponseValue(value)) ? 1 : 0;
        const sex = normalizeSexDisplay(sexLabels[patient?.sexe] || patient?.sexe || 'Inconnu');
        const inclusion = resolveTableCellValue(patient, 'statut_inclusion');

        const latestActivityTs = [
          patient?.updated_at,
          patient?.created_at,
          patient?.date_admission,
          patient?.date_evaluation_initiale,
        ]
          .map((candidateDate) => toDateOrNull(candidateDate)?.getTime())
          .filter((value) => Number.isFinite(value))
          .sort((a, b) => b - a)[0];

        if (latestActivityTs && (nowTs - latestActivityTs) <= recentActivityThresholdMs) {
          recentActivityCount += 1;
        }

        const burdenScore = positives.length + complicationCount;
        if ((age >= 60 && burdenScore >= 3) || burdenScore >= 4) {
          highBurdenPatients += 1;
        }

        profile3dPoints.push({
          age,
          comorbidityCount: positives.length,
          complicationCount,
          sex,
          inclusion: isNoResponseValue(inclusion) ? 'Non renseigne' : String(inclusion),
        });
      }

      if (positives.length < 2) {
        return;
      }

      const combinationLabel = positives.slice(0, 3).join(' + ');
      comorbidityCombinationMap[combinationLabel] = (comorbidityCombinationMap[combinationLabel] || 0) + 1;
    });

    const qualityColumns = [
      ...fixedBaseColumns.map((column) => ({ key: column.key, label: column.label, isExtra: false })),
      ...tableDisplaySchemaFields.map((field) => ({ key: field.key, label: field.label, isExtra: false })),
    ];

    const fillRates = qualityColumns.map((column) => {
      const filled = patients.reduce((acc, patient) => {
        const rawValue = column.isExtra
          ? patient?.extra_data?.[column.key]
          : resolveTableCellValue(patient, column.key);
        return acc + (isNoResponseValue(rawValue) ? 0 : 1);
      }, 0);
      const rate = totalPatients ? Math.round((filled / totalPatients) * 100) : 0;
      return { key: column.key, label: column.label, rate, isExtra: column.isExtra };
    }).sort((a, b) => a.rate - b.rate);

    const averageCompleteness = fillRates.length
      ? Math.round(fillRates.reduce((acc, item) => acc + item.rate, 0) / fillRates.length)
      : 0;

    const completenessSections = [
      { prefix: 'demographie_', label: 'Démographie' },
      { prefix: 'irc_', label: 'IRC' },
      { prefix: 'comorbidite_', label: 'Comorbidités' },
      { prefix: 'presentation_', label: 'Présentation' },
      { prefix: 'biologie_', label: 'Biologie' },
      { prefix: 'imagerie_', label: 'Imagerie' },
      { prefix: 'dialyse_', label: 'Dialyse' },
      { prefix: 'qualite_', label: 'Qualité' },
      { prefix: 'complication_', label: 'Complications' },
      { prefix: 'traitement_', label: 'Traitement' },
      { prefix: 'devenir_', label: 'Devenir' },
    ]
      .map((section) => {
        const sectionRates = fillRates.filter((item) => item.key.startsWith(section.prefix));
        const rate = sectionRates.length
          ? Math.round(sectionRates.reduce((acc, item) => acc + item.rate, 0) / sectionRates.length)
          : 0;
        return { ...section, rate, fieldCount: sectionRates.length };
      })
      .filter((section) => section.fieldCount > 0)
      .sort((a, b) => b.rate - a.rate);

    const monthlyInclusions = Object.entries(monthlyInclusionMap)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([monthKey, count]) => ({ label: monthKeyToLabel(monthKey), count }));

    const monthlyComplications = Object.entries(monthlyComplicationMap)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([monthKey, values]) => ({
        label: monthKeyToLabel(monthKey),
        documented: values.documented,
        hospitalizations: values.hospitalizations,
        hospitalizationDays: values.hospitalizationDays,
      }));

    const topEtiologyLabels = Object.entries(etiologyMap)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label]) => label);

    const inclusionStatuses = Array.from(new Set(Object.values(etiologyInclusionMap)
      .flatMap((statusMap) => Object.keys(statusMap)))).slice(0, 5);

    const etiologyInclusionGrouped = {
      labels: topEtiologyLabels,
      datasets: inclusionStatuses.map((status) => ({
        status,
        values: topEtiologyLabels.map((etiology) => etiologyInclusionMap?.[etiology]?.[status] || 0),
      })),
    };

    const ageSexDistribution = Object.keys(ageBandsMap).map((band) => ({
      band,
      homme: 0,
      femme: 0,
      inconnu: 0,
    }));

    patients.forEach((patient) => {
      const age = Number(patient?.age);
      if (!Number.isFinite(age) || age < 0) {
        return;
      }

      const sex = normalizeSexDisplay(sexLabels[patient?.sexe] || patient?.sexe || 'Inconnu');
      const targetBand = age <= 20
        ? '0-20'
        : age <= 40
          ? '21-40'
          : age <= 60
            ? '41-60'
            : age <= 80
              ? '61-80'
              : '81+';

      const target = ageSexDistribution.find((item) => item.band === targetBand);
      if (!target) {
        return;
      }

      if (sex === 'Homme') {
        target.homme += 1;
      } else if (sex === 'Femme') {
        target.femme += 1;
      } else {
        target.inconnu += 1;
      }
    });

    const inclusionCount = Object.values(inclusionMap).reduce((acc, count) => acc + count, 0);
    const hasExplicitInclusionStatus = patients.some((patient) => !isNoResponseValue(resolveTableCellValue(patient, 'statut_inclusion')));
    const fallbackInclusionCount = hasExplicitInclusionStatus
      ? 0
      : patients.filter((patient) => Boolean(
          patient?.date_evaluation_initiale
          || patient?.date_admission
          || patient?.created_at
        )).length;

    return {
      totalPatients,
      averageAge,
      medianAge,
      inclusionCount: inclusionCount > 0 ? inclusionCount : fallbackInclusionCount,
      averageCompleteness,
      recentActivityCount,
      highBurdenPatients,
      sexCounts: Object.entries(sexCountsMap).map(([label, count]) => ({ label, count })),
      inclusionCounts: Object.entries(inclusionMap)
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count),
      ageBands: Object.entries(ageBandsMap).map(([label, count]) => ({ label, count })),
      topEtiologies: Object.entries(etiologyMap)
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 6),
      topComorbidities: Object.entries(comorbidityMap)
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8),
      monthlyInclusions,
      monthlyComplications,
      etiologyInclusionGrouped,
      ageSexDistribution,
      topComorbidityCombinations: Object.entries(comorbidityCombinationMap)
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8),
      profile3dPoints: profile3dPoints.slice(0, 1200),
      weakestColumns: fillRates.slice(0, 10),
      strongestSections: completenessSections.slice(0, 6),
    };
  }, [fixedBaseColumns, patients, tableDisplaySchemaFields, activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const monthlyInclusionChartData = useMemo(() => ({
    labels: analysisSummary.monthlyInclusions.map((item) => item.label),
    datasets: [
      {
        label: 'Patients inclus',
        data: analysisSummary.monthlyInclusions.map((item) => item.count),
        borderColor: 'rgba(31, 122, 140, 1)',
        backgroundColor: 'rgba(31, 122, 140, 0.25)',
        tension: 0.25,
        fill: true,
      },
    ],
  }), [analysisSummary.monthlyInclusions]);

  const monthlyComplicationsChartData = useMemo(() => ({
    labels: analysisSummary.monthlyComplications.map((item) => item.label),
    datasets: [
      {
        label: 'Dossiers documentés',
        data: analysisSummary.monthlyComplications.map((item) => item.documented),
        backgroundColor: 'rgba(231, 76, 60, 0.75)',
      },
      {
        label: 'Hospitalisations',
        data: analysisSummary.monthlyComplications.map((item) => item.hospitalizations),
        backgroundColor: 'rgba(241, 196, 15, 0.75)',
      },
    ],
  }), [analysisSummary.monthlyComplications]);

  const etiologyInclusionChartData = useMemo(() => ({
    labels: analysisSummary.etiologyInclusionGrouped.labels,
    datasets: analysisSummary.etiologyInclusionGrouped.datasets.map((dataset, index) => ({
      label: dataset.status,
      data: dataset.values,
      backgroundColor: [
        'rgba(31, 122, 140, 0.72)',
        'rgba(241, 196, 15, 0.72)',
        'rgba(231, 76, 60, 0.72)',
        'rgba(46, 204, 113, 0.72)',
        'rgba(155, 89, 182, 0.72)',
      ][index % 5],
    })),
  }), [analysisSummary.etiologyInclusionGrouped]);

  const ageSexHistogramData = useMemo(() => ({
    labels: analysisSummary.ageSexDistribution.map((item) => item.band),
    datasets: [
      {
        label: 'Homme',
        data: analysisSummary.ageSexDistribution.map((item) => item.homme),
        backgroundColor: 'rgba(52, 152, 219, 0.72)',
      },
      {
        label: 'Femme',
        data: analysisSummary.ageSexDistribution.map((item) => item.femme),
        backgroundColor: 'rgba(231, 76, 60, 0.72)',
      },
      {
        label: 'Inconnu',
        data: analysisSummary.ageSexDistribution.map((item) => item.inconnu),
        backgroundColor: 'rgba(127, 140, 141, 0.72)',
      },
    ],
  }), [analysisSummary.ageSexDistribution]);

  const comorbidityCombinationChartData = useMemo(() => ({
    labels: analysisSummary.topComorbidityCombinations.map((item) => item.label),
    datasets: [
      {
        label: 'Patients',
        data: analysisSummary.topComorbidityCombinations.map((item) => item.count),
        backgroundColor: 'rgba(142, 68, 173, 0.72)',
      },
    ],
  }), [analysisSummary.topComorbidityCombinations]);

  const defaultChartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          precision: 0,
        },
      },
    },
  }), []);

  const profileProjectedBubbleData = useMemo(() => {
    const points = analysisSummary.profile3dPoints || [];
    const colorBySex = {
      Homme: 'rgba(31, 119, 180, 0.75)',
      Femme: 'rgba(231, 76, 60, 0.75)',
      Inconnu: 'rgba(127, 140, 141, 0.75)',
    };

    if (!points.length) {
      return { datasets: [] };
    }

    const angleRad = (profile3dAngle * Math.PI) / 180;
    const ages = points.map((p) => p.age);
    const comorbs = points.map((p) => p.comorbidityCount);
    const meanAge = ages.reduce((acc, n) => acc + n, 0) / ages.length;
    const meanComorb = comorbs.reduce((acc, n) => acc + n, 0) / comorbs.length;

    const projected = points.map((p) => {
      const x = p.age - meanAge;
      const y = p.comorbidityCount - meanComorb;
      const z = p.complicationCount;

      const depth = (x * Math.sin(angleRad)) + (z * Math.cos(angleRad));
      const u = (x * Math.cos(angleRad)) - (z * Math.sin(angleRad));
      const v = y + (depth * 0.35);

      return {
        u,
        v,
        r: Math.max(4, 4 + (p.complicationCount * 2)),
        sex: p.sex,
      };
    });

    const minU = Math.min(...projected.map((p) => p.u));
    const minV = Math.min(...projected.map((p) => p.v));

    return {
      datasets: [
        {
          label: 'Patients (taille = complications, couleur = sexe)',
          data: projected.map((p) => ({
            x: p.u - minU + 1,
            y: p.v - minV + 1,
            r: p.r,
          })),
          backgroundColor: projected.map((p) => colorBySex[p.sex] || colorBySex.Inconnu),
        },
      ],
    };
  }, [analysisSummary.profile3dPoints, profile3dAngle]);

  const profileBubbleOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        title: {
          display: true,
          text: 'Age',
        },
        beginAtZero: true,
      },
      y: {
        title: {
          display: true,
          text: 'Nombre de comorbidites',
        },
        beginAtZero: true,
        ticks: {
          precision: 0,
        },
      },
    },
    plugins: {
      tooltip: {
        callbacks: {
          label: (context) => {
            const point = analysisSummary.profile3dPoints[context.dataIndex];
            if (!point) {
              return '';
            }
            return `Age: ${point.age}, Comorbidites: ${point.comorbidityCount}, Complications: ${point.complicationCount}, Sexe: ${point.sex}, Inclusion: ${point.inclusion}`;
          },
        },
      },
      legend: {
        display: false,
      },
    },
  }), [analysisSummary.profile3dPoints]);

  const analysisKpis = useMemo(() => {
    const total = analysisSummary.totalPatients || 0;
    const hasExplicitInclusionStatus = patients.some((patient) => !isNoResponseValue(resolveTableCellValue(patient, 'statut_inclusion')));
    const inclusionRate = hasExplicitInclusionStatus && total
      ? Math.round((analysisSummary.inclusionCount / total) * 100)
      : null;
    const recentActivityRate = total ? Math.round((analysisSummary.recentActivityCount / total) * 100) : 0;
    const highBurdenRate = total ? Math.round((analysisSummary.highBurdenPatients / total) * 100) : 0;

    const complicationsTotal = analysisSummary.monthlyComplications.reduce((acc, month) => {
      return acc + month.documented + month.hospitalizations;
    }, 0);

    const topEtiology = analysisSummary.topEtiologies[0]?.label || '-';

    return {
      inclusionRate,
      recentActivityRate,
      highBurdenRate,
      complicationsTotal,
      topEtiology,
    };
  }, [analysisSummary, patients, resolveTableCellValue]);

  const loadPatients = async (activeFilters = filters) => {
    setLoading(true);
    setError('');

    const flattenResponse = (data) => {
      if (!Array.isArray(data)) {
        return [];
      }

      return data
        .map(flattenPatientRow)
        .sort((a, b) => {
          const aId = getNumericPatientId(a.id_patient ?? a.id);
          const bId = getNumericPatientId(b.id_patient ?? b.id);
          if (aId !== bId) {
            return aId - bId;
          }
          return (a.id ?? 0) - (b.id ?? 0);
        });
    };

    try {
      const response = await api.get('patients/flat/');
      const rows = flattenResponse(response.data);
      setPatients(rows);
      return rows;
    } catch (flatError) {
      try {
        const response = await api.get('patients/', {
          params: {
            search: activeFilters.search || undefined,
            id_patient: activeFilters.id_patient || undefined,
            sexe: activeFilters.sexe || undefined,
            age_min: activeFilters.age_min || undefined,
            age_max: activeFilters.age_max || undefined,
            date_naissance: activeFilters.date_naissance || undefined,
            statut_inclusion: activeFilters.statut_inclusion || undefined,
            infection: activeFilters.infection || undefined,
            hemorrhage: activeFilters.hemorrhage || undefined,
            avf_created: activeFilters.avf_created || undefined,
          },
        });
        const rows = flattenResponse(response.data);
        setPatients(rows);
        return rows;
      } catch (requestError) {
        setError(extractApiMessage(requestError, 'Impossible de charger les données patients.'));
        return [];
      }
    } finally {
      setLoading(false);
    }
  };
  const loadSchema = async () => {
    try {
      const response = await api.get('patients/schema/');
      setSchemaTemplate(response.data?.template || DEFAULT_SCHEMA_TEMPLATE);
    } catch (requestError) {
      setSchemaTemplate(DEFAULT_SCHEMA_TEMPLATE);
    }
  };

  useEffect(() => {
    loadPatients();
    loadSchema();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetForm = () => {
    setForm(emptyForm);
    setExtraDataValues({});
    setIsEditDialogOpen(false);
    setSchemaAnswers({});
  };

  const beginEdit = (patient) => {
    setForm({
      id: patient.id,
      id_patient: patient.id_patient || '',
      id_enregistrement_source: patient.id_enregistrement_source || '',
      nom: patient.nom || '',
      prenom: patient.prenom || '',
    });
    setExtraDataValues(patient.extra_data && typeof patient.extra_data === 'object' ? patient.extra_data : {});
    setIsEditDialogOpen(true);

    const loadedAnswers = {};
    const fieldsToLoad = schemaTemplate?.fields?.length
      ? schemaTemplate.fields
      : FALLBACK_SCHEMA_FIELDS;
    fieldsToLoad.forEach((field) => {
      const editableValue = getEditableFieldValue(patient, field);
      loadedAnswers[field.key] = Array.isArray(editableValue) ? editableValue : (editableValue ?? '');
    });
    setSchemaAnswers(loadedAnswers);

    setError('');
    setSuccess('');
  };

  const togglePatientSelection = (patientId) => {
    setSelectedPatientIds((current) => {
      if (current.includes(patientId)) {
        return current.filter((id) => id !== patientId);
      }
      return [...current, patientId];
    });
  };

  const toggleSelectAllVisible = (checked) => {
    const visibleIds = visiblePatients.map((patient) => getPatientUniqueId(patient));

    if (checked) {
      setSelectedPatientIds((current) => Array.from(new Set([...current, ...visibleIds])));
      return;
    }

    const visibleSet = new Set(visibleIds);
    setSelectedPatientIds((current) => current.filter((id) => !visibleSet.has(id)));
  };

  const handleEditSelected = () => {
    if (selectedPatientIds.length !== 1) {
      return;
    }

    const selectedPatient = patients.find((patient) => getPatientUniqueId(patient) === selectedPatientIds[0]);
    if (!selectedPatient) {
      setError('La ligne selectionnee est introuvable. Rechargez la liste.');
      return;
    }

    beginEdit(selectedPatient);
  };

  useEffect(() => {
    // Utiliser les champs du schéma API s'ils existent, sinon le fallback complet
    const fieldsToInit = (schemaTemplate?.fields?.length)
      ? schemaTemplate.fields
      : FALLBACK_SCHEMA_FIELDS;

    setSchemaAnswers((current) => {
      const next = { ...current };
      fieldsToInit.forEach((field) => {
        if (next[field.key] !== undefined) {
          return;
        }
        if (field.field_type === 'multiple_choice') {
          next[field.key] = [];
        } else {
          next[field.key] = '';
        }
      });
      return next;
    });
  }, [schemaTemplate, form.id]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({
      ...current,
      [name]: value,
    }));

    if (['id_patient', 'id_enregistrement_source', 'nom', 'prenom'].includes(name)) {
      setSchemaAnswers((current) => ({
        ...current,
        [name]: value,
      }));
    }
  };

  const handleFilterChange = (event) => {
    const { name, value } = event.target;
    setFilters((current) => ({
      ...current,
      [name]: value,
    }));
  };

  const handleSchemaAnswerChange = (field, value) => {
    setSchemaAnswers((current) => ({
      ...current,
      [field.key]: value,
    }));
  };

  const handleExtraDataFieldChange = (columnKey, value) => {
    setExtraDataValues((current) => ({
      ...current,
      [columnKey]: value,
    }));
  };

  const handleSearch = async (event) => {
    if (event?.preventDefault) {
      event.preventDefault();
    }
    setAppliedFilters(filters);
    await loadPatients(filters);
  };

  const handleResetFilters = async () => {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    await loadPatients(emptyFilters);
  };

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    const parsedExtraData = Object.entries(extraDataValues || {}).reduce((acc, [key, value]) => {
      if (value !== undefined && value !== null) {
        acc[key] = value;
      }
      return acc;
    }, {});

    const payload = {
      id_patient: form.id_patient || schemaAnswers.id_patient || undefined,
      id_enregistrement_source: form.id_enregistrement_source || schemaAnswers.id_enregistrement_source || undefined,
      nom: form.nom || schemaAnswers.nom || '',
      prenom: form.prenom || schemaAnswers.prenom || '',
      extra_data: parsedExtraData,
    };

    const fieldsForSave = schemaTemplate?.fields?.length ? schemaTemplate.fields : FALLBACK_SCHEMA_FIELDS;
    fieldsForSave.forEach((field) => {
      const currentValue = schemaAnswers[field.key];
      let value = currentValue;

      if (field.field_type === 'multiple_choice') {
        value = Array.isArray(value) ? value : [];
      }

      if (PATIENT_FIELD_MAP[field.key]) {
        const modelField = PATIENT_FIELD_MAP[field.key];
        if (value !== '' && value !== null && value !== undefined) {
          payload[modelField] = value;
        }
      } else {
        const sectionField = getSectionFieldBySchemaKey(field.key);
        if (sectionField) {
          if (value !== '' && value !== null && value !== undefined && !(Array.isArray(value) && !value.length)) {
            if (!payload[sectionField] || typeof payload[sectionField] !== 'object') {
              payload[sectionField] = {};
            }
            payload[sectionField][field.key] = value;
          }
        } else if (value !== '' && value !== null && value !== undefined && !(Array.isArray(value) && !value.length)) {
          payload.extra_data[field.key] = value;
        }
      }
    });

    try {
      if (form.id) {
        await api.put(`patients/${form.id}/`, payload);
        setSuccess('Patient modifié avec succès.');
      } else {
        await api.post('patients/', payload);
        setSuccess('Patient ajouté avec succès.');
      }
      await loadPatients();
      resetForm();
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Impossible d’enregistrer le patient.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSelected = async () => {
    if (!selectedPatientIds.length) {
      return;
    }

    const selectedPatients = patients.filter((patient) => selectedPatientIds.includes(patient.id));
    const confirmed = window.confirm(
      selectedPatientIds.length === 1
        ? `Supprimer le patient ${selectedPatients[0]?.prenom || ''} ${selectedPatients[0]?.nom || ''} ?`
        : `Supprimer ${selectedPatientIds.length} patients selectionnes ?`,
    );
    if (!confirmed) {
      return;
    }

    setDeletingSelection(true);
    setError('');
    setSuccess('');
    try {
      const idsToDelete = [...selectedPatientIds];
      const deletionResults = await Promise.allSettled(
        idsToDelete.map((id) => api.delete(`patients/${id}/`)),
      );

      const deletedIds = idsToDelete.filter((_, index) => deletionResults[index].status === 'fulfilled');
      const failedCount = deletionResults.length - deletedIds.length;

      // Debug: log erreurs
      deletionResults.forEach((result, index) => {
        if (result.status === 'rejected') {
          console.error(`Suppression patient ${idsToDelete[index]} échouée:`, result.reason?.response?.data || result.reason?.message);
        }
      });

      if (deletedIds.length) {
        const deletedIdSet = new Set(deletedIds);
        setPatients((currentPatients) => currentPatients.filter((item) => !deletedIdSet.has(item.id)));
        setSelectedPatientIds((current) => current.filter((id) => !deletedIdSet.has(id)));
      }

      if (deletedIds.length && failedCount === 0) {
        setSuccess(
          deletedIds.length === 1
            ? 'Patient supprime avec succes.'
            : `${deletedIds.length} patients supprimes avec succes.`,
        );
      } else if (deletedIds.length) {
        setSuccess(`${deletedIds.length} patients supprimes. ${failedCount} suppression(s) ont echoue.`);
      } else {
        setError('Aucune suppression n a pu etre effectuee.');
      }

      if (form.id && deletedIds.includes(form.id)) {
        resetForm();
      }
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Suppression impossible.'));
    } finally {
      setDeletingSelection(false);
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handlePurgeImportedData = async () => {
    const confirmed = window.confirm('Supprimer toutes les donnees patients importees de la base et de la plateforme ?');
    if (!confirmed) {
      return;
    }

    setPurging(true);
    setError('');
    setSuccess('');
    try {
      await api.delete('patients/purge/');
      setPatients([]);
      setSelectedPatientIds([]);
      resetForm();
      // Réinitialiser le schéma : supprimer les colonnes dynamiques, garder uniquement la structure fixe
      setSchemaTemplate(DEFAULT_SCHEMA_TEMPLATE);
      // Réinitialiser le statut de validation
      const resetStatus = { status: 'idle', approvedBy: null, requestedBy: null, timestamp: null, pendingIds: [] };
      setInsertValidationStatus(resetStatus);
      window.dispatchEvent(new Event('patientsInsertValidationUpdated'));
      setSuccess('Toutes les données importées ont été supprimées. Les colonnes dynamiques ont été retirées de la plateforme.');
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Suppression globale impossible.'));
    } finally {
      setPurging(false);
    }
  };

  const handleValidateInsertion = async () => {
    const roleName = roleLabel;
    const pendingIds = insertValidationStatus?.pendingIds || [];
    if (!pendingIds.length) {
      setError('Aucune insertion en attente à valider.');
      return;
    }

    setError('');
    setSuccess('');

    try {
      const validationTimestamp = new Date().toISOString();
      await Promise.all(pendingIds.map((id) => {
        const patient = patients.find((item) => item.id === id);
        const extra_data = {
          ...(patient?.extra_data || {}),
          insertion_validation_status: 'validated',
          insertion_validation_approved_by: roleName,
          insertion_validation_timestamp: validationTimestamp,
        };
        return api.patch(`patients/${id}/`, { extra_data });
      }));

      const newStatus = {
        status: 'validated',
        approvedBy: roleName,
        requestedBy: insertValidationStatus.requestedBy || roleName,
        timestamp: validationTimestamp,
        pendingIds: [],
      };
      setInsertValidationStatus(newStatus);
      window.dispatchEvent(new Event('patientsInsertValidationUpdated'));
      setSuccess(`Insertion validée par ${roleName}. Les patients ont conservé leur statut d'inclusion d'origine.`);
      await loadPatients();
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Validation impossible.'));
    }
  };

  const handleRejectInsertion = async () => {
    const roleName = roleLabel;
    const pendingIds = insertValidationStatus?.pendingIds || [];
    if (!pendingIds.length) {
      setError('Aucune insertion en attente à refuser.');
      return;
    }

    const confirmed = window.confirm('Refuser cette insertion supprimera les patients importés en attente. Continuer ?');
    if (!confirmed) {
      return;
    }

    setError('');
    setSuccess('');
    setRejectingInsertion(true);

    try {
      const deletionResults = await Promise.allSettled(
        pendingIds.map((id) => api.delete(`patients/${id}/`)),
      );

      const deletedIds = pendingIds.filter((_, index) => deletionResults[index].status === 'fulfilled');
      const failedCount = deletionResults.length - deletedIds.length;
      if (!deletedIds.length) {
        setError('Aucune suppression n’a pu être effectuée. L’insertion n’a pas été refusée.');
        return;
      }

      const rejectionTimestamp = new Date().toISOString();
      const newStatus = {
        status: 'rejected',
        approvedBy: roleName,
        requestedBy: insertValidationStatus.requestedBy || roleName,
        timestamp: rejectionTimestamp,
        pendingIds: [],
      };

      let removedDynamicColumnsCount = 0;
      try {
        const cleanupResponse = await api.post('patients/cleanup-dynamic-columns/');
        removedDynamicColumnsCount = Number(cleanupResponse?.data?.removed_count || 0);
      } catch {
        // Le refus d'insertion reste valide meme si le nettoyage dynamique echoue.
      }

      setInsertValidationStatus(newStatus);
      window.dispatchEvent(new Event('patientsInsertValidationUpdated'));
      setSuccess(
        failedCount === 0
          ? `Insertion refusée par ${roleName}. ${deletedIds.length} patient(s) importé(s) supprimé(s). ${removedDynamicColumnsCount} colonne(s) dynamique(s) nettoyée(s).`
          : `Insertion partiellement refusée par ${roleName}. ${deletedIds.length} patient(s) supprimé(s), ${failedCount} échec(s). ${removedDynamicColumnsCount} colonne(s) dynamique(s) nettoyée(s).`,
      );
      await loadPatients();
      await loadSchema();
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Refus impossible.'));
    } finally {
      setRejectingInsertion(false);
    }
  };

  const handleExportExcel = () => {
    setError('');
    try {
      const headerRow = [
        ...fixedBaseColumns.map((column) => column.label),
        ...tableDisplaySchemaFields.map((field) => field.label),
      ];

      const rows = visiblePatients.map((patient) => [
        ...fixedBaseColumns.map((column) => renderValue(resolveTableCellValue(patient, column.key), column.key)),
        ...tableDisplaySchemaFields.map((field) => renderValue(resolveTableCellValue(patient, field.key), field.key)),
      ]);

      const csvContent = [headerRow, ...rows]
        .map((row) => row.map((cell) => `"${escapeCsvCell(cell)}"`).join(';'))
        .join('\n');

      const bom = '\uFEFF';
      const blob = new Blob([bom, csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `patients_tableau_${new Date().toISOString().slice(0, 19).replaceAll(':', '-')}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setSuccess('Fichier Excel téléchargé avec succès.');
    } catch (requestError) {
      setError(extractApiMessage(requestError, 'Téléchargement Excel impossible.'));
    }
  };

  const handleFileSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setImporting(true);
    setError('');
    setSuccess('');

    try {
      const buildFormData = () => {
        const formData = new FormData();
        formData.append('file', file);
        return formData;
      };

      let response;
      try {
        response = await api.post('patients/import/', buildFormData());
      } catch (primaryError) {
        const isRouteIssue = primaryError?.response?.status === 404;
        if (!isRouteIssue) {
          throw primaryError;
        }

        // Backward compatibility with older backend route naming.
        response = await api.post('patients/import-excel/', buildFormData());
      }

      const importedFields = response.data?.fields_created || 0;
      const patientsCreated = response.data?.patients_created || 0;
      const mode = response.data?.mode;
      const dynamicColumns = response.data?.dynamic_columns || [];
      const newDynamicCount = response.data?.new_dynamic_columns_count || 0;

      // Stocker le rapport des colonnes dynamiques
      if (dynamicColumns.length > 0) {
        setImportDynamicColumns({ columns: dynamicColumns, newCount: newDynamicCount });
      } else {
        setImportDynamicColumns(null);
      }

      if (mode === 'schema') {
        setSuccess(`${importedFields} colonne(s) de structure importée(s) depuis Excel.`);
      } else {
        const dynMsg = newDynamicCount > 0
          ? ` • ${newDynamicCount} nouvelle(s) colonne(s) dynamique(s) détectée(s).`
          : '';
        setSuccess(`${patientsCreated} patient(s) importé(s) et ${importedFields} colonne(s) gérée(s).${dynMsg}`);
      }

      if ((response.data?.errors || []).length) {
        setError(`Import partiel: ${response.data.errors.length} ligne(s) rejetée(s).`);
      }

      const existingPatientIds = new Set(patients.map((patient) => patient.id));
      if (patientsCreated > 0) {
        await loadSchema();
        const loadedPatients = await loadPatients();
        if (canValidateInsertion) {
          const newImportedIds = Array.from(new Set((loadedPatients || []).map((patient) => patient.id))).filter((id) => !existingPatientIds.has(id));
          const requesterRoleName = roleLabel;
          const validationTimestamp = new Date().toISOString();
          await Promise.allSettled(newImportedIds.map((id) => {
            const extra_data = {
              insertion_validation_status: 'pending',
              insertion_validation_requested_by: requesterRoleName,
              insertion_validation_timestamp: validationTimestamp,
            };
            return api.patch(`patients/${id}/`, { extra_data });
          }));
          const newStatus = {
            status: 'pending',
            approvedBy: null,
            requestedBy: requesterRoleName,
            timestamp: validationTimestamp,
            pendingIds: newImportedIds,
          };
          setInsertValidationStatus(newStatus);
          window.dispatchEvent(new Event('patientsInsertValidationUpdated'));
        } else {
          setInsertValidationStatus({ status: 'idle', approvedBy: null, requestedBy: null, timestamp: null, pendingIds: [] });
        }
      } else {
        await loadSchema();
        await loadPatients();
      }
    } catch (requestError) {
      const apiMessage = extractApiMessage(requestError, 'Import de la structure Excel impossible.');
      setError(apiMessage === 'Import de la structure Excel impossible.'
        ? apiMessage
        : `Import de la structure Excel impossible. ${apiMessage}`);
    } finally {
      setImporting(false);
      event.target.value = '';
    }
  };

  const renderValue = (value, key) => {
    if (value === null || value === undefined || value === '') {
      return '-';
    }
    if (key === 'id_enregistrement_source') {
      return normalizeIdEnregistrement(value);
    }
    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (normalized === 'x' || normalized === '-') {
        return '-';
      }
      // Conversion binaire 0/1 → oui/non UNIQUEMENT pour les colonnes purement binaires
      const isColumnBinary = schemaBooleanFieldKeys.has(key) || extraBinaryColumnKeys.has(key);
      if (isColumnBinary) {
        if (normalized === '1') return 'oui';
        if (normalized === '0') return 'non';
      }
    }
    // Conversion binaire numérique 0/1 → oui/non UNIQUEMENT pour les colonnes purement binaires
    if (value === 1 || value === 0) {
      const isColumnBinary = schemaBooleanFieldKeys.has(key) || extraBinaryColumnKeys.has(key);
      if (isColumnBinary) {
        return value === 1 ? 'oui' : 'non';
      }
    }
    if (typeof value === 'object') {
      return safeStringify(value);
    }
    // Quick fix: if `prenom` erroneously contains a suffix `_oui`, display `_1` instead.
    if (typeof value === 'string' && key === 'prenom') {
      const t = value.trim();
      if (/[_-]?oui$/i.test(t)) {
        return t.replace(/[_-]?oui$/i, '_1');
      }
    }
    // Normalize consent status display for table list to match monitoring
    if (key === 'statut_consentement') {
      const v = value;
      if (v === null || v === undefined || v === '') return '-';
      const s = String(v).trim().toLowerCase();
      if (['1', 'true', 'oui', 'consenti'].includes(s)) return 'Oui';
      if (['0', 'false', 'non', 'refuse'].includes(s)) return 'Non';
      if (s === 'en_attente') return 'En attente';
      if (s === 'non_applicable') return 'N/A';
      // Fallback: capitalize first letter
      return String(v).charAt(0).toUpperCase() + String(v).slice(1);
    }
    return value;
  };

  const closeEditDialog = () => {
    resetForm();
  };

  // Rendu générique d'un bloc de champs dans le formulaire patient
  const renderSchemaFieldInput = (field) => {
    const identityKeys = ['id_patient', 'id_enregistrement_source', 'nom', 'prenom'];
    const value = identityKeys.includes(field.key)
      ? (form[field.key] ?? schemaAnswers[field.key] ?? '')
      : schemaAnswers[field.key];

    const handleFieldChange = (event) => {
      const nextValue = event.target.value;
      if (identityKeys.includes(field.key)) {
        setForm((current) => ({
          ...current,
          [field.key]: nextValue,
        }));
      }
      handleSchemaAnswerChange(field, nextValue);
    };

    if (field.field_type === 'auto') {
      return (
        <TextField
          key={field.id}
          label={field.label}
          value={value ?? '(genere automatiquement)'}
          size="small"
          fullWidth
          disabled
        />
      );
    }
    if (field.field_type === 'single_choice' || field.field_type === 'boolean') {
      return (
        <TextField
          key={field.id}
          select
          label={field.label}
          value={value ?? ''}
          onChange={handleFieldChange}
          size="small"
          fullWidth
        >
          <MenuItem value="">Selectionner</MenuItem>
          {(field.choices || []).map((choice) => (
            <MenuItem key={`${field.id}-${choice}`} value={choice}>{choice}</MenuItem>
          ))}
        </TextField>
      );
    }
    if (field.field_type === 'multiple_choice') {
      return (
        <TextField
          key={field.id}
          select
          label={field.label}
          value={Array.isArray(value) ? value : []}
          onChange={handleFieldChange}
          size="small"
          fullWidth
          SelectProps={{
            multiple: true,
            renderValue: (selected) => selected.join(', '),
          }}
        >
          {(field.choices || []).map((choice) => (
            <MenuItem key={`${field.id}-dlg-m-${choice}`} value={choice}>{choice}</MenuItem>
          ))}
        </TextField>
      );
    }
    if (field.field_type === 'date') {
      return (
        <TextField
          key={field.id}
          label={field.label}
          type="date"
          value={value ?? ''}
          onChange={handleFieldChange}
          size="small"
          fullWidth
          InputLabelProps={{ shrink: true }}
        />
      );
    }
    if (field.field_type === 'integer' || field.field_type === 'decimal') {
      return (
        <TextField
          key={field.id}
          label={field.label}
          type="number"
          value={value ?? ''}
          onChange={handleFieldChange}
          size="small"
          fullWidth
          inputProps={field.field_type === 'decimal' ? { step: 'any' } : undefined}
        />
      );
    }
    return (
      <TextField
        key={field.id}
        label={field.label}
        value={value ?? ''}
        onChange={handleFieldChange}
        size="small"
        fullWidth
        multiline={field.field_type === 'text_long'}
        minRows={field.field_type === 'text_long' ? 2 : undefined}
      />
    );
  };

  const renderDynamicExtraFields = (title) => {
    if (!formDynamicExtraColumns.length) {
      return null;
    }

    return (
      <Box
        sx={{
          p: 1.5,
          borderRadius: 2,
          border: '1px solid rgba(124,91,168,.12)',
          backgroundColor: 'rgba(240,235,250,.95)',
          maxHeight: 280,
          overflowY: 'auto',
          display: 'grid',
          gap: 1.25,
        }}
      >
        <Typography variant="subtitle2" fontWeight={800}>
          {title}
        </Typography>
        {formDynamicExtraColumns.map((columnKey) => (
          <TextField
            key={`dynamic-form-${columnKey}`}
            label={columnKey}
            value={extraDataValues[columnKey] ?? ''}
            onChange={(event) => handleExtraDataFieldChange(columnKey, event.target.value)}
            size="small"
            fullWidth
          />
        ))}
      </Box>
    );
  };

  // ─── Palette NéphroCare ───────────────────────────────────────────────────
  const PM = {
    navy:   '#1e2d5a',
    steel:  '#3d5a8a',
    sky:    '#a8cfee',
    rose:   '#9e3d6a',
    blush:  '#e8c4d4',
    bg:     'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 45%,#f4eef8 100%)',
    card:   '#ffffff',
    border: 'rgba(61,90,138,.10)',
    text:   '#1e2d5a',
    muted:  '#7a90b0',
  };

  const PAGE_STYLES = {
    shell: {
      minHeight: '100vh',
      py: 0,
      px: 0,
      position: 'relative',
      overflowX: 'hidden',
      background: [
        'radial-gradient(circle at top left, rgba(168,207,238,.48), transparent 34%)',
        'radial-gradient(circle at top right, rgba(158,61,106,.14), transparent 28%)',
        'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 42%,#f4eef8 100%)',
      ].join(', '),
      fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
      '&::before': {
        content: '""',
        position: 'fixed',
        inset: 0,
        pointerEvents: 'none',
        background: 'linear-gradient(135deg, rgba(255,255,255,.34), rgba(255,255,255,0))',
        zIndex: 0,
      },
      '& .MuiGrid-root, & .MuiCard-root, & .MuiDialog-paper': {
        position: 'relative',
        zIndex: 1,
      },
      '& .MuiCard-root': {
        fontFamily: 'inherit',
        borderRadius: '24px',
        border: '1px solid rgba(61,90,138,.10)',
        boxShadow: '0 12px 32px rgba(30,45,90,.06)',
        backdropFilter: 'blur(12px)',
        backgroundImage: 'linear-gradient(180deg, rgba(255,255,255,.95), rgba(255,255,255,.88))',
      },
      '& .MuiButton-root': {
        fontFamily: 'inherit',
        textTransform: 'none',
        fontWeight: 700,
        borderRadius: '14px',
        boxShadow: 'none',
      },
      '& .MuiButton-contained': {
        background: 'linear-gradient(135deg,#3d5a8a,#1e2d5a)',
        boxShadow: '0 10px 22px rgba(30,45,90,.18)',
        '&:hover': { background: 'linear-gradient(135deg,#4a6fa8,#2a3d72)', boxShadow: '0 14px 26px rgba(30,45,90,.22)' },
      },
      '& .MuiButton-outlined': {
        borderColor: 'rgba(61,90,138,.24)',
        color: '#3d5a8a',
        '&:hover': { borderColor: '#3d5a8a', background: 'rgba(61,90,138,.05)' },
      },
      '& .MuiButton-outlinedError': {
        borderColor: 'rgba(158,61,106,.28)',
        color: '#9e3d6a',
        '&:hover': { borderColor: '#9e3d6a', background: 'rgba(158,61,106,.05)' },
      },
      '& .MuiTextField-root .MuiOutlinedInput-root': {
        borderRadius: '14px',
        background: 'rgba(255,255,255,.92)',
        '& fieldset': { borderColor: 'rgba(61,90,138,.18)' },
        '&:hover fieldset': { borderColor: 'rgba(61,90,138,.40)' },
        '&.Mui-focused fieldset': { borderColor: '#3d5a8a', borderWidth: 2 },
      },
      '& .MuiTextField-root label.Mui-focused': { color: '#3d5a8a' },
      '& .MuiTableCell-head': {
        fontWeight: 800,
        color: '#1e2d5a',
        fontFamily: 'inherit',
        fontSize: '0.78rem',
        letterSpacing: '.02em',
        textTransform: 'uppercase',
        background: 'linear-gradient(135deg, rgba(168,207,238,.28), rgba(61,90,138,.10))',
      },
      '& .MuiTableCell-body': { fontFamily: 'inherit', color: '#2d3f6a', fontSize: '0.83rem' },
      '& .MuiTableRow-hover:hover': { background: 'rgba(168,207,238,.10) !important' },
      '& .MuiCheckbox-root.Mui-checked': { color: '#3d5a8a' },
      '& .MuiChip-root': { fontFamily: 'inherit', fontWeight: 700 },
      '& .MuiDialogTitle-root': { fontFamily: 'inherit', fontWeight: 800, color: '#1e2d5a' },
      '& .MuiTab-root': { fontFamily: 'inherit' },
      '& .MuiAlert-root': { borderRadius: '16px', fontFamily: 'inherit', boxShadow: '0 8px 22px rgba(30,45,90,.06)' },
      '& .MuiLinearProgress-root': { borderRadius: 999, height: 8 },
      '& .MuiLinearProgress-bar': { background: 'linear-gradient(90deg,#3d5a8a,#9e3d6a)' },
    },
    heroCard: {
      borderRadius: '28px',
      border: '1px solid rgba(61,90,138,.12)',
      background: 'linear-gradient(135deg, rgba(255,255,255,.94), rgba(255,255,255,.84))',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '0 16px 44px rgba(30,45,90,.10)',
      '&::before': {
        content: '""',
        position: 'absolute',
        inset: '0 0 auto 0',
        height: 5,
        background: `linear-gradient(90deg,${PM.sky},${PM.steel},${PM.rose},${PM.blush})`,
      },
      '&::after': {
        content: '""',
        position: 'absolute',
        top: -60,
        right: -60,
        width: 180,
        height: 180,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(158,61,106,.10), transparent 68%)',
        pointerEvents: 'none',
      },
    },
    panelCard: {
      borderRadius: '28px',
      border: '1px solid rgba(61,90,138,.12)',
      background: 'linear-gradient(180deg, rgba(255,255,255,.95), rgba(247,250,255,.88))',
      boxShadow: '0 16px 38px rgba(30,45,90,.08)',
      backdropFilter: 'blur(14px)',
    },
    softCard: {
      borderRadius: '24px',
      border: '1px solid rgba(61,90,138,.10)',
      background: 'linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,251,255,.90))',
      boxShadow: '0 10px 28px rgba(30,45,90,.06)',
    },
    dialogPaper: {
      borderRadius: '28px',
      border: '1px solid rgba(61,90,138,.14)',
      boxShadow: '0 28px 72px rgba(30,45,90,.20)',
      overflow: 'hidden',
    },
    tableContainer: {
      borderRadius: '22px',
      overflowX: 'auto',
      border: '1px solid rgba(61,90,138,.10)',
      background: 'linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,251,255,.94))',
      boxShadow: '0 14px 30px rgba(30,45,90,.06)',
    },
    selectionBar: {
      mb: 1.5,
      p: 1.25,
      borderRadius: '18px',
      border: '1px solid rgba(61,90,138,.18)',
      background: 'linear-gradient(135deg, rgba(168,207,238,.16), rgba(255,255,255,.92))',
      position: 'sticky',
      top: 8,
      zIndex: 5,
      backdropFilter: 'blur(8px)',
    },
  };

  return (
    <Box
      sx={{
        ...PAGE_STYLES.shell,
      }}
    >
      {/* Google Font */}
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');`}</style>

      <Grid container spacing={1.5} alignItems="flex-start" sx={{ width: '100%', minWidth: 0, px: { xs: 1, md: 1 }, py: { xs: 1, md: 1 } }}>
        <Grid item xs={12} sx={{ display: { xs: 'block', md: 'block' }, width: { md: '88px' }, flex: { md: '0 0 88px' }, pr: 0 }}>
          <AppSidebar onValidateInsertion={handleValidateInsertion} onViewImport={() => { /* Scroll to validation panel */ if (isValidationPending) { const elem = document.querySelector('[data-validation-panel]'); elem?.scrollIntoView({ behavior: 'smooth' }); } }} />
        </Grid>

        <Grid item xs={12} sx={{ minWidth: 0, ml: { md: '252px' } }}>
          <Stack spacing={2.5}>
        {mainSection === 'data_patient' ? (
          <>
        {/* ── Header card ─────────────────────────────────────────────── */}
        <Card elevation={0} sx={PAGE_STYLES.heroCard}>
          <CardContent sx={{ p: 3, position: 'relative' }}>
            {/* Background corner image (place file in frontend/public/) */}
            <Box
              component="img"
              src="/images/chatgpt-image-2026-04-23.png"
              alt="decor"
              sx={{
                position: 'absolute',
                left: 10,
                top: 8,
                width: 152,
                maxWidth: '36%',
                opacity: 0.16,
                transform: 'translateZ(0)',
                zIndex: 0,
                pointerEvents: 'none',
                filter: 'drop-shadow(0 8px 20px rgba(158,61,106,0.10)) saturate(1.05) contrast(1.04)'
              }}
            />
            <Stack direction={{ xs: 'column', lg: 'row' }} justifyContent="space-between" spacing={2.5} sx={{ position: 'relative', zIndex: 1 }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: PM.navy, letterSpacing: '-.02em', fontFamily: 'inherit' }}>
                  {t('patientsManagementTitle')}
                </Typography>
                {/* description removed per request */}
              </Box>
              <Box
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: { xs: 'flex-start', lg: 'flex-end' },
                  gap: 1,
                  minWidth: { lg: 340 },
                }}
              >
                <Chip
                  label={roleLabel}
                  sx={{
                    alignSelf: { xs: 'flex-start', lg: 'flex-end' },
                    background: `linear-gradient(135deg,${PM.steel},${PM.navy})`,
                    color: '#fff', fontWeight: 700, fontSize: '0.75rem',
                    border: 'none',
                    '& .MuiChip-icon': { display: 'none' },
                    '& .MuiAvatar-root': { display: 'none' }
                  }}
                />
                <Box sx={{ p: 0, borderRadius: 0, border: 'none', background: 'transparent', boxShadow: 'none' }}>
                  <Tabs
                    value={activeTab}
                    onChange={(_, newValue) => setActiveTab(newValue)}
                    sx={{
                      minHeight: 34,
                      '& .MuiTab-root': { fontFamily: 'inherit', fontWeight: 700, color: PM.muted, textTransform: 'none', fontSize: '0.85rem', minHeight: 34 },
                      '& .Mui-selected': { color: `${PM.rose} !important`, fontWeight: 800 },
                      '& .MuiTabs-indicator': { background: `linear-gradient(90deg,${PM.rose},${PM.steel})`, height: 3, borderRadius: 2 },
                    }}
                  >
                    <Tab value="pretraitement" label={language === 'en' ? 'Preprocessing' : 'Prétraitement'} />
                    <Tab value="gestion" label={language === 'en' ? 'Management' : 'Gestion'} />
                    <Tab value="analyse" label={t('aiAnalysis')} />
                  </Tabs>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {insertValidationStatus.status === 'pending' && canValidateInsertion && (
          <Alert severity="info" sx={{ borderRadius: '18px', border: '2px solid rgba(61,90,138,.24)', background: 'linear-gradient(135deg, rgba(168,207,238,.16), rgba(158,61,106,.08))', fontFamily: 'inherit', boxShadow: '0 8px 20px rgba(61,90,138,.10)', py: 2, px: 2.5 }}>
            {language === 'en'
              ? `New import pending validation. ${validatorPhrase} can validate the insertion to make the data available across the platform.`
              : `Nouvelle importation en attente de validation. ${validatorPhrase} pouvez valider l'insertion pour rendre les données disponibles sur toute la plateforme.`}
          </Alert>
        )}
        {error && <Alert severity="error" onClose={() => setError('')} sx={{ borderRadius: "14px", fontFamily: "inherit" }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ borderRadius: "14px", fontFamily: "inherit" }}>{success}</Alert>}

        {/* ── Rapport colonnes dynamiques détectées lors de l'import ── */}
        {importDynamicColumns && importDynamicColumns.columns.length > 0 && (
          <Alert
            severity="info"
            sx={{ mt: 1 }}
            onClose={() => setImportDynamicColumns(null)}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
              Colonnes dynamiques détectées dans le fichier importé
              {importDynamicColumns.newCount > 0 && (
                <Chip
                  label={`${importDynamicColumns.newCount} nouvelle(s)`}
                  size="small"
                  color="warning"
                  sx={{ ml: 1, fontWeight: 600, '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }}
                />
              )}
            </Typography>
            <Typography variant="body2" sx={{ mb: 1, color: 'text.secondary' }}>
              Ces colonnes ne figuraient pas dans le schéma de la plateforme. Elles ont été
              automatiquement ajoutées comme <strong>colonnes dynamiques</strong> et leurs valeurs
              sont stockées dans <code>extra_data</code>. Elles sont désormais visibles dans les
              fiches patients et dans le tableau.
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
              {importDynamicColumns.columns.map((col) => (
                <Chip
                  key={col.key}
                  label={col.label}
                  size="small"
                  variant="outlined"
                  color={col.is_new ? 'warning' : 'default'}
                  title={col.is_new ? 'Nouvelle colonne créée' : 'Colonne dynamique existante mise à jour'}
                  sx={{ fontFamily: 'monospace', fontSize: '0.72rem', '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }}
                />
              ))}
            </Box>
          </Alert>
        )}
        {/* Alerte validation pending supprimée */}
        {insertValidationStatus.status === 'validated' && (
          <Alert severity="success" sx={{ borderRadius: '14px', fontFamily: 'inherit' }}>Insertion validée par {insertValidationStatus.approvedBy} le {formattedValidationTimestamp}.</Alert>
        )}
        {insertValidationStatus.status === 'rejected' && (
          <Alert severity="error" sx={{ borderRadius: '14px', fontFamily: 'inherit' }}>Insertion refusée par {insertValidationStatus.approvedBy} le {formattedValidationTimestamp}.</Alert>
        )}

        {activeTab === 'pretraitement' ? (
          <Preprocessing />
        ) : activeTab === 'gestion' ? (
        <Grid container spacing={3}>
          <Grid item xs={12} lg={8} sx={{ order: { xs: 1, lg: 1 } }}>
            <Stack spacing={3}>
              <Card elevation={0} sx={PAGE_STYLES.softCard}>
                <CardContent sx={{ p: 3 }}>
                  <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2} sx={{ mb: 2 }}>
                    <Box>
                      <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {t('patientsListTitle')}
                      </Typography>
                      {/* description removed per request */}
                    </Box>
                    <Box sx={{ p: 1.5, borderRadius: 3, border: '1px solid rgba(61,90,138,.12)', background: 'linear-gradient(180deg, rgba(255,255,255,.98), rgba(247,250,255,.94))', minWidth: { md: 440 } }}>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center" sx={{ mb: 1 }}>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={handleImportClick}
                          startIcon={<UploadFileOutlinedIcon />}
                          disabled={importing || purging}
                          sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, whiteSpace: 'nowrap' }}
                          title={t('patientsImportHint')}
                        >
                          {importing ? t('patientsImporting') : t('patientsImportExcel')}
                        </Button>
                        <Button
                          size="small"
                          variant="contained"
                          onClick={() => setShowFilterPanel(s => !s)}
                          startIcon={<FilterListOutlinedIcon />}
                          sx={{
                            textTransform: 'none',
                            borderRadius: 2,
                            fontWeight: 800,
                            background: 'linear-gradient(135deg, #1A8FA8 0%, #D47A8E 100%)',
                            color: '#fff',
                            border: 'none',
                            boxShadow: '0 6px 20px rgba(26,143,168,0.28)',
                            '&:hover': { filter: 'brightness(1.06)', boxShadow: '0 8px 24px rgba(26,143,168,0.36)' },
                            whiteSpace: 'nowrap'
                          }}
                        >
                          {t('patientsFilter')}
                        </Button>
                        {canPurgeImportedData && (
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            startIcon={<DeleteOutlineOutlinedIcon />}
                            onClick={handlePurgeImportedData}
                            disabled={importing || purging}
                            sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, whiteSpace: 'nowrap' }}
                            title={t('patientsReservedHint')}
                          >
                            {purging ? t('patientsDeleting') : t('patientsClearImported')}
                          </Button>
                        )}
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".xlsx,.xls"
                          hidden
                          onChange={handleFileSelect}
                        />
                      </Stack>

                      {(isValidationPending || isValidationValidated) && (
                        <Box
                          data-validation-panel
                          sx={{
                            mt: 2,
                            p: 2,
                            borderRadius: 2,
                            border: '1px solid rgba(61,90,138,.12)',
                            backgroundColor: 'rgba(237,244,251,.80)',
                          }}
                        >
                          <Typography variant="subtitle2" fontWeight={800} sx={{ mb: 1 }}>
                            {t('patientsDataStatus')}
                          </Typography>
                          {isValidationPending && (
                            <Stack spacing={1}>
                              <Typography variant="body2" color="text.secondary">
                                {t('patientsImportPendingSince')} {insertValidationStatus.requestedBy || 'un utilisateur'} le {formattedValidationTimestamp}.
                              </Typography>
                              {canValidateInsertion ? (
                                <Stack direction="row" spacing={1} flexWrap="wrap">
                                  <Button
                                    size="small"
                                    variant="contained"
                                    onClick={handleValidateInsertion}
                                    disabled={!isValidationPending || rejectingInsertion}
                                    sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, alignSelf: 'flex-start' }}
                                  >
                                    {t('patientsValidateImport')}
                                  </Button>
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    color="error"
                                    onClick={handleRejectInsertion}
                                    disabled={!isValidationPending || rejectingInsertion}
                                    sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, alignSelf: 'flex-start' }}
                                  >
                                    {t('patientsRejectImport')}
                                  </Button>
                                </Stack>
                              ) : (
                                <Typography variant="body2" color="text.secondary">
                                  {t('patientsImportRequiredInfo')}
                                </Typography>
                              )}
                            </Stack>
                          )}
                          {isValidationValidated && (
                            <Typography variant="body2" color="text.secondary">
                              {t('patientsImportValidated')} {insertValidationStatus.approvedBy} le {formattedValidationTimestamp}. Les données peuvent maintenant être utilisées par toute la plateforme.
                            </Typography>
                          )}
                        </Box>
                      )}

                      <Box sx={{ display: showFilterPanel ? 'block' : 'none', position: 'relative', mt: 1.5, mb: 1, p: 1.5, borderRadius: 2, background: `linear-gradient(180deg, rgba(255,255,255,0.98), ${PM.blush}10)`, border: `1px solid ${PM.border}`, boxShadow: `0 12px 34px rgba(158,61,106,0.06), inset 0 -6px 18px rgba(158,61,106,0.03)`, '&::after': { content: '""', position: 'absolute', left: 12, right: 12, bottom: -10, height: 10, background: `linear-gradient(180deg, ${PM.rose}06, rgba(255,255,255,0))`, borderRadius: '8px', pointerEvents: 'none' } }}>
                        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} useFlexGap flexWrap="wrap" sx={{}}>
                        <TextField
                          size="small"
                          name="id_patient"
                          label={t('patientsSearchId')}
                          value={filters.id_patient}
                          onChange={handleFilterChange}
                          sx={{ width: { xs: '100%', sm: 180 }, bgcolor: 'rgba(255,255,255,.92)' }}
                        />
                        <TextField
                          size="small"
                          name="search"
                          label={t('patientsSearchName')}
                          value={filters.search}
                          onChange={handleFilterChange}
                          placeholder={t('patientsSearchNamePlaceholder')}
                          sx={{ width: { xs: '100%', sm: 220 }, bgcolor: 'rgba(255,255,255,.92)' }}
                          InputProps={{
                            startAdornment: (
                              <InputAdornment position="start">
                                <SearchOutlinedIcon fontSize="small" />
                              </InputAdornment>
                            ),
                          }}
                        />
                        <TextField
                          select
                          size="small"
                          name="sexe"
                          label={t('patientsSearchSex')}
                          value={filters.sexe}
                          onChange={handleFilterChange}
                          sx={{ width: { xs: '100%', sm: 140 }, bgcolor: 'rgba(255,255,255,.92)' }}
                        >
                          <MenuItem value="">{t('patientsSearchAll')}</MenuItem>
                          <MenuItem value="M">{t('patientsSearchMale')}</MenuItem>
                          <MenuItem value="F">{t('patientsSearchFemale')}</MenuItem>
                          <MenuItem value="O">{t('patientsSearchUnknown')}</MenuItem>
                        </TextField>
                        <TextField
                          size="small"
                          name="age_min"
                          label={t('patientsAgeMin')}
                          value={filters.age_min}
                          onChange={handleFilterChange}
                          type="number"
                          inputProps={{ min: 0 }}
                          sx={{ width: { xs: '100%', sm: 130 }, bgcolor: 'rgba(255,255,255,.92)' }}
                        />
                        <TextField
                          size="small"
                          name="age_max"
                          label={t('patientsAgeMax')}
                          value={filters.age_max}
                          onChange={handleFilterChange}
                          type="number"
                          inputProps={{ min: 0 }}
                          sx={{ width: { xs: '100%', sm: 130 }, bgcolor: 'rgba(255,255,255,.92)' }}
                        />
                        <Button
                          size="small"
                          variant="contained"
                          onClick={handleSearch}
                          sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, minWidth: 120, background: 'linear-gradient(135deg, #1A8FA8 0%, #D47A8E 100%)', boxShadow: '0 6px 20px rgba(26,143,168,0.28)', '&:hover': { filter: 'brightness(1.06)', boxShadow: '0 8px 24px rgba(26,143,168,0.36)' } }}
                        >
                          {t('patientsApply')}
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={handleResetFilters}
                          sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, minWidth: 120 }}
                        >
                          {t('patientsReset')}
                        </Button>
                        </Stack>
                      </Box>

                      <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" alignItems="center">
                        {patients.length > INITIAL_ROWS_LIMIT && (
                          <Button
                            size="small"
                            variant="text"
                            onClick={() => setShowAllRows((current) => !current)}
                            sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700 }}
                          >
                                {showAllRows
                                  ? t('patientsHideExtraRows')
                                  : `${t('patientsShowAllRows')} (${patients.length})`}
                          </Button>
                        )}
                      </Stack>
                    </Box>
                  </Stack>

                  {selectedPatientIds.length > 0 && (
                    <Box sx={PAGE_STYLES.selectionBar}>
                      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ xs: 'stretch', sm: 'center' }}>
                        <Typography variant="body2" fontWeight={700} sx={{ color: '#1e2d5a', fontFamily: 'inherit' }}>
                          {selectedPatientsCountLabel}
                        </Typography>
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="contained"
                            startIcon={<EditOutlinedIcon />}
                            onClick={handleEditSelected}
                            disabled={selectedPatientIds.length !== 1 || deletingSelection}
                            sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, whiteSpace: 'nowrap' }}
                          >
                            {t('patientsModify')}
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            variant="outlined"
                            startIcon={<DeleteOutlineOutlinedIcon />}
                            onClick={handleDeleteSelected}
                            disabled={!selectedPatientIds.length || deletingSelection}
                            sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, whiteSpace: 'nowrap' }}
                          >
                            {deletingSelection ? t('patientsDeleting') : t('patientsDelete')}
                          </Button>
                        </Stack>
                      </Stack>
                    </Box>
                  )}

                  <TableContainer component={Paper} variant="outlined" sx={PAGE_STYLES.tableContainer}>
                    <Table stickyHeader size="small" sx={{ minWidth: Math.max(900, (fixedBaseColumns.length + tableDisplaySchemaFields.length) * 130) }}>
                      <TableHead>
                        <TableRow>
                          <TableCell padding="checkbox" sx={{ fontWeight: 800 }}>
                            <Checkbox
                              size="small"
                              checked={allVisibleSelected}
                              indeterminate={selectedVisibleCount > 0 && !allVisibleSelected}
                              onChange={(event) => toggleSelectAllVisible(event.target.checked)}
                              inputProps={{ 'aria-label': 'Selectionner toutes les lignes visibles' }}
                            />
                          </TableCell>
                          {patientColumnKeys.map((columnKey) => (
                            <TableCell
                              key={`flat-head-${columnKey}`}
                              sx={{
                                fontWeight: 800,
                                ...(dynamicColumnKeys.has(columnKey) && {
                                  color: '#9e3d6a',
                                  borderBottom: '2px solid',
                                  borderColor: '#9e3d6a',
                                }),
                              }}
                              title={dynamicColumnKeys.has(columnKey) ? 'Colonne dynamique (importée automatiquement)' : undefined}
                            >
                              {FIELD_LABEL_MAP[columnKey] || columnLabelMap[columnKey] || columnKey}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {visiblePatients.map((patient) => (
                          <TableRow
                            key={getPatientUniqueId(patient)}
                            hover
                            onDoubleClick={() => beginEdit(patient)}
                            sx={{ cursor: 'pointer', '&:nth-of-type(even)': { backgroundColor: 'rgba(248,251,255,.65)' } }}
                          >
                            <TableCell padding="checkbox">
                              <Checkbox
                                size="small"
                                checked={selectedPatientIds.includes(getPatientUniqueId(patient))}
                                onChange={() => togglePatientSelection(getPatientUniqueId(patient))}
                                inputProps={{ 'aria-label': `Selectionner la ligne du patient ${getPatientUniqueId(patient)}` }}
                              />
                            </TableCell>
                            {patientColumnKeys.map((columnKey) => (
                              <TableCell key={`${getPatientUniqueId(patient)}-${columnKey}`}>
                                {renderValue(resolveTableCellValue(patient, columnKey), columnKey)}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                        {!visiblePatients.length && (
                          <TableRow>
                            <TableCell colSpan={Math.max(2, patientColumnKeys.length + 1)} align="center">
                              {language === 'en' ? 'No patient found for this filter.' : 'Aucun patient trouvé pour ce filtre.'}
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Stack>
          </Grid>

          <Grid item xs={12} lg={4} sx={{ order: { xs: 2, lg: 2 }, position: { lg: 'sticky' }, top: { lg: 24 }, alignSelf: 'flex-start' }}>
            <Card elevation={0} sx={PAGE_STYLES.panelCard}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>
                    {form.id ? 'Modifier un patient' : 'Ajouter un patient'}
                  </Typography>
                  {form.id && (
                    <Button size="small" variant="text" onClick={resetForm} startIcon={<ClearOutlinedIcon />}>
                      Annuler
                    </Button>
                  )}
                </Stack>

                <Box component="form" onSubmit={handleSave} sx={{ display: 'grid', gap: 2 }}>
                  {/* ── Formulaire complet avec TOUS les 150+ champs organisés par catégories ── */}
                  {fixedSchemaFieldsForForm.length > 0 && (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {groupFieldsByCategory(fixedSchemaFieldsForForm).map((category) => (
                        <Box key={category.label} sx={{ display: 'grid', gap: 0 }}>
                          {/* En-tête de catégorie */}
                          <Stack
                            direction="row"
                            alignItems="center"
                            spacing={1}
                            sx={{
                              px: 1.5,
                              py: 0.75,
                              borderRadius: '8px 8px 0 0',
                              background: 'linear-gradient(90deg,rgba(124,91,168,.18) 0%,rgba(124,91,168,.06) 100%)',
                              border: '1px solid rgba(61,90,138,.20)',
                              borderBottom: 'none',
                            }}
                          >
                            <Typography variant="subtitle2" fontWeight={800} color="#1e2d5a">
                              {category.label}
                            </Typography>
                            <Chip
                              label={`${category.fields.length} champs`}
                              size="small"
                              color="default"
                              variant="outlined"
                              sx={{ fontSize: '0.68rem', height: 18, '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }}
                            />
                          </Stack>
                          {/* Corps de la catégorie - Grille responsive */}
                          <Box
                            sx={{
                              p: 2,
                              borderRadius: '0 0 8px 8px',
                              border: '1px solid rgba(124,91,168,.20)',
                              backgroundColor: 'rgba(240,235,250,0.92)',
                              maxHeight: 500,
                              overflowY: 'auto',
                              display: 'grid',
                              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                              gap: 1.5,
                            }}
                          >
                            {category.fields.map((field) => {
                              // Ne pas afficher les champs auto-générés en édition (sauf si déjà remplis)
                              if (field.field_type === 'auto' && !schemaAnswers[field.key]) {
                                return null;
                              }
                              return renderSchemaFieldInput(field);
                            })}
                          </Box>
                        </Box>
                      ))}
                    </Box>
                  )}

                  {/* ── Séparateur visuel si les deux blocs sont présents ── */}
                  {fixedSchemaFieldsForForm.length > 0 && dynamicSchemaFieldsForForm.length > 0 && (
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ my: -0.5 }}>
                      <Box sx={{ flex: 1, height: '1px', background: `repeating-linear-gradient(90deg, ${PM.rose}40 0, ${PM.rose}40 6px, transparent 6px, transparent 12px)` }} />
                      <Typography variant="caption" sx={{ color: PM.rose, fontWeight: 700, whiteSpace: 'nowrap', fontSize: '0.7rem' }}>
                        colonnes dynamiques ci-dessous
                      </Typography>
                      <Box sx={{ flex: 1, height: '1px', background: `repeating-linear-gradient(90deg, ${PM.rose}40 0, ${PM.rose}40 6px, transparent 6px, transparent 12px)` }} />
                    </Stack>
                  )}

                  {/* ── Bloc 2 : Colonnes dynamiques (importées automatiquement) ── */}
                  {dynamicSchemaFieldsForForm.length > 0 && (
                    <Box sx={{ display: 'grid', gap: 0 }}>
                      {/* En-tête section dynamique */}
                      <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1}
                        sx={{
                          px: 1.5,
                          py: 0.75,
                          borderRadius: '8px 8px 0 0',
                          background: `linear-gradient(90deg, ${PM.rose}18 0%, ${PM.rose}08 100%)`,
                          border: `2px solid rgba(158,61,106,0.30)`,
                          borderBottom: 'none',
                        }}
                      >
                        <Typography variant="subtitle2" fontWeight={800} sx={{ color: PM.rose }}>
                          Colonnes dynamiques
                        </Typography>
                        <Chip
                          label={`${dynamicSchemaFieldsForForm.length} champs`}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.68rem', height: 18, borderColor: 'rgba(158,61,106,.30)', color: PM.rose, '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }}
                        />
                      </Stack>
                      {/* Corps section dynamique */}
                      <Box
                        sx={{
                          p: 1.5,
                          borderRadius: '0 0 8px 8px',
                          border: `2px solid rgba(158,61,106,0.30)`,
                          backgroundColor: 'rgba(158,61,106,0.06)',
                          maxHeight: 280,
                          overflowY: 'auto',
                          display: 'grid',
                          gap: 1.25,
                        }}
                      >
                        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.25 }}>
                          Ces champs proviennent d'un fichier importé et ne font pas partie du schéma standard de la plateforme.
                        </Typography>
                        {dynamicSchemaFieldsForForm.map((field) => renderSchemaFieldInput(field))}
                      </Box>
                    </Box>
                  )}

                  {/* Colonnes extra_data non encore dans le schéma (seulement en mode édition) */}
                  {form.id && formDynamicExtraColumns.length > 0 && (
                    <Box sx={{ display: 'grid', gap: 0 }}>
                      <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1}
                        sx={{
                          px: 1.5,
                          py: 0.75,
                          borderRadius: '8px 8px 0 0',
                          background: 'linear-gradient(90deg, rgba(103,58,183,0.10) 0%, rgba(103,58,183,0.04) 100%)',
                          border: '1px dashed rgba(103,58,183,0.30)',
                          borderBottom: 'none',
                        }}
                      >
                        <Typography variant="subtitle2" fontWeight={800} sx={{ color: 'rgb(103,58,183)' }}>
                          Données supplémentaires (ce patient)
                        </Typography>
                        <Chip
                          label={`${formDynamicExtraColumns.length}`}
                          size="small"
                          sx={{ fontSize: '0.68rem', height: 18, backgroundColor: 'rgba(103,58,183,0.12)', color: 'rgb(103,58,183)', '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }}
                        />
                      </Stack>
                      <Box
                        sx={{
                          p: 1.5,
                          borderRadius: '0 0 8px 8px',
                          border: '1px dashed rgba(103,58,183,0.30)',
                          backgroundColor: 'rgba(243,237,255,0.55)',
                          maxHeight: 220,
                          overflowY: 'auto',
                          display: 'grid',
                          gap: 1.25,
                        }}
                      >
                        {formDynamicExtraColumns.map((columnKey) => (
                          <TextField
                            key={`dynamic-form-${columnKey}`}
                            label={columnKey}
                            value={extraDataValues[columnKey] ?? ''}
                            onChange={(event) => handleExtraDataFieldChange(columnKey, event.target.value)}
                            size="small"
                            fullWidth
                          />
                        ))}
                      </Box>
                    </Box>
                  )}

                  <Stack direction="row" spacing={1.5}>
                    <Button type="submit" variant="contained" disabled={saving} startIcon={<AddCircleOutlineOutlinedIcon />} fullWidth>
                      {form.id ? 'Modifier' : 'Créer'}
                    </Button>
                    <Button type="button" variant="outlined" onClick={resetForm} fullWidth>
                      Réinitialiser
                    </Button>
                  </Stack>
                  <Button type="button" variant="outlined" startIcon={<FileDownloadOutlinedIcon />} onClick={handleExportExcel} fullWidth>
                    Télécharger les données (Excel)
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
        ) : (
          <Stack spacing={3}>
            <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
              <CardContent>
                <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
                  <Box>
                    <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Tableau d'analyse clinique</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Vue professionnelle orientee activite et risques cliniques.
                    </Typography>
                  </Box>
                  <Tabs
                    value={analysisView}
                    onChange={(_, value) => setAnalysisView(value)}
                    variant="scrollable"
                    allowScrollButtonsMobile
                    sx={{ minHeight: 38, '& .MuiTab-root': { fontFamily: 'inherit', fontWeight: 600, textTransform: 'none' }, '& .Mui-selected': { color: '#3d5a8a !important' }, '& .MuiTabs-indicator': { background: 'linear-gradient(90deg,#3d5a8a,#9e3d6a)', height: 3, borderRadius: 2 } }}
                  >
                    <Tab value="synthese" label="Synthese" />
                    <Tab value="profils" label="Profils" />
                    <Tab value="comorbidites" label="Comorbidites" />
                  </Tabs>
                </Stack>
              </CardContent>
            </Card>

            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Card elevation={0} sx={{ borderRadius: '16px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 12px rgba(30,45,90,.04)' }}>
                  <CardContent>
                    <Typography variant="body2" sx={{ color: '#7a90b0', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '.08em', mb: 0.5 }}>Total patients</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 900, color: '#1e2d5a', letterSpacing: '-.03em', lineHeight: 1, fontFamily: 'inherit' }}>{analysisSummary.totalPatients}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card elevation={0} sx={{ borderRadius: '16px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 12px rgba(30,45,90,.04)' }}>
                  <CardContent>
                    <Typography variant="body2" sx={{ color: '#7a90b0', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '.08em', mb: 0.5 }}>Age moyen</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 900, color: '#1e2d5a', letterSpacing: '-.03em', lineHeight: 1, fontFamily: 'inherit' }}>{analysisSummary.averageAge}</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card elevation={0} sx={{ borderRadius: '16px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 12px rgba(30,45,90,.04)' }}>
                  <CardContent>
                    <Typography variant="body2" sx={{ color: '#7a90b0', fontFamily: 'inherit', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '.08em', mb: 0.5 }}>Completude moyenne</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 900, color: '#1e2d5a', letterSpacing: '-.03em', lineHeight: 1, fontFamily: 'inherit' }}>{analysisSummary.averageCompleteness}%</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {analysisView === 'synthese' && (
              <Stack spacing={3}>
                <Grid container spacing={3}>
                  <Grid item xs={12} lg={7}>
                    <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Evolution mensuelle des inclusions</Typography>
                        {analysisSummary.monthlyInclusions.length ? (
                          <Box sx={{ height: 300 }}>
                            <Line data={monthlyInclusionChartData} options={defaultChartOptions} />
                          </Box>
                        ) : <Typography variant="body2" color="text.secondary">Aucune date exploitable pour les inclusions.</Typography>}
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} lg={5}>
                    <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)', height: '100%' }}>
                      <CardContent>
                        <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Points cles</Typography>
                        <Stack spacing={1.5}>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Volume total complications</Typography>
                            <Typography variant="h5" sx={{ fontWeight: 900, color: '#1e2d5a', letterSpacing: '-.02em', fontFamily: 'inherit' }}>{analysisKpis.complicationsTotal}</Typography>
                          </Box>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Profil dominant</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>{analysisKpis.topEtiology}</Typography>
                          </Box>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Complétude moyenne</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>{analysisSummary.averageCompleteness}%</Typography>
                          </Box>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Dossiers récents</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>{analysisSummary.recentActivityCount} ({analysisKpis.recentActivityRate}%)</Typography>
                          </Box>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Dossiers à charge</Typography>
                            <Typography variant="h6" sx={{ fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>{analysisSummary.highBurdenPatients} ({analysisKpis.highBurdenRate}%)</Typography>
                          </Box>
                          <Box>
                            <Typography variant="body2" color="text.secondary">Répartition sexe</Typography>
                            <Stack spacing={1} sx={{ mt: 0.5 }}>
                              {analysisSummary.sexCounts.map((item) => {
                                const percent = analysisSummary.totalPatients ? Math.round((item.count / analysisSummary.totalPatients) * 100) : 0;
                                return (
                                  <Box key={`sex-summary-${item.label}`}>
                                    <Stack direction="row" justifyContent="space-between">
                                      <Typography variant="body2">{item.label}</Typography>
                                      <Typography variant="body2" fontWeight={700}>{percent}%</Typography>
                                    </Stack>
                                    <LinearProgress variant="determinate" value={percent} sx={{ mt: 0.5, height: 8, borderRadius: 999, '& .MuiLinearProgress-bar': { background: 'linear-gradient(90deg,#3d5a8a,#9e3d6a)' } }} />
                                  </Box>
                                );
                              })}
                            </Stack>
                          </Box>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Complications dans le temps (barres empilees)</Typography>
                    {analysisSummary.monthlyComplications.length ? (
                      <Box sx={{ height: 320 }}>
                        <Bar
                          data={monthlyComplicationsChartData}
                          options={{
                            ...defaultChartOptions,
                            scales: {
                              x: { stacked: true },
                              y: {
                                ...(defaultChartOptions.scales?.y || {}),
                                stacked: true,
                              },
                            },
                          }}
                        />
                      </Box>
                    ) : <Typography variant="body2" color="text.secondary">Aucune date exploitable pour les complications.</Typography>}
                  </CardContent>
                </Card>
              </Stack>
            )}

            {analysisView === 'profils' && (
              <Stack spacing={3}>
                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 0.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Graphe 3D profil patient</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                      Projection 3D interactive: age, comorbidites et complications.
                    </Typography>
                    {analysisSummary.profile3dPoints.length ? (
                      <>
                        <Box sx={{ px: 1, mb: 1.5 }}>
                          <Typography variant="caption" color="text.secondary">Angle 3D: {profile3dAngle}°</Typography>
                          <Slider
                            value={profile3dAngle}
                            onChange={(_, value) => setProfile3dAngle(Number(value))}
                            min={0}
                            max={85}
                            step={1}
                            valueLabelDisplay="auto"
                            size="small"
                          />
                        </Box>
                        <Box sx={{ height: 360 }}>
                          <Bubble data={profileProjectedBubbleData} options={profileBubbleOptions} />
                        </Box>
                      </>
                    ) : <Typography variant="body2" color="text.secondary">Aucune donnee suffisante pour le graphe 3D.</Typography>}
                  </CardContent>
                </Card>

                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Distribution age par sexe</Typography>
                    <Box sx={{ height: 320 }}>
                      <Bar data={ageSexHistogramData} options={defaultChartOptions} />
                    </Box>
                  </CardContent>
                </Card>

                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Etiologie IRC vers statut inclusion (barres groupees)</Typography>
                    {analysisSummary.etiologyInclusionGrouped.labels.length ? (
                      <Box sx={{ height: 330 }}>
                        <Bar data={etiologyInclusionChartData} options={defaultChartOptions} />
                      </Box>
                    ) : <Typography variant="body2" color="text.secondary">Aucune donnee suffisante pour le graphe etiologie/inclusion.</Typography>}
                  </CardContent>
                </Card>
              </Stack>
            )}

            {analysisView === 'comorbidites' && (
              <Stack spacing={3}>
                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Barres des comorbidites les plus frequentes</Typography>
                    <Stack spacing={1.5}>
                      {analysisSummary.topComorbidities.length ? analysisSummary.topComorbidities.map((item) => {
                        const percent = analysisSummary.totalPatients
                          ? Math.round((item.count / analysisSummary.totalPatients) * 100)
                          : 0;
                        return (
                          <Box key={`comorb-${item.label}`}>
                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                              <Typography variant="body2">{item.label}</Typography>
                              <Typography variant="body2" fontWeight={700}>{item.count} ({percent}%)</Typography>
                            </Stack>
                            <LinearProgress
                              variant="determinate"
                              value={percent}
                              sx={{
                                mt: 0.75,
                                height: 8,
                                borderRadius: 999,
                                '& .MuiLinearProgress-bar': {
                                  background: 'linear-gradient(90deg,#3d5a8a,#9e3d6a)',
                                },
                              }}
                            />
                          </Box>
                        );
                      }) : (
                        <Typography variant="body2" color="text.secondary">Aucune donnee comorbidite exploitable.</Typography>
                      )}
                    </Stack>
                  </CardContent>
                </Card>

                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>Top combinaisons de comorbidites</Typography>
                    {analysisSummary.topComorbidityCombinations.length ? (
                      <Box sx={{ height: 340 }}>
                        <Bar
                          data={comorbidityCombinationChartData}
                          options={{
                            ...defaultChartOptions,
                            indexAxis: 'y',
                          }}
                        />
                      </Box>
                    ) : (
                      <Typography variant="body2" color="text.secondary">Aucune combinaison de comorbidites disponible.</Typography>
                    )}
                  </CardContent>
                </Card>
              </Stack>
            )}

          </Stack>
        )}
          </>
        ) : (
          <Stack spacing={3}>
            <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#1e2d5a', letterSpacing: '-.02em', fontFamily: 'inherit' }}>
                  Modele AI
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  Espace dedie aux modeles IA: experimentation, evaluation et suivi des performances.
                </Typography>
              </CardContent>
            </Card>

            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>
                      Entrainement du modele
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Zone reservee pour lancer les entrainements, choisir les features et comparer les versions du modele.
                    </Typography>
                    <Button variant="contained" sx={{ mt: 2, borderRadius: '10px', background: 'linear-gradient(135deg,#3d5a8a,#1e2d5a)', textTransform: 'none', fontWeight: 700, fontFamily: 'inherit' }} disabled>
                      Configurer (bientot)
                    </Button>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card elevation={0} sx={{ borderRadius: '20px', border: '1px solid rgba(61,90,138,.10)', boxShadow: '0 2px 16px rgba(30,45,90,.05)' }}>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 1, fontWeight: 800, color: '#1e2d5a', letterSpacing: '-.01em', fontFamily: 'inherit' }}>
                      Evaluation et inference
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Zone reservee pour la prediction IA, la qualite du modele et la visualisation des metriques cliniques.
                    </Typography>
                    <Button variant="outlined" sx={{ mt: 2, borderRadius: '10px', borderColor: 'rgba(61,90,138,.35)', color: '#3d5a8a', textTransform: 'none', fontWeight: 700, fontFamily: 'inherit' }} disabled>
                      Ouvrir module IA (bientot)
                    </Button>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Stack>
        )}
      </Stack>
        </Grid>
      </Grid>

      <Dialog open={isEditDialogOpen} onClose={closeEditDialog} fullWidth maxWidth="lg"
        PaperProps={{ sx: PAGE_STYLES.dialogPaper }}>
        <DialogTitle sx={{ fontFamily: 'inherit', fontWeight: 800, color: '#1e2d5a', borderBottom: '1px solid rgba(61,90,138,.10)', background: 'linear-gradient(135deg, rgba(168,207,238,.22), rgba(255,255,255,.98))', py: 2.2 }}>Modifier la ligne sélectionnée</DialogTitle>
        <Box component="form" onSubmit={handleSave}>
          <DialogContent dividers sx={{ display: 'grid', gap: 2.25, background: 'linear-gradient(180deg, rgba(248,251,255,.96), rgba(255,255,255,.98))', py: 2.5, maxHeight: 'calc(100vh - 280px)', overflowY: 'auto', overflowX: 'hidden', '&::-webkit-scrollbar': { width: '8px' }, '&::-webkit-scrollbar-track': { background: 'rgba(61,90,138,.05)', borderRadius: '10px' }, '&::-webkit-scrollbar-thumb': { background: 'rgba(61,90,138,.20)', borderRadius: '10px', '&:hover': { background: 'rgba(61,90,138,.30)' } } }}>
            {/* ── Dialogue d'édition avec TOUS les 150+ champs organisés par catégories ── */}
            {fixedSchemaFieldsForForm.length > 0 && (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {groupFieldsByCategory(fixedSchemaFieldsForForm).map((category) => (
                  <Box key={category.label} sx={{ display: 'grid', gap: 0 }}>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 1.5, py: 0.75, borderRadius: '8px 8px 0 0', background: 'linear-gradient(90deg,rgba(124,91,168,.18) 0%,rgba(124,91,168,.06) 100%)', border: '1px solid rgba(124,91,168,.20)', borderBottom: 'none' }}>
                      <Typography variant="subtitle2" fontWeight={800} color="#1e2d5a">{category.label}</Typography>
                      <Chip label={`${category.fields.length} champs`} size="small" color="default" variant="outlined" sx={{ fontSize: '0.68rem', height: 18, '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }} />
                    </Stack>
                    <Box sx={{ p: 2, borderRadius: '0 0 8px 8px', border: '1px solid rgba(124,91,168,.20)', backgroundColor: 'rgba(240,235,250,0.92)', maxHeight: 500, overflowY: 'auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 1.5 }}>
                      {category.fields.map((field) => {
                        if (field.field_type === 'auto' && !schemaAnswers[field.key]) return null;
                        return renderSchemaFieldInput(field);
                      })}
                    </Box>
                  </Box>
                ))}
              </Box>
            )}

            {/* ── Bloc 2 : Colonnes dynamiques dans le dialogue ── */}
            {dynamicSchemaFieldsForForm.length > 0 && (
              <Box sx={{ p: 1.5, borderRadius: 2, border: '2px solid', borderColor: 'rgba(158,61,106,.18)', backgroundColor: 'rgba(158,61,106,0.06)', maxHeight: 280, overflowY: 'auto', display: 'grid', gap: 1.25 }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
                  <Typography variant="subtitle2" fontWeight={800} sx={{ color: PM.rose }}>Colonnes dynamiques</Typography>
                  <Chip label={`${dynamicSchemaFieldsForForm.length} champs`} size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 18, borderColor: 'rgba(158,61,106,.30)', color: PM.rose, '& .MuiChip-icon': { display: 'none' }, '& .MuiAvatar-root': { display: 'none' } }} />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: -0.5, mb: 0.5 }}>Colonnes détectées automatiquement lors d'un import Excel.</Typography>
                {dynamicSchemaFieldsForForm.map((field) => renderSchemaFieldInput(field))}
              </Box>
            )}

            {renderDynamicExtraFields('Données supplémentaires de ce patient')}
          </DialogContent>
          <DialogActions sx={{ px: 3, py: 2.25, background: 'linear-gradient(180deg, rgba(255,255,255,.98), rgba(247,250,255,.95))', borderTop: '1px solid rgba(61,90,138,.10)' }}>
            <Button type="button" onClick={closeEditDialog} sx={{ borderRadius: '14px', color: '#7a90b0', fontFamily: 'inherit', textTransform: 'none', fontWeight: 700 }}>Annuler</Button>
            <Button type="submit" variant="contained" disabled={saving} sx={{ borderRadius: '14px', background: 'linear-gradient(135deg,#3d5a8a,#1e2d5a)', fontFamily: 'inherit', textTransform: 'none', fontWeight: 800, boxShadow: '0 10px 22px rgba(30,45,90,.22)' }}>Enregistrer</Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}

export default PatientsManagement;