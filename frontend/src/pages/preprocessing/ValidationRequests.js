import React, { useEffect, useState, useCallback } from 'react';
import {
  Box, Paper, Typography, Button, Chip, Stack, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow, Alert,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider,
  TextField, LinearProgress,
} from '@mui/material';
import api from '../../services/api/axios';
import AppSidebar from '../../components/common/AppSidebar';

const PALETTE = {
  navy: '#0A2B3E', navyLight: '#1A6B8A', teal: '#2C8C9E',
  rose: '#D47A8E', roseBg: '#F0D3DF',
  green: '#4A8B7C', greenBg: '#dcf7f2',
  orange: '#d18f47', orangeBg: '#fff1df',
  red: '#d64545', redBg: '#ffe3e4',
  bg: '#F5F9FC', card: '#FFFFFF', border: '#E2ECF0',
  textDark: '#1A2F3C', textMuted: '#6B8A9C',
};

const StatusChip = ({ status }) => {
  const map = {
    pending:  { label: 'En attente', bg: PALETTE.orangeBg, color: PALETTE.orange },
    approved: { label: 'Validé',     bg: PALETTE.greenBg,  color: PALETTE.green },
    rejected: { label: 'Rejeté',     bg: PALETTE.redBg,    color: PALETTE.red },
  };
  const s = map[status] || map.pending;
  return (
    <Chip label={s.label} size="small"
      sx={{ bgcolor: s.bg, color: s.color, fontWeight: 700, fontSize: 11, border: 'none' }} />
  );
};

const ACTION_LABELS = { add: 'Ajout', delete: 'Suppression' };
const ACTION_COLORS = {
  add:    { bg: `#e8f5e9`, color: '#388e3c' },
  delete: { bg: `#fce4ec`, color: '#c62828' },
};

export default function ValidationRequests() {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [selected, setSelected] = useState(null);
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [comment, setComment] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [actionResult, setActionResult] = useState(null);

  // ── Demandes colonnes dynamiques ──
  const [colRequests, setColRequests] = useState([]);
  const [colFilter, setColFilter] = useState('pending');
  const [colLoading, setColLoading] = useState(true);
  const [colComment, setColComment] = useState('');
  const [colActionLoading, setColActionLoading] = useState(false);
  const [colSelected, setColSelected] = useState(null);
  const [colActionResult, setColActionResult] = useState(null);
  const [pendingColCount, setPendingColCount] = useState(0);

  const loadColRequests = useCallback(async () => {
    setColLoading(true);
    try {
      const { data } = await api.get(`patients/dynamic-columns/requests/?status=${colFilter}`);
      setColRequests(data.results || []);
    } catch { setColRequests([]); }
    setColLoading(false);
  }, [colFilter]);

  useEffect(() => { loadColRequests(); }, [loadColRequests]);

  // Badge polling toutes les 30s
  useEffect(() => {
    const fetchCount = async () => {
      try {
        const { data } = await api.get('patients/dynamic-columns/requests/?count=1');
        setPendingColCount(data.pending || 0);
      } catch {}
    };
    fetchCount();
    const t = setInterval(fetchCount, 30000);
    return () => clearInterval(t);
  }, []);

  const handleColAction = async (action) => {
    if (!colSelected) return;
    setColActionLoading(true);
    try {
      await api.post(`patients/dynamic-columns/requests/${colSelected.id}/`, { action, comment: colComment });
      setColActionResult({ action });
      loadColRequests();
      const { data } = await api.get('patients/dynamic-columns/requests/?count=1');
      setPendingColCount(data.pending || 0);
    } catch (err) {
      setColActionResult({ error: err?.response?.data?.error || 'Erreur.' });
    }
    setColActionLoading(false);
  };

  const loadRequests = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`patients/preprocess/validations/?status=${filter}`);
      setRequests(data.results || []);
    } catch { setRequests([]); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { loadRequests(); }, [loadRequests]);

  const openDetail = async (req) => {
    setSelected(req);
    setPreview(null);
    setComment('');
    setActionResult(null);
    setPreviewLoading(true);
    try {
      const { data } = await api.get(`patients/preprocess/validations/${req.id}/`);
      setPreview(data);
    } catch { setPreview(null); }
    setPreviewLoading(false);
  };

  const handleAction = async (action) => {
    if (!selected) return;
    setActionLoading(true);
    try {
      const { data } = await api.post(`patients/preprocess/validations/${selected.id}/`, { action, comment });
      setActionResult({ action, data });
      loadRequests();
    } catch (err) {
      setActionResult({ error: err?.response?.data?.error || 'Erreur.' });
    }
    setActionLoading(false);
  };

  const colStyle = { fontSize: 12, color: PALETTE.textMuted, fontWeight: 600, py: 1.5, px: 2 };
  const cellStyle = { fontSize: 13, color: PALETTE.textDark, py: 1.5, px: 2, borderBottom: `1px solid ${PALETTE.border}` };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: PALETTE.bg }}>
      <AppSidebar />
      <Box sx={{ flex: 1, ml: { xs: 0, md: '88px' }, p: { xs: 2, md: 4 } }}>
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
          <Typography variant="h5" sx={{ fontWeight: 800, color: PALETTE.navy }}>
            Validations en attente
          </Typography>
          {pendingColCount > 0 && (
            <Chip
              label={`${pendingColCount} colonne${pendingColCount > 1 ? 's' : ''} en attente`}
              size="small"
              sx={{ bgcolor: PALETTE.orangeBg, color: PALETTE.orange, fontWeight: 700, fontSize: 11 }}
            />
          )}
        </Stack>
        <Typography variant="body2" sx={{ color: PALETTE.textMuted, mb: 3 }}>
          Données prétraitées soumises pour intégration — réservé au chef de service et à l'administrateur.
        </Typography>

        {/* Filter tabs */}
        <Stack direction="row" spacing={1} sx={{ mb: 3 }}>
          {['pending', 'approved', 'rejected', 'all'].map(f => (
            <Button key={f} size="small" variant={filter === f ? 'contained' : 'outlined'}
              onClick={() => setFilter(f)}
              sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 600, fontSize: 12,
                ...(filter === f ? { bgcolor: PALETTE.navy, '&:hover': { bgcolor: PALETTE.navyLight } } :
                  { borderColor: PALETTE.border, color: PALETTE.textMuted }) }}>
              {{ pending: 'En attente', approved: 'Validés', rejected: 'Rejetés', all: 'Tous' }[f]}
            </Button>
          ))}
        </Stack>

        <Paper elevation={0} sx={{ borderRadius: 3, border: `1px solid ${PALETTE.border}`, overflow: 'hidden' }}>
          {loading ? (
            <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress size={28} sx={{ color: PALETTE.teal }} /></Box>
          ) : requests.length === 0 ? (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography sx={{ color: PALETTE.textMuted, fontSize: 14 }}>Aucune demande de validation.</Typography>
            </Box>
          ) : (
            <Table>
              <TableHead sx={{ bgcolor: PALETTE.bg }}>
                <TableRow>
                  {['Fichier', 'Version', 'Soumis par', 'Date', 'Lignes', 'Score', 'Statut', ''].map(h => (
                    <TableCell key={h} sx={colStyle}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {requests.map(req => (
                  <TableRow key={req.id} hover sx={{ cursor: 'pointer' }} onClick={() => openDetail(req)}>
                    <TableCell sx={cellStyle}>{req.source_file_name || `session_${req.session_id?.slice(0,8)}`}</TableCell>
                    <TableCell sx={cellStyle}>
                      <Chip label={req.source === 'corrected' ? 'Corrigée' : 'Originale'} size="small"
                        sx={{ bgcolor: req.source === 'corrected' ? `${PALETTE.teal}15` : `${PALETTE.rose}15`,
                          color: req.source === 'corrected' ? PALETTE.teal : PALETTE.rose, fontWeight: 600, fontSize: 11 }} />
                    </TableCell>
                    <TableCell sx={cellStyle}>{req.submitted_by}</TableCell>
                    <TableCell sx={cellStyle}>{req.submitted_at ? new Date(req.submitted_at).toLocaleString('fr-FR') : '—'}</TableCell>
                    <TableCell sx={cellStyle}>{req.rows_count}</TableCell>
                    <TableCell sx={cellStyle}>
                      {req.quality_score != null ? (
                        <Chip label={`${req.quality_score}%`} size="small"
                          sx={{ bgcolor: req.quality_score >= 80 ? PALETTE.greenBg : PALETTE.orangeBg,
                            color: req.quality_score >= 80 ? PALETTE.green : PALETTE.orange, fontWeight: 700, fontSize: 11 }} />
                      ) : '—'}
                    </TableCell>
                    <TableCell sx={cellStyle}><StatusChip status={req.status} /></TableCell>
                    <TableCell sx={cellStyle}>
                      <Button size="small" variant="outlined"
                        sx={{ borderRadius: 2, textTransform: 'none', fontSize: 11, fontWeight: 600,
                          borderColor: PALETTE.teal, color: PALETTE.teal, px: 1.5 }}>
                        Voir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>

        {/* ── Section demandes colonnes dynamiques ── */}
        <Typography variant="h6" sx={{ fontWeight: 800, color: PALETTE.navy, mt: 5, mb: 1 }}>
          Demandes de colonnes dynamiques
          {pendingColCount > 0 && (
            <Chip label={pendingColCount} size="small"
              sx={{ ml: 1.5, bgcolor: PALETTE.orangeBg, color: PALETTE.orange, fontWeight: 800, fontSize: 12 }} />
          )}
        </Typography>
        <Typography variant="body2" sx={{ color: PALETTE.textMuted, mb: 2 }}>
          Ajouts ou suppressions de colonnes dynamiques soumis par les utilisateurs.
        </Typography>

        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          {['pending', 'approved', 'rejected', 'all'].map(f => (
            <Button key={f} size="small" variant={colFilter === f ? 'contained' : 'outlined'}
              onClick={() => setColFilter(f)}
              sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 600, fontSize: 12,
                ...(colFilter === f ? { bgcolor: PALETTE.rose, '&:hover': { bgcolor: '#b5607a' } } :
                  { borderColor: PALETTE.border, color: PALETTE.textMuted }) }}>
              {{ pending: 'En attente', approved: 'Approuvés', rejected: 'Rejetés', all: 'Tous' }[f]}
            </Button>
          ))}
        </Stack>

        <Paper elevation={0} sx={{ borderRadius: 3, border: `1px solid ${PALETTE.border}`, overflow: 'hidden', mb: 4 }}>
          {colLoading ? (
            <Box sx={{ p: 3, textAlign: 'center' }}><CircularProgress size={24} sx={{ color: PALETTE.rose }} /></Box>
          ) : colRequests.length === 0 ? (
            <Box sx={{ p: 3, textAlign: 'center' }}>
              <Typography sx={{ color: PALETTE.textMuted, fontSize: 13 }}>Aucune demande.</Typography>
            </Box>
          ) : (
            <Table>
              <TableHead sx={{ bgcolor: PALETTE.bg }}>
                <TableRow>
                  {['Action', 'Colonne', 'Type', 'Soumis par', 'Date', 'Statut', ''].map(h => (
                    <TableCell key={h} sx={{ fontSize: 12, color: PALETTE.textMuted, fontWeight: 600, py: 1.5, px: 2 }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {colRequests.map(r => (
                  <TableRow key={r.id} hover sx={{ cursor: 'pointer' }} onClick={() => { setColSelected(r); setColComment(''); setColActionResult(null); }}>
                    <TableCell sx={{ py: 1.5, px: 2, fontSize: 13 }}>
                      <Chip label={ACTION_LABELS[r.action] || r.action} size="small"
                        sx={{ bgcolor: ACTION_COLORS[r.action]?.bg, color: ACTION_COLORS[r.action]?.color, fontWeight: 700, fontSize: 11 }} />
                    </TableCell>
                    <TableCell sx={{ py: 1.5, px: 2, fontSize: 13, fontFamily: 'monospace', color: PALETTE.textDark }}>{r.column_key}</TableCell>
                    <TableCell sx={{ py: 1.5, px: 2, fontSize: 12, color: PALETTE.textMuted }}>{r.field_type}</TableCell>
                    <TableCell sx={{ py: 1.5, px: 2, fontSize: 13 }}>{r.submitted_by}</TableCell>
                    <TableCell sx={{ py: 1.5, px: 2, fontSize: 12, color: PALETTE.textMuted }}>
                      {r.submitted_at ? new Date(r.submitted_at).toLocaleString('fr-FR') : '—'}
                    </TableCell>
                    <TableCell sx={{ py: 1.5, px: 2 }}><StatusChip status={r.status} /></TableCell>
                    <TableCell sx={{ py: 1.5, px: 2 }}>
                      <Button size="small" variant="outlined"
                        sx={{ borderRadius: 2, textTransform: 'none', fontSize: 11, fontWeight: 600,
                          borderColor: PALETTE.rose, color: PALETTE.rose, px: 1.5 }}>
                        Voir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>

        {/* Dialog détail demande colonne */}
        <Dialog open={!!colSelected} onClose={() => !colActionLoading && setColSelected(null)} maxWidth="xs" fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}>
          {colSelected && (
            <>
              <DialogTitle sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 16 }}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Chip label={ACTION_LABELS[colSelected.action]} size="small"
                    sx={{ bgcolor: ACTION_COLORS[colSelected.action]?.bg, color: ACTION_COLORS[colSelected.action]?.color, fontWeight: 700 }} />
                  <Typography sx={{ fontFamily: 'monospace', fontSize: 15, fontWeight: 700 }}>{colSelected.column_key}</Typography>
                </Stack>
                <Typography variant="body2" sx={{ color: PALETTE.textMuted, mt: 0.5, fontWeight: 400 }}>
                  Soumis par {colSelected.submitted_by} · {colSelected.submitted_at ? new Date(colSelected.submitted_at).toLocaleString('fr-FR') : ''}
                </Typography>
              </DialogTitle>
              <Divider />
              <DialogContent sx={{ pt: 2, display: 'grid', gap: 1.5 }}>
                <Stack direction="row" spacing={2}>
                  <Paper variant="outlined" sx={{ borderRadius: 2, px: 2, py: 1, flex: 1 }}>
                    <Typography sx={{ fontSize: 11, color: PALETTE.textMuted, fontWeight: 600 }}>Libellé</Typography>
                    <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{colSelected.column_label || '—'}</Typography>
                  </Paper>
                  <Paper variant="outlined" sx={{ borderRadius: 2, px: 2, py: 1, flex: 1 }}>
                    <Typography sx={{ fontSize: 11, color: PALETTE.textMuted, fontWeight: 600 }}>Type</Typography>
                    <Typography sx={{ fontSize: 14, fontWeight: 700 }}>{colSelected.field_type}</Typography>
                  </Paper>
                </Stack>
                {colActionResult && (
                  <Alert severity={colActionResult.error ? 'error' : 'success'}>
                    {colActionResult.error || (colActionResult.action === 'approve' ? '✓ Action appliquée.' : 'Demande rejetée.')}
                  </Alert>
                )}
                {colSelected.status === 'pending' && !colActionResult && (
                  <TextField fullWidth multiline rows={2} label="Commentaire (optionnel)"
                    value={colComment} onChange={(e) => setColComment(e.target.value)}
                    size="small" placeholder="Motif de la décision..." />
                )}
              </DialogContent>
              <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
                <Button onClick={() => setColSelected(null)} disabled={colActionLoading}
                  sx={{ textTransform: 'none', color: PALETTE.textMuted, borderRadius: 2 }}>Fermer</Button>
                {colSelected.status === 'pending' && !colActionResult && (
                  <>
                    <Button variant="outlined" onClick={() => handleColAction('reject')} disabled={colActionLoading}
                      sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 600, borderColor: PALETTE.red, color: PALETTE.red }}>
                      {colActionLoading ? <CircularProgress size={13} sx={{ mr: 1 }} /> : null} Rejeter
                    </Button>
                    <Button variant="contained" onClick={() => handleColAction('approve')} disabled={colActionLoading}
                      sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, bgcolor: PALETTE.rose }}>
                      {colActionLoading ? <CircularProgress size={13} sx={{ color: 'white', mr: 1 }} /> : null} Approuver
                    </Button>
                  </>
                )}
              </DialogActions>
            </>
          )}
        </Dialog>

        {/* Detail Dialog */}
        <Dialog open={!!selected} onClose={() => !actionLoading && setSelected(null)} maxWidth="lg" fullWidth
          PaperProps={{ sx: { borderRadius: 3 } }}>
          {selected && (
            <>
              <DialogTitle sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 17 }}>
                Demande de validation — {selected.source_file_name || selected.session_id?.slice(0, 8)}
                <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                  <StatusChip status={selected.status} />
                  <Chip label={selected.source === 'corrected' ? 'Version corrigée' : 'Version originale'} size="small"
                    sx={{ bgcolor: `${PALETTE.teal}15`, color: PALETTE.teal, fontWeight: 600, fontSize: 11 }} />
                </Stack>
              </DialogTitle>
              <Divider />
              <DialogContent sx={{ pt: 2 }}>
                {previewLoading && <LinearProgress sx={{ mb: 2 }} />}
                {preview && (
                  <>
                    {/* Stats */}
                    <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
                      {[
                        { label: 'Patients', value: preview.rows_count },
                        { label: 'Colonnes', value: preview.columns_count },
                        { label: 'Score qualité', value: preview.quality_score != null ? `${preview.quality_score}%` : '—' },
                        { label: 'Problèmes détectés', value: preview.issues_count },
                      ].map(s => (
                        <Paper key={s.label} variant="outlined" sx={{ borderRadius: 2, px: 2, py: 1, borderColor: PALETTE.border, minWidth: 100 }}>
                          <Typography sx={{ fontSize: 11, color: PALETTE.textMuted, fontWeight: 600 }}>{s.label}</Typography>
                          <Typography sx={{ fontSize: 16, fontWeight: 800, color: PALETTE.navy }}>{s.value}</Typography>
                        </Paper>
                      ))}
                    </Stack>

                    {/* Cross-column issues */}
                    {preview.cross_column_issues?.length > 0 && (
                      <Alert severity="warning" sx={{ mb: 2, fontSize: 12 }}>
                        {preview.cross_column_issues.length} incohérence(s) entre colonnes détectée(s).
                      </Alert>
                    )}

                    {/* Data preview table */}
                    <Typography sx={{ fontWeight: 700, color: PALETTE.navy, fontSize: 13, mb: 1 }}>
                      Aperçu des données ({preview.preview_rows?.length} premières lignes)
                    </Typography>
                    <Box sx={{ overflowX: 'auto', maxHeight: 320, border: `1px solid ${PALETTE.border}`, borderRadius: 2 }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            {(preview.columns || []).slice(0, 15).map(col => (
                              <TableCell key={col} sx={{ bgcolor: PALETTE.bg, fontSize: 11, fontWeight: 700,
                                color: PALETTE.textMuted, py: 1, px: 1.5, whiteSpace: 'nowrap' }}>
                                {col}
                              </TableCell>
                            ))}
                            {(preview.columns || []).length > 15 && (
                              <TableCell sx={{ bgcolor: PALETTE.bg, fontSize: 11, color: PALETTE.textMuted }}>
                                +{(preview.columns || []).length - 15} col.
                              </TableCell>
                            )}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {(preview.preview_rows || []).slice(0, 20).map((row, ri) => (
                            <TableRow key={ri} hover>
                              {(preview.columns || []).slice(0, 15).map(col => (
                                <TableCell key={col} sx={{ fontSize: 11, color: PALETTE.textDark, py: 0.8, px: 1.5,
                                  whiteSpace: 'nowrap', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {row[col] != null && row[col] !== '' ? String(row[col]) : <span style={{ color: PALETTE.textMuted }}>—</span>}
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </Box>
                  </>
                )}

                {/* Action result */}
                {actionResult && (
                  <Alert severity={actionResult.error ? 'error' : 'success'} sx={{ mt: 2 }}>
                    {actionResult.error || (actionResult.action === 'approve'
                      ? `✓ Données intégrées avec succès dans la plateforme.`
                      : `Demande rejetée.`)}
                  </Alert>
                )}

                {/* Comment field for rejection */}
                {selected.status === 'pending' && !actionResult && (
                  <TextField fullWidth multiline rows={2} label="Commentaire (optionnel)"
                    value={comment} onChange={(e) => setComment(e.target.value)}
                    sx={{ mt: 2 }} size="small"
                    placeholder="Motif de validation ou de rejet..." />
                )}
              </DialogContent>
              <DialogActions sx={{ px: 3, pb: 2.5, gap: 1 }}>
                <Button onClick={() => setSelected(null)} disabled={actionLoading}
                  sx={{ textTransform: 'none', color: PALETTE.textMuted, borderRadius: 2 }}>
                  Fermer
                </Button>
                {selected.status === 'pending' && !actionResult && (
                  <>
                    <Button variant="outlined" onClick={() => handleAction('reject')} disabled={actionLoading}
                      sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 600, px: 2.5,
                        borderColor: PALETTE.red, color: PALETTE.red, '&:hover': { bgcolor: PALETTE.redBg } }}>
                      {actionLoading ? <CircularProgress size={14} sx={{ mr: 1 }} /> : null}
                      Rejeter
                    </Button>
                    <Button variant="contained" onClick={() => handleAction('approve')} disabled={actionLoading}
                      sx={{ textTransform: 'none', borderRadius: 2, fontWeight: 700, px: 3,
                        bgcolor: PALETTE.navy, '&:hover': { bgcolor: PALETTE.navyLight } }}>
                      {actionLoading ? <CircularProgress size={14} sx={{ color: 'white', mr: 1 }} /> : null}
                      Valider et intégrer
                    </Button>
                  </>
                )}
              </DialogActions>
            </>
          )}
        </Dialog>
      </Box>
    </Box>
  );
}
