from flask import Flask, request, jsonify
import os
import ccxt

app = Flask(__name__)

# Load environment variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "test1234")

# Validate presence of keys
if not API_KEY or not API_SECRET:
    raise Exception("Missing API_KEY or API_SECRET environment variables")

# Connect to Delta Exchange
exchange = ccxt.delta({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("Webhook received:", data)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Invalid JSON: {e}"}), 400

    # Validate secret key
    if data.get("secret") != SECRET_KEY:
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    product_id = data.get("product_id")
    side = data.get("side")
    action = data.get("action")
    qty_pct = float(data.get("qty_pct", 0))

    if not product_id:
        return jsonify({"status": "error", "message": "Missing product_id"}), 400

    try:
        # Fetch available balance
        balance = exchange.fetch_balance()
        quote = "USDT"
        available = balance['free'][quote]

        if side == "buy":
            ticker = exchange.fetch_ticker("ETH/USD")  # needed to get price
            price = ticker["last"]
            amount = (available * qty_pct / 100) / price
            order = exchange.create_order(
                symbol="ETH/USD",
                type="market",
                side="buy",
                amount=amount,
                params={"product_id": product_id}
            )
            return jsonify({"status": "success", "order": order}), 200

        elif action == "close":
            positions = exchange.fetch_positions()
            pos = next((p for p in positions if p['symbol'] == "ETH/USD" and float(p.get("contracts", 0)) > 0), None)
            if pos:
                qty = float(pos["contracts"])
                order = exchange.create_order(
                    symbol="ETH/USD",
                    type="market",
                    side="sell",
                    amount=qty,
                    params={"reduceOnly": True, "product_id": product_id}
                )
                return jsonify({"status": "success", "order": order}), 200
            else:
                return jsonify({"status": "info", "message": "No position to close"}), 200

        return jsonify({"status": "error", "message": "Invalid command"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def health():
    return "Webhook Bot Running!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
