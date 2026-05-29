from telegram.ext import ApplicationBuilder
import sqlite3
from urllib.parse import urlparse
from telegram import Bot
import json
import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TOKEN_KEY")
CHAT_ID = 7859694973

bot = Bot(token=TOKEN)

with open("config.json", "r") as f:
    config = json.load(f)



def get_domain(url):
    return urlparse(url).netloc


async def sending_alerts(context):
    threshold = config["alert_threshold_percent"]
    conn = sqlite3.connect("products.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
SELECT
    products.id,
    products.name,
    products.amazon_url,
    products.ebay_url,
    price_history.amazon_price,
    price_history.ebay_price,
    price_history.best_deal

FROM products
JOIN price_history ON products.id = price_history.product_id
WHERE price_history.date = (
    SELECT MAX(ph2.date) FROM price_history ph2
    WHERE ph2.product_id = products.id
)
ORDER BY products.id
""")

    products = cursor.fetchall()
    product_name_map = {p["id"]: p["name"] for p in products}

    cursor.execute("""
SELECT *
FROM (
    SELECT
        ph.*,
        ROW_NUMBER() OVER (
            PARTITION BY ph.product_id
            ORDER BY ph.date DESC
        ) AS rn
    FROM price_history ph
)
WHERE rn <= 2
ORDER BY product_id, rn;
""")

    prices_drop = cursor.fetchall()
    conn.close()

    latest = []
    previous = []

    for row in prices_drop:
        if row["rn"] == 1:
            latest.append(row)
        elif row["rn"] == 2:
            previous.append(row)

    lookup_y = {p["product_id"]: p for p in previous}

    for x in latest:
        y = lookup_y.get(x["product_id"])
        if not y:
            continue

        name = product_name_map.get(x["product_id"], "Unknown product")
        amazon_dropped = False
        ebay_dropped = False

        if x["amazon_price"] is not None and y["amazon_price"] is not None:
            temp_amazon = (y["amazon_price"] * threshold) / 100
            threshold_amazon = y["amazon_price"] - temp_amazon
            if x["amazon_price"] < threshold_amazon:
                amazon_dropped = True
                text = f"🔔 Price Drop Alert!\n\n📦 {name}\n\n🟠 Amazon: ${y['amazon_price']} → ${x['amazon_price']}"
                await context.bot.send_message(chat_id=CHAT_ID, text=text)

        if x["ebay_price"] is not None and y["ebay_price"] is not None:
            temp_ebay = (y["ebay_price"] * threshold) / 100
            threshold_ebay = y["ebay_price"] - temp_ebay
            if x["ebay_price"] < threshold_ebay:
                ebay_dropped = True
                text = f"🔔 Price Drop Alert!\n\n📦 {name}\n\n🟢 eBay: ${y['ebay_price']} → ${x['ebay_price']}"
                await context.bot.send_message(chat_id=CHAT_ID, text=text)

       
            


