#!/bin/sh
# Works from any directory. Opens login/signup unless --practice is supplied.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'GunZ needs Python 3. Install it and run this launcher again.' >&2
    exit 1
fi
exec python3 "$ROOT/launch.py" "$@"