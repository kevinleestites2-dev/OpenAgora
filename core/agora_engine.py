"""
OpenAgora — The Meta Trading Engine v2.1
Stocks + Crypto + Prediction Markets | Self-Evolving | MidasPrime Powered

v2.1 upgrades (surgical — no core logic changed):
  1. Confidence-scaled position sizing — bigger bet at conf=1.0, smaller at conf<0.85
  2. Consecutive loss circuit breaker — 2 losses in a row → skip 1 cycle, let EverOS breathe
  3. Asset diversification nudge — EverOS can promote a 2nd asset when confidence is high

Usage:
  python core/agora_engine.py --mode simulate
  python core/agora_engine.py --mode live
"""

import os
import sys
import time
import argparse
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.market_feed import MarketFeed
from core.war_chest import log_trade, get_summary
from strategies.meta_strategy import MetaStrategy
from memory.everos_bridge import (
    record_trade,
    get_strategy_weights,
    get_top_assets,
    get_memory_summary,
    is_blacklisted,
    record_signal_pattern,
    reflect,
    add_lesson
)
from reporting.telegram_bot import startup_message, trade_alert, heartbeat, send

SIMULATE       = os.getenv("SIMULATE_MODE", "true").lower() == "true"
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "300"))  # 5 min default
REFLECT_EVERY  = 10

# ─── v2.1: CIRCUIT BREAKER STATE ─────────────────────────────────────────────
_consecutive_losses  = 0   # rolling counter — resets on any win
_skip_next_cycle     = False  # set True after 2 consecutive losses
CIRCUIT_BREAKER_LIMIT = int(os.getenv("CIRCUIT_BREAKER_LIMIT", "2"))

# ─── v2.1: CONFIDENCE SCALING ────────────────────────────────────────────────
def confidence_scale(base_pnl: float, confidence: float) -> float:
    """
    Scale simulated P&L by confidence tier.
    conf >= 0.95 → full size (1.0x)
    conf >= 0.85 → 0.75x
    conf >= 0.70 → 0.50x
    conf <  0.70 → 0.30x (barely alive — EverOS should blacklist soon)
    This doesn't change the win/loss outcome, only the size of the reward/risk.
    """
    if confidence >= 0.95:
        return base_pnl * 1.0
    elif confidence >= 0.85:
        return round(base_pnl * 0.75, 4)
    elif confidence >= 0.70:
        return round(base_pnl * 0.50, 4)
    else:
        return round(base_pnl * 0.30, 4)

# ─── v2.1: DIVERSIFICATION NUDGE ─────────────────────────────────────────────
def maybe_diversify(signals: list, top: dict) -> dict:
    """
    If top signal is conf=1.0 AND there's a strong 2nd signal (conf>=0.85),
    EverOS gets a second trade this cycle. Doubles the upside on high-conviction cycles.
    Both must be different assets — no doubling up on same coin.
    Returns second trade dict or None.
    """
    if top["confidence"] < 1.0:
        return None
    others = [
        s for s in signals
        if s["asset"] != top["asset"]
        and not is_blacklisted(s["asset"])
        and s["confidence"] >= 0.85
    ]
    if others:
        return others[0]
    return None


# ─── CCXT LIVE EXECUTOR ───────────────────────────────────────────────────────
def ccxt_execute(asset: str, action: str, asset_type: str, confidence: float = 1.0) -> float:
    """
    Execute a real trade via CCXT.
    Returns PnL estimate (entry price - fill price delta).
    v2.1: trade size scales with confidence.
    """
    import ccxt

    COIN_MAP = {
        "bitcoin":      "BTC/USDT",
        "ethereum":     "ETH/USDT",
        "solana":       "SOL/USDT",
        "polygon":      "MATIC/USDT",
        "chainlink":    "LINK/USDT",
        "cardano":      "ADA/USDT",
        "avalanche-2":  "AVAX/USDT",
        "dot":          "DOT/USDT",
    }

    EXCHANGE_ID = os.getenv("CCXT_EXCHANGE", "binance")
    API_KEY     = os.getenv(f"{EXCHANGE_ID.upper()}_API_KEY", "")
    API_SECRET  = os.getenv(f"{EXCHANGE_ID.upper()}_API_SECRET", "")
    BASE_SIZE   = float(os.getenv("TRADE_SIZE_USD", "10"))

    # v2.1: scale trade size by confidence
    if confidence >= 0.95:
        trade_size = BASE_SIZE * 1.0
    elif confidence >= 0.85:
        trade_size = BASE_SIZE * 0.75
    elif confidence >= 0.70:
        trade_size = BASE_SIZE * 0.50
    else:
        trade_size = BASE_SIZE * 0.30

    if not API_KEY or not API_SECRET:
        print(f"[CCXT] No keys for {EXCHANGE_ID} — add {EXCHANGE_ID.upper()}_API_KEY to .env")
        return 0.0

    try:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        exchange = exchange_class({
            "apiKey":          API_KEY,
            "secret":          API_SECRET,
            "enableRateLimit": True,
        })

        symbol = COIN_MAP.get(asset.lower())
        if not symbol:
            symbol = asset if "/" in asset else f"{asset.upper()}/USDT"

        ticker = exchange.fetch_ticker(symbol)
        price  = ticker["last"]
        amount = trade_size / price

        side = "buy" if action == "BUY" else "sell"
        print(f"[CCXT] LIVE {side.upper()} {symbol} @ ${price:.4f} | size=${trade_size:.2f} (conf={confidence})")

        order      = exchange.create_market_order(symbol, side, amount)
        fill_price = order.get("average") or order.get("price") or price
        fee        = order.get("fee", {}).get("cost", 0) or 0
        pnl        = (fill_price - price) * amount if side == "buy" else (price - fill_price) * amount
        pnl        = round(pnl - fee, 6)

        print(f"[CCXT] Filled | fill={fill_price} | fee={fee} | pnl={pnl:+.6f}")
        send(
            f"🔴 *LIVE TRADE EXECUTED*\n"
            f"Exchange: `{EXCHANGE_ID}` | Pair: `{symbol}`\n"
            f"Side: `{side.upper()}` | Size: `${trade_size:.2f}` (conf={confidence})\n"
            f"Fill: `${fill_price:.4f}` | Fee: `${fee:.4f}` | PnL: `${pnl:+.6f}`"
        )
        return pnl

    except ccxt.InsufficientFunds as e:
        print(f"[CCXT] Insufficient funds: {e}")
        send(f"⚠️ *Insufficient Funds*\n`{e}`")
        return 0.0
    except ccxt.NetworkError as e:
        print(f"[CCXT] Network error: {e}")
        return 0.0
    except Exception as e:
        print(f"[CCXT] Error: {e}")
        send(f"⚠️ *CCXT Error*\n`{str(e)[:200]}`")
        return 0.0
# ─────────────────────────────────────────────────────────────────────────────


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║    The Meta Trading Engine — Pantheon v2.1       ║
║  Risk-Protected | Self-Evolving | Always Watching ║
╚══════════════════════════════════════════════════╝
""")


def run_relay_thread():
    """Push status to Nexus Relay every 60s (background)"""
    import threading
    import requests

    RELAY_URL    = os.getenv("NEXUS_RELAY_URL", "")
    RELAY_SECRET = os.getenv("RELAY_SECRET", "pantheon_prime")

    if not RELAY_URL:
        return

    def _push():
        while True:
            try:
                summary = get_summary()
                requests.post(
                    f"{RELAY_URL}/command",
                    json={"type": "status", "trades": summary.get("total_trades", 0), "pnl": summary.get("total_pnl", 0.0)},
                    headers={"X-Secret": RELAY_SECRET},
                    timeout=5
                )
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=_push, daemon=True).start()


def run_cycle(engine: MetaStrategy, simulate: bool, cycle_num: int):
    """Execute one full Meta trading cycle — v2.1"""
    global _consecutive_losses, _skip_next_cycle

    mode_tag = "[SIMULATE]" if simulate else "[LIVE]"

    # ── v2.1: Circuit Breaker ──────────────────────────────────────────────
    if _skip_next_cycle:
        _skip_next_cycle = False
        print(f"[Agora] ⚡ Circuit breaker — skipping cycle #{cycle_num} (letting EverOS recalibrate)")
        send(f"⚡ *Circuit Breaker* — Cycle {cycle_num} skipped after 2 consecutive losses. EverOS recalibrating.")
        return None

    print(f"\n[Agora] {mode_tag} Running Meta cycle #{cycle_num}...")

    result   = engine.run_cycle()
    strategy = result["strategy_selected"]
    signals  = result["signals"]

    print(f"[Agora] {len(signals)} signals generated")

    if not signals:
        print("[Agora] No signals this cycle.")
        return None

    # Filter blacklisted
    clean_signals = [s for s in signals if not is_blacklisted(s["asset"])]
    if len(signals) != len(clean_signals):
        print(f"[Agora] 🚫 {len(signals)-len(clean_signals)} blacklisted signal(s) dropped")

    # Confidence gate
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))
    eligible = [s for s in clean_signals if s["confidence"] >= MIN_CONFIDENCE]

    if not eligible:
        print("[Agora] Cycle complete — 0 trades executed (confidence gate)")
        return None

    top        = eligible[0]
    asset      = top["asset"]
    action     = top["action"]
    confidence = top["confidence"]
    asset_type = top["type"]

    # ── Execute primary trade ──────────────────────────────────────────────
    if simulate:
        import random
        base_pnl = round(random.uniform(0.5, 5.0), 4) if random.random() < confidence else round(-random.uniform(0.5, 3.0), 4)
        # v2.1: scale by confidence
        pnl = confidence_scale(base_pnl, confidence)
    else:
        pnl = ccxt_execute(asset, action, asset_type, confidence)

    total_pnl = log_trade(asset, asset_type, action, 1.0, pnl, strategy)
    record_trade(strategy, asset, pnl, confidence)
    record_signal_pattern(
        {"asset_type": asset_type, "action": action,
         "confidence_bucket": "high" if confidence >= 0.7 else "mid",
         "strategy": strategy},
        strategy, pnl
    )
    trade_alert(asset, action, pnl, total_pnl, strategy, simulate)

    outcome = "WIN ✅" if pnl > 0 else "LOSS ❌"
    print(f"[Agora] {outcome} | {action} {asset} | conf={confidence} | P&L: ${pnl:+.4f} | War Chest: ${total_pnl:+.4f}")

    # ── v2.1: Track consecutive losses ────────────────────────────────────
    if pnl < 0:
        _consecutive_losses += 1
        if _consecutive_losses >= CIRCUIT_BREAKER_LIMIT:
            _skip_next_cycle = True
            _consecutive_losses = 0
            print(f"[Agora] ⚡ {CIRCUIT_BREAKER_LIMIT} consecutive losses — circuit breaker ARMED for next cycle")
    else:
        _consecutive_losses = 0  # reset on any win

    # ── v2.1: Diversification nudge ───────────────────────────────────────
    second = maybe_diversify(eligible, top)
    if second:
        asset2      = second["asset"]
        action2     = second["action"]
        confidence2 = second["confidence"]
        type2       = second["type"]

        if simulate:
            import random
            base2 = round(random.uniform(0.5, 5.0), 4) if random.random() < confidence2 else round(-random.uniform(0.5, 3.0), 4)
            pnl2  = confidence_scale(base2, confidence2)
        else:
            pnl2 = ccxt_execute(asset2, action2, type2, confidence2)

        total_pnl = log_trade(asset2, type2, action2, 1.0, pnl2, strategy, notes="diversification")
        record_trade(strategy, asset2, pnl2, confidence2)
        outcome2 = "WIN ✅" if pnl2 > 0 else "LOSS ❌"
        print(f"[Agora] DIVERSIFY {outcome2} | {action2} {asset2} | conf={confidence2} | P&L: ${pnl2:+.4f} | War Chest: ${total_pnl:+.4f}")
        trade_alert(asset2, action2, pnl2, total_pnl, strategy + "+div", simulate)

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine v2.1")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")
    print(f"[Agora] v2.1 upgrades: confidence scaling ✅ | circuit breaker ✅ | diversification nudge ✅")

    run_relay_thread()
    startup_message(simulate)

    engine      = MetaStrategy()
    cycle_count = 0

    while True:
        try:
            cycle_count += 1
            run_cycle(engine, simulate, cycle_count)

            if cycle_count % REFLECT_EVERY == 0:
                reflect(cycle_count)

            if cycle_count % 12 == 0:
                summary     = get_summary()
                mem_summary = get_memory_summary()
                heartbeat(summary, simulate)
                weights   = mem_summary["strategy_weights"]
                blacklist = mem_summary["blacklist"]
                bl_str    = ", ".join(blacklist) if blacklist else "None"
                send(
                    f"*🧠 EverOS Memory Report — Cycle {cycle_count}*\n"
                    f"Strategy weights: `{weights}`\n"
                    f"Blacklist: `{bl_str}`\n"
                    f"Lessons: `{mem_summary['lesson_count']}`\n"
                    f"Last insight: _{mem_summary['last_lesson']}_"
                )

            if args.once:
                print("[Agora] --once flag. Exiting.")
                break

            print(f"[Agora] Sleeping {CYCLE_INTERVAL}s...")
            time.sleep(CYCLE_INTERVAL)

        except KeyboardInterrupt:
            summary     = get_summary()
            mem_summary = get_memory_summary()
            add_lesson(f"[SHUTDOWN @ cycle {cycle_count}] War Chest: ${summary['total_pnl']:+.4f} | Trades: {summary['total_trades']}")
            send(
                f"*🏛️ OpenAgora OFFLINE*\n"
                f"Final War Chest: `${summary['total_pnl']:+.4f}`\n"
                f"Total Trades: `{summary['total_trades']}`\n"
                f"Lessons banked: `{mem_summary['lesson_count']}`\n"
                f"_The Agora will return._ 🔱"
            )
            break
        except Exception as e:
            print(f"[Agora] Error: {e}")
            send(f"⚠️ *OpenAgora Error*\n`{str(e)}`")
            time.sleep(30)


if __name__ == "__main__":
    main()
