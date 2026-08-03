#!/bin/sh
set -eu
umask 077

root_dir=${VEKSHA_ROOT:-/srv/veksha}
release_dir="$root_dir/current"
env_file=${VEKSHA_ENV_FILE:-"$root_dir/shared/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
backup_dir=${VEKSHA_BACKUP_DIR:-"$root_dir/backups"}
retention_days=${VEKSHA_BACKUP_RETENTION_DAYS:-7}
manifest="$release_dir/manifest.env"

cd "$root_dir"

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
