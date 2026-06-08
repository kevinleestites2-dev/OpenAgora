"""
OpenAgora — Telegram Reporting via SeekerClaw
Dedicated bot for OpenAgora ONLY.
Token: @Seekerclaw27_bot
"""

import os
import requests
from datetime import datetime

# SeekerClaw — OpenAgora's dedicated Telegram bot
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("AGORA_TELEGRAM_TOKEN", "8847391123:AAEvnj4sEtJABzxBE3jqP0IhhybQAwCL6q4")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7135054241")


def send(message: str):
    """Send a message to the Forgemaster via SeekerClaw"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[SeekerClaw] Error: {e}")
        return False


def trade_alert(asset, action, pnl, total_pnl, strategy, simulate=True):
    """Send a trade alert"""
    mode  = "🔵 SIMULATE" if simulate else "🟢 LIVE"
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
    mode = "SIMULATE 🔵" if simulate else "🔴 LIVE TRADING"
    send(
        f"*🏛️ OpenAgora ONLINE*\n"
        f"Bot: `@Seekerclaw27_bot`\n"
        f"Mode: `{mode}`\n"
        f"Markets: Crypto + Stocks + Predictions\n"
        f"Meta Layer: ACTIVE\n"
        f"EverOS: CALIBRATING\n"
        f"War Chest: SYNCED\n"
        f"_The Agora never closes._ 🔱"
    )


def circuit_breaker_alert(cycle: int):
    """Alert when circuit breaker fires"""
    send(
        f"⚡ *Circuit Breaker Fired*\n"
        f"Cycle `{cycle}` skipped — 2 consecutive losses\n"
        f"EverOS recalibrating...\n"
        f"_Next cycle resumes automatically._"
    )


def diversification_alert(asset: str, action: str, pnl: float, total_pnl: float, simulate=True):
    """Alert when diversification nudge fires a second trade"""
    mode  = "🔵 SIMULATE" if simulate else "🟢 LIVE"
    emoji = "📈" if pnl >= 0 else "📉"
    send(
        f"*🔀 Diversification Trade* {mode}\n"
        f"{emoji} *{asset}* | {action.upper()}\n"
        f"P&L: `${pnl:+.4f}`\n"
        f"War Chest Total: `${total_pnl:+.4f}`\n"
        f"_EverOS confidence was high enough to double down._"
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
        f"Bot offline — restart required."
    )


def kill_command_received():
    """Acknowledge remote kill command"""
    send(
        f"*⛔ KILL COMMAND RECEIVED*\n"
        f"Trading HALTED by remote\n"
        f"Send /start to resume"
    )


def check_commands():
    """Check for incoming Telegram commands"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            for update in updates:
                if "message" in update:
                    text    = update["message"].get("text", "")
                    chat_id = update["message"]["chat"]["id"]
                    if text == "/kill":
                        return {"command": "kill",  "chat_id": chat_id}
                    elif text == "/start":
                        return {"command": "start", "chat_id": chat_id}
                    elif text == "/status":
                        return {"command": "status", "chat_id": chat_id}
                    elif text == "/warcheck":
                        return {"command": "warcheck", "chat_id": chat_id}
    except Exception as e:
        print(f"[SeekerClaw] Command check error: {e}")
    return None
