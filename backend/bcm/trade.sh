#!/bin/bash
# Helper to execute generic trade actions via Active Exchange

# Script lives in backend/bcm/ — resolve paths relative to it
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$BACKEND_DIR")"
BCM_DIR="$SCRIPT_DIR"

# Load environment variables from project root .env
set -a
source "$PROJECT_DIR/.env"
set +a

if [ -z "$1" ]; then
    echo "Usage:"
    echo "  trade.sh buy <symbol_id> <volume> [sl] [tp]"
    echo "  trade.sh sell <symbol_id> <volume> [sl] [tp]"
    echo "  trade.sh close <order_id> <symbol_id> <side> <volume>"
    echo "  trade.sh modify <order_id> <symbol_id> <side> <volume> <sl> <tp>"
    exit 1
fi

# Use backend venv python with mock_exchange or CLI tool
PYTHON="$BACKEND_DIR/.venv/bin/python3"
CLIENT="$BCM_DIR/mock_exchange.py"

if [ ! -f "$PYTHON" ]; then
    echo "ERROR: Python venv not found at $PYTHON" >&2
    exit 2
fi
if [ ! -f "$CLIENT" ]; then
    echo "ERROR: Exchange client not found at $CLIENT" >&2
    exit 2
fi

case $1 in
    buy)
        "$PYTHON" "$CLIENT" place "$2" 1 "$3" "$4" "$5"
        ;;
    sell)
        "$PYTHON" "$CLIENT" place "$2" 2 "$3" "$4" "$5"
        ;;
    close)
        "$PYTHON" "$CLIENT" close "$2" "$3" "$4" "$5"
        ;;
    modify)
        "$PYTHON" "$CLIENT" modify "$2" "$3" "$4" "$5" "$6" "$7"
        ;;
    positions)
        "$PYTHON" "$CLIENT" positions
        ;;
    *)
        echo "Unknown command: $1"
        exit 1
        ;;
esac
