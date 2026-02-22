#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Extract cookies and export as environment variables
eval "$("$DIR/venv/bin/python" "$DIR/extract_cookies.py")"
export TWITTER_CT0
export TWITTER_AUTH_TOKEN

exec "$DIR/venv/bin/python" "$DIR/server.py"
