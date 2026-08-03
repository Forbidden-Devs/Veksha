#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive=${1:-}
target=${2:-}

if [ -z "$archive" ] || [ ! -f "$archive" ] || [ ! -f "$archive.sha256" ] || [ -z "$target" ]; then
  echo "Usage: $0 /path/to/veksha-<release>.tar.gz <ssh-host>" >&2
  exit 1
fi
for command_name in rsync ssh; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

archive_dir=$(CDPATH= cd -- "$(dirname -- "$archive")" && pwd)
archive_name=$(basename -- "$archive")
case "$archive_name" in *[!A-Za-z0-9._-]*) echo "Unsafe archive name." >&2; exit 1 ;; esac
archive="$archive_dir/$archive_name"

(
  cd "$archive_dir"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$archive_name.sha256"
  else
    shasum -a 256 -c "$archive_name.sha256"
  fi
)

echo "Uploading server-side deployment tools"
rsync -a --progress \
  "$script_dir/install-release.sh" \
  "$script_dir/rollback.sh" \
  "$script_dir/backup-postgres.sh" \
  "$script_dir/restore-postgres.sh" \
  "$script_dir/smoke-test.sh" \
  "$target:/srv/veksha/bin/"
ssh "$target" "chmod 0750 /srv/veksha/bin/*.sh"

ssh "$target" "mkdir -p /srv/veksha/shared/systemd"
rsync -a \
  "$script_dir/systemd/veksha-backup.service" \
  "$script_dir/systemd/veksha-backup.timer" \
  "$target:/srv/veksha/shared/systemd/"

echo "Uploading $archive_name"
rsync -a --partial --progress \
  "$archive" "$archive.sha256" \
  "$target:/srv/veksha/incoming/"

echo "Installing $archive_name"
ssh "$target" "/srv/veksha/bin/install-release.sh /srv/veksha/incoming/$archive_name"
