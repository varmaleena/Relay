#!/usr/bin/env sh
set -eu
exec python "$(dirname "$0")/setup.py" "$@"
