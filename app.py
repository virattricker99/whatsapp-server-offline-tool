import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, render_template_string, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    db_url = os.getenv("DATABASE_URL", "sqlite:///app.db").strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "2")) * 1024 * 1024
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v26.0").strip()
    DEFAULT_MESSAGE = os.getenv("DEFAULT_MESSAGE", "Hello from Virat Rajput").strip()
    DEFAULT_DELAY = int(os.getenv("DEFAULT_DELAY", "5"))
    MIN_DELAY = int(os.getenv("MIN_DELAY", "3"))
    MAX_DELAY = int(os.getenv("MAX_DELAY", "120"))
    MAX_RECIPIENTS = int(os.getenv("MAX_RECIPIENTS", "500"))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("whatsapp-cloud-console")
db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    task_ref = db.Column(db.String(64), unique=True, nullable=False, index=True)
    target_type = db.Column(db.String(20), nullable=False)
    target = db.Column(db.String(255))
    status = db.Column(db.String(20), default="queued", nullable=False)
    total = db.Column(db.Integer, default=0, nullable=False)
    processed = db.Column(db.Integer, default=0, nullable=False)
    succeeded = db.Column(db.Integer, default=0, nullable=False)
    failed = db.Column(db.Integer, default=0, nullable=False)
    delay_seconds = db.Column(db.Integer, default=5, nullable=False)
    prefix = db.Column(db.String(255), default="")
    opt_in_confirmed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    error_message = db.Column(db.Text)

class MessageLog(db.Model):
    __tablename__ = "message_logs"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, index=True)
    recipient = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(20), default="queued", nullable=False)
    wa_message_id = db.Column(db.String(128), index=True)
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WHAT'S APP NON STOP SERVER BY VIRAT RAJPUT</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<style>
  :root { --white:#FFFFFF; --black:#000000; --navy:#0B132B; --navy-light:#1C2541; --sky:#38BDF8; --sky-dark:#0284C7; --light-grey:#F3F4F6; }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: radial-gradient(1200px 800px at 10% -10%, rgba(56,189,248,0.15), transparent 60%), radial-gradient(900px 700px at 110% 10%, rgba(28,37,65,0.8), transparent 60%), var(--navy);
    color: var(--white); min-height: 100vh; margin: 0; overflow-x: hidden;
  }
  .glow-heading { font-weight: 900; font-style: italic; letter-spacing: 0.5px; color: var(--white); text-shadow: 0 0 15px rgba(56,189,248,0.4); margin: 0; }
  .accent { color: var(--sky); }
  .bg-particles {
    position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background-image: radial-gradient(circle at 20% 30%, rgba(56,189,248,.10) 0 2px, transparent 3px), radial-gradient(circle at 80% 60%, rgba(255,255,255,.05) 0 2px, transparent 3px), radial-gradient(circle at 50% 80%, rgba(56,189,248,.06) 0 2px, transparent 3px);
    background-size: 200px 200px, 300px 300px, 250px 250px; animation: drift 40s linear infinite;
  }
  @keyframes drift { from { background-position: 0 0, 0 0, 0 0; } to { background-position: 400px 400px, 600px 600px, 500px 500px; } }
  .glass-card { background: rgba(28, 37, 65, 0.6); border: 1px solid rgba(56, 189, 248, 0.2); backdrop-filter: blur(16px); border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
  .form-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.6px; color: var(--sky); font-weight: 800; font-style: italic; }
  .form-control, .form-select { background: rgba(11, 19, 43, 0.6); border: 1px solid rgba(56, 189, 248, 0.3); color: var(--white); border-radius: 12px; padding: 0.75rem 1rem; font-weight: 500; }
  .form-control:focus, .form-select:focus { background: rgba(11, 19, 43, 0.9); color: var(--white); border-color: var(--sky); box-shadow: 0 0 0 0.25rem rgba(56, 189, 248, 0.25); }
  .form-control::placeholder { color: rgba(255,255,255,0.3); }
  .form-select option { background: var(--navy); color: var(--white); }
  .btn-red { background: #DC2626; border: 0; color: var(--white); font-weight: 800; border-radius: 12px; transition: all 0.3s ease; }
  .btn-red:hover { background: #b91c1c; color: var(--white); transform: translateY(-2px); box-shadow: 0 10px 24px rgba(220,38,38,0.4); }
  .btn-sky { background: var(--sky); border: 0; color: var(--navy); font-weight: 800; border-radius: 12px; transition: all 0.3s ease; }
  .btn-sky:hover { background: var(--sky-dark); color: var(--white); transform: translateY(-2px); box-shadow: 0 10px 24px rgba(56,189,248,0.4); }
  .topbar { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.5rem; margin: 1rem; border-radius: 16px; flex-wrap: wrap; gap: 1rem; }
  .brand { font-weight: 900; font-style: italic; font-size: 1.2rem; display: flex; align-items: center; gap: 0.5rem; color: var(--white); }
  .brand i { font-size: 1.5rem; color: var(--sky); }
  .nav-right { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .clock { font-variant-numeric: tabular-nums; color: var(--sky); font-weight: 700; font-size: 1rem; }
  .badge-status { background: rgba(220,38,38,0.2); border: 1px solid #DC2626; color: var(--white); padding: 0.4rem 0.9rem; border-radius: 20px; font-weight: 700; font-size: 0.8rem; font-style: italic; }
  .badge-status.connected { background: rgba(56,189,248,0.2); border-color: var(--sky); color: var(--sky); }
  .card-icon { width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 24px; color: var(--navy); margin-bottom: 1rem; background: var(--sky); box-shadow: 0 0 15px rgba(56,189,248,0.3); }
  .card-title { font-weight: 900; font-style: italic; letter-spacing: 0.5px; font-size: 1.05rem; margin-bottom: 0.5rem; color: var(--white); }
  .small-muted { font-size: 0.85rem; color: #9CA3AF; font-weight: 500; }
  .custom-toast { background: var(--navy-light); border-left: 4px solid var(--sky); color: var(--white); padding: 1rem 1.2rem; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem; animation: slideIn 0.3s ease; }
  .custom-toast.success { border-left-color: #22c55e; }
  .custom-toast.error { border-left-color: #DC2626; }
  .custom-toast.warning { border-left-color: #F59E0B; }
  @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
  .site-footer { text-align: center; padding: 2.5rem 1rem; margin-top: 3rem; border-top: 1px solid rgba(56,189,248,0.15); font-size: 0.85rem; background: rgba(11, 19, 43, 0.4); }
  .site-footer a { color: var(--sky); text-decoration: none; font-weight: 600; }
  .site-footer a:hover { color: var(--white); }
  .animate-in { animation: fadeInUp 0.7s ease both; }
  @keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
  .hidden { display: none !important; }
  @media (max-width: 576px) { .topbar { margin: 0.5rem; padding: 0.8rem; } .clock { font-size: 0.85rem; } .card-title { font-size: 0.95rem; } }
</style>
</head>
<body>
<div class="bg-particles"></div>
<div id="dashboard-page">
  <nav class="topbar glass-card">
    <div class="brand"><i class="bi bi-whatsapp"></i><span>VIRAT<span class="accent">SERVER</span></span></div>
    <div class="nav-right">
      <span class="clock" id="clock">--:--:--</span>
      <span class="badge badge-status" id="conn-badge">Disconnected</span>
    </div>
  </nav>
  <div class="container-fluid px-3 px-md-4 mt-4">
    <div class="row g-4">
      <div class="col-12 col-lg-6">
        <div class="glass-card p-4 animate-in h-100">
          <div class="card-icon"><i class="bi bi-phone"></i></div>
          <h5 class="card-title">WHATSAPP CLOUD API CONNECTION</h5>
          <p class="small-muted mb-3">Connect your WhatsApp Business account via official Cloud API.</p>
          <div class="mb-3">
            <label class="form-label" for="wa-phone">WhatsApp Phone Number (E.164)</label>
            <input id="wa-phone" class="form-control" placeholder="+919876543210">
          </div>
          <button id="btn-connect" class="btn btn-red w-100 py-2"><i class="bi bi-key-fill"></i> VERIFY CLOUD API CONNECTION</button>
          <div class="mt-3 small-muted" id="conn-result">Status: <b>Not Configured</b></div>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="glass-card p-4 animate-in h-100">
          <div class="card-icon"><i class="bi bi-send-fill"></i></div>
          <h5 class="card-title">BULK MESSAGING BY VIRAT RAJPUT</h5>
          <p class="small-muted mb-3">Send the configured plain-text message to opted-in recipients with controlled scheduling.</p>
          <form id="bulk-form" enctype="multipart/form-data">
            <div class="mb-2">
              <label class="form-label" for="target_type">Target Type</label>
              <select class="form-select" name="target_type" id="target_type" onchange="toggleTargetInput()">
                <option value="phone">Phone Number</option>
                <option value="group" disabled>Group ID (not available)</option>
              </select>
            </div>
            <div id="phone-input-group" class="mb-2">
              <label class="form-label" for="target_phone">Target Number (E.164)</label>
              <input class="form-control" name="target_phone" id="target_phone" placeholder="+919876543210">
            </div>
            <div id="group-input-group" class="mb-2 hidden">
              <label class="form-label" for="target_group">Select WhatsApp Group</label>
              <select class="form-select mb-2" id="group_list" onchange="document.getElementById('target_group_id').value = this.value">
                <option value="">-- Loading Groups... --</option>
              </select>
              <input class="form-control" name="target_group_id" id="target_group_id" placeholder="Or enter Group ID manually">
            </div>
            <div class="mb-2 mt-3">
              <label class="form-label" for="file">Recipient List (.txt)</label>
              <input class="form-control" type="file" name="file" id="file" accept=".txt">
              <small class="small-muted" id="file-name"></small>
            </div>
            <div class="row g-2 mt-1">
              <div class="col-12 col-md-7">
                <label class="form-label" for="prefix">Prefix (Optional)</label>
                <input class="form-control" name="prefix" id="prefix" placeholder="ADD PREFIX">
              </div>
              <div class="col-12 col-md-5">
                <label class="form-label" for="delay">Delay (Sec)</label>
                <input class="form-control" type="number" name="delay" id="delay" value="5" min="3" max="120">
              </div>
            </div>
            <button type="submit" class="btn btn-red w-100 py-2 mt-3"><i class="bi bi-play-fill"></i> START SENDING</button>
          </form>
          <div id="bulk-result" class="mt-3 small-muted"></div>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="glass-card p-4 animate-in h-100">
          <div class="card-icon"><i class="bi bi-gear-fill"></i></div>
          <h5 class="card-title">TASK MANAGEMENT</h5>
          <p class="small-muted mb-3">Monitor and control your active messaging tasks.</p>
          <button id="btn-last" class="btn btn-sky w-100 py-2 mb-3"><i class="bi bi-eye-fill"></i> SHOW LAST TASK ID</button>
          <div id="last-task" class="small-muted mb-3"></div>
          <label class="form-label" for="stop-task-id">Stop Task</label>
          <input id="stop-task-id" class="form-control mb-2" placeholder="ENTER TASK ID">
          <button id="btn-stop" class="btn btn-red w-100 py-2"><i class="bi bi-stop-fill"></i> STOP TASK</button>
          <div id="stop-result" class="mt-2 small-muted"></div>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="glass-card p-4 animate-in h-100">
          <div class="card-icon"><i class="bi bi-person-badge"></i></div>
          <h5 class="card-title">SESSION INFORMATION</h5>
          <p class="small-muted mb-1">Server Session</p>
          <p class="small-muted mb-1">Session Ref: <code id="session-ref">N/A</code></p>
          <p class="small-muted mb-0">Last Task: <code id="session-lasttask">none</code></p>
        </div>
      </div>
    </div>
  </div>
  <footer class="site-footer">
    <p class="glow-heading" style="font-size:1.1rem;">MADE BY <span class="accent">VIRAT RAJPUT</span></p>
    <p class="small-muted mb-2" style="font-weight:700; font-style:italic;">SOFTWARE AND WEB DEVELOPER</p>
    <p class="mb-2">
      <a href="https://wa.me/917310927827" target="_blank"><i class="bi bi-whatsapp"></i> WhatsApp: 7310927827</a> · 
      <a href="https://t.me/Viratdeveloper988" target="_blank"><i class="bi bi-telegram"></i> Telegram</a>
    </p>
    <p class="small-muted mb-0">© 2026 Virat Rajput. All rights reserved.</p>
  </footer>
</div>
<div id="toast-container" class="position-fixed bottom-0 end-0 p-3" style="z-index:9999;"></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
function getAdminKey(){
  let key = sessionStorage.getItem('wa_admin_api_key');
  if(!key){
    key = window.prompt('Enter the ADMIN_API_KEY configured in your Render service:');
    if(key) sessionStorage.setItem('wa_admin_api_key', key.trim());
  }
  return key ? key.trim() : '';
}
async function apiFetch(url, options={}){
  let key = getAdminKey();
  if(!key) throw new Error('Admin key is required for this action.');
  const send = (secret) => {
    const headers = new Headers(options.headers || {});
    headers.set('X-Admin-Key', secret);
    return fetch(url, {...options, headers});
  };
  let response = await send(key);
  if(response.status === 401){
    sessionStorage.removeItem('wa_admin_api_key');
    key = window.prompt('Admin key rejected. Enter the correct ADMIN_API_KEY:');
    if(!key) return response;
    sessionStorage.setItem('wa_admin_api_key', key.trim());
    response = await send(key.trim());
  }
  return response;
}
function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function toast(msg, type='info'){
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = 'custom-toast ' + type;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(()=>{ el.style.opacity='0'; setTimeout(()=>el.remove(),300); }, 4000);
}
function startClock(){
  const c = document.getElementById('clock');
  setInterval(()=>{ c.textContent = new Date().toLocaleTimeString(); }, 1000);
}
document.addEventListener('DOMContentLoaded', ()=>{
  startClock();
  document.getElementById('session-ref').textContent = Math.random().toString(16).slice(2,10).toUpperCase();
});
function toggleTargetInput(){
  const type = document.getElementById('target_type').value;
  document.getElementById('phone-input-group').classList.toggle('hidden', type!=='phone');
  document.getElementById('group-input-group').classList.toggle('hidden', type!=='group');
  if(type==='group') loadWhatsAppGroups();
}
function loadWhatsAppGroups(){
  const sel = document.getElementById('group_list');
  sel.innerHTML = '<option value="" disabled selected>Group messaging is not enabled</option>';
}
document.getElementById('btn-connect').addEventListener('click', async function(){
  const phone = document.getElementById('wa-phone').value.trim();
  const out = document.getElementById('conn-result');
  if(!/^\+[1-9]\d{7,14}$/.test(phone)){ toast('Invalid phone format','error'); return; }
  const btn = this; btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Verifying...';
  try {
    const res = await apiFetch('/api/whatsapp/connect', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({phone}) });
    const data = await res.json();
    if(data.ok){
      toast('Connected','success');
      out.innerHTML = `Status: <b>Connected</b> — ${escapeHtml(data.display_phone || data.phone_number_id)}`;
      const b = document.getElementById('conn-badge'); b.textContent='Connected'; b.classList.add('connected');
    } else {
      toast(data.error||'Failed','error');
      out.innerHTML = `<span style="color:#fca5a5;">${escapeHtml(data.error||'Failed')}</span>`;
    }
  } catch(e){ toast('Network error','error'); }
  finally { btn.disabled = false; btn.innerHTML = '<i class="bi bi-key-fill"></i> VERIFY CLOUD API CONNECTION'; }
});
document.getElementById('file').addEventListener('change', e=>{
  document.getElementById('file-name').textContent = e.target.files[0] ? 'Selected: '+e.target.files[0].name : '';
});
document.getElementById('bulk-form').addEventListener('submit', async function(e){
  e.preventDefault();
  const file = document.getElementById('file').files[0];
  const singleNumber = document.getElementById('target_phone').value.trim();
  if(!file && !singleNumber){ toast('Enter one E.164 number or choose a recipient list','error'); return; }
  if(!window.confirm('Confirm that every number in this file explicitly opted in to receive messages from your business AND has an open WhatsApp 24-hour customer-service window. This app sends free-form text only; approved templates are not enabled. Continue?')) return;
  const form = e.target; const fd = new FormData(form);
  fd.append('opt_in_confirmed', 'yes');
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
  try {
    const res = await apiFetch('/api/bulk/create', { method:'POST', body: fd });
    const data = await res.json();
    const out = document.getElementById('bulk-result');
    if(data.ok){
      out.innerHTML = `Task created: <code>${data.task_id}</code> — Recipients: ${data.total}`;
      toast('Task created','success');
      document.getElementById('session-lasttask').textContent = data.task_id;
    } else {
      out.innerHTML = `<span style="color:#fca5a5;">${escapeHtml(data.error)}</span>`;
      toast(data.error,'error');
    }
  } catch(err){ toast('Network error','error'); }
  finally { btn.disabled = false; btn.innerHTML = '<i class="bi bi-play-fill"></i> START SENDING'; }
});
document.getElementById('btn-last').addEventListener('click', async ()=>{
  const el = document.getElementById('last-task');
  try {
    const res = await apiFetch('/api/tasks/last'); const d = await res.json();
    if(d.ok){
      const t = d.task;
      el.innerHTML = `<b>${escapeHtml(t.task_ref)}</b><br>Status: ${escapeHtml(t.status)}<br>Progress: ${escapeHtml(t.processed)}/${escapeHtml(t.total)}<br>✓ ${escapeHtml(t.succeeded)} · ✗ ${escapeHtml(t.failed)}`;
    } else { el.innerHTML = `<span style="color:#fbbf24;">${d.message}</span>`; }
  } catch(e){ toast('Network error','error'); }
});
document.getElementById('btn-stop').addEventListener('click', async ()=>{
  const ref = document.getElementById('stop-task-id').value.trim();
  if(!ref){ toast('Enter task ID','error'); return; }
  if(!confirm('Stop task '+ref+'?')) return;
  try {
    const res = await apiFetch(`/api/tasks/${encodeURIComponent(ref)}/stop`, { method:'POST' });
    const d = await res.json();
    document.getElementById('stop-result').textContent = d.message || d.error;
    toast(d.message || d.error, d.ok ? 'success':'error');
  } catch(e){ toast('Network error','error'); }
});
</script>
</body>
</html>
"""

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.before_request
def protect_private_api():
    if not request.path.startswith("/api/"):
        return None
    expected = current_app.config.get("ADMIN_API_KEY", "").strip()
    supplied = request.headers.get("X-Admin-Key", "").strip()
    if not expected:
        return jsonify({"ok": False, "error": "ADMIN_API_KEY is not configured on the server. API actions are disabled."}), 503
    if not supplied or not hmac.compare_digest(supplied, expected):
        return jsonify({"ok": False, "error": "Admin key required or invalid."}), 401
    return None

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"ok": False, "error": "Upload exceeds the configured size limit."}), 413

@app.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    log.exception("Database operation failed: %s", error)
    return jsonify({"ok": False, "error": "Database operation failed. Check the database configuration and logs."}), 500

def is_configured():
    return bool(current_app.config.get("WHATSAPP_ACCESS_TOKEN") and current_app.config.get("WHATSAPP_PHONE_NUMBER_ID"))

def _headers():
    return {"Authorization": f"Bearer {current_app.config['WHATSAPP_ACCESS_TOKEN']}"}

def _graph_url(path=""):
    version = current_app.config["WHATSAPP_API_VERSION"]
    return f"https://graph.facebook.com/{version}/{path.lstrip('/')}"

def health_check():
    if not is_configured():
        return {"ok": False, "reason": "WhatsApp Cloud API credentials are not configured in the server environment."}
    try:
        response = requests.get(
            _graph_url(current_app.config["WHATSAPP_PHONE_NUMBER_ID"]),
            headers=_headers(),
            params={"fields": "display_phone_number,verified_name,quality_rating"},
            timeout=(5, 15),
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.ok:
            return {"ok": True, "data": data}
        meta_error = (data.get("error") or {}).get("message")
        return {"ok": False, "reason": f"Meta API returned HTTP {response.status_code}: {meta_error or 'connection check failed'}"}
    except requests.RequestException as exc:
        log.warning("WhatsApp connection check failed: %s", exc)
        return {"ok": False, "reason": "Could not reach Meta Graph API. Check the service logs/network and try again."}
    except ValueError:
        return {"ok": False, "reason": "Meta API returned an unreadable response."}

def send_text(to, body):
    if not is_configured():
        return {"ok": False, "error": "WhatsApp Cloud API credentials are not configured."}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    try:
        response = requests.post(
            _graph_url(f"{current_app.config['WHATSAPP_PHONE_NUMBER_ID']}/messages"),
            headers={**_headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=(5, 20),
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.ok:
            messages = data.get("messages") or []
            message_id = messages[0].get("id") if messages else None
            return {"ok": True, "message_id": message_id}
        meta_error = (data.get("error") or {}).get("message")
        return {"ok": False, "error": f"Meta API returned HTTP {response.status_code}: {meta_error or 'message rejected'}"}
    except requests.Timeout:
        return {"ok": False, "unknown": True, "error": "Meta request timed out; delivery status is unknown. No automatic retry was made."}
    except requests.RequestException as exc:
        log.warning("WhatsApp send request failed: %s", exc)
        return {"ok": False, "unknown": True, "error": "Could not confirm Meta response. Delivery may be unknown; no automatic retry was made."}
    except ValueError:
        return {"ok": False, "unknown": True, "error": "Meta returned an unreadable response; delivery may be unknown. No automatic retry was made."}

def serialize_task(task):
    return {
        "task_ref": task.task_ref,
        "status": task.status,
        "total": task.total,
        "processed": task.processed,
        "succeeded": task.succeeded,
        "failed": task.failed,
        "delay_seconds": task.delay_seconds,
        "target_type": task.target_type,
        "target": task.target,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "error": task.error_message,
    }

def run_task(task_id):
    with app.app_context():
        try:
            task = db.session.get(Task, task_id)
            if not task or task.status == "cancelled":
                return
            task.status = "running"
            task.updated_at = utcnow()
            db.session.commit()
            message_logs = MessageLog.query.filter_by(task_id=task_id).order_by(MessageLog.id).all()
            for item in message_logs:
                db.session.expire_all()
                task = db.session.get(Task, task_id)
                if not task or task.status == "cancelled":
                    log.info("Task cancelled: %s", task_id)
                    return
                item = db.session.get(MessageLog, item.id)
                if not item or item.status != "queued":
                    continue
                body = (task.prefix + " " if task.prefix else "") + current_app.config["DEFAULT_MESSAGE"]
                result = send_text(item.recipient, body)
                if result.get("ok"):
                    item.status = "accepted"
                    item.wa_message_id = result.get("message_id")
                    task.succeeded += 1
                else:
                    item.status = "unknown" if result.get("unknown") else "failed"
                    item.error = (result.get("error") or "Message rejected")[:500]
                    task.failed += 1
                task.processed += 1
                task.updated_at = utcnow()
                db.session.commit()
                if item.id != message_logs[-1].id:
                    time.sleep(task.delay_seconds)
            task = db.session.get(Task, task_id)
            if task and task.status != "cancelled":
                task.status = "completed"
                task.updated_at = utcnow()
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            log.exception("Task runner failed for task id %s", task_id)
            task = db.session.get(Task, task_id)
            if task:
                task.status = "failed"
                task.error_message = "Task runner stopped unexpectedly; review message statuses before retrying."
                task.updated_at = utcnow()
                db.session.commit()
        finally:
            db.session.remove()

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/api/whatsapp/connect", methods=["POST"])
def whatsapp_connect():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        return jsonify({"ok": False, "error": "Enter a phone number in E.164 format, including + and country code."}), 400
    if not is_configured():
        return jsonify({"ok": False, "error": "Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in Render Environment first."}), 400
    result = health_check()
    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("reason", "Connection check failed.")}), 502
    data = result["data"]
    number_digits = re.sub(r"\D", "", phone)
    configured_digits = re.sub(r"\D", "", data.get("display_phone_number", ""))
    if configured_digits and number_digits != configured_digits:
        return jsonify({"ok": False, "error": "The number entered does not match the Cloud API phone number configured on this server."}), 400
    return jsonify({
        "ok": True,
        "display_phone": data.get("display_phone_number"),
        "verified_name": data.get("verified_name"),
        "phone_number_id": data.get("id"),
    })

@app.route("/api/whatsapp/groups", methods=["GET"])
def whatsapp_groups():
    return jsonify({"ok": False, "groups": [], "note": "Group sending is not implemented in this individual-recipient console."})

def valid_e164(value):
    return bool(re.fullmatch(r"\+[1-9]\d{7,14}", value))

@app.route("/api/bulk/create", methods=["POST"])
def bulk_create():
    if not is_configured():
        return jsonify({"ok": False, "error": "WhatsApp Cloud API is not configured on the server."}), 503
    if request.form.get("opt_in_confirmed") != "yes":
        return jsonify({"ok": False, "error": "Confirm that every recipient opted in and is eligible for a free-form message before sending."}), 400
    target_type = (request.form.get("target_type") or "phone").strip()
    if target_type != "phone":
        return jsonify({"ok": False, "error": "This app sends individual Cloud API messages only; group messaging is not enabled."}), 400
    prefix = (request.form.get("prefix") or "").strip()
    if len(prefix) > 200:
        return jsonify({"ok": False, "error": "Prefix must be 200 characters or shorter."}), 400
    try:
        delay = int(request.form.get("delay", current_app.config["DEFAULT_DELAY"]))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Delay must be a number."}), 400
    if delay < current_app.config["MIN_DELAY"] or delay > current_app.config["MAX_DELAY"]:
        return jsonify({"ok": False, "error": f"Delay must be between {current_app.config['MIN_DELAY']} and {current_app.config['MAX_DELAY']} seconds."}), 400
    file = request.files.get("file")
    single_number = (request.form.get("target_phone") or "").strip()
    if file and file.filename:
        if not file.filename.lower().endswith(".txt"):
            return jsonify({"ok": False, "error": "Recipient list must be a .txt file."}), 400
        raw = file.read()
        if not raw:
            return jsonify({"ok": False, "error": "Recipient file is empty."}), 400
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return jsonify({"ok": False, "error": "Recipient file must be UTF-8 encoded."}), 400
        recipients = [line.strip() for line in content.splitlines() if line.strip()]
    elif single_number:
        recipients = [single_number]
    else:
        return jsonify({"ok": False, "error": "Enter one E.164 number or upload a .txt file with one number per line."}), 400
    if not recipients:
        return jsonify({"ok": False, "error": "No recipient numbers found."}), 400
    invalid = [number for number in recipients if not valid_e164(number)]
    if invalid:
        return jsonify({"ok": False, "error": f"Invalid E.164 number on recipient list (example: +919876543210): {invalid[0][:40]}"}), 400
    if len(set(recipients)) != len(recipients):
        return jsonify({"ok": False, "error": "Recipient list contains duplicate numbers. Remove duplicates before sending."}), 400
    if len(recipients) > current_app.config["MAX_RECIPIENTS"]:
        return jsonify({"ok": False, "error": f"Maximum {current_app.config['MAX_RECIPIENTS']} recipients per task."}), 400
    task_ref = "TASK-" + uuid.uuid4().hex[:10].upper()
    task = Task(
        task_ref=task_ref,
        target_type="phone",
        target=f"{len(recipients)} individual recipient(s)",
        status="queued",
        total=len(recipients),
        delay_seconds=delay,
        prefix=prefix,
        opt_in_confirmed=True,
    )
    db.session.add(task)
    db.session.flush()
    for recipient in recipients:
        db.session.add(MessageLog(task_id=task.id, recipient=recipient, status="queued"))
    db.session.commit()
    thread = threading.Thread(target=run_task, args=(task.id,), daemon=True, name=f"wa-{task_ref}")
    thread.start()
    return jsonify({"ok": True, "task_id": task_ref, "total": len(recipients), "target_type": "phone"}), 202

@app.route("/api/tasks/last", methods=["GET"])
def tasks_last():
    task = Task.query.order_by(Task.id.desc()).first()
    if not task:
        return jsonify({"ok": False, "message": "No task has been created yet."}), 404
    return jsonify({"ok": True, "task": serialize_task(task)})

@app.route("/api/tasks/<task_ref>", methods=["GET"])
def task_get(task_ref):
    task = Task.query.filter_by(task_ref=task_ref).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found."}), 404
    return jsonify({"ok": True, "task": serialize_task(task)})

@app.route("/api/tasks/<task_ref>/stop", methods=["POST"])
def task_stop(task_ref):
    task = Task.query.filter_by(task_ref=task_ref).first()
    if not task:
        return jsonify({"ok": False, "error": "Task not found."}), 404
    if task.status in ("completed", "cancelled", "failed"):
        return jsonify({"ok": False, "error": f"Task already {task.status}."}), 400
    task.status = "cancelled"
    task.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "message": f"Task {task_ref} marked cancelled."})

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode", "")
        token = request.args.get("hub.verify_token", "")
        challenge = request.args.get("hub.challenge", "")
        expected = current_app.config.get("WHATSAPP_VERIFY_TOKEN", "")
        if expected and mode == "subscribe" and hmac.compare_digest(token, expected):
            return challenge, 200
        return "Forbidden", 403
    app_secret = current_app.config.get("WHATSAPP_APP_SECRET", "")
    if not app_secret:
        return jsonify({"ok": False, "error": "WHATSAPP_APP_SECRET is not configured."}), 503
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected_signature = "sha256=" + hmac.new(app_secret.encode(), request.get_data(cache=True), hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected_signature):
        return jsonify({"ok": False, "error": "Invalid webhook signature."}), 401
    data = request.get_json(silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status_event in value.get("statuses", []):
                    message_id = status_event.get("id")
                    status = status_event.get("status")
                    if not message_id or not status:
                        continue
                    message_log = MessageLog.query.filter_by(wa_message_id=message_id).first()
                    if message_log:
                        message_log.status = status[:20]
                        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log.exception("Webhook status processing failed: %s", exc)
        return jsonify({"ok": False}), 500
    return jsonify({"ok": True}), 200

with app.app_context():
    db.create_all()
    log.info("Database initialized")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
