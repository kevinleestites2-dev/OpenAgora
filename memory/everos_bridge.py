"""
OpenAgora — EverOS Memory Bridge v2.1
Self-Evolving Meta Brain.
v2.1: ROBUST ATOMIC SAVING
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

MEMORY_PATH = "memory/trade_memory.json"

def _load():
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r") as f:
                content = f.read().strip()
                return json.loads(content)
        except Exception:
            print(f"[EverOS] LOAD ERROR. Attempting repair...")
            with open(MEMORY_PATH, "r") as f:
                content = f.read()
            for i in range(len(content), 0, -1):
                try:
                    data = json.loads(content[:i])
                    print("[EverOS] Repair success.")
                    _save(data)
                    return data
                except: continue
    return {"version": "2.1", "strategy_stats": {}, "asset_performance": {}, "blacklist": [], "lessons": [], "cycle_count": 0}

def _save(data):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    temp_file = MEMORY_PATH + ".tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, MEMORY_PATH)

def record_trade(strategy, asset, pnl, confidence=0.5):
    mem = _load()
    if strategy not in mem["strategy_stats"]:
        mem["strategy_stats"][strategy] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "weighted_score": 1.0, "trade_history": []}
    s = mem["strategy_stats"][strategy]
    s["total_pnl"] = round(s["total_pnl"] + pnl, 4)
    if pnl > 0: s["wins"] += 1
    else: s["losses"] += 1
    s["trade_history"].append({"pnl": pnl, "ts": datetime.now(timezone.utc).isoformat()})
    if len(s["trade_history"]) > 20: s["trade_history"].pop(0)
    
    # Simple score
    score = sum((1.0 if t["pnl"] > 0 else -0.5) for t in s["trade_history"])
    s["weighted_score"] = round(score, 4)
    
    mem["cycle_count"] = mem.get("cycle_count", 0) + 1
    _save(mem)

def get_strategy_weights():
    mem = _load()
    stats = mem["strategy_stats"]
    weights = {strat: max(0.05, data.get("weighted_score", 0.5) + 2.0) for strat, data in stats.items()}
    if not weights: return {"momentum": 0.5, "mean_reversion": 0.5}
    total = sum(weights.values())
    return {k: round(v/total, 4) for k, v in weights.items()}

def add_lesson(lesson):
    mem = _load()
    mem["lessons"].append({"ts": datetime.now(timezone.utc).isoformat(), "lesson": lesson})
    if len(mem["lessons"]) > 200: mem["lessons"] = mem["lessons"][-200:]
    _save(mem)

def get_memory_summary():
    mem = _load()
    return {"cycle_count": mem.get("cycle_count", 0), "lesson_count": len(mem.get("lessons", [])), "last_lesson": mem["lessons"][-1]["lesson"] if mem["lessons"] else "None"}
