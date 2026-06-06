# app.py - Complete WhatsApp Bulk Sender Server (Working)
import os
import json
import time
import threading
import base64
import sqlite3
import secrets
import logging
from datetime import datetime
from urllib.parse import quote
from functools import wraps

from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# Initialize Flask App
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global Variables
broadcast_active = False
broadcast_thread = None
driver = None
driver_lock = threading.Lock()
messages_sent = 0
total_messages = 0
server_start_time = datetime.now()
messages_list = []

# Database Setup
DATABASE_PATH = 'whatsapp_data.db'

def init_database():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            country_code TEXT NOT NULL,
            message TEXT,
            status TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def log_message(phone_number, country_code, message, status):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages_log (phone_number, country_code, message, status)
        VALUES (?, ?, ?, ?)
    ''', (phone_number, country_code, message, status))
    conn.commit()
    conn.close()

# Selenium Driver Setup
def init_driver():
    global driver
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-data-dir=/tmp/whatsapp_session")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://web.whatsapp.com")
        logger.info("Driver initialized")
        return True
    except Exception as e:
        logger.error(f"Driver init error: {e}")
        return False

def get_qr_base64():
    global driver
    try:
        if driver is None:
            if not init_driver():
                return None
        
        # Generate QR code data URL
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data("https://web.whatsapp.com")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        logger.error(f"QR error: {e}")
        return None

def check_login_status():
    global driver
    try:
        if driver is None:
            return False
        # Check if logged in by looking for chat list
        driver.find_element(By.XPATH, "//div[@data-testid='chat-list']")
        return True
    except:
        return False

def send_whatsapp_message(phone_number, country_code, message):
    global driver, messages_sent
    try:
        full_number = f"{country_code}{phone_number}".replace("+", "").strip()
        
        with driver_lock:
            if driver is None:
                init_driver()
            
            wa_url = f"https://web.whatsapp.com/send?phone={full_number}&text={quote(message)}"
            driver.get(wa_url)
            time.sleep(3)
            
            try:
                send_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']"))
                )
                send_button.click()
                time.sleep(2)
                
                log_message(phone_number, country_code, message, "sent")
                messages_sent += 1
                logger.info(f"Sent to {full_number}")
                return True
            except:
                log_message(phone_number, country_code, message, "failed")
                return False
    except Exception as e:
        logger.error(f"Send error: {e}")
        log_message(phone_number, country_code, message, "failed")
        return False

def broadcast_worker(delay):
    global broadcast_active, messages_sent, total_messages, messages_list
    try:
        broadcast_active = True
        messages_sent = 0
        total_messages = len(messages_list)
        
        for idx, msg in enumerate(messages_list):
            if not broadcast_active:
                break
            
            phone = msg.get('phone', '')
            country = msg.get('country', '+91')
            text = msg.get('message', '')
            
            if phone and text:
                send_whatsapp_message(phone, country, text)
                time.sleep(delay)
        
        broadcast_active = False
        logger.info(f"Broadcast complete. Sent: {messages_sent}/{total_messages}")
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        broadcast_active = False

# HTML Template (Complete Frontend)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Bulk Sender - Pro Max</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            text-align: center;
        }
        header h1 { color: #667eea; font-size: 2em; margin-bottom: 5px; }
        header p { color: #666; font-size: 0.95em; }
        .uptime-badge {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-top: 10px;
            font-weight: bold;
        }
        .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .card {
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
            transition: transform 0.3s ease;
        }
        .card:hover { transform: translateY(-5px); }
        .card h2 {
            color: #667eea;
            font-size: 1.3em;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .card h2::before {
            content: '';
            display: inline-block;
            width: 4px;
            height: 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 2px;
        }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; color: #333; font-weight: 600; font-size: 0.95em; }
        input[type="text"], input[type="number"], input[type="file"], select, textarea {
            width: 100%;
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 5px;
            font-size: 0.95em;
            font-family: inherit;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            font-size: 0.95em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            margin-right: 10px;
        }
        .btn-primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .btn-primary:hover { transform: scale(1.05); }
        .btn-success { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; }
        .btn-danger { background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); color: white; }
        .btn-secondary { background: #f0f0f0; color: #333; border: 2px solid #e0e0e0; }
        .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }
        .status-active { background: #38ef7d; animation: pulse 2s infinite; }
        .status-inactive { background: #ccc; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .info-box {
            background: #f5f5f5;
            border-left: 4px solid #667eea;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 0.9em;
            color: #666;
        }
        .qr-container {
            text-align: center;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 8px;
            border: 2px dashed #667eea;
        }
        .qr-container img { max-width: 250px; margin: 10px auto; border-radius: 8px; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-card .value { font-size: 1.8em; font-weight: bold; margin: 5px 0; }
        .stat-card .label { font-size: 0.85em; opacity: 0.9; }
        .logs-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 0.9em;
        }
        .logs-table th {
            background: #f0f0f0;
            padding: 10px;
            text-align: left;
            border-bottom: 2px solid #ddd;
        }
        .logs-table td { padding: 10px; border-bottom: 1px solid #eee; }
        .logs-table tr:hover { background: #f9f9f9; }
        .status-sent { color: #38ef7d; font-weight: bold; }
        .status-failed { color: #f45c43; font-weight: bold; }
        .alert {
            padding: 12px;
            border-radius: 5px;
            margin-bottom: 15px;
            display: none;
        }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .alert-info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .alert.show { display: block; }
        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 0.85em;
            font-weight: bold;
            transition: width 0.3s ease;
        }
        .file-upload-area {
            border: 2px dashed #667eea;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: #f9f9f9;
        }
        .file-upload-area:hover { background: #f5f7ff; border-color: #764ba2; }
        .message-preview {
            background: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
            padding: 10px;
            max-height: 200px;
            overflow-y: auto;
            margin-top: 10px;
        }
        @media (max-width: 768px) { .main-grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 WhatsApp Bulk Sender - Pro Max</h1>
            <p>Automated WhatsApp Message Broadcasting System | 24/7 Non-Stop</p>
            <div class="uptime-badge" id="uptimeBadge">⏱️ Server Uptime: Loading...</div>
        </header>

        <div id="successAlert" class="alert alert-success"></div>
        <div id="errorAlert" class="alert alert-error"></div>
        <div id="infoAlert" class="alert alert-info"></div>

        <div class="main-grid">
            <!-- Left Column -->
            <div>
                <div class="card">
                    <h2>🔐 WhatsApp Login</h2>
                    <div class="info-box">
                        <strong>Status:</strong> <span class="status-indicator" id="loginStatus"></span>
                        <span id="loginStatusText">Checking...</span>
                    </div>
                    <div id="qrCodeSection">
                        <p style="margin-bottom: 10px; color: #666;">Scan QR Code with your phone:</p>
                        <div class="qr-container" id="qrContainer">
                            <button class="btn-primary" onclick="getQRCode()">📷 Generate QR Code</button>
                        </div>
                    </div>
                </div>

                <div class="card" style="margin-top: 20px;">
                    <h2>📋 Upload Messages</h2>
                    <div class="info-box">Format: CSV (phone,message) or JSON array</div>
                    <div class="file-upload-area" id="fileUploadArea" onclick="document.getElementById('messagesFile').click()">
                        <p>📁 Click to select CSV/JSON/TXT file</p>
                        <input type="file" id="messagesFile" accept=".csv,.json,.txt" style="display: none;" onchange="uploadMessages()">
                    </div>
                    <div id="fileStatus" style="margin-top: 15px; text-align: center; color: #667eea; font-weight: bold;"></div>
                    <div id="messagePreview" class="message-preview"></div>
                </div>
            </div>

            <!-- Right Column -->
            <div>
                <div class="card">
                    <h2>📤 Broadcast Control</h2>
                    
                    <div class="form-group">
                        <label>🌍 Default Country Code:</label>
                        <input type="text" id="countryCode" placeholder="e.g., 91, 1, 44" value="91">
                    </div>

                    <div class="form-group">
                        <label>⏱️ Delay Between Messages (seconds):</label>
                        <input type="number" id="messageDelay" value="10" min="3" max="300">
                    </div>

                    <div class="form-group">
                        <label>📝 Custom Message Template (optional):</label>
                        <textarea id="messageTemplate" rows="3" placeholder="Enter your message here..."></textarea>
                    </div>

                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="label">Status</div>
                            <div class="value" style="font-size: 1.2em;">
                                <span class="status-indicator" id="broadcastStatus"></span>
                                <span id="broadcastStatusText">Idle</span>
                            </div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Messages Sent</div>
                            <div class="value" id="messagesSent">0</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Total Messages</div>
                            <div class="value" id="totalMessages">0</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Progress</div>
                            <div class="value" id="progressPercent">0%</div>
                        </div>
                    </div>

                    <div class="progress-bar">
                        <div class="progress-fill" id="progressBar"></div>
                    </div>

                    <div style="margin-top: 20px; display: flex; gap: 10px;">
                        <button class="btn-success" onclick="startBroadcast()" id="startBtn" style="flex: 1;">▶️ Start Broadcast</button>
                        <button class="btn-danger" onclick="stopBroadcast()" id="stopBtn" style="flex: 1; opacity: 0.5; cursor: not-allowed;" disabled>⏹️ Stop Broadcast</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📊 Message Logs</h2>
            <div style="display: flex; gap: 10px; margin-bottom: 15px;">
                <button class="btn-secondary" onclick="refreshLogs()">🔄 Refresh Logs</button>
                <button class="btn-danger" onclick="clearLogs()">🗑️ Clear All Logs</button>
            </div>
            <div style="overflow-x: auto; max-height: 400px; overflow-y: auto;">
                <table class="logs-table">
                    <thead><tr><th>Time</th><th>Phone</th><th>Message</th><th>Status</th></tr></thead>
                    <tbody id="logsTbody"><tr><td colspan="4" style="text-align: center;">No logs yet</td></tr></tbody>
                </table>
            </div>
        </div>

        <footer style="text-align: center; margin-top: 20px; color: white;">
            <p>🚀 WhatsApp Bulk Sender Pro Max | Non-Stop Broadcasting | Powered by Flask + Selenium</p>
        </footer>
    </div>

    <script>
        let refreshInterval = null;

        function showAlert(type, message) {
            const alertEl = document.getElementById(`${type}Alert`);
            alertEl.textContent = message;
            alertEl.classList.add('show');
            setTimeout(() => alertEl.classList.remove('show'), 3000);
        }

        async function getQRCode() {
            showAlert('info', 'Generating QR code...');
            try {
                const res = await fetch('/api/get-qr');
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('qrContainer').innerHTML = `<img src="data:image/png;base64,${data.qr}" alt="QR Code"><p style="margin-top:10px;">Scan with WhatsApp</p>`;
                    showAlert('success', 'QR code generated! Scan with your phone.');
                } else {
                    showAlert('error', data.message);
                }
            } catch(e) { showAlert('error', e.message); }
        }

        async function checkLoginStatus() {
            try {
                const res = await fetch('/api/check-login');
                const data = await res.json();
                const statusSpan = document.getElementById('loginStatus');
                const textSpan = document.getElementById('loginStatusText');
                if (data.logged_in) {
                    statusSpan.className = 'status-indicator status-active';
                    textSpan.innerHTML = '✅ Logged In';
                } else {
                    statusSpan.className = 'status-indicator status-inactive';
                    textSpan.innerHTML = '❌ Not Logged In';
                }
            } catch(e) { console.error(e); }
        }

        async function uploadMessages() {
            const file = document.getElementById('messagesFile').files[0];
            if (!file) return;
            const fd = new FormData();
            fd.append('messages_file', file);
            showAlert('info', 'Uploading...');
            try {
                const res = await fetch('/api/upload-messages', { method: 'POST', body: fd });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('fileStatus').textContent = `✅ ${data.count} messages loaded`;
                    document.getElementById('totalMessages').textContent = data.count;
                    if (data.preview) {
                        document.getElementById('messagePreview').innerHTML = '<strong>Preview:</strong><br>' + data.preview.map(m => `<div>📱 ${m.phone} - ${m.message.substring(0, 50)}...</div>`).join('');
                    }
                    showAlert('success', data.message);
                } else {
                    showAlert('error', data.message);
                }
            } catch(e) { showAlert('error', e.message); }
        }

        async function startBroadcast() {
            const delay = document.getElementById('messageDelay').value;
            const countryCode = document.getElementById('countryCode').value;
            const template = document.getElementById('messageTemplate').value;
            showAlert('info', 'Starting broadcast...');
            try {
                const res = await fetch('/api/start-broadcast', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ delay: parseInt(delay), country_code: countryCode, template: template })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('startBtn').disabled = true;
                    document.getElementById('startBtn').style.opacity = '0.5';
                    document.getElementById('stopBtn').disabled = false;
                    document.getElementById('stopBtn').style.opacity = '1';
                    showAlert('success', data.message);
                } else {
                    showAlert('error', data.message);
                }
            } catch(e) { showAlert('error', e.message); }
        }

        async function stopBroadcast() {
            try {
                const res = await fetch('/api/stop-broadcast', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('startBtn').style.opacity = '1';
                    document.getElementById('stopBtn').disabled = true;
                    document.getElementById('stopBtn').style.opacity = '0.5';
                    showAlert('success', 'Broadcast stopped');
                }
            } catch(e) { showAlert('error', e.message); }
        }

        async function refreshStatus() {
            try {
                const res = await fetch('/api/broadcast-status');
                const data = await res.json();
                document.getElementById('messagesSent').textContent = data.sent;
                document.getElementById('totalMessages').textContent = data.total;
                const percent = data.total > 0 ? Math.round((data.sent / data.total) * 100) : 0;
                document.getElementById('progressPercent').textContent = percent + '%';
                document.getElementById('progressBar').style.width = percent + '%';
                document.getElementById('progressBar').textContent = percent > 15 ? percent + '%' : '';
                document.getElementById('uptimeBadge').textContent = '⏱️ Uptime: ' + data.uptime;
                
                const statusSpan = document.getElementById('broadcastStatus');
                const statusText = document.getElementById('broadcastStatusText');
                if (data.active) {
                    statusSpan.className = 'status-indicator status-active';
                    statusText.textContent = '🔴 Running';
                } else {
                    statusSpan.className = 'status-indicator status-inactive';
                    statusText.textContent = 'Idle';
                }
            } catch(e) { console.error(e); }
        }

        async function refreshLogs() {
            try {
                const res = await fetch('/api/get-logs');
                const data = await res.json();
                const tbody = document.getElementById('logsTbody');
                if (data.logs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center;">No logs yet</td></tr>';
                    return;
                }
                tbody.innerHTML = data.logs.map(log => `
                    <tr>
                        <td>${new Date(log.timestamp).toLocaleTimeString()}</td>
                        <td>${log.phone_number}</td>
                        <td>${log.message ? log.message.substring(0, 50) : 'N/A'}...</td>
                        <td class="status-${log.status}">${log.status.toUpperCase()}</td>
                    </tr>
                `).join('');
            } catch(e) { console.error(e); }
        }

        async function clearLogs() {
            if (!confirm('Clear all logs?')) return;
            try {
                await fetch('/api/clear-logs', { method: 'POST' });
                refreshLogs();
                showAlert('success', 'Logs cleared');
            } catch(e) { showAlert('error', e.message); }
        }

        function startAutoRefresh() {
            if (refreshInterval) clearInterval(refreshInterval);
            refreshInterval = setInterval(() => {
                refreshStatus();
                refreshLogs();
                checkLoginStatus();
            }, 2000);
        }

        document.addEventListener('DOMContentLoaded', () => {
            startAutoRefresh();
            checkLoginStatus();
            refreshStatus();
            refreshLogs();
        });
    </script>
</body>
</html>
"""

# API Routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/init-session', methods=['POST'])
def init_session():
    session['session_id'] = secrets.token_hex(16)
    return jsonify({"status": "success", "session_id": session.get('session_id')})

@app.route('/api/get-qr', methods=['GET'])
def get_qr():
    try:
        import qrcode
        from io import BytesIO
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data("https://web.whatsapp.com")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return jsonify({"status": "success", "qr": img_str})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/check-login', methods=['GET'])
def check_login():
    is_logged = check_login_status()
    return jsonify({"logged_in": is_logged})

@app.route('/api/upload-messages', methods=['POST'])
def upload_messages():
    global messages_list
    try:
        file = request.files.get('messages_file')
        if not file:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        content = file.read().decode('utf-8')
        messages = []
        
        # Try JSON
        try:
            data = json.loads(content)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        phone = item.get('phone', item.get('number', ''))
                        msg = item.get('message', item.get('text', ''))
                    else:
                        parts = str(item).split(',', 1)
                        phone = parts[0].strip()
                        msg = parts[1].strip() if len(parts) > 1 else ''
                    if phone:
                        messages.append({'phone': phone, 'message': msg})
        except:
            # Parse as CSV/TXT
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith(','):
                    continue
                parts = line.split(',', 1)
                phone = parts[0].strip()
                msg = parts[1].strip() if len(parts) > 1 else ''
                if phone:
                    messages.append({'phone': phone, 'message': msg})
        
        if not messages:
            return jsonify({"status": "error", "message": "No valid messages found"}), 400
        
        messages_list = messages
        preview = messages[:5]
        
        return jsonify({
            "status": "success",
            "message": f"{len(messages)} messages loaded",
            "count": len(messages),
            "preview": preview
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/start-broadcast', methods=['POST'])
def start_broadcast():
    global broadcast_active, broadcast_thread, messages_list, messages_sent, total_messages
    
    if broadcast_active:
        return jsonify({"status": "error", "message": "Broadcast already running"}), 400
    
    if not messages_list:
        return jsonify({"status": "error", "message": "No messages loaded"}), 400
    
    data = request.get_json()
    delay = data.get('delay', 10)
    
    # Reset counters
    messages_sent = 0
    total_messages = len(messages_list)
    broadcast_active = True
    
    # Start broadcast thread
    broadcast_thread = threading.Thread(target=broadcast_worker, args=(delay,))
    broadcast_thread.daemon = True
    broadcast_thread.start()
    
    return jsonify({"status": "success", "message": f"Broadcast started with {len(messages_list)} messages", "total": len(messages_list)})

@app.route('/api/stop-broadcast', methods=['POST'])
def stop_broadcast():
    global broadcast_active
    broadcast_active = False
    return jsonify({"status": "success", "message": "Broadcast stopped"})

@app.route('/api/broadcast-status', methods=['GET'])
def broadcast_status():
    global broadcast_active, messages_sent, total_messages, server_start_time
    
    uptime = datetime.now() - server_start_time
    uptime_str = str(uptime).split('.')[0]
    
    return jsonify({
        "active": broadcast_active,
        "sent": messages_sent,
        "total": total_messages,
        "uptime": uptime_str
    })

@app.route('/api/get-logs', methods=['GET'])
def get_logs():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM messages_log ORDER BY timestamp DESC LIMIT 100')
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"logs": []})

@app.route('/api/clear-logs', methods=['POST'])
def clear_logs():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages_log')
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# Initialize
init_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)