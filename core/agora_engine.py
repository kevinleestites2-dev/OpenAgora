"""
OpenAgora — The Meta Trading Engine v2.0
Stocks + Crypto + Prediction Markets | Self-Evolving | MidasPrime Powered

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

SIMULATE = os.getenv("SIMULATE_MODE", "true").lower() == "true"
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "300"))  # 5 min default
REFLECT_EVERY = 10


# ─── CCXT LIVE EXECUTOR ───────────────────────────────────────────────────────
def ccxt_execute(asset: str, action: str, asset_type: str) -> float:
    """
    Execute a real trade via CCXT.
    Returns PnL estimate (entry price - fill price delta).
    Supports crypto pairs. Prediction markets routed separately.
    """
    import ccxt

    # Map asset name to CCXT symbol
    COIN_MAP = {
        "bitcoin": "BTC/USDT",
        "ethereum": "ETH/USDT",
        "solana": "SOL/USDT",
        "polygon": "MATIC/USDT",
        "chainlink": "LINK/USDT",
        "cardano": "ADA/USDT",
        "avalanche-2": "AVAX/USDT",
        "dot": "DOT/USDT",
    }

    EXCHANGE_ID = os.getenv("CCXT_EXCHANGE", "binance")
    API_KEY     = os.getenv(f"{EXCHANGE_ID.upper()}_API_KEY", "")
    API_SECRET  = os.getenv(f"{EXCHANGE_ID.upper()}_API_SECRET", "")
    TRADE_SIZE  = float(os.getenv("TRADE_SIZE_USD", "10"))  # default $10 per trade

    if not API_KEY or not API_SECRET:
        print(f"[CCXT] No keys for {EXCHANGE_ID} — add {EXCHANGE_ID.upper()}_API_KEY to .env")
        return 0.0

    try:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        exchange = exchange_class({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
        })

        symbol = COIN_MAP.get(asset.lower())
        if not symbol:
            # Try direct (e.g. signal already formatted as BTC/USDT)
            symbol = asset if "/" in asset else f"{asset.upper()}/USDT"

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price  = ticker["last"]
        amount = TRADE_SIZE / price  # units to buy/sell

        side = "buy" if action == "BUY" else "sell"

        print(f"[CCXT] LIVE {side.upper()} {symbol} @ ${price:.4f} | size=${TRADE_SIZE} | units={amount:.6f}")

        order = exchange.create_market_order(symbol, side, amount)

        fill_price = order.get("average") or order.get("price") or price
        fee        = order.get("fee", {}).get("cost", 0) or 0
        pnl        = (fill_price - price) * amount if side == "buy" else (price - fill_price) * amount
        pnl        = round(pnl - fee, 6)

        print(f"[CCXT] Order filled | fill={fill_price} | fee={fee} | pnl={pnl:+.6f}")
        send(
            f"🔴 *LIVE TRADE EXECUTED*\n"
            f"Exchange: `{EXCHANGE_ID}`\n"
            f"Pair: `{symbol}`\n"
            f"Side: `{side.upper()}`\n"
            f"Price: `${fill_price:.4f}`\n"
            f"Size: `${TRADE_SIZE}`\n"
            f"Fee: `${fee:.4f}`\n"
            f"PnL: `${pnl:+.6f}`"
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
        print(f"[CCXT] Execution error: {e}")
        send(f"⚠️ *CCXT Error*\n`{str(e)[:200]}`")
        return 0.0
# ─────────────────────────────────────────────────────────────────────────────


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║     The Meta Trading Engine — Pantheon v2.0      ║
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
    """Execute one full Meta trading cycle"""
    mode_tag = "[SIMULATE]" if simulate else "[LIVE]"
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

    # ── Execute ──
    if simulate:
        import random
        pnl = round(random.uniform(0.5, 5.0) * confidence, 4) if random.random() < confidence else round(-random.uniform(0.5, 3.0), 4)
    else:
        # LIVE — CCXT execution
        pnl = ccxt_execute(asset, action, asset_type)

    # Log + memory
    total_pnl = log_trade(asset, asset_type, action, 1.0, pnl, strategy)
    record_trade(strategy, asset, pnl, confidence)
    record_signal_pattern({"asset_type": asset_type, "action": action, "confidence_bucket": "high" if confidence >= 0.7 else "mid", "strategy": strategy}, strategy, pnl)

    trade_alert(asset, action, pnl, total_pnl, strategy, simulate)

    outcome = "WIN ✅" if pnl > 0 else "LOSS ❌"
    print(f"[Agora] {outcome} | {action} {asset} | conf={confidence} | P&L: ${pnl:+.4f} | War Chest: ${total_pnl:+.4f}")

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine v2.0")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")

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
                weights    = mem_summary["strategy_weights"]
                blacklist  = mem_summary["blacklist"]
                bl_str     = ", ".join(blacklist) if blacklist else "None"
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
