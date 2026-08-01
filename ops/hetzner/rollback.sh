#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
env_file=${VEKSHA_ENV_FILE:-"$repo_root/.env.production"}
compose_project=${VEKSHA_COMPOSE_PROJECT:-veksha}
state_dir="$repo_root/.deployments"

cd "$repo_root"

target_revision=${1:-}
if [ -z "$target_revision" ] && [ -f "$state_dir/previous" ]; then
  target_revision=$(sed -n '1p' "$state_dir/previous")
fi
if [ -z "$target_revision" ]; then
  echo "Usage: $0 <previous-commit-sha>" >&2
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
if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
  echo "Refusing to roll back a dirty worktree." >&2
  exit 1
fi
git cat-file -e "$target_revision^{commit}"
target_revision=$(git rev-parse "$target_revision^{commit}")

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

for image in backend web admin tgbot; do
  if ! docker image inspect "veksha/$image:$target_revision" >/dev/null 2>&1; then
    echo "Missing rollback image: veksha/$image:$target_revision" >&2
    exit 1
  fi
done

current_revision=$(git rev-parse --verify HEAD)
echo "Switching deployment checkout from $current_revision to $target_revision"
git switch --detach "$target_revision"

VEKSHA_REVISION=$target_revision
export VEKSHA_REVISION

compose config --quiet
compose up --detach --remove-orphans --no-build --wait --wait-timeout 240

running_revision=$(compose exec -T backend python -c \
  "import json, urllib.request; print(json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz'))['revision'])")
if [ "$running_revision" != "$target_revision" ]; then
  echo "Backend reports revision $running_revision instead of $target_revision" >&2
  exit 1
fi

mkdir -p "$state_dir"
printf '%s\n' "$current_revision" > "$state_dir/previous"
printf '%s\n' "$target_revision" > "$state_dir/current"
compose ps
echo "Rollback completed at revision $target_revision"
echo "A code rollback does not reverse incompatible database changes."
