from flask import Flask, request, jsonify, render_template
from datetime import datetime
import sqlite3
import threading

app = Flask(__name__)

# Initialize database
def init_db():
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS executions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  player TEXT,
                  userId INTEGER,
                  placeId INTEGER,
                  jobId TEXT,
                  timestamp INTEGER)''')
    conn.commit()
    conn.close()

init_db()

# API endpoint
@app.route('/track', methods=['POST'])
def track():
    data = request.json
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()
    c.execute("INSERT INTO executions (player, userId, placeId, jobId, timestamp) VALUES (?, ?, ?, ?, ?)",
              (data['player'], data['userId'], data['placeId'], data['jobId'], data['timestamp']))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# Dashboard
@app.route('/')
def dashboard():
    conn = sqlite3.connect('tracker.db')
    c = conn.cursor()
    c.execute("SELECT * FROM executions ORDER BY timestamp DESC LIMIT 100")
    executions = c.fetchall()
    c.execute("SELECT COUNT(*) FROM executions")
    total = c.fetchone()[0]
    conn.close()
    
    # Format data for HTML
    formatted = []
    for e in executions:
        formatted.append({
            'player': e[1],
            'userId': e[2],
            'placeId': e[3],
            'jobId': e[4],
            'time': datetime.fromtimestamp(e[5]).strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return render_template('dashboard.html', executions=formatted, total=total)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)