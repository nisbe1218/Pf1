import React, { useEffect, useRef, useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  List,
  ListItem,
  Grid,
  Chip,
  Alert,
  Stack,
} from '@mui/material';
import api from '../../services/api/axios';

export default function Preprocessing() {
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState('');
  const [loading, setLoading] = useState(false);
  const [session, setSession] = useState(null);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState(null);  // 'pending', 'completed', 'error'
  const [statusMessage, setStatusMessage] = useState('');
  const pollIntervalRef = useRef(null);
  const [ollamaStatus, setOllamaStatus] = useState({
    checking: true,
    connected: false,
    message: 'Vérification de la connexion Ollama...',
    base_url: null,
    configured_model: null,
    errors: [],
  });
  const [datasetProfile, setDatasetProfile] = useState(null);
  const [originalPreviewRows, setOriginalPreviewRows] = useState([]);
  const [correctedPreviewRows, setCorrectedPreviewRows] = useState([]);
  const [pipelineInfo, setPipelineInfo] = useState(null);
  const [routeInfo, setRouteInfo] = useState(null);

  const isAllowedFileType = (selectedFile) => {
    if (!selectedFile) return false;
    const fileName = String(selectedFile.name || '').toLowerCase();
    return fileName.endsWith('.csv') || fileName.endsWith('.xlsx');
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files && e.target.files[0];
    setReport(null);
    setSession(null);
    setStatus(null);
    setStatusMessage('');
    setDatasetProfile(null);
    setOriginalPreviewRows([]);
    setCorrectedPreviewRows([]);
    setPipelineInfo(null);
    setRouteInfo(null);

    if (!selectedFile) {
      setFile(null);
      setFileError('');
      return;
    }

    if (!isAllowedFileType(selectedFile)) {
      setFile(null);
      setFileError('Format invalide. Choisissez un fichier .csv ou .xlsx.');
      return;
    }

    setFile(selectedFile);
    setFileError('');
  };

  // Poll for job status when session ID is set and status is pending
  useEffect(() => {
    if (!session || status !== 'pending') {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    const interval = setInterval(async () => {
      try {
        const resp = await api.get(`patients/preprocess/${session}/status/`);
        const data = resp.data || {};
        const jobStatus = data.status || 'pending';
        setStatusMessage(data.progress_message || data.message || 'Traitement en cours...');

        if (jobStatus === 'completed') {
          setStatus('completed');
          setReport(data.report || null);
          setDatasetProfile(data.dataset_profile || data.report?.dataset_profile || null);
          setOriginalPreviewRows(data.original_preview_rows || []);
          setCorrectedPreviewRows(data.corrected_preview_rows || data.preview_rows || []);
          setPipelineInfo(data.report?.pipeline || null);
          setRouteInfo(data.report?.route || data.report?.llm_analysis?.route || null);
          clearInterval(interval);
          pollIntervalRef.current = null;
          setLoading(false);
        } else if (jobStatus === 'error') {
          setStatus('error');
          setStatusMessage(data.error || 'Erreur inconnue');
          clearInterval(interval);
          pollIntervalRef.current = null;
          setLoading(false);
        }
      } catch (err) {
        console.error('Erreur lors du polling:', err);
        setStatusMessage('Erreur lors de la vérification du statut');
      }
    }, 2000);  // Poll every 2 seconds

    pollIntervalRef.current = interval;
    return () => {
      clearInterval(interval);
      if (pollIntervalRef.current === interval) {
        pollIntervalRef.current = null;
      }
    };
  }, [session, status]);

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    setStatus('pending');
    setStatusMessage('Initialisation du traitement...');
    try {
      const form = new FormData();
      form.append('file', file);
      const resp = await api.post('patients/preprocess/analyze/', form);
      const data = resp.data || {};
      
      // Backend returns 202 ACCEPTED with preprocess_id
      const sessionId = data.preprocess_id || data.id || null;
      if (sessionId) {
        setSession(sessionId);
        setStatus('pending');
        setStatusMessage(data.message || 'Analyse en cours...');
        setPipelineInfo(null);
        setRouteInfo(null);
        // Polling will start automatically via useEffect
      } else {
        setStatus('error');
        setStatusMessage('ID de session non reçu');
        setLoading(false);
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
      setStatusMessage(err?.response?.data?.error || 'Erreur lors de l\'analyse');
      setLoading(false);
    }
  };

  const checkOllamaStatus = async () => {
    setOllamaStatus((prev) => ({ ...prev, checking: true }));
    try {
      const resp = await api.get('patients/preprocess/health/');
      const data = resp.data || {};
      setOllamaStatus({
        checking: false,
        connected: Boolean(data.connected),
        message: data.message || 'Ollama connecté.',
        base_url: data.base_url || null,
        configured_model: data.configured_model || null,
        errors: Array.isArray(data.errors) ? data.errors : [],
      });
    } catch (err) {
      const data = err?.response?.data || {};
      setOllamaStatus({
        checking: false,
        connected: false,
        message: data.message || 'Ollama indisponible.',
        base_url: data.base_url || null,
        configured_model: data.configured_model || null,
        errors: Array.isArray(data.errors) ? data.errors : [],
      });
    }
  };

  useEffect(() => {
    checkOllamaStatus();
  }, []);

  const ollamaChipColor = ollamaStatus.checking
    ? 'warning'
    : ollamaStatus.connected
      ? 'success'
      : 'error';
  const ollamaChipLabel = ollamaStatus.checking
    ? 'Ollama: vérification...'
    : ollamaStatus.connected
      ? 'Ollama: connecté'
      : 'Ollama: indisponible';

  const pipelineStages = [
    { key: 'upload', label: 'Upload & lecture' },
    { key: 'profile', label: 'Profilage Pandas' },
    { key: 'chunking', label: 'Chunking intelligent' },
    { key: 'retrieval', label: 'Retrieval contextuel' },
    { key: 'llm1', label: 'LLM diagnostic' },
    { key: 'llm2', label: 'Plan de correction' },
    { key: 'merge', label: 'Fusion & rapport' },
  ];

  const currentStageLabel = (() => {
    const text = String(statusMessage || '').toLowerCase();
    if (text.includes('lecture')) return 'upload';
    if (text.includes('profilage')) return 'profile';
    if (text.includes('chunk')) return 'chunking';
    if (text.includes('retrieval') || text.includes('contexte')) return 'retrieval';
    if (text.includes('passe 1')) return 'llm1';
    if (text.includes('passe 2')) return 'llm2';
    if (text.includes('fusion') || text.includes('rapport') || text.includes('correction')) return 'merge';
    return null;
  })();

  const visibleIssues = Array.isArray(report?.issues)
    ? report.issues.filter((issue) => {
        if (typeof issue?.ui_visible === 'boolean') {
          return issue.ui_visible === true;
        }
        return !issue?.internal_trigger;
      })
    : [];

  const reportIssues = Array.isArray(report?.all_issues)
    ? report.all_issues
    : Array.isArray(report?.issues)
      ? report.issues
      : [];

  const appliedCorrections = Array.isArray(report?.applied_corrections)
    ? report.applied_corrections
    : [];

  const correctionPlan = report?.correction_plan && typeof report.correction_plan === 'object'
    ? report.correction_plan
    : {};

  const datasetColumnsProfile = Array.isArray(datasetProfile?.columns_profile)
    ? datasetProfile.columns_profile
    : [];

  const plannedColumnStatus = {};
  const registerPlannedStatus = (columnName, label) => {
    if (!columnName) return;
    const key = String(columnName);
    if (!plannedColumnStatus[key]) plannedColumnStatus[key] = [];
    if (!plannedColumnStatus[key].includes(label)) plannedColumnStatus[key].push(label);
  };

  Object.entries(correctionPlan?.fill_missing || {}).forEach(([columnName, spec]) => {
    registerPlannedStatus(columnName, `fill_missing${spec?.strategy ? `:${spec.strategy}` : ''}`);
  });
  Object.entries(correctionPlan?.type_casts || {}).forEach(([columnName, targetType]) => {
    registerPlannedStatus(columnName, `type_cast:${targetType}`);
  });
  (correctionPlan?.parse_dates || []).forEach((columnName) => registerPlannedStatus(columnName, 'parse_dates'));
  (correctionPlan?.trim_whitespace_columns || []).forEach((columnName) => registerPlannedStatus(columnName, 'trim_whitespace'));
  Object.entries(correctionPlan?.value_mappings || {}).forEach(([columnName]) => {
    registerPlannedStatus(columnName, 'value_mappings');
  });
  Object.entries(correctionPlan?.rename_columns || {}).forEach(([fromColumn, toColumn]) => {
    registerPlannedStatus(fromColumn, `rename_to:${toColumn}`);
  });
  Object.entries(correctionPlan?.default_values || {}).forEach(([columnName]) => {
    registerPlannedStatus(columnName, 'default_values');
  });

  const appliedColumnStatus = {};
  const registerAppliedStatus = (columnName, label) => {
    if (!columnName) return;
    const key = String(columnName);
    if (!appliedColumnStatus[key]) appliedColumnStatus[key] = [];
    if (!appliedColumnStatus[key].includes(label)) appliedColumnStatus[key].push(label);
  };

  appliedCorrections.forEach((item) => {
    const action = String(item?.action || 'correction');
    const details = item?.details || {};
    const columns = Array.isArray(details.columns) ? details.columns : [];
    if (action === 'rename_columns') {
      columns.forEach((column) => {
        if (column?.from) registerAppliedStatus(column.from, `rename_to:${column.to || ''}`.replace(/:$/, ''));
      });
      return;
    }
    if (action === 'parse_dates' || action === 'trim_whitespace' || action === 'value_mappings' || action === 'fill_missing' || action === 'type_casts') {
      columns.forEach((column) => {
        if (column?.column) registerAppliedStatus(column.column, action);
      });
      return;
    }
    columns.forEach((column) => {
      if (typeof column === 'string') registerAppliedStatus(column, action);
      else if (column?.column || column?.name) registerAppliedStatus(column.column || column.name, action);
    });
  });

  const columnRows = datasetColumnsProfile.map((column) => {
    const columnName = String(column?.column || column?.name || '');
    const planned = plannedColumnStatus[columnName] || [];
    const applied = appliedColumnStatus[columnName] || [];
    const missingPct = column?.missing_pct;
    const dtype = column?.dtype || column?.type || '-';
    let statusLabel = 'Aucune modification';
    let statusColor = 'default';

    if (applied.length > 0) {
      statusLabel = planned.length > 0 ? 'Corrigée' : 'Corrigée (hors plan)';
      statusColor = 'success';
    } else if (planned.length > 0) {
      statusLabel = 'Proposée';
      statusColor = 'warning';
    }

    return {
      columnName,
      dtype,
      missingPct,
      examples: Array.isArray(column?.sample_values) ? column.sample_values.join(' | ') : '',
      planned: planned.join(', '),
      applied: applied.join(', '),
      statusLabel,
      statusColor,
    };
  });

  const planHasConcreteActions = Object.values(correctionPlan).some((value) => {
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === 'object') return Object.keys(value).length > 0;
    return Boolean(value);
  });

  const formatCorrectionDetail = (item) => {
    const details = item?.details || {};
    const columns = Array.isArray(details.columns) ? details.columns : [];

    if (item?.action === 'rename_columns') {
      return columns.map((column) => `${column.from} -> ${column.to}`).join(', ');
    }

    if (item?.action === 'drop_columns_skipped') {
      return details.message || `Colonnes ignorees: ${columns.join(', ')}`;
    }

    if (columns.length > 0) {
      return columns.map((column) => {
        if (typeof column === 'string') return column;
        const name = column.column || column.name || '';
        const parts = [name].filter(Boolean);
        if (column.target_type) parts.push(`type: ${column.target_type}`);
        if (column.cells_changed !== undefined) parts.push(`${column.cells_changed} cellule(s)`);
        if (column.mapping) parts.push(`mapping: ${JSON.stringify(column.mapping)}`);
        if (column.strategy) parts.push(`strategie: ${JSON.stringify(column.strategy)}`);
        if (column.default_value !== undefined) parts.push(`defaut: ${JSON.stringify(column.default_value)}`);
        return parts.join(' - ');
      }).join('; ');
    }

    if (item?.reason) return item.reason;
    return JSON.stringify(details || {});
  };

  const correctionDiffs = [];
  const rowCount = Math.min(originalPreviewRows.length, correctedPreviewRows.length);
  for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
    const originalRow = originalPreviewRows[rowIndex] || {};
    const correctedRow = correctedPreviewRows[rowIndex] || {};
    const fields = new Set([...Object.keys(originalRow), ...Object.keys(correctedRow)]);
    fields.forEach((field) => {
      const before = originalRow[field];
      const after = correctedRow[field];
      if (String(before ?? '') !== String(after ?? '')) {
        correctionDiffs.push({
          row: rowIndex + 1,
          field,
          before: before ?? '',
          after: after ?? '',
        });
      }
    });
  }

  const handleExport = async () => {
    if (!session) return;
    try {
      const resp = await api.get(`patients/preprocess/${session}/export/`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const a = document.createElement('a');
      a.href = url;
      a.setAttribute('download', `preprocess_${session}.xlsx`);
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      console.error(err);
      alert('Erreur export');
    }
  };

  const handleIntegrate = async () => {
    if (!session) return;
    if (!window.confirm('Intégrer les lignes corrigées dans la plateforme ?')) return;
    setLoading(true);
    try {
      await api.post(`patients/preprocess/${session}/integrate/`, {});
      alert('Import intégré. Rafraîchissez la page patients si nécessaire.');
    } catch (err) {
      console.error(err);
      alert('Erreur integration');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6">Prétraitement </Typography>
        <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: 'center', flexWrap: 'wrap' }}>
          <Chip color={ollamaChipColor} label={ollamaChipLabel} />
          <Button variant="text" size="small" onClick={checkOllamaStatus} disabled={loading || ollamaStatus.checking}>
            Actualiser l'état Ollama
          </Button>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {ollamaStatus.message}
          {ollamaStatus.base_url ? ` URL: ${ollamaStatus.base_url}` : ''}
          {ollamaStatus.configured_model ? ` • Modèle: ${ollamaStatus.configured_model}` : ''}
        </Typography>
        {!ollamaStatus.checking && !ollamaStatus.connected && ollamaStatus.errors.length > 0 && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {ollamaStatus.errors[0]}
          </Alert>
        )}
        <Box sx={{ mt: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
          <input type="file" accept=".csv,.xlsx" onChange={handleFileChange} />
          <Button variant="contained" onClick={handleAnalyze} disabled={!file || loading}>Analyser</Button>
          <Button variant="outlined" onClick={handleExport} disabled={!session || loading}>Exporter corrigé</Button>
          <Button color="secondary" variant="contained" onClick={handleIntegrate} disabled={!session || loading}>Intégrer</Button>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Formats acceptés: CSV ou XLSX, avec XLSX recommandé dans la plupart des cas.
        </Typography>

        {fileError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {fileError}
          </Alert>
        )}

        {loading && status === 'pending' && (
          <Box sx={{ mt: 2 }}>
            <Alert severity="info" sx={{ mb: 2 }}>
              <Stack spacing={1}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Analyse en cours...
                </Typography>
                <Typography variant="body2">{statusMessage}</Typography>
                <LinearProgress />
              </Stack>
            </Alert>
          </Box>
        )}

        {(loading || report?.pipeline || currentStageLabel) && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle1">Pipeline d'analyse</Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
              {pipelineStages.map((stage) => {
                const isDone = ['profile', 'chunking', 'retrieval', 'llm1', 'llm2', 'merge'].indexOf(stage.key) <
                  ['profile', 'chunking', 'retrieval', 'llm1', 'llm2', 'merge'].indexOf(currentStageLabel);
                const isActive = currentStageLabel === stage.key;
                return (
                  <Chip
                    key={stage.key}
                    label={stage.label}
                    color={isActive ? 'primary' : isDone ? 'success' : 'default'}
                    variant={isActive || isDone ? 'filled' : 'outlined'}
                    size="small"
                  />
                );
              })}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {pipelineInfo?.stage ? `Étape finale: ${pipelineInfo.stage}` : statusMessage}
            </Typography>
            {pipelineInfo?.chunks_count ? (
              <Typography variant="body2" color="text.secondary">
                Chunks analysés: {pipelineInfo.chunks_count}
                {pipelineInfo?.retrieved_chunks_count ? ` • Chunks récupérés: ${pipelineInfo.retrieved_chunks_count}` : ''}
              </Typography>
            ) : null}
            {routeInfo?.mode ? (
              <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
                <Chip size="small" label={`Route: ${routeInfo.mode}`} color="secondary" variant="outlined" />
                {routeInfo.label ? <Chip size="small" label={routeInfo.label} variant="outlined" /> : null}
                {routeInfo.primary_model ? <Chip size="small" label={`Modèle: ${routeInfo.primary_model}`} variant="outlined" /> : null}
              </Stack>
            ) : null}
          </Box>
        )}

        {status === 'error' && (
          <Alert severity="error" sx={{ mt: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              Erreur d'analyse
            </Typography>
            <Typography variant="body2">{statusMessage}</Typography>
          </Alert>
        )}

        {loading && status !== 'pending' && <LinearProgress sx={{ mt: 2 }} />}

        {report?.summary && (
          <Grid container spacing={2} sx={{ mt: 2 }}>
            <Grid item xs={12}>
              <Alert severity="success">
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  ✓ Analyse terminée avec succès
                </Typography>
              </Alert>
            </Grid>
            <Grid item xs={12} md={3}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="overline" color="text.secondary">Score qualité</Typography>
                <Typography variant="h4">{report.summary.quality_score ?? '-'}</Typography>
                <Typography variant="body2" color="text.secondary">Évaluation LLM du dataset importé</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} md={3}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="overline" color="text.secondary">Lignes</Typography>
                <Typography variant="h4">{report.summary.rows ?? '-'}</Typography>
                <Typography variant="body2" color="text.secondary">{report.summary.corrected_rows ?? report.summary.rows ?? '-'} après corrections proposées</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} md={3}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="overline" color="text.secondary">Colonnes</Typography>
                <Typography variant="h4">{report.summary.columns ?? '-'}</Typography>
                <Typography variant="body2" color="text.secondary">Structure détectée par Pandas</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} md={3}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="overline" color="text.secondary">Corrections</Typography>
                <Typography variant="h4">{report.summary.applied_corrections_count ?? 0}</Typography>
                <Typography variant="body2" color="text.secondary">Règles exécutées sur la proposition corrigée</Typography>
              </Paper>
            </Grid>
          </Grid>
        )}

        {report?.summary && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">Résumé du rapport</Typography>
            <Typography variant="body2" sx={{ mt: 0.5 }}>{report.llm_analysis?.summary || 'Aucun résumé renvoyé par le modèle.'}</Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
              {(report.llm_analysis?.limitations || []).map((item, index) => (
                <Chip key={`${item}-${index}`} label={item} size="small" variant="outlined" />
              ))}
            </Stack>
          </Box>
        )}

        {visibleIssues.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">Problèmes détectés</Typography>
            <List dense>
              {visibleIssues.map((issue, index) => (
                <ListItem key={index} sx={{ display: 'block' }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {`${issue.severity || 'info'} • ${issue.category || 'general'}${issue.column ? ` • ${issue.column}` : ''}`}
                  </Typography>
                  <Typography variant="body2">{issue.explanation || issue.message || ''}</Typography>
                  {Array.isArray(issue.rows) && issue.rows.length > 0 && (
                    <Typography variant="caption" color="text.secondary">Lignes: {issue.rows.join(', ')}</Typography>
                  )}
                </ListItem>
              ))}
            </List>
          </Box>
        )}

        {Array.isArray(report?.recommendations) && report.recommendations.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">Recommandations</Typography>
            <List dense>
              {report.recommendations.map((item, index) => (
                <ListItem key={index}>{item}</ListItem>
              ))}
            </List>
          </Box>
        )}

        {datasetProfile?.columns_profile && datasetProfile.columns_profile.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">Profil de structure extrait par Pandas</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {datasetProfile.rows ?? '-'} lignes • {datasetProfile.columns ?? '-'} colonnes
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Colonne</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Manquants</TableCell>
                  <TableCell>Exemples</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {datasetProfile.columns_profile.map((column) => (
                  <TableRow key={column.column}>
                    <TableCell>{column.column}</TableCell>
                    <TableCell>{column.dtype}</TableCell>
                    <TableCell>{column.missing_pct}%</TableCell>
                    <TableCell>{Array.isArray(column.sample_values) ? column.sample_values.join(' | ') : ''}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}

        {originalPreviewRows && originalPreviewRows.length > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="subtitle1">Aperçu brut extrait</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {Object.keys(originalPreviewRows[0]).map((k) => (
                    <TableCell key={k}>{k}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {originalPreviewRows.map((row, idx) => (
                  <TableRow key={idx}>
                    {Object.keys(row).map((k) => (
                      <TableCell key={k}>{String(row[k] ?? '')}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}

        {report && (
          <Box sx={{ mt: 3 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>Rapport de correction LLM</Typography>
            <Stack spacing={2}>
              <Alert severity={report?.summary ? 'success' : 'info'}>
                {report?.summary
                  ? (appliedCorrections.length > 0 || correctionDiffs.length > 0
                    ? 'Analyse terminée. Le rapport ci-dessous synthétise les corrections appliquées par le backend à partir du plan du LLM.'
                    : "Analyse terminée. Le backend n'a appliqué aucune correction sur cette session : le dataset est resté inchangé.")
                  : 'Aucun rapport disponible.'}
              </Alert>

              {/* Erreurs détectées */}
              {reportIssues.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                    Erreurs détectées ({reportIssues.length})
                  </Typography>
                  <Stack spacing={1}>
                    {reportIssues.map((issue, index) => {
                      const sev = String(issue?.severity || 'info').toLowerCase();
                      const sevColor = sev === 'critical' ? '#d32f2f' : sev === 'warning' ? '#ed6c02' : '#0288d1';
                      return (
                        <Box key={index} sx={{ borderLeft: `4px solid ${sevColor}`, pl: 1.5, py: 0.75, bgcolor: 'grey.50', borderRadius: 1 }}>
                          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" sx={{ mb: 0.4 }}>
                            <Chip label={sev} size="small" sx={{ bgcolor: sevColor, color: '#fff', fontWeight: 700, height: 20, fontSize: 11 }} />
                            {issue?.category && <Chip label={issue.category} size="small" variant="outlined" sx={{ height: 20, fontSize: 11 }} />}
                            {issue?.column && (
                              <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: 'monospace' }}>{issue.column}</Typography>
                            )}
                          </Stack>
                          <Typography variant="body2" color="text.secondary">{issue?.explanation || issue?.message || ''}</Typography>
                        </Box>
                      );
                    })}
                  </Stack>
                </Box>
              )}

              {/* Corrections appliquées — une card par action */}
              {appliedCorrections.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>
                    Corrections appliquées ({appliedCorrections.length} action{appliedCorrections.length > 1 ? 's' : ''})
                  </Typography>
                  <Stack spacing={1}>
                    {appliedCorrections.map((item, index) => {
                      const action = String(item?.action || 'action');
                      const details = item?.details || {};
                      const cols = Array.isArray(details.columns) ? details.columns : [];
                      const count = item?.count ?? item?.rows ?? null;
                      const cellsChanged = item?.cells_changed ?? null;
                      return (
                        <Paper key={index} variant="outlined" sx={{ p: 1.5 }}>
                          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: cols.length ? 0.75 : 0 }}>
                            <Chip label={action} size="small" color="primary" sx={{ fontWeight: 700 }} />
                            {count !== null && (
                              <Typography variant="caption" color="text.secondary">{count} colonne(s)</Typography>
                            )}
                            {cellsChanged !== null && (
                              <Typography variant="caption" color="text.secondary">{cellsChanged} cellule(s) modifiée(s)</Typography>
                            )}
                          </Stack>
                          {action === 'rename_columns' && cols.length > 0 && (
                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                              {cols.map((c, i) => (
                                <Chip key={i} label={`${c.from} → ${c.to}`} size="small" variant="outlined" />
                              ))}
                            </Stack>
                          )}
                          {action !== 'rename_columns' && cols.length > 0 && (
                            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                              {cols.map((c, i) => {
                                const colName = typeof c === 'string' ? c : (c.column || c.name || '');
                                const extra = c.target_type
                                  ? ` → ${c.target_type}`
                                  : c.cells_changed !== undefined
                                    ? ` (${c.cells_changed})`
                                    : '';
                                return <Chip key={i} label={`${colName}${extra}`} size="small" variant="outlined" />;
                              })}
                            </Stack>
                          )}
                        </Paper>
                      );
                    })}
                  </Stack>
                </Box>
              )}

              {appliedCorrections.length === 0 && correctionDiffs.length === 0 && (
                <Alert severity="info">Aucune correction n'a été appliquée par le backend pour cette session.</Alert>
              )}
              {appliedCorrections.length === 0 && !planHasConcreteActions && (
                <Alert severity="warning">
                  Le LLM a renvoyé un plan vide. Le backend ne peut appliquer que les actions réellement présentes dans ce plan.
                </Alert>
              )}

              {/* Plan proposé par le LLM — sections structurées */}
              {planHasConcreteActions && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 700 }}>Plan proposé par le LLM</Typography>
                  <Stack spacing={1}>
                    {Object.keys(correctionPlan.fill_missing || {}).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Valeurs manquantes (fill_missing)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {Object.entries(correctionPlan.fill_missing).map(([col, spec]) => (
                            <Chip key={col} label={`${col} — ${spec?.strategy || spec || '?'}`} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                    {Object.keys(correctionPlan.type_casts || {}).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Conversions de type (type_casts)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {Object.entries(correctionPlan.type_casts).map(([col, type]) => (
                            <Chip key={col} label={`${col} → ${type}`} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                    {(correctionPlan.parse_dates || []).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Colonnes date (parse_dates)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {correctionPlan.parse_dates.map((col) => (
                            <Chip key={col} label={col} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                    {(correctionPlan.trim_whitespace_columns || []).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Nettoyage espaces (trim_whitespace)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {correctionPlan.trim_whitespace_columns.map((col) => (
                            <Chip key={col} label={col} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                    {Object.keys(correctionPlan.value_mappings || {}).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Mappings de valeurs (value_mappings)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {Object.entries(correctionPlan.value_mappings).map(([col]) => (
                            <Chip key={col} label={col} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                    {Object.keys(correctionPlan.rename_columns || {}).length > 0 && (
                      <Paper variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
                          Renommage (rename_columns)
                        </Typography>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                          {Object.entries(correctionPlan.rename_columns).map(([from, to]) => (
                            <Chip key={from} label={`${from} → ${to}`} size="small" variant="outlined" />
                          ))}
                        </Stack>
                      </Paper>
                    )}
                  </Stack>
                </Box>
              )}

              {/* Diff aperçu brut vs corrigé */}
              {correctionDiffs.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Changements détectés entre la version brute et la version corrigée</Typography>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Ligne</TableCell>
                        <TableCell>Champ</TableCell>
                        <TableCell>Avant</TableCell>
                        <TableCell>Après</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {correctionDiffs.map((item, index) => (
                        <TableRow key={`${item.row}-${item.field}-${index}`}>
                          <TableCell>{item.row}</TableCell>
                          <TableCell>{item.field}</TableCell>
                          <TableCell>{String(item.before)}</TableCell>
                          <TableCell>{String(item.after)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}

              {Array.isArray(report?.recommendations) && report.recommendations.length > 0 && (
                <Box>
                  <Typography variant="subtitle2">Recommandations du modèle</Typography>
                  <List dense>
                    {report.recommendations.map((item, index) => (
                      <ListItem key={`${item}-${index}`} sx={{ px: 0 }}>{item}</ListItem>
                    ))}
                  </List>
                </Box>
              )}

              {correctedPreviewRows && correctedPreviewRows.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Aperçu de la version corrigée</Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
                    <Button size="small" variant="outlined" onClick={handleExport} disabled={!session || loading}>Télécharger corrigé</Button>
                  </Box>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        {Object.keys(correctedPreviewRows[0]).map((k) => (
                          <TableCell key={k}>{k}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {correctedPreviewRows.slice(0, 10).map((row, idx) => (
                        <TableRow key={idx}>
                          {Object.keys(row).map((k) => (
                            <TableCell key={k}>{String(row[k] ?? '')}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Box>
              )}

              {columnRows.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Vue complète des colonnes</Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {columnRows.length} colonnes détectées. Le statut indique si une correction a été proposée par le LLM ou appliquée par le backend.
                  </Typography>
                  <Box sx={{ overflowX: 'auto' }}>
                    <Table size="small" stickyHeader sx={{ minWidth: 1100 }}>
                      <TableHead>
                        <TableRow>
                          <TableCell>Colonne</TableCell>
                          <TableCell>Type</TableCell>
                          <TableCell>Manquants</TableCell>
                          <TableCell>Plan LLM</TableCell>
                          <TableCell>Appliqué</TableCell>
                          <TableCell>Statut</TableCell>
                          <TableCell>Exemples</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {columnRows.map((row) => (
                          <TableRow key={row.columnName} hover>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{row.columnName}</TableCell>
                            <TableCell>{row.dtype}</TableCell>
                            <TableCell>{row.missingPct ?? '-'}</TableCell>
                            <TableCell sx={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{row.planned || '-'}</TableCell>
                            <TableCell sx={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{row.applied || '-'}</TableCell>
                            <TableCell>
                              <Chip size="small" label={row.statusLabel} color={row.statusColor} variant={row.statusColor === 'default' ? 'outlined' : 'filled'} />
                            </TableCell>
                            <TableCell sx={{ whiteSpace: 'normal', wordBreak: 'break-word' }}>{row.examples || '-'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                </Box>
              )}
            </Stack>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
