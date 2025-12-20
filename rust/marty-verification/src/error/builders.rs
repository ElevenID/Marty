//! Builder functions for creating VerificationError instances.
//!
//! These factory functions provide convenient ways to create error instances
//! with proper initialization of backtraces and span traces.

use tracing_error::SpanTrace;

use super::codes;
use super::types::{CapturedBacktrace, ErrorContext};
use super::verification_error::VerificationError;

impl VerificationError {
    /// Create an X5Chain parse error.
    pub fn x5chain_parse(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::X5ChainParseError {
            reason: reason.into(),
            code: codes::X5CHAIN_PARSE_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an X5Chain parse error with source.
    pub fn x5chain_parse_with_source(
        reason: impl Into<String>,
        source: impl std::error::Error + Send + Sync + 'static,
    ) -> Box<Self> {
        Box::new(Self::X5ChainParseError {
            reason: reason.into(),
            code: codes::X5CHAIN_PARSE_ERROR,
            context: ErrorContext::default(),
            source: Some(Box::new(source)),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an empty X5Chain error.
    pub fn x5chain_empty() -> Box<Self> {
        Box::new(Self::X5ChainEmpty {
            code: codes::X5CHAIN_EMPTY,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a missing X5Chain error.
    pub fn x5chain_missing() -> Box<Self> {
        Box::new(Self::X5ChainMissing {
            code: codes::X5CHAIN_MISSING,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a no trust anchor error.
    pub fn no_trust_anchor(details: impl Into<String>) -> Box<Self> {
        Box::new(Self::NoTrustAnchor {
            details: details.into(),
            code: codes::TRUST_NO_ANCHOR,
            context: ErrorContext::default(),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a no trust anchor error with context.
    pub fn no_trust_anchor_with_context(
        details: impl Into<String>,
        context: ErrorContext,
    ) -> Box<Self> {
        Box::new(Self::NoTrustAnchor {
            details: details.into(),
            code: codes::TRUST_NO_ANCHOR,
            context,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an empty registry error.
    pub fn empty_registry() -> Box<Self> {
        Box::new(Self::EmptyRegistry {
            code: codes::TRUST_EMPTY_REGISTRY,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a trust anchor load error.
    pub fn trust_anchor_load(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::TrustAnchorLoadError {
            reason: reason.into(),
            code: codes::TRUST_LOAD_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a certificate expired error.
    pub fn cert_expired(subject: impl Into<String>, expiry: impl Into<String>) -> Box<Self> {
        Box::new(Self::CertificateExpired {
            subject: subject.into(),
            expiry: expiry.into(),
            code: codes::CERT_EXPIRED,
            context: ErrorContext::default(),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a certificate not yet valid error.
    pub fn cert_not_yet_valid(
        subject: impl Into<String>,
        valid_from: impl Into<String>,
    ) -> Box<Self> {
        Box::new(Self::CertificateNotYetValid {
            subject: subject.into(),
            valid_from: valid_from.into(),
            code: codes::CERT_NOT_YET_VALID,
            context: ErrorContext::default(),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an invalid signature error.
    pub fn invalid_signature(subject: impl Into<String>, reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::InvalidSignature {
            subject: subject.into(),
            reason: reason.into(),
            code: codes::CERT_INVALID_SIGNATURE,
            context: ErrorContext::default(),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an issuer auth failed error.
    pub fn issuer_auth_failed(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::IssuerAuthFailed {
            reason: reason.into(),
            code: codes::AUTH_ISSUER_FAILED,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an issuer auth failed error with source.
    pub fn issuer_auth_failed_with_source(
        reason: impl Into<String>,
        source: impl std::error::Error + Send + Sync + 'static,
    ) -> Box<Self> {
        Box::new(Self::IssuerAuthFailed {
            reason: reason.into(),
            code: codes::AUTH_ISSUER_FAILED,
            context: ErrorContext::default(),
            source: Some(Box::new(source)),
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a DER error.
    pub fn der_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::DerError {
            reason: reason.into(),
            code: codes::DER_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a PEM error.
    pub fn pem_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::PemError {
            reason: reason.into(),
            code: codes::PEM_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an IO error.
    pub fn io_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::IoError {
            reason: reason.into(),
            code: codes::IO_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an internal error.
    pub fn internal(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: reason.into(),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a CBOR parsing error.
    pub fn cbor_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::CborError {
            reason: reason.into(),
            code: codes::CBOR_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a not-implemented error.
    pub fn not_implemented(feature: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("Not implemented: {}", feature.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a key parsing/handling error.
    pub fn key_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("Key error: {}", reason.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a signature error.
    pub fn signature_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("Signature error: {}", reason.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a parse error.
    pub fn parse_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("Parse error: {}", reason.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create an encoding error.
    pub fn encoding_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::DerError {
            reason: format!("Encoding error: {}", reason.into()),
            code: codes::DER_ERROR,
            context: ErrorContext::default(),
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a cryptographic operation error.
    pub fn crypto_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("Crypto error: {}", reason.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a network error.
    pub fn network_error(reason: impl Into<String>) -> Box<Self> {
        Box::new(Self::PkdFetchError {
            endpoint: "network".to_string(),
            reason: reason.into(),
            code: codes::PKD_FETCH_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }

    /// Create a JWK missing field error.
    pub fn jwk_missing_field(field: impl Into<String>) -> Box<Self> {
        Box::new(Self::Internal {
            reason: format!("JWK missing required field: {}", field.into()),
            code: codes::INTERNAL_ERROR,
            source: None,
            bt: CapturedBacktrace::capture(),
            span_trace: SpanTrace::capture(),
        })
    }
}
