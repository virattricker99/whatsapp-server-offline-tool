# app.py - WhatsApp Bulk Messaging System (Full Stack in One File)
import os
import re
import threading
import time
import random
from datetime import datetime, timedelta
from functools import wraps
from uuid import uuid4

from flask import Flask, request, jsonify, render_template_string, session as flask_session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import jwt

# ---------- App Initialization ----------
app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///whatsapp_bulk.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=7)

# Fix for PostgreSQL on Render
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

# ---------- Database Models ----------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_messages_sent = db.Column(db.Integer, default=0)
    
    sessions = db.relationship('Session', backref='user', lazy=True, cascade='all, delete-orphan')
    groups = db.relationship('Group', backref='user', lazy=True, cascade='all, delete-orphan')
    tasks = db.relationship('MessageTask', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'email': self.email, 'is_admin': self.is_admin, 'total_messages_sent': self.total_messages_sent}

class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='disconnected')
    pairing_code = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone_number,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    contacts = db.relationship('GroupContact', backref='group', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'contacts': [contact.to_dict() for contact in self.contacts]
        }

class GroupContact(db.Model):
    __tablename__ = 'group_contacts'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    contact_number = db.Column(db.String(50), nullable=False)
    contact_name = db.Column(db.String(100), nullable=True)
    
    def to_dict(self):
        return {'id': self.id, 'number': self.contact_number, 'name': self.contact_name}

class MessageTask(db.Model):
    __tablename__ = 'message_tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    target_number = db.Column(db.String(50), nullable=True)
    total_messages = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    logs = db.relationship('MessageLog', backref='task', lazy=True, cascade='all, delete-orphan')
    session = db.relationship('Session', backref='tasks')
    
    def to_dict(self):
        return {
            'id': self.id,
            'target_type': self.target_type,
            'total_messages': self.total_messages,
            'sent_count': self.sent_count,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class MessageLog(db.Model):
    __tablename__ = 'message_logs'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('message_tasks.id'), nullable=False)
    recipient_number = db.Column(db.String(50), nullable=False)
    message_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='sent')
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------- JWT Helper ----------
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
            return jsonify({'error': 'Missing or invalid token'}), 401
        token = auth_header.split(' ')[1]
        user_id = decode_token(token)
        if not user_id:
            return jsonify({'error': 'Invalid or expired token'}), 401
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# ---------- Background Message Sending ----------
def send_messages_task(task_id, delay_seconds):
    with app.app_context():
        task = MessageTask.query.get(task_id)
        if not task:
            return
        
        session = Session.query.get(task.session_id)
        if not session or session.status != 'connected':
            task.status = 'failed'
            db.session.commit()
            return
        
        recipients = []
        if task.target_type == 'individual' and task.target_number:
            recipients.append(task.target_number)
        elif task.target_type == 'group' and task.target_id:
            group = Group.query.get(task.target_id)
            if group:
                recipients = [contact.contact_number for contact in group.contacts]
        
        logs = MessageLog.query.filter_by(task_id=task.id).all()
        if not logs:
            task.status = 'failed'
            db.session.commit()
            return
        
        task.status = 'processing'
        db.session.commit()
        
        for index, log in enumerate(logs):
            time.sleep(delay_seconds)
            log.status = 'sent'
            log.sent_at = datetime.utcnow()
            task.sent_count = index + 1
            db.session.commit()
            
            user = User.query.get(task.user_id)
            if user:
                user.total_messages_sent += 1
                db.session.commit()
        
        task.status = 'completed'
        task.completed_at = datetime.utcnow()
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
        return jsonify({'error': 'Username already exists'}), 400
    
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    # Add default groups
    default_groups = [
        {'name': 'Marketing Team', 'contacts': ['+1234567890', '+1987654321']},
        {'name': 'VIP Customers', 'contacts': ['+1122334455', '+9988776655']},
        {'name': 'Support Group', 'contacts': ['+5566778899']},
        {'name': 'Community General', 'contacts': ['+4433221100']}
    ]
    for group_data in default_groups:
        group = Group(user_id=user.id, name=group_data['name'], description='Default group')
        db.session.add(group)
        db.session.commit()
        for contact in group_data['contacts']:
            gc = GroupContact(group_id=group.id, contact_number=contact, contact_name='')
            db.session.add(gc)
        db.session.commit()
    
    token = generate_token(user.id)
    return jsonify({'token': token, 'user': user.to_dict()}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = generate_token(user.id)
    return jsonify({'token': token, 'user': user.to_dict()})

@app.route('/api/auth/admin-login', methods=['POST'])
def admin_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    admin_username = os.environ.get('ADMIN_USERNAME', 'virattricker0909')
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    
    if username == admin_username and (not admin_password or password == admin_password):
        admin_user = User.query.filter_by(username=username).first()
        if not admin_user:
            admin_user = User(username=username, email='admin@example.com', is_admin=True)
            admin_user.set_password(password if password else 'admin123')
            db.session.add(admin_user)
            db.session.commit()
        else:
            admin_user.is_admin = True
            db.session.commit()
        
        token = generate_token(admin_user.id)
        return jsonify({'token': token, 'user': admin_user.to_dict()})
    
    user = User.query.filter_by(username=username).first()
    if user and user.is_admin and user.check_password(password):
        token = generate_token(user.id)
        return jsonify({'token': token, 'user': user.to_dict()})
    
    return jsonify({'error': 'Invalid admin credentials'}), 401

@app.route('/api/sessions', methods=['GET'])
@login_required
def get_sessions():
    sessions = Session.query.filter_by(user_id=request.current_user.id).all()
    return jsonify([s.to_dict() for s in sessions])

@app.route('/api/sessions/pair', methods=['POST'])
@login_required
def pair_session():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    
    if not phone:
        return jsonify({'error': 'Phone number required'}), 400
    
    pairing_code = str(random.randint(100000, 999999))
    name = f"Session {phone[-6:]}"
    session = Session(
        user_id=request.current_user.id,
        name=name,
        phone_number=phone,
        status='connected',
        pairing_code=pairing_code
    )
    db.session.add(session)
    db.session.commit()
    
    return jsonify({
        'session': session.to_dict(),
        'pairing_code': pairing_code,
        'message': f'Use code {pairing_code} in WhatsApp to link device'
    }), 201

@app.route('/api/sessions/<int:session_id>/toggle', methods=['POST'])
@login_required
def toggle_session_status(session_id):
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id).first_or_404()
    session.status = 'disconnected' if session.status == 'connected' else 'connected'
    db.session.commit()
    return jsonify(session.to_dict())

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
@login_required
def delete_session(session_id):
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id).first_or_404()
    db.session.delete(session)
    db.session.commit()
    return jsonify({'message': 'Session deleted'})

@app.route('/api/groups', methods=['GET'])
@login_required
def get_groups():
    groups = Group.query.filter_by(user_id=request.current_user.id).all()
    return jsonify([g.to_dict() for g in groups])

@app.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Group name required'}), 400
    group = Group(user_id=request.current_user.id, name=name, description=data.get('description', ''))
    db.session.add(group)
    db.session.commit()
    return jsonify(group.to_dict()), 201

@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_group(group_id):
    group = Group.query.filter_by(id=group_id, user_id=request.current_user.id).first_or_404()
    db.session.delete(group)
    db.session.commit()
    return jsonify({'message': 'Group deleted'})

@app.route('/api/groups/<int:group_id>/contacts', methods=['POST'])
@login_required
def add_group_contact(group_id):
    group = Group.query.filter_by(id=group_id, user_id=request.current_user.id).first_or_404()
    data = request.get_json()
    number = data.get('number', '').strip()
    if not number:
        return jsonify({'error': 'Phone number required'}), 400
    contact = GroupContact(group_id=group.id, contact_number=number, contact_name=data.get('name', ''))
    db.session.add(contact)
    db.session.commit()
    return jsonify(contact.to_dict()), 201

@app.route('/api/messages/stats', methods=['GET'])
@login_required
def get_stats():
    active_tasks = MessageTask.query.filter(
        MessageTask.user_id == request.current_user.id,
        MessageTask.status.in_(['pending', 'processing'])
    ).count()
    
    return jsonify({
        'total_messages_sent': request.current_user.total_messages_sent,
        'active_tasks': active_tasks,
        'total_sessions': Session.query.filter_by(user_id=request.current_user.id).count(),
        'connected_sessions': Session.query.filter_by(user_id=request.current_user.id, status='connected').count()
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
    
    session = Session.query.filter_by(id=session_id, user_id=request.current_user.id, status='connected').first()
    if not session:
        return jsonify({'error': 'Valid connected session required'}), 400
    
    lines = [line.strip() for line in file_content.split('\n') if line.strip()]
    if not lines:
        return jsonify({'error': 'No messages found in file'}), 400
    
    messages = [f"{prefix}{line}" for line in lines]
    
    recipients = []
    target_id = None
    target_number = None
    
    if target_type == 'individual':
        target_number = target_value
        recipients = [target_value]
    else:
        group = Group.query.filter_by(id=int(target_value), user_id=request.current_user.id).first()
        if not group:
            return jsonify({'error': 'Group not found'}), 404
        target_id = group.id
        recipients = [c.contact_number for c in group.contacts]
    
    if not recipients:
        return jsonify({'error': 'No recipients found'}), 400
    
    task = MessageTask(
        user_id=request.current_user.id,
        session_id=session.id,
        target_type=target_type,
        target_id=target_id,
        target_number=target_number,
        total_messages=len(recipients) * len(messages),
        sent_count=0,
        status='pending'
    )
    db.session.add(task)
    db.session.commit()
    
    for recipient in recipients:
        for msg in messages:
            log = MessageLog(task_id=task.id, recipient_number=recipient, message_content=msg, status='pending')
            db.session.add(log)
    db.session.commit()
    
    thread = threading.Thread(target=send_messages_task, args=(task.id, delay))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'task_id': task.id,
        'message': f'Task created. Sending {len(recipients) * len(messages)} messages in background.'
    }), 202

# ---------- HTML Template (embedded) ----------
HTML_TEMPLATE = """
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>WhatsApp Server by Virat Rajput | Complete Suite</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', system-ui, sans-serif; }
        body { min-height: 100vh; background: linear-gradient(135deg, #5f7de7 0%, #6f6ed9 50%, #8354b4 100%); padding: 25px 20px; }
        .header-box { max-width: 1300px; margin: 0 auto 25px auto; background: rgba(255,255,255,0.12); backdrop-filter: blur(3px); border-radius: 32px; padding: 20px 28px; text-align: center; color: white; box-shadow: 0 12px 30px rgba(0,0,0,0.2); }
        .header-box h1 { font-size: 2.5rem; font-weight: 700; }
        .form-card { max-width: 1300px; margin: 0 auto 30px auto; background: #fefefe; border-radius: 32px; padding: 32px 36px; box-shadow: 0 20px 35px rgba(0,0,0,0.2); }
        .form-title { color: #4c62dd; font-size: 28px; font-weight: 700; border-bottom: 2px solid #e9ecef; padding-bottom: 16px; margin-bottom: 28px; }
        .btn-login { background: #6c6ddc; color: white; border: none; padding: 10px 24px; font-weight: 600; border-radius: 40px; }
        .btn-signup { background: #8bc34a; color: white; font-weight: 600; border-radius: 40px; }
        .btn-admin { background: linear-gradient(90deg, #ff7bc1, #ef4d73); color: white; font-weight: 600; border-radius: 40px; }
        .btn-pair, .btn-refresh-groups { background: linear-gradient(135deg, #4a6cf7, #6f8eff); color: white; border: none; font-weight: 600; border-radius: 40px; padding: 12px 20px; }
        .send-btn { background: #8dd94e; color: #1f3a0a; font-weight: 800; border-radius: 50px; padding: 14px; font-size: 1.2rem; border: none; transition: 0.2s; }
        .stat-card { background: linear-gradient(145deg, #6fa8ff, #4a6cf7); color: white; border-radius: 28px; padding: 20px 12px; text-align: center; box-shadow: 0 8px 18px rgba(0,0,0,0.1); }
        .stat-card h1 { font-size: 48px; font-weight: 800; margin-bottom: 5px; }
        .dashboard-tab-buttons { display: flex; gap: 12px; border-bottom: 1px solid #dee2e6; margin-bottom: 28px; flex-wrap: wrap; }
        .tab-btn { background: none; border: none; padding: 12px 28px; font-size: 1.1rem; font-weight: 600; color: #5f6c80; border-radius: 40px 40px 0 0; }
        .tab-btn.active { color: #4a6cf7; background: #eef3ff; border-bottom: 3px solid #4a6cf7; }
        .tab-pane { display: none; animation: fade 0.2s ease; }
        .tab-pane.active-pane { display: block; }
        @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
        .session-item { background: #f8f9ff; border-radius: 20px; padding: 15px 18px; margin-bottom: 14px; border-left: 6px solid; transition: 0.1s; }
        .badge-connected { background: #2ecc71; color: white; padding: 6px 14px; border-radius: 40px; font-size: 0.75rem; font-weight: 700; }
        .badge-disconnected { background: #e67e22; color: white; }
        .btn-sm-icon { background: transparent; border: none; font-size: 1.2rem; margin-left: 12px; color: #888; }
        .btn-sm-icon:hover { color: #e74c3c; }
        .hidden { display: none; }
        .form-control, .form-select { border-radius: 60px; padding: 12px 18px; }
        .footer-note { font-size: 12px; text-align: center; margin-top: 20px; color: #ffffffaa; }
        .page { display: none; }
        .page.active { display: block; }
    </style>
</head>
<body>

<div class="header-box">
    <h1><i class="fab fa-whatsapp"></i> WhatsApp Non Stop By Virat Rajput</h1>
    <p> OFFLINE  WHATSAPP LODER BY VIRAT// SOFTWARE DEVELOPER| Full Stack Edition</p>
</div>

<!-- LOGIN PAGE -->
<div id="loginPage" class="page active">
    <div class="form-card">
        <div class="form-title"><i class="fas fa-sign-in-alt"></i> Login</div>
        <div class="mb-3"><label class="form-label fw-bold">Username</label><input type="text" id="loginUsername" class="form-control" placeholder="Enter your username"></div>
        <div class="mb-4"><label class="form-label fw-bold">Password</label><input type="password" id="loginPassword" class="form-control" placeholder="Enter your password"></div>
        <button class="btn btn-login w-100 py-2" onclick="performLogin()"><i class="fas fa-sign-in-alt"></i> Login</button>
        <div class="center-links text-center mt-4">
            Don't have an account? <a onclick="showPage('signupPage')" style="cursor:pointer; color:#5c74df;">Sign Up</a><br>
            <a onclick="showPage('adminPage')" style="cursor:pointer; color:#5c74df;">Admin Login</a>
        </div>
    </div>
</div>

<!-- SIGNUP PAGE -->
<div id="signupPage" class="page">
    <div class="form-card">
        <div class="form-title"><i class="fas fa-user-plus"></i> Sign Up</div>
        <div class="mb-3"><label class="form-label fw-bold">Username</label><input type="text" id="signupUser" class="form-control" placeholder="Choose a username"></div>
        <div class="mb-3"><label class="form-label fw-bold">Email</label><input type="email" id="signupEmail" class="form-control" placeholder="Enter your email"></div>
        <div class="mb-4"><label class="form-label fw-bold">Password</label><input type="password" id="signupPass" class="form-control" placeholder="Choose a password"></div>
        <button class="btn btn-signup w-100 py-2" onclick="performSignup()"><i class="fas fa-user-plus"></i> Sign Up</button>
        <div class="text-center mt-4">Already have an account? <a onclick="showPage('loginPage')" style="cursor:pointer;">Login</a></div>
    </div>
</div>

<!-- ADMIN LOGIN -->
<div id="adminPage" class="page">
    <div class="form-card">
        <div class="form-title"><i class="fas fa-user-shield"></i> Admin Login</div>
        <div class="mb-3"><label class="form-label fw-bold">Admin Username</label><input type="text" id="adminUsername" class="form-control" placeholder="virattricker0909" value="virattricker0909"></div>
        <div class="mb-4"><label class="form-label fw-bold">Admin Password</label><input type="password" id="adminPassword" class="form-control" placeholder="Enter admin password"></div>
        <button class="btn btn-admin w-100 py-2" onclick="performAdminLogin()"><i class="fas fa-right-to-bracket"></i> Admin Login</button>
        <div class="text-center mt-4"><a onclick="showPage('loginPage')" style="cursor:pointer;">Back to User Login</a></div>
    </div>
</div>

<!-- MAIN DASHBOARD -->
<div id="dashboardPage" class="page">
    <div class="form-card">
        <div class="d-flex justify-content-between align-items-center flex-wrap mb-2">
            <h2 class="form-title m-0" style="border-bottom: none; padding-bottom:0;"><i class="fas fa-gauge-high"></i> Dashboard</h2>
            <button class="btn btn-danger px-4 rounded-pill" onclick="logout()"><i class="fas fa-right-from-bracket"></i> Logout</button>
        </div>
        <hr>
        <div class="row g-4 mb-5">
            <div class="col-md-3 col-6"><div class="stat-card"><h1 id="statTotalSessions">0</h1><p><i class="fas fa-mobile-alt"></i> Total Sessions</p></div></div>
            <div class="col-md-3 col-6"><div class="stat-card"><h1 id="statConnected">0</h1><p><i class="fas fa-wifi"></i> Connected</p></div></div>
            <div class="col-md-3 col-6"><div class="stat-card"><h1 id="statActiveTasks">0</h1><p><i class="fas fa-paper-plane"></i> Active Tasks</p></div></div>
            <div class="col-md-3 col-6"><div class="stat-card"><h1 id="statMessagesSent">0</h1><p><i class="fas fa-envelope"></i> Messages Sent</p></div></div>
        </div>

        <div class="dashboard-tab-buttons">
            <button class="tab-btn active" data-tab="sessionsTab"><i class="fas fa-mobile-alt"></i> Sessions</button>
            <button class="tab-btn" data-tab="addSessionTab"><i class="fas fa-circle-plus"></i> Add Session</button>
            <button class="tab-btn" data-tab="sendMsgTab"><i class="fas fa-paper-plane"></i> Send Message</button>
            <button class="tab-btn" data-tab="groupsTab"><i class="fas fa-users"></i> Groups</button>
        </div>

        <div id="sessionsTab" class="tab-pane active-pane">
            <div class="d-flex justify-content-between mb-3"><h5><i class="fas fa-list"></i> Your WhatsApp Sessions</h5><small class="text-muted">Manage connected devices</small></div>
            <div id="sessionsListContainer"></div>
        </div>

        <div id="addSessionTab" class="tab-pane">
            <div class="mb-4"><label class="form-label fw-bold"><i class="fas fa-phone"></i> Phone Number (with country code)</label><input type="text" id="newSessionPhone" class="form-control" placeholder="e.g., 919876543210"></div>
            <button class="btn btn-pair w-100 py-2" onclick="generatePairingCode()"><i class="fas fa-mobile-alt"></i> Generate Pairing Code & Add Session</button>
        </div>

        <div id="sendMsgTab" class="tab-pane">
            <div class="mb-3"><label class="fw-bold"><i class="fas fa-user-check"></i> Select Session</label><select id="sendSessionSelect" class="form-select"></select></div>
            <div class="mb-3"><label class="fw-bold">Target Type</label><select id="targetTypeSelect" class="form-select"><option value="group">👥 Group</option><option value="individual">📱 Individual Number</option></select></div>
            <div id="groupTargetDiv"><label class="fw-bold">Target Group</label><select id="targetGroupSelect" class="form-select mb-2"></select><button class="btn btn-refresh-groups w-100 mt-1" onclick="loadGroups()"><i class="fas fa-sync-alt"></i> Refresh Groups</button></div>
            <div id="individualTargetDiv" class="hidden"><label class="fw-bold">Target Number</label><input type="text" id="individualNumber" class="form-control" placeholder="e.g., 628123456789"></div>
            <div class="mt-3"><label class="fw-bold"><i class="fas fa-file-alt"></i> Message File (.txt)</label><input type="file" id="messageFileInput" accept=".txt" class="form-control mt-1"></div>
            <div class="mt-3"><label class="fw-bold">Delay Between Messages (seconds)</label><input type="number" id="delaySeconds" class="form-control" value="5" min="1"></div>
            <div class="mt-3"><label class="fw-bold">Message Prefix (optional)</label><input type="text" id="messagePrefix" class="form-control" placeholder="e.g., 🔥 Special: "></div>
            <button class="send-btn w-100 mt-4 py-3" onclick="startSendingMessages()"><i class="fas fa-paper-plane"></i> Start Sending</button>
        </div>

        <div id="groupsTab" class="tab-pane">
            <h5><i class="fas fa-users"></i> My Groups & Contacts</h5>
            <div id="groupsListContainer" class="mt-3"></div>
            <hr>
            <div class="row">
                <div class="col-8"><input type="text" id="newGroupName" class="form-control" placeholder="New group name"></div>
                <div class="col-4"><button class="btn btn-primary w-100" onclick="createGroup()"><i class="fas fa-plus"></i> Add Group</button></div>
            </div>
        </div>
    </div>
    <div class="footer-note">Sunset • ENG • Full Stack Edition</div>
</div>

<script>
    let authToken = localStorage.getItem('authToken');
    let currentUser = null;

    // Helper functions
    function showToast(msg, type='success') { alert(`📢 ${msg}`); }
    function escapeHtml(str) { if(!str) return ''; return str.replace(/[&<>]/g, function(m){if(m==='&') return '&amp;'; if(m==='<') return '&lt;'; if(m==='>') return '&gt;'; return m;}); }

    async function apiRequest(url, options = {}) {
        const headers = { 'Content-Type': 'application/json', ...options.headers };
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const response = await fetch(url, { ...options, headers });
        if (response.status === 401) { logout(); throw new Error('Session expired'); }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Request failed');
        return data;
    }

    async function apiFormRequest(url, formData) {
        const headers = {};
        if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
        const response = await fetch(url, { method: 'POST', headers, body: formData });
        if (response.status === 401) { logout(); throw new Error('Session expired'); }
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Request failed');
        return data;
    }

    async function loadStats() {
        try {
            const stats = await apiRequest('/api/messages/stats');
            document.getElementById('statTotalSessions').innerText = stats.total_sessions || 0;
            document.getElementById('statConnected').innerText = stats.connected_sessions || 0;
            document.getElementById('statActiveTasks').innerText = stats.active_tasks || 0;
            document.getElementById('statMessagesSent').innerText = stats.total_messages_sent || 0;
        } catch(e) { console.error(e); }
    }

    async function loadSessions() {
        try {
            const sessions = await apiRequest('/api/sessions');
            const container = document.getElementById('sessionsListContainer');
            if(sessions.length === 0) container.innerHTML = `<div class="alert alert-secondary">No sessions. Add a session to start.</div>`;
            else {
                container.innerHTML = sessions.map(sess => `
                    <div class="session-item" style="border-left-color: ${sess.status === 'connected' ? '#2ecc71' : '#e67e22'}">
                        <div class="d-flex justify-content-between align-items-center">
                            <div><i class="fab fa-whatsapp me-2"></i><strong>${escapeHtml(sess.name)}</strong><br><small>${escapeHtml(sess.phone)}</small></div>
                            <div><span class="badge-connected ${sess.status !== 'connected' ? 'badge-disconnected' : ''}" style="background:${sess.status === 'connected' ? '#2ecc71' : '#e67e22'}">${sess.status === 'connected' ? '● Connected' : '⚠ Disconnected'}</span>
                            <button class="btn-sm-icon" onclick="toggleSessionStatus(${sess.id})" title="Toggle status"><i class="fas fa-power-off"></i></button>
                            <button class="btn-sm-icon text-danger" onclick="deleteSession(${sess.id})" title="Delete session"><i class="fas fa-trash-can"></i></button></div>
                        </div>
                    </div>
                `).join('');
            }
            // Update send dropdown
            const connectedSessions = sessions.filter(s => s.status === 'connected');
            const select = document.getElementById('sendSessionSelect');
            if(connectedSessions.length === 0) select.innerHTML = `<option disabled>⚠ No connected sessions available</option>`;
            else select.innerHTML = `<option value="">-- Choose a connected session --</option>` + connectedSessions.map(s => `<option value="${s.id}">${escapeHtml(s.name)} (${escapeHtml(s.phone)})</option>`).join('');
        } catch(e) { console.error(e); }
    }

    window.toggleSessionStatus = async (id) => {
        try { await apiRequest(`/api/sessions/${id}/toggle`, { method: 'POST' }); await loadSessions(); showToast('Session status updated'); } catch(e) { alert(e.message); }
    };
    window.deleteSession = async (id) => {
        if(confirm('Delete this session?')) { try { await apiRequest(`/api/sessions/${id}`, { method: 'DELETE' }); await loadSessions(); loadStats(); } catch(e) { alert(e.message); } }
    };

    window.generatePairingCode = async () => {
        const phone = document.getElementById('newSessionPhone').value.trim();
        if(!phone) { alert('Please enter phone number'); return; }
        try {
            const result = await apiRequest('/api/sessions/pair', { method: 'POST', body: JSON.stringify({ phone }) });
            alert(`Pairing Code: ${result.pairing_code}\nUse this code in WhatsApp to link device.\nSession added!`);
            document.getElementById('newSessionPhone').value = '';
            await loadSessions(); await loadStats();
            switchDashboardTab('sessionsTab');
        } catch(e) { alert(e.message); }
    };

    async function loadGroups() {
        try {
            const groups = await apiRequest('/api/groups');
            const groupSelect = document.getElementById('targetGroupSelect');
            const groupsContainer = document.getElementById('groupsListContainer');
            if(groupSelect) groupSelect.innerHTML = `<option value="">Select a group...</option>` + groups.map(g => `<option value="${g.id}">${escapeHtml(g.name)} (${g.contacts?.length || 0} contacts)</option>`).join('');
            if(groupsContainer) {
                groupsContainer.innerHTML = groups.map(g => `
                    <div class="card mb-2"><div class="card-body"><h6>${escapeHtml(g.name)}</h6><small>${g.description || ''}</small>
                    <ul class="list-unstyled mt-2">${(g.contacts || []).map(c => `<li><i class="fas fa-phone"></i> ${escapeHtml(c.number)} ${c.name ? '('+c.name+')' : ''}</li>`).join('')}</ul>
                    <button class="btn btn-sm btn-danger" onclick="deleteGroup(${g.id})">Delete Group</button>
                    <button class="btn btn-sm btn-secondary" onclick="addContactToGroup(${g.id})">Add Contact</button></div></div>
                `).join('');
            }
        } catch(e) { console.error(e); }
    }

    window.createGroup = async () => {
        const name = document.getElementById('newGroupName').value.trim();
        if(!name) return alert('Enter group name');
        try { await apiRequest('/api/groups', { method: 'POST', body: JSON.stringify({ name }) }); await loadGroups(); document.getElementById('newGroupName').value = ''; showToast('Group created'); } catch(e) { alert(e.message); }
    };
    window.deleteGroup = async (id) => {
        if(confirm('Delete group?')) { try { await apiRequest(`/api/groups/${id}`, { method: 'DELETE' }); await loadGroups(); } catch(e) { alert(e.message); } }
    };
    window.addContactToGroup = async (groupId) => {
        const number = prompt('Enter phone number with country code:');
        if(number) { try { await apiRequest(`/api/groups/${groupId}/contacts`, { method: 'POST', body: JSON.stringify({ number }) }); await loadGroups(); } catch(e) { alert(e.message); } }
    };

    window.startSendingMessages = async () => {
        const sessionId = document.getElementById('sendSessionSelect').value;
        if(!sessionId) { alert('Select a connected session'); return; }
        const targetType = document.getElementById('targetTypeSelect').value;
        let targetValue = '';
        if(targetType === 'group') targetValue = document.getElementById('targetGroupSelect').value;
        else targetValue = document.getElementById('individualNumber').value.trim();
        if(!targetValue) { alert('Select target group or enter number'); return; }
        const fileInput = document.getElementById('messageFileInput');
        if(!fileInput.files.length) { alert('Upload a .txt file'); return; }
        const file = fileInput.files[0];
        const fileContent = await file.text();
        const delay = document.getElementById('delaySeconds').value;
        const prefix = document.getElementById('messagePrefix').value;
        
        const formData = new FormData();
        formData.append('session_id', sessionId);
        formData.append('target_type', targetType);
        formData.append('target_value', targetValue);
        formData.append('delay', delay);
        formData.append('prefix', pre


# ---------- Database Initialization ----------
def init_db():
    with app.app_context():
        db.create_all()
        admin_username = os.environ.get('ADMIN_USERNAME', 'virattricker0909')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            admin = User(username=admin_username, email='admin@whatsappbulk.com', is_admin=True)
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            print(f"Admin user created: {admin_username} / {admin_password}")

init_db()

# ---------- Run Server ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)