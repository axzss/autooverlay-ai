#!/usr/bin/env python3
"""
Alpaca MCP Server Integration Test
Using official Alpaca SDK to validate credentials
"""
import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv("/root/alpaca-overlay-agent-a2z/.env")

# Install alpaca-py if needed
try:
    import alpaca
except ImportError:
    print("Installing alpaca-py...")
    os.system(f"{sys.executable} -m pip install -q alpaca-py")
    import alpaca

from alpaca.trading.client import TradingClient
# Removed StockDataSource import - not available in this version

# Get credentials
KEY_ID = os.getenv("ALPACA_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET")
ACCOUNT_ID = os.getenv("ALPACA_ACCOUNT_ID")
ENDPOINT = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")

print("=== Alpaca MCP Server Integration Test ===")
print(f"Account ID: {ACCOUNT_ID}")
print(f"API Key ID: {KEY_ID}")
print(f"Endpoint: {ENDPOINT}\n")

try:
    # Initialize trading client (paper trading mode)
    trading_client = TradingClient(
        api_key=KEY_ID,
        secret_key=SECRET_KEY,
        paper=True
    )
    print("🔌 Connecting to Alpaca API...")
    
    # Fetch account information
    account = trading_client.get_account()
    
    print("✅ Connected successfully!")
    print(f"\n📊 Account Details:")
    print(f"   ID: {account.id}")
    print(f"   Account Number: {account.account_number}")
    print(f"   Status: {account.status}")
    print(f"   Cash: ${account.cash}")
    print(f"   Portfolio Value: ${account.portfolio_value}")
    print(f"   Buying Power: ${account.buying_power}")
    print(f"   Currency: {account.currency}")
    print(f"   Pattern Day Trader: {account.pattern_day_trader}")
    print(f"   Trade Suspended: {account.trade_suspended_by_user}")
    print(f"   Shorting Enabled: {account.shorting_enabled}")
    
    # Fetch positions
    print(f"\n📁 Active Positions:")
    positions = trading_client.get_all_positions()
    if positions:
        for pos in positions:
            print(f"   - {pos.symbol}: {pos.qty} shares (Avg: ${pos.avg_entry_price}, P&L: ${pos.unrealized_pl})")
    else:
        print("   No active positions")
    
    # Fetch recent orders
    print(f"\n📥 Recent Orders:")
    orders = trading_client.get_orders(limit=5)
    if orders:
        for order in orders:
            print(f"   - {order.symbol} {order.side} {order.qty} @ market | Status: {order.status}")
    else:
        print("   No recent orders")
    
    print(f"\n🎉 All systems operational!")
    
except Exception as e:
    print(f"❌ Connection failed: {e}")
    
    # Additional diagnostics
    print(f"\n🔧 Diagnostic Information:")
    print(f"   Key format valid: {len(KEY_ID) == 20 if KEY_ID else False}")
    print(f"   Secret format valid: {len(SECRET_KEY) == 40 if SECRET_KEY else False}")
    
    # Check for common issues
    if not KEY_ID or not SECRET_KEY:
        print("   ISSUE: Missing credentials")
    elif len(KEY_ID) != 20 or len(SECRET_KEY) != 40:
        print("   ISSUE: Incorrect credential format")
        print("   Alpaca Key ID should be 20 chars, Secret Key should be 40 chars")
    else:
        print("   ISSUE: Credentials appear valid but authentication failed")
        print("   Possible causes: IP whitelist, account not activated, or key revoked")