import logging
import secrets
from functools import wraps
from flask import request, jsonify, session, redirect


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
