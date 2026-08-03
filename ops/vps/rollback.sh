#!/bin/sh
set -eu

root_dir=${VEKSHA_ROOT:-/srv/veksha}
env_file=${VEKSHA_ENV_FILE:-"$root_dir/shared/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
releases_dir="$root_dir/releases"
state_dir="$root_dir/state"
target_id=${1:-}

if [ -z "$target_id" ] && [ -f "$state_dir/previous" ]; then
  target_id=$(sed -n '1p' "$state_dir/previous")
fi
if [ -z "$target_id" ]; then
  echo "Usage: $0 <release-id>" >&2
  echo "No previous release is recorded." >&2
  exit 1
fi
case "$target_id" in ''|*[!A-Za-z0-9._-]*) echo "Invalid release id." >&2; exit 1 ;; esac

target_dir="$releases_dir/$target_id"
manifest="$target_dir/manifest.env"
if [ ! -d "$target_dir" ] || [ ! -f "$manifest" ]; then
  echo "Release is unavailable: $target_dir" >&2
  exit 1
fi
if [ ! -f "$env_file" ] || [ "$(stat -c '%a' "$env_file")" != "600" ]; then
  echo "$env_file must exist with mode 600." >&2
  exit 1
fi

mkdir -p "$state_dir"
exec 9>"$state_dir/deploy.lock"
if ! flock -n 9; then
  echo "Another deploy or rollback is already running." >&2
  exit 1
fi

revision=$(sed -n 's/^revision=//p' "$manifest" | sed -n '1p')
image_tag=$(sed -n 's/^image_tag=//p' "$manifest" | sed -n '1p')
environment=$(sed -n 's/^environment=//p' "$manifest" | sed -n '1p')
configured_environment=$(sed -n 's/^VEKSHA_ENVIRONMENT=//p' "$env_file" | sed -n '1p')
if [ "$configured_environment" != "$environment" ]; then
  echo "Release environment is $environment but the server configures $configured_environment." >&2
  exit 1
fi
for image in backend web admin tgbot; do
  if ! docker image inspect "veksha/$image:$image_tag" >/dev/null 2>&1; then
    echo "Missing rollback image: veksha/$image:$image_tag" >&2
    exit 1
  fi
done

current_id=""
if [ -f "$state_dir/current" ]; then
  current_id=$(sed -n '1p' "$state_dir/current")
fi
if [ "$current_id" = "$target_id" ]; then
  echo "Release $target_id is already current." >&2
  exit 1
fi

VEKSHA_REVISION=$revision
VEKSHA_IMAGE_TAG=$image_tag
export VEKSHA_REVISION VEKSHA_IMAGE_TAG

echo "Rolling back from ${current_id:-unknown} to $target_id"
docker compose \
  --project-name "$compose_project" \
  --env-file "$env_file" \
  -f "$target_dir/compose.prod.yaml" \
  config --quiet
docker compose \
  --project-name "$compose_project" \
  --env-file "$env_file" \
  -f "$target_dir/compose.prod.yaml" \
  up --detach --remove-orphans --no-build --wait --wait-timeout 240

running_revision=$(docker compose \
  --project-name "$compose_project" \
  --env-file "$env_file" \
  -f "$target_dir/compose.prod.yaml" \
  exec -T backend python -c \
  "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['revision'])")
if [ "$running_revision" != "$revision" ]; then
  echo "Backend reports $running_revision instead of $revision" >&2
  exit 1
fi

if [ -n "$current_id" ]; then
  printf '%s\n' "$current_id" > "$state_dir/previous"
fi
printf '%s\n' "$target_id" > "$state_dir/current"
ln -sfn "$target_dir" "$root_dir/current.next"
mv -Tf "$root_dir/current.next" "$root_dir/current"

docker compose \
  --project-name "$compose_project" \
  --env-file "$env_file" \
  -f "$target_dir/compose.prod.yaml" \
  ps
echo "Rollback completed at revision $revision ($target_id)."
echo "A code rollback does not reverse incompatible database changes."
