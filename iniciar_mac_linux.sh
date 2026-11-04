#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python scripts/check_runtime.py || python -m pip install -r requirements-local.txt
python -m streamlit run app.py --server.address 127.0.0.1
