#!/bin/sh
# Run from a repository clone: ./install.sh goultard
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$script_dir/install.py" "$@"
fi
if command -v python >/dev/null 2>&1; then
    exec python "$script_dir/install.py" "$@"
fi
printf '%s\n' 'Install Python 3.9 or newer, then run this script again.' >&2
exit 1
