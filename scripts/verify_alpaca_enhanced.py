#!/usr/bin/env python3
"""
Enhanced Alpaca API verification script
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv("/root/alpaca-overlay-agent-a2z/.env")

def test_alpaca_configurations():
    """Test multiple Alpaca API configurations"""

    # Get credentials
    key = os.getenv("ALPACA_KEY")
    secret = os.getenv("ALPACA_SECRET")
    paper_endpoint = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")
    live_endpoint = "https://api.alpaca.markets/v2"
    data_endpoint = os.getenv("ALPACA_DATA_ENDPOINT", "https://data.alpaca.markets/")

    print("=== Enhanced Alpaca API Verification ===\n")
    print(f"Key ID: {key}")
    print(f"Account ID: {os.getenv('ALPACA_ACCOUNT_ID')}")
    print(f"Paper Endpoint: {paper_endpoint}")
    print(f"Live Endpoint: {live_endpoint}")
    print(f"Data Endpoint: {data_endpoint}\n")

    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret
    }

    # Test 1: Paper API - Account Info
    print("🔍 Test 1: Paper API - Account Information")
    try:
        resp = requests.get(f"{paper_endpoint}/account", headers=headers, timeout=10)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print("   ✅ SUCCESS - Real Account Data:")
            print(f"   - Account ID: {data.get('id', 'N/A')}")
            print(f"   - Status: {data.get('status', 'N/A')}")
            print(f"   - Currency: {data.get('currency', 'N/A')}")
            print(f"   - Cash: {data.get('cash', 'N/A')}")
            print(f"   - Portfolio Value: {data.get('portfolio_value', 'N/A')}")
            print(f"   - Pattern Day Trader: {data.get('pattern_day_trader', 'N/A')}")
            print(f"   - Trade Suspended By User: {data.get('trade_suspended_by_user', 'N/A')}")
            print(f"   - Shorting Enabled: {data.get('shorting_enabled', 'N/A')}")
        else:
            print(f"   ❌ FAILED: {resp.json()}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 2: Paper API - Positions
    print("\n🔍 Test 2: Paper API - Current Positions")
    try:
        resp = requests.get(f"{paper_endpoint}/positions", headers=headers, timeout=10)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            positions = resp.json()
            if positions:
                print("   ✅ Active Positions:")
                for pos in positions:
                    print(f"     - {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_entry_price']}")
            else:
                print("   ✅ No active positions")
        else:
            print(f"   ❌ FAILED: {resp.json()}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 3: Paper API - Orders (last 5)
    print("\n🔍 Test 3: Paper API - Recent Orders (last 5)")
    try:
        resp = requests.get(f"{paper_endpoint}/orders?limit=5", headers=headers, timeout=10)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            orders = resp.json()
            if orders:
                print("   ✅ Recent Orders:")
                for order in orders:
                    print(f"     - {order['symbol']} {order['side']} {order['qty']} @ {order.get('type', 'market')} | Status: {order['status']}")
            else:
                print("   ✅ No recent orders")
        else:
            print(f"   ❌ FAILED: {resp.json()}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 4: Market Data API
    print("\n🔍 Test 4: Market Data API - AAPL Quote")
    try:
        resp = requests.get(
            f"{data_endpoint}v2/stocks/AAPL/quotes/latest",
            headers=headers,
            timeout=10
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"   ✅ SUCCESS: {resp.json()}")
        else:
            print(f"   ❌ FAILED: {resp.json()}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    # Test 5: Check API key validity
    print("\n🔍 Test 5: Key Validation (via /v2/account)")
    try:
        resp = requests.get(f"{paper_endpoint}/account", headers=headers, timeout=10)
        if resp.status_code == 200:
            print("   ✅ API Key is VALID for Paper Trading")
        elif resp.status_code == 401:
            print("   ❌ API Key is INVALID or MISCONFIGURED")
            print(f"   Response: {resp.text}")
        elif resp.status_code == 403:
            print("   ❌ API Key lacks permission or account not activated")
            print(f"   Response: {resp.text}")
    except Exception as e:
        print(f"   ❌ Connection Error: {e}")

if __name__ == "__main__":
    test_alpaca_configurations()