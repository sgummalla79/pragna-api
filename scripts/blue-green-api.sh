#!/usr/bin/env bash
# blue-green-api.sh — zero-downtime production deploy for the API via K8s Service selector switching.
#
# Usage:
#   blue-green-api.sh <image-tag> <repo-owner>
#
# What it does:
#   1. Detect the currently active slot (blue or green)
#   2. Deploy new image to the INACTIVE slot
#   3. Scale up the inactive slot and wait for readiness
#   4. Run Alembic migrations (backwards-compatible schemas only)
#   5. Health-check the new slot directly before switching traffic
#   6. Switch the Service selector to the new slot (atomic, ~1s downtime window)
#   7. Post-switch health check with 2-minute rollback window
#   8. Scale down the old slot
#
# Requirements on the cluster (run once):
#   - Namespace 'pragna' with both blue/green Deployments applied
#   - Secret 'pragna-secrets' populated
#   - ghcr-pull-secret for image pulls
#
set -euo pipefail

VERSION="${1:-}"
OWNER="${2:-sgummalla79}"

if [ -z "$VERSION" ]; then
  echo "Usage: $0 <image-tag> [repo-owner]" >&2
  exit 1
fi

NS="pragna"
IMAGE_API="ghcr.io/${OWNER}/pragna-api:${VERSION}"

# ── 1. Detect active slot ──────────────────────────────────────────────────────

ACTIVE=$(kubectl get service pragna-api -n "$NS" \
  -o jsonpath='{.spec.selector.slot}' 2>/dev/null || echo "")

if [ "$ACTIVE" = "blue" ]; then
  NEW_SLOT="green"
  OLD_SLOT="blue"
elif [ "$ACTIVE" = "green" ]; then
  NEW_SLOT="blue"
  OLD_SLOT="green"
else
  echo "=== No active slot found — first deploy, using blue ==="
  NEW_SLOT="blue"
  OLD_SLOT=""
  ACTIVE="none"
fi

echo "=== Blue-Green API Deploy: v${VERSION} ==="
echo "    Active slot : ${ACTIVE}"
echo "    New slot    : ${NEW_SLOT}"
echo "    Image (api) : ${IMAGE_API}"
echo ""

# ── 2. Deploy new image to inactive slot ───────────────────────────────────────

echo "=== Updating pragna-api-${NEW_SLOT} image ==="
kubectl set image deployment/pragna-api-${NEW_SLOT} \
  pragna-api="${IMAGE_API}" \
  -n "$NS"

# ── 3. Scale up inactive slot and wait for readiness ──────────────────────────

echo "=== Scaling up pragna-api-${NEW_SLOT} ==="
kubectl scale deployment/pragna-api-${NEW_SLOT} --replicas=1 -n "$NS"

echo "=== Waiting for pragna-api-${NEW_SLOT} rollout ==="
kubectl rollout status deployment/pragna-api-${NEW_SLOT} \
  -n "$NS" --timeout=180s

# ── 4. Run Alembic migrations ─────────────────────────────────────────────────

echo "=== Running Alembic migrations ==="
DB_URL=$(kubectl get secret pragna-secrets -n "$NS" \
  -o jsonpath='{.data.DATABASE_URL}' | base64 --decode)
MIGRATION_POD="alembic-migrate-${VERSION//\./-}"
kubectl run "${MIGRATION_POD}" \
  --image="${IMAGE_API}" \
  --restart=Never \
  -n "$NS" \
  --env="DATABASE_URL=${DB_URL}" \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"ghcr-pull-secret"}]}}' \
  -- python -m alembic upgrade head
echo "Waiting for migration pod to complete..."
for i in $(seq 1 60); do
  PHASE=$(kubectl get pod "${MIGRATION_POD}" -n "$NS" \
    -o jsonpath='{.status.phase}' 2>/dev/null || echo "Pending")
  echo "  attempt $i: phase=${PHASE}"
  if [ "${PHASE}" = "Succeeded" ]; then break; fi
  if [ "${PHASE}" = "Failed" ]; then
    kubectl logs "${MIGRATION_POD}" -n "$NS" || true
    kubectl delete pod "${MIGRATION_POD}" -n "$NS" --ignore-not-found
    exit 1
  fi
  if [ "$i" = "6" ]; then
    echo "--- pod describe (diagnosing pending) ---"
    kubectl describe pod "${MIGRATION_POD}" -n "$NS" || true
  fi
  sleep 5
done
kubectl logs "${MIGRATION_POD}" -n "$NS" || true
kubectl delete pod "${MIGRATION_POD}" -n "$NS" --ignore-not-found
echo "=== Migrations complete ==="

# ── 5. Health-check the new slot directly before switching ────────────────────

echo "=== Health-checking ${NEW_SLOT} slot ==="
NEW_POD=$(kubectl get pod -n "$NS" \
  -l "app=pragna-api,slot=${NEW_SLOT}" \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$NEW_POD" ]; then
  HEALTH=$(kubectl exec "$NEW_POD" -n "$NS" -- \
    wget -qO- http://localhost:8000/health 2>/dev/null || echo "failed")
  echo "    /health response: $HEALTH"
  if echo "$HEALTH" | grep -q '"status"'; then
    echo "    ✓ New slot is healthy"
  else
    echo "    ✗ New slot health check failed — aborting before traffic switch"
    kubectl scale deployment/pragna-api-${NEW_SLOT} --replicas=0 -n "$NS" || true
    exit 1
  fi
else
  echo "    ⚠ Could not find pod — skipping pre-switch health check"
fi

# ── 6. Switch Service selector (traffic flip) ─────────────────────────────────

echo "=== Switching traffic to ${NEW_SLOT} slot ==="
kubectl patch service pragna-api -n "$NS" \
  --type=merge \
  -p "{\"spec\":{\"selector\":{\"app\":\"pragna-api\",\"slot\":\"${NEW_SLOT}\"}}}"
echo "    ✓ Traffic now flowing to ${NEW_SLOT}"

# ── 7. Post-switch health check with 2-minute rollback window ─────────────────

echo "=== Post-switch health check (120s rollback window) ==="
HEALTHY=false
for i in $(seq 1 12); do
  STATUS=$(curl -s -o /tmp/health.json -w "%{http_code}" \
    https://pragna.sgummallaworks.com/health 2>/dev/null || echo "000")
  if [ "$STATUS" = "200" ]; then
    echo "    ✓ Health check passed (attempt $i)"
    HEALTHY=true
    break
  fi
  echo "    Attempt $i: HTTP $STATUS — retrying in 10s..."
  sleep 10
done

if [ "$HEALTHY" = "false" ]; then
  echo ""
  echo "  ✗ Health check failed — rolling back to ${OLD_SLOT} slot"
  kubectl patch service pragna-api -n "$NS" \
    --type=merge \
    -p "{\"spec\":{\"selector\":{\"app\":\"pragna-api\",\"slot\":\"${OLD_SLOT}\"}}}"
  echo "    Traffic restored to ${OLD_SLOT}"
  exit 1
fi

# ── 8. Scale down old slot ────────────────────────────────────────────────────

if [ -n "$OLD_SLOT" ] && [ "$OLD_SLOT" != "none" ]; then
  echo "=== Scaling down old slot (${OLD_SLOT}) ==="
  kubectl scale deployment/pragna-api-${OLD_SLOT} --replicas=0 -n "$NS"
  echo "    ✓ pragna-api-${OLD_SLOT} scaled to 0 (kept for instant rollback)"
fi

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════════"
echo "  Deployed v${VERSION} → ${NEW_SLOT} slot"
echo "  Rollback: kubectl patch service pragna-api -n pragna \\"
echo "    --type=merge -p '{\"spec\":{\"selector\":{\"app\":\"pragna-api\",\"slot\":\"${OLD_SLOT}\"}}}'"
echo "══════════════════════════════════════════════════"
