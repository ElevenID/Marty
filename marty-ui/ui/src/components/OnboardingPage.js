/**
 * Onboarding Page Component
 *
 * Post-registration onboarding flow where users:
 * 1. Choose their role (Applicant or Vendor)
 * 2. For Applicants: Join via invite code, request membership, or select open org
 * 3. For Vendors: Create a new organization with visibility/membership settings
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Container,
  Stepper,
  Step,
  StepLabel,
  CircularProgress,
  Alert,
  Paper,
} from '@mui/material';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

import {
  RoleSelectionStep,
  ApplicantJoinStep,
  VendorCreateOrgStep,
  CompletionStep,
  ConfirmOrgDialog,
  WalletPairingStep,
} from './onboarding';

const API_BASE_URL = process.env.REACT_APP_API_URL || '/api';

const STEPS_APPLICANT = ['Choose Your Role', 'Join Organization', 'Connect Wallet', 'Complete'];
const STEPS_VENDOR = ['Choose Your Role', 'Create Organization', 'Complete'];

/**
 * Main Onboarding Page Component
 */
const OnboardingPage = () => {
  const navigate = useNavigate();

  // State
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // User selections
  const [userType, setUserType] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  
  // Applicant join options
  const [joinMethod, setJoinMethod] = useState('code'); // 'code', 'browse', 'skip'
  const [inviteCode, setInviteCode] = useState('');
  
  // Vendor org creation
  const [newOrgName, setNewOrgName] = useState('');
  const [newOrgDescription, setNewOrgDescription] = useState('');
  const [newOrgType, setNewOrgType] = useState('');
  const [jurisdiction, setJurisdiction] = useState('');
  const [isDiscoverable, setIsDiscoverable] = useState(false);
  const [membershipMode, setMembershipMode] = useState('invite_only');
  
  // Result state
  const [resultInviteCode, setResultInviteCode] = useState(null);
  const [resultOrgName, setResultOrgName] = useState(null);
  const [membershipStatus, setMembershipStatus] = useState(null);
  
  // Wallet pairing state
  const [walletPaired, setWalletPaired] = useState(false);
  const [pairedDeviceId, setPairedDeviceId] = useState(null);

  // Confirmation dialog
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  const [selectedOrgForConfirm, setSelectedOrgForConfirm] = useState(null);

  // Check onboarding status on mount
  useEffect(() => {
    checkOnboardingStatus();
  }, []);

  const checkOnboardingStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/status`, {
        credentials: 'include',
      });

      if (response.status === 401) {
        navigate('/');
        return;
      }

      const data = await response.json();

      if (!data.needs_onboarding) {
        if (data.user_type === 'vendor') {
          navigate('/vendor/dashboard');
        } else if (data.user_type === 'administrator') {
          navigate('/admin');
        } else {
          navigate('/dashboard');
        }
        return;
      }

      await loadOrganizations();
      setLoading(false);
    } catch (err) {
      console.error('Error checking onboarding status:', err);
      setError('Failed to load onboarding status');
      setLoading(false);
    }
  };

  const loadOrganizations = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/organizations`, {
        credentials: 'include',
      });

      if (response.ok) {
        const data = await response.json();
        setOrganizations(data.organizations || []);
      }
    } catch (err) {
      console.error('Error loading organizations:', err);
    }
  };

  const handleNext = () => {
    if (activeStep === 0 && !userType) {
      setError('Please select a role to continue');
      return;
    }
    setError(null);
    setActiveStep((prev) => prev + 1);
  };

  const handleBack = () => {
    setError(null);
    setActiveStep((prev) => prev - 1);
  };

  const handleJoinWithCode = async () => {
    if (!inviteCode.trim()) {
      setError('Please enter an invite code');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/join-with-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ invite_code: inviteCode.trim() }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Invalid invite code');
      }

      setResultOrgName(data.organization_name);
      setMembershipStatus('joined');
      // Move to wallet pairing step
      setActiveStep(2);
      setSubmitting(false);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  const handleSelectOrg = (org) => {
    if (org.membership_mode === 'invite_only') {
      setError('This organization only accepts members via invitation. Please use an invite code.');
      return;
    }
    setSelectedOrgForConfirm(org);
    setConfirmDialogOpen(true);
  };

  const handleConfirmOrgSelection = async () => {
    setConfirmDialogOpen(false);
    setSubmitting(true);
    setError(null);

    const org = selectedOrgForConfirm;

    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_type: 'applicant',
          organization_id: org.id,
          confirm_organization: true,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to join organization');
      }

      setResultOrgName(data.organization_name);
      setMembershipStatus(data.membership_status);
      // Move to wallet pairing step
      setActiveStep(2);
      setSubmitting(false);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  const handleCompleteApplicantWithoutOrg = async () => {
    // Skip org, go directly to wallet pairing
    setMembershipStatus('none');
    setActiveStep(2);
  };

  const handleFinalizeApplicantOnboarding = async (withWallet = false) => {
    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_type: 'applicant',
          organization_id: selectedOrgForConfirm?.id || null,
          wallet_paired: withWallet,
          device_id: pairedDeviceId,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to complete setup');
      }

      // Move to completion step
      setActiveStep(3);
      setSubmitting(false);

      // Redirect after showing completion
      setTimeout(() => {
        navigate('/dashboard');
      }, 3000);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  const handleCompleteVendor = async () => {
    if (!newOrgName.trim()) {
      setError('Please enter an organization name');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/onboarding/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_type: 'vendor',
          organization_name: newOrgName.trim(),
          organization_description: newOrgDescription.trim() || null,
          organization_type: newOrgType || null,
          jurisdiction: jurisdiction.trim() || null,
          is_discoverable: isDiscoverable,
          membership_mode: membershipMode,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to create organization');
      }

      setResultOrgName(data.organization_name);
      setResultInviteCode(data.invite_code);
      setMembershipStatus('owner');
      setActiveStep(2);

      setTimeout(() => {
        navigate('/vendor/dashboard');
      }, 5000);
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
        }}
        data-testid="onboarding-loading"
      >
        <CircularProgress size={48} sx={{ color: 'white' }} />
      </Box>
    );
  }

  const steps = userType === 'vendor' ? STEPS_VENDOR : STEPS_APPLICANT;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
        py: 4,
      }}
      data-testid="onboarding-page"
    >
      <Container maxWidth="lg">
        {/* Header */}
        <Box sx={{ textAlign: 'center', mb: 4 }} data-testid="onboarding-header">
          <FlightTakeoffIcon sx={{ fontSize: 48, color: 'white', mb: 1 }} />
          <Typography variant="h4" fontWeight="bold" color="white" data-testid="onboarding-title">
            Welcome to Marty Trust Services
          </Typography>
          <Typography variant="subtitle1" color="rgba(255,255,255,0.9)">
            Let's get you set up
          </Typography>
        </Box>

        {/* Stepper */}
        <Paper sx={{ p: 3, mb: 4 }} data-testid="onboarding-stepper">
          <Stepper activeStep={activeStep} alternativeLabel>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
        </Paper>

        {/* Error Alert */}
        {error && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)} data-testid="onboarding-error">
            {error}
          </Alert>
        )}

        {/* Step Content */}
        <Paper sx={{ p: 4, minHeight: 400 }} data-testid="onboarding-content">
          {/* Step 1: Role Selection */}
          {activeStep === 0 && (
            <RoleSelectionStep
              userType={userType}
              onSelectRole={setUserType}
            />
          )}

          {/* Step 2: Applicant - Join Organization */}
          {activeStep === 1 && userType === 'applicant' && (
            <ApplicantJoinStep
              joinMethod={joinMethod}
              onJoinMethodChange={setJoinMethod}
              inviteCode={inviteCode}
              onInviteCodeChange={setInviteCode}
              organizations={organizations}
              submitting={submitting}
              onJoinWithCode={handleJoinWithCode}
              onSelectOrg={handleSelectOrg}
              onSkip={handleCompleteApplicantWithoutOrg}
            />
          )}

          {/* Step 2: Vendor - Create Organization */}
          {activeStep === 1 && userType === 'vendor' && (
            <VendorCreateOrgStep
              orgName={newOrgName}
              onOrgNameChange={setNewOrgName}
              orgDescription={newOrgDescription}
              onOrgDescriptionChange={setNewOrgDescription}
              orgType={newOrgType}
              onOrgTypeChange={setNewOrgType}
              jurisdiction={jurisdiction}
              onJurisdictionChange={setJurisdiction}
              isDiscoverable={isDiscoverable}
              onDiscoverableChange={setIsDiscoverable}
              membershipMode={membershipMode}
              onMembershipModeChange={setMembershipMode}
            />
          )}

          {/* Step 3: Applicant - Wallet Pairing */}
          {activeStep === 2 && userType === 'applicant' && (
            <WalletPairingStep
              onPairingComplete={(data) => {
                setWalletPaired(true);
                setPairedDeviceId(data.device_id);
                handleFinalizeApplicantOnboarding(true);
              }}
              onSkip={() => handleFinalizeApplicantOnboarding(false)}
              submitting={submitting}
            />
          )}

          {/* Step 3/4: Completion */}
          {((activeStep === 3 && userType === 'applicant') || 
            (activeStep === 2 && userType === 'vendor')) && (
            <CompletionStep
              userType={userType}
              resultOrgName={resultOrgName}
              resultInviteCode={resultInviteCode}
              membershipStatus={membershipStatus}
              walletPaired={walletPaired}
              pairedDeviceId={pairedDeviceId}
            />
          )}

          {/* Navigation Buttons - show for step 0-1 only */}
          {activeStep < 2 && (
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                mt: 4,
                pt: 3,
                borderTop: '1px solid',
                borderColor: 'divider',
              }}
              data-testid="onboarding-nav-buttons"
            >
              <Button
                disabled={activeStep === 0}
                onClick={handleBack}
                startIcon={<ArrowBackIcon />}
                data-testid="onboarding-back-btn"
              >
                Back
              </Button>

              {activeStep === 0 && (
                <Button
                  variant="contained"
                  onClick={handleNext}
                  disabled={!userType}
                  endIcon={<ArrowForwardIcon />}
                  data-testid="continue-btn"
                >
                  Continue
                </Button>
              )}

              {activeStep === 1 && userType === 'vendor' && (
                <Button
                  variant="contained"
                  onClick={handleCompleteVendor}
                  disabled={submitting || !newOrgName.trim()}
                  endIcon={submitting ? <CircularProgress size={16} /> : <CheckCircleIcon />}
                  data-testid="onboarding-create-org-btn"
                >
                  {submitting ? 'Creating...' : 'Create Organization'}
                </Button>
              )}
            </Box>
          )}
        </Paper>
      </Container>

      {/* Confirmation Dialog */}
      <ConfirmOrgDialog
        open={confirmDialogOpen}
        onClose={() => setConfirmDialogOpen(false)}
        organization={selectedOrgForConfirm}
        submitting={submitting}
        onConfirm={handleConfirmOrgSelection}
      />
    </Box>
  );
};

export default OnboardingPage;
