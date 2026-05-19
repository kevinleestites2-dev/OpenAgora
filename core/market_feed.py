"""
OpenAgora - Enhanced Market Feed
Unified data layer: Stocks + Crypto + Prediction Markets + Training Data
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
        
        # Stock API integrations
        self.alpaca_key = os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret = os.getenv("ALPACA_API_SECRET", "")
        
        # Crypto exchange data
        self.binance_base = "https://api.binance.com/api/v3"

    # ─── CRYPTO ───────────────────────────────────────────────
    def get_crypto_prices(self, coins=None):
        """Get live crypto prices via CoinGecko (free, no key)"""
        if coins is None:
            coins = ["bitcoin", "ethereum", "solana", "polygon", "chainlink", "cardano", "avalanche-2", "dot"]
        ids = ",".join(coins)
        try:
            r = requests.get(
                f"{self.coingecko_base}/simple/price",
                params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true", "include_24hr_vol": "true"},
                timeout=10
            )
            return r.json()
        except Exception as e:
            print(f"[MarketFeed] Crypto error: {e}")
            return {}

    def get_crypto_price(self, coin_id):
        """Get price for a single coin"""
        try:
            r = requests.get(
                f"{self.coingecko_base}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true", "include_24hr_vol": "true", "include_market_cap": "true"},
                timeout=10
            )
            return r.json()
        except Exception as e:
            print(f"[MarketFeed] Crypto price error: {e}")
            return {}
    
    def get_crypto_orderbook(self, symbol="BTCUSDT"):
        """Get Binance orderbook for deeper market data"""
        try:
            r = requests.get(
                f"{self.binance_base}/depth",
                params={"symbol": symbol, "limit": 20},
                timeout=10
            )
            return r.json()
        except Exception as e:
            print(f"[MarketFeed] Orderbook error: {e}")
            return {}

    def get_crypto_klines(self, symbol="BTCUSDT", interval="1h", limit=100):
        """Get klines/candlestick data for training"""
        try:
            r = requests.get(
                f"{self.binance_base}/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
                timeout=10
            )
            return r.json()
        except Exception as e:
            print(f"[MarketFeed] Klines error: {e}")
            return []

    def get_crypto_trending(self):
        """Get trending coins"""
        try:
            r = requests.get(f"{self.coingecko_base}/search/trending", timeout=10)
            data = r.json()
            return [c["item"]["name"] for c in data.get("coins", [])[:10]]
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
                    "date": d["date"],
                    "volume": d.get("volume", 0)
                }
        except Exception as e:
            print(f"[MarketFeed] Stock error: {e}")
        return {}
    
    def get_stock_batch(self, tickers):
        """Get batch stock prices"""
        if not self.marketstack_key:
            return {}
        tickers_str = ",".join(tickers)
        try:
            r = requests.get(
                "http://api.marketstack.com/v1/eod/latest",
                params={"access_key": self.marketstack_key, "symbols": tickers_str},
                timeout=10
            )
            data = r.json()
            if "data" in data:
                return {d["symbol"]: d for d in data["data"]}
        except Exception as e:
            print(f"[MarketFeed] Batch stock error: {e}")
        return {}
    
    def get_alpaca_quote(self, ticker):
        """Get real-time quote via Alpaca"""
        if not self.alpaca_key or not self.alpaca_secret:
            return None
        try:
            r = requests.get(
                f"https://data.alpaca.markets/v2/stocks/{ticker}/quotes/latest",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret
                },
                timeout=10
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[MarketFeed] Alpaca quote error: {e}")
        return None

    # ─── PREDICTION MARKETS ───────────────────────────────────
    def get_poly_markets(self, limit=10):
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
            "prediction_markets": self.get_poly_markets(5)
        }
    
    def get_training_data(self, asset_type="crypto", symbol="BTCUSDT", interval="1h"):
        """Get historical data for training/learning"""
        if asset_type == "crypto":
            return self.get_crypto_klines(symbol, interval, 500)
        return []
