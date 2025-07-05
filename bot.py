from flask import Flask, request, jsonify
import os
import ccxt

app = Flask(__name__)

# Load environment variables from Render
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "test1234")  # Default secret key

# Check if API keys are present in the environment
if not API_KEY or not API_SECRET:
    raise Exception("CRITICAL: Missing API_KEY or API_SECRET in environment variables. Please check your Render dashboard.")

# --- Exchange Connection Block ---
# This block initializes the connection to Delta Exchange.
# Based on their official documentation, we are explicitly setting the URL
# to point to the testnet/demo server. This is the most reliable method.
try:
    print("Attempting to connect to Delta Exchange Testnet...")
    
    exchange = ccxt.delta({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future'
        },
        # THIS IS THE CRITICAL FIX: Forcing the use of the Testnet URL
        'urls': {
            'api': {
                'public': 'https://testnet-api.delta.exchange',
                'private': 'https://testnet-api.delta.exchange',
            }
        }
    })

    # The line below is no longer needed, but we check if the connection works.
    exchange.load_markets() # A good way to test the connection early.
    print("SUCCESS: Connection to Delta Exchange TESTNET established.")

except Exception as e:
    # If this block runs, the app will stop. Check logs for the error.
    raise Exception(f"Error initializing exchange connection: {e}")
# --- End of Connection Block ---


@app.route('/')
def home():
    """ A simple route to confirm the bot is online. """
    return "Webhook Bot is live and running!"


@app.route('/webhook', methods=['POST'])
def webhook():
    """
    This is the main endpoint that receives alerts from TradingView.
    """
    try:
        data = request.get_json(force=True)
        print(f"Webhook received: {data}")
    except Exception as e:
        print(f"Error: Could not parse incoming JSON. Reason: {e}")
        return jsonify({"status": "error", "message": f"Invalid JSON: {e}"}), 400

    # Validate the secret key to ensure the request is from a trusted source
    if data.get("secret") != SECRET_KEY:
        print(f"Error: Invalid secret key. Expected '{SECRET_KEY}', but received '{data.get('secret')}'.")
        return jsonify({"status": "error", "message": "Invalid secret key"}), 403

    # Extract data from the webhook payload
    symbol = data.get("symbol")
    side = data.get("side")
    action = data.get("action")
    
    try:
        qty_pct = float(data.get("qty_pct", 0))
    except (ValueError, TypeError):
        qty_pct = 0

    if not symbol:
        return jsonify({"status": "error", "message": "Missing 'symbol' in webhook data"}), 400

    try:
        # --- Trading Logic ---
        if side == "buy":
            print(f"Processing BUY order for {symbol}...")
            # Fetch balance and market price to calculate order size
            balance = exchange.fetch_balance()
            quote_currency = "USDT" # Perpetual contracts on Delta are quoted in USDT
            available_balance = balance['free'].get(quote_currency, 0)
            print(f"Available balance: {available_balance} {quote_currency}")

            if available_balance <= 0:
                 return jsonify({"status": "error", "message": f"Insufficient balance. 0 {quote_currency} available."}), 400

            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker['last']
            amount = (available_balance * qty_pct / 100) / last_price

            # Create the market buy order
            order = exchange.create_market_buy_order(symbol, amount)
            print(f"SUCCESS: Buy Order executed: {order}")
            return jsonify({"status": "success", "order": order}), 200

        elif action == "close":
            print(f"Processing CLOSE signal for {symbol}...")
            # Fetch open positions to find the one to close
            positions = exchange.fetch_positions([symbol])
            # Find the specific position for the symbol with a positive size
            pos = next((p for p in positions if p.get('symbol') == symbol and float(p.get("contracts", 0)) > 0), None)

            if pos:
                qty = float(pos["contracts"])
                # Create a market sell order with reduceOnly to close the position
                order = exchange.create_market_sell_order(symbol, qty, {"reduceOnly": True})
                print(f"SUCCESS: Close Order executed: {order}")
                return jsonify({"status": "success", "order": order}), 200
            else:
                print("Info: No open position found to close.")
                return jsonify({"status": "info", "message": "No open position to close"}), 200

        else:
            return jsonify({"status": "error", "message": "Invalid 'side' or 'action' in webhook"}), 400

    except ccxt.BaseError as e:
        # Catch specific CCXT errors for better logging
        print(f"ERROR (CCXT): An error occurred with the exchange: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        # Catch any other unexpected errors
        print(f"ERROR (General): An unexpected error occurred: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # Get the port from Render's environment variable, defaulting to 10000 for local testing
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
