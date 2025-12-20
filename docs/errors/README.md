# Marty API Error Codes

This directory contains documentation for all hierarchical error codes used in the Marty API.

## Error Code Structure

Error codes follow a hierarchical format: `CATEGORY.SPECIFIC_ERROR`

| Category | Description | HTTP Status Range |
|----------|-------------|-------------------|
| `AUTH` | Authentication errors | 401 |
| `AUTHZ` | Authorization errors | 403 |
| `ORG` | Organization-related errors | 400-410 |
| `USER` | User-related errors | 400-409 |
| `APP` | Application/applicant errors | 400-422 |
| `CRED` | Credential errors | 400-500 |
| `VAL` | Validation errors | 400-422 |
| `API` | API-level errors | 400-429 |
| `SRV` | Server/infrastructure errors | 500-504 |
| `CLIENT` | Client-side reported errors | 202, 429 |

## Error Response Format

All API errors return a consistent JSON structure:

```json
{
  "error": {
    "code": "ORG.INVITE_EXPIRED",
    "message": "Invite code 'ABC123' expired at 2025-12-15T00:00:00Z",
    "user_message": "This invite code has expired. Please request a new one.",
    "severity": "low",
    "recovery_action": "fail_fast",
    "field": "invite_code",
    "details": {
      "expired_at": "2025-12-15T00:00:00Z"
    },
    "documentation_url": "https://docs.marty.io/errors/ORG/INVITE_EXPIRED"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1734355200.0
}
```

## Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `code` | string | Hierarchical error code for programmatic handling |
| `message` | string | Technical message for developers/logs |
| `user_message` | string | User-friendly message safe to display in UI |
| `severity` | enum | `low`, `medium`, `high`, `critical` |
| `recovery_action` | enum | `retry`, `retry_with_backoff`, `reauthenticate`, `contact_support`, `fail_fast` |
| `field` | string? | Field name for validation errors |
| `details` | object? | Additional context-specific information |
| `documentation_url` | string? | Link to detailed error documentation |
| `request_id` | string | UUID for request tracing (include in support requests) |
| `timestamp` | number | Unix timestamp when error occurred |

## Severity Levels

| Severity | Description | Typical Action |
|----------|-------------|----------------|
| `low` | User can easily recover | Fix input and retry |
| `medium` | User may need to retry | Wait and retry |
| `high` | Significant issue | Contact support if persists |
| `critical` | System-level failure | Contact support immediately |

## Recovery Actions

| Action | Description | Client Behavior |
|--------|-------------|-----------------|
| `fail_fast` | Don't retry, fix the issue | Show error, don't auto-retry |
| `retry` | Retry immediately | Auto-retry once |
| `retry_with_backoff` | Retry with exponential backoff | Auto-retry with delays |
| `reauthenticate` | User session expired | Redirect to login |
| `contact_support` | Manual intervention needed | Show support contact info |

## Error Categories

- [AUTH - Authentication Errors](./AUTH.md)
- [AUTHZ - Authorization Errors](./AUTHZ.md)
- [ORG - Organization Errors](./ORG.md)
- [USER - User Errors](./USER.md)
- [APP - Application Errors](./APP.md)
- [CRED - Credential Errors](./CRED.md)
- [VAL - Validation Errors](./VAL.md)
- [API - API Errors](./API.md)
- [SRV - Server Errors](./SRV.md)

## Client Error Reporting

The UI automatically reports client-side errors to `/api/client-errors`. This endpoint:
- Accepts error reports from the React application
- Rate-limited to 10 errors per minute per IP
- Logs errors for monitoring and debugging

See [CLIENT.md](./CLIENT.md) for client error codes.
