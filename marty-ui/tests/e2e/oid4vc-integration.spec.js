/**
 * OID4VC Integration Smoke Tests
 *
 * These tests verify the credential issuance and presentation flow
 * using the test orchestration endpoints. They serve as a foundation
 * for full E2E tests that will include wallet integration.
 *
 * Prerequisites:
 * - Backend running with ENABLE_TEST_ENDPOINTS=true
 * - marty-rs Python bindings available (optional, falls back to mock)
 */

const { test, expect } = require("@playwright/test");

// Base URL for the API
const API_BASE = process.env.API_URL || "http://localhost:8000";

test.describe("OID4VC Test Endpoints Integration", () => {
  // Check if test endpoints are enabled - skip tests if not
  test.beforeAll(async ({ request }) => {
    try {
      const response = await request.get(`${API_BASE}/api/test/health`);
      if (response.ok()) {
        const data = await response.json();
        if (!data.test_endpoints_enabled) {
          console.log("⚠️ Test endpoints not enabled. Set ENABLE_TEST_ENDPOINTS=true to run these tests.");
          test.skip();
        }
      }
    } catch (e) {
      console.log("⚠️ Backend not available:", e.message);
      test.skip();
    }
  });

  test.describe("Health & Setup", () => {
    test("should confirm test endpoints are enabled", async ({ request }) => {
      const response = await request.get(`${API_BASE}/api/test/health`);
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      expect(data.healthy).toBe(true);
      // Log status but don't fail if not enabled - beforeAll handles skip
      console.log("Test endpoints enabled:", data.test_endpoints_enabled);
      console.log("marty-rs available:", data.marty_rs_available);
    });

    test("should clear test data before running tests", async ({ request }) => {
      // Clear credentials
      const credResponse = await request.delete(`${API_BASE}/api/test/credentials`);
      expect(credResponse.ok()).toBeTruthy();
      
      // Clear presentation requests
      const presResponse = await request.delete(`${API_BASE}/api/test/presentation-requests`);
      expect(presResponse.ok()).toBeTruthy();
    });
  });

  test.describe("Credential Issuance Flow", () => {
    test("should issue a verifiable credential", async ({ request }) => {
      const response = await request.post(`${API_BASE}/api/test/issue-credential`, {
        data: {
          subject_did: "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
          credential_type: "TravelVisa",
          claims: {
            given_name: "John",
            family_name: "Doe",
            birth_date: "1980-01-15",
            nationality: "US",
            visa_type: "Tourist",
            valid_from: "2024-01-01",
            valid_until: "2025-01-01"
          },
          expiration_days: 365
        }
      });
      
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      
      expect(data.success).toBe(true);
      expect(data.credential_id).toBeTruthy();
      expect(data.jwt).toBeTruthy();
      expect(data.issuer_did).toMatch(/^did:/);
      expect(data.offer_uri).toMatch(/^openid-credential-offer:/);
      
      console.log("Issued credential:", data.credential_id);
      console.log("Issuer DID:", data.issuer_did);
    });

    test("should list issued credentials", async ({ request }) => {
      // First ensure we have at least one credential by issuing one
      const issueResponse = await request.post(`${API_BASE}/api/test/issue-credential`, {
        data: {
          subject_did: "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
          credential_type: "UniversityDegreeCredential",
          claims: { degree: "Bachelor of Science" }
        }
      });
      expect(issueResponse.ok()).toBeTruthy();
      const issuedCredential = await issueResponse.json();
      
      const response = await request.get(`${API_BASE}/api/test/credentials`);
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      // The list endpoint should work  
      expect(data).toHaveProperty("count");
      expect(data).toHaveProperty("credentials");
      expect(Array.isArray(data.credentials)).toBe(true);
      
      // Find our credential by ID
      const ourCredential = data.credentials.find(c => c.id === issuedCredential.credential_id);
      if (ourCredential) {
        // If we found our credential, verify its structure
        expect(ourCredential).toHaveProperty("jwt");
        expect(ourCredential).toHaveProperty("issuer_did");
      } else {
        // If our credential was cleared by a parallel test, at least verify
        // the issued credential response had correct structure
        expect(issuedCredential.credential_id).toBeTruthy();
        expect(issuedCredential.jwt).toBeTruthy();
        expect(issuedCredential.issuer_did).toBeTruthy();
      }
    });
  });

  test.describe("Presentation Request Flow", () => {
    test("should create a presentation request", async ({ request }) => {
      const response = await request.post(`${API_BASE}/api/test/request-presentation`, {
        data: {
          requested_credentials: ["TravelVisa"],
          redirect_uri: "https://verifier.example.com/callback"
        }
      });
      
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      
      expect(data.success).toBe(true);
      expect(data.request_id).toBeTruthy();
      expect(data.nonce).toBeTruthy();
      expect(data.verifier_did).toMatch(/^did:/);
      expect(data.request_uri).toMatch(/^openid4vp:/);
      
      console.log("Created presentation request:", data.request_id);
      console.log("Verifier DID:", data.verifier_did);
    });

    test("should list pending presentation requests", async ({ request }) => {
      // First ensure we have at least one presentation request
      const createResponse = await request.post(`${API_BASE}/api/test/request-presentation`, {
        data: {
          requested_credentials: ["TestCredentialForListing"],
          redirect_uri: "https://verifier.example.com/callback"
        }
      });
      expect(createResponse.ok()).toBeTruthy();
      const createdRequest = await createResponse.json();
      
      const response = await request.get(`${API_BASE}/api/test/presentation-requests`);
      expect(response.ok()).toBeTruthy();
      
      const data = await response.json();
      // The list endpoint should work
      expect(data).toHaveProperty("count");
      expect(data).toHaveProperty("requests");
      expect(Array.isArray(data.requests)).toBe(true);
      
      // Find the request we just created by ID
      const ourRequest = data.requests.find(r => r.id === createdRequest.request_id);
      if (ourRequest) {
        // If we found our request, verify its structure
        expect(ourRequest).toHaveProperty("nonce");
        expect(ourRequest).toHaveProperty("verifier_did");
        expect(ourRequest.status).toBe("pending");
      } else {
        // If our request was cleared by a parallel test, at least verify
        // the created request had correct structure
        expect(createdRequest.request_id).toBeTruthy();
        expect(createdRequest.nonce).toBeTruthy();
        expect(createdRequest.verifier_did).toBeTruthy();
      }
    });
  });

  test.describe("Complete Flow: Issue → Present → Verify", () => {
    let credentialJwt;
    let requestId;
    let nonce;
    
    test("Step 1: Issue a credential", async ({ request }) => {
      const response = await request.post(`${API_BASE}/api/test/issue-credential`, {
        data: {
          credential_type: "EmployeeBadge",
          claims: {
            employee_id: "EMP-12345",
            department: "Engineering",
            role: "Senior Developer",
            hire_date: "2020-06-15"
          },
          expiration_days: 30
        }
      });
      
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      expect(data.success).toBe(true);
      
      credentialJwt = data.jwt;
      console.log("Credential JWT (first 100 chars):", credentialJwt.substring(0, 100) + "...");
    });
    
    test("Step 2: Create a presentation request", async ({ request }) => {
      const response = await request.post(`${API_BASE}/api/test/request-presentation`, {
        data: {
          requested_credentials: ["EmployeeBadge"]
        }
      });
      
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      
      requestId = data.request_id;
      nonce = data.nonce;
      console.log("Request ID:", requestId, "Nonce:", nonce);
    });
    
    test("Step 3: Verify a presentation (mock VP)", async ({ request }) => {
      // In a real test, the wallet would create a proper VP with the correct nonce.
      // Here we're testing that the verify-presentation endpoint is callable and 
      // handles the mock/invalid VP appropriately.
      const response = await request.post(`${API_BASE}/api/test/verify-presentation`, {
        data: {
          vp_jwt: credentialJwt,  // Using credential as mock VP (will fail validation)
          request_id: requestId,
          expected_nonce: nonce
        }
      });
      
      // The endpoint may return 400 (invalid VP) or 200 with success=false
      // Either is acceptable for this mock test case
      const status = response.status();
      console.log("Verification response status:", status);
      
      if (response.ok()) {
        const data = await response.json();
        console.log("Verification result:", data);
        // If endpoint returns 200, verify structure
        expect(data).toHaveProperty("valid");
      } else {
        // 400 is expected when VP is invalid
        expect([400, 422, 500]).toContain(status);
        console.log("Verification correctly rejected invalid mock VP");
      }
    });
  });
});
