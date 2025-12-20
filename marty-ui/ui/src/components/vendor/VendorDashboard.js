/**
 * Vendor Dashboard
 *
 * Main dashboard for vendor organization administrators.
 * Shows organization overview, quick stats, and navigation to management features.
 */

import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Grid,
  Typography,
  Button,
  Chip,
  Paper,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
} from '@mui/material';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import BusinessIcon from '@mui/icons-material/Business';
import VpnKeyIcon from '@mui/icons-material/VpnKey';
import PeopleIcon from '@mui/icons-material/People';
import WebhookIcon from '@mui/icons-material/Webhook';
import DevicesIcon from '@mui/icons-material/Devices';
import AttachMoneyIcon from '@mui/icons-material/AttachMoney';
import SettingsIcon from '@mui/icons-material/Settings';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import CredentialIcon from '@mui/icons-material/VerifiedUser';

/**
 * Quick stat card component
 */
function StatCard({ title, value, icon, color = 'primary', trend, testId }) {
  return (
    <Card sx={{ height: '100%' }} data-testid={testId}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box>
            <Typography variant="body2" color="textSecondary" gutterBottom>
              {title}
            </Typography>
            <Typography variant="h4" component="div" fontWeight="bold" data-testid={testId ? `${testId}-value` : undefined}>
              {value}
            </Typography>
            {trend && (
              <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                <TrendingUpIcon fontSize="small" color="success" />
                <Typography variant="caption" color="success.main" sx={{ ml: 0.5 }}>
                  {trend}
                </Typography>
              </Box>
            )}
          </Box>
          <Box
            sx={{
              backgroundColor: `${color}.light`,
              borderRadius: 2,
              p: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {React.cloneElement(icon, { sx: { color: `${color}.main`, fontSize: 32 } })}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

/**
 * Quick action link component
 */
function QuickAction({ title, description, icon, to, testId }) {
  return (
    <ListItem
      component={Link}
      to={to}
      sx={{
        borderRadius: 1,
        mb: 1,
        '&:hover': {
          backgroundColor: 'action.hover',
        },
      }}
      data-testid={testId}
    >
      <ListItemIcon>{icon}</ListItemIcon>
      <ListItemText
        primary={title}
        secondary={description}
        primaryTypographyProps={{ fontWeight: 'medium' }}
      />
      <ListItemSecondaryAction>
        <IconButton edge="end" component={Link} to={to}>
          <ArrowForwardIcon />
        </IconButton>
      </ListItemSecondaryAction>
    </ListItem>
  );
}

export default function VendorDashboard() {
  const { user, organizationName, organizationId } = useAuth();

  // TODO: Fetch real stats from API
  const stats = {
    apiKeys: 3,
    activeApplicants: 24,
    credentialsIssued: 156,
    processingFee: 25.0,
  };

  return (
    <Box sx={{ p: 3 }} data-testid="vendor-dashboard">
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <BusinessIcon color="primary" fontSize="large" />
          <Typography variant="h4" component="h1" data-testid="org-name">
            {organizationName || 'Your Organization'}
          </Typography>
          <Chip label="Vendor" color="secondary" size="small" data-testid="vendor-chip" />
        </Box>
        <Typography variant="body1" color="textSecondary" data-testid="welcome-message">
          Welcome back, {user?.given_name || user?.email}. Manage your organization and applicants.
        </Typography>
        {organizationId && (
          <Typography variant="caption" color="textSecondary" data-testid="org-id">
            Organization ID: {organizationId}
          </Typography>
        )}
      </Box>

      {/* Stats Grid */}
      <Grid container spacing={3} sx={{ mb: 4 }} data-testid="stats-grid">
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="API Keys"
            value={stats.apiKeys}
            icon={<VpnKeyIcon />}
            color="primary"
            testId="stat-api-keys"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Active Applicants"
            value={stats.activeApplicants}
            icon={<PeopleIcon />}
            color="secondary"
            trend="+3 this week"
            testId="stat-active-applicants"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Credentials Issued"
            value={stats.credentialsIssued}
            icon={<CredentialIcon />}
            color="success"
            trend="+12 this month"
            testId="stat-credentials-issued"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Processing Fee"
            value={`$${stats.processingFee.toFixed(2)}`}
            icon={<AttachMoneyIcon />}
            color="warning"
            testId="stat-processing-fee"
          />
        </Grid>
      </Grid>

      {/* Quick Actions */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }} data-testid="quick-actions-panel">
            <Typography variant="h6" gutterBottom>
              Quick Actions
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <List disablePadding>
              <QuickAction
                title="Manage API Keys"
                description="Create and manage API keys for integrations"
                icon={<VpnKeyIcon color="primary" />}
                to="/vendor/api-keys"
                testId="action-api-keys"
              />
              <QuickAction
                title="Invite Applicants"
                description="Send email invitations to new applicants"
                icon={<PeopleIcon color="secondary" />}
                to="/vendor/invite"
                testId="action-invite-applicants"
              />
              <QuickAction
                title="Configure Devices"
                description="Manage mobile device fleet for your applicants"
                icon={<DevicesIcon color="info" />}
                to="/vendor/devices"
                testId="action-devices"
              />
              <QuickAction
                title="Processing Fees"
                description="Set and manage applicant processing fees"
                icon={<AttachMoneyIcon color="warning" />}
                to="/vendor/fees"
                testId="action-fees"
              />
            </List>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 2 }} data-testid="org-settings-panel">
            <Typography variant="h6" gutterBottom>
              Organization Settings
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <List disablePadding>
              <QuickAction
                title="Webhook Endpoints"
                description="Configure webhook notifications"
                icon={<WebhookIcon color="primary" />}
                to="/vendor/webhooks"
                testId="action-webhooks"
              />
              <QuickAction
                title="Credential Types"
                description="Configure available credential types"
                icon={<CredentialIcon color="success" />}
                to="/vendor/credentials"
                testId="action-credentials"
              />
              <QuickAction
                title="Organization Settings"
                description="Update organization profile and preferences"
                icon={<SettingsIcon color="action" />}
                to="/vendor/settings"
                testId="action-settings"
              />
            </List>
          </Paper>
        </Grid>
      </Grid>

      {/* Subscription Status */}
      <Paper sx={{ p: 2, mt: 3 }} data-testid="subscription-panel">
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h6">Subscription</Typography>
            <Typography variant="body2" color="textSecondary">
              Professional Plan • Renews Jan 15, 2026
            </Typography>
          </Box>
          <Button variant="outlined" component={Link} to="/vendor/subscription" data-testid="manage-subscription-btn">
            Manage Subscription
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}
