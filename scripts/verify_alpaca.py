#!/usr/bin/env python3
"""
Skrip verifikasi koneksi Alpaca API
"""
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv("/root/alpaca-overlay-agent-a2z/.env")

def verify_alpaca_connection():
    """Verify connection to Alpaca API"""

    # Get credentials
    endpoint = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")
    key = os.getenv("ALPACA_KEY")
    secret = os.getenv("ALPACA_SECRET")

    if not key or not secret:
        print("❌ ERROR: Alpaca key atau secret tidak ditemukan di .env")
        return False

    print("🔑 Menggunakan kredensial:")
    print(f"   Key: {key[:10]}...")
    print(f"   Secret: {secret[:10]}...")
    print(f"   Endpoint: {endpoint}")

    # Test account endpoint
    try:
        response = requests.get(
            f"{endpoint}/account",
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret
            }
        )

        if response.status_code == 200:
            account_data = response.json()
            print("\n✅ Koneksi berhasil!")
            print(f"   Status Akun: {account_data.get('status', 'N/A')}")
            print(f"   Cash: ${account_data.get('cash', 'N/A')}")
            print(f"   Portfolio Value: ${account_data.get('portfolio_value', 'N/A')}")
            return True
        else:
            print(f"\n❌ Gagal menghubungkan ke API")
            print(f"   HTTP Status: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"\n❌ Error saat menghubungi API: {e}")
        return False

if __name__ == "__main__":
    print("=== Verifikasi Koneksi Alpaca API ===")
    verify_alpaca_connection()