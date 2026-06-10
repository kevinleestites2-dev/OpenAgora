"""
OpenAgora — EverOS Memory Bridge v2.2
Self-Evolving Meta Brain.
v2.2: ROBUST ATOMIC SAVING + QuantMind + Fable 5
"""

import json
import os
import urllib.request
import sys
from datetime import datetime, timezone

MEMORY_PATH = "memory/trade_memory.json"

# ── QuantMind Research Intelligence Bridge ──────────────────────────────────
_QM_BRIDGE = None

def _get_qm():
    global _QM_BRIDGE
    if _QM_BRIDGE is None:
        try:
            _bd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if _bd not in sys.path: sys.path.insert(0, _bd)
            from quantmind_prime_bridge import get_research_signal
            _QM_BRIDGE = get_research_signal
        except Exception as e:
            print("[EverOS] QuantMind not loaded:", e)
            _QM_BRIDGE = lambda topic, ctx="": ""
    return _QM_BRIDGE

# ── Fable 5 Brain ──────────────────────────────────────────────────────────
_OR_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
_OR_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-fable-5")

def _fable5(prompt: str, max_tokens: int = 200) -> str:
    if not _OR_KEY: return None
    try:
        data = json.dumps({
            "model": _OR_MODEL,
            "messages": [{"role": "system", "content": "You are OpenAgora EverOS, a self-evolving trading meta-brain."},
                         {"role": "user", "content": prompt}],
            "max_tokens": max_tokens
        }).encode()
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=data, 
                                     headers={"Authorization": f"Bearer {_OR_KEY}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[EverOS] Fable 5 error: {e}")
        return None

def _load():
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r") as f:
                content = f.read().strip()
                if not content: raise ValueError("Empty")
                return json.loads(content)
        except Exception:
            print(f"[EverOS] Corruption detected. Repairing...")
            with open(MEMORY_PATH, "r") as f:
                content = f.read()
            for i in range(len(content), 0, -1):
                try:
                    data = json.loads(content[:i])
                    _save(data)
                    return data
                except: continue
    return {"version": "2.2", "strategy_stats": {}, "asset_performance": {}, "blacklist": [], "lessons": [], "cycle_count": 0}

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
    score = sum((1.0 if t["pnl"] > 0 else -0.5) for t in s["trade_history"])
    s["weighted_score"] = round(score, 4)
    mem["cycle_count"] = mem.get("cycle_count", 0) + 1
    _save(mem)

def reflect(cycle):
    mem = _load()
    weights = get_strategy_weights()
    qm = _get_qm()
    qm_signal = qm("crypto market regime", str(weights))
    prompt = f"Cycle {cycle} Report. Weights: {weights}. Research: {qm_signal}. What should we change?"
    insight = _fable5(prompt)
    if insight: add_lesson(f"Cycle {cycle} | Fable5: {insight}")

def add_lesson(lesson):
    mem = _load()
    mem["lessons"].append({"ts": datetime.now(timezone.utc).isoformat(), "lesson": lesson})
    if len(mem["lessons"]) > 200: mem["lessons"] = mem["lessons"][-200:]
    _save(mem)

def get_strategy_weights():
    mem = _load()
    stats = mem["strategy_stats"]
    weights = {strat: max(0.05, data.get("weighted_score", 0.5) + 2.0) for strat, data in stats.items()}
    if not weights: return {"momentum": 0.5, "mean_reversion": 0.5}
    total = sum(weights.values())
    return {k: round(v/total, 4) for k, v in weights.items()}

def get_memory_summary():
    mem = _load()
    return {"cycle_count": mem.get("cycle_count", 0), "lesson_count": len(mem.get("lessons", [])), "last_lesson": mem["lessons"][-1]["lesson"] if mem["lessons"] else "None"}
