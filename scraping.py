from playwright.async_api import async_playwright
import asyncio
import json
import logging
import re
import string
import sqlite3
import os

logger = logging.getLogger(__name__)


def database_creation():
    with sqlite3.connect('products.db') as conn:
        #print(os.path.abspath('products.db'))
        cursor = conn.cursor()

        # Create the table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                amazon_url TEXT,
                ebay_url TEXT,
                amazon_img TEXT,
                ebay_img TEXT,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                amazon_price REAL,
                ebay_price REAL,
                confidence REAL,
                best_deal TEXT,
                date TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')

        conn.commit()
        #print("Table created successfully!")


#------------------------------------------
def product_insertion(name, amazon_url, ebay_url, amazon_img, ebay_img):
    with sqlite3.connect("products.db") as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO products (
                name, amazon_url, ebay_url, amazon_img, ebay_img
            )
            VALUES (?, ?, ?, ?, ?)
        """, (name, amazon_url, ebay_url, amazon_img, ebay_img))

        if cursor.lastrowid:
            product_id = cursor.lastrowid
            print("Product inserted successfully")
            return product_id

        cursor.execute("SELECT id FROM products WHERE name = ?", (name,))
        product_id = cursor.fetchone()[0]
        #print(f"Product already exists — id = {product_id}")
        return product_id


#-------------------------------------------
def price_insertion(product_id, amazon_price, ebay_price, confidence, best_deal):
    with sqlite3.connect("products.db") as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO price_history (
                product_id,
                amazon_price,
                ebay_price,
                confidence,
                best_deal,
                date
            )
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (product_id, amazon_price, ebay_price, confidence, best_deal))

        conn.commit()
        print("price history inserted successfully")


#--------------------------------
def load_args_json(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data


#----------------------------------
def clean_ebay_url(url):
    if url is None:
        return None

    match = re.match(r'(https://www\.ebay\.com/itm/\d+)', url)
    if match:
        return match.group(1)

    # fallback: force https
    match = re.match(r'https?://(?:www\.)?ebay\.com/itm/(\d+)', url)
    return f"https://www.ebay.com/itm/{match.group(1)}" if match else url


#--------------------------------------------
async def scrape_product(context, product_url):
    page = await context.new_page()
    try:
        await page.goto(product_url, timeout=30000, wait_until="domcontentloaded")

        title_el = page.locator("span#productTitle")
        img = page.locator("#landingImage")

        if await title_el.count() == 0 and await img.count() == 0:
            return

        title = await title_el.text_content()
        img_url = await page.locator("#landingImage").get_attribute("src")
        await asyncio.sleep(2)

    except Exception as e:
        print(f"Error on {product_url}: {e}")
        return None

    finally:
        await page.close()

    return title, product_url, img_url


#---------------------------------

async def scrape_amazon(context, semaphore, Product_Name):
    FILLER_WORDS = [
        "the", "and", "or", "with", "for", "to", "of", "in", "on", "by",
        "from", "at", "a", "an", "new", "best", "premium", "quality",
        "original", "official", "authentic", "genuine", "sale", "deal",
        "offer", "free", "shipping", "available", "stock", "amazing",
        "ultra", "super", "compatible", "includes", "including", "sealed",
        "bundle", "kit", "set", "portable", "smart"
    ]

    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, amazon_url, amazon_img
        FROM products
        WHERE name = ?
    """, (Product_Name,))

    row = cursor.fetchone()
    conn.close()

    if row:
        id, name, url, amazon_img = row
        #print(f"Product exists\nID: {id}\nName: {name}\nURL: {url}")

        page = await context.new_page()
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")

        continue_button = page.get_by_role("button", name="Continue shopping")
        if await continue_button.count() > 0:
            await continue_button.click()
            await asyncio.sleep(2)
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

        p_w = None
        if await page.locator("[id*='corePrice'] .a-offscreen").count() > 0:
            product_price = page.locator("[id*='corePrice'] .a-offscreen").first
            p_w = await product_price.text_content(timeout=5000)
            #print(f"price of the prodcut is : {p_w}")
        else:
            print("")

        await page.close()
        return name, p_w, url, amazon_img

    else:
        async with semaphore:
            try:
                reference_Product = Product_Name
                numbers_reference_product = re.findall(r'-?\d+\.?\d*', reference_Product)
                best_matching_prodcuct = []
                reference_words = set(re.findall(r'\b\w+\b', reference_Product.lower()))
                word_count = len(reference_words)

                page = await context.new_page()
                await page.goto("https://www.amazon.com", timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                await page.locator("#twotabsearchtextbox").press_sequentially(Product_Name, delay=300)
                await asyncio.sleep(4)
                await page.locator("#nav-search-submit-button").click()
                await asyncio.sleep(6)

                links = page.locator('a[href*="/dp/"]')
                count = await links.count()

                product_urls = []
                for i in range(count):
                    link = links.nth(i)
                    href = await link.get_attribute("href")
                    if href and "/dp/" in href:
                        parts = href.strip('/').split('/')
                        dp_index = parts.index("dp")
                        asin = parts[dp_index + 1]
                        product_urls.append("https://www.amazon.com/dp/" + asin + "/")

                seen = set()
                unique_urls = []
                for url in product_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)

                product_urls = unique_urls[:5]

                chunk_size = 1
                for i in range(0, len(product_urls), chunk_size):
                    chunk = product_urls[i:i + chunk_size]
                    best_matching_prodcuct.extend(
                        await asyncio.gather(*[scrape_product(context, url) for url in chunk])
                    )
                    await asyncio.sleep(4)

                best_match = None
                best_url = None
                best_img = None
                max_overlap = -1

                for item in best_matching_prodcuct:
                    if item is None:
                        continue

                    cand, url, img = item
                    cand_words = set(re.findall(r'\b\w+\b', cand.lower()))
                    overlap_count = len(reference_words.intersection(cand_words)) - (
                        word_count - len(reference_words.intersection(cand_words))
                    ) - 0.01 * len((cand_words - reference_words))

                    if overlap_count > max_overlap:
                        max_overlap = overlap_count
                        best_match = cand
                        best_url = url
                        best_img = img

                if best_url is None:
                    print("No matching product found on Amazon — possible anti-bot block")
                    return

                #print(best_url)
                #print(f"Most matching words ({max_overlap}):\n-> '{best_match}'")
                #print(best_img)

                await page.goto(best_url, timeout=30000, wait_until="domcontentloaded")

                p_w = None
                if await page.locator("[id*='corePrice'] .a-offscreen").count() > 0:
                    product_price = page.locator("[id*='corePrice'] .a-offscreen").first
                    p_w = await product_price.text_content(timeout=5000)
                    #print(f"price of the prodcut is : {p_w}")
                else:
                    #print("price is unavailable")
                    print("")


                best_match = best_match.lower()
                remove_set = set(FILLER_WORDS)
                clean_text = best_match.translate(str.maketrans('', '', string.punctuation))
                filtered_words = [
                    word for word in clean_text.split()
                    if word.lower() not in remove_set
                ]

                existing_numbers = set(re.findall(r'-?\d+\.?\d*', " ".join(filtered_words)))
                missing_numbers = [n for n in numbers_reference_product if n not in existing_numbers]

                short_query_words = filtered_words[:6]
                result = " ".join(short_query_words) + (
                    " " + " ".join(missing_numbers) if missing_numbers else ""
                )

                #print(result)

                if result:
                    await page.close()
                    return result, p_w, best_url, best_img

            except Exception as e:
                print(e)

#--------------------------------
async def scrape_ebay(context, Product_Name, cleaned_title, numbers_reference_product):
    FILLER_WORDS = [
        "the", "and", "or", "with", "for", "to", "of", "in", "on", "by",
        "from", "at", "a", "an", "new", "best", "premium", "quality",
        "original", "official", "authentic", "genuine", "sale", "deal",
        "offer", "free", "shipping", "available", "stock", "amazing",
        "ultra", "super", "compatible", "includes", "including", "sealed",
        "bundle", "kit", "set", "portable", "smart"
    ]

    conn = sqlite3.connect("products.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, ebay_url, ebay_img
        FROM products
        WHERE name = ?
    """, (Product_Name,))

    row = cursor.fetchone()

    if row:
        cursor.execute("""
            SELECT confidence
            FROM price_history
            WHERE product_id = ?
            ORDER BY date DESC
            LIMIT 1
        """, (row[0],))

        confidence_row = cursor.fetchone()
        confidence = confidence_row[0] if confidence_row else 0
        conn.close()

        id, name, url, ebay_img = row
        page1 = await context.new_page()
        #print(f"Before clean: {url}")
        ebay_url = clean_ebay_url(url)
        #print(f"After clean: {ebay_url}")
        ebay_url = clean_ebay_url(url)

        await page1.goto("https://www.ebay.com", timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        #await page1.goto(ebay_url, timeout=30000, wait_until="domcontentloaded")
        await page1.goto(ebay_url, timeout=30000, wait_until="domcontentloaded")
        # missing this line

        price_ebay = await page1.locator('[data-testid="x-price-primary"] .ux-textspans').first.inner_text()
        #print(f"Product exists\nID: {id}\nName: {name}\nURL: {url}")
        return url, ebay_img, price_ebay, confidence

    else:
        try:
            page1 = await context.new_page()
            await page1.goto("https://www.ebay.com/", timeout=90000, wait_until="domcontentloaded")
            await page1.locator("#gh-ac").wait_for(state="attached")
            await page1.locator("#gh-ac").type(cleaned_title, delay=100)
            await page1.locator("#gh-search-btn").click()
            #print("ebay")
            await page1.wait_for_selector("li.s-card")

            products_ebay = page1.locator("li.s-card")
            products_ebay_store = []
            count = min(await products_ebay.count(), 10)

            for i in range(count):
                item = products_ebay.nth(i)
                title = await item.locator("div.s-card__title span.su-styled-text").text_content()
                price = await item.locator("span.s-card__price:has-text('$')").first.text_content()
                url = await item.locator("div.su-image a.s-card__link").first.get_attribute("href")
                img = await item.locator("img.s-card__image").first.get_attribute("src")

                title = title.lower()
                remove_set = set(FILLER_WORDS)
                clean_text = title.translate(str.maketrans('', '', string.punctuation))
                filtered_words = [
                    word for word in clean_text.split()
                    if word.lower() not in remove_set
                ]
                result_ebay = " ".join(filtered_words)
                numbers = re.findall(r'-?\d+\.?\d*', clean_text)

                products_ebay_store.append({
                    "title": result_ebay,
                    "price": price,
                    "url": url,
                    "image": img,
                    "numbers": numbers
                })

            best_match = None
            best_url_ebay = None
            best_price_ebay = None
            best_image_ebay = None
            best_score = 0

            result_words = set(re.findall(r'\b\w+\b', cleaned_title.lower()))

            for item in products_ebay_store:
                if not item:
                    continue

                cand = item['title']
                cand_words = set(re.findall(r'\b\w+\b', cand.lower()))
                intersection = len(result_words.intersection(cand_words))
                union = len(result_words.union(cand_words))

                if union == 0:
                    continue

                score = intersection / union
                if score > best_score:
                    best_score = score
                    best_match = cand
                    best_url_ebay = item['url']
                    best_price_ebay = item['price']
                    best_image_ebay = item['image']

            confidence = round(best_score * 100, 1)

            if confidence < 60:
                #print("No exact match found on eBay but heres we got ")
                #print(f"Best eBay match ({confidence}% confidence): {best_match}")
                #print(f"eBay URL: {best_url_ebay}")
                #print(f"price :{best_price_ebay}")
                print("")

            else:
                #print(f"Best eBay match ({confidence}% confidence): {best_match}")
                #print(f"eBay URL: {best_url_ebay}")
                #print(f"price :{best_price_ebay}")
                #print(f"image :{best_image_ebay}")
                print("")

            return best_url_ebay, best_image_ebay, best_price_ebay, confidence

        except Exception as e:
            print(e)


#-------------------------------- async def main():
async def main():
    def normalize(price):
        if not price or price.strip() == "":
            return None

        # remove currency symbols and prefixes
        price = re.sub(r'[^\d.]', '', price)

        try:
            return float(price)
        except:
            return None

    database_creation()

    config_path = "config.json"
    if not os.path.exists(config_path):
        logger.error(
            "config.json not found. Current working directory: %s — "
            "make sure config.json is present in that directory.",
            os.getcwd()
        )
        return

    try:
        arguments = load_args_json(config_path)
    except json.JSONDecodeError:
        logger.exception("config.json exists but contains malformed JSON — cannot parse it.")
        return
    except Exception:
        logger.exception("Unexpected error while loading config.json (cwd: %s).", os.getcwd())
        return

    products = arguments['products']
    logger.info("Config loaded successfully. Products to scrape (%d): %s", len(products), products)
    semaphore = asyncio.Semaphore(3)

    try:
        playwright_ctx = async_playwright()
        playwright = await playwright_ctx.__aenter__()
    except Exception:
        logger.exception("Failed to start Playwright.")
        return

    try:
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-automation',
                '--no-sandbox',
            ]
        )
    except Exception:
        logger.exception("Failed to launch Chromium browser.")
        await playwright_ctx.__aexit__(None, None, None)
        return

    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
    except Exception:
        logger.exception("Failed to create browser context.")
        await browser.close()
        await playwright_ctx.__aexit__(None, None, None)
        return

    amazon_results = await asyncio.gather(
        *[scrape_amazon(context, semaphore, product) for product in products]
    )

    # in main() loop, after unpacking amazon_result:
    #numbers_reference_product = re.findall(r'-?\d+\.?\d*', product)
    for product, amazon_result in zip(products, amazon_results):
        #for amazon_result in amazon_results:
        if amazon_result is None or isinstance(amazon_result, Exception):
            continue

        cleaned_title, amazon_price, amazon_url, amazon_img = amazon_result
        numbers_reference_product = re.findall(r'-?\d+\.?\d*', product)

        ebay_result = await scrape_ebay(
            context,
            product,
            cleaned_title,
            numbers_reference_product
        )

        if ebay_result is None:
            continue

        ebay_url, ebay_img, ebay_price, confidence = ebay_result

        product_id = product_insertion(product, amazon_url, ebay_url, amazon_img, ebay_img)

        amazon_price = normalize(amazon_price)
        ebay_price = normalize(ebay_price)

        best_deal = None
        if amazon_price is not None and ebay_price is not None:
            best_deal = "amazon" if amazon_price < ebay_price else "ebay"
        elif amazon_price is not None:
            best_deal = "amazon"
        elif ebay_price is not None:
            best_deal = "ebay"
        else:
            best_deal = None

        price_insertion(
            product_id,
            amazon_price,
            ebay_price,
            confidence,
            best_deal
        )

    await browser.close()
    await playwright_ctx.__aexit__(None, None, None)
    logger.info("Scrape cycle completed successfully — %d products processed.", len(products))


if __name__ == "__main__":
    asyncio.run(main())
