#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

export TWITTER_COOKIES=$("$DIR/venv/bin/python" "$DIR/extract_cookies.py")
export AUTH_METHOD=cookies

exec /Users/rix/.nvm/nvm-exec npx -y agent-twitter-client-mcp
