from flask import Flask, request, jsonify
import ccxt
import os

app = Flask(__name__)

# Debug log to verify environment variables
print("DEBUG - API_KEY:", os.getenv("API_KEY"))
print("DEBUG - API_SECRET:", os.getenv("API_SECRET"))
print("DEBUG - SECRET_KEY:", os.getenv("SECRET_KEY"))

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY")

if not API_KEY or not API_SECRET:
    raise ValueError("API_KEY or API_SECRET is missing from environment variables.")

exchange = ccxt.delta({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'options': {'defaultType': 'future'},
    'enableRateLimit': True
})

@app.route('/')
def home():
    return "Bot is running."

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("Webhook received:", data)
    except Exception as e:
        print("Error parsing JSON:", e)
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    if data.get("secret") != SECRET_KEY:
        print("Invalid secret key.")
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    symbol = data.get("symbol")
    side = data.get("side")
    action = data.get("action")
    qty_pct = float(data.get("qty_pct", 100))

    try:
        markets = exchange.load_markets()
        if symbol not in markets:
            print(f"Symbol {symbol} not found in market list.")
            return jsonify({"status": "error", "message": "Invalid symbol"}), 400

        if side == "buy":
            balance = exchange.fetch_balance()
            quote_currency = "USDT"
            available = balance["free"].get(quote_currency, 0)
            print(f"Available balance: {available:.2f} {quote_currency}")
            ticker = exchange.fetch_ticker(symbol)
            price = ticker["last"]
            quantity = available * (qty_pct / 100) / price
            print(f"Buying {quantity:.5f} of {symbol} at {price}")
            order = exchange.create_market_buy_order(symbol, quantity)
            return jsonify({"status": "success", "order": order}), 200

        elif action == "close":
            positions = exchange.fetch_positions([symbol])
            open_position = next((p for p in positions if p["symbol"] == symbol and float(p.get("contracts", 0)) > 0), None)
            if open_position:
                qty = float(open_position["contracts"])
                print(f"Closing position with {qty} contracts of {symbol}")
                order = exchange.create_market_sell_order(symbol, qty, {"reduceOnly": True})
                return jsonify({"status": "success", "order": order}), 200
            else:
                return jsonify({"status": "info", "message": "No open position"}), 200

        else:
            return jsonify({"status": "error", "message": "Unknown action/side"}), 400

    except ccxt.BaseError as e:
        print("CCXT Error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print("Unhandled Exception:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
