import os
import time
import threading
from datetime import datetime

import requests
from flask import Flask

#########################################
#  FLASK WEB SERVER  (for Replit uptime)
#########################################
app = Flask(__name__)

@app.route("/")
def home():
    return "Upstox Free Bot Running!"

def run_server():
    # Replit expects web apps on port 8080
    app.run(host="0.0.0.0", port=8080)


#########################################
#  ENV VARIABLES (from Replit Secrets)
#########################################
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")          # not used yet, but kept
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

INSTRUMENT_KEYS = os.getenv(
    "INSTRUMENT_KEYS",
    "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank"
)

POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "1"))
LEVEL_STEP_POINTS = float(os.getenv("LEVEL_STEP_POINTS", "50"))

last_level_alert = {}  # remember last alerted price level per symbol


#########################################
#  TELEGRAM ALERT
#########################################
def send_telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, skipping:", msg)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=5
        )
    except Exception as e:
        print("Telegram error:", e)


#########################################
#  FETCH QUOTES FROM UPSTOX REST API
#########################################
def fetch_quotes(keys: str) -> dict:
    """
    Calls Upstox 'market-quote/quotes' REST endpoint for one or more symbols.
    keys: comma-separated instrument_key list.
    Returns dict mapping instrument_key -> quote info (or {} on error).
    """
    if not UPSTOX_ACCESS_TOKEN:
        print("❌ UPSTOX_ACCESS_TOKEN not set in secrets.")
        return {}

    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {
        "Authorization": f"Bearer {UPSTOX_ACCESS_TOKEN}",
        "Accept": "application/json",
    }
    params = {"instrument_key": keys}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
    except Exception as e:
        print("Request error:", e)
        return {}

    if r.status_code == 401:
        print("⚠️ Upstox 401 Unauthorized – access token is invalid/expired.")
        send_telegram("⚠️ Upstox access token invalid or expired. Update in Replit.")
        return {}

    try:
        data = r.json()
    except Exception as e:
        print("JSON decode error:", e, "body:", r.text[:200])
        return {}

    if data.get("status") != "success":
        print("Upstox error:", data)
        return {}

    return data.get("data", {})


#########################################
#  PROCESS EACH TICK (simple level alert)
#########################################
def process_tick(symbol: str, ltp: float, buy_volume: float) -> None:
    """
    For now: send alert when price crosses a multiple of LEVEL_STEP_POINTS.
    You will later plug HFT/gamma logic here.
    """
    global last_level_alert

    level = int(round(ltp / LEVEL_STEP_POINTS) * LEVEL_STEP_POINTS)
    prev_level = last_level_alert.get(symbol)

    if prev_level != level:
        last_level_alert[symbol] = level
        msg = (
            f"⚡ {symbol}\n"
            f"Price: {ltp}\n"
            f"Level touched: {level}\n"
            f"Buy-side volume (snapshot): {buy_volume}\n"
            f"Time: {datetime.now()}"
        )
        print(msg)
        send_telegram(msg)


#########################################
#  MAIN BOT LOOP
#########################################
def main_bot():
    print("🚀 Upstox Free Replit Bot Started!")
    send_telegram("🚀 Upstox Free Replit Bot Started!")

    keys_list = [k.strip() for k in INSTRUMENT_KEYS.split(",") if k.strip()]
    joined_keys = ",".join(keys_list)

    while True:
        try:
            quotes = fetch_quotes(joined_keys)
            for k in keys_list:
                q = quotes.get(k)
                if not q:
                    continue

                # Try different fields Upstox might return
                ltp = q.get("last_price") or q.get("ltp")
                depth = q.get("depth", {})
                buy_side = depth.get("buy", [])
                buy_qty = sum(x.get("quantity", 0) for x in buy_side)

                if ltp is not None:
                    process_tick(k, float(ltp), float(buy_qty))
        except Exception as e:
            print("Error in main_bot loop:", e)

        time.sleep(POLL_INTERVAL_SEC)


#########################################
#  START FLASK + BOT TOGETHER
#########################################
def start_all():
    print("🚀 Starting services…")
    # Start the bot loop in a background thread
    threading.Thread(target=main_bot, daemon=True).start()
    # Start the Flask web server (blocks main thread)
    run_server()


#########################################
#  ENTRY POINT
#########################################
if __name__ == "__main__":
    start_all()
