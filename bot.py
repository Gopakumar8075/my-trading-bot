from flask import Flask, request, jsonify
import ccxt
import os
import json

app = Flask(__name__)

# --- Load credentials ---
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-if-not-set")

# --- Safety check ---
if not API_KEY or not API_SECRET:
    print("❌ API_KEY or API_SECRET is missing. Set them in environment variables.")
    exit(1)

# --- Connect to Delta Exchange ---
try:
    exchange = ccxt.delta({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'options': {
            'defaultType': 'future',
        },
        'enableRateLimit': True
    })
    exchange.load_markets()
    print("✅ Exchange connected and markets loaded.")
except Exception as e:
    print(f"❌ Error connecting to exchange: {e}")
    exchange = None

# --- Webhook route ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Handle both JSON and raw string payload
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode('utf-8'))
        print(f"📨 Webhook received: {data}")
    except Exception as e:
        print(f"❌ Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    # Security check
    if data.get('secret') != SECRET_KEY:
        print("🚨 Invalid secret key.")
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    symbol = data.get('symbol')
    side = data.get('side')
    action = data.get('action')
    qty_percent = float(data.get('qty_pct', 0))
    leverage = int(data.get('leverage', 1))

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol is required"}), 400

    if not exchange:
        return jsonify({"status": "error", "message": "Exchange not connected"}), 500

    try:
        # Reload markets to ensure symbol list is up to date
        markets = exchange.load_markets()
        if symbol not in markets:
            print(f"❌ Symbol {symbol} not found in market list.")
            return jsonify({"status": "error", "message": f"Symbol {symbol} not found"}), 400

        # Set leverage
        try:
            exchange.set_leverage(leverage, symbol)
            print(f"⚙️ Leverage set to {leverage}x for {symbol}")
        except Exception as le:
            print(f"⚠️ Failed to set leverage: {le}")

        if side == 'buy':
            balance = exchange.fetch_balance()
            quote_currency = 'USDT'
            available_balance = balance['free'].get(quote_currency, 0)
            print(f"💰 Available balance: {available_balance:.2f} {quote_currency}")

            amount_to_spend = available_balance * (qty_percent / 100)
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            quantity = amount_to_spend / current_price

            print(f"🛒 Placing MARKET BUY order for {quantity:.5f} of {symbol}")
            order = exchange.create_market_buy_order(symbol, quantity)
            print("✅ Order placed:", order)
            return jsonify({"status": "success", "order": order}), 200

        elif action == 'close':
            positions = exchange.fetch_positions([symbol])
            position = next((p for p in positions if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0), None)

            if position:
                qty = float(position['contracts'])
                print(f"❌ Closing position: MARKET SELL for {qty} of {symbol}")
                order = exchange.create_market_sell_order(symbol, qty, {'reduceOnly': True})
                print("✅ Close order placed:", order)
                return jsonify({"status": "success", "order": order}), 200
            else:
                print(f"ℹ️ No open position found for {symbol}")
                return jsonify({"status": "info", "message": "No position to close"}), 200

        else:
            return jsonify({"status": "error", "message": "Invalid side/action specified"}), 400

    except ccxt.BaseError as e:
        print(f"💥 CCXT Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print(f"❌ General Error: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

# --- Health check ---
@app.route('/')
def health():
    return "✅ Bot is running."

# --- Entry point ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
