"""
OpenAgora — Market Feed
Unified data layer: Stocks + Crypto + Prediction Markets
"""

import requests
import os
import json
from datetime import datetime


class MarketFeed:
    def __init__(self):
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.marketstack_key = os.getenv("MARKETSTACK_API_KEY", "")
        self.polymarket_base = "https://clob.polymarket.com"

    # ─── CRYPTO ───────────────────────────────────────────────
    def get_crypto_prices(self, coins=None):
        """Get live crypto prices via CoinGecko (free, no key)"""
        if coins is None:
            coins = ["bitcoin", "ethereum", "solana", "polygon", "chainlink"]
        ids = ",".join(coins)
        try:
            r = requests.get(
                f"{self.coingecko_base}/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=10
            )
            return r.json()
        except Exception as e:
            print(f"[MarketFeed] Crypto error: {e}")
            return {}

    def get_crypto_trending(self):
        """Get trending coins"""
        try:
            r = requests.get(f"{self.coingecko_base}/search/trending", timeout=10)
            data = r.json()
            return [c["item"]["name"] for c in data.get("coins", [])[:5]]
        except Exception as e:
            print(f"[MarketFeed] Trending error: {e}")
            return []

    # ─── STOCKS ───────────────────────────────────────────────
    def get_stock_price(self, ticker):
        """Get stock price via Marketstack (100 req/mo free)"""
        if not self.marketstack_key:
            return {"error": "No Marketstack key"}
        try:
            r = requests.get(
                "http://api.marketstack.com/v1/eod/latest",
                params={"access_key": self.marketstack_key, "symbols": ticker},
                timeout=10
            )
            data = r.json()
            if "data" in data and data["data"]:
                d = data["data"][0]
                return {
                    "ticker": d["symbol"],
                    "close": d["close"],
                    "open": d["open"],
                    "high": d["high"],
                    "low": d["low"],
                    "date": d["date"]
                }
        except Exception as e:
            print(f"[MarketFeed] Stock error: {e}")
        return {}

    # ─── PREDICTION MARKETS ───────────────────────────────────
    def get_poly_markets(self, limit=5):
        """Get top active Polymarket prediction markets"""
        try:
            r = requests.get(
                f"{self.polymarket_base}/markets",
                params={"active": True, "closed": False, "_limit": limit},
                timeout=10
            )
            return r.json().get("data", [])
        except Exception as e:
            print(f"[MarketFeed] Polymarket error: {e}")
            return []

    # ─── UNIFIED SNAPSHOT ─────────────────────────────────────
    def snapshot(self):
        """Full market snapshot across all asset classes"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "crypto": self.get_crypto_prices(),
            "trending": self.get_crypto_trending(),
            "prediction_markets": self.get_poly_markets(3)
        }
