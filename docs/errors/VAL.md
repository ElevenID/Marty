# VAL - Validation Errors

Validation errors occur when input data doesn't meet requirements.

## Error Codes

### VAL.REQUIRED_FIELD

**HTTP Status:** 400 Bad Request

**Description:** A required field is missing from the request.

**User Message:** "[Field Name] is required."

**Recovery Action:** `fail_fast`

**Details Provided:**
- `field`: Name of the missing field

**Possible Causes:**
- Required field was not included in request
- Field was null or empty

**Resolution:**
1. Include the required field in your request
2. Ensure the field has a non-empty value

---

### VAL.INVALID_FORMAT

**HTTP Status:** 400 Bad Request

**Description:** A field value doesn't match the expected format.

**User Message:** "[Field Name] format is invalid."

**Recovery Action:** `fail_fast`

**Details Provided:**
- `field`: Name of the invalid field
- `expected_format`: Description of expected format (when available)
- `received_value`: The invalid value (sanitized)

**Possible Causes:**
- Email doesn't match email format
- Date not in ISO 8601 format
- Phone number format incorrect
- UUID format invalid

**Resolution:**
1. Check the expected format in API documentation
2. Correct the field value format

**Examples:**
- Email: `user@example.com`
- Date: `2025-12-16T10:30:00Z`
- UUID: `550e8400-e29b-41d4-a716-446655440000`
- Phone: `+1-555-123-4567`

---

### VAL.OUT_OF_RANGE

**HTTP Status:** 400 Bad Request

**Description:** A numeric value is outside the allowed range.

**User Message:** "[Field Name] must be between [min] and [max]."

**Recovery Action:** `fail_fast`

**Details Provided:**
- `field`: Name of the field
- `min`: Minimum allowed value
- `max`: Maximum allowed value
- `received_value`: The out-of-range value

**Possible Causes:**
- Number too large or too small
- Percentage outside 0-100
- Age outside valid range

**Resolution:**
1. Adjust the value to be within the allowed range
2. Check API documentation for valid ranges

---

### VAL.CONSTRAINT_VIOLATED

**HTTP Status:** 400 Bad Request

**Description:** A validation constraint was violated (e.g., uniqueness, relationship).

**User Message:** "The input does not meet the requirements."

**Recovery Action:** `fail_fast`

**Details Provided:**
- `constraint`: Name or description of the violated constraint
- `field`: Related field (if applicable)

**Possible Causes:**
- Unique constraint violation
- Foreign key reference doesn't exist
- Business rule violation

**Resolution:**
1. Review the constraint requirement
2. Modify input to satisfy the constraint

## Validation Error Response Format

When multiple validation errors occur, the API returns a `ValidationErrorResponse`:

```json
{
  "errors": [
    {
      "code": "VAL.REQUIRED_FIELD",
      "message": "Field 'email' is required",
      "user_message": "Email is required.",
      "field": "email"
    },
    {
      "code": "VAL.OUT_OF_RANGE",
      "message": "Age must be between 18 and 120",
      "user_message": "Age must be between 18 and 120.",
      "field": "age",
      "details": { "min": 18, "max": 120, "received_value": 15 }
    }
  ],
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": 1734355200.0
}
```

## Best Practices for Clients

1. **Display all validation errors** - Don't just show the first error
2. **Highlight relevant form fields** - Use the `field` property to highlight inputs
3. **Use user_message** - Display `user_message` in the UI, not `message`
4. **Pre-validate on client** - Validate before submission when possible
