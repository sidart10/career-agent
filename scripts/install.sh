#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

UV=$(command -v uv || true)
if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then UV="$HOME/.local/bin/uv"; fi
if [ -z "$UV" ]; then
  echo 'Setup needs uv. See https://docs.astral.sh/uv/getting-started/installation/ or ask your agent to install it with your permission.' >&2
  exit 3
fi
export PATH="$(dirname "$UV"):$PATH"
exec "$UV" run --no-project --python 3.12 "$SCRIPT_DIR/install_support.py" --source "$SOURCE_ROOT" --target "$SOURCE_ROOT" "$@"
