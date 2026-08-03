#!/bin/sh
set -eu

root_dir=${VEKSHA_ROOT:-/srv/veksha}
env_file=${VEKSHA_ENV_FILE:-"$root_dir/shared/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
releases_dir="$root_dir/releases"
state_dir="$root_dir/state"
archive=${1:-}

if [ -z "$archive" ] || [ ! -f "$archive" ] || [ ! -f "$archive.sha256" ]; then
  echo "Usage: $0 /srv/veksha/incoming/veksha-<release>.tar.gz" >&2
  echo "The adjacent .sha256 file is required." >&2
  exit 1
fi
if [ ! -f "$env_file" ]; then
  echo "Missing environment file: $env_file" >&2
  exit 1
fi
env_mode=$(stat -c '%a' "$env_file")
if [ "$env_mode" != "600" ]; then
  echo "$env_file must have mode 600." >&2
  exit 1
fi

mkdir -p "$releases_dir" "$state_dir"
exec 9>"$state_dir/deploy.lock"
if ! flock -n 9; then
  echo "Another deploy or rollback is already running." >&2
  exit 1
fi

archive_dir=$(CDPATH= cd -- "$(dirname -- "$archive")" && pwd)
archive_name=$(basename -- "$archive")
archive="$archive_dir/$archive_name"
(
  cd "$archive_dir"
  sha256sum -c "$archive_name.sha256"
)

temporary_dir=$(mktemp -d "$releases_dir/.installing.XXXXXX")
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM
tar -xzf "$archive" -C "$temporary_dir"
unpacked="$temporary_dir/release"
manifest="$unpacked/manifest.env"
if [ ! -f "$manifest" ] || [ ! -f "$unpacked/compose.prod.yaml" ] || \
   [ ! -f "$unpacked/ops/vps/Caddyfile" ] || [ ! -f "$unpacked/images.tar" ]; then
  echo "Release archive is incomplete." >&2
  exit 1
fi

manifest_value() {
  sed -n "s/^$1=//p" "$manifest" | sed -n '1p'
}
release_id=$(manifest_value release_id)
revision=$(manifest_value revision)
image_tag=$(manifest_value image_tag)
environment=$(manifest_value environment)
platform=$(manifest_value platform)

case "$release_id" in ''|*[!A-Za-z0-9._-]*) echo "Invalid release id." >&2; exit 1 ;; esac
case "$revision" in ''|*[!0-9a-f]*) echo "Invalid release revision." >&2; exit 1 ;; esac
if [ "${#revision}" -ne 40 ]; then
  echo "Release revision must be a full 40-character Git SHA." >&2
  exit 1
fi
if [ "$environment" != "staging" ] && [ "$environment" != "production" ]; then
  echo "Invalid release environment: $environment" >&2
  exit 1
fi
if [ "$release_id" != "$revision-$environment" ] || [ "$image_tag" != "$release_id" ]; then
  echo "Release id, revision, environment and image tag do not agree." >&2
  exit 1
fi
if [ "$platform" != "linux/amd64" ]; then
  echo "Unsupported release platform: $platform" >&2
  exit 1
fi

configured_environment=$(sed -n 's/^VEKSHA_ENVIRONMENT=//p' "$env_file" | sed -n '1p')
if [ "$configured_environment" != "$environment" ]; then
  echo "Release environment is $environment but $env_file configures $configured_environment." >&2
  exit 1
fi

(
  cd "$unpacked"
  sha256sum -c images.tar.sha256
)

release_dir="$releases_dir/$release_id"
if [ -e "$release_dir" ]; then
  echo "Release already exists: $release_dir" >&2
  exit 1
fi

echo "Loading application images for $release_id"
docker load --input "$unpacked/images.tar"
for image in backend web admin tgbot; do
  if ! docker image inspect "veksha/$image:$image_tag" >/dev/null 2>&1; then
    echo "Missing release image: veksha/$image:$image_tag" >&2
    exit 1
  fi
done

mv "$unpacked" "$release_dir"
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM
rmdir "$temporary_dir"
trap - EXIT HUP INT TERM

activate_release() {
  target_dir=$1
  target_manifest="$target_dir/manifest.env"
  VEKSHA_REVISION=$(sed -n 's/^revision=//p' "$target_manifest" | sed -n '1p')
  VEKSHA_IMAGE_TAG=$(sed -n 's/^image_tag=//p' "$target_manifest" | sed -n '1p')
  export VEKSHA_REVISION VEKSHA_IMAGE_TAG

  if ! docker compose \
    --project-name "$compose_project" \
    --env-file "$env_file" \
    -f "$target_dir/compose.prod.yaml" \
    config --quiet; then
    return 1
  fi
  if ! docker compose \
    --project-name "$compose_project" \
    --env-file "$env_file" \
    -f "$target_dir/compose.prod.yaml" \
    up --detach --remove-orphans --no-build --wait --wait-timeout 240; then
    return 1
  fi

  if ! running_revision=$(docker compose \
    --project-name "$compose_project" \
    --env-file "$env_file" \
    -f "$target_dir/compose.prod.yaml" \
    exec -T backend python -c \
    "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['revision'])"); then
    return 1
  fi
  if [ "$running_revision" != "$VEKSHA_REVISION" ]; then
    echo "Backend reports $running_revision instead of $VEKSHA_REVISION" >&2
    return 1
  fi
}

previous_id=""
if [ -f "$state_dir/current" ]; then
  previous_id=$(sed -n '1p' "$state_dir/current")
fi

echo "Activating release $release_id"
if ! activate_release "$release_dir"; then
  echo "Release failed health checks." >&2
  if [ -n "$previous_id" ] && [ -d "$releases_dir/$previous_id" ]; then
    echo "Restoring previous release $previous_id"
    activate_release "$releases_dir/$previous_id" || \
      echo "Automatic recovery also failed; inspect the containers immediately." >&2
  fi
  exit 1
fi

if [ -n "$previous_id" ] && [ "$previous_id" != "$release_id" ]; then
  printf '%s\n' "$previous_id" > "$state_dir/previous"
fi
printf '%s\n' "$release_id" > "$state_dir/current"
ln -sfn "$release_dir" "$root_dir/current.next"
mv -Tf "$root_dir/current.next" "$root_dir/current"

docker compose \
  --project-name "$compose_project" \
  --env-file "$env_file" \
  -f "$release_dir/compose.prod.yaml" \
  ps
echo "Deployment is healthy at revision $revision ($release_id)."
