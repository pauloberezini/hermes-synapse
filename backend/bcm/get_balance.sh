#!/bin/bash
# Pepperstone Balance API

set -e

# Source environment
source "$(dirname "${BASH_SOURCE[0]}")/../.env"

echo "Fetching Pepperstone balance..."
echo ""

curl -s -u "${ACCOUNT_ID}:" "https://practice.pepperstone.com/api/v1/accounts/${ACCOUNT_ID}/balance" || {
    echo "Error: Failed to fetch balance"
    exit 1
}

echo ""
echo "Done."