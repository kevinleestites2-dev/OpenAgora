"""
OpenAgora — War Chest Bridge
MidasPrime integration — logs all P&L in real time
v3.5: ROBUST ATOMIC SAVING (Anti-corruption)
"""

import json
import os
import base64
import urllib.request
from datetime import datetime, timedelta

# Risk management settings
MAX_POSITION_RISK_PERCENT = float(os.getenv("MAX_POSITION_RISK_PERCENT", "2"))
STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "5"))
DAILY_DRAWDOWN_LIMIT_PERCENT = float(os.getenv("DAILY_DRAWDOWN_LIMIT_PERCENT", "10"))
INITIAL_WAR_CHEST = float(os.getenv("INITIAL_WAR_CHEST", "1000"))
WAR_CHEST_FILE = os.getenv("WAR_CHEST_PATH", "logs/war_chest.json")

# ── GitHub Persistence ──
_GH_TOKEN  = os.getenv("GITHUB_TOKEN", os.getenv("GH_PAT", ""))
_GH_REPO   = os.getenv("GH_REPO", "kevinleestites2-dev/OpenAgora")
_GH_PATH   = "logs/war_chest.json"

def _gh_sync(data):
    if not _GH_TOKEN: return
    try:
        # Get current SHA
        req = urllib.request.Request(
            f"https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PATH}",
            headers={"Authorization": f"token {_GH_TOKEN}", "Accept": "application/vnd.github+json"}
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
            headers={"Authorization": f"token {_GH_TOKEN}", "Content-Type": "application/json"},
            method="PUT"
        )
        with urllib.request.urlopen(req, timeout=15): pass
    except Exception as e:
        print(f"[WarChest] GitHub sync failed: {e}")

def _load():
    if os.path.exists(WAR_CHEST_FILE):
        try:
            with open(WAR_CHEST_FILE, "r") as f:
                content = f.read().strip()
                if not content: raise ValueError("Empty file")
                return json.loads(content)
        except Exception as e:
            print(f"[WarChest] LOAD ERROR: {e}. Attempting repair...")
            with open(WAR_CHEST_FILE, "r") as f:
                content = f.read()
            for i in range(len(content), 0, -1):
                try:
                    data = json.loads(content[:i])
                    print("[WarChest] Truncated corrupted tail. Repair success.")
                    _save(data)
                    return data
                except: continue
            print("[WarChest] REPAIR FAILED. Starting fresh.")
    return {"total_pnl": 0.0, "trades": [], "last_updated": None}

def _save(data):
    os.makedirs(os.path.dirname(WAR_CHEST_FILE), exist_ok=True)
    temp_file = WAR_CHEST_FILE + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, WAR_CHEST_FILE)
    # Sync to GH
    _gh_sync(data)

def log_trade(asset, asset_type, action, amount, pnl, strategy, notes=""):
    chest = _load()
    chest["trades"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "asset": asset, "asset_type": asset_type,
        "action": action, "amount": amount, "pnl": pnl,
        "strategy": strategy, "notes": notes
    })
    chest["total_pnl"] = round(chest["total_pnl"] + pnl, 4)
    chest["last_updated"] = datetime.utcnow().isoformat()
    _save(chest)
    return chest["total_pnl"]

def get_summary():
    chest = _load()
    trades = chest.get("trades", [])
    wins = [t for t in trades if t["pnl"] > 0]
    return {
        "total_pnl": chest.get("total_pnl", 0),
        "total_trades": len(trades),
        "wins": len(wins), "losses": len(trades) - len(wins),
        "win_rate": round(len(wins)/len(trades)*100, 1) if trades else 0,
        "last_updated": chest.get("last_updated")
    }

def check_daily_drawdown():
    chest = _load()
    trades = [t for t in chest.get("trades", []) if datetime.fromisoformat(t["timestamp"]).date() == datetime.utcnow().date()]
    if not trades: return False
    daily_pnl = sum(t["pnl"] for t in trades)
    return daily_pnl < 0 and (abs(daily_pnl) / INITIAL_WAR_CHEST) * 100 >= DAILY_DRAWDOWN_LIMIT_PERCENT

def get_kill_switch_status():
    if check_daily_drawdown(): return {"triggered": True, "reason": "daily_drawdown", "message": "Limit exceeded"}
    return {"triggered": False, "reason": None, "message": "OK"}
