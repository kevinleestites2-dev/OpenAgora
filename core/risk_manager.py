"""
OpenAgora — Risk Manager
The Warden. Nothing trades without passing through here.

Checks:
  - Kill switch (daily drawdown)
  - Position sizing (2% rule)
  - Stop loss per trade
  - Confidence threshold
  - Remote kill command
"""

import os
from core.war_chest import (
    get_kill_switch_status,
    calculate_position_size,
    get_summary,
    check_stop_loss
)
from reporting.telegram_bot import kill_switch_alert

MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))


def pre_trade_check(signal: dict) -> dict:
    """
    Run all pre-trade risk checks.
    Returns: {"approved": bool, "reason": str, "position_size": float}
    """
    # 1. Kill switch — daily drawdown
    kill = get_kill_switch_status()
    if kill["triggered"]:
        kill_switch_alert(kill["reason"])
        return {"approved": False, "reason": f"Kill switch: {kill['reason']}", "position_size": 0}

    # 2. Confidence threshold
    confidence = signal.get("confidence", 0)
    if confidence < MIN_CONFIDENCE:
        return {"approved": False, "reason": f"Low confidence: {confidence:.2f} < {MIN_CONFIDENCE}", "position_size": 0}

    # 3. Position sizing
    summary = get_summary()
    position_size = calculate_position_size(summary["total_pnl"])
    if position_size <= 0:
        return {"approved": False, "reason": "War Chest depleted", "position_size": 0}

    return {
        "approved": True,
        "reason": "All checks passed",
        "position_size": round(position_size, 2),
        "confidence": confidence
    }


def post_trade_check(entry_price: float, current_price: float, action: str) -> bool:
    """
    Check if open position should be stopped out.
    Returns True if stop loss hit.
    """
    if entry_price <= 0:
        return False
    return check_stop_loss(entry_price, current_price, action)
