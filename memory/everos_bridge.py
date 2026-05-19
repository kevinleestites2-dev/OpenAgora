"""
OpenAgora — EverOS Memory Bridge
Long-term trade memory — the Meta brain learns from every trade.
"""

import json
import os
from datetime import datetime


MEMORY_PATH = "memory/trade_memory.json"


def _load():
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r") as f:
            return json.load(f)
    return {
        "strategy_stats": {},
        "asset_performance": {},
        "lessons": [],
        "created": datetime.utcnow().isoformat()
    }


def _save(data):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w") as f:
        json.dump(data, f, indent=2)


def record_trade(strategy, asset, pnl):
    """Record trade result — Meta brain learns"""
    mem = _load()

    # Strategy stats
    if strategy not in mem["strategy_stats"]:
        mem["strategy_stats"][strategy] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
    s = mem["strategy_stats"][strategy]
    s["total_pnl"] = round(s["total_pnl"] + pnl, 4)
    if pnl > 0:
        s["wins"] += 1
    else:
        s["losses"] += 1

    # Asset performance
    if asset not in mem["asset_performance"]:
        mem["asset_performance"][asset] = {"trades": 0, "total_pnl": 0.0}
    a = mem["asset_performance"][asset]
    a["trades"] += 1
    a["total_pnl"] = round(a["total_pnl"] + pnl, 4)

    _save(mem)


def get_strategy_weights():
    """
    Meta Layer — compute dynamic strategy weights based on historical win rates.
    Better strategies get more capital allocation.
    """
    mem = _load()
    stats = mem["strategy_stats"]
    if not stats:
        return {}

    weights = {}
    for strategy, data in stats.items():
        total = data["wins"] + data["losses"]
        if total == 0:
            weights[strategy] = 1.0
        else:
            win_rate = data["wins"] / total
            # Weight = win_rate * pnl bonus (floor at 0.1)
            pnl_bonus = max(0, data["total_pnl"] / 100)
            weights[strategy] = max(0.1, win_rate + pnl_bonus)

    # Normalize
    total_weight = sum(weights.values())
    return {k: round(v / total_weight, 4) for k, v in weights.items()}


def add_lesson(lesson: str):
    """Record a Meta insight — the bot notes what it learned"""
    mem = _load()
    mem["lessons"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "lesson": lesson
    })
    _save(mem)


def get_top_assets(n=3):
    """Return top performing assets by total P&L"""
    mem = _load()
    assets = mem["asset_performance"]
    sorted_assets = sorted(assets.items(), key=lambda x: x[1]["total_pnl"], reverse=True)
    return sorted_assets[:n]
