"""
OpenAgora — FMP Backtest Engine
Pulls historical OHLCV data from Financial Modeling Prep.
Runs OpenAgora's meta strategy against real past data.
Compresses weeks of sim runtime into hours.
"""

import os
import json
import time
import random
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

FMP_BASE = "https://financialmodelingprep.com/api/v3"
FMP_KEY = os.getenv("FMP_API_KEY", "")

# Assets to backtest
BACKTEST_SYMBOLS = {
    "stocks": ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "META", "GOOGL", "SPY", "QQQ"],
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "MATICUSD"],
}

BACKTEST_RESULTS_PATH = Path("logs/backtest_results.json")
BACKTEST_MEMORY_PATH  = Path("memory/backtest_weights.json")


# ─── FMP Data Fetcher ─────────────────────────────────────────

def fetch_historical(symbol: str, days: int = 365) -> list:
    """
    Pull daily OHLCV from FMP.
    Returns list of candles sorted oldest → newest.
    """
    if not FMP_KEY:
        print("[Backtest] FMP_API_KEY not set.")
        return []

    end   = datetime.utcnow()
    start = end - timedelta(days=days)

    try:
        url = f"{FMP_BASE}/historical-price-full/{symbol}"
        r = requests.get(url, params={
            "from": start.strftime("%Y-%m-%d"),
            "to":   end.strftime("%Y-%m-%d"),
            "apikey": FMP_KEY
        }, timeout=15)

        data = r.json()
        candles = data.get("historical", [])

        # Normalize + reverse to oldest-first
        normalized = []
        for c in reversed(candles):
            normalized.append({
                "date":   c.get("date"),
                "open":   float(c.get("open",  0)),
                "high":   float(c.get("high",  0)),
                "low":    float(c.get("low",   0)),
                "close":  float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
                "change": float(c.get("changePercent", 0)),
            })

        print(f"[Backtest] {symbol}: {len(normalized)} candles loaded")
        return normalized

    except Exception as e:
        print(f"[Backtest] Error fetching {symbol}: {e}")
        return []


# ─── Signal Generator (mirrors MetaStrategy logic) ───────────

def generate_signal(candles: list, idx: int) -> dict | None:
    """
    Generate a signal from a candle window.
    Uses same logic as MetaStrategy.analyze_crypto / generate_stock_signals.
    """
    if idx < 5:
        return None

    current  = candles[idx]
    prev5    = candles[idx - 5: idx]

    change   = current["change"]
    avg_vol  = sum(c["volume"] for c in prev5) / 5
    vol_surge = current["volume"] > avg_vol * 1.2

    # Momentum signal
    if abs(change) > 0.5:
        action     = "BUY" if change > 0 else "SELL"
        confidence = min(abs(change) / 5.0, 1.0)

        # Boost confidence on volume surge
        if vol_surge:
            confidence = min(confidence + 0.15, 1.0)

        return {
            "action":     action,
            "change":     round(change, 2),
            "confidence": round(confidence, 2),
            "vol_surge":  vol_surge,
        }

    return None


def simulate_trade(signal: dict, current_candle: dict, next_candle: dict) -> float:
    """
    Simulate P&L: entry at current close, exit at next close.
    Returns realistic P&L based on actual price movement.
    """
    entry  = current_candle["close"]
    exit_  = next_candle["close"]

    if entry <= 0:
        return 0.0

    actual_change = (exit_ - entry) / entry * 100  # % move

    if signal["action"] == "BUY":
        raw_pnl = actual_change
    else:  # SELL / SHORT
        raw_pnl = -actual_change

    # Scale to dollar P&L (normalized unit trade)
    pnl = round(raw_pnl * signal["confidence"], 4)
    return pnl


# ─── Core Backtest Runner ─────────────────────────────────────

def run_backtest(days: int = 365, verbose: bool = True) -> dict:
    """
    Main backtest loop.
    Pulls FMP historical data for all symbols.
    Runs signal generation + simulated execution.
    Outputs win rate, total P&L, and per-strategy weights.
    """
    print("\n" + "="*54)
    print("  🏛️  OpenAgora — FMP Backtest Engine")
    print(f"  Period: {days} days | Assets: {sum(len(v) for v in BACKTEST_SYMBOLS.values())}")
    print("="*54 + "\n")

    all_trades     = []
    strategy_stats = {}  # strategy → {wins, losses, pnl}

    for asset_type, symbols in BACKTEST_SYMBOLS.items():
        for symbol in symbols:
            candles = fetch_historical(symbol, days=days)
            if len(candles) < 10:
                continue

            time.sleep(0.3)  # FMP rate limit (300 req/min free tier)

            for i in range(5, len(candles) - 1):
                signal = generate_signal(candles, i)
                if not signal:
                    continue

                pnl = simulate_trade(signal, candles[i], candles[i + 1])

                # Map to a strategy bucket (mirrors MetaStrategy)
                if signal["vol_surge"] and abs(signal["change"]) > 2.0:
                    strategy = "momentum"
                elif abs(signal["change"]) > 1.5:
                    strategy = "trend_follow"
                else:
                    strategy = "mean_reversion"

                trade = {
                    "symbol":     symbol,
                    "type":       asset_type,
                    "date":       candles[i]["date"],
                    "action":     signal["action"],
                    "confidence": signal["confidence"],
                    "pnl":        pnl,
                    "strategy":   strategy,
                    "win":        pnl > 0,
                }
                all_trades.append(trade)

                # Accumulate strategy stats
                if strategy not in strategy_stats:
                    strategy_stats[strategy] = {"wins": 0, "losses": 0, "pnl": 0.0}
                strategy_stats[strategy]["pnl"]    += pnl
                if pnl > 0:
                    strategy_stats[strategy]["wins"]   += 1
                else:
                    strategy_stats[strategy]["losses"] += 1

    # ─── Aggregate Results ────────────────────────────────────
    total_trades = len(all_trades)
    total_wins   = sum(1 for t in all_trades if t["win"])
    total_pnl    = sum(t["pnl"] for t in all_trades)
    win_rate     = (total_wins / total_trades * 100) if total_trades > 0 else 0

    # ─── Build EverOS-compatible weights ─────────────────────
    weights = {}
    for strat, stats in strategy_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            wr = stats["wins"] / total
            weights[strat] = round(wr, 4)

    # Normalize weights to sum to 1.0
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: round(v / total_w, 4) for k, v in weights.items()}

    results = {
        "timestamp":     datetime.utcnow().isoformat(),
        "period_days":   days,
        "total_trades":  total_trades,
        "total_wins":    total_wins,
        "win_rate":      round(win_rate, 2),
        "total_pnl":     round(total_pnl, 4),
        "strategy_stats": strategy_stats,
        "everos_weights": weights,
    }

    # ─── Save Results ─────────────────────────────────────────
    BACKTEST_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_RESULTS_PATH.write_text(json.dumps(results, indent=2))

    # ─── Write weights to EverOS memory ──────────────────────
    _inject_weights_to_everos(weights)

    # ─── Print Summary ────────────────────────────────────────
    if verbose:
        print(f"\n{'='*54}")
        print(f"  BACKTEST COMPLETE")
        print(f"{'='*54}")
        print(f"  Period    : {days} days")
        print(f"  Trades    : {total_trades:,}")
        print(f"  Win Rate  : {win_rate:.1f}%")
        print(f"  Total P&L : {total_pnl:+.2f}")
        print(f"\n  Strategy Weights (→ EverOS):")
        for strat, w in weights.items():
            s = strategy_stats[strat]
            wr = s['wins'] / (s['wins'] + s['losses']) * 100 if (s['wins'] + s['losses']) > 0 else 0
            print(f"    {strat:<16} weight={w:.3f}  win_rate={wr:.1f}%  pnl={s['pnl']:+.2f}")
        print(f"{'='*54}\n")

    return results


# ─── EverOS Weight Injection ──────────────────────────────────

def _inject_weights_to_everos(weights: dict):
    """
    Write backtest-derived weights directly into EverOS memory.
    This is what compresses 2-3 weeks of runtime into hours.
    EverOS will use these as a pre-trained starting point.
    """
    try:
        memory_path = Path("memory/trade_memory.json")
        if memory_path.exists():
            data = json.loads(memory_path.read_text())
        else:
            data = {}

        data.setdefault("strategy_weights", {})
        data.setdefault("trade_history",    [])
        data.setdefault("lessons",          [])
        data.setdefault("signal_patterns",  {})
        data.setdefault("blacklist",        [])
        data.setdefault("confidence_calibration", {})

        # Merge: backtest weights take precedence
        data["strategy_weights"].update(weights)
        data["lessons"].append(
            f"[BACKTEST INJECT] Pre-trained weights from FMP historical data: {weights}"
        )

        memory_path.parent.mkdir(parents=True, exist_ok=True)
        memory_path.write_text(json.dumps(data, indent=2))
        print(f"[Backtest] ✅ EverOS weights injected: {weights}")

    except Exception as e:
        print(f"[Backtest] EverOS inject error: {e}")


# ─── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OpenAgora FMP Backtest Engine")
    parser.add_argument("--days", type=int, default=365, help="Days of history to backtest")
    args = parser.parse_args()

    run_backtest(days=args.days)
