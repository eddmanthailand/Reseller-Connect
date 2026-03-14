from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, make_response
from authlib.integrations.flask_client import OAuth
from database import get_db
from utils import (login_required, admin_required, handle_error,
                   generate_csrf_token, validate_csrf_token, csrf_protect)
from blueprints.mail_utils import send_email, send_password_reset_email, log_activity
from blueprints.push_utils import send_push_notification, create_notification
import psycopg2.extras
import psycopg2
import bcrypt
import json, os, re, secrets, time
from datetime import datetime, timedelta
from replit.object_storage import Client

auth_bp = Blueprint('auth', __name__)

# ==================== GOOGLE OAUTH ====================
oauth = OAuth()
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@auth_bp.route('/test/google')
@auth_bp.route('/auth/google')
def test_google_login():
    """Redirect to Google OAuth"""
    redirect_uri = url_for('auth.google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@auth_bp.route('/auth/google/callback')
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


@auth_bp.route('/api/csrf-token', methods=['GET'])
def get_csrf_token():
    """Get CSRF token for authenticated requests"""
    return jsonify({'csrf_token': generate_csrf_token()}), 200

@auth_bp.route('/')
def index():
    """Show landing page for guests, redirect to dashboard if logged in"""
    if 'user_id' in session:
        return redirect('/dashboard')
    return render_template('landing_page.html')

@auth_bp.route('/login')
def login_page():
    """Render login page"""
    if 'user_id' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@auth_bp.route('/register')
def register_page():
    """QR code landing page - handles WebView browsers that block Google OAuth"""
    role = session.get('role')
    is_admin = role in ('Super Admin', 'Assistant Admin')
    if 'user_id' in session and not is_admin:
        return redirect('/dashboard')
    return render_template('register.html', preview_mode=is_admin)

@auth_bp.route('/become-reseller')
def fb_landing_page():
    """Landing page for Facebook Ads - separate from main registration"""
    if 'user_id' in session:
        return redirect('/dashboard')
    return render_template('fb_landing.html')

@auth_bp.route('/join')
def ad_landing_page():
    """New ad landing page for Google/Facebook ads"""
    if 'user_id' in session:
        return redirect('/dashboard')
    return render_template('ad_landing.html')

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard after login - routes based on role"""
    role = session.get('role')
    
    if role in ['Super Admin', 'Assistant Admin']:
        return redirect('/admin')
    elif role == 'Reseller':
        return render_template('reseller_spa.html')
    else:
        return redirect('/login')

@auth_bp.route('/admin')
@admin_required
def admin_management():
    """Render the admin dashboard"""
    return render_template('admin_dashboard.html')

@auth_bp.route('/chat')
@admin_required
def admin_chat_page():
    """Full-page chat interface for admins"""
    response = make_response(render_template('chat.html', user_name=session.get('full_name', ''), user_role=session.get('role', '')))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@auth_bp.route('/admin/products')
@admin_required
def product_list():
    """Redirect to admin dashboard (Product Management is now integrated)"""
    return redirect('/admin')

@auth_bp.route('/admin/products/create')
@admin_required
def product_create():
    """Render the product creation page"""
    return render_template('product_create.html')

@auth_bp.route('/admin/products/edit/<int:product_id>')
@admin_required
def product_edit(product_id):
    """Render the product edit page"""
    return render_template('product_edit.html')

@auth_bp.route('/admin/mto/products/create')
@admin_required
def mto_product_create():
    """Render the MTO product creation page"""
    return render_template('mto_product_create.html')

@auth_bp.route('/admin/mto/products/edit/<int:product_id>')
@admin_required
def mto_product_edit(product_id):
    """Render the MTO product edit page"""
    return render_template('mto_product_edit.html')

@auth_bp.route('/admin/brands')
@admin_required
def brand_management():
    """Render the brand management page"""
    return render_template('brand_management.html')

@auth_bp.route('/admin/categories')
@admin_required
def category_management():
    """Render the category management page"""
    return render_template('category_management.html')

@auth_bp.route('/api/public/products', methods=['GET'])
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

@auth_bp.route('/api/public/brands', methods=['GET'])
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

@auth_bp.route('/api/public/categories', methods=['GET'])
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

@auth_bp.route('/api/public/promotions', methods=['GET'])
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


@auth_bp.route('/api/public/product/<int:product_id>/skus', methods=['GET'])
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


@auth_bp.route('/catalog')
def public_catalog():
    """Public product catalog page - no login required"""
    return render_template('catalog.html')

@auth_bp.route('/api/public/tiers', methods=['GET'])
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

@auth_bp.route('/api/admin/catalog-bot/sessions', methods=['GET'])
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


@auth_bp.route('/api/admin/catalog-bot/sessions/<path:session_id>/messages', methods=['GET'])
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


@auth_bp.route('/api/admin/guest-chat-stats', methods=['GET'])
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


@auth_bp.route('/api/login', methods=['POST'])
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

@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    """Handle user logout (API call from dashboard)"""
    user_name = session.get('full_name', 'Unknown')
    user_id = session.get('user_id')
    log_activity('logout', 'auth', f"ออกจากระบบ: {user_name}", 
                target_type='user', target_id=user_id, target_name=user_name)
    session.clear()
    return jsonify({'message': 'ออกจากระบบสำเร็จ'}), 200

@auth_bp.route('/logout')
def logout_get():
    """Handle logout via direct URL visit — clears session and redirects to login"""
    session.clear()
    response = redirect('/login')
    response.delete_cookie('session')
    return response

from blueprints.mail_utils import (
    send_email, send_order_status_chat, send_order_notification_to_admin,
    send_order_status_email, send_low_stock_alert, send_password_reset_email, log_activity)
@auth_bp.route('/api/forgot-password', methods=['POST'])
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

@auth_bp.route('/reset-password')
def reset_password_page():
    """Render password reset page"""
    return render_template('reset_password.html')

@auth_bp.route('/api/reset-password', methods=['POST'])
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

@auth_bp.route('/api/me', methods=['GET'])
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

@auth_bp.route('/api/activity-logs', methods=['GET'])
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

@auth_bp.route('/api/activity-logs/categories', methods=['GET'])
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

@auth_bp.route('/api/admin/check-low-stock', methods=['POST'])
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

@auth_bp.route('/api/roles', methods=['GET'])
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

@auth_bp.route('/api/reseller-tiers', methods=['GET'])
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

@auth_bp.route('/api/reseller/stats', methods=['GET'])
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

@auth_bp.route('/api/users', methods=['GET'])
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

@auth_bp.route('/api/users', methods=['POST'])
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

@auth_bp.route('/api/users/<int:user_id>', methods=['GET'])
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

@auth_bp.route('/api/users/<int:user_id>', methods=['PUT'])
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

@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
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

