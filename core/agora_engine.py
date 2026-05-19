"""
OpenAgora — The Meta Trading Engine
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

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.market_feed import MarketFeed
from core.war_chest import log_trade, get_summary
from strategies.meta_strategy import MetaStrategy
from memory.everos_bridge import record_trade, get_strategy_weights, get_top_assets
from reporting.telegram_bot import startup_message, trade_alert, heartbeat, send

SIMULATE = os.getenv("SIMULATE_MODE", "true").lower() == "true"
CYCLE_INTERVAL = 300  # 5 minutes


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║     The Meta Trading Engine — Pantheon v1.0      ║
║   Stocks + Crypto + Predictions | Self-Evolving  ║
╚══════════════════════════════════════════════════╝
""")


def run_cycle(engine: MetaStrategy, simulate: bool):
    """Execute one full Meta trading cycle"""
    print(f"\n[Agora] {'[SIMULATE]' if simulate else '[LIVE]'} Running Meta cycle...")

    result = engine.run_cycle()
    strategy = result["strategy_selected"]
    signals = result["signals"]

    print(f"[Agora] Strategy selected: {strategy}")
    print(f"[Agora] Signals found: {len(signals)}")

    if not signals:
        print("[Agora] No signals this cycle.")
        return

    # Execute top signal
    top = signals[0]
    asset = top["asset"]
    action = top["action"]
    confidence = top["confidence"]
    asset_type = top["type"]

    # Simulate P&L (in live mode, replace with real execution)
    import random
    if simulate:
        # Simulate: confidence-weighted random outcome
        if random.random() < confidence:
            pnl = round(random.uniform(0.5, 5.0) * confidence, 4)
        else:
            pnl = round(-random.uniform(0.5, 3.0), 4)
    else:
        # TODO: Wire real execution here
        pnl = 0.0
        print("[Agora] LIVE execution not yet wired — set SIMULATE_MODE=false when ready")

    # Log to War Chest
    total_pnl = log_trade(asset, asset_type, action, 1.0, pnl, strategy)

    # Record to EverOS memory
    record_trade(strategy, asset, pnl)

    # Telegram alert
    trade_alert(asset, action, pnl, total_pnl, strategy, simulate)

    print(f"[Agora] Trade: {action} {asset} | P&L: ${pnl:+.4f} | War Chest: ${total_pnl:+.4f}")

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")

    startup_message(simulate)

    engine = MetaStrategy()
    cycle_count = 0

    while True:
        try:
            run_cycle(engine, simulate)
            cycle_count += 1

            # Heartbeat every 12 cycles (~1 hour)
            if cycle_count % 12 == 0:
                summary = get_summary()
                heartbeat(summary, simulate)
                weights = get_strategy_weights()
                print(f"[Agora] Strategy weights: {weights}")
                top_assets = get_top_assets(3)
                print(f"[Agora] Top assets: {top_assets}")

            if args.once:
                print("[Agora] --once flag set. Exiting.")
                break

            print(f"[Agora] Sleeping {CYCLE_INTERVAL}s...")
            time.sleep(CYCLE_INTERVAL)

        except KeyboardInterrupt:
            print("\n[Agora] Shutdown signal received.")
            summary = get_summary()
            send(
                f"*🏛️ OpenAgora OFFLINE*\n"
                f"Final War Chest: `${summary['total_pnl']:+.4f}`\n"
                f"Total Trades: `{summary['total_trades']}`\n"
                f"_The Agora will return._ 🔱"
            )
            break
        except Exception as e:
            print(f"[Agora] Error: {e}")
            send(f"⚠️ *OpenAgora Error*\n`{str(e)}`")
            time.sleep(30)


if __name__ == "__main__":
    main()
