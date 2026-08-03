#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
environment=${1:-}
api_domain=${2:-}
output_dir=${3:-"$repo_root/releases"}

if [ "$environment" != "staging" ] && [ "$environment" != "production" ]; then
  echo "Usage: $0 <staging|production> <api-domain> [output-directory]" >&2
  exit 1
fi
case "$api_domain" in
  ''|*/*|*:*|*[!A-Za-z0-9.-]*)
    echo "Invalid API domain: $api_domain" >&2
    exit 1
    ;;
esac

cd "$repo_root"
if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "Refusing to build a release from a dirty worktree." >&2
  echo "Commit or remove every modified and untracked file first." >&2
  exit 1
fi

for command_name in docker git gzip tar; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done
if docker buildx version >/dev/null 2>&1; then
  buildx() { docker buildx "$@"; }
elif command -v docker-buildx >/dev/null 2>&1; then
  buildx() { docker-buildx "$@"; }
else
  echo "Docker Buildx is required." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable. Start Docker Desktop or Docker Engine." >&2
  exit 1
fi

revision=$(git rev-parse --verify HEAD)
case "$revision" in
  *[!0-9a-f]*|'') echo "Unexpected Git revision: $revision" >&2; exit 1 ;;
esac
image_tag="$revision-$environment"
release_id="$image_tag"
app_url="https://$api_domain"

images="veksha/backend:$image_tag veksha/web:$image_tag veksha/admin:$image_tag veksha/tgbot:$image_tag"

echo "Building backend for linux/amd64"
buildx build --platform linux/amd64 --pull --load \
  --tag "veksha/backend:$image_tag" \
  "$repo_root/veksha-backend"

echo "Building web for linux/amd64"
buildx build --platform linux/amd64 --pull --load \
  --build-arg "VITE_BACKEND_URL=$app_url" \
  --file "$repo_root/veksha-web/Dockerfile" \
  --tag "veksha/web:$image_tag" \
  "$repo_root"

echo "Building admin for linux/amd64"
buildx build --platform linux/amd64 --pull --load \
  --build-arg "VITE_BACKEND_URL=$app_url" \
  --tag "veksha/admin:$image_tag" \
  "$repo_root/veksha-admin"

echo "Building Telegram bot for linux/amd64"
buildx build --platform linux/amd64 --pull --load \
  --tag "veksha/tgbot:$image_tag" \
  "$repo_root/veksha-tgbot"

for image in $images; do
  image_platform=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")
  if [ "$image_platform" != "linux/amd64" ]; then
    echo "$image has platform $image_platform instead of linux/amd64" >&2
    exit 1
  fi
done

mkdir -p "$output_dir"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)
temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/veksha-release.XXXXXX")
trap 'rm -rf "$temporary_dir"' EXIT HUP INT TERM
release_dir="$temporary_dir/release"
mkdir -p "$release_dir/ops/vps"

cp "$repo_root/compose.prod.yaml" "$release_dir/compose.prod.yaml"
cp "$repo_root/ops/vps/Caddyfile" "$release_dir/ops/vps/Caddyfile"

created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
{
  printf 'release_id=%s\n' "$release_id"
  printf 'revision=%s\n' "$revision"
  printf 'image_tag=%s\n' "$image_tag"
  printf 'environment=%s\n' "$environment"
  printf 'api_domain=%s\n' "$api_domain"
  printf 'platform=linux/amd64\n'
  printf 'created_at=%s\n' "$created_at"
} > "$release_dir/manifest.env"

echo "Exporting application images"
# Word splitting is intentional: $images contains four validated image names.
# shellcheck disable=SC2086
docker save $images > "$release_dir/images.tar"
(
  cd "$release_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum images.tar > images.tar.sha256
  else
    shasum -a 256 images.tar > images.tar.sha256
  fi
)

archive="$output_dir/veksha-$release_id.tar.gz"
# Prevent macOS tar from adding AppleDouble/xattr records that GNU tar would
# otherwise unpack as extra files on the Linux server.
COPYFILE_DISABLE=1 tar -C "$temporary_dir" -czf "$archive" release
(
  cd "$output_dir"
  archive_name=$(basename -- "$archive")
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$archive_name" > "$archive_name.sha256"
  else
    shasum -a 256 "$archive_name" > "$archive_name.sha256"
  fi
)

echo "Release created: $archive"
echo "Checksum: $archive.sha256"
echo "Revision: $revision"
echo "Image tag: $image_tag"
