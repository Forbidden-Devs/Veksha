#!/bin/sh
set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_file=${VEKSHA_ENV_FILE:-"$repo_root/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
backup_dir=${VEKSHA_BACKUP_DIR:-"$repo_root/backups"}
retention_days=${VEKSHA_BACKUP_RETENTION_DAYS:-7}
state_dir="$repo_root/.deployments"

cd "$repo_root"

if [ ! -f "$env_file" ]; then
  echo "Missing production environment file: $env_file" >&2
  exit 1
fi
env_mode=$(stat -c '%a' "$env_file" 2>/dev/null || stat -f '%Lp' "$env_file")
if [ "$env_mode" != "600" ]; then
  echo "$env_file must have mode 600." >&2
  exit 1
fi
case "$retention_days" in
  ''|*[!0-9]*) echo "VEKSHA_BACKUP_RETENTION_DAYS must be a positive integer." >&2; exit 1 ;;
esac
if [ "$retention_days" -lt 1 ]; then
  echo "VEKSHA_BACKUP_RETENTION_DAYS must be at least 1." >&2
  exit 1
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

mkdir -p "$backup_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
filename="veksha-postgres-$timestamp.dump"
temporary="$backup_dir/.$filename.tmp"
destination="$backup_dir/$filename"
trap 'rm -f "$temporary"' EXIT HUP INT TERM

echo "Creating PostgreSQL backup"
compose exec -T postgres pg_dump \
  --username veksha \
  --dbname veksha \
  --format custom \
  --no-owner \
  --no-acl > "$temporary"
mv "$temporary" "$destination"
trap - EXIT HUP INT TERM
(
  cd "$backup_dir"
  sha256sum "$filename" > "$filename.sha256"
)

if [ -n "${VEKSHA_BACKUP_REMOTE:-}" ]; then
  if ! command -v rclone >/dev/null 2>&1; then
    echo "VEKSHA_BACKUP_REMOTE is set but rclone is unavailable." >&2
    exit 1
  fi
  remote=${VEKSHA_BACKUP_REMOTE%/}
  rclone copyto "$destination" "$remote/$filename"
  rclone copyto "$destination.sha256" "$remote/$filename.sha256"
  echo "Uploaded backup to $remote"
else
  echo "Warning: VEKSHA_BACKUP_REMOTE is unset; this copy remains on the VPS." >&2
fi

find "$backup_dir" -type f -name 'veksha-postgres-*.dump' -mtime "+$retention_days" -delete
find "$backup_dir" -type f -name 'veksha-postgres-*.dump.sha256' -mtime "+$retention_days" -delete

echo "Backup created: $destination"
