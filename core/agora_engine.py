"""
OpenAgora — The Meta Trading Engine v3.0
Stocks + Crypto + Prediction Markets | Self-Evolving | MidasPrime Powered

v3.0 upgrades (surgical over v2.1):
  1. Strategy-Asset Combo Blacklist — 3 consecutive losses on same strategy+asset
     combo → that combo is banned for COMBO_COOLDOWN_CYCLES cycles. No more
     mean_reversion hammering the same losing asset over and over.
  2. Forced Strategy Rotation — after ROTATION_LOSS_LIMIT losses on the same
     strategy, the engine forces a switch to the next best strategy in EverOS.
  3. Smarter Circuit Breaker — instead of just skipping a cycle, the breaker now
     also forces strategy rotation before resuming. Skip + rotate, not just skip.
  4. Combo cooldown reporting — Telegram alerts when a combo is banned/unbanned.

All v2.1 logic preserved — confidence scaling, diversification nudge, relay thread.
"""

import os
import sys
import time
import argparse
from dotenv import load_dotenv
from collections import defaultdict

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
CYCLE_INTERVAL = int(os.getenv("CYCLE_INTERVAL", "300"))
REFLECT_EVERY  = 10

# ─── CIRCUIT BREAKER ──────────────────────────────────────────────────────────
_consecutive_losses   = 0
_skip_next_cycle      = False
CIRCUIT_BREAKER_LIMIT = int(os.getenv("CIRCUIT_BREAKER_LIMIT", "2"))

# ─── v3.0: COMBO BLACKLIST ────────────────────────────────────────────────────
# Tracks consecutive losses per (strategy, asset) combo
_combo_loss_streak    = defaultdict(int)   # (strategy, asset) -> consecutive losses
_combo_cooldown       = {}                 # (strategy, asset) -> cycle it was banned
COMBO_LOSS_LIMIT      = int(os.getenv("COMBO_LOSS_LIMIT", "3"))       # ban after 3 consecutive losses
COMBO_COOLDOWN_CYCLES = int(os.getenv("COMBO_COOLDOWN_CYCLES", "6"))  # banned for 6 cycles (~30 min at 5 min intervals)

# ─── v3.0: STRATEGY ROTATION ─────────────────────────────────────────────────
_strategy_loss_streak = defaultdict(int)   # strategy -> consecutive losses
ROTATION_LOSS_LIMIT   = int(os.getenv("ROTATION_LOSS_LIMIT", "4"))    # force rotation after 4 losses on same strategy
_forced_strategy      = None               # when set, overrides MetaStrategy selection


def _is_combo_banned(strategy: str, asset: str, current_cycle: int) -> bool:
    """Check if a strategy+asset combo is currently in cooldown."""
    key = (strategy, asset)
    if key not in _combo_cooldown:
        return False
    banned_at = _combo_cooldown[key]
    if current_cycle - banned_at > COMBO_COOLDOWN_CYCLES:
        # Cooldown expired — unban (ban covers banned_at+1 through banned_at+COOLDOWN inclusive)
        del _combo_cooldown[key]
        _combo_loss_streak[key] = 0
        send(
            f"🔓 *Combo Unbanned*\n"
            f"Strategy `{strategy}` + `{asset}` cooldown expired.\n"
            f"Re-entering rotation."
        )
        return False
    return True


def _record_combo_outcome(strategy: str, asset: str, pnl: float, current_cycle: int):
    """Update combo loss streak. Ban if threshold hit."""
    global _forced_strategy
    key = (strategy, asset)

    if pnl < 0:
        _combo_loss_streak[key] += 1
        _strategy_loss_streak[strategy] += 1

        # Ban the combo if it hits the limit
        if _combo_loss_streak[key] >= COMBO_LOSS_LIMIT:
            _combo_cooldown[key] = current_cycle
            send(
                f"🚫 *Combo Banned — v3.0*\n"
                f"Strategy `{strategy}` on `{asset}` banned for {COMBO_COOLDOWN_CYCLES} cycles.\n"
                f"Reason: {COMBO_LOSS_LIMIT} consecutive losses.\n"
                f"Rotating to next best strategy."
            )
            print(f"[Agora v3] COMBO BANNED: {strategy}+{asset} for {COMBO_COOLDOWN_CYCLES} cycles")

        # Force strategy rotation if the whole strategy is bleeding
        if _strategy_loss_streak[strategy] >= ROTATION_LOSS_LIMIT:
            weights = get_strategy_weights()
            # Pick the next best strategy that isn't the current one
            alternatives = sorted(
                [(s, w) for s, w in weights.items() if s != strategy],
                key=lambda x: x[1], reverse=True
            )
            if alternatives:
                _forced_strategy = alternatives[0][0]
                _strategy_loss_streak[strategy] = 0  # reset after rotation
                send(
                    f"🔄 *Strategy Rotation Forced — v3.0*\n"
                    f"`{strategy}` hit {ROTATION_LOSS_LIMIT} consecutive losses.\n"
                    f"Rotating to: `{_forced_strategy}` (EverOS top pick)"
                )
                print(f"[Agora v3] FORCED ROTATION: {strategy} → {_forced_strategy}")
    else:
        # Win — reset streaks
        _combo_loss_streak[key] = 0
        _strategy_loss_streak[strategy] = 0
        _forced_strategy = None  # rotation no longer needed


# ─── v2.1: CONFIDENCE SCALING ────────────────────────────────────────────────
def confidence_scale(base_pnl: float, confidence: float) -> float:
    if confidence >= 0.95:
        return base_pnl * 1.0
    elif confidence >= 0.85:
        return round(base_pnl * 0.75, 4)
    elif confidence >= 0.70:
        return round(base_pnl * 0.50, 4)
    else:
        return round(base_pnl * 0.30, 4)


# ─── v2.1: DIVERSIFICATION NUDGE ─────────────────────────────────────────────
def maybe_diversify(signals: list, top: dict, cycle_num: int, strategy: str) -> dict:
    if top["confidence"] < 1.0:
        return None
    others = [
        s for s in signals
        if s["asset"] != top["asset"]
        and not is_blacklisted(s["asset"])
        and not _is_combo_banned(strategy, s["asset"], cycle_num)
        and s["confidence"] >= 0.85
    ]
    return others[0] if others else None


# ─── CCXT LIVE EXECUTOR ───────────────────────────────────────────────────────
def ccxt_execute(asset: str, action: str, asset_type: str, confidence: float = 1.0) -> float:
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

    if confidence >= 0.95:
        trade_size = BASE_SIZE * 1.0
    elif confidence >= 0.85:
        trade_size = BASE_SIZE * 0.75
    elif confidence >= 0.70:
        trade_size = BASE_SIZE * 0.50
    else:
        trade_size = BASE_SIZE * 0.30

    if not API_KEY or not API_SECRET:
        print(f"[CCXT] No keys for {EXCHANGE_ID}")
        return 0.0

    try:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        exchange = exchange_class({
            "apiKey":          API_KEY,
            "secret":          API_SECRET,
            "enableRateLimit": True,
        })
        symbol     = COIN_MAP.get(asset.lower(), f"{asset.upper()}/USDT")
        ticker     = exchange.fetch_ticker(symbol)
        price      = ticker["last"]
        amount     = trade_size / price
        side       = "buy" if action == "BUY" else "sell"
        order      = exchange.create_market_order(symbol, side, amount)
        fill_price = order.get("average") or order.get("price") or price
        fee        = order.get("fee", {}).get("cost", 0) or 0
        pnl        = (fill_price - price) * amount if side == "buy" else (price - fill_price) * amount
        pnl        = round(pnl - fee, 6)
        send(
            f"🔴 *LIVE TRADE*\n"
            f"`{EXCHANGE_ID}` | `{symbol}` | `{side.upper()}`\n"
            f"Size: `${trade_size:.2f}` | Fill: `${fill_price:.4f}` | PnL: `${pnl:+.6f}`"
        )
        return pnl
    except Exception as e:
        print(f"[CCXT] Error: {e}")
        send(f"⚠️ *CCXT Error*\n`{str(e)[:200]}`")
        return 0.0


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║    The Meta Trading Engine — Pantheon v3.0       ║
║  Combo Blacklist | Strategy Rotation | Always On ║
╚══════════════════════════════════════════════════╝
""")


def run_relay_thread():
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
                    json={"type": "status",
                          "trades": summary.get("total_trades", 0),
                          "pnl": summary.get("total_pnl", 0.0)},
                    headers={"X-Secret": RELAY_SECRET},
                    timeout=5
                )
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=_push, daemon=True).start()


def run_cycle(engine: MetaStrategy, simulate: bool, cycle_num: int):
    """Execute one full Meta trading cycle — v3.0"""
    global _consecutive_losses, _skip_next_cycle, _forced_strategy

    mode_tag = "[SIMULATE]" if simulate else "[LIVE]"

    # ── v3.0: Circuit Breaker — skip + rotate ─────────────────────────────
    if _skip_next_cycle:
        _skip_next_cycle = False
        # Force rotation on resume if EverOS has alternatives
        weights = get_strategy_weights()
        if weights and _forced_strategy is None:
            best = max(weights.items(), key=lambda x: x[1])
            _forced_strategy = best[0]
        print(f"[Agora] ⚡ Circuit breaker — skipping cycle #{cycle_num}, rotating to {_forced_strategy}")
        send(
            f"⚡ *Circuit Breaker — Cycle {cycle_num} skipped*\n"
            f"Consecutive losses cleared. Rotating to `{_forced_strategy or 'auto'}`.\n"
            f"EverOS recalibrating."
        )
        return None

    print(f"\n[Agora] {mode_tag} Running Meta cycle #{cycle_num}...")

    result   = engine.run_cycle()
    signals  = result["signals"]

    # ── v3.0: Apply forced strategy if set ────────────────────────────────
    strategy = _forced_strategy if _forced_strategy else result["strategy_selected"]
    if _forced_strategy:
        print(f"[Agora v3] Using forced strategy: {_forced_strategy}")
        # ── v3.1: Combo ban check during forced cycles ────────────────────
        # Circuit breaker does NOT bypass the combo blacklist — filter here first
        signals = [
            s for s in signals
            if not _is_combo_banned(strategy, s["asset"], cycle_num)
        ]
        if not signals:
            print(f"[Agora v3] All signals combo-banned during forced cycle #{cycle_num}. Waiting.")
            send(
                f"⚠️ *Forced Cycle {cycle_num} — All combos banned*\n"
                f"Strategy `{strategy}` has no valid assets. Holding."
            )
            return None

    print(f"[Agora] Strategy: {strategy} | {len(signals)} signals")

    if not signals:
        print("[Agora] No signals this cycle.")
        return None

    # Filter EverOS blacklisted assets
    clean_signals = [s for s in signals if not is_blacklisted(s["asset"])]

    # ── v3.0: Filter combo-banned (strategy+asset) combos ─────────────────
    clean_signals = [
        s for s in clean_signals
        if not _is_combo_banned(strategy, s["asset"], cycle_num)
    ]

    if not clean_signals:
        print(f"[Agora v3] All signals combo-banned for strategy '{strategy}'. Skipping cycle.")
        send(
            f"⚠️ *All signals banned — Cycle {cycle_num}*\n"
            f"Strategy `{strategy}` has no valid assets this cycle.\n"
            f"Waiting for cooldowns to expire."
        )
        return None

    # Confidence gate
    MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))
    eligible = [s for s in clean_signals if s["confidence"] >= MIN_CONFIDENCE]

    if not eligible:
        print("[Agora] Cycle complete — 0 trades (confidence gate)")
        return None

    top        = eligible[0]
    asset      = top["asset"]
    action     = top["action"]
    confidence = top["confidence"]
    asset_type = top["type"]

    # ── Execute primary trade ──────────────────────────────────────────────
    if simulate:
        import random
        base_pnl = (round(random.uniform(0.5, 5.0), 4)
                    if random.random() < confidence
                    else round(-random.uniform(0.5, 3.0), 4))
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

    # ── v3.0: Update combo + strategy streaks ─────────────────────────────
    _record_combo_outcome(strategy, asset, pnl, cycle_num)

    # ── v2.1: Global consecutive loss tracker ─────────────────────────────
    if pnl < 0:
        _consecutive_losses += 1
        if _consecutive_losses >= CIRCUIT_BREAKER_LIMIT:
            _skip_next_cycle = True
            _consecutive_losses = 0
            print(f"[Agora] ⚡ {CIRCUIT_BREAKER_LIMIT} consecutive losses — circuit breaker ARMED")
    else:
        _consecutive_losses = 0

    # ── v2.1: Diversification nudge ───────────────────────────────────────
    second = maybe_diversify(eligible, top, cycle_num, strategy)
    if second:
        asset2      = second["asset"]
        action2     = second["action"]
        confidence2 = second["confidence"]
        type2       = second["type"]

        if simulate:
            import random
            base2 = (round(random.uniform(0.5, 5.0), 4)
                     if random.random() < confidence2
                     else round(-random.uniform(0.5, 3.0), 4))
            pnl2 = confidence_scale(base2, confidence2)
        else:
            pnl2 = ccxt_execute(asset2, action2, type2, confidence2)

        total_pnl = log_trade(asset2, type2, action2, 1.0, pnl2, strategy, notes="diversification")
        record_trade(strategy, asset2, pnl2, confidence2)
        _record_combo_outcome(strategy, asset2, pnl2, cycle_num)
        outcome2 = "WIN ✅" if pnl2 > 0 else "LOSS ❌"
        print(f"[Agora] DIVERSIFY {outcome2} | {action2} {asset2} | P&L: ${pnl2:+.4f}")
        trade_alert(asset2, action2, pnl2, total_pnl, strategy + "+div", simulate)

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine v3.0")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")
    print(f"[Agora] v3.0: combo blacklist (limit={COMBO_LOSS_LIMIT}, cooldown={COMBO_COOLDOWN_CYCLES} cycles) ✅")
    print(f"[Agora] v3.0: strategy rotation (limit={ROTATION_LOSS_LIMIT} losses) ✅")
    print(f"[Agora] v3.0: smarter circuit breaker (skip + rotate) ✅")

    run_relay_thread()
    startup_message(simulate)
    send(
        f"🏛️ *OpenAgora v3.0 ONLINE*\n"
        f"Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}\n"
        f"New: Combo Blacklist | Strategy Rotation | Smarter Breaker\n"
        f"Combo ban limit: {COMBO_LOSS_LIMIT} losses → {COMBO_COOLDOWN_CYCLES} cycle cooldown\n"
        f"Rotation trigger: {ROTATION_LOSS_LIMIT} consecutive strategy losses\n"
        f"_Mean reversion will never hammer the same asset again._"
    )

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
                # v3.0: report active combo bans
                active_bans = [f"{s}+{a}" for (s, a) in _combo_cooldown.keys()]
                ban_str = ", ".join(active_bans) if active_bans else "None"
                send(
                    f"*🧠 EverOS Memory — Cycle {cycle_count}*\n"
                    f"Strategy weights: `{weights}`\n"
                    f"Asset blacklist: `{bl_str}`\n"
                    f"Combo bans: `{ban_str}`\n"
                    f"Forced strategy: `{_forced_strategy or 'none'}`\n"
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
            add_lesson(
                f"[SHUTDOWN @ cycle {cycle_count}] "
                f"War Chest: ${summary['total_pnl']:+.4f} | "
                f"Trades: {summary['total_trades']}"
            )
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
