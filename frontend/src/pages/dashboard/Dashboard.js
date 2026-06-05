import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  Avatar,
  Chip,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  MenuItem,
  Paper,
  Popover,
  Stack,
  SvgIcon,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';
import CallOutlinedIcon from '@mui/icons-material/CallOutlined';
import AppSidebar from '../../components/common/AppSidebar';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined';
import NotificationsActiveOutlinedIcon from '@mui/icons-material/NotificationsActiveOutlined';
import { useLocation, useNavigate } from 'react-router-dom';
import { useLanguage } from '../../context/LanguageContext';

const roleLabels = {
  super_admin: 'Super Administrateur',
  chef_service: 'Chef de Service',
  professeur: 'Professeur',
  resident: 'Résident',
};

const roleDescriptions = {
  super_admin: 'Gestion globale du système, supervision des accès et traçabilité complète.',
  chef_service: 'Supervision médicale, gestion des comptes du service et validation des données.',
  professeur: 'Analyse clinique, suivi des patients et exploitation des modèles prédictifs.',
  resident: 'Utilisation opérationnelle, consultation des dossiers et application des prédictions IA.',
};

const DASHBOARD_THEME = {
  deepNavy: '#0A2B3E',
  medicalBlue: '#1A6B8A',
  tealGreen: '#1E9E84',
  softRose: '#D47A8E',
  dustyRose: '#C46B82',
  indigo: '#5B6BC0',
  steelBlue: '#3A8FB5',
  purple: '#8B6FC4',
  blushPink: '#F0D3DF',
  offWhite: '#F5F9FC',
  lightGray: '#EFF3F6',
  borderLight: '#E2ECF0',
  textMuted: '#6B8A9C',
  white: '#FFFFFF',
  warning: '#E8A29E',
};

const emptyForm = {
  id: null,
  email: '',
  nom: '',
  prenom: '',
  telephone: '',
  role_id: '',
  is_active: true,
  password: '',
};

function Dashboard() {
  const { user, refreshProfile } = useContext(AuthContext);
  const { t } = useLanguage();
  const navigate = useNavigate();
  const location = useLocation();
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [recentActivity, setRecentActivity] = useState([]);
  const [expandedActivity, setExpandedActivity] = useState(null);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState(emptyForm);
  const [adminPassword, setAdminPassword] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTargetUser, setDeleteTargetUser] = useState(null);
  const [deletePassword, setDeletePassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showManagementPanel, setShowManagementPanel] = useState(false);
  const [activeFilter, setActiveFilter] = useState(null);

  const isAdminScope = user?.role === 'super_admin' || user?.role === 'chef_service';
  const isDashboardActive = location.pathname.startsWith('/dashboard');
  const isPatientsActive = location.pathname.startsWith('/patients');
  const isModelAiActive = location.pathname.startsWith('/modele-ai');

  const shellSx = {
    flexGrow: 1,
    minHeight: '100vh',
    pt: 0,
    pb: { xs: 2, md: 3 },
    px: { xs: 0, md: 1 },
    background: [
      'radial-gradient(circle at top left, rgba(168,207,238,.48), transparent 34%)',
      'radial-gradient(circle at top right, rgba(158,61,106,.14), transparent 28%)',
      'linear-gradient(160deg,#f7f0f5 0%,#edf4fb 42%,#f4eef8 100%)',
    ].join(', '),
  };

  const heroSx = {
    mb: 3,
    p: { xs: 2.5, md: 3.5 },
    borderRadius: 5,
    color: DASHBOARD_THEME.white,
    overflow: 'hidden',
    position: 'relative',
    boxShadow: '0 24px 60px rgba(15, 23, 42, 0.14)',
    background: `linear-gradient(135deg, #0D4D63 0%, #1A8FA8 55%, #D47A8E 100%)`,
  };

  const softCardSx = {
    borderRadius: 5,
    overflow: 'hidden',
    border: `1px solid ${DASHBOARD_THEME.borderLight}`,
    background: `linear-gradient(180deg, ${DASHBOARD_THEME.white} 0%, ${DASHBOARD_THEME.offWhite} 100%)`,
    boxShadow: '0 18px 52px rgba(15, 23, 42, 0.08)',
  };

  const subtlePanelSx = {
    borderRadius: 5,
    border: `1px solid ${DASHBOARD_THEME.borderLight}`,
    background: `linear-gradient(180deg, ${DASHBOARD_THEME.white}, ${DASHBOARD_THEME.offWhite})`,
    boxShadow: '0 16px 44px rgba(15, 23, 42, 0.06)',
  };

  const statCardSx = (accent) => ({
    height: '100%',
    borderRadius: 4,
    border: `1px solid ${DASHBOARD_THEME.borderLight}`,
    borderTop: `4px solid ${accent}`,
    background: `linear-gradient(180deg, ${DASHBOARD_THEME.white}, ${DASHBOARD_THEME.offWhite})`,
    boxShadow: '0 4px 20px rgba(15, 23, 42, 0.05)',
    transition: 'transform 180ms ease, box-shadow 180ms ease',
    '&:hover': { transform: 'translateY(-3px)', boxShadow: '0 12px 32px rgba(15,23,42,0.10)' },
  });

  const stats = useMemo(() => {
    const managedUsers = users.filter((managedUser) => {
      if (user?.role === 'super_admin') {
        return true;
      }
      return managedUser.role?.nom === 'professeur' || managedUser.role?.nom === 'resident';
    });

    return {
      visibleUsers: managedUsers.length,
      activeUsers: managedUsers.filter((managedUser) => managedUser.is_active).length,
      inactiveUsers: managedUsers.filter((managedUser) => !managedUser.is_active).length,
      professorsCount: managedUsers.filter((managedUser) => managedUser.role?.nom === 'professeur').length,
      residentsCount: managedUsers.filter((managedUser) => managedUser.role?.nom === 'resident').length,
      adminsCount: managedUsers.filter((managedUser) => managedUser.role?.nom === 'super_admin').length,
      chefsCount: managedUsers.filter((managedUser) => managedUser.role?.nom === 'chef_service').length,
      rolesCount: roles.length,
    };
  }, [roles.length, user?.role, users]);

  const manageableUsers = useMemo(() => {
    const lower = search.trim().toLowerCase();
    return users.filter((managedUser) => {
      const allowed = user?.role === 'super_admin'
        || managedUser.role?.nom === 'professeur'
        || managedUser.role?.nom === 'resident';
      if (!allowed) return false;
      if (activeFilter === 'active'   && !managedUser.is_active) return false;
      if (activeFilter === 'inactive' &&  managedUser.is_active) return false;
      if (['super_admin','chef_service','professeur','resident'].includes(activeFilter)
          && managedUser.role?.nom !== activeFilter) return false;
      if (!lower) return true;
      return [
        managedUser.email,
        managedUser.nom,
        managedUser.prenom,
        managedUser.role?.label,
        managedUser.role?.nom,
      ].some((value) => value?.toLowerCase().includes(lower));
    });
  }, [user?.role, users, search, activeFilter]);

  const resolveRoleById = (roleId) => {
    return roles.find((role) => String(role.id) === String(roleId)) || null;
  };

  const loadManagementData = async () => {
    if (!isAdminScope) {
      return;
    }

    setError('');
    try {
      const [rolesResponse, usersResponse] = await Promise.all([
        api.get('auth/roles/'),
        api.get('auth/utilisateurs/'),
      ]);
      setRoles(rolesResponse.data);
      setUsers(usersResponse.data);
    } catch (requestError) {
      setError('Impossible de charger les comptes et les rôles.');
    }
  };

  useEffect(() => {
    loadManagementData();
  }, [isAdminScope]);

  useEffect(() => {
    if (!isAdminScope) {
      api.get('audit/my-activity/').then(r => setRecentActivity(r.data || [])).catch(() => {});
    }
  }, [isAdminScope]);

  const resetForm = () => {
    setForm(emptyForm);
    setAdminPassword('');
    setError('');
    setSuccess('');
  };

  const beginEdit = (selectedUser) => {
    setForm({
      id: selectedUser.id,
      email: selectedUser.email,
      nom: selectedUser.nom,
      prenom: selectedUser.prenom,
      telephone: selectedUser.telephone || '',
      role_id: selectedUser.role?.id || '',
      is_active: selectedUser.is_active,
      password: '',
    });
    setShowManagementPanel(true);
    setError('');
    setSuccess('');
  };

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;
    setForm((current) => ({
      ...current,
      [name]: type === 'checkbox' ? checked : value,
    }));
  };

  const handleSaveUser = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const payload = {
        email: form.email,
        nom: form.nom,
        prenom: form.prenom,
        telephone: form.telephone,
        role_id: form.role_id,
        is_active: form.is_active,
        ...(form.id ? { confirmation_password: adminPassword } : {}),
      };

      if (form.password && String(form.password).trim()) {
        payload.password = form.password;
      }

      const resolvedRole = resolveRoleById(form.role_id);

      if (form.id) {
        const response = await api.put(`auth/utilisateurs/${form.id}/`, payload);
        setUsers((currentUsers) => currentUsers.map((existingUser) => (
          existingUser.id === form.id
            ? { ...existingUser, ...response.data, role: resolvedRole || existingUser.role }
            : existingUser
        )));
        if (String(form.id) === String(user?.id)) {
          await refreshProfile();
        }
        setSuccess('Compte modifié avec succès.');
      } else {
        const response = await api.post('auth/utilisateurs/', {
          ...payload,
          password: form.password,
        });
        setUsers((currentUsers) => [{ ...response.data, role: resolvedRole }, ...currentUsers]);
        setSuccess('Compte créé avec succès.');
      }

      await loadManagementData();
      resetForm();
    } catch (requestError) {
      const apiMessage = requestError?.response?.data?.error
        || requestError?.response?.data?.detail
        || Object.values(requestError?.response?.data || {})[0];
      
      let userFriendlyError = apiMessage;
      if (apiMessage === 'Confirmation refusée') {
        userFriendlyError = 'Mot de passe de validation incorrect. Vérifie que tu as entré ton propre mot de passe d\'administrateur.';
      } else if (apiMessage === 'Confirmation administrateur requise') {
        userFriendlyError = 'Tu dois entrer ton mot de passe de validation pour pouvoir modifier ce compte.';
      }
      
      setError(userFriendlyError || 'Impossible d\'enregistrer le compte. Vérifie les droits et la confirmation.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteUser = async (selectedUser) => {
    setDeleteTargetUser(selectedUser);
    setDeletePassword('');
    setDeleteDialogOpen(true);
    setError('');
    setSuccess('');
  };

  const closeDeleteDialog = () => {
    if (saving) {
      return;
    }
    setDeleteDialogOpen(false);
    setDeleteTargetUser(null);
    setDeletePassword('');
  };

  const confirmDeleteUser = async () => {
    if (!deleteTargetUser) {
      return;
    }

    if (!deletePassword.trim()) {
      setError('Saisis le mot de passe de ton compte pour confirmer la suppression.');
      return;
    }

    setSaving(true);
    setError('');
    setSuccess('');

    try {
      await api.delete(`auth/utilisateurs/${deleteTargetUser.id}/`, {
        data: { confirmation_password: deletePassword },
      });
      setUsers((currentUsers) => currentUsers.filter((managedUser) => managedUser.id !== deleteTargetUser.id));
      setSuccess('Compte supprimé avec succès.');
      await loadManagementData();
      resetForm();
      setDeleteDialogOpen(false);
      setDeleteTargetUser(null);
      setDeletePassword('');
    } catch (requestError) {
      const apiMessage = requestError?.response?.data?.error
        || requestError?.response?.data?.detail
        || Object.values(requestError?.response?.data || {})[0];
      setError(apiMessage || 'Suppression refusée ou confirmation invalide.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box
      sx={{
        ...shellSx,
      }}
    >
      <Box sx={{ width: '100%' }}>
        <AppSidebar />

        <Box sx={{ minWidth: 0, '@media (min-width:768px)': { ml: '252px' } }}>
          <Paper elevation={0} sx={heroSx}>
            {/* Cercles décoratifs */}
            <Box sx={{ position: 'absolute', inset: 'auto -80px -80px auto', width: 240, height: 240, borderRadius: '50%', background: 'rgba(255,255,255,0.07)', pointerEvents: 'none' }} />
            <Box sx={{ position: 'absolute', top: -40, left: '38%', width: 180, height: 180, borderRadius: '50%', background: 'rgba(255,255,255,0.04)', pointerEvents: 'none' }} />
            {/* Schéma rein — arrière-plan décoratif */}
            <Box component="img" src="/kidney-landing.png" alt="" sx={{ position: 'absolute', bottom: -50, right: -10, height: 320, opacity: 0.22, pointerEvents: 'none', userSelect: 'none', filter: 'brightness(2) saturate(0)', transform: 'rotate(-8deg)' }} />

            <Stack direction={{ xs: 'column', lg: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', lg: 'center' }} spacing={3} sx={{ position: 'relative' }}>
              {/* Gauche — texte */}
              <Box>
                <Typography variant="body1" sx={{ mb: 1.5, color: 'rgba(255,255,255,0.90)', fontWeight: 400, fontSize: '1rem' }}>
                  Bienvenue,{' '}
                  <Box component="span" sx={{ fontWeight: 800, color: '#fff' }}>
                    {roleLabels[user?.role] || 'Utilisateur'}
                  </Box>
                </Typography>
                <Typography variant="h3" fontWeight={900} sx={{ letterSpacing: '-.04em', lineHeight: 1.02, color: '#FFFFFF', textShadow: '0 2px 10px rgba(10,43,62,0.30)' }}>
                  {t('dashboardTitle')}
                </Typography>
                <Typography variant="body1" sx={{ mt: 1, maxWidth: 520, color: 'rgba(255,255,255,0.85)', fontSize: '0.97rem' }}>
                  {t('dashboardSubtitle')}
                </Typography>
                <Button variant="contained" onClick={() => navigate('/monitor')} sx={{ mt: 2, borderRadius: 999, textTransform: 'none', bgcolor: 'rgba(255,255,255,0.16)', color: '#fff', border: '1px solid rgba(255,255,255,0.24)', boxShadow: 'none', '&:hover': { bgcolor: 'rgba(255,255,255,0.24)', boxShadow: 'none' } }}>
                  {t('dashboardOpenMonitor')}
                </Button>
              </Box>

              {/* Droite — stats inline (admin/chef uniquement) */}
              {isAdminScope && <Stack direction={{ xs: 'row', sm: 'row' }} spacing={1.5} flexWrap="wrap" useFlexGap sx={{ flexShrink: 0 }}>
                {[
                  { label: 'Actifs',        value: stats.activeUsers,     filterKey: 'active'       },
                  { label: 'Inactifs',      value: stats.inactiveUsers,   filterKey: 'inactive'     },
                  { label: 'Super Admins',  value: stats.adminsCount,     filterKey: 'super_admin'  },
                  { label: 'Chefs Service', value: stats.chefsCount,      filterKey: 'chef_service' },
                  { label: 'Professeurs',   value: stats.professorsCount, filterKey: 'professeur'   },
                  { label: 'Résidents',     value: stats.residentsCount,  filterKey: 'resident'     },
                  { label: 'Rôles',         value: stats.rolesCount,      filterKey: null           },
                ].map(({ label, value, filterKey }) => {
                  const isActive = filterKey && activeFilter === filterKey;
                  return (
                    <Box
                      key={label}
                      onClick={() => filterKey && setActiveFilter((f) => f === filterKey ? null : filterKey)}
                      sx={{
                        px: 2.5, py: 1.75,
                        borderRadius: 3,
                        background: isActive ? 'rgba(255,255,255,0.32)' : 'rgba(255,255,255,0.12)',
                        border: isActive ? '2px solid rgba(255,255,255,0.70)' : '1px solid rgba(255,255,255,0.18)',
                        backdropFilter: 'blur(8px)',
                        minWidth: 90, textAlign: 'center',
                        cursor: filterKey ? 'pointer' : 'default',
                        transition: 'all 0.18s',
                        transform: isActive ? 'translateY(-2px)' : 'none',
                        boxShadow: isActive ? '0 6px 18px rgba(0,0,0,0.18)' : 'none',
                        '&:hover': filterKey ? { background: 'rgba(255,255,255,0.22)', transform: 'translateY(-1px)' } : {},
                      }}
                    >
                      <Typography variant="h5" fontWeight={900} sx={{ color: '#fff', letterSpacing: '-.03em' }}>{value}</Typography>
                      <Typography sx={{ fontSize: 11, color: isActive ? '#fff' : 'rgba(255,255,255,0.70)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', mt: 0.25 }}>{label}</Typography>
                    </Box>
                  );
                })}
              </Stack>}
            </Stack>
          </Paper>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 3 }}>{success}</Alert>}

      <Grid container spacing={3}>
        <Grid item xs={12} xl={isAdminScope ? 4 : 5}>
          <Stack spacing={3} sx={isAdminScope ? { position: { xl: 'sticky' }, top: { xl: 24 } } : undefined}>
            <Card elevation={0} sx={subtlePanelSx}>
              <Box sx={{ height: 10, background: `linear-gradient(90deg, #0D4D63 0%, #1A8FA8 55%, #D47A8E 100%)` }} />
              <CardContent sx={{ p: 0 }}>
                <Box sx={{ p: 3 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2} sx={{ mb: 2.25 }}>
                    <Box>
                      <Typography variant="overline" color="primary.main" fontWeight={800}>
                        {t("dashboardSessionActive")}
                      </Typography>
                      <Typography variant="h5" fontWeight={900} sx={{ mt: 0.5 }}>
                        {t('dashboardConnectedProfile')}
                      </Typography>
                    </Box>
                    <Chip label={roleLabels[user?.role] || 'Utilisateur'} sx={{ fontWeight: 800, bgcolor: 'rgba(26, 107, 138, 0.10)', color: DASHBOARD_THEME.medicalBlue }} />
                  </Stack>

                  <Box sx={{ p: 2.25, borderRadius: 4, background: 'linear-gradient(135deg, rgba(44,105,117,0.10), rgba(104,178,160,0.08))', border: '1px solid rgba(108, 178, 160, 0.18)', mb: 2.5 }}>
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Avatar sx={{ width: 58, height: 58, bgcolor: DASHBOARD_THEME.deepNavy, fontWeight: 900, boxShadow: '0 10px 24px rgba(10, 43, 62, 0.25)' }}>
                        {(user?.prenom?.[0] || '') + (user?.nom?.[0] || '')}
                      </Avatar>
                      <Box>
                        <Typography variant="caption" color="text.secondary">{t('dashboardFullName')}</Typography>
                        <Typography variant="h6" fontWeight={900} sx={{ lineHeight: 1.15 }}>
                          {user?.prenom || '-'} {user?.nom || ''}
                        </Typography>
                      </Box>
                    </Stack>
                  </Box>

                  <Stack spacing={1.5}>
                    <Stack direction="row" spacing={1.25} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={user?.email || '-'} variant="outlined" sx={{ borderRadius: 2 }} />
                      <Chip size="small" label={user?.telephone || t('dashboardUserPhone')} variant="outlined" sx={{ borderRadius: 2 }} />
                    </Stack>
                    <Divider sx={{ my: 0.5 }} />
                    <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
                      <Box sx={{ minWidth: 110 }}>
                        <Typography variant="caption" color="text.secondary">Nom</Typography>
                        <Typography variant="body1" fontWeight={600}>{user?.nom || '-'}</Typography>
                      </Box>
                      <Box sx={{ minWidth: 110 }}>
                        <Typography variant="caption" color="text.secondary">Prénom</Typography>
                        <Typography variant="body1" fontWeight={600}>{user?.prenom || '-'}</Typography>
                      </Box>
                      <Box sx={{ minWidth: 180 }}>
                        <Typography variant="caption" color="text.secondary">Rôle</Typography>
                        <Typography variant="body1" fontWeight={600}>{roleLabels[user?.role] || '-'}</Typography>
                      </Box>
                    </Stack>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          </Stack>
        </Grid>

        {!isAdminScope && (
          <Grid item xs={12} xl={7}>
            <Card elevation={0} sx={subtlePanelSx}>
              <Box sx={{ height: 10, background: `linear-gradient(90deg, #0D4D63 0%, #1A8FA8 55%, #D47A8E 100%)` }} />
              <CardContent sx={{ p: 3 }}>
                <Typography variant="h6" fontWeight={800} sx={{ color: DASHBOARD_THEME.deepNavy, mb: 2 }}>
                  Activité récente
                </Typography>
                {recentActivity.length === 0 ? (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="text.secondary">Aucune activité enregistrée pour le moment.</Typography>
                  </Box>
                ) : (
                  <Stack spacing={1.5}>
                    {recentActivity.map((item) => {
                      const isApproved = item.action?.startsWith('PREPROCESSING_APPROVED');
                      const isRejected = item.action?.startsWith('PREPROCESSING_REJECTED');
                      const isExpanded = expandedActivity === item.id;

                      // Parse action string: "TYPE: detail — comment"
                      const actionParts = (item.action || '').split(': ');
                      const actionType = actionParts[0] || '';
                      const actionDetail = actionParts.slice(1).join(': ') || '';
                      const mainDetail = actionDetail.split(' — ')[0] || '';
                      const commentPart = actionDetail.includes(' — ') ? actionDetail.split(' — ').slice(1).join(' — ') : null;

                      // Navigation target
                      const navTarget = actionType.includes('PATIENT') ? '/patients'
                        : actionType.includes('PREDICTION') ? '/modele-ai'
                        : actionType.includes('PREPROCESSING') ? '/patients?tab=preprocessing'
                        : null;

                      return (
                        <Box
                          key={item.id}
                          onClick={() => setExpandedActivity(isExpanded ? null : item.id)}
                          sx={{
                            borderRadius: 3, overflow: 'hidden',
                            border: '1.5px solid',
                            borderColor: isApproved ? 'rgba(30,158,132,0.35)' : isRejected ? 'rgba(212,122,142,0.35)' : isExpanded ? DASHBOARD_THEME.medicalBlue : DASHBOARD_THEME.borderLight,
                            cursor: 'pointer',
                            transition: 'all 0.18s ease',
                            '&:hover': { borderColor: DASHBOARD_THEME.medicalBlue, boxShadow: '0 2px 8px rgba(26,107,138,0.10)' },
                          }}
                        >
                          {/* Ligne principale */}
                          <Box sx={{
                            display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5,
                            bgcolor: isApproved ? 'rgba(30,158,132,0.06)' : isRejected ? 'rgba(212,122,142,0.06)' : isExpanded ? 'rgba(26,107,138,0.04)' : 'rgba(0,0,0,0.02)',
                          }}>
                            <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: item.color, flexShrink: 0 }} />
                            <Typography variant="body2" fontWeight={isApproved || isRejected ? 700 : 600} sx={{ flex: 1, color: isApproved || isRejected ? item.color : DASHBOARD_THEME.deepNavy }}>
                              {item.label}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, mr: 0.5 }}>
                              {item.date ? new Date(item.date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                            </Typography>
                            <Box sx={{ color: DASHBOARD_THEME.textMuted, fontSize: 10, transition: 'transform 0.2s', transform: isExpanded ? 'rotate(180deg)' : 'none' }}>▾</Box>
                          </Box>

                          {/* Détails expandés */}
                          {isExpanded && (
                            <Box sx={{ px: 2, pb: 1.5, pt: 0.5, borderTop: `1px solid ${DASHBOARD_THEME.borderLight}`, bgcolor: '#fafcfe' }}>
                              {mainDetail && (
                                <Typography variant="caption" sx={{ display: 'block', color: DASHBOARD_THEME.textMuted, mb: 0.5 }}>
                                  {mainDetail}
                                </Typography>
                              )}
                              {commentPart && (
                                <Typography variant="caption" sx={{ display: 'block', color: isRejected ? DASHBOARD_THEME.softRose : DASHBOARD_THEME.medicalBlue, fontStyle: 'italic', mb: 0.5 }}>
                                  💬 {commentPart}
                                </Typography>
                              )}
                              {item.entite_id && (
                                <Typography variant="caption" sx={{ display: 'block', color: DASHBOARD_THEME.textMuted }}>
                                  Référence : {item.entite} #{item.entite_id}
                                </Typography>
                              )}
                              {navTarget && (
                                <Box
                                  component="span"
                                  onClick={(e) => { e.stopPropagation(); navigate(navTarget); }}
                                  sx={{ display: 'inline-block', mt: 1, fontSize: 11, fontWeight: 700, color: DASHBOARD_THEME.medicalBlue, cursor: 'pointer', textDecoration: 'underline', '&:hover': { color: DASHBOARD_THEME.deepNavy } }}
                                >
                                  Voir →
                                </Box>
                              )}
                            </Box>
                          )}
                        </Box>
                      );
                    })}
                  </Stack>
                )}
              </CardContent>
            </Card>
          </Grid>
        )}

        {isAdminScope && (
          <Grid item xs={12} xl={8}>
            <Stack spacing={3}>
              {showManagementPanel && (
                <Card elevation={0} sx={{ ...softCardSx }}>
                  <CardContent sx={{ p: 3 }}>
                      <Typography variant="h6" fontWeight={800} sx={{ color: DASHBOARD_THEME.deepNavy, mb: 1.25 }}>
                      {t('dashboardUserManagement')}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2.25, lineHeight: 1.7 }}>
                      {t('dashboardUserManagementDesc')}
                    </Typography>

                    <Box component="form" onSubmit={handleSaveUser} sx={{ display: 'grid', gap: 2.25 }}>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Email"
                        name="email"
                        value={form.email}
                        onChange={handleChange}
                        required
                        fullWidth
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label={t('dashboardUserPhone')}
                        name="telephone"
                        value={form.telephone}
                        onChange={handleChange}
                        fullWidth
                        size="small"
                        placeholder="+212 6 12 34 56 78"
                        inputMode="tel"
                        helperText="Numéro du contact principal du compte."
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <CallOutlinedIcon fontSize="small" />
                            </InputAdornment>
                          ),
                        }}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Nom"
                        name="nom"
                        value={form.nom}
                        onChange={handleChange}
                        required
                        fullWidth
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        label="Prénom"
                        name="prenom"
                        value={form.prenom}
                        onChange={handleChange}
                        required
                        fullWidth
                        size="small"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        select
                        label="Rôle"
                        name="role_id"
                        value={form.role_id}
                        onChange={handleChange}
                        required
                        fullWidth
                        size="small"
                      >
                        <MenuItem value="">{t('dashboardUserSelectRole')}</MenuItem>
                        {roles.map((role) => (
                          <MenuItem key={role.id} value={role.id}>
                            {role.label || role.nom}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        select
                        label="Statut"
                        name="is_active"
                        value={form.is_active ? 'true' : 'false'}
                        onChange={(event) => setForm((current) => ({
                          ...current,
                          is_active: event.target.value === 'true',
                        }))}
                        fullWidth
                        size="small"
                      >
                        <MenuItem value="true">Actif</MenuItem>
                        <MenuItem value="false">Inactif</MenuItem>
                      </TextField>
                    </Grid>
                  </Grid>

                  {form.id && (
                    <TextField
                      label="Mot de passe de validation"
                      type="password"
                      value={adminPassword}
                      onChange={(event) => setAdminPassword(event.target.value)}
                      fullWidth
                      required
                      size="small"
                      helperText={t('dashboardSaveConfirmationPassword')}
                    />
                  )}

                  {!form.id && (
                    <TextField
                      label="Mot de passe du nouveau compte"
                      type="password"
                      name="password"
                      value={form.password}
                      onChange={handleChange}
                      fullWidth
                      required
                      size="small"
                      helperText="Ce mot de passe sera utilisé par l’utilisateur créé."
                    />
                  )}

                  {form.id && (
                    <TextField
                      label="Nouveau mot de passe"
                      type="password"
                      name="password"
                      value={form.password}
                      onChange={handleChange}
                      fullWidth
                      size="small"
                      helperText="Laisser vide pour conserver le mot de passe actuel."
                    />
                  )}

                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                      <Button type="submit" variant="contained" disabled={saving} fullWidth>
                        {form.id ? t('dashboardUpdateButton') : t('dashboardCreateButton')}
                      </Button>
                      <Button type="button" variant="outlined" onClick={resetForm} fullWidth>
                        {t('dashboardResetButton')}
                      </Button>
                    </Stack>
                  </Box>
                  </CardContent>
                </Card>
              )}

              <Card elevation={0} sx={softCardSx}>
                <CardContent sx={{ p: 3 }}>
                  <Stack direction={{ xs: 'column', md: 'row' }} alignItems={{ xs: 'stretch', md: 'center' }} justifyContent="space-between" spacing={2.25} sx={{ mb: 2.25 }}>
                    <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap">
                      <Typography variant="h6" fontWeight={800} sx={{ color: DASHBOARD_THEME.deepNavy }}>
                        Comptes gérés
                      </Typography>
                      {activeFilter && (
                        <Chip
                          size="small"
                          label={{
                            active: 'Actifs', inactive: 'Inactifs',
                            super_admin: 'Super Admins', chef_service: 'Chefs Service',
                            professeur: 'Professeurs', resident: 'Résidents',
                          }[activeFilter]}
                          onDelete={() => setActiveFilter(null)}
                          sx={{ fontWeight: 700, bgcolor: DASHBOARD_THEME.medicalBlue, color: '#fff', '& .MuiChip-deleteIcon': { color: 'rgba(255,255,255,0.8)' } }}
                        />
                      )}
                      {isAdminScope && (
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => setShowManagementPanel((current) => !current)}
                          sx={{
                            borderRadius: 999,
                            textTransform: 'none',
                            borderColor: DASHBOARD_THEME.medicalBlue,
                            color: DASHBOARD_THEME.medicalBlue,
                            bgcolor: 'white',
                            '&:hover': {
                              borderColor: DASHBOARD_THEME.softRose,
                              color: DASHBOARD_THEME.deepNavy,
                              bgcolor: 'rgba(212,122,142,0.08)',
                            },
                          }}
                        >
                          {showManagementPanel ? 'Masquer' : 'Afficher'}
                        </Button>
                      )}
                    </Stack>
                    <TextField
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Rechercher un utilisateur..."
                      size="small"
                      sx={{ width: { xs: '100%', sm: 360 }, bgcolor: 'white', borderRadius: 2 }}
                    />
                  </Stack>
                  <Grid container spacing={2}>
                    {manageableUsers.length ? manageableUsers.map((managedUser) => (
                      <Grid item xs={12} sm={6} md={4} key={managedUser.id}>
                        <Card
                          elevation={0}
                          sx={{
                            borderRadius: 3,
                            bgcolor: DASHBOARD_THEME.white,
                            border: `1px solid ${DASHBOARD_THEME.borderLight}`,
                            borderTop: `4px solid transparent`,
                            borderImage: managedUser.is_active
                              ? 'linear-gradient(90deg, #1A8FA8, #D47A8E) 1'
                              : `linear-gradient(90deg, ${DASHBOARD_THEME.softRose}, #C46B82) 1`,
                            minHeight: 250,
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                            boxShadow: '0 8px 22px rgba(15, 23, 42, 0.04)',
                            transition: 'transform 180ms ease, box-shadow 180ms ease',
                            '&:hover': {
                              transform: 'translateY(-2px)',
                              boxShadow: '0 14px 30px rgba(15, 23, 42, 0.08)',
                            },
                          }}
                        >
                        <CardContent sx={{ p: 2.5 }}>
                          <Stack spacing={1.5}>
                            <Stack direction="row" spacing={2} alignItems="center">
                              <Avatar sx={{ width: 48, height: 48, fontWeight: 700, background: `linear-gradient(135deg, #1A8FA8, #D47A8E)`, boxShadow: '0 6px 16px rgba(26,107,138,0.20)' }}>
                                {(managedUser.nom?.[0] || managedUser.prenom?.[0] || 'U').toUpperCase()}
                              </Avatar>
                              <Box>
                                <Typography variant="subtitle1" fontWeight={800} sx={{ color: DASHBOARD_THEME.deepNavy }}>
                                  {managedUser.nom || '-'} {managedUser.prenom || ''}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {managedUser.email || '-'}
                                </Typography>
                              </Box>
                            </Stack>

                            <Stack direction="row" spacing={1} alignItems="center">
                              <Chip label={managedUser.is_active ? 'Actif' : 'Inactif'} color={managedUser.is_active ? 'success' : 'error'} size="small" />
                            </Stack>

                            <Stack spacing={0.75}>
                              <Typography variant="caption" color="text.secondary">{t('dashboardUserPhone')}</Typography>
                              <Typography variant="body2">{managedUser.telephone || '-'}</Typography>
                            </Stack>

                            <Stack spacing={0.75}>
                              <Typography variant="caption" color="text.secondary">Rôle</Typography>
                              <Typography variant="body2">{managedUser.role?.label || managedUser.role?.nom || '-'}</Typography>
                            </Stack>
                          </Stack>
                        </CardContent>

                        <Box sx={{ p: 2.5, pt: 0 }}>
                          <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1}>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => beginEdit(managedUser)}
                              aria-label="Éditer le compte"
                              sx={{ minWidth: 0, px: 1.1, borderRadius: 2 }}
                            >
                              <EditOutlinedIcon fontSize="small" />
                            </Button>
                            <Button
                              size="small"
                              color="error"
                              variant="outlined"
                              onClick={() => handleDeleteUser(managedUser)}
                              aria-label="Révoquer le compte"
                              sx={{ minWidth: 0, px: 1.1, borderRadius: 2 }}
                            >
                              <DeleteOutlineOutlinedIcon fontSize="small" />
                            </Button>
                          </Stack>
                        </Box>
                      </Card>
                    </Grid>
                  )) : (
                    <Grid item xs={12}>
                      <Typography align="center" color="text.secondary">
                        Aucun compte disponible.
                      </Typography>
                    </Grid>
                  )}
                </Grid>
              </CardContent>
            </Card>
            </Stack>
          </Grid>
        )}
      </Grid>

        </Box>
      </Box>

      <Dialog open={deleteDialogOpen} onClose={closeDeleteDialog} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ fontWeight: 800 }}>Confirmer la suppression</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="warning">
              {deleteTargetUser
                ? `Voulez-vous vraiment supprimer le compte ${deleteTargetUser.email} ?`
                : 'Voulez-vous vraiment supprimer ce compte ?'}
            </Alert>
            <Typography variant="body2" color="text.secondary">
              Si oui, saisis le mot de passe de ton propre compte pour valider l’opération.
            </Typography>
            <TextField
              label="Mot de passe de validation"
              type="password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
              fullWidth
              size="small"
              autoFocus
            />
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button onClick={closeDeleteDialog} variant="outlined" disabled={saving}>
            Annuler
          </Button>
          <Button onClick={confirmDeleteUser} variant="contained" color="error" disabled={saving}>
            {saving ? 'Suppression...' : 'Supprimer'}
          </Button>
        </DialogActions>
      </Dialog>

    </Box>
  );
}

export default Dashboard;