"""
OpenAgora — Nexus Relay Reporter
Pushes live status to Nexus Relay every 60s so ZapiaPrime can check in anytime.
"""

import os
import threading
import time
import requests
from core.war_chest import get_summary

RELAY_URL = os.getenv("NEXUS_RELAY_URL", "https://nexus-relay-production.up.railway.app")
RELAY_SECRET = os.getenv("NEXUS_RELAY_SECRET", "pantheon_prime")
RELAY_INTERVAL = int(os.getenv("RELAY_INTERVAL", "60"))

_agora_state = {
    "mode": "simulate",
    "cycle_count": 0,
    "remote_kill": False,
    "regime": "UNKNOWN",
    "active_strategies": []
}

def update_state(**kwargs):
    """Call this from agora_engine to keep state fresh"""
    _agora_state.update(kwargs)

def _push_status():
    while True:
        try:
            summary = get_summary()
            payload = {
                "agent": "OpenAgora",
                "version": "v2.0",
                "mode": _agora_state.get("mode", "simulate").upper(),
                "cycle_count": _agora_state.get("cycle_count", 0),
                "remote_kill": _agora_state.get("remote_kill", False),
                "total_pnl": summary["total_pnl"],
                "total_trades": summary["total_trades"],
                "wins": summary["wins"],
                "losses": summary["losses"],
                "win_rate": summary["win_rate"],
                "last_trade": summary["last_updated"],
                "active_strategies": _agora_state.get("active_strategies", []),
                "regime": _agora_state.get("regime", "UNKNOWN")
            }
            resp = requests.post(
                f"{RELAY_URL}/command",
                json={"type": "status_push", "agent": "OpenAgora", "data": payload},
                headers={"X-Secret": RELAY_SECRET},
                timeout=10
            )
            print(f"[AGORA-RELAY] Pushed | Trades: {payload['total_trades']} | PnL: {payload['total_pnl']:+.4f}")
        except Exception as e:
            print(f"[AGORA-RELAY] Push failed: {e}")
        time.sleep(RELAY_INTERVAL)

def start_relay():
    t = threading.Thread(target=_push_status, daemon=True)
    t.start()
    print(f"[AGORA-RELAY] Started — pushing every {RELAY_INTERVAL}s to Nexus Relay")
