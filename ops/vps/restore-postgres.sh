#!/bin/sh
set -eu

root_dir=${VEKSHA_ROOT:-/srv/veksha}
release_dir="$root_dir/current"
env_file=${VEKSHA_ENV_FILE:-"$root_dir/shared/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
manifest="$release_dir/manifest.env"
dump_file=${1:-}

cd "$root_dir"

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
if [ ! -f "$dump_file.sha256" ]; then
  echo "Checksum file is required: $dump_file.sha256" >&2
  exit 1
fi
(
  cd "$dump_dir"
  sha256sum -c "$dump_name.sha256"
)

if [ ! -f "$manifest" ]; then
  echo "No active release manifest: $manifest" >&2
  exit 1
fi
VEKSHA_REVISION=$(sed -n 's/^revision=//p' "$manifest" | sed -n '1p')
VEKSHA_IMAGE_TAG=$(sed -n 's/^image_tag=//p' "$manifest" | sed -n '1p')
export VEKSHA_REVISION VEKSHA_IMAGE_TAG

if docker compose version >/dev/null 2>&1; then
  compose() {
    docker compose --project-name "$compose_project" --env-file "$env_file" -f "$release_dir/compose.prod.yaml" "$@"
  }
elif docker-compose version >/dev/null 2>&1; then
  compose() {
    docker-compose --project-name "$compose_project" --env-file "$env_file" -f "$release_dir/compose.prod.yaml" "$@"
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
