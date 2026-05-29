import threading
import time
import asyncio
import logging
import sys

import app
import scraping
import telegram_alert

from telegram import Update
from telegram.ext import ApplicationBuilder

TOKEN = telegram_alert.TOKEN

# --------------------
# Logging setup
# --------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


# --------------------
# Flask server
# --------------------
def run_flask():
    logger.info("Flask thread started — binding to 0.0.0.0:5000")
    try:
        app.app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False
        )
        logger.info("Flask server exited cleanly")
    except Exception:
        logger.exception("Flask thread crashed with an unhandled exception")


# --------------------
# Scraper loop
# --------------------
def run_scraper():
    logger.info("Scraper thread started")
    while True:
        logger.info("Scraper: beginning scrape cycle")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scraping.main())
            loop.close()
            logger.info("Scraper: scrape cycle completed successfully")
        except Exception:
            logger.exception("Scraper thread crashed with an unhandled exception")
        logger.info("Scraper: sleeping for 24 hours until next cycle")
        time.sleep(60 * 60 * 24)


# --------------------
# Telegram bot
# --------------------
def run_telegram():
    logger.info("Telegram thread started — waiting 5 s before first connect")
    # Brief delay on startup so any previous instance has time to release
    # its long-poll connection before we open a new one.
    time.sleep(5)

    while True:
        logger.info("Telegram: building application and starting polling")
        try:
            tg_app = ApplicationBuilder().token(TOKEN).build()

            tg_app.job_queue.run_repeating(
                telegram_alert.sending_alerts,
                interval=60 * 60 * 24,
                first=5
            )

            tg_app.run_polling(allowed_updates=Update.ALL_TYPES)
            logger.info("Telegram: polling exited cleanly")

        except Exception as e:
            err = str(e)
            if "Conflict" in err:
                # Another instance is still polling; wait and retry.
                logger.warning(
                    "Telegram: Conflict detected — another instance is still "
                    "running. Retrying in 15 s… (%s)", e
                )
                time.sleep(15)
            else:
                logger.exception(
                    "Telegram thread crashed with an unhandled exception"
                )
                time.sleep(5)


# --------------------
# MAIN
# --------------------
if __name__ == "__main__":
    logger.info("Starting Ecommerce Price Tracker")

    logger.info("Spawning Flask thread")
    threading.Thread(target=run_flask, daemon=True, name="FlaskThread").start()

    logger.info("Spawning scraper thread")
    threading.Thread(target=run_scraper, daemon=True, name="ScraperThread").start()

    logger.info("Starting Telegram bot on main thread")
    run_telegram()