#!/usr/bin/env bash
set -euo pipefail

# ── Parse arguments ───────────────────────────────────────────────────────────
IMAGE=""
NAMESPACE="ai-agents"
DB_URL=""
ENCRYPTION_KEY=""

usage() {
  echo "Usage: $0 --image <image-uri> --db-url <postgres-url> --encryption-key <key> [--namespace <ns>]"
  echo ""
  echo "  --image           (required) Full container image URI, e.g. ghcr.io/org/alert-analyser:v1.0.0"
  echo "  --db-url          (required) PostgreSQL connection string (asyncpg format)"
  echo "  --encryption-key  (required) Fernet key for encrypting stored secrets"
  echo "  --namespace       (optional) Kubernetes namespace, default: ai-agents"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)           IMAGE="$2";          shift 2 ;;
    --namespace)       NAMESPACE="$2";      shift 2 ;;
    --db-url)          DB_URL="$2";         shift 2 ;;
    --encryption-key)  ENCRYPTION_KEY="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; usage ;;
  esac
done

[[ -z "$IMAGE" ]]          && echo "Error: --image is required"          && usage
[[ -z "$DB_URL" ]]         && echo "Error: --db-url is required"         && usage
[[ -z "$ENCRYPTION_KEY" ]] && echo "Error: --encryption-key is required" && usage

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Create namespace if it doesn't exist ──────────────────────────────────────
echo "→ Ensuring namespace '${NAMESPACE}' exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ── Create / update Kubernetes secret ────────────────────────────────────────
echo "→ Upserting secret 'alert-analyser-secrets'..."
kubectl create secret generic alert-analyser-secrets \
  --namespace "${NAMESPACE}" \
  --from-literal=database-url="${DB_URL}" \
  --from-literal=encryption-key="${ENCRYPTION_KEY}" \
  --save-config \
  --dry-run=client -o yaml | kubectl apply -f -

# ── Substitute IMAGE_TAG and apply manifests ──────────────────────────────────
echo "→ Applying manifests (image: ${IMAGE})..."

sed "s|IMAGE_TAG|${IMAGE}|g" "${SCRIPT_DIR}/deployment.yaml" \
  | sed "s|\${NAMESPACE:-ai-agents}|${NAMESPACE}|g" \
  | kubectl apply -f -

sed "s|\${NAMESPACE:-ai-agents}|${NAMESPACE}|g" "${SCRIPT_DIR}/service.yaml" \
  | kubectl apply -f -

sed "s|\${NAMESPACE:-ai-agents}|${NAMESPACE}|g" "${SCRIPT_DIR}/hpa.yaml" \
  | kubectl apply -f -

# ── Wait for rollout ──────────────────────────────────────────────────────────
echo "→ Waiting for rollout..."
kubectl rollout status deployment/alert-analyser --namespace "${NAMESPACE}" --timeout=120s

# ── Print status ──────────────────────────────────────────────────────────────
echo ""
echo "✓ Deployment complete"
echo ""
kubectl get pods --namespace "${NAMESPACE}" -l app=alert-analyser
echo ""
echo "Health check (from within the cluster):"
echo "  curl http://alert-analyser.${NAMESPACE}.svc.cluster.local:8080/health"
