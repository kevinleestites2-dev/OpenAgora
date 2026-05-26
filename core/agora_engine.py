"""
OpenAgora — The Meta Trading Engine
Stocks + Crypto + Prediction Markets | Self-Evolving | Risk-Protected

Enhanced with:
- Full risk management (stop loss, drawdown kill switch, position sizing)
- Remote Telegram kill switch (/kill /start /status)
- Yahoo Finance (free stock data, no key needed)
- Crash recovery loop
- Heartbeat every hour
- Nexus Relay reporting (ZapiaPrime status checks)

Usage:
  python core/agora_engine.py --mode simulate
  python core/agora_engine.py --mode live
  python core/agora_engine.py --once
"""

import os
import sys
import time
import argparse
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.market_feed import MarketFeed
from core.war_chest import log_trade, get_summary, get_kill_switch_status
from core.risk_manager import pre_trade_check
from strategies.meta_strategy import MetaStrategy
from memory.everos_bridge import record_trade, get_strategy_weights, get_top_assets
from reporting.telegram_bot import (
    startup_message, trade_alert, heartbeat,
    send, crash_alert, kill_switch_alert, check_commands
)
from reporting.agora_relay import start_relay, update_state

SIMULATE = os.getenv("SIMULATE_MODE", "true").lower() == "true"
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "300"))  # 5 minutes


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║     The Meta Trading Engine — Pantheon v2.0      ║
║  Risk-Protected | Self-Evolving | Always Watching ║
╚══════════════════════════════════════════════════╝
""")


def run_cycle(engine: MetaStrategy, simulate: bool):
    """Execute one full Meta trading cycle with full risk checks"""
    print(f"\n[Agora] {'[SIMULATE]' if simulate else '[LIVE]'} Running Meta cycle...")

    # Kill switch check FIRST — before any market calls
    kill = get_kill_switch_status()
    if kill["triggered"]:
        kill_switch_alert(kill["reason"])
        print(f"[Agora] ⛔ Kill switch active: {kill['reason']} — skipping cycle")
        return

    result = engine.run_cycle()

    if "error" in result:
        print(f"[Agora] Cycle error: {result['error']}")
        return

    signals = result.get("signals", [])

    # ─── OpenStock Layer — merge stock signals ─────────────────
    try:
        from core.openstock_layer import generate_stock_signals, get_watchlist_snapshot, check_alerts, get_watchlist_prices
        from reporting.telegram_bot import send as tg_send
        stock_snapshot = get_watchlist_snapshot()
        stock_signals = generate_stock_signals(stock_snapshot)
        # Check price alerts and fire Telegram notifications
        prices = {sym: d["price"] for sym, d in stock_snapshot.items() if d.get("price", 0) > 0}
        triggered_alerts = check_alerts(prices)
        for alert in triggered_alerts:
            tg_send(
                f"🚨 *Price Alert Triggered*\n"
                f"`{alert['symbol']}` crossed `${alert['targetPrice']:.2f}` "
                f"({alert['condition']})\nCurrent: `${alert['currentPrice']:.2f}`"
            )
        if stock_signals:
            signals.extend(stock_signals)
            print(f"[OpenStock] +{len(stock_signals)} stock signals merged")
    except Exception as e:
        print(f"[OpenStock] Layer error (non-fatal): {e}")
    # ──────────────────────────────────────────────────────────

    print(f"[Agora] {len(signals)} signals generated (crypto + stock)")

    # Update relay with current strategy info
    active_strats = list(set([s.get("source", "meta") for s in signals if s.get("action") != "HOLD"]))
    update_state(
        active_strategies=active_strats,
        regime=result.get("training_state", "UNKNOWN")
    )

    trades_executed = 0
    for signal in signals[:3]:  # Max 3 trades per cycle
        # Risk check EVERY trade — no exceptions
        risk = pre_trade_check(signal)

        if not risk["approved"]:
            print(f"[Agora] ❌ Trade blocked: {risk['reason']}")
            continue

        asset = signal.get("asset", "UNKNOWN")
        action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0)
        position_size = risk["position_size"]

        if action == "HOLD":
            continue

        print(f"[Agora] ✅ Trade approved — {action} {asset} | size=${position_size} | conf={confidence:.2f}")

        if simulate:
            import random
            pnl = random.uniform(-position_size * 0.05, position_size * 0.08)
        else:
            # Live execution placeholder — wire Alpaca/Binance here
            pnl = 0.0

        strategy = result.get("strategy_selected", "meta")
        log_trade(asset, signal.get("asset_type", "unknown"), action, position_size, pnl, strategy)
        record_trade(strategy, asset, pnl)

        if abs(pnl) > 0.01:
            trade_alert(asset, action, pnl, confidence, simulate)

        trades_executed += 1

    print(f"[Agora] Cycle complete — {trades_executed} trades executed")


def main():
    print_banner()

    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    simulate = args.mode == "simulate" or SIMULATE
    if not simulate:
        print("[Agora] ⚠️  LIVE MODE — real capital at risk")

    engine = MetaStrategy()
    cycle_count = 0
    remote_kill = False

    startup_message(simulate)

    # Start Nexus Relay reporter — ZapiaPrime can check status anytime
    start_relay()
    update_state(mode="simulate" if simulate else "live")

    while True:
        try:
            # Check Telegram commands every cycle
            cmd = check_commands()
            if cmd:
                if cmd.get("command") == "kill":
                    remote_kill = True
                    update_state(remote_kill=True)
                    send("⛔ *KILL COMMAND RECEIVED*\nTrading HALTED. Send /start to resume.")
                    print("[Agora] ⛔ Remote kill received")
                elif cmd.get("command") == "start":
                    remote_kill = False
                    update_state(remote_kill=False)
                    send("▶️ *START COMMAND RECEIVED*\nTrading resumed.")
                    print("[Agora] ▶ Remote start received")
                elif cmd.get("command") == "status":
                    summary = get_summary()
                    send(
                        f"📊 *OpenAgora Status*\n"
                        f"Mode: `{'SIMULATE' if simulate else 'LIVE'}`\n"
                        f"Cycles: `{cycle_count}`\n"
                        f"War Chest P&L: `${summary['total_pnl']:+.4f}`\n"
                        f"Trades: `{summary['total_trades']}` | Win Rate: `{summary['win_rate']}%`\n"
                        f"Kill Switch: `{'ACTIVE' if remote_kill else 'OFF'}`"
                    )

            if remote_kill:
                print("[Agora] ⛔ Remote killed — skipping cycle...")
                time.sleep(CYCLE_INTERVAL)
                continue

            run_cycle(engine, simulate)
            cycle_count += 1
            update_state(cycle_count=cycle_count)

            # Heartbeat every 12 cycles (~1 hour)
            if cycle_count % 12 == 0:
                summary = get_summary()
                heartbeat(summary, simulate)
                weights = get_strategy_weights()
                top_assets = get_top_assets(3)
                print(f"[Agora] Strategy weights: {weights}")
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
                f"_The Agora never closes._ 🔱"
            )
            break
        except Exception as e:
            print(f"[Agora] Error: {e}")
            crash_alert(str(e))
            print("[Agora] Recovering in 30s...")
            time.sleep(30)


if __name__ == "__main__":
    main()
