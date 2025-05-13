from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import sqlite3
import uuid
import datetime
import requests
import os
import functools
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/scripts'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SECRET_KEY'] = os.urandom(24).hex()

# Database setup
def init_db():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     username TEXT, 
                     hwid TEXT UNIQUE, 
                     blacklisted INTEGER DEFAULT 0,
                     last_execution TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS executions 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     hwid TEXT, 
                     script_name TEXT, 
                     execution_time TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS webhooks 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     url TEXT UNIQUE)''')
        conn.commit()

init_db()

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/execute', methods=['POST'])
def execute_script():
    data = request.json
    username = data.get('username', 'Unknown')
    hwid = data.get('hwid')
    script_name = data.get('script_name', 'Unknown')
    
    if not hwid:
        return jsonify({'error': 'HWID required'}), 400
    
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        
        # Check if user is blacklisted
        c.execute("SELECT blacklisted FROM users WHERE hwid=?", (hwid,))
        user = c.fetchone()
        
        if user and user[0] == 1:
            return jsonify({'error': 'User is blacklisted'}), 403
        
        # Update or create user
        c.execute("INSERT OR REPLACE INTO users (username, hwid, last_execution) VALUES (?, ?, ?)",
                 (username, hwid, datetime.datetime.now().isoformat()))
        
        # Log execution
        c.execute("INSERT INTO executions (hwid, script_name, execution_time) VALUES (?, ?, ?)",
                 (hwid, script_name, datetime.datetime.now().isoformat()))
        
        # Get webhook URL
        c.execute("SELECT url FROM webhooks LIMIT 1")
        webhook_url = c.fetchone()
        
        conn.commit()
    
    # Send to Discord webhook if configured
    if webhook_url and webhook_url[0]:
        send_discord_webhook(webhook_url[0], username, hwid, script_name)
    
    return jsonify({'status': 'success'})

def send_discord_webhook(url, username, hwid, script_name):
    payload = {
        "embeds": [{
            "title": "Script Execution",
            "description": f"**User:** {username}\n**HWID:** `{hwid}`\n**Script:** {script_name}",
            "color": 0x9933ff,
            "timestamp": datetime.datetime.now().isoformat(),
            "footer": {"text": "OnyxLuaLoader"}
        }]
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Webhook error: {e}")

@app.route('/blacklist', methods=['POST'])
def blacklist_user():
    hwid = request.json.get('hwid')
    if not hwid:
        return jsonify({'error': 'HWID required'}), 400
    
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET blacklisted=1 WHERE hwid=?", (hwid,))
        conn.commit()
    
    return jsonify({'status': 'success'})

@app.route('/reset_hwid', methods=['POST'])
def reset_hwid():
    old_hwid = request.json.get('hwid')
    if not old_hwid:
        return jsonify({'error': 'HWID required'}), 400
    
    new_hwid = str(uuid.uuid4())
    
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET hwid=? WHERE hwid=?", (new_hwid, old_hwid))
        conn.commit()
    
    return jsonify({'status': 'success', 'new_hwid': new_hwid})

@app.route('/script/<path:filename>')
def serve_script(filename):
    # Basic referrer check
    if not request.referrer or 'onyxlualoader' not in request.referrer:
        return "Access denied", 403
    
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        abort(404)

@app.route('/upload_script', methods=['POST'])
def upload_script():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    return jsonify({
        'status': 'success', 
        'url': f'/script/{filename}',
        'filename': filename
    })

@app.route('/set_webhook', methods=['POST'])
def set_webhook():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400
    
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO webhooks (id, url) VALUES (1, ?)", (url,))
        conn.commit()
    
    return jsonify({'status': 'success'})

@app.route('/get_users')
def get_users():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("SELECT username, hwid, blacklisted, last_execution FROM users")
        users = [{
            'username': row[0],
            'hwid': row[1],
            'blacklisted': bool(row[2]),
            'last_execution': row[3]
        } for row in c.fetchall()]
    
    return jsonify(users)

@app.route('/get_executions')
def get_executions():
    with sqlite3.connect('database.db') as conn:
        c = conn.cursor()
        c.execute("SELECT hwid, script_name, execution_time FROM executions ORDER BY execution_time DESC LIMIT 50")
        executions = [{
            'hwid': row[0],
            'script_name': row[1],
            'execution_time': row[2]
        } for row in c.fetchall()]
    
    return jsonify(executions)

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=False)
