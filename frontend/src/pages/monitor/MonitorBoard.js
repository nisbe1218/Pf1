import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  InputAdornment,
  IconButton,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Tooltip,
  TextField,
  Typography,
} from '@mui/material';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import AutoGraphOutlinedIcon from '@mui/icons-material/AutoGraphOutlined';
import HistoryToggleOffOutlinedIcon from '@mui/icons-material/HistoryToggleOffOutlined';
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined';
import TimelineOutlinedIcon from '@mui/icons-material/TimelineOutlined';
import AppSidebar from '../../components/common/AppSidebar';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';

const roleLabels = {
  super_admin: 'Super Administrateur',
  chef_service: 'Chef de Service',
  professeur: 'Professeur',
  resident: 'Résident',
};

const boardTheme = {
  deepNavy: '#0A2B3E',
  medicalBlue: '#1A6B8A',
  softRose: '#D47A8E',
  offWhite: '#F5F9FC',
  border: '#E2ECF0',
  textMuted: '#6B8A9C',
};

const formatDateTime = (value, language) => {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  const locale = language === 'en' ? 'en-US' : 'fr-FR';
  return parsed.toLocaleString(locale);
};

const BOOLEAN_TRUE_VALUES = ['1', 'true', 'yes', 'oui', 'y'];
const BOOLEAN_FALSE_VALUES = ['0', 'false', 'no', 'non', 'n'];

const toBooleanDisplay = (rawValue) => {
  if (rawValue === null || rawValue === undefined || rawValue === '') return rawValue;
  const normalized = String(rawValue).trim().toLowerCase();
  if (BOOLEAN_TRUE_VALUES.includes(normalized)) return 'Oui';
  if (BOOLEAN_FALSE_VALUES.includes(normalized)) return 'Non';
  return rawValue;
};

const normalize = (value) => String(value || '').trim().toLowerCase();

const formatAuditFieldLabel = (field) => {
  if (!field) return null;
  const cleaned = String(field)
    .replace(/^(MODIFICATION_PATIENT|CREATION_PATIENT|SUPPRESSION_PATIENT|LATEST_UPDATE|UPDATE)\s*:\s*/i, '')
    .trim();
  if (!cleaned) return null;

  return cleaned
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(.)/, (match) => match.toUpperCase());
};

const tryParseStructuredValue = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'object') return value;
  if (typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
  try {
    return JSON.parse(trimmed);
  } catch (error) {
    return null;
  }
};

const flattenStructuredChanges = (oldValue, newValue, fieldPrefix = null) => {
  const oldStructured = tryParseStructuredValue(oldValue);
  const newStructured = tryParseStructuredValue(newValue);

  if (!oldStructured && !newStructured) {
    return [{ field: fieldPrefix, old: oldValue, new: newValue }];
  }

  const oldIsObject = oldStructured && typeof oldStructured === 'object' && !Array.isArray(oldStructured);
  const newIsObject = newStructured && typeof newStructured === 'object' && !Array.isArray(newStructured);

  if (oldIsObject || newIsObject) {
    const keys = new Set([
      ...Object.keys(oldIsObject ? oldStructured : {}),
      ...Object.keys(newIsObject ? newStructured : {}),
    ]);

    const nested = [];
    keys.forEach((key) => {
      const nextField = fieldPrefix ? `${fieldPrefix}.${key}` : key;
      nested.push(...flattenStructuredChanges(oldIsObject ? oldStructured[key] : undefined, newIsObject ? newStructured[key] : undefined, nextField));
    });

    return nested.length ? nested : [{ field: fieldPrefix, old: oldValue, new: newValue }];
  }

  return [{ field: fieldPrefix, old: oldValue, new: newValue }];
};

const getAuditTone = (label) => {
  const normalized = String(label || '').toUpperCase();
  if (normalized.includes('PRED')) {
    return {
      border: '#2C8C9E',
      bg: 'linear-gradient(180deg, rgba(26,107,138,0.08) 0%, rgba(255,255,255,0.98) 100%)',
      chipBg: 'rgba(26,107,138,0.12)',
      chipColor: '#1A6B8A',
      dot: '#1A6B8A',
    };
  }

  if (normalized.includes('MODIFICATION')) {
    return {
      border: '#D47A8E',
      bg: 'linear-gradient(180deg, rgba(212,122,142,0.08) 0%, rgba(255,255,255,0.98) 100%)',
      chipBg: 'rgba(212,122,142,0.12)',
      chipColor: '#B85C72',
      dot: '#D47A8E',
    };
  }

  if (normalized.includes('CREATION')) {
    return {
      border: '#7E9A8E',
      bg: 'linear-gradient(180deg, rgba(126,154,142,0.08) 0%, rgba(255,255,255,0.98) 100%)',
      chipBg: 'rgba(126,154,142,0.12)',
      chipColor: '#4A8B7C',
      dot: '#4A8B7C',
    };
  }

  return {
    border: boardTheme.border,
    bg: 'linear-gradient(180deg, rgba(245,249,252,0.98) 0%, rgba(255,255,255,1) 100%)',
    chipBg: 'rgba(61,90,138,0.10)',
    chipColor: boardTheme.deepNavy,
    dot: boardTheme.softRose,
  };
};

const extractOldNewFromDetail = (detail) => {
  if (!detail) return { raw: '' };
  // Try JSON parse first
  try {
    const parsed = typeof detail === 'string' ? JSON.parse(detail) : detail;
    if (parsed && typeof parsed === 'object') {
      // If object with explicit changes array
      if (Array.isArray(parsed.changes) && parsed.changes.length) {
        const changes = parsed.changes.map((c) => ({ field: c.field || c.key || null, old: c.old ?? c.previous, new: c.new ?? c.current }));
        return { changes, raw: detail };
      }

      // simple single-field shapes
      if (parsed.field && (parsed.old !== undefined || parsed.new !== undefined)) {
        return { changes: [{ field: parsed.field, old: parsed.old, new: parsed.new }], raw: detail };
      }

      // common flat shapes
      if (parsed.old !== undefined || parsed.new !== undefined) {
        return { changes: [{ field: null, old: parsed.old, new: parsed.new }], raw: detail };
      }
      if (parsed.previous !== undefined || parsed.current !== undefined) {
        return { changes: [{ field: null, old: parsed.previous, new: parsed.current }], raw: detail };
      }
      if (parsed.old_value !== undefined || parsed.new_value !== undefined) {
        return { changes: [{ field: null, old: parsed.old_value, new: parsed.new_value }], raw: detail };
      }
    }
  } catch (e) {
    // ignore JSON parse errors
  }

  const text = String(detail || '');
  const changes = [];

  // Match entries like "field: old -> new" possibly multiple lines
    const lineParts = text
      .split('\n')
      .map((line) => line.split(';'))
      .flat()
      .map((line) => line.trim())
      .filter(Boolean);

    lineParts.forEach((line) => {
      const withoutSummaryPrefix = line.replace(/^(MODIFICATION_PATIENT|CREATION_PATIENT|SUPPRESSION_PATIENT|LATEST_UPDATE|UPDATE)\s*:\s*/i, '').trim();
      if (!withoutSummaryPrefix) {
        return;
      }

      const arrowIndex = withoutSummaryPrefix.indexOf('->');
      if (arrowIndex !== -1) {
        const left = withoutSummaryPrefix.slice(0, arrowIndex).trim();
        const right = withoutSummaryPrefix.slice(arrowIndex + 2).trim();
        if (right) {
          const colonIndex = left.lastIndexOf(':');
          const field = colonIndex !== -1 ? left.slice(0, colonIndex).trim() : null;
          const old = colonIndex !== -1 ? left.slice(colonIndex + 1).trim() : left;
          if (field && /^(MODIFICATION_PATIENT|CREATION_PATIENT|SUPPRESSION_PATIENT|LATEST_UPDATE|UPDATE)$/i.test(field)) {
            return;
          }
          flattenStructuredChanges(old, right, field)
            .forEach((item) => changes.push(item));
          return;
        }
      }

      const fromToRegex = /(?:from|de)\s+([^\-\n\r]+?)\s+(?:to|à)\s+([^\n\r]+)/i;
      const m2 = withoutSummaryPrefix.match(fromToRegex);
      if (m2) {
        changes.push({ field: null, old: m2[1].trim(), new: m2[2].trim() });
      }
    });

  if (changes.length) return { changes, raw: detail };

  // fallback: try to find single "old -> new" in the entire text
  const anyArrow = text.match(/(.*?)\s*->\s*(.*)/);
  if (anyArrow) return { changes: [{ field: null, old: anyArrow[1].trim(), new: anyArrow[2].trim() }], raw: detail };

  return { raw: detail };
};

function MonitorBoard() {
  const { user } = useContext(AuthContext);
  const { language, t } = useLanguage();
  const [patients, setPatients] = useState([]);
  const [initialPatients, setInitialPatients] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [patientAuditEvents, setPatientAuditEvents] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [patientDetails, setPatientDetails] = useState(null);
  const [selectedAuditEvent, setSelectedAuditEvent] = useState(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastPrediction, setLastPrediction] = useState(null);
  const [patientPrediction, setPatientPrediction] = useState(null);
  const [loadingPrediction, setLoadingPrediction] = useState(false);

  const roleLabel = roleLabels[user?.role] || (language === 'en' ? 'User' : 'Utilisateur');

  useEffect(() => {
    const loadBoardData = async () => {
      setLoading(true);
      setError('');
      try {
        const [patientsResponse, predictionsResponse, lastPredResp] = await Promise.all([
          api.get('patients/'),
          api.get('predictions/history/?days=365'),
          api.get('predictions/latest-mortalite/').catch(() => null),
        ]);

        const extractArray = (resp) => {
          if (!resp) return [];
          if (Array.isArray(resp.data)) return resp.data;
          if (resp.data && Array.isArray(resp.data.results)) return resp.data.results;
          return [];
        };

        const fetched = extractArray(patientsResponse);
        setInitialPatients(fetched);
        setPatients(fetched.slice(0, 12));
        setPredictions(Array.isArray(predictionsResponse.data) ? predictionsResponse.data : []);
        if (lastPredResp?.data?.success) setLastPrediction(lastPredResp.data);
      } catch (requestError) {
        setError(language === 'en' ? 'Unable to load the Patient Monitoring Board.' : 'Impossible de charger le Patient Monitoring Board.');
      } finally {
        setLoading(false);
      }
    };

    loadBoardData();
  }, [language]);

  // Debounced server-side search for short numeric queries + client-side fallback
  const fetchPatientsByQuery = async (query) => {
    setLoading(true);
    setError('');
    try {
      const isNumeric = /^\d+$/.test(query);
      // Prefer id_patient param for short numeric queries to rely on DB indexes
      const endpoint = isNumeric && query.length <= 6
        ? `patients/?id_patient=${encodeURIComponent(query)}`
        : `patients/?search=${encodeURIComponent(query)}`;

      const resp = await api.get(endpoint);
      const extractArray = (r) => {
        if (!r) return [];
        if (Array.isArray(r.data)) return r.data;
        if (r.data && Array.isArray(r.data.results)) return r.data.results;
        return [];
      };
      const arr = extractArray(resp);
      // Si la requête est numérique courte, prioriser les correspondances exactes
      if (isNumeric) {
        const numericQuery = String(query);
        const exactMatches = arr.filter((p) => {
          const suffix = String(p.id_patient || '').replace(/\D+/g, '');
          return suffix === numericQuery || String(p.id) === numericQuery || String(p.id_patient || '') === numericQuery;
        });
        if (exactMatches.length) {
          const rest = arr.filter((p) => !exactMatches.includes(p));
          const reordered = [...exactMatches, ...rest];
          setPatients(reordered);
          // If single exact match, auto-select
          if (exactMatches.length === 1) {
            setTimeout(() => handlePatientSelect(exactMatches[0]), 50);
          }
          return;
        }
      }

      setPatients(arr);
    } catch (err) {
      setError(language === 'en' ? 'Search is temporarily unavailable.' : 'Recherche indisponible pour le moment.');
      setPatients([]);
    } finally {
      setLoading(false);
    }
  };

  // Search is performed only when user confirms (press Enter)
  const handleSearch = async () => {
    const q = (search || '').trim();
    if (!q) {
      setPatients([]);
      return;
    }
    await fetchPatientsByQuery(q);
  };

  const filteredPatients = useMemo(() => {
    const q = (search || '').trim();
    if (!q) return [];

    const query = normalize(search);
    return patients.filter((patient) => {
      const haystack = [
        patient.id,
        patient.id_patient,
        patient.nom,
        patient.prenom,
        patient.maladie,
        patient.statut_inclusion,
      ].map(normalize).join(' ');
      return haystack.includes(query);
    }).slice(0, 12);
  }, [patients, search]);

  useEffect(() => {
    if (!search.trim()) {
      return;
    }

    if (filteredPatients.length === 1) {
      const [singlePatient] = filteredPatients;
      if (String(selectedPatient?.id) !== String(singlePatient.id)) {
        handlePatientSelect(singlePatient);
      }
    }
  }, [filteredPatients, search, selectedPatient?.id]);

  const latestPrediction = useMemo(() => {
    if (!selectedPatient) return null;
    const keys = [selectedPatient.id_patient, selectedPatient.id].filter(Boolean).map((value) => String(value));
    return predictions.find((prediction) => keys.includes(String(prediction.patient_id))) || null;
  }, [predictions, selectedPatient]);

  const canSeeAuditActor = ['super_admin', 'chef_service'].includes(user?.role);

  const localizePatientAuditLabel = (label, detail) => {
    const combined = `${label || ''} ${detail || ''}`.trim();
    const normalized = combined.toUpperCase();

    // Prefer explicit patient creation/deletion labels
    if (normalized.includes('CREATION_PATIENT') || normalized.includes('RECORD CREATION') || normalized.includes('CREATION')) return t('monitorActionPatientCreate');
    if (normalized.includes('SUPPRESSION_PATIENT') || normalized.includes('RECORD DELETION') || normalized.includes('SUPPRESSION')) return t('monitorActionPatientDelete');

    // Modification vs latest update: if detail contains keywords indicating clinical data updated, map to Latest update
    if (normalized.includes('DERNI') && normalized.includes('MISE') && normalized.includes('A JOUR')) return t('monitorActionPatientLatestUpdate');
    if (normalized.includes('CLINICAL DATA') || normalized.includes('CLINICAL') && normalized.includes('UPDATED')) return t('monitorActionPatientLatestUpdate');

    // Patient modification events
    if (normalized.includes('MODIFICATION_PATIENT') || normalized.includes('MODIFICATION') || normalized.includes('MODIFIED') || normalized.includes('UPDATE')) return t('monitorActionPatientUpdate');

    if (normalized.includes('DOSSIER CONSULT') || normalized.includes('RECORD VIEW') || normalized.includes('CONSULT')) return t('monitorActionPatientConsult');
    if (normalized.includes('PREDICTION') || normalized.includes('PRED')) return t('monitorActionPrediction');

    return label || detail || '-';
  };

  const events = useMemo(() => {
    if (!selectedPatient) return [];

    const timeline = patientAuditEvents.length
      ? [...patientAuditEvents]
      : [
          {
            label: t('monitorActionPatientConsult'),
            detail: `${t('monitorOpenedRecordBy')} ${roleLabel}.`,
            date: selectedPatient.updated_at || selectedPatient.created_at,
          },
          {
            label: t('monitorActionPatientCreate'),
            detail: `Patient ${selectedPatient.id_patient || selectedPatient.id || '-'} ${t('monitorPatientSaved')}`,
            date: selectedPatient.created_at,
          },
        ];

    if (!patientAuditEvents.length && selectedPatient.updated_at && selectedPatient.updated_at !== selectedPatient.created_at) {
      timeline.push({
          label: t('monitorActionPatientLatestUpdate'),
          detail: t('monitorClinicalDataUpdated'),
        date: selectedPatient.updated_at,
      });
    }

    if (latestPrediction) {
      timeline.push({
          label: t('monitorActionPrediction'),
        detail: `${latestPrediction.model || 'Modèle IA'} - score ${latestPrediction.score ?? '-'} / risque ${latestPrediction.risk_level || '-'}.`,
        date: latestPrediction.created_at,
      });
    }

    return timeline
      .filter((event) => event.date)
      .sort((left, right) => new Date(right.date).getTime() - new Date(left.date).getTime());
  }, [latestPrediction, patientAuditEvents, roleLabel, selectedPatient, t]);

  const handlePatientSelect = async (patient) => {
    setSelectedPatient(patient);
    setPatientPrediction(null);
    setError('');
    try {
      const [patientResponse, historyResponse] = await Promise.all([
        api.get(`patients/${patient.id}/`),
        api.get(`audit/patients/${patient.id}/history/`),
      ]);
      setPatientDetails(patientResponse.data);
      setPatientAuditEvents(Array.isArray(historyResponse.data) ? historyResponse.data : []);
    } catch (requestError) {
      setPatientDetails(patient);
      setPatientAuditEvents([]);
      setError("Les détails complets du patient n'ont pas pu être chargés.");
    }
    // Lire la prédiction déjà lancée pour ce patient (sans relancer le modèle)
    setLoadingPrediction(true);
    try {
      const predResp = await api.get(`predictions/stored-mortalite/${patient.id}/`);
      if (predResp.data?.success) setPatientPrediction(predResp.data);
      else setPatientPrediction(null);
    } catch (_) {
      setPatientPrediction(null);
    } finally {
      setLoadingPrediction(false);
    }
  };

  const handleHideAuditEvent = async (eventId) => {
    if (!selectedPatient?.id || !eventId) return;

    try {
      await api.post(`audit/patients/${selectedPatient.id}/history/${eventId}/hide/`);
      setPatientAuditEvents((currentEvents) => currentEvents.filter((event) => String(event.id) !== String(eventId)));
    } catch (requestError) {
      setError('Impossible de supprimer cet événement de votre historique.');
    }
  };

  const openAuditEvent = (event) => {
    setSelectedAuditEvent(event);
  };

  const closeAuditEvent = () => {
    setSelectedAuditEvent(null);
  };

  const clinicalRows = useMemo(() => {
    const source = patientDetails || selectedPatient;
    if (!source) return [];

    return [
      [t('monitorPatientId'), source.id_patient || source.id || '-'],
      [t('monitorFullName'), `${source.prenom || ''} ${source.nom || ''}`.trim() || '-'],
      [t('monitorAge'), source.age || source.demographie_age_ans || '-'],
      [t('monitorSex'), source.sexe || source.demographie_sexe || '-'],
      ['Durée dialyse', source.dialyse_duree_dialyse_mois != null && source.dialyse_duree_dialyse_mois !== '' ? `${source.dialyse_duree_dialyse_mois} mois` : '-'],
      ['Séances / semaine', source.dialyse_seances_par_semaine != null && source.dialyse_seances_par_semaine !== '' ? `${source.dialyse_seances_par_semaine}` : '-'],
      ['Hospitalisations', source.complication_nombre_hospitalisations != null && source.complication_nombre_hospitalisations !== '' ? `${source.complication_nombre_hospitalisations}` : '-'],
      [t('monitorLastUpdate'), formatDateTime(source.updated_at || source.derniere_mise_a_jour, language)],
    ];
  }, [language, patientDetails, selectedPatient, t]);

  const patientRiskScore = patientPrediction?.score_risque ?? latestPrediction?.score ?? latestPrediction?.probability ?? null;
  const patientRiskLevel = patientPrediction?.niveau_risque ?? latestPrediction?.risk_level ?? null;
  const patientRiskColor = patientRiskLevel === 'Elevé' || patientRiskLevel === 'Élevé' ? '#E74C3C' : patientRiskLevel === 'Modéré' ? '#E67E22' : patientRiskLevel === 'Faible' ? '#27AE60' : boardTheme.textMuted;

  return (
    <Box sx={{ minHeight: '100vh', background: 'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 42%,#f4eef8 100%)' }}>
      <AppSidebar />
      <Box sx={{ ml: { md: '252px' }, px: { xs: 2, md: 3 }, py: 3, maxWidth: 1760, mx: 'auto' }}>
        <Card elevation={0} sx={{ borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)', overflow: 'hidden', mb: 3, background: '#fff' }}>
          <CardContent sx={{ p: 3, position: 'relative' }}>
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
                <Typography variant="h5" sx={{ fontWeight: 900, color: boardTheme.deepNavy, letterSpacing: '-.02em', fontFamily: 'inherit' }}>
                  {t('monitorTitle')}
                </Typography>
                <Typography variant="body2" sx={{ mt: 1, maxWidth: 920, color: boardTheme.textMuted }}>
                  {t('monitorSubtitle')}
                </Typography>
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
                <Box sx={{ p: 0, borderRadius: 0, border: 'none', background: 'transparent', boxShadow: 'none' }}>
                  <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', justifyContent: { xs: 'flex-start', lg: 'flex-end' } }}>
                    <Chip label={t('monitorPatientChip')} sx={{ bgcolor: 'rgba(26,107,138,0.10)', color: boardTheme.medicalBlue, fontWeight: 700 }} />
                    <Chip label={t('monitorClinicalChip')} sx={{ bgcolor: 'rgba(212,122,142,0.10)', color: boardTheme.softRose, fontWeight: 700 }} />
                  </Stack>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {error && <Alert severity="warning" sx={{ mb: 3 }}>{error}</Alert>}

        <Grid container spacing={3}>
          <Grid item xs={12} lg={4}>
            <Card elevation={0} sx={{ borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)', overflow: 'hidden' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="overline" fontWeight={800} color="primary.main">{t('monitorSearchSectionTitle')}</Typography>
                    <Typography variant="h6" fontWeight={900} sx={{ mt: 0.5 }}>{t('monitorSearchTitle')}</Typography>
                  </Box>
                  <TextField
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        void handleSearch();
                      }
                    }}
                    placeholder={t('monitorSearchPlaceholder')}
                    fullWidth
                    size="small"
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchOutlinedIcon fontSize="small" />
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Divider />
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>
                      {t('monitorSearchResults')}
                    </Typography>
                    <List dense disablePadding sx={{ maxHeight: 280, overflow: 'auto' }}>
                      {filteredPatients.length ? filteredPatients.map((patient) => (
                        <ListItemButton
                          key={patient.id}
                          selected={String(selectedPatient?.id) === String(patient.id)}
                          onClick={() => handlePatientSelect(patient)}
                          sx={{ borderRadius: 2, mb: 0.75 }}
                        >
                          <ListItemText
                            primary={`${patient.prenom || ''} ${patient.nom || ''}`.trim() || patient.id_patient || 'Patient'}
                            secondary={`${patient.id_patient || t('monitorPatientIdMissingShort')} · ${patient.maladie || t('monitorNoClinicalData')}`}
                          />
                        </ListItemButton>
                      )) : (
                        <Typography variant="body2" color="text.secondary">{t('monitorNoMatch')}</Typography>
                      )}
                    </List>
                  </Box>
                  {loading && <Typography variant="body2" color="text.secondary">{t('monitorLoading')}</Typography>}
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} lg={8}>
            {selectedPatient ? (
              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={{ height: '100%', borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Stack spacing={2}>
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Avatar sx={{ width: 58, height: 58, bgcolor: boardTheme.deepNavy, fontWeight: 900 }}>
                            {(selectedPatient.prenom?.[0] || '') + (selectedPatient.nom?.[0] || '')}
                          </Avatar>
                          <Box>
                            <Typography variant="caption" color="text.secondary">{t('monitorPatientFile')}</Typography>
                            <Typography variant="h6" fontWeight={900}>{`${selectedPatient.prenom || ''} ${selectedPatient.nom || ''}`.trim() || '-'}</Typography>
                            <Typography variant="body2" color="text.secondary">{selectedPatient.id_patient || t('monitorPatientIdAbsent')}</Typography>
                          </Box>
                        </Stack>
                        <Divider />
                        {clinicalRows.map(([label, value]) => (
                          <Box key={label}>
                            <Typography variant="caption" color="text.secondary">{label}</Typography>
                            <Typography variant="body1" fontWeight={700}>{value || '-'}</Typography>
                          </Box>
                        ))}
                        <Box>
                          <Typography variant="caption" color="text.secondary">{t('monitorRiskLabel')}</Typography>
                          {loadingPrediction ? (
                            <Typography variant="body2" color="text.secondary">Calcul...</Typography>
                          ) : (
                            <>
                              <Typography variant="h4" fontWeight={900} sx={{ color: patientRiskScore ? patientRiskColor : boardTheme.textMuted }}>
                                {patientRiskScore !== null ? `${patientRiskScore}%` : 'N/A'}
                              </Typography>
                              {patientRiskLevel && (
                                <Typography variant="caption" sx={{ color: patientRiskColor, fontWeight: 700 }}>
                                  {patientRiskLevel}
                                </Typography>
                              )}
                            </>
                          )}
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={{ height: '100%', borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)', overflow: 'hidden' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Stack spacing={2}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                            <Box sx={{ width: 38, height: 38, borderRadius: '50%', display: 'grid', placeItems: 'center', bgcolor: 'rgba(26,107,138,0.10)', color: boardTheme.medicalBlue }}>
                              <HistoryToggleOffOutlinedIcon fontSize="small" />
                            </Box>
                            <Box>
                              <Typography variant="h6" fontWeight={900} sx={{ lineHeight: 1.1 }}>{t('monitorHistoryTitle')}</Typography>
                              <Typography variant="body2" color="text.secondary">
                                {events.length} {language === 'en' ? 'entries' : 'entrées'}
                              </Typography>
                            </Box>
                          </Box>
                          <Chip
                            label={language === 'en' ? 'Timeline' : 'Chronologie'}
                            size="small"
                            sx={{ bgcolor: 'rgba(61,90,138,0.08)', color: boardTheme.deepNavy, fontWeight: 800 }}
                          />
                        </Stack>

                        <Divider />

                        <Stack spacing={1.25} sx={{ maxHeight: 520, overflowY: 'auto', pr: 0.5 }}>
                          {events.length ? events.map((event) => {
                            const tone = getAuditTone(event.label);
                            const title = localizePatientAuditLabel(event.label, event.detail);
                            const extracted = extractOldNewFromDetail(event.detail);
                            const changes = extracted.changes || [];
                            return (
                              <Paper
                                key={`${event.id || event.label}-${event.date}`}
                                elevation={0}
                                onClick={() => openAuditEvent(event)}
                                role="button"
                                tabIndex={0}
                                onKeyDown={(keyboardEvent) => {
                                  if (keyboardEvent.key === 'Enter' || keyboardEvent.key === ' ') {
                                    keyboardEvent.preventDefault();
                                    openAuditEvent(event);
                                  }
                                }}
                                sx={{
                                  p: 1.5,
                                  borderRadius: 3,
                                  cursor: 'pointer',
                                  border: `1px solid ${tone.border}40`,
                                  background: tone.bg,
                                  position: 'relative',
                                  overflow: 'hidden',
                                  transition: 'transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease',
                                  '&:hover': {
                                    transform: 'translateY(-1px)',
                                    boxShadow: '0 10px 28px rgba(15,23,42,0.06)',
                                    borderColor: tone.border,
                                  },
                                  '&::before': {
                                    content: '""',
                                    position: 'absolute',
                                    left: 0,
                                    top: 0,
                                    bottom: 0,
                                    width: 4,
                                    background: tone.dot,
                                  },
                                }}
                              >
                                <Stack direction="row" spacing={1.25} alignItems="flex-start" justifyContent="space-between">
                                  <Box sx={{ minWidth: 0, flex: 1, pl: 0.5 }}>
                                    <Stack direction="row" spacing={1} alignItems="center" sx={{ flexWrap: 'wrap', mb: 1 }}>
                                      <Chip
                                        label={title}
                                        size="small"
                                        sx={{
                                          bgcolor: tone.chipBg,
                                          color: tone.chipColor,
                                          fontWeight: 900,
                                          borderRadius: 999,
                                          '& .MuiChip-label': { px: 1.1 },
                                        }}
                                      />
                                      <Chip
                                        label={formatDateTime(event.date, language)}
                                        size="small"
                                        variant="outlined"
                                        sx={{ borderColor: 'rgba(61,90,138,0.12)', color: boardTheme.textMuted, fontWeight: 700, height: 24 }}
                                      />
                                        <Chip
                                          label={t('auditShowDetails')}
                                          size="small"
                                          variant="outlined"
                                          sx={{ borderColor: 'rgba(26,107,138,0.16)', color: boardTheme.medicalBlue, fontWeight: 700, height: 24 }}
                                        />
                                    </Stack>
                                    <Typography variant="body2" sx={{ color: boardTheme.deepNavy, lineHeight: 1.7, mt: 0.5 }}>
                                      {changes.length
                                        ? `${changes.length} ${language === 'en' ? 'change(s)' : 'changement(s)'} ${language === 'en' ? 'available' : 'disponible(s)'}`
                                        : t('auditNoDetails')}
                                    </Typography>

                                    {canSeeAuditActor && event.user ? (
                                      <Stack direction="row" spacing={1} sx={{ mt: 1.25, flexWrap: 'wrap' }}>
                                        {canSeeAuditActor && event.user && (
                                          <Chip
                                            label={`${t('monitorPerformedBy')}: ${event.user}`}
                                            size="small"
                                            variant="outlined"
                                            sx={{ borderColor: 'rgba(61,90,138,0.20)', color: boardTheme.medicalBlue, fontWeight: 700, height: 24 }}
                                          />
                                        )}
                                      </Stack>
                                    ) : null}
                                  </Box>

                                  <Tooltip title={t('monitorDeleteHistory')}>
                                    <IconButton
                                      size="small"
                                      onClick={() => handleHideAuditEvent(event.id)}
                                      aria-label={t('monitorDeleteHistory')}
                                      sx={{
                                        mt: -0.25,
                                        border: '1px solid rgba(212,122,142,0.18)',
                                        bgcolor: 'rgba(255,255,255,0.75)',
                                        '&:hover': { bgcolor: 'rgba(212,122,142,0.10)' },
                                      }}
                                    >
                                      <DeleteOutlineOutlinedIcon fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                </Stack>
                              </Paper>
                            );
                          }) : (
                            <Box sx={{ p: 2, borderRadius: 3, border: '1px dashed rgba(61,90,138,0.20)', background: 'rgba(245,249,252,0.8)' }}>
                              <Typography variant="body2" color="text.secondary">{t('monitorNoEvents')}</Typography>
                            </Box>
                          )}
                        </Stack>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Card elevation={0} sx={{ height: '100%', borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)' }}>
                    <CardContent sx={{ p: 3 }}>
                      <Stack spacing={2}>
                        <Stack direction="row" spacing={1.25} alignItems="center">
                          <AutoGraphOutlinedIcon color="primary" />
                          <Typography variant="h6" fontWeight={900}>{t('monitorAITitle')}</Typography>
                        </Stack>
                        <Divider />
                        {loadingPrediction ? (
                          <Stack alignItems="center" py={3}>
                            <Typography variant="body2" color="text.secondary">Analyse en cours...</Typography>
                          </Stack>
                        ) : patientPrediction ? (() => {
                          const pp = patientPrediction;
                          const niv = pp.niveau_risque || 'Inconnu';
                          const rc = niv === 'Elevé' || niv === 'Élevé' ? '#E74C3C' : niv === 'Modéré' ? '#E67E22' : '#27AE60';
                          const proba = pp.probabilite_calibree ?? pp.probabilite_deces ?? 0;
                          const _ty = (pp.seuil_faible_modere ?? pp.seuil_youden ?? 0.10) * 100;
                          const _ts = (pp.seuil_modere_eleve ?? pp.seuil_spec90 ?? 0.29) * 100;
                          const grad = `linear-gradient(90deg,#27AE60 0%,#27AE60 ${_ty}%,#f39c12 ${_ty+2}%,#E67E22 ${_ts}%,#e74c3c ${_ts+2}%,#c0392b 100%)`;
                          return (
                            <Stack spacing={1.5}>
                              {/* Jauge + zone */}
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                <Box sx={{ position: 'relative', width: 72, height: 72, flexShrink: 0 }}>
                                  <svg viewBox="0 0 120 120" style={{ width: '100%', height: '100%' }}>
                                    <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(0,0,0,.08)" strokeWidth="13" />
                                    <circle cx="60" cy="60" r="50" fill="none" stroke={rc} strokeWidth="13" strokeLinecap="round"
                                      strokeDasharray={`${Math.min(proba,.999)*2*Math.PI*50} ${2*Math.PI*50}`}
                                      transform="rotate(-90 60 60)"
                                      style={{ filter: `drop-shadow(0 0 4px ${rc}80)` }} />
                                  </svg>
                                  <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                                    <Typography sx={{ fontWeight: 900, fontSize: '1rem', color: '#1e2d5a', lineHeight: 1 }}>{pp.score_risque}</Typography>
                                    <Typography sx={{ fontSize: '0.65rem', color: rc, fontWeight: 800 }}>%</Typography>
                                  </Box>
                                </Box>
                                <Box>
                                  <Typography sx={{ fontWeight: 900, fontSize: '1.4rem', color: rc, lineHeight: 1 }}>{niv}</Typography>
                                  <Typography variant="caption" color="text.secondary">Risque rel. {pp.risque_relatif || '—'}×</Typography>
                                </Box>
                              </Box>
                              {/* Spectre */}
                              <Box>
                                <Box sx={{ position: 'relative', height: 7, borderRadius: 4, background: grad, mb: 0.5 }}>
                                  <Box sx={{ position: 'absolute', left: `${Math.min(proba*100,97)}%`, top: '50%',
                                    transform: 'translate(-50%,-50%)', width: 12, height: 12, borderRadius: '50%',
                                    background: 'white', border: `2px solid ${rc}`, boxShadow: `0 0 0 2px ${rc}40` }} />
                                </Box>
                              </Box>
                              {/* Recommandation */}
                              <Box sx={{ p: 1.5, borderRadius: 2, background: `${rc}08`, border: `1px solid ${rc}20` }}>
                                <Typography variant="caption" sx={{ color: rc, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', mb: 0.5 }}>
                                  Recommandation
                                </Typography>
                                <Typography variant="body2" sx={{ color: '#444', lineHeight: 1.6, fontSize: '0.78rem' }}>
                                  {pp.recommendation || '-'}
                                </Typography>
                              </Box>
                              {/* Facteurs */}
                              {pp.factors && pp.factors.length > 0 && (
                                <Box>
                                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: 'block', mb: 0.5 }}>
                                    Facteurs déterminants
                                  </Typography>
                                  <Stack spacing={0.5}>
                                    {pp.factors.slice(0,3).map((f, i) => (
                                      <Typography key={f.label} variant="caption" sx={{ color: '#555' }}>
                                        {i+1}. {f.label.replace(/_/g,' ')} ({f.weight > 0 ? '+' : ''}{f.weight})
                                      </Typography>
                                    ))}
                                  </Stack>
                                </Box>
                              )}
                            </Stack>
                          );
                        })() : (
                          <Stack spacing={1.5} alignItems="flex-start">
                            <Typography variant="body2" color="text.secondary">
                              {t('monitorNoPrediction')}
                            </Typography>
                            <Button variant="contained" href="/modele-ai" sx={{ borderRadius: 999, textTransform: 'none' }}>
                              {t('monitorOpenAI')}
                            </Button>
                          </Stack>
                        )}
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>

                <Dialog
                  open={Boolean(selectedAuditEvent)}
                  onClose={closeAuditEvent}
                  fullWidth
                  maxWidth="md"
                  PaperProps={{ sx: { borderRadius: 4, overflow: 'hidden' } }}
                >
                  <DialogTitle sx={{ fontWeight: 900, color: boardTheme.deepNavy, borderBottom: '1px solid rgba(61,90,138,0.10)' }}>
                    {selectedAuditEvent ? localizePatientAuditLabel(selectedAuditEvent.label, selectedAuditEvent.detail) : t('auditDetails')}
                  </DialogTitle>
                  <DialogContent dividers sx={{ background: 'linear-gradient(180deg, rgba(245,249,252,0.94) 0%, rgba(255,255,255,1) 100%)' }}>
                    {selectedAuditEvent && (() => {
                      const extracted = extractOldNewFromDetail(selectedAuditEvent.detail);
                      const changes = extracted.changes || [];
                      return (
                        <Stack spacing={2}>
                          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                            <Chip label={formatDateTime(selectedAuditEvent.date, language)} sx={{ fontWeight: 800, bgcolor: 'rgba(61,90,138,0.08)', color: boardTheme.deepNavy }} />
                            {canSeeAuditActor && selectedAuditEvent.user && (
                              <Chip label={`${t('monitorPerformedBy')}: ${selectedAuditEvent.user}`} variant="outlined" sx={{ fontWeight: 700, borderColor: 'rgba(61,90,138,0.18)', color: boardTheme.medicalBlue }} />
                            )}
                          </Stack>

                          {changes.length ? (
                            <Stack spacing={1.5} sx={{ maxHeight: '58vh', overflowY: 'auto', pr: 0.5 }}>
                              {changes.map((change, index) => (
                                <Box
                                  key={`dialog-change-${selectedAuditEvent.id || selectedAuditEvent.label}-${index}`}
                                  sx={{ p: 1.5, borderRadius: 3, border: '1px solid rgba(61,90,138,0.10)', background: '#fff' }}
                                >
                                  <Typography variant="subtitle2" sx={{ fontWeight: 900, color: boardTheme.medicalBlue, mb: 1 }}>
                                    {formatAuditFieldLabel(change.field) || t('monitorClinicalDataUpdated')}
                                  </Typography>
                                  <Grid container spacing={1.25}>
                                    <Grid item xs={12} md={6}>
                                      <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: 'rgba(212,122,142,0.07)', border: '1px solid rgba(212,122,142,0.14)', maxHeight: 260, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, letterSpacing: '.05em', textTransform: 'uppercase' }}>{t('auditOldValue')}</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5, color: boardTheme.deepNavy, lineHeight: 1.65, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{String(change.old ?? '-')}</Typography>
                                      </Box>
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                      <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: 'rgba(26,107,138,0.07)', border: '1px solid rgba(26,107,138,0.14)', maxHeight: 260, overflowY: 'auto', whiteSpace: 'pre-wrap' }}>
                                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, letterSpacing: '.05em', textTransform: 'uppercase' }}>{t('auditNewValue')}</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5, color: boardTheme.deepNavy, lineHeight: 1.65, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{String(change.new ?? '-')}</Typography>
                                      </Box>
                                    </Grid>
                                  </Grid>
                                </Box>
                              ))}
                            </Stack>
                          ) : (
                            <Box sx={{ p: 2, borderRadius: 3, border: '1px solid rgba(61,90,138,0.10)', background: '#fff' }}>
                              <Typography variant="body2" sx={{ color: boardTheme.deepNavy, whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
                                {selectedAuditEvent.detail || t('auditNoDetails')}
                              </Typography>
                            </Box>
                          )}
                        </Stack>
                      );
                    })()}
                  </DialogContent>
                  <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid rgba(61,90,138,0.10)' }}>
                    <Button onClick={closeAuditEvent} variant="contained" sx={{ textTransform: 'none', fontWeight: 800 }}>
                      {t('cancel')}
                    </Button>
                  </DialogActions>
                </Dialog>
              </Grid>
            ) : false ? (
              (() => {
                const lp = lastPrediction;
                const niveau = lp.niveau_risque || 'Inconnu';
                const riskColor = niveau === 'Élevé' ? '#E74C3C' : niveau === 'Modéré' ? '#E67E22' : '#27AE60';
                const proba = lp.probabilite_deces || 0;
                const _ty = (lp.seuil_youden || 0.194) * 100;
                const _ts = (lp.seuil_spec90 || 0.357) * 100;
                const grad = `linear-gradient(90deg,#27AE60 0%,#27AE60 ${_ty}%,#f39c12 ${_ty+2}%,#E67E22 ${_ts}%,#e74c3c ${_ts+2}%,#c0392b 100%)`;
                const missing = lp.features_missing || 0;
                const cachedAt = lp.cached_at ? new Date(lp.cached_at).toLocaleString('fr-FR') : '—';
                return (
                  <Card elevation={0} sx={{ borderRadius: 5, border: `1.5px solid ${riskColor}28`, boxShadow: `0 18px 52px ${riskColor}14, 0 4px 16px rgba(15,23,42,0.06)`, overflow: 'hidden' }}>
                    {/* Header */}
                    <Box sx={{ background: 'linear-gradient(145deg,#f7f9fc,#eef1f7)', p: 2.5, borderBottom: '1px solid rgba(0,0,0,.07)' }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                        <Chip label="Dernière prédiction du système" size="small"
                          sx={{ bgcolor: 'rgba(26,107,138,.09)', color: boardTheme.medicalBlue, fontWeight: 700, fontSize: '0.7rem' }} />
                        <Typography variant="caption" sx={{ color: boardTheme.textMuted, fontSize: '0.65rem' }}>{cachedAt}</Typography>
                      </Stack>
                      <Stack direction="row" alignItems="center" spacing={2.5}>
                        {/* Mini jauge SVG */}
                        <Box sx={{ position: 'relative', width: 90, height: 90, flexShrink: 0 }}>
                          <svg viewBox="0 0 120 120" style={{ width: '100%', height: '100%' }}>
                            <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(0,0,0,.08)" strokeWidth="12" />
                            <circle cx="60" cy="60" r="50" fill="none" stroke={riskColor} strokeWidth="12" strokeLinecap="round"
                              strokeDasharray={`${Math.min(proba, .999) * 2 * Math.PI * 50} ${2 * Math.PI * 50}`}
                              transform="rotate(-90 60 60)"
                              style={{ filter: `drop-shadow(0 0 5px ${riskColor}80)` }} />
                          </svg>
                          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                            <Typography sx={{ fontWeight: 900, fontSize: '1.3rem', color: '#1e2d5a', lineHeight: 1 }}>{lp.score_risque}</Typography>
                            <Typography sx={{ fontSize: '0.75rem', color: riskColor, fontWeight: 800 }}>%</Typography>
                          </Box>
                        </Box>
                        {/* Infos patient + zone */}
                        <Box sx={{ flex: 1 }}>
                          <Typography sx={{ fontWeight: 900, fontSize: '1.6rem', color: riskColor, lineHeight: 1 }}>{niveau}</Typography>
                          <Typography sx={{ color: '#555', fontSize: '0.78rem', mt: 0.3 }}>
                            {lp.patient_name || '—'}  ·  {lp.patient_id_plateforme || `ID #${lp.patient_id}`}
                          </Typography>
                          <Stack direction="row" spacing={1} mt={1}>
                            <Chip label={`Risque rel. ${lp.risque_relatif || '—'}×`} size="small"
                              sx={{ bgcolor: `${riskColor}12`, color: riskColor, fontWeight: 700, fontSize: '0.65rem', border: `1px solid ${riskColor}25` }} />
                            <Chip label={`${32 - missing}/32 variables`} size="small"
                              sx={{ bgcolor: 'rgba(0,0,0,.04)', color: '#555', fontWeight: 600, fontSize: '0.65rem' }} />
                          </Stack>
                        </Box>
                      </Stack>
                      {/* Spectre */}
                      <Box mt={2}>
                        <Typography sx={{ color: 'rgba(0,0,0,.35)', fontSize: '0.58rem', textTransform: 'uppercase', letterSpacing: '.08em', mb: 0.8 }}>
                          Position sur le spectre — cohorte HD-478
                        </Typography>
                        <Box sx={{ position: 'relative', height: 8, borderRadius: 4, background: grad }}>
                          <Box sx={{ position: 'absolute', left: `${Math.min(proba * 100, 97)}%`, top: '50%',
                            transform: 'translate(-50%,-50%)', width: 14, height: 14, borderRadius: '50%',
                            background: 'white', border: `2.5px solid ${riskColor}`, boxShadow: `0 0 0 2px ${riskColor}40` }} />
                        </Box>
                      </Box>
                    </Box>
                    {/* Recommandation */}
                    <CardContent sx={{ p: 2.5 }}>
                      <Typography variant="caption" sx={{ color: riskColor, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.07em', fontSize: '0.65rem', display: 'block', mb: 0.8 }}>
                        Recommandation clinique
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#444', lineHeight: 1.7, fontSize: '0.84rem' }}>
                        {lp.recommendation || '—'}
                      </Typography>
                    </CardContent>
                  </Card>
                );
              })()
            ) : (
              <Card elevation={0} sx={{ borderRadius: 5, border: `1px solid ${boardTheme.border}`, boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)' }}>
                <CardContent sx={{ p: 4 }}>
                  <Stack spacing={2} alignItems="center" textAlign="center">
                    <TimelineOutlinedIcon sx={{ fontSize: 56, color: boardTheme.medicalBlue }} />
                    <Typography variant="h5" fontWeight={900}>{t('monitorSelectPatientTitle')}</Typography>
                    <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 640 }}>
                      {t('monitorSelectPatientSubtitle')}
                    </Typography>
                  </Stack>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
}

export default MonitorBoard;