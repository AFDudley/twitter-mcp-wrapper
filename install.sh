#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Python deps
python3 -m venv venv
./venv/bin/pip install browser-cookie3 mcp twikit twikit_grok pydantic python-dotenv
