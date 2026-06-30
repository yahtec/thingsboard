#!/usr/bin/env bash
# tb-notify — one-shot environment bootstrap (venv + deps).
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt
echo
echo "venv ready at $(pwd)/.venv"
echo "next: cp .env.example .env  &&  edit .env  (Brevo SMTP keys, WEB_SECRET)"
