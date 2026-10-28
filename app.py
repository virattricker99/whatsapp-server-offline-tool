import os, logging, uuid, threading, time, re
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

# ---------------- CONFIGURATION ----------------
class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    
    db_url = os.getenv("DATABASE_URL", "sqlite:///app.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "2")) * 1024 * 1024
    
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "verify_me")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")
    
    DEFAULT_DELAY = int(os.getenv("DEFAULT_DELAY", "5"))
    MIN_DELAY = int(os.getenv("MIN_DELAY", "3"))
    MAX_DELAY = int(os.getenv("MAX_DELAY", "120"))

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("whatsapp")

# ---------------- DATABASE (using raw SQLite/Postgres via SQLAlchemy - safe fallback) ----------------
# To keep it single-file and avoid extension errors, using a lightweight in-memory + file-based fallback
# For production Render: use PostgreSQL. We'll use SQLAlchemy here.
from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    task_ref = db.Column(db.String(64), unique=True, nullable=False, index=True)
    target_type = db.Column(db.String(20), nullable=False)
    target = db.Column(db.String(255))
    status = db.Column(db.String(20), default="queued")
    total = db.Column(db.Integer, default=0)
    processed = db.Column(db.Integer, default=0)
    succeeded = db.Column(db.Integer, default=0)
    failed = db.Column(db.Integer, default=0)
    delay_seconds = db.Column(db.Integer, default=5)
    prefix = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    error_message = db.Column(db.Text)

class MessageLog(db.Model):
    __tablename__ = "message_logs"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    recipient = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(20), default="queued")
    wa_message_id = db.Column(db.String(128))
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- WHATSAPP SERVICE ----------------
import requests

def is_configured():
    return bool(Config.WHATSAPP_ACCESS_TOKEN and Config.WHATSAPP_PHONE_NUMBER_ID)

def _headers():
    return {"Authorization": f"Bearer {Config.WHATSAPP_ACCESS_TOKEN}"}

def health_check():
    if not is_configured():
        return {"ok": False, "reason": "WhatsApp Cloud API credentials not configured on server."}
    try:
        base = f"https://graph.facebook.com/{Config.WHATSAPP_API_VERSION}"
        r = requests.get(f"{base}/{Config.WHATSAPP_PHONE_NUMBER_ID}", headers=_headers(), timeout=10,
                         params={"fields": "display_phone_number,verified_name,quality_rating"})
        if r.status_code == 200:
            return {"ok": True, "data": r.json()}
        return {"ok": False, "reason": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

def send_text(to, body):
    if not is_configured():
        return {"ok": False, "error": "WhatsApp API not configured"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4096]},
    }
    try:
        base = f"https://graph.facebook.com/{Config.WHATSAPP_API_VERSION}"
        r = requests.post(f"{base}/{Config.WHATSAPP_PHONE_NUMBER_ID}/messages",
                          headers={**_headers(), "Content-Type": "application/json"},
                          json=payload, timeout=15)
        if r.status_code in (200, 201):
            data = r.json()
            msg_id = (data.get("messages") or [{}])[0].get("id")
            return {"ok": True, "message_id": msg_id}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------------- BACKGROUND TASK RUNNER ----------------
def run_task(app_context, task_id, recipients):
    with app_context:
        t = db.session.get(Task, task_id)
        if not t:
            return
        t.status = "running"
        t.updated_at = datetime.utcnow()
        db.session.commit()
        
        logs = MessageLog.query.filter_by(task_id=t.id).order_by(MessageLog.id).all()
        
        for idx, phone in enumerate(recipients):
            db.session.refresh(t)
            if t.status == "cancelled":
                log.info(f"Task {t.task_ref} cancelled at {idx}/{t.total}")
                return
            
            body = (t.prefix + " " if t.prefix else "") + "Hello from Virat Rajput"
            res = send_text(phone, body)
            
            if res["ok"]:
                logs[idx].status = "sent"
                logs[idx].wa_message_id = res.get("message_id")
                t.succeeded += 1
            else:
                logs[idx].status = "failed"
                logs[idx].error = res.get("error", "unknown")[:500]
                t.failed += 1
            
            t.processed += 1
            t.updated_at = datetime.utcnow()
            db.session.commit()
            
            if idx < len(recipients) - 1:
                time.sleep(t.delay_seconds)
        
        db.session.refresh(t)
        t.status = "completed"
        t.updated_at = datetime.utcnow()
        db.session.commit()
        log.info(f"Task {t.task_ref} completed")

# ---------------- SERIALIZER ----------------
def serialize_task(t):
    return {
        "task_ref": t.task_ref,
        "status": t.status,
        "total": t.total,
        "processed": t.processed,
        "succeeded": t.succeeded,
        "failed": t.failed,
        "delay_seconds": t.delay_seconds,
        "target_type": t.target_type,
        "target": t.target,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "error": t.error_message,
    }

# ---------------- HTML (EMBEDDED) ----------------
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
          <h5 class="card-title">DEVICE PAIRING / WHATSAPP CONNECTION</h5>
          <p class="small-muted mb-3">Connect your WhatsApp Business account via official Cloud API.</p>
          <div class="mb-3">
            <label class="form-label" for="wa-phone">WhatsApp Phone Number (E.164)</label>
            <input id="wa-phone" class="form-control" placeholder="+919876543210">
          </div>
          <button id="btn-connect" class="btn btn-red w-100 py-2"><i class="bi bi-key-fill"></i> GENERATE / VERIFY CONNECTION</button>
          <div class="mt-3 small-muted" id="conn-result">Status: <b>Not Configured</b></div>
        </div>
      </div>
      <div class="col-12 col-lg-6">
        <div class="glass-card p-4 animate-in h-100">
          <div class="card-icon"><i class="bi bi-send-fill"></i></div>
          <h5 class="card-title">BULK MESSAGING BY VIRAT RAJPUT</h5>
          <p class="small-muted mb-3">Send messages to opted-in recipients with controlled scheduling.</p>
          <form id="bulk-form" enctype="multipart/form-data">
            <div class="mb-2">
              <label class="form-label" for="target_type">Target Type</label>
              <select class="form-select" name="target_type" id="target_type" onchange="toggleTargetInput()">
                <option value="phone">Phone Number</option>
                <option value="group">Group ID</option>
              </select>
            </div>
            <div id="phone-input-group" class="mb-2">
              <label class="form-label" for="target_phone">Target Number (E.164)</label>
              <input class="form-control" name="target_phone" id="target_phone" placeholder="919876543210">
            </div>
            <div id="group-input-group" class="mb-2 hidden">
              <label class="form-label" for="target_group">Select WhatsApp Group</label>
              <select class="form-select mb-2" id="group_list" onchange="document.getElementById('target_group_id').value = this.value">
                <option value="">-- Loading Groups... --</option>
              </select>
              <input class="form-control" name="target_group_id" id="target_group_id" placeholder="Or enter Group ID manually">
            </div>
            <div class="mb-2 mt-3">
              <label class="form-label" for="file">Message File (.txt)</label>
              <input class="form-control" type="file" name="file" id="file" accept=".txt" required>
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
  if(sel.options.length > 1) return;
  fetch('/api/whatsapp/groups').then(r=>r.json()).then(d=>{
    sel.innerHTML = '<option value="">-- Select a Group --</option>';
    if(d.groups && d.groups.length){
      d.groups.forEach(g=>{ sel.innerHTML += `<option value="${g.id}">${g.name}</option>`; });
    } else {
      sel.innerHTML += '<option value="" disabled>No groups available</option>';
    }
  }).catch(()=>{ sel.innerHTML = '<option value="">-- Error loading --</option>'; });
}
document.getElementById('btn-connect').addEventListener('click', async function(){
  const phone = document.getElementById('wa-phone').value.trim();
  const out = document.getElementById('conn-result');
  if(!/^\+?[1-9]\d{7,14}$/.test(phone)){ toast('Invalid phone format','error'); return; }
  const btn = this; btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Verifying...';
  try {
    const res = await fetch('/api/whatsapp/connect', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({phone}) });
    const data = await res.json();
    if(data.ok){
      toast('Connected','success');
      out.innerHTML = `Status: <b>Connected</b> — ${data.display_phone || data.phone_number_id}`;
      const b = document.getElementById('conn-badge'); b.textContent='Connected'; b.classList.add('connected');
    } else {
      toast(data.error||'Failed','error');
      out.innerHTML = `<span style="color:#fca5a5;">${data.error||'Failed'}</span>`;
    }
  } catch(e){ toast('Network error','error'); }
  finally { btn.disabled = false; btn.innerHTML = '<i class="bi bi-key-fill"></i> GENERATE / VERIFY CONNECTION'; }
});
document.getElementById('file').addEventListener('change', e=>{
  document.getElementById('file-name').textContent = e.target.files[0] ? 'Selected: '+e.target.files[0].name : '';
});
document.getElementById('bulk-form').addEventListener('submit', async function(e){
  e.preventDefault();
  const file = document.getElementById('file').files[0];
  if(!file){ toast('Select a .txt file','error'); return; }
  const form = e.target; const fd = new FormData(form);
  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
  try {
    const res = await fetch('/api/bulk/create', { method:'POST', body: fd });
    const data = await res.json();
    const out = document.getElementById('bulk-result');
    if(data.ok){
      out.innerHTML = `Task created: <code>${data.task_id}</code> — Recipients: ${data.total}`;
      toast('Task created','success');
      document.getElementById('session-lasttask').textContent = data.task_id;
    } else {
      out.innerHTML = `<span style="color:#fca5a5;">${data.error}</span>`;
      toast(data.error,'error');
    }
  } catch(err){ toast('Network error','error'); }
  finally { btn.disabled = false; btn.innerHTML = '<i class="bi bi-play-fill"></i> START SENDING'; }
});
document.getElementById('btn-last').addEventListener('click', async ()=>{
  const el = document.getElementById('last-task');
  try {
    const res = await fetch('/api/tasks/last'); const d = await res.json();
    if(d.ok){
      const t = d.task;
      el.innerHTML = `<b>${t.task_ref}</b><br>Status: ${t.status}<br>Progress: ${t.processed}/${t.total}<br>✓ ${t.succeeded} · ✗ ${t.failed}`;
    } else { el.innerHTML = `<span style="color:#fbbf24;">${d.message}</span>`; }
  } catch(e){ toast('Network error','error'); }
});
document.getElementById('btn-stop').addEventListener('click', async ()=>{
  const ref = document.getElementById('stop-task-id').value.trim();
  if(!ref){ toast('Enter task ID','error'); return; }
  if(!confirm('Stop task '+ref+'?')) return;
  try {
    const res = await fetch(`/api/tasks/${encodeURIComponent(ref)}/stop`, { method:'POST' });
    const d = await res.json();
    document.getElementById('stop-result').textContent = d.message || d.error;
    toast(d.message || d.error, d.ok ? 'success':'error');
  } catch(e){ toast('Network error','error'); }
});
</script>
</body>
</html>
"""

# ---------------- FLASK APP ----------------
app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_DATABASE_URI"] = Config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/api/whatsapp/connect", methods=["POST"])
def whatsapp_connect():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not re.match(r"^\+?[1-9]\d{7,14}$", phone):
        return jsonify({"ok": False, "error": "Invalid phone number. Use E.164 format (e.g. +919876543210)"}), 400
    if not is_configured():
        return jsonify({"ok": False, "error": "WhatsApp Cloud API not configured on server. Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in environment variables."}), 400
    h = health_check()
    if h.get("ok"):
        d = h["data"]
        return jsonify({"ok": True, "display_phone": d.get("display_phone_number"), "verified_name": d.get("verified_name"), "phone_number_id": d.get("id")})
    return jsonify({"ok": False, "error": h.get("reason", "Health check failed")}), 502

@app.route("/api/whatsapp/groups", methods=["GET"])
def whatsapp_groups():
    if not is_configured():
        return jsonify({"ok": False, "error": "API not configured", "groups": []}), 200
    return jsonify({"ok": True, "groups": [], "note": "Cloud API does not expose personal WhatsApp groups. Use Business Groups only."})

@app.route("/api/bulk/create", methods=["POST"])
def bulk_create():
    target_type = request.form.get("target_type", "phone")
    target_phone = (request.form.get("target_phone") or "").strip()
    target_group = (request.form.get("target_group_id") or "").strip()
    prefix = (request.form.get("prefix") or "").strip()
    try:
        delay = int(request.form.get("delay", Config.DEFAULT_DELAY))
    except ValueError:
        return jsonify({"ok": False, "error": "Delay must be a number"}), 400
    if delay < Config.MIN_DELAY or delay > Config.MAX_DELAY:
        return jsonify({"ok": False, "error": f"Delay must be between {Config.MIN_DELAY} and {Config.MAX_DELAY} seconds"}), 400
    if target_type not in ("phone", "group"):
        return jsonify({"ok": False, "error": "Invalid target type"}), 400
    final_target = target_phone if target_type == "phone" else target_group
    if not final_target:
        return jsonify({"ok": False, "error": "Target number/group required"}), 400
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Message file required"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".txt"):
        return jsonify({"ok": False, "error": "Only .txt files allowed"}), 400
    raw = file.read()
    if len(raw) == 0:
        return jsonify({"ok": False, "error": "File is empty"}), 400
    if len(raw) > Config.MAX_CONTENT_LENGTH:
        return jsonify({"ok": False, "error": "File exceeds size limit"}), 400
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"ok": False, "error": "File must be UTF-8"}), 400
    recipients = [line.strip() for line in text.splitlines() if line.strip()]
    if not recipients:
        return jsonify({"ok": False, "error": "No valid recipients in file"}), 400
    if len(recipients) > 5000:
        return jsonify({"ok": False, "error": "Max 5000 recipients per task"}), 400
    task_ref = "TASK-" + uuid.uuid4().hex[:10].upper()
    task = Task(task_ref=task_ref, target_type=target_type, target=final_target, status="queued", total=len(recipients), delay_seconds=delay, prefix=prefix)
    db.session.add(task)
    db.session.flush()
    for r in recipients:
        db.session.add(MessageLog(task_id=task.id, recipient=r, status="queued"))
    db.session.commit()
    app_ctx = app.app_context()
    threading.Thread(target=run_task, args=(app_ctx, task.id, recipients), daemon=True).start()
    return jsonify({"ok": True, "task_id": task_ref, "total": len(recipients), "target_type": target_type, "target": final_target})

@app.route("/api/tasks/last", methods=["GET"])
def tasks_last():
    t = Task.query.order_by(Task.id.desc()).first()
    if not t:
        return jsonify({"ok": False, "message": "NO ACTIVE TASK FOUND. START A MESSAGING TASK FIRST."})
    return jsonify({"ok": True, "task": serialize_task(t)})

@app.route("/api/tasks/<task_ref>", methods=["GET"])
def task_get(task_ref):
    t = Task.query.filter_by(task_ref=task_ref).first()
    if not t:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({"ok": True, "task": serialize_task(t)})

@app.route("/api/tasks/<task_ref>/stop", methods=["POST"])
def task_stop(task_ref):
    t = Task.query.filter_by(task_ref=task_ref).first()
    if not t:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    if t.status in ("completed", "cancelled", "failed"):
        return jsonify({"ok": False, "error": f"Task already {t.status}"}), 400
    t.status = "cancelled"
    db.session.commit()
    return jsonify({"ok": True, "message": f"Task {task_ref} marked cancelled"})

@app.route("/webhook/whatsapp", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        if mode == "subscribe" and token == Config.WHATSAPP_VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403
    data = request.get_json(silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for st in value.get("statuses", []):
                    mid = st.get("id")
                    status = st.get("status")
                    if mid and status:
                        ml = MessageLog.query.filter_by(wa_message_id=mid).first()
                        if ml:
                            ml.status = status
                            db.session.commit()
    except Exception as e:
        log.exception("Webhook error: %s", e)
    return jsonify({"ok": True}), 200

# ---------------- INIT DB ----------------
with app.app_context():
    db.create_all()
    log.info("Database initialized")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))