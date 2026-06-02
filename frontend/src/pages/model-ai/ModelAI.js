import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress,
  Divider, Grid, InputAdornment, Paper, Stack,
  Tab, Tabs, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Table, TextField, Typography,
} from '@mui/material';
import SearchIcon         from '@mui/icons-material/Search';
import PlayArrowIcon      from '@mui/icons-material/PlayArrow';
import RefreshIcon        from '@mui/icons-material/Refresh';
import WarningAmberIcon   from '@mui/icons-material/WarningAmber';
import { Doughnut, Bar, Line } from 'react-chartjs-2';
import {
  Chart as ChartJS, ArcElement, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement,
  PointElement, LineElement, Filler,
} from 'chart.js';
import AppSidebar from '../../components/common/AppSidebar';
import api        from '../../services/api/axios';

ChartJS.register(
  ArcElement, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement,
  PointElement, LineElement, Filler,
);

// ── Palette identique aux autres pages ───────────────────────────────────────
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
  white:  '#ffffff',
};

// ── Variables du modèle SVM (32 features) ────────────────────────────────────
const FEATURE_LABELS = {
  fistule_arterioveineuse_creee:      { label: 'Fistule artério-veineuse (FAV)', binary: true,  group: 'Dialyse' },
  admission_cathetere_tunnellise:     { label: "Cathéter tunnellisé à l'admission", binary: true,  group: 'Dialyse' },
  hemodialyse:                        { label: 'Hémodialyse',                binary: true,  group: 'Dialyse' },
  seances_par_semaine:                { label: 'Séances / semaine',           unit: '',       group: 'Dialyse' },
  annee_inclusion:                    { label: 'Année début dialyse',         unit: '',       group: 'Dialyse' },
  du_residuelle:                      { label: 'Diurèse résiduelle',          binary: true,  group: 'Dialyse' },

  albumine_basale:                    { label: 'Albumine',                    unit: 'g/L',    group: 'Biologie' },
  calcium_basale:                     { label: 'Calcium corrigé',             unit: 'mg/L',   group: 'Biologie' },
  ferritine_basale:                   { label: 'Ferritine',                   unit: 'ng/mL',  group: 'Biologie' },
  pth_basale:                         { label: 'PTH',                         unit: 'pg/mL',  group: 'Biologie' },
  sodium_lt130:                       { label: 'Sodium < 130 mmol/L',         binary: true,  group: 'Biologie' },
  albumine_lt35:                      { label: 'Albumine < 35 g/L',           binary: true,  group: 'Biologie' },

  diabete:                            { label: 'Diabète',                     binary: true,  group: 'Comorbidités' },
  hypertension:                       { label: 'Hypertension artérielle',     binary: true,  group: 'Comorbidités' },
  cardiopathie:                       { label: 'Cardiopathie',                binary: true,  group: 'Comorbidités' },
  maladie_renale_hereditaire:         { label: 'Maladie rénale héréditaire',  binary: true,  group: 'Comorbidités' },
  etiologie_mrc:                      { label: 'Étiologie MRC (code)',        unit: '',       group: 'Comorbidités' },
  couverture_medicale:                { label: 'Couverture médicale',         unit: '(0–3)',  group: 'Comorbidités' },

  dyspnee:                            { label: 'Dyspnée',                     binary: true,  group: 'Clinique' },
  oedemes_surcharge:                  { label: 'Œdèmes / surcharge',          binary: true,  group: 'Clinique' },
  douleur_abdominale:                 { label: 'Douleur abdominale',          binary: true,  group: 'Clinique' },
  crise_convulsive:                   { label: 'Crise convulsive',            binary: true,  group: 'Clinique' },
  evenement_cardiovasculaire:         { label: 'Événement cardiovasculaire',  binary: true,  group: 'Clinique' },
  nombre_hospitalisations:            { label: "Nombre d'hospitalisations",   unit: '',       group: 'Clinique' },
  liste_attente_transplantation:      { label: 'Liste attente transplant.',   binary: true,  group: 'Clinique' },
  information_transplantation_donnee: { label: 'Info transplant. donnée',     binary: true,  group: 'Clinique' },

  age_x_charlson:                     { label: 'Âge × Charlson',             unit: '',       group: 'Interactions' },
  dyspnee_x_oedeme:                   { label: 'Dyspnée × Œdème',            unit: '',       group: 'Interactions' },
  charlson_x_hosp:                    { label: 'Charlson × Hosp.',           unit: '',       group: 'Interactions' },
  hypert_x_cardio:                    { label: 'HTA × Cardiopathie',         unit: '',       group: 'Interactions' },
  albumine_x_hosp:                    { label: 'Albumine × Hosp.',           unit: '',       group: 'Interactions' },
  age_x_cardio:                       { label: 'Âge × Cardiopathie',         unit: '',       group: 'Interactions' },
};

// ── Résolution feature ML → valeur dans l'objet patient ─────────────────────
const _NUMERIC_MAP = {
  albumine_basale:   'biologie_albumine_g_l',
  calcium_basale:    'biologie_calcium_corrige_mg_l',
  pth_basale:        'biologie_pth_pg_ml',
  ferritine_basale:  'biologie_ferritine_ng_ml',
  seances_par_semaine:        'dialyse_seances_par_semaine',
  nombre_hospitalisations:    'complication_nombre_hospitalisations',
  couverture_medicale:        'demographie_couverture_sociale',
  etiologie_mrc:              'irc_etiologie_principale',
};

const _BINARY_MAP = {
  liste_attente_transplantation:      'dialyse_statut_liste_attente_transplantation',
  information_transplantation_donnee: 'dialyse_information_transplantation_donnee',
  maladie_renale_hereditaire:         'irc_maladie_renale_hereditaire',
  du_residuelle:                      'dialyse_statut_fonction_renale_residuelle',
};

const _KEYWORD_MAP = {
  hemodialyse:               { fields: ['dialyse_modalite_actuelle', 'dialyse_modalite_initiale'], kw: ['hemodialyse', 'hémodialyse', 'hd', 'hemodiafiltration'] },
  dyspnee:                   { fields: ['presentation_symptomes'],   kw: ['dyspnee', 'dyspnée', 'essoufflement'] },
  oedemes_surcharge:         { fields: ['presentation_symptomes'],   kw: ['oedeme', 'œdème', 'surcharge', 'edeme'] },
  crise_convulsive:          { fields: ['complication_liste'],       kw: ['convulsion', 'epilepsie', 'crise'] },
  douleur_abdominale:        { fields: ['presentation_symptomes'],   kw: ['douleur abdominale', 'abdominal'] },
  evenement_cardiovasculaire:{ fields: ['complication_liste'],       kw: ['cardiovasculaire', 'infarctus', 'avc'] },
  hypertension:              { fields: ['comorbidite_liste'],        kw: ['hypertension', 'hta'] },
  cardiopathie:              { fields: ['comorbidite_liste'],        kw: ['cardiopathie', 'insuffisance cardiaque'] },
  diabete:                   { fields: ['comorbidite_statut_diabete', 'comorbidite_liste'], kw: ['diabete', 'diabète', 'diabetes'] },
  fistule_arterioveineuse_creee:  { fields: ['dialyse_type_acces_initial'], kw: ['fistule'] },
  admission_cathetere_tunnellise: { fields: ['dialyse_type_acces_initial'], kw: ['catheter', 'cathetere', 'tunnelli'] },
};

function _toBin(v) {
  if (v === null || v === undefined || v === '') return null;
  const s = String(v).trim().toLowerCase();
  if (['oui','yes','1','true','vrai'].includes(s)) return 1;
  if (['non','no','0','false','faux'].includes(s)) return 0;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function resolveFeature(patient, key) {
  // 1. extra_data direct (import Excel)
  const ed = patient.extra_data;
  if (ed && typeof ed === 'object' && ed[key] !== undefined && ed[key] !== null && ed[key] !== '') {
    return ed[key];
  }
  // 2. Numeric direct mapping
  if (_NUMERIC_MAP[key]) {
    const v = patient[_NUMERIC_MAP[key]];
    return (v !== null && v !== undefined && v !== '') ? v : null;
  }
  // 3. Binary direct mapping
  if (_BINARY_MAP[key]) {
    return _toBin(patient[_BINARY_MAP[key]]);
  }
  // 4. Keyword-based binary
  if (_KEYWORD_MAP[key]) {
    const cfg = _KEYWORD_MAP[key];
    const direct = _toBin(patient[key]);
    if (direct !== null) return direct;
    for (const f of cfg.fields) {
      const text = String(patient[f] || '').toLowerCase();
      if (cfg.kw.some(k => text.includes(k))) return 1;
    }
    return 0;
  }
  // 5. Computed features
  if (key === 'annee_inclusion') {
    const d = patient.dialyse_date_debut;
    if (!d) return null;
    const y = String(d).match(/(\d{4})/);
    return y ? parseInt(y[1]) : null;
  }
  if (key === 'sodium_lt130') {
    const v = parseFloat(patient.biologie_sodium_mmol_l);
    return isNaN(v) ? null : v < 130 ? 1 : 0;
  }
  if (key === 'albumine_lt35') {
    const v = parseFloat(patient.biologie_albumine_g_l);
    return isNaN(v) ? null : v < 35 ? 1 : 0;
  }
  // 6. Interaction features
  const age = parseFloat(patient.demographie_age_ans || patient.age);
  const charlson = parseFloat(patient.icc_charlson);
  const alb = parseFloat(resolveFeature(patient, 'albumine_basale'));
  const hospRaw = patient.complication_nombre_hospitalisations;
  const hosp = (hospRaw !== null && hospRaw !== undefined && hospRaw !== '') ? parseFloat(hospRaw) : 0;
  const dysp = resolveFeature(patient, 'dyspnee');
  const oede = resolveFeature(patient, 'oedemes_surcharge');
  const hta  = resolveFeature(patient, 'hypertension');
  const card = resolveFeature(patient, 'cardiopathie');
  if (key === 'age_x_charlson')  return !isNaN(age) && !isNaN(charlson) ? parseFloat((age * charlson).toFixed(1)) : null;
  if (key === 'dyspnee_x_oedeme') return (dysp != null && oede != null) ? dysp * oede : null;
  if (key === 'charlson_x_hosp') return !isNaN(charlson) && !isNaN(hosp) ? parseFloat((charlson * hosp).toFixed(1)) : null;
  if (key === 'hypert_x_cardio') return (hta != null && card != null) ? hta * card : null;
  if (key === 'albumine_x_hosp') return !isNaN(alb) && !isNaN(hosp) ? parseFloat((alb * hosp).toFixed(1)) : null;
  if (key === 'age_x_cardio')    return !isNaN(age) && card != null ? parseFloat((age * card).toFixed(1)) : null;
  // Fallback
  const direct = patient[key];
  return (direct !== null && direct !== undefined && direct !== '') ? direct : null;
}

const GROUP_COLORS = {
  'Dialyse':      { bg: 'rgba(61,90,138,.08)',  border: 'rgba(61,90,138,.18)',  text: '#3d5a8a' },
  'Biologie':     { bg: 'rgba(39,174,96,.07)',  border: 'rgba(39,174,96,.18)',  text: '#1e8449' },
  'Comorbidités': { bg: 'rgba(230,126,34,.07)', border: 'rgba(230,126,34,.18)', text: '#b7770d' },
  'Clinique':     { bg: 'rgba(142,68,173,.07)', border: 'rgba(142,68,173,.18)', text: '#7d3c98' },
  'Interactions': { bg: 'rgba(180,180,180,.07)',border: 'rgba(180,180,180,.20)', text: '#7a90b0' },
};

// ── Shell global — copié exactement depuis PatientsManagement ─────────────────
const shellSx = {
  minHeight: '100vh',
  py: 0, px: 0,
  position: 'relative',
  overflowX: 'hidden',
  background: [
    'radial-gradient(circle at top left,  rgba(168,207,238,.48), transparent 34%)',
    'radial-gradient(circle at top right, rgba(158,61,106,.14),  transparent 28%)',
    'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 42%,#f4eef8 100%)',
  ].join(', '),
  fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
  '&::before': {
    content: '""', position: 'fixed', inset: 0, pointerEvents: 'none',
    background: 'linear-gradient(135deg, rgba(255,255,255,.34), rgba(255,255,255,0))',
    zIndex: 0,
  },
  '& .MuiCard-root': {
    position: 'relative', zIndex: 1,
    fontFamily: 'inherit',
    borderRadius: '24px',
    border: '1px solid rgba(61,90,138,.10)',
    boxShadow: '0 12px 32px rgba(30,45,90,.06)',
    backdropFilter: 'blur(12px)',
    backgroundImage: 'linear-gradient(180deg, rgba(255,255,255,.95), rgba(255,255,255,.88))',
  },
  '& .MuiButton-root': { fontFamily: 'inherit', textTransform: 'none', fontWeight: 700, borderRadius: '14px', boxShadow: 'none' },
  '& .MuiButton-contained': {
    background: 'linear-gradient(135deg,#3d5a8a,#1e2d5a)',
    boxShadow: '0 10px 22px rgba(30,45,90,.18)',
    '&:hover': { background: 'linear-gradient(135deg,#4a6fa8,#2a3d72)', boxShadow: '0 14px 26px rgba(30,45,90,.22)' },
  },
  '& .MuiTextField-root .MuiOutlinedInput-root': {
    borderRadius: '14px', background: 'rgba(255,255,255,.92)',
    '& fieldset': { borderColor: 'rgba(61,90,138,.18)' },
    '&:hover fieldset': { borderColor: 'rgba(61,90,138,.40)' },
    '&.Mui-focused fieldset': { borderColor: '#3d5a8a', borderWidth: 2 },
  },
  '& .MuiTableCell-head': {
    fontWeight: 800, color: '#1e2d5a', fontFamily: 'inherit',
    fontSize: '0.78rem', letterSpacing: '.02em', textTransform: 'uppercase',
    background: 'linear-gradient(135deg, rgba(168,207,238,.28), rgba(61,90,138,.10))',
  },
  '& .MuiTableCell-body': { fontFamily: 'inherit', color: '#2d3f6a', fontSize: '0.83rem' },
  '& .MuiTableRow-hover:hover': { background: 'rgba(168,207,238,.10) !important' },
  '& .MuiAlert-root': { borderRadius: '16px', fontFamily: 'inherit', boxShadow: '0 8px 22px rgba(30,45,90,.06)' },
  '& .MuiLinearProgress-root': { borderRadius: 999, height: 8 },
  '& .MuiLinearProgress-bar': { background: 'linear-gradient(90deg,#3d5a8a,#9e3d6a)' },
  '& .MuiChip-root': { fontFamily: 'inherit', fontWeight: 700 },
  '& .MuiTab-root': { fontFamily: 'inherit' },
};

// ── Hero card — identique à PatientsManagement ────────────────────────────────
const heroCardSx = {
  borderRadius: '28px',
  border: '1px solid rgba(61,90,138,.12)',
  background: 'linear-gradient(135deg, rgba(255,255,255,.94), rgba(255,255,255,.84))',
  position: 'relative', overflow: 'hidden',
  boxShadow: '0 16px 44px rgba(30,45,90,.10)',
  '&::before': {
    content: '""', position: 'absolute', inset: '0 0 auto 0', height: 5,
    background: `linear-gradient(90deg,${PM.sky},${PM.steel},${PM.rose},${PM.blush})`,
  },
  '&::after': {
    content: '""', position: 'absolute', top: -60, right: -60,
    width: 200, height: 200, borderRadius: '50%',
    background: `radial-gradient(circle, rgba(158,61,106,.06), transparent 70%)`,
    pointerEvents: 'none',
  },
};

const RISK = {
  Faible: { color: '#27AE60', bg: '#E8F8F0', grad: '#27AE60, #1e8449' },
  Modéré: { color: '#E67E22', bg: '#FEF3E2', grad: '#E67E22, #ca6f1e' },
  Élevé:  { color: '#E74C3C', bg: '#FDEDEC', grad: '#E74C3C, #c0392b' },
};

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ pt: 2.5 }}>{children}</Box>}
    </div>
  );
}

// ── Carte statistique ────────────────────────────────────────────────────────
function StatCard({ label, value, sub, accent }) {
  return (
    <Card sx={{ height: '100%', borderTop: `4px solid ${accent} !important` }}>
      <CardContent sx={{ p: 2.5 }}>
        <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em', fontSize: '0.7rem' }}>
          {label}
        </Typography>
        <Typography variant="h5" sx={{ color: accent, fontWeight: 900, mt: 0.5, lineHeight: 1.1 }}>
          {value}
        </Typography>
        {sub && <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.72rem' }}>{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

export default function ModelAI() {
  const [activeTab, setActiveTab]             = useState(0);
  const [patients, setPatients]               = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [predictionResult, setPredictionResult] = useState(null);
  const [loading, setLoading]                 = useState(false);
  const [searchTerm, setSearchTerm]           = useState('');
  const [predicting, setPredicting]           = useState(false);
  const [editedValues, setEditedValues]       = useState({});
  const [simResult, setSimResult]             = useState(null);
  const [simulating, setSimulating]           = useState(false);

  const fetchPatients = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('patients/?limit=1000');
      setPatients(res.data.results || res.data || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPatients(); }, [fetchPatients]);

  const filteredPatients = patients.filter(p => {
    const s = searchTerm.toLowerCase();
    return (p.nom?.toLowerCase().includes(s) || p.prenom?.toLowerCase().includes(s) || p.id?.toString().includes(s));
  });

  const handlePredict = useCallback(async () => {
    if (!selectedPatient) return;
    try {
      setPredicting(true);
      const res = await api.get(`predictions/patient/${selectedPatient.id}/mortalite/`);
      setPredictionResult(res.data);
      setActiveTab(2);
    } catch (e) {
      setPredictionResult({ error: e.response?.data?.error || 'Erreur lors de la prédiction' });
      setActiveTab(2);
    } finally { setPredicting(false); }
  }, [selectedPatient]);

  const handleReset = () => { setSelectedPatient(null); setPredictionResult(null); setEditedValues({}); setSimResult(null); setActiveTab(1); };

  const handleSimulate = useCallback(async () => {
    if (!selectedPatient) return;
    try {
      setSimulating(true);
      setSimResult(null);
      const res = await api.post(`predictions/patient/${selectedPatient.id}/mortalite/`, { features: editedValues });
      setSimResult(res.data);
    } catch (e) {
      setSimResult({ error: e.response?.data?.error || 'Erreur lors de la simulation' });
    } finally { setSimulating(false); }
  }, [selectedPatient, editedValues]);

  // ── Tableau de bord ─────────────────────────────────────────────────────────
  const DashboardTab = () => {
    const cf = { family: "'Plus Jakarta Sans', system-ui, sans-serif" };

    // ── KPIs clairs pour le médecin — issues cliniques réelles ──────────────
    const total = patients.length;

    const enVie       = patients.filter(p => /vivant|surviv|en vie/i.test(String(p.devenir_statut || ''))).length;
    const nbDeces     = patients.filter(p => /dece/i.test(String(p.devenir_statut || ''))).length;
    const nbTranspl   = patients.filter(p => /transpl/i.test(String(p.devenir_statut || ''))).length;
    const sansIssue   = patients.filter(p => !p.devenir_statut || String(p.devenir_statut).trim() === '').length;

    const ages = patients
      .map(p => parseFloat(p.demographie_age_ans || p.age))
      .filter(a => !isNaN(a) && a > 0);
    const avgAge = ages.length ? Math.round(ages.reduce((s, a) => s + a, 0) / ages.length) : null;

    const liveStats = [
      {
        icon: null,
        color: PM.steel,
        label: 'Total patients',
        value: total || '—',
        sub: avgAge ? `Âge moyen : ${avgAge} ans` : 'Base de données',
        alert: false,
      },
      {
        icon: null,
        color: '#2E86AB',
        label: 'Âge moyen',
        value: avgAge ? `${avgAge} ans` : '—',
        sub: ages.length ? `Calculé sur ${ages.length} patients` : 'Données insuffisantes',
        alert: false,
      },
      {
        icon: null,
        color: '#27AE60',
        label: 'Patients en vie',
        value: total ? enVie : '—',
        sub: total && enVie ? `${Math.round(enVie / total * 100)} % de la cohorte` : 'Statut "vivant" enregistré',
        alert: false,
      },
      {
        icon: null,
        color: '#E74C3C',
        label: 'Décès enregistrés',
        value: total ? nbDeces : '—',
        sub: total && nbDeces ? `${Math.round(nbDeces / total * 100)} % de la cohorte` : 'Aucun décès enregistré',
        alert: false,
      },
    ];

    // ── Graphe 1 : Combien de patients dans chaque zone ? ──────────────────
    const distData = {
      labels: ['Zone Faible', 'Zone Modérée', 'Zone Élevée'],
      datasets: [{
        label: 'Patients',
        data: [284, 100, 94],
        backgroundColor: ['rgba(39,174,96,.80)', 'rgba(230,126,34,.80)', 'rgba(231,76,60,.80)'],
        borderColor: ['#27AE60', '#E67E22', '#E74C3C'],
        borderWidth: 2, borderRadius: 10, borderSkipped: false,
      }],
    };
    const distOpts = {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => ` ${c.parsed.y} patients (${Math.round(c.parsed.y/478*100)} % de la cohorte)` },
          bodyFont: cf, titleFont: cf,
        },
      },
      scales: {
        y: { beginAtZero: true, max: 320, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted, callback: v => `${v} pts` } },
        x: { grid: { display: false }, ticks: { font: { ...cf, weight: '700' }, color: PM.navy } },
      },
    };

    // ── Graphe 2 : Que se passe-t-il dans chaque zone ? ───────────────────
    const mortData = {
      labels: ['Zone Faible\n(< 14 %)', 'Zone Modérée\n(14–42 %)', 'Zone Élevée\n(> 42 %)'],
      datasets: [{
        label: 'Décès à 1 an (%)',
        data: [5.1, 29.1, 55.6],
        backgroundColor: ['rgba(39,174,96,.80)', 'rgba(230,126,34,.80)', 'rgba(231,76,60,.80)'],
        borderColor: ['#27AE60', '#E67E22', '#E74C3C'],
        borderWidth: 2, borderRadius: 10, borderSkipped: false,
      }],
    };
    const mortOpts = {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => ` ${c.parsed.y} % des patients de cette zone sont décédés dans l'année` },
          bodyFont: cf, titleFont: cf,
        },
      },
      scales: {
        y: { beginAtZero: true, max: 75, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted, callback: v => `${v} %` } },
        x: { grid: { display: false }, ticks: { font: { ...cf, weight: '700' }, color: PM.navy } },
      },
    };

    // ── Graphe 3 : Le modèle est-il fiable ? (résultats cliniques simples) ─
    const perfData = {
      labels: ['Patients à risque\nidentifiés', 'Patients sains\nbien classés', 'Patients classés\nen Zone Élevée\nqui décèdent'],
      datasets: [{
        label: 'Résultat (%)',
        data: [73, 78, 60.6],
        backgroundColor: ['rgba(39,174,96,.80)', 'rgba(61,90,138,.80)', 'rgba(231,76,60,.80)'],
        borderColor: ['#27AE60', PM.steel, '#E74C3C'],
        borderWidth: 2, borderRadius: 10, borderSkipped: false,
      }],
    };
    const perfOpts = {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => ` ${c.parsed.x} %` },
          bodyFont: cf, titleFont: cf,
        },
      },
      scales: {
        x: { beginAtZero: true, max: 100, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted, callback: v => `${v} %` } },
        y: { grid: { display: false }, ticks: { font: { ...cf, weight: '700', size: 11 }, color: PM.navy } },
      },
    };

    // ── Graphe 4 : Facteurs de risque clés (langage médical) ──────────────
    const riskData = {
      labels: [
        'Albumine basse (< 35 g/L)',
        'Âge élevé + comorbidités',
        'Antécédent cardiovasculaire',
        'Dyspnée présente',
        'Hypoalbuminémie (valeur brute)',
        'Comorbidités + hospitalisations',
      ],
      datasets: [{
        label: 'Poids dans la prédiction',
        data: [18.5, 15.2, 12.8, 11.4, 10.6, 9.2],
        backgroundColor: [
          'rgba(231,76,60,.85)', 'rgba(231,76,60,.65)',
          'rgba(230,126,34,.85)', 'rgba(230,126,34,.65)',
          'rgba(61,90,138,.75)', 'rgba(61,90,138,.55)',
        ],
        borderColor: ['#E74C3C','#E74C3C','#E67E22','#E67E22',PM.steel,PM.steel],
        borderWidth: 2, borderRadius: 8, borderSkipped: false,
      }],
    };
    const riskOpts = {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: c => ` Ce facteur contribue à ${c.parsed.x} % du score de risque` },
          bodyFont: cf, titleFont: cf,
        },
      },
      scales: {
        x: { beginAtZero: true, max: 22, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted, callback: v => `${v} %` } },
        y: { grid: { display: false }, ticks: { font: { ...cf, size: 11 }, color: PM.navy } },
      },
    };

    const ChartCard = ({ title, subtitle, note, children }) => (
      <Card sx={{ height: '100%' }}>
        <CardContent sx={{ p: 2.5, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 900, color: PM.navy, mb: 0.3, fontSize: '0.95rem' }}>
            {title}
          </Typography>
          <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.73rem', display: 'block', mb: 1.5 }}>
            {subtitle}
          </Typography>
          <Box sx={{ flex: 1 }}>{children}</Box>
          {note && (
            <Box sx={{ mt: 1.5, p: 1.2, borderRadius: '10px', background: 'rgba(61,90,138,.05)', border: '1px solid rgba(61,90,138,.08)' }}>
              <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.7rem', fontStyle: 'italic', lineHeight: 1.5 }}>
                {note}
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>
    );

    return (
      <Stack spacing={2.5}>

        {/* ── KPIs actionnables ────────────────────────────────────────── */}
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800, color: PM.navy, fontSize: '0.9rem' }}>
              État de votre base
            </Typography>
            <Chip label="Live" size="small" sx={{ bgcolor: '#27AE6018', color: '#27AE60', fontWeight: 700, fontSize: '0.65rem', height: 20, border: '1px solid #27AE6035' }} />
            <Box sx={{ flex: 1 }} />
            <Button
              size="small"
              startIcon={loading ? <CircularProgress size={12} sx={{ color: PM.rose }} /> : <RefreshIcon fontSize="small" />}
              onClick={fetchPatients}
              disabled={loading}
              sx={{ fontSize: '0.72rem', color: PM.rose, borderColor: `${PM.rose}60`, border: '1px solid', borderRadius: '10px', px: 1.5, py: 0.4, textTransform: 'none', '&:hover': { bgcolor: `${PM.rose}10` } }}
            >
              Actualiser
            </Button>
          </Box>
          <Grid container spacing={1.5}>
            {liveStats.map(k => (
              <Grid item xs={6} sm={3} key={k.label}>
                <Box sx={{
                  p: 2, borderRadius: '16px', position: 'relative', overflow: 'hidden',
                  border: `1.5px solid ${k.color}30`,
                  background: `linear-gradient(160deg, ${k.color}0e, rgba(255,255,255,.98))`,
                  boxShadow: k.alert ? `0 4px 20px ${k.color}30` : `0 4px 14px ${k.color}0e`,
                }}>
                  {k.alert && (
                    <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${k.color}, ${k.color}88)` }} />
                  )}
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end', mb: 0.5 }}>
                    {k.alert && <Chip label="À voir" size="small" sx={{ bgcolor: `${k.color}18`, color: k.color, fontWeight: 700, fontSize: '0.6rem', height: 18, border: `1px solid ${k.color}30` }} />}
                  </Box>
                  <Typography sx={{ fontWeight: 900, color: k.color, fontSize: '1.6rem', lineHeight: 1.1, mt: 0.5 }}>
                    {loading ? '…' : k.value}
                  </Typography>
                  <Typography variant="caption" sx={{ color: PM.navy, fontWeight: 700, fontSize: '0.72rem', display: 'block', mt: 0.2 }}>
                    {k.label}
                  </Typography>
                  <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.67rem', lineHeight: 1.4, display: 'block' }}>
                    {k.note}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Box>

        {/* ── Graphes ───────────────────────────────────────────────────── */}
        <Grid container spacing={2} alignItems="stretch">
          <Grid item xs={12} sm={6}>
            <ChartCard
              title="Que se passe-t-il dans chaque zone ?"
              subtitle="Taux de décès réels à 1 an — zones définies par GMM (cohorte HD-478, n = 478)"
              note="Zones définies par GMM : Zone Élevée → 55,6 % de décès | Zone Modérée → 29,1 % | Zone Faible → 5,1 %. Risque relatif Élevée/Faible = 11×."
            >
              <Bar data={mortData} options={mortOpts} height={140} />
            </ChartCard>
          </Grid>
          <Grid item xs={12} sm={6}>
            <ChartCard
              title="Quels facteurs augmentent le risque ?"
              subtitle="Les 6 variables cliniques les plus déterminantes dans le calcul du score (sur 32 variables analysées)"
              note="L'albumine basse et l'accumulation de comorbidités sont les signaux les plus forts. La dyspnée et les antécédents cardiovasculaires amplifient le risque."
            >
              <Bar data={riskData} options={riskOpts} height={175} />
            </ChartCard>
          </Grid>
        </Grid>

        {/* ── Analyse de la cohorte réelle ────────────────────────────── */}
        {total > 0 && (() => {
          // Comorbidités
          const comorb = [
            { label: 'Diabète',        count: patients.filter(p => String(p.comorbidite_statut_diabete||'').toLowerCase() === 'oui' || String(p.irc_etiologie_principale||'').toLowerCase().includes('diabet')).length },
            { label: 'Hypertension',   count: patients.filter(p => /hypert|hta/i.test(String(p.comorbidite_liste||''))).length },
            { label: 'Cardiopathie',   count: patients.filter(p => /cardio|infarctus|cardiomyo/i.test(String(p.comorbidite_liste||''))).length },
            { label: 'Anémie',         count: patients.filter(p => /anemie|anémie/i.test(String(p.comorbidite_liste||''))).length },
            { label: 'Maladie héréd.', count: patients.filter(p => String(p.irc_maladie_renale_hereditaire||'').toLowerCase() === 'oui').length },
          ].sort((a, b) => b.count - a.count);

          // Étiologies IRC
          const etioRaw = [
            { label: 'Diabète',             count: patients.filter(p => /diabet/i.test(String(p.irc_etiologie_principale||''))).length },
            { label: 'HTA / Vasculaire',    count: patients.filter(p => /hypert|hta|vasc|nephroangio/i.test(String(p.irc_etiologie_principale||''))).length },
            { label: 'Glomérulonéphrite',   count: patients.filter(p => /glom/i.test(String(p.irc_etiologie_principale||''))).length },
            { label: 'Polykystose',         count: patients.filter(p => /polykyst|pkr/i.test(String(p.irc_etiologie_principale||''))).length },
            { label: 'Autre / Inconnue',    count: patients.filter(p => !p.irc_etiologie_principale || /indet|autre|inconnu/i.test(String(p.irc_etiologie_principale||''))).length },
          ].filter(e => e.count > 0).sort((a, b) => b.count - a.count);

          // Devenir
          const vivant      = patients.filter(p => /vivant|surviv/i.test(String(p.devenir_statut||''))).length;
          const deced       = patients.filter(p => /dece/i.test(String(p.devenir_statut||''))).length;
          const transpl     = patients.filter(p => /transpl/i.test(String(p.devenir_statut||''))).length;
          const perdu       = patients.filter(p => /perdu|suivi.{0,10}interr/i.test(String(p.devenir_statut||''))).length;
          const nonRenseigne = total - vivant - deced - transpl - perdu;

          // Score de Charlson
          const charlsonGroups = [
            { label: '0 – 2\n(faible)',  count: patients.filter(p => { const v = parseFloat(p.icc_charlson); return !isNaN(v) && v <= 2; }).length },
            { label: '3 – 5\n(modéré)',  count: patients.filter(p => { const v = parseFloat(p.icc_charlson); return !isNaN(v) && v > 2 && v <= 5; }).length },
            { label: '> 5\n(élevé)',     count: patients.filter(p => { const v = parseFloat(p.icc_charlson); return !isNaN(v) && v > 5; }).length },
          ];

          // Durée en dialyse
          const now = new Date();
          const dialDurations = patients.map(p => {
            if (!p.dialyse_date_debut) return null;
            const d = new Date(p.dialyse_date_debut);
            if (isNaN(d)) return null;
            return (now - d) / (1000 * 60 * 60 * 24 * 365.25);
          }).filter(d => d !== null && d >= 0);
          const dialGroups = [
            { label: '< 1 an',    count: dialDurations.filter(d => d < 1).length },
            { label: '1 – 3 ans', count: dialDurations.filter(d => d >= 1 && d < 3).length },
            { label: '3 – 5 ans', count: dialDurations.filter(d => d >= 3 && d < 5).length },
            { label: '> 5 ans',   count: dialDurations.filter(d => d >= 5).length },
          ];

          // ── Chart data ──────────────────────────────────────────────────
          const comorbChartData = {
            labels: comorb.map(c => c.label),
            datasets: [{ label: 'Patients', data: comorb.map(c => Math.round(c.count / total * 100)), backgroundColor: ['rgba(231,76,60,.80)','rgba(230,126,34,.80)','rgba(142,68,173,.75)','rgba(39,174,96,.75)','rgba(61,90,138,.70)'], borderRadius: 8, borderSkipped: false }],
          };
          const comorbOpts = {
            indexAxis: 'y', responsive: true,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.x} % (${comorb[c.dataIndex].count} patients)` }, bodyFont: cf } },
            scales: {
              x: { beginAtZero: true, max: 100, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted, callback: v => `${v} %` } },
              y: { grid: { display: false }, ticks: { font: { ...cf, weight: '700' }, color: PM.navy } },
            },
          };

          const etioChartData = {
            labels: etioRaw.map(e => e.label),
            datasets: [{ label: 'Patients', data: etioRaw.map(e => e.count), backgroundColor: ['rgba(61,90,138,.80)','rgba(230,126,34,.80)','rgba(142,68,173,.75)','rgba(39,174,96,.75)','rgba(180,180,180,.60)'], borderRadius: 8, borderSkipped: false }],
          };
          const etioOpts = {
            indexAxis: 'y', responsive: true,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.x} patients (${Math.round(c.parsed.x / total * 100)} %)` }, bodyFont: cf } },
            scales: {
              x: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted } },
              y: { grid: { display: false }, ticks: { font: { ...cf, weight: '700' }, color: PM.navy } },
            },
          };

          const devenirLabels = []; const devenirData = []; const devenirColors = [];
          [
            { label: 'Vivant',        val: vivant,       color: 'rgba(39,174,96,.80)'  },
            { label: 'Décédé',        val: deced,        color: 'rgba(231,76,60,.80)'  },
            { label: 'Transplanté',   val: transpl,      color: 'rgba(61,90,138,.75)'  },
            { label: 'Perdu de vue',  val: perdu,        color: 'rgba(230,126,34,.75)' },
            { label: 'Non renseigné', val: nonRenseigne, color: 'rgba(180,180,180,.55)'},
          ].filter(d => d.val > 0).forEach(d => { devenirLabels.push(d.label); devenirData.push(d.val); devenirColors.push(d.color); });
          const devenirChartData = {
            labels: devenirLabels,
            datasets: [{ data: devenirData, backgroundColor: devenirColors, borderColor: ['#fff'], borderWidth: 3, hoverOffset: 6 }],
          };
          const devenirCenterPlugin = {
            id: 'devenirCenter',
            afterDraw(chart) {
              const { ctx, chartArea } = chart;
              if (!chartArea) return;
              const cx = (chartArea.left + chartArea.right) / 2;
              const cy = (chartArea.top + chartArea.bottom) / 2;
              ctx.save();
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.font = 'bold 22px Inter, sans-serif';
              ctx.fillStyle = '#1e2d5a';
              ctx.fillText(String(total), cx, cy - 9);
              ctx.font = '11px Inter, sans-serif';
              ctx.fillStyle = '#94a3b8';
              ctx.fillText('patients', cx, cy + 11);
              ctx.restore();
            },
          };
          const devenirOpts = {
            cutout: '62%',
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'bottom',
                labels: {
                  font: { ...cf, size: 12 },
                  color: PM.navy,
                  padding: 16,
                  boxWidth: 14,
                  generateLabels: (chart) => {
                    const ds = chart.data.datasets[0];
                    return chart.data.labels.map((label, i) => ({
                      text: `${label} — ${Math.round(ds.data[i] / total * 100)} %`,
                      fillStyle: ds.backgroundColor[i],
                      strokeStyle: '#fff',
                      lineWidth: 2,
                      index: i,
                    }));
                  },
                },
              },
              tooltip: { callbacks: { label: c => ` ${c.parsed} patients (${Math.round(c.parsed / total * 100)} %)` }, bodyFont: cf },
            },
          };

          const charlsonChartData = {
            labels: charlsonGroups.map(g => g.label),
            datasets: [{ label: 'Patients', data: charlsonGroups.map(g => g.count), backgroundColor: ['rgba(39,174,96,.80)','rgba(230,126,34,.80)','rgba(231,76,60,.80)'], borderRadius: 8, borderSkipped: false }],
          };
          const charlsonOpts = {
            responsive: true,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.y} patients` }, bodyFont: cf } },
            scales: {
              y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted } },
              x: { grid: { display: false }, ticks: { font: { ...cf, weight: '700', size: 10 }, color: PM.navy } },
            },
          };

          const dialChartData = {
            labels: dialGroups.map(g => g.label),
            datasets: [{ label: 'Patients', data: dialGroups.map(g => g.count), backgroundColor: ['rgba(61,90,138,.40)','rgba(61,90,138,.60)','rgba(61,90,138,.80)','rgba(61,90,138,1)'], borderRadius: 8, borderSkipped: false }],
          };
          const dialOpts = {
            responsive: true,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${c.parsed.y} patients` }, bodyFont: cf } },
            scales: {
              y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' }, ticks: { font: cf, color: PM.muted } },
              x: { grid: { display: false }, ticks: { font: { ...cf, weight: '700' }, color: PM.navy } },
            },
          };

          return (
            <>
              <Divider sx={{ my: 0.5 }} />
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 800, color: PM.navy, fontSize: '0.9rem' }}>
                  Analyse de votre cohorte
                </Typography>
                <Chip label="Live" size="small" sx={{ bgcolor: '#27AE6018', color: '#27AE60', fontWeight: 700, fontSize: '0.65rem', height: 20, border: '1px solid #27AE6035' }} />
                <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.72rem' }}>
                  Calculé depuis vos {total} patients
                </Typography>
              </Box>

              {/* Ligne 1 : Comorbidités + Étiologies IRC */}
              <Grid container spacing={2} alignItems="stretch">
                <Grid item xs={12} sm={6}>
                  <ChartCard title="Comorbidités principales" subtitle="Prévalence dans votre base de patients (%)">
                    <Bar data={comorbChartData} options={comorbOpts} height={140} />
                  </ChartCard>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ChartCard title="Étiologies de l'IRC" subtitle="Cause principale de l'insuffisance rénale chronique">
                    <Bar data={etioChartData} options={etioOpts} height={140} />
                  </ChartCard>
                </Grid>
              </Grid>

              {/* Ligne 2 : Devenir + Profil de risque */}
              <Grid container spacing={2} alignItems="stretch">
                <Grid item xs={12} sm={6}>
                  <ChartCard title="Devenir des patients" subtitle="Statut final enregistré dans le dossier">
                    <Box sx={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 240 }}>
                      <Box sx={{ width: 230, height: 230 }}>
                        <Doughnut data={devenirChartData} options={devenirOpts} plugins={[devenirCenterPlugin]} />
                      </Box>
                    </Box>
                  </ChartCard>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ChartCard title="Profil de risque" subtitle="Score de Charlson et ancienneté en dialyse">
                    <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, fontSize: '0.7rem', display: 'block', mb: 0.5 }}>
                      Score de Charlson — charge en comorbidités
                    </Typography>
                    <Bar data={charlsonChartData} options={charlsonOpts} height={80} />
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, fontSize: '0.7rem', display: 'block', mb: 0.5 }}>
                      Durée en dialyse — ancienneté
                    </Typography>
                    <Bar data={dialChartData} options={dialOpts} height={80} />
                  </ChartCard>
                </Grid>
              </Grid>
            </>
          );
        })()}

        {/* ── Guide ─────────────────────────────────────────────────────── */}
        <Card elevation={0} sx={{ borderRadius: '20px', background: 'linear-gradient(135deg,rgba(61,90,138,.07) 0%,rgba(158,61,106,.05) 100%)', border: '1px solid rgba(61,90,138,.12)' }}>
          <CardContent sx={{ p: 3 }}>
            <Box sx={{ mb: 2.5 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 900, color: PM.navy, fontSize: '1rem', letterSpacing: '-.01em' }}>
                Comment utiliser ce module ?
              </Typography>
              <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.75rem' }}>
                4 étapes pour obtenir et explorer un score de risque de mortalité à 1 an
              </Typography>
            </Box>
            <Grid container spacing={2}>
              {[
                { n: '1', t: 'Sélectionner un patient', d: 'Onglet "Patients" → recherchez par nom, prénom ou ID.', color: PM.steel },
                { n: '2', t: 'Lancer la prédiction',    d: 'Cliquez "Lancer la prédiction" — le modèle analyse 32 variables automatiquement.', color: PM.rose },
                { n: '3', t: 'Lire le résultat',         d: 'Onglet "Score" → zone de risque + recommandation clinique + détail des variables.', color: '#27AE60' },
                { n: '4', t: 'Simuler une modification', d: 'Modifiez une valeur clinique puis cliquez "Simuler" pour voir l\'impact sur le risque sans sauvegarder.', color: '#E67E22' },
              ].map((g, i) => (
                <Grid item xs={12} sm={3} key={g.n}>
                  <Box sx={{ p: 2, borderRadius: '16px', background: 'rgba(255,255,255,0.80)', border: `1px solid ${g.color}22`, height: '100%', display: 'flex', flexDirection: 'column', gap: 1.2, boxShadow: `0 4px 16px ${g.color}0e` }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
                      <Box sx={{ width: 36, height: 36, borderRadius: '12px', flexShrink: 0, background: `linear-gradient(135deg,${g.color}dd,${g.color}99)`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: `0 4px 12px ${g.color}30` }}>
                        <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.9rem' }}>{g.n}</Typography>
                      </Box>
                      <Typography variant="body2" sx={{ fontWeight: 800, color: PM.navy, fontSize: '0.88rem', lineHeight: 1.3 }}>{g.t}</Typography>
                    </Box>
                    <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.76rem', lineHeight: 1.6, pl: 0.5 }}>{g.d}</Typography>
                    {i < 2 && (
                      <Box sx={{ display: { xs: 'none', sm: 'none' } }} />
                    )}
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>

      </Stack>
    );
  };

  // ── Patients ─────────────────────────────────────────────────────────────────
  const PatientsTab = () => {
    const showDetail = !!selectedPatient;
    const p = selectedPatient;
    const fv = (v, unit = '') => (v !== null && v !== undefined && v !== '') ? `${v}${unit ? ' ' + unit : ''}` : '—';
    const boolVal = (v) => (v === 1 || v === true || v === '1') ? 'Oui' : (v === 0 || v === false || v === '0') ? 'Non' : '—';

    return (
      <Grid container spacing={2} alignItems="flex-start">

        {/* ── Colonne gauche : recherche + table ── */}
        <Grid item xs={12} md={showDetail ? 5 : 12}>
          <Stack spacing={1.5}>
            <TextField
              fullWidth size="small"
              placeholder="Rechercher par nom, prénom ou ID..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon sx={{ color: PM.muted, fontSize: 20 }} /></InputAdornment> }}
            />
            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                <CircularProgress sx={{ color: PM.steel }} />
              </Box>
            ) : (
              <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: '16px', border: '1px solid rgba(61,90,138,.12)', maxHeight: 460, overflow: 'auto' }}>
                <Table stickyHeader size="small">
                  <TableHead>
                    <TableRow>
                      {['ID', 'Nom', 'Prénom', 'Âge', 'Action'].map(h => (
                        <TableCell key={h} sx={{ textAlign: h === 'Action' ? 'center' : 'left', fontSize: showDetail ? '0.75rem' : undefined }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {filteredPatients.length > 0 ? filteredPatients.map(pt => {
                      const sel = selectedPatient?.id === pt.id;
                      return (
                        <TableRow key={pt.id} hover sx={{ background: sel ? 'rgba(61,90,138,.07) !important' : undefined, cursor: 'pointer' }}
                          onClick={() => setSelectedPatient(pt)}>
                          <TableCell sx={{ color: PM.muted, fontWeight: 600, fontSize: '0.78rem' }}>#{pt.id}</TableCell>
                          <TableCell sx={{ fontWeight: 700, color: PM.navy, fontSize: '0.82rem' }}>{pt.nom || '—'}</TableCell>
                          <TableCell sx={{ fontSize: '0.82rem' }}>{pt.prenom || '—'}</TableCell>
                          <TableCell sx={{ color: PM.muted, fontSize: '0.78rem' }}>{(pt.age || pt.demographie_age_ans) ? `${pt.age || pt.demographie_age_ans} ans` : '—'}</TableCell>
                          <TableCell sx={{ textAlign: 'center' }}>
                            <Button size="small" variant="outlined"
                              onClick={e => { e.stopPropagation(); setSelectedPatient(pt); }}
                              sx={{
                                borderRadius: '20px', fontSize: '0.72rem', px: 1.6, py: 0.35, fontWeight: 700,
                                ...(sel
                                  ? { color: '#27AE60', borderColor: '#27AE6055', background: 'rgba(39,174,96,.08)', '&:hover': { background: 'rgba(39,174,96,.14)', borderColor: '#27AE60' } }
                                  : { color: PM.muted, borderColor: 'rgba(61,90,138,.20)', '&:hover': { color: PM.steel, borderColor: PM.steel, background: 'rgba(61,90,138,.05)' } }
                                ),
                              }}>
                              {sel ? '✓ Ouvert' : 'Voir'}
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    }) : (
                      <TableRow>
                        <TableCell colSpan={5} sx={{ textAlign: 'center', py: 5, color: PM.muted }}>
                          Aucun patient trouvé
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Stack>
        </Grid>

        {/* ── Colonne droite : dossier patient ── */}
        {showDetail && (
          <Grid item xs={12} md={7}>
            <Card sx={{ borderRadius: '20px', border: '1.5px solid rgba(61,90,138,.14)', background: 'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 60%,#f4eef8 100%)', boxShadow: '0 8px 32px rgba(61,90,138,.10)', position: 'sticky', top: 16, maxHeight: 'calc(100vh - 180px)', display: 'flex', flexDirection: 'column' }}>
              <CardContent sx={{ p: 3, overflowY: 'auto', flex: 1, '&::-webkit-scrollbar': { width: 5 }, '&::-webkit-scrollbar-thumb': { borderRadius: 4, background: 'rgba(61,90,138,.20)' } }}>

                {/* En-tête */}
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2.5 }}>
                  <Box>
                    <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em', fontSize: '0.65rem', display: 'block', mb: 0.3 }}>
                      Dossier patient
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 900, color: PM.navy, lineHeight: 1.2 }}>
                      {p.prenom} {p.nom}
                    </Typography>
                    <Typography variant="body2" sx={{ color: PM.muted, fontSize: '0.8rem' }}>ID #{p.id}</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', gap: 1 }}>
                    <Chip label="Sélectionné" size="small" sx={{ bgcolor: 'rgba(61,90,138,.10)', color: PM.steel, fontWeight: 700, fontSize: '0.68rem' }} />
                    <Button size="small" variant="text" onClick={() => setSelectedPatient(null)}
                      sx={{ color: PM.muted, fontSize: '0.72rem', minWidth: 0, px: 1 }}>✕</Button>
                  </Box>
                </Box>

                {/* Identité */}
                <Grid container spacing={1} sx={{ mb: 2 }}>
                  {[
                    { label: 'Âge',           value: fv(p.demographie_age_ans || p.age, 'ans') },
                    { label: 'Sexe',          value: (() => { const s = String(p.demographie_sexe || p.sexe || '').trim(); return /^[mMhH]/i.test(s) || /masculin|homme/i.test(s) ? 'Masculin' : /^[fF]/i.test(s) || /f[eé]minin|femme/i.test(s) ? 'Féminin' : '—'; })() },
                    { label: 'Score Charlson',value: fv(p.icc_charlson) },
                  ].map(item => (
                    <Grid item xs={4} key={item.label}>
                      <Box sx={{ p: 1.2, borderRadius: '10px', background: 'rgba(255,255,255,.9)', border: '1px solid rgba(61,90,138,.12)', textAlign: 'center' }}>
                        <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.62rem', fontWeight: 700, display: 'block' }}>{item.label}</Typography>
                        <Typography sx={{ fontWeight: 800, color: PM.navy, fontSize: '0.9rem' }}>{item.value}</Typography>
                      </Box>
                    </Grid>
                  ))}
                </Grid>

                {/* 32 variables groupées — éditables — scrollable */}
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
                  <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.68rem' }}>
                    Modifiez les valeurs pour simuler un scénario
                  </Typography>
                  {Object.keys(editedValues).length > 0 && (
                    <Button size="small" variant="text" onClick={() => { setEditedValues({}); setSimResult(null); }}
                      sx={{ color: PM.muted, fontSize: '0.65rem', py: 0, minWidth: 0 }}>
                      Réinitialiser ({Object.keys(editedValues).length})
                    </Button>
                  )}
                </Box>
                <Box sx={{ maxHeight: 320, overflowY: 'auto', pr: 0.5,
                  '&::-webkit-scrollbar': { width: 5 },
                  '&::-webkit-scrollbar-track': { borderRadius: 4, background: 'rgba(61,90,138,.05)' },
                  '&::-webkit-scrollbar-thumb': { borderRadius: 4, background: 'rgba(61,90,138,.25)' },
                }}>
                  {Object.entries(
                    Object.entries(FEATURE_LABELS).reduce((acc, [key, meta]) => {
                      const g = meta.group || 'Autre';
                      if (!acc[g]) acc[g] = [];
                      acc[g].push({ key, ...meta });
                      return acc;
                    }, {})
                  ).map(([group, items]) => {
                    const gc = GROUP_COLORS[group] || GROUP_COLORS['Interactions'];
                    return (
                      <Box key={group} sx={{ mb: 1.5 }}>
                        <Typography variant="caption" sx={{
                          color: gc.text, fontWeight: 800, textTransform: 'uppercase',
                          letterSpacing: '.07em', fontSize: '0.62rem', display: 'block', mb: 0.75,
                        }}>
                          {group}
                        </Typography>
                        <Grid container spacing={0.75}>
                          {items.map(({ key, label, binary, unit, group: g2 }) => {
                            const isInteraction = g2 === 'Interactions';
                            const originalRaw = resolveFeature(p, key);
                            const edited = key in editedValues;
                            const raw = edited ? editedValues[key] : originalRaw;
                            const isEmpty = raw === null || raw === undefined || raw === '';
                            const isOui = binary && !isEmpty && (raw === 1 || raw === '1' || raw === true);
                            return (
                              <Grid item xs={6} key={key}>
                                <Box sx={{
                                  px: 1.2, py: 0.7, borderRadius: '10px',
                                  background: edited ? 'rgba(158,61,106,.06)' : isEmpty ? 'rgba(180,180,180,.05)' : gc.bg,
                                  border: `1.5px solid ${edited ? 'rgba(158,61,106,.35)' : isEmpty ? 'rgba(180,180,180,.12)' : gc.border}`,
                                }}>
                                  <Typography sx={{ fontSize: '0.65rem', color: PM.muted, fontWeight: 700, display: 'block', mb: 0.3, lineHeight: 1.2 }}>
                                    {label}{unit ? ` (${unit})` : ''}
                                    {edited && <span style={{ color: PM.rose, marginLeft: 4 }}>✎</span>}
                                  </Typography>
                                  {isInteraction ? (
                                    <Typography sx={{ fontSize: '0.75rem', fontWeight: 800, color: isEmpty ? 'rgba(180,180,180,.5)' : gc.text }}>
                                      {isEmpty ? '—' : String(raw)}
                                    </Typography>
                                  ) : binary ? (
                                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                                      {['Oui', 'Non'].map(opt => {
                                        const active = opt === 'Oui' ? isOui : !isOui && !isEmpty;
                                        const isOuiOpt = opt === 'Oui';
                                        return (
                                          <Button key={opt} size="small" variant={active ? 'contained' : 'outlined'}
                                            onClick={() => { setEditedValues(ev => ({ ...ev, [key]: isOuiOpt ? 1 : 0 })); setSimResult(null); }}
                                            sx={{
                                              fontSize: '0.65rem', py: 0.15, px: 0.8, minWidth: 0, borderRadius: '7px', flex: 1,
                                              ...(active && isOuiOpt ? { background: '#C0392B !important', color: 'white' } : {}),
                                              ...(active && !isOuiOpt ? { background: `${gc.text} !important`, color: 'white' } : {}),
                                              ...(!active ? { color: PM.muted, borderColor: 'rgba(180,180,180,.25)', fontSize: '0.65rem' } : {}),
                                            }}>
                                            {opt}
                                          </Button>
                                        );
                                      })}
                                    </Box>
                                  ) : (
                                    <TextField variant="standard" size="small"
                                      defaultValue={isEmpty ? '' : String(raw)}
                                      placeholder={isEmpty ? '—' : ''}
                                      onBlur={e => {
                                        const v = e.target.value.trim();
                                        if (v === '' || v === String(originalRaw)) {
                                          setEditedValues(ev => { const n = { ...ev }; delete n[key]; return n; });
                                        } else {
                                          setEditedValues(ev => ({ ...ev, [key]: v }));
                                        }
                                        setSimResult(null);
                                      }}
                                      inputProps={{ style: { fontSize: '0.78rem', fontWeight: 800, color: PM.navy, padding: '1px 0' } }}
                                      sx={{ width: '100%', '& .MuiInput-underline:before': { borderColor: 'transparent' }, '& .MuiInput-underline:hover:before': { borderColor: gc.border } }}
                                    />
                                  )}
                                </Box>
                              </Grid>
                            );
                          })}
                        </Grid>
                      </Box>
                    );
                  })}
                </Box>

                <Divider sx={{ my: 1.5, borderColor: 'rgba(61,90,138,.10)' }} />

                {/* Boutons lancer + simuler */}
                <Stack spacing={1}>
                  <Button fullWidth variant="contained" size="large"
                    startIcon={predicting ? <CircularProgress size={18} sx={{ color: 'white' }} /> : <PlayArrowIcon />}
                    onClick={handlePredict} disabled={predicting}
                    sx={{
                      background: `linear-gradient(135deg,${PM.rose},#7a2d52) !important`,
                      boxShadow: `0 8px 18px rgba(158,61,106,.25) !important`,
                      borderRadius: '12px', py: 1.2, fontSize: '0.88rem', fontWeight: 800,
                      '&:hover': { background: `linear-gradient(135deg,#b04878,#6a2548) !important` },
                      '&:disabled': { opacity: 0.65 },
                    }}>
                    {predicting ? 'Analyse en cours...' : 'Lancer la prédiction'}
                  </Button>
                  <Button fullWidth variant="outlined" size="large"
                    startIcon={simulating ? <CircularProgress size={16} sx={{ color: PM.steel }} /> : <span>⚗</span>}
                    onClick={handleSimulate} disabled={simulating}
                    sx={{
                      borderRadius: '12px', py: 1.1, fontSize: '0.88rem', fontWeight: 700,
                      color: PM.steel, borderColor: 'rgba(61,90,138,.35)',
                      '&:hover': { background: 'rgba(61,90,138,.05)', borderColor: PM.steel },
                      '&:disabled': { opacity: 0.65 },
                    }}>
                    {simulating ? 'Simulation...' : 'Simuler'}
                  </Button>
                </Stack>

                {/* Résultat simulation inline */}
                {simResult && (() => {
                  if (simResult.error) return (
                    <Alert severity="error" sx={{ mt: 1.5, fontSize: '0.8rem' }}>{simResult.error}</Alert>
                  );
                  const niveau = simResult.niveau_risque || 'Inconnu';
                  const zColor = niveau === 'Élevé' ? '#E74C3C' : niveau === 'Modéré' ? '#E67E22' : '#27AE60';
                  const nbEdited = Object.keys(editedValues).length;
                  return (
                    <Box sx={{ mt: 1.5, p: 2, borderRadius: '14px', border: `1.5px solid ${zColor}35`, background: `linear-gradient(135deg,${zColor}08,rgba(255,255,255,.9))` }}>
                      <Typography variant="caption" sx={{ color: zColor, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.07em', fontSize: '0.62rem', display: 'block', mb: 0.5 }}>
                        ⚗ Résultat simulation
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Box>
                          <Typography sx={{ fontWeight: 900, color: zColor, fontSize: '1.05rem' }}>Zone {niveau}</Typography>
                          <Typography sx={{ fontSize: '0.78rem', color: PM.muted }}>
                            Probabilité : {simResult.score_risque} %
                          </Typography>
                        </Box>
                        <Chip label={`${nbEdited} var. modifiée${nbEdited > 1 ? 's' : ''}`} size="small"
                          sx={{ bgcolor: 'rgba(158,61,106,.10)', color: PM.rose, fontWeight: 700, fontSize: '0.65rem', border: `1px solid rgba(158,61,106,.20)` }} />
                      </Box>
                      <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.65rem', mt: 0.5, display: 'block', fontStyle: 'italic' }}>
                        ⚠ Simulation uniquement — données non sauvegardées
                      </Typography>
                    </Box>
                  );
                })()}
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    );
  };

  // ── Score ─────────────────────────────────────────────────────────────────────
  const ScoreTab = () => {
    const [showVars, setShowVars] = React.useState(false);

    if (!selectedPatient) return <Alert severity="info">Sélectionnez d'abord un patient dans l'onglet "Patients"</Alert>;
    if (predicting) return (
      <Box sx={{ textAlign: 'center', py: 6 }}>
        <CircularProgress sx={{ color: PM.steel }} />
        <Typography sx={{ mt: 2, color: PM.muted }}>Analyse des 32 variables cliniques...</Typography>
      </Box>
    );
    if (!predictionResult) return <Alert severity="warning">Cliquez sur "Lancer la prédiction" pour analyser ce patient</Alert>;
    if (predictionResult.error) return <Alert severity="error">{predictionResult.error}</Alert>;

    const niveau  = predictionResult.niveau_risque || 'Inconnu';
    const risk    = RISK[niveau] || { color: '#999', bg: '#f5f5f5', grad: '#999,#777' };
    const missing = predictionResult.features_missing || 0;
    const dqColor = missing > 16 ? '#E74C3C' : missing > 8 ? '#E67E22' : '#27AE60';
    const dqLabel = missing > 16 ? 'Insuffisante' : missing > 8 ? 'Partielle' : 'Complète';
    const _ty = (predictionResult.seuil_youden || 0.194) * 100;
    const _ts = (predictionResult.seuil_spec90 || 0.357) * 100;
    const spectrumGradient = `linear-gradient(90deg,#27AE60 0%,#27AE60 ${_ty}%,#f39c12 ${_ty + 2}%,#E67E22 ${_ts}%,#e74c3c ${_ts + 2}%,#c0392b 100%)`;

    const formatValue = (fv) => {
      if (fv.missing || fv.value === null || fv.value === undefined) return null;
      const meta = FEATURE_LABELS[fv.key] || {};
      if (meta.binary) return fv.value === 1 || fv.value === 1.0 ? 'Oui' : 'Non';
      const num = typeof fv.value === 'number' ? (Number.isInteger(fv.value) ? fv.value : parseFloat(fv.value.toFixed(2))) : fv.value;
      return meta.unit ? `${num} ${meta.unit}` : String(num);
    };

    const ZONE_DETAILS = {
      Faible: {
        symbol: '○',
        action: 'Suivi standard recommandé',
        detail: 'Le modèle ne signale pas ce patient comme prioritaire. Continuez le suivi habituel.',
        observed: '5,1 %',
        gradient: 'linear-gradient(135deg, #1a8a4a 0%, #27AE60 50%, #52c27a 100%)',
        glow: 'rgba(39,174,96,.35)',
      },
      Modéré: {
        symbol: '◐',
        action: 'Surveillance renforcée',
        detail: 'Le modèle signale ce patient. Renforcer la surveillance et réévaluer les facteurs de risque.',
        observed: '29,1 %',
        gradient: 'linear-gradient(135deg, #b8560a 0%, #E67E22 50%, #f0a050 100%)',
        glow: 'rgba(230,126,34,.35)',
      },
      Élevé: {
        symbol: '●',
        action: 'Prise en charge prioritaire',
        detail: 'Ce patient est dans le groupe à haut risque. Une prise en charge active et urgente est recommandée.',
        observed: '55,6 %',
        gradient: 'linear-gradient(135deg, #a01f1f 0%, #E74C3C 50%, #f07070 100%)',
        glow: 'rgba(231,76,60,.35)',
      },
    };
    const zd = ZONE_DETAILS[niveau] || ZONE_DETAILS['Modéré'];
    const zones = ['Faible', 'Modéré', 'Élevé'];
    const activeIdx = zones.indexOf(niveau);

    return (
      <Stack spacing={2}>
        {missing > 8 && (
          <Alert severity={missing > 16 ? 'error' : 'warning'} icon={<WarningAmberIcon />}>
            <strong>{missing}/32 variables manquantes</strong> — imputation KNN appliquée.
            {missing > 16 && ' Ce score est à interpréter avec précaution.'}
          </Alert>
        )}

        {/* ── CARTE PRINCIPALE — design clinique ───────────────────────── */}
        <Card sx={{ overflow: 'hidden', border: 'none !important', borderRadius: '22px !important', boxShadow: `0 24px 56px ${zd.glow}, 0 6px 20px rgba(0,0,0,.10) !important` }}>

          {/* ── HEADER LIGHT CLINIQUE ─────────────────────────────────── */}
          <Box sx={{ background: 'linear-gradient(145deg,#ffffff 0%,#f7f9fc 60%,#eef1f7 100%)', p: { xs: 2.5, md: 3 }, position: 'relative', overflow: 'hidden', borderBottom: '1.5px solid rgba(0,0,0,.07)' }}>

            {/* Glow blob décoratif */}
            <Box sx={{ position: 'absolute', top: -80, right: -80, width: 280, height: 280, borderRadius: '50%', background: `radial-gradient(circle,${risk.color}12 0%,transparent 70%)`, pointerEvents: 'none' }} />
            <Box sx={{ position: 'absolute', bottom: -60, left: '40%', width: 200, height: 200, borderRadius: '50%', background: 'radial-gradient(circle,rgba(212,122,142,.08) 0%,transparent 70%)', pointerEvents: 'none' }} />

            {/* Top bar : patient + modèle */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5, position: 'relative', zIndex: 1 }}>
              <Chip label={`${selectedPatient.prenom || ''} ${selectedPatient.nom || ''}`.trim() + `  ·  ${selectedPatient.id_patient || `ID #${selectedPatient.id}`}`} size="small"
                sx={{ bgcolor: 'rgba(0,0,0,.05)', color: '#2d3436', fontWeight: 700, fontSize: '0.75rem', border: '1px solid rgba(0,0,0,.09)' }} />
            </Box>

            {/* Jauge SVG + zone info */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 2, md: 3.5 }, position: 'relative', zIndex: 1 }}>

              {/* Jauge circulaire SVG */}
              <Box sx={{ position: 'relative', width: 130, height: 130, flexShrink: 0 }}>
                <svg viewBox="0 0 120 120" style={{ width: '100%', height: '100%' }}>
                  <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(0,0,0,.08)" strokeWidth="11" />
                  <circle cx="60" cy="60" r="50" fill="none"
                    stroke={risk.color} strokeWidth="11" strokeLinecap="round"
                    strokeDasharray={`${Math.min(predictionResult.probabilite_deces, .999) * 2 * Math.PI * 50} ${2 * Math.PI * 50}`}
                    transform="rotate(-90 60 60)"
                    style={{ filter: `drop-shadow(0 0 6px ${risk.color}80)` }}
                  />
                  <circle cx="60" cy="60" r="36" fill="rgba(0,0,0,.02)" />
                </svg>
                <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <Typography sx={{ fontWeight: 900, fontSize: '1.75rem', color: '#1e2d5a', lineHeight: 1 }}>{predictionResult.score_risque}</Typography>
                  <Typography sx={{ fontSize: '0.9rem', color: risk.color, fontWeight: 800, lineHeight: 1 }}>%</Typography>
                  <Typography sx={{ fontSize: '0.55rem', color: 'rgba(0,0,0,.35)', mt: 0.3, textTransform: 'uppercase', letterSpacing: '.05em' }}>probabilité</Typography>
                </Box>
              </Box>

              {/* Info zone + métriques */}
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, mb: 0.4 }}>
                  <Typography sx={{ fontWeight: 900, fontSize: { xs: '2rem', md: '2.5rem' }, color: risk.color, lineHeight: 1, letterSpacing: '-.02em' }}>
                    {niveau}
                  </Typography>
                  <Box sx={{ width: 9, height: 9, borderRadius: '50%', background: risk.color, boxShadow: `0 0 10px ${risk.color}, 0 0 20px ${risk.color}60`, mt: 0.5 }} />
                </Box>
                <Typography sx={{ color: 'rgba(0,0,0,.45)', fontSize: '0.75rem', mb: 1.8, letterSpacing: '.01em' }}>
                  Mortalité observée {zd.observed} · Zone de risque à 1 an
                </Typography>
                <Box sx={{ display: 'flex', gap: 1.5 }}>
                  {[
                    { label: 'Risque rel.', value: `${predictionResult.risque_relatif || '—'}×`, color: risk.color },
                  ].map(m => (
                    <Box key={m.label} sx={{ px: 1.2, py: 0.9, borderRadius: '10px', background: 'rgba(0,0,0,.04)', border: '1px solid rgba(0,0,0,.08)', textAlign: 'center', minWidth: 68 }}>
                      <Typography sx={{ color: 'rgba(0,0,0,.38)', fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '.06em', display: 'block' }}>{m.label}</Typography>
                      <Typography sx={{ color: m.color, fontWeight: 800, fontSize: '0.95rem', mt: 0.2 }}>{m.value}</Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            </Box>

            {/* ── Spectre de risque ───────────────────────────────────── */}
            <Box sx={{ mt: 3, position: 'relative', zIndex: 1 }}>
              <Typography sx={{ color: 'rgba(0,0,0,.35)', fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '.09em', mb: 1 }}>
                Position sur le spectre de risque — cohorte HD-478
              </Typography>
              <Box sx={{ position: 'relative', height: 10, borderRadius: '10px', background: spectrumGradient, boxShadow: 'inset 0 1px 4px rgba(0,0,0,.15)' }}>
                {/* Marqueur seuil Youden */}
                {predictionResult.seuil_youden != null && (
                  <Box sx={{ position: 'absolute', left: `${predictionResult.seuil_youden * 100}%`, top: '50%', transform: 'translate(-50%,-50%)', zIndex: 2 }}>
                    <Box sx={{ width: 2, height: 18, background: 'rgba(255,255,255,.70)', borderRadius: 1 }} />
                  </Box>
                )}
                {/* Marqueur patient */}
                <Box sx={{ position: 'absolute', left: `${Math.min(predictionResult.probabilite_deces * 100, 97)}%`, top: '50%', transform: 'translate(-50%,-50%)', zIndex: 3,
                  width: 18, height: 18, borderRadius: '50%', background: 'white',
                  border: `3px solid ${risk.color}`, boxShadow: `0 0 0 3px ${risk.color}45, 0 2px 8px rgba(0,0,0,.25)`,
                }} />
              </Box>
              <Box sx={{ position: 'relative', height: 18, mt: 0.8 }}>
                {[
                  { z: 'Faible',  pos: _ty / 2,                       anchor: 'left'   },
                  { z: 'Modéré', pos: (_ty + _ts) / 2,               anchor: 'center' },
                  { z: 'Élevé',  pos: _ts + (100 - _ts) / 2,         anchor: 'right'  },
                ].map(({ z, pos, anchor }) => (
                  <Typography key={z} sx={{
                    position: 'absolute',
                    left: `${Math.min(Math.max(pos, 0), 100)}%`,
                    transform: anchor === 'center' ? 'translateX(-50%)' : anchor === 'right' ? 'translateX(-100%)' : 'none',
                    color: z === niveau ? RISK[z].color : 'rgba(0,0,0,.28)',
                    fontSize: '0.68rem',
                    fontWeight: z === niveau ? 800 : 500,
                    whiteSpace: 'nowrap',
                  }}>{z}</Typography>
                ))}
              </Box>
            </Box>
          </Box>

          {/* ── CORPS BLANC ─────────────────────────────────────────────── */}
          <CardContent sx={{ p: { xs: 2.5, md: 3.5 } }}>
            <Box sx={{ p: 2.5, borderRadius: '18px', background: `linear-gradient(135deg,${risk.bg},rgba(255,255,255,.9))`, border: `1.5px solid ${risk.color}28` }}>
              <Typography variant="caption" sx={{ color: risk.color, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.08em', fontSize: '0.68rem', display: 'block', mb: 1 }}>
                Recommandation clinique
              </Typography>
              <Typography variant="h6" sx={{ color: PM.navy, fontWeight: 900, mb: 0.8, fontSize: '1.05rem' }}>{zd.action}</Typography>
              <Typography variant="body2" sx={{ color: PM.muted, lineHeight: 1.7, fontSize: '0.85rem' }}>{zd.detail}</Typography>
            </Box>

            {/* ── Facteurs déterminants ────────────────────────────────── */}
            {predictionResult.factors && predictionResult.factors.length > 0 && (() => {
              const factors = predictionResult.factors.slice(0, 5);
              const maxW = Math.max(...factors.map(f => Math.abs(f.weight)));
              return (
                <Box sx={{ mt: 3 }}>
                  <Typography variant="caption" sx={{ color: risk.color, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.08em', fontSize: '0.68rem', display: 'block', mb: 1.5 }}>
                    Facteurs déterminants
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.1 }}>
                    {factors.map((f, i) => {
                      const isRisk = f.weight >= 0;
                      const barColor = isRisk ? '#e74c3c' : '#27AE60';
                      const barWidth = maxW > 0 ? Math.round((Math.abs(f.weight) / maxW) * 100) : 0;
                      const label = FEATURE_LABELS[f.label]?.label || f.label.replace(/_/g, ' ');
                      const unit  = FEATURE_LABELS[f.label]?.unit  || '';
                      return (
                        <Box key={f.label} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                          {/* Rang */}
                          <Typography sx={{ fontWeight: 800, color: PM.muted, fontSize: '0.7rem', width: 16, flexShrink: 0, textAlign: 'right' }}>
                            {i + 1}
                          </Typography>
                          {/* Label */}
                          <Box sx={{ width: 170, flexShrink: 0 }}>
                            <Typography sx={{ fontWeight: 700, color: PM.navy, fontSize: '0.78rem', lineHeight: 1.2 }}>{label}</Typography>
                            {unit && <Typography sx={{ color: PM.muted, fontSize: '0.62rem' }}>{unit}</Typography>}
                          </Box>
                          {/* Barre */}
                          <Box sx={{ flex: 1, position: 'relative', height: 8, borderRadius: 4, background: 'rgba(0,0,0,.06)' }}>
                            <Box sx={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${barWidth}%`, borderRadius: 4, background: barColor, transition: 'width .4s ease' }} />
                          </Box>
                          {/* Badge +/- */}
                          <Chip
                            label={isRisk ? '↑ Risque' : '↓ Protecteur'}
                            size="small"
                            sx={{ fontSize: '0.58rem', fontWeight: 700, height: 18, bgcolor: isRisk ? '#fdecea' : '#eafaf1', color: barColor, border: `1px solid ${barColor}30`, flexShrink: 0 }}
                          />
                        </Box>
                      );
                    })}
                  </Box>
                </Box>
              );
            })()}
          </CardContent>
        </Card>

        {/* ── INFOS SECONDAIRES + BOUTON VARIABLES ─────────────────────── */}
        <Grid container spacing={2}>
          {/* Qualité données */}
          <Grid item xs={6}>
            <Box sx={{
              p: 2.2, borderRadius: '16px', textAlign: 'center', height: '100%',
              border: `1.5px solid ${dqColor}25`,
              background: `linear-gradient(135deg, ${dqColor}08, rgba(255,255,255,.95))`,
              boxShadow: `0 4px 16px ${dqColor}12`,
            }}>
              <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', fontSize: '0.65rem', display: 'block', mb: 0.5 }}>
                Qualité des données
              </Typography>
              <Typography sx={{ fontWeight: 900, color: dqColor, fontSize: '1.1rem', lineHeight: 1.2 }}>{dqLabel}</Typography>
              <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.68rem' }}>{32 - missing} / 32 variables</Typography>
            </Box>
          </Grid>

          {/* Variables utilisées — avec bouton Afficher intégré */}
          <Grid item xs={6}>
            <Box sx={{
              p: 2.2, borderRadius: '16px', textAlign: 'center', height: '100%',
              border: `1.5px solid ${PM.steel}25`,
              background: `linear-gradient(135deg, rgba(61,90,138,.06), rgba(255,255,255,.95))`,
              boxShadow: `0 4px 16px rgba(61,90,138,.08)`,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-between', gap: 1,
            }}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="caption" sx={{ color: PM.muted, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', fontSize: '0.65rem', display: 'block', mb: 0.5 }}>
                  Variables utilisées
                </Typography>
                <Typography sx={{ fontWeight: 900, color: PM.steel, fontSize: '1.1rem', lineHeight: 1.2 }}>{32 - missing} / 32</Typography>
                <Typography variant="caption" sx={{ color: PM.muted, fontSize: '0.68rem' }}>
                  {missing > 0 ? `${missing} imputée${missing > 1 ? 's' : ''} (KNN)` : 'Données complètes'}
                </Typography>
              </Box>
              {predictionResult.feature_values && (
                <Button
                  size="small"
                  variant={showVars ? 'contained' : 'outlined'}
                  onClick={() => setShowVars(!showVars)}
                  sx={{
                    fontSize: '0.72rem', borderRadius: '10px', px: 2, py: 0.6, mt: 0.5,
                    ...(showVars
                      ? { background: `linear-gradient(135deg,${PM.steel},${PM.navy})`, color: 'white' }
                      : { color: PM.steel, borderColor: 'rgba(61,90,138,.30)' }
                    ),
                  }}
                >
                  {showVars ? 'Masquer ▲' : 'Afficher ▼'}
                </Button>
              )}
            </Box>
          </Grid>
        </Grid>

        {/* ── LISTE DES VARIABLES (dépliable) ─────────────────────────── */}
        {showVars && predictionResult.feature_values && (
          <Card sx={{ border: '1px solid rgba(61,90,138,.10) !important' }}>
            <CardContent sx={{ p: 2.5 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: PM.navy, mb: 1.5, fontSize: '0.88rem' }}>
                Détail des 32 variables
              </Typography>
              <Grid container spacing={1}>
                {predictionResult.feature_values.map((fv) => {
                  const meta = FEATURE_LABELS[fv.key] || { label: fv.key };
                  const isInteraction = fv.key.includes('_x_') || fv.key.includes('_lt');
                  const displayVal = formatValue(fv);
                  const isBinary = meta.binary;
                  const valColor = fv.missing
                    ? '#E67E22'
                    : isBinary
                      ? (displayVal === 'Oui' ? '#27AE60' : PM.muted)
                      : PM.navy;

                  return (
                    <Grid item xs={12} sm={6} key={fv.key}>
                      <Box sx={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        px: 1.5, py: 1, borderRadius: '10px',
                        background: fv.missing ? 'rgba(243,156,18,.06)' : isInteraction ? 'rgba(61,90,138,.04)' : 'rgba(255,255,255,.9)',
                        border: `1px solid ${fv.missing ? 'rgba(243,156,18,.20)' : 'rgba(61,90,138,.08)'}`,
                      }}>
                        <Typography sx={{ fontSize: '0.75rem', color: PM.muted, fontWeight: 600, flex: 1, pr: 1, lineHeight: 1.3 }}>
                          {meta.label}
                        </Typography>
                        <Typography sx={{ fontSize: '0.82rem', fontWeight: 800, color: valColor, flexShrink: 0, textAlign: 'right' }}>
                          {fv.missing ? '—' : displayVal}
                        </Typography>
                      </Box>
                    </Grid>
                  );
                })}
              </Grid>
            </CardContent>
          </Card>
        )}

        <Alert severity="info" sx={{ fontSize: '0.8rem' }}>
          Zones issues de la courbe ROC du modèle SVM — à interpréter en complément du jugement clinique.
        </Alert>

        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={handleReset}
            sx={{ color: PM.steel, borderColor: 'rgba(61,90,138,.30)', borderRadius: '14px', px: 3 }}>
            Analyser un autre patient
          </Button>
        </Box>
      </Stack>
    );
  };

  // ── Rendu principal ───────────────────────────────────────────────────────────
  return (
    <Box sx={shellSx}>
      <AppSidebar />

      {/* Même offset que les autres pages */}
      <Box sx={{ minWidth: 0, '@media (min-width:768px)': { ml: '252px' }, px: { xs: 1.5, md: 2 }, py: { xs: 1.5, md: 2 } }}>

        {/* ── Hero card — identique PatientsManagement ── */}
        <Card elevation={0} sx={{ ...heroCardSx, mb: 2.5 }}>
          <CardContent sx={{ p: 3, position: 'relative', zIndex: 1 }}>
            {/* Image décorative */}
            <Box
              component="img"
              src="/images/chatgpt-image-2026-04-23.png"
              alt=""
              sx={{
                position: 'absolute', left: 10, top: 8,
                width: 140, maxWidth: '30%', opacity: 0.13,
                transform: 'translateZ(0)', zIndex: 0, pointerEvents: 'none',
                filter: 'drop-shadow(0 8px 20px rgba(158,61,106,.10)) saturate(1.05)',
              }}
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={2}>
              <Box>
                <Typography variant="h5" sx={{ fontWeight: 900, color: PM.navy, letterSpacing: '-.02em' }}>
                  Modèle AI — Prédiction de Mortalité
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* ── Tabs card ── */}
        <Card elevation={0}>
          <Tabs
            value={activeTab}
            onChange={(_, v) => setActiveTab(v)}
            sx={{
              px: 2, borderBottom: '1px solid rgba(61,90,138,.10)',
              '& .MuiTab-root': { fontWeight: 700, textTransform: 'none', fontSize: '0.88rem', minHeight: 52, color: PM.muted },
              '& .Mui-selected': { color: `${PM.rose} !important`, fontWeight: 800 },
              '& .MuiTabs-indicator': { background: `linear-gradient(90deg,${PM.rose},${PM.steel})`, height: 3, borderRadius: 2 },
            }}
          >
            <Tab label="Tableau de bord" />
            <Tab label="Patients" />
            <Tab
              label={
                predictionResult && !predictionResult.error ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    Score
                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: RISK[predictionResult.niveau_risque]?.color || PM.rose, boxShadow: `0 0 6px ${RISK[predictionResult.niveau_risque]?.color || PM.rose}` }} />
                  </Box>
                ) : 'Score'
              }
            />
          </Tabs>

          <CardContent sx={{ p: { xs: 2, md: 3 } }}>
            <TabPanel value={activeTab} index={0}><DashboardTab /></TabPanel>
            <TabPanel value={activeTab} index={1}><PatientsTab /></TabPanel>
            <TabPanel value={activeTab} index={2}><ScoreTab /></TabPanel>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
