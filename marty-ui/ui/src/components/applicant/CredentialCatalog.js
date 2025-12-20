/**
 * CredentialCatalog Component
 * 
 * Displays available credentials for applicants to apply for.
 * Credentials are filtered based on the vendor organization's configuration.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Container,
  Grid,
  Paper,
  Typography,
  Box,
  Card,
  CardContent,
  CardMedia,
  CardActions,
  Button,
  Chip,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Skeleton,
  Alert,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider
} from '@mui/material';
import {
  Search as SearchIcon,
  FilterList as FilterIcon,
  CardMembership as CredentialIcon,
  Flight as PassportIcon,
  DirectionsCar as DLIcon,
  Badge as BadgeIcon,
  Info as InfoIcon,
  CheckCircle as CheckIcon,
  Schedule as PendingIcon,
  AttachMoney as PriceIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

// Credential types configuration
const CREDENTIAL_TYPES = {
  PASSPORT: {
    id: 'passport',
    name: 'Digital Passport',
    description: 'ICAO 9303 compliant digital travel credential with NFC capability',
    icon: PassportIcon,
    category: 'travel',
    processingTime: '5-10 business days',
    requirements: ['Government-issued ID', 'Proof of citizenship', 'Biometric photo']
  },
  MDL: {
    id: 'mdl',
    name: 'Mobile Driver\'s License',
    description: 'ISO/IEC 18013-5 compliant mobile driving license',
    icon: DLIcon,
    category: 'identity',
    processingTime: '3-5 business days',
    requirements: ['Current driver\'s license', 'Proof of residence', 'Biometric photo']
  },
  MDOC: {
    id: 'mdoc',
    name: 'Mobile Document (mDoc)',
    description: 'Generic mobile document credential for various use cases',
    icon: BadgeIcon,
    category: 'identity',
    processingTime: '1-3 business days',
    requirements: ['Valid government ID', 'Supporting documents']
  },
  EMPLOYEE_BADGE: {
    id: 'employee_badge',
    name: 'Employee Badge',
    description: 'Corporate employee identification credential',
    icon: BadgeIcon,
    category: 'enterprise',
    processingTime: '1-2 business days',
    requirements: ['Employment verification', 'Photo ID']
  },
  ACCESS_CREDENTIAL: {
    id: 'access_credential',
    name: 'Access Credential',
    description: 'Physical and digital access control credential',
    icon: CredentialIcon,
    category: 'enterprise',
    processingTime: 'Same day',
    requirements: ['Authorization from sponsor', 'Photo ID']
  }
};

const CATEGORIES = [
  { value: 'all', label: 'All Categories' },
  { value: 'travel', label: 'Travel Documents' },
  { value: 'identity', label: 'Identity Documents' },
  { value: 'enterprise', label: 'Enterprise Credentials' }
];

const CredentialCatalog = () => {
  const navigate = useNavigate();
  const { organizationId, organizationName } = useAuth();
  
  // State
  const [credentials, setCredentials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [selectedCredential, setSelectedCredential] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [existingApplications, setExistingApplications] = useState([]);

  useEffect(() => {
    fetchAvailableCredentials();
    fetchExistingApplications();
  }, [organizationId]);

  /**
   * Fetch credentials available to applicants of this organization
   */
  const fetchAvailableCredentials = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/applicant/credentials?orgId=${organizationId}`);
      if (response.ok) {
        const data = await response.json();
        setCredentials(data);
      } else {
        // Fallback to showing default credentials based on organization config
        console.warn('Credentials API not available, using defaults');
        setCredentials(
          Object.values(CREDENTIAL_TYPES).map(type => ({
            ...type,
            available: true,
            processingFee: Math.floor(Math.random() * 30) + 5, // Random fee for demo
            vendorName: organizationName || 'Demo Vendor'
          }))
        );
      }
    } catch (error) {
      console.error('Failed to fetch credentials:', error);
      // Show all credential types as fallback
      setCredentials(Object.values(CREDENTIAL_TYPES));
    } finally {
      setLoading(false);
    }
  };

  /**
   * Fetch applicant's existing applications
   */
  const fetchExistingApplications = async () => {
    try {
      const response = await fetch('/api/applicant/applications');
      if (response.ok) {
        const data = await response.json();
        setExistingApplications(data.map(app => app.credentialId));
      }
    } catch (error) {
      console.error('Failed to fetch applications:', error);
    }
  };

  /**
   * Filter credentials based on search and category
   */
  const filteredCredentials = useMemo(() => {
    return credentials.filter(cred => {
      const matchesSearch = cred.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           cred.description.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCategory = categoryFilter === 'all' || cred.category === categoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [credentials, searchTerm, categoryFilter]);

  /**
   * Handle credential application
   */
  const handleApply = (credential) => {
    navigate(`/apply/${credential.id}`, {
      state: {
        credential,
        processingFee: credential.processingFee
      }
    });
  };

  /**
   * Open credential details modal
   */
  const handleViewDetails = (credential) => {
    setSelectedCredential(credential);
    setDetailsOpen(true);
  };

  /**
   * Check if already applied for credential
   */
  const hasExistingApplication = (credentialId) => {
    return existingApplications.includes(credentialId);
  };

  /**
   * Get application status chip
   */
  const getApplicationStatus = (credentialId) => {
    if (hasExistingApplication(credentialId)) {
      return (
        <Chip
          icon={<PendingIcon />}
          label="Application Pending"
          size="small"
          color="warning"
          sx={{ mt: 1 }}
        />
      );
    }
    return null;
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          <CredentialIcon sx={{ mr: 2, verticalAlign: 'middle' }} />
          Credential Catalog
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Browse and apply for available credentials
          {organizationName && ` from ${organizationName}`}
        </Typography>
      </Box>

      {/* Search and Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              placeholder="Search credentials..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                )
              }}
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>Category</InputLabel>
              <Select
                value={categoryFilter}
                label="Category"
                onChange={(e) => setCategoryFilter(e.target.value)}
                startAdornment={
                  <InputAdornment position="start">
                    <FilterIcon />
                  </InputAdornment>
                }
              >
                {CATEGORIES.map(cat => (
                  <MenuItem key={cat.value} value={cat.value}>
                    {cat.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              {filteredCredentials.length} credential{filteredCredentials.length !== 1 ? 's' : ''} found
            </Typography>
          </Grid>
        </Grid>
      </Paper>

      {/* Credential Grid */}
      <Grid container spacing={3}>
        {loading ? (
          // Loading skeletons
          [...Array(6)].map((_, index) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <Card>
                <Skeleton variant="rectangular" height={140} />
                <CardContent>
                  <Skeleton variant="text" width="60%" />
                  <Skeleton variant="text" />
                  <Skeleton variant="text" width="80%" />
                </CardContent>
              </Card>
            </Grid>
          ))
        ) : filteredCredentials.length === 0 ? (
          <Grid item xs={12}>
            <Alert severity="info">
              No credentials match your search criteria. Try adjusting your filters.
            </Alert>
          </Grid>
        ) : (
          filteredCredentials.map((credential) => {
            const IconComponent = credential.icon || CredentialIcon;
            const hasApplied = hasExistingApplication(credential.id);
            
            return (
              <Grid item xs={12} sm={6} md={4} key={credential.id}>
                <Card 
                  sx={{ 
                    height: '100%', 
                    display: 'flex', 
                    flexDirection: 'column',
                    opacity: hasApplied ? 0.8 : 1
                  }}
                >
                  <Box 
                    sx={{ 
                      p: 3, 
                      display: 'flex', 
                      justifyContent: 'center',
                      bgcolor: 'primary.light',
                      color: 'white'
                    }}
                  >
                    <IconComponent sx={{ fontSize: 64 }} />
                  </Box>
                  <CardContent sx={{ flexGrow: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <Typography variant="h6" gutterBottom>
                        {credential.name}
                      </Typography>
                      <Tooltip title="View details">
                        <IconButton 
                          size="small" 
                          onClick={() => handleViewDetails(credential)}
                        >
                          <InfoIcon />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {credential.description}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                      <Chip 
                        label={credential.category} 
                        size="small" 
                        variant="outlined" 
                      />
                      <Chip 
                        icon={<PriceIcon />}
                        label={credential.processingFee ? `$${credential.processingFee}` : 'Free'} 
                        size="small" 
                        color={credential.processingFee ? 'default' : 'success'}
                      />
                    </Box>
                    {getApplicationStatus(credential.id)}
                  </CardContent>
                  <CardActions sx={{ p: 2, pt: 0 }}>
                    <Button
                      fullWidth
                      variant={hasApplied ? 'outlined' : 'contained'}
                      disabled={hasApplied}
                      onClick={() => handleApply(credential)}
                    >
                      {hasApplied ? 'Application Pending' : 'Apply Now'}
                    </Button>
                  </CardActions>
                </Card>
              </Grid>
            );
          })
        )}
      </Grid>

      {/* Credential Details Dialog */}
      <Dialog
        open={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        {selectedCredential && (
          <>
            <DialogTitle>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {React.createElement(selectedCredential.icon || CredentialIcon)}
                {selectedCredential.name}
              </Box>
            </DialogTitle>
            <DialogContent>
              <Typography variant="body1" paragraph>
                {selectedCredential.description}
              </Typography>
              
              <Divider sx={{ my: 2 }} />
              
              <Typography variant="subtitle2" gutterBottom>
                Processing Time
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                {selectedCredential.processingTime}
              </Typography>
              
              <Typography variant="subtitle2" gutterBottom>
                Processing Fee
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                {selectedCredential.processingFee 
                  ? `$${selectedCredential.processingFee}` 
                  : 'No fee required'}
              </Typography>
              
              <Typography variant="subtitle2" gutterBottom>
                Requirements
              </Typography>
              <List dense>
                {(selectedCredential.requirements || []).map((req, index) => (
                  <ListItem key={index}>
                    <ListItemIcon>
                      <CheckIcon color="success" fontSize="small" />
                    </ListItemIcon>
                    <ListItemText primary={req} />
                  </ListItem>
                ))}
              </List>
              
              {selectedCredential.vendorName && (
                <>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="caption" color="text.secondary">
                    Offered by: {selectedCredential.vendorName}
                  </Typography>
                </>
              )}
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDetailsOpen(false)}>
                Close
              </Button>
              <Button
                variant="contained"
                onClick={() => {
                  setDetailsOpen(false);
                  handleApply(selectedCredential);
                }}
                disabled={hasExistingApplication(selectedCredential.id)}
              >
                Apply Now
              </Button>
            </DialogActions>
          </>
        )}
      </Dialog>
    </Container>
  );
};

export default CredentialCatalog;
