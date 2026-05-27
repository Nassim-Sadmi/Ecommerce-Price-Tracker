# 🛒 Ecommerce Price Tracker

A fully automated price comparison and monitoring system that tracks products across Amazon and eBay, stores price history, displays a live dashboard, and sends Telegram alerts when prices drop.

---

## What It Does

- Searches Amazon and eBay for any product you specify
- Uses a custom matching algorithm to identify the same product across both platforms
- Tracks price history daily and stores it in a local database
- Displays a dark-mode dashboard with product cards, prices, best deal, and price history charts
- Sends Telegram alerts when a product drops below a configurable threshold
- On first run: full search and matching pipeline. On subsequent runs: goes directly to stored URLs for fast price checks

---

## Tech Stack

- **Python** — core language
- **Playwright** — browser automation for Amazon and eBay scraping
- **SQLite** — local database for products and price history
- **Flask** — lightweight web server for the dashboard
- **ApexCharts** — interactive price history charts
- **python-telegram-bot** — Telegram alert delivery
- **asyncio** — concurrent scraping with semaphore rate limiting

---

## Project Structure

```
Ecommerce_Price_Tracker/
├── scraping.py         # Amazon + eBay scraping, matching logic, database insertion
├── app.py              # Flask dashboard server
├── telegram_alert.py   # Telegram alert logic
├── main.py             # Single entry point — starts everything
├── config.json         # Product list and settings
├── products.db         # SQLite database (auto-created)
└── templates/
    └── dashboard.html  # Dark mode dashboard UI
```

---

## Setup

**1. Install dependencies**

```bash
pip install playwright flask python-telegram-bot requests
playwright install chromium
```

**2. Configure `config.json`**

```json
{
  "products": [
    "Sony WH-1000XM5 headphones",
    "Nintendo Switch OLED",
    "Logitech MX Master 3S mouse"
  ],
  "alert_threshold_percent": 5
}
```

- `products` — list of products to track. Be specific for better matching (e.g. include brand, model, key specs)
- `alert_threshold_percent` — minimum price drop percentage to trigger a Telegram alert

**3. Set your Telegram credentials**

In `.env`, replace:

```python
TOKEN_KEY = "your_telegram_bot_token"
```

In `telegram_alert.py`, replace :
```python
CHAT_ID = your_chat_id
```
To get these: create a bot via [@BotFather](https://t.me/BotFather) on Telegram, then get your chat ID via [@userinfobot](https://t.me/userinfobot).

**4. Run**

```bash
python main.py
```

This starts everything in one command:
- Flask dashboard at `http://localhost:5000`
- Scraper runs immediately, then every 24 hours
- Telegram bot checks for price drops every 60 seconds

---

## How the Matching Algorithm Works

Since Amazon and eBay use completely different product identifiers, the system uses a multi-step matching pipeline to find the same product on both platforms:

**Phase 1 — Amazon Search**
Playwright searches Amazon, visits the top 5 product URLs, and scores each one against the user's query using word overlap scoring. The best match becomes the reference product.

**Phase 2 — Title Cleaning**
The Amazon title is stripped of filler words, punctuation, and marketing language. The first 6 meaningful words are extracted as a clean search query. Numbers from the original config query are appended if missing from the Amazon title (e.g. "16 oz", "256GB").

**Phase 3 — eBay Candidate Collection**
The cleaned query is used to search eBay. The top 10 listings are collected with their title, price, URL, and image.

**Phase 4 — Evaluation Gate**
Each eBay candidate is scored against the cleaned Amazon title using Jaccard similarity (intersection / union of word sets). Before scoring, a number strike filter discards candidates whose key numbers conflict with the config query. The highest scoring candidate above 60% confidence is selected as the match.

**Phase 5 — Confidence Score**
The final match score is stored and displayed in the dashboard. Scores between 60–84% are flagged as "Good Match" (yellow), 85%+ as "Strong Match" (green).

---

## Dashboard

Open `http://localhost:5000` after running `main.py`.

Each product card shows:
- Product images linked to Amazon and eBay listings
- Current Amazon and eBay prices
- Best deal badge
- Match confidence score
- "View Price History" button — opens a modal with an ApexCharts line chart showing price trends over time for both platforms

---

## Telegram Alerts

Alerts fire when a product's price drops by more than the configured threshold since the last check.

Example alert:
```
🔔 Price Drop Alert!

📦 Sony WH-1000XM5 Noise Canceling Headphones

🟠 Amazon: $279.0 → $229.0
```

If no price change is detected, a "no change" message is sent (useful for testing — can be disabled in `telegram_alert.py`).

---

## Database Schema

**`products` table** — created once per product, stores identity and URLs

| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| name | TEXT UNIQUE | Cleaned Amazon product title |
| amazon_url | TEXT | Direct Amazon product URL |
| ebay_url | TEXT | Direct eBay listing URL |
| amazon_img | TEXT | Amazon product image URL |
| ebay_img | TEXT | eBay listing image URL |
| added_date | TEXT | Timestamp of first insertion |

**`price_history` table** — new row added every daily run

| Column | Type | Description |
|---|---|---|
| id | INTEGER | Primary key |
| product_id | INTEGER | Foreign key → products.id |
| amazon_price | REAL | Amazon price at time of check |
| ebay_price | REAL | eBay price at time of check |
| confidence | REAL | Match confidence score (0–100) |
| best_deal | TEXT | "amazon" or "ebay" |
| date | TEXT | Timestamp of price check |

---

## Limitations

- **Amazon anti-bot:** Amazon actively detects automated browsing. The system uses human-like delays, randomized headers, and sequential requests to reduce detection. Running from a residential IP is recommended. For high-volume usage, proxy rotation should be added.
- **Price availability:** Some Amazon listings hide prices behind login or "Add to cart" flows. These are logged as unavailable and skipped.
- **Product matching:** The matching algorithm is based on word similarity and works well for specific product names with model numbers. Vague queries or products with many variants (sizes, colors) may produce lower confidence scores.
- **eBay layout variations:** eBay serves slightly different HTML layouts across sessions. The scraper handles this with `.first` selectors and per-field error handling.

---

## Notes

- The database file `products.db` is auto-created on first run in the project directory
- Products are never duplicated — `INSERT OR IGNORE` prevents duplicate entries
- On subsequent runs, the system skips the search pipeline entirely and goes directly to stored URLs for faster execution
- The Telegram "no change" message can be removed in production by deleting the final `else` block in `sending_alerts()`
