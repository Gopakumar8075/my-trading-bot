from flask import Flask, request, jsonify
import ccxt
import os
import json

app = Flask(__name__)

# Security: Secret key from environment variable
SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-if-not-set")

# --- Connect to Delta Exchange ---
try:
    exchange = ccxt.delta({
        'apiKey': os.getenv('API_KEY'),
        'secret': os.getenv('API_SECRET'),
        'options': {
            'defaultType': 'future',
        },
        'enableRateLimit': True
    })
    print("Exchange connected successfully.")
except Exception as e:
    print(f"Error connecting to exchange: {e}")
    exchange = None

# --- Webhook Endpoint ---
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Handles both proper JSON and TradingView's text/plain
        if request.is_json:
            data = request.get_json()
        else:
            data = json.loads(request.data.decode('utf-8'))
        print(f"Webhook received: {data}")
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400

    if data.get('secret') != SECRET_KEY:
        print("Security alert: Invalid secret key.")
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    symbol = data.get('symbol')
    side = data.get('side')
    action = data.get('action')
    qty_percent = float(data.get('qty_pct', 0))
    leverage = int(data.get('leverage', 1))  # Optional: default to 1

    if not symbol:
        return jsonify({"status": "error", "message": "Symbol is required"}), 400

    if not exchange:
        return jsonify({"status": "error", "message": "Exchange not connected"}), 500

    try:
        # Set leverage (only needed once per symbol per session)
        markets = exchange.load_markets()
        if symbol in markets:
            market = markets[symbol]
            exchange.set_leverage(leverage, symbol)
            print(f"Leverage set to {leverage}x for {symbol}")
        else:
            print(f"Symbol {symbol} not found in market list.")

        if side == 'buy':
            balance = exchange.fetch_balance()
            quote_currency = 'USDT'
            available_balance = balance['free'].get(quote_currency, 0)
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
            position = next((p for p in positions if p['symbol'] == symbol and float(p.get('contracts', 0)) > 0), None)

            if position:
                qty = float(position['contracts'])
                print(f"Closing position: MARKET SELL for {qty} of {symbol}")
                order = exchange.create_market_sell_order(symbol, qty, {'reduceOnly': True})
                print("Close order result:", order)
                return jsonify({"status": "success", "order": order}), 200
            else:
                print(f"No open position found for {symbol}")
                return jsonify({"status": "info", "message": "No position to close"}), 200

        else:
            return jsonify({"status": "error", "message": "Invalid side/action specified"}), 400

    except ccxt.BaseError as e:
        print(f"CCXT Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({"status": "error", "message": "Internal error occurred"}), 500

@app.route('/')
def health_check():
    return "Bot is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
