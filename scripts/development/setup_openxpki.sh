#!/bin/bash
# Setup script for OpenXPKI integration with Marty

# Create necessary directories
echo "Creating directories for OpenXPKI..."
mkdir -p data/openxpki/config
mkdir -p data/openxpki/tls
mkdir -p data/openxpki/ca
mkdir -p data/openxpki/logs
mkdir -p data/openxpki/db
mkdir -p data/trust/openxpki_sync
mkdir -p data/openxpki/secrets

# Create development secret files if they do not exist (DO NOT USE IN PROD)
if [ ! -f data/openxpki/secrets/admin_password.txt ]; then
	echo "secret" > data/openxpki/secrets/admin_password.txt
	echo "[dev] Created default admin password file: data/openxpki/secrets/admin_password.txt"
fi
if [ ! -f data/openxpki/secrets/db_password.txt ]; then
	echo "openxpki" > data/openxpki/secrets/db_password.txt
	echo "[dev] Created default DB password file: data/openxpki/secrets/db_password.txt"
fi

if [ ! -f docker/openxpki.env ]; then
	cp docker/openxpki.env.example docker/openxpki.env
	echo "[dev] Created docker/openxpki.env from example"
fi

# Start OpenXPKI using Docker Compose
echo "Starting OpenXPKI services..."
docker-compose -f docker/docker-compose.openxpki.yml up -d

echo "Waiting for OpenXPKI to initialize (30 seconds)..."
sleep 30

# Display connection information
echo -e "\n=== OpenXPKI Setup Complete ==="
echo "Web UI: https://localhost:8443/openxpki/"
echo "API Endpoint: https://localhost:8443/api/v2"
echo "Username: pkiadmin (override OPENXPKI_ADMIN_USER)"
echo "Password: (stored in data/openxpki/secrets/admin_password.txt)"
echo -e "\nUpdate your development.yaml with these settings:\n"
echo "openxpki:"
echo "  base_url: \"https://localhost:8443/api/v2\""
echo "  username: \"pkiadmin\""
echo "  password: \"<REDACTED - use secret file or env var>\""
echo "  realm: \"11id\""
echo -e "\n=== Important Notes ==="
echo "1. You may need to accept the self-signed certificate when accessing the Web UI"
echo "2. Initial setup may take a few minutes to complete after container starts"
echo "3. For production:"
echo "   - Replace secret files with secure values (never commit them)"
echo "   - Or integrate with Vault / AWS Secrets Manager and supply env vars"
echo "   - Enable TLS and set OPENXPKI_VERIFY_SSL=true"
