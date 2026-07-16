#!/bin/bash

# Script to standardize all Helm chart values.yaml files
# This script generates standardized values.yaml for each service

SERVICES=(
  "csca-service"
  "document-signer"
  "inspection-system"
  "mdl-engine"
  "mdoc-engine"
  "passport-engine"
  "trust-anchor"
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)/helm/charts"

for service in "${SERVICES[@]}"; do
  echo "Updating ${service}..."

  # Generate service-specific database name (replace hyphens with underscores)
  db_name=$(echo "${service}" | tr '-' '_')

  cat > "${BASE_DIR}/${service}/values.yaml" << EOF
# Default values for ${service}.
# This is a YAML-formatted file.
# Declare variables to be passed into your templates.

replicaCount: 1

image:
  repository: marty/${service}
  tag: "latest"
  pullPolicy: IfNotPresent

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: "${service}"

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8081"
  prometheus.io/path: "/metrics"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false
  runAsNonRoot: true
  runAsUser: 1000
  capabilities:
    drop:
    - ALL

service:
  type: ClusterIP
  http:
    port: 8080
    targetPort: 8080
  grpc:
    port: 9090
    targetPort: 9090
  metrics:
    port: 8081
    targetPort: 8081

# Environment configuration
env:
  LOG_LEVEL: "INFO"
  SERVICE_NAME: "${service}"
  SERVICE_VERSION: "1.0.0"
  HEALTH_CHECK_PORT: "8081"
  METRICS_PORT: "8081"

# gRPC TLS Configuration
grpc:
  tls:
    enabled: true
    mtls: true
    require_client_auth: true
    server_cert: "/etc/tls/server/tls.crt"
    server_key: "/etc/tls/server/tls.key"
    client_ca: "/etc/tls/ca/ca.crt"
    client_cert: "/etc/tls/client/tls.crt"
    client_key: "/etc/tls/client/tls.key"
    secrets:
      server:
        name: "${service}-server-tls"
        cert_key: "tls.crt"
        key_key: "tls.key"
      client:
        name: "${service}-client-tls"
        cert_key: "tls.crt"
        key_key: "tls.key"
      ca:
        name: "${service}-ca"
        cert_key: "ca.crt"

# Database configuration
database:
  dsn: "postgresql://marty:password@postgres.marty.svc.cluster.local:5432/${db_name}"
  host: "postgres.marty.svc.cluster.local"
  port: 5432
  name: "${db_name}"
  user: "marty"
  password: ""
  passwordSecret:
    name: "${service}-db-secret"
    key: "password"
  pool:
    min_size: 1
    max_size: 10
    max_overflow: 20

# Object Storage configuration
objectStorage:
  enabled: false
  endpoint: "minio.marty.svc.cluster.local:9000"
  bucket: "${service}-storage"
  region: "us-east-1"
  use_ssl: false
  access_key: ""
  secret_key: ""
  credentialsSecret:
    name: "${service}-storage-secret"
    access_key_key: "access-key"
    secret_key_key: "secret-key"

# Key Vault configuration
keyVault:
  enabled: false
  type: "hashicorp"
  hashicorp:
    endpoint: "vault.marty.svc.cluster.local:8200"
    auth_method: "kubernetes"
    role: "${service}"
    mount_path: "auth/kubernetes"
    secrets_path: "secret/${service}"
  azure:
    vault_url: "https://marty-keyvault.vault.azure.net/"
    tenant_id: ""
    client_id: ""
    client_secret: ""
    credentialsSecret:
      name: "${service}-keyvault-secret"
      tenant_id_key: "tenant-id"
      client_id_key: "client-id"
      client_secret_key: "client-secret"

# Event Bus configuration
eventBus:
  type: "kafka"
  kafka:
    brokers: "kafka.marty.svc.cluster.local:9092"
    topic_prefix: "${service}."
    consumer_group: "${service}-consumers"
    security:
      enabled: false
      protocol: "SASL_SSL"
      sasl_mechanism: "PLAIN"
      username: ""
      password: ""
      credentialsSecret:
        name: "${service}-kafka-secret"
        username_key: "username"
        password_key: "password"

resources:
  limits:
    cpu: 1000m
    memory: 1Gi
  requests:
    cpu: 500m
    memory: 512Mi

ingress:
  enabled: false
  className: ""
  annotations: {}
  hosts:
    - host: "${service}.chart-example.local"
      paths:
        - path: /
          pathType: Prefix
  tls: []

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 100
  targetCPUUtilizationPercentage: 80

nodeSelector: {}
tolerations: []
affinity: {}

# Service-specific configuration
serviceConfig: {}

# Migration job configuration
migration:
  enabled: true
  image:
    repository: marty/${service}
    tag: "latest"
    pullPolicy: IfNotPresent
  alembic:
    command: ["python", "-m", "alembic", "upgrade", "head"]
    config_file: "/app/alembic.ini"
  job:
    restartPolicy: Never
    backoffLimit: 3
    activeDeadlineSeconds: 600
    ttlSecondsAfterFinished: 86400
  resources:
    limits:
      cpu: 500m
      memory: 512Mi
    requests:
      cpu: 250m
      memory: 256Mi

# Monitoring configuration
monitoring:
  serviceMonitor:
    enabled: true
    interval: 30s
    path: /metrics
    port: metrics
    labels: {}
  podMonitor:
    enabled: false
    interval: 30s
    path: /metrics
    port: metrics-sidecar
    labels: {}

# Service mesh configuration
serviceMesh:
  enabled: false
  type: "istio"
  istio:
    injection: enabled
    mtls:
      mode: "STRICT"
    trafficPolicy:
      tls:
        mode: "ISTIO_MUTUAL"
  linkerd:
    injection: enabled
EOF

  echo "Updated ${service} values.yaml"
done

echo "All services updated with standardized values.yaml files!"
EOF
