#!/usr/bin/env bash
# Run any amv command from anywhere: ./amv.sh list
#
# By default in a small cached environment (requirements-light.txt), so it
# works without syncing the full torch/CUDA project environment. Commands that
# need torch (vocals, transcribe, subs) say so; run those with AMV_FULL=1
# after `uv sync`.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if [ "${AMV_FULL:-0}" = "1" ]; then
    exec uv run --project "$ROOT" python -m amv "$@"
fi
exec uv run -q --no-project --python 3.12 --with-requirements "$ROOT/requirements-light.txt" python -m amv "$@"
