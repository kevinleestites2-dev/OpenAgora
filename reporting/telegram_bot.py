"""
OpenAgora — Telegram Reporting
Pantheon Deploy Rule: every Prime MUST have a reporting channel.
"""

import os
import requests
from datetime import datetime


TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8679655550:AAGUB1m5fmqHc8OHqqM24Vixz8FfwX-gqD4")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7135054241")


def send(message: str):
    """Send a message to the Forgemaster via Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def trade_alert(asset, action, pnl, total_pnl, strategy, simulate=True):
    """Send a trade alert"""
    mode = "🔵 SIMULATE" if simulate else "🟢 LIVE"
    emoji = "📈" if pnl >= 0 else "📉"
    msg = (
        f"*OpenAgora Trade* {mode}\n"
        f"{emoji} *{asset}* | {action.upper()}\n"
        f"P&L: `${pnl:+.4f}`\n"
        f"Strategy: `{strategy}`\n"
        f"War Chest Total: `${total_pnl:+.4f}`\n"
        f"⏱ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send(msg)


def heartbeat(summary: dict, simulate=True):
    """Send a periodic heartbeat with War Chest summary"""
    mode = "🔵 SIMULATE" if simulate else "🟢 LIVE"
    msg = (
        f"*OpenAgora Heartbeat* {mode}\n"
        f"🏛️ *The Agora Never Closes*\n\n"
        f"💰 Total P&L: `${summary['total_pnl']:+.4f}`\n"
        f"📊 Trades: `{summary['total_trades']}`\n"
        f"✅ Wins: `{summary['wins']}` | ❌ Losses: `{summary['losses']}`\n"
        f"🎯 Win Rate: `{summary['win_rate']}%`\n"
        f"⏱ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    return send(msg)


def startup_message(simulate=True):
    """Announce OpenAgora is live"""
    mode = "SIMULATE" if simulate else "🔴 LIVE TRADING"
    send(
        f"*🏛️ OpenAgora ONLINE*\n"
        f"Mode: `{mode}`\n"
        f"Markets: Crypto + Stocks + Predictions\n"
        f"Meta Layer: ACTIVE\n"
        f"War Chest: SYNCED\n"
        f"_The Agora never closes._ 🔱"
    )
