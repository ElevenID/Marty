import { useState, useCallback } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Chip,
  Stack,
} from '@mui/material';
import {
  QrCodeScanner as ScanIcon,
} from '@mui/icons-material';
import { verifyCredential, VerificationResult, VerifyRequest } from '@/services/tauri-api';
import { useAppStore } from '@/store';
import VerificationResultCard from './VerificationResultCard';

interface VerifierPanelProps {
  credentialType?: string;
  onVerificationComplete?: (result: VerificationResult) => void;
}

export default function VerifierPanel({
  credentialType = 'mdl',
  onVerificationComplete,
}: VerifierPanelProps) {
  const [scanning, setScanning] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const { setLastVerification, setVerificationInProgress, license } = useAppStore();

  const handleScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    setResult(null);

    try {
      // TODO: Implement actual QR scanning via Tauri plugin
      // For now, simulate with mock data
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Mock credential data
      const mockCredentialData = 'mock_credential_qr_data';

      setScanning(false);
      setVerifying(true);
      setVerificationInProgress(true);

      const request: VerifyRequest = {
        credential_type: credentialType,
        credential_data: mockCredentialData,
        policy: {
          required_claims: ['given_name', 'family_name'],
          allow_expired_grace: false,
        },
      };

      const verificationResult = await verifyCredential(request);
      setResult(verificationResult);
      setLastVerification(verificationResult);
      onVerificationComplete?.(verificationResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setScanning(false);
      setVerifying(false);
      setVerificationInProgress(false);
    }
  }, [credentialType, onVerificationComplete, setLastVerification, setVerificationInProgress]);

  const handleReset = () => {
    setResult(null);
    setError(null);
  };

  // Check if credential type is licensed
  const isLicensed = license?.features.some(
    (f) => f === '*' || f === credentialType || credentialType.startsWith(f)
  );

  if (!isLicensed) {
    return (
      <Card>
        <CardContent>
          <Alert severity="error">
            {credentialType.toUpperCase()} verification is not licensed.
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (result) {
    return (
      <Box>
        <VerificationResultCard result={result} />
        <Button
          variant="outlined"
          fullWidth
          onClick={handleReset}
          sx={{ mt: 2 }}
        >
          Verify Another Credential
        </Button>
      </Box>
    );
  }

  return (
    <Card data-testid="verifier-panel">
      <CardContent>
        <Stack spacing={3} alignItems="center">
          <Typography variant="h5">
            {credentialType.toUpperCase()} Verification
          </Typography>

          <Chip
            label={credentialType}
            color="primary"
            variant="outlined"
          />

          {error && (
            <Alert severity="error" sx={{ width: '100%' }}>
              {error}
            </Alert>
          )}

          <Box
            sx={{
              width: 200,
              height: 200,
              border: '2px dashed',
              borderColor: scanning ? 'primary.main' : 'grey.400',
              borderRadius: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              bgcolor: scanning ? 'action.hover' : 'transparent',
            }}
          >
            {scanning || verifying ? (
              <CircularProgress />
            ) : (
              <ScanIcon sx={{ fontSize: 64, color: 'grey.400' }} />
            )}
          </Box>

          <Typography variant="body2" color="text.secondary" textAlign="center">
            {scanning
              ? 'Scanning QR code...'
              : verifying
              ? 'Verifying credential...'
              : 'Position the credential QR code in the camera view'}
          </Typography>

          <Button
            data-testid="scan-button"
            variant="contained"
            size="large"
            startIcon={<ScanIcon />}
            onClick={handleScan}
            disabled={scanning || verifying}
            fullWidth
          >
            {scanning ? 'Scanning...' : verifying ? 'Verifying...' : 'Start Scan'}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
