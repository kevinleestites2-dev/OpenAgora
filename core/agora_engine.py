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
REFLECT_EVERY = 10   # write a reflection lesson every N cycles


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

    RELAY_URL = os.getenv("NEXUS_RELAY_URL", "")
    RELAY_SECRET = os.getenv("RELAY_SECRET", "pantheon_prime")

    if not RELAY_URL:
        return  # Relay not configured — skip silently

    def _push():
        trade_count = 0
        total_pnl = 0.0
        while True:
            try:
                summary = get_summary()
                trade_count = summary.get("total_trades", 0)
                total_pnl = summary.get("total_pnl", 0.0)
                requests.post(
                    f"{RELAY_URL}/command",
                    json={"type": "status", "trades": trade_count, "pnl": total_pnl},
                    headers={"X-Secret": RELAY_SECRET},
                    timeout=5
                )
                print(f"[AGORA-RELAY] Pushed | Trades: {trade_count} | PnL: +{total_pnl:.4f}")
            except Exception:
                pass
            time.sleep(60)

    t = threading.Thread(target=_push, daemon=True)
    t.start()


def run_cycle(engine: MetaStrategy, simulate: bool, cycle_num: int):
    """Execute one full Meta trading cycle with EverOS v2 memory hooks"""
    mode_tag = "[SIMULATE]" if simulate else "[LIVE]"
    print(f"\n[Agora] {mode_tag} Running Meta cycle #{cycle_num}...")

    result = engine.run_cycle()
    strategy = result["strategy_selected"]
    signals = result["signals"]

    print(f"[Agora] {len(signals)} signals generated (crypto + stock)")

    if not signals:
        print("[Agora] No signals this cycle.")
        return None

    # ── Filter blacklisted assets ──
    clean_signals = [s for s in signals if not is_blacklisted(s["asset"])]
    blocked_bl = len(signals) - len(clean_signals)
    if blocked_bl:
        print(f"[Agora] 🚫 {blocked_bl} signal(s) blocked — blacklisted assets")

    # ── Confidence gate ──
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))
    eligible = [s for s in clean_signals if s["confidence"] >= MIN_CONFIDENCE]
    blocked_conf = len(clean_signals) - len(eligible)
    for s in clean_signals:
        if s["confidence"] < MIN_CONFIDENCE:
            print(f"[Agora] ❌ Trade blocked: Low confidence: {s['confidence']} < {MIN_CONFIDENCE}")

    if not eligible:
        print("[Agora] Cycle complete — 0 trades executed")
        return None

    # ── Execute top signal ──
    top = eligible[0]
    asset = top["asset"]
    action = top["action"]
    confidence = top["confidence"]
    asset_type = top["type"]

    import random
    if simulate:
        if random.random() < confidence:
            pnl = round(random.uniform(0.5, 5.0) * confidence, 4)
        else:
            pnl = round(-random.uniform(0.5, 3.0), 4)
    else:
        pnl = 0.0
        print("[Agora] LIVE execution not yet wired — set SIMULATE_MODE=false when ready")

    # ── Log to War Chest ──
    total_pnl = log_trade(asset, asset_type, action, 1.0, pnl, strategy)

    # ── EverOS v2: record trade with confidence + signal pattern ──
    record_trade(strategy, asset, pnl, confidence)

    conditions = {
        "asset_type": asset_type,
        "action": action,
        "confidence_bucket": "high" if confidence >= 0.7 else "mid",
        "strategy": strategy
    }
    record_signal_pattern(conditions, strategy, pnl)

    # ── Telegram alert ──
    trade_alert(asset, action, pnl, total_pnl, strategy, simulate)

    outcome = "WIN ✅" if pnl > 0 else "LOSS ❌"
    print(f"[Agora] {outcome} | {action} {asset} | conf={confidence} | P&L: ${pnl:+.4f} | War Chest: ${total_pnl:+.4f}")

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine v2.0")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")
    print(f"[Agora] Reflect every: {REFLECT_EVERY} cycles")

    run_relay_thread()
    startup_message(simulate)

    engine = MetaStrategy()
    cycle_count = 0

    while True:
        try:
            cycle_count += 1
            run_cycle(engine, simulate, cycle_count)

            # ── EverOS Reflection every N cycles ──
            if cycle_count % REFLECT_EVERY == 0:
                reflect(cycle_count)

            # ── Heartbeat every 12 cycles (~1 hour) ──
            if cycle_count % 12 == 0:
                summary = get_summary()
                heartbeat(summary, simulate)
                mem_summary = get_memory_summary()
                weights = mem_summary["strategy_weights"]
                top_assets = mem_summary["top_assets"]
                blacklist = mem_summary["blacklist"]
                print(f"[Agora] Strategy weights: {weights}")
                print(f"[Agora] Top assets: {top_assets}")
                if blacklist:
                    print(f"[Agora] Blacklisted: {blacklist}")
                print(f"[EverOS] Lessons logged: {mem_summary['lesson_count']}")
                print(f"[EverOS] Last lesson: {mem_summary['last_lesson']}")

                # Push memory summary to Telegram
                bl_str = ", ".join(blacklist) if blacklist else "None"
                send(
                    f"*🧠 EverOS Memory Report — Cycle {cycle_count}*\n"
                    f"Strategy weights: `{weights}`\n"
                    f"Blacklist: `{bl_str}`\n"
                    f"Lessons: `{mem_summary['lesson_count']}`\n"
                    f"Last insight: _{mem_summary['last_lesson']}_"
                )

            if args.once:
                print("[Agora] --once flag set. Exiting.")
                break

            print(f"[Agora] Sleeping {CYCLE_INTERVAL}s...")
            time.sleep(CYCLE_INTERVAL)

        except KeyboardInterrupt:
            print("\n[Agora] Shutdown signal received.")
            summary = get_summary()
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
