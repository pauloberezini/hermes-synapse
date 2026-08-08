#!/bin/bash
# Pepperstone Close Position API

set -e

# Source environment
source "$(dirname "${BASH_SOURCE[0]}")/../.env"

POSITION_ID=$1

if [ -z "$POSITION_ID" ]; then
    echo "Usage: $0 <POSITION_ID>"
    echo "Example: $0 12345"
    exit 1
fi

echo "Closing position $POSITION_ID..."
echo ""

curl -s -u "${ACCOUNT_ID}:" \
  -X DELETE "https://practice.pepperstone.com/api/v1/accounts/${ACCOUNT_ID}/positions/${POSITION_ID}" || {
    echo "Error: Failed to close position"
    exit 1
}

echo ""
echo "Position closed."