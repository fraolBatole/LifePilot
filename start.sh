#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
    echo "❌ .env not found. Run ./setup.sh first."
    exit 1
fi

cd "$(dirname "$0")"

# Use conda env if available, otherwise fall back to system python
if command -v conda &>/dev/null && conda env list | grep -q lifepilot; then
    conda run --no-capture-output -n lifepilot env PYTHONPATH=src python src/bot.py
else
    PYTHONPATH=src python3 src/bot.py
fi
