#!/bin/sh
# Pull EnvVault secrets or a named env config into a file on the bind-mounted workspace.
# Configure via ENVVAULT_* (see docker/compose-envvault.md).

set -eu

OUT="${ENVVAULT_OUTPUT_FILE:-.env}"
WORKDIR="${ENVVAULT_WORKDIR:-/workspace}"
cd "$WORKDIR"

if [ -z "${ENVVAULT_PROJECT_ID:-}" ]; then
  echo "envvault-compose-sync: ENVVAULT_PROJECT_ID is required" >&2
  exit 1
fi
if [ -z "${ENVVAULT_SERVICE_TOKEN:-}" ]; then
  echo "envvault-compose-sync: ENVVAULT_SERVICE_TOKEN is required" >&2
  exit 1
fi

MODE="${ENVVAULT_EXPORT_MODE:-secrets}"
ENV_SLUG="${ENVVAULT_ENV:-dev}"
SERVER="${ENVVAULT_SERVER_URL:-http://host.docker.internal:8000}"

set -- envvault --server "$SERVER" --token "$ENVVAULT_SERVICE_TOKEN"

case "${ENVVAULT_NO_VERIFY_SSL:-}" in 1|true|yes|on)
  set -- "$@" --no-verify-ssl
  ;;
esac

if [ -n "${ENVVAULT_CA_BUNDLE:-}" ]; then
  set -- "$@" --ca-bundle "$ENVVAULT_CA_BUNDLE"
fi

case "$MODE" in
  secrets)
    if [ -n "${ENVVAULT_VERSION_NAME:-}" ]; then
      exec "$@" export \
        --project-id "$ENVVAULT_PROJECT_ID" \
        --env "$ENV_SLUG" \
        --version "$ENVVAULT_VERSION_NAME" \
        --output "$OUT"
    fi
    exec "$@" export \
      --project-id "$ENVVAULT_PROJECT_ID" \
      --env "$ENV_SLUG" \
      --output "$OUT"
    ;;
  env-config)
    NAME="${ENVVAULT_ENV_CONFIG_NAME:-.env}"
    if [ -n "${ENVVAULT_VERSION_NAME:-}" ]; then
      exec "$@" env-config dist \
        --project-id "$ENVVAULT_PROJECT_ID" \
        --env "$ENV_SLUG" \
        --name "$NAME" \
        --version "$ENVVAULT_VERSION_NAME" \
        --output "$OUT"
    fi
    exec "$@" env-config dist \
      --project-id "$ENVVAULT_PROJECT_ID" \
      --env "$ENV_SLUG" \
      --name "$NAME" \
      --output "$OUT"
    ;;
  *)
    echo "envvault-compose-sync: ENVVAULT_EXPORT_MODE must be 'secrets' or 'env-config', got: $MODE" >&2
    exit 1
    ;;
esac
