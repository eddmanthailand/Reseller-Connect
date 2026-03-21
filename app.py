from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, make_response
from flask_cors import CORS
import psycopg2.extras
import bcrypt
from functools import wraps
from database import get_db, init_db
from utils import handle_error, login_required, admin_required
import os
import logging
import threading
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
_log_file_handler = logging.FileHandler('/tmp/app.log', mode='a', encoding='utf-8')
_log_file_handler.setLevel(logging.WARNING)
_log_file_handler.setFormatter(_log_formatter)
_log_stream_handler = logging.StreamHandler()
_log_stream_handler.setFormatter(_log_formatter)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[_log_stream_handler, _log_file_handler]
)
logging.getLogger('werkzeug').setLevel(logging.ERROR)
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from replit.object_storage import Client
from datetime import timedelta, datetime
import time
import secrets
from pywebpush import webpush, WebPushException
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# SESSION_SECRET is required for production security
session_secret = os.environ.get('SESSION_SECRET')
if not session_secret:
    raise RuntimeError(
        "SESSION_SECRET environment variable is required. "
        "Please configure a strong session secret for security."
    )
app.secret_key = session_secret

# Configure session cookie for iframe embedding (Replit preview)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['PREFERRED_URL_SCHEME'] = 'https'

# Rate limiting storage (in-memory for simplicity)
login_attempts = {}
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 300  # 5 minutes

# CSRF token storage
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def validate_csrf_token():
    token = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token')
    if not token or token != session.get('_csrf_token'):
        return False
    return True

# CORS — production domains only; Replit dev domain only in non-production environments
_PROD_ORIGINS = ["https://ekgshops.com", "https://www.ekgshops.com"]
_is_production = os.environ.get('PRODUCTION', '').lower() in ('1', 'true', 'yes')

if _is_production:
    allowed_origins = _PROD_ORIGINS
else:
    _replit_dev = os.environ.get('REPLIT_DEV_DOMAIN', '')
    allowed_origins = _PROD_ORIGINS + (
        [f"https://{_replit_dev}"] if _replit_dev else []
    )

CORS(app, supports_credentials=True, origins=allowed_origins)

# Initialize database on startup
init_db()

# Register blueprints
from routes.agent import agent_bp
app.register_blueprint(agent_bp)

from routes.stripe_payment import stripe_bp
app.register_blueprint(stripe_bp)

from blueprints.facebook_ads import facebook_ads_bp
app.register_blueprint(facebook_ads_bp)

from blueprints.product_analytics import product_analytics_bp
app.register_blueprint(product_analytics_bp)

from blueprints.guest_bot import guest_bot_bp
app.register_blueprint(guest_bot_bp)

from blueprints.member_bot import member_bot_bp
app.register_blueprint(member_bot_bp)

from blueprints.warehouse import warehouse_bp
app.register_blueprint(warehouse_bp)

from blueprints.analytics import analytics_bp
app.register_blueprint(analytics_bp)

from blueprints.marketing import marketing_bp
app.register_blueprint(marketing_bp)

from blueprints.settings import settings_bp
app.register_blueprint(settings_bp)

from blueprints.push import push_bp
app.register_blueprint(push_bp)

from blueprints.mail_utils import send_email, send_order_status_chat, send_order_notification_to_admin, send_order_status_email, send_low_stock_alert, send_password_reset_email, log_activity

from blueprints.reseller import reseller_bp
app.register_blueprint(reseller_bp)

from blueprints.orders import orders_bp
app.register_blueprint(orders_bp)

from blueprints.products import products_bp
app.register_blueprint(products_bp)

from blueprints.cart import cart_bp
app.register_blueprint(cart_bp)

from blueprints.auth import auth_bp, oauth
oauth.init_app(app)
app.register_blueprint(auth_bp)

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')


@app.route('/robots.txt')
def robots_txt():
    content = (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Allow: /catalog\n"
        "Allow: /\n"
        "\n"
        "Sitemap: https://ekgshops.com/sitemap.xml\n"
    )
    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/.well-known/security.txt')
def security_txt():
    content = (
        "Contact: mailto:admin@ekgshops.com\n"
        "Preferred-Languages: th, en\n"
        "Policy: https://ekgshops.com/privacy-policy\n"
    )
    return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.errorhandler(400)
def bad_request(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Bad Request', 'message': str(e)}), 400
    return e

@app.errorhandler(401)
def unauthorized(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Unauthorized', 'message': 'กรุณาเข้าสู่ระบบก่อน'}), 401
    return e

@app.errorhandler(403)
def forbidden(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Forbidden', 'message': 'คุณไม่มีสิทธิ์เข้าถึงส่วนนี้'}), 403
    return e

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not Found', 'message': f'ไม่พบ endpoint: {request.path}'}), 404
    return e

@app.errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Method Not Allowed', 'message': str(e)}), 405
    return e

@app.errorhandler(500)
def internal_error(e):
    logging.error(f'500 Internal Server Error: {e}', exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal Server Error', 'message': 'เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่อีกครั้ง'}), 500
    return e

@app.errorhandler(Exception)
def unhandled_exception(e):
    logging.error(f'Unhandled Exception: {e}', exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Server Error', 'message': 'เกิดข้อผิดพลาดที่ไม่คาดคิด กรุณาลองใหม่อีกครั้ง'}), 500
    return jsonify({'error': str(e)}), 500


@app.after_request
def add_header(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    # Security headers — applied to all responses
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(), payment=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://connect.facebook.net https://www.googletagmanager.com "
            "https://www.clarity.ms https://cdn.clarity.ms https://js.stripe.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https: http:; "
        "connect-src 'self' https://api.facebook.com https://graph.facebook.com "
            "https://www.clarity.ms https://api.stripe.com; "
        "frame-src 'self' https://js.stripe.com https://www.facebook.com; "
        "object-src 'none';"
    )
    # Remove server identification
    response.headers.pop('Server', None)
    return response


# ==================== AUTO-CANCEL SCHEDULER ====================

def _auto_cancel_expired_orders():
    """
    Background job: Cancel pending_payment orders older than 24 hours.
    Restores stock and notifies resellers via bot chat.
    Runs every 30 minutes via APScheduler.
    """
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Find expired pending_payment orders (older than 24 hours)
        cursor.execute('''
            SELECT id, order_number, user_id, final_amount
            FROM orders
            WHERE status = 'pending_payment'
              AND created_at < NOW() - INTERVAL '24 hours'
            FOR UPDATE SKIP LOCKED
        ''')
        expired_orders = cursor.fetchall()

        if not expired_orders:
            return

        print(f"[AUTO-CANCEL] Found {len(expired_orders)} expired orders to cancel")

        # Get system admin id once
        cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin') LIMIT 1")
        admin_row = cursor.fetchone()
        system_admin_id = admin_row['id'] if admin_row else 1

        for order in expired_orders:
            order_id = order['id']
            order_number = order['order_number'] or f'#{order_id}'
            reseller_id = order['user_id']

            try:
                # Get shipment items to restore stock
                cursor.execute('''
                    SELECT osi.order_item_id, osi.quantity, os.warehouse_id, oi.sku_id
                    FROM order_shipment_items osi
                    JOIN order_shipments os ON os.id = osi.shipment_id
                    JOIN order_items oi ON oi.id = osi.order_item_id
                    WHERE os.order_id = %s
                ''', (order_id,))
                shipment_items = cursor.fetchall()

                # Restore warehouse stock
                for item in shipment_items:
                    cursor.execute('''
                        UPDATE sku_warehouse_stock
                        SET stock = stock + %s
                        WHERE sku_id = %s AND warehouse_id = %s
                    ''', (item['quantity'], item['sku_id'], item['warehouse_id']))

                    cursor.execute('''
                        INSERT INTO stock_audit_log
                            (sku_id, warehouse_id, quantity_before, quantity_after, change_type,
                             reference_id, reference_type, notes, created_by)
                        SELECT %s, %s, stock - %s, stock, 'order_cancel', %s, 'order',
                               'Auto-cancel: ไม่ชำระเงินภายใน 24 ชม.', %s
                        FROM sku_warehouse_stock
                        WHERE sku_id = %s AND warehouse_id = %s
                    ''', (item['sku_id'], item['warehouse_id'], item['quantity'],
                          order_id, system_admin_id, item['sku_id'], item['warehouse_id']))

                # Restore main SKU stock
                cursor.execute('''
                    SELECT sku_id, SUM(quantity) as total_qty
                    FROM order_items WHERE order_id = %s
                    GROUP BY sku_id
                ''', (order_id,))
                for sku in cursor.fetchall():
                    cursor.execute(
                        'UPDATE skus SET stock = stock + %s WHERE id = %s',
                        (sku['total_qty'], sku['sku_id'])
                    )

                # Update order status to cancelled
                cursor.execute('''
                    UPDATE orders
                    SET status = 'cancelled',
                        notes = CONCAT(COALESCE(notes, ''), ' [ยกเลิกอัตโนมัติ: ไม่ชำระเงินภายใน 24 ชม.]'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (order_id,))

                conn.commit()
                print(f"[AUTO-CANCEL] Cancelled order {order_number} (id={order_id}), stock restored")

                # Notify reseller via bot chat (separate connection to avoid tx conflict)
                try:
                    send_order_status_chat(reseller_id, order_number, 'auto_cancelled', order_id=order_id)
                except Exception as chat_err:
                    print(f"[AUTO-CANCEL] Chat notify error for order {order_number}: {chat_err}")

            except Exception as order_err:
                conn.rollback()
                print(f"[AUTO-CANCEL] Error cancelling order {order_number}: {order_err}")

    except Exception as e:
        print(f"[AUTO-CANCEL] Scheduler error: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# Start APScheduler — runs auto-cancel every 30 minutes
def _check_restock_and_notify():
    """
    Runs periodically — checks if any SKU in restock_alerts is back in stock.
    For members: sends a chat notification.
    For guests: marks as 'notified' so admin can see it in admin panel.
    Frequency: every 4 hours.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT ra.id, ra.product_id, ra.size, ra.product_name,
                           ra.user_id, ra.phone, ra.session_id,
                           p.name as p_name
                    FROM restock_alerts ra
                    LEFT JOIN products p ON p.id = ra.product_id
                    WHERE ra.status = 'pending'
                    ORDER BY ra.created_at ASC
                    LIMIT 100
                ''')
                alerts = cur.fetchall()
                if not alerts:
                    return

                notified_ids = []
                for alert in alerts:
                    pid = alert['product_id']
                    size = str(alert.get('size') or '').strip().upper()
                    if not pid:
                        continue

                    cur.execute('''
                        SELECT s.id, s.stock,
                               COALESCE(json_object_agg(o.name, ov.value)
                                        FILTER (WHERE o.id IS NOT NULL), '{}') as options
                        FROM skus s
                        LEFT JOIN sku_values_map svm ON svm.sku_id = s.id
                        LEFT JOIN option_values ov ON ov.id = svm.option_value_id
                        LEFT JOIN options o ON o.id = ov.option_id
                        WHERE s.product_id = %s AND s.stock > 0
                        GROUP BY s.id, s.stock
                    ''', (pid,))
                    in_stock_skus = cur.fetchall()

                    is_back = False
                    if size:
                        for sku in in_stock_skus:
                            opts = sku.get('options') or {}
                            for v in opts.values():
                                if str(v).upper() == size:
                                    is_back = True
                                    break
                            if is_back:
                                break
                    else:
                        is_back = len(in_stock_skus) > 0

                    if is_back:
                        pname = alert.get('p_name') or alert.get('product_name') or 'สินค้า'
                        size_label = f' ไซส์ {alert["size"]}' if alert.get('size') else ''
                        notif_msg = f'🔔 แจ้งเตือนสต็อกคืน: {pname}{size_label} มีสินค้าแล้วนะคะ สามารถสั่งซื้อได้เลยค่ะ 😊'

                        if alert.get('user_id'):
                            try:
                                send_order_status_chat(
                                    alert['user_id'], f'restock#{alert["id"]}',
                                    'restock', notif_msg
                                )
                            except Exception as _ne:
                                print(f'[RESTOCK] chat notify error: {_ne}')

                        cur.execute('''
                            UPDATE restock_alerts
                            SET status = 'notified', notified_at = NOW()
                            WHERE id = %s
                        ''', (alert['id'],))
                        notified_ids.append(alert['id'])
                        print(f'[RESTOCK] Notified alert #{alert["id"]} pid={pid} size={size}')

                if notified_ids:
                    conn.commit()
                    print(f'[RESTOCK] Notified {len(notified_ids)} restock alerts')
    except Exception as e:
        print(f'[RESTOCK] Scheduler error: {e}')


_scheduler = BackgroundScheduler(daemon=True, timezone='Asia/Bangkok')
_scheduler.add_job(
    _auto_cancel_expired_orders,
    trigger='interval',
    minutes=30,
    id='auto_cancel_expired_orders',
    replace_existing=True,
    max_instances=1
)
_scheduler.add_job(
    _check_restock_and_notify,
    trigger='interval',
    hours=4,
    id='check_restock_alerts',
    replace_existing=True,
    max_instances=1
)
_scheduler.start()
print("[SCHEDULER] Auto-cancel scheduler started (every 30 min)")
print("[SCHEDULER] Restock check scheduler started (every 4 hours)")

# ==================== END AUTO-CANCEL SCHEDULER ====================


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
