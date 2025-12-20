# SRV - Server Errors

Server errors indicate issues with the Marty infrastructure.

## Error Codes

### SRV.INTERNAL_ERROR

**HTTP Status:** 500 Internal Server Error

**Description:** An unexpected error occurred on the server.

**User Message:** "An unexpected error occurred. Our team has been notified."

**Recovery Action:** `retry` or `contact_support`

**Possible Causes:**
- Unhandled exception in application code
- Unexpected null/undefined values
- Logic errors

**Resolution:**
1. Retry the request after a short delay
2. If persists, contact support with the `request_id`

---

### SRV.DATABASE_ERROR

**HTTP Status:** 500 Internal Server Error

**Description:** A database operation failed.

**User Message:** "A database error occurred. Please try again."

**Recovery Action:** `retry_with_backoff`

**Possible Causes:**
- Database connection lost
- Query timeout
- Deadlock detected
- Constraint violation (internal)

**Resolution:**
1. Wait a few seconds and retry
2. If persists, check database health status

---

### SRV.EXTERNAL_SERVICE

**HTTP Status:** 502 Bad Gateway

**Description:** A call to an external service failed.

**User Message:** "A dependent service is temporarily unavailable."

**Recovery Action:** `retry_with_backoff`

**Details Provided:**
- `service`: Name of the failing external service

**Possible Causes:**
- External API is down
- Network connectivity issues
- External service rate limiting
- DNS resolution failure

**Resolution:**
1. Wait and retry with exponential backoff
2. Check status page of external service
3. If persists, contact support

---

### SRV.TEMPORARILY_UNAVAILABLE

**HTTP Status:** 503 Service Unavailable

**Description:** The service is temporarily unavailable, usually due to maintenance or overload.

**User Message:** "The service is temporarily unavailable. Please try again later."

**Recovery Action:** `retry_with_backoff`

**Details Provided:**
- `retry_after`: Suggested wait time in seconds (when available)

**Possible Causes:**
- Planned maintenance
- Service overloaded
- Deployment in progress
- Health check failing

**Resolution:**
1. Check the `Retry-After` header for suggested wait time
2. Wait and retry
3. Check status page for maintenance announcements

---

### SRV.TIMEOUT

**HTTP Status:** 504 Gateway Timeout

**Description:** The request timed out waiting for a response.

**User Message:** "The request timed out. Please try again."

**Recovery Action:** `retry_with_backoff`

**Possible Causes:**
- Long-running database query
- External service slow to respond
- Network latency
- Large payload processing

**Resolution:**
1. Retry the request
2. If a specific operation, try with smaller payload
3. Check if operation can be done asynchronously

---

### SRV.IO_ERROR

**HTTP Status:** 500 Internal Server Error

**Description:** An I/O operation failed (file system, network, etc.).

**User Message:** "An I/O error occurred. Please try again."

**Recovery Action:** `retry`

**Possible Causes:**
- File not found
- Permission denied
- Disk full
- Network socket error

**Resolution:**
1. Retry the request
2. If persists, contact support

## Retry Strategies

For server errors, clients should implement exponential backoff:

```javascript
async function retryWithBackoff(fn, maxRetries = 3) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (!isRetryable(error) || attempt === maxRetries) {
        throw error;
      }
      const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
      await new Promise(r => setTimeout(r, delay));
    }
  }
}
```

## Monitoring

Server errors are automatically logged with:
- Request ID for tracing
- Stack trace (internal logs only)
- User ID (if authenticated)
- Request path and method
- Error context

Include the `request_id` in support requests for faster debugging.
