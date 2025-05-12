from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, abort
import sqlite3
import uuid
import datetime
import requests
import os
import functools
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/scripts'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['SECRET_KEY'] = 'FT&G^F%NBUI@##BYU#G^&#VGU'  # Replace with your own secret key

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  username TEXT, 
                  hwid TEXT, 
                  api_key TEXT UNIQUE, 
                  blacklisted INTEGER DEFAULT 0,
                  last_execution TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS executions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  script_name TEXT, 
                  execution_time TEXT,
                  FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS webhooks 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  url TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Modified API Key authentication decorator to avoid endpoint conflicts
def api_key_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-KEY') or request.args.get('api_key')
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
            
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id, blacklisted FROM users WHERE api_key=?", (api_key,))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Invalid API key'}), 401
        if user[1] == 1:  # Check if blacklisted
            return jsonify({'error': 'User is blacklisted'}), 403
            
        return f(*args, **kwargs)
    return wrapper

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/execute', methods=['POST'])
@api_key_required
def execute_script():
    data = request.json
    username = data.get('username')
    hwid = data.get('hwid')
    script_name = data.get('script_name')
    
    # Get API key from request
    api_key = request.headers.get('X-API-KEY') or request.args.get('api_key')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Update or create user
    c.execute("SELECT id FROM users WHERE api_key=?", (api_key,))
    user = c.fetchone()
    
    if user:
        user_id = user[0]
        c.execute("UPDATE users SET username=?, hwid=?, last_execution=? WHERE id=?", 
                 (username, hwid, datetime.datetime.now().isoformat(), user_id))
    else:
        c.execute("INSERT INTO users (username, hwid, api_key, last_execution) VALUES (?, ?, ?, ?)",
                 (username, hwid, api_key, datetime.datetime.now().isoformat()))
        user_id = c.lastrowid
    
    # Log execution
    c.execute("INSERT INTO executions (user_id, script_name, execution_time) VALUES (?, ?, ?)",
             (user_id, script_name, datetime.datetime.now().isoformat()))
    
    conn.commit()
    
    # Get webhook URL
    c.execute("SELECT url FROM webhooks LIMIT 1")
    webhook_url = c.fetchone()
    
    conn.close()
    
    # Send to Discord webhook if configured
    if webhook_url and webhook_url[0]:
        payload = {
            "content": f"New script execution from {username}",
            "embeds": [{
                "title": "Script Execution",
                "description": f"User: {username}\nHWID: {hwid}\nScript: {script_name}",
                "color": 0x9933ff,
                "timestamp": datetime.datetime.now().isoformat()
            }]
        }
        try:
            requests.post(webhook_url[0], json=payload)
        except:
            pass
    
    return jsonify({'status': 'success'})

@app.route('/blacklist', methods=['POST'])
@api_key_required
def blacklist_user():
    data = request.json
    api_key_to_blacklist = data.get('api_key')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET blacklisted=1 WHERE api_key=?", (api_key_to_blacklist,))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/reset_hwid', methods=['POST'])
@api_key_required
def reset_hwid():
    data = request.json
    api_key_to_reset = data.get('api_key')
    new_hwid = str(uuid.uuid4())
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET hwid=? WHERE api_key=?", (new_hwid, api_key_to_reset))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'new_hwid': new_hwid})

@app.route('/script/<path:filename>')
def serve_script(filename):
    # Basic protection - in production you should implement better security
    referrer = request.headers.get('Referer')
    if not referrer or 'onyxlualoader' not in referrer:
        return "Sorry, you can't view this", 403
    
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        abort(404)

@app.route('/upload_script', methods=['POST'])
@api_key_required
def upload_script():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'status': 'success', 'url': f'/script/{filename}'})
    
    return jsonify({'error': 'Upload failed'}), 400

@app.route('/set_webhook', methods=['POST'])
@api_key_required
def set_webhook():
    data = request.json
    webhook_url = data.get('url')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM webhooks")  # Only keep one webhook
    c.execute("INSERT INTO webhooks (url) VALUES (?)", (webhook_url,))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/get_users')
@api_key_required
def get_users():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username, hwid, blacklisted, last_execution FROM users")
    users = [{
        'id': row[0],
        'username': row[1],
        'hwid': row[2],
        'blacklisted': bool(row[3]),
        'last_execution': row[4]
    } for row in c.fetchall()]
    conn.close()
    
    return jsonify(users)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
