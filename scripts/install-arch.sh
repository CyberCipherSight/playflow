#!/usr/bin/env bash
set -euo pipefail

# Work when invoked from outside the repository as well.
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,browser,publish]'
.venv/bin/python -m playwright install chromium

echo "Installed. Activate with: source .venv/bin/activate"
echo "Then run: playflow --help"
