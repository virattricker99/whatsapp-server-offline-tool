from __future__ import annotations

"""Single-file WhatsApp Business Cloud API console and RQ worker.
Use only the official Meta Cloud API. This app does not pair personal WhatsApp accounts,
message groups, scrape contacts, or infer delivery from an API acceptance response.
"""
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from threading import Thread
from urllib.parse import quote

import phonenumbers
import requests
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from flask import Flask, abort, current_app, g, jsonify, make_response, redirect, request, send_file, session, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, generate_csrf
from redis import Redis
from rq import Queue, Worker
from rq.exceptions import DuplicateJobError
from rq.job import Job, NoSuchJobError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

# Local .env files are useful for development, but must never override the
# managed secret environment in a production service.
_requested_app_env = os.getenv("APP_ENV", "development").strip().lower()
if _requested_app_env not in {"production", "prod"}:
    load_dotenv()

# Ensure worker-mode configuration is applied before the Flask app is constructed.
if len(sys.argv) > 1 and sys.argv[1] == "worker":
    os.environ.setdefault("APP_ROLE", "worker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_environment_name = os.getenv("APP_ENV", "development").strip().lower()
APP_ENV = {"prod": "production", "dev": "development", "test": "testing"}.get(_environment_name, _environment_name)
APP_ROLE = os.getenv("APP_ROLE", "web").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
DEMO_USERNAME = "VIRATKING73"
DEMO_PASSWORD = "VIRATKING73"

def _database_url() -> str:
    raw = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'whatsapp.db')}")
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw[len("postgres://"):]
    elif raw.startswith("postgresql://") and "+psycopg" not in raw:
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

class Config:
    APP_ENV = APP_ENV
    APP_ROLE = APP_ROLE
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_urlsafe(48)
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 60 * 60
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI") or os.getenv("REDIS_URL") or "memory://"
    RATELIMIT_HEADERS_ENABLED = True
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", DEMO_USERNAME).strip()
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_TEMPLATE_NAME = os.getenv("WHATSAPP_TEMPLATE_NAME", "")
    WHATSAPP_TEMPLATE_LANGUAGE = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en_US")
    GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v26.0")
    GRAPH_API_TIMEOUT_SECONDS = int(os.getenv("GRAPH_API_TIMEOUT_SECONDS", "10"))
    MESSAGE_ENCRYPTION_KEY = os.getenv("MESSAGE_ENCRYPTION_KEY", "")
    REDIS_URL = os.getenv("REDIS_URL", "")
    MAX_CAMPAIGN_RECIPIENTS = int(os.getenv("MAX_CAMPAIGN_RECIPIENTS", "200"))
    MIN_MESSAGE_DELAY_SECONDS = int(os.getenv("MIN_MESSAGE_DELAY_SECONDS", "1"))
    MAX_MESSAGE_DELAY_SECONDS = int(os.getenv("MAX_MESSAGE_DELAY_SECONDS", "60"))
    MESSAGE_FILE_MAX_BYTES = int(os.getenv("MESSAGE_FILE_MAX_BYTES", "65536"))
    MESSAGE_MAX_CHARACTERS = int(os.getenv("MESSAGE_MAX_CHARACTERS", "4000"))

db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

class LoginSession(db.Model):
    __tablename__ = "login_sessions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_digest = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship("AdminUser")

class Recipient(db.Model):
    __tablename__ = "recipients"
    id = db.Column(db.Integer, primary_key=True)
    phone_e164 = db.Column(db.String(20), unique=True, nullable=False, index=True)
    consent_note = db.Column(db.String(160), nullable=False)
    opted_in_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_inbound_at = db.Column(db.DateTime(timezone=True), index=True)
    suppressed_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

class MessagingTask(db.Model):
    __tablename__ = "messaging_tasks"
    __table_args__ = (
        db.UniqueConstraint("user_id", "submission_key", name="uq_task_user_submission"),
        db.Index("ix_task_user_created", "user_id", "created_at"),
    )
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_key = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(24), nullable=False, default="queued", index=True)
    message_mode = db.Column(db.String(24), nullable=False)
    target_count = db.Column(db.Integer, nullable=False, default=0)
    processed_count = db.Column(db.Integer, nullable=False, default=0)
    submitted_count = db.Column(db.Integer, nullable=False, default=0)
    failure_count = db.Column(db.Integer, nullable=False, default=0)
    unknown_count = db.Column(db.Integer, nullable=False, default=0)
    delay_seconds = db.Column(db.Integer, nullable=False, default=5)
    message_ciphertext = db.Column(db.Text, nullable=False)
    body_sha256 = db.Column(db.String(64), nullable=False)
    rq_job_id = db.Column(db.String(80), unique=True)
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    recipients = db.relationship("TaskRecipient", back_populates="task", cascade="all, delete-orphan", lazy="selectin")
    user = db.relationship("AdminUser")

class TaskRecipient(db.Model):
    __tablename__ = "task_recipients"
    __table_args__ = (db.UniqueConstraint("task_id", "recipient_id", name="uq_task_recipient"),)
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(36), db.ForeignKey("messaging_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("recipients.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False, default="queued", index=True)
    provider_message_id = db.Column(db.String(180), index=True)
    error_code = db.Column(db.String(64))
    queued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    processed_at = db.Column(db.DateTime(timezone=True))
    task = db.relationship("MessagingTask", back_populates="recipients")
    recipient = db.relationship("Recipient")

class ConnectionState(db.Model):
    __tablename__ = "connection_state"
    id = db.Column(db.Integer, primary_key=True, default=1)
    status = db.Column(db.String(24), nullable=False, default="disconnected")
    phone_number_id = db.Column(db.String(64))
    display_phone_number = db.Column(db.String(40))
    verified_name = db.Column(db.String(120))
    last_checked_at = db.Column(db.DateTime(timezone=True))
    error_summary = db.Column(db.String(240))

class Activity(db.Model):
    __tablename__ = "activity"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    event = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.String(180), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

class WebhookEvent(db.Model):
    __tablename__ = "webhook_events"
    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(220), unique=True, nullable=False, index=True)
    event_type = db.Column(db.String(32), nullable=False)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

class PendingMessageStatus(db.Model):
    __tablename__ = "pending_message_statuses"
    event_key = db.Column(db.String(80), primary_key=True)
    provider_message_id = db.Column(db.String(180), nullable=False, index=True)
    status = db.Column(db.String(24), nullable=False)
    error_code = db.Column(db.String(64))
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)

class ValidationError(ValueError):
    pass

def normalize_phone(raw: str) -> str:
    value = (raw or "").strip()
    if not value or len(value) > 32:
        raise ValidationError("Enter a phone number with country code, such as +919876543210.")
    try:
        parsed = phonenumbers.parse(value, None)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("That phone number could not be parsed. Include the country code.") from exc
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        raise ValidationError("That phone number is invalid or unsupported. Check the country code and digits.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

def parse_target_list(raw: str, limit: int) -> list[str]:
    if not raw or not raw.strip():
        raise ValidationError("Add at least one opted-in recipient phone number.")
    values = [part.strip() for part in raw.replace("\r", "\n").replace(",", "\n").split("\n") if part.strip()]
    if len(values) > limit:
        raise ValidationError(f"A task can include at most {limit} recipients.")
    phones = [normalize_phone(value) for value in values]
    if len(set(phones)) != len(phones):
        raise ValidationError("Duplicate phone numbers were found. Remove duplicates before continuing.")
    return phones

def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("Message encryption is not configured. Set MESSAGE_ENCRYPTION_KEY before creating tasks.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("MESSAGE_ENCRYPTION_KEY is invalid. Generate a Fernet key and restart the app.") from exc

def encrypt_message(message: str, key: str) -> str:
    return _fernet(key).encrypt(message.encode("utf-8")).decode("ascii")

def decrypt_message(ciphertext: str, key: str) -> str:
    try:
        return _fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("The stored task message cannot be decrypted. Check MESSAGE_ENCRYPTION_KEY.") from exc

def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def verify_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256=") or not app_secret:
        return False
    supplied = signature_header.removeprefix("sha256=").strip()
    if len(supplied) != 64:
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)

def validate_production_config(app: Flask) -> None:
    if app.config.get("APP_ENV") != "production":
        return
    role = app.config.get("APP_ROLE", "web")
    required = ["DATABASE_URL", "REDIS_URL", "MESSAGE_ENCRYPTION_KEY"]
    if role != "worker":
        required += ["FLASK_SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError("Missing required production environment variables: " + ", ".join(missing))
    if role != "worker":
        if os.getenv("ADMIN_PASSWORD"):
            raise RuntimeError("ADMIN_PASSWORD is local-development only. Set ADMIN_PASSWORD_HASH in production.")
        if app.config["ADMIN_USERNAME"].strip().upper() == DEMO_USERNAME:
            raise RuntimeError("Choose a new production ADMIN_USERNAME; the local demo account is not allowed.")
        if len(os.getenv("FLASK_SECRET_KEY", "")) < 32:
            raise RuntimeError("FLASK_SECRET_KEY must be at least 32 characters.")
        try:
            if check_password_hash(app.config["ADMIN_PASSWORD_HASH"], DEMO_PASSWORD):
                raise RuntimeError("The local demo password is not allowed in production.")
        except ValueError as exc:
            raise RuntimeError("ADMIN_PASSWORD_HASH is invalid.") from exc
    try:
        _fernet(app.config.get("MESSAGE_ENCRYPTION_KEY", ""))
    except RuntimeError:
        raise
    whatsapp_core = ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_BUSINESS_ACCOUNT_ID")
    configured_core = [bool(app.config.get(key)) for key in whatsapp_core]
    if any(configured_core) and not all(configured_core):
        raise RuntimeError("Configure WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and WHATSAPP_BUSINESS_ACCOUNT_ID together, or leave all three empty until Meta setup is ready.")
    if role != "worker" and all(configured_core):
        webhook_missing = [key for key in ("WHATSAPP_VERIFY_TOKEN", "WHATSAPP_APP_SECRET") if not app.config.get(key)]
        if webhook_missing:
            raise RuntimeError("The web service needs WHATSAPP_VERIFY_TOKEN and WHATSAPP_APP_SECRET to accept verified Meta webhooks.")
    if not re.fullmatch(r"v\d+\.\d+", app.config.get("GRAPH_API_VERSION", "")):
        raise RuntimeError("GRAPH_API_VERSION must look like v26.0.")

def issue_session(user: AdminUser) -> str:
    raw_id = secrets.token_urlsafe(32)
    now = utcnow()
    row = LoginSession(user_id=user.id, session_digest=hashlib.sha256(raw_id.encode()).hexdigest(), created_at=now,
                       last_seen_at=now, expires_at=now + current_app.permanent_session_lifetime)
    db.session.add(row)
    db.session.commit()
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["sid"] = raw_id
    generate_csrf()
    return raw_id

def revoke_current_session() -> None:
    sid = session.get("sid")
    if sid:
        digest = hashlib.sha256(sid.encode()).hexdigest()
        row = LoginSession.query.filter_by(session_digest=digest, revoked_at=None).first()
        if row:
            row.revoked_at = utcnow()
            db.session.commit()
    session.clear()
    g.user = None
    g.login_session = None

def load_identity() -> None:
    g.user = None
    g.login_session = None
    sid, user_id = session.get("sid"), session.get("user_id")
    if not sid or not user_id:
        return
    digest = hashlib.sha256(sid.encode()).hexdigest()
    row = LoginSession.query.filter_by(session_digest=digest, user_id=user_id, revoked_at=None).first()
    if not row or not row.expires_at or as_utc(row.expires_at) <= utcnow() or not row.user or not row.user.active:
        session.clear()
        return
    g.user, g.login_session = row.user, row
    if (utcnow() - as_utc(row.last_seen_at)).total_seconds() > 300:
        row.last_seen_at = utcnow()
        db.session.commit()

def login_required(allow_password_change: bool = False):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = getattr(g, "user", None)
            if user is None:
                return jsonify(error="Authentication required."), 401
            if user.must_change_password and not allow_password_change:
                return jsonify(error="Change the initial password before using this feature."), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator

def safe_meta_error(response: requests.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        text_value = str(error.get("message", "")) if isinstance(error, dict) else ""
        code = error.get("code") if isinstance(error, dict) else None
        if text_value:
            text_value = re.sub(r"(?:EA[A-Za-z0-9]{20,}|[A-Za-z0-9_-]{40,})", "[redacted]", text_value)
            return (f"Meta API error ({code}): " if code else "Meta API error: ") + text_value[:240]
    except (ValueError, requests.RequestException):
        pass
    return f"Meta API returned HTTP {response.status_code}. Check server-side credentials and Meta setup."

class WhatsAppAPIError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, code: str | None = None, outcome_unknown: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown
        self.code = code or "api_error"

class WhatsAppClient:
    def __init__(self, config=None):
        self.config = config or current_app.config
        self.token = self.config.get("WHATSAPP_ACCESS_TOKEN", "")
        self.phone_id = self.config.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.business_id = self.config.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
        self.version = self.config.get("GRAPH_API_VERSION", "v26.0")
        self.timeout = int(self.config.get("GRAPH_API_TIMEOUT_SECONDS", 10))
        self.base_url = f"https://graph.facebook.com/{self.version}"
        self.session = requests.Session()

    def configured(self) -> bool:
        return bool(self.token and self.phone_id and self.business_id)

    def _require_config(self):
        if not self.configured():
            raise WhatsAppAPIError("WhatsApp Cloud API credentials are incomplete. Add the access token, phone-number ID, and business account ID.", code="configuration_missing")

    def _request(self, method: str, path: str, *, params=None, payload=None):
        self._require_config()
        try:
            response = self.session.request(method, f"{self.base_url}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                params=params, json=payload, timeout=self.timeout)
        except requests.Timeout as exc:
            raise WhatsAppAPIError("The request timed out; Meta may have received it, so the outcome is unknown and it will not be retried automatically.", code="outcome_unknown", outcome_unknown=True) from exc
        except requests.RequestException as exc:
            raise WhatsAppAPIError("The network outcome is uncertain; this message will not be resent automatically to avoid a duplicate.", code="outcome_unknown", outcome_unknown=True) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if not response.ok:
            meta_error = data.get("error", {}) if isinstance(data, dict) else {}
            code = str(meta_error.get("code", response.status_code))
            retryable = response.status_code == 429
            unknown = response.status_code >= 500 or response.status_code in {408, 425}
            if response.status_code in {401, 403}:
                message = "WhatsApp rejected the configured credentials or permissions. Review the permanent token and app permissions."
            elif response.status_code == 429:
                message = "WhatsApp rate-limited this request. It may be retried with backoff."
            else:
                message = "WhatsApp rejected the request. Check the account, recipient, template, and API setup."
            raise WhatsAppAPIError(message, retryable=retryable, code="outcome_unknown" if unknown else code, outcome_unknown=unknown)
        return data

    def check_connection(self) -> dict:
        self._require_config()
        data = self._request("GET", f"{quote(self.business_id, safe='')}/phone_numbers",
            params={"fields": "id,display_phone_number,verified_name", "limit": 100})
        phones = data.get("data", []) if isinstance(data, dict) else []
        found = next((item for item in phones if str(item.get("id")) == str(self.phone_id)), None)
        if not found:
            raise WhatsAppAPIError("The configured phone-number ID was not found under the configured WhatsApp Business Account.", code="phone_account_mismatch")
        return {"phone_number_id": str(found["id"]), "display_phone_number": found.get("display_phone_number", ""), "verified_name": found.get("verified_name", "")}

    def approved_template(self) -> dict:
        self._require_config()
        name = (self.config.get("WHATSAPP_TEMPLATE_NAME", "") or "").strip()
        language = (self.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en_US") or "en_US").strip()
        if not name:
            raise WhatsAppAPIError("Template mode is unavailable until WHATSAPP_TEMPLATE_NAME is configured.", code="template_not_configured")
        data = self._request("GET", f"{quote(self.business_id, safe='')}/message_templates",
            params={"name": name, "fields": "name,status,language,components", "limit": 100})
        templates = data.get("data", []) if isinstance(data, dict) else []
        item = next((row for row in templates if row.get("name") == name and row.get("language") == language), None)
        if not item or item.get("status") != "APPROVED":
            raise WhatsAppAPIError("The configured template was not found in APPROVED status for that language.", code="template_not_approved")
        components = item.get("components", [])
        bodies = [part for part in components if str(part.get("type", "")).lower() == "body"]
        if len(bodies) != 1 or not isinstance(bodies[0].get("text"), str):
            raise WhatsAppAPIError("Template mode supports one text body with exactly one placeholder.", code="template_shape_unsupported")
        placeholders = re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", bodies[0]["text"])
        if len(placeholders) != 1:
            raise WhatsAppAPIError("Use an approved template with exactly one body placeholder.", code="template_shape_unsupported")
        for component in components:
            kind = str(component.get("type", "")).lower()
            if kind == "header" and str(component.get("format", "")).upper() != "TEXT":
                raise WhatsAppAPIError("Template mode supports only static text headers; media headers need a different payload.", code="template_shape_unsupported")
            if kind != "body" and re.search(r"\{\{\s*[a-zA-Z0-9_]+\s*\}\}", json.dumps(component)):
                raise WhatsAppAPIError("Template mode cannot fill placeholders outside the body.", code="template_shape_unsupported")
        return {"name": name, "language": language, "placeholder": placeholders[0]}

    def send_text(self, to: str, body: str) -> str:
        data = self._request("POST", f"{quote(self.phone_id, safe='')}/messages", payload={
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
            "type": "text", "text": {"preview_url": False, "body": body}})
        return self._message_id(data)

    def send_template(self, to: str, parameter: str, template: dict) -> str:
        variable = template["placeholder"]
        param = {"type": "text", "text": parameter}
        if not variable.isdigit():
            param["parameter_name"] = variable
        data = self._request("POST", f"{quote(self.phone_id, safe='')}/messages", payload={
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
            "type": "template", "template": {"name": template["name"],
                "language": {"code": template["language"]}, "components": [{"type": "body", "parameters": [param]}]}})
        return self._message_id(data)

    @staticmethod
    def _message_id(data: dict) -> str:
        try:
            return str(data["messages"][0]["id"])
        except (KeyError, IndexError, TypeError) as exc:
            raise WhatsAppAPIError("Meta returned no recognizable message ID; the outcome is unknown and will not be retried.", code="outcome_unknown", outcome_unknown=True) from exc

def get_queue(config=None) -> Queue:
    config = config or current_app.config
    redis_url = config.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("Durable queue is not configured. Set REDIS_URL and run the separate worker service.")
    connection = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    connection.ping()
    return Queue("whatsapp", connection=connection, default_timeout=4 * 60 * 60)

def check_recipients(phones: list[str], mode: str) -> tuple[list[Recipient], list[dict]]:
    rows = Recipient.query.filter(Recipient.phone_e164.in_(phones)).all()
    by_phone = {row.phone_e164: row for row in rows}
    approved, blocked = [], []
    now = utcnow()
    for phone in phones:
        contact = by_phone.get(phone)
        if not contact:
            blocked.append({"phone": phone, "reason": "No documented opt-in record."})
        elif contact.suppressed_at:
            blocked.append({"phone": phone, "reason": "This recipient is on the suppression list."})
        elif mode == "session_text" and (not contact.last_inbound_at or now - as_utc(contact.last_inbound_at) >= timedelta(hours=24)):
            blocked.append({"phone": phone, "reason": "No inbound WhatsApp message within the last 24 hours; use an approved template."})
        else:
            approved.append(contact)
    return approved, blocked

def task_payload(task: MessagingTask) -> dict:
    counts = {name: 0 for name in ("queued", "submitting", "submitted", "sent", "delivered", "read", "failed", "unknown", "cancelled")}
    for row in task.recipients:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {"id": task.id, "state": task.state, "mode": task.message_mode,
        "created_at": as_utc(task.created_at).isoformat() if task.created_at else None,
        "updated_at": as_utc(task.updated_at).isoformat() if task.updated_at else None,
        "started_at": as_utc(task.started_at).isoformat() if task.started_at else None,
        "completed_at": as_utc(task.completed_at).isoformat() if task.completed_at else None,
        "total": task.target_count, "processed": task.processed_count, "submitted": task.submitted_count,
        "failures": task.failure_count, "unknown": task.unknown_count, "cancel_requested": task.cancel_requested,
        "delay_seconds": task.delay_seconds, "statuses": counts,
        "recipients": [{"phone": row.recipient.phone_e164, "status": row.status, "error_code": row.error_code} for row in task.recipients]}

def check_connection_fresh() -> bool:
    state = db.session.get(ConnectionState, 1)
    return bool(state and state.status == "connected" and state.last_checked_at and utcnow() - as_utc(state.last_checked_at) <= timedelta(minutes=5))

def validate_campaign(targets_raw, mode, body, prefix):
    if mode not in {"session_text", "template"}:
        raise ValidationError("Choose either service-window text or an approved template.")
    phones = parse_target_list(targets_raw, current_app.config["MAX_CAMPAIGN_RECIPIENTS"])
    body = (body or "").strip()
    prefix = prefix or ""
    if not body:
        raise ValidationError("The .txt message file must contain non-empty UTF-8 text.")
    if "\x00" in body:
        raise ValidationError("The message text contains invalid binary characters.")
    if len(prefix) > 120:
        raise ValidationError("The optional prefix must be 120 characters or fewer.")
    final_text = f"{prefix}{body}" if prefix else body
    max_chars = current_app.config["MESSAGE_MAX_CHARACTERS"] if mode == "session_text" else min(current_app.config["MESSAGE_MAX_CHARACTERS"], 1024)
    if len(final_text) > max_chars:
        raise ValidationError(f"Message text must be {max_chars} characters or fewer for the selected mode.")
    if not check_connection_fresh():
        raise ValidationError("Run a successful connection health check first. The app will not schedule messages on an unverified connection.")
    if not current_app.config.get("MESSAGE_ENCRYPTION_KEY"):
        raise ValidationError("Message encryption is not configured. Set MESSAGE_ENCRYPTION_KEY before creating tasks.")
    client = WhatsAppClient()
    template = client.approved_template() if mode == "template" else None
    if mode == "session_text" and not client.configured():
        raise ValidationError("WhatsApp Cloud API credentials are incomplete. Configure them before sending.")
    contacts, blocked = check_recipients(phones, mode)
    if blocked:
        return {"valid": False, "recipient_count": len(phones), "eligible_count": len(contacts), "blocked": blocked, "mode": mode}, None
    queue = get_queue()
    return {"valid": True, "recipient_count": len(contacts), "mode": mode, "template": template, "queue_ready": bool(queue)}, (phones, contacts, final_text)

def mark_cancelled(task: MessagingTask) -> None:
    now = utcnow()
    for row in task.recipients:
        if row.status == "queued":
            row.status = "cancelled"
            row.processed_at = now
            row.updated_at = now
    task.cancel_requested = True
    task.state = "cancelled"
    task.completed_at = now
    task.updated_at = now
    db.session.commit()

def reconcile_queued_dispatches(queue: Queue) -> int:
    dispatched = 0
    for task in MessagingTask.query.filter_by(state="queued").order_by(MessagingTask.created_at.asc()).all():
        if task.cancel_requested:
            mark_cancelled(task)
            continue
        job_id = task.rq_job_id or f"campaign-{task.id}"
        try:
            job = Job.fetch(job_id, connection=queue.connection)
            status = getattr(job.get_status(refresh=True), "value", str(job.get_status(refresh=True))).lower()
            if status == "failed" and all(item.status == "queued" for item in task.recipients):
                job.delete(remove_from_queue=True)
            else:
                if task.rq_job_id != job_id:
                    task.rq_job_id = job_id
                    db.session.commit()
                continue
        except NoSuchJobError:
            pass
        except Exception:
            continue
        try:
            queue.enqueue("app.process_campaign", task.id, job_id=job_id, job_timeout=4 * 60 * 60, result_ttl=0, failure_ttl=86400)
            dispatched += 1
        except DuplicateJobError:
            pass
        except Exception:
            continue
        task.rq_job_id = job_id
        db.session.commit()
    return dispatched

def _process_campaign(task_id: str):
    task = db.session.get(MessagingTask, task_id)
    if not task:
        return
    claimed = MessagingTask.query.filter_by(id=task_id, state="queued").update(
        {"state": "sending", "started_at": utcnow(), "updated_at": utcnow()}, synchronize_session="fetch")
    db.session.commit()
    if claimed != 1:
        return
    task = db.session.get(MessagingTask, task_id)
    if task.cancel_requested:
        mark_cancelled(task)
        return
    client = WhatsAppClient()
    try:
        message = decrypt_message(task.message_ciphertext, current_app.config.get("MESSAGE_ENCRYPTION_KEY", ""))
        connection_info = client.check_connection()
        state = db.session.get(ConnectionState, 1) or ConnectionState(id=1)
        state.status = "connected"
        state.phone_number_id = connection_info["phone_number_id"]
        state.display_phone_number = connection_info["display_phone_number"][:40]
        state.verified_name = connection_info["verified_name"][:120]
        state.last_checked_at = utcnow()
        state.error_summary = None
        db.session.add(state)
        db.session.commit()
        template = client.approved_template() if task.message_mode == "template" else None
    except WhatsAppAPIError as exc:
        state = db.session.get(ConnectionState, 1) or ConnectionState(id=1)
        state.status = "error"
        state.last_checked_at = utcnow()
        state.error_summary = str(exc)[:240]
        task.state = "failed"
        task.failure_count = task.target_count
        task.processed_count = task.target_count
        task.completed_at = utcnow()
        for item in task.recipients:
            if item.status == "queued":
                item.status = "failed"
                item.error_code = exc.code
                item.processed_at = utcnow()
        db.session.add(state)
        db.session.commit()
        return
    links = TaskRecipient.query.filter_by(task_id=task.id).order_by(TaskRecipient.id.asc()).all()
    for index, item in enumerate(links):
        db.session.refresh(task)
        if task.cancel_requested:
            mark_cancelled(task)
            return
        if item.status != "queued":
            continue
        db.session.refresh(item.recipient)
        if item.recipient.suppressed_at:
            item.status, item.error_code, item.processed_at = "failed", "suppressed", utcnow()
            task.failure_count += 1
            task.processed_count += 1
            db.session.commit()
            continue
        if task.message_mode == "session_text":
            inbound = as_utc(item.recipient.last_inbound_at)
            if not inbound or utcnow() - inbound >= timedelta(hours=24):
                item.status, item.error_code, item.processed_at = "failed", "service_window_closed", utcnow()
                task.failure_count += 1
                task.processed_count += 1
                db.session.commit()
                continue
        item.status = "submitting"
        item.updated_at = utcnow()
        db.session.commit()
        accepted, uncertain, last_error = False, False, None
        for attempt in range(3):
            try:
                provider_id = client.send_template(item.recipient.phone_e164, message, template) if task.message_mode == "template" else client.send_text(item.recipient.phone_e164, message)
                item.status = "submitted"
                item.provider_message_id = provider_id
                item.error_code = None
                task.submitted_count += 1
                accepted = True
                break
            except WhatsAppAPIError as exc:
                last_error = exc
                if exc.outcome_unknown:
                    uncertain = True
                    break
                if not exc.retryable or attempt == 2:
                    break
                time.sleep(min(2 ** attempt, 8))
        if not accepted and uncertain:
            item.status, item.error_code = "unknown", "outcome_unknown"
            task.unknown_count += 1
        elif not accepted:
            item.status = "failed"
            item.error_code = (last_error.code if last_error else "send_failed")[:64]
            task.failure_count += 1
        item.processed_at = utcnow()
        item.updated_at = utcnow()
        task.processed_count += 1
        task.updated_at = utcnow()
        db.session.commit()
        if item.provider_message_id:
            apply_pending_message_statuses(item)
            db.session.commit()
        if index < len(links) - 1:
            for second in range(task.delay_seconds):
                time.sleep(1)
                db.session.refresh(task)
                if task.cancel_requested:
                    mark_cancelled(task)
                    return
                if (second + 1) % 10 == 0:
                    task.updated_at = utcnow()
                    db.session.commit()
    task.failure_count = TaskRecipient.query.filter_by(task_id=task.id, status="failed").count()
    task.unknown_count = TaskRecipient.query.filter_by(task_id=task.id, status="unknown").count()
    task.state = "completed_with_errors" if task.failure_count or task.unknown_count else "completed"
    task.completed_at = utcnow()
    task.updated_at = utcnow()
    db.session.commit()

def process_campaign(task_id: str):
    try:
        with app.app_context():
            return _process_campaign(task_id)
    except Exception as exc:
        with app.app_context():
            db.session.rollback()
            task = db.session.get(MessagingTask, task_id)
            if task and task.state == "sending":
                now = utcnow()
                for item in task.recipients:
                    if item.status == "submitting":
                        item.status, item.error_code = "unknown", "worker_interrupted"
                        item.processed_at = item.updated_at = now
                        task.unknown_count += 1
                        task.processed_count += 1
                task.state = "interrupted"
                task.completed_at = task.updated_at = now
                db.session.commit()
            current_app.logger.error("Campaign %s interrupted by %s", task_id, type(exc).__name__)
        raise

def recover_stale_sends() -> None:
    with app.app_context():
        cutoff = utcnow() - timedelta(minutes=5)
        pending_cutoff = utcnow() - timedelta(days=7)
        PendingMessageStatus.query.filter(PendingMessageStatus.received_at < pending_cutoff).delete(synchronize_session=False)
        db.session.commit()
        for task in MessagingTask.query.filter_by(state="sending").all():
            if not task.updated_at or as_utc(task.updated_at) >= cutoff:
                continue
            now = utcnow()
            for item in task.recipients:
                if item.status == "submitting":
                    item.status, item.error_code = "unknown", "worker_interrupted"
                    item.processed_at = item.updated_at = now
                    task.unknown_count += 1
                    task.processed_count += 1
            task.state = "interrupted"
            task.completed_at = task.updated_at = now
            db.session.commit()

def worker_main() -> None:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise SystemExit("REDIS_URL is required for the campaign worker.")
    connection = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    queue = Queue("whatsapp", connection=connection, default_timeout=4 * 60 * 60)
    with app.app_context():
        reconcile_queued_dispatches(queue)
    def dispatcher_loop():
        while True:
            try:
                recover_stale_sends()
                with app.app_context():
                    reconcile_queued_dispatches(queue)
            except Exception as exc:
                print(f"Queue reconciliation deferred ({type(exc).__name__}).", file=sys.stderr)
            time.sleep(15)
    Thread(target=dispatcher_loop, name="whatsapp-outbox-dispatcher", daemon=True).start()
    Worker([queue], connection=connection, name=f"whatsapp-worker-{os.getpid()}").work(with_scheduler=False)

# ---------------- HTML TEMPLATE (EMBEDDED) ----------------
HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WHAT'S APP NON STOP SERVER BY VIRAT RAJPUT</title>
<meta name="csrf-token" content="__CSRF_TOKEN__">
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
<script nonce="__CSP_NONCE__">
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

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
    const res = await fetch('/api/connection/check', { method:'POST', headers:{'Content-Type':'application/json', 'X-CSRFToken': csrfToken}, body: JSON.stringify({phone}) });
    const data = await res.json();
    if(data.connection && data.connection.status === 'connected'){
      toast('Connected','success');
      out.innerHTML = `Status: <b>Connected</b> — ${data.connection.display_phone_number || data.connection.phone_number_id}`;
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
  
  // Add target logic
  const targetType = document.getElementById('target_type').value;
  if(targetType === 'phone'){
    fd.append('targets', document.getElementById('target_phone').value.trim());
  } else {
    fd.append('targets', document.getElementById('target_group_id').value.trim());
  }
  fd.append('submission_key', Math.random().toString(36).substring(2) + Date.now().toString(36));
  fd.append('mode', 'session_text');

  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Submitting...';
  try {
    const res = await fetch('/api/tasks', { method:'POST', headers: {'X-CSRFToken': csrfToken}, body: fd });
    const data = await res.json();
    const out = document.getElementById('bulk-result');
    if(data.task){
      out.innerHTML = `Task created: <code>${data.task.id}</code> — Recipients: ${data.task.total}`;
      toast('Task created','success');
      document.getElementById('session-lasttask').textContent = data.task.id;
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
    if(d.task){
      const t = d.task;
      el.innerHTML = `<b>${t.id}</b><br>Status: ${t.state}<br>Progress: ${t.processed}/${t.total}<br>✓ ${t.submitted} · ✗ ${t.failures}`;
    } else { el.innerHTML = `<span style="color:#fbbf24;">${d.message}</span>`; }
  } catch(e){ toast('Network error','error'); }
});
document.getElementById('btn-stop').addEventListener('click', async ()=>{
  const ref = document.getElementById('stop-task-id').value.trim();
  if(!ref){ toast('Enter task ID','error'); return; }
  if(!confirm('Stop task '+ref+'?')) return;
  try {
    const res = await fetch(`/api/tasks/stop`, { method:'POST', headers:{'Content-Type':'application/json', 'X-CSRFToken': csrfToken}, body: JSON.stringify({task_id: ref}) });
    const d = await res.json();
    document.getElementById('stop-result').textContent = d.message || d.error;
    toast(d.message || d.error, d.task ? 'success':'error');
  } catch(e){ toast('Network error','error'); }
});
</script>
</body>
</html>
"""

def create_app(test_config=None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config.get("APP_ENV") not in {"development", "testing", "production"}:
        raise RuntimeError("APP_ENV must be development, testing, or production.")
    if app.config.get("APP_ENV") != "testing":
        validate_production_config(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    app.before_request(load_identity)

    @app.after_request
    def security_headers(response):
        nonce = getattr(g, "csp_nonce", "")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "img-src 'self' data:; connect-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}'")
        if app.config.get("APP_ENV") == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.before_request
    def set_nonce():
        g.csp_nonce = secrets.token_urlsafe(18)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify(error="The request is too large. Text uploads must be 64 KB or less."), 413

    @app.errorhandler(429)
    def rate_limited(_error):
        return jsonify(error="Too many requests. Wait a moment and try again."), 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error("Unhandled request error: %s", type(error).__name__)
        if request.path.startswith("/api/"):
            return jsonify(error="The request could not be completed. Check the app logs for a safe diagnostic."), 500
        return "Internal server error", 500

    @app.get("/")
    def index():
        token = generate_csrf()
        html = HTML_PAGE.replace("__CSRF_TOKEN__", token).replace("__CSP_NONCE__", g.csp_nonce)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/healthz")
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
            if app.config.get("REDIS_URL"):
                Redis.from_url(app.config["REDIS_URL"], socket_connect_timeout=3, socket_timeout=3).ping()
            return jsonify(status="ok"), 200
        except Exception:
            app.logger.exception("Health check dependency query failed")
            return jsonify(status="unavailable"), 503

    @app.get("/api/session")
    def session_info():
        user = getattr(g, "user", None)
        return jsonify(csrf=generate_csrf(), authenticated=bool(user), username=user.username if user else None,
                       must_change_password=bool(user and user.must_change_password))

    @app.post("/api/login")
    @limiter.limit("5 per minute")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        user = AdminUser.query.filter_by(username=username, active=True).first()
        if not (user and check_password_hash(user.password_hash, password)):
            return jsonify(error="Username or password is incorrect."), 401
        issue_session(user)
        db.session.add(Activity(user_id=user.id, event="login", detail="Successful sign-in"))
        db.session.commit()
        return jsonify(ok=True, username=user.username, must_change_password=user.must_change_password, csrf=generate_csrf())

    @app.get("/api/dashboard")
    @login_required()
    def dashboard_data():
        tasks = MessagingTask.query.filter_by(user_id=g.user.id).order_by(MessagingTask.created_at.desc()).limit(10).all()
        state = db.session.get(ConnectionState, 1)
        status = state.status if state else "disconnected"
        message = state.error_summary or "" if state else "Connection has not been verified."
        checked = as_utc(state.last_checked_at) if state else None
        if status == "connected" and (not checked or utcnow() - checked > timedelta(minutes=5)):
            status, message = "stale", "Last health check is older than five minutes. Check connection before scheduling a task."
        iso = lambda value: as_utc(value).isoformat() if value else None
        return jsonify(connection={"status": status, "phone_number_id": state.phone_number_id if state else None,
                "display_phone_number": state.display_phone_number if state else None,
                "verified_name": state.verified_name if state else None, "last_checked_at": iso(state.last_checked_at) if state else None,
                "message": message}, tasks=[task_payload(t) for t in tasks],
            session_ref=session.get("sid", "")[:8] or "—", server_time=iso(utcnow()),
            task_count=MessagingTask.query.filter_by(user_id=g.user.id).count(),
            active_count=MessagingTask.query.filter(MessagingTask.user_id == g.user.id, MessagingTask.state.in_(["queued", "sending", "cancel_requested"])).count())

    @app.post("/api/connection/check")
    @login_required()
    @limiter.limit("20 per hour")
    def connection_check():
        state = db.session.get(ConnectionState, 1) or ConnectionState(id=1, status="disconnected")
        try:
            info = WhatsAppClient().check_connection()
            state.status = "connected"
            state.phone_number_id = info["phone_number_id"]
            state.display_phone_number = info["display_phone_number"][:40]
            state.verified_name = info["verified_name"][:120]
            state.last_checked_at = utcnow()
            state.error_summary = None
            db.session.add(state)
            db.session.add(Activity(user_id=g.user.id, event="connection_verified", detail="Cloud API health check passed"))
            db.session.commit()
            return jsonify(connection={"status": "connected", "phone_number_id": state.phone_number_id, "display_phone_number": state.display_phone_number,
                "verified_name": state.verified_name, "last_checked_at": as_utc(state.last_checked_at).isoformat(), "message": "Meta verified the configured business account and phone number."},
                message="Cloud API credentials and phone-number assignment were verified by Meta.")
        except WhatsAppAPIError as exc:
            state.status, state.last_checked_at, state.error_summary = "error", utcnow(), str(exc)[:240]
            state.phone_number_id = current_app.config.get("WHATSAPP_PHONE_NUMBER_ID", "")[:64] or None
            state.display_phone_number = state.verified_name = None
            db.session.add(state)
            db.session.add(Activity(user_id=g.user.id, event="connection_check_failed", detail="Cloud API health check failed"))
            db.session.commit()
            return jsonify(connection={"status": "error", "message": str(exc), "phone_number_id": state.phone_number_id,
                "display_phone_number": None, "verified_name": None, "last_checked_at": as_utc(state.last_checked_at).isoformat()}, error=str(exc)), 400
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Connection check failed unexpectedly")
            return jsonify(error="Connection check failed. Verify the required API settings and try again."), 503

    @app.post("/api/tasks")
    @login_required()
    @limiter.limit("20 per hour")
    def create_task():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify(error="Choose a .txt message file."), 422
        if not uploaded.filename.lower().endswith(".txt"):
            return jsonify(error="Only .txt files are accepted."), 422
        raw = uploaded.stream.read(current_app.config["MESSAGE_FILE_MAX_BYTES"] + 1)
        if len(raw) > current_app.config["MESSAGE_FILE_MAX_BYTES"]:
            return jsonify(error=f"Message file must be {current_app.config['MESSAGE_FILE_MAX_BYTES'] // 1024} KB or smaller."), 413
        try:
            body = raw.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            return jsonify(error="The .txt message file must be valid UTF-8 text."), 422
        if not body or "\x00" in body:
            return jsonify(error="The .txt file must contain non-empty UTF-8 text."), 422
        mode = request.form.get("mode", "session_text")
        if request.form.get("target_type", "phone") == "group":
            return jsonify(error="Group messaging is not enabled; this integration will not send to a group ID."), 422
        targets_raw = request.form.get("targets", "")
        prefix = request.form.get("prefix", "")
        submission_key = (request.form.get("submission_key") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", submission_key):
            return jsonify(error="Invalid task submission key. Refresh the page and try again."), 422
        try:
            delay = int(request.form.get("delay", "5"))
        except (TypeError, ValueError):
            return jsonify(error="Delay must be a whole number of seconds."), 422
        if not current_app.config["MIN_MESSAGE_DELAY_SECONDS"] <= delay <= current_app.config["MAX_MESSAGE_DELAY_SECONDS"]:
            return jsonify(error=f"Delay must be between {current_app.config['MIN_MESSAGE_DELAY_SECONDS']} and {current_app.config['MAX_MESSAGE_DELAY_SECONDS']} seconds."), 422
        existing = MessagingTask.query.filter_by(user_id=g.user.id, submission_key=submission_key).first()
        if existing:
            return jsonify(message="This task submission was already received.", task=task_payload(existing), duplicate=True), 200
        try:
            result, internal = validate_campaign(targets_raw, mode, body, prefix)
            if not result["valid"]:
                return jsonify(result), 422
            phones, contacts, final_text = internal
            ciphertext = encrypt_message(final_text, current_app.config["MESSAGE_ENCRYPTION_KEY"])
        except ValidationError as exc:
            return jsonify(error=str(exc)), 422
        except WhatsAppAPIError as exc:
            return jsonify(error=str(exc)), 422
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 503
        task = MessagingTask(user_id=g.user.id, submission_key=submission_key, state="queued", message_mode=mode,
            target_count=len(contacts), delay_seconds=delay, message_ciphertext=ciphertext, body_sha256=sha256_text(final_text))
        task.recipients.extend(TaskRecipient(recipient=contact, status="queued") for contact in contacts)
        db.session.add(task)
        db.session.add(Activity(user_id=g.user.id, event="task_created", detail=f"Messaging task queued for {len(contacts)} opted-in recipient(s)"))
        try:
            db.session.flush()
            task.rq_job_id = f"campaign-{task.id}"
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = MessagingTask.query.filter_by(user_id=g.user.id, submission_key=submission_key).first()
            if existing:
                return jsonify(message="This task submission was already received.", task=task_payload(existing), duplicate=True), 200
            return jsonify(error="The task could not be saved. Please try again with a new submission."), 409
        try:
            get_queue().enqueue("app.process_campaign", task.id, job_id=task.rq_job_id,
                job_timeout=4 * 60 * 60, result_ttl=0, failure_ttl=86400)
        except Exception as exc:
            db.session.rollback()
            task = db.session.get(MessagingTask, task.id)
            current_app.logger.warning("Campaign dispatch acknowledgement pending (%s)", type(exc).__name__)
            return jsonify(message="Task saved. Queue confirmation is pending; worker reconciliation will resolve dispatch. Check this task before retrying.", task=task_payload(task), dispatch_pending=True), 202
        return jsonify(message="Task queued. Delivery is not confirmed until Meta sends a webhook.", task=task_payload(task)), 202

    @app.get("/api/tasks/last")
    @login_required()
    def last_task():
        task = MessagingTask.query.filter_by(user_id=g.user.id).order_by(MessagingTask.created_at.desc()).first()
        if not task:
            return jsonify(message="No task has been created yet.", task=None)
        return jsonify(message="Most recent task loaded.", task=task_payload(task))

    @app.post("/api/tasks/stop")
    @login_required()
    @limiter.limit("60 per hour")
    def stop_task():
        task_id = str((request.get_json(silent=True) or {}).get("task_id", "")).strip()
        task = db.session.get(MessagingTask, task_id)
        if not task or task.user_id != g.user.id:
            return jsonify(error="Task not found."), 404
        if task.state in {"completed", "completed_with_errors", "cancelled", "failed", "interrupted"}:
            return jsonify(message=f"Task is already {task.state.replace('_', ' ')}.", task=task_payload(task)), 409
        task.cancel_requested = True
        task.updated_at = utcnow()
        db.session.commit()
        immediate = False
        if task.rq_job_id and task.state == "queued":
            try:
                queue = get_queue()
                job = Job.fetch(task.rq_job_id, connection=queue.connection)
                status = getattr(job.get_status(refresh=True), "value", str(job.get_status(refresh=True))).lower()
                if status in {"queued", "deferred", "scheduled"}:
                    job.cancel()
                    for row in task.recipients:
                        if row.status == "queued":
                            row.status = "cancelled"
                            row.processed_at = utcnow()
                    task.state, task.completed_at, task.updated_at = "cancelled", utcnow(), utcnow()
                    immediate = True
                    db.session.commit()
            except Exception:
                current_app.logger.warning("Queued task cancellation will be handled by the worker")
        db.session.add(Activity(user_id=g.user.id, event="task_stop_requested", detail="Task cancellation requested"))
        db.session.commit()
        task = db.session.get(MessagingTask, task_id)
        message = "Task cancelled before processing; no messages were sent." if immediate else "Stop requested. The worker will stop before the next eligible send; submitted messages cannot be recalled."
        return jsonify(message=message, task=task_payload(task))

    @app.route("/webhooks/whatsapp", methods=["GET", "POST"])
    @csrf.exempt
    def whatsapp_webhook():
        if request.method == "GET":
            verify_token = current_app.config.get("WHATSAPP_VERIFY_TOKEN", "")
            mode = request.args.get("hub.mode", "")
            supplied = request.args.get("hub.verify_token", "")
            challenge = request.args.get("hub.challenge", "")
            if not verify_token or mode != "subscribe" or not supplied or not hmac.compare_digest(supplied, verify_token) or not challenge:
                return "Forbidden", 403
            return make_response(challenge, 200, {"Content-Type": "text/plain; charset=utf-8"})
        raw = request.get_data(cache=True)
        if len(raw) > 3 * 1024 * 1024:
            return "Payload too large", 413
        if not verify_meta_signature(raw, request.headers.get("X-Hub-Signature-256"), current_app.config.get("WHATSAPP_APP_SECRET", "")):
            return "Invalid signature", 401
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "Invalid JSON", 400
        if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
            return "Unsupported payload", 400
        business_id = str(current_app.config.get("WHATSAPP_BUSINESS_ACCOUNT_ID", ""))
        phone_id = str(current_app.config.get("WHATSAPP_PHONE_NUMBER_ID", ""))
        try:
            for entry in payload.get("entry", []):
                if not isinstance(entry, dict) or not business_id or str(entry.get("id", "")) != business_id:
                    continue
                for change in entry.get("changes", []):
                    if not isinstance(change, dict) or change.get("field") != "messages":
                        continue
                    value = change.get("value", {})
                    if not isinstance(value, dict):
                        continue
                    metadata = value.get("metadata", {})
                    if not phone_id or not isinstance(metadata, dict) or str(metadata.get("phone_number_id", "")) != phone_id:
                        continue
                    for message in value.get("messages", []):
                        handle_inbound(message)
                    for status in value.get("statuses", []):
                        handle_status(status)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("WhatsApp webhook processing failed")
            return "Webhook processing failed", 500
        return "EVENT_RECEIVED", 200

    with app.app_context():
        db.create_all()
        if app.config.get("APP_ROLE") != "worker" and not AdminUser.query.first():
            if app.config.get("APP_ENV") == "production":
                password_hash = app.config.get("ADMIN_PASSWORD_HASH", "")
                username = app.config.get("ADMIN_USERNAME", "")
                if not username or not password_hash:
                    raise RuntimeError("Set ADMIN_USERNAME and ADMIN_PASSWORD_HASH to create the first administrator.")
                user = AdminUser(username=username, password_hash=password_hash, must_change_password=False)
            else:
                dev_password = app.config.get("ADMIN_PASSWORD") or DEMO_PASSWORD
                user = AdminUser(username=app.config.get("ADMIN_USERNAME") or DEMO_USERNAME,
                    password_hash=generate_password_hash(dev_password), must_change_password=(dev_password == DEMO_PASSWORD))
            db.session.add(user)
            db.session.commit()
    return app

def handle_inbound(message: dict) -> None:
    if not isinstance(message, dict) or not message.get("id"):
        return
    event_key = f"in:{message['id']}"
    if WebhookEvent.query.filter_by(event_key=event_key[:220]).first():
        return
    db.session.add(WebhookEvent(event_key=event_key[:220], event_type="inbound"))
    raw_phone = message.get("from", "")
    try:
        phone = normalize_phone("+" + str(raw_phone).lstrip("+"))
    except ValueError:
        return
    contact = Recipient.query.filter_by(phone_e164=phone).first()
    if not contact:
        return
    stamp = message.get("timestamp")
    try:
        inbound_at = datetime.fromtimestamp(int(stamp), tz=timezone.utc) if stamp else utcnow()
    except (ValueError, TypeError, OSError):
        inbound_at = utcnow()
    content = message.get("text", {}).get("body", "") if message.get("type") == "text" else ""
    if isinstance(content, str) and content.strip().casefold() in {"stop", "unsubscribe", "cancel", "end", "quit"}:
        contact.suppressed_at = inbound_at
        db.session.add(Activity(event="recipient_opted_out", detail="Webhook opt-out recorded"))
    else:
        contact.last_inbound_at = inbound_at
        db.session.add(Activity(event="inbound_message", detail="Inbound message timestamp recorded"))

def handle_status(status: dict) -> None:
    if not isinstance(status, dict) or not status.get("id") or not status.get("status"):
        return
    name = str(status["status"]).lower()
    if name not in {"sent", "delivered", "read", "failed"}:
        return
    provider_id = str(status["id"])[:180]
    timestamp = str(status.get("timestamp", ""))[:80]
    key_input = f"{provider_id}\0{name}\0{timestamp}"
    event_key = "status:" + hashlib.sha256(key_input.encode("utf-8")).hexdigest()
    if WebhookEvent.query.filter_by(event_key=event_key).first() or db.session.get(PendingMessageStatus, event_key):
        return
    errors = status.get("errors", [])
    error_code = str(errors[0].get("code", "delivery_failed"))[:64] if errors and isinstance(errors[0], dict) else "delivery_failed"
    row = TaskRecipient.query.filter_by(provider_message_id=provider_id).first()
    if row:
        db.session.add(WebhookEvent(event_key=event_key, event_type="status"))
        apply_recipient_status(row, name, error_code)
        return
    in_flight = TaskRecipient.query.filter_by(status="submitting", provider_message_id=None).first()
    if in_flight:
        db.session.add(PendingMessageStatus(event_key=event_key, provider_message_id=provider_id,
            status=name, error_code=error_code))
    else:
        db.session.add(WebhookEvent(event_key=event_key, event_type="status_untracked"))

def apply_recipient_status(row: TaskRecipient, name: str, error_code: str | None = None) -> None:
    rank = {"queued": 0, "submitting": 1, "unknown": 1, "submitted": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 4}
    previous = row.status
    if previous == "failed" or (name == "failed" and previous in {"delivered", "read"}):
        return
    if name != "failed" and rank.get(name, -1) < rank.get(previous, 0):
        return
    if previous == name:
        return
    row.status = name
    row.error_code = error_code if name == "failed" else None
    row.updated_at = utcnow()
    task = row.task
    db.session.flush()
    task.failure_count = TaskRecipient.query.filter_by(task_id=task.id, status="failed").count()
    task.unknown_count = TaskRecipient.query.filter_by(task_id=task.id, status="unknown").count()
    if task.state in {"completed", "completed_with_errors"}:
        task.state = "completed_with_errors" if task.failure_count or task.unknown_count else "completed"
    task.updated_at = utcnow()

def apply_pending_message_statuses(row: TaskRecipient) -> None:
    if not row.provider_message_id:
        return
    pending = PendingMessageStatus.query.filter_by(provider_message_id=row.provider_message_id).order_by(
        PendingMessageStatus.received_at.asc()).all()
    for event in pending:
        if not WebhookEvent.query.filter_by(event_key=event.event_key).first():
            db.session.add(WebhookEvent(event_key=event.event_key, event_type="status"))
            apply_recipient_status(row, event.status, event.error_code)
        db.session.delete(event)

app = create_app()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker_main()
    else:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=(APP_ENV == "development"))