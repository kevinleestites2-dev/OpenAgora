"""
OpenAgora — OpenStock Layer
Ported from OpenStock (kevinleestites2-dev/OpenStock)

Provides:
  - Watchlist management (JSON-persisted, no MongoDB needed)
  - Price alerts (ABOVE / BELOW thresholds)
  - Finnhub real-time quotes + company profiles (free tier)
  - Yahoo Finance fallback (no key needed)
  - Alert engine: checks every cycle, fires Telegram when triggered

This is the OpenStock data layer wired directly into OpenAgora's market feed.
No Next.js, no MongoDB, no Inngest — pure Python, runs inside the engine.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")

WATCHLIST_PATH = Path("logs/watchlist.json")
ALERTS_PATH = Path("logs/alerts.json")

# ─── Default Pantheon Watchlist ───────────────────────────────
DEFAULT_WATCHLIST = [
    {"symbol": "AAPL",  "company": "Apple Inc."},
    {"symbol": "NVDA",  "company": "NVIDIA Corporation"},
    {"symbol": "TSLA",  "company": "Tesla Inc."},
    {"symbol": "MSFT",  "company": "Microsoft Corporation"},
    {"symbol": "AMZN",  "company": "Amazon.com Inc."},
    {"symbol": "META",  "company": "Meta Platforms Inc."},
    {"symbol": "GOOGL", "company": "Alphabet Inc."},
    {"symbol": "SPY",   "company": "S&P 500 ETF"},
    {"symbol": "QQQ",   "company": "Nasdaq 100 ETF"},
    {"symbol": "BRK-B", "company": "Berkshire Hathaway"},
]


# ─── Watchlist ─────────────────────────────────────────────────
def load_watchlist() -> list:
    if WATCHLIST_PATH.exists():
        return json.loads(WATCHLIST_PATH.read_text())
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(DEFAULT_WATCHLIST, indent=2))
    return DEFAULT_WATCHLIST


def add_to_watchlist(symbol: str, company: str) -> dict:
    wl = load_watchlist()
    symbols = [w["symbol"] for w in wl]
    if symbol.upper() in symbols:
        return {"status": "exists", "symbol": symbol}
    wl.append({"symbol": symbol.upper(), "company": company, "addedAt": datetime.utcnow().isoformat()})
    WATCHLIST_PATH.write_text(json.dumps(wl, indent=2))
    return {"status": "added", "symbol": symbol}


def remove_from_watchlist(symbol: str) -> dict:
    wl = load_watchlist()
    wl = [w for w in wl if w["symbol"] != symbol.upper()]
    WATCHLIST_PATH.write_text(json.dumps(wl, indent=2))
    return {"status": "removed", "symbol": symbol}


def get_watchlist_symbols() -> list:
    return [w["symbol"] for w in load_watchlist()]


# ─── Price Alerts ──────────────────────────────────────────────
def load_alerts() -> list:
    if ALERTS_PATH.exists():
        return json.loads(ALERTS_PATH.read_text())
    return []


def save_alerts(alerts: list):
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps(alerts, indent=2))


def create_alert(symbol: str, target_price: float, condition: str) -> dict:
    """
    condition: 'ABOVE' or 'BELOW'
    Alert fires once when price crosses threshold, then deactivates.
    """
    alerts = load_alerts()
    expires_at = (datetime.utcnow() + timedelta(days=90)).isoformat()
    alert = {
        "id": f"{symbol}_{condition}_{target_price}_{int(time.time())}",
        "symbol": symbol.upper(),
        "targetPrice": target_price,
        "condition": condition.upper(),
        "active": True,
        "triggered": False,
        "expiresAt": expires_at,
        "createdAt": datetime.utcnow().isoformat()
    }
    alerts.append(alert)
    save_alerts(alerts)
    return alert


def check_alerts(prices: dict) -> list:
    """
    prices: {symbol: current_price, ...}
    Returns list of triggered alerts.
    Ported from OpenStock inngest/functions.ts alert check loop.
    """
    alerts = load_alerts()
    triggered = []
    now = datetime.utcnow()

    for alert in alerts:
        if not alert.get("active") or alert.get("triggered"):
            continue
        # Check expiry
        try:
            expires = datetime.fromisoformat(alert["expiresAt"])
            if now > expires:
                alert["active"] = False
                continue
        except Exception:
            pass

        symbol = alert["symbol"]
        current_price = prices.get(symbol)
        if current_price is None:
            continue

        target = alert["targetPrice"]
        condition = alert["condition"]

        hit = (condition == "ABOVE" and current_price >= target) or \
              (condition == "BELOW" and current_price <= target)

        if hit:
            alert["triggered"] = True
            alert["active"] = False
            triggered.append({
                "symbol": symbol,
                "condition": condition,
                "targetPrice": target,
                "currentPrice": current_price,
                "alert_id": alert["id"]
            })

    save_alerts(alerts)
    return triggered


# ─── Finnhub Quotes ────────────────────────────────────────────
def get_finnhub_quote(symbol: str) -> dict:
    """Real-time quote from Finnhub (free tier: 60 calls/min)"""
    if not FINNHUB_KEY:
        return {}
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/quote",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=8
        )
        data = r.json()
        return {
            "symbol": symbol,
            "price": data.get("c", 0),       # current price
            "change": data.get("d", 0),       # change
            "pct_change": data.get("dp", 0),  # % change
            "high": data.get("h", 0),
            "low": data.get("l", 0),
            "open": data.get("o", 0),
            "prev_close": data.get("pc", 0),
            "source": "finnhub"
        }
    except Exception as e:
        print(f"[OpenStock] Finnhub quote error for {symbol}: {e}")
        return {}


def get_finnhub_company(symbol: str) -> dict:
    """Company profile from Finnhub"""
    if not FINNHUB_KEY:
        return {}
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/stock/profile2",
            params={"symbol": symbol, "token": FINNHUB_KEY},
            timeout=8
        )
        return r.json()
    except Exception as e:
        print(f"[OpenStock] Finnhub profile error for {symbol}: {e}")
        return {}


def get_finnhub_news(symbol: str, days_back: int = 3) -> list:
    """Stock news from Finnhub"""
    if not FINNHUB_KEY:
        return []
    try:
        from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
        r = requests.get(
            f"{FINNHUB_BASE}/company-news",
            params={"symbol": symbol, "from": from_date, "to": to_date, "token": FINNHUB_KEY},
            timeout=8
        )
        articles = r.json()
        # Filter + format — same as OpenStock validateArticle/formatArticle logic
        valid = []
        for a in articles[:5]:
            if a.get("headline") and a.get("url") and a.get("summary"):
                valid.append({
                    "headline": a["headline"],
                    "summary": a["summary"][:200],
                    "url": a["url"],
                    "source": a.get("source", ""),
                    "datetime": a.get("datetime", 0)
                })
        return valid
    except Exception as e:
        print(f"[OpenStock] Finnhub news error: {e}")
        return []


# ─── Yahoo Fallback Quote ──────────────────────────────────────
def get_yahoo_quote(symbol: str) -> dict:
    """Free Yahoo Finance quote — no key needed"""
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            timeout=8
        )
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            return {
                "symbol": symbol,
                "price": meta.get("regularMarketPrice", 0),
                "prev_close": meta.get("chartPreviousClose", 0),
                "high": meta.get("regularMarketDayHigh", 0),
                "low": meta.get("regularMarketDayLow", 0),
                "volume": meta.get("regularMarketVolume", 0),
                "source": "yahoo"
            }
    except Exception as e:
        print(f"[OpenStock] Yahoo quote error for {symbol}: {e}")
    return {}


# ─── Watchlist Snapshot ────────────────────────────────────────
def get_watchlist_snapshot() -> dict:
    """
    Pull current prices for all watchlist symbols.
    Uses Finnhub if key available, falls back to Yahoo.
    Returns {symbol: price_data} dict.
    """
    symbols = get_watchlist_symbols()
    snapshot = {}
    for symbol in symbols:
        if FINNHUB_KEY:
            data = get_finnhub_quote(symbol)
        else:
            data = get_yahoo_quote(symbol)
        if data and data.get("price", 0) > 0:
            snapshot[symbol] = data
        time.sleep(0.15)  # gentle rate limiting
    return snapshot


def get_watchlist_prices() -> dict:
    """Returns {symbol: current_price} for alert checking"""
    snapshot = get_watchlist_snapshot()
    return {sym: data["price"] for sym, data in snapshot.items()}


# ─── Signal Generator ──────────────────────────────────────────
def generate_stock_signals(snapshot: dict) -> list:
    """
    Generate simple momentum signals from watchlist snapshot.
    Ported from OpenStock's AI sentiment concept — simplified for speed.
    Signal: if pct_change > +1.5% → BUY signal | < -1.5% → SELL signal
    """
    signals = []
    for symbol, data in snapshot.items():
        pct = data.get("pct_change", 0)
        price = data.get("price", 0)
        if price <= 0:
            continue

        if pct >= 1.5:
            signals.append({
                "asset": symbol,
                "asset_type": "stock",
                "action": "BUY",
                "confidence": min(0.5 + (pct / 20), 0.85),
                "price": price,
                "reason": f"Momentum +{pct:.1f}%"
            })
        elif pct <= -1.5:
            signals.append({
                "asset": symbol,
                "asset_type": "stock",
                "action": "SELL",
                "confidence": min(0.5 + (abs(pct) / 20), 0.85),
                "price": price,
                "reason": f"Momentum {pct:.1f}%"
            })

    return signals
