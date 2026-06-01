import React, { useEffect, useRef, useState, useCallback, useContext } from 'react';
import {
  Box, Paper, Typography, Button, LinearProgress,
  Table, TableBody, TableCell, TableHead, TableRow,
  Alert, Stack, CircularProgress, Chip, Tooltip, InputBase,
  Dialog, DialogTitle, DialogContent, DialogActions, Radio, RadioGroup,
  FormControlLabel, FormControl, Divider, Tabs, Tab, IconButton,
} from '@mui/material';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';

const PALETTE = {
  navy: '#0A2B3E',
  navyLight: '#1A6B8A',
  teal: '#2C8C9E',
  tealDark: '#1A6B8A',
  rose: '#D47A8E',
  roseBg: '#F0D3DF',
  green: '#4A8B7C',
  greenBg: '#dcf7f2',
  orange: '#d18f47',
  orangeBg: '#fff1df',
  red: '#d64545',
  redBg: '#ffe3e4',
  bg: '#F5F9FC',
  bgAlt: '#EFF3F6',
  card: '#FFFFFF',
  border: '#E2ECF0',
  textDark: '#1A2F3C',
  textMuted: '#6B8A9C',
};

const MedicalIcon = () => (
  <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
    <circle cx="28" cy="28" r="28" fill="rgba(44,140,158,0.18)" />
    <rect x="24" y="14" width="8" height="28" rx="4" fill="#2C8C9E" />
    <rect x="14" y="24" width="28" height="8" rx="4" fill="#2C8C9E" />
    <circle cx="28" cy="28" r="4" fill="white" />
  </svg>
);

const DatabaseIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <ellipse cx="12" cy="6" rx="8" ry="3" stroke="currentColor" strokeWidth="2" />
    <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" stroke="currentColor" strokeWidth="2" />
    <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" stroke="currentColor" strokeWidth="2" />
  </svg>
);

const ShieldIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <path d="M12 2L4 6v6c0 5.25 3.75 10.15 8 11 4.25-.85 8-5.75 8-11V6l-8-4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const BoltIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <path d="M13 2L4.5 13.5H11L10 22L19.5 10.5H13L13 2Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
  </svg>
);

const UploadIcon = () => (
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
    <path d="M24 32V16M24 16L17 23M24 16L31 23" stroke="#1A6B8A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M10 36h28" stroke="#1A6B8A" strokeWidth="2.5" strokeLinecap="round" />
  </svg>
);

const ScoreRing = ({ score }) => {
  const color = score >= 80 ? PALETTE.green : score >= 50 ? PALETTE.orange : PALETTE.red;
  const pct = Math.max(0, Math.min(100, score));
  const r = 30, cx = 40, cy = 40;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <svg width="80" height="80" viewBox="0 0 80 80">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={PALETTE.border} strokeWidth="8" />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="8"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cy})`} style={{ transition: 'stroke-dasharray 1s ease' }} />
      <text x={cx} y={cy + 6} textAnchor="middle" fontSize="16" fontWeight="700" fill={color}>{score}</text>
    </svg>
  );
};

const StatCard = ({ icon, value, label, color }) => (
  <Box sx={{
    flex: 1, minWidth: 140, bgcolor: PALETTE.card, border: `1px solid ${PALETTE.border}`,
    borderRadius: 3, p: 2.5, display: 'flex', flexDirection: 'column', gap: 0.5,
    borderTop: `3px solid ${color}`,
  }}>
    <Box sx={{ color, mb: 0.5 }}>{icon}</Box>
    <Typography sx={{ fontSize: 26, fontWeight: 800, color: PALETTE.navy, lineHeight: 1 }}>{value}</Typography>
    <Typography sx={{ fontSize: 12, color: PALETTE.textMuted, fontWeight: 500 }}>{label}</Typography>
  </Box>
);

const PipelineStep = ({ label, status }) => {
  const bg = status === 'done' ? PALETTE.green : status === 'active' ? PALETTE.teal : PALETTE.border;
  const textColor = status === 'idle' ? PALETTE.textMuted : 'white';
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5 }}>
      <Box sx={{
        width: 36, height: 36, borderRadius: '50%', bgcolor: bg,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.4s ease',
        boxShadow: status === 'active' ? `0 0 0 6px ${PALETTE.teal}33` : 'none',
      }}>
        {status === 'done'
          ? <svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 8l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" /></svg>
          : status === 'active'
          ? <CircularProgress size={16} sx={{ color: 'white' }} />
          : <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: PALETTE.textMuted }} />
        }
      </Box>
      <Typography sx={{ fontSize: 10, fontWeight: 600, color: textColor === 'white' ? PALETTE.navy : PALETTE.textMuted, textAlign: 'center', maxWidth: 70 }}>
        {label}
      </Typography>
    </Box>
  );
};

const SeverityBadge = ({ severity }) => {
  const map = {
    critical: { bg: '#ffe3e4', color: '#d64545', label: 'Critique' },
    warning:  { bg: '#fff1df', color: '#d18f47', label: 'Attention' },
    info:     { bg: '#e8f2ff', color: '#2b6cb0', label: 'Info' },
    corrected:{ bg: '#dcf7f2', color: '#1f9d8a', label: 'Corrigé' },
    knn:      { bg: '#F0D3DF', color: '#C46B82', label: 'KNN' },
  };
  const s = map[severity] || map.info;
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', px: 1.5, py: 0.3,
      borderRadius: 10, bgcolor: s.bg, color: s.color, fontSize: 11, fontWeight: 700 }}>
      {s.label}
    </Box>
  );
};

export default function Preprocessing() {
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [loading, setLoading] = useState(() => !!localStorage.getItem('preprocess_session_id'));
  const [session, setSession] = useState(() => localStorage.getItem('preprocess_session_id') || null);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState(() => {
    const sid = localStorage.getItem('preprocess_session_id');
    return sid ? 'pending' : null;
  });
  const [statusMessage, setStatusMessage] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const pollIntervalRef = useRef(null);
  const pollErrorCountRef = useRef(0);
  const pollStartTimeRef = useRef(null);
  const fileInputRef = useRef(null);
  const [ollamaStatus, setOllamaStatus] = useState({ checking: true, connected: false, message: '', configured_model: null });
  const [datasetProfile, setDatasetProfile] = useState(null); // eslint-disable-line no-unused-vars
  const [originalPreviewRows, setOriginalPreviewRows] = useState([]); // eslint-disable-line no-unused-vars
  const [correctedPreviewRows, setCorrectedPreviewRows] = useState([]); // eslint-disable-line no-unused-vars
  const [pipelineInfo, setPipelineInfo] = useState(null); // eslint-disable-line no-unused-vars
  const [routeInfo, setRouteInfo] = useState(null);
  const [cellCorrections, setCellCorrections] = useState(null);
  const [corrTableTab, setCorrTableTab] = useState(0);
  // Inline editing: key = `${row}-${column}`, value = current edited string
  const [editingCell, setEditingCell] = useState(null); // {row, column}
  const [editingValue, setEditingValue] = useState('');
  const [manualOverrides, setManualOverrides] = useState({}); // key `${row}-${col}` → new value
  const [savingOverride, setSavingOverride] = useState(false);
  const [integrateDialogOpen, setIntegrateDialogOpen] = useState(false);
  const [integrateSource, setIntegrateSource] = useState('corrected');
  const [integrateLoading, setIntegrateLoading] = useState(false);
  const [integrateSuccess, setIntegrateSuccess] = useState(null);
  const { user } = useContext(AuthContext);
  const isChefOrAdmin = user?.role === 'super_admin' || user?.role === 'chef_service';

  const isAllowedFileType = (f) => {
    const n = String(f?.name || '').toLowerCase();
    return n.endsWith('.csv') || n.endsWith('.xlsx');
  };

  const applyFile = (f) => {
    localStorage.removeItem('preprocess_session_id');
    setReport(null); setSession(null); setStatus(null); setStatusMessage('');
    setDatasetProfile(null); setOriginalPreviewRows([]); setCorrectedPreviewRows([]);
    setPipelineInfo(null); setRouteInfo(null); setCellCorrections(null); setCorrTableTab(0);
    setManualOverrides({}); setEditingCell(null);
    if (!f) { setFile(null); setFileError(''); return; }
    if (!isAllowedFileType(f)) { setFile(null); setFileError('Format invalide. Choisissez .csv ou .xlsx.'); return; }
    setFile(f); setFileError('');
  };

  const handleFileChange = (e) => applyFile(e.target.files?.[0]);
  const handleDrop = (e) => { e.preventDefault(); setDragOver(false); applyFile(e.dataTransfer.files?.[0]); };

  useEffect(() => {
    if (!session || status !== 'pending') { if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; } return; }
    pollStartTimeRef.current = Date.now();
    const interval = setInterval(async () => {
      if (Date.now() - pollStartTimeRef.current > 240 * 60 * 1000) { setStatus('error'); setStatusMessage("Délai dépassé (4h)."); clearInterval(interval); setLoading(false); return; }
      try {
        const resp = await api.get(`patients/preprocess/${session}/status/`);
        pollErrorCountRef.current = 0;
        const data = resp.data || {};
        setStatusMessage(data.progress_message || data.message || 'Traitement...');
        if (data.status === 'completed') {
          localStorage.removeItem('preprocess_session_id');
          setStatus('completed'); setReport(data.report || null);
          setDatasetProfile(data.dataset_profile || data.report?.dataset_profile || null);
          setOriginalPreviewRows(data.original_preview_rows || []);
          // Fetch per-cell corrections after analysis completes
          try {
            const corrResp = await api.get(`patients/preprocess/${session}/cell-corrections/`);
            setCellCorrections(corrResp.data || null);
          } catch { /* non-blocking */ }
          setCorrectedPreviewRows(data.corrected_preview_rows || data.preview_rows || []);
          setPipelineInfo(data.report?.pipeline || null);
          setRouteInfo(data.report?.route || null);
          clearInterval(interval); pollIntervalRef.current = null; setLoading(false);
        } else if (data.status === 'error') {
          localStorage.removeItem('preprocess_session_id');
          setStatus('error'); setStatusMessage(data.error || 'Erreur analyse.');
          clearInterval(interval); pollIntervalRef.current = null; setLoading(false);
        }
      } catch {
        pollErrorCountRef.current += 1;
        if (pollErrorCountRef.current >= 15) { setStatus('error'); setStatusMessage('Serveur indisponible.'); clearInterval(interval); setLoading(false); }
      }
    }, 2000);
    pollIntervalRef.current = interval;
    return () => clearInterval(interval);
  }, [session, status]);

  const handleAnalyze = async () => {
    if (!file || loading || status === 'pending') return;
    setLoading(true); setStatus('pending'); setStatusMessage('Initialisation...');
    pollErrorCountRef.current = 0;
    try {
      const form = new FormData(); form.append('file', file);
      const resp = await api.post('patients/preprocess/analyze/', form);
      const sid = resp.data?.preprocess_id || resp.data?.id;
      if (sid) { setSession(sid); setStatus('pending'); localStorage.setItem('preprocess_session_id', sid); }
      else { setStatus('error'); setStatusMessage('ID de session non reçu.'); setLoading(false); }
    } catch (err) { setStatus('error'); setStatusMessage(err?.response?.data?.error || 'Erreur.'); setLoading(false); }
  };

  const handleStopAnalysis = async () => {
    if (!session) return;
    try {
      await api.post(`patients/preprocess/${session}/cancel/`, {});
    } catch {}
    localStorage.removeItem('preprocess_session_id');
    if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; }
    setStatus(null); setSession(null); setLoading(false); setStatusMessage('');
  };

  const checkOllamaStatus = async () => {
    setOllamaStatus(p => ({ ...p, checking: true }));
    try {
      const { data } = await api.get('patients/preprocess/health/');
      setOllamaStatus({ checking: false, connected: !!data.connected, message: data.message || '', configured_model: data.configured_model || null });
    } catch (err) {
      const d = err?.response?.data || {};
      setOllamaStatus({ checking: false, connected: false, message: d.message || 'Ollama indisponible.', configured_model: null });
    }
  };

  useEffect(() => { checkOllamaStatus(); }, []);

  const startEdit = useCallback((row, column, currentValue) => {
    setEditingCell({ row, column });
    setEditingValue(String(currentValue ?? ''));
  }, []);

  const cancelEdit = useCallback(() => {
    setEditingCell(null);
    setEditingValue('');
  }, []);

  const commitEdit = useCallback(async () => {
    if (!editingCell || !session) return;
    const { row, column } = editingCell;
    const key = `${row}-${column}`;
    setSavingOverride(true);
    try {
      await api.post(`patients/preprocess/${session}/apply-overrides/`, {
        overrides: [{ row, column, new_value: editingValue }],
      });
      setManualOverrides(prev => ({ ...prev, [key]: editingValue }));
      // Update local cellCorrections display
      setCellCorrections(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          corrections: prev.corrections.map(c =>
            c.row === row && c.column === column
              ? { ...c, new_value: editingValue, manually_edited: true }
              : c
          ),
        };
      });
    } catch { /* silently ignore — local state already updated */ }
    finally { setSavingOverride(false); }
    setEditingCell(null);
    setEditingValue('');
  }, [editingCell, editingValue, session]);

  const handleExport = async (source = 'corrected') => {
    if (!session) return;
    try {
      const resp = await api.get(`patients/preprocess/${session}/export/?source=${source}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const a = document.createElement('a'); a.href = url;
      a.setAttribute('download', `preprocess_${session}_${source}.xlsx`);
      document.body.appendChild(a); a.click(); a.remove();
    } catch { alert('Erreur export'); }
  };

  const handleIntegrate = async () => {
    if (!session) return;
    setIntegrateDialogOpen(true);
  };

  const handleIntegrateConfirm = async () => {
    setIntegrateLoading(true);
    try {
      const resp = await api.post(`patients/preprocess/${session}/submit-validation/`, { source: integrateSource });
      const validationId = resp.data?.validation_id;
      if (isChefOrAdmin && validationId) {
        await api.post(`patients/preprocess/validations/${validationId}/`, { action: 'approve' });
        setIntegrateSuccess('inserted');
      } else {
        setIntegrateSuccess('pending');
      }
    } catch { alert('Erreur soumission.'); setIntegrateLoading(false); }
    finally { setLoading(false); setIntegrateLoading(false); }
  };

  const pipelineStages = [
    { key: 'upload', label: 'Lecture' },
    { key: 'profile', label: 'Profilage' },
    { key: 'chunking', label: 'Découpage' },
    { key: 'retrieval', label: 'Retrieval' },
    { key: 'llm1', label: 'LLM' },
    { key: 'llm2', label: 'Correction' },
    { key: 'merge', label: 'Rapport' },
  ];

  const currentStageKey = (() => {
    const t = String(statusMessage || '').toLowerCase();
    if (t.includes('lecture') || t.includes('initialisation')) return 'upload';
    if (t.includes('profilage')) return 'profile';
    if (t.includes('chunk')) return 'chunking';
    if (t.includes('retrieval') || t.includes('contexte') || t.includes('rag')) return 'retrieval';
    if (t.includes('batch') || t.includes('llm') || t.includes('ollama')) return 'llm1';
    if (t.includes('correction') || t.includes('bio') || t.includes('knn')) return 'llm2';
    if (t.includes('rapport') || t.includes('fusion') || t.includes('finalis')) return 'merge';
    return null;
  })();

  const stageOrder = pipelineStages.map(s => s.key);

  const getStageStatus = (key) => {
    if (status === 'completed') return 'done';
    const activeIdx = stageOrder.indexOf(currentStageKey);
    const thisIdx = stageOrder.indexOf(key);
    if (thisIdx < activeIdx) return 'done';
    if (thisIdx === activeIdx) return 'active';
    return 'idle';
  };

  // Build table rows
  const allIssues = report ? (report.all_issues || report.issues || []) : [];
  const appliedCorrections = report?.applied_corrections || [];
  // eslint-disable-next-line no-unused-vars
  const correctionPlan = report?.correction_plan || {};

  const issuesByColumn = {};
  allIssues.forEach(issue => {
    const col = issue?.column; if (!col) return;
    if (!issuesByColumn[col]) issuesByColumn[col] = [];
    issuesByColumn[col].push(issue);
  });

  const correctedColumns = new Set();
  const tableRows = [];

  appliedCorrections.forEach(action => {
    const actionType = String(action?.action || '');
    const cols = Array.isArray(action?.details?.columns) ? action.details.columns : [];
    cols.forEach(c => {
      const colName = typeof c === 'string' ? c : (c?.column || c?.name || c?.from || '');
      if (!colName) return;
      correctedColumns.add(colName);
      const colIssues = issuesByColumn[colName] || [];
      let justification = colIssues.map(i => i.explanation).filter(Boolean).join(' | ') || '';
      let correction = '';
      if (actionType === 'type_casts') correction = `→ ${c?.target_type || 'numeric'}`;
      else if (actionType === 'fill_missing') correction = `Manquants comblés (${c?.strategy || 'auto'})`;
      else if (actionType === 'trim_whitespace') correction = `Espaces nettoyés`;
      else if (actionType === 'parse_dates') correction = 'Format date unifié';
      else if (actionType === 'value_mappings') {
        const m = c?.mapping || {};
        correction = Object.entries(m).slice(0, 2).map(([f, t]) => `"${f}"→"${t}"`).join(', ') + (Object.keys(m).length > 2 ? '...' : '');
      } else if (actionType === 'bio_value_correction' || actionType === 'llm_value_correction') {
        const corrs = c?.corrections || {};
        correction = Object.entries(corrs).slice(0, 2).map(([f, t]) => `${f}→${t ?? 'NaN'}`).join(', ');
        justification = c?.explanation || justification;
      } else if (actionType === 'knn_imputation') {
        correction = `${c?.imputed_count ?? 0} valeur(s) KNN`;
      } else correction = actionType;
      tableRows.push({ colName, actionType, correction, justification: justification || 'Correction automatique', cells: c?.cells_changed ?? c?.imputed_count ?? null, status: actionType === 'knn_imputation' ? 'knn' : 'corrected', severity: 'corrected' });
    });
  });

  const flaggedAdded = new Set();
  allIssues.forEach(issue => {
    const colName = issue?.column;
    if (!colName || correctedColumns.has(colName) || flaggedAdded.has(colName)) return;
    flaggedAdded.add(colName);
    const severity = String(issue?.severity || 'warning').toLowerCase();
    tableRows.push({ colName, actionType: issue?.category || 'anomalie', correction: null, justification: issue?.explanation || '—', cells: null, status: 'flagged', severity });
  });

  tableRows.sort((a, b) => {
    if (a.status !== b.status) return a.status === 'corrected' ? -1 : 1;
    const o = { critical: 0, warning: 1, info: 2 };
    return (o[a.severity] ?? 1) - (o[b.severity] ?? 1);
  });

  const score = report?.summary?.quality_score ?? null;
  const correctedCount = tableRows.filter(r => r.status === 'corrected' || r.status === 'knn').length;
  const flaggedCount = tableRows.filter(r => r.status === 'flagged').length;

  return (
    <Box sx={{ pb: 4 }}>

      {/* ── Main Content ── */}
      <Box>

        {/* Upload Card */}
        <Paper elevation={0} sx={{ borderRadius: 3, border: `1px solid ${PALETTE.border}`, overflow: 'hidden', mb: 3 }}>
          <Box sx={{ px: 3, py: 2.5, borderBottom: `1px solid ${PALETTE.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography sx={{ fontWeight: 700, color: PALETTE.textDark, fontSize: 15 }}>
              Importer un fichier de données
            </Typography>
            {/* Ollama status inline */}
            <Stack direction="row" spacing={1} alignItems="center">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, px: 1.5, py: 0.5, borderRadius: 10,
                bgcolor: ollamaStatus.connected ? '#dcf7f2' : '#ffe3e4',
                border: `1px solid ${ollamaStatus.connected ? '#4A8B7C' : '#d64545'}33` }}>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%',
                  bgcolor: ollamaStatus.checking ? PALETTE.orange : ollamaStatus.connected ? PALETTE.green : PALETTE.red,
                  animation: ollamaStatus.checking ? 'pulse 1s infinite' : 'none' }} />
                <Typography sx={{ fontSize: 11, fontWeight: 600,
                  color: ollamaStatus.connected ? PALETTE.green : PALETTE.red }}>
                  {ollamaStatus.checking ? 'Vérification...' : ollamaStatus.connected ? `LLM · ${ollamaStatus.configured_model || 'Ollama'}` : 'LLM indisponible'}
                </Typography>
              </Box>
              <Button onClick={checkOllamaStatus} disabled={ollamaStatus.checking}
                sx={{ fontSize: 11, color: PALETTE.textMuted, textTransform: 'none', minWidth: 0, px: 1,
                  '&:hover': { color: PALETTE.navyLight, bgcolor: 'transparent' } }}>
                Actualiser
              </Button>
            </Stack>
          </Box>

          <Box sx={{ p: 4 }}>
            {/* Drop zone */}
            <Box
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              sx={{
                border: `2px dashed ${dragOver ? PALETTE.teal : file ? PALETTE.green : PALETTE.border}`,
                borderRadius: 3, p: 4, textAlign: 'center', cursor: 'pointer',
                bgcolor: dragOver ? `${PALETTE.teal}08` : file ? `${PALETTE.green}08` : PALETTE.bg,
                transition: 'all 0.2s ease',
                '&:hover': { borderColor: PALETTE.teal, bgcolor: `${PALETTE.teal}08` },
              }}>
              <input ref={fileInputRef} type="file" accept=".csv,.xlsx" onChange={handleFileChange} style={{ display: 'none' }} />
              {file ? (
                <Stack spacing={1} alignItems="center">
                  <Box sx={{ width: 48, height: 48, borderRadius: 2, bgcolor: `${PALETTE.green}20`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke={PALETTE.green} strokeWidth="2" />
                      <path d="M14 2v6h6M9 15l2 2 4-4" stroke={PALETTE.green} strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </Box>
                  <Typography sx={{ fontWeight: 700, color: PALETTE.navy }}>{file.name}</Typography>
                  <Typography sx={{ fontSize: 12, color: PALETTE.textMuted }}>
                    {(file.size / 1024).toFixed(1)} KB · Cliquer pour changer
                  </Typography>
                </Stack>
              ) : (
                <Stack spacing={1.5} alignItems="center">
                  <UploadIcon />
                  <Typography sx={{ fontWeight: 700, color: PALETTE.navy }}>
                    Glisser-déposer votre fichier ici
                  </Typography>
                  <Typography sx={{ fontSize: 13, color: PALETTE.textMuted }}>
                    ou cliquer pour sélectionner · CSV ou XLSX recommandé
                  </Typography>
                </Stack>
              )}
            </Box>

            {fileError && <Alert severity="error" sx={{ mt: 2, borderRadius: 2 }}>{fileError}</Alert>}

            {/* Action buttons */}
            <Stack direction="row" spacing={2} sx={{ mt: 3, flexWrap: 'wrap' }}>

              {/* Lancer l'analyse */}
              <Button variant="contained" onClick={handleAnalyze} disabled={!file || loading}
                sx={{
                  background: `linear-gradient(135deg, ${PALETTE.navy} 0%, #1A6B8A 100%)`,
                  color: 'white', borderRadius: 2.5, px: 4, py: 1.5,
                  fontWeight: 700, fontSize: 14, textTransform: 'none',
                  boxShadow: `0 4px 15px ${PALETTE.navy}55`,
                  transition: 'all 0.25s ease',
                  '&:hover': {
                    background: `linear-gradient(135deg, #1A6B8A 0%, #2C8C9E 100%)`,
                    boxShadow: `0 6px 20px ${PALETTE.navy}77`,
                    transform: 'translateY(-2px)',
                  },
                  '&:disabled': { background: PALETTE.border, color: PALETTE.textMuted, boxShadow: 'none', transform: 'none' },
                }}>
                {loading && status === 'pending'
                  ? <><CircularProgress size={15} sx={{ color: 'white', mr: 1 }} />Analyse en cours...</>
                  : <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="white" strokeWidth="2"/>
                        <path d="M10 8l6 4-6 4V8z" fill="white"/>
                      </svg>
                      Lancer l'analyse
                    </Box>
                }
              </Button>

              {/* Arrêter */}
              {loading && status === 'pending' && (
                <Button variant="outlined" onClick={handleStopAnalysis}
                  sx={{
                    borderRadius: 2.5, px: 3, py: 1.5, fontWeight: 600, textTransform: 'none',
                    borderColor: PALETTE.red, color: PALETTE.red,
                    transition: 'all 0.25s ease',
                    '&:hover': { bgcolor: PALETTE.redBg, transform: 'translateY(-2px)', boxShadow: `0 4px 12px ${PALETTE.red}44` },
                  }}>
                  Arrêter
                </Button>
              )}

              {/* Exporter corrigé */}
              <Button variant="contained" onClick={() => handleExport('corrected')}
                disabled={!session || loading || status !== 'completed'}
                sx={{
                  background: 'linear-gradient(135deg, #D47A8E 0%, #C46B82 50%, #A855A0 100%)',
                  color: 'white', borderRadius: 2.5, px: 3, py: 1.5,
                  fontWeight: 700, fontSize: 13, textTransform: 'none',
                  boxShadow: '0 4px 15px #D47A8E66',
                  transition: 'all 0.25s ease',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #C46B82 0%, #A855A0 100%)',
                    boxShadow: '0 6px 22px #D47A8E88',
                    transform: 'translateY(-2px)',
                  },
                  '&:disabled': { background: PALETTE.border, color: PALETTE.textMuted, boxShadow: 'none', transform: 'none' },
                }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M12 16l-4-4h3V4h2v8h3l-4 4z" fill="white"/>
                    <path d="M4 20h16v-2H4v2z" fill="white"/>
                  </svg>
                  Exporter (.xlsx)
                </Box>
              </Button>

              {/* Suivant */}
              <Button variant="contained" onClick={handleIntegrate}
                disabled={!session || loading || status !== 'completed'}
                sx={{
                  background: 'linear-gradient(135deg, #D47A8E 0%, #9B59B6 100%)',
                  color: 'white', borderRadius: 2.5, px: 3.5, py: 1.5,
                  fontWeight: 700, fontSize: 13, textTransform: 'none',
                  boxShadow: '0 4px 15px #9B59B655',
                  transition: 'all 0.25s ease',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #C46B82 0%, #8e44ad 100%)',
                    boxShadow: '0 6px 22px #9B59B677',
                    transform: 'translateY(-2px)',
                  },
                  '&:disabled': { background: PALETTE.border, color: PALETTE.textMuted, boxShadow: 'none', transform: 'none' },
                }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  Suivant
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                    <path d="M9 18l6-6-6-6" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </Box>
              </Button>

            </Stack>
          </Box>
        </Paper>

        {/* Integration Dialog */}
        <Dialog open={integrateDialogOpen} onClose={() => !integrateLoading && setIntegrateDialogOpen(false)}
          PaperProps={{ sx: { borderRadius: 3, minWidth: 420, p: 1 } }}>
          <DialogTitle sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 18 }}>
            Intégrer les données
          </DialogTitle>
          <Divider />
          <DialogContent sx={{ pt: 3 }}>
            {integrateSuccess ? (
              <Box sx={{ textAlign: 'center', py: 2 }}>
                {integrateSuccess === 'inserted' ? (
                  <>
                    <Typography sx={{ color: PALETTE.green, fontWeight: 700, fontSize: 16, mb: 1 }}>
                      ✓ Données intégrées avec succès !
                    </Typography>
                    <Typography variant="body2" sx={{ color: PALETTE.textMuted }}>
                      Les données ont été validées et insérées dans la plateforme.
                    </Typography>
                  </>
                ) : (
                  <>
                    <Typography sx={{ color: PALETTE.orange, fontWeight: 700, fontSize: 16, mb: 1 }}>
                      ✓ Import soumis pour validation !
                    </Typography>
                    <Typography variant="body2" sx={{ color: PALETTE.textMuted }}>
                      La version {integrateSource === 'corrected' ? 'corrigée' : 'originale'} est en attente de validation par le chef de service ou l'administrateur.
                    </Typography>
                  </>
                )}
              </Box>
            ) : (
              <>
                <Typography variant="body2" sx={{ color: PALETTE.textMuted, mb: 2 }}>
                  {isChefOrAdmin
                    ? 'Choisissez la version à intégrer directement dans la plateforme.'
                    : "Choisissez la version à soumettre pour validation. Le chef de service ou l'administrateur devra valider avant intégration."}
                </Typography>
                <FormControl component="fieldset" sx={{ width: '100%' }}>
                  <RadioGroup value={integrateSource} onChange={(e) => setIntegrateSource(e.target.value)}>
                    <Paper variant="outlined" sx={{
                      p: 2, mb: 1.5, borderRadius: 2, cursor: 'pointer',
                      borderColor: integrateSource === 'corrected' ? PALETTE.teal : PALETTE.border,
                      bgcolor: integrateSource === 'corrected' ? `${PALETTE.teal}08` : 'white',
                    }} onClick={() => setIntegrateSource('corrected')}>
                      <FormControlLabel value="corrected" control={<Radio size="small" sx={{ color: PALETTE.teal, '&.Mui-checked': { color: PALETTE.teal } }} />}
                        label={<Box>
                          <Typography sx={{ fontWeight: 600, fontSize: 14, color: PALETTE.navy }}>Version corrigée</Typography>
                          <Typography variant="caption" sx={{ color: PALETTE.textMuted }}>
                            Données après corrections automatiques du LLM (recommandé)
                          </Typography>
                        </Box>} />
                    </Paper>
                    <Paper variant="outlined" sx={{
                      p: 2, borderRadius: 2, cursor: 'pointer',
                      borderColor: integrateSource === 'original' ? PALETTE.rose : PALETTE.border,
                      bgcolor: integrateSource === 'original' ? `${PALETTE.rose}08` : 'white',
                    }} onClick={() => setIntegrateSource('original')}>
                      <FormControlLabel value="original" control={<Radio size="small" sx={{ color: PALETTE.rose, '&.Mui-checked': { color: PALETTE.rose } }} />}
                        label={<Box>
                          <Typography sx={{ fontWeight: 600, fontSize: 14, color: PALETTE.navy }}>Version originale</Typography>
                          <Typography variant="caption" sx={{ color: PALETTE.textMuted }}>
                            Données brutes sans aucune modification
                          </Typography>
                        </Box>} />
                    </Paper>
                  </RadioGroup>
                </FormControl>
              </>
            )}
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
            {integrateSuccess ? (
              <Button variant="contained" onClick={() => { setIntegrateDialogOpen(false); setIntegrateSuccess(null); }}
                sx={{ bgcolor: PALETTE.navy, borderRadius: 2, textTransform: 'none', fontWeight: 600, px: 3 }}>
                Fermer
              </Button>
            ) : (
              <>
                <Button onClick={() => setIntegrateDialogOpen(false)} disabled={integrateLoading}
                  sx={{ borderRadius: 2, textTransform: 'none', color: PALETTE.textMuted }}>
                  Annuler
                </Button>
                <Button variant="contained" onClick={handleIntegrateConfirm} disabled={integrateLoading}
                  sx={{ bgcolor: PALETTE.navy, borderRadius: 2, textTransform: 'none', fontWeight: 600, px: 3,
                    '&:hover': { bgcolor: PALETTE.navyLight } }}>
                  {integrateLoading ? <><CircularProgress size={14} sx={{ color: 'white', mr: 1 }} />Envoi...</> : (isChefOrAdmin ? 'Valider et intégrer' : 'Soumettre pour validation')}
                </Button>
              </>
            )}
          </DialogActions>
        </Dialog>

        {/* Pipeline Progress */}
        {(loading || status === 'completed') && (
          <Paper elevation={0} sx={{ borderRadius: 4, border: `1px solid ${PALETTE.border}`, mb: 3, overflow: 'hidden' }}>
            <Box sx={{ px: 4, py: 2.5, borderBottom: `1px solid ${PALETTE.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 15 }}>Pipeline d'analyse</Typography>
              {status === 'completed' && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, color: PALETTE.green }}>
                  <svg width="16" height="16" viewBox="0 0 16 16"><path d="M3 8l3 3 7-7" stroke={PALETTE.green} strokeWidth="2" strokeLinecap="round" /></svg>
                  <Typography sx={{ fontSize: 13, fontWeight: 700, color: PALETTE.green }}>Terminé</Typography>
                </Box>
              )}
            </Box>
            <Box sx={{ px: 4, py: 3 }}>
              {/* Steps */}
              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0 }}>
                {pipelineStages.map((stage, idx) => (
                  <Box key={stage.key} sx={{ display: 'flex', alignItems: 'flex-start', flex: 1 }}>
                    <PipelineStep label={stage.label} status={getStageStatus(stage.key)} />
                    {idx < pipelineStages.length - 1 && (
                      <Box sx={{ flex: 1, height: 2, mt: 2.2, mx: 0.5,
                        bgcolor: getStageStatus(stage.key) === 'done' ? PALETTE.green : PALETTE.border,
                        transition: 'background-color 0.4s' }} />
                    )}
                  </Box>
                ))}
              </Box>

              {status === 'pending' && (
                <Box sx={{ mt: 2.5 }}>
                  <LinearProgress sx={{ borderRadius: 10, height: 4,
                    '& .MuiLinearProgress-bar': { bgcolor: PALETTE.teal } }} />
                  <Typography sx={{ mt: 1.5, fontSize: 13, color: PALETTE.textMuted }}>
                    {statusMessage}
                    {routeInfo?.primary_model && ` · Modèle: ${routeInfo.primary_model}`}
                  </Typography>
                </Box>
              )}
            </Box>
          </Paper>
        )}

        {/* Error */}
        {status === 'error' && (
          <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>
            <Typography sx={{ fontWeight: 700 }}>Erreur d'analyse</Typography>
            <Typography variant="body2">{statusMessage}</Typography>
          </Alert>
        )}

        {/* Results */}
        {report?.summary && (() => {
          const s = report.summary;
          const cellCorrs = cellCorrections?.corrections || [];
          const cellFlagged = cellCorrections?.flagged || [];
          const totalCellCorr = cellCorrections?.total_corrections ?? correctedCount;
          const totalFlagged = cellCorrections?.total_flagged ?? flaggedCount;

          const severityColor = (sev) => {
            if (sev === 'critical' || sev === 'error') return PALETTE.red;
            if (sev === 'warning') return PALETTE.orange;
            return PALETTE.teal;
          };
          const severityLabel = (sev) => {
            if (sev === 'critical' || sev === 'error') return 'Critique';
            if (sev === 'warning') return 'Attention';
            return 'Info';
          };
          const severityBg = (sev) => {
            if (sev === 'critical' || sev === 'error') return PALETTE.redBg;
            if (sev === 'warning') return PALETTE.orangeBg;
            return '#e8f2ff';
          };

          return (
            <Box>
              {/* Stats row */}
              <Stack direction="row" spacing={2} sx={{ mb: 3, flexWrap: 'wrap' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2,
                  bgcolor: PALETTE.card, border: `1px solid ${PALETTE.border}`, borderRadius: 3, p: 2.5,
                  borderTop: `3px solid ${score >= 80 ? PALETTE.green : score >= 50 ? PALETTE.orange : PALETTE.red}` }}>
                  <ScoreRing score={score ?? 0} />
                  <Box>
                    <Typography sx={{ fontSize: 12, color: PALETTE.textMuted, fontWeight: 600 }}>SCORE QUALITÉ</Typography>
                    <Typography sx={{ fontSize: 13, color: PALETTE.navy, fontWeight: 600, mt: 0.3 }}>
                      {score >= 80 ? 'Excellent' : score >= 50 ? 'À améliorer' : 'Critique'}
                    </Typography>
                  </Box>
                </Box>
                <StatCard icon={<DatabaseIcon />} value={s.rows ?? '-'} label="Lignes analysées" color={PALETTE.teal} />
                <StatCard icon={<ShieldIcon />} value={totalCellCorr} label="Cellules corrigées" color={PALETTE.green} />
                <StatCard icon={<BoltIcon />} value={totalFlagged} label="Colonnes suspectes" color={totalFlagged > 0 ? PALETTE.orange : PALETTE.green} />
              </Stack>

              {totalFlagged > 0 && (
                <Alert severity="warning" sx={{ mb: 2.5, borderRadius: 3 }}>
                  <Typography sx={{ fontWeight: 700, fontSize: 13 }}>
                    {totalFlagged} colonne(s) suspecte(s) sans correction automatique — vérification manuelle recommandée
                  </Typography>
                </Alert>
              )}

              {/* Detailed Corrections Table */}
              <Paper elevation={0} sx={{ borderRadius: 4, border: `1px solid ${PALETTE.border}`, overflow: 'hidden', mb: 2 }}>
                {/* Header */}
                <Box sx={{ px: 3, py: 2, borderBottom: `1px solid ${PALETTE.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Typography sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 15 }}>
                      Rapport détaillé — Anomalies &amp; Corrections
                    </Typography>
                    {Object.keys(manualOverrides).length > 0 && (
                      <Chip
                        label={`${Object.keys(manualOverrides).length} modif. manuelle(s)`}
                        size="small"
                        sx={{ bgcolor: PALETTE.teal, color: 'white', fontWeight: 700, fontSize: 11 }}
                      />
                    )}
                  </Box>
                  <Stack direction="row" spacing={1}>
                    <Tooltip title="Exporter le fichier corrigé (cellules modifiées surlignées en jaune)">
                      <Button onClick={() => handleExport('corrected')} disabled={!session}
                        startIcon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 16l-4-4h3V4h2v8h3l-4 4zM4 20h16v-2H4v2z" fill="currentColor"/></svg>}
                        sx={{ bgcolor: PALETTE.green, color: 'white', borderRadius: 2, px: 2, py: 0.8,
                          fontSize: 12, fontWeight: 700, textTransform: 'none',
                          '&:hover': { bgcolor: '#3a7a6c' }, '&:disabled': { bgcolor: PALETTE.border, color: PALETTE.textMuted } }}>
                        Exporter corrigé (.xlsx)
                      </Button>
                    </Tooltip>
                    <Tooltip title="Exporter le fichier original sans aucune modification">
                      <Button onClick={() => handleExport('original')} disabled={!session}
                        startIcon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 16l-4-4h3V4h2v8h3l-4 4zM4 20h16v-2H4v2z" fill="currentColor"/></svg>}
                        sx={{ border: `1px solid ${PALETTE.border}`, color: PALETTE.textMuted, borderRadius: 2, px: 2, py: 0.8,
                          fontSize: 12, fontWeight: 700, textTransform: 'none', bgcolor: 'white',
                          '&:hover': { bgcolor: PALETTE.bgAlt } }}>
                        Exporter original
                      </Button>
                    </Tooltip>
                  </Stack>
                </Box>

                {/* Tabs */}
                <Box sx={{ borderBottom: `1px solid ${PALETTE.border}`, px: 3 }}>
                  <Tabs value={corrTableTab} onChange={(_, v) => setCorrTableTab(v)}
                    sx={{ minHeight: 40, '& .MuiTab-root': { minHeight: 40, fontSize: 12, fontWeight: 600, textTransform: 'none', px: 2 },
                      '& .Mui-selected': { color: PALETTE.navy }, '& .MuiTabs-indicator': { bgcolor: PALETTE.navy } }}>
                    <Tab label={`Cellules corrigées (${cellCorrs.length})`} title="Cliquez sur une valeur corrigée pour la modifier manuellement" />
                    <Tab label={`Colonnes suspectes (${cellFlagged.length})`} />
                  </Tabs>
                </Box>

                {/* Tab 0: Per-cell corrections */}
                {corrTableTab === 0 && (
                  cellCorrs.length === 0 ? (
                    <Box sx={{ p: 5, textAlign: 'center' }}>
                      <Box sx={{ color: PALETTE.green, mb: 1 }}>
                        <svg width="36" height="36" viewBox="0 0 40 40">
                          <circle cx="20" cy="20" r="18" fill={`${PALETTE.green}20`} />
                          <path d="M12 20l5 5 11-11" stroke={PALETTE.green} strokeWidth="2.5" strokeLinecap="round" />
                        </svg>
                      </Box>
                      <Typography sx={{ fontWeight: 700, color: PALETTE.navy }}>Aucune correction appliquée</Typography>
                      <Typography sx={{ color: PALETTE.textMuted, fontSize: 13, mt: 0.5 }}>Le fichier est propre ou toutes les anomalies sont à vérifier manuellement.</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ overflowX: 'auto' }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow sx={{ bgcolor: PALETTE.bgAlt }}>
                            {['Ligne', 'ID Patient', 'Colonne', 'Valeur originale', 'Valeur corrigée', 'Type', 'Justification'].map(h => (
                              <TableCell key={h} sx={{ fontWeight: 700, fontSize: 11, color: PALETTE.textMuted,
                                textTransform: 'uppercase', letterSpacing: 0.4, borderBottom: `2px solid ${PALETTE.border}`,
                                whiteSpace: 'nowrap', py: 1.2, px: 1.5 }}>
                                {h}
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {cellCorrs.map((c, idx) => {
                            const cellKey = `${c.row}-${c.column}`;
                            const isEditing = editingCell?.row === c.row && editingCell?.column === c.column;
                            const isManual = c.manually_edited || manualOverrides[cellKey] !== undefined;
                            return (
                              <TableRow key={idx} sx={{
                                '&:hover': { bgcolor: isManual ? '#F0FFF4' : '#FFFBEB' },
                                borderLeft: `3px solid ${isManual ? PALETTE.teal : PALETTE.green}`,
                              }}>
                                <TableCell sx={{ fontSize: 12, color: PALETTE.textMuted, py: 1, px: 1.5, whiteSpace: 'nowrap' }}>
                                  #{c.row}
                                </TableCell>
                                <TableCell sx={{ fontSize: 12, fontFamily: 'monospace', color: PALETTE.navy, py: 1, px: 1.5, whiteSpace: 'nowrap' }}>
                                  {c.patient_id ?? '—'}
                                </TableCell>
                                <TableCell sx={{ py: 1, px: 1.5, whiteSpace: 'nowrap' }}>
                                  <Chip label={c.column} size="small"
                                    sx={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600,
                                      bgcolor: `${PALETTE.navy}0F`, color: PALETTE.navy, height: 22 }} />
                                </TableCell>
                                <TableCell sx={{ py: 1, px: 1.5 }}>
                                  <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5,
                                    px: 1.2, py: 0.3, borderRadius: 1.5,
                                    bgcolor: PALETTE.redBg, color: PALETTE.red,
                                    fontSize: 12, fontWeight: 600, fontFamily: 'monospace',
                                    textDecoration: 'line-through' }}>
                                    {c.old_value === '' || c.old_value === null ? <em style={{opacity:.6}}>vide</em> : String(c.old_value)}
                                  </Box>
                                </TableCell>

                                {/* ── Editable corrected value ── */}
                                <TableCell sx={{ py: 0.5, px: 1.5, minWidth: 140 }}>
                                  {isEditing ? (
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <InputBase
                                        autoFocus
                                        value={editingValue}
                                        onChange={e => setEditingValue(e.target.value)}
                                        onKeyDown={e => {
                                          if (e.key === 'Enter') commitEdit();
                                          if (e.key === 'Escape') cancelEdit();
                                        }}
                                        sx={{
                                          px: 1, py: 0.3, borderRadius: 1.5, border: `2px solid ${PALETTE.teal}`,
                                          bgcolor: 'white', fontSize: 12, fontFamily: 'monospace', fontWeight: 700,
                                          color: PALETTE.navy, minWidth: 80, maxWidth: 140,
                                        }}
                                      />
                                      <Tooltip title="Confirmer (Entrée)">
                                        <IconButton size="small" onClick={commitEdit} disabled={savingOverride}
                                          sx={{ color: PALETTE.green, p: 0.4 }}>
                                          {savingOverride
                                            ? <CircularProgress size={12} />
                                            : <svg width="14" height="14" viewBox="0 0 16 16"><path d="M3 8l3 3 7-7" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none"/></svg>
                                          }
                                        </IconButton>
                                      </Tooltip>
                                      <Tooltip title="Annuler (Échap)">
                                        <IconButton size="small" onClick={cancelEdit}
                                          sx={{ color: PALETTE.red, p: 0.4 }}>
                                          <svg width="12" height="12" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" fill="none"/></svg>
                                        </IconButton>
                                      </Tooltip>
                                    </Box>
                                  ) : (
                                    <Tooltip title="Cliquer pour modifier cette valeur" placement="top">
                                      <Box
                                        onClick={() => startEdit(c.row, c.column, c.new_value)}
                                        sx={{
                                          display: 'inline-flex', alignItems: 'center', gap: 0.8,
                                          px: 1.2, py: 0.3, borderRadius: 1.5, cursor: 'pointer',
                                          bgcolor: isManual ? '#DCFCE7' : '#FFF2CC',
                                          color: isManual ? '#166534' : '#B45309',
                                          border: `1px dashed ${isManual ? PALETTE.green : '#D4A017'}`,
                                          fontSize: 12, fontWeight: 700, fontFamily: 'monospace',
                                          '&:hover': { opacity: 0.8, border: `1px solid ${PALETTE.teal}` },
                                        }}>
                                        {c.new_value === '' || c.new_value === null
                                          ? <em style={{opacity:.6}}>supprimé</em>
                                          : String(c.new_value)
                                        }
                                        {isManual && (
                                          <Chip label="modifié" size="small"
                                            sx={{ height: 16, fontSize: 9, fontWeight: 700, ml: 0.5,
                                              bgcolor: PALETTE.teal, color: 'white' }} />
                                        )}
                                        <svg width="10" height="10" viewBox="0 0 16 16" style={{opacity:.5}}>
                                          <path d="M11 2l3 3-9 9H2v-3L11 2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
                                        </svg>
                                      </Box>
                                    </Tooltip>
                                  )}
                                </TableCell>

                                <TableCell sx={{ py: 1, px: 1.5 }}>
                                  <Box sx={{ display: 'inline-flex', px: 1.2, py: 0.3, borderRadius: 10,
                                    bgcolor: `${PALETTE.navy}10`, color: PALETTE.navy, fontSize: 10, fontWeight: 600, whiteSpace: 'nowrap' }}>
                                    {c.type || 'correction'}
                                  </Box>
                                </TableCell>
                                <TableCell sx={{ fontSize: 11, color: PALETTE.textMuted, maxWidth: 300, py: 1, px: 1.5 }}>
                                  {c.justification || '—'}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </Box>
                  )
                )}

                {/* Tab 1: Flagged columns (no auto-correction) */}
                {corrTableTab === 1 && (
                  cellFlagged.length === 0 ? (
                    <Box sx={{ p: 5, textAlign: 'center' }}>
                      <Typography sx={{ fontWeight: 700, color: PALETTE.navy }}>Aucune colonne suspecte sans correction</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ overflowX: 'auto' }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow sx={{ bgcolor: PALETTE.bgAlt }}>
                            {['Colonne', 'Sévérité', 'Type d\'anomalie', 'Description du problème'].map(h => (
                              <TableCell key={h} sx={{ fontWeight: 700, fontSize: 11, color: PALETTE.textMuted,
                                textTransform: 'uppercase', letterSpacing: 0.4, borderBottom: `2px solid ${PALETTE.border}`,
                                whiteSpace: 'nowrap', py: 1.2, px: 1.5 }}>
                                {h}
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {cellFlagged.map((f, idx) => (
                            <TableRow key={idx} sx={{
                              '&:hover': { bgcolor: PALETTE.bgAlt },
                              borderLeft: `3px solid ${severityColor(f.severity)}`,
                            }}>
                              <TableCell sx={{ py: 1, px: 1.5 }}>
                                <Chip label={f.column} size="small"
                                  sx={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600,
                                    bgcolor: `${PALETTE.navy}0F`, color: PALETTE.navy, height: 22 }} />
                              </TableCell>
                              <TableCell sx={{ py: 1, px: 1.5 }}>
                                <Box sx={{ display: 'inline-flex', px: 1.2, py: 0.3, borderRadius: 10,
                                  bgcolor: severityBg(f.severity), color: severityColor(f.severity),
                                  fontSize: 11, fontWeight: 700 }}>
                                  {severityLabel(f.severity)}
                                </Box>
                              </TableCell>
                              <TableCell sx={{ py: 1, px: 1.5 }}>
                                <Box sx={{ display: 'inline-flex', px: 1.2, py: 0.3, borderRadius: 10,
                                  bgcolor: `${PALETTE.navy}10`, color: PALETTE.navy, fontSize: 10, fontWeight: 600 }}>
                                  {f.type || 'anomalie'}
                                </Box>
                              </TableCell>
                              <TableCell sx={{ fontSize: 12, color: PALETTE.textMuted, maxWidth: 400, py: 1, px: 1.5 }}>
                                {f.justification || '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </Box>
                  )
                )}
              </Paper>

              {/* No anomalies at all */}
              {cellCorrs.length === 0 && cellFlagged.length === 0 && tableRows.length === 0 && (
                <Paper elevation={0} sx={{ borderRadius: 4, border: `1px solid ${PALETTE.green}44`, p: 4, textAlign: 'center' }}>
                  <Box sx={{ color: PALETTE.green, mb: 1 }}>
                    <svg width="40" height="40" viewBox="0 0 40 40">
                      <circle cx="20" cy="20" r="18" fill={`${PALETTE.green}20`} />
                      <path d="M12 20l5 5 11-11" stroke={PALETTE.green} strokeWidth="2.5" strokeLinecap="round" />
                    </svg>
                  </Box>
                  <Typography sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 16 }}>Aucune anomalie détectée</Typography>
                  <Typography sx={{ color: PALETTE.textMuted, mt: 0.5 }}>Ce dataset est propre et conforme aux normes médicales.</Typography>
                </Paper>
              )}
            </Box>
          );
        })()}
      </Box>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </Box>
  );
}
