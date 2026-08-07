#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
speech_root=${SPEECH_PLATFORM_DIR:-"$(dirname "$repo_root")/speech-platform"}
veksha_env="$repo_root/.env"

read_env_value() {
  local key=$1
  local file=$2
  local value
  value=$(sed -n "s/^${key}=//p" "$file" | tail -n 1)
  printf '%s' "$value"
}

if [[ ! -f "$veksha_env" ]]; then
  echo "Missing $veksha_env; copy .env.example to .env first." >&2
  exit 1
fi
if [[ ! -f "$speech_root/compose.yaml" || ! -f "$speech_root/.env" ]]; then
  echo "speech-platform is not configured at $speech_root." >&2
  echo "Set SPEECH_PLATFORM_DIR or create its .env from .env.example." >&2
  exit 1
fi

speech_secret=$(read_env_value SPEECH_SHARED_SECRET "$veksha_env")
speech_secret=${speech_secret:-local-development-shared-secret}
speech_network=$(read_env_value SPEECH_DOCKER_NETWORK "$veksha_env")
speech_network=${speech_network:-speech-platform-local}

if [[ ${#speech_secret} -lt 24 ]]; then
  echo "SPEECH_SHARED_SECRET must contain at least 24 characters." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose_command=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_command=(docker-compose)
else
  echo "Docker Compose is required (docker compose or docker-compose)." >&2
  exit 1
fi

compose() {
  "${compose_command[@]}" "$@"
}

case ${1:-up} in
  up)
    (
      cd "$speech_root"
      SPEECH_SHARED_SECRETS="veksha:${speech_secret}" \
        SPEECH_DOCKER_NETWORK="$speech_network" \
        compose up --build --detach --wait
    )
    cd "$repo_root"
    compose up --build
    ;;
  down)
    (
      cd "$repo_root"
      compose down
    )
    (
      cd "$speech_root"
      SPEECH_DOCKER_NETWORK="$speech_network" compose down
    )
    ;;
  status)
    (
      cd "$speech_root"
      SPEECH_DOCKER_NETWORK="$speech_network" compose ps
    )
    (
      cd "$repo_root"
      compose ps
    )
    ;;
  *)
    echo "Usage: $0 {up|down|status}" >&2
    exit 2
    ;;
esac
