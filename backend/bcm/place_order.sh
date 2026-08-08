#!/bin/bash
# Pepperstone Place Order API

set -e

# Source environment
source "$(dirname "${BASH_SOURCE[0]}")/../.env"

SYMBOL=$1
VOLUME=$2
SIDE=$3

if [ -z "$SYMBOL" ] || [ -z "$VOLUME" ] || [ -z "$SIDE" ]; then
    echo "Usage: $0 <SYMBOL> <VOLUME> <BUY|SELL>"
    echo "Example: $0 EURUSD 0.1 BUY"
    exit 1
fi

echo "Placing order..."
echo "Symbol: $SYMBOL"
echo "Volume: $VOLUME"
echo "Side: $SIDE"
echo ""

# Check if volume is integer or float
if [[ $VOLUME == *"."* ]]; then
    # Float
    VOLUME_FORMAT="${VOLUME//./_}"
else
    # Integer
    VOLUME_FORMAT="$VOLUME"
fi

curl -s -u "${ACCOUNT_ID}:" \
  -X POST "https://practice.pepperstone.com/api/v1/accounts/${ACCOUNT_ID}/orders" \
  -H "Content-Type: application/json" \
  -d "{
    \"symbol\": \"$SYMBOL\",
    \"volume\": $VOLUME_FORMAT,
    \"type\": \"MARKET\",
    \"side\": \"$SIDE\"
  }" || {
    echo "Error: Failed to place order"
    exit 1
}

echo ""
echo "Order placed."