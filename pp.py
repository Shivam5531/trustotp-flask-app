import os
import time
import threading
import requests
from flask import Flask, render_template_string, request

app = Flask(__name__)

# --- TrustOTP CONFIG ---
api_key = "d83spu9hii4ew31ycjdmi6hecd9j7atw"
service = "vision"
country = 14
base_url = "https://trustotp.com/control/api.php"

# --- Global Variables ---
data = {
    "balance": None,
    "status": "Starting...",
    "phone": None,
    "otp": None,
    "error": None,
    "calls": 0,
    "id": None,
    "cancelled": False
}

worker_thread = None

def safe_get(params):
    try:
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        data["calls"] += 1
        return response.text.strip()
    except Exception as e:
        data["error"] = f"Request failed: {e}"
        return None

# --- Main Logic (Background Worker) ---
def background_worker():
    # Reset state
    for k in ["phone", "otp", "error", "id", "cancelled"]:
        data[k] = None
    data["status"] = "Starting..."
    
    # Step 1: Get balance
    data["balance"] = safe_get({"api_key": api_key, "action": "getBalance"})

    # Step 2: Get number
    retry = 0
    while not data["cancelled"]:
        get_number_params = {
            "action": "getNumber",
            "api_key": api_key,
            "service": service,
            "country": country
        }
        result = safe_get(get_number_params)
        if result and "ACCESS_NUMBER" in result:
            parts = result.split(":")
            data["id"] = parts[1]
            data["phone"] = parts[2][-10:]
            data["status"] = "Number Acquired"
            break
        else:
            retry += 1
            data["status"] = f"Retrying to get number... (attempt {retry})"
            time.sleep(2)

    # Step 3: Wait for OTP
    if not data["id"]:
        data["status"] = "Failed to acquire number."
        return

    otp_params = {
        "action": "getStatus",
        "api_key": api_key,
        "id": data["id"]
    }

    start = time.time()
    timeout = 180  # 3 minutes
    while time.time() - start < timeout:
        if data["cancelled"]:
            return

        result = safe_get(otp_params)
        if result and "STATUS_OK" in result:
            data["otp"] = result.split(":")[1].strip('%')
            data["status"] = "✅ OTP Received"
            return
        data["status"] = "⌛ Waiting for OTP..."
        time.sleep(2)

    # Step 4: Timeout cancel
    if data["id"]:
        cancel_activation(data["id"])
        data["status"] = "OTP Timeout - Number Cancelled"

# --- Cancel Activation ---
def cancel_activation(activation_id):
    cancel_params = {
        "action": "setStatus",
        "api_key": api_key,
        "id": activation_id,
        "status": 8
    }
    safe_get(cancel_params)
    data["cancelled"] = True
    data["status"] = "❌ Number Cancelled"

# --- Restart Process ---
def restart_process():
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        data["cancelled"] = True
        time.sleep(1)
    data["cancelled"] = False
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()

# --- Web Routes ---
@app.route("/", methods=["GET"])
def index():
    html = """
    <html>
    <head>
        <title>TrustOTP Dashboard</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { font-family: Arial; background: #111; color: #0f0; padding: 2rem; }
            h1, h2 { color: #0f0; }
            .box { border: 1px solid #0f0; padding: 1rem; margin: 1rem 0; }
            button {
                background: red; color: white; padding: 0.5rem 1rem;
                font-size: 16px; border: none; cursor: pointer; margin-top: 1rem;
            }
            .green-button {
                background: green;
                margin-left: 1rem;
            }
        </style>
    </head>
    <body>
        <h1>🔐 TrustOTP Live Monitor</h1>
        <div class="box">📶 API Calls: {{calls}}</div>
        <div class="box">💰 Balance: {{balance}}</div>
        <div class="box">📱 Number: {{phone}}</div>
        <div class="box">⌛ Status: {{status}}</div>
        <div class="box">🔐 OTP: <b>{{otp}}</b></div>
        {% if error %}
        <div class="box" style="color: red;">❌ Error: {{error}}</div>
        {% endif %}
        <form method="POST" action="/cancel" style="display:inline;">
            {% if id and not cancelled %}
            <button type="submit">❌ Cancel Number</button>
            {% endif %}
        </form>
        <form method="POST" action="/restart" style="display:inline;">
            {% if cancelled or otp %}
            <button type="submit" class="green-button">🔁 Buy Next Number</button>
            {% endif %}
        </form>
    </body>
    </html>
    """
    return render_template_string(html, **data)

@app.route("/cancel", methods=["POST"])
def cancel():
    if data.get("id") and not data["cancelled"]:
        cancel_activation(data["id"])
    return ("", 204)

@app.route("/restart", methods=["POST"])
def restart():
    restart_process()
    return ("", 204)

# --- Run First Time ---
restart_process()

if __name__ == "__main__":
    app.run(debug=True)
