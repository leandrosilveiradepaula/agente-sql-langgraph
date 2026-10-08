#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="${SHADOW_DEPLOY_DIR:-/docker/agente-sql-langgraph}"
SERVICE="${SHADOW_SERVICE_NAME:-langgraph-shadow-test}"
CONTAINER="${SHADOW_CONTAINER:-agente-sql-langgraph-shadow-test-langgraph-shadow-test-1}"
ENV_FILE="${SHADOW_ENV_FILE:-${DEPLOY_DIR}/shadow-test.env}"

cd "${ROOT_DIR}"

TARGET_COMMIT="$(git rev-parse HEAD)"
if [[ -z "${TARGET_COMMIT}" ]]; then
  echo "ERROR: cannot resolve repository commit."
  exit 2
fi

if [[ ! -f "${DEPLOY_DIR}/compose.yaml" ]]; then
  echo "ERROR: compose file not found: ${DEPLOY_DIR}/compose.yaml"
  exit 3
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: env file not found: ${ENV_FILE}"
  exit 4
fi

REAL_SQL_FLAG="$(sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' "${ENV_FILE}" | tail -n 1)"
if [[ "${REAL_SQL_FLAG}" != "false" ]]; then
  echo "ABORTED: LANGGRAPH_ALLOW_REAL_SQL_EXECUTION must be false."
  exit 5
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
ENV_BACKUP="${ENV_FILE}.pre-runtime-${STAMP}"
COMPOSE_BACKUP="${DEPLOY_DIR}/compose.yaml.pre-runtime-${STAMP}"
cp -a "${ENV_FILE}" "${ENV_BACKUP}"
cp -a "${DEPLOY_DIR}/compose.yaml" "${COMPOSE_BACKUP}"

cleanup_on_error() {
  status=$?
  if [[ $status -ne 0 ]]; then
    cp -a "${ENV_BACKUP}" "${ENV_FILE}" || true
    cp -a "${COMPOSE_BACKUP}" "${DEPLOY_DIR}/compose.yaml" || true
    (
      cd "${DEPLOY_DIR}"
      docker compose -f compose.yaml up -d --force-recreate "${SERVICE}"
    ) >/dev/null 2>&1 || true
  fi
  exit $status
}
trap cleanup_on_error EXIT

if grep -q '^LANGGRAPH_COMMIT=' "${ENV_FILE}"; then
  sed -i "s/^LANGGRAPH_COMMIT=.*/LANGGRAPH_COMMIT=${TARGET_COMMIT}/" "${ENV_FILE}"
else
  printf '\nLANGGRAPH_COMMIT=%s\n' "${TARGET_COMMIT}" >> "${ENV_FILE}"
fi

IMAGE_TAG="agente-sql-langgraph-shadow-test:${TARGET_COMMIT:0:7}"

cd "${DEPLOY_DIR}"

if ! grep -Eq '^[[:space:]]*image:[[:space:]]*agente-sql-langgraph-shadow-test:' compose.yaml; then
  echo "ERROR: expected Shadow image declaration was not found in compose.yaml."
  exit 6
fi

sed -Ei   "s#^([[:space:]]*image:[[:space:]]*)agente-sql-langgraph-shadow-test:[^[:space:]]+#\\1${IMAGE_TAG}#"   compose.yaml

CONFIG_IMAGE="$(docker compose -f compose.yaml config --images | head -n 1)"
if [[ "${CONFIG_IMAGE}" != "${IMAGE_TAG}" ]]; then
  echo "ERROR: compose image does not match target commit tag."
  echo "configured_image=${CONFIG_IMAGE}"
  echo "target_image=${IMAGE_TAG}"
  exit 7
fi

echo "BUILD: ${IMAGE_TAG}"
docker build   -f "${ROOT_DIR}/deploy/docker/Dockerfile.shadow-test"   -t "${IMAGE_TAG}"   "${ROOT_DIR}"

docker compose -f compose.yaml up -d --force-recreate "${SERVICE}"

for _ in $(seq 1 90); do
  health="$(docker inspect "${CONTAINER}" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)"
  echo "health=${health:-unknown}"
  if [[ "${health}" == "healthy" ]]; then
    break
  fi
  sleep 2
done

health="$(docker inspect "${CONTAINER}" --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' 2>/dev/null || true)"
if [[ "${health}" != "healthy" ]]; then
  echo "ERROR: shadow runtime did not become healthy."
  exit 8
fi

ACTIVE_COMMIT="$(docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^LANGGRAPH_COMMIT=//p' | tail -n 1)"
ACTIVE_REAL_SQL="$(docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=//p' | tail -n 1)"
ACTIVE_IMAGE="$(docker inspect "${CONTAINER}" --format '{{.Config.Image}}')"

if [[ "${ACTIVE_COMMIT}" != "${TARGET_COMMIT}" ]]; then
  echo "ERROR: active LANGGRAPH_COMMIT does not match repository HEAD."
  exit 9
fi

if [[ "${ACTIVE_REAL_SQL}" != "false" ]]; then
  echo "ERROR: active runtime real SQL execution flag is not false."
  exit 10
fi

if [[ "${ACTIVE_IMAGE}" != "${IMAGE_TAG}" ]]; then
  echo "ERROR: active container image does not match repository build."
  echo "active_image=${ACTIVE_IMAGE}"
  echo "target_image=${IMAGE_TAG}"
  exit 11
fi

trap - EXIT

echo "DONE: shadow runtime commit=${ACTIVE_COMMIT} image=${ACTIVE_IMAGE} real_sql_execution=false"
