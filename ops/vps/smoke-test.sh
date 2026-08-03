#!/bin/sh
set -eu

app_url=${1:-}
api_url=${2:-}
expected_revision=${3:-}

if [ -z "$app_url" ] || [ -z "$api_url" ]; then
  echo "Usage: $0 https://app.example.com https://api.example.com [commit-sha]" >&2
  exit 1
fi

app_url=${app_url%/}
api_url=${api_url%/}

echo "Checking public PWA"
curl --fail --silent --show-error --retry 5 --retry-all-errors \
  "$app_url/healthz" >/dev/null
curl --fail --silent --show-error --retry 5 --retry-all-errors \
  "$app_url/" >/dev/null

echo "Checking public backend"
reported_revision=$(python3 -c \
  "import json, sys, urllib.request; print(json.load(urllib.request.urlopen(sys.argv[1]))['revision'])" \
  "$api_url/healthz")

if [ -n "$expected_revision" ] && [ "$reported_revision" != "$expected_revision" ]; then
  echo "Backend reports $reported_revision instead of $expected_revision" >&2
  exit 1
fi

echo "Public smoke test passed; backend revision: $reported_revision"
