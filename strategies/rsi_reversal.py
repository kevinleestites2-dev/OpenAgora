"""
OpenAgora — RSI Reversal Strategy
Trades overbought/oversold conditions using RSI on OHLCV candles.
Uses CCXT Binance for real candle data.

RSI < 30 = oversold -> BUY signal
RSI > 70 = overbought -> SELL signal
Confidence scales with distance from threshold.
"""

from core.market_feed import MarketFeed

ASSETS = [
    ("BTC/USDT", "bitcoin"),
    ("ETH/USDT", "ethereum"),
    ("SOL/USDT", "solana"),
    ("LINK/USDT", "chainlink"),
    ("ADA/USDT", "cardano"),
]

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70


def _calc_rsi(closes):
    if len(closes) < RSI_PERIOD + 1:
        return None
    gains, losses = [], []
    for i in range(1, RSI_PERIOD + 1):
        delta = closes[-i] - closes[-i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(delta))
    avg_gain = sum(gains) / RSI_PERIOD
    avg_loss = sum(losses) / RSI_PERIOD
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def analyze_rsi(feed=None):
    """Generate RSI reversal signals across ASSETS."""
    if feed is None:
        feed = MarketFeed()
    signals = []
    for symbol, coin_id in ASSETS:
        try:
            candles = feed.ccxt_ohlcv(symbol=symbol, timeframe="1h", limit=50)
            if not candles or len(candles) < RSI_PERIOD + 2:
                continue
            closes = [c[4] for c in candles]
            rsi = _calc_rsi(closes)
            if rsi is None:
                continue
            if rsi < RSI_OVERSOLD:
                action = "BUY"
                confidence = round(min((RSI_OVERSOLD - rsi) / RSI_OVERSOLD, 1.0), 2)
            elif rsi > RSI_OVERBOUGHT:
                action = "SELL"
                confidence = round(min((rsi - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT), 1.0), 2)
            else:
                continue
            signals.append({
                "asset": coin_id,
                "symbol": symbol,
                "type": "crypto",
                "action": action,
                "rsi": rsi,
                "confidence": confidence,
                "strategy": "rsi_reversal"
            })
        except Exception as e:
            print(f"[RSI] Error on {symbol}: {e}")
            continue
    return sorted(signals, key=lambda x: x["confidence"], reverse=True)
