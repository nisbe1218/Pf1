import React, { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Button,
  Box,
  Chip,
  Fab,
  IconButton,
  Paper,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import NoteAltRoundedIcon from '@mui/icons-material/NoteAltRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import MinimizeRoundedIcon from '@mui/icons-material/MinimizeRounded';
import RestartAltRoundedIcon from '@mui/icons-material/RestartAltRounded';
import api from '../../services/api/axios';
import { AuthContext } from '../../context/AuthContext';
import { useLanguage } from '../../context/LanguageContext';

const AUTOSAVE_DELAY_MS = 800;

function NotesFab() {
  const { user } = useContext(AuthContext);
  const { t } = useLanguage();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState('');
  const [lastSavedNotes, setLastSavedNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [hasLoaded, setHasLoaded] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const saveTimerRef = useRef(null);

  const isAuthenticated = Boolean(user?.id);

  const clearSaveTimer = () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
  };

  const fetchNotes = useCallback(async () => {
    if (!isAuthenticated) {
      setNotes('');
      setLastSavedNotes('');
      setHasLoaded(false);
      return;
    }

    try {
      setLoading(true);
      setErrorMessage('');
      const response = await api.get('auth/notes/');
      const savedNotes = response?.data?.notes || '';
      setNotes(savedNotes);
      setLastSavedNotes(savedNotes);
      setStatus('saved');
      setLastSavedAt(new Date());
    } catch (error) {
      setErrorMessage(t('notesLoadError'));
      setStatus('error');
    } finally {
      setLoading(false);
      setHasLoaded(true);
    }
  }, [isAuthenticated, t]);

  const persistNotes = useCallback(async (nextNotes) => {
    if (!isAuthenticated) {
      return;
    }

    try {
      setStatus('saving');
      setErrorMessage('');
      await api.put('auth/notes/', { notes: nextNotes });
      setLastSavedNotes(nextNotes);
      setStatus('saved');
      setLastSavedAt(new Date());
    } catch (error) {
      setStatus('error');
      setErrorMessage(t('notesAutoSaveError'));
    }
  }, [isAuthenticated, t]);

  useEffect(() => {
    fetchNotes();
    return clearSaveTimer;
  }, [fetchNotes, user?.id]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [open]);

  useEffect(() => {
    if (!hasLoaded || !isAuthenticated) {
      return;
    }

    if (notes === lastSavedNotes) {
      return;
    }

    clearSaveTimer();
    setStatus('pending');

    saveTimerRef.current = setTimeout(() => {
      persistNotes(notes);
    }, AUTOSAVE_DELAY_MS);

    return clearSaveTimer;
  }, [notes, lastSavedNotes, hasLoaded, persistNotes, isAuthenticated]);

  const statusChip = useMemo(() => {
    if (status === 'saving' || status === 'pending') {
      return <Chip size="small" label={t('notesSaving')} sx={{ bgcolor: '#ffe2ea', color: '#8a2a48', fontWeight: 600 }} />;
    }
    if (status === 'saved') {
      return <Chip size="small" label={t('notesSaved')} sx={{ bgcolor: '#ffd3e2', color: '#7a2440', fontWeight: 600 }} />;
    }
    if (status === 'error') {
      return <Chip size="small" label={t('notesError')} sx={{ bgcolor: '#ffcad6', color: '#8e1f3f', fontWeight: 600 }} />;
    }
    return <Chip size="small" label={t('notesReady')} sx={{ bgcolor: '#fdebf1', color: '#8a2a48', fontWeight: 600 }} />;
  }, [status, t]);

  const lastSavedLabel = useMemo(() => {
    if (!lastSavedAt) {
      return t('notesNoSave');
    }
    return `${t('notesLastSaved')} ${lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }, [lastSavedAt, t]);

  const publicPaths = ['/', '/login', '/unauthorized'];
  const isOnPublicPage = publicPaths.some((p) => location.pathname === p || location.pathname.startsWith(p + '/'));

  if (!isAuthenticated || isOnPublicPage) {
    return null;
  }

  return (
    <>
      <Tooltip title={t('notesOpen')} arrow placement="left">
        <Fab
          color="secondary"
          aria-label={t('notesOpen')}
          onClick={() => setOpen((current) => !current)}
          sx={{
            position: 'fixed',
            right: { xs: 16, md: 24 },
            bottom: { xs: 18, md: 26 },
            zIndex: (theme) => theme.zIndex.drawer + 5,
            width: { xs: 58, md: 64 },
            height: { xs: 58, md: 64 },
            boxShadow: '0 16px 36px rgba(156, 49, 90, 0.42)',
            background: 'linear-gradient(142deg, #b13e68 0%, #cf6f94 45%, #e59cb7 100%)',
            '&:hover': {
              background: 'linear-gradient(142deg, #9f345d 0%, #c76089 45%, #dc8ca9 100%)',
              transform: 'translateY(-2px) scale(1.03)',
            },
            transition: 'all 0.2s ease',
          }}
        >
          <NoteAltRoundedIcon sx={{ fontSize: { xs: 28, md: 32 } }} />
        </Fab>
      </Tooltip>

      {open && (
        <Paper
          elevation={0}
          sx={{
            position: 'fixed',
            right: { xs: 12, md: 24 },
            bottom: { xs: 88, md: 98 },
            width: { xs: 'calc(100vw - 24px)', sm: 390, md: 410 },
            maxWidth: 'calc(100vw - 24px)',
            zIndex: (theme) => theme.zIndex.drawer + 4,
            borderRadius: 4,
            border: '1px solid rgba(190, 109, 142, 0.32)',
            boxShadow: '0 24px 54px rgba(109, 28, 57, 0.28)',
            overflow: 'hidden',
            animation: 'notesPopIn 0.22s ease-out',
            '@keyframes notesPopIn': {
              from: { opacity: 0, transform: 'translateY(12px) scale(0.97)' },
              to: { opacity: 1, transform: 'translateY(0) scale(1)' },
            },
          }}
      >
        <Box
          sx={{
            maxHeight: { xs: '72vh', md: '74vh' },
            display: 'flex',
            flexDirection: 'column',
            background: 'linear-gradient(175deg, #fff5f9 0%, #ffffff 42%, #fff0f5 100%)',
          }}
        >
          <Box
            sx={{
              px: 2,
              py: 1.4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(190, 109, 142, 0.26)',
              background: 'linear-gradient(120deg, #fff8fb 0%, #fff0f6 100%)',
              color: '#b03f69',
            }}
          >
            <Typography variant="subtitle1" sx={{ fontWeight: 800, fontStyle: 'italic', lineHeight: 1.15, color: '#b03f69' }}>
              {t('notesTitle')}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.3 }}>
              <IconButton onClick={() => setOpen(false)} sx={{ color: '#b03f69' }} aria-label={t('notesMinimize')} size="small">
                <MinimizeRoundedIcon fontSize="small" />
              </IconButton>
              <IconButton onClick={() => setOpen(false)} sx={{ color: '#b03f69' }} aria-label={t('notesClose')} size="small">
                <CloseRoundedIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>

          <Box sx={{ px: 2, py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
            {statusChip}
            {loading ? (
              <Typography variant="caption" color="text.secondary">{t('notesLoading')}</Typography>
            ) : (
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>{lastSavedLabel}</Typography>
            )}
          </Box>

          <Box sx={{ px: 2, pb: 2, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 1 }}>
            <TextField
              autoFocus
              multiline
              fullWidth
              minRows={12}
              maxRows={20}
              placeholder={t('notesPlaceholder')}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              disabled={loading}
              sx={{
                flex: 1,
                '& .MuiOutlinedInput-root': {
                  alignItems: 'flex-start',
                  borderRadius: 2.5,
                  backgroundColor: '#ffffff',
                  '& fieldset': {
                    borderColor: 'rgba(195, 116, 150, 0.45)',
                  },
                  '&:hover fieldset': {
                    borderColor: 'rgba(179, 70, 112, 0.72)',
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: '#b03f69',
                    borderWidth: '2px',
                  },
                },
                '& textarea': {
                  fontFamily: '"Segoe UI", "Tahoma", sans-serif',
                  lineHeight: 1.6,
                  fontSize: '0.95rem',
                  color: '#3f1830',
                },
              }}
            />

            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {notes.length} {t('notesCharCount')}
              </Typography>
              <Button
                size="small"
                startIcon={<RestartAltRoundedIcon fontSize="small" />}
                onClick={() => setNotes('')}
                sx={{
                  color: '#9a2f58',
                  bgcolor: '#fde7ef',
                  borderRadius: 2,
                  '&:hover': {
                    bgcolor: '#fad9e5',
                  },
                }}
              >
                {t('notesClear')}
              </Button>
            </Box>

            {!!errorMessage && (
              <Typography variant="caption" color="error">
                {errorMessage}
              </Typography>
            )}
          </Box>
        </Box>
        </Paper>
      )}
    </>
  );
}

export default NotesFab;
