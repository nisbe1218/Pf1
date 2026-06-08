import React, { useContext, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
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

  const userInitials = useMemo(() => {
    const first = (user?.prenom || '').trim();
    const last = (user?.nom || '').trim();
    const initials = `${first[0] || ''}${last[0] || ''}`.trim();
    return initials || 'U';
  }, [user?.nom, user?.prenom]);

  const canChangePassword = !!user?.role;



  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
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
      <Box sx={{
        minHeight: '100vh',
        ml: { xs: 0, md: `${APP_SIDEBAR_WIDTH}px` },
        width: { xs: '100%', md: `calc(100% - ${APP_SIDEBAR_WIDTH}px)` },
        background: PROFILE_THEME.pageBackground,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'flex-start',
        p: { xs: 2, md: 4 },
      }}>
        <Box sx={{ width: '100%', maxWidth: 520 }}>
          <Stack spacing={3}>

            {/* Avatar + nom + rôle */}
            <Box sx={{ textAlign: 'center', p: 3, borderRadius: 3, border: `1px solid ${PROFILE_THEME.border}`, background: PROFILE_THEME.panelBackground, boxShadow: '0 12px 30px rgba(31,42,68,.06)' }}>
              <Avatar sx={{ width: 80, height: 80, bgcolor: PROFILE_THEME.deepNavy, color: 'white', fontWeight: 900, fontSize: 28, mx: 'auto', mb: 2, boxShadow: '0 8px 20px rgba(31,42,68,.18)' }}>
                {userInitials}
              </Avatar>
              <Typography variant="h6" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy, letterSpacing: -0.5 }}>
                {user?.prenom || ''} {user?.nom || ''}
              </Typography>
              <Chip label={user?.role || '-'} size="small" sx={{ mt: 1.5, bgcolor: 'rgba(79,109,154,.10)', color: PROFILE_THEME.medicalBlue, fontWeight: 800 }} />
            </Box>

            {/* Informations du compte */}
            <Card sx={softCardSx}>
              <CardContent sx={{ p: 2.5 }}>
                <Typography variant="overline" fontWeight={900} sx={{ color: PROFILE_THEME.medicalBlue, letterSpacing: 1.2, fontSize: '0.7rem', display: 'block', mb: 1.5 }}>
                  {t('profileAccountInfo')}
                </Typography>
                <Stack spacing={1.5}>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>Email</Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ wordBreak: 'break-word', color: PROFILE_THEME.deepNavy }}>{user?.email || '-'}</Typography>
                  </Box>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>{t('role')}</Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: PROFILE_THEME.deepNavy }}>{user?.role || '-'}</Typography>
                  </Box>
                  <Box sx={infoRowSx}>
                    <Typography variant="caption" color="text.secondary" fontWeight={700}>{t('telephone')}</Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: PROFILE_THEME.deepNavy }}>{user?.telephone || '-'}</Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

            {/* Langue */}
            <Card sx={softCardSx}>
              <CardContent sx={{ p: 2.5 }}>
                <Stack spacing={1.5}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <LanguageOutlinedIcon sx={{ color: PROFILE_THEME.medicalBlue, fontSize: 20 }} />
                    <Typography variant="subtitle2" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy }}>{t('languageSectionTitle')}</Typography>
                  </Stack>
                  <Stack direction="row" spacing={1}>
                    <Button type="button" variant={language === 'fr' ? 'contained' : 'outlined'} onClick={() => setLanguage('fr')} fullWidth sx={{ minHeight: 42, borderRadius: 999, textTransform: 'none', fontWeight: 800 }}>{t('french')}</Button>
                    <Button type="button" variant={language === 'en' ? 'contained' : 'outlined'} onClick={() => setLanguage('en')} fullWidth sx={{ minHeight: 42, borderRadius: 999, textTransform: 'none', fontWeight: 800 }}>{t('english')}</Button>
                  </Stack>
                </Stack>
              </CardContent>
            </Card>

            {/* Modifier mot de passe */}
            <Card sx={softCardSx}>
              <CardContent sx={{ p: 2.5 }}>
                <Stack spacing={2.5}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <LockOutlinedIcon sx={{ color: PROFILE_THEME.softRose, fontSize: 22 }} />
                    <Box>
                      <Typography variant="h6" fontWeight={900} sx={{ color: PROFILE_THEME.deepNavy, fontSize: 15 }}>{t('changePasswordTitle')}</Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ fontSize: 12 }}>{t('profilePasswordHint')}</Typography>
                    </Box>
                  </Stack>

                  {message.text && (
                    <Alert severity={message.type} onClose={() => setMessage({ type: '', text: '' })}>{message.text}</Alert>
                  )}

                  <Box component="form" onSubmit={handleSubmit}>
                    <Stack spacing={2}>
                      <TextField label={t('currentPassword')} type="password" name="currentPassword" value={form.currentPassword} onChange={handleChange} fullWidth size="small" disabled={loading} />
                      <TextField label={t('newPassword')} type="password" name="newPassword" value={form.newPassword} onChange={handleChange} fullWidth size="small" disabled={loading} />
                      <TextField label={t('confirmPassword')} type="password" name="confirmPassword" value={form.confirmPassword} onChange={handleChange} fullWidth size="small" disabled={loading} />
                      <Stack direction="row" spacing={1.5}>
                        <Button type="submit" variant="contained" disabled={loading} sx={{ flex: 1, minHeight: 44, borderRadius: 999, background: PROFILE_THEME.deepNavy, textTransform: 'none', fontWeight: 800, '&:hover': { background: PROFILE_THEME.medicalBlue } }}>
                          {loading ? <CircularProgress size={18} sx={{ mr: 1, color: 'white' }} /> : null}
                          {loading ? '...' : t('submitPassword')}
                        </Button>
                        <Button type="button" variant="outlined" onClick={() => { setForm({ currentPassword: '', newPassword: '', confirmPassword: '' }); setMessage({ type: '', text: '' }); }} disabled={loading}
                          sx={{ flex: 1, minHeight: 44, borderRadius: 999, textTransform: 'none', fontWeight: 800, borderColor: PROFILE_THEME.border, color: PROFILE_THEME.deepNavy, '&:hover': { borderColor: PROFILE_THEME.medicalBlue } }}>
                          {t('cancel')}
                        </Button>
                      </Stack>
                    </Stack>
                  </Box>
                </Stack>
              </CardContent>
            </Card>

          </Stack>
        </Box>
      </Box>
    </>
  );
}

export default Profile;
