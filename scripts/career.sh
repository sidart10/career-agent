#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
POINTER="$ROOT/.career-agent/active-runtime"
if [ ! -f "$POINTER" ]; then
  echo 'Career Agent is not installed. Run bash scripts/install.sh from the project folder.' >&2
  exit 3
fi
RUNTIME=$(tr -d '\r\n' < "$POINTER")
case "$RUNTIME" in runtimes/*) ;; *) echo 'Invalid runtime pointer. Rerun setup.' >&2; exit 3;; esac
ID=${RUNTIME#runtimes/}
case "$ID" in ''|*[!0-9a-f]*) echo 'Invalid runtime pointer. Rerun setup.' >&2; exit 3;; esac
[ ${#ID} -eq 32 ] || exit 3
DIR="$ROOT/.career-agent/$RUNTIME"
if [ ! -f "$DIR/.project-root" ] || [ "$(cat "$DIR/.project-root")" != "$ROOT" ]; then
  echo 'Project was moved or runtime is invalid. Rerun setup to rebuild software; workspace files will be preserved.' >&2
  exit 3
fi
exec "$DIR/bin/python" -m career_agent --project "$ROOT" "$@"
