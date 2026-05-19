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


def kill_switch_alert(reason: str):
    """Alert when kill switch triggers"""
    send(
        f"*⛔ KILL SWITCH TRIGGERED*\n"
        f"Reason: `{reason}`\n"
        f"Trading HALTED\n"
        f"Check logs before restart!"
    )


def crash_alert(error: str):
    """Alert when engine crashes"""
    send(
        f"*⚠️ OpenAgora CRASHED*\n"
        f"Error: `{error}`\n"
        f"Bot offline!\n"
        f"Restart required."
    )


def kill_command_received():
    """Acknowledge remote kill command"""
    send(
        f"*⛔ KILL COMMAND RECEIVED*\n"
        f"Trading HALTED by remote\n"
        f"Use /start to resume"
    )


# Command handler - check incoming messages for commands
def check_commands():
    """Check for incoming commands (call periodically)"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            # Look for /kill or /start commands
            for update in updates:
                if "message" in update:
                    text = update["message"].get("text", "")
                    chat_id = update["message"]["chat"]["id"]
                    if text == "/kill":
                        return {"command": "kill", "chat_id": chat_id}
                    elif text == "/start":
                        return {"command": "start", "chat_id": chat_id}
    except Exception as e:
        print(f"[Telegram] Command check error: {e}")
    return None
