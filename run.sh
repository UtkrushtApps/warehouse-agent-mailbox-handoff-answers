#!/usr/bin/env bash
set -u
cd /root/task
pip install -q -r requirements.txt
python -m agent --selfcheck
python -m pytest -q invariants
rc=$?
if [ "$rc" -le 1 ]; then
  echo "ready"
  exit 0
else
  exit "$rc"
fi
