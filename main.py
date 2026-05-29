import threading
import time
import asyncio

import app
import scraping
import telegram_alert

from telegram import Update
from telegram.ext import ApplicationBuilder

TOKEN = telegram_alert.TOKEN


# --------------------
# Flask server
# --------------------
def run_flask():
    app.app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )


# --------------------
# Scraper loop
# --------------------
def run_scraper():
    while True:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scraping.main())
            loop.close()
        except Exception as e:
            print(f"[SCRAPER ERROR] {e}")
        time.sleep(60 * 60 * 24)


# --------------------
# Telegram bot
# --------------------
def run_telegram():
    # Brief delay on startup so any previous instance has time to release
    # its long-poll connection before we open a new one.
    time.sleep(5)

    while True:
        try:
            tg_app = ApplicationBuilder().token(TOKEN).build()

            tg_app.job_queue.run_repeating(
                telegram_alert.sending_alerts,
                interval=60 * 60 * 24,
                first=5
            )

            tg_app.run_polling(allowed_updates=Update.ALL_TYPES)

        except Exception as e:
            err = str(e)
            if "Conflict" in err:
                # Another instance is still polling; wait and retry.
                print(f"[TELEGRAM] Conflict detected — another instance is "
                      f"still running. Retrying in 15 s… ({e})")
                time.sleep(15)
            else:
                print(f"[TELEGRAM ERROR] {e}")
                time.sleep(5)


# --------------------
# MAIN
# --------------------
if __name__ == "__main__":

    threading.Thread(target=run_flask, daemon=True).start()

    threading.Thread(target=run_scraper, daemon=True).start()

    run_telegram()