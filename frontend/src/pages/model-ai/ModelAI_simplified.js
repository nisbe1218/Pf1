import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Tab,
  Tabs,
  Typography,
  Button,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  Chip,
  Stack,
  TextField,
  InputAdornment,
  Divider,
  LinearProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RefreshIcon from '@mui/icons-material/Refresh';
import AppSidebar from '../../components/common/AppSidebar';
import api from '../../services/api/axios';

const ROSE = {
  light: '#F0D3DF',
  main: '#D47A8E',
  dark: '#C46B82',
};

const RISK_COLORS = {
  Faible: '#27AE60',
  Modéré: '#F39C12',
  Élevé: '#E74C3C',
};

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

export default function ModelAI() {
  const [activeTab, setActiveTab] = useState(0);
  const [patients, setPatients] = useState([]);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [predictionResult, setPredictionResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [predicting, setPredicting] = useState(false);

  // ── Charger la liste des patients ──────────────────────────────────────
  useEffect(() => {
    const fetchPatients = async () => {
      try {
        setLoading(true);
        const response = await api.get('patients/?limit=1000');
        setPatients(response.data.results || response.data || []);
      } catch (error) {
        console.error('Erreur chargement patients:', error);
      } finally {
        setLoading(false);
      }
    };
    fetchPatients();
  }, []);

  // ── Filtrer les patients par recherche ──────────────────────────────────
  const filteredPatients = patients.filter(p => {
    const search = searchTerm.toLowerCase();
    return (
      (p.nom && p.nom.toLowerCase().includes(search)) ||
      (p.prenom && p.prenom.toLowerCase().includes(search)) ||
      (p.id && p.id.toString().includes(search))
    );
  });

  // ── Faire une prédiction pour le patient sélectionné ──────────────────
  const handlePredict = useCallback(async () => {
    if (!selectedPatient) return;

    try {
      setPredicting(true);
      const response = await api.get(
        `predictions/patient/${selectedPatient.id}/mortalite/`
      );
      setPredictionResult(response.data);
      setActiveTab(2); // Aller à l'onglet Score
    } catch (error) {
      console.error('Erreur prédiction:', error);
      setPredictionResult({
        error: error.response?.data?.error || 'Erreur lors de la prédiction',
      });
    } finally {
      setPredicting(false);
    }
  }, [selectedPatient]);

  // ── Réinitialiser la prédiction et revenir à l'onglet Patients ──────────
  const handleNewPrediction = () => {
    setSelectedPatient(null);
    setPredictionResult(null);
    setActiveTab(1);
  };

  // ── Onglet 1 : Tableau de bord ─────────────────────────────────────────
  const DashboardTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card sx={{ background: `linear-gradient(135deg, ${ROSE.light}, white)` }}>
          <CardContent>
            <Typography variant="h4" sx={{ color: ROSE.dark, mb: 2 }}>
              🏥 Prédiction de Mortalité
            </Typography>
            <Typography variant="body1" sx={{ color: '#666', mb: 2 }}>
              Cohorte HD-478 | Modèle SVM Linéaire
            </Typography>
            <Divider sx={{ my: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" sx={{ color: '#888' }}>
                  Performance du modèle
                </Typography>
                <Typography variant="h6" sx={{ color: '#27AE60', fontWeight: 'bold' }}>
                  AUC = 0.8235
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" sx={{ color: '#888' }}>
                  Patients analysés
                </Typography>
                <Typography variant="h6" sx={{ color: ROSE.main, fontWeight: 'bold' }}>
                  478 patients
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" sx={{ color: '#888' }}>
                  Sensibilité
                </Typography>
                <Typography variant="h6" sx={{ color: '#2E86AB' }}>
                  73%
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Typography variant="subtitle2" sx={{ color: '#888' }}>
                  Pipeline
                </Typography>
                <Typography variant="body2">
                  KNNImputer → PowerTransformer → SVC
                </Typography>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 2 }}>
              📋 Guide d'utilisation
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Typography variant="body2">
                <strong>1. Onglet "Patients"</strong> - Sélectionnez un patient dans la liste
              </Typography>
              <Typography variant="body2">
                <strong>2. Cliquez "Prédire"</strong> - Le modèle analyse automatiquement toutes les données du patient
              </Typography>
              <Typography variant="body2">
                <strong>3. Onglet "Score"</strong> - Consultez le score de risque (0-100) et les recommandations
              </Typography>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  // ── Onglet 2 : Sélection patient ───────────────────────────────────────
  const PatientsTab = () => (
    <Box>
      <TextField
        fullWidth
        placeholder="Rechercher par nom, prénom ou ID..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon sx={{ color: ROSE.main }} />
            </InputAdornment>
          ),
        }}
        sx={{ mb: 3 }}
      />

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow sx={{ background: ROSE.light }}>
                <TableCell sx={{ fontWeight: 'bold' }}>ID</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Nom</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Prénom</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Âge</TableCell>
                <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredPatients.length > 0 ? (
                filteredPatients.map((patient) => (
                  <TableRow
                    key={patient.id}
                    sx={{
                      background:
                        selectedPatient?.id === patient.id
                          ? 'rgba(212, 122, 142, 0.1)'
                          : 'white',
                      '&:hover': { background: 'rgba(212, 122, 142, 0.05)' },
                    }}
                  >
                    <TableCell>#{patient.id}</TableCell>
                    <TableCell>{patient.nom || '-'}</TableCell>
                    <TableCell>{patient.prenom || '-'}</TableCell>
                    <TableCell>
                      {patient.age_annees ? `${patient.age_annees} ans` : '-'}
                    </TableCell>
                    <TableCell sx={{ textAlign: 'center' }}>
                      <Button
                        size="small"
                        variant={
                          selectedPatient?.id === patient.id ? 'contained' : 'outlined'
                        }
                        onClick={() => setSelectedPatient(patient)}
                        sx={{
                          color: selectedPatient?.id === patient.id ? 'white' : ROSE.main,
                          borderColor: ROSE.main,
                          background:
                            selectedPatient?.id === patient.id ? ROSE.main : 'transparent',
                          '&:hover': {
                            background:
                              selectedPatient?.id === patient.id ? ROSE.dark : ROSE.light,
                          },
                        }}
                      >
                        Sélectionner
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} sx={{ textAlign: 'center', py: 3 }}>
                    Aucun patient trouvé
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {selectedPatient && (
        <Box sx={{ mt: 3 }}>
          <Card sx={{ background: ROSE.light, p: 2 }}>
            <Typography variant="body2" sx={{ mb: 1 }}>
              Patient sélectionné:
            </Typography>
            <Typography variant="h6" sx={{ color: ROSE.dark, mb: 2 }}>
              {selectedPatient.prenom} {selectedPatient.nom} (ID: {selectedPatient.id})
            </Typography>
            <Button
              fullWidth
              variant="contained"
              startIcon={<PlayArrowIcon />}
              onClick={handlePredict}
              disabled={predicting}
              sx={{
                background: `linear-gradient(90deg, ${ROSE.main}, ${ROSE.dark})`,
                color: 'white',
                fontWeight: 'bold',
                py: 1.5,
                '&:hover': { background: ROSE.dark },
              }}
            >
              {predicting ? 'Prédiction en cours...' : 'Lancer la prédiction'}
            </Button>
          </Card>
        </Box>
      )}
    </Box>
  );

  // ── Onglet 3 : Score et résultats ──────────────────────────────────────
  const ScoreTab = () => {
    if (!selectedPatient) {
      return (
        <Alert severity="info">
          Sélectionnez d'abord un patient dans l'onglet "Patients"
        </Alert>
      );
    }

    if (predicting) {
      return (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <CircularProgress />
          <Typography sx={{ mt: 2 }}>Analyse en cours...</Typography>
        </Box>
      );
    }

    if (!predictionResult) {
      return (
        <Alert severity="warning">
          Cliquez sur "Lancer la prédiction" pour analyser ce patient
        </Alert>
      );
    }

    if (predictionResult.error) {
      return <Alert severity="error">{predictionResult.error}</Alert>;
    }

    const proba = predictionResult.probabilite_deces || 0;
    const score = predictionResult.score_risque || 0;
    const missing = predictionResult.features_missing || 0;

    return (
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card sx={{ textAlign: 'center', p: 3, background: `linear-gradient(135deg, ${ROSE.light}, white)` }}>
            <Typography variant="body2" sx={{ color: '#888', mb: 1 }}>
              Patient: {selectedPatient.prenom} {selectedPatient.nom} (ID: {selectedPatient.id})
            </Typography>
            <Typography variant="h3" sx={{ color: '#1e2d5a', fontWeight: 'bold', my: 2 }}>
              {(proba * 100).toFixed(1)} %
            </Typography>
            <Typography variant="body2" sx={{ color: '#888', mb: 2 }}>
              Probabilité de décès à 1 an — sortie directe du modèle SVM
            </Typography>
            <LinearProgress
              variant="determinate"
              value={score}
              sx={{
                height: 12,
                borderRadius: 6,
                background: '#e0e0e0',
                '& .MuiLinearProgress-bar': { background: '#3d5a8a', borderRadius: 6 },
                mb: 2,
              }}
            />
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 1 }}>
                Résultat du modèle SVM
              </Typography>
              <Typography variant="body2" sx={{ color: '#666', mb: 2, lineHeight: 1.7 }}>
                Le modèle estime que ce patient présente un profil similaire à des patients dont{' '}
                <strong>{(proba * 100).toFixed(1)} %</strong> sont décédés dans l'année dans la cohorte de validation (n = 478).
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" sx={{ color: '#888' }}>
                    Probabilité SVM
                  </Typography>
                  <Typography variant="h6" sx={{ color: '#1e2d5a', fontWeight: 'bold' }}>
                    {(proba * 100).toFixed(1)} %
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" sx={{ color: '#888' }}>
                    Variables utilisées
                  </Typography>
                  <Typography variant="h6" sx={{ color: '#1e2d5a', fontWeight: 'bold' }}>
                    {32 - missing} / 32
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" sx={{ color: '#888' }}>
                    Modèle
                  </Typography>
                  <Typography variant="body1">SVM Linéaire calibré</Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" sx={{ color: '#888' }}>
                    Fiabilité (AUC)
                  </Typography>
                  <Typography variant="body1" sx={{ color: '#27AE60', fontWeight: 'bold' }}>
                    0.82 · Validé sur 478 patients
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {missing > 0 && (
          <Grid item xs={12}>
            <Alert severity="warning">
              {missing} variables manquantes sur 32 — imputation KNN appliquée
            </Alert>
          </Grid>
        )}

        <Grid item xs={12}>
          <Stack direction="row" spacing={2} justifyContent="center">
            <Button
              variant="outlined"
              startIcon={<RefreshIcon />}
              onClick={handleNewPrediction}
              sx={{ color: ROSE.main, borderColor: ROSE.main }}
            >
              Autre patient
            </Button>
          </Stack>
        </Grid>
      </Grid>
    );
  };

  return (
    <Box sx={{ display: 'flex', background: '#f5f5f5', minHeight: '100vh' }}>
      <AppSidebar />
      <Box sx={{ flex: 1, p: 3 }}>
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h4" sx={{ color: ROSE.dark, mb: 1 }}>
              🤖 Modèle AI — Prédiction de Mortalité
            </Typography>
            <Typography variant="body2" sx={{ color: '#888' }}>
              SVM Linéaire | Cohorte HD-478 | AUC = 0.8235
            </Typography>
          </CardContent>
        </Card>

        <Card>
          <Tabs
            value={activeTab}
            onChange={(e, val) => setActiveTab(val)}
            sx={{
              borderBottom: `2px solid ${ROSE.light}`,
              '& .MuiTab-root': { color: '#888' },
              '& .Mui-selected': { color: ROSE.main, fontWeight: 'bold' },
              '& .MuiTabs-indicator': { background: ROSE.main },
            }}
          >
            <Tab label="📊 Tableau de bord" />
            <Tab label="👥 Patients" />
            <Tab label="📈 Score" />
          </Tabs>

          <CardContent>
            <TabPanel value={activeTab} index={0}>
              <DashboardTab />
            </TabPanel>
            <TabPanel value={activeTab} index={1}>
              <PatientsTab />
            </TabPanel>
            <TabPanel value={activeTab} index={2}>
              <ScoreTab />
            </TabPanel>
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
