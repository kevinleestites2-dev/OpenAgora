"""
OpenAgora - Enhanced Market Feed
Unified data layer: Stocks + Crypto + Prediction Markets + Training Data
With Yahoo Finance, rate limiting, and null guards
"""

import requests
import os
import json
import time
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
        
        # Rate limiting
        self.coingecko_calls = 0
        self.last_coingecko_call = 0
        self.coingecko_rate_limit = 10  # calls per minute (free tier)

    # ─── CRYPTO ───────────────────────────────────────────────
    def _coingecko_rate_limit_wait(self):
        """Wait if rate limited"""
        now = time.time()
        # Reset counter every minute
        if now - self.last_coingecko_call > 60:
            self.coingecko_calls = 0
            self.last_coingecko_call = now
        
        if self.coingecko_calls >= self.coingecko_rate_limit:
            wait_time = 60 - (now - self.last_coingecko_call)
            print(f"[MarketFeed] Rate limited, waiting {wait_time:.1f}s...")
            time.sleep(max(1, wait_time))
            self.coingecko_calls = 0
            self.last_coingecko_call = time.time()
        
        self.coingecko_calls += 1
    
    def get_crypto_prices(self, coins=None):
        """Get live crypto prices via CoinGecko (free, no key)"""
        self._coingecko_rate_limit_wait()
        
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
        """Get stock price via Yahoo Finance (free, no key needed)"""
        # First try Yahoo Finance
        yahoo_data = self._yahoo_get_quote(ticker)
        if yahoo_data:
            return yahoo_data
        
        # Fallback to Marketstack
        if not self.marketstack_key:
            return {"error": "No Marketstack key"}
        
        # ... rest of Marketstack code
        return {}
    
    def _yahoo_get_quote(self, ticker):
        """Get stock via Yahoo Finance (free, no key)"""
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    return {
                        "ticker": ticker,
                        "close": meta.get("regularMarketPrice", 0),
                        "open": meta.get("chartPreviousClose", 0) or meta.get("regularMarketPreviousClose", 0),
                        "high": meta.get("regularMarketDayHigh", 0),
                        "low": meta.get("regularMarketDayLow", 0),
                        "volume": meta.get("regularMarketVolume", 0),
                        "source": "yahoo"
                    }
        except Exception as e:
            print(f"[MarketFeed] Yahoo error for {ticker}: {e}")
        return None
    
    def get_stock_batch(self, tickers):
        """Get batch stock prices via Yahoo"""
        results = {}
        for t in tickers:
            data = self._yahoo_get_quote(t)
            if data:
                results[t] = data
        return results
    
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
            data = r.json()
            # Null guard - return empty list if no data
            return data.get("data") or []
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

    # ─── OPENSTOCK LAYER ──────────────────────────────────────
    def get_stock_watchlist_snapshot(self):
        """Pull live prices for all OpenStock watchlist symbols"""
        from core.openstock_layer import get_watchlist_snapshot, check_alerts, get_watchlist_prices
        from reporting.telegram_bot import send
        snapshot = get_watchlist_snapshot()
        # Run alert checks on every cycle
        prices = {sym: d["price"] for sym, d in snapshot.items() if d.get("price", 0) > 0}
        triggered = check_alerts(prices)
        for alert in triggered:
            msg = (
                f"🚨 *OpenStock Alert Triggered*\n"
                f"Symbol: `{alert['symbol']}`\n"
                f"Condition: `{alert['condition']} ${alert['targetPrice']:.2f}`\n"
                f"Current Price: `${alert['currentPrice']:.2f}`"
            )
            send(msg)
            print(f"[OpenStock] Alert fired: {alert['symbol']} {alert['condition']} ${alert['targetPrice']}")
        return snapshot

    def get_stock_signals(self):
        """Generate momentum signals from watchlist — OpenStock layer"""
        from core.openstock_layer import get_watchlist_snapshot, generate_stock_signals
        snapshot = get_watchlist_snapshot()
        return generate_stock_signals(snapshot)

    def full_snapshot(self):
        """Complete snapshot: crypto + stocks (OpenStock) + prediction markets"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "crypto": self.get_crypto_prices(),
            "trending": self.get_crypto_trending(),
            "stocks": self.get_stock_watchlist_snapshot(),
            "prediction_markets": self.get_poly_markets(5)
        }

