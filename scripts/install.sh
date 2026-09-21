#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

exec python3 "$SCRIPT_DIR/install_support.py" --source "$SOURCE_ROOT" --target "$SOURCE_ROOT" "$@"
