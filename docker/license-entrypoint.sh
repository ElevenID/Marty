#!/bin/sh
set -e

# ──────────────────────────────────────────────────────────────────────
# Marty Container License Entrypoint
#
# Validates the license before starting the main application.
# Requires:
#   - MARTY_PRODUCT_ID env var (e.g., "document-signer")
#   - MARTY_LICENSE env var or /etc/marty/license.key file
#   - MARTY_LICENSE_PUBLIC_KEY env var or /etc/marty/license.pub file
#
# Optional:
#   - MARTY_LICENSE_STRICT=false to skip enforcement (dev/test)
#   - MARTY_LICENSE_VALIDATION_URL for phone-home revocation checks
# ──────────────────────────────────────────────────────────────────────

# Skip license check if explicitly disabled (development/testing only)
if [ "${MARTY_LICENSE_STRICT}" = "false" ]; then
    echo "[license] Enforcement disabled (MARTY_LICENSE_STRICT=false)"
    exec "$@"
fi

# Require MARTY_PRODUCT_ID
if [ -z "${MARTY_PRODUCT_ID}" ]; then
    echo "[license] ERROR: MARTY_PRODUCT_ID not set" >&2
    exit 78
fi

# Run the Python license check
python -c "
from src.licensing.startup import startup_license_check
startup_license_check('${MARTY_PRODUCT_ID}', strict=True)
"

# License valid — start the application
exec "$@"
