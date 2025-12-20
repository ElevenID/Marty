/**
 * Application Form Component
 *
 * Multi-step wizard for applicants to apply for credentials (mDL, etc.)
 * Steps: Personal Info → Address → License Details → Photo Upload → Review & Submit
 */

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  Button,
  Stepper,
  Step,
  StepLabel,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Card,
  CardContent,
  Alert,
  CircularProgress,
  Checkbox,
  FormControlLabel,
  Chip,
  Avatar,
  Fade,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import PhotoCameraIcon from '@mui/icons-material/PhotoCamera';
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar';
import DeleteIcon from '@mui/icons-material/Delete';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { useAuth } from '../../hooks/useAuth';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// US States
const US_STATES = [
  { value: 'AL', label: 'Alabama' },
  { value: 'AK', label: 'Alaska' },
  { value: 'AZ', label: 'Arizona' },
  { value: 'AR', label: 'Arkansas' },
  { value: 'CA', label: 'California' },
  { value: 'CO', label: 'Colorado' },
  { value: 'CT', label: 'Connecticut' },
  { value: 'DE', label: 'Delaware' },
  { value: 'FL', label: 'Florida' },
  { value: 'GA', label: 'Georgia' },
  { value: 'HI', label: 'Hawaii' },
  { value: 'ID', label: 'Idaho' },
  { value: 'IL', label: 'Illinois' },
  { value: 'IN', label: 'Indiana' },
  { value: 'IA', label: 'Iowa' },
  { value: 'KS', label: 'Kansas' },
  { value: 'KY', label: 'Kentucky' },
  { value: 'LA', label: 'Louisiana' },
  { value: 'ME', label: 'Maine' },
  { value: 'MD', label: 'Maryland' },
  { value: 'MA', label: 'Massachusetts' },
  { value: 'MI', label: 'Michigan' },
  { value: 'MN', label: 'Minnesota' },
  { value: 'MS', label: 'Mississippi' },
  { value: 'MO', label: 'Missouri' },
  { value: 'MT', label: 'Montana' },
  { value: 'NE', label: 'Nebraska' },
  { value: 'NV', label: 'Nevada' },
  { value: 'NH', label: 'New Hampshire' },
  { value: 'NJ', label: 'New Jersey' },
  { value: 'NM', label: 'New Mexico' },
  { value: 'NY', label: 'New York' },
  { value: 'NC', label: 'North Carolina' },
  { value: 'ND', label: 'North Dakota' },
  { value: 'OH', label: 'Ohio' },
  { value: 'OK', label: 'Oklahoma' },
  { value: 'OR', label: 'Oregon' },
  { value: 'PA', label: 'Pennsylvania' },
  { value: 'RI', label: 'Rhode Island' },
  { value: 'SC', label: 'South Carolina' },
  { value: 'SD', label: 'South Dakota' },
  { value: 'TN', label: 'Tennessee' },
  { value: 'TX', label: 'Texas' },
  { value: 'UT', label: 'Utah' },
  { value: 'VT', label: 'Vermont' },
  { value: 'VA', label: 'Virginia' },
  { value: 'WA', label: 'Washington' },
  { value: 'WV', label: 'West Virginia' },
  { value: 'WI', label: 'Wisconsin' },
  { value: 'WY', label: 'Wyoming' },
];

// License classes
const LICENSE_CLASSES = [
  { value: 'A', label: 'Class A - Commercial (Combination Vehicles)' },
  { value: 'B', label: 'Class B - Commercial (Single Vehicles)' },
  { value: 'C', label: 'Class C - Standard (Non-Commercial)' },
  { value: 'M', label: 'Class M - Motorcycle' },
];

const STEPS = ['Personal Information', 'Address', 'License Details', 'Photo Upload', 'Review & Submit'];

export default function ApplicationForm() {
  const { credentialType } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const fileInputRef = useRef(null);

  const [activeStep, setActiveStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [submitted, setSubmitted] = useState(false);
  const [applicationId, setApplicationId] = useState(null);

  // Form data
  const [formData, setFormData] = useState({
    // Personal Info
    firstName: '',
    lastName: '',
    dateOfBirth: '',
    email: user?.email || '',
    
    // Address
    street: '',
    city: '',
    state: '',
    zip: '',
    
    // License Details
    licenseClass: 'C',
    documentNumber: '',
    restrictions: '',
    
    // Photo
    portrait: null,
    portraitPreview: null,
    
    // Terms
    acceptTerms: false,
  });

  // Validation errors
  const [validationErrors, setValidationErrors] = useState({});

  useEffect(() => {
    // Pre-fill user email
    if (user?.email) {
      setFormData(prev => ({ ...prev, email: user.email }));
    }
  }, [user]);

  const handleInputChange = (field) => (event) => {
    setFormData(prev => ({
      ...prev,
      [field]: event.target.value
    }));
    // Clear validation error when field is edited
    if (validationErrors[field]) {
      setValidationErrors(prev => ({ ...prev, [field]: null }));
    }
  };

  const handlePhotoUpload = (event) => {
    const file = event.target.files[0];
    if (file) {
      // Validate file type
      if (!file.type.startsWith('image/')) {
        setError('Please upload an image file');
        return;
      }
      // Validate file size (max 5MB)
      if (file.size > 5 * 1024 * 1024) {
        setError('Photo must be less than 5MB');
        return;
      }

      setFormData(prev => ({
        ...prev,
        portrait: file,
        portraitPreview: URL.createObjectURL(file)
      }));
      setError(null);
    }
  };

  const handleRemovePhoto = () => {
    if (formData.portraitPreview) {
      URL.revokeObjectURL(formData.portraitPreview);
    }
    setFormData(prev => ({
      ...prev,
      portrait: null,
      portraitPreview: null
    }));
  };

  const validateStep = (step) => {
    const errors = {};
    
    switch (step) {
      case 0: // Personal Info
        if (!formData.firstName.trim()) errors.firstName = 'First name is required';
        if (!formData.lastName.trim()) errors.lastName = 'Last name is required';
        if (!formData.dateOfBirth) errors.dateOfBirth = 'Date of birth is required';
        if (!formData.email.trim()) errors.email = 'Email is required';
        break;
        
      case 1: // Address
        if (!formData.street.trim()) errors.street = 'Street address is required';
        if (!formData.city.trim()) errors.city = 'City is required';
        if (!formData.state) errors.state = 'State is required';
        if (!formData.zip.trim()) errors.zip = 'ZIP code is required';
        if (formData.zip && !/^\d{5}(-\d{4})?$/.test(formData.zip)) {
          errors.zip = 'Invalid ZIP code format';
        }
        break;
        
      case 2: // License Details
        if (!formData.licenseClass) errors.licenseClass = 'License class is required';
        if (!formData.documentNumber.trim()) errors.documentNumber = 'Document number is required';
        break;
        
      case 3: // Photo
        if (!formData.portrait) errors.portrait = 'Portrait photo is required';
        break;
        
      case 4: // Review
        if (!formData.acceptTerms) errors.acceptTerms = 'You must accept the terms';
        break;
        
      default:
        break;
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleNext = () => {
    if (validateStep(activeStep)) {
      setActiveStep(prev => prev + 1);
    }
  };

  const handleBack = () => {
    setActiveStep(prev => prev - 1);
  };

  const handleSubmit = async () => {
    if (!validateStep(activeStep)) return;

    setSubmitting(true);
    setError(null);

    try {
      // Create FormData for multipart upload
      const submitData = new FormData();
      submitData.append('credential_type', credentialType || 'mdl');
      submitData.append('first_name', formData.firstName);
      submitData.append('last_name', formData.lastName);
      submitData.append('date_of_birth', formData.dateOfBirth);
      submitData.append('email', formData.email);
      submitData.append('street', formData.street);
      submitData.append('city', formData.city);
      submitData.append('state', formData.state);
      submitData.append('zip', formData.zip);
      submitData.append('license_class', formData.licenseClass);
      submitData.append('document_number', formData.documentNumber);
      submitData.append('restrictions', formData.restrictions);
      if (formData.portrait) {
        submitData.append('portrait', formData.portrait);
      }

      const response = await fetch(`${API_URL}/api/applications/submit`, {
        method: 'POST',
        credentials: 'include',
        body: submitData,
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to submit application');
      }

      const data = await response.json();
      setApplicationId(data.application_id);
      setSubmitted(true);

      // Redirect after delay
      setTimeout(() => {
        navigate('/my-applications');
      }, 5000);
    } catch (err) {
      console.error('Error submitting application:', err);
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const renderPersonalInfoStep = () => (
    <Box data-testid="personal-info-step">
      <Typography variant="h6" gutterBottom>
        Personal Information
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Enter your personal details as they appear on your government-issued ID.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            required
            label="First Name"
            value={formData.firstName}
            onChange={handleInputChange('firstName')}
            error={!!validationErrors.firstName}
            helperText={validationErrors.firstName}
            data-testid="first-name-input"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            required
            label="Last Name"
            value={formData.lastName}
            onChange={handleInputChange('lastName')}
            error={!!validationErrors.lastName}
            helperText={validationErrors.lastName}
            data-testid="last-name-input"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            required
            type="date"
            label="Date of Birth"
            value={formData.dateOfBirth}
            onChange={handleInputChange('dateOfBirth')}
            error={!!validationErrors.dateOfBirth}
            helperText={validationErrors.dateOfBirth}
            InputLabelProps={{ shrink: true }}
            data-testid="dob-input"
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            required
            type="email"
            label="Email Address"
            value={formData.email}
            onChange={handleInputChange('email')}
            error={!!validationErrors.email}
            helperText={validationErrors.email}
            data-testid="email-input"
          />
        </Grid>
      </Grid>
    </Box>
  );

  const renderAddressStep = () => (
    <Box data-testid="address-step">
      <Typography variant="h6" gutterBottom>
        Residential Address
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Enter your current residential address.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <TextField
            fullWidth
            required
            label="Street Address"
            value={formData.street}
            onChange={handleInputChange('street')}
            error={!!validationErrors.street}
            helperText={validationErrors.street}
            data-testid="street-input"
          />
        </Grid>
        <Grid item xs={12} md={5}>
          <TextField
            fullWidth
            required
            label="City"
            value={formData.city}
            onChange={handleInputChange('city')}
            error={!!validationErrors.city}
            helperText={validationErrors.city}
            data-testid="city-input"
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <FormControl fullWidth required error={!!validationErrors.state}>
            <InputLabel>State</InputLabel>
            <Select
              value={formData.state}
              onChange={handleInputChange('state')}
              label="State"
              data-testid="state-select"
            >
              {US_STATES.map(s => (
                <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={3}>
          <TextField
            fullWidth
            required
            label="ZIP Code"
            value={formData.zip}
            onChange={handleInputChange('zip')}
            error={!!validationErrors.zip}
            helperText={validationErrors.zip}
            data-testid="zip-input"
          />
        </Grid>
      </Grid>
    </Box>
  );

  const renderLicenseStep = () => (
    <Box data-testid="license-step">
      <Typography variant="h6" gutterBottom>
        License Details
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Enter your driving license information.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth required error={!!validationErrors.licenseClass}>
            <InputLabel>License Class</InputLabel>
            <Select
              value={formData.licenseClass}
              onChange={handleInputChange('licenseClass')}
              label="License Class"
              data-testid="license-class-select"
            >
              {LICENSE_CLASSES.map(lc => (
                <MenuItem key={lc.value} value={lc.value}>{lc.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={6}>
          <TextField
            fullWidth
            required
            label="Document Number"
            value={formData.documentNumber}
            onChange={handleInputChange('documentNumber')}
            error={!!validationErrors.documentNumber}
            helperText={validationErrors.documentNumber || 'Your current license number'}
            data-testid="document-number-input"
          />
        </Grid>
        <Grid item xs={12}>
          <TextField
            fullWidth
            label="Restrictions (if any)"
            value={formData.restrictions}
            onChange={handleInputChange('restrictions')}
            placeholder="e.g., Corrective lenses required"
            data-testid="restrictions-input"
          />
        </Grid>
      </Grid>
    </Box>
  );

  const renderPhotoStep = () => (
    <Box data-testid="photo-step">
      <Typography variant="h6" gutterBottom>
        Portrait Photo
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Upload a recent passport-style photo. Face must be clearly visible with neutral expression.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
            {formData.portraitPreview ? (
              <Box>
                <Avatar
                  src={formData.portraitPreview}
                  sx={{ width: 150, height: 150, mx: 'auto', mb: 2 }}
                  data-testid="photo-preview"
                />
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteIcon />}
                  onClick={handleRemovePhoto}
                  sx={{ mr: 1 }}
                >
                  Remove
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<PhotoCameraIcon />}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Change
                </Button>
              </Box>
            ) : (
              <Box>
                <Avatar sx={{ width: 150, height: 150, mx: 'auto', mb: 2, bgcolor: 'grey.200' }}>
                  <PhotoCameraIcon sx={{ fontSize: 60, color: 'grey.400' }} />
                </Avatar>
                <Button
                  variant="contained"
                  startIcon={<UploadFileIcon />}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload Photo
                </Button>
              </Box>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={handlePhotoUpload}
              data-testid="portrait-upload-input"
            />
            {validationErrors.portrait && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {validationErrors.portrait}
              </Alert>
            )}
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Photo Requirements:
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText primary="• Clear, focused image" />
              </ListItem>
              <ListItem>
                <ListItemText primary="• Full face visible, eyes open" />
              </ListItem>
              <ListItem>
                <ListItemText primary="• Neutral expression" />
              </ListItem>
              <ListItem>
                <ListItemText primary="• Plain white or light background" />
              </ListItem>
              <ListItem>
                <ListItemText primary="• No hats or head coverings (except religious)" />
              </ListItem>
              <ListItem>
                <ListItemText primary="• Maximum file size: 5MB" />
              </ListItem>
            </List>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderReviewStep = () => (
    <Box data-testid="review-step">
      <Typography variant="h6" gutterBottom>
        Review Your Application
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Please review your information before submitting.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Personal Information
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">First Name</Typography>
                  <Typography data-testid="review-first-name">{formData.firstName}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Last Name</Typography>
                  <Typography data-testid="review-last-name">{formData.lastName}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Date of Birth</Typography>
                  <Typography>{formData.dateOfBirth}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Email</Typography>
                  <Typography>{formData.email}</Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Address
              </Typography>
              <Typography>{formData.street}</Typography>
              <Typography>{formData.city}, {formData.state} {formData.zip}</Typography>
            </CardContent>
          </Card>

          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                License Details
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">License Class</Typography>
                  <Typography>{formData.licenseClass}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Document Number</Typography>
                  <Typography>{formData.documentNumber}</Typography>
                </Grid>
                {formData.restrictions && (
                  <Grid item xs={12}>
                    <Typography variant="body2" color="text.secondary">Restrictions</Typography>
                    <Typography>{formData.restrictions}</Typography>
                  </Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          {formData.portraitPreview && (
            <Card variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Portrait Photo
              </Typography>
              <Avatar
                src={formData.portraitPreview}
                sx={{ width: 120, height: 120, mx: 'auto' }}
              />
            </Card>
          )}
        </Grid>

        <Grid item xs={12}>
          <FormControlLabel
            control={
              <Checkbox
                checked={formData.acceptTerms}
                onChange={(e) => setFormData(prev => ({ ...prev, acceptTerms: e.target.checked }))}
                data-testid="accept-terms-checkbox"
              />
            }
            label="I certify that all information provided is accurate and complete. I understand that providing false information may result in denial of my application."
          />
          {validationErrors.acceptTerms && (
            <Typography color="error" variant="caption" display="block">
              {validationErrors.acceptTerms}
            </Typography>
          )}
        </Grid>
      </Grid>
    </Box>
  );

  const renderSubmittedState = () => (
    <Fade in>
      <Box sx={{ textAlign: 'center', py: 6 }} data-testid="application-submitted">
        <CheckCircleIcon sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
        <Typography variant="h4" gutterBottom>
          Application Submitted!
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Your mDL application has been submitted successfully.
        </Typography>
        
        {applicationId && (
          <Chip
            label={`Application ID: ${applicationId}`}
            color="primary"
            variant="outlined"
            sx={{ mb: 3 }}
            data-testid="application-id"
            data-value={applicationId}
          />
        )}

        <Alert severity="info" sx={{ maxWidth: 400, mx: 'auto', mb: 3 }}>
          You will receive updates on your application status via email. Redirecting to your applications page...
        </Alert>

        <Button
          variant="contained"
          onClick={() => navigate('/my-applications')}
        >
          View My Applications
        </Button>
      </Box>
    </Fade>
  );

  const stepContent = [
    renderPersonalInfoStep,
    renderAddressStep,
    renderLicenseStep,
    renderPhotoStep,
    renderReviewStep,
  ];

  if (submitted) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Paper sx={{ p: 4 }}>
          {renderSubmittedState()}
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="md" sx={{ py: 4 }} data-testid="mdl-application-form">
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <DirectionsCarIcon color="primary" fontSize="large" />
          <Typography variant="h4" component="h1">
            Mobile Driver's License Application
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary">
          Complete the form below to apply for your mDL credential.
        </Typography>
      </Box>

      {/* Stepper */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Stepper activeStep={activeStep} alternativeLabel>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Paper>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Form Content */}
      <Paper sx={{ p: 4, mb: 3 }}>
        {stepContent[activeStep]()}
      </Paper>

      {/* Navigation */}
      <Paper sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button
            disabled={activeStep === 0}
            onClick={handleBack}
            startIcon={<ArrowBackIcon />}
          >
            Back
          </Button>

          {activeStep < STEPS.length - 1 ? (
            <Button
              variant="contained"
              onClick={handleNext}
              endIcon={<ArrowForwardIcon />}
              data-testid="next-step-btn"
            >
              Next
            </Button>
          ) : (
            <Button
              variant="contained"
              color="success"
              onClick={handleSubmit}
              disabled={submitting}
              endIcon={submitting ? <CircularProgress size={20} /> : <CheckCircleIcon />}
              data-testid="submit-application-btn"
            >
              {submitting ? 'Submitting...' : 'Submit Application'}
            </Button>
          )}
        </Box>
      </Paper>
    </Container>
  );
}
