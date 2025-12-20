/**
 * Role Selection Step Component
 * 
 * Step 1: User chooses their role (Applicant or Vendor)
 */

import React from 'react';
import { Box, Typography, Grid, Fade } from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import BusinessIcon from '@mui/icons-material/Business';
import RoleCard from '../RoleCard';

const RoleSelectionStep = ({ userType, onSelectRole }) => {
  return (
    <Fade in>
      <Box data-testid="role-selection-step">
        <Typography variant="h5" gutterBottom textAlign="center">
          How will you use Marty?
        </Typography>
        <Typography
          variant="body1"
          color="text.secondary"
          textAlign="center"
          sx={{ mb: 4 }}
        >
          Choose the option that best describes you
        </Typography>

        <Grid container spacing={4} justifyContent="center">
          <Grid item xs={12} md={5}>
            <RoleCard
              role="applicant"
              title="Applicant"
              description="I'm applying for digital travel documents"
              icon={PersonIcon}
              selected={userType === 'applicant'}
              onSelect={onSelectRole}
              features={[
                'Apply for digital travel documents',
                'Store credentials in your wallet',
                'Share documents securely',
                'Track application status',
              ]}
              testId="role-card-applicant"
            />
          </Grid>
          <Grid item xs={12} md={5}>
            <RoleCard
              role="vendor"
              title="Vendor / Organization"
              description="I'm issuing documents for my organization"
              icon={BusinessIcon}
              selected={userType === 'vendor'}
              onSelect={onSelectRole}
              features={[
                'Issue digital travel documents',
                'Manage applicants and applications',
                'Access API for integrations',
                'Configure webhooks and automations',
              ]}
              testId="role-card-vendor"
            />
          </Grid>
        </Grid>
      </Box>
    </Fade>
  );
};

export default RoleSelectionStep;
