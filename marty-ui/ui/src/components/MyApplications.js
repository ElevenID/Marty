/**
 * My Applications Component
 *
 * Applicant view showing their travel document applications and status.
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Button,
  CircularProgress,
  Alert,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useAuth } from '../hooks/useAuth';

// Application status colors
const STATUS_COLORS = {
  pending: 'warning',
  under_review: 'info',
  approved: 'success',
  rejected: 'error',
  completed: 'success',
};

// Application status labels
const STATUS_LABELS = {
  pending: 'Pending',
  under_review: 'Under Review',
  approved: 'Approved',
  rejected: 'Rejected',
  completed: 'Completed',
};

function MyApplications() {
  const { user } = useAuth();
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchApplications = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/applicants/me/applications', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to fetch applications');
      }

      const data = await response.json();
      setApplications(data.applications || []);
    } catch (err) {
      console.error('Error fetching applications:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApplications();
  }, []);

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1">
          My Applications
        </Typography>

        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={fetchApplications}>
            Refresh
          </Button>
          <Button variant="contained" startIcon={<AddIcon />}>
            New Application
          </Button>
        </Box>
      </Box>

      {/* Welcome Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Welcome, {user?.name || 'Applicant'}
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Track your travel document applications below. You can start a new application or check
            the status of existing ones.
          </Typography>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Loading State */}
      {loading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}

      {/* Applications Table */}
      {!loading && !error && (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Application ID</TableCell>
                <TableCell>Document Type</TableCell>
                <TableCell>Submitted</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Last Updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {applications.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography color="textSecondary" sx={{ py: 4 }}>
                      No applications found. Start a new application to begin your travel document
                      process.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                applications.map((app) => (
                  <TableRow key={app.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {app.id?.slice(0, 8)}...
                      </Typography>
                    </TableCell>
                    <TableCell>{app.document_type || 'Passport'}</TableCell>
                    <TableCell>{formatDate(app.submitted_at)}</TableCell>
                    <TableCell>
                      <Chip
                        label={STATUS_LABELS[app.status] || app.status}
                        color={STATUS_COLORS[app.status] || 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{formatDate(app.updated_at)}</TableCell>
                    <TableCell align="right">
                      <Button size="small">View Details</Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}

export default MyApplications;
