import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AppBar, Toolbar, Typography, Container, Box } from '@mui/material';

import { AuthProvider } from './contexts/AuthContext';
import { NotificationProvider } from './contexts/NotificationContext';
import ErrorBoundary from './components/ErrorBoundary';
import ProtectedRoute, { AdminRoute, ApplicantRoute, VendorRoute } from './components/ProtectedRoute';
import LandingPage from './components/LandingPage';
import Home from './components/Home';
import TravelDocuments from './components/TravelDocuments';
import VerifierDemo from './components/VerifierDemo';
import WalletDemo from './components/WalletDemo';
import EnhancedVerifierDemo from './components/EnhancedVerifierDemo';
import Navigation from './components/Navigation';
import AdminDashboard from './components/AdminDashboard';
import PassportDemo from './components/PassportDemo';
import CscaManager from './components/CscaManager';
import PkdManager from './components/PkdManager';
import TrustAnchor from './components/TrustAnchor';
import MetricsViewer from './components/MetricsViewer';
import MasterListViewer from './components/MasterListViewer';
import ApplicantVetting from './components/ApplicantVetting';
import LoginPage from './components/LoginPage';
import AuthCallback from './components/AuthCallback';
import OnboardingPage from './components/OnboardingPage';
import MyApplications from './components/MyApplications';
import MyDocuments from './components/MyDocuments';
import ProfilePage from './components/ProfilePage';
import { VendorDashboard, APIKeyManager, CredentialConfigManager } from './components/vendor';

const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        <NotificationProvider>
          <Router>
            <AuthProvider>
              <AppBar position="static">
                <Toolbar>
                  <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                    Marty Trust Services
                  </Typography>
                </Toolbar>
              </AppBar>

              <Container maxWidth="lg">
                <Box sx={{ my: 4 }}>
                  <Navigation />

                  <Routes>
                {/* Public Routes */}
                <Route path="/" element={<LandingPage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/callback" element={<AuthCallback />} />
                <Route path="/onboarding" element={<OnboardingPage />} />

                {/* Admin Dashboard (the original Home component) */}
                <Route
                  path="/dashboard"
                  element={
                    <AdminRoute>
                      <Home />
                    </AdminRoute>
                  }
                />

                {/* Administrator-Only Routes */}
                <Route
                  path="/documents"
                  element={
                    <AdminRoute>
                      <TravelDocuments />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/applicants"
                  element={
                    <AdminRoute>
                      <ApplicantVetting />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/verifier"
                  element={
                    <AdminRoute>
                      <VerifierDemo />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/wallet"
                  element={
                    <AdminRoute>
                      <WalletDemo />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/enhanced"
                  element={
                    <AdminRoute>
                      <EnhancedVerifierDemo />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin"
                  element={
                    <AdminRoute>
                      <AdminDashboard />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/passport"
                  element={
                    <AdminRoute>
                      <PassportDemo />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/csca"
                  element={
                    <AdminRoute>
                      <CscaManager />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/pkd"
                  element={
                    <AdminRoute>
                      <PkdManager />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/trust-anchor"
                  element={
                    <AdminRoute>
                      <TrustAnchor />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/master-lists"
                  element={
                    <AdminRoute>
                      <MasterListViewer />
                    </AdminRoute>
                  }
                />
                <Route
                  path="/admin/metrics"
                  element={
                    <AdminRoute>
                      <MetricsViewer />
                    </AdminRoute>
                  }
                />

                {/* Vendor-Only Routes */}
                <Route
                  path="/vendor"
                  element={
                    <VendorRoute>
                      <VendorDashboard />
                    </VendorRoute>
                  }
                />
                <Route
                  path="/vendor/api-keys"
                  element={
                    <VendorRoute>
                      <APIKeyManager />
                    </VendorRoute>
                  }
                />
                <Route
                  path="/vendor/credentials"
                  element={
                    <VendorRoute>
                      <CredentialConfigManager />
                    </VendorRoute>
                  }
                />

                {/* Applicant-Only Routes */}
                <Route
                  path="/my-applications"
                  element={
                    <ApplicantRoute>
                      <MyApplications />
                    </ApplicantRoute>
                  }
                />
                <Route
                  path="/my-documents"
                  element={
                    <ApplicantRoute>
                      <MyDocuments />
                    </ApplicantRoute>
                  }
                />
                <Route
                  path="/profile"
                  element={
                    <ProtectedRoute>
                      <ProfilePage />
                    </ProtectedRoute>
                  }
                />

                {/* Fallback - redirect unknown routes to home */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Box>
          </Container>
        </AuthProvider>
      </Router>
        </NotificationProvider>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export default App;
