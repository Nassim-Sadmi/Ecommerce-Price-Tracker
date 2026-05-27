import sqlite3
from flask import Flask, render_template, jsonify

app = Flask(__name__)


@app.route('/')
def index():
    conn = sqlite3.connect("products.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
SELECT
    products.id,
    products.name,
    products.amazon_img,
    products.ebay_img,
    products.amazon_url,
    products.ebay_url,
    price_history.amazon_price,
    price_history.ebay_price,
    price_history.confidence,
    price_history.best_deal

FROM products
JOIN price_history ON products.id = price_history.product_id
WHERE price_history.date = (
    SELECT MAX(ph2.date) FROM price_history ph2
    WHERE ph2.product_id = products.id
)
ORDER BY products.id
""")    
    inventory = cursor.fetchall()
   

    conn.close()

    return render_template("dashboard.html", products=inventory)


@app.route('/api/price_history/<int:product_id>')
def price_history(product_id):
    conn = sqlite3.connect("products.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
SELECT date, amazon_price, ebay_price
FROM price_history
WHERE product_id = ?
ORDER BY date ASC
""", (product_id,))

    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


if __name__ == '__main__':
    app.run(debug=True)