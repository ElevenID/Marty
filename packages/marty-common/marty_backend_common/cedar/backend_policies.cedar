// ============================================================================
// MIP Backend Policies — Role-Based Access Control for gRPC Services
// ============================================================================
//
// These policies replace the YAML-based policy.yaml configuration with
// Cedar's formal policy language. They define which roles can perform
// which actions on backend service resources.
//
// Evaluation: deny-by-default. At least one permit must match, and zero
// forbid policies may match, for the request to be authorized.
// ============================================================================

// ── Admin: full access to all actions ─────────────────────────────────────

@id("role-admin-full-access")
permit (
    principal is MIP::User,
    action,
    resource
)
when {
    principal in MIP::Role::"admin"
};

// ── Document Signer: document signing and certificate validation ──────────

@id("role-document-signer")
permit (
    principal is MIP::User,
    action in [
        MIP::Action::"document:sign",
        MIP::Action::"document:verify",
        MIP::Action::"certificate:validate"
    ],
    resource
)
when {
    principal in MIP::Role::"document_signer"
};

// ── Inspection Officer: document and travel document verification ─────────

@id("role-inspection-officer")
permit (
    principal is MIP::User,
    action in [
        MIP::Action::"document:inspect",
        MIP::Action::"document:verify",
        MIP::Action::"passport:verify",
        MIP::Action::"mdl:verify"
    ],
    resource
)
when {
    principal in MIP::Role::"inspection_officer"
};

// ── Trust Manager: trust and certificate management ───────────────────────

@id("role-trust-manager")
permit (
    principal is MIP::User,
    action in [
        MIP::Action::"trust:manage",
        MIP::Action::"trust:query",
        MIP::Action::"certificate:issue",
        MIP::Action::"certificate:revoke"
    ],
    resource
)
when {
    principal in MIP::Role::"trust_manager"
};

// ── Service Account: health and metrics only ──────────────────────────────

@id("role-service-account")
permit (
    principal is MIP::ServiceAccount,
    action in [
        MIP::Action::"service:health",
        MIP::Action::"service:metrics"
    ],
    resource
)
when { true };

// ── Administrator: full document, applicant, application, and KYC mgmt ───

@id("role-administrator")
permit (
    principal is MIP::User,
    action in [
        MIP::Action::"document:create",
        MIP::Action::"document:read",
        MIP::Action::"document:update",
        MIP::Action::"document:sign",
        MIP::Action::"document:verify",
        MIP::Action::"document:revoke",
        MIP::Action::"applicant:read",
        MIP::Action::"applicant:update",
        MIP::Action::"applicant:vet",
        MIP::Action::"application:read",
        MIP::Action::"application:create",
        MIP::Action::"application:update",
        MIP::Action::"application:approve",
        MIP::Action::"application:reject",
        MIP::Action::"vetting:create",
        MIP::Action::"vetting:read",
        MIP::Action::"vetting:update",
        MIP::Action::"biometric:enroll",
        MIP::Action::"biometric:verify",
        MIP::Action::"kyc:review",
        MIP::Action::"kyc:approve",
        MIP::Action::"kyc:reject"
    ],
    resource
)
when {
    principal in MIP::Role::"administrator"
};

// ── Applicant: self-service access to own resources ───────────────────────
// Note: resource-level ownership scoping must be enforced at the service
// layer. This policy gates which actions the applicant role can invoke.

@id("role-applicant")
permit (
    principal is MIP::User,
    action in [
        MIP::Action::"application:create",
        MIP::Action::"application:read",
        MIP::Action::"application:update",
        MIP::Action::"document:read",
        MIP::Action::"kyc:submit",
        MIP::Action::"profile:read",
        MIP::Action::"profile:update"
    ],
    resource
)
when {
    principal in MIP::Role::"applicant"
};

// ── Forbid: suspended or deactivated users ────────────────────────────────

@id("deny-suspended-users")
forbid (
    principal is MIP::User,
    action,
    resource
)
when {
    principal.status == "SUSPENDED" ||
    principal.status == "DEACTIVATED"
};
