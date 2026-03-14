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

# CORS configuration - allow Replit domains
allowed_origins = [
    f"https://{os.environ.get('REPLIT_DEV_DOMAIN', '')}",
    f"https://{os.environ.get('REPLIT_DEPLOYMENT_DOMAIN', '')}",
    "https://ekgshops.com",
    "https://www.ekgshops.com"
]
allowed_origins = [o for o in allowed_origins if o and o != "https://"]

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

from blueprints.guest_bot import guest_bot_bp
app.register_blueprint(guest_bot_bp)

from blueprints.member_bot import member_bot_bp
app.register_blueprint(member_bot_bp)

from blueprints.warehouse import warehouse_bp
app.register_blueprint(warehouse_bp)

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

# ==================== GOOGLE OAUTH ====================
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@app.route('/test/google')
@app.route('/auth/google')
def test_google_login():
    """Redirect to Google OAuth"""
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback — login existing user or auto-register new Reseller"""
    conn = None
    cursor = None
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            return redirect('/login?error=google_failed')

        email = user_info.get('email', '').strip().lower()
        name = user_info.get('name', '')

        if not email:
            return redirect('/login?error=no_email')

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.email,
                   r.name as role_name, u.reseller_tier_id, rt.name as reseller_tier_name
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE LOWER(u.email) = %s
        ''', (email,))
        user = cursor.fetchone()

        if user:
            display_name = user['full_name'] or user['username'] or email.split('@')[0]
            session.clear()
            session['user_id'] = user['id']
            session['role'] = user['role_name']
            session['reseller_tier'] = user['reseller_tier_name'] or 'Bronze'
            session['full_name'] = display_name
            session['username'] = user['username']
            session['_csrf_token'] = secrets.token_hex(32)
            session.permanent = True
            role = user['role_name']
            if 'Admin' in role:
                return redirect('/admin')
            return redirect('/dashboard')

        # Email not found → auto-register as Reseller
        base_username = email.split('@')[0].replace('.', '_').replace('-', '_')
        username = base_username
        counter = 1
        while True:
            cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
            if not cursor.fetchone():
                break
            username = f'{base_username}{counter}'
            counter += 1

        cursor.execute("SELECT id FROM roles WHERE name = 'Reseller'")
        reseller_role = cursor.fetchone()
        if not reseller_role:
            return redirect('/login?error=no_role')

        cursor.execute('SELECT id, name FROM reseller_tiers ORDER BY level_rank ASC LIMIT 1')
        default_tier = cursor.fetchone()
        tier_id = default_tier['id'] if default_tier else None
        tier_name = default_tier['name'] if default_tier else 'Bronze'

        random_password = secrets.token_hex(32)
        password_hash = bcrypt.hashpw(random_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        display_name = name or username

        cursor.execute('''
            INSERT INTO users (full_name, username, password, role_id, reseller_tier_id, email)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (display_name, username, password_hash, reseller_role['id'], tier_id, email))

        new_user_id = cursor.fetchone()['id']
        conn.commit()

        # Track register_complete conversion event
        try:
            visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
            user_agent = request.headers.get('User-Agent', '')
            utm_campaign = session.get('_utm_campaign') or request.referrer or None
            traffic_type = 'facebook' if (utm_campaign and 'fb' in str(utm_campaign).lower()) else 'organic'
            import uuid as _uuid
            sess_id = session.get('_tracking_session') or str(_uuid.uuid4())[:16]
            cursor.execute('''
                INSERT INTO conversion_events (session_id, event_type, source, traffic_type, utm_campaign, visitor_ip, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (sess_id, 'register_complete', 'google_oauth', traffic_type, utm_campaign, visitor_ip, user_agent[:300] if user_agent else ''))
            conn.commit()
        except Exception:
            pass

        session.clear()
        session['user_id'] = new_user_id
        session['role'] = 'Reseller'
        session['reseller_tier'] = tier_name
        session['full_name'] = display_name
        session['username'] = username
        session['_csrf_token'] = secrets.token_hex(32)
        session.permanent = True

        return redirect('/dashboard')

    except Exception as e:
        logging.error(f"Google callback error: {e}", exc_info=True)
        return redirect('/login?error=oauth_failed')
    finally:
        if cursor:
            cursor.close()

# Disable caching for HTML responses to ensure updates are visible
@app.after_request
def add_header(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# CSRF protection decorator for state-changing endpoints
def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            if not validate_csrf_token():
                return jsonify({'error': 'เซสชันหมดอายุ กรุณารีเฟรชหน้าเว็บ'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """Get CSRF token for authenticated requests"""
    return jsonify({'csrf_token': generate_csrf_token()}), 200

@app.route('/')
def index():
    """Show landing page for guests, redirect to dashboard if logged in"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing_page.html')

@app.route('/login')
def login_page():
    """Render login page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register')
def register_page():
    """QR code landing page - handles WebView browsers that block Google OAuth"""
    role = session.get('role')
    is_admin = role in ('Super Admin', 'Assistant Admin')
    if 'user_id' in session and not is_admin:
        return redirect(url_for('dashboard'))
    return render_template('register.html', preview_mode=is_admin)

@app.route('/become-reseller')
def fb_landing_page():
    """Landing page for Facebook Ads - separate from main registration"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('fb_landing.html')

@app.route('/join')
def ad_landing_page():
    """New ad landing page for Google/Facebook ads"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('ad_landing.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard after login - routes based on role"""
    role = session.get('role')
    
    if role in ['Super Admin', 'Assistant Admin']:
        return redirect(url_for('admin_management'))
    elif role == 'Reseller':
        return render_template('reseller_spa.html')
    else:
        return redirect(url_for('login_page'))

@app.route('/admin')
@admin_required
def admin_management():
    """Render the admin dashboard"""
    return render_template('admin_dashboard.html')

@app.route('/chat')
@admin_required
def admin_chat_page():
    """Full-page chat interface for admins"""
    response = make_response(render_template('chat.html', user_name=session.get('full_name', ''), user_role=session.get('role', '')))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/admin/products')
@admin_required
def product_list():
    """Redirect to admin dashboard (Product Management is now integrated)"""
    return redirect(url_for('admin_management'))

@app.route('/admin/products/create')
@admin_required
def product_create():
    """Render the product creation page"""
    return render_template('product_create.html')

@app.route('/admin/products/edit/<int:product_id>')
@admin_required
def product_edit(product_id):
    """Render the product edit page"""
    return render_template('product_edit.html')

@app.route('/admin/mto/products/create')
@admin_required
def mto_product_create():
    """Render the MTO product creation page"""
    return render_template('mto_product_create.html')

@app.route('/admin/mto/products/edit/<int:product_id>')
@admin_required
def mto_product_edit(product_id):
    """Render the MTO product edit page"""
    return render_template('mto_product_edit.html')

@app.route('/admin/brands')
@admin_required
def brand_management():
    """Render the brand management page"""
    return render_template('brand_management.html')

@app.route('/admin/categories')
@admin_required
def category_management():
    """Render the category management page"""
    return render_template('category_management.html')

@app.route('/api/public/products', methods=['GET'])
def public_products():
    """Get products for public catalog/landing page (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        brand_id = request.args.get('brand')
        category_id = request.args.get('category')
        featured_only = request.args.get('featured') == '1'

        query = '''
            SELECT
                p.id,
                p.name,
                p.is_featured,
                b.id as brand_id,
                b.name as brand_name,
                (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                (SELECT MIN(s.price) FROM skus s WHERE s.product_id = p.id) as min_price,
                (SELECT MAX(s.price) FROM skus s WHERE s.product_id = p.id) as max_price,
                COALESCE((SELECT SUM(s.stock) FROM skus s WHERE s.product_id = p.id), 0) as total_stock,
                (SELECT STRING_AGG(c.name, \', \') FROM product_categories pc JOIN categories c ON c.id = pc.category_id WHERE pc.product_id = p.id) as category_names,
                (SELECT MAX(ptp.discount_percent) FROM product_tier_pricing ptp WHERE ptp.product_id = p.id) as max_discount_percent,
                (SELECT MIN(ptp.discount_percent) FROM product_tier_pricing ptp WHERE ptp.product_id = p.id) as min_discount_percent
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.status = \'active\'
        '''
        params = []

        if brand_id:
            query += ' AND p.brand_id = %s'
            params.append(int(brand_id))
        if category_id:
            query += ' AND EXISTS (SELECT 1 FROM product_categories pc WHERE pc.product_id = p.id AND pc.category_id = %s)'
            params.append(int(category_id))
        if featured_only:
            query += ' AND p.is_featured = TRUE'

        query += ' ORDER BY p.is_featured DESC, p.created_at DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        products = []
        for r in rows:
            d = dict(r)
            d['min_price'] = float(d['min_price']) if d.get('min_price') is not None else 0
            d['max_price'] = float(d['max_price']) if d.get('max_price') is not None else 0
            d['total_stock'] = int(d['total_stock']) if d.get('total_stock') is not None else 0
            d['max_discount_percent'] = float(d['max_discount_percent']) if d.get('max_discount_percent') is not None else 0
            d['min_discount_percent'] = float(d['min_discount_percent']) if d.get('min_discount_percent') is not None else 0
            products.append(d)

        return jsonify({'products': products}), 200
    except Exception as e:
        print(f"Error fetching public products: {e}")
        return jsonify({'products': [], 'error': str(e)}), 200
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/public/brands', methods=['GET'])
def public_brands():
    """Get all brands for public catalog filter (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT b.id, b.name
            FROM brands b
            WHERE EXISTS (SELECT 1 FROM products p WHERE p.brand_id = b.id AND p.status = \'active\')
            ORDER BY b.name
        ''')
        return jsonify({'brands': cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({'brands': []}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/public/categories', methods=['GET'])
def public_categories():
    """Get all categories for public catalog filter (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT c.id, c.name
            FROM categories c
            WHERE EXISTS (
                SELECT 1 FROM product_categories pc
                JOIN products p ON p.id = pc.product_id
                WHERE pc.category_id = c.id AND p.status = \'active\'
            )
            ORDER BY c.name
        ''')
        return jsonify({'categories': cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({'categories': []}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/public/promotions', methods=['GET'])
def public_promotions():
    """Get active promotions and shipping promotions for public catalog (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        now = __import__('datetime').datetime.now()

        cursor.execute('''
            SELECT id, name, promo_type, reward_type, reward_value,
                   condition_min_spend, start_date, end_date
            FROM promotions
            WHERE is_active = TRUE
              AND (start_date IS NULL OR start_date <= %s)
              AND (end_date IS NULL OR end_date >= %s)
            ORDER BY priority DESC, created_at DESC
        ''', (now, now))
        promos = []
        for r in cursor.fetchall():
            d = dict(r)
            d['reward_value'] = float(d['reward_value']) if d.get('reward_value') is not None else 0
            d['condition_min_spend'] = float(d['condition_min_spend']) if d.get('condition_min_spend') is not None else 0
            d['type'] = 'promotion'
            promos.append(d)

        cursor.execute('''
            SELECT id, name, promo_type, min_order_value, discount_amount, start_date, end_date
            FROM shipping_promotions
            WHERE is_active = TRUE
              AND (start_date IS NULL OR start_date <= %s)
              AND (end_date IS NULL OR end_date >= %s)
            ORDER BY min_order_value ASC
        ''', (now, now))
        for r in cursor.fetchall():
            d = dict(r)
            d['min_order_value'] = float(d['min_order_value']) if d.get('min_order_value') is not None else 0
            d['type'] = 'shipping'
            promos.append(d)

        return jsonify({'promotions': promos}), 200
    except Exception as e:
        return jsonify({'promotions': []}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/public/product/<int:product_id>/skus', methods=['GET'])
def public_product_skus(product_id):
    """Get SKU variants for a product for the public catalog cart (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT p.id, p.name, p.product_type, p.size_chart_image_url,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                   (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                     JOIN reseller_tiers rt ON rt.id = ptp.tier_id
                     WHERE ptp.product_id = p.id ORDER BY rt.upgrade_threshold ASC LIMIT 1) as tier1_discount
            FROM products p
            WHERE p.id = %s AND p.status = 'active'
        ''', (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        cursor.execute('''
            SELECT s.id, s.sku_code, s.price, s.stock,
                   COALESCE(
                       json_object_agg(o.name, ov.value) FILTER (WHERE o.id IS NOT NULL),
                       '{}'::json
                   ) as options
            FROM skus s
            LEFT JOIN sku_values_map svm ON svm.sku_id = s.id
            LEFT JOIN option_values ov ON ov.id = svm.option_value_id
            LEFT JOIN options o ON o.id = ov.option_id
            WHERE s.product_id = %s
            GROUP BY s.id, s.sku_code, s.price, s.stock
            ORDER BY s.price ASC, s.id ASC
        ''', (product_id,))
        skus = []
        for r in cursor.fetchall():
            d = dict(r)
            d['price'] = float(d['price']) if d.get('price') else 0
            d['stock'] = int(d['stock']) if d.get('stock') else 0
            if d.get('options') is None:
                d['options'] = {}
            skus.append(d)

        p = dict(product)
        p['tier1_discount'] = float(p['tier1_discount']) if p.get('tier1_discount') is not None else 0

        cursor.execute('''
            SELECT scg.id, scg.name, scg.columns, scg.rows
            FROM size_chart_groups scg
            JOIN products pr ON pr.size_chart_group_id = scg.id
            WHERE pr.id = %s
        ''', (product_id,))
        sc_row = cursor.fetchone()
        if sc_row:
            p['size_chart_group'] = {
                'id': sc_row['id'],
                'name': sc_row['name'],
                'columns': sc_row['columns'] if isinstance(sc_row['columns'], list) else json.loads(sc_row['columns'] or '[]'),
                'rows': sc_row['rows'] if isinstance(sc_row['rows'], list) else json.loads(sc_row['rows'] or '[]')
            }
        else:
            p['size_chart_group'] = None

        return jsonify({'product': p, 'skus': skus}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/catalog')
def public_catalog():
    """Public product catalog page - no login required"""
    return render_template('catalog.html')

@app.route('/api/public/tiers', methods=['GET'])
def public_tiers():
    """Get reseller tiers for public landing page (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, description, upgrade_threshold, level_rank
            FROM reseller_tiers
            ORDER BY level_rank ASC
        ''')
        tiers = cursor.fetchall()
        
        return jsonify({'tiers': tiers}), 200
    except Exception as e:
        print(f"Error fetching tiers: {e}")
        return jsonify({'tiers': [], 'error': str(e)}), 200
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/catalog-bot/sessions', methods=['GET'])
@login_required
def admin_catalog_bot_sessions():
    if session.get('role') not in ['Super Admin', 'Assistant Admin']:
        return jsonify({'error': 'Forbidden'}), 403
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        limit = min(int(request.args.get('limit', 100)), 500)
        offset = max(int(request.args.get('offset', 0)), 0)
        cursor.execute('''
            SELECT session_id, ip, started_at, last_seen, msg_count
            FROM guest_chat_sessions
            ORDER BY last_seen DESC
            LIMIT %s OFFSET %s
        ''', (limit, offset))
        sessions = [dict(r) for r in cursor.fetchall()]
        cursor.execute('SELECT COUNT(*) AS total FROM guest_chat_sessions')
        total = cursor.fetchone()['total']
        return jsonify({'sessions': sessions, 'total': total}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/admin/catalog-bot/sessions/<path:session_id>/messages', methods=['GET'])
@login_required
def admin_catalog_bot_messages(session_id):
    if session.get('role') not in ['Super Admin', 'Assistant Admin']:
        return jsonify({'error': 'Forbidden'}), 403
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT id, user_msg, bot_reply, created_at
            FROM guest_chat_messages
            WHERE session_id = %s
            ORDER BY created_at ASC
        ''', (session_id,))
        messages = [dict(r) for r in cursor.fetchall()]
        return jsonify({'messages': messages}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/admin/guest-chat-stats', methods=['GET'])
@login_required
def admin_guest_chat_stats():
    """Return top guest questions from catalog chat."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        limit = min(int(request.args.get('limit', 100)), 500)
        cursor.execute("""
            SELECT question, count, first_seen, last_seen
            FROM guest_chat_log
            ORDER BY count DESC, last_seen DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        total = sum(r['count'] for r in rows)
        return jsonify({'rows': rows, 'total_questions': len(rows), 'total_messages': total}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/login', methods=['POST'])
def login():
    """Handle user login"""
    data = request.json
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'กรุณากรอกชื่อผู้ใช้และรหัสผ่าน'}), 400
    
    username = data['username']
    password = data['password']
    
    # Rate limiting check
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    current_time = time.time()
    
    # Clean old entries
    login_attempts[client_ip] = [t for t in login_attempts.get(client_ip, []) 
                                  if current_time - t < RATE_LIMIT_WINDOW]
    
    if len(login_attempts.get(client_ip, [])) >= RATE_LIMIT_MAX_ATTEMPTS:
        remaining = int(RATE_LIMIT_WINDOW - (current_time - login_attempts[client_ip][0]))
        return jsonify({'error': f'ลองเข้าสู่ระบบมากเกินไป กรุณารอ {remaining} วินาที'}), 429
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user by username or email
        cursor.execute('''
            SELECT 
                u.id,
                u.full_name,
                u.username,
                u.password,
                r.name as role,
                u.reseller_tier_id,
                rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.username = %s OR u.email = %s
        ''', (username, username))
        
        user = cursor.fetchone()
        
        # Verify password with bcrypt
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            # Record failed attempt
            if client_ip not in login_attempts:
                login_attempts[client_ip] = []
            login_attempts[client_ip].append(current_time)
            return jsonify({'error': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'}), 401
        
        # Clear failed attempts on successful login
        if client_ip in login_attempts:
            del login_attempts[client_ip]
        
        # Regenerate session to prevent session fixation
        session.clear()
        session.permanent = True
        
        # Set session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role']
        session['reseller_tier'] = user['reseller_tier']
        session['_csrf_token'] = secrets.token_hex(32)
        
        # Determine redirect URL based on role
        if user['role'] in ['Super Admin', 'Assistant Admin']:
            redirect_url = '/admin'
        elif user['role'] == 'Reseller':
            redirect_url = '/dashboard'
        else:
            redirect_url = '/dashboard'
        
        log_activity('login', 'auth', f"เข้าสู่ระบบ: {user['username']} ({user['role']})", 
                    target_type='user', target_id=user['id'], target_name=user['full_name'])
        
        return jsonify({
            'message': 'เข้าสู่ระบบสำเร็จ',
            'user': {
                'id': user['id'],
                'full_name': user['full_name'],
                'username': user['username'],
                'role': user['role'],
                'reseller_tier': user['reseller_tier']
            },
            'redirect': redirect_url
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle user logout (API call from dashboard)"""
    user_name = session.get('full_name', 'Unknown')
    user_id = session.get('user_id')
    log_activity('logout', 'auth', f"ออกจากระบบ: {user_name}", 
                target_type='user', target_id=user_id, target_name=user_name)
    session.clear()
    return jsonify({'message': 'ออกจากระบบสำเร็จ'}), 200

@app.route('/logout')
def logout_get():
    """Handle logout via direct URL visit — clears session and redirects to login"""
    session.clear()
    response = redirect(url_for('login_page'))
    response.delete_cookie('session')
    return response

from blueprints.mail_utils import (
    send_email, send_order_status_chat, send_order_notification_to_admin,
    send_order_status_email, send_low_stock_alert, send_password_reset_email, log_activity)
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """Request password reset email"""
    data = request.json
    email = data.get('email', '').strip().lower() if data else ''
    
    if not email:
        return jsonify({'error': 'กรุณากรอกอีเมล'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, full_name, email FROM users WHERE LOWER(email) = %s', (email,))
        user = cursor.fetchone()
        
        if user:
            reset_token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=1)
            
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (%s, %s, %s)
            ''', (user['id'], reset_token, expires_at))
            
            conn.commit()
            
            # Use request host for correct URL
            reset_link = f"{request.host_url}reset-password?token={reset_token}"
            
            send_password_reset_email(user['email'], user['full_name'], reset_token, reset_link)
        
        return jsonify({'message': 'หากอีเมลนี้มีในระบบ คุณจะได้รับลิงก์รีเซ็ตรหัสผ่านทางอีเมล'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/reset-password')
def reset_password_page():
    """Render password reset page"""
    return render_template('reset_password.html')

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """Reset password with token"""
    data = request.json
    token = data.get('token', '') if data else ''
    new_password = data.get('password', '') if data else ''
    
    if not token or not new_password:
        return jsonify({'error': 'กรุณากรอกข้อมูลให้ครบถ้วน'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT prt.id, prt.user_id, prt.expires_at, prt.used_at, u.email
            FROM password_reset_tokens prt
            JOIN users u ON u.id = prt.user_id
            WHERE prt.token = %s
        ''', (token,))
        reset_token = cursor.fetchone()
        
        if not reset_token:
            return jsonify({'error': 'ลิงก์รีเซ็ตรหัสผ่านไม่ถูกต้องหรือหมดอายุ'}), 400
        
        if reset_token['used_at']:
            return jsonify({'error': 'ลิงก์นี้ถูกใช้งานแล้ว'}), 400
        
        if reset_token['expires_at'] < datetime.now():
            return jsonify({'error': 'ลิงก์หมดอายุแล้ว กรุณาขอลิงก์ใหม่'}), 400
        
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_password, reset_token['user_id']))
        cursor.execute('UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE id = %s', (reset_token['id'],))
        
        conn.commit()
        
        log_activity('update', 'user', f"รีเซ็ตรหัสผ่านสำเร็จ: {reset_token['email']}", 
                    target_type='user', target_id=reset_token['user_id'])
        
        return jsonify({'message': 'เปลี่ยนรหัสผ่านสำเร็จ กรุณาเข้าสู่ระบบใหม่'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user info"""
    tier = session.get('reseller_tier')
    # If tier is stored as numeric ID (legacy sessions), look up the name
    if tier is not None:
        try:
            tier_as_int = int(tier)
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT name FROM reseller_tiers WHERE id = %s', (tier_as_int,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                tier = row['name']
                session['reseller_tier'] = tier
        except (ValueError, TypeError):
            pass
    return jsonify({
        'id': session.get('user_id'),
        'username': session.get('username'),
        'full_name': session.get('full_name'),
        'role': session.get('role'),
        'reseller_tier': tier
    }), 200

@app.route('/api/activity-logs', methods=['GET'])
@admin_required
def get_activity_logs():
    """Get activity logs with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    category = request.args.get('category', '')
    action_type = request.args.get('action_type', '')
    user_id = request.args.get('user_id', '', type=str)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    search = request.args.get('search', '')
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        where_clauses = []
        params = []
        
        if category:
            where_clauses.append('action_category = %s')
            params.append(category)
        
        if action_type:
            where_clauses.append('action_type = %s')
            params.append(action_type)
        
        if user_id:
            where_clauses.append('user_id = %s')
            params.append(int(user_id))
        
        if date_from:
            where_clauses.append('created_at >= %s')
            params.append(date_from)
        
        if date_to:
            where_clauses.append('created_at <= %s::date + interval \'1 day\'')
            params.append(date_to)
        
        if search:
            where_clauses.append('(description ILIKE %s OR user_name ILIKE %s OR target_name ILIKE %s)')
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'
        
        cursor.execute(f'SELECT COUNT(*) FROM activity_logs WHERE {where_sql}', params)
        total = cursor.fetchone()['count']
        
        offset = (page - 1) * per_page
        cursor.execute(f'''
            SELECT id, user_id, user_name, action_type, action_category, description,
                   target_type, target_id, target_name, ip_address, created_at
            FROM activity_logs 
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        ''', params + [per_page, offset])
        
        logs = cursor.fetchall()
        result = []
        for log in logs:
            log_dict = dict(log)
            log_dict['created_at'] = log_dict['created_at'].isoformat() if log_dict['created_at'] else None
            result.append(log_dict)
        
        return jsonify({
            'logs': result,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/activity-logs/categories', methods=['GET'])
@admin_required
def get_activity_log_categories():
    """Get distinct activity log categories"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT action_category FROM activity_logs ORDER BY action_category')
        categories = [row[0] for row in cursor.fetchall()]
        
        cursor.execute('SELECT DISTINCT action_type FROM activity_logs ORDER BY action_type')
        action_types = [row[0] for row in cursor.fetchall()]
        
        return jsonify({
            'categories': categories,
            'action_types': action_types
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/check-low-stock', methods=['POST'])
@admin_required
def check_and_alert_low_stock():
    """Check for low stock products and send email alert"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT p.name, s.sku_code, s.stock, COALESCE(p.low_stock_threshold, 5) as threshold
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.stock > 0 AND s.stock <= COALESCE(p.low_stock_threshold, 5)
            ORDER BY s.stock ASC
            LIMIT 50
        ''')
        
        low_stock_products = [dict(row) for row in cursor.fetchall()]
        
        if low_stock_products:
            send_low_stock_alert('cmidcoteam@gmail.com', low_stock_products)
            log_activity('alert', 'stock', f"ส่งแจ้งเตือนสินค้าใกล้หมด {len(low_stock_products)} รายการ")
            return jsonify({
                'message': f'ส่งแจ้งเตือนสินค้าใกล้หมด {len(low_stock_products)} รายการ',
                'products': low_stock_products
            }), 200
        else:
            return jsonify({'message': 'ไม่มีสินค้าใกล้หมด'}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/roles', methods=['GET'])
@admin_required
def get_roles():
    """Get all available roles"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('SELECT id, name FROM roles')
    roles = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(roles)

@app.route('/api/reseller-tiers', methods=['GET'])
@admin_required
def get_reseller_tiers():
    """Get all reseller tiers with their details (admin only)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, level_rank, upgrade_threshold, description, is_manual_only
            FROM reseller_tiers 
            ORDER BY level_rank ASC
        ''')
        
        tiers = cursor.fetchall()
        result = []
        for tier in tiers:
            tier_dict = dict(tier)
            if tier_dict.get('upgrade_threshold'):
                tier_dict['upgrade_threshold'] = float(tier_dict['upgrade_threshold'])
            result.append(tier_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/stats', methods=['GET'])
@login_required
def get_reseller_stats():
    """Get statistics for reseller dashboard"""
    user_role = session.get('role')
    if user_role not in ['Reseller', 'Super Admin', 'Assistant Admin']:
        return jsonify({'error': 'คุณไม่มีสิทธิ์เข้าถึง'}), 403
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT COUNT(*) as product_count
            FROM products
            WHERE COALESCE(status, 'active') = 'active'
        ''')
        
        stats = dict(cursor.fetchone())
        return jsonify(stats), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users with their role information and assigned brands for Assistant Admins"""
    conn = get_db()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute('''
        SELECT 
            u.id,
            u.full_name,
            u.username,
            r.name as role,
            rt.name as reseller_tier
        FROM users u
        JOIN roles r ON u.role_id = r.id
        LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
        ORDER BY u.created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    
    # Get assigned brands for Assistant Admins
    assistant_admin_ids = [u['id'] for u in users if u['role'] == 'Assistant Admin']
    if assistant_admin_ids:
        cursor.execute('''
            SELECT aba.user_id, b.id, b.name
            FROM admin_brand_access aba
            JOIN brands b ON aba.brand_id = b.id
            WHERE aba.user_id = ANY(%s)
            ORDER BY b.name
        ''', (assistant_admin_ids,))
        brand_access = cursor.fetchall()
        
        # Group brands by user_id
        user_brands = {}
        for ba in brand_access:
            user_id = ba['user_id']
            if user_id not in user_brands:
                user_brands[user_id] = []
            user_brands[user_id].append({'id': ba['id'], 'name': ba['name']})
        
        # Add assigned_brands to each user
        for user in users:
            if user['role'] == 'Assistant Admin':
                user['assigned_brands'] = user_brands.get(user['id'], [])
    
    cursor.close()
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user"""
    data = request.json
    
    # Validate required fields
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    required_fields = ['full_name', 'username', 'password', 'role_id']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'กรุณากรอก {field}'}), 400
    
    # Hash password with bcrypt
    password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Privilege check: assistant_admin cannot create admin-level accounts
        current_user_id = session.get('user_id')
        cursor.execute('SELECT r.name as role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s', (current_user_id,))
        current_user = cursor.fetchone()
        if current_user and current_user['role'] == 'assistant_admin':
            cursor.execute('SELECT name FROM roles WHERE id = %s', (data['role_id'],))
            target_role = cursor.fetchone()
            if target_role and target_role['name'] in ('super_admin', 'assistant_admin'):
                return jsonify({'error': 'ผู้ช่วย Admin ไม่มีสิทธิ์สร้างบัญชี Admin'}), 403
        
        # Check if username already exists
        cursor.execute('SELECT id FROM users WHERE username = %s', (data['username'],))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อผู้ใช้นี้ถูกใช้งานแล้ว'}), 400
        
        # Insert new user
        reseller_tier_id = data.get('reseller_tier_id') if data.get('reseller_tier_id') else None
        
        cursor.execute('''
            INSERT INTO users (full_name, username, password, role_id, reseller_tier_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['full_name'], data['username'], password_hash, data['role_id'], reseller_tier_id))
        
        result = cursor.fetchone()
        user_id = result['id']
        
        # Get the created user with role information
        cursor.execute('''
            SELECT 
                u.id,
                u.full_name,
                u.username,
                r.name as role,
                rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.id = %s
        ''', (user_id,))
        
        user = dict(cursor.fetchone())
        
        conn.commit()
        
        return jsonify({
            'message': 'สร้างผู้ใช้สำเร็จ',
            'user': user
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """Get a single user by ID"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.role_id, u.reseller_tier_id,
                   u.tier_manual_override, u.phone, u.email, u.address, u.province,
                   u.district, u.subdistrict, u.postal_code, u.brand_name, u.logo_url,
                   r.name as role, rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.id = %s
        ''', (user_id,))
        
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        return jsonify(dict(user)), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Update an existing user"""
    data = request.json
    
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists
        cursor.execute('''
            SELECT u.id, u.username, r.name as role 
            FROM users u JOIN roles r ON u.role_id = r.id 
            WHERE u.id = %s
        ''', (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        # Privilege check: assistant_admin cannot edit admin accounts or promote to admin
        current_user_id = session.get('user_id')
        cursor.execute('SELECT r.name as role FROM users u JOIN roles r ON u.role_id = r.id WHERE u.id = %s', (current_user_id,))
        current_user = cursor.fetchone()
        if current_user and current_user['role'] == 'assistant_admin':
            if existing_user['role'] in ('super_admin', 'assistant_admin'):
                return jsonify({'error': 'ผู้ช่วย Admin ไม่มีสิทธิ์แก้ไขบัญชี Admin'}), 403
            if 'role_id' in data:
                cursor.execute('SELECT name FROM roles WHERE id = %s', (data['role_id'],))
                target_role = cursor.fetchone()
                if target_role and target_role['name'] in ('super_admin', 'assistant_admin'):
                    return jsonify({'error': 'ผู้ช่วย Admin ไม่มีสิทธิ์เปลี่ยน Role เป็น Admin'}), 403
        
        # Check if username is being changed and if it's already taken
        if 'username' in data and data['username'] != existing_user['username']:
            cursor.execute('SELECT id FROM users WHERE username = %s AND id != %s', (data['username'], user_id))
            if cursor.fetchone():
                return jsonify({'error': 'ชื่อผู้ใช้นี้ถูกใช้งานแล้ว'}), 400
        
        # Build update query
        update_fields = []
        update_values = []
        
        if 'full_name' in data:
            update_fields.append('full_name = %s')
            update_values.append(data['full_name'])
        
        if 'username' in data:
            update_fields.append('username = %s')
            update_values.append(data['username'])
        
        if 'role_id' in data:
            update_fields.append('role_id = %s')
            update_values.append(data['role_id'])
        
        if 'reseller_tier_id' in data:
            update_fields.append('reseller_tier_id = %s')
            update_values.append(data['reseller_tier_id'] if data['reseller_tier_id'] else None)
        
        if 'tier_manual_override' in data:
            update_fields.append('tier_manual_override = %s')
            update_values.append(data['tier_manual_override'])
        
        if 'phone' in data:
            update_fields.append('phone = %s')
            update_values.append(data['phone'] if data['phone'] else None)
        
        if 'email' in data:
            update_fields.append('email = %s')
            update_values.append(data['email'] if data['email'] else None)
        
        if 'address' in data:
            update_fields.append('address = %s')
            update_values.append(data['address'] if data['address'] else None)
        
        if 'province' in data:
            update_fields.append('province = %s')
            update_values.append(data['province'] if data['province'] else None)
        
        if 'district' in data:
            update_fields.append('district = %s')
            update_values.append(data['district'] if data['district'] else None)
        
        if 'subdistrict' in data:
            update_fields.append('subdistrict = %s')
            update_values.append(data['subdistrict'] if data['subdistrict'] else None)
        
        if 'postal_code' in data:
            update_fields.append('postal_code = %s')
            update_values.append(data['postal_code'] if data['postal_code'] else None)
        
        if 'brand_name' in data:
            update_fields.append('brand_name = %s')
            update_values.append(data['brand_name'] if data['brand_name'] else None)
        
        if 'logo_url' in data:
            update_fields.append('logo_url = %s')
            update_values.append(data['logo_url'] if data['logo_url'] else None)
        
        if 'password' in data and data['password']:
            password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            update_fields.append('password = %s')
            update_values.append(password_hash)
        
        if not update_fields:
            return jsonify({'error': 'ไม่มีข้อมูลที่ต้องการอัพเดท'}), 400
        
        update_values.append(user_id)
        cursor.execute(f'''
            UPDATE users SET {', '.join(update_fields)}
            WHERE id = %s
        ''', update_values)
        
        conn.commit()
        
        # Fetch updated user
        cursor.execute('''
            SELECT u.id, u.full_name, u.username, r.name as role, rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.id = %s
        ''', (user_id,))
        
        updated_user = dict(cursor.fetchone())
        
        return jsonify({
            'message': 'อัพเดทผู้ใช้สำเร็จ',
            'user': updated_user
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists
        cursor.execute('SELECT id FROM users WHERE id = %s', (user_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        
        return jsonify({'message': 'ลบผู้ใช้สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== BRAND MANAGEMENT ROUTES ====================

@app.route('/api/brands', methods=['GET'])
@admin_required
def get_brands():
    """Get all brands"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT b.id, b.name, b.description, b.created_at,
                   COUNT(DISTINCT p.id) as product_count
            FROM brands b
            LEFT JOIN products p ON b.id = p.brand_id
            GROUP BY b.id, b.name, b.description, b.created_at
            ORDER BY b.name ASC
        ''')
        
        brands = [dict(row) for row in cursor.fetchall()]
        return jsonify(brands), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/brands', methods=['POST'])
@admin_required
def create_brand():
    """Create a new brand (Super Admin only)"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'เฉพาะ Super Admin เท่านั้นที่สามารถสร้างแบรนด์'}), 403
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'กรุณากรอกชื่อแบรนด์'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand already exists
        cursor.execute('SELECT id FROM brands WHERE name = %s', (data['name'],))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อแบรนด์นี้มีอยู่แล้ว'}), 400
        
        cursor.execute('''
            INSERT INTO brands (name, description)
            VALUES (%s, %s)
            RETURNING id, name, description, created_at
        ''', (data['name'], data.get('description', '')))
        
        brand = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(brand), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/brands/<int:brand_id>', methods=['PUT'])
@admin_required
def update_brand(brand_id):
    """Update a brand (Super Admin only)"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'เฉพาะ Super Admin เท่านั้นที่สามารถแก้ไขแบรนด์'}), 403
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'กรุณากรอกชื่อแบรนด์'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบแบรนด์'}), 404
        
        # Check for duplicate name
        cursor.execute('SELECT id FROM brands WHERE name = %s AND id != %s', (data['name'], brand_id))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อแบรนด์นี้มีอยู่แล้ว'}), 400
        
        cursor.execute('''
            UPDATE brands SET name = %s, description = %s
            WHERE id = %s
            RETURNING id, name, description, created_at
        ''', (data['name'], data.get('description', ''), brand_id))
        
        brand = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(brand), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/brands/<int:brand_id>', methods=['DELETE'])
@admin_required
def delete_brand(brand_id):
    """Delete a brand (Super Admin only, only if no products)"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'เฉพาะ Super Admin เท่านั้นที่สามารถลบแบรนด์'}), 403
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบแบรนด์'}), 404
        
        # Check if brand has products
        cursor.execute('SELECT COUNT(*) as count FROM products WHERE brand_id = %s', (brand_id,))
        count = cursor.fetchone()['count']
        if count > 0:
            return jsonify({'error': f'ไม่สามารถลบแบรนด์ที่มี {count} สินค้าอยู่ กรุณาย้ายหรือลบสินค้าก่อน'}), 400
        
        # Delete brand
        cursor.execute('DELETE FROM brands WHERE id = %s', (brand_id,))
        conn.commit()
        
        return jsonify({'message': 'ลบแบรนด์สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin-brand-access/<int:user_id>', methods=['GET'])
@admin_required
def get_admin_brands(user_id):
    """Get brands assigned to an admin user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT b.id, b.name
            FROM brands b
            JOIN admin_brand_access aba ON b.id = aba.brand_id
            WHERE aba.user_id = %s
            ORDER BY b.name ASC
        ''', (user_id,))
        
        brands = [dict(row) for row in cursor.fetchall()]
        return jsonify(brands), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin-brand-access/<int:user_id>', methods=['PUT'])
@admin_required
def update_admin_brands(user_id):
    """Update brands assigned to an admin user (Super Admin only)"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'เฉพาะ Super Admin เท่านั้นที่สามารถกำหนดแบรนด์'}), 403
    
    data = request.json
    if not data or 'brand_ids' not in data:
        return jsonify({'error': 'กรุณาเลือกแบรนด์'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists and is Assistant Admin
        cursor.execute('''
            SELECT u.id, r.name as role FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        # Delete existing assignments
        cursor.execute('DELETE FROM admin_brand_access WHERE user_id = %s', (user_id,))
        
        # Insert new assignments
        for brand_id in data['brand_ids']:
            cursor.execute('''
                INSERT INTO admin_brand_access (user_id, brand_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, brand_id) DO NOTHING
            ''', (user_id, brand_id))
        
        conn.commit()
        
        return jsonify({'message': 'กำหนดแบรนด์สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== CATEGORY MANAGEMENT ROUTES ====================

@app.route('/api/categories', methods=['GET'])
@admin_required
def get_categories():
    """Get all categories with hierarchy and product counts"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT c.id, c.name, c.parent_id, c.sort_order, c.created_at,
                   COUNT(pc.product_id) as product_count
            FROM categories c
            LEFT JOIN product_categories pc ON c.id = pc.category_id
            GROUP BY c.id, c.name, c.parent_id, c.sort_order, c.created_at
            ORDER BY c.parent_id NULLS FIRST, c.sort_order, c.name
        ''')
        
        categories = [dict(row) for row in cursor.fetchall()]
        return jsonify(categories), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/categories', methods=['POST'])
@admin_required
def create_category():
    """Create a new category"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'error': 'กรุณากรอกชื่อหมวดหมู่'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        parent_id = data.get('parent_id') if data.get('parent_id') else None
        sort_order = data.get('sort_order', 0)
        
        cursor.execute('''
            INSERT INTO categories (name, parent_id, sort_order)
            VALUES (%s, %s, %s)
            RETURNING id, name, parent_id, sort_order, created_at
        ''', (data['name'], parent_id, sort_order))
        
        category = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(category), 201
        
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({'error': 'ชื่อหมวดหมู่นี้มีอยู่แล้ว'}), 409
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/categories/<int:category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    """Update a category"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'error': 'กรุณากรอกชื่อหมวดหมู่'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        parent_id = data.get('parent_id') if data.get('parent_id') else None
        sort_order = data.get('sort_order', 0)
        
        cursor.execute('''
            UPDATE categories
            SET name = %s, parent_id = %s, sort_order = %s
            WHERE id = %s
            RETURNING id, name, parent_id, sort_order, created_at
        ''', (data['name'], parent_id, sort_order, category_id))
        
        category = cursor.fetchone()
        if not category:
            return jsonify({'error': 'ไม่พบหมวดหมู่'}), 404
        
        conn.commit()
        return jsonify(dict(category)), 200
        
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({'error': 'ชื่อหมวดหมู่นี้มีอยู่แล้ว'}), 409
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """Delete a category"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM categories WHERE id = %s RETURNING id', (category_id,))
        deleted = cursor.fetchone()
        
        if not deleted:
            return jsonify({'error': 'ไม่พบหมวดหมู่'}), 404
        
        conn.commit()
        return jsonify({'message': 'ลบหมวดหมู่สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PRODUCT MANAGEMENT ROUTES ====================

@app.route('/api/products', methods=['GET'])
@admin_required
def get_products():
    """Get all products with their basic information (filtered by brand for Assistant Admin)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_role = session.get('role')
        user_id = session.get('user_id')
        
        # Build query with brand info, price range and stock
        base_query = '''
            SELECT 
                p.id,
                p.name,
                p.parent_sku,
                p.description,
                p.size_chart_image_url,
                p.brand_id,
                b.name as brand_name,
                COALESCE(p.status, 'active') as status,
                p.created_at,
                COALESCE(p.low_stock_threshold, 5) as low_stock_threshold,
                COALESCE(p.is_featured, FALSE) as is_featured,
                COUNT(DISTINCT s.id) as sku_count,
                COALESCE(MIN(s.price), 0) as min_price,
                COALESCE(MAX(s.price), 0) as max_price,
                COALESCE(SUM(s.stock), 0) as total_stock,
                (
                    SELECT COUNT(*) FROM skus ss WHERE ss.product_id = p.id AND ss.stock = 0
                ) as out_of_stock_count,
                (
                    SELECT COUNT(*) FROM skus ss WHERE ss.product_id = p.id AND ss.stock > 0 AND ss.stock <= COALESCE(p.low_stock_threshold, 5)
                ) as low_stock_count,
                (
                    SELECT pi.image_url 
                    FROM product_images pi 
                    WHERE pi.product_id = p.id 
                    ORDER BY pi.sort_order ASC 
                    LIMIT 1
                ) as first_image_url
            FROM products p
            LEFT JOIN skus s ON p.id = s.product_id
            LEFT JOIN brands b ON p.brand_id = b.id
        '''
        
        # Filter by brand for Assistant Admin
        if user_role == 'Assistant Admin':
            base_query += '''
                WHERE p.brand_id IN (
                    SELECT brand_id FROM admin_brand_access WHERE user_id = %s
                )
            '''
            base_query += '''
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at, p.low_stock_threshold, p.is_featured
                ORDER BY p.created_at DESC
            '''
            cursor.execute(base_query, (user_id,))
        else:
            base_query += '''
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at, p.low_stock_threshold, p.is_featured
                ORDER BY p.created_at DESC
            '''
            cursor.execute(base_query)
        
        products = [dict(row) for row in cursor.fetchall()]
        
        # Fetch SKUs for each product (for collapsible display)
        for product in products:
            # Convert Decimal to float for JSON serialization (check is not None for zero values)
            if product.get('min_price') is not None:
                product['min_price'] = float(product['min_price'])
            if product.get('max_price') is not None:
                product['max_price'] = float(product['max_price'])
            if product.get('total_stock') is not None:
                product['total_stock'] = int(product['total_stock'])
            # Convert count fields to int for JSON serialization
            if product.get('out_of_stock_count') is not None:
                product['out_of_stock_count'] = int(product['out_of_stock_count'])
            if product.get('low_stock_count') is not None:
                product['low_stock_count'] = int(product['low_stock_count'])
            if product.get('low_stock_threshold') is not None:
                product['low_stock_threshold'] = int(product['low_stock_threshold'])
            
            cursor.execute('''
                SELECT 
                    s.id,
                    s.sku_code,
                    s.price::float as price,
                    s.stock::int as stock,
                    COALESCE(
                        STRING_AGG(o.name || ':' || ov.value, ' / ' ORDER BY o.id, ov.sort_order),
                        ''
                    ) as variant_name
                FROM skus s
                LEFT JOIN sku_values_map svm ON s.id = svm.sku_id
                LEFT JOIN option_values ov ON svm.option_value_id = ov.id
                LEFT JOIN options o ON ov.option_id = o.id
                WHERE s.product_id = %s
                GROUP BY s.id, s.sku_code, s.price, s.stock
                ORDER BY
                    CASE SUBSTRING(s.sku_code FROM '[^-]*$')
                        WHEN 'XS'       THEN 1
                        WHEN 'S'        THEN 2
                        WHEN 'M'        THEN 3
                        WHEN 'L'        THEN 4
                        WHEN 'XL'       THEN 5
                        WHEN '2XL'      THEN 6
                        WHEN '3XL'      THEN 7
                        WHEN '4XL'      THEN 8
                        WHEN '5XL'      THEN 9
                        WHEN 'FREESIZE' THEN 10
                        WHEN 'ONESIZE'  THEN 11
                        ELSE 99
                    END,
                    s.sku_code
            ''', (product['id'],))
            product['skus'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(products), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>', methods=['GET'])
@admin_required
def get_product(product_id):
    """Get detailed product information including options and SKUs"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get product basic info
        cursor.execute('SELECT * FROM products WHERE id = %s', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        product = dict(product)
        
        # Get product category
        cursor.execute('''
            SELECT category_id FROM product_categories
            WHERE product_id = %s
            LIMIT 1
        ''', (product_id,))
        category_row = cursor.fetchone()
        product['category_id'] = category_row['category_id'] if category_row else None
        
        # Get product images
        cursor.execute('''
            SELECT id, image_url, sort_order
            FROM product_images
            WHERE product_id = %s
            ORDER BY sort_order ASC
        ''', (product_id,))
        
        images = [dict(row) for row in cursor.fetchall()]
        product['images'] = images
        
        # Get options and their values
        cursor.execute('''
            SELECT 
                o.id,
                o.name,
                json_agg(
                    json_build_object(
                        'id', ov.id,
                        'value', ov.value,
                        'sort_order', ov.sort_order
                    ) ORDER BY ov.sort_order
                ) as values
            FROM options o
            LEFT JOIN option_values ov ON o.id = ov.option_id
            WHERE o.product_id = %s
            GROUP BY o.id, o.name
            ORDER BY o.id
        ''', (product_id,))
        
        options = [dict(row) for row in cursor.fetchall()]
        product['options'] = options
        
        # Get SKUs with their option values
        cursor.execute('''
            SELECT 
                s.id,
                s.sku_code,
                s.price,
                s.stock,
                s.cost_price,
                json_agg(
                    json_build_object(
                        'option_id', o.id,
                        'option_name', o.name,
                        'value_id', ov.id,
                        'value', ov.value
                    )
                ) as option_values
            FROM skus s
            LEFT JOIN sku_values_map svm ON s.id = svm.sku_id
            LEFT JOIN option_values ov ON svm.option_value_id = ov.id
            LEFT JOIN options o ON ov.option_id = o.id
            WHERE s.product_id = %s
            GROUP BY s.id, s.sku_code, s.price, s.stock, s.cost_price
            ORDER BY s.sku_code
        ''', (product_id,))
        
        skus = [dict(row) for row in cursor.fetchall()]
        product['skus'] = skus
        
        # Get default warehouse from sku_warehouse_stock (find the most common warehouse used by SKUs)
        cursor.execute('''
            SELECT sws.warehouse_id, COUNT(*) as count
            FROM sku_warehouse_stock sws
            JOIN skus s ON sws.sku_id = s.id
            WHERE s.product_id = %s AND sws.stock > 0
            GROUP BY sws.warehouse_id
            ORDER BY count DESC
            LIMIT 1
        ''', (product_id,))
        warehouse_row = cursor.fetchone()
        product['default_warehouse_id'] = warehouse_row['warehouse_id'] if warehouse_row else None
        
        return jsonify(product), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products', methods=['POST'])
@admin_required
def create_product():
    """Create a new product with options, values, and SKUs"""
    data = request.json
    
    # Validate required fields
    if not data or 'name' not in data or 'parent_sku' not in data:
        return jsonify({'error': 'กรุณากรอกชื่อสินค้าและรหัส SKU'}), 400
    
    # Validate brand_id is provided
    brand_id = data.get('brand_id')
    if not brand_id:
        return jsonify({'error': 'กรุณาเลือกแบรนด์'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบแบรนด์'}), 400
        
        # Check if parent_sku already exists
        cursor.execute('SELECT id FROM products WHERE parent_sku = %s', (data['parent_sku'],))
        if cursor.fetchone():
            return jsonify({'error': 'รหัส SKU หลักนี้มีอยู่แล้ว'}), 400
        
        # Insert product with brand_id, status, and shipping info
        status = data.get('status', 'active')
        low_stock = data.get('low_stock_threshold')
        if low_stock is not None and low_stock != '':
            low_stock = int(low_stock)
        else:
            low_stock = None
        cursor.execute('''
            INSERT INTO products (brand_id, name, parent_sku, description, bot_description,
                                  size_chart_image_url, status, keywords,
                                  weight, length, width, height, low_stock_threshold, size_chart_group_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (brand_id, data['name'], data['parent_sku'], data.get('description', ''),
              data.get('bot_description', '') or '',
              data.get('size_chart_image_url'), status,
              data.get('keywords', '') or '',
              data.get('weight'), data.get('length'), data.get('width'), data.get('height'),
              low_stock, data.get('size_chart_group_id') or None))
        
        product_id = cursor.fetchone()['id']
        
        # Insert product category if provided
        category_id = data.get('category_id')
        if category_id:
            cursor.execute('SELECT id FROM categories WHERE id = %s', (category_id,))
            if cursor.fetchone():
                cursor.execute('''
                    INSERT INTO product_categories (product_id, category_id)
                    VALUES (%s, %s)
                ''', (product_id, category_id))
        
        # Insert product images if provided
        image_urls = data.get('image_urls', [])
        for idx, image_url in enumerate(image_urls):
            cursor.execute('''
                INSERT INTO product_images (product_id, image_url, sort_order)
                VALUES (%s, %s, %s)
            ''', (product_id, image_url, idx))
        
        # Insert options and values
        options_data = data.get('options', [])
        options_order = []  # ordered list of option_ids as inserted
        option_value_text_map = {}  # {option_id: {value_text: value_id}}

        for option in options_data:
            if not option.get('name') or not option.get('values'):
                continue

            cursor.execute('''
                INSERT INTO options (product_id, name)
                VALUES (%s, %s)
                RETURNING id
            ''', (product_id, option['name']))

            option_id = cursor.fetchone()['id']
            options_order.append(option_id)
            option_value_text_map[option_id] = {}

            for idx, value_data in enumerate(option['values']):
                cursor.execute('''
                    INSERT INTO option_values (option_id, value, sort_order)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (option_id, value_data['value'], value_data.get('sort_order', idx)))

                value_id = cursor.fetchone()['id']
                option_value_text_map[option_id][value_data['value']] = value_id

        # Insert SKUs if provided
        skus_data = data.get('skus', [])
        for sku_data in skus_data:
            if not sku_data.get('sku_code'):
                continue

            cursor.execute('''
                INSERT INTO skus (product_id, sku_code, price, stock, cost_price)
                VALUES (%s, %s, %s, 0, %s)
                RETURNING id
            ''', (
                product_id,
                sku_data['sku_code'],
                sku_data.get('price', 0),
                sku_data.get('cost_price')
            ))

            sku_id = cursor.fetchone()['id']

            value_ids_to_map = sku_data.get('option_value_ids') or []
            if not value_ids_to_map:
                variant_values = sku_data.get('variant_values', [])
                for j, val_text in enumerate(variant_values):
                    if j < len(options_order):
                        opt_id = options_order[j]
                        vid = option_value_text_map.get(opt_id, {}).get(val_text)
                        if vid:
                            value_ids_to_map.append(vid)

            for value_id in value_ids_to_map:
                cursor.execute('''
                    INSERT INTO sku_values_map (sku_id, option_value_id)
                    VALUES (%s, %s)
                ''', (sku_id, value_id))
        
        conn.commit()
        
        return jsonify({
            'message': 'สร้างสินค้าสำเร็จ',
            'product_id': product_id
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>/images/reorder', methods=['PUT'])
@admin_required
def reorder_product_images(product_id):
    """Reorder product images"""
    data = request.json
    
    if not data or 'image_ids' not in data:
        return jsonify({'error': 'ไม่ได้เลือกรูปภาพ'}), 400
    
    image_ids = data['image_ids']
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Update sort_order for each image
        for idx, image_id in enumerate(image_ids):
            cursor.execute('''
                UPDATE product_images 
                SET sort_order = %s 
                WHERE id = %s AND product_id = %s
            ''', (idx, image_id, product_id))
        
        conn.commit()
        
        return jsonify({'message': 'จัดเรียงรูปภาพสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    """Update an existing product with options, values, and SKUs using diff-based approach.
    This preserves sku_id to maintain referential integrity with order_items."""
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'กรุณากรอกชื่อ'}), 400
    
    brand_id = data.get('brand_id')
    if not brand_id:
        return jsonify({'error': 'กรุณาเลือกแบรนด์'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Validate brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบแบรนด์'}), 400
        
        # Validate product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Update basic product information including shipping info
        status = data.get('status', 'active')
        low_stock = data.get('low_stock_threshold')
        if low_stock is not None and low_stock != '':
            low_stock = int(low_stock)
        else:
            low_stock = None
        cursor.execute('''
            UPDATE products 
            SET brand_id = %s, name = %s, description = %s, bot_description = %s,
                size_chart_image_url = %s, status = %s, keywords = %s,
                weight = %s, length = %s, width = %s, height = %s, low_stock_threshold = %s,
                size_chart_group_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (brand_id, data['name'], data.get('description', ''), data.get('bot_description', '') or '',
              data.get('size_chart_image_url'), status, data.get('keywords', '') or '',
              data.get('weight'), data.get('length'), data.get('width'), data.get('height'),
              low_stock, data.get('size_chart_group_id') or None, product_id))
        
        # Update product category
        cursor.execute('DELETE FROM product_categories WHERE product_id = %s', (product_id,))
        category_id = data.get('category_id')
        if category_id:
            cursor.execute('SELECT id FROM categories WHERE id = %s', (category_id,))
            if cursor.fetchone():
                cursor.execute('INSERT INTO product_categories (product_id, category_id) VALUES (%s, %s)', (product_id, category_id))
        
        # ========== DIFF-BASED OPTIONS UPDATE ==========
        # Get existing options with their values
        cursor.execute('''
            SELECT o.id as option_id, o.name as option_name, 
                   ov.id as value_id, ov.value as value_name, ov.sort_order
            FROM options o
            LEFT JOIN option_values ov ON o.id = ov.option_id
            WHERE o.product_id = %s
            ORDER BY o.id, ov.sort_order
        ''', (product_id,))
        existing_options_rows = cursor.fetchall()
        
        # Build existing options map: {option_name: {option_id, values: {value_name: value_id}}}
        existing_options = {}
        for row in existing_options_rows:
            opt_name = row['option_name']
            if opt_name not in existing_options:
                existing_options[opt_name] = {'option_id': row['option_id'], 'values': {}}
            if row['value_id']:
                existing_options[opt_name]['values'][row['value_name']] = row['value_id']
        
        # Process new options data
        options_data = data.get('options', [])
        new_option_names = set()
        options_map = []  # For SKU mapping later
        
        for option in options_data:
            if not option.get('name') or not option.get('values'):
                continue
            
            option_name = option['name']
            new_option_names.add(option_name)
            value_to_id = {}
            
            if option_name in existing_options:
                # Option exists - update values
                option_id = existing_options[option_name]['option_id']
                existing_values = existing_options[option_name]['values']
                new_value_names = set()
                
                for idx, value_data in enumerate(option['values']):
                    value_name = value_data['value']
                    new_value_names.add(value_name)
                    
                    if value_name in existing_values:
                        # Value exists - just update sort_order
                        value_id = existing_values[value_name]
                        cursor.execute('UPDATE option_values SET sort_order = %s WHERE id = %s', 
                                      (value_data.get('sort_order', idx), value_id))
                        value_to_id[value_name] = value_id
                    else:
                        # New value - insert
                        cursor.execute('''
                            INSERT INTO option_values (option_id, value, sort_order)
                            VALUES (%s, %s, %s) RETURNING id
                        ''', (option_id, value_name, value_data.get('sort_order', idx)))
                        value_id = cursor.fetchone()['id']
                        value_to_id[value_name] = value_id
                
                # Delete removed values (only if not referenced by SKUs with orders)
                for old_value_name, old_value_id in existing_values.items():
                    if old_value_name not in new_value_names:
                        cursor.execute('DELETE FROM option_values WHERE id = %s', (old_value_id,))
            else:
                # New option - insert
                cursor.execute('INSERT INTO options (product_id, name) VALUES (%s, %s) RETURNING id',
                              (product_id, option_name))
                option_id = cursor.fetchone()['id']
                
                for idx, value_data in enumerate(option['values']):
                    value_name = value_data['value']
                    cursor.execute('''
                        INSERT INTO option_values (option_id, value, sort_order)
                        VALUES (%s, %s, %s) RETURNING id
                    ''', (option_id, value_name, value_data.get('sort_order', idx)))
                    value_id = cursor.fetchone()['id']
                    value_to_id[value_name] = value_id
            
            options_map.append({'name': option_name, 'value_to_id': value_to_id})
        
        # Delete removed options
        for old_option_name in existing_options:
            if old_option_name not in new_option_names:
                cursor.execute('DELETE FROM options WHERE id = %s', 
                              (existing_options[old_option_name]['option_id'],))
        
        # ========== DIFF-BASED SKUs UPDATE ==========
        # Get existing SKUs including cost_price
        cursor.execute('SELECT id, sku_code, price, stock, cost_price FROM skus WHERE product_id = %s', (product_id,))
        existing_skus = {row['sku_code']: row for row in cursor.fetchall()}
        
        # Get SKU codes that have order references (cannot be deleted)
        cursor.execute('''
            SELECT DISTINCT s.sku_code 
            FROM skus s
            INNER JOIN order_items oi ON s.id = oi.sku_id
            WHERE s.product_id = %s
        ''', (product_id,))
        protected_sku_codes = {row['sku_code'] for row in cursor.fetchall()}
        
        # Process new SKUs
        skus_data = data.get('skus', [])
        new_sku_codes = set()
        
        for sku_data in skus_data:
            sku_code = sku_data.get('sku_code')
            if not sku_code:
                continue
            
            new_sku_codes.add(sku_code)
            new_price = sku_data.get('price', 0)
            new_cost_price = sku_data.get('cost_price')
            variant_values = sku_data.get('variant_values', [])
            
            if sku_code in existing_skus:
                # SKU exists - UPDATE price and cost_price only (preserve sku_id and stock)
                # Stock must be changed through Stock Adjustment page for audit trail
                sku_id = existing_skus[sku_code]['id']
                cursor.execute('''
                    UPDATE skus SET price = %s, cost_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_price, new_cost_price, sku_id))
                
                # Update sku_values_map if variant_values changed
                cursor.execute('DELETE FROM sku_values_map WHERE sku_id = %s', (sku_id,))
                if len(variant_values) == len(options_map):
                    for idx, value_name in enumerate(variant_values):
                        if value_name in options_map[idx]['value_to_id']:
                            value_id = options_map[idx]['value_to_id'][value_name]
                            cursor.execute('INSERT INTO sku_values_map (sku_id, option_value_id) VALUES (%s, %s)',
                                          (sku_id, value_id))
            else:
                # New SKU - INSERT with stock=0 (use Stock Adjustment to add inventory)
                cursor.execute('''
                    INSERT INTO skus (product_id, sku_code, price, stock, cost_price)
                    VALUES (%s, %s, %s, 0, %s) RETURNING id
                ''', (product_id, sku_code, new_price, new_cost_price))
                sku_id = cursor.fetchone()['id']
                
                # Map to option values
                if len(variant_values) == len(options_map):
                    for idx, value_name in enumerate(variant_values):
                        if value_name in options_map[idx]['value_to_id']:
                            value_id = options_map[idx]['value_to_id'][value_name]
                            cursor.execute('INSERT INTO sku_values_map (sku_id, option_value_id) VALUES (%s, %s)',
                                          (sku_id, value_id))
        
        # Delete removed SKUs (only if not referenced by orders)
        for old_sku_code, old_sku in existing_skus.items():
            if old_sku_code not in new_sku_codes:
                if old_sku_code in protected_sku_codes:
                    # Cannot delete - mark as inactive by setting stock to 0
                    cursor.execute('UPDATE skus SET stock = 0, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
                                  (old_sku['id'],))
                else:
                    # Safe to delete
                    cursor.execute('DELETE FROM skus WHERE id = %s', (old_sku['id'],))
        
        # ========== DIFF-BASED IMAGES UPDATE ==========
        cursor.execute('SELECT id, image_url FROM product_images WHERE product_id = %s', (product_id,))
        existing_images = {row['image_url']: row['id'] for row in cursor.fetchall()}
        
        new_image_urls = data.get('image_urls', [])
        new_image_set = set(new_image_urls)
        
        # Collect removed images for Object Storage cleanup
        images_to_delete_from_storage = []
        
        # Delete removed images from database
        for old_url, old_id in existing_images.items():
            if old_url not in new_image_set:
                cursor.execute('DELETE FROM product_images WHERE id = %s', (old_id,))
                if old_url and old_url.startswith('/storage/'):
                    images_to_delete_from_storage.append(old_url.replace('/storage/', ''))
        
        # Check if size chart was changed/removed
        cursor.execute('SELECT size_chart_image_url FROM products WHERE id = %s', (product_id,))
        old_product = cursor.fetchone()
        old_size_chart = old_product['size_chart_image_url'] if old_product else None
        new_size_chart = data.get('size_chart_image_url')
        if old_size_chart and old_size_chart != new_size_chart and old_size_chart.startswith('/storage/'):
            images_to_delete_from_storage.append(old_size_chart.replace('/storage/', ''))
        
        # Insert or update images with correct sort_order
        for idx, image_url in enumerate(new_image_urls):
            if image_url in existing_images:
                cursor.execute('UPDATE product_images SET sort_order = %s WHERE id = %s',
                              (idx, existing_images[image_url]))
            else:
                cursor.execute('INSERT INTO product_images (product_id, image_url, sort_order) VALUES (%s, %s, %s)',
                              (product_id, image_url, idx))
        
        conn.commit()
        
        # Delete removed images from Object Storage (after successful DB commit)
        if images_to_delete_from_storage:
            try:
                storage_client = Client()
                for filename in images_to_delete_from_storage:
                    try:
                        storage_client.delete(filename)
                    except Exception:
                        pass  # Ignore individual file deletion errors
            except Exception:
                pass  # Don't fail the request if storage cleanup fails
        
        return jsonify({
            'message': 'อัพเดทสินค้าสำเร็จ',
            'product_id': product_id
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>/status', methods=['PATCH'])
@admin_required
def update_product_status(product_id):
    """Quick update product status"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['active', 'inactive', 'draft']:
            return jsonify({'error': 'สถานะไม่ถูกต้อง กรุณาเลือก: ใช้งาน, ไม่ใช้งาน หรือ ฉบับร่าง'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE products SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        ''', (status, product_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        conn.commit()
        return jsonify({'message': 'อัพเดทสถานะสำเร็จ', 'status': status}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>/featured', methods=['PATCH'])
@admin_required
def toggle_product_featured(product_id):
    """Toggle is_featured flag on a product"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        is_featured = bool(data.get('is_featured', False))
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE products SET is_featured = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s RETURNING id
        ''', (is_featured, product_id))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        conn.commit()
        return jsonify({'message': 'อัพเดทสำเร็จ', 'is_featured': is_featured}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    """Delete a product and all related data (cascade), including images from Object Storage"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists and get size_chart_image_url
        cursor.execute('SELECT id, size_chart_image_url FROM products WHERE id = %s', (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Get all product images before deletion
        cursor.execute('SELECT image_url FROM product_images WHERE product_id = %s', (product_id,))
        product_images = cursor.fetchall()
        
        # Collect all image URLs to delete from Object Storage
        images_to_delete = []
        for img in product_images:
            if img['image_url'] and img['image_url'].startswith('/storage/'):
                images_to_delete.append(img['image_url'].replace('/storage/', ''))
        
        # Add size chart image if exists
        if product['size_chart_image_url'] and product['size_chart_image_url'].startswith('/storage/'):
            images_to_delete.append(product['size_chart_image_url'].replace('/storage/', ''))
        
        # Delete product from database (cascade will handle related data)
        cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
        conn.commit()
        
        # Delete images from Object Storage (after successful DB deletion)
        if images_to_delete:
            try:
                storage_client = Client()
                for filename in images_to_delete:
                    try:
                        storage_client.delete(filename)
                    except Exception:
                        pass  # Ignore individual file deletion errors
            except Exception:
                pass  # Don't fail the request if storage cleanup fails
        
        return jsonify({'message': 'ลบสินค้าสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/skus/<int:sku_id>', methods=['PATCH'])
@admin_required
def update_sku(sku_id):
    """Update SKU price and/or stock (inline editing)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
        
        updates = []
        params = []
        
        if 'price' in data:
            try:
                price = round(float(data['price']), 2)
                if price < 0:
                    return jsonify({'error': 'ราคาต้องไม่ติดลบ'}), 400
                updates.append('price = %s')
                params.append(price)
            except (ValueError, TypeError):
                return jsonify({'error': 'ราคาไม่ถูกต้อง'}), 400
        
        # Stock updates disabled - silently ignore to preserve price edit functionality
        # Stock changes must go through Stock Adjustment page for audit trail
        
        if not updates:
            return jsonify({'error': 'ไม่มีข้อมูลที่ต้องการอัพเดท'}), 400
        
        params.append(sku_id)
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute(f'''
            UPDATE skus SET {', '.join(updates)}
            WHERE id = %s
            RETURNING id
        ''', tuple(params))
        
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบ SKU'}), 404
        
        conn.commit()
        return jsonify({'message': 'อัพเดท SKU สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PRODUCT CUSTOMIZATION ROUTES ====================

@app.route('/api/products/<int:product_id>/customizations', methods=['GET'])
@admin_required
def get_product_customizations(product_id):
    """Get all customizations for a product"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, is_required, allow_multiple, sort_order
            FROM product_customizations
            WHERE product_id = %s
            ORDER BY sort_order, id
        ''', (product_id,))
        
        customizations = []
        for row in cursor.fetchall():
            customization = dict(row)
            
            cursor.execute('''
                SELECT id, label, extra_price, sort_order
                FROM customization_choices
                WHERE customization_id = %s
                ORDER BY sort_order, id
            ''', (customization['id'],))
            
            customization['choices'] = [dict(c) for c in cursor.fetchall()]
            for choice in customization['choices']:
                if choice.get('extra_price'):
                    choice['extra_price'] = float(choice['extra_price'])
            customizations.append(customization)
        
        return jsonify(customizations), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>/customizations', methods=['POST'])
@admin_required
def create_product_customization(product_id):
    """Create a new customization group for a product"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'error': 'กรุณากรอกชื่อตัวเลือก'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO product_customizations (product_id, name, is_required, allow_multiple, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, is_required, allow_multiple, sort_order
        ''', (
            product_id,
            data['name'],
            data.get('is_required', False),
            data.get('allow_multiple', False),
            data.get('sort_order', 0)
        ))
        
        customization = dict(cursor.fetchone())
        
        choices = data.get('choices', [])
        customization['choices'] = []
        
        for idx, choice in enumerate(choices):
            if not choice.get('label'):
                continue
            cursor.execute('''
                INSERT INTO customization_choices (customization_id, label, extra_price, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id, label, extra_price, sort_order
            ''', (
                customization['id'],
                choice['label'],
                choice.get('extra_price', 0),
                choice.get('sort_order', idx)
            ))
            choice_data = dict(cursor.fetchone())
            if choice_data.get('extra_price'):
                choice_data['extra_price'] = float(choice_data['extra_price'])
            customization['choices'].append(choice_data)
        
        conn.commit()
        return jsonify(customization), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/customizations/<int:customization_id>', methods=['PUT'])
@admin_required
def update_customization(customization_id):
    """Update a customization group"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'error': 'กรุณากรอกชื่อตัวเลือก'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE product_customizations
            SET name = %s, is_required = %s, allow_multiple = %s, sort_order = %s
            WHERE id = %s
            RETURNING id, product_id, name, is_required, allow_multiple, sort_order
        ''', (
            data['name'],
            data.get('is_required', False),
            data.get('allow_multiple', False),
            data.get('sort_order', 0),
            customization_id
        ))
        
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'ไม่พบตัวเลือก'}), 404
        
        customization = dict(result)
        
        cursor.execute('DELETE FROM customization_choices WHERE customization_id = %s', (customization_id,))
        
        choices = data.get('choices', [])
        customization['choices'] = []
        
        for idx, choice in enumerate(choices):
            if not choice.get('label'):
                continue
            cursor.execute('''
                INSERT INTO customization_choices (customization_id, label, extra_price, sort_order)
                VALUES (%s, %s, %s, %s)
                RETURNING id, label, extra_price, sort_order
            ''', (
                customization_id,
                choice['label'],
                choice.get('extra_price', 0),
                choice.get('sort_order', idx)
            ))
            choice_data = dict(cursor.fetchone())
            if choice_data.get('extra_price'):
                choice_data['extra_price'] = float(choice_data['extra_price'])
            customization['choices'].append(choice_data)
        
        conn.commit()
        return jsonify(customization), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/customizations/<int:customization_id>', methods=['DELETE'])
@admin_required
def delete_customization(customization_id):
    """Delete a customization group"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM product_customizations WHERE id = %s RETURNING id', (customization_id,))
        
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบตัวเลือก'}), 404
        
        conn.commit()
        return jsonify({'message': 'ลบตัวเลือกสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_single_file():
    """Upload a single file to Replit Object Storage"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
        
        # Allowed extensions
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'ประเภทไฟล์ไม่ถูกต้อง'}), 400
        
        # Initialize Object Storage client
        storage_client = Client()
        import uuid
        
        # Generate unique filename
        unique_filename = f"settings/{uuid.uuid4()}.{file_ext}"
        
        # Upload to Object Storage
        storage_client.upload_from_bytes(unique_filename, file.read())
        
        # Return image URL
        image_url = f"/storage/{unique_filename}"
        
        return jsonify({
            'message': 'อัพโหลดไฟล์สำเร็จ',
            'url': image_url
        }), 200
        
    except Exception as e:
        return handle_error(e)

@app.route('/api/upload-images', methods=['POST'])
@admin_required
def upload_images():
    """Upload multiple product images to Replit Object Storage"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'ไม่ได้เลือกรูปภาพ'}), 400
        
        files = request.files.getlist('images')
        
        if not files or len(files) == 0:
            return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
        
        # Allowed extensions
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        uploaded_images = []
        
        # Initialize Object Storage client
        storage_client = Client()
        import uuid
        
        for file in files:
            if file.filename == '':
                continue
            
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            if file_ext not in allowed_extensions:
                continue
            
            # Generate unique filename
            unique_filename = f"products/{uuid.uuid4()}.{file_ext}"
            
            # Upload to Object Storage
            storage_client.upload_from_bytes(unique_filename, file.read())
            
            # Store image URL
            image_url = f"/storage/{unique_filename}"
            uploaded_images.append(image_url)
        
        if len(uploaded_images) == 0:
            return jsonify({'error': 'ไม่มีรูปภาพที่ถูกต้อง'}), 400
        
        return jsonify({
            'message': f'อัพโหลดรูปภาพสำเร็จ {len(uploaded_images)} รูป',
            'image_urls': uploaded_images
        }), 200
        
    except Exception as e:
        return handle_error(e)

@app.route('/storage/<path:filename>')
def serve_image(filename):
    """Serve images from Object Storage"""
    try:
        storage_client = Client()
        image_data = storage_client.download_as_bytes(filename)
        
        # Determine content type
        content_type = 'image/jpeg'
        if filename.endswith('.png'):
            content_type = 'image/png'
        elif filename.endswith('.gif'):
            content_type = 'image/gif'
        elif filename.endswith('.webp'):
            content_type = 'image/webp'
        
        from io import BytesIO
        return send_file(BytesIO(image_data), mimetype=content_type)
        
    except Exception as e:
        return jsonify({'error': 'ไม่พบรูปภาพ'}), 404

# ==================== RESELLER TIER PRICING ENDPOINTS ====================

@app.route('/api/products/<int:product_id>/tier-pricing', methods=['GET'])
@login_required
def get_product_tier_pricing(product_id):
    """Get tier pricing for a specific product"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Get tier pricing
        cursor.execute('''
            SELECT ptp.id, ptp.tier_id, rt.name as tier_name, rt.level_rank,
                   ptp.discount_percent
            FROM product_tier_pricing ptp
            JOIN reseller_tiers rt ON rt.id = ptp.tier_id
            WHERE ptp.product_id = %s
            ORDER BY rt.level_rank ASC
        ''', (product_id,))
        
        pricing = cursor.fetchall()
        result = []
        for p in pricing:
            p_dict = dict(p)
            if p_dict.get('discount_percent'):
                p_dict['discount_percent'] = float(p_dict['discount_percent'])
            result.append(p_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/products/<int:product_id>/tier-pricing', methods=['POST', 'PUT'])
@admin_required
def save_product_tier_pricing(product_id):
    """Save tier pricing for a product (all tiers required)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        if not data or 'pricing' not in data:
            return jsonify({'error': 'ไม่ได้กรอกข้อมูลราคา'}), 400
        
        pricing_data = data['pricing']
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Get all tiers
        cursor.execute('SELECT id, name FROM reseller_tiers ORDER BY level_rank')
        tiers = cursor.fetchall()
        
        # Validate all tiers have pricing
        tier_ids_required = set(t['id'] for t in tiers)
        tier_ids_provided = set(p['tier_id'] for p in pricing_data if p.get('tier_id'))
        
        if tier_ids_required != tier_ids_provided:
            missing = tier_ids_required - tier_ids_provided
            cursor.execute('SELECT name FROM reseller_tiers WHERE id = ANY(%s)', (list(missing),))
            missing_names = [r['name'] for r in cursor.fetchall()]
            return jsonify({'error': f'Missing pricing for tiers: {", ".join(missing_names)}'}), 400
        
        # Delete existing pricing
        cursor.execute('DELETE FROM product_tier_pricing WHERE product_id = %s', (product_id,))
        
        # Insert new pricing
        for p in pricing_data:
            discount = p.get('discount_percent', 0)
            if discount is None or discount < 0:
                discount = 0
            if discount > 100:
                discount = 100
                
            cursor.execute('''
                INSERT INTO product_tier_pricing (product_id, tier_id, discount_percent)
                VALUES (%s, %s, %s)
            ''', (product_id, p['tier_id'], discount))
        
        conn.commit()
        
        # Return updated pricing
        cursor.execute('''
            SELECT ptp.id, ptp.tier_id, rt.name as tier_name, rt.level_rank,
                   ptp.discount_percent
            FROM product_tier_pricing ptp
            JOIN reseller_tiers rt ON rt.id = ptp.tier_id
            WHERE ptp.product_id = %s
            ORDER BY rt.level_rank ASC
        ''', (product_id,))
        
        pricing = cursor.fetchall()
        result = []
        for p in pricing:
            p_dict = dict(p)
            if p_dict.get('discount_percent'):
                p_dict['discount_percent'] = float(p_dict['discount_percent'])
            result.append(p_dict)
        
        return jsonify({
            'message': 'บันทึกราคาตามระดับสำเร็จ',
            'pricing': result
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>/tier-override', methods=['PATCH'])
@admin_required
def update_user_tier_override(user_id):
    """Update user tier with manual override option"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists and is a reseller
        cursor.execute('''
            SELECT u.id, r.name as role_name 
            FROM users u 
            JOIN roles r ON r.id = u.role_id 
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        if user['role_name'] != 'Reseller':
            return jsonify({'error': 'ผู้ใช้ไม่ใช่สมาชิก'}), 400
        
        tier_id = data.get('reseller_tier_id')
        manual_override = data.get('tier_manual_override', False)
        
        if tier_id:
            # Verify tier exists
            cursor.execute('SELECT id FROM reseller_tiers WHERE id = %s', (tier_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'ไม่พบระดับสมาชิก'}), 404
        
        cursor.execute('''
            UPDATE users 
            SET reseller_tier_id = %s, tier_manual_override = %s
            WHERE id = %s
            RETURNING id, reseller_tier_id, tier_manual_override
        ''', (tier_id, manual_override, user_id))
        
        updated = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify({
            'message': 'อัพเดทระดับผู้ใช้สำเร็จ',
            'user': updated
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/admin/tier-settings')
@admin_required
def tier_settings_page():
    """Tier settings management page"""
    return render_template('tier_settings.html')

@app.route('/api/reseller-tiers/<int:tier_id>', methods=['PUT'])
@admin_required
def update_reseller_tier(tier_id):
    """Update reseller tier settings (upgrade_threshold, description)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM reseller_tiers WHERE id = %s', (tier_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบระดับสมาชิก'}), 404
        
        upgrade_threshold = data.get('upgrade_threshold', 0)
        description = data.get('description', '')
        
        cursor.execute('''
            UPDATE reseller_tiers 
            SET upgrade_threshold = %s, description = %s
            WHERE id = %s
            RETURNING id, name, level_rank, upgrade_threshold, description, is_manual_only
        ''', (upgrade_threshold, description, tier_id))
        
        updated = dict(cursor.fetchone())
        if updated.get('upgrade_threshold'):
            updated['upgrade_threshold'] = float(updated['upgrade_threshold'])
        conn.commit()
        
        return jsonify({
            'message': 'อัพเดทระดับสมาชิกสำเร็จ',
            'tier': updated
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-tiers/bulk', methods=['PUT'])
@admin_required
def update_reseller_tiers_bulk():
    """Bulk update reseller tier thresholds"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        tiers = data.get('tiers', [])
        
        if not tiers:
            return jsonify({'error': 'No tiers provided'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        updated_tiers = []
        for tier_data in tiers:
            tier_id = tier_data.get('id')
            upgrade_threshold = tier_data.get('upgrade_threshold', 0)
            description = tier_data.get('description', '')
            
            cursor.execute('''
                UPDATE reseller_tiers 
                SET upgrade_threshold = %s, description = %s
                WHERE id = %s
                RETURNING id, name, level_rank, upgrade_threshold, description, is_manual_only
            ''', (upgrade_threshold, description, tier_id))
            
            result = cursor.fetchone()
            if result:
                tier_dict = dict(result)
                if tier_dict.get('upgrade_threshold'):
                    tier_dict['upgrade_threshold'] = float(tier_dict['upgrade_threshold'])
                updated_tiers.append(tier_dict)
        
        conn.commit()
        
        return jsonify({
            'message': 'อัพเดทระดับสมาชิกสำเร็จ',
            'tiers': updated_tiers
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/<int:user_id>/add-purchase', methods=['POST'])
@admin_required
def add_user_purchase(user_id):
    """Add purchase amount to user's total and check for tier upgrade"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        amount = data.get('amount', 0)
        
        if amount <= 0:
            return jsonify({'error': 'Amount must be positive'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT u.id, u.total_purchases, u.reseller_tier_id, u.tier_manual_override, r.name as role_name
            FROM users u 
            JOIN roles r ON r.id = u.role_id 
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        if user['role_name'] != 'Reseller':
            return jsonify({'error': 'ผู้ใช้ไม่ใช่สมาชิก'}), 400
        
        new_total = float(user['total_purchases'] or 0) + float(amount)
        
        cursor.execute('''
            UPDATE users SET total_purchases = %s WHERE id = %s
        ''', (new_total, user_id))
        
        tier_upgraded = False
        new_tier_name = None
        
        if not user['tier_manual_override']:
            cursor.execute('''
                SELECT id, name, upgrade_threshold 
                FROM reseller_tiers 
                WHERE upgrade_threshold <= %s AND is_manual_only = FALSE
                ORDER BY level_rank DESC
                LIMIT 1
            ''', (new_total,))
            new_tier = cursor.fetchone()
            
            if new_tier and new_tier['id'] != user['reseller_tier_id']:
                cursor.execute('''
                    UPDATE users SET reseller_tier_id = %s WHERE id = %s
                ''', (new_tier['id'], user_id))
                tier_upgraded = True
                new_tier_name = new_tier['name']
        
        conn.commit()
        
        return jsonify({
            'message': 'เพิ่มยอดซื้อสำเร็จ',
            'new_total': new_total,
            'tier_upgraded': tier_upgraded,
            'new_tier': new_tier_name
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/users/check-tier-upgrades', methods=['POST'])
@admin_required
def check_all_tier_upgrades():
    """Check and upgrade tiers for all resellers based on their total purchases"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, upgrade_threshold, level_rank
            FROM reseller_tiers 
            WHERE is_manual_only = FALSE
            ORDER BY level_rank DESC
        ''')
        tiers = cursor.fetchall()
        
        cursor.execute('''
            SELECT u.id, u.username, u.total_purchases, u.reseller_tier_id, rt.name as current_tier
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE r.name = 'Reseller' AND u.tier_manual_override = FALSE
        ''')
        resellers = cursor.fetchall()
        
        upgraded_users = []
        
        for reseller in resellers:
            total = float(reseller['total_purchases'] or 0)
            
            new_tier = None
            for tier in tiers:
                threshold = float(tier['upgrade_threshold'] or 0)
                if total >= threshold:
                    new_tier = tier
                    break
            
            if new_tier and new_tier['id'] != reseller['reseller_tier_id']:
                cursor.execute('''
                    UPDATE users SET reseller_tier_id = %s WHERE id = %s
                ''', (new_tier['id'], reseller['id']))
                upgraded_users.append({
                    'user_id': reseller['id'],
                    'username': reseller['username'],
                    'old_tier': reseller['current_tier'],
                    'new_tier': new_tier['name'],
                    'total_purchases': total
                })
        
        conn.commit()
        
        return jsonify({
            'message': f'Checked {len(resellers)} resellers, upgraded {len(upgraded_users)}',
            'upgraded_users': upgraded_users
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/resellers', methods=['GET'])
@admin_required
def get_resellers_list():
    """Get all resellers with their tier and purchase info"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT u.id, u.username, u.full_name, u.total_purchases, 
                   u.tier_manual_override, rt.name as tier_name, rt.level_rank
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE r.name = 'Reseller'
            ORDER BY rt.level_rank DESC, u.total_purchases DESC
        ''')
        resellers = cursor.fetchall()
        
        result = []
        for r in resellers:
            r_dict = dict(r)
            if r_dict.get('total_purchases'):
                r_dict['total_purchases'] = float(r_dict['total_purchases'])
            result.append(r_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SHOPPING CART API ====================

def get_or_create_cart(user_id, cursor):
    """Get active cart for user or create one"""
    cursor.execute('''
        SELECT id FROM carts WHERE user_id = %s AND status = 'active'
    ''', (user_id,))
    cart = cursor.fetchone()
    
    if cart:
        return cart['id'] if isinstance(cart, dict) else cart[0]
    
    # Create new cart
    cursor.execute('''
        INSERT INTO carts (user_id, status) VALUES (%s, 'active')
        RETURNING id
    ''', (user_id,))
    return cursor.fetchone()[0]

@app.route('/api/cart', methods=['GET'])
@login_required
def get_cart():
    """Get current user's cart with items"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get or create cart
        cart_id = get_or_create_cart(user_id, cursor)
        conn.commit()
        
        # Get cart items with product info
        cursor.execute('''
            SELECT ci.id, ci.sku_id, ci.quantity, ci.unit_price, ci.tier_discount_percent,
                   ci.customization_data, ci.created_at,
                   s.sku_code, s.price as current_price, s.stock,
                   p.id as product_id, p.name as product_name, p.parent_sku, p.brand_id, p.weight,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM cart_items ci
            JOIN skus s ON s.id = ci.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE ci.cart_id = %s
            ORDER BY ci.created_at DESC
        ''', (cart_id,))
        
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            # Calculate discounted price
            unit_price = float(item['unit_price'] or 0)
            discount_pct = float(item['tier_discount_percent'] or 0)
            discounted_price = unit_price * (1 - discount_pct / 100)
            quantity = item['quantity']
            
            item['discounted_price'] = round(discounted_price, 2)
            item['subtotal'] = round(discounted_price * quantity, 2)
            item['unit_price'] = float(item['unit_price']) if item['unit_price'] else 0
            item['current_price'] = float(item['current_price']) if item['current_price'] else 0
            items.append(item)
        
        # Calculate totals
        total_amount = sum(float(item['unit_price']) * item['quantity'] for item in items)
        total_discount = sum((float(item['unit_price']) - item['discounted_price']) * item['quantity'] for item in items)
        final_amount = total_amount - total_discount
        
        return jsonify({
            'cart_id': cart_id,
            'items': items,
            'item_count': len(items),
            'total_quantity': sum(item['quantity'] for item in items),
            'total_amount': round(total_amount, 2),
            'total_discount': round(total_discount, 2),
            'final_amount': round(final_amount, 2)
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/cart/items', methods=['POST'])
@login_required
def add_to_cart():
    """Add item to cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        sku_id = data.get('sku_id')
        quantity = data.get('quantity', 1)
        customization_data = data.get('customization_data')
        
        if not sku_id:
            return jsonify({'error': 'SKU ID is required'}), 400
        
        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get SKU info
        cursor.execute('''
            SELECT s.id, s.price, s.stock, p.id as product_id
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = %s AND p.status = 'active'
        ''', (sku_id,))
        sku = cursor.fetchone()
        
        if not sku:
            return jsonify({'error': 'Product not found or not available'}), 404
        
        if sku['stock'] < quantity:
            return jsonify({'error': f'Not enough stock. Available: {sku["stock"]}'}), 400
        
        # Get user's tier discount for this product
        cursor.execute('''
            SELECT ptp.discount_percent
            FROM users u
            JOIN product_tier_pricing ptp ON ptp.tier_id = u.reseller_tier_id
            WHERE u.id = %s AND ptp.product_id = %s
        ''', (user_id, sku['product_id']))
        tier_pricing = cursor.fetchone()
        discount_percent = float(tier_pricing['discount_percent']) if tier_pricing else 0
        
        # Get or create cart
        cart_id = get_or_create_cart(user_id, cursor)
        
        # Check if item already in cart
        cursor.execute('''
            SELECT id, quantity FROM cart_items
            WHERE cart_id = %s AND sku_id = %s
        ''', (cart_id, sku_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update quantity
            new_quantity = existing['quantity'] + quantity
            if new_quantity > sku['stock']:
                return jsonify({'error': f'Total quantity exceeds stock. Available: {sku["stock"]}'}), 400
            
            cursor.execute('''
                UPDATE cart_items
                SET quantity = %s, unit_price = %s, tier_discount_percent = %s,
                    customization_data = COALESCE(%s, customization_data), updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id
            ''', (new_quantity, sku['price'], discount_percent, 
                  json.dumps(customization_data) if customization_data else None,
                  existing['id']))
        else:
            # Insert new item
            cursor.execute('''
                INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent, customization_data)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (cart_id, sku_id, quantity, sku['price'], discount_percent,
                  json.dumps(customization_data) if customization_data else None))
        
        conn.commit()
        
        return jsonify({'message': 'Added to cart successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/cart/migrate-guest', methods=['POST'])
@login_required
def migrate_guest_cart():
    """Migrate guest localStorage cart items into the logged-in member's server-side cart."""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json() or {}
        items = data.get('items') or []
        if not items:
            return jsonify({'migrated': 0}), 200

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cart_id = get_or_create_cart(user_id, cursor)

        migrated = 0
        for item in items:
            try:
                sku_id = int(item.get('skuId') or item.get('sku_id') or 0)
                quantity = max(1, int(item.get('qty') or item.get('quantity') or 1))
                if not sku_id:
                    continue

                cursor.execute('''
                    SELECT s.id, s.price, s.stock, p.id as product_id
                    FROM skus s JOIN products p ON p.id = s.product_id
                    WHERE s.id = %s AND p.status = 'active'
                ''', (sku_id,))
                sku = cursor.fetchone()
                if not sku:
                    continue

                cursor.execute('''
                    SELECT ptp.discount_percent
                    FROM users u
                    JOIN product_tier_pricing ptp ON ptp.tier_id = u.reseller_tier_id
                    WHERE u.id = %s AND ptp.product_id = %s
                ''', (user_id, sku['product_id']))
                tier_pricing = cursor.fetchone()
                discount_percent = float(tier_pricing['discount_percent']) if tier_pricing else 0

                cursor.execute('''
                    SELECT id, quantity FROM cart_items
                    WHERE cart_id = %s AND sku_id = %s
                ''', (cart_id, sku_id))
                existing = cursor.fetchone()

                if existing:
                    new_qty = min(existing['quantity'] + quantity, int(sku['stock']))
                    cursor.execute('''
                        UPDATE cart_items SET quantity = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (new_qty, existing['id']))
                else:
                    qty_to_add = min(quantity, int(sku['stock']))
                    if qty_to_add < 1:
                        continue
                    cursor.execute('''
                        INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent)
                        VALUES (%s, %s, %s, %s, %s)
                    ''', (cart_id, sku_id, qty_to_add, sku['price'], discount_percent))
                migrated += 1
            except Exception:
                continue

        conn.commit()
        return jsonify({'migrated': migrated}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/cart/items/<int:item_id>', methods=['PATCH'])
@login_required
def update_cart_item(item_id):
    """Update cart item quantity"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        quantity = data.get('quantity', 1)
        
        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify item belongs to user's cart
        cursor.execute('''
            SELECT ci.id, ci.sku_id, s.stock
            FROM cart_items ci
            JOIN carts c ON c.id = ci.cart_id
            JOIN skus s ON s.id = ci.sku_id
            WHERE ci.id = %s AND c.user_id = %s AND c.status = 'active'
        ''', (item_id, user_id))
        item = cursor.fetchone()
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        if quantity > item['stock']:
            return jsonify({'error': f'Not enough stock. Available: {item["stock"]}'}), 400
        
        cursor.execute('''
            UPDATE cart_items
            SET quantity = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (quantity, item_id))
        
        conn.commit()
        return jsonify({'message': 'Cart updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
@login_required
def remove_cart_item(item_id):
    """Remove item from cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verify and delete
        cursor.execute('''
            DELETE FROM cart_items
            WHERE id = %s AND cart_id IN (
                SELECT id FROM carts WHERE user_id = %s AND status = 'active'
            )
            RETURNING id
        ''', (item_id, user_id))
        
        if cursor.fetchone() is None:
            return jsonify({'error': 'Item not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Item removed from cart'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/cart/clear', methods=['DELETE'])
@login_required
def clear_cart():
    """Clear all items from cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM cart_items
            WHERE cart_id IN (
                SELECT id FROM carts WHERE user_id = %s AND status = 'active'
            )
        ''', (user_id,))
        
        conn.commit()
        return jsonify({'message': 'Cart cleared'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
