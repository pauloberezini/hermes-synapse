#!/bin/bash
# Helper to execute trade actions

cd "$(dirname "$0")/.."
set -a
source .env
set +a

if [ -z "$1" ]; then
    echo "Usage:"
    echo "  ./scripts/trade.sh buy <symbol_id> <volume> [sl] [tp]"
    echo "  ./scripts/trade.sh sell <symbol_id> <volume> [sl] [tp]"
    echo "  ./scripts/trade.sh close <order_id> <symbol_id> <side> <volume>"
    echo "  ./scripts/trade.sh modify <order_id> <symbol_id> <side> <volume> <sl> <tp>"
    exit 1
fi

case $1 in
    buy)
        openapi/.venv/bin/python3 scripts/openapi_client.py place "$2" 1 "$3" "$4" "$5"
        ;;
    sell)
        openapi/.venv/bin/python3 scripts/openapi_client.py place "$2" 2 "$3" "$4" "$5"
        ;;
    close)
        openapi/.venv/bin/python3 scripts/openapi_client.py close "$2" "$3" "$4" "$5"
        ;;
    modify)
        openapi/.venv/bin/python3 scripts/openapi_client.py modify "$2" "$3" "$4" "$5" "$6" "$7"
        ;;
    *)
        echo "Unknown command: $1"
        ;;
esac
