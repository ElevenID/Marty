# AUTH - Authentication Errors

Authentication errors occur when a user's identity cannot be verified.

## Error Codes

### AUTH.INVALID_TOKEN

**HTTP Status:** 401 Unauthorized

**Description:** The provided authentication token is invalid, malformed, or has been tampered with.

**User Message:** "You need to log in to access this resource."

**Recovery Action:** `reauthenticate`

**Possible Causes:**
- Token was manually modified
- Token was issued by a different authority
- Token signature verification failed

**Resolution:**
1. Clear browser cookies and local storage
2. Log in again to obtain a fresh token

---

### AUTH.TOKEN_EXPIRED

**HTTP Status:** 401 Unauthorized

**Description:** The authentication token has expired and is no longer valid.

**User Message:** "Your session has expired. Please log in again."

**Recovery Action:** `reauthenticate`

**Possible Causes:**
- User was inactive for too long
- Token's expiration time has passed

**Resolution:**
1. Log in again to obtain a new token
2. If using refresh tokens, the client should automatically refresh

---

### AUTH.SESSION_EXPIRED

**HTTP Status:** 401 Unauthorized

**Description:** The user's session has expired on the server side.

**User Message:** "Your session has expired. Please log in again."

**Recovery Action:** `reauthenticate`

**Possible Causes:**
- Session timeout due to inactivity
- Session was invalidated by admin
- Redis session store was cleared

**Resolution:**
1. Log in again to create a new session

---

### AUTH.INVALID_CREDENTIALS

**HTTP Status:** 401 Unauthorized

**Description:** The provided username/password combination is incorrect.

**User Message:** "Invalid username or password."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- Incorrect password entered
- User account doesn't exist
- Case-sensitive username mismatch

**Resolution:**
1. Verify username is correct
2. Reset password if forgotten
3. Check for caps lock

---

### AUTH.MFA_REQUIRED

**HTTP Status:** 401 Unauthorized

**Description:** Multi-factor authentication is required but was not provided.

**User Message:** "Please complete two-factor authentication."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- Organization requires MFA
- User has MFA enabled on their account

**Resolution:**
1. Complete MFA challenge
2. Use authenticator app or SMS code

---

### AUTH.ACCOUNT_LOCKED

**HTTP Status:** 403 Forbidden

**Description:** The user account has been locked due to too many failed login attempts or administrative action.

**User Message:** "Your account has been locked. Please contact support."

**Recovery Action:** `contact_support`

**Possible Causes:**
- Too many failed login attempts
- Account locked by administrator
- Security policy enforcement

**Resolution:**
1. Wait for automatic unlock (if enabled)
2. Contact support to unlock account
3. Reset password through email verification
