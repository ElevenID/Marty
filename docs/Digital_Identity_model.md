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
* **Revocation Profile reference:** Links to a RevocationProfile for revocation configuration (see RevocationProfile abstraction)
* Time policy: clock skew, freshness windows
* Format support: mdoc/mDL, VC, SD-JWT/Selective disclosure capabilities

**Revocation Handling:**

Trust Profiles reference a **RevocationProfile** (new abstraction) that encapsulates all revocation complexity:
* Format-agnostic configuration (OCSP, CRL, StatusList2021, BitstringStatusList, TokenStatusList)
* Issuer-side automation (index allocation, publishing, batch updates)
* Verifier-side behavior (check mode, caching, offline grace, mechanism priority)
* See [RevocationProfile Proposal](./RevocationProfile_Proposal.md) for full details

**Stability:** changes rarely; owned by security/admin.

---

### 2) Credential Template (CT)

**Purpose:** Define the *complete credential issuance configuration* (schema + profiles + crypto + validity).

**Contains:**

* Credential type (e.g., Pre-Boarding Clearance, Employee Badge, mDL, Age Attestation)
* Claims map (what fields exist, types, derived attributes like `age_over_21`)
* **Application Template reference** (optional - for application-based issuance)
* **Compliance Profile reference** (required - format and framework selection)
* **Trust Profile reference** (optional - issuer validation requirements)
* **Revocation Profile reference** (optional - revocation configuration)
* Validity rules (TTL, reissue rules, renewable flag)
* **Cryptographic configuration:**
  * Issuer key ID and algorithm (RS256, ES256, EdDSA)
  * Key access mode (key_vault, hsm, local)
  * Issuer certificate chain (for mDoc/X.509-based credentials)
  * Issuer DID (for DID-based credentials)
  * Auto-generate artifacts flag (dev vs production behavior)
* Privacy posture (fields intended to be selectively disclosable)
* Supported formats (SD-JWT, mDoc, JWT-VC, JSON-LD)

**Architectural Note:**

Credential Template is the **master issuance configuration** combining:
1. Schema/claims (what the credential contains)
2. Compliance Profile (format and framework abstraction)
3. Application Template (optional - how users apply for it)
4. Cryptographic materials (keys, certs, DIDs for signing)
5. Validity and revocation settings

For **direct issuance** (batch/API-driven): `application_template_id` is None
For **application-based issuance**: `application_template_id` references an Application Template

**Stability:** changes occasionally; owned by program/business + security/compliance.

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

**Purpose:** Define *how users apply for credentials* (evidence + form fields + workflow).

**Contains:**

* Form field definitions (what users fill out: text, date, select, file uploads)
* Evidence requirements (documents, biometrics, verifications needed)
* Claim collection rules (how to gather claim values from applicants: form fields, evidence extraction, third-party APIs)
* Approval strategy (auto, manual, rules_based) and workflow configuration
* Notification settings (email/SMS templates for application status updates)
* UI/UX configuration (theme, welcome message, wizard vs single-page display)

**Key Characteristics:**

* **Pure user-facing entity** - NO cryptographic concerns
* **Workflow-focused** - Defines the application process, not the credential structure
* **Referenced by Credential Templates** - Inverted relationship (CT → AT, not AT → CT)
* **Optional** - Only needed for application-based issuance (not for direct/batch issuance)

**Architectural Note:**

Application Templates are referenced BY Credential Templates when application-based issuance is needed. For direct/API-driven issuance (batch issuance, pre-authorized flows), Credential Templates have no `application_template_id` reference.

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
* **ZK predicate configuration** (see below)

#### Zero-Knowledge Predicate Configuration

Presentation Policies support structured ZK (zero-knowledge) predicate specifications that enable privacy-preserving verification without revealing raw claim values.

**Predicate Specification (`predicate_spec`):**

Each required claim can include an optional `predicate_spec` that defines:

* **`predicate_type`:** Type of ZK proof
  * `range_proof` - Value within a range (e.g., age >= 21)
  * `membership` - Value in a set (e.g., country in [US, CA, MX])
  * `equality` - Value equals target without revealing
  * `non_membership` - Value NOT in a set
  * `inequality` - Value does not equal target

* **`params`:** Type-specific parameters
  * For `range_proof`: `{"threshold": 21, "comparison": "gte"}` or `{"min": 18, "max": 65}`
  * For `membership`: `{"allowed_values": ["US", "CA", "MX"]}`

* **`supported_circuits`:** List of acceptable ZK circuit identifiers
  * Example: `["ligero_age_over_21", "bbs_range"]`

* **`fallback_policy`:** Behavior when ZK proof unavailable
  * `require_predicate` - Strict: reject if ZK unavailable
  * `accept_raw` - Graceful: accept raw claim value as fallback
  * `deny` - Block: deny verification entirely

**Policy-Level ZK Configuration:**

* **`fallback_policy`:** Default fallback for all claims (can be overridden per-claim)
* **`supported_circuits`:** List of ZK circuits supported by this policy
* **`prefer_predicates`:** Boolean flag to prefer ZK proofs over raw values

**Example Configuration:**

```json
{
  "name": "Age Verification Policy",
  "required_claims": [
    {
      "claim_name": "birth_date",
      "credential_type": "mDL",
      "predicate_spec": {
        "predicate_type": "range_proof",
        "params": {"threshold": 21, "comparison": "gte"},
        "supported_circuits": ["ligero_age_over_21"],
        "fallback_policy": "accept_raw"
      }
    }
  ],
  "prefer_predicates": true,
  "fallback_policy": "accept_raw",
  "supported_circuits": ["ligero_age_over_21", "ligero_age_over_18"]
}
```

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

* `Organizations` - multi-tenant organization management
* `TrustProfiles` - define who is trusted and how validation happens
* `CredentialTemplates` - **master issuance configuration** (schema + profiles + crypto)
* `ComplianceProfiles` - abstract credential format complexity (ICAO, AAMVA, EUDI, etc.)
* `ApplicationTemplates` - define user-facing application workflows (evidence, forms, UI)
* `RevocationProfiles` - format-agnostic revocation configuration
* `PresentationPolicies` - define what must be shown to satisfy verification requests
* `DeploymentProfiles` - package trust + policies + runtime behavior for endpoints
* `Flows` - orchestrate end-to-end journeys (apply → approve → issue → present → verify)
* `Applications` - instances created from Application Templates (user submissions)
* `Issuance` - issue operations + status (references Credential Templates directly)
* `VerificationSessions` - presentation requests + results
* `AuditEvents` - immutable log

Key architectural principle:

* **Policies are data.** Endpoints execute them, not re-implement them.

**Relationship Architecture:**

```
Organization
    │
    ├── Compliance Profile (format abstraction)
    │
    ├── Application Template (user workflow - OPTIONAL)
    │       ├── form_fields
    │       ├── evidence_requirements
    │       └── claim_collection_rules
    │
    └── Credential Template (MASTER CONFIG)
            ├── application_template_id → (optional reference)
            ├── compliance_profile_id → (required reference)
            ├── trust_profile_id → (optional reference)
            ├── revocation_profile_id → (optional reference)
            ├── claims (schema)
            ├── validity_rules
            └── issuer_key_id, issuer_certificate_chain_pem, issuer_did (crypto)
                    │
                    ├── Direct Issuance (API/batch)
                    │   └── POST /v1/issuance (references credential_template_id)
                    │
                    └── Application-Based Issuance
                        └── POST /v1/applications (uses application_template workflow)
```

**Implementation Note:**

The API exposes both Credential Templates and Application Templates as first-class resources:
- `POST /v1/credential-templates` — Create/manage complete issuance configurations
- `POST /v1/application-templates` — Create/manage user-facing application workflows
- `POST /v1/credential-templates/{id}/validate-artifacts` — Validate cryptographic configuration
- Credential Templates reference Application Templates (inverted from previous design)
- Application Templates are purely user-facing (NO crypto concerns)

---

## The core claim of the white paper

**Digital identity is a governed exchange of verifiable claims.**
It becomes automatable when you model it as **trust configuration (TP)** + **what is issued (CT)** + **what is requested (PP)** + **where it runs (DP)**, tied together by **flows (F)** that handle application, approval, issuance, and verification.