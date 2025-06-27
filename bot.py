from flask import Flask, request, jsonify
import ccxt
import os
import json

# --- CONFIGURATION ---
app = Flask(__name__)

# Security: Your secret key from Render's environment variables.
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-if-not-set")

# Exchange Connection
try:
    exchange = ccxt.binance({
        'apiKey': os.getenv('API_KEY'),
        'secret': os.getenv('API_SECRET'),
        'options': {
            'defaultType': 'future', # IMPORTANT: change to 'spot' if you trade spot
        },
        'enableRateLimit': True
    })
    # For paper trading on Binance Testnet, uncomment the line below:
    # exchange.set_sandbox_mode(True)
    print("Exchange connected successfully.")
except Exception as e:
    print(f"Error connecting to exchange: {e}")
    exchange = None

# --- WEBHOOK LISTENER ---
@app.route('/webhook', methods=['POST'])
def webhook():
    # 1. Receive and validate the message
    try:
        data = request.get_json()
        print(f"Webhook received: {data}")
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    if data.get('secret') != SECRET_KEY:
        print("Security alert: Invalid secret key.")
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    # 2. Parse the command
    symbol = data.get('symbol')
    side = data.get('side')
    action = data.get('action')
    qty_percent = float(data.get('qty_pct', 0))

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol is required"}), 400

    if not exchange:
        return jsonify({"status": "error", "message": "Exchange not connected"}), 500

    # 3. Execute the Action
    try:
        if side == 'buy':
            balance = exchange.fetch_balance()
            quote_currency = 'USDT' # The currency you use to buy
            available_balance = balance['free'][quote_currency]
            print(f"Available balance: {available_balance:.2f} {quote_currency}")

            amount_to_spend = available_balance * (qty_percent / 100)
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            quantity = amount_to_spend / current_price
            
            print(f"Placing MARKET BUY order for {quantity:.5f} of {symbol}")
            order = exchange.create_market_buy_order(symbol, quantity)
            print("Order result:", order)
            return jsonify({"status": "success", "order": order}), 200

        elif action == 'close':
            positions = exchange.fetch_positions([symbol])
            position_to_close = next((p for p in positions if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0), None)

            if position_to_close:
                quantity_to_close = float(position_to_close['contracts'])
                print(f"Closing position: Placing MARKET SELL for {quantity_to_close} of {symbol}")
                order = exchange.create_market_sell_order(symbol, quantity_to_close, {'reduceOnly': True})
                print("Close order result:", order)
                return jsonify({"status": "success", "order": order}), 200
            else:
                print(f"No open position found for {symbol} to close.")
                return jsonify({"status": "info", "message": "No position to close"}), 200

        else:
            return jsonify({"status": "error", "message": "Invalid side/action specified"}), 400

    except ccxt.BaseError as e:
        print(f"An CCXT error occurred: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print(f"A general error occurred: {e}")
        return jsonify({"status": "error", "message": "An internal error occurred"}), 500

# Health check route
@app.route('/')
def health_check():
    return "Bot is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
