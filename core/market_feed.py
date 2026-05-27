"""
OpenAgora - Enhanced Market Feed
Unified data layer: Stocks + Crypto + Prediction Markets
CCXT integration: 100+ exchanges via unified API
"""

import requests
import os
import json
import time
from datetime import datetime

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("[MarketFeed] ccxt not installed — run: pip install ccxt")


class MarketFeed:
    def __init__(self):
        self.coingecko_base = "https://api.coingecko.com/api/v3"
        self.polymarket_base = "https://clob.polymarket.com"

        # CCXT exchange instances — add keys per exchange as needed
        self.exchanges = {}
        if CCXT_AVAILABLE:
            self._init_ccxt_exchanges()

        # Rate limiting
        self.coingecko_calls = 0
        self.last_coingecko_call = 0
        self.coingecko_rate_limit = 10

    def _init_ccxt_exchanges(self):
        """Initialize CCXT exchange connections. Add keys as they become available."""
        # Binance — public data (no key needed for market data)
        self.exchanges["binance"] = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_API_SECRET", ""),
            "enableRateLimit": True,
        })
        # Kraken
        self.exchanges["kraken"] = ccxt.kraken({
            "apiKey": os.getenv("KRAKEN_API_KEY", ""),
            "secret": os.getenv("KRAKEN_API_SECRET", ""),
            "enableRateLimit": True,
        })
        # Coinbase
        self.exchanges["coinbase"] = ccxt.coinbaseadvanced({
            "apiKey": os.getenv("COINBASE_API_KEY", ""),
            "secret": os.getenv("COINBASE_API_SECRET", ""),
            "enableRateLimit": True,
        })
        print(f"[CCXT] {len(self.exchanges)} exchanges initialized")

    # ─── CCXT UNIFIED LAYER ───────────────────────────────────
    def ccxt_ticker(self, symbol="BTC/USDT", exchange="binance"):
        """Get ticker via CCXT — works on any exchange"""
        if not CCXT_AVAILABLE:
            return {}
        try:
            ex = self.exchanges.get(exchange)
            if ex:
                return ex.fetch_ticker(symbol)
        except Exception as e:
            print(f"[CCXT] Ticker error {exchange}/{symbol}: {e}")
        return {}

    def ccxt_orderbook(self, symbol="BTC/USDT", exchange="binance", limit=20):
        """Get orderbook via CCXT"""
        if not CCXT_AVAILABLE:
            return {}
        try:
            ex = self.exchanges.get(exchange)
            if ex:
                return ex.fetch_order_book(symbol, limit)
        except Exception as e:
            print(f"[CCXT] Orderbook error: {e}")
        return {}

    def ccxt_ohlcv(self, symbol="BTC/USDT", timeframe="1h", limit=100, exchange="binance"):
        """Get OHLCV candles via CCXT"""
        if not CCXT_AVAILABLE:
            return []
        try:
            ex = self.exchanges.get(exchange)
            if ex:
                return ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            print(f"[CCXT] OHLCV error: {e}")
        return []

    def ccxt_multi_exchange_ticker(self, symbol="BTC/USDT"):
        """Get ticker across ALL initialized exchanges — arbitrage scanner"""
        results = {}
        for name, ex in self.exchanges.items():
            try:
                t = ex.fetch_ticker(symbol)
                results[name] = {"bid": t.get("bid"), "ask": t.get("ask"), "last": t.get("last")}
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    # ─── CRYPTO ───────────────────────────────────────────────
    def _coingecko_rate_limit_wait(self):
        now = time.time()
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

    def get_crypto_trending(self):
        try:
            r = requests.get(f"{self.coingecko_base}/search/trending", timeout=10)
            data = r.json()
            return [c["item"]["name"] for c in data.get("coins", [])[:10]]
        except Exception as e:
            print(f"[MarketFeed] Trending error: {e}")
            return []

    # ─── STOCKS ───────────────────────────────────────────────
    def _yahoo_get_quote(self, ticker):
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
                        "open": meta.get("chartPreviousClose", 0),
                        "high": meta.get("regularMarketDayHigh", 0),
                        "low": meta.get("regularMarketDayLow", 0),
                        "volume": meta.get("regularMarketVolume", 0),
                        "source": "yahoo"
                    }
        except Exception as e:
            print(f"[MarketFeed] Yahoo error for {ticker}: {e}")
        return None

    def get_stock_price(self, ticker):
        return self._yahoo_get_quote(ticker)

    def get_stock_batch(self, tickers):
        results = {}
        for t in tickers:
            data = self._yahoo_get_quote(t)
            if data:
                results[t] = data
        return results

    # ─── PREDICTION MARKETS ───────────────────────────────────
    def get_poly_markets(self, limit=10):
        try:
            r = requests.get(
                f"{self.polymarket_base}/markets",
                params={"active": True, "closed": False, "_limit": limit},
                timeout=10
            )
            data = r.json()
            return data.get("data") or []
        except Exception as e:
            print(f"[MarketFeed] Polymarket error: {e}")
            return []

    # ─── SNAPSHOTS ────────────────────────────────────────────
    def snapshot(self):
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "crypto": self.get_crypto_prices(),
            "trending": self.get_crypto_trending(),
            "prediction_markets": self.get_poly_markets(5)
        }

    def full_snapshot(self):
        from core.openstock_layer import get_watchlist_snapshot
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "crypto": self.get_crypto_prices(),
            "ccxt_btc": self.ccxt_ticker("BTC/USDT", "binance"),
            "trending": self.get_crypto_trending(),
            "stocks": get_watchlist_snapshot(),
            "prediction_markets": self.get_poly_markets(5)
        }

    def arbitrage_scan(self, symbol="BTC/USDT"):
        """Scan price differences across exchanges — find the spread"""
        return self.ccxt_multi_exchange_ticker(symbol)
