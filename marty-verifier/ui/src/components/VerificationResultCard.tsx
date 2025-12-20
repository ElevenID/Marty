import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  Divider,
  Alert,
  Stack,
} from '@mui/material';
import {
  CheckCircle as ValidIcon,
  Cancel as InvalidIcon,
  Warning as WarningIcon,
  Schedule as PendingIcon,
  VerifiedUser as TrustIcon,
} from '@mui/icons-material';
import { VerificationResult } from '@/services/tauri-api';

interface VerificationResultCardProps {
  result: VerificationResult;
}

const statusConfig = {
  valid: { color: 'success' as const, icon: <ValidIcon />, label: 'Valid' },
  invalid: { color: 'error' as const, icon: <InvalidIcon />, label: 'Invalid' },
  failed: { color: 'error' as const, icon: <InvalidIcon />, label: 'Failed' },
  expired: { color: 'warning' as const, icon: <WarningIcon />, label: 'Expired' },
  revoked: { color: 'error' as const, icon: <InvalidIcon />, label: 'Revoked' },
  pending: { color: 'info' as const, icon: <PendingIcon />, label: 'Pending' },
};

export default function VerificationResultCard({ result }: VerificationResultCardProps) {
  const config = statusConfig[result.status] ?? statusConfig.failed;

  return (
    <Card
      data-testid="verification-result"
      role="region"
      aria-label="Verification result"
      sx={{
        borderLeft: 6,
        borderColor: `${config.color}.main`,
      }}
    >
      <CardContent>
        <Stack spacing={2}>
          {/* Status Header */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box
              sx={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                bgcolor: `${config.color}.light`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: `${config.color}.main`,
              }}
            >
              {config.icon}
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography variant="h5" fontWeight="bold">
                {config.label}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {result.credential_type.toUpperCase()} Credential
              </Typography>
            </Box>
            <Chip
              label={result.trust_chain.offline_verified ? 'Offline' : 'Online'}
              size="small"
              color={result.trust_chain.offline_verified ? 'warning' : 'success'}
              variant="outlined"
            />
          </Box>

          <Divider />

          {/* Issuer Info */}
          {result.issuer && (
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                Issuer
              </Typography>
              <Typography variant="body1">
                {result.issuer.name ?? 'Unknown'}
                {result.issuer.jurisdiction && ` (${result.issuer.jurisdiction})`}
              </Typography>
            </Box>
          )}

          {/* Trust Chain */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TrustIcon color={result.trust_chain.valid ? 'success' : 'error'} />
            <Typography variant="body2">
              Trust Chain: {result.trust_chain.chain_type.toUpperCase()}
              {result.trust_chain.trust_anchor && ` (${result.trust_chain.trust_anchor})`}
            </Typography>
          </Box>

          {/* Disclosed Claims */}
          {Object.keys(result.disclosed_claims).length > 0 && (
            <Box>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Disclosed Claims
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {Object.entries(result.disclosed_claims).map(([key, value]) => (
                  <Chip
                    key={key}
                    label={`${key}: ${typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value}`}
                    size="small"
                    variant="outlined"
                  />
                ))}
              </Box>
            </Box>
          )}

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <Box>
              {result.warnings.map((warning, index) => (
                <Alert key={index} severity="warning" sx={{ mb: 1 }}>
                  {warning}
                </Alert>
              ))}
            </Box>
          )}

          {/* Metadata */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              ID: {result.verification_id.slice(0, 8)}...
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {new Date(result.verified_at).toLocaleString()}
            </Typography>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  );
}
