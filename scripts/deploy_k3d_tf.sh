#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-alpes}"
IMAGE="${IMAGE:-alpes-water-monitor:latest}"
KUBE_CONTEXT="k3d-${CLUSTER_NAME}"

: "${CDSE_CLIENT_ID:?Set CDSE_CLIENT_ID}"
: "${CDSE_CLIENT_SECRET:?Set CDSE_CLIENT_SECRET}"

ACTION="${1:-apply}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing $1" >&2; exit 1; }; }
need k3d; need docker; need kubectl; need terraform

echo "Cluster: $CLUSTER_NAME | Image: $IMAGE | Context: $KUBE_CONTEXT | Action: $ACTION"

cluster_exists() {
  k3d cluster list -o json | python3 - <<'PY'
import json,sys,os
name=os.environ["CLUSTER_NAME"]
data=json.load(sys.stdin)
print("1" if any(c.get("name")==name for c in data) else "0")
PY
}

export CLUSTER_NAME

if [[ "$(cluster_exists)" != "1" ]]; then
  k3d cluster create "$CLUSTER_NAME" --api-port 6443 --servers 1 --agents 1 --wait
fi

docker build -t "$IMAGE" .
k3d image import "$IMAGE" -c "$CLUSTER_NAME"

k3d kubeconfig merge "$CLUSTER_NAME" >/dev/null
kubectl config use-context "$KUBE_CONTEXT" >/dev/null

export TF_IN_AUTOMATION=1

pushd infra >/dev/null
terraform init -input=false

TF_VAR_kube_context="$KUBE_CONTEXT" \
terraform "$ACTION" -auto-approve \
  -var cdse_client_id="$CDSE_CLIENT_ID" \
  -var cdse_client_secret="$CDSE_CLIENT_SECRET" \
  -var user_code_image="$IMAGE"
popd >/dev/null

if [[ "$ACTION" == "apply" ]]; then
  echo "Done. Check pods with: kubectl -n alpes-water-monitor get pods"
  echo "Port-forward Dagster: kubectl -n alpes-water-monitor port-forward deploy/dagster-webserver 3000:3000"
  echo "Port-forward MinIO:   kubectl -n alpes-water-monitor port-forward deploy/minio 9000:9000 9001:9001"
fi
