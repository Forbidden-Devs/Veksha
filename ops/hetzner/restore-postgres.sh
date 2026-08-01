#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_file=${VEKSHA_ENV_FILE:-"$repo_root/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
state_dir="$repo_root/.deployments"
dump_file=${1:-}

cd "$repo_root"

if [ -z "$dump_file" ] || [ ! -f "$dump_file" ]; then
  echo "Usage: $0 /path/to/veksha-postgres-<timestamp>.dump" >&2
  exit 1
fi
if [ ! -f "$env_file" ]; then
  echo "Missing production environment file: $env_file" >&2
  exit 1
fi
env_mode=$(stat -c '%a' "$env_file" 2>/dev/null || stat -f '%Lp' "$env_file")
if [ "$env_mode" != "600" ]; then
  echo "$env_file must have mode 600." >&2
  exit 1
fi

dump_dir=$(CDPATH= cd -- "$(dirname -- "$dump_file")" && pwd)
dump_name=$(basename -- "$dump_file")
dump_file="$dump_dir/$dump_name"
if [ -f "$dump_file.sha256" ]; then
  (
    cd "$dump_dir"
    sha256sum -c "$dump_name.sha256"
  )
else
  echo "Warning: checksum file is missing: $dump_file.sha256" >&2
fi

if [ -f "$state_dir/current" ]; then
  VEKSHA_REVISION=$(sed -n '1p' "$state_dir/current")
else
  VEKSHA_REVISION=$(git rev-parse --verify HEAD)
fi
export VEKSHA_REVISION

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

compose up --detach --wait --wait-timeout 120 postgres
table_count=$(compose exec -T postgres psql \
  --username veksha \
  --dbname veksha \
  --tuples-only \
  --no-align \
  --command "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
if [ "$table_count" != "0" ]; then
  echo "Refusing to restore: target database contains $table_count public tables." >&2
  echo "Create a separate empty Compose project or empty database first." >&2
  exit 1
fi

echo "Target Compose project: $compose_project"
echo "Target database is empty. Type RESTORE EMPTY VEKSHA to continue:"
IFS= read -r confirmation
if [ "$confirmation" != "RESTORE EMPTY VEKSHA" ]; then
  echo "Restore cancelled." >&2
  exit 1
fi

compose exec -T postgres pg_restore \
  --username veksha \
  --dbname veksha \
  --exit-on-error \
  --no-owner \
  --no-acl < "$dump_file"

restored_tables=$(compose exec -T postgres psql \
  --username veksha \
  --dbname veksha \
  --tuples-only \
  --no-align \
  --command "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
if [ "$restored_tables" = "0" ]; then
  echo "Restore completed without public tables; inspect the dump and target." >&2
  exit 1
fi

echo "Restore completed into empty project $compose_project ($restored_tables public tables)."
