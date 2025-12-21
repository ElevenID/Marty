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
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Checkbox,
  FormControlLabel,
  TextField,
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
  const [selectedType, setSelectedType] = useState(credentialType);
  const [useNfc, setUseNfc] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const [credentialData, setCredentialData] = useState('');
  const { setLastVerification, setVerificationInProgress, license } = useAppStore();

  const handleScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    setResult(null);

    try {
      // TODO: Implement actual QR scanning via Tauri plugin
      // For now, simulate with mock data
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Use provided data or mock placeholder
      const payload = credentialData || 'mock_credential_qr_data';

      setScanning(false);
      setVerifying(true);
      setVerificationInProgress(true);

      const request: VerifyRequest = {
        credential_type: selectedType,
        credential_data: payload,
        use_nfc: selectedType === 'emrtd' ? useNfc : undefined,
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
  }, [selectedType, useNfc, onVerificationComplete, setLastVerification, setVerificationInProgress]);

  const handleReset = () => {
    setResult(null);
    setError(null);
  };

  // Check if credential type is licensed
  const isLicensed = license?.features.some(
    (f) => f === '*' || f === selectedType || selectedType.startsWith(f)
  );

  if (!isLicensed) {
    return (
      <Card>
        <CardContent>
          <Alert severity="error">
            {selectedType.toUpperCase()} verification is not licensed.
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
            {selectedType.toUpperCase()} Verification
          </Typography>

          <FormControl fullWidth>
            <InputLabel id="credential-type-label">Credential Type</InputLabel>
            <Select
              labelId="credential-type-label"
              value={selectedType}
              label="Credential Type"
              onChange={(e) => setSelectedType(e.target.value)}
              data-testid="credential-type-select"
            >
              <MenuItem value="mdl">mDL</MenuItem>
              <MenuItem value="emrtd">eMRTD (Passport)</MenuItem>
              <MenuItem value="oid4vp">OID4VP</MenuItem>
              <MenuItem value="sd-jwt">SD-JWT</MenuItem>
            </Select>
          </FormControl>

          {selectedType === 'emrtd' && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={useNfc}
                  onChange={(e) => setUseNfc(e.target.checked)}
                  data-testid="use-nfc-checkbox"
                />
              }
              label="Use NFC reader (if available)"
            />
          )}

          <TextField
            label="Credential Data (JSON, base64, or QR contents)"
            placeholder={
              selectedType === 'emrtd'
                ? '{"sod_base64":"...","data_groups":{"DG1":"..."},"country":"USA"}'
                : 'Paste credential payload'
            }
            value={credentialData}
            onChange={(e) => setCredentialData(e.target.value)}
            fullWidth
            multiline
            minRows={3}
            data-testid="credential-data-input"
          />

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
