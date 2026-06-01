import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  CircularProgress,
  Chip,
  Divider,
  IconButton,
  Stack,
  TextField,
  Typography,
  Container,
} from '@mui/material';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';
import AppSidebar from '../../components/common/AppSidebar';
import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import LanguageOutlinedIcon from '@mui/icons-material/LanguageOutlined';
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined';
import ExpandMoreOutlinedIcon from '@mui/icons-material/ExpandMoreOutlined';
import { useLanguage } from '../../context/LanguageContext';

const PROFILE_THEME = {
  deepNavy: '#1f2a44',
  medicalBlue: '#4f6d9a',
  softRose: '#b86f86',
  border: 'rgba(31,42,68,.10)',
  pageBackground: '#f4f6fa',
  panelBackground: '#ffffff',
  softPanelBackground: '#fbfcfe',
  sidebarBackground: '#fcf7f9',
};

const APP_SIDEBAR_WIDTH = 220;

const softCardSx = {
  elevation: 0,
  border: `1px solid ${PROFILE_THEME.border}`,
  background: PROFILE_THEME.panelBackground,
  borderRadius: 3,
  boxShadow: '0 10px 30px rgba(31,42,68,.05)',
};

const infoRowSx = {
  p: 1.5,
  borderRadius: 2,
  border: `1px solid ${PROFILE_THEME.border}`,
  bgcolor: PROFILE_THEME.softPanelBackground,
};

const detailPanelSx = {
  p: 1.75,
  borderRadius: 2.5,
  border: `1px solid ${PROFILE_THEME.border}`,
  background: PROFILE_THEME.softPanelBackground,
};

const detailChipSx = {
  height: 24,
  fontSize: '0.72rem',
  fontWeight: 700,
  bgcolor: 'rgba(61,90,138,.08)',
  color: PROFILE_THEME.deepNavy,
};

function Profile() {
  const { user } = useContext(AuthContext);
  const { language, setLanguage, t } = useLanguage();
  const [form, setForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState('');
  const [hiddenAuditIds, setHiddenAuditIds] = useState([]);
  const [expandedAuditIds, setExpandedAuditIds] = useState([]);

  const userInitials = useMemo(() => {
    const first = (user?.prenom || '').trim();
    const last = (user?.nom || '').trim();
    const initials = `${first[0] || ''}${last[0] || ''}`.trim();
    return initials || 'U';
  }, [user?.nom, user?.prenom]);

  const canViewAuditSummary = ['super_admin', 'chef_service'].includes(user?.role);
  const canChangePassword = ['super_admin', 'chef_service'].includes(user?.role);

  const auditActionLabels = useMemo(() => ({
    CREATION_UTILISATEUR: t('auditActionCreateUser'),
    MODIFICATION_UTILISATEUR: t('auditActionUpdateUser'),
    SUPPRESSION_UTILISATEUR: t('auditActionDeleteUser'),
    CONSULTATION_MOT_DE_PASSE_HASH: t('auditActionViewPassword'),
    MODIFICATION_MOT_DE_PASSE: t('auditActionChangePassword'),
  }), [t]);

  const visibleAuditLogs = useMemo(
    () => auditLogs.filter((entry) => !hiddenAuditIds.includes(entry.id)),
    [auditLogs, hiddenAuditIds],
  );

  const formatAuditDate = (value) => {
    if (!value) {
      return '-';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    const locale = language === 'en' ? 'en-US' : 'fr-FR';
    return date.toLocaleString(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  };

  const parseAuditDetails = (details) => {
    const lines = String(details || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    const sections = [];
    lines.forEach((line) => {
      const separatorIndex = line.indexOf(':');
      if (separatorIndex === -1) {
        sections.push({ label: null, value: line });
        return;
      }

      const label = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();
      sections.push({ label, value });
    });

    return sections;
  };

  const renderKeyValuePairs = (value) => {
    const pairs = String(value || '')
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const separatorIndex = part.indexOf(':');
        if (separatorIndex === -1) {
          return { key: null, value: part };
        }

        return {
          key: part.slice(0, separatorIndex).trim(),
          value: part.slice(separatorIndex + 1).trim(),
        };
      });

    return pairs;
  };

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

  const extractOldNewFromDetail = (detail) => {
    if (!detail) return { raw: '' };
    try {
      const parsed = typeof detail === 'string' ? JSON.parse(detail) : detail;
      if (parsed && typeof parsed === 'object') {
        if (Array.isArray(parsed.changes) && parsed.changes.length) {
          const changes = parsed.changes.map((c) => ({ field: c.field || c.key || null, old: c.old ?? c.previous, new: c.new ?? c.current }));
          return { changes, raw: detail };
        }

        if (parsed.field && (parsed.old !== undefined || parsed.new !== undefined)) {
          return { changes: [{ field: parsed.field, old: parsed.old, new: parsed.new }], raw: detail };
        }

        if (parsed.old !== undefined || parsed.new !== undefined) return { changes: [{ field: null, old: parsed.old, new: parsed.new }], raw: detail };
        if (parsed.previous !== undefined || parsed.current !== undefined) return { changes: [{ field: null, old: parsed.previous, new: parsed.current }], raw: detail };
        if (parsed.old_value !== undefined || parsed.new_value !== undefined) return { changes: [{ field: null, old: parsed.old_value, new: parsed.new_value }], raw: detail };
      }
    } catch (e) {
      // ignore
    }

    const text = String(detail || '');
    const changes = [];
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

    const anyArrow = text.match(/(.*?)\s*->\s*(.*)/);
    if (anyArrow) return { changes: [{ field: null, old: anyArrow[1].trim(), new: anyArrow[2].trim() }], raw: detail };

    return { raw: detail };
  };

  useEffect(() => {
    if (!canViewAuditSummary) {
      setAuditLogs([]);
      setAuditLoading(false);
      setAuditError('');
      return;
    }

    let active = true;

    const loadAuditHistory = async () => {
      setAuditLoading(true);
      setAuditError('');

      try {
        const response = await api.get('/auth/audit-history/');
        if (active) {
          setAuditLogs(Array.isArray(response.data) ? response.data : []);
          setHiddenAuditIds([]);
          setExpandedAuditIds([]);
        }
      } catch (error) {
        if (active) {
          const status = error.response?.status;
          if (status === 401) {
            setAuditError('Votre session a expiré. Reconnectez-vous pour charger l’historique.');
          } else if (status === 403) {
            setAuditError('Accès refusé. Seuls le Super Administrateur et le Chef de service peuvent voir cet historique.');
          } else {
            setAuditError(error.response?.data?.error || t('auditError'));
          }
        }
      } finally {
        if (active) {
          setAuditLoading(false);
        }
      }
    };

    loadAuditHistory();

    return () => {
      active = false;
    };
  }, [canViewAuditSummary, t]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const toggleAuditDetails = (auditId) => {
    setExpandedAuditIds((current) => (
      current.includes(auditId)
        ? current.filter((id) => id !== auditId)
        : [...current, auditId]
    ));
  };

  const hideAuditEntry = (auditId) => {
    setHiddenAuditIds((current) => (current.includes(auditId) ? current : [...current, auditId]));
    setExpandedAuditIds((current) => current.filter((id) => id !== auditId));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validations
    if (!form.currentPassword.trim()) {
      setMessage({ type: 'error', text: t('currentPasswordError') });
      return;
    }

    if (!form.newPassword.trim()) {
      setMessage({ type: 'error', text: t('newPasswordError') });
      return;
    }

    if (form.newPassword.length < 8) {
      setMessage({ type: 'error', text: t('passwordLengthError') });
      return;
    }

    if (form.newPassword !== form.confirmPassword) {
      setMessage({ type: 'error', text: t('passwordMismatchError') });
      return;
    }

    if (form.newPassword === form.currentPassword) {
      setMessage({ type: 'error', text: t('passwordSameError') });
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/change-password/', {
        current_password: form.currentPassword,
        new_password: form.newPassword,
      });

      setMessage({ type: 'success', text: t('passwordSuccess') });
      setForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
    } catch (error) {
      const errorMsg = error.response?.data?.error || 
                       error.response?.data?.non_field_errors?.[0] ||
                       t('passwordGenericError');
      setMessage({ type: 'error', text: errorMsg });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AppSidebar />
      {/* Main profile container with background image */}
      <Box
        sx={{
                                  maxHeight: 320,
                                  overflowY: 'auto',
                                  scrollbarGutter: 'stable',
          minHeight: '100vh',
          ml: { xs: 0, md: `${APP_SIDEBAR_WIDTH}px` },
          width: { xs: '100%', md: `calc(100% - ${APP_SIDEBAR_WIDTH}px)` },
          background: PROFILE_THEME.pageBackground,
          position: 'relative',
        }}
      >
        {/* Content wrapper */}
        <Box
          sx={{
            position: 'relative',
            zIndex: 2,
            display: 'flex',
            minHeight: '100vh',
            width: '100%',
            flexDirection: { xs: 'column', md: 'row' },
          }}
        >
          {/* Left Sidebar */}
          <Box
            sx={{
              width: { xs: '100%', md: '320px' },
              minWidth: { xs: '100%', md: '320px' },
              maxWidth: { xs: '100%', md: '320px' },
              background: PROFILE_THEME.sidebarBackground,
              boxShadow: { xs: 'none', md: '10px 0 28px rgba(31,42,68,0.06)' },
              p: { xs: 2, md: 2.5 },
              overflowY: 'auto',
              borderRight: { xs: 'none', md: `1px solid ${PROFILE_THEME.border}` },
              flexShrink: 0,
            }}
          >
            <Stack spacing={3}>
              {/* User Card Header */}
              <Box
                sx={{
                  textAlign: 'center',
                  p: 2.25,
                  borderRadius: 3,
                  border: `1px solid ${PROFILE_THEME.border}`,
                  background: PROFILE_THEME.panelBackground,
                  boxShadow: '0 12px 30px rgba(31,42,68,.06)',
                }}
              >
                <Avatar
                  sx={{
                    width: 80,
                    height: 80,
                    bgcolor: PROFILE_THEME.deepNavy,
                    color: 'white',
                    fontWeight: 900,
                    fontSize: 28,
                    mx: 'auto',
                    mb: 2,
                    boxShadow: '0 8px 20px rgba(31, 42, 68, 0.18)',
                  }}
                >
                  {userInitials}
                </Avatar>
                <Typography
                  variant="h6"
                  fontWeight={900}
                  sx={{ color: PROFILE_THEME.deepNavy, letterSpacing: -0.5 }}
                >
                  {user?.prenom || ''} {user?.nom || ''}
                </Typography>
                <Chip
                  label={user?.role || '-'}
                  size="small"
                  sx={{
                    mt: 1.5,
                    mx: 'auto',
                    bgcolor: 'rgba(79,109,154,.10)',
                    color: PROFILE_THEME.medicalBlue,
                    fontWeight: 800,
                  }}
                />
              </Box>

              <Divider />

              {/* User Info */}
              <Stack spacing={2}>
                <Typography
                  variant="overline"
                  fontWeight={900}
                  sx={{ color: PROFILE_THEME.medicalBlue, letterSpacing: 1.2, fontSize: '0.7rem' }}
                >
                  Informations du compte
                </Typography>
                <Stack spacing={1.5}>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>
                      Email
                    </Typography>
                    <Typography
                      variant="body2"
                      fontWeight={700}
                      sx={{ wordBreak: 'break-word', color: PROFILE_THEME.deepNavy }}
                    >
                      {user?.email || '-'}
                    </Typography>
                  </Box>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>
                      {t('role')}
                    </Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: PROFILE_THEME.deepNavy }}>
                      {user?.role || '-'}
                    </Typography>
                  </Box>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>
                      {t('telephone')}
                    </Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: PROFILE_THEME.deepNavy }}>
                      {user?.telephone || '-'}
                    </Typography>
                  </Box>
                </Stack>
              </Stack>

              <Divider />

              {/* Language Selector Card */}
              <Card sx={softCardSx}>
                <CardContent sx={{ p: 2 }}>
                  <Stack spacing={1.5}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <LanguageOutlinedIcon
                        sx={{ color: PROFILE_THEME.medicalBlue, fontSize: 20 }}
                      />
                      <Typography
                        variant="subtitle2"
                        fontWeight={900}
                        sx={{ color: PROFILE_THEME.deepNavy }}
                      >
                        {t('languageSectionTitle')}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={1}>
                      <Button
                        type="button"
                        variant={language === 'fr' ? 'contained' : 'outlined'}
                        onClick={() => setLanguage('fr')}
                        fullWidth
                        sx={{
                          minHeight: 42,
                          borderRadius: 999,
                          textTransform: 'none',
                          fontWeight: 800,
                        }}
                      >
                        {t('french')}
                      </Button>
                      <Button
                        type="button"
                        variant={language === 'en' ? 'contained' : 'outlined'}
                        onClick={() => setLanguage('en')}
                        fullWidth
                        sx={{
                          minHeight: 42,
                          borderRadius: 999,
                          textTransform: 'none',
                          fontWeight: 800,
                        }}
                      >
                        {t('english')}
                      </Button>
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>
          </Box>

          {/* Right Content Area - Desktop View */}
          <Box
            sx={{
              flex: 1,
              p: { xs: 0, md: 4 },
                            pb: 4,
              overflowY: 'auto',
              display: { xs: 'none', md: 'block' },
                          minHeight: '100vh',
            }}
          >
            <Container maxWidth="md">
              <Stack spacing={3}>
                {/* Change Password Card */}
                <Card sx={softCardSx}>
                  <CardContent sx={{ p: 3 }}>
                    <Stack spacing={3}>
                      <Stack direction="row" spacing={1.5} alignItems="center">
                        <LockOutlinedIcon
                          sx={{ color: PROFILE_THEME.softRose, fontSize: 24 }}
                        />
                        <Box>
                          <Typography
                            variant="h6"
                            fontWeight={900}
                            sx={{ color: PROFILE_THEME.deepNavy }}
                          >
                            {t('changePasswordTitle')}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                                Mettez à jour votre accès en toute sécurité.
                              </Typography>
                        </Box>
                      </Stack>

                      {message.text && (
                        <Alert
                          severity={message.type}
                          onClose={() => setMessage({ type: '', text: '' })}
                        >
                          {message.text}
                        </Alert>
                      )}

                      {canChangePassword ? (
                        <Box component="form" onSubmit={handleSubmit}>
                          <Stack spacing={2}>
                            <TextField
                              label={t('currentPassword')}
                              type="password"
                              name="currentPassword"
                              value={form.currentPassword}
                              onChange={handleChange}
                              fullWidth
                              size="small"
                              disabled={loading}
                            />

                            <TextField
                              label={t('newPassword')}
                              type="password"
                              name="newPassword"
                              value={form.newPassword}
                              onChange={handleChange}
                              fullWidth
                              size="small"
                              disabled={loading}
                            />

                            <TextField
                              label={t('confirmPassword')}
                              type="password"
                              name="confirmPassword"
                              value={form.confirmPassword}
                              onChange={handleChange}
                              fullWidth
                              size="small"
                              disabled={loading}
                            />

                            <Stack direction="row" spacing={1.5}>
                              <Button
                                type="submit"
                                variant="contained"
                                disabled={loading}
                                sx={{
                                  minHeight: 46,
                                  borderRadius: 999,
                                  background: PROFILE_THEME.deepNavy,
                                  textTransform: 'none',
                                  fontWeight: 800,
                                  boxShadow: '0 12px 24px rgba(31,42,68,.16)',
                                  '&:hover': {
                                    background: PROFILE_THEME.medicalBlue,
                                  },
                                }}
                              >
                                {loading ? (
                                  <CircularProgress size={20} sx={{ mr: 1, color: 'white' }} />
                                ) : null}
                                {loading ? '...' : t('submitPassword')}
                              </Button>
                              <Button
                                type="button"
                                variant="outlined"
                                onClick={() => {
                                  setForm({
                                    currentPassword: '',
                                    newPassword: '',
                                    confirmPassword: '',
                                  });
                                  setMessage({ type: '', text: '' });
                                }}
                                disabled={loading}
                                sx={{
                                  minHeight: 46,
                                  borderRadius: 999,
                                  textTransform: 'none',
                                  fontWeight: 800,
                                  borderColor: PROFILE_THEME.border,
                                  color: PROFILE_THEME.deepNavy,
                                  '&:hover': {
                                    borderColor: PROFILE_THEME.medicalBlue,
                                    backgroundColor: 'rgba(79,109,154,.04)',
                                  },
                                }}
                              >
                                {t('cancel')}
                              </Button>
                            </Stack>
                          </Stack>
                        </Box>
                      ) : (
                        <Alert severity="info">
                          La modification du mot de passe est réservée au Super Administrateur et au Chef de service.
                        </Alert>
                      )}
                    </Stack>
                  </CardContent>
                </Card>

                {/* Audit Summary Card (for admin/chef only) */}
                {canViewAuditSummary && (
                  <Card sx={softCardSx}>
                    <CardContent sx={{ p: 3 }}>
                      <Stack spacing={2}>
                        <Typography
                          variant="h6"
                          fontWeight={900}
                          sx={{ color: PROFILE_THEME.deepNavy }}
                        >
                          {t('auditCardTitle')}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {t('auditCardDescription')}
                        </Typography>
                        <Chip
                          label={t('auditViewerHint')}
                          sx={{
                            alignSelf: 'flex-start',
                            bgcolor: 'rgba(61,90,138,.10)',
                            color: PROFILE_THEME.medicalBlue,
                            fontWeight: 800,
                          }}
                        />
                        {auditLoading ? (
                          <Stack direction="row" spacing={1.5} alignItems="center">
                            <CircularProgress size={18} />
                            <Typography variant="body2" color="text.secondary">
                              {t('auditLoading')}
                            </Typography>
                          </Stack>
                        ) : auditError ? (
                          <Alert severity="error">{auditError}</Alert>
                        ) : visibleAuditLogs.length === 0 ? (
                          <Typography variant="body2" color="text.secondary">
                            {t('auditEmpty')}
                          </Typography>
                        ) : (
                          <Stack spacing={1.25}>
                            {visibleAuditLogs.map((entry) => (
                              <Box
                                key={entry.id}
                                sx={{
                                  ...infoRowSx,
                                  borderLeft: `4px solid ${PROFILE_THEME.medicalBlue}`,
                                }}
                              >
                                <Stack direction="row" spacing={1.5} alignItems="flex-start" justifyContent="space-between">
                                  <Box sx={{ minWidth: 0, flex: 1 }}>
                                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5, flexWrap: 'wrap' }}>
                                      <Chip
                                        label={auditActionLabels[entry.action] || entry.action}
                                        size="small"
                                        sx={detailChipSx}
                                      />
                                      <Chip
                                        label={entry.user || 'Utilisateur système'}
                                        size="small"
                                        variant="outlined"
                                        sx={{ height: 24, fontSize: '0.72rem', fontWeight: 700, borderColor: 'rgba(79,109,154,.18)', color: PROFILE_THEME.medicalBlue }}
                                      />
                                      <Typography variant="caption" color="text.secondary">
                                        {formatAuditDate(entry.date)}
                                      </Typography>
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">
                                      {[entry.entite_id ? `ID ${entry.entite_id}` : null].filter(Boolean).join(' • ')}
                                    </Typography>
                                  </Box>
                                  <Stack direction="row" spacing={0.25} sx={{ flexShrink: 0 }}>
                                    <IconButton size="small" onClick={() => toggleAuditDetails(entry.id)} aria-label={t('auditShowDetails')}>
                                      <ExpandMoreOutlinedIcon
                                        fontSize="small"
                                        sx={{
                                          transition: 'transform 160ms ease',
                                          transform: expandedAuditIds.includes(entry.id) ? 'rotate(180deg)' : 'rotate(0deg)',
                                        }}
                                      />
                                    </IconButton>
                                    <IconButton size="small" onClick={() => hideAuditEntry(entry.id)} aria-label={t('auditHideEntry')} sx={{ color: PROFILE_THEME.softRose }}>
                                      <DeleteOutlineOutlinedIcon fontSize="small" />
                                    </IconButton>
                                  </Stack>
                                </Stack>

                                <Collapse in={expandedAuditIds.includes(entry.id)} timeout="auto" unmountOnExit>
                                  <Box sx={{ mt: 1.5, ...detailPanelSx }}>
                                    <Stack spacing={1.25}>
                                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase' }}>
                                        {t('auditDetails')}
                                      </Typography>

                                      {
                                        (() => {
                                          const extracted = extractOldNewFromDetail(entry.details);
                                          if (extracted.changes && extracted.changes.length) {
                                            return (
                                              <Box sx={{ p: 1.25, borderRadius: 2, bgcolor: 'rgba(245,249,252,0.95)', border: `1px solid ${PROFILE_THEME.border}` }}>
                                                {extracted.changes.map((c, ci) => (
                                                  <Box key={`chg-${entry.id}-${ci}`} sx={{ mb: ci === extracted.changes.length - 1 ? 0 : 1, p: 1.25, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.82)', border: '1px solid rgba(61,90,138,.10)' }}>
                                                    {c.field && (
                                                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75, fontWeight: 800, letterSpacing: '.05em', textTransform: 'uppercase' }}>{formatAuditFieldLabel(c.field)}</Typography>
                                                    )}
                                                    <Stack spacing={1}>
                                                      <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'rgba(212,122,142,.08)', border: '1px solid rgba(212,122,142,.14)', maxHeight: 180, overflowY: 'auto', pr: 0.75, '&::-webkit-scrollbar': { width: 8 }, '&::-webkit-scrollbar-thumb': { background: 'rgba(212,122,142,.25)', borderRadius: 999 } }}>
                                                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, letterSpacing: '.05em', textTransform: 'uppercase' }}>{t('auditOldValue')}</Typography>
                                                        <Typography variant="body2" sx={{ mt: 0.35, color: PROFILE_THEME.deepNavy, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{String(c.old ?? '-')}</Typography>
                                                      </Box>
                                                      <Box sx={{ p: 1, borderRadius: 1.5, bgcolor: 'rgba(26,107,138,.08)', border: '1px solid rgba(26,107,138,.14)', maxHeight: 180, overflowY: 'auto', pr: 0.75, '&::-webkit-scrollbar': { width: 8 }, '&::-webkit-scrollbar-thumb': { background: 'rgba(26,107,138,.25)', borderRadius: 999 } }}>
                                                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 800, letterSpacing: '.05em', textTransform: 'uppercase' }}>{t('auditNewValue')}</Typography>
                                                        <Typography variant="body2" sx={{ mt: 0.35, color: PROFILE_THEME.deepNavy, wordBreak: 'break-word', whiteSpace: 'pre-wrap' }}>{String(c.new ?? '-')}</Typography>
                                                      </Box>
                                                    </Stack>
                                                  </Box>
                                                ))}
                                              </Box>
                                            );
                                          }

                                          const sections = parseAuditDetails(entry.details);
                                          if (sections.length) {
                                            return (
                                              <Stack spacing={1.25}>
                                                {sections.map((section, index) => {
                                                  const pairs = section.value ? renderKeyValuePairs(section.value) : [];
                                                  const isSummaryLine = !section.label || section.label === 'Modifications';

                                                  return (
                                                    <Box key={`${entry.id}-${index}`} sx={{ p: 1.25, borderRadius: 2, bgcolor: isSummaryLine ? 'rgba(212,122,142,.08)' : 'rgba(61,90,138,.05)', border: '1px solid rgba(61,90,138,.10)' }}>
                                                      {section.label && (
                                                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75, fontWeight: 800 }}>
                                                          {section.label}
                                                        </Typography>
                                                      )}

                                                      {pairs.length ? (
                                                        <Stack spacing={0.75}>
                                                          {pairs.map((pair, pairIndex) => (
                                                            <Stack key={`${entry.id}-${index}-${pairIndex}`} direction="row" spacing={1} alignItems="flex-start">
                                                              {pair.key ? (
                                                                <Chip label={pair.key} size="small" sx={{ height: 22, fontSize: '0.7rem', bgcolor: 'rgba(79,109,154,.10)', color: PROFILE_THEME.deepNavy, fontWeight: 700 }} />
                                                              ) : null}
                                                              <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', color: PROFILE_THEME.deepNavy, fontWeight: pair.key ? 500 : 700 }}>
                                                                {pair.value}
                                                              </Typography>
                                                            </Stack>
                                                          ))}
                                                        </Stack>
                                                      ) : (
                                                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', color: PROFILE_THEME.deepNavy, fontWeight: isSummaryLine ? 700 : 500 }}>
                                                          {section.value || t('auditNoDetails')}
                                                        </Typography>
                                                      )}
                                                    </Box>
                                                  );
                                                })}
                                              </Stack>
                                            );
                                          }

                                          return (
                                            <Typography variant="body2" color="text.secondary">{t('auditNoDetails')}</Typography>
                                          );
                                        })()
                                      }
                                    </Stack>
                                  </Box>
                                </Collapse>
                              </Box>
                            ))}
                          </Stack>
                        )}
                      </Stack>
                    </CardContent>
                  </Card>
                )}
              </Stack>
            </Container>
          </Box>
        </Box>

        {/* Mobile View - Stacked Layout */}
        <Box sx={{ display: { xs: 'block', md: 'none' }, position: 'relative', zIndex: 2, p: 2 }}>
          <Stack spacing={2}>
            {/* Mobile Profile Card */}
            <Card sx={softCardSx}>
              <CardContent sx={{ p: 2 }}>
                <Stack spacing={2} alignItems="center" sx={{ textAlign: 'center' }}>
                  <Avatar
                    sx={{
                      width: 60,
                      height: 60,
                      bgcolor: PROFILE_THEME.deepNavy,
                      color: 'white',
                      fontWeight: 900,
                      fontSize: 22,
                    }}
                  >
                    {userInitials}
                  </Avatar>
                  <Box>
                    <Typography variant="h6" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy }}>
                      {user?.prenom || ''} {user?.nom || ''}
                    </Typography>
                    <Chip
                      label={user?.role || '-'}
                      size="small"
                      sx={{
                        mt: 1,
                        bgcolor: 'rgba(61,90,138,.10)',
                        color: PROFILE_THEME.medicalBlue,
                        fontWeight: 800,
                      }}
                    />
                  </Box>
                  <Stack spacing={1} sx={{ width: '100%' }}>
                    <Box sx={infoRowSx}>
                      <Typography variant="caption" color="text.secondary" fontWeight={700}>
                        Email
                      </Typography>
                      <Typography variant="body2" fontWeight={700} sx={{ wordBreak: 'break-word' }}>
                        {user?.email || '-'}
                      </Typography>
                    </Box>
                    <Box sx={infoRowSx}>
                      <Typography variant="caption" color="text.secondary" fontWeight={700}>
                        {t('role')}
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {user?.role || '-'}
                      </Typography>
                    </Box>
                    <Box sx={infoRowSx}>
                      <Typography variant="caption" color="text.secondary" fontWeight={700}>
                        {t('telephone')}
                      </Typography>
                      <Typography variant="body2" fontWeight={700}>
                        {user?.telephone || '-'}
                      </Typography>
                    </Box>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>

            {/* Mobile Language Card */}
            <Card sx={softCardSx}>
              <CardContent sx={{ p: 2 }}>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <LanguageOutlinedIcon sx={{ color: PROFILE_THEME.medicalBlue, fontSize: 20 }} />
                    <Typography
                      variant="subtitle2"
                      fontWeight={900}
                      sx={{ color: PROFILE_THEME.deepNavy }}
                    >
                      {t('languageSectionTitle')}
                    </Typography>
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <Button
                      type="button"
                      variant={language === 'fr' ? 'contained' : 'outlined'}
                      onClick={() => setLanguage('fr')}
                      fullWidth
                      sx={{
                        minHeight: 42,
                        borderRadius: 999,
                        textTransform: 'none',
                        fontWeight: 800,
                      }}
                    >
                      {t('french')}
                    </Button>
                    <Button
                      type="button"
                      variant={language === 'en' ? 'contained' : 'outlined'}
                      onClick={() => setLanguage('en')}
                      fullWidth
                      sx={{
                        minHeight: 42,
                        borderRadius: 999,
                        textTransform: 'none',
                        fontWeight: 800,
                      }}
                    >
                      {t('english')}
                    </Button>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>

            {/* Mobile Password Card */}
            {canChangePassword && (
              <Card sx={softCardSx}>
              <CardContent sx={{ p: 2 }}>
                <Stack spacing={2}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <LockOutlinedIcon sx={{ color: PROFILE_THEME.softRose, fontSize: 20 }} />
                    <Typography variant="subtitle2" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy }}>
                      {t('changePasswordTitle')}
                    </Typography>
                  </Stack>

                  {message.text && (
                    <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })}>
                      {message.text}
                    </Alert>
                  )}

                  <Box component="form" onSubmit={handleSubmit}>
                    <Stack spacing={1.5}>
                      <TextField
                        label={t('currentPassword')}
                        type="password"
                        name="currentPassword"
                        value={form.currentPassword}
                        onChange={handleChange}
                        fullWidth
                        size="small"
                        disabled={loading}
                      />
                      <TextField
                        label={t('newPassword')}
                        type="password"
                        name="newPassword"
                        value={form.newPassword}
                        onChange={handleChange}
                        fullWidth
                        size="small"
                        disabled={loading}
                      />
                      <TextField
                        label={t('confirmPassword')}
                        type="password"
                        name="confirmPassword"
                        value={form.confirmPassword}
                        onChange={handleChange}
                        fullWidth
                        size="small"
                        disabled={loading}
                      />
                      <Stack direction="column" spacing={1}>
                        <Button
                          type="submit"
                          variant="contained"
                          disabled={loading}
                          sx={{
                            minHeight: 40,
                            borderRadius: 999,
                            background: PROFILE_THEME.deepNavy,
                            textTransform: 'none',
                            fontWeight: 800,
                            '&:hover': {
                              background: PROFILE_THEME.medicalBlue,
                            },
                          }}
                        >
                          {loading ? <CircularProgress size={16} sx={{ mr: 1, color: 'white' }} /> : null}
                          {loading ? '...' : t('submitPassword')}
                        </Button>
                        <Button
                          type="button"
                          variant="outlined"
                          onClick={() => {
                            setForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
                            setMessage({ type: '', text: '' });
                          }}
                          disabled={loading}
                          sx={{
                            minHeight: 40,
                            borderRadius: 999,
                            textTransform: 'none',
                            fontWeight: 800,
                          }}
                        >
                          {t('cancel')}
                        </Button>
                      </Stack>
                    </Stack>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
            )}

            {/* Mobile Audit Card */}
            {canViewAuditSummary && (
              <Card sx={softCardSx}>
                <CardContent sx={{ p: 2 }}>
                  <Stack spacing={1.5}>
                    <Typography variant="subtitle2" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy }}>
                      {t('auditCardTitle')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" fontSize="0.85rem">
                      {t('auditCardDescription')}
                    </Typography>
                    {auditLoading ? (
                      <Stack direction="row" spacing={1.25} alignItems="center">
                        <CircularProgress size={16} />
                        <Typography variant="body2" color="text.secondary" fontSize="0.85rem">
                          {t('auditLoading')}
                        </Typography>
                      </Stack>
                    ) : auditError ? (
                      <Alert severity="error">{auditError}</Alert>
                    ) : visibleAuditLogs.length === 0 ? (
                      <Typography variant="body2" color="text.secondary" fontSize="0.85rem">
                        {t('auditEmpty')}
                      </Typography>
                    ) : (
                      <Stack spacing={0.75}>
                        {visibleAuditLogs.map((entry) => (
                          <Box key={entry.id} sx={{ display: 'block' }}>
                            <Stack direction="row" spacing={1} alignItems="flex-start">
                              <Box
                                sx={{
                                  width: 6,
                                  height: 6,
                                  borderRadius: '50%',
                                  bgcolor: PROFILE_THEME.softRose,
                                  flexShrink: 0,
                                  mt: 0.8,
                                }}
                              />
                              <Box sx={{ minWidth: 0, flex: 1 }}>
                                <Typography variant="body2" fontWeight={800} fontSize="0.85rem">
                                  {auditActionLabels[entry.action] || entry.action}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {[entry.user, formatAuditDate(entry.date)].filter(Boolean).join(' • ')}
                                </Typography>
                              </Box>
                              <Stack direction="row" spacing={0.25}>
                                <IconButton size="small" onClick={() => toggleAuditDetails(entry.id)} aria-label={t('auditShowDetails')}>
                                  <ExpandMoreOutlinedIcon
                                    fontSize="small"
                                    sx={{ transform: expandedAuditIds.includes(entry.id) ? 'rotate(180deg)' : 'rotate(0deg)' }}
                                  />
                                </IconButton>
                                <IconButton size="small" onClick={() => hideAuditEntry(entry.id)} aria-label={t('auditHideEntry')} sx={{ color: PROFILE_THEME.softRose }}>
                                  <DeleteOutlineOutlinedIcon fontSize="small" />
                                </IconButton>
                              </Stack>
                            </Stack>

                            <Collapse in={expandedAuditIds.includes(entry.id)} timeout="auto" unmountOnExit>
                              <Box sx={{ mt: 1, p: 1.25, borderRadius: 2, bgcolor: 'rgba(61,90,138,.06)', border: `1px solid ${PROFILE_THEME.border}` }}>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5, fontWeight: 700 }}>
                                  {t('auditDetails')}
                                </Typography>
                                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                                  {entry.details || t('auditNoDetails')}
                                </Typography>
                              </Box>
                            </Collapse>
                          </Box>
                        ))}
                      </Stack>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            )}
          </Stack>
        </Box>
      </Box>
    </>
  );
}

export default Profile;
