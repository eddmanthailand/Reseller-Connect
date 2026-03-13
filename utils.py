import logging
from functools import wraps
from flask import request, jsonify, session, redirect, url_for


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
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
            return redirect(url_for('login_page'))
        if session.get('role') not in ['Super Admin', 'Assistant Admin']:
            return jsonify({'error': 'คุณไม่มีสิทธิ์เข้าถึงส่วนนี้ (เฉพาะแอดมิน)'}), 403
        return f(*args, **kwargs)
    return decorated_function
