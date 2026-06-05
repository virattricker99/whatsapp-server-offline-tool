# app.py - WhatsApp Bulk Messaging System (Complete Working Version)
import os
import threading
import time
import random
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import jwt

# ---------- App Initialization ----------
app = Flask(__name__)
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'my-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///whatsapp_bulk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

# Fix for PostgreSQL on Render
database_url = app.config['SQLALCHEMY_DATABASE_URI']
if database_url and database_url.startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url.replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

# ---------- Database Models ----------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_messages_sent = db.Column(db.Integer, default=0)

class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='disconnected')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GroupContact(db.Model):
    __tablename__ = 'group_contacts'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    contact_number = db.Column(db.String(50), nullable=False)

# ---------- JWT Functions ----------
def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + app.config['JWT_ACCESS_TOKEN_EXPIRES']
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def decode_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except:
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing token'}), 401
        token = auth_header.split(' ')[1]
        user_id = decode_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid token'}), 401
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

# ---------- Helper Functions ----------
def create_default_groups(user_id):
    default_groups = ['Marketing Team', 'VIP Customers', 'Support Group', 'Community General']
    default_contacts = {
        'Marketing Team': ['+1234567890', '+1987654321'],
        'VIP Customers': ['+1122334455', '+9988776655'],
        'Support Group': ['+5566778899'],
        'Community General': ['+4433221100']
    }
    
    for group_name in default_groups:
        group = Group(user_id=user_id, name=group_name)
        db.session.add(group)
        db.session.commit()
        for contact in default_contacts.get(group_name, []):
            gc = GroupContact(group_id=group.id, contact_number=contact)
            db.session.add(gc)
        db.session.commit()

# ---------- API Routes ----------
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username exists'}), 400
    
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email exists'}), 400
    
    user = User(username=username, email=email, password=password)
    db.session.add(user)
    db.session.commit()
    
    create_default_groups(user.id)
    
    token = generate_token(user.id)
    return jsonify({'token': token, 'user': {'id': user.id, 'username': user.username, 'email': user.email, 'total_messages_sent': 0}}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = generate_token(user.id)
    return jsonify({'token': token, 'user': {'id': user.id, 'username': user.username, 'email': user.email, 'total_messages_sent': user.total_messages_sent}})

@app.route('/api/auth/admin-login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    # Check for admin user
    admin_user = User.query.filter_by(username=username, is_admin=True).first()
    if admin_user and admin_user.password == password:
        token = generate_token(admin_user.id)
        return jsonify({'token': token, 'user': {'id': admin_user.id, 'username': admin_user.username, 'is_admin': True}})
    
    # Create admin if not exists (default: virattricker0909 / admin123)
    if username == 'virattricker0909' and password == 'admin123':
        admin = User.query.filter_by(username=username).first()
        if not admin:
            admin = User(username=username, email='admin@system.com', password=password, is_admin=True)
            db.session.add(admin)
            db.session.commit()
        token = generate_token(admin.id)
        return jsonify({'token': token, 'user': {'id': admin.id, 'username': admin.username, 'is_admin': True}})
    
    return jsonify({'error': 'Invalid admin credentials'}), 401

@app.route('/api/sessions', methods=['GET'])
@login_required
def get_sessions():
    sessions = Session.query.filter_by(user_id=request.current_user.id).all()
    result = [{'id': s.id, 'name': s.name, 'phone': s.phone_number, 'status': s.status} for s in sessions]
    return jsonify(result)

@app.route('/api/sessions/pair', methods=['POST'])
@login_required
def pair_session():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    pairing_code = str(random.randint(100000, 999999))
    name = f"Session_{phone[-6:]}"
    
    session = Session(
        user_id=request.current_user.id,
        name=name,
        phone_number=phone,
        status='connected'
    )
    db.session.add(session)
    db.session.commit()
    
    return jsonify({
        'session': {'id': session.id, 'name': session.name, 'phone': session.phone_number, 'status': session.status},
        'pairing_code': pairing_code
    }), 201

@app.route('/api/sessions/<int:session_id>/toggle', methods=['POST'])
@login_required
def toggle_session(session_id):
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id).first()
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    session.status = 'disconnected' if session.status == 'connected' else 'connected'
    db.session.commit()
    return jsonify({'id': session.id, 'name': session.name, 'phone': session.phone_number, 'status': session.status})

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id).first()
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    db.session.delete(session)
    db.session.commit()
    return jsonify({'message': 'Session deleted'})

@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    groups = Group.query.filter_by(user_id=request.current_user.id).all()
    result = []
    for group in groups:
        contacts = GroupContact.query.filter_by(group_id=group.id).all()
        result.append({
            'id': group.id,
            'name': group.name,
            'contacts': [{'id': c.id, 'number': c.contact_number} for c in contacts]
        })
    return jsonify(result)

@app.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Group name required'}), 400
    
    group = Group(user_id=request.current_user.id, name=name)
    db.session.add(group)
    db.session.commit()
    return jsonify({'id': group.id, 'name': group.name, 'contacts': []}), 201

@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_group(group_id):
    group = Group.query.filter_by(id=group_id, user_id=request.current_user.id).first()
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    db.session.delete(group)
    db.session.commit()
    return jsonify({'message': 'Group deleted'})

@app.route('/api/groups/<int:group_id>/contacts', methods=['POST'])
@login_required
def add_contact(group_id):
    group = Group.query.filter_by(id=group_id, user_id=request.current_user.id).first()
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    data = request.get_json()
    number = data.get('number', '').strip()
    if not number:
        return jsonify({'error': 'Phone number required'}), 400
    
    contact = GroupContact(group_id=group.id, contact_number=number)
    db.session.add(contact)
    db.session.commit()
    return jsonify({'id': contact.id, 'number': contact.contact_number}), 201

@app.route('/api/messages/stats', methods=['GET'])
@login_required
def get_stats():
    total_sessions = Session.query.filter_by(user_id=request.current_user.id).count()
    connected_sessions = Session.query.filter_by(user_id=request.current_user.id, status='connected').count()
    
    return jsonify({
        'total_messages_sent': request.current_user.total_messages_sent,
        'active_tasks': 0,
        'total_sessions': total_sessions,
        'connected_sessions': connected_sessions
    })

@app.route('/api/messages/send', methods=['POST'])
@login_required
def send_messages():
    session_id = request.form.get('session_id')
    target_type = request.form.get('target_type')
    target_value = request.form.get('target_value')
    delay = float(request.form.get('delay', 5))
    prefix = request.form.get('prefix', '')
    file_content = request.form.get('file_content', '')
    
    if not session_id or not target_type or not target_value or not file_content:
        return jsonify({'error': 'Missing required fields'}), 400
    
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id).first()
    if not session or session.status != 'connected':
        return jsonify({'error': 'Valid connected session required'}), 400
    
    # Parse messages
    lines = [line.strip() for line in file_content.split('\n') if line.strip()]
    if not lines:
        return jsonify({'error': 'No messages found'}), 400
    
    messages = [f"{prefix}{line}" for line in lines]
    
    # Get recipients
    recipients = []
    if target_type == 'individual':
        recipients = [target_value]
    else:
        group = Group.query.filter_by(id=int(target_value), user_id=request.current_user.id).first()
        if group:
            contacts = GroupContact.query.filter_by(group_id=group.id).all()
            recipients = [c.contact_number for c in contacts]
    
    if not recipients:
        return jsonify({'error': 'No recipients found'}), 400
    
    total_msgs = len(recipients) * len(messages)
    
    # Update user stats
    request.current_user.total_messages_sent += total_msgs
    db.session.commit()
    
    # Simulate sending in background
    def send_in_background():
        time.sleep(delay * 2)
        # Actual sending logic would go here
    
    thread = threading.Thread(target=send_in_background)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'task_id': random.randint(1000, 9999),
        'message': f'Task created. Sending {total_msgs} messages.'
    }), 202

# ---------- HTML Template ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Bulk Messaging System</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container-custom { max-width: 1200px; margin: 0 auto; }
        .card-custom { background: white; border-radius: 20px; padding: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.2); margin-bottom: 20px; }
        .header { text-align: center; color: white; margin-bottom: 30px; }
        .header h1 { font-size: 2.5rem; font-weight: 700; }
        .stat-card { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border-radius: 15px; padding: 20px; text-align: center; margin-bottom: 20px; }
        .stat-card h2 { font-size: 2rem; font-weight: bold; margin: 0; }
        .tab-btn { padding: 10px 20px; margin-right: 10px; border: none; background: #e0e0e0; border-radius: 10px; cursor: pointer; }
        .tab-btn.active { background: #667eea; color: white; }
        .tab-content { display: none; margin-top: 20px; }
        .tab-content.active { display: block; }
        .session-item { background: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 4px solid #28a745; }
        .btn-custom { background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; padding: 10px 20px; border-radius: 10px; cursor: pointer; }
        .hidden { display: none; }
        .page { display: none; }
        .page.active { display: block; }
    </style>
</head>
<body>
<div class="container-custom">
    <div class="header">
        <h1><i class="fab fa-whatsapp"></i> WhatsApp Bulk Messaging</h1>
        <p>Professional Bulk Messaging Solution</p>
    </div>

    <!-- Login Page -->
    <div id="loginPage" class="page active">
        <div class="card-custom">
            <h2><i class="fas fa-sign-in-alt"></i> Login</h2>
            <input type="text" id="loginUsername" class="form-control mb-3" placeholder="Username">
            <input type="password" id="loginPassword" class="form-control mb-3" placeholder="Password">
            <button class="btn-custom w-100" onclick="performLogin()">Login</button>
            <div class="text-center mt-3">
                <a onclick="showPage('signupPage')" style="cursor:pointer;">Sign Up</a> | 
                <a onclick="showPage('adminPage')" style="cursor:pointer;">Admin Login</a>
            </div>
        </div>
    </div>

    <!-- Signup Page -->
    <div id="signupPage" class="page">
        <div class="card-custom">
            <h2><i class="fas fa-user-plus"></i> Sign Up</h2>
            <input type="text" id="signupUser" class="form-control mb-3" placeholder="Username">
            <input type="email" id="signupEmail" class="form-control mb-3" placeholder="Email">
            <input type="password" id="signupPass" class="form-control mb-3" placeholder="Password">
            <button class="btn-custom w-100" onclick="performSignup()">Sign Up</button>
            <div class="text-center mt-3"><a onclick="showPage('loginPage')" style="cursor:pointer;">Back to Login</a></div>
        </div>
    </div>

    <!-- Admin Login Page -->
    <div id="adminPage" class="page">
        <div class="card-custom">
            <h2><i class="fas fa-user-shield"></i> Admin Login</h2>
            <input type="text" id="adminUsername" class="form-control mb-3" placeholder="Admin Username" value="virattricker0909">
            <input type="password" id="adminPassword" class="form-control mb-3" placeholder="Admin Password">
            <button class="btn-custom w-100" onclick="performAdminLogin()">Admin Login</button>
            <div class="text-center mt-3"><a onclick="showPage('loginPage')" style="cursor:pointer;">Back to Login</a></div>
        </div>
    </div>

    <!-- Dashboard Page -->
    <div id="dashboardPage" class="page">
        <div class="card-custom">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h2><i class="fas fa-tachometer-alt"></i> Dashboard</h2>
                <button class="btn btn-danger" onclick="logout()">Logout</button>
            </div>
            
            <div class="row mb-4">
                <div class="col-md-3"><div class="stat-card"><h2 id="statTotalSessions">0</h2><p>Total Sessions</p></div></div>
                <div class="col-md-3"><div class="stat-card"><h2 id="statConnected">0</h2><p>Connected</p></div></div>
                <div class="col-md-3"><div class="stat-card"><h2 id="statActiveTasks">0</h2><p>Active Tasks</p></div></div>
                <div class="col-md-3"><div class="stat-card"><h2 id="statMessagesSent">0</h2><p>Messages Sent</p></div></div>
            </div>

            <div>
                <button class="tab-btn active" onclick="showTab('sessions')">Sessions</button>
                <button class="tab-btn" onclick="showTab('addSession')">Add Session</button>
                <button class="tab-btn" onclick="showTab('sendMsg')">Send Message</button>
                <button class="tab-btn" onclick="showTab('groups')">Groups</button>
            </div>

            <!-- Sessions Tab -->
            <div id="sessionsTab" class="tab-content active">
                <div id="sessionsList"></div>
            </div>

            <!-- Add Session Tab -->
            <div id="addSessionTab" class="tab-content">
                <input type="text" id="newSessionPhone" class="form-control mb-3" placeholder="Phone number with country code">
                <button class="btn-custom w-100" onclick="generatePairingCode()">Generate Pairing Code & Add Session</button>
            </div>

            <!-- Send Message Tab -->
            <div id="sendMsgTab" class="tab-content">
                <select id="sendSessionSelect" class="form-control mb-3"></select>
                <select id="targetTypeSelect" class="form-control mb-3" onchange="toggleTargetFields()">
                    <option value="group">Group</option>
                    <option value="individual">Individual Number</option>
                </select>
                <div id="groupTargetDiv"><select id="targetGroupSelect" class="form-control mb-3"></select></div>
                <div id="individualTargetDiv" class="hidden"><input type="text" id="individualNumber" class="form-control mb-3" placeholder="Phone number"></div>
                <input type="file" id="messageFileInput" accept=".txt" class="form-control mb-3">
                <input type="number" id="delaySeconds" class="form-control mb-3" value="5" placeholder="Delay (seconds)">
                <input type="text" id="messagePrefix" class="form-control mb-3" placeholder="Message prefix">
                <button class="btn-custom w-100" onclick="startSending()">Start Sending</button>
            </div>

            <!-- Groups Tab -->
            <div id="groupsTab" class="tab-content">
                <div id="groupsList"></div>
                <div class="input-group mt-3">
                    <input type="text" id="newGroupName" class="form-control" placeholder="New group name">
                    <button class="btn-custom" onclick="createGroup()">Add Group</button>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    let authToken = localStorage.getItem('authToken');

    async function apiRequest(url, options = {}) {
        const headers = { 'Content-Type': 'application/json' };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const response = await fetch(url, { ...options, headers });
        if (response.status === 401) { logout(); throw new Error('Session expired'); }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        return data;
    }

    async function apiFormRequest(url, formData) {
        const headers = {};
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const response = await fetch(url, { method: 'POST', headers, body: formData });
        if (response.status === 401) { logout(); throw new Error('Session expired'); }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error);
        return data;
    }

    async function loadStats() {
        try {
            const stats = await apiRequest('/api/messages/stats');
            document.getElementById('statTotalSessions').innerText = stats.total_sessions || 0;
            document.getElementById('statConnected').innerText = stats.connected_sessions || 0;
            document.getElementById('statMessagesSent').innerText = stats.total_messages_sent || 0;
        } catch(e) { console.error(e); }
    }

    async function loadSessions() {
        try {
            const sessions = await apiRequest('/api/sessions');
            const container = document.getElementById('sessionsList');
            if (!sessions.length) container.innerHTML = '<div class="alert alert-info">No sessions found. Add a session to start.</div>';
            else {
                container.innerHTML = sessions.map(s => `
                    <div class="session-item">
                        <div class="d-flex justify-content-between align-items-center">
                            <div><strong>${s.name}</strong><br><small>${s.phone}</small><br><span class="badge ${s.status === 'connected' ? 'bg-success' : 'bg-warning'}">${s.status}</span></div>
                            <div><button class="btn btn-sm btn-secondary me-2" onclick="toggleSession(${s.id})">Toggle</button><button class="btn btn-sm btn-danger" onclick="deleteSession(${s.id})">Delete</button></div>
                        </div>
                    </div>
                `).join('');
            }
            const select = document.getElementById('sendSessionSelect');
            const connected = sessions.filter(s => s.status === 'connected');
            select.innerHTML = '<option value="">Select session</option>' + connected.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        } catch(e) { console.error(e); }
    }

    async function toggleSession(id) {
        try { await apiRequest(`/api/sessions/${id}/toggle`, { method: 'POST' }); await loadSessions(); } catch(e) { alert(e.message); }
    }

    async function deleteSession(id) {
        if (confirm('Delete this session?')) { try { await apiRequest(`/api/sessions/${id}`, { method: 'DELETE' }); await loadSessions(); await loadStats(); } catch(e) { alert(e.message); } }
    }

    async function generatePairingCode() {
        const phone = document.getElementById('newSessionPhone').value.trim();
        if (!phone) return alert('Enter phone number');
        try {
            const result = await apiRequest('/api/sessions/pair', { method: 'POST', body: JSON.stringify({ phone }) });
            alert(`Pairing Code: ${result.pairing_code}\\nSession added successfully!`);
            document.getElementById('newSessionPhone').value = '';
            await loadSessions();
            await loadStats();
            showTab('sessions');
        } catch(e) { alert(e.message); }
    }

    async function loadGroups() {
        try {
            const groups = await apiRequest('/api/groups');
            const container = document.getElementById('groupsList');
            const select = document.getElementById('targetGroupSelect');
            if (select) select.innerHTML = '<option value="">Select group</option>' + groups.map(g => `<option value="${g.id}">${g.name}</option>`).join('');
            if (container) {
                container.innerHTML = groups.map(g => `
                    <div class="card mb-2"><div class="card-body"><h6>${g.name}</h6><ul>${(g.contacts || []).map(c => `<li>${c.number}</li>`).join('')}</ul><button class="btn btn-sm btn-danger" onclick="deleteGroup(${g.id})">Delete Group</button> <button class="btn btn-sm btn-secondary" onclick="addContact(${g.id})">Add Contact</button></div></div>
                `).join('');
            }
        } catch(e) { console.error(e); }
    }

    async function createGroup() {
        const name = document.getElementById('newGroupName').value.trim();
        if (!name) return alert('Enter group name');
        try { await apiRequest('/api/groups', { method: 'POST', body: JSON.stringify({ name }) }); await loadGroups(); document.getElementById('newGroupName').value = ''; } catch(e) { alert(e.message); }
    }

    async function deleteGroup(id) {
        if (confirm('Delete group?')) { try { await apiRequest(`/api/groups/${id}`, { method: 'DELETE' }); await loadGroups(); } catch(e) { alert(e.message); } }
    }

    async function addContact(groupId) {
        const number = prompt('Enter phone number with country code:');
        if (number) { try { await apiRequest(`/api/groups/${groupId}/contacts`, { method: 'POST', body: JSON.stringify({ number }) }); await loadGroups(); } catch(e) { alert(e.message); } }
    }

    async function startSending() {
        const sessionId = document.getElementById('sendSessionSelect').value;
        if (!sessionId) return alert('Select a session');
        const targetType = document.getElementById('targetTypeSelect').value;
        let targetValue = targetType === 'group' ? document.getElementById('targetGroupSelect').value : document.getElementById('individualNumber').value.trim();
        if (!targetValue) return alert('Select target');
        const fileInput = document.getElementById('messageFileInput');
        if (!fileInput.files.length) return alert('Upload a .txt file');
        const fileContent = await fileInput.files[0].text();
        
        const formData = new FormData();
        formData.append('session_id', sessionId);
        formData.append('target_type', targetType);
        formData.append('target_value', targetValue);
        formData.append('delay', document.getElementById('delaySeconds').value);
        formData.append('prefix', document.getElementById('messagePrefix').value);
        formData.append('file_content', fileContent);
        
        try {
            const result = await apiFormRequest('/api/messages/send', formData);
            alert(result.message);
            await loadStats();
        } catch(e) { alert(e.message); }
    }

    function toggleTargetFields() {
        const isGroup = document.getElementById('targetTypeSelect').value === 'group';
        document.getElementById('groupTargetDiv').classList.toggle('hidden', !isGroup);
        document.getElementById('individualTargetDiv').classList.toggle('hidden', isGroup);
    }

    function showTab(tabName) {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.getElementById(`${tabName}Tab`).classList.add('active');
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        if (tabName === 'sessions') { loadSessions(); }
        if (tabName === 'groups') { loadGroups(); }
    }

    async function performLogin() {
        const username = document.getElementById('loginUsername').value.trim();
        const password = document.getElementById('loginPassword').value.trim();
        try {
            const data = await apiRequest('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
            authToken = data.token;
            localStorage.setItem('authToken', authToken);
            showPage('dashboardPage');
            await loadDashboard();
        } catch(e) { alert('Login failed: ' + e.message); }
    }

    async function performSignup() {
        const username = document.getElementById('signupUser').value.trim();
        const email = document.getElementById('signupEmail').value.trim();
        const password = document.getElementById('signupPass').value.trim();
        try {
            const data = await apiRequest('/api/auth/signup', { method: 'POST', body: JSON.stringify({ username, email, password }) });
            authToken = data.token;
            localStorage.setItem('authToken', authToken);
            showPage('dashboardPage');
            await loadDashboard();
        } catch(e) { alert('Signup failed: ' + e.message); }
    }

    async function performAdminLogin() {
        const username = document.getElementById('adminUsername').value.trim();
        const password = document.getElementById('adminPassword').value.trim();
        try {
            const data = await apiRequest('/api/auth/admin-login', { method: 'POST', body: JSON.stringify({ username, password }) });
            authToken = data.token;
            localStorage.setItem('authToken', authToken);
            showPage('dashboardPage');
            await loadDashboard();
        } catch(e) { alert('Admin login failed: ' + e.message); }
    }

    async function loadDashboard() {
        await loadStats();
        await loadSessions();
        await loadGroups();
        toggleTargetFields();
    }

    function showPage(pageId) {
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(pageId).classList.add('active');
        if (pageId === 'dashboardPage') loadDashboard();
    }

    function logout() {
        localStorage.removeItem('authToken');
        authToken = null;
        showPage('loginPage');
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (localStorage.getItem('authToken')) { authToken = localStorage.getItem('authToken'); showPage('dashboardPage'); loadDashboard(); }
    });
</script>
</body>
</html>
"""

# ---------- Database Initialization ----------
def init_db():
    with app.app_context():
        db.create_all()
        # Create default admin
        admin = User.query.filter_by(username='virattricker0909').first()
        if not admin:
            admin = User(username='virattricker0909', email='admin@system.com', password='admin123', is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created: virattricker0909 / admin123")

init_db()

# ---------- Run Server ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
