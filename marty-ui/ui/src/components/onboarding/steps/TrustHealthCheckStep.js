/**
 * Trust Health Check Step Component
 * 
 * Step 5 of trust setup: Validate configuration and show health status.
 * Final step before activating trust profile.
 */

import React, { useEffect } from 'react';
import {
  Box,
  Typography,
  Fade,
  CircularProgress,
} from '@mui/material';
import { TrustHealthChecklist } from '../../trust/components';
import { useTrust } from '../../trust';

/**
 * Trust Health Check Step Component.
 * 
 * @param {Object} props
 * @param {function} props.onActivate - Callback when user clicks activate
 * @param {function} props.onReviewIssues - Callback when user clicks review issues
 * @param {function} [props.onHealthLoaded] - Callback when health status is loaded
 */
const TrustHealthCheckStep = ({
  onActivate,
  onReviewIssues,
  onHealthLoaded,
}) => {
  const { healthStatus, loading, refreshHealth, organizationId } = useTrust();

  // Refresh health on mount
  useEffect(() => {
    if (organizationId) {
      refreshHealth();
    }
  }, [organizationId, refreshHealth]);

  // Notify parent when health is loaded
  useEffect(() => {
    if (healthStatus && onHealthLoaded) {
      onHealthLoaded(healthStatus);
    }
  }, [healthStatus, onHealthLoaded]);

  return (
    <Fade in>
      <Box data-testid="trust-health-check-step">
        <Typography variant="h5" gutterBottom textAlign="center">
          Ready to activate
        </Typography>
        <Typography
          variant="body1"
          color="text.secondary"
          textAlign="center"
          sx={{ mb: 4 }}
        >
          We'll run checks to ensure your org can verify and issue safely.
        </Typography>

        <Box sx={{ maxWidth: 600, mx: 'auto' }}>
          {loading && !healthStatus ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <TrustHealthChecklist
              healthStatus={healthStatus}
              loading={loading}
              onActivate={onActivate}
              onReviewIssues={onReviewIssues}
              showChainStatus
              showActions
              compact={false}
            />
          )}
        </Box>
      </Box>
    </Fade>
  );
};

export default TrustHealthCheckStep;
