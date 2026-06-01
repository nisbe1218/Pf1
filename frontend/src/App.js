import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Box } from '@mui/material';
import Dashboard from './pages/dashboard/Dashboard';
import Landing from './pages/auth/Landing';
import Login from './pages/auth/Login';
import Unauthorized from './pages/unauthorized/Unauthorized';
import PatientsManagement from './pages/patients/PatientsManagement';
import ModelAI from './pages/model-ai/ModelAI';
import ValidationRequests from './pages/preprocessing/ValidationRequests';
import Profile from './pages/profile/Profile';
import MonitorBoard from './pages/monitor/MonitorBoard';
import ProtectedRoute from './components/common/ProtectedRoute';
import NotesFab from './components/common/NotesFab';
import { AuthProvider } from './context/AuthContext';
import { LanguageProvider } from './context/LanguageContext';

function App() {
  return (
    <AuthProvider>
      <LanguageProvider>
        <Router>
          <Box
            sx={{ width: '100%', minHeight: '100vh', pt: 0, pb: 4, px: 0, mx: 0, minWidth: 0, overflowX: 'hidden' }}
          >
            <Routes>
              {/* Page d’accueil publique */}
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/unauthorized" element={<Unauthorized />} />

              {/* Routes Protégées (Tous les rôles connectés) */}
              <Route element={<ProtectedRoute />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/modele-ai" element={<ModelAI />} />
                <Route path="/monitor" element={<MonitorBoard />} />
                <Route path="/profil" element={<Profile />} />
              </Route>

              <Route element={<ProtectedRoute allowedRoles={['super_admin', 'chef_service', 'professeur', 'resident']} />}>
                <Route path="/patients" element={<PatientsManagement />} />
              </Route>

              <Route element={<ProtectedRoute allowedRoles={['super_admin', 'chef_service']} />}>
                <Route path="/validation-requests" element={<ValidationRequests />} />
              </Route>

              {/* Les autres rôles viendront ici (ex: routes admin, route patients) */}

              {/* Redirection par défaut */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
            <NotesFab />
          </Box>
        </Router>
      </LanguageProvider>
    </AuthProvider>
  );
}

export default App;