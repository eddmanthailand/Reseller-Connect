import logging
import secrets
import threading
import collections
import time as _time
import os
from functools import wraps
from flask import request, jsonify, session, redirect

# ─────────────────────────────────────────────
# IP-based Rate Limiter (in-memory, thread-safe)
# ─────────────────────────────────────────────
_rate_store: dict = collections.defaultdict(list)
_rate_lock = threading.Lock()

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """Return True if allowed, False if rate limit exceeded."""
    now = _time.monotonic()
    cutoff = now - window_seconds
    with _rate_lock:
        hits = _rate_store[key]
        hits[:] = [t for t in hits if t > cutoff]
        if len(hits) >= max_requests:
            return False
        hits.append(now)
        return True


# ─────────────────────────────────────────────
# Origin / Referer validator for public APIs
# ─────────────────────────────────────────────
_ALLOWED_HOSTS = {
    'ekgshops.com',
    'www.ekgshops.com',
}
_replit_dev = os.environ.get('REPLIT_DEV_DOMAIN', '')
if _replit_dev:
    _ALLOWED_HOSTS.add(_replit_dev)

def is_trusted_origin() -> bool:
    """Check that the request comes from a trusted browser origin or referer."""
    import urllib.parse as _urlparse
    for header in ('Origin', 'Referer'):
        val = request.headers.get(header, '')
        if not val:
            continue
        try:
            host = _urlparse.urlparse(val).netloc.split(':')[0]
        except Exception:
            continue
        if host in _ALLOWED_HOSTS:
            return True
    # Allow requests with no origin header (e.g. same-origin page requests,
    # server-side calls).  Reject only when an explicit foreign origin is set.
    if not request.headers.get('Origin') and not request.headers.get('Referer'):
        return True
    return False


def handle_error(e, user_msg='เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง'):
    """Log full error for admin, return safe generic message to user."""
    logging.error(e, exc_info=True)
    return jsonify({'error': user_msg}), 500


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
            return redirect('/login')
        if session.get('role') not in ['Super Admin', 'Assistant Admin']:
            return jsonify({'error': 'คุณไม่มีสิทธิ์เข้าถึงส่วนนี้ (เฉพาะแอดมิน)'}), 403
        return f(*args, **kwargs)
    return decorated_function


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token():
    token = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token')
    if not token or token != session.get('_csrf_token'):
        return False
    return True


def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if not validate_csrf_token():
                return jsonify({'error': 'เซสชันหมดอายุ กรุณารีเฟรชหน้าเว็บ'}), 403
        return f(*args, **kwargs)
    return decorated_function
