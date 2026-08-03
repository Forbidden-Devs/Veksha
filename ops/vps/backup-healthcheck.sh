#!/bin/sh
set -u

event=${1:-}
healthcheck_url=${VEKSHA_BACKUP_HEALTHCHECK_URL:-}

if [ -z "$healthcheck_url" ]; then
  exit 0
fi

case "$healthcheck_url" in
  https://*) ;;
  *)
    echo "VEKSHA_BACKUP_HEALTHCHECK_URL must use HTTPS; skipping healthcheck ping." >&2
    exit 0
    ;;
esac

case "$event" in
  start)
    suffix=/start
    ;;
  success)
    suffix=
    ;;
  stop)
    if [ "${SERVICE_RESULT:-}" = success ]; then
      exit 0
    fi
    suffix=/fail
    ;;
  *)
    echo "Usage: $0 start|success|stop" >&2
    exit 0
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is unavailable; skipping backup healthcheck ping." >&2
  exit 0
fi

if ! curl \
  --fail \
  --silent \
  --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  --retry 2 \
  --output /dev/null \
  "$healthcheck_url$suffix"; then
  echo "Backup healthcheck ping failed; backup result is unaffected." >&2
fi

exit 0
