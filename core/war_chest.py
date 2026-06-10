"""
OpenAgora — War Chest Bridge
MidasPrime integration — logs all P&L in real time
Enhanced with risk management: stop loss, daily drawdown, position sizing, kill switch
"""

import json
import os
import base64
import urllib.request
from datetime import datetime, timedelta

# ── GitHub Persistence (2026-06-10) ──────────────────────────────────────────
_GH_TOKEN  = os.getenv("GITHUB_TOKEN", os.getenv("GH_PAT", ""))
_GH_REPO   = os.getenv("GH_REPO", "kevinleestites2-dev/OpenAgora")
_GH_PATH   = "logs/war_chest.json"
_SYNC_EVERY = int(os.getenv("WAR_CHEST_SYNC_EVERY", "3"))  # sync every N trades
_sync_counter = 0

def _gh_sync(data):
    """Push war_chest.json to GitHub so restarts resume from real state."""
    if not _GH_TOKEN:
        return
    try:
        # Get current SHA
        req = urllib.request.Request(
            f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}",
            headers={"Authorization": f"Bearer {_GH_TOKEN}", "Accept": "application/vnd.github+json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read())["sha"]
        # Push updated content
        body_str = json.dumps(data, indent=2)
        payload  = json.dumps({
            "message": f"[AutoSync] War Chest — total_pnl=${data.get('total_pnl',0):.4f}",
            "content": base64.b64encode(body_str.encode()).decode(),
            "sha": sha
        }).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}",
            data=payload,
            headers={"Authorization": f"Bearer {_GH_TOKEN}", "Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            pass  # 200/201 = success
    except Exception as e:
        print(f"[WarChest] GitHub sync failed: {e}")

def _load_from_gh():
    """Pull war_chest.json from GitHub on startup if local file is missing/stale."""
    if not _GH_TOKEN:
        return None
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}",
            headers={"Authorization": f"Bearer {_GH_TOKEN}", "Accept": "application/vnd.github+json"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        return json.loads(base64.b64decode(d["content"]).decode())
    except Exception as e:
        print(f"[WarChest] GitHub load failed: {e}")
        return None


WAR_CHEST_PATH = os.getenv("WAR_CHEST_PATH", "logs/war_chest.json")

# Risk management settings
MAX_POSITION_RISK_PERCENT = float(os.getenv("MAX_POSITION_RISK_PERCENT", "2"))  # Max 2% of War Chest per trade
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "5"))  # 5% stop loss per trade
DAILY_DRAWDOWN_LIMIT_PERCENT = float(os.getenv("DAILY_DRAWDOWN_LIMIT_PERCENT", "10"))  # 10% daily drawdown halt
INITIAL_WAR_CHEST = float(os.getenv("INITIAL_WAR_CHEST", "1000"))  # Starting value for drawdown calc


def _load():
    if os.path.exists(WAR_CHEST_PATH):
        with open(WAR_CHEST_PATH, "r") as f:
            return json.load(f)
    # Local file missing — pull from GitHub before starting fresh
    gh_data = _load_from_gh()
    if gh_data:
        print(f"[WarChest] Restored from GitHub — total_pnl=${gh_data.get('total_pnl',0):.4f}")
        _save(gh_data)
        return gh_data
    return {"total_pnl": 0.0, "trades": [], "last_updated": None}


def _save(data):
    global _sync_counter
    os.makedirs(os.path.dirname(WAR_CHEST_PATH), exist_ok=True)
    with open(WAR_CHEST_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # Sync to GitHub every N trades
    _sync_counter += 1
    if _sync_counter >= _SYNC_EVERY:
        _sync_counter = 0
        _gh_sync(data)


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


# === RISK MANAGEMENT ===

def calculate_position_size(current_chest_pnl):
    """Calculate max position size based on 2% risk rule"""
    chest_worth = INITIAL_WAR_CHEST + current_chest_pnl
    max_risk = chest_worth * (MAX_POSITION_RISK_PERCENT / 100)
    return max_risk


def check_stop_loss(entry_price, current_price, action):
    """Check if trade hits stop loss"""
    if action.upper() == "BUY":
        loss_pct = (entry_price - current_price) / entry_price * 100
    else:  # SELL
        loss_pct = (current_price - entry_price) / entry_price * 100
    
    return loss_pct >= STOP_LOSS_PERCENT


def check_daily_drawdown():
    """Check if daily drawdown exceeds limit"""
    chest = _load()
    trades = chest.get("trades", [])
    
    if not trades:
        return False  # No trades today
    
    # Get today's trades
    today = datetime.utcnow().date()
    today_trades = [
        t for t in trades 
        if datetime.fromisoformat(t["timestamp"]).date() == today
    ]
    
    if not today_trades:
        return False
    
    daily_pnl = sum(t["pnl"] for t in today_trades)
    daily_loss_pct = (abs(daily_pnl) / INITIAL_WAR_CHEST) * 100
    
    # Only trigger if negative
    if daily_pnl < 0 and daily_loss_pct >= DAILY_DRAWDOWN_LIMIT_PERCENT:
        return True
    
    return False


def get_kill_switch_status():
    """Check if kill switch is triggered"""
    if check_daily_drawdown():
        return {
            "triggered": True,
            "reason": "daily_drawdown",
            "message": f"Daily drawdown limit ({DAILY_DRAWDOWN_LIMIT_PERCENT}%) exceeded"
        }
    return {"triggered": False, "reason": None, "message": "OK"}


def reset_daily_tracking():
    """Reset daily tracking (call at start of new day)"""
    # Can be used for daily reset logic if needed
    pass
