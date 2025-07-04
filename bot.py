from flask import Flask, request, jsonify
from delta_rest_client import DeltaRestClient
import os

app = Flask(__name__)

# Load env variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "test1234")

# Connect to Delta
try:
   delta = DeltaRestClient(access_key=API_KEY, access_secret=API_SECRET)
    print("Delta client initialized.")
except Exception as e:
    print("Error initializing Delta client:", e)
    delta = None

# Map symbol to product_id (must match Delta Exchange)
product_map = {
    "ETH-USD": 3136,  # You can add more symbols here
    "BTC-USD": 1
}

@app.route('/')
def health():
    return "Delta Bot Running."

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("Webhook received:", data)
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "detail": str(e)}), 400

    if data.get("secret") != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 403

    symbol = data.get("symbol")
    product_id = product_map.get(symbol)
    side = data.get("side")
    action = data.get("action")
    qty_pct = float(data.get("qty_pct", 0))

    if not product_id:
        return jsonify({"error": f"Symbol '{symbol}' not found in product map"}), 400

    if not delta:
        return jsonify({"error": "Delta client not initialized"}), 500

    try:
        account = delta.get_account()
        usdt_balance = float(account["result"]["balances"]["USDT"]["available_balance"])
        amount_to_use = usdt_balance * (qty_pct / 100)

        # Get current price
        ticker = delta.get_l2_snapshot(product_id=product_id)
        price = float(ticker["result"]["best_ask_price"])
        size = round(amount_to_use / price, 4)

        if side == "buy":
            print(f"Placing MARKET BUY on {symbol} ({product_id}) for size {size}")
            order = delta.create_order(
                product_id=product_id,
                size=size,
                side="buy",
                order_type="market",
                post_only=False
            )
            return jsonify({"status": "success", "order": order}), 200

        elif action == "close":
            positions = delta.get_positions()
            position = next((p for p in positions["result"] if p["product_id"] == product_id), None)

            if position and float(position["size"]) > 0:
                print(f"Closing position for {symbol} with size {position['size']}")
                order = delta.create_order(
                    product_id=product_id,
                    size=position["size"],
                    side="sell",
                    order_type="market",
                    reduce_only=True
                )
                return jsonify({"status": "success", "order": order}), 200
            else:
                return jsonify({"status": "info", "message": f"No open position for {symbol}"}), 200

        return jsonify({"error": "Invalid command"}), 400

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
