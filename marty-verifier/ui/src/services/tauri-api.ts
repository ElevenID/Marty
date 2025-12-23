/**
 * Tauri IPC API bindings
 * 
 * Type-safe wrappers for Rust commands exposed via Tauri.
 */

import { invoke } from '@tauri-apps/api/core';

// =============================================================================
// Types
// =============================================================================

export interface LicenseStatus {
  valid: boolean;
  org_id: string | null;
  expires_at: string | null;
  days_until_expiry: number | null;
  features: string[];
  hardware_bound: boolean;
  grace_period_active: boolean;
  grace_period_days: number | null;
  deployment_mode: string | null;
  max_daily_verifications: number | null;
  verifications_today: number;
}

export interface VerifyRequest {
  credential_type: string;
  credential_data: string;
  use_nfc?: boolean;
  liveness_challenge?: LivenessChallenge;
  require_liveness?: boolean;
  preferred_liveness_mode?: LivenessMode;
  allow_network_fallback?: boolean;
  accessibility_mode?: boolean;
  retain_audit_clip?: boolean;
  audit_clip_ttl_seconds?: number;
  session_id?: string;
  perform_face_match?: boolean;
  reference_image?: string;
  probe_image?: string;
  face_threshold?: number;
  policy?: VerificationPolicy;
}

export interface VerificationPolicy {
  required_claims: string[];
  age_threshold?: number;
  allow_expired_grace: boolean;
}

export interface VerificationResult {
  verification_id: string;
  status: 'valid' | 'invalid' | 'failed' | 'expired' | 'revoked' | 'pending';
  credential_type: string;
  issuer: IssuerInfo | null;
  disclosed_claims: Record<string, unknown>;
  trust_chain: TrustChainStatus;
  revocation_status: 'valid' | 'revoked' | 'unknown' | 'cached_valid';
  verified_at: string;
  warnings: string[];
  emrtd_details?: EmrtdDetails;
  liveness?: LivenessResult;
  face_match?: FaceMatchResponse;
}

export interface IssuerInfo {
  name: string | null;
  jurisdiction: string | null;
  subject: string | null;
}

export interface EmrtdDetails {
  dsc_chain_status: string;
  sod_signature_status: string;
  dg_hash_status: string;
  errors: string[];
}

export interface TrustChainStatus {
  valid: boolean;
  chain_type: string;
  trust_anchor: string | null;
  offline_verified: boolean;
}

export interface VerificationHistoryEntry {
  id: string;
  credential_type: string;
  status: string;
  verified_at: string;
  jurisdiction: string | null;
  synced: boolean;
}

export interface SyncStatus {
  last_sync: string | null;
  hours_since_sync: number | null;
  iaca_certificates: number;
  csca_certificates: number;
  dsc_certificates: number;
  crl_cache_age_hours: number | null;
  sync_overdue: boolean;
  sync_in_progress: boolean;
  last_error: string | null;
}

export interface SyncResult {
  success: boolean;
  iaca_updated: number;
  csca_updated: number;
  dsc_updated: number;
  crl_updated: boolean;
  duration_seconds: number;
  error: string | null;
}

export interface UsbImportResult {
  success: boolean;
  certificates_imported: number;
  signature_valid: boolean;
  package_version: string | null;
  error: string | null;
}

export interface HardwareCapabilities {
  has_camera: boolean;
  has_nfc: boolean;
  has_ble: boolean;
  has_tpm: boolean;
  has_biometric_sensor: boolean;
  has_usb_scanner: boolean;
}

export type HardwareTier = 'simple' | 'complex';

export interface OfflineQueueStatus {
  pending_events: number;
  oldest_event: string | null;
  data_size_bytes: number;
  last_sync_attempt: string | null;
  last_successful_sync: string | null;
}

export interface AppConfig {
  data_dir: string;
  license_public_key: string;
  liveness_retention: LivenessRetentionConfig;
  sync_config: SyncConfig;
  reporting_config: ReportingConfig;
  ui_config: UiConfig;
  retention: RetentionConfig;
}

export interface SyncConfig {
  aamva_dts_url: string | null;
  icao_pkd_url: string | null;
  sync_interval_hours: number;
  enable_usb_import: boolean;
  max_offline_hours: number;
}

export interface ReportingConfig {
  enabled: boolean;
  api_endpoint: string | null;
  batch_upload_endpoint: string | null;
  local_only: boolean;
  batch_interval_minutes: number;
  max_queue_size: number;
}

export interface UiConfig {
  hardware_tier_override: string | null;
  kiosk_mode: boolean;
  show_offline_banner: boolean;
  theme: string;
  language: string;
}

export interface RetentionConfig {
  verification_events_days: number;
  audit_log_days: number;
  encrypt_pii: boolean;
  redacted_fields: string[];
}

export interface LivenessRetentionConfig {
  default_audit_clip_ttl_seconds: number;
  max_audit_clip_ttl_seconds: number;
  encrypt_temp_media: boolean;
}

export type LivenessMode = 'unknown' | 'on_device' | 'network';
export type LivenessStepType = 'unknown' | 'head_pose' | 'blink' | 'phrase';

export interface LivenessStep {
  step_id: string;
  step_type: LivenessStepType;
  prompt?: string;
  pose_direction?: string;
  time_limit_ms?: number;
}

export interface LivenessChallenge {
  challenge_id: string;
  nonce: string;
  session_id: string;
  steps: LivenessStep[];
  issued_at: string;
  expires_at: string;
  signature: string;
  preferred_mode: LivenessMode;
  allow_network_fallback: boolean;
  accessibility_mode: boolean;
}

export interface FaceMatchRequest {
  reference_image: string;
  probe_image: string;
  threshold?: number;
  liveness_challenge?: LivenessChallenge;
  require_liveness?: boolean;
}

export interface FaceMatchResponse {
  verified: boolean;
  similarity: number;
  threshold: number;
  provider: string;
}

export interface LivenessScores {
  pad_score?: number;
  pose_score?: number;
  speech_score?: number;
  voice_spoof_score?: number;
  av_sync_score?: number;
}

export interface LivenessThresholds {
  min_pad_score?: number;
  min_pose_score?: number;
  min_speech_score?: number;
  min_voice_spoof_score?: number;
  min_av_sync_score?: number;
  fused_threshold?: number;
}

export interface LivenessResult {
  passed: boolean;
  fused_score: number;
  scores?: LivenessScores;
  thresholds?: LivenessThresholds;
  mode_used?: LivenessMode;
  errors?: string[];
  decision?: string;
}

export interface IssueLivenessChallengeRequest {
  session_id?: string;
  preferred_mode?: LivenessMode;
  allow_network_fallback?: boolean;
  accessibility_mode?: boolean;
  ttl_seconds?: number;
}

// =============================================================================
// License Commands
// =============================================================================

export async function validateLicense(licenseData: string): Promise<LicenseStatus> {
  return invoke('validate_license', { licenseData });
}

export async function getLicenseStatus(): Promise<LicenseStatus> {
  return invoke('get_license_status');
}

export async function getLicensedFeatures(): Promise<string[]> {
  return invoke('get_licensed_features');
}

// =============================================================================
// Verification Commands
// =============================================================================

export async function verifyCredential(request: VerifyRequest): Promise<VerificationResult> {
  return invoke('verify_credential', { request });
}

type IssueLivenessChallengeResponse = { challenge: LivenessChallenge };

export async function issueLivenessChallenge(
  request: IssueLivenessChallengeRequest,
): Promise<LivenessChallenge> {
  const { challenge } = await invoke<IssueLivenessChallengeResponse>('issue_liveness_challenge', {
    request,
  });
  return challenge;
}

export async function getVerificationHistory(limit?: number): Promise<VerificationHistoryEntry[]> {
  return invoke('get_verification_history', { limit });
}

export async function verifyFaceMatch(request: FaceMatchRequest): Promise<FaceMatchResponse> {
  return invoke('verify_face_match', { request });
}

// =============================================================================
// Storage Commands
// =============================================================================

export async function getOfflineQueueStatus(): Promise<OfflineQueueStatus> {
  return invoke('get_offline_queue_status');
}

export async function clearVerificationHistory(olderThanDays?: number): Promise<number> {
  return invoke('clear_verification_history', { olderThanDays });
}

// =============================================================================
// Sync Commands
// =============================================================================

export async function syncTrustAnchors(force?: boolean): Promise<SyncResult> {
  return invoke('sync_trust_anchors', { force });
}

export async function getSyncStatus(): Promise<SyncStatus> {
  return invoke('get_sync_status');
}

export async function importTrustAnchorsUsb(path: string): Promise<UsbImportResult> {
  return invoke('import_trust_anchors_usb', { path });
}

// =============================================================================
// Hardware Commands
// =============================================================================

export async function detectHardware(): Promise<HardwareCapabilities> {
  return invoke('detect_hardware');
}

export async function getHardwareTier(): Promise<HardwareTier> {
  return invoke('get_hardware_tier');
}

// =============================================================================
// Config Commands
// =============================================================================

export async function getConfig(): Promise<AppConfig> {
  return invoke('get_config');
}

export async function updateConfig(newConfig: AppConfig): Promise<void> {
  return invoke('update_config', { newConfig });
}
