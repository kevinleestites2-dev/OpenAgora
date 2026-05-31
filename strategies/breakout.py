"""
OpenAgora — Breakout Strategy
Detects price breaking above recent N-candle high or below N-candle low.
Uses CCXT Binance OHLCV. High breakout = BUY. Low breakdown = SELL.
Confidence scales with breakout magnitude.
"""

from core.market_feed import MarketFeed

ASSETS = [
    ("BTC/USDT", "bitcoin"),
    ("ETH/USDT", "ethereum"),
    ("SOL/USDT", "solana"),
    ("LINK/USDT", "chainlink"),
    ("ADA/USDT", "cardano"),
]

LOOKBACK = 20
BREAKOUT_THRESHOLD = 0.005  # 0.5% above range high to confirm breakout


def analyze_breakout(feed=None):
    """Generate breakout signals across ASSETS."""
    if feed is None:
        feed = MarketFeed()
    signals = []
    for symbol, coin_id in ASSETS:
        try:
            candles = feed.ccxt_ohlcv(symbol=symbol, timeframe="1h", limit=LOOKBACK + 5)
            if not candles or len(candles) < LOOKBACK + 2:
                continue
            closes = [c[4] for c in candles]
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]

            current_price = closes[-1]
            range_high = max(highs[-LOOKBACK - 1:-1])
            range_low = min(lows[-LOOKBACK - 1:-1])

            breakout_up = current_price > range_high * (1 + BREAKOUT_THRESHOLD)
            breakdown = current_price < range_low * (1 - BREAKOUT_THRESHOLD)

            if breakout_up:
                magnitude = (current_price - range_high) / range_high
                confidence = round(min(magnitude * 20, 1.0), 2)
                signals.append({
                    "asset": coin_id,
                    "symbol": symbol,
                    "type": "crypto",
                    "action": "BUY",
                    "breakout_pct": round(magnitude * 100, 2),
                    "confidence": confidence,
                    "strategy": "breakout"
                })
            elif breakdown:
                magnitude = (range_low - current_price) / range_low
                confidence = round(min(magnitude * 20, 1.0), 2)
                signals.append({
                    "asset": coin_id,
                    "symbol": symbol,
                    "type": "crypto",
                    "action": "SELL",
                    "breakdown_pct": round(magnitude * 100, 2),
                    "confidence": confidence,
                    "strategy": "breakout"
                })
        except Exception as e:
            print(f"[Breakout] Error on {symbol}: {e}")
            continue
    return sorted(signals, key=lambda x: x["confidence"], reverse=True)
