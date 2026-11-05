#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
python3 tests/native_recipe.py
