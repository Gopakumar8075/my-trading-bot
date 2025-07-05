from flask import Flask, request, jsonify
import os
import ccxt

app = Flask(__name__)

# Load environment variables
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "test1234")  # Should match TradingView Pine alert

# Check API key presence
if not API_KEY or not API_SECRET:
    raise Exception("Missing API_KEY or API_SECRET in environment variables")

# Initialize exchange connection
try:
    exchange = ccxt.delta({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'  # Use 'spot' if you're trading spot
        }
    })
    print("Connected to Delta Exchange")
except Exception as e:
    raise Exception(f"Error initializing exchange: {e}")


@app.route('/')
def home():
    return "Webhook Bot is live!"


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

    symbol = data.get("symbol")          # e.g., "ETH-PERP" (Delta future)
    side = data.get("side")              # "buy" for entry
    action = data.get("action")          # "close" to exit
    qty_pct = float(data.get("qty_pct", 0))

    if not symbol:
        return jsonify({"status": "error", "message": "Missing symbol"}), 400

    try:
        # Fetch balance
        balance = exchange.fetch_balance()
        quote_currency = "USDT"
        available_balance = balance['free'].get(quote_currency, 0)

        if side == "buy":
            # Get market price
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker['last']
            amount = (available_balance * qty_pct / 100) / last_price

            # Place buy order
            order = exchange.create_order(
                symbol=symbol,
                type="market",
                side="buy",
                amount=exchange.amount_to_precision(symbol, amount),
            )
            print("Buy Order:", order)
            return jsonify({"status": "success", "order": order}), 200

        elif action == "close":
            positions = exchange.fetch_positions()
            pos = next((p for p in positions if p['symbol'] == symbol and float(p.get("contracts", 0)) > 0), None)

            if pos:
                qty = float(pos["contracts"])
                order = exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side="sell",
                    amount=exchange.amount_to_precision(symbol, qty),
                    params={"reduceOnly": True}
                )
                print("Close Order:", order)
                return jsonify({"status": "success", "order": order}), 200
            else:
                return jsonify({"status": "info", "message": "No open position to close"}), 200

        return jsonify({"status": "error", "message": "Invalid side/action"}), 400

    except Exception as e:
        print("Error processing order:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
