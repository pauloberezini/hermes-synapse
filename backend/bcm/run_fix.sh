#!/bin/bash
# Wrapper to run the FIX client with all ENV variables

cd "$(dirname "$0")/.."
# Source .env and export all variables defined in it
set -a
source .env
set +a

if [ -z "$PASSWORD" ]; then
    echo "Error: PASSWORD not set in .env"
    exit 1
fi

# Run Open API client (formerly FIX client)
openapi/.venv/bin/python3 scripts/openapi_client.py "$@"
