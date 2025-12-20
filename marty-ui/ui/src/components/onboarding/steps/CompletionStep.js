/**
 * Completion Step Component
 * 
 * Final step showing success message and redirecting to dashboard
 */

import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Alert,
  CircularProgress,
  Tooltip,
  Fade,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

const CompletionStep = ({
  userType,
  resultOrgName,
  resultInviteCode,
  membershipStatus,
}) => {
  const copyInviteCode = () => {
    navigator.clipboard.writeText(resultInviteCode);
  };

  return (
    <Fade in>
      <Box sx={{ textAlign: 'center', py: 6 }}>
        <CheckCircleIcon sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
        <Typography variant="h4" gutterBottom>
          You're All Set!
        </Typography>
        
        {userType === 'vendor' && resultInviteCode && (
          <Box sx={{ my: 4, maxWidth: 400, mx: 'auto' }}>
            <Alert severity="success" sx={{ mb: 2 }}>
              <Typography variant="body2">
                Your organization <strong>{resultOrgName}</strong> has been created!
              </Typography>
            </Alert>
            <Paper variant="outlined" sx={{ p: 3, bgcolor: 'grey.50' }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Your Invite Code:
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                <Typography variant="h4" fontFamily="monospace" fontWeight="bold">
                  {resultInviteCode}
                </Typography>
                <Tooltip title="Copy to clipboard">
                  <Button size="small" onClick={copyInviteCode}>
                    <ContentCopyIcon />
                  </Button>
                </Tooltip>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Share this code with users who need to join your organization
              </Typography>
            </Paper>
          </Box>
        )}

        {userType === 'applicant' && membershipStatus === 'joined' && (
          <Alert severity="success" sx={{ maxWidth: 400, mx: 'auto', mb: 3 }}>
            You've joined <strong>{resultOrgName}</strong>!
          </Alert>
        )}

        {userType === 'applicant' && membershipStatus === 'pending_approval' && (
          <Alert severity="info" sx={{ maxWidth: 400, mx: 'auto', mb: 3 }}>
            Your request to join <strong>{resultOrgName}</strong> is pending approval.
          </Alert>
        )}

        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          Redirecting to your dashboard...
        </Typography>
        <CircularProgress size={24} />
      </Box>
    </Fade>
  );
};

export default CompletionStep;
