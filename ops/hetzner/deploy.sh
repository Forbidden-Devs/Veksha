#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_file=${VEKSHA_ENV_FILE:-"$repo_root/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
state_dir="$repo_root/.deployments"

cd "$repo_root"

if [ ! -f "$env_file" ]; then
  echo "Missing production environment file: $env_file" >&2
  echo "Copy .env.production.example, fill it, and set mode 600." >&2
  exit 1
fi

env_mode=$(stat -c '%a' "$env_file" 2>/dev/null || stat -f '%Lp' "$env_file")
if [ "$env_mode" != "600" ]; then
  echo "$env_file must have mode 600." >&2
  exit 1
fi

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "Refusing to deploy a dirty worktree." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  compose() {
    docker compose --project-name "$compose_project" --env-file "$env_file" -f compose.prod.yaml "$@"
  }
elif docker-compose version >/dev/null 2>&1; then
  compose() {
    docker-compose --project-name "$compose_project" --env-file "$env_file" -f compose.prod.yaml "$@"
  }
else
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

VEKSHA_REVISION=$(git rev-parse --verify HEAD)
export VEKSHA_REVISION

mkdir -p "$state_dir"
previous_revision=""
if [ -f "$state_dir/current" ]; then
  previous_revision=$(sed -n '1p' "$state_dir/current")
fi

echo "Validating production configuration for $VEKSHA_REVISION"
compose config --quiet

echo "Building revision-tagged application images"
compose --profile telegram build --pull

echo "Starting services and waiting for health checks"
compose up --detach --remove-orphans --wait --wait-timeout 240

running_revision=$(compose exec -T backend python -c \
  "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['revision'])")
if [ "$running_revision" != "$VEKSHA_REVISION" ]; then
  echo "Backend reports revision $running_revision instead of $VEKSHA_REVISION" >&2
  exit 1
fi

if [ -n "$previous_revision" ] && [ "$previous_revision" != "$VEKSHA_REVISION" ]; then
  printf '%s\n' "$previous_revision" > "$state_dir/previous"
fi
printf '%s\n' "$VEKSHA_REVISION" > "$state_dir/current"

compose ps
echo "Deployment is healthy at revision $VEKSHA_REVISION"
echo "Run ops/hetzner/smoke-test.sh after DNS points to this server."
