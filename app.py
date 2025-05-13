from flask import Flask, render_template, request, jsonify
import json
import requests
from pathlib import Path

app = Flask(__name__)

# File to store the webhook URL and execution count
DATA_FILE = "webhook_data.json"

def load_data():
    try:
        if Path(DATA_FILE).exists():
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"webhook_url": "", "execution_count": 0}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

@app.route('/')
def index():
    data = load_data()
    return render_template('index.html', 
                         webhook_url=data['webhook_url'],
                         execution_count=data['execution_count'])

@app.route('/update_webhook', methods=['POST'])
def update_webhook():
    webhook_url = request.form.get('webhook_url', '')
    data = load_data()
    data['webhook_url'] = webhook_url
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/execute', methods=['GET'])
def track_execution():
    data = load_data()
    data['execution_count'] += 1
    save_data(data)
    
    # Send webhook if configured
    if data['webhook_url']:
        try:
            payload = {
                "content": f"Roblox script executed! Total executions: {data['execution_count']}",
                "username": "Roblox Script Tracker"
            }
            requests.post(data['webhook_url'], json=payload)
        except:
            pass
    
    return jsonify({"status": "success", "execution_count": data['execution_count']})

if __name__ == '__main__':
    app.run(debug=True)
