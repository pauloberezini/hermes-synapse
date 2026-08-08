#!/bin/bash
# Pepperstone Positions via Open API (Protobuf)

# In the container, the venv is at /opt/hermes/.venv
# If running locally, it might be elsewhere.
PYTHON_BIN="/opt/hermes/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Fetching Pepperstone positions via Open API..."
"$PYTHON_BIN" "$SCRIPT_DIR/openapi_client.py" positions