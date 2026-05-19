"""
OpenAgora — War Chest Bridge
MidasPrime integration — logs all P&L in real time
"""

import json
import os
from datetime import datetime


WAR_CHEST_PATH = os.getenv("WAR_CHEST_PATH", "logs/war_chest.json")


def _load():
    if os.path.exists(WAR_CHEST_PATH):
        with open(WAR_CHEST_PATH, "r") as f:
            return json.load(f)
    return {"total_pnl": 0.0, "trades": [], "last_updated": None}


def _save(data):
    os.makedirs(os.path.dirname(WAR_CHEST_PATH), exist_ok=True)
    with open(WAR_CHEST_PATH, "w") as f:
        json.dump(data, f, indent=2)


def log_trade(asset, asset_type, action, amount, pnl, strategy, notes=""):
    """Log a completed trade to the War Chest"""
    chest = _load()
    trade = {
        "timestamp": datetime.utcnow().isoformat(),
        "asset": asset,
        "asset_type": asset_type,  # "crypto" | "stock" | "prediction"
        "action": action,           # "buy" | "sell" | "close"
        "amount": amount,
        "pnl": pnl,
        "strategy": strategy,
        "notes": notes
    }
    chest["trades"].append(trade)
    chest["total_pnl"] = round(chest["total_pnl"] + pnl, 4)
    chest["last_updated"] = datetime.utcnow().isoformat()
    _save(chest)
    return chest["total_pnl"]


def get_summary():
    """Return War Chest summary"""
    chest = _load()
    trades = chest.get("trades", [])
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    return {
        "total_pnl": chest.get("total_pnl", 0),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "last_updated": chest.get("last_updated")
    }
