#!/bin/bash
# Pepperstone Trader Setup Script

set -e

echo "=========================================="
echo "Pepperstone Trader Setup"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create .env file with your Pepperstone credentials."
    exit 1
fi

# Source environment
source "../.env"

echo "Configuration:"
echo "  Account ID: $ACCOUNT_ID"
echo "  Currency: $CURRENCY"
echo "  Base URL: $BASE_URL"
echo ""

# Create logs directory
mkdir -p logs

echo "✓ Logs directory created"

# Make scripts executable
chmod +x scripts/*.sh

echo "✓ Scripts made executable"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Test balance: bash scripts/get_balance.sh"
echo "2. Test positions: bash scripts/get_positions.sh"
echo "3. Place order: bash scripts/place_order.sh EURUSD 0.1 BUY"
echo ""
echo "Note: Pepperstone REST API requires correct endpoint."
echo "If REST API fails, use FIX API directly (see documentation)."
echo ""