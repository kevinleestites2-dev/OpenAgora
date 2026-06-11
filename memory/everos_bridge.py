"""
OpenAgora — EverOS Memory Bridge v2.0
Self-Evolving Meta Brain. Learns from every trade, every signal, every cycle.

Upgrades over v1:
  - Recency-weighted strategy scores (recent wins > old wins)
  - Confidence calibration (tracks predicted vs actual outcomes)
  - Asset blacklist (auto-bans chronic losers)
  - Signal pattern memory (market conditions → outcome mapping)
  - Structured reflection engine (auto-writes lessons every N cycles)
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

# ── Fable 5 Brain (injected 2026-06-10) ──────────────────────────────────────
_OR_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
_OR_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-fable-5")

def _fable5(prompt: str, max_tokens: int = 200) -> str:
    if not _OR_KEY:
        return None
    try:
        payload = json.dumps({
            "model": _OR_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {_OR_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/kevinleestites2-dev",
                "X-Title": "OpenAgora-EverOS"
            }, method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None


MEMORY_PATH = "memory/trade_memory.json"
MAX_LESSONS = 200       # cap lesson log to avoid bloat
BLACKLIST_THRESHOLD = -10.0   # auto-ban asset if PnL drops below this
DECAY_FACTOR = 0.92     # older trades count 8% less per batch of 10 trades


# ─────────────────────────────────────────
#  Internal I/O
# ─────────────────────────────────────────

def _load():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    return {
        "version": "2.0",
        "created": _now(),
        "strategy_stats": {},
        "asset_performance": {},
        "blacklist": [],
        "confidence_calibration": {},
        "signal_patterns": [],
        "lessons": [],
        "cycle_count": 0
    }


def _save(data):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _now():
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────
#  Core Trade Recording
# ─────────────────────────────────────────

def record_trade(strategy: str, asset: str, pnl: float, confidence: float = 0.5):
    """
    Record trade result. The Meta brain learns on every call.
    - Updates strategy stats with recency decay
    - Updates asset performance
    - Checks blacklist threshold
    - Updates confidence calibration
    """
    mem = _load()

    # ── Strategy stats (with recency decay) ──
    if strategy not in mem["strategy_stats"]:
        mem["strategy_stats"][strategy] = {
            "wins": 0, "losses": 0,
            "total_pnl": 0.0,
            "weighted_score": 1.0,
            "trade_history": []
        }
    s = mem["strategy_stats"][strategy]
    # ── Migration guard: heal any record missing v3.0 keys ──
    s.setdefault("losses", 0)
    s.setdefault("trade_history", [])
    s["total_pnl"] = round(s["total_pnl"] + pnl, 4)
    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1

    # Append to rolling history (cap at 20)
    s["trade_history"].append({"pnl": pnl, "ts": _now()})
    if len(s["trade_history"]) > 20:
        s["trade_history"].pop(0)

    # Recompute weighted score using decay
    score = 0.0
    for i, t in enumerate(reversed(s["trade_history"])):
        weight = DECAY_FACTOR ** i
        score += (1.0 if t["pnl"] > 0 else -0.5) * weight
    s["weighted_score"] = round(score, 4)

    # ── Asset performance ──
    if asset not in mem["asset_performance"]:
        mem["asset_performance"][asset] = {"trades": 0, "total_pnl": 0.0, "streak": 0}
    a = mem["asset_performance"][asset]
    a["trades"] += 1
    a["total_pnl"] = round(a["total_pnl"] + pnl, 4)
    if pnl > 0:
        a["streak"] = max(1, a.get("streak", 0) + 1)
    else:
        a["streak"] = min(-1, a.get("streak", 0) - 1)

    # ── Auto-blacklist chronic losers ──
    if a["total_pnl"] < BLACKLIST_THRESHOLD and asset not in mem["blacklist"]:
        mem["blacklist"].append(asset)
        add_lesson(f"AUTO-BLACKLISTED: {asset} | Total PnL: ${a['total_pnl']:.2f} breached threshold ${BLACKLIST_THRESHOLD}", mem)
        print(f"[EverOS] BLACKLISTED: {asset} (PnL: ${a['total_pnl']:.2f})")

    # ── Confidence calibration ──
    if strategy not in mem["confidence_calibration"]:
        mem["confidence_calibration"][strategy] = {
            "predicted_wins": 0.0, "actual_wins": 0, "total": 0
        }
    cal = mem["confidence_calibration"][strategy]
    cal["predicted_wins"] = round(cal["predicted_wins"] + confidence, 4)
    cal["actual_wins"] += 1 if pnl > 0 else 0
    cal["total"] += 1

    mem["cycle_count"] = mem.get("cycle_count", 0) + 1

    _save(mem)


# ─────────────────────────────────────────
#  Strategy Weight Engine
# ─────────────────────────────────────────

def get_strategy_weights() -> dict:
    """
    Compute dynamic strategy weights.
    Uses recency-decayed weighted_score — recent wins dominate.
    Floors at 0.05 so no strategy is fully abandoned.

    v3.1: Baseline entries for all known strategies so EverOS always
    has alternatives to rotate to — even before a strategy has been traded.
    New strategies start at a neutral 0.5 weighted_score (below the +2.0
    offset baseline, so they rank below any strategy with real trade history).
    """
    _KNOWN_STRATEGIES = ["mean_reversion", "momentum", "trend_follow", "arbitrage"]
    _BASELINE_SCORE   = 0.5   # neutral — below a strategy with wins, above one bleeding

    mem = _load()
    stats = mem["strategy_stats"]

    # Seed missing strategies with baseline so they always appear in weights
    seeded = False
    for strat in _KNOWN_STRATEGIES:
        if strat not in stats:
            stats[strat] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "weighted_score": _BASELINE_SCORE,
                "trade_history": [],
            }
            seeded = True
    if seeded:
        _save(mem)

    weights = {}
    for strategy, data in stats.items():
        raw_score = data.get("weighted_score", _BASELINE_SCORE)
        weights[strategy] = max(0.05, raw_score + 2.0)

    total = sum(weights.values())
    return {k: round(v / total, 4) for k, v in weights.items()}


# ─────────────────────────────────────────
#  Signal Pattern Memory
# ─────────────────────────────────────────

def record_signal_pattern(conditions: dict, strategy: str = "unknown", pnl: float = 0.0):
    """
    Remember what market conditions produced this outcome.
    conditions = {asset_type, action, confidence_bucket, market_regime}
    """
    mem = _load()
    
    # Handle cases where only one arg (a dict) was passed
    if isinstance(conditions, dict) and strategy == "unknown" and pnl == 0.0:
        if "strategy" in conditions and "pnl" in conditions:
            # It was likely passed as a single object
            strategy = conditions.get("strategy", "unknown")
            pnl = conditions.get("pnl", 0.0)
            conditions = conditions.get("conditions", conditions)

    pattern = {
        "ts": _now(),
        "conditions": conditions,
        "strategy": strategy,
        "outcome": "WIN" if pnl > 0 else "LOSS",
        "pnl": round(pnl, 4)
    }
    mem["signal_patterns"].append(pattern)
    if len(mem["signal_patterns"]) > 100:
        mem["signal_patterns"].pop(0)
    _save(mem)


def get_best_conditions() -> list:
    """Return the top 3 winning signal patterns"""
    mem = _load()
    wins = [p for p in mem["signal_patterns"] if p["outcome"] == "WIN"]
    wins.sort(key=lambda x: x["pnl"], reverse=True)
    return wins[:3]


# ─────────────────────────────────────────
#  Blacklist
# ─────────────────────────────────────────

def is_blacklisted(asset: str) -> bool:
    mem = _load()
    return asset in mem.get("blacklist", [])


def get_blacklist() -> list:
    mem = _load()
    return mem.get("blacklist", [])


# ─────────────────────────────────────────
#  Confidence Calibration Report
# ─────────────────────────────────────────

def get_calibration_report() -> dict:
    """
    For each strategy: how accurate was the confidence score?
    Returns calibration error (lower = better calibrated).
    """
    mem = _load()
    report = {}
    for strategy, cal in mem.get("confidence_calibration", {}).items():
        if cal["total"] == 0:
            continue
        predicted_rate = cal["predicted_wins"] / cal["total"]
        actual_rate = cal["actual_wins"] / cal["total"]
        error = round(abs(predicted_rate - actual_rate), 4)
        report[strategy] = {
            "predicted_win_rate": round(predicted_rate, 4),
            "actual_win_rate": round(actual_rate, 4),
            "calibration_error": error
        }
    return report


# ─────────────────────────────────────────
#  Lessons & Reflection
# ─────────────────────────────────────────

def add_lesson(lesson: str, mem: dict = None):
    """Record a Meta insight"""
    save_after = mem is None
    if mem is None:
        mem = _load()
    mem["lessons"].append({
        "ts": _now(),
        "lesson": lesson
    })
    if len(mem["lessons"]) > MAX_LESSONS:
        mem["lessons"] = mem["lessons"][-MAX_LESSONS:]
    if save_after:
        _save(mem)


def reflect(cycle: int):
    """
    Auto-reflection engine — called every N cycles.
    Writes a structured lesson summarizing current state.
    """
    mem = _load()
    stats = mem["strategy_stats"]
    if not stats:
        return

    best = max(stats.items(), key=lambda x: x[1].get("weighted_score", 0))
    worst = min(stats.items(), key=lambda x: x[1].get("weighted_score", 0))

    assets = mem["asset_performance"]
    if assets:
        top_asset = max(assets.items(), key=lambda x: x[1]["total_pnl"])
        asset_note = f"Top asset: {top_asset[0]} (${top_asset[1]['total_pnl']:+.2f})"
    else:
        asset_note = "No asset data yet"

    bl = mem.get("blacklist", [])
    bl_note = f"Blacklisted: {', '.join(bl)}" if bl else "No blacklisted assets"

    cal_report = get_calibration_report()
    if cal_report:
        cal_note = " | ".join([
            f"{s}: err={v['calibration_error']:.3f}" for s, v in cal_report.items()
        ])
    else:
        cal_note = "No calibration data yet"

    lesson = (
        f"[REFLECTION @ cycle {cycle}] "
        f"Best strategy: {best[0]} (score={best[1].get('weighted_score', 0):.3f}) | "
        f"Worst: {worst[0]} (score={worst[1].get('weighted_score', 0):.3f}) | "
        f"{asset_note} | {bl_note} | Calibration: {cal_note}"
    )

    # ── Fable 5 Strategic Insight ────────────────────────────────────────────
    fable_prompt = (
        "You are OpenAgora, a self-evolving trading engine. Cycle "
        + str(cycle) + " reflection:\n"
        "Best strategy: " + best[0]
        + " (score=" + str(round(best[1].get("weighted_score", 0), 3)) + ")\n"
        "Worst strategy: " + worst[0]
        + " (score=" + str(round(worst[1].get("weighted_score", 0), 3)) + ")\n"
        + asset_note + " | " + bl_note + "\n"
        "Calibration: " + cal_note + "\n"
        "In 2 sentences: what should change in strategy selection next cycle? Be specific."
    )
    fable_insight = _fable5(fable_prompt, max_tokens=120)
    if fable_insight:
        lesson += " | Fable5: " + fable_insight

    # ── Fable 5 Strategic Insight ────────────────────────────────────────────
    fable_prompt = (
        f"You are OpenAgora, a self-evolving trading engine. Cycle {cycle} reflection:\n"
        f"Best strategy: {best[0]} (score={best[1].get('weighted_score',0):.3f})\n"
        f"Worst strategy: {worst[0]} (score={worst[1].get('weighted_score',0):.3f})\n"
        f"{asset_note} | {bl_note}\n"
        f"Calibration: {cal_note}\n"
        f"In 2 sentences: what should change in strategy selection next cycle? Be specific."
    )
    fable_insight = _fable5(fable_prompt, max_tokens=120)
    if fable_insight:
        lesson += f" | Fable5: {fable_insight}"

    add_lesson(lesson)
    print(f"[EverOS] Reflection written at cycle {cycle}")
    print(f"[EverOS] {lesson}")


# ─────────────────────────────────────────
#  Reporting Helpers
# ─────────────────────────────────────────

def get_top_assets(n: int = 3) -> list:
    mem = _load()
    assets = mem["asset_performance"]
    sorted_assets = sorted(assets.items(), key=lambda x: x[1]["total_pnl"], reverse=True)
    return sorted_assets[:n]


def get_memory_summary() -> dict:
    """Full state snapshot for Telegram heartbeat"""
    mem = _load()
    weights = get_strategy_weights()
    top_assets = get_top_assets(3)
    cal = get_calibration_report()
    return {
        "cycle_count": mem.get("cycle_count", 0),
        "strategy_weights": weights,
        "top_assets": top_assets,
        "blacklist": mem.get("blacklist", []),
        "calibration": cal,
        "lesson_count": len(mem.get("lessons", [])),
        "last_lesson": mem["lessons"][-1]["lesson"] if mem.get("lessons") else "None"
    }

