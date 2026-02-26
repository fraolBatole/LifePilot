#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
    echo "❌ .env not found. Run ./setup.sh first."
    exit 1
fi

cd "$(dirname "$0")"
PYTHONPATH=src python3 src/bot.py
