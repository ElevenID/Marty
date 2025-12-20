# ORG - Organization Errors

Organization errors occur during organization management operations.

## Error Codes

### ORG.NOT_FOUND

**HTTP Status:** 404 Not Found

**Description:** The specified organization does not exist.

**User Message:** "Organization not found."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- Organization ID is incorrect
- Organization was deleted
- Typo in organization name/slug

**Resolution:**
1. Verify the organization ID
2. Check if organization still exists
3. Contact organization administrator

---

### ORG.INVITE_EXPIRED

**HTTP Status:** 410 Gone

**Description:** The organization invite code has expired and can no longer be used.

**User Message:** "This invite code has expired. Please request a new one."

**Recovery Action:** `fail_fast`

**Details Provided:**
- `expired_at`: When the invite expired

**Possible Causes:**
- Invite was not used within validity period (typically 7 days)
- Invite was manually expired by organization admin

**Resolution:**
1. Request a new invite code from the organization
2. Use the invite promptly after receiving it

---

### ORG.INVITE_INVALID

**HTTP Status:** 410 Gone

**Description:** The organization invite code is invalid, revoked, or does not exist.

**User Message:** "This invite code is not valid. Please check with your organization."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- Invite code was typed incorrectly
- Invite was revoked by organization admin
- Invite was already used (single-use invites)

**Resolution:**
1. Double-check the invite code for typos
2. Contact the organization for a new invite

---

### ORG.MEMBERSHIP_EXISTS

**HTTP Status:** 409 Conflict

**Description:** The user is already a member of the organization.

**User Message:** "You are already a member of this organization."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- User trying to join an organization they're already in
- Duplicate join request

**Resolution:**
1. Navigate to the organization dashboard
2. No action needed - already a member

---

### ORG.NAME_TAKEN

**HTTP Status:** 409 Conflict

**Description:** The organization name is already in use by another organization.

**User Message:** "This organization name is already taken. Please choose a different name."

**Recovery Action:** `fail_fast`

**Possible Causes:**
- Another organization has the same name
- Name collision with reserved names

**Resolution:**
1. Choose a different organization name
2. Add a suffix or prefix to make it unique

---

### ORG.LIMIT_REACHED

**HTTP Status:** 429 Too Many Requests

**Description:** The organization has reached its limit (members, invites, etc.) based on subscription.

**User Message:** "Organization limit reached. Please upgrade your plan or contact support."

**Recovery Action:** `contact_support`

**Details Provided:**
- `limit_type`: What limit was reached (members, invites, etc.)
- `current_count`: Current usage
- `max_allowed`: Maximum allowed by subscription

**Possible Causes:**
- Maximum members reached for subscription tier
- Too many pending invites
- Free tier limits exceeded

**Resolution:**
1. Upgrade subscription for higher limits
2. Remove inactive members to free up slots
3. Cancel unused pending invites
