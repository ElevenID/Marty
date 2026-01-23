## White Paper: Digital Identity as Trust + Policy + Flows

### Executive summary

Digital identity is **not** a database record or a login. Digital identity is a **cryptographically verifiable set of claims** (about a person, device, organization, or entitlement) that can be **issued**, **held**, and **presented** under explicit rules of **trust** and **disclosure**.

Most identity systems fail adoption because they mix three concerns:

1. **Trust** (who is allowed to vouch for what)
2. **Policy** (what must be shown, to whom, and under what conditions)
3. **Orchestration** (how issuance + presentation happens across mobile, kiosks, and cloud)

We solve this by representing identity operations with four automatable primitives:

> **Digital identity management can be represented by: Trust Profiles + Credential Templates + Presentation Policies + Deployment Profiles, orchestrated by Flows.**

That’s the minimum set that makes issuing and verifying repeatable, secure, and deployable across real-world environments like airports, government gates, retail age checks, and employee access.

---

## What “digital identity” is

A digital identity system answers three questions reliably:

1. **Authenticity:** “Was this claim issued by an authority I trust?”
2. **Binding:** “Is the presenter the legitimate holder?”
3. **Appropriateness:** “Is the disclosed information the minimum necessary and allowed for this verifier and use case?”

So “identity” becomes a **transaction**:

* A verifier asks for a proof (policy).
* A holder shares a proof (presentation).
* The verifier validates it (trust + crypto + revocation).
* A relying party takes an action (grant boarding, sell alcohol, open door).

---

## The core model for automation

### 1) Trust Profile (TP)

**Purpose:** Define *who is trusted* and *how cryptographic validation happens.*

**Contains:**

* Trust sources: official lists/registries, pinned roots, issuer allow/deny lists
* Validation rules: chain building, allowed algorithms, key usage constraints
* Revocation policy: OCSP/CRL/status list; hard-fail vs soft-fail; offline grace
* Time policy: clock skew, freshness windows
* Format support: mdoc/mDL, VC, SD-JWT/Selective disclosure capabilities

**Stability:** changes rarely; owned by security/admin.

---

### 2) Credential Template (CT)

**Purpose:** Define *what is issued* (schema + semantics + constraints).

**Contains:**

* Credential type (e.g., Pre-Boarding Clearance, Employee Badge, Age Attestation)
* Claims map (what fields exist, derived attributes like `age_over_21`)
* Validity rules (TTL, reissue rules)
* Issuer requirements (which issuer keys can sign this template)
* Optional: privacy posture (fields intended to be selectively disclosable)

**Stability:** changes occasionally; owned by program/business + security.

---

### 2a) Compliance Profile (CP)

**Purpose:** Abstract credential format complexity behind compliance-focused profiles.

**Contains:**

* Compliance code (e.g., `ICAO_DTC`, `AAMVA_MDL`, `EUDI_PID`, `ENTERPRISE_VC`)
* Credential format mapping (mdoc, SD-JWT, JSON-LD, JWT-VC)
* Issuer artifact requirements per format
* Default claim verification rules
* Trust profile constraints
* System vs. custom flag

**Implementation:** Hides technical complexity (mdoc vs SD-JWT) from users by presenting compliance standards. Organizations can use system presets or create custom profiles.

**Stability:** changes rarely for system profiles; medium frequency for custom profiles; owned by compliance/security.

---

### 2b) Application Template (AT)

**Purpose:** Define *how users apply for credentials* (evidence + verification + artifacts).

**Contains:**

* Reference to Credential Template (what is issued)
* Reference to Compliance Profile (format abstraction)
* Evidence requirements (documents, biometrics, verifications needed)
* Claim verification rules (how claims are validated before issuance)
* Issuer cryptographic artifacts (signing keys, certificates, DIDs)
* Auto-generate artifacts flag (dev vs production behavior)
* Approval strategy and workflow configuration

**Implementation:** Extends Credential Template with application-specific requirements. Manages issuer artifacts with environment-aware behavior:
- Development: auto-generates missing keys/DIDs
- Production: validates artifacts exist, enforces HSM for sensitive formats

**Stability:** changes frequently; owned by operations/product.

---

### 3) Presentation Policy (PP)

**Purpose:** Define *what must be shown to satisfy a request* (minimum disclosure).

**Contains:**

* Accepted credential types/templates
* Required claims (e.g., `age_over_21=true` OR predicate proof)
* Holder-binding requirements (proof-of-possession, device binding, nonce/challenge)
* Issuer constraints (trusted issuers by TP, or explicit allowlist)
* Freshness constraints (issued within X hours, not revoked)
* Data minimization rules (prefer boolean over DOB; prefer derived attributes)

**Stability:** changes frequently; owned by product/ops/compliance.

---

### 4) Deployment Profile (DP) (Verifier Profile / Site / Device)

**Purpose:** Package trust + policies + runtime behavior for real endpoints.

**Contains:**

* Enabled flows (which policies are available)
* Default policy per profile
* Lanes: logical device groupings with optional policy overrides
* Network mode: online/offline, cache strategy
* UX config: language, signage text, operator mode, accessibility
* Update channel: version pinning, rollout rings, rollout percentage, audit logs
* Key access mode: key vault / signing agent / device keystore (BYOK strategy)

**Lanes:** A Lane is a logical grouping of devices (e.g., "Gate 12", "Checkpoint North") under a Deployment Profile. Each lane can have:
* Name and metadata (zone info, operator assignments)
* Device assignments (list of device IDs)
* Default policy override (optional lane-specific policy)

**Hierarchy:** Organization → Site → Deployment Profile → Lane(s) → Device(s)

**Stability:** changes frequently; owned by operations.

---

### 5) Flow (F)

**Purpose:** Orchestrate the end-to-end journey: apply → approve → issue → present → verify.

A Flow ties together:

* a Trust Profile
* a Credential Template (for issuance flows)
* a Presentation Policy (for verification)
* one or more Deployment Profiles (where verification happens)
* an Application Process (if user must apply/submit evidence)

Flows are where you get automation: state machines, events, approvals, retries, audit.

---

## Why this solves adoption

Non-technical organizations don’t want “PKI configuration.” They want:

* “Which ecosystem am I operating in?” (Trust Profile)
* “What are we issuing?” (Credential Template)
* “What do we ask for at the gate?” (Presentation Policy)
* “How do we roll it out to devices?” (Deployment Profile)
* “What is the operational sequence?” (Flow)

This model also makes compliance achievable because **each object maps cleanly to spec concerns**:

* Trust Profile → trust anchors, revocation, crypto compliance
* Presentation Policy → selective disclosure, claim minimization, verifier authorization
* Deployment Profile → endpoint behavior, offline rules, auditing
* Flow → protocol sequences (issuance and presentation), approvals, evidence

---

## The “pre-border screening” flow, expressed in the model

### Goal

Traveler scans passport after buying ticket → authority issues **Pre-Boarding Credential** → traveler presents at gate.

### Automated configuration

* **TP:** “Travel Trust” (ICAO/ePassport trust + authority issuer trust)
* **CT:** “Pre-Boarding Clearance” (flight binding, validity window, holder binding)
* **PP:** “Boarding Gate Check” (requires valid clearance, correct flight, freshness)
* **DP:** “Gate Lane Profile” (offline mode rules, camera/biometric optional, UI)
* **Flow:** “Pre-Board Clearance Issuance + Gate Verification”

### Automation sequence (operational)

1. **Flow starts** at booking/check-in (trigger from airline system)
2. **Application**: traveler submits passport scan + ticket reference
3. **Validation**: passport authenticity verified using TP (and ticket match)
4. **Approval**: automated or officer review
5. **Issue**: credential generated from CT and signed using issuer key strategy
6. **Present**: wallet presents at gate under PP (nonce/challenge)
7. **Verify**: gate uses DP+TP+PP; returns pass/fail + event log

This is exactly the order you listed — with one improvement:

* Treat “Application Template” as part of the Flow (or as its own object if you want reuse). In API design, it’s often best as `ApplicationTemplate` referenced by a Flow.

---

## Selective disclosure flows (age, employee) in one sentence each

* **Age check:** PP requires `age_over_21=true` from trusted government issuers (TP); DP ensures kiosk requests only that claim; flow returns a boolean decision + audit proof.
* **Employee access:** CT defines an employee badge; PP requires “active employment” + optional role; DP binds to site permissions; verifier returns access decision.

---

## API surface (minimal, composable)

Design your API around these resources (CRUD + versioning + publish):

* `TrustProfiles`
* `CredentialTemplates`
* `ComplianceProfiles` — NEW: abstract credential format complexity
* `ApplicationTemplates` — NEW: define application/issuance requirements
* `PresentationPolicies`
* `DeploymentProfiles`
* `Flows`
* `Applications` (instances created from Flow/ApplicationTemplate)
* `Issuance` (issue operations + status)
* `VerificationSessions` (presentation requests + results)
* `AuditEvents` (immutable log)

Key architectural principle:

* **Policies are data.** Endpoints execute them, not re-implement them.

**Implementation Note:** The API exposes compliance profiles and application templates through dedicated endpoints:
- `POST /v1/compliance-profiles` — Create/manage compliance configurations
- `POST /v1/application-templates` — Create/manage application requirements
- `POST /v1/application-templates/validate-artifacts` — Validate issuer artifacts
- Flow entity references `application_template_id` (mutually exclusive with `credential_template_id`)

---

## The core claim of the white paper

**Digital identity is a governed exchange of verifiable claims.**
It becomes automatable when you model it as **trust configuration (TP)** + **what is issued (CT)** + **what is requested (PP)** + **where it runs (DP)**, tied together by **flows (F)** that handle application, approval, issuance, and verification.