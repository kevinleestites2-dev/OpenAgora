"""
OpenAgora — GitHub War Chest Sync
Pulls war_chest.json from the repo at startup, pushes after every cycle.
This gives OpenAgora persistent memory across GitHub Actions runs.
"""

import os
import json
import base64
import urllib.request
import urllib.error

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO         = "kevinleestites2-dev/OpenAgora"
REMOTE_PATH  = "logs/war_chest.json"
LOCAL_PATH   = os.getenv("WAR_CHEST_PATH", "logs/war_chest.json")
API_BASE     = f"https://api.github.com/repos/{REPO}/contents/{REMOTE_PATH}"


def _headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }


def pull():
    """Pull war_chest.json from GitHub into local file. Returns True if found."""
    if not GITHUB_TOKEN:
        print("[GitSync] No GITHUB_TOKEN — skipping pull")
        return False
    try:
        req = urllib.request.Request(API_BASE, headers=_headers())
        resp = urllib.request.urlopen(req)
        d = json.loads(resp.read())
        content = base64.b64decode(d["content"]).decode()
        os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
        with open(LOCAL_PATH, "w") as f:
            f.write(content)
        data = json.loads(content)
        trades = data.get("trades", [])
        wins   = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] < 0]
        rate   = f"{len(wins)/len(trades)*100:.1f}%" if trades else "N/A"
        print(f"[GitSync] WAR CHEST RESTORED — {len(trades)} trades | {rate} win rate | ${data.get('total_pnl', 0):+.4f} total PnL")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("[GitSync] No war_chest.json on GitHub yet — starting fresh")
        else:
            print(f"[GitSync] Pull error {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"[GitSync] Pull error: {e}")
        return False


def push(message="OpenAgora — war chest sync"):
    """Push local war_chest.json to GitHub."""
    if not GITHUB_TOKEN:
        print("[GitSync] No GITHUB_TOKEN — skipping push")
        return False
    if not os.path.exists(LOCAL_PATH):
        print("[GitSync] No local war_chest.json to push")
        return False
    try:
        with open(LOCAL_PATH, "rb") as f:
            content = f.read()
        encoded = base64.b64encode(content).decode()

        # Get current SHA if file exists
        sha = ""
        try:
            req = urllib.request.Request(API_BASE, headers=_headers())
            resp = urllib.request.urlopen(req)
            sha = json.loads(resp.read()).get("sha", "")
        except:
            pass

        payload = {"message": message, "content": encoded}
        if sha:
            payload["sha"] = sha

        req2 = urllib.request.Request(
            API_BASE,
            data=json.dumps(payload).encode(),
            method="PUT",
            headers=_headers()
        )
        urllib.request.urlopen(req2)
        print("[GitSync] WAR CHEST PUSHED to GitHub ✅")
        return True
    except Exception as e:
        print(f"[GitSync] Push error: {e}")
        return False
