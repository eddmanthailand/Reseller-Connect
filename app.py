from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, make_response
from flask_cors import CORS
import psycopg2.extras
import bcrypt
from functools import wraps
from database import get_db, init_db
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from replit.object_storage import Client
from datetime import timedelta, datetime
import time
import secrets
from pywebpush import webpush, WebPushException

app = Flask(__name__)

# SESSION_SECRET is required for production security
session_secret = os.environ.get('SESSION_SECRET')
if not session_secret:
    raise RuntimeError(
        "SESSION_SECRET environment variable is required. "
        "Please configure a strong session secret for security."
    )
app.secret_key = session_secret

# Configure session cookie for iframe embedding (Replit preview)
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

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

# Authentication decorator
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
    """Render registration page for new resellers"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/become-reseller')
def fb_landing_page():
    """Landing page for Facebook Ads - separate from main registration"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('fb_landing.html')

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
    """Get products for public landing page (no login required)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT 
                p.id,
                p.name,
                b.name as brand_name,
                (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id LIMIT 1) as image_url,
                (SELECT MIN(s.price) FROM skus s WHERE s.product_id = p.id) as retail_price,
                COALESCE((SELECT SUM(s.stock) FROM skus s WHERE s.product_id = p.id), 0) as total_stock
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.status = 'active'
            ORDER BY p.created_at DESC
            LIMIT 8
        ''')
        products = cursor.fetchall()
        
        return jsonify({'products': products}), 200
    except Exception as e:
        print(f"Error fetching public products: {e}")
        return jsonify({'products': [], 'error': str(e)}), 200
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle user logout"""
    user_name = session.get('full_name', 'Unknown')
    user_id = session.get('user_id')
    log_activity('logout', 'auth', f"ออกจากระบบ: {user_name}", 
                target_type='user', target_id=user_id, target_name=user_name)
    session.clear()
    return jsonify({'message': 'ออกจากระบบสำเร็จ'}), 200

def send_email(to_email, subject, html_content):
    """Send email using Gmail SMTP"""
    try:
        gmail_user = 'cmidcoteam@gmail.com'
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_password:
            print("GMAIL_APP_PASSWORD not set")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"ระบบตัวแทนจำหน่าย <{gmail_user}>"
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_order_notification_to_admin(order_number, reseller_name, total_amount, item_count):
    """Send email notification to admin when new order is created"""
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8b5cf6;">📦 คำสั่งซื้อใหม่</h2>
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <p><strong>หมายเลขคำสั่งซื้อ:</strong> {order_number}</p>
            <p><strong>ตัวแทนจำหน่าย:</strong> {reseller_name}</p>
            <p><strong>จำนวนรายการ:</strong> {item_count} รายการ</p>
            <p><strong>ยอดรวม:</strong> ฿{total_amount:,.2f}</p>
        </div>
        <p>กรุณาเข้าสู่ระบบเพื่อตรวจสอบคำสั่งซื้อ</p>
    </div>
    '''
    send_email('cmidcoteam@gmail.com', f'[คำสั่งซื้อใหม่] {order_number} - {reseller_name}', html)

def send_order_status_email(to_email, reseller_name, order_number, status, message, extra_info=''):
    """Send order status update email to reseller"""
    status_colors = {
        'approved': '#22c55e',
        'request_new_slip': '#f59e0b',
        'shipped': '#3b82f6',
        'delivered': '#10b981',
        'cancelled': '#ef4444'
    }
    status_labels = {
        'approved': '✅ สลิปได้รับการยืนยัน',
        'request_new_slip': '⚠️ กรุณาอัปโหลดสลิปใหม่',
        'shipped': '🚚 จัดส่งสินค้าแล้ว',
        'delivered': '📦 ส่งถึงปลายทางแล้ว',
        'cancelled': '❌ คำสั่งซื้อถูกยกเลิก'
    }
    color = status_colors.get(status, '#6b7280')
    label = status_labels.get(status, 'อัปเดตสถานะ')
    
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: {color};">{label}</h2>
        <p>สวัสดี คุณ{reseller_name}</p>
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <p><strong>หมายเลขคำสั่งซื้อ:</strong> {order_number}</p>
            <p>{message}</p>
            {f'<p>{extra_info}</p>' if extra_info else ''}
        </div>
        <p>หากมีข้อสงสัย สามารถติดต่อได้ที่ Line: @cmidco</p>
        <p style="color: #666; margin-top: 20px;">ขอบคุณที่ใช้บริการ</p>
    </div>
    '''
    subject = f'[{label}] คำสั่งซื้อ {order_number}'
    send_email(to_email, subject, html)

def send_order_status_chat(reseller_id, order_number, status, extra_info=''):
    """Send order status update as chat message"""
    status_messages = {
        'slip_uploaded': f'🧾 คำสั่งซื้อ {order_number} อัปโหลดสลิปแล้ว รอตรวจสอบ',
        'approved': f'✅ คำสั่งซื้อ {order_number} สลิปได้รับการยืนยันแล้ว กำลังเตรียมจัดส่ง',
        'request_new_slip': f'⚠️ คำสั่งซื้อ {order_number} กรุณาอัปโหลดสลิปใหม่',
        'shipped': f'🚚 คำสั่งซื้อ {order_number} จัดส่งแล้ว',
        'delivered': f'📦 คำสั่งซื้อ {order_number} ส่งถึงปลายทางแล้ว',
        'cancelled': f'❌ คำสั่งซื้อ {order_number} ถูกยกเลิก',
        'shipping_issue': f'⚠️ คำสั่งซื้อ {order_number} มีปัญหาการจัดส่ง',
        'failed_delivery': f'❌ คำสั่งซื้อ {order_number} จัดส่งไม่สำเร็จ',
        'reship': f'🔄 คำสั่งซื้อ {order_number} กำลังจัดส่งใหม่'
    }
    message = status_messages.get(status, f'📋 คำสั่งซื้อ {order_number} อัปเดตสถานะ: {status}')
    if extra_info:
        message += f'\n{extra_info}'
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
        thread = cursor.fetchone()
        if not thread:
            cursor.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (reseller_id,))
            thread = cursor.fetchone()
        
        thread_id = thread['id']
        
        cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin') LIMIT 1")
        admin = cursor.fetchone()
        admin_id = admin['id'] if admin else 1
        
        cursor.execute('''
            INSERT INTO chat_messages (thread_id, sender_id, sender_type, content)
            VALUES (%s, %s, 'admin', %s) RETURNING id
        ''', (thread_id, admin_id, message))
        
        preview = message[:100]
        cursor.execute('''
            UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s, is_archived = FALSE
            WHERE id = %s
        ''', (preview, thread_id))
        
        conn.commit()
        
        send_push_notification(reseller_id, '📋 อัปเดตคำสั่งซื้อ', message[:100], url='/reseller#chat', tag=f'order-status-{order_number}')
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"[CHAT] Error sending order status chat: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def send_low_stock_alert(admin_email, products):
    """Send email alert for low stock products"""
    items_html = ''
    for p in products:
        items_html += f'<tr><td style="padding: 8px; border-bottom: 1px solid #eee;">{p["name"]}</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{p["sku_code"]}</td><td style="padding: 8px; border-bottom: 1px solid #eee; color: #ef4444;">{p["stock"]} ชิ้น</td></tr>'
    
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #f59e0b;">⚠️ แจ้งเตือนสินค้าใกล้หมด</h2>
        <p>สินค้าต่อไปนี้มีสต็อกต่ำกว่าที่กำหนด:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; text-align: left;">สินค้า</th>
                    <th style="padding: 10px; text-align: left;">รหัส SKU</th>
                    <th style="padding: 10px; text-align: left;">สต็อกคงเหลือ</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
        <p>กรุณาเติมสต็อกโดยเร็ว</p>
    </div>
    '''
    send_email(admin_email, f'[แจ้งเตือน] สินค้าใกล้หมด {len(products)} รายการ', html)

def send_password_reset_email(to_email, full_name, reset_token, reset_link):
    """Send password reset email"""
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8b5cf6;">🔐 รีเซ็ตรหัสผ่าน</h2>
        <p>สวัสดี คุณ{full_name}</p>
        <p>เราได้รับคำขอรีเซ็ตรหัสผ่านสำหรับบัญชีของคุณ</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background: linear-gradient(135deg, #8b5cf6, #ec4899); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">รีเซ็ตรหัสผ่าน</a>
        </div>
        <p style="color: #666;">ลิงก์นี้จะหมดอายุใน 1 ชั่วโมง</p>
        <p style="color: #666;">หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยอีเมลนี้</p>
        <hr style="margin: 20px 0; border: none; border-top: 1px solid #eee;">
        <p style="color: #999; font-size: 12px;">หากปุ่มไม่ทำงาน คัดลอกลิงก์นี้: {reset_link}</p>
    </div>
    '''
    send_email(to_email, 'รีเซ็ตรหัสผ่าน - ระบบตัวแทนจำหน่าย', html)

def log_activity(action_type, action_category, description, target_type=None, target_id=None, target_name=None, extra_data=None):
    """Log user activity to activity_logs table"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        user_id = session.get('user_id')
        user_name = session.get('full_name', 'ระบบ')
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:500] if request else None
        
        cursor.execute('''
            INSERT INTO activity_logs 
            (user_id, user_name, action_type, action_category, description, target_type, target_id, target_name, ip_address, user_agent, extra_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (user_id, user_name, action_type, action_category, description, 
              target_type, target_id, target_name, ip_address, user_agent, 
              json.dumps(extra_data) if extra_data else None))
        
        conn.commit()
    except Exception as e:
        print(f"Log activity error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/register', methods=['POST'])
def register_reseller():
    """Handle new reseller registration"""
    data = request.json
    
    required_fields = ['full_name', 'username', 'email', 'password', 'phone', 'line_id', 
                       'address', 'province', 'district', 'subdistrict', 'postal_code']
    
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': f'กรุณากรอก {field}'}), 400
    
    if len(data['password']) < 6:
        return jsonify({'error': 'รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM users WHERE username = %s', (data['username'],))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อผู้ใช้นี้ถูกใช้งานแล้ว'}), 400
        
        cursor.execute('SELECT id FROM users WHERE email = %s', (data['email'],))
        if cursor.fetchone():
            return jsonify({'error': 'อีเมลนี้ถูกใช้งานแล้ว'}), 400
        
        cursor.execute('SELECT id FROM reseller_applications WHERE username = %s AND status = %s', 
                      (data['username'], 'pending'))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อผู้ใช้นี้มีใบสมัครรอพิจารณาอยู่แล้ว'}), 400
        
        cursor.execute('SELECT id FROM reseller_applications WHERE email = %s AND status = %s', 
                      (data['email'], 'pending'))
        if cursor.fetchone():
            return jsonify({'error': 'อีเมลนี้มีใบสมัครรอพิจารณาอยู่แล้ว'}), 400
        
        password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        source = data.get('source', '')
        notes = data.get('notes', '')
        if source:
            notes = f"[source: {source}] {notes}".strip()
        
        cursor.execute('''
            INSERT INTO reseller_applications 
            (full_name, username, email, password_hash, phone, line_id, address, province, district, subdistrict, postal_code, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['full_name'], data['username'], data['email'], password_hash, 
              data['phone'], data['line_id'], data['address'], data['province'], 
              data['district'], data['subdistrict'], data['postal_code'], notes))
        
        application_id = cursor.fetchone()['id']
        conn.commit()
        
        admin_email_html = f'''
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #667eea;">มีใบสมัครตัวแทนจำหน่ายใหม่</h2>
            <p>มีผู้สมัครใหม่รอการอนุมัติ:</p>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>ชื่อ-นามสกุล:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['full_name']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Username:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['username']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Email:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['email']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>เบอร์โทร:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['phone']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>Line ID:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['line_id']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>จังหวัด:</strong></td><td style="padding: 8px; border-bottom: 1px solid #eee;">{data['province']}</td></tr>
            </table>
            <p style="margin-top: 20px;">กรุณาเข้าสู่ระบบเพื่อตรวจสอบและอนุมัติใบสมัคร</p>
        </div>
        '''
        send_email('cmidcoteam@gmail.com', f'[ใบสมัครใหม่] {data["full_name"]} - รอการอนุมัติ', admin_email_html)
        
        applicant_email_html = f'''
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #667eea;">ขอบคุณสำหรับการสมัครตัวแทนจำหน่าย</h2>
            <p>สวัสดีคุณ {data['full_name']},</p>
            <p>เราได้รับใบสมัครของคุณเรียบร้อยแล้ว</p>
            <p>ทีมงานจะตรวจสอบข้อมูลและติดต่อกลับทางโทรศัพท์เพื่อยืนยันข้อมูล</p>
            <p>หากมีข้อสงสัย สามารถติดต่อได้ที่ Line: @cmidco</p>
            <p style="margin-top: 20px; color: #666;">ขอบคุณที่สนใจเป็นตัวแทนจำหน่ายกับเรา</p>
        </div>
        '''
        send_email(data['email'], 'ได้รับใบสมัครตัวแทนจำหน่ายแล้ว', applicant_email_html)
        
        return jsonify({'message': 'ส่งใบสมัครสำเร็จ', 'id': application_id}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-applications', methods=['GET'])
@admin_required
def get_reseller_applications():
    """Get all reseller applications (admin only)"""
    status = request.args.get('status', 'pending')
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        if status == 'all':
            cursor.execute('''
                SELECT ra.*, u.full_name as reviewed_by_name
                FROM reseller_applications ra
                LEFT JOIN users u ON ra.reviewed_by = u.id
                ORDER BY ra.created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT ra.*, u.full_name as reviewed_by_name
                FROM reseller_applications ra
                LEFT JOIN users u ON ra.reviewed_by = u.id
                WHERE ra.status = %s
                ORDER BY ra.created_at DESC
            ''', (status,))
        
        applications = cursor.fetchall()
        result = []
        for app in applications:
            app_dict = dict(app)
            if app_dict.get('created_at'):
                app_dict['created_at'] = app_dict['created_at'].isoformat()
            if app_dict.get('reviewed_at'):
                app_dict['reviewed_at'] = app_dict['reviewed_at'].isoformat()
            del app_dict['password_hash']
            result.append(app_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-applications/count', methods=['GET'])
@admin_required
def get_reseller_applications_count():
    """Get count of pending reseller applications"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM reseller_applications WHERE status = 'pending'")
        count = cursor.fetchone()[0]
        
        return jsonify({'count': count}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-applications/<int:app_id>', methods=['GET'])
@admin_required
def get_reseller_application(app_id):
    """Get a specific reseller application"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT ra.*, u.full_name as reviewed_by_name
            FROM reseller_applications ra
            LEFT JOIN users u ON ra.reviewed_by = u.id
            WHERE ra.id = %s
        ''', (app_id,))
        
        app = cursor.fetchone()
        if not app:
            return jsonify({'error': 'ไม่พบใบสมัคร'}), 404
        
        app_dict = dict(app)
        if app_dict.get('created_at'):
            app_dict['created_at'] = app_dict['created_at'].isoformat()
        if app_dict.get('reviewed_at'):
            app_dict['reviewed_at'] = app_dict['reviewed_at'].isoformat()
        
        return jsonify(app_dict), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-applications/<int:app_id>/approve', methods=['POST'])
@admin_required
def approve_reseller_application(app_id):
    """Approve a reseller application and create user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT * FROM reseller_applications WHERE id = %s', (app_id,))
        app = cursor.fetchone()
        
        if not app:
            return jsonify({'error': 'ไม่พบใบสมัคร'}), 404
        
        if app['status'] != 'pending':
            return jsonify({'error': 'ใบสมัครนี้ได้รับการพิจารณาแล้ว'}), 400
        
        cursor.execute('SELECT id FROM users WHERE username = %s', (app['username'],))
        if cursor.fetchone():
            return jsonify({'error': 'ชื่อผู้ใช้นี้ถูกใช้งานแล้ว'}), 400
        
        cursor.execute('SELECT id FROM reseller_tiers ORDER BY level_rank ASC LIMIT 1')
        default_tier = cursor.fetchone()
        tier_id = default_tier['id'] if default_tier else None
        
        cursor.execute('SELECT id FROM roles WHERE name = %s', ('Reseller',))
        reseller_role = cursor.fetchone()
        if not reseller_role:
            return jsonify({'error': 'ไม่พบบทบาทตัวแทนจำหน่ายในระบบ'}), 500
        
        cursor.execute('''
            INSERT INTO users 
            (full_name, username, password, role_id, reseller_tier_id, email, phone, line_id, address, province, district, subdistrict, postal_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (app['full_name'], app['username'], app['password_hash'], reseller_role['id'], tier_id,
              app['email'], app['phone'], app['line_id'], app['address'], app['province'], 
              app['district'], app['subdistrict'], app['postal_code']))
        
        new_user_id = cursor.fetchone()['id']
        
        cursor.execute('''
            UPDATE reseller_applications 
            SET status = 'approved', reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (session['user_id'], app_id))
        
        conn.commit()
        
        approval_email_html = f'''
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #4CAF50;">ยินดีด้วย! ใบสมัครของคุณได้รับการอนุมัติแล้ว</h2>
            <p>สวัสดีคุณ {app['full_name']},</p>
            <p>ใบสมัครตัวแทนจำหน่ายของคุณได้รับการอนุมัติเรียบร้อยแล้ว</p>
            <p>คุณสามารถเข้าสู่ระบบได้ทันทีด้วยข้อมูลดังนี้:</p>
            <div style="background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <p><strong>Username:</strong> {app['username']}</p>
                <p><strong>Email:</strong> {app['email']}</p>
                <p>(ใช้รหัสผ่านที่คุณตั้งไว้ตอนสมัคร)</p>
            </div>
            <p>หากมีข้อสงสัย สามารถติดต่อได้ที่ Line: @cmidco</p>
            <p style="margin-top: 20px; color: #666;">ขอบคุณที่เป็นส่วนหนึ่งของเรา</p>
        </div>
        '''
        send_email(app['email'], 'ใบสมัครตัวแทนจำหน่ายได้รับการอนุมัติแล้ว', approval_email_html)
        
        log_activity('approve', 'application', f"อนุมัติใบสมัคร: {app['full_name']} ({app['email']})", 
                    target_type='application', target_id=app_id, target_name=app['full_name'])
        
        return jsonify({'message': 'อนุมัติใบสมัครสำเร็จ', 'user_id': new_user_id}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller-applications/<int:app_id>/reject', methods=['POST'])
@admin_required
def reject_reseller_application(app_id):
    """Reject a reseller application"""
    data = request.json
    reject_reason = data.get('reason', '') if data else ''
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT * FROM reseller_applications WHERE id = %s', (app_id,))
        app = cursor.fetchone()
        
        if not app:
            return jsonify({'error': 'ไม่พบใบสมัคร'}), 404
        
        if app['status'] != 'pending':
            return jsonify({'error': 'ใบสมัครนี้ได้รับการพิจารณาแล้ว'}), 400
        
        cursor.execute('''
            UPDATE reseller_applications 
            SET status = 'rejected', reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP, reject_reason = %s
            WHERE id = %s
        ''', (session['user_id'], reject_reason, app_id))
        
        conn.commit()
        
        rejection_email_html = f'''
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #f44336;">แจ้งผลการพิจารณาใบสมัคร</h2>
            <p>สวัสดีคุณ {app['full_name']},</p>
            <p>เราขอแจ้งให้ทราบว่าใบสมัครตัวแทนจำหน่ายของคุณไม่ผ่านการอนุมัติในครั้งนี้</p>
            {f'<p><strong>เหตุผล:</strong> {reject_reason}</p>' if reject_reason else ''}
            <p>หากต้องการสอบถามเพิ่มเติม สามารถติดต่อได้ที่ Line: @cmidco</p>
            <p style="margin-top: 20px; color: #666;">ขอบคุณที่สนใจเป็นตัวแทนจำหน่ายกับเรา</p>
        </div>
        '''
        send_email(app['email'], 'แจ้งผลการพิจารณาใบสมัครตัวแทนจำหน่าย', rejection_email_html)
        
        log_activity('reject', 'application', f"ปฏิเสธใบสมัคร: {app['full_name']} ({app['email']})" + (f" - เหตุผล: {reject_reason}" if reject_reason else ""), 
                    target_type='application', target_id=app_id, target_name=app['full_name'])
        
        return jsonify({'message': 'ปฏิเสธใบสมัครสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged in user info"""
    return jsonify({
        'id': session.get('user_id'),
        'username': session.get('username'),
        'full_name': session.get('full_name'),
        'role': session.get('role'),
        'reseller_tier': session.get('reseller_tier')
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        cursor.execute('SELECT id, username FROM users WHERE id = %s', (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at, p.low_stock_threshold
                ORDER BY p.created_at DESC
            '''
            cursor.execute(base_query, (user_id,))
        else:
            base_query += '''
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at, p.low_stock_threshold
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
                ORDER BY s.id
            ''', (product['id'],))
            product['skus'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(products), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
            INSERT INTO products (brand_id, name, parent_sku, description, size_chart_image_url, status, 
                                  weight, length, width, height, low_stock_threshold)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (brand_id, data['name'], data['parent_sku'], data.get('description', ''), 
              data.get('size_chart_image_url'), status,
              data.get('weight'), data.get('length'), data.get('width'), data.get('height'),
              low_stock))
        
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
        option_value_ids_map = {}  # Map to store option_value_ids for SKU generation
        
        for option in options_data:
            if not option.get('name') or not option.get('values'):
                continue
            
            # Insert option
            cursor.execute('''
                INSERT INTO options (product_id, name)
                VALUES (%s, %s)
                RETURNING id
            ''', (product_id, option['name']))
            
            option_id = cursor.fetchone()['id']
            option_value_ids_map[option_id] = []
            
            # Insert option values with sort_order
            for idx, value_data in enumerate(option['values']):
                cursor.execute('''
                    INSERT INTO option_values (option_id, value, sort_order)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (option_id, value_data['value'], value_data.get('sort_order', idx)))
                
                value_id = cursor.fetchone()['id']
                option_value_ids_map[option_id].append(value_id)
        
        # Insert SKUs if provided
        skus_data = data.get('skus', [])
        for sku_data in skus_data:
            if not sku_data.get('sku_code'):
                continue
            
            # Insert SKU with cost_price (stock always starts at 0, use Stock Adjustment to add inventory)
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
            
            # Map SKU to option values
            for value_id in sku_data.get('option_value_ids', []):
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
            SET brand_id = %s, name = %s, description = %s, size_chart_image_url = %s, status = %s,
                weight = %s, length = %s, width = %s, height = %s, low_stock_threshold = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (brand_id, data['name'], data.get('description', ''), data.get('size_chart_image_url'), status,
              data.get('weight'), data.get('length'), data.get('width'), data.get('height'),
              low_stock, product_id))
        
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
            return jsonify({'error': 'ผู้ใช้ไม่ใช่ตัวแทนจำหน่าย'}), 400
        
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
            return jsonify({'error': 'ผู้ใช้ไม่ใช่ตัวแทนจำหน่าย'}), 400
        
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SALES CHANNELS API ====================

@app.route('/api/sales-channels', methods=['GET'])
@login_required
def get_sales_channels():
    """Get all sales channels"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, description, is_active, sort_order, created_at
            FROM sales_channels
            ORDER BY sort_order ASC
        ''')
        channels = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(channels), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/sales-channels', methods=['POST'])
@admin_required
def create_sales_channel():
    """Create a new sales channel"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'error': 'Channel name is required'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO sales_channels (name, description, is_active, sort_order)
            VALUES (%s, %s, %s, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM sales_channels))
            RETURNING id, name, description, is_active, sort_order
        ''', (name, data.get('description', ''), data.get('is_active', True)))
        
        channel = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(channel), 201
        
    except psycopg2.errors.UniqueViolation:
        return jsonify({'error': 'Channel name already exists'}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/sales-channels/<int:channel_id>', methods=['PUT'])
@admin_required
def update_sales_channel(channel_id):
    """Update a sales channel"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE sales_channels
            SET name = %s, description = %s, is_active = %s, sort_order = %s
            WHERE id = %s
            RETURNING id, name, description, is_active, sort_order
        ''', (
            data.get('name', ''),
            data.get('description', ''),
            data.get('is_active', True),
            data.get('sort_order', 0),
            channel_id
        ))
        
        channel = cursor.fetchone()
        if not channel:
            return jsonify({'error': 'ไม่พบช่องทางขาย'}), 404
        
        conn.commit()
        return jsonify(dict(channel)), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/sales-channels/<int:channel_id>', methods=['DELETE'])
@admin_required
def delete_sales_channel(channel_id):
    """Delete a sales channel"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Don't allow deleting the default "ระบบออนไลน์" channel
        cursor.execute('SELECT name FROM sales_channels WHERE id = %s', (channel_id,))
        result = cursor.fetchone()
        if result and result[0] == 'ระบบออนไลน์':
            return jsonify({'error': 'Cannot delete the default online channel'}), 400
        
        cursor.execute('DELETE FROM sales_channels WHERE id = %s RETURNING id', (channel_id,))
        if cursor.fetchone() is None:
            return jsonify({'error': 'ไม่พบช่องทางขาย'}), 404
        
        conn.commit()
        return jsonify({'message': 'ลบช่องทางขายสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PROMPTPAY SETTINGS API ====================

@app.route('/api/promptpay-settings', methods=['GET'])
@login_required
def get_promptpay_settings():
    """Get PromptPay settings"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, qr_image_url, account_name, account_number, is_active, updated_at
            FROM promptpay_settings
            WHERE is_active = TRUE
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        
        if settings:
            return jsonify(dict(settings)), 200
        return jsonify({}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/promptpay-settings', methods=['POST'])
@admin_required
def save_promptpay_settings():
    """Save or update PromptPay settings"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if settings exist
        cursor.execute('SELECT id FROM promptpay_settings LIMIT 1')
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE promptpay_settings
                SET qr_image_url = %s, account_name = %s, account_number = %s,
                    is_active = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
                WHERE id = %s
                RETURNING id, qr_image_url, account_name, account_number, is_active
            ''', (
                data.get('qr_image_url'),
                data.get('account_name'),
                data.get('account_number'),
                data.get('is_active', True),
                user_id,
                existing['id']
            ))
        else:
            cursor.execute('''
                INSERT INTO promptpay_settings (qr_image_url, account_name, account_number, is_active, updated_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, qr_image_url, account_name, account_number, is_active
            ''', (
                data.get('qr_image_url'),
                data.get('account_name'),
                data.get('account_number'),
                data.get('is_active', True),
                user_id
            ))
        
        settings = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify({
            'message': 'บันทึกการตั้งค่า PromptPay สำเร็จ',
            'settings': settings
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/promptpay-qr', methods=['GET'])
@login_required
def generate_promptpay_qr():
    """Generate PromptPay QR Code with amount"""
    import qrcode
    import io
    import base64
    
    amount = request.args.get('amount', type=float)
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT account_number, account_name
            FROM promptpay_settings
            WHERE is_active = TRUE
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        
        if not settings or not settings['account_number']:
            return jsonify({'error': 'PromptPay settings not configured'}), 400
        
        phone_or_id = settings['account_number'].replace('-', '').replace(' ', '')
        
        if len(phone_or_id) == 10 and phone_or_id.startswith('0'):
            formatted_id = '0066' + phone_or_id[1:]
            aid = '01'
        elif len(phone_or_id) == 13:
            formatted_id = phone_or_id
            aid = '02'
        else:
            return jsonify({'error': 'Invalid PromptPay number format'}), 400
        
        def crc16(data):
            crc = 0xFFFF
            for byte in data.encode('ascii'):
                crc ^= byte << 8
                for _ in range(8):
                    if crc & 0x8000:
                        crc = (crc << 1) ^ 0x1021
                    else:
                        crc <<= 1
                    crc &= 0xFFFF
            return format(crc, '04X')
        
        aid_field = f'00{len("A000000677010111"):02d}A000000677010111{aid}{len(formatted_id):02d}{formatted_id}'
        merchant_field = f'29{len(aid_field):02d}{aid_field}'
        
        payload_parts = [
            '000201',
            '010212',
            merchant_field,
            '52040000',
            '5303764',
        ]
        
        if amount and amount > 0:
            amount_str = f'{amount:.2f}'
            payload_parts.append(f'54{len(amount_str):02d}{amount_str}')
        
        payload_parts.append('5802TH')
        
        payload_parts.append('6304')
        payload = ''.join(payload_parts)
        payload += crc16(payload)
        
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return jsonify({
            'qr_image': f'data:image/png;base64,{img_base64}',
            'account_name': settings['account_name'],
            'amount': amount
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SHIPPING SETTINGS API ====================

@app.route('/api/shipping-rates', methods=['GET'])
@login_required
def get_shipping_rates():
    """Get all shipping weight rates"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, min_weight, max_weight, rate, is_active, sort_order
            FROM shipping_weight_rates
            WHERE is_active = TRUE
            ORDER BY sort_order ASC
        ''')
        rates = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(rates), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-rates', methods=['POST'])
@admin_required
def create_shipping_rate():
    """Create a new shipping rate"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO shipping_weight_rates (min_weight, max_weight, rate, sort_order)
            VALUES (%s, %s, %s, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM shipping_weight_rates))
            RETURNING id, min_weight, max_weight, rate, is_active, sort_order
        ''', (data.get('min_weight', 0), data.get('max_weight'), data.get('rate', 0)))
        
        rate = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(rate), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-rates/<int:rate_id>', methods=['PUT'])
@admin_required
def update_shipping_rate(rate_id):
    """Update a shipping rate"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE shipping_weight_rates
            SET min_weight = %s, max_weight = %s, rate = %s, is_active = %s
            WHERE id = %s
            RETURNING id, min_weight, max_weight, rate, is_active, sort_order
        ''', (data.get('min_weight'), data.get('max_weight'), data.get('rate'), data.get('is_active', True), rate_id))
        
        rate = cursor.fetchone()
        if not rate:
            return jsonify({'error': 'Rate not found'}), 404
        
        conn.commit()
        return jsonify(dict(rate)), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-rates/<int:rate_id>', methods=['DELETE'])
@admin_required
def delete_shipping_rate(rate_id):
    """Delete a shipping rate"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM shipping_weight_rates WHERE id = %s', (rate_id,))
        conn.commit()
        
        return jsonify({'message': 'ลบอัตราค่าจัดส่งสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-promotions', methods=['GET'])
@login_required
def get_shipping_promotions():
    """Get all shipping promotions"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, promo_type, min_order_value, discount_amount, is_active, start_date, end_date
            FROM shipping_promotions
            ORDER BY min_order_value DESC
        ''')
        promos = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(promos), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-promotions', methods=['POST'])
@admin_required
def create_shipping_promotion():
    """Create a new shipping promotion"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO shipping_promotions (name, promo_type, min_order_value, discount_amount, is_active, start_date, end_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, promo_type, min_order_value, discount_amount, is_active, start_date, end_date
        ''', (
            data.get('name', ''),
            data.get('promo_type', 'free_shipping'),
            data.get('min_order_value', 0),
            data.get('discount_amount', 0),
            data.get('is_active', True),
            data.get('start_date'),
            data.get('end_date')
        ))
        
        promo = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(promo), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-promotions/<int:promo_id>', methods=['PUT'])
@admin_required
def update_shipping_promotion(promo_id):
    """Update a shipping promotion"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE shipping_promotions
            SET name = %s, promo_type = %s, min_order_value = %s, discount_amount = %s, 
                is_active = %s, start_date = %s, end_date = %s
            WHERE id = %s
            RETURNING id, name, promo_type, min_order_value, discount_amount, is_active, start_date, end_date
        ''', (
            data.get('name'),
            data.get('promo_type'),
            data.get('min_order_value'),
            data.get('discount_amount'),
            data.get('is_active', True),
            data.get('start_date'),
            data.get('end_date'),
            promo_id
        ))
        
        promo = cursor.fetchone()
        if not promo:
            return jsonify({'error': 'Promotion not found'}), 404
        
        conn.commit()
        return jsonify(dict(promo)), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-promotions/<int:promo_id>', methods=['DELETE'])
@admin_required
def delete_shipping_promotion(promo_id):
    """Delete a shipping promotion"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM shipping_promotions WHERE id = %s', (promo_id,))
        conn.commit()
        
        return jsonify({'message': 'ลบโปรโมชั่นสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SHIPPING PROVIDERS API ====================

@app.route('/api/shipping-providers', methods=['GET'])
@login_required
def get_shipping_providers():
    """Get all shipping providers"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, logo_url, tracking_url, is_active, display_order, created_at
            FROM shipping_providers
            ORDER BY display_order, name
        ''')
        providers = cursor.fetchall()
        
        return jsonify(providers), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-providers', methods=['POST'])
@admin_required
def create_shipping_provider():
    """Create a new shipping provider"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        name = data.get('name')
        logo_url = data.get('logo_url')
        tracking_url = data.get('tracking_url')
        is_active = data.get('is_active', True)
        display_order = data.get('display_order', 0)
        
        if not name:
            return jsonify({'error': 'กรุณาระบุชื่อบริษัทขนส่ง'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO shipping_providers (name, logo_url, tracking_url, is_active, display_order)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, logo_url, tracking_url, is_active, display_order, created_at
        ''', (name, logo_url, tracking_url, is_active, display_order))
        
        provider = cursor.fetchone()
        conn.commit()
        
        return jsonify(provider), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-providers/<int:provider_id>', methods=['PUT'])
@admin_required
def update_shipping_provider(provider_id):
    """Update a shipping provider"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        name = data.get('name')
        logo_url = data.get('logo_url')
        tracking_url = data.get('tracking_url')
        is_active = data.get('is_active')
        display_order = data.get('display_order')
        
        if not name:
            return jsonify({'error': 'กรุณาระบุชื่อบริษัทขนส่ง'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE shipping_providers
            SET name = %s, logo_url = %s, tracking_url = %s, is_active = %s, display_order = %s
            WHERE id = %s
            RETURNING id, name, logo_url, tracking_url, is_active, display_order, created_at
        ''', (name, logo_url, tracking_url, is_active, display_order, provider_id))
        
        provider = cursor.fetchone()
        if not provider:
            return jsonify({'error': 'ไม่พบบริษัทขนส่ง'}), 404
        
        conn.commit()
        
        return jsonify(provider), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/shipping-providers/<int:provider_id>', methods=['DELETE'])
@admin_required
def delete_shipping_provider(provider_id):
    """Delete a shipping provider"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM shipping_providers WHERE id = %s', (provider_id,))
        conn.commit()
        
        return jsonify({'message': 'ลบบริษัทขนส่งสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/calculate-shipping', methods=['POST'])
@login_required
def calculate_shipping():
    """Calculate shipping cost based on weight and apply promotions"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        total_weight = data.get('total_weight', 0)
        order_total = data.get('order_total', 0)
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT rate FROM shipping_weight_rates
            WHERE is_active = TRUE
              AND min_weight <= %s
              AND (max_weight IS NULL OR max_weight >= %s)
            ORDER BY min_weight DESC
            LIMIT 1
        ''', (total_weight, total_weight))
        
        rate_row = cursor.fetchone()
        shipping_cost = float(rate_row['rate']) if rate_row else 0
        original_shipping = shipping_cost
        
        cursor.execute('''
            SELECT promo_type, min_order_value, discount_amount, name
            FROM shipping_promotions
            WHERE is_active = TRUE
              AND min_order_value <= %s
              AND (start_date IS NULL OR start_date <= CURRENT_TIMESTAMP)
              AND (end_date IS NULL OR end_date >= CURRENT_TIMESTAMP)
            ORDER BY min_order_value DESC
            LIMIT 1
        ''', (order_total,))
        
        promo = cursor.fetchone()
        promo_applied = None
        
        if promo:
            if promo['promo_type'] == 'free_shipping':
                shipping_cost = 0
                promo_applied = promo['name']
            elif promo['promo_type'] == 'discount':
                discount = float(promo['discount_amount'])
                shipping_cost = max(0, shipping_cost - discount)
                promo_applied = promo['name']
        
        return jsonify({
            'shipping_cost': shipping_cost,
            'original_shipping': original_shipping,
            'promo_applied': promo_applied,
            'total_weight': total_weight
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ORDER NUMBER SETTINGS API ====================

@app.route('/api/order-number-settings', methods=['GET'])
@admin_required
def get_order_number_settings():
    """Get order number settings"""
    from datetime import datetime
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        current_period = datetime.now().strftime('%y%m')
        
        cursor.execute('''
            SELECT id, prefix, format_type, digit_count, current_sequence, current_period, updated_at
            FROM order_number_settings
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        
        if settings:
            # Generate preview of next order number
            if settings['current_period'] == current_period:
                next_seq = settings['current_sequence'] + 1
            else:
                next_seq = 1
            preview = f"{settings['prefix']}-{current_period}-{str(next_seq).zfill(settings['digit_count'])}"
            settings['preview'] = preview
            return jsonify(dict(settings)), 200
        
        # Return defaults if no settings
        return jsonify({
            'prefix': 'ORD',
            'format_type': 'YYMM',
            'digit_count': 4,
            'current_sequence': 0,
            'current_period': '',
            'preview': 'ORD-' + current_period + '-0001'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/order-number-settings', methods=['POST'])
@admin_required
def save_order_number_settings():
    """Save order number settings"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        prefix = data.get('prefix', 'ORD').upper().strip()
        digit_count = int(data.get('digit_count', 4))
        
        # Validate prefix (alphanumeric, 1-10 chars)
        if not prefix or len(prefix) > 10:
            return jsonify({'error': 'Prefix must be 1-10 characters'}), 400
        
        # Validate digit count (3-6)
        if digit_count < 3 or digit_count > 6:
            return jsonify({'error': 'Digit count must be between 3 and 6'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if settings exist
        cursor.execute('SELECT id FROM order_number_settings LIMIT 1')
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE order_number_settings
                SET prefix = %s, digit_count = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, prefix, format_type, digit_count, current_sequence, current_period
            ''', (prefix, digit_count, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO order_number_settings (prefix, format_type, digit_count, current_sequence, current_period)
                VALUES (%s, 'YYMM', %s, 0, '')
                RETURNING id, prefix, format_type, digit_count, current_sequence, current_period
            ''', (prefix, digit_count))
        
        settings = dict(cursor.fetchone())
        conn.commit()
        
        # Generate preview
        from datetime import datetime
        current_period = datetime.now().strftime('%y%m')
        if settings['current_period'] == current_period:
            next_seq = settings['current_sequence'] + 1
        else:
            next_seq = 1
        settings['preview'] = f"{prefix}-{current_period}-{str(next_seq).zfill(digit_count)}"
        
        return jsonify({
            'message': 'บันทึกการตั้งค่าเลขที่ใบสั่งซื้อสำเร็จ',
            'settings': settings
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== FACEBOOK PIXEL SETTINGS API ====================

@app.route('/api/facebook-pixel-settings', methods=['GET'])
@admin_required
def get_facebook_pixel_settings():
    """Get Facebook Pixel settings"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, pixel_id, access_token, is_active, 
                   track_page_view, track_lead, track_complete_registration, updated_at
            FROM facebook_pixel_settings
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        
        if settings:
            # Mask access token for security
            if settings.get('access_token'):
                settings['access_token_masked'] = settings['access_token'][:10] + '...' if len(settings['access_token']) > 10 else settings['access_token']
            return jsonify(dict(settings)), 200
        return jsonify({}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/facebook-pixel-settings', methods=['POST'])
@admin_required
def save_facebook_pixel_settings():
    """Save Facebook Pixel settings"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        pixel_id = data.get('pixel_id', '').strip()
        access_token = data.get('access_token', '').strip()
        is_active = data.get('is_active', False)
        track_page_view = data.get('track_page_view', True)
        track_lead = data.get('track_lead', True)
        track_complete_registration = data.get('track_complete_registration', True)
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if settings exist
        cursor.execute('SELECT id, access_token FROM facebook_pixel_settings LIMIT 1')
        existing = cursor.fetchone()
        
        # If access_token is not provided, keep existing one
        if not access_token and existing and existing.get('access_token'):
            access_token = existing['access_token']
        
        if existing:
            cursor.execute('''
                UPDATE facebook_pixel_settings
                SET pixel_id = %s, access_token = %s, is_active = %s,
                    track_page_view = %s, track_lead = %s, track_complete_registration = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, pixel_id, is_active, track_page_view, track_lead, track_complete_registration
            ''', (pixel_id, access_token, is_active, track_page_view, track_lead, track_complete_registration, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO facebook_pixel_settings (pixel_id, access_token, is_active, track_page_view, track_lead, track_complete_registration)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, pixel_id, is_active, track_page_view, track_lead, track_complete_registration
            ''', (pixel_id, access_token, is_active, track_page_view, track_lead, track_complete_registration))
        
        settings = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify({
            'message': 'บันทึกการตั้งค่า Facebook Pixel สำเร็จ',
            'settings': settings
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/facebook-pixel-settings/public', methods=['GET'])
def get_facebook_pixel_public():
    """Get Facebook Pixel ID for frontend (public endpoint)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT pixel_id, track_page_view, track_lead, track_complete_registration
            FROM facebook_pixel_settings
            WHERE is_active = TRUE
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        
        if settings and settings.get('pixel_id'):
            return jsonify(dict(settings)), 200
        return jsonify({}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PAGE VISITS TRACKING API ====================

@app.route('/api/track-visit', methods=['POST'])
def track_page_visit():
    """Track a page visit (public endpoint for landing pages)"""
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        page_name = data.get('page_name', 'unknown')
        source = data.get('source', 'direct')
        
        # Get visitor info
        visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if visitor_ip:
            visitor_ip = visitor_ip.split(',')[0].strip()
        user_agent = request.headers.get('User-Agent', '')[:500]
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO page_visits (page_name, source, visitor_ip, user_agent)
            VALUES (%s, %s, %s, %s)
        ''', (page_name, source, visitor_ip, user_agent))
        
        conn.commit()
        return jsonify({'success': True}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/facebook-ads/stats', methods=['GET'])
@login_required
@admin_required
def get_facebook_ads_stats():
    """Get Facebook Ads statistics for admin dashboard"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get today's stats
        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits 
            WHERE page_name = 'become-reseller' 
            AND source = 'facebook'
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_visits = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM users 
            WHERE notes LIKE '%[source: facebook]%'
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_registrations = cursor.fetchone()['count']
        
        # Get this week's stats
        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits 
            WHERE page_name = 'become-reseller' 
            AND source = 'facebook'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_visits = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM users 
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_registrations = cursor.fetchone()['count']
        
        # Get this month's stats
        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits 
            WHERE page_name = 'become-reseller' 
            AND source = 'facebook'
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_visits = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM users 
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_registrations = cursor.fetchone()['count']
        
        # Get total stats
        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits 
            WHERE page_name = 'become-reseller' 
            AND source = 'facebook'
        ''')
        total_visits = cursor.fetchone()['count']
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM users 
            WHERE notes LIKE '%[source: facebook]%'
        ''')
        total_registrations = cursor.fetchone()['count']
        
        # Get daily stats for chart (last 7 days)
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as visits
            FROM page_visits 
            WHERE page_name = 'become-reseller' 
            AND source = 'facebook'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        daily_visits = {str(row['date']): row['visits'] for row in cursor.fetchall()}
        
        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as registrations
            FROM users 
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        daily_registrations = {str(row['date']): row['registrations'] for row in cursor.fetchall()}
        
        # Build chart data for last 7 days
        from datetime import datetime, timedelta
        chart_labels = []
        chart_visits = []
        chart_registrations = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            chart_labels.append((datetime.now() - timedelta(days=i)).strftime('%d/%m'))
            chart_visits.append(daily_visits.get(date, 0))
            chart_registrations.append(daily_registrations.get(date, 0))
        
        # Get recent registrations from Facebook
        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.created_at, u.is_approved,
                   rt.name as tier_name
            FROM users u
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.notes LIKE '%[source: facebook]%'
            ORDER BY u.created_at DESC
            LIMIT 10
        ''')
        recent_registrations = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'today': {
                'visits': today_visits,
                'registrations': today_registrations,
                'conversion': round((today_registrations / today_visits * 100) if today_visits > 0 else 0, 1)
            },
            'week': {
                'visits': week_visits,
                'registrations': week_registrations,
                'conversion': round((week_registrations / week_visits * 100) if week_visits > 0 else 0, 1)
            },
            'month': {
                'visits': month_visits,
                'registrations': month_registrations,
                'conversion': round((month_registrations / month_visits * 100) if month_visits > 0 else 0, 1)
            },
            'total': {
                'visits': total_visits,
                'registrations': total_registrations,
                'conversion': round((total_registrations / total_visits * 100) if total_visits > 0 else 0, 1)
            },
            'chart': {
                'labels': chart_labels,
                'visits': chart_visits,
                'registrations': chart_registrations
            },
            'recent_registrations': recent_registrations
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== NOTIFICATIONS API ====================

@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    """Get notifications for current user"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, title, message, type, reference_type, reference_id, is_read, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        ''', (user_id,))
        
        notifications = [dict(row) for row in cursor.fetchall()]
        
        # Get unread count
        cursor.execute('''
            SELECT COUNT(*) as count FROM notifications
            WHERE user_id = %s AND is_read = FALSE
        ''', (user_id,))
        unread_count = cursor.fetchone()['count']
        
        return jsonify({
            'notifications': notifications,
            'unread_count': unread_count
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/notifications/<int:notification_id>/read', methods=['PATCH'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE notifications SET is_read = TRUE
            WHERE id = %s AND user_id = %s
        ''', (notification_id, user_id))
        
        conn.commit()
        return jsonify({'message': 'Marked as read'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/notifications/read-all', methods=['PATCH'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE notifications SET is_read = TRUE
            WHERE user_id = %s AND is_read = FALSE
        ''', (user_id,))
        
        conn.commit()
        return jsonify({'message': 'All marked as read'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Helper function to create notification
def create_notification(user_id, title, message, notification_type='info', reference_type=None, reference_id=None):
    """Create a notification for a user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, type, reference_type, reference_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (user_id, title, message, notification_type, reference_type, reference_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ADMIN PAGES ====================

@app.route('/admin/settings')
@admin_required
def settings_page():
    """Admin settings page"""
    return render_template('settings.html')

@app.route('/admin/orders')
@admin_required
def admin_orders_page():
    """Admin orders management page"""
    return render_template('admin_orders.html')

@app.route('/admin/sales-channels')
@admin_required
def sales_channels_page():
    """Sales channels management page"""
    return render_template('sales_channels.html')

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
                   p.id as product_id, p.name as product_name, p.parent_sku,
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER DASHBOARD APIs ====================

@app.route('/api/reseller/dashboard-stats', methods=['GET'])
@login_required
def get_reseller_dashboard_stats():
    """Get dashboard statistics for reseller"""
    conn = None
    cursor = None
    try:
        from datetime import datetime, timedelta
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user info with tier
        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.total_purchases,
                   u.reseller_tier_id, u.tier_manual_override,
                   rt.name as tier_name, rt.level_rank, rt.description as tier_description
            FROM users u
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'error': 'ไม่พบผู้ใช้'}), 404
        
        # Get this month's purchases
        today = datetime.now().date()
        first_of_month = today.replace(day=1)
        
        cursor.execute('''
            SELECT COALESCE(SUM(final_amount), 0) as month_total,
                   COUNT(*) as month_orders
            FROM orders
            WHERE user_id = %s AND status = 'paid'
            AND DATE(paid_at) >= %s AND DATE(paid_at) <= %s
        ''', (user_id, first_of_month, today))
        month_stats = cursor.fetchone()
        
        # Get all-time stats
        cursor.execute('''
            SELECT COALESCE(SUM(final_amount), 0) as all_time_total,
                   COUNT(*) as all_time_orders
            FROM orders
            WHERE user_id = %s AND status = 'paid'
        ''', (user_id,))
        all_time_stats = cursor.fetchone()
        
        # Get pending orders count (by status)
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE user_id = %s AND status != 'paid' AND status != 'cancelled'
            GROUP BY status
        ''', (user_id,))
        pending_orders = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # Get tier progress info
        tier_progress = {
            'current_tier': user['tier_name'] or 'ไม่มีระดับ',
            'current_tier_rank': user['level_rank'] or 0,
            'tier_description': user['tier_description'] or '',
            'total_purchases': float(user['total_purchases'] or 0),
            'next_tier': None,
            'next_tier_threshold': 0,
            'progress_percent': 100,
            'amount_to_next': 0,
            'is_manual_override': user['tier_manual_override'] or False
        }
        
        # Get next tier info
        if user['level_rank']:
            cursor.execute('''
                SELECT name, upgrade_threshold, level_rank
                FROM reseller_tiers 
                WHERE level_rank > %s AND is_manual_only = FALSE
                ORDER BY level_rank ASC
                LIMIT 1
            ''', (user['level_rank'],))
            next_tier = cursor.fetchone()
            
            if next_tier:
                tier_progress['next_tier'] = next_tier['name']
                tier_progress['next_tier_threshold'] = float(next_tier['upgrade_threshold'] or 0)
                
                # Calculate progress
                current_purchases = float(user['total_purchases'] or 0)
                threshold = float(next_tier['upgrade_threshold'] or 0)
                
                if threshold > 0:
                    tier_progress['progress_percent'] = min(100, round((current_purchases / threshold) * 100, 1))
                    tier_progress['amount_to_next'] = max(0, threshold - current_purchases)
        
        # Get cart item count
        cursor.execute('''
            SELECT COALESCE(SUM(ci.quantity), 0) as cart_count
            FROM cart_items ci
            JOIN carts c ON c.id = ci.cart_id
            WHERE c.user_id = %s AND c.status = 'active'
        ''', (user_id,))
        cart_result = cursor.fetchone()
        cart_count = int(cart_result['cart_count']) if cart_result else 0
        
        # Get notification count
        cursor.execute('''
            SELECT COUNT(*) as unread_count
            FROM notifications
            WHERE user_id = %s AND is_read = FALSE
        ''', (user_id,))
        notif_result = cursor.fetchone()
        notification_count = int(notif_result['unread_count']) if notif_result else 0
        
        return jsonify({
            'user': {
                'id': user['id'],
                'full_name': user['full_name'],
                'username': user['username']
            },
            'month_stats': {
                'total': float(month_stats['month_total']),
                'orders': int(month_stats['month_orders'])
            },
            'all_time_stats': {
                'total': float(all_time_stats['all_time_total']),
                'orders': int(all_time_stats['all_time_orders'])
            },
            'pending_orders': pending_orders,
            'tier_progress': tier_progress,
            'cart_count': cart_count,
            'notification_count': notification_count
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/recent-orders', methods=['GET'])
@login_required
def get_reseller_recent_orders():
    """Get recent orders for reseller dashboard"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        limit = request.args.get('limit', 5, type=int)
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT o.id, o.order_number, o.status, o.final_amount, 
                   o.created_at, o.updated_at, o.paid_at,
                   (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                   (SELECT COUNT(*) FROM payment_slips WHERE order_id = o.id AND status = 'pending') as pending_slips
            FROM orders o
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC
            LIMIT %s
        ''', (user_id, limit))
        
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
            orders.append(order)
        
        return jsonify(orders), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/featured-products', methods=['GET'])
@login_required
def get_reseller_featured_products():
    """Get featured/new products for reseller dashboard"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user's tier
        cursor.execute('''
            SELECT reseller_tier_id FROM users WHERE id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        tier_id = user['reseller_tier_id'] if user else None
        
        # Get newest products (last 10)
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku,
                   b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT MIN(price) FROM skus WHERE product_id = p.id) as min_price,
                   (SELECT MAX(price) FROM skus WHERE product_id = p.id) as max_price,
                   (SELECT SUM(stock) FROM skus WHERE product_id = p.id) as total_stock,
                   ptp.discount_percent,
                   p.created_at
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            WHERE p.status = 'active'
            ORDER BY p.created_at DESC
            LIMIT 10
        ''', (tier_id,))
        
        new_products = []
        for row in cursor.fetchall():
            product = dict(row)
            product['min_price'] = float(product['min_price']) if product['min_price'] else 0
            product['max_price'] = float(product['max_price']) if product['max_price'] else 0
            product['discount_percent'] = float(product['discount_percent']) if product['discount_percent'] else 0
            
            if product['discount_percent'] > 0:
                product['discounted_min_price'] = round(product['min_price'] * (1 - product['discount_percent'] / 100), 2)
                product['discounted_max_price'] = round(product['max_price'] * (1 - product['discount_percent'] / 100), 2)
            else:
                product['discounted_min_price'] = product['min_price']
                product['discounted_max_price'] = product['max_price']
            
            new_products.append(product)
        
        # Get best-selling products (based on order items)
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku,
                   b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT MIN(price) FROM skus WHERE product_id = p.id) as min_price,
                   (SELECT MAX(price) FROM skus WHERE product_id = p.id) as max_price,
                   ptp.discount_percent,
                   COALESCE(SUM(oi.quantity), 0) as total_sold
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            LEFT JOIN skus s ON s.product_id = p.id
            LEFT JOIN order_items oi ON oi.sku_id = s.id
            LEFT JOIN orders o ON o.id = oi.order_id AND o.status = 'paid'
            WHERE p.status = 'active'
            GROUP BY p.id, p.name, p.parent_sku, b.name, ptp.discount_percent
            HAVING COALESCE(SUM(oi.quantity), 0) > 0
            ORDER BY total_sold DESC
            LIMIT 10
        ''', (tier_id,))
        
        best_sellers = []
        for row in cursor.fetchall():
            product = dict(row)
            product['min_price'] = float(product['min_price']) if product['min_price'] else 0
            product['max_price'] = float(product['max_price']) if product['max_price'] else 0
            product['discount_percent'] = float(product['discount_percent']) if product['discount_percent'] else 0
            
            if product['discount_percent'] > 0:
                product['discounted_min_price'] = round(product['min_price'] * (1 - product['discount_percent'] / 100), 2)
                product['discounted_max_price'] = round(product['max_price'] * (1 - product['discount_percent'] / 100), 2)
            else:
                product['discounted_min_price'] = product['min_price']
                product['discounted_max_price'] = product['max_price']
            
            best_sellers.append(product)
        
        return jsonify({
            'new_products': new_products,
            'best_sellers': best_sellers
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== THAILAND ADDRESS DATA ====================

@app.route('/api/thailand/provinces', methods=['GET'])
def get_thailand_provinces():
    """Get all Thailand provinces"""
    try:
        import json
        with open('static/data/provinces.json', 'r', encoding='utf-8') as f:
            provinces = json.load(f)
        return jsonify(provinces), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/thailand/districts/<int:province_code>', methods=['GET'])
def get_thailand_districts(province_code):
    """Get districts by province code"""
    try:
        import json
        with open('static/data/districts.json', 'r', encoding='utf-8') as f:
            all_districts = json.load(f)
        districts = [d for d in all_districts if d['provinceCode'] == province_code]
        return jsonify(districts), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/thailand/subdistricts/<int:district_code>', methods=['GET'])
def get_thailand_subdistricts(district_code):
    """Get subdistricts by district code"""
    try:
        import json
        with open('static/data/subdistricts.json', 'r', encoding='utf-8') as f:
            all_subdistricts = json.load(f)
        subdistricts = [s for s in all_subdistricts if s['districtCode'] == district_code]
        return jsonify(subdistricts), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== RESELLER CUSTOMERS ====================

@app.route('/api/reseller/customers', methods=['GET'])
@login_required
def get_reseller_customers():
    """Get all customers for the logged-in reseller"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        search = request.args.get('search', '')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        if search:
            cursor.execute('''
                SELECT id, full_name, phone, email, address, province, district, 
                       subdistrict, postal_code, notes, created_at
                FROM reseller_customers
                WHERE reseller_id = %s 
                AND (full_name ILIKE %s OR phone ILIKE %s OR email ILIKE %s)
                ORDER BY created_at DESC
            ''', (user_id, f'%{search}%', f'%{search}%', f'%{search}%'))
        else:
            cursor.execute('''
                SELECT id, full_name, phone, email, address, province, district, 
                       subdistrict, postal_code, notes, created_at
                FROM reseller_customers
                WHERE reseller_id = %s
                ORDER BY created_at DESC
            ''', (user_id,))
        
        customers = [dict(row) for row in cursor.fetchall()]
        return jsonify({'customers': customers}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/customers', methods=['POST'])
@login_required
def create_reseller_customer():
    """Create a new customer for the reseller"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        if not data.get('full_name'):
            return jsonify({'error': 'กรุณากรอกชื่อลูกค้า'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO reseller_customers 
            (reseller_id, full_name, phone, email, address, province, district, subdistrict, postal_code, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, full_name, phone, email, address, province, district, subdistrict, postal_code, notes, created_at
        ''', (
            user_id,
            data.get('full_name'),
            data.get('phone'),
            data.get('email'),
            data.get('address'),
            data.get('province'),
            data.get('district'),
            data.get('subdistrict'),
            data.get('postal_code'),
            data.get('notes')
        ))
        
        customer = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify({'message': 'เพิ่มลูกค้าสำเร็จ', 'customer': customer}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/customers/<int:customer_id>', methods=['GET'])
@login_required
def get_reseller_customer(customer_id):
    """Get a specific customer"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, full_name, phone, email, address, province, district, 
                   subdistrict, postal_code, notes, created_at
            FROM reseller_customers
            WHERE id = %s AND reseller_id = %s
        ''', (customer_id, user_id))
        
        customer = cursor.fetchone()
        if not customer:
            return jsonify({'error': 'ไม่พบลูกค้า'}), 404
        
        return jsonify({'customer': dict(customer)}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/customers/<int:customer_id>', methods=['PUT'])
@login_required
def update_reseller_customer(customer_id):
    """Update a customer"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        if not data.get('full_name'):
            return jsonify({'error': 'กรุณากรอกชื่อลูกค้า'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE reseller_customers
            SET full_name = %s, phone = %s, email = %s, address = %s,
                province = %s, district = %s, subdistrict = %s, postal_code = %s,
                notes = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND reseller_id = %s
            RETURNING id, full_name, phone, email, address, province, district, subdistrict, postal_code, notes
        ''', (
            data.get('full_name'),
            data.get('phone'),
            data.get('email'),
            data.get('address'),
            data.get('province'),
            data.get('district'),
            data.get('subdistrict'),
            data.get('postal_code'),
            data.get('notes'),
            customer_id,
            user_id
        ))
        
        customer = cursor.fetchone()
        if not customer:
            return jsonify({'error': 'ไม่พบลูกค้า'}), 404
        
        conn.commit()
        return jsonify({'message': 'อัปเดตข้อมูลสำเร็จ', 'customer': dict(customer)}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/customers/<int:customer_id>', methods=['DELETE'])
@login_required
def delete_reseller_customer(customer_id):
    """Delete a customer"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM reseller_customers
            WHERE id = %s AND reseller_id = %s
            RETURNING id
        ''', (customer_id, user_id))
        
        deleted = cursor.fetchone()
        if not deleted:
            return jsonify({'error': 'ไม่พบลูกค้า'}), 404
        
        conn.commit()
        return jsonify({'message': 'ลบลูกค้าสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/profile', methods=['GET'])
@login_required
def get_reseller_profile():
    """Get reseller's profile with shipping info"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.phone, u.email, u.address,
                   u.province, u.district, u.subdistrict, u.postal_code,
                   u.brand_name, u.logo_url,
                   rt.name as tier_name
            FROM users u
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (user_id,))
        
        profile = cursor.fetchone()
        if not profile:
            return jsonify({'error': 'ไม่พบข้อมูล'}), 404
        
        return jsonify({'profile': dict(profile)}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/profile', methods=['PUT'])
@login_required
def update_reseller_profile():
    """Update reseller's profile with shipping info"""
    if session.get('role') != 'Reseller':
        return jsonify({'error': 'Reseller access only'}), 403
    
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE users
            SET phone = %s, email = %s, address = %s,
                province = %s, district = %s, subdistrict = %s, postal_code = %s,
                brand_name = %s, logo_url = %s
            WHERE id = %s
            RETURNING id, full_name, phone, email, address, province, district, subdistrict, postal_code, brand_name, logo_url
        ''', (
            data.get('phone'),
            data.get('email'),
            data.get('address'),
            data.get('province'),
            data.get('district'),
            data.get('subdistrict'),
            data.get('postal_code'),
            data.get('brand_name'),
            data.get('logo_url'),
            user_id
        ))
        
        profile = cursor.fetchone()
        conn.commit()
        
        return jsonify({'message': 'อัปเดตข้อมูลสำเร็จ', 'profile': dict(profile)}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER PRODUCT CATALOG ====================

@app.route('/api/reseller/products', methods=['GET'])
@login_required
def get_reseller_products():
    """Get products for reseller with tier pricing"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user's tier
        cursor.execute('''
            SELECT u.reseller_tier_id, rt.name as tier_name, rt.level_rank
            FROM users u
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        tier_id = user['reseller_tier_id'] if user else None
        
        # Get active products with tier pricing
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku, p.description, p.status,
                   b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT MIN(price) FROM skus WHERE product_id = p.id) as min_price,
                   (SELECT MAX(price) FROM skus WHERE product_id = p.id) as max_price,
                   (SELECT SUM(stock) FROM skus WHERE product_id = p.id) as total_stock,
                   (SELECT COUNT(*) FROM skus WHERE product_id = p.id) as sku_count,
                   ptp.discount_percent
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            WHERE p.status = 'active'
            ORDER BY p.created_at DESC
        ''', (tier_id,))
        
        products = []
        for row in cursor.fetchall():
            product = dict(row)
            product['min_price'] = float(product['min_price']) if product['min_price'] else 0
            product['max_price'] = float(product['max_price']) if product['max_price'] else 0
            product['discount_percent'] = float(product['discount_percent']) if product['discount_percent'] else 0
            
            # Calculate discounted prices
            if product['discount_percent'] > 0:
                product['discounted_min_price'] = round(product['min_price'] * (1 - product['discount_percent'] / 100), 2)
                product['discounted_max_price'] = round(product['max_price'] * (1 - product['discount_percent'] / 100), 2)
            else:
                product['discounted_min_price'] = product['min_price']
                product['discounted_max_price'] = product['max_price']
            
            products.append(product)
        
        return jsonify({
            'tier': user,
            'products': products
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/products/<int:product_id>', methods=['GET'])
@login_required
def get_reseller_product_detail(product_id):
    """Get product detail with SKUs and tier pricing for reseller"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user's tier
        cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        tier_id = user['reseller_tier_id'] if user else None
        
        # Get product
        cursor.execute('''
            SELECT p.*, b.name as brand_name, ptp.discount_percent
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            WHERE p.id = %s AND p.status = 'active'
        ''', (tier_id, product_id))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        product = dict(product)
        discount_percent = float(product['discount_percent']) if product['discount_percent'] else 0
        
        # Get images
        cursor.execute('''
            SELECT id, image_url, sort_order
            FROM product_images
            WHERE product_id = %s
            ORDER BY sort_order
        ''', (product_id,))
        product['images'] = [dict(row) for row in cursor.fetchall()]
        
        # Get SKUs with discounted prices
        cursor.execute('''
            SELECT s.id, s.sku_code, s.price, s.stock
            FROM skus s
            WHERE s.product_id = %s
            ORDER BY s.sku_code
        ''', (product_id,))
        
        skus = []
        for sku in cursor.fetchall():
            sku_dict = dict(sku)
            price = float(sku_dict['price']) if sku_dict['price'] else 0
            sku_dict['price'] = price
            sku_dict['discounted_price'] = round(price * (1 - discount_percent / 100), 2)
            sku_dict['discount_percent'] = discount_percent
            
            # Get SKU option values
            cursor.execute('''
                SELECT o.name as option_name, ov.value as option_value
                FROM sku_values_map svm
                JOIN option_values ov ON ov.id = svm.option_value_id
                JOIN options o ON o.id = ov.option_id
                WHERE svm.sku_id = %s
                ORDER BY o.id
            ''', (sku_dict['id'],))
            sku_dict['options'] = [dict(row) for row in cursor.fetchall()]
            
            skus.append(sku_dict)
        
        product['skus'] = skus
        product['discount_percent'] = discount_percent
        
        # Get options
        cursor.execute('''
            SELECT o.id, o.name,
                   ARRAY_AGG(
                       JSON_BUILD_OBJECT('id', ov.id, 'value', ov.value, 'sort_order', ov.sort_order)
                       ORDER BY ov.sort_order
                   ) as values
            FROM options o
            JOIN option_values ov ON ov.option_id = o.id
            WHERE o.product_id = %s
            GROUP BY o.id, o.name
            ORDER BY o.id
        ''', (product_id,))
        product['options'] = [dict(row) for row in cursor.fetchall()]
        
        # Get customizations
        cursor.execute('''
            SELECT pc.id, pc.name, pc.is_required, pc.allow_multiple, pc.sort_order
            FROM product_customizations pc
            WHERE pc.product_id = %s
            ORDER BY pc.sort_order
        ''', (product_id,))
        customizations = []
        for c in cursor.fetchall():
            c_dict = dict(c)
            cursor.execute('''
                SELECT id, label, extra_price, sort_order
                FROM customization_choices
                WHERE customization_id = %s
                ORDER BY sort_order
            ''', (c_dict['id'],))
            c_dict['choices'] = [dict(ch) for ch in cursor.fetchall()]
            for ch in c_dict['choices']:
                if ch['extra_price']:
                    ch['extra_price'] = float(ch['extra_price'])
            customizations.append(c_dict)
        product['customizations'] = customizations
        
        return jsonify(product), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER CART API ====================

@app.route('/api/reseller/cart', methods=['GET'])
@login_required
def get_reseller_cart():
    """Get current user's cart"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get or create active cart
        cursor.execute('''
            INSERT INTO carts (user_id, status) 
            VALUES (%s, 'active') 
            ON CONFLICT (user_id, status) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (user_id,))
        cart = cursor.fetchone()
        cart_id = cart['id']
        conn.commit()
        
        # Get cart items with product info
        cursor.execute('''
            SELECT ci.id, ci.sku_id, ci.quantity, ci.unit_price, ci.tier_discount_percent,
                   ci.customization_data,
                   s.sku_code, s.stock, p.name as product_name, p.id as product_id,
                   b.name as brand_name,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url
            FROM cart_items ci
            JOIN skus s ON s.id = ci.sku_id
            JOIN products p ON p.id = s.product_id
            LEFT JOIN brands b ON b.id = p.brand_id
            WHERE ci.cart_id = %s
            ORDER BY ci.created_at ASC
        ''', (cart_id,))
        
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            item['unit_price'] = float(item['unit_price']) if item['unit_price'] else 0
            item['tier_discount_percent'] = float(item['tier_discount_percent']) if item['tier_discount_percent'] else 0
            item['final_price'] = round(item['unit_price'] * (1 - item['tier_discount_percent']/100), 2)
            item['subtotal'] = round(item['final_price'] * item['quantity'], 2)
            
            # Get SKU variant options (e.g., Color: White, Size: XL)
            cursor.execute('''
                SELECT o.name as option_name, ov.value as option_value
                FROM sku_values_map svm
                JOIN option_values ov ON ov.id = svm.option_value_id
                JOIN options o ON o.id = ov.option_id
                WHERE svm.sku_id = %s
                ORDER BY o.id, ov.sort_order
            ''', (item['sku_id'],))
            sku_options = cursor.fetchall()
            item['sku_options'] = [dict(opt) for opt in sku_options]
            
            # Resolve customization_data IDs to names
            if item['customization_data']:
                cust_data = item['customization_data'] if isinstance(item['customization_data'], dict) else {}
                resolved_customizations = []
                for cust_id_str, choice_ids in cust_data.items():
                    try:
                        cust_id = int(cust_id_str)
                        # Get customization name
                        cursor.execute('SELECT name FROM product_customizations WHERE id = %s', (cust_id,))
                        cust_row = cursor.fetchone()
                        cust_name = cust_row['name'] if cust_row else f'Option {cust_id}'
                        
                        # Get choice labels
                        if choice_ids:
                            choice_id_list = choice_ids if isinstance(choice_ids, list) else [choice_ids]
                            for choice_id in choice_id_list:
                                cursor.execute('SELECT label FROM customization_choices WHERE id = %s', (choice_id,))
                                choice_row = cursor.fetchone()
                                choice_label = choice_row['label'] if choice_row else f'Choice {choice_id}'
                                resolved_customizations.append({'name': cust_name, 'value': choice_label})
                    except:
                        pass
                item['customizations'] = resolved_customizations
            else:
                item['customizations'] = []
            
            items.append(item)
        
        total = sum(item['subtotal'] for item in items)
        
        return jsonify({
            'cart_id': cart_id,
            'items': items,
            'total': total,
            'item_count': len(items)
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/cart', methods=['POST'])
@login_required
def reseller_add_to_cart():
    """Add item to cart for reseller"""
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
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user tier
        cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        tier_id = user['reseller_tier_id'] if user else None
        
        # Get SKU and product info
        cursor.execute('''
            SELECT s.id, s.price, s.stock, p.id as product_id, ptp.discount_percent
            FROM skus s
            JOIN products p ON p.id = s.product_id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            WHERE s.id = %s AND p.status = 'active'
        ''', (tier_id, sku_id))
        sku = cursor.fetchone()
        
        if not sku:
            return jsonify({'error': 'SKU not found or product inactive'}), 404
        
        if sku['stock'] < quantity:
            return jsonify({'error': f'Not enough stock (available: {sku["stock"]})'}), 400
        
        price = float(sku['price']) if sku['price'] else 0
        discount = float(sku['discount_percent']) if sku['discount_percent'] else 0
        
        # Get or create active cart
        cursor.execute('''
            INSERT INTO carts (user_id, status) 
            VALUES (%s, 'active') 
            ON CONFLICT (user_id, status) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (user_id,))
        cart = cursor.fetchone()
        cart_id = cart['id']
        
        # Add or update cart item
        cursor.execute('''
            INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent, customization_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (cart_id, sku_id) DO UPDATE SET 
                quantity = cart_items.quantity + EXCLUDED.quantity,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        ''', (cart_id, sku_id, quantity, price, discount, 
              json.dumps(customization_data) if customization_data else None))
        
        conn.commit()
        
        # Get updated cart count
        cursor.execute('SELECT COUNT(*) as count FROM cart_items WHERE cart_id = %s', (cart_id,))
        count = cursor.fetchone()['count']
        
        return jsonify({
            'success': True,
            'message': 'Added to cart',
            'cart_count': count
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/cart/<int:item_id>', methods=['PUT'])
@login_required
def reseller_update_cart_item(item_id):
    """Update cart item quantity for reseller"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        quantity = data.get('quantity', 1)
        
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
            return jsonify({'error': f'Not enough stock (available: {item["stock"]})'}), 400
        
        if quantity <= 0:
            cursor.execute('DELETE FROM cart_items WHERE id = %s', (item_id,))
        else:
            cursor.execute('UPDATE cart_items SET quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', 
                          (quantity, item_id))
        
        conn.commit()
        return jsonify({'success': True}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/cart/<int:item_id>', methods=['DELETE'])
@login_required
def reseller_remove_cart_item(item_id):
    """Remove item from cart for reseller"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Delete item if it belongs to user's cart
        cursor.execute('''
            DELETE FROM cart_items 
            WHERE id = %s AND cart_id IN (
                SELECT id FROM carts WHERE user_id = %s AND status = 'active'
            )
        ''', (item_id, user_id))
        
        conn.commit()
        return jsonify({'success': True}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/cart/count', methods=['GET'])
@login_required
def get_cart_count():
    """Get cart item count"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT COALESCE(SUM(ci.quantity), 0) as count
            FROM cart_items ci
            JOIN carts c ON c.id = ci.cart_id
            WHERE c.user_id = %s AND c.status = 'active'
        ''', (user_id,))
        result = cursor.fetchone()
        
        return jsonify({'count': int(result['count'])}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER MTO API ====================

@app.route('/api/reseller/mto/products', methods=['GET'])
@login_required
def get_reseller_mto_products():
    """Get MTO products for reseller catalog"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT p.id, p.name, p.description, p.product_type, p.production_days, 
                   p.min_order_qty, p.deposit_percent, p.status,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url
            FROM products p
            WHERE p.product_type = 'made_to_order' AND p.status = 'active'
            ORDER BY p.created_at DESC
        ''')
        products = cursor.fetchall()
        
        return jsonify([dict(p) for p in products]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/products/<int:product_id>/details', methods=['GET'])
@login_required
def get_reseller_mto_product_details(product_id):
    """Get MTO product with options and SKUs for matrix ordering"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get product
        cursor.execute('''
            SELECT id, name, parent_sku, production_days, deposit_percent
            FROM products
            WHERE id = %s AND product_type = 'made_to_order' AND status = 'active'
        ''', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        product = dict(product)
        
        # Get options with values (including min_order_qty)
        cursor.execute('SELECT id, name FROM options WHERE product_id = %s ORDER BY id', (product_id,))
        options = [dict(o) for o in cursor.fetchall()]
        
        for opt in options:
            cursor.execute('''
                SELECT id, value, min_order_qty
                FROM option_values
                WHERE option_id = %s
                ORDER BY sort_order
            ''', (opt['id'],))
            opt['values'] = [dict(v) for v in cursor.fetchall()]
        
        product['options'] = options
        
        # Get SKUs with option values
        cursor.execute('SELECT id, sku_code, price FROM skus WHERE product_id = %s ORDER BY id', (product_id,))
        skus = [dict(s) for s in cursor.fetchall()]
        
        for sku in skus:
            cursor.execute('''
                SELECT ov.id, ov.value, o.name as option_name, o.id as option_id
                FROM sku_values_map svm
                JOIN option_values ov ON svm.option_value_id = ov.id
                JOIN options o ON ov.option_id = o.id
                WHERE svm.sku_id = %s
            ''', (sku['id'],))
            sku['option_values'] = [dict(ov) for ov in cursor.fetchall()]
        
        product['skus'] = skus
        
        return jsonify(product), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/products/<int:product_id>/skus', methods=['GET'])
@login_required
def get_reseller_mto_product_skus(product_id):
    """Get SKUs for MTO product"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT s.id, s.sku_code, 
                   COALESCE((
                       SELECT string_agg(ov.value, ' / ' ORDER BY o.sort_order)
                       FROM sku_values_map svm
                       JOIN option_values ov ON ov.id = svm.option_value_id
                       JOIN options o ON o.id = ov.option_id
                       WHERE svm.sku_id = s.id
                   ), '') as variant_name
            FROM skus s
            WHERE s.product_id = %s
            ORDER BY s.sku_code
        ''', (product_id,))
        skus = cursor.fetchall()
        
        return jsonify([dict(s) for s in skus]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/quotation-requests', methods=['POST'])
@login_required
def create_reseller_quotation_request():
    """Create a new quotation request"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        product_id = data.get('product_id')
        items = data.get('items', [])
        notes = data.get('notes', '')
        
        if not product_id:
            return jsonify({'error': 'Product ID required'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get product info
        cursor.execute('SELECT id, name, production_days, min_order_qty, deposit_percent FROM products WHERE id = %s', (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Create quotation request
        cursor.execute('''
            INSERT INTO quotation_requests (reseller_id, product_id, notes, status, created_at)
            VALUES (%s, %s, %s, 'pending', NOW())
            RETURNING id
        ''', (user_id, product_id, notes))
        request_id = cursor.fetchone()['id']
        
        # Insert request items
        for item in items:
            sku_id = item.get('sku_id')
            quantity = item.get('quantity', 1)
            
            cursor.execute('''
                INSERT INTO quotation_request_items (request_id, sku_id, quantity)
                VALUES (%s, %s, %s)
            ''', (request_id, sku_id, quantity))
        
        conn.commit()
        
        return jsonify({'success': True, 'request_id': request_id}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/quotations', methods=['GET'])
@login_required
def get_reseller_quotations():
    """Get quotations for current reseller"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        status_filter = request.args.get('status')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = '''
            SELECT qr.id, qr.product_id, p.name as product_name, qr.notes, 
                   qr.status, qr.created_at,
                   q.id as quotation_id, q.total_amount, q.valid_until
            FROM quotation_requests qr
            JOIN products p ON p.id = qr.product_id
            LEFT JOIN quotations q ON q.request_id = qr.id
            WHERE qr.reseller_id = %s
        '''
        params = [user_id]
        
        if status_filter and status_filter != 'all':
            query += ' AND qr.status = %s'
            params.append(status_filter)
        
        query += ' ORDER BY qr.created_at DESC'
        
        cursor.execute(query, params)
        quotations = cursor.fetchall()
        
        # Get items for each quotation
        result = []
        for q in quotations:
            q_dict = dict(q)
            
            cursor.execute('''
                SELECT qri.sku_id, qri.quantity, s.sku_code,
                       COALESCE((
                           SELECT string_agg(ov.value, ' / ' ORDER BY o.sort_order)
                           FROM sku_values_map svm
                           JOIN option_values ov ON ov.id = svm.option_value_id
                           JOIN options o ON o.id = ov.option_id
                           WHERE svm.sku_id = s.id
                       ), '') as variant_name
                FROM quotation_request_items qri
                LEFT JOIN skus s ON s.id = qri.sku_id
                WHERE qri.request_id = %s
            ''', (q['id'],))
            q_dict['items'] = [dict(i) for i in cursor.fetchall()]
            result.append(q_dict)
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/quotations/<int:quotation_id>/accept', methods=['POST'])
@login_required
def accept_reseller_quotation(quotation_id):
    """Accept a quotation and create MTO order"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify quotation belongs to user
        cursor.execute('''
            SELECT qr.id as request_id, qr.product_id, q.total_amount, p.deposit_percent, p.production_days
            FROM quotation_requests qr
            JOIN quotations q ON q.request_id = qr.id
            JOIN products p ON p.id = qr.product_id
            WHERE qr.id = %s AND qr.reseller_id = %s AND qr.status = 'quoted'
        ''', (quotation_id, user_id))
        
        quotation = cursor.fetchone()
        if not quotation:
            return jsonify({'error': 'Quotation not found or not available'}), 404
        
        deposit_percent = quotation['deposit_percent'] or 50
        total_amount = quotation['total_amount']
        deposit_amount = round(total_amount * deposit_percent / 100, 2)
        balance_amount = round(total_amount - deposit_amount, 2)
        
        # Create MTO order
        cursor.execute('''
            INSERT INTO mto_orders (
                quotation_id, reseller_id, total_amount, deposit_percent, 
                deposit_amount, balance_amount, status, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'awaiting_deposit', NOW())
            RETURNING id
        ''', (quotation_id, user_id, total_amount, deposit_percent, deposit_amount, balance_amount))
        order_id = cursor.fetchone()['id']
        
        # Update quotation request status
        cursor.execute("UPDATE quotation_requests SET status = 'accepted' WHERE id = %s", (quotation_id,))
        
        conn.commit()
        
        return jsonify({'success': True, 'order_id': order_id}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/quotations/<int:quotation_id>/reject', methods=['POST'])
@login_required
def reject_reseller_quotation(quotation_id):
    """Reject a quotation"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            UPDATE quotation_requests 
            SET status = 'rejected'
            WHERE id = %s AND reseller_id = %s AND status = 'quoted'
            RETURNING id
        ''', (quotation_id, user_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'Quotation not found'}), 404
        
        conn.commit()
        return jsonify({'success': True}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/orders', methods=['GET'])
@login_required
def get_reseller_mto_orders():
    """Get MTO orders for current reseller"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        status_filter = request.args.get('status')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = '''
            SELECT mo.*, 
                   p.name as product_name, p.production_days,
                   CONCAT('MTO-', LPAD(mo.id::text, 6, '0')) as mto_order_number
            FROM mto_orders mo
            JOIN quotation_requests qr ON qr.id = mo.quotation_id
            JOIN products p ON p.id = qr.product_id
            WHERE mo.reseller_id = %s
        '''
        params = [user_id]
        
        if status_filter and status_filter != 'all':
            query += ' AND mo.status = %s'
            params.append(status_filter)
        
        query += ' ORDER BY mo.created_at DESC'
        
        cursor.execute(query, params)
        orders = cursor.fetchall()
        
        return jsonify([dict(o) for o in orders]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/orders/<int:order_id>/qr-code', methods=['GET'])
@login_required
def get_mto_order_qr_code(order_id):
    """Generate PromptPay QR code for MTO payment"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        payment_type = request.args.get('payment_type', 'deposit')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT deposit_amount, balance_amount
            FROM mto_orders
            WHERE id = %s AND reseller_id = %s
        ''', (order_id, user_id))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        amount = order['deposit_amount'] if payment_type == 'deposit' else order['balance_amount']
        
        # Generate PromptPay QR (using existing function if available)
        import qrcode
        import io
        import base64
        
        qr_data = f"00020101021129370016A000000677010111011300669000000005802TH530376454{len(str(int(amount * 100)))}{int(amount * 100)}6304"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({'qr_code': f'data:image/png;base64,{img_str}'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/reseller/mto/orders/<int:order_id>/payment', methods=['POST'])
@login_required
def reseller_submit_mto_payment(order_id):
    """Submit payment slip for MTO order (Reseller)"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        payment_type = request.form.get('payment_type', 'deposit')
        
        if 'slip' not in request.files:
            return jsonify({'error': 'No slip file uploaded'}), 400
        
        slip_file = request.files['slip']
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify order belongs to user
        cursor.execute('SELECT id, status FROM mto_orders WHERE id = %s AND reseller_id = %s', (order_id, user_id))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        # Upload slip (using object storage or save locally)
        import uuid
        import os
        filename = f"mto_slip_{order_id}_{payment_type}_{uuid.uuid4().hex[:8]}.png"
        upload_folder = 'static/uploads/mto_slips'
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        slip_file.save(filepath)
        slip_url = f'/static/uploads/mto_slips/{filename}'
        
        # Create payment record
        amount = 0
        cursor.execute('SELECT deposit_amount, balance_amount FROM mto_orders WHERE id = %s', (order_id,))
        amounts = cursor.fetchone()
        amount = amounts['deposit_amount'] if payment_type == 'deposit' else amounts['balance_amount']
        
        cursor.execute('''
            INSERT INTO mto_payments (mto_order_id, payment_type, amount, slip_image_url, status, created_at)
            VALUES (%s, %s, %s, %s, 'pending', NOW())
            RETURNING id
        ''', (order_id, payment_type, amount, slip_url))
        
        # Update order status
        new_status = 'deposit_pending' if payment_type == 'deposit' else 'balance_pending'
        cursor.execute('UPDATE mto_orders SET status = %s WHERE id = %s', (new_status, order_id))
        
        conn.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER PAGES ====================

@app.route('/reseller')
@login_required
def reseller_spa_root():
    """Reseller SPA root"""
    return render_template('reseller_spa.html')

@app.route('/reseller/dashboard')
@login_required
def reseller_dashboard_page():
    """Reseller dashboard SPA"""
    return render_template('reseller_spa.html')

@app.route('/reseller/catalog')
@login_required
def reseller_catalog_page():
    """Redirect to SPA with catalog hash"""
    return redirect('/dashboard#catalog')

@app.route('/reseller/cart')
@login_required
def reseller_cart_page():
    """Redirect to SPA with cart hash"""
    return redirect('/dashboard#cart')

@app.route('/reseller/checkout')
@login_required
def reseller_checkout_page():
    """Reseller checkout page"""
    return render_template('reseller_checkout.html')

@app.route('/reseller/orders')
@login_required
def reseller_orders_page():
    """Redirect to SPA with orders hash"""
    return redirect('/dashboard#orders')

@app.route('/reseller/customers')
@login_required
def reseller_customers_page():
    """Redirect to SPA with customers hash"""
    return redirect('/dashboard#customers')

@app.route('/reseller/profile')
@login_required
def reseller_profile_page():
    """Redirect to SPA with profile hash"""
    return redirect('/dashboard#profile')

# ==================== ORDER API ====================

import uuid

def generate_order_number(cursor):
    """Generate unique order number in format PREFIX-YYMM-XXXX"""
    from datetime import datetime
    
    # Get current period (YYMM)
    current_period = datetime.now().strftime('%y%m')
    
    # Get settings from database
    cursor.execute('SELECT prefix, digit_count, current_sequence, current_period FROM order_number_settings LIMIT 1')
    settings = cursor.fetchone()
    
    if settings:
        prefix = settings['prefix']
        digit_count = settings['digit_count']
        last_sequence = settings['current_sequence']
        last_period = settings['current_period']
        
        # Check if period changed (new month) - reset sequence
        if last_period != current_period:
            new_sequence = 1
        else:
            new_sequence = last_sequence + 1
        
        # Update settings with new sequence and period
        cursor.execute('''
            UPDATE order_number_settings 
            SET current_sequence = %s, current_period = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = (SELECT id FROM order_number_settings LIMIT 1)
        ''', (new_sequence, current_period))
    else:
        # Default fallback
        prefix = 'ORD'
        digit_count = 4
        new_sequence = 1
        cursor.execute('''
            INSERT INTO order_number_settings (prefix, format_type, digit_count, current_sequence, current_period)
            VALUES (%s, 'YYMM', %s, %s, %s)
        ''', (prefix, digit_count, new_sequence, current_period))
    
    # Format sequence with leading zeros
    sequence_str = str(new_sequence).zfill(digit_count)
    
    return f'{prefix}-{current_period}-{sequence_str}'

@app.route('/api/orders', methods=['POST'])
@login_required
def create_order():
    """Create order from cart with automatic shipment splitting by warehouse"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        notes = data.get('notes', '')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user's active cart with items
        cursor.execute('''
            SELECT c.id as cart_id
            FROM carts c
            WHERE c.user_id = %s AND c.status = 'active'
        ''', (user_id,))
        cart = cursor.fetchone()
        
        if not cart:
            return jsonify({'error': 'Cart not found'}), 404
        
        # Get cart items
        cursor.execute('''
            SELECT ci.id, ci.sku_id, ci.quantity, ci.unit_price, ci.tier_discount_percent, ci.customization_data,
                   s.stock, s.sku_code, p.name as product_name
            FROM cart_items ci
            JOIN skus s ON s.id = ci.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE ci.cart_id = %s
        ''', (cart['cart_id'],))
        items = cursor.fetchall()
        
        if not items:
            return jsonify({'error': 'Cart is empty'}), 400
        
        # Get all sku_ids from cart
        sku_ids = [item['sku_id'] for item in items]
        
        # Get warehouse stock for all SKUs
        cursor.execute('''
            SELECT sws.sku_id, sws.warehouse_id, sws.stock, w.name as warehouse_name, w.is_active
            FROM sku_warehouse_stock sws
            JOIN warehouses w ON w.id = sws.warehouse_id
            WHERE sws.sku_id = ANY(%s) AND sws.stock > 0 AND w.is_active = TRUE
            ORDER BY sws.warehouse_id, sws.sku_id
        ''', (sku_ids,))
        warehouse_stocks = cursor.fetchall()
        
        # Build a lookup: {sku_id: [{warehouse_id, stock, warehouse_name}, ...]}
        sku_warehouse_map = {}
        for ws in warehouse_stocks:
            sku_id = ws['sku_id']
            if sku_id not in sku_warehouse_map:
                sku_warehouse_map[sku_id] = []
            sku_warehouse_map[sku_id].append({
                'warehouse_id': ws['warehouse_id'],
                'stock': ws['stock'],
                'warehouse_name': ws['warehouse_name']
            })
        
        # Calculate total available stock per SKU (from all warehouses)
        for item in items:
            total_available = sum(ws['stock'] for ws in sku_warehouse_map.get(item['sku_id'], []))
            if total_available < item['quantity']:
                return jsonify({
                    'error': f'สินค้า {item["product_name"]} ({item["sku_code"]}) สต็อกไม่พอ เหลือ {total_available} ชิ้น'
                }), 400
        
        # Calculate totals
        total_amount = 0
        total_discount = 0
        for item in items:
            unit_price = float(item['unit_price'])
            discount_pct = float(item['tier_discount_percent'] or 0)
            discounted_price = unit_price * (1 - discount_pct / 100)
            total_amount += unit_price * item['quantity']
            total_discount += (unit_price - discounted_price) * item['quantity']
        
        final_amount = total_amount - total_discount
        
        # Get default online channel
        cursor.execute("SELECT id FROM sales_channels WHERE name = 'ระบบออนไลน์' LIMIT 1")
        channel = cursor.fetchone()
        channel_id = channel['id'] if channel else None
        
        # Get customer_id if provided
        customer_id = data.get('customer_id')
        
        # Create order with new order number format (ORD-YYMM-XXXX)
        order_number = generate_order_number(cursor)
        cursor.execute('''
            INSERT INTO orders (order_number, user_id, channel_id, status, total_amount, discount_amount, final_amount, notes, customer_id)
            VALUES (%s, %s, %s, 'pending_payment', %s, %s, %s, %s, %s)
            RETURNING id, order_number, status, final_amount, created_at
        ''', (order_number, user_id, channel_id, total_amount, total_discount, final_amount, notes, customer_id))
        order = dict(cursor.fetchone())
        
        # Create order items and track their IDs using cart_item_id as unique key
        order_item_map = {}  # {cart_item_id: order_item_id}
        for item in items:
            unit_price = float(item['unit_price'])
            discount_pct = float(item['tier_discount_percent'] or 0)
            discounted_price = round(unit_price * (1 - discount_pct / 100), 2)
            
            # Convert customization_data to JSON string if it's a dict
            cust_data = item['customization_data']
            if isinstance(cust_data, dict):
                cust_data = json.dumps(cust_data)
            
            discount_amount = round(unit_price * discount_pct / 100, 2)
            subtotal = round(discounted_price * item['quantity'], 2)
            
            cursor.execute('''
                INSERT INTO order_items (order_id, sku_id, product_name, sku_code, quantity, unit_price, tier_discount_percent, discount_amount, subtotal, customization_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (order['id'], item['sku_id'], item['product_name'], item['sku_code'], item['quantity'], unit_price, discount_pct, discount_amount, subtotal, cust_data))
            order_item_id = cursor.fetchone()['id']
            
            # Use cart item id as unique key (guaranteed unique per cart item)
            order_item_map[item['id']] = order_item_id
        
        # Re-allocate items to warehouses using cart_item_id for accurate tracking
        warehouse_shipments = {}  # {warehouse_id: {shipment items grouped by order_item_id}}
        stock_deductions = []  # Track deductions: [(sku_id, warehouse_id, quantity)]
        
        for item in items:
            remaining_qty = item['quantity']
            warehouses_for_sku = sku_warehouse_map.get(item['sku_id'], [])
            order_item_id = order_item_map[item['id']]
            
            for wh in warehouses_for_sku:
                if remaining_qty <= 0:
                    break
                
                allocate_qty = min(remaining_qty, wh['stock'])
                if allocate_qty > 0:
                    wh_id = wh['warehouse_id']
                    if wh_id not in warehouse_shipments:
                        warehouse_shipments[wh_id] = []
                    
                    warehouse_shipments[wh_id].append({
                        'order_item_id': order_item_id,
                        'quantity': allocate_qty
                    })
                    
                    stock_deductions.append((item['sku_id'], wh_id, allocate_qty))
                    wh['stock'] -= allocate_qty
                    remaining_qty -= allocate_qty
        
        # Create shipments per warehouse
        for wh_id, shipment_items in warehouse_shipments.items():
            cursor.execute('''
                INSERT INTO order_shipments (order_id, warehouse_id, status)
                VALUES (%s, %s, 'pending')
                RETURNING id
            ''', (order['id'], wh_id))
            shipment_id = cursor.fetchone()['id']
            
            # Create shipment items with verified order_item_ids
            for ship_item in shipment_items:
                cursor.execute('''
                    INSERT INTO order_shipment_items (shipment_id, order_item_id, quantity)
                    VALUES (%s, %s, %s)
                ''', (shipment_id, ship_item['order_item_id'], ship_item['quantity']))
        
        # Deduct stock from warehouses
        for sku_id, wh_id, qty in stock_deductions:
            cursor.execute('''
                UPDATE sku_warehouse_stock
                SET stock = stock - %s
                WHERE sku_id = %s AND warehouse_id = %s
            ''', (qty, sku_id, wh_id))
        
        # Also update the main SKU stock in skus table
        for item in items:
            cursor.execute('''
                UPDATE skus SET stock = stock - %s WHERE id = %s
            ''', (item['quantity'], item['sku_id']))
        
        # Clear cart items
        cursor.execute('DELETE FROM cart_items WHERE cart_id = %s', (cart['cart_id'],))
        
        conn.commit()
        
        # Add shipment count to response
        order['shipment_count'] = len(warehouse_shipments)
        
        # Send email notification to admin
        reseller_name = session.get('full_name', 'Unknown')
        send_order_notification_to_admin(
            order['order_number'], 
            reseller_name, 
            float(order['final_amount']), 
            len(items)
        )
        
        # Send push notification to admins
        try:
            fmt_amount = f"{float(order['final_amount']):,.0f}"
            send_push_to_admins(
                '🛒 ออเดอร์ใหม่!',
                f'{reseller_name} สั่งซื้อ {order["order_number"]} (฿{fmt_amount})',
                url='/admin#orders',
                tag=f'order-{order["id"]}'
            )
        except Exception:
            pass
        
        return jsonify({
            'message': 'Order created successfully',
            'order': order
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/orders', methods=['GET'])
@login_required
def get_user_orders():
    """Get orders for current user"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        status_filter = request.args.get('status')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = '''
            SELECT o.id, o.order_number, o.status, o.total_amount, o.discount_amount, 
                   o.final_amount, o.notes, o.created_at, o.updated_at,
                   sc.name as channel_name,
                   (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
            FROM orders o
            LEFT JOIN sales_channels sc ON sc.id = o.channel_id
            WHERE o.user_id = %s
        '''
        params = [user_id]
        
        if status_filter:
            query += ' AND o.status = %s'
            params.append(status_filter)
        
        query += ' ORDER BY o.created_at DESC'
        
        cursor.execute(query, params)
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order['total_amount'] = float(order['total_amount']) if order['total_amount'] else 0
            order['discount_amount'] = float(order['discount_amount']) if order['discount_amount'] else 0
            order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
            orders.append(order)
        
        return jsonify(orders), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/orders/<int:order_id>', methods=['GET'])
@login_required
def get_order_detail(order_id):
    """Get order detail"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        user_role = session.get('role')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order (check ownership for non-admins)
        query = '''
            SELECT o.*, sc.name as channel_name, 
                   u.full_name as reseller_name, u.username as reseller_username,
                   u.phone as reseller_phone, u.email as reseller_email,
                   u.address as reseller_address, u.province as reseller_province,
                   u.district as reseller_district, u.subdistrict as reseller_subdistrict,
                   u.postal_code as reseller_postal_code, u.brand_name as reseller_brand_name,
                   rt.name as reseller_tier_name
            FROM orders o
            LEFT JOIN sales_channels sc ON sc.id = o.channel_id
            LEFT JOIN users u ON u.id = o.user_id
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE o.id = %s
        '''
        if user_role not in ['Super Admin', 'Assistant Admin']:
            query += ' AND o.user_id = %s'
            cursor.execute(query, (order_id, user_id))
        else:
            cursor.execute(query, (order_id,))
        
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        order = dict(order)
        order['total_amount'] = float(order['total_amount']) if order['total_amount'] else 0
        order['discount_amount'] = float(order['discount_amount']) if order['discount_amount'] else 0
        order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
        
        # Get order items with variant names
        cursor.execute('''
            SELECT oi.*, s.sku_code, p.name as product_name, p.parent_sku,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM order_items oi
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE oi.order_id = %s
        ''', (order_id,))
        
        items = []
        for item in cursor.fetchall():
            item_dict = dict(item)
            item_dict['unit_price'] = float(item_dict['unit_price']) if item_dict['unit_price'] else 0
            item_dict['subtotal'] = float(item_dict['subtotal']) if item_dict['subtotal'] else 0
            item_dict['tier_discount_percent'] = float(item_dict['tier_discount_percent']) if item_dict['tier_discount_percent'] else 0
            item_dict['discount_amount'] = float(item_dict['discount_amount']) if item_dict['discount_amount'] else 0
            # Get variant name (option values) for this SKU
            cursor.execute('''
                SELECT ov.value as option_value
                FROM sku_values_map svm
                JOIN option_values ov ON ov.id = svm.option_value_id
                JOIN options o ON o.id = ov.option_id
                WHERE svm.sku_id = %s
                ORDER BY o.id
            ''', (item_dict['sku_id'],))
            option_values = cursor.fetchall()
            item_dict['variant_name'] = ' - '.join([ov['option_value'] for ov in option_values]) if option_values else ''
            
            # Get customization labels if customization_data exists
            customization_labels = []
            if item_dict.get('customization_data'):
                cust_data = item_dict['customization_data']
                if isinstance(cust_data, str):
                    import json
                    cust_data = json.loads(cust_data)
                if isinstance(cust_data, dict):
                    choice_ids = []
                    for cust_id, choices in cust_data.items():
                        if isinstance(choices, list):
                            choice_ids.extend(choices)
                    if choice_ids:
                        cursor.execute('''
                            SELECT pc.name as customization_name, cc.label as choice_label
                            FROM customization_choices cc
                            JOIN product_customizations pc ON pc.id = cc.customization_id
                            WHERE cc.id = ANY(%s)
                        ''', (choice_ids,))
                        for row in cursor.fetchall():
                            customization_labels.append(f"{row['customization_name']}: {row['choice_label']}")
            item_dict['customization_labels'] = customization_labels
            items.append(item_dict)
        
        order['items'] = items
        
        # Get payment slips
        cursor.execute('''
            SELECT id, slip_image_url, amount, status, admin_notes, created_at
            FROM payment_slips
            WHERE order_id = %s
            ORDER BY created_at DESC
        ''', (order_id,))
        order['payment_slips'] = [dict(s) for s in cursor.fetchall()]
        
        # Get shipping providers tracking URL mapping
        cursor.execute('SELECT name, tracking_url FROM shipping_providers WHERE is_active = TRUE')
        provider_tracking_map = {p['name']: p['tracking_url'] for p in cursor.fetchall()}
        
        # Get shipments with warehouse info
        cursor.execute('''
            SELECT os.id, os.warehouse_id, os.tracking_number, os.shipping_provider,
                   os.status, os.shipped_at, os.delivered_at, os.created_at,
                   w.name as warehouse_name
            FROM order_shipments os
            JOIN warehouses w ON w.id = os.warehouse_id
            WHERE os.order_id = %s
            ORDER BY os.id
        ''', (order_id,))
        shipments = []
        for shipment in cursor.fetchall():
            shipment_dict = dict(shipment)
            # Add tracking URL if available
            if shipment_dict.get('shipping_provider') and shipment_dict.get('tracking_number'):
                tracking_template = provider_tracking_map.get(shipment_dict['shipping_provider'], '')
                if tracking_template:
                    shipment_dict['tracking_url'] = tracking_template.replace('{tracking}', shipment_dict['tracking_number'])
            # Get items in this shipment with option values
            cursor.execute('''
                SELECT osi.id, osi.order_item_id, osi.quantity,
                       oi.sku_id, s.sku_code, p.name as product_name
                FROM order_shipment_items osi
                JOIN order_items oi ON oi.id = osi.order_item_id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE osi.shipment_id = %s
            ''', (shipment_dict['id'],))
            shipment_items = []
            for item in cursor.fetchall():
                item_dict = dict(item)
                # Get option values for this SKU
                cursor.execute('''
                    SELECT o.name as option_name, ov.value as option_value
                    FROM sku_values_map svm
                    JOIN option_values ov ON ov.id = svm.option_value_id
                    JOIN options o ON o.id = ov.option_id
                    WHERE svm.sku_id = %s
                    ORDER BY o.id
                ''', (item_dict['sku_id'],))
                option_values = cursor.fetchall()
                item_dict['variant_name'] = ' - '.join([ov['option_value'] for ov in option_values]) if option_values else ''
                
                # Get customization labels from order_items
                cursor.execute('SELECT customization_data FROM order_items WHERE id = %s', (item_dict['order_item_id'],))
                oi_row = cursor.fetchone()
                customization_labels = []
                if oi_row and oi_row.get('customization_data'):
                    cust_data = oi_row['customization_data']
                    if isinstance(cust_data, str):
                        cust_data = json.loads(cust_data)
                    if isinstance(cust_data, dict):
                        choice_ids = []
                        for cust_id, choices in cust_data.items():
                            if isinstance(choices, list):
                                choice_ids.extend(choices)
                        if choice_ids:
                            cursor.execute('''
                                SELECT pc.name as customization_name, cc.label as choice_label
                                FROM customization_choices cc
                                JOIN product_customizations pc ON pc.id = cc.customization_id
                                WHERE cc.id = ANY(%s)
                            ''', (choice_ids,))
                            for row in cursor.fetchall():
                                customization_labels.append(f"{row['customization_name']}: {row['choice_label']}")
                item_dict['customization_labels'] = customization_labels
                shipment_items.append(item_dict)
            shipment_dict['items'] = shipment_items
            shipments.append(shipment_dict)
        
        order['shipments'] = shipments
        
        # Get customer info if exists (reseller's customer)
        if order.get('customer_id'):
            cursor.execute('''
                SELECT full_name, phone, email, address, province, district, subdistrict, postal_code
                FROM reseller_customers WHERE id = %s
            ''', (order['customer_id'],))
            customer = cursor.fetchone()
            if customer:
                order['customer'] = dict(customer)
        
        # Get shipping provider tracking URLs
        cursor.execute('SELECT name, tracking_url FROM shipping_providers WHERE is_active = TRUE')
        tracking_urls = {p['name']: p['tracking_url'] for p in cursor.fetchall()}
        order['tracking_urls'] = tracking_urls
        
        return jsonify(order), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/orders/<int:order_id>/shipments/<int:shipment_id>', methods=['PATCH'])
@admin_required
def update_shipment(order_id, shipment_id):
    """Update shipment tracking and status"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify shipment exists and belongs to this order
        cursor.execute('''
            SELECT id, status FROM order_shipments
            WHERE id = %s AND order_id = %s
        ''', (shipment_id, order_id))
        shipment = cursor.fetchone()
        
        if not shipment:
            return jsonify({'error': 'Shipment not found'}), 404
        
        # Build update query
        update_fields = []
        update_values = []
        
        if 'tracking_number' in data:
            update_fields.append('tracking_number = %s')
            update_values.append(data['tracking_number'])
        
        if 'shipping_provider' in data:
            update_fields.append('shipping_provider = %s')
            update_values.append(data['shipping_provider'])
        
        if 'status' in data:
            update_fields.append('status = %s')
            update_values.append(data['status'])
            
            # Set timestamps based on status
            if data['status'] == 'shipped' and shipment['status'] != 'shipped':
                update_fields.append('shipped_at = CURRENT_TIMESTAMP')
            elif data['status'] == 'delivered' and shipment['status'] != 'delivered':
                update_fields.append('delivered_at = CURRENT_TIMESTAMP')
        
        if not update_fields:
            return jsonify({'error': 'ไม่มีข้อมูลที่ต้องการอัพเดท'}), 400
        
        update_values.append(shipment_id)
        cursor.execute(f'''
            UPDATE order_shipments SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING id, tracking_number, shipping_provider, status, shipped_at, delivered_at
        ''', update_values)
        
        updated = dict(cursor.fetchone())
        
        # Check if all shipments are delivered -> update order status and trigger tier upgrade
        # Only process if shipment was NOT already delivered (idempotency check)
        if updated['status'] == 'delivered' and shipment['status'] != 'delivered':
            cursor.execute('''
                SELECT COUNT(*) as total, 
                       COUNT(CASE WHEN status = 'delivered' THEN 1 END) as delivered_count
                FROM order_shipments WHERE order_id = %s
            ''', (order_id,))
            shipment_stats = cursor.fetchone()
            
            if shipment_stats['total'] == shipment_stats['delivered_count']:
                # Check if order is already delivered (idempotency)
                cursor.execute('SELECT status FROM orders WHERE id = %s', (order_id,))
                current_order_status = cursor.fetchone()
                
                if current_order_status and current_order_status['status'] != 'delivered':
                    # All shipments delivered - update order status
                    cursor.execute('''
                        UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING user_id, final_amount
                    ''', (order_id,))
                    order_data = cursor.fetchone()
                    
                    if order_data:
                        # Trigger tier upgrade for reseller
                        user_id = order_data['user_id']
                        order_amount = float(order_data['final_amount'] or 0)
                        
                        # Get user info
                        cursor.execute('''
                            SELECT u.id, u.total_purchases, u.reseller_tier_id, u.tier_manual_override, r.name as role_name
                            FROM users u
                            JOIN roles r ON r.id = u.role_id
                            WHERE u.id = %s
                        ''', (user_id,))
                        user = cursor.fetchone()
                        
                        if user and user['role_name'] == 'Reseller':
                            new_total = float(user['total_purchases'] or 0) + order_amount
                            
                            # Update total_purchases
                            cursor.execute('''
                                UPDATE users SET total_purchases = %s WHERE id = %s
                            ''', (new_total, user_id))
                            
                            # Check tier upgrade if not manual override
                            if not user.get('tier_manual_override'):
                                cursor.execute('''
                                    SELECT id, name, upgrade_threshold 
                                    FROM reseller_tiers 
                                    WHERE upgrade_threshold <= %s AND is_manual_only = FALSE
                                    ORDER BY upgrade_threshold DESC LIMIT 1
                                ''', (new_total,))
                                new_tier = cursor.fetchone()
                                
                                if new_tier and new_tier['id'] != user['reseller_tier_id']:
                                    cursor.execute('''
                                        UPDATE users SET reseller_tier_id = %s WHERE id = %s
                                    ''', (new_tier['id'], user_id))
        
        # Check if any shipment is shipped -> update order status to shipped
        elif data.get('status') == 'shipped':
            cursor.execute('''
                SELECT status FROM orders WHERE id = %s
            ''', (order_id,))
            current_order = cursor.fetchone()
            
            if current_order and current_order['status'] == 'paid':
                cursor.execute('''
                    UPDATE orders SET status = 'shipped', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (order_id,))
        
        conn.commit()
        
        # Send email notification for shipped/delivered status
        if data.get('status') in ['shipped', 'delivered']:
            try:
                cursor.execute('''
                    SELECT u.full_name, u.email, u.id as user_id, o.order_number 
                    FROM users u 
                    JOIN orders o ON o.user_id = u.id 
                    WHERE o.id = %s
                ''', (order_id,))
                reseller_info = cursor.fetchone()
                if reseller_info and reseller_info['email']:
                    if data['status'] == 'shipped':
                        tracking_info = f"เลขพัสดุ: {updated.get('tracking_number', '-')} | ขนส่ง: {updated.get('shipping_provider', '-')}"
                        send_order_status_email(
                            reseller_info['email'],
                            reseller_info['full_name'],
                            reseller_info['order_number'] or f'#{order_id}',
                            'shipped',
                            'สินค้าของคุณถูกจัดส่งแล้ว',
                            tracking_info
                        )
                        try:
                            send_order_status_chat(reseller_info['user_id'], reseller_info['order_number'] or f'#{order_id}', 'shipped', tracking_info)
                        except Exception as chat_err:
                            print(f"Chat notification error: {chat_err}")
                    elif data['status'] == 'delivered':
                        send_order_status_email(
                            reseller_info['email'],
                            reseller_info['full_name'],
                            reseller_info['order_number'] or f'#{order_id}',
                            'delivered',
                            'สินค้าของคุณถูกส่งถึงปลายทางเรียบร้อยแล้ว'
                        )
                        try:
                            send_order_status_chat(reseller_info['user_id'], reseller_info['order_number'] or f'#{order_id}', 'delivered')
                        except Exception as chat_err:
                            print(f"Chat notification error: {chat_err}")
            except Exception as email_err:
                print(f"Email notification error: {email_err}")
        
        return jsonify({
            'message': 'Shipment updated successfully',
            'shipment': updated
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/orders/<int:order_id>/payment-slip', methods=['POST'])
@app.route('/api/orders/<int:order_id>/payment-slips', methods=['POST'])
@login_required
def upload_payment_slip(order_id):
    """Upload payment slip for order (supports both file upload and JSON URL)"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        
        slip_image_url = None
        amount = None
        
        if request.content_type and 'multipart/form-data' in request.content_type:
            slip_file = request.files.get('slip_image')
            amount = request.form.get('amount')
            
            if slip_file and slip_file.filename:
                allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'}
                original_ext = slip_file.filename.rsplit('.', 1)[-1].lower() if '.' in slip_file.filename else 'jpg'
                if original_ext not in allowed_ext:
                    return jsonify({'error': 'ไฟล์ไม่รองรับ กรุณาอัปโหลดรูปภาพ'}), 400
                
                upload_folder = os.path.join('static', 'uploads', 'slips')
                os.makedirs(upload_folder, exist_ok=True)
                
                import time as time_module
                filename = f"slip_{order_id}_{int(time_module.time())}_{user_id}.{original_ext}"
                file_path = os.path.join(upload_folder, filename)
                slip_file.save(file_path)
                slip_image_url = f'/{file_path}'
            else:
                return jsonify({'error': 'กรุณาเลือกรูปสลิป'}), 400
        else:
            data = request.get_json() or {}
            slip_image_url = data.get('slip_image_url')
            amount = data.get('amount')
        
        if not slip_image_url:
            return jsonify({'error': 'กรุณาแนบรูปสลิปการชำระเงิน'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, status, final_amount, order_number FROM orders
            WHERE id = %s AND user_id = %s
        ''', (order_id, user_id))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] not in ['pending_payment', 'rejected']:
            return jsonify({'error': 'ไม่สามารถอัปโหลดสลิปสำหรับสถานะนี้ได้'}), 400
        
        cursor.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
        ''', (order_id, slip_image_url, amount or order['final_amount']))
        
        cursor.execute('''
            UPDATE orders SET status = 'under_review', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (order_id,))
        
        conn.commit()
        
        cursor.execute("SELECT id FROM users WHERE role_id IN (SELECT id FROM roles WHERE name IN ('Super Admin', 'Assistant Admin'))")
        admins = cursor.fetchall()
        order_num = order.get('order_number') or f'#{order_id}'
        
        cursor.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
        reseller = cursor.fetchone()
        reseller_name = reseller['full_name'] if reseller else 'Reseller'
        
        for admin in admins:
            create_notification(
                admin['id'],
                'สลิปการชำระเงินใหม่',
                f'{reseller_name} อัปโหลดสลิป คำสั่งซื้อ {order_num}',
                'payment',
                'order',
                order_id
            )
            try:
                send_push_notification(
                    admin['id'],
                    '🧾 สลิปใหม่รอตรวจสอบ',
                    f'{reseller_name} อัปโหลดสลิป {order_num}',
                    url='/admin#slip-review',
                    tag=f'slip-{order_id}'
                )
            except Exception as push_err:
                print(f"[PUSH] Admin push error: {push_err}")
        
        try:
            send_order_status_chat(user_id, order_num, 'slip_uploaded')
        except Exception as chat_err:
            print(f"[CHAT] Slip upload chat notification error: {chat_err}")
        
        return jsonify({'message': 'อัปโหลดสลิปสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[SLIP] Error uploading payment slip: {e}")
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัปโหลดสลิป กรุณาลองใหม่'}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ADMIN DASHBOARD STATISTICS ====================

@app.route('/api/admin/dashboard-stats', methods=['GET'])
@admin_required
def get_dashboard_stats():
    """Get dashboard statistics for admin home page"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_role = session.get('role')
        user_id = session.get('user_id')
        
        # Get brand filter for Assistant Admin
        brand_ids = None
        brand_ids_tuple = None
        is_assistant_admin = user_role == 'Assistant Admin'
        if is_assistant_admin:
            cursor.execute('SELECT brand_id FROM admin_brand_access WHERE user_id = %s', (user_id,))
            brand_ids = [row['brand_id'] for row in cursor.fetchall()]
            # If Assistant Admin has no brands assigned, return empty stats
            if not brand_ids:
                return jsonify({
                    'sales_today': {'total': 0, 'count': 0},
                    'sales_month': {'total': 0, 'count': 0},
                    'sales_all': {'total': 0, 'count': 0},
                    'orders_today': 0,
                    'pending_orders': 0,
                    'low_stock': 0,
                    'low_stock_skus': 0,
                    'out_of_stock': 0,
                    'out_of_stock_skus': 0,
                    'sales_7_days': [],
                    'recent_orders': [],
                    'top_products': []
                }), 200
            brand_ids_tuple = tuple(brand_ids)
        
        # Today's date range
        cursor.execute("SELECT CURRENT_DATE as today")
        today = cursor.fetchone()['today']
        
        # Sales today (paid orders - filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid' 
                AND DATE(o.paid_at) = %s
                AND p.brand_id IN %s
            ''', (today, brand_ids_tuple))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE status = 'paid' 
                AND DATE(paid_at) = %s
            ''', (today,))
        sales_today = cursor.fetchone()
        
        # Sales this month
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid' 
                AND EXTRACT(YEAR FROM o.paid_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND EXTRACT(MONTH FROM o.paid_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE status = 'paid' 
                AND EXTRACT(YEAR FROM paid_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND EXTRACT(MONTH FROM paid_at) = EXTRACT(MONTH FROM CURRENT_DATE)
            ''')
        sales_month = cursor.fetchone()
        
        # All time sales
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid'
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE status = 'paid'
            ''')
        sales_all = cursor.fetchone()
        
        # Orders today (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE DATE(o.created_at) = %s
                AND p.brand_id IN %s
            ''', (today, brand_ids_tuple))
        else:
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM orders 
                WHERE DATE(created_at) = %s
            ''', (today,))
        orders_today = cursor.fetchone()
        
        # Pending orders (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status IN ('pending_payment', 'under_review')
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM orders 
                WHERE status IN ('pending_payment', 'under_review')
            ''')
        pending_orders = cursor.fetchone()
        
        # Low stock SKUs (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COUNT(*) as sku_count,
                       COUNT(DISTINCT p.id) as product_count
                FROM products p
                JOIN skus s ON s.product_id = p.id
                WHERE s.stock <= COALESCE(p.low_stock_threshold, 5)
                AND s.stock > 0
                AND p.status = 'active'
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COUNT(*) as sku_count,
                       COUNT(DISTINCT p.id) as product_count
                FROM products p
                JOIN skus s ON s.product_id = p.id
                WHERE s.stock <= COALESCE(p.low_stock_threshold, 5)
                AND s.stock > 0
                AND p.status = 'active'
            ''')
        low_stock = cursor.fetchone()
        
        # Out of stock SKUs (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COUNT(*) as sku_count,
                       COUNT(DISTINCT p.id) as product_count
                FROM products p
                JOIN skus s ON s.product_id = p.id
                WHERE s.stock = 0
                AND p.status = 'active'
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COUNT(*) as sku_count,
                       COUNT(DISTINCT p.id) as product_count
                FROM products p
                JOIN skus s ON s.product_id = p.id
                WHERE s.stock = 0
                AND p.status = 'active'
            ''')
        out_of_stock = cursor.fetchone()
        
        # Sales last 7 days for chart (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT DATE(o.paid_at) as date,
                       COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid' 
                AND o.paid_at >= CURRENT_DATE - INTERVAL '6 days'
                AND p.brand_id IN %s
                GROUP BY DATE(o.paid_at)
                ORDER BY DATE(o.paid_at)
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT DATE(paid_at) as date,
                       COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE status = 'paid' 
                AND paid_at >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY DATE(paid_at)
                ORDER BY DATE(paid_at)
            ''')
        sales_7_days = []
        for row in cursor.fetchall():
            sales_7_days.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'total': float(row['total']),
                'count': row['count']
            })
        
        # Fill in missing days with zeros
        from datetime import datetime, timedelta
        all_dates = []
        for i in range(6, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            all_dates.append(d)
        
        sales_7_days_filled = []
        existing_dates = {s['date']: s for s in sales_7_days}
        for d in all_dates:
            if d in existing_dates:
                sales_7_days_filled.append(existing_dates[d])
            else:
                sales_7_days_filled.append({'date': d, 'total': 0, 'count': 0})
        
        # Recent orders (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT DISTINCT o.id, o.order_number, o.status, o.final_amount, o.created_at,
                       u.full_name as customer_name,
                       (SELECT COUNT(*) FROM order_items oi2 
                        JOIN skus s2 ON s2.id = oi2.sku_id 
                        JOIN products p2 ON p2.id = s2.product_id 
                        WHERE oi2.order_id = o.id AND p2.brand_id IN %s) as item_count
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE p.brand_id IN %s
                ORDER BY o.created_at DESC
                LIMIT 5
            ''', (brand_ids_tuple, brand_ids_tuple))
        else:
            cursor.execute('''
                SELECT o.id, o.order_number, o.status, o.final_amount, o.created_at,
                       u.full_name as customer_name,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                ORDER BY o.created_at DESC
                LIMIT 5
            ''')
        recent_orders = []
        for row in cursor.fetchall():
            recent_orders.append({
                'id': row['id'],
                'order_number': row['order_number'],
                'status': row['status'],
                'final_amount': float(row['final_amount']) if row['final_amount'] else 0,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'customer_name': row['customer_name'],
                'item_count': row['item_count']
            })
        
        # Top selling products this month (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT p.name, SUM(oi.quantity) as total_sold, SUM(oi.subtotal) as revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid'
                AND EXTRACT(YEAR FROM o.paid_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND EXTRACT(MONTH FROM o.paid_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND p.brand_id IN %s
                GROUP BY p.id, p.name
                ORDER BY total_sold DESC
                LIMIT 5
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT p.name, SUM(oi.quantity) as total_sold, SUM(oi.subtotal) as revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.status = 'paid'
                AND EXTRACT(YEAR FROM o.paid_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND EXTRACT(MONTH FROM o.paid_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                GROUP BY p.id, p.name
                ORDER BY total_sold DESC
                LIMIT 5
            ''')
        top_products = []
        for row in cursor.fetchall():
            top_products.append({
                'name': row['name'],
                'total_sold': int(row['total_sold']) if row['total_sold'] else 0,
                'revenue': float(row['revenue']) if row['revenue'] else 0
            })
        
        return jsonify({
            'sales_today': {
                'total': float(sales_today['total']),
                'count': sales_today['count']
            },
            'sales_month': {
                'total': float(sales_month['total']),
                'count': sales_month['count']
            },
            'sales_all': {
                'total': float(sales_all['total']),
                'count': sales_all['count']
            },
            'orders_today': orders_today['count'],
            'pending_orders': pending_orders['count'],
            'low_stock': low_stock['product_count'],
            'low_stock_skus': low_stock['sku_count'],
            'out_of_stock': out_of_stock['product_count'],
            'out_of_stock_skus': out_of_stock['sku_count'],
            'sales_7_days': sales_7_days_filled,
            'recent_orders': recent_orders,
            'top_products': top_products
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/sales-history', methods=['GET'])
@admin_required
def get_sales_history():
    """Get sales history with filters for dashboard"""
    conn = None
    cursor = None
    try:
        from datetime import datetime, timedelta
        
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        channel_id = request.args.get('channel_id')
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        period = request.args.get('period', '7days')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_role = session.get('role')
        user_id = session.get('user_id')
        is_assistant_admin = user_role == 'Assistant Admin'
        
        # Get brand filter for Assistant Admin
        brand_ids = None
        brand_ids_tuple = None
        if is_assistant_admin:
            cursor.execute('SELECT brand_id FROM admin_brand_access WHERE user_id = %s', (user_id,))
            brand_ids = [row['brand_id'] for row in cursor.fetchall()]
            # If no brands assigned, return empty results
            if not brand_ids:
                return jsonify({
                    'orders': [],
                    'summary': {'total': 0, 'count': 0, 'paid_count': 0, 'paid_total': 0},
                    'channels': [],
                    'period': {'start': '', 'end': ''}
                }), 200
            brand_ids_tuple = tuple(brand_ids)
        
        # Calculate date range based on period
        today = datetime.now().date()
        if period == '7days':
            start = today - timedelta(days=6)
            end = today
        elif period == '30days':
            start = today - timedelta(days=29)
            end = today
        elif period == 'this_month':
            start = today.replace(day=1)
            end = today
        elif period == 'last_month':
            first_of_this_month = today.replace(day=1)
            end = first_of_this_month - timedelta(days=1)
            start = end.replace(day=1)
        elif period == 'custom' and start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            start = today - timedelta(days=6)
            end = today
        
        # Build query - filter by brand for Assistant Admin
        if is_assistant_admin and brand_ids_tuple:
            query = '''
                SELECT DISTINCT o.id, o.order_number, o.status, o.final_amount, o.created_at, o.paid_at,
                       u.full_name as customer_name,
                       sc.name as channel_name,
                       (SELECT COUNT(*) FROM order_items oi2 
                        JOIN skus s2 ON s2.id = oi2.sku_id 
                        JOIN products p2 ON p2.id = s2.product_id 
                        WHERE oi2.order_id = o.id AND p2.brand_id IN %s) as item_count
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN sales_channels sc ON sc.id = o.channel_id
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE DATE(o.created_at) >= %s AND DATE(o.created_at) <= %s
                AND p.brand_id IN %s
            '''
            params = [brand_ids_tuple, start, end, brand_ids_tuple]
        else:
            query = '''
                SELECT o.id, o.order_number, o.status, o.final_amount, o.created_at, o.paid_at,
                       u.full_name as customer_name,
                       sc.name as channel_name,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN sales_channels sc ON sc.id = o.channel_id
                WHERE DATE(o.created_at) >= %s AND DATE(o.created_at) <= %s
            '''
            params = [start, end]
        
        if channel_id:
            query += ' AND o.channel_id = %s'
            params.append(int(channel_id))
        
        if status:
            query += ' AND o.status = %s'
            params.append(status)
        
        if search:
            query += ' AND (o.order_number ILIKE %s OR u.full_name ILIKE %s)'
            search_term = f'%{search}%'
            params.extend([search_term, search_term])
        
        query += ' ORDER BY o.created_at DESC LIMIT 100'
        
        cursor.execute(query, params)
        orders = []
        for row in cursor.fetchall():
            orders.append({
                'id': row['id'],
                'order_number': row['order_number'],
                'status': row['status'],
                'final_amount': float(row['final_amount']) if row['final_amount'] else 0,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'paid_at': row['paid_at'].isoformat() if row['paid_at'] else None,
                'customer_name': row['customer_name'],
                'channel_name': row['channel_name'],
                'item_count': row['item_count']
            })
        
        # Get summary stats for the period (filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count,
                       COUNT(DISTINCT CASE WHEN o.status = 'paid' THEN o.id END) as paid_count,
                       COALESCE(SUM(CASE WHEN o.status = 'paid' THEN oi.subtotal END), 0) as paid_total
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE DATE(o.created_at) >= %s AND DATE(o.created_at) <= %s
                AND p.brand_id IN %s
            ''', (start, end, brand_ids_tuple))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count,
                       COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_count,
                       COALESCE(SUM(CASE WHEN status = 'paid' THEN final_amount END), 0) as paid_total
                FROM orders 
                WHERE DATE(created_at) >= %s AND DATE(created_at) <= %s
            ''', (start, end))
        summary = cursor.fetchone()
        
        # Get sales channels for filter
        cursor.execute('SELECT id, name FROM sales_channels WHERE is_active = true ORDER BY name')
        channels = [{'id': row['id'], 'name': row['name']} for row in cursor.fetchall()]
        
        return jsonify({
            'orders': orders,
            'summary': {
                'total': float(summary['total']),
                'count': summary['count'],
                'paid_count': summary['paid_count'],
                'paid_total': float(summary['paid_total'])
            },
            'channels': channels,
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/brand-sales', methods=['GET'])
@admin_required
def get_brand_sales():
    """Get sales statistics by brand with filters"""
    conn = None
    cursor = None
    try:
        from datetime import datetime, timedelta
        
        # Get filter parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        brand_id = request.args.get('brand_id')
        period = request.args.get('period', 'this_month')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_role = session.get('role')
        user_id = session.get('user_id')
        is_assistant_admin = user_role == 'Assistant Admin'
        
        # Get brand filter for Assistant Admin
        allowed_brand_ids = None
        allowed_brand_ids_tuple = None
        if is_assistant_admin:
            cursor.execute('SELECT brand_id FROM admin_brand_access WHERE user_id = %s', (user_id,))
            allowed_brand_ids = [row['brand_id'] for row in cursor.fetchall()]
            # If no brands assigned, return empty results
            if not allowed_brand_ids:
                return jsonify({
                    'brands': [],
                    'all_brands': [],
                    'summary': {'total_revenue': 0, 'total_sold': 0, 'brand_count': 0},
                    'period': {'start': '', 'end': ''}
                }), 200
            allowed_brand_ids_tuple = tuple(allowed_brand_ids)
        
        # Calculate date range
        today = datetime.now().date()
        if period == '7days':
            start = today - timedelta(days=6)
            end = today
        elif period == '30days':
            start = today - timedelta(days=29)
            end = today
        elif period == 'this_month':
            start = today.replace(day=1)
            end = today
        elif period == 'last_month':
            first_of_this_month = today.replace(day=1)
            end = first_of_this_month - timedelta(days=1)
            start = end.replace(day=1)
        elif period == 'custom' and start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            start = today.replace(day=1)
            end = today
        
        # Build query for brand sales
        query = '''
            SELECT b.id, b.name,
                   COALESCE(SUM(oi.quantity), 0) as total_sold,
                   COALESCE(SUM(oi.subtotal), 0) as revenue,
                   COUNT(DISTINCT o.id) as order_count
            FROM brands b
            LEFT JOIN products p ON p.brand_id = b.id
            LEFT JOIN skus s ON s.product_id = p.id
            LEFT JOIN order_items oi ON oi.sku_id = s.id
            LEFT JOIN orders o ON o.id = oi.order_id AND o.status = 'paid' 
                AND DATE(o.paid_at) >= %s AND DATE(o.paid_at) <= %s
        '''
        params = [start, end]
        
        # Filter by allowed brands for Assistant Admin
        where_clauses = []
        if is_assistant_admin and allowed_brand_ids_tuple:
            where_clauses.append('b.id IN %s')
            params.append(allowed_brand_ids_tuple)
        
        if brand_id:
            where_clauses.append('b.id = %s')
            params.append(int(brand_id))
        
        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)
        
        query += ' GROUP BY b.id, b.name ORDER BY revenue DESC'
        
        cursor.execute(query, params)
        brands_sales = []
        total_revenue = 0
        total_sold = 0
        for row in cursor.fetchall():
            revenue = float(row['revenue']) if row['revenue'] else 0
            sold = int(row['total_sold']) if row['total_sold'] else 0
            total_revenue += revenue
            total_sold += sold
            brands_sales.append({
                'id': row['id'],
                'name': row['name'],
                'total_sold': sold,
                'revenue': revenue,
                'order_count': row['order_count']
            })
        
        # Get all brands for filter (only allowed brands for Assistant Admin)
        if is_assistant_admin and allowed_brand_ids_tuple:
            cursor.execute('SELECT id, name FROM brands WHERE id IN %s ORDER BY name', (allowed_brand_ids_tuple,))
        else:
            cursor.execute('SELECT id, name FROM brands ORDER BY name')
        all_brands = [{'id': row['id'], 'name': row['name']} for row in cursor.fetchall()]
        
        return jsonify({
            'brands': brands_sales,
            'all_brands': all_brands,
            'summary': {
                'total_revenue': total_revenue,
                'total_sold': total_sold,
                'brand_count': len(brands_sales)
            },
            'period': {
                'start': start.strftime('%Y-%m-%d'),
                'end': end.strftime('%Y-%m-%d')
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ADMIN ORDER MANAGEMENT ====================

@app.route('/api/admin/quick-order', methods=['POST'])
@admin_required
def create_quick_order():
    """Create a quick order from admin dashboard"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        sales_channel_id = data.get('sales_channel_id')
        customer_name = data.get('customer_name')
        customer_phone = data.get('customer_phone')
        notes = data.get('notes')
        items = data.get('items', [])
        
        if not sales_channel_id:
            return jsonify({'error': 'กรุณาเลือกช่องทางขาย'}), 400
        
        if not items:
            return jsonify({'error': 'กรุณาเพิ่มสินค้าอย่างน้อย 1 รายการ'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Validate sales channel
        cursor.execute('SELECT id FROM sales_channels WHERE id = %s AND is_active = TRUE', (sales_channel_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ช่องทางขายไม่ถูกต้อง'}), 400
        
        # Validate and get server-side SKU prices with product info
        sku_ids = [item['sku_id'] for item in items]
        cursor.execute('''
            SELECT s.id, s.sku_code, s.price, p.name as product_name
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = ANY(%s)
        ''', (sku_ids,))
        sku_info = {row['id']: {'price': float(row['price']), 'sku_code': row['sku_code'], 'product_name': row['product_name']} for row in cursor.fetchall()}
        
        # Update items with server-side prices and product info
        for item in items:
            if item['sku_id'] not in sku_info:
                return jsonify({'error': f"SKU #{item['sku_id']} ไม่พบในระบบ"}), 400
            item['price'] = sku_info[item['sku_id']]['price']
            item['sku_code'] = sku_info[item['sku_id']]['sku_code']
            item['product_name'] = sku_info[item['sku_id']]['product_name']
        cursor.execute('''
            SELECT sws.sku_id, sws.warehouse_id, sws.stock, w.name as warehouse_name, w.is_active
            FROM sku_warehouse_stock sws
            JOIN warehouses w ON w.id = sws.warehouse_id
            WHERE sws.sku_id = ANY(%s) AND sws.stock > 0 AND w.is_active = TRUE
            ORDER BY sws.warehouse_id, sws.sku_id
        ''', (sku_ids,))
        warehouse_stocks = cursor.fetchall()
        
        # Build a lookup: {sku_id: [{warehouse_id, stock, warehouse_name}, ...]}
        sku_warehouse_map = {}
        for ws in warehouse_stocks:
            sku_id = ws['sku_id']
            if sku_id not in sku_warehouse_map:
                sku_warehouse_map[sku_id] = []
            sku_warehouse_map[sku_id].append({
                'warehouse_id': ws['warehouse_id'],
                'stock': ws['stock'],
                'warehouse_name': ws['warehouse_name']
            })
        
        # Check stock availability
        for item in items:
            total_available = sum(ws['stock'] for ws in sku_warehouse_map.get(item['sku_id'], []))
            if total_available < item['quantity']:
                cursor.execute('SELECT sku_code FROM skus WHERE id = %s', (item['sku_id'],))
                sku = cursor.fetchone()
                sku_code = sku['sku_code'] if sku else f"SKU#{item['sku_id']}"
                return jsonify({'error': f'สินค้า {sku_code} สต็อกไม่พอ เหลือ {total_available} ชิ้น'}), 400
        
        # Calculate totals
        total_amount = sum(float(item['price']) * item['quantity'] for item in items)
        
        # Build customer notes
        order_notes = []
        if customer_name:
            order_notes.append(f"ลูกค้า: {customer_name}")
        if customer_phone:
            order_notes.append(f"โทร: {customer_phone}")
        if notes:
            order_notes.append(notes)
        final_notes = ' | '.join(order_notes) if order_notes else None
        
        # Generate order number
        order_number = generate_order_number(cursor)
        
        # Create order
        cursor.execute('''
            INSERT INTO orders (order_number, user_id, channel_id, status, total_amount, discount_amount, final_amount, notes)
            VALUES (%s, %s, %s, 'paid', %s, 0, %s, %s)
            RETURNING id, order_number, status, final_amount, created_at
        ''', (order_number, session.get('user_id'), sales_channel_id, total_amount, total_amount, final_notes))
        order = dict(cursor.fetchone())
        
        # Create order items and track their IDs
        order_item_map = {}
        for idx, item in enumerate(items):
            item_subtotal = float(item['price']) * item['quantity']
            cursor.execute('''
                INSERT INTO order_items (order_id, sku_id, product_name, sku_code, quantity, unit_price, tier_discount_percent, discount_amount, subtotal, customization_data)
                VALUES (%s, %s, %s, %s, %s, %s, 0, 0, %s, NULL)
                RETURNING id
            ''', (order['id'], item['sku_id'], item['product_name'], item['sku_code'], item['quantity'], item['price'], item_subtotal))
            order_item_id = cursor.fetchone()['id']
            order_item_map[idx] = order_item_id
        
        # Allocate items to warehouses
        warehouse_shipments = {}
        stock_deductions = []
        
        for idx, item in enumerate(items):
            remaining_qty = item['quantity']
            warehouses_for_sku = sku_warehouse_map.get(item['sku_id'], [])
            order_item_id = order_item_map[idx]
            
            for wh in warehouses_for_sku:
                if remaining_qty <= 0:
                    break
                
                allocate_qty = min(remaining_qty, wh['stock'])
                if allocate_qty > 0:
                    wh_id = wh['warehouse_id']
                    if wh_id not in warehouse_shipments:
                        warehouse_shipments[wh_id] = []
                    
                    warehouse_shipments[wh_id].append({
                        'order_item_id': order_item_id,
                        'quantity': allocate_qty
                    })
                    
                    stock_deductions.append((item['sku_id'], wh_id, allocate_qty))
                    wh['stock'] -= allocate_qty
                    remaining_qty -= allocate_qty
        
        # Create shipments per warehouse
        for wh_id, shipment_items in warehouse_shipments.items():
            cursor.execute('''
                INSERT INTO order_shipments (order_id, warehouse_id, status)
                VALUES (%s, %s, 'pending')
                RETURNING id
            ''', (order['id'], wh_id))
            shipment_id = cursor.fetchone()['id']
            
            for ship_item in shipment_items:
                cursor.execute('''
                    INSERT INTO order_shipment_items (shipment_id, order_item_id, quantity)
                    VALUES (%s, %s, %s)
                ''', (shipment_id, ship_item['order_item_id'], ship_item['quantity']))
        
        # Deduct stock from warehouses
        for sku_id, wh_id, qty in stock_deductions:
            cursor.execute('''
                UPDATE sku_warehouse_stock
                SET stock = stock - %s
                WHERE sku_id = %s AND warehouse_id = %s
            ''', (qty, sku_id, wh_id))
        
        # Update main SKU stock
        for item in items:
            cursor.execute('''
                UPDATE skus SET stock = stock - %s WHERE id = %s
            ''', (item['quantity'], item['sku_id']))
        
        conn.commit()
        
        return jsonify({
            'message': 'สร้างคำสั่งซื้อสำเร็จ',
            'order_number': order['order_number'],
            'order_id': order['id']
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders', methods=['GET'])
@admin_required
def get_all_orders():
    """Get all orders for admin"""
    conn = None
    cursor = None
    try:
        status_filter = request.args.get('status')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_role = session.get('role')
        user_id = session.get('user_id')
        is_assistant_admin = user_role == 'Assistant Admin'
        
        # Get brand filter for Assistant Admin
        brand_ids = None
        brand_ids_tuple = None
        if is_assistant_admin:
            cursor.execute('SELECT brand_id FROM admin_brand_access WHERE user_id = %s', (user_id,))
            brand_ids = [row['brand_id'] for row in cursor.fetchall()]
            # If no brands assigned, return empty results
            if not brand_ids:
                return jsonify([]), 200
            brand_ids_tuple = tuple(brand_ids)
        
        # Build query - filter by brand for Assistant Admin
        if is_assistant_admin and brand_ids_tuple:
            query = '''
                SELECT DISTINCT o.id, o.order_number, o.status, o.total_amount, o.discount_amount, 
                       o.final_amount, o.notes, o.created_at, o.updated_at,
                       u.full_name as reseller_name, u.username,
                       sc.name as channel_name,
                       rt.name as reseller_tier_name,
                       (SELECT COUNT(*) FROM order_items oi2 
                        JOIN skus s2 ON s2.id = oi2.sku_id 
                        JOIN products p2 ON p2.id = s2.product_id 
                        WHERE oi2.order_id = o.id AND p2.brand_id IN %s) as item_count,
                       (SELECT COUNT(*) FROM payment_slips WHERE order_id = o.id AND status = 'pending') as pending_slips,
                       (SELECT ps.slip_image_url FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_image_url,
                       (SELECT ps.amount FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_amount
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                LEFT JOIN sales_channels sc ON sc.id = o.channel_id
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE p.brand_id IN %s
            '''
            params = [brand_ids_tuple, brand_ids_tuple]
            
            if status_filter:
                query += ' AND o.status = %s'
                params.append(status_filter)
        else:
            query = '''
                SELECT o.id, o.order_number, o.status, o.total_amount, o.discount_amount, 
                       o.final_amount, o.notes, o.created_at, o.updated_at,
                       u.full_name as reseller_name, u.username,
                       sc.name as channel_name,
                       rt.name as reseller_tier_name,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                       (SELECT COUNT(*) FROM payment_slips WHERE order_id = o.id AND status = 'pending') as pending_slips,
                       (SELECT ps.slip_image_url FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_image_url,
                       (SELECT ps.amount FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_amount
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                LEFT JOIN sales_channels sc ON sc.id = o.channel_id
            '''
            params = []
            
            if status_filter:
                query += ' WHERE o.status = %s'
                params.append(status_filter)
        
        query += ' ORDER BY o.created_at DESC'
        
        cursor.execute(query, params)
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order['total_amount'] = float(order['total_amount']) if order['total_amount'] else 0
            order['discount_amount'] = float(order['discount_amount']) if order['discount_amount'] else 0
            order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
            if order.get('slip_amount'):
                order['slip_amount'] = float(order['slip_amount'])
            orders.append(order)
        
        return jsonify(orders), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/approve', methods=['POST'])
@admin_required
def approve_order(order_id):
    """Approve order payment and deduct stock"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json() or {}
        slip_id = data.get('slip_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order
        cursor.execute('SELECT id, status, user_id, final_amount FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        if order['status'] != 'under_review':
            return jsonify({'error': 'Order is not under review'}), 400
        
        # Get order items for stock deduction
        cursor.execute('''
            SELECT oi.sku_id, oi.quantity, s.stock
            FROM order_items oi
            JOIN skus s ON s.id = oi.sku_id
            WHERE oi.order_id = %s
        ''', (order_id,))
        items = cursor.fetchall()
        
        # Validate and deduct stock
        for item in items:
            if item['stock'] < item['quantity']:
                return jsonify({'error': f'Insufficient stock for SKU'}), 400
            
            # Deduct stock
            cursor.execute('''
                UPDATE skus SET stock = stock - %s WHERE id = %s
            ''', (item['quantity'], item['sku_id']))
            
            # Record stock transaction
            cursor.execute('''
                INSERT INTO stock_transactions (sku_id, transaction_type, quantity_change, reference_type, reference_id, notes, created_by)
                VALUES (%s, 'sale', %s, 'order', %s, %s, %s)
            ''', (item['sku_id'], -item['quantity'], order_id, f'Order #{order_id} approved', admin_id))
        
        # Update order status to preparing (ready to ship)
        cursor.execute('''
            UPDATE orders SET status = 'preparing', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (order_id,))
        
        # Update slip status if provided
        if slip_id:
            cursor.execute('''
                UPDATE payment_slips SET status = 'approved', reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (admin_id, slip_id))
        else:
            cursor.execute('''
                UPDATE payment_slips SET status = 'approved', reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND status = 'pending'
            ''', (admin_id, order_id))
        
        # Update user's total purchases
        cursor.execute('''
            UPDATE users SET total_purchases = COALESCE(total_purchases, 0) + %s
            WHERE id = %s
        ''', (order['final_amount'], order['user_id']))
        
        # Check for tier upgrade
        cursor.execute('''
            SELECT u.id, u.reseller_tier_id, u.total_purchases, u.tier_manual_override,
                   (SELECT id FROM reseller_tiers 
                    WHERE upgrade_threshold <= u.total_purchases + %s 
                    AND is_manual_only = FALSE
                    ORDER BY level_rank DESC LIMIT 1) as new_tier_id
            FROM users u WHERE u.id = %s
        ''', (order['final_amount'], order['user_id']))
        user = cursor.fetchone()
        
        if user and user['new_tier_id'] and not user['tier_manual_override']:
            if user['new_tier_id'] != user['reseller_tier_id']:
                cursor.execute('''
                    UPDATE users SET reseller_tier_id = %s WHERE id = %s
                ''', (user['new_tier_id'], user['id']))
                
                # Get tier name
                cursor.execute('SELECT name FROM reseller_tiers WHERE id = %s', (user['new_tier_id'],))
                new_tier = cursor.fetchone()
                
                # Notify user of tier upgrade
                create_notification(
                    user['id'],
                    'ยินดีด้วย! คุณได้รับการอัพเกรดระดับ',
                    f'คุณได้รับการอัพเกรดเป็นระดับ {new_tier["name"]}',
                    'success',
                    'tier',
                    user['new_tier_id']
                )
        
        conn.commit()
        
        # Get reseller info for email
        cursor2 = None
        conn2 = None
        try:
            conn2 = get_db()
            cursor2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor2.execute('SELECT full_name, email FROM users WHERE id = %s', (order['user_id'],))
            reseller = cursor2.fetchone()
            cursor2.execute('SELECT order_number FROM orders WHERE id = %s', (order_id,))
            order_info = cursor2.fetchone()
            if reseller and reseller['email']:
                send_order_status_email(
                    reseller['email'],
                    reseller['full_name'],
                    order_info['order_number'] if order_info else f'#{order_id}',
                    'approved',
                    'สลิปการชำระเงินของคุณได้รับการยืนยันแล้ว กำลังเตรียมจัดส่งสินค้า'
                )
            try:
                send_order_status_chat(order['user_id'], order_info['order_number'] if order_info else f'#{order_id}', 'approved')
            except Exception as chat_err:
                print(f"Chat notification error: {chat_err}")
        except Exception as email_err:
            print(f"Email notification error: {email_err}")
        finally:
            if cursor2:
                cursor2.close()
            if conn2:
                conn2.close()
        
        # Notify user
        create_notification(
            order['user_id'],
            'การชำระเงินได้รับการอนุมัติ',
            f'คำสั่งซื้อ #{order_id} ได้รับการอนุมัติแล้ว',
            'success',
            'order',
            order_id
        )
        
        return jsonify({'message': 'Order approved and stock deducted'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/request-new-slip', methods=['POST'])
@admin_required
def request_new_slip(order_id):
    """Request new payment slip - delete old slip and reset to pending_payment"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        if not reason:
            return jsonify({'error': 'กรุณาระบุเหตุผล'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order
        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        if order['status'] != 'under_review':
            return jsonify({'error': 'Order is not under review'}), 400
        
        # Delete old payment slips for this order
        cursor.execute('DELETE FROM payment_slips WHERE order_id = %s', (order_id,))
        
        # Update order status back to pending_payment
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        cursor.execute('''
            UPDATE orders SET status = 'pending_payment', 
                             notes = CONCAT(COALESCE(notes, ''), '[', %s, '] ขอสลิปใหม่: ', %s, ' | '), 
                             updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (timestamp, reason, order_id))
        
        conn.commit()
        
        # Get reseller info for email
        cursor.execute('SELECT full_name, email FROM users WHERE id = %s', (order['user_id'],))
        reseller = cursor.fetchone()
        if reseller and reseller['email']:
            send_order_status_email(
                reseller['email'],
                reseller['full_name'],
                order['order_number'] or f'#{order_id}',
                'request_new_slip',
                'กรุณาอัปโหลดสลิปการชำระเงินใหม่',
                f'เหตุผล: {reason}'
            )
        try:
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'request_new_slip', f'เหตุผล: {reason}')
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        # Notify user
        create_notification(
            order['user_id'],
            'กรุณาแนบสลิปใหม่',
            f'คำสั่งซื้อ {order["order_number"] or "#" + str(order_id)}: {reason}',
            'warning',
            'order',
            order_id
        )
        
        return jsonify({'message': 'ขอสลิปใหม่สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/cancel', methods=['POST'])
@admin_required
def cancel_order(order_id):
    """Cancel order and restore stock"""
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '')
        admin_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order status
        cursor.execute('SELECT id, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] not in ('pending_payment', 'under_review', 'rejected', 'paid', 'preparing', 'failed_delivery'):
            return jsonify({'error': 'ไม่สามารถยกเลิกคำสั่งซื้อนี้ได้'}), 400
        
        # Get order items and shipments to restore stock
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
            
            # Log stock restoration
            cursor.execute('''
                INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, change_type, reference_id, reference_type, notes, created_by)
                SELECT %s, %s, stock - %s, stock, 'order_cancel', %s, 'order', %s, %s
                FROM sku_warehouse_stock WHERE sku_id = %s AND warehouse_id = %s
            ''', (item['sku_id'], item['warehouse_id'], item['quantity'], order_id, f'ยกเลิกออเดอร์: {reason}', admin_id, item['sku_id'], item['warehouse_id']))
        
        # Restore main SKU stock
        cursor.execute('''
            SELECT sku_id, SUM(quantity) as total_qty
            FROM order_items WHERE order_id = %s
            GROUP BY sku_id
        ''', (order_id,))
        for sku in cursor.fetchall():
            cursor.execute('UPDATE skus SET stock = stock + %s WHERE id = %s', (sku['total_qty'], sku['sku_id']))
        
        # Update order status
        cursor.execute('''
            UPDATE orders SET status = 'cancelled', notes = CONCAT(COALESCE(notes, ''), ' [ยกเลิก: ', %s, ']'), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (reason, order_id))
        
        conn.commit()
        
        # Get reseller info for email and order number
        cursor.execute('''
            SELECT u.full_name, u.email, u.id as user_id, o.order_number 
            FROM users u 
            JOIN orders o ON o.user_id = u.id 
            WHERE o.id = %s
        ''', (order_id,))
        reseller_info = cursor.fetchone()
        if reseller_info and reseller_info['email']:
            send_order_status_email(
                reseller_info['email'],
                reseller_info['full_name'],
                reseller_info['order_number'] or f'#{order_id}',
                'cancelled',
                'คำสั่งซื้อของคุณถูกยกเลิก',
                f'เหตุผล: {reason}' if reason else ''
            )
        try:
            send_order_status_chat(reseller_info.get('user_id') or order.get('user_id', 0), reseller_info['order_number'] or f'#{order_id}', 'cancelled', f'เหตุผล: {reason}' if reason else '')
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        # Notify user
        create_notification(
            order['user_id'],
            'คำสั่งซื้อถูกยกเลิก',
            f'คำสั่งซื้อ #{order_id} ถูกยกเลิก: {reason}',
            'warning',
            'order',
            order_id
        )
        
        return jsonify({'message': 'ยกเลิกคำสั่งซื้อสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/mark-delivered', methods=['POST'])
@admin_required
def mark_order_delivered(order_id):
    """Mark order as delivered"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] != 'shipped':
            return jsonify({'error': 'คำสั่งซื้อนี้ยังไม่ได้จัดส่ง'}), 400
        
        cursor.execute('''
            UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (order_id,))
        
        # Update all shipments to delivered
        cursor.execute('''
            UPDATE order_shipments SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
        ''', (order_id,))
        
        conn.commit()
        
        create_notification(
            order['user_id'],
            'ได้รับสินค้าแล้ว',
            f'คำสั่งซื้อ {order["order_number"] or "#" + str(order_id)} จัดส่งสำเร็จแล้ว',
            'success',
            'order',
            order_id
        )
        
        try:
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'delivered')
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'อัปเดตสถานะสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/mark-failed-delivery', methods=['POST'])
@admin_required
def mark_order_failed_delivery(order_id):
    """Mark order as failed delivery (returned)"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json() or {}
        reason = data.get('reason', 'สินค้าตีกลับ')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] != 'shipped':
            return jsonify({'error': 'คำสั่งซื้อนี้ยังไม่ได้จัดส่ง'}), 400
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        cursor.execute('''
            UPDATE orders SET status = 'failed_delivery', 
                             notes = CONCAT(COALESCE(notes, ''), '[', %s, '] จัดส่งไม่สำเร็จ: ', %s, ' | '),
                             updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (timestamp, reason, order_id))
        
        conn.commit()
        
        create_notification(
            order['user_id'],
            'จัดส่งไม่สำเร็จ',
            f'คำสั่งซื้อ {order["order_number"] or "#" + str(order_id)}: {reason}',
            'warning',
            'order',
            order_id
        )
        
        try:
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'failed_delivery', f'เหตุผล: {reason}' if reason else '')
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'อัปเดตสถานะสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/orders/<int:order_id>/reship', methods=['POST'])
@admin_required
def reship_order(order_id):
    """Reship order after failed delivery - reset to preparing"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] != 'failed_delivery':
            return jsonify({'error': 'คำสั่งซื้อนี้ไม่อยู่ในสถานะจัดส่งไม่สำเร็จ'}), 400
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        cursor.execute('''
            UPDATE orders SET status = 'preparing', 
                             notes = CONCAT(COALESCE(notes, ''), '[', %s, '] จัดส่งใหม่ | '),
                             updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (timestamp, order_id))
        
        # Reset shipment tracking
        cursor.execute('''
            UPDATE order_shipments SET tracking_number = NULL, shipping_provider = NULL, status = 'pending', shipped_at = NULL
            WHERE order_id = %s
        ''', (order_id,))
        
        conn.commit()
        
        create_notification(
            order['user_id'],
            'กำลังจัดส่งใหม่',
            f'คำสั่งซื้อ {order["order_number"] or "#" + str(order_id)} กำลังจัดส่งใหม่',
            'info',
            'order',
            order_id
        )
        
        try:
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'reship')
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'เริ่มจัดส่งใหม่สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== WAREHOUSE MANAGEMENT ROUTES ====================

@app.route('/api/admin/warehouses', methods=['GET'])
@admin_required
def get_warehouses():
    """Get all warehouses"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, address, province, district, subdistrict, postal_code, 
                   phone, contact_name, is_active, created_at
            FROM warehouses
            ORDER BY name ASC
        ''')
        
        warehouses = []
        for row in cursor.fetchall():
            w = dict(row)
            w['is_active'] = bool(w.get('is_active', True))
            warehouses.append(w)
        return jsonify(warehouses), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/warehouses', methods=['POST'])
@admin_required
def create_warehouse():
    """Create a new warehouse"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'Only Super Admin can create warehouses'}), 403
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Warehouse name is required'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            INSERT INTO warehouses (name, address, province, district, subdistrict, postal_code, phone, contact_name, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, address, province, district, subdistrict, postal_code, phone, contact_name, is_active, created_at
        ''', (
            data['name'],
            data.get('address', ''),
            data.get('province', ''),
            data.get('district', ''),
            data.get('subdistrict', ''),
            data.get('postal_code', ''),
            data.get('phone', ''),
            data.get('contact_name', ''),
            data.get('is_active', True)
        ))
        
        warehouse = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify(warehouse), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/warehouses/<int:warehouse_id>', methods=['GET'])
@admin_required
def get_warehouse(warehouse_id):
    """Get a single warehouse"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, name, address, province, district, subdistrict, postal_code, 
                   phone, contact_name, is_active, created_at
            FROM warehouses
            WHERE id = %s
        ''', (warehouse_id,))
        
        warehouse = cursor.fetchone()
        if not warehouse:
            return jsonify({'error': 'Warehouse not found'}), 404
        
        result = dict(warehouse)
        result['is_active'] = bool(result.get('is_active', True))
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/warehouses/<int:warehouse_id>', methods=['PUT'])
@admin_required
def update_warehouse(warehouse_id):
    """Update a warehouse"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'Only Super Admin can update warehouses'}), 403
    
    data = request.json
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM warehouses WHERE id = %s', (warehouse_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Warehouse not found'}), 404
        
        update_fields = []
        update_values = []
        
        for field in ['name', 'address', 'province', 'district', 'subdistrict', 'postal_code', 'phone', 'contact_name']:
            if field in data:
                update_fields.append(f'{field} = %s')
                update_values.append(data[field])
        
        if 'is_active' in data:
            update_fields.append('is_active = %s')
            update_values.append(data['is_active'])
        
        if not update_fields:
            return jsonify({'error': 'ไม่มีข้อมูลที่ต้องการอัพเดท'}), 400
        
        update_values.append(warehouse_id)
        cursor.execute(f'''
            UPDATE warehouses SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING id, name, address, province, district, subdistrict, postal_code, phone, contact_name, is_active, created_at
        ''', update_values)
        
        warehouse = dict(cursor.fetchone())
        warehouse['is_active'] = bool(warehouse.get('is_active'))
        conn.commit()
        
        return jsonify(warehouse), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/warehouses/<int:warehouse_id>', methods=['DELETE'])
@admin_required
def delete_warehouse(warehouse_id):
    """Delete a warehouse"""
    if session.get('role') != 'Super Admin':
        return jsonify({'error': 'Only Super Admin can delete warehouses'}), 403
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT COUNT(*) as cnt FROM sku_warehouse_stock WHERE warehouse_id = %s AND stock > 0', (warehouse_id,))
        if cursor.fetchone()['cnt'] > 0:
            return jsonify({'error': 'Cannot delete warehouse with stock. Move stock first.'}), 400
        
        cursor.execute('DELETE FROM warehouses WHERE id = %s RETURNING id', (warehouse_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Warehouse not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Warehouse deleted successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/products', methods=['GET'])
@admin_required
def api_get_products():
    """Search/list products for stock adjustment page"""
    search = request.args.get('search', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = '''
            SELECT p.id, p.name, p.parent_sku, p.status,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT COUNT(*) FROM skus WHERE product_id = p.id) as sku_count
            FROM products p
            WHERE p.status != 'deleted'
        '''
        params = []
        
        if search:
            query += ' AND (p.name ILIKE %s OR p.parent_sku ILIKE %s)'
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += ' ORDER BY p.name LIMIT %s'
        params.append(limit)
        
        cursor.execute(query, params)
        products = cursor.fetchall()
        
        return jsonify({'products': products}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/products/<int:product_id>/warehouse-stock', methods=['GET'])
@admin_required
def get_product_warehouse_stock(product_id):
    """Get warehouse stock for all SKUs of a product"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        cursor.execute('''
            SELECT s.id as sku_id, s.sku_code, s.stock as total_stock,
                   w.id as warehouse_id, w.name as warehouse_name,
                   COALESCE(sws.stock, 0) as warehouse_stock
            FROM skus s
            CROSS JOIN warehouses w
            LEFT JOIN sku_warehouse_stock sws ON s.id = sws.sku_id AND w.id = sws.warehouse_id
            WHERE s.product_id = %s AND w.is_active = TRUE
            ORDER BY s.id, w.name
        ''', (product_id,))
        
        rows = cursor.fetchall()
        
        sku_stock = {}
        for row in rows:
            sku_id = row['sku_id']
            if sku_id not in sku_stock:
                sku_stock[sku_id] = {
                    'sku_id': sku_id,
                    'sku_code': row['sku_code'],
                    'total_stock': row['total_stock'],
                    'warehouses': []
                }
            sku_stock[sku_id]['warehouses'].append({
                'warehouse_id': row['warehouse_id'],
                'warehouse_name': row['warehouse_name'],
                'stock': row['warehouse_stock']
            })
        
        return jsonify(list(sku_stock.values())), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/products/<int:product_id>/warehouse-stock', methods=['PUT'])
@admin_required
def update_product_warehouse_stock(product_id):
    """Disabled - Stock updates must go through Stock Adjustment page for audit trail"""
    return jsonify({
        'error': 'การแก้ไขสต็อกโดยตรงถูกปิดใช้งาน กรุณาใช้หน้าปรับสต็อกเพื่อให้มีประวัติการเปลี่ยนแปลง'
    }), 400

@app.route('/api/admin/products/<int:product_id>/skus-with-stock', methods=['GET'])
@admin_required
def get_product_skus_with_stock(product_id):
    """Get all SKUs of a product with warehouse stock and variant info for bulk stock adjustment"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get product info
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku, 
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM products p
            WHERE p.id = %s
        ''', (product_id,))
        product = cursor.fetchone()
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Get options for this product
        cursor.execute('''
            SELECT o.id, o.name, 
                   json_agg(json_build_object('id', ov.id, 'value', ov.value) ORDER BY ov.sort_order) as values
            FROM options o
            LEFT JOIN option_values ov ON o.id = ov.option_id
            WHERE o.product_id = %s
            GROUP BY o.id, o.name
            ORDER BY o.id
        ''', (product_id,))
        options = cursor.fetchall()
        
        # Get SKUs with variant values and warehouse stock
        cursor.execute('''
            SELECT s.id, s.sku_code, s.stock as total_stock, s.price,
                   json_agg(DISTINCT jsonb_build_object('option_name', o.name, 'value', ov.value)) as variant_values
            FROM skus s
            LEFT JOIN sku_values_map svm ON s.id = svm.sku_id
            LEFT JOIN option_values ov ON svm.option_value_id = ov.id
            LEFT JOIN options o ON ov.option_id = o.id
            WHERE s.product_id = %s
            GROUP BY s.id, s.sku_code, s.stock, s.price
            ORDER BY s.id
        ''', (product_id,))
        skus_raw = cursor.fetchall()
        
        # Get warehouses
        cursor.execute('SELECT id, name FROM warehouses WHERE is_active = TRUE ORDER BY name')
        warehouses = cursor.fetchall()
        
        # Get warehouse stock for all SKUs
        cursor.execute('''
            SELECT sws.sku_id, sws.warehouse_id, sws.stock
            FROM sku_warehouse_stock sws
            JOIN skus s ON s.id = sws.sku_id
            WHERE s.product_id = %s
        ''', (product_id,))
        warehouse_stocks = cursor.fetchall()
        
        # Build warehouse stock map
        stock_map = {}
        for ws in warehouse_stocks:
            key = (ws['sku_id'], ws['warehouse_id'])
            stock_map[key] = ws['stock']
        
        # Build SKU list with warehouse stocks
        skus = []
        for sku in skus_raw:
            # Parse variant values to readable format
            variant_display = []
            if sku['variant_values']:
                for v in sku['variant_values']:
                    if v.get('option_name') and v.get('value'):
                        variant_display.append(f"{v['option_name']}: {v['value']}")
            
            # Get stock per warehouse
            sku_warehouses = []
            for wh in warehouses:
                stock = stock_map.get((sku['id'], wh['id']), 0)
                sku_warehouses.append({
                    'warehouse_id': wh['id'],
                    'warehouse_name': wh['name'],
                    'stock': stock
                })
            
            skus.append({
                'id': sku['id'],
                'sku_code': sku['sku_code'],
                'total_stock': sku['total_stock'],
                'price': float(sku['price']) if sku['price'] else 0,
                'variant_display': ' / '.join(variant_display) if variant_display else '-',
                'warehouses': sku_warehouses
            })
        
        return jsonify({
            'product': {
                'id': product['id'],
                'name': product['name'],
                'parent_sku': product['parent_sku'],
                'image_url': product['image_url']
            },
            'options': [{'id': o['id'], 'name': o['name'], 'values': o['values'] or []} for o in options],
            'warehouses': [{'id': w['id'], 'name': w['name']} for w in warehouses],
            'skus': skus,
            'sku_count': len(skus)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK TRANSFER ROUTES ====================

@app.route('/api/admin/stock-transfers', methods=['GET'])
@admin_required
def get_stock_transfers():
    """Get all stock transfers with filters"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        sku_id = request.args.get('sku_id')
        warehouse_id = request.args.get('warehouse_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        query = '''
            SELECT st.id, st.sku_id, st.from_warehouse_id, st.to_warehouse_id,
                   st.quantity, st.notes, st.created_at, st.created_by,
                   s.sku_code, p.name as product_name,
                   fw.name as from_warehouse_name, tw.name as to_warehouse_name,
                   u.username as created_by_name
            FROM stock_transfers st
            JOIN skus s ON s.id = st.sku_id
            JOIN products p ON p.id = s.product_id
            JOIN warehouses fw ON fw.id = st.from_warehouse_id
            JOIN warehouses tw ON tw.id = st.to_warehouse_id
            LEFT JOIN users u ON u.id = st.created_by
            WHERE 1=1
        '''
        params = []
        
        if sku_id:
            query += ' AND st.sku_id = %s'
            params.append(sku_id)
        if warehouse_id:
            query += ' AND (st.from_warehouse_id = %s OR st.to_warehouse_id = %s)'
            params.extend([warehouse_id, warehouse_id])
        if date_from:
            query += ' AND st.created_at >= %s'
            params.append(date_from)
        if date_to:
            query += ' AND st.created_at <= %s'
            params.append(date_to + ' 23:59:59')
        
        query += ' ORDER BY st.created_at DESC LIMIT 500'
        
        cursor.execute(query, params)
        transfers = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(transfers), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock-transfers', methods=['POST'])
@admin_required
def create_stock_transfer():
    """Create a stock transfer between warehouses"""
    data = request.json
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    required = ['sku_id', 'from_warehouse_id', 'to_warehouse_id', 'quantity']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    if data['from_warehouse_id'] == data['to_warehouse_id']:
        return jsonify({'error': 'Source and destination warehouses must be different'}), 400
    
    if data['quantity'] <= 0:
        return jsonify({'error': 'Quantity must be greater than 0'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT sws.stock FROM sku_warehouse_stock sws
            WHERE sws.sku_id = %s AND sws.warehouse_id = %s
        ''', (data['sku_id'], data['from_warehouse_id']))
        stock_row = cursor.fetchone()
        current_stock = stock_row['stock'] if stock_row else 0
        
        if current_stock < data['quantity']:
            return jsonify({'error': f'Insufficient stock. Available: {current_stock}'}), 400
        
        cursor.execute('''
            UPDATE sku_warehouse_stock 
            SET stock = stock - %s
            WHERE sku_id = %s AND warehouse_id = %s
        ''', (data['quantity'], data['sku_id'], data['from_warehouse_id']))
        
        cursor.execute('''
            INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
            VALUES (%s, %s, %s)
            ON CONFLICT (sku_id, warehouse_id) 
            DO UPDATE SET stock = sku_warehouse_stock.stock + EXCLUDED.stock
        ''', (data['sku_id'], data['to_warehouse_id'], data['quantity']))
        
        cursor.execute('''
            INSERT INTO stock_transfers (sku_id, from_warehouse_id, to_warehouse_id, quantity, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['sku_id'], data['from_warehouse_id'], data['to_warehouse_id'], 
              data['quantity'], data.get('notes', ''), session.get('user_id')))
        transfer_id = cursor.fetchone()['id']
        
        cursor.execute('''
            SELECT COALESCE(stock, 0) as stock FROM sku_warehouse_stock 
            WHERE sku_id = %s AND warehouse_id = %s
        ''', (data['sku_id'], data['from_warehouse_id']))
        new_from_stock = cursor.fetchone()['stock']
        
        cursor.execute('''
            SELECT COALESCE(stock, 0) as stock FROM sku_warehouse_stock 
            WHERE sku_id = %s AND warehouse_id = %s
        ''', (data['sku_id'], data['to_warehouse_id']))
        new_to_stock = cursor.fetchone()['stock']
        
        cursor.execute('''
            INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, 
                                         change_type, reference_id, reference_type, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (data['sku_id'], data['from_warehouse_id'], current_stock, new_from_stock,
              'transfer_out', transfer_id, 'stock_transfer', 
              f"Transfer to warehouse ID {data['to_warehouse_id']}", session.get('user_id')))
        
        cursor.execute('''
            INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, 
                                         change_type, reference_id, reference_type, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (data['sku_id'], data['to_warehouse_id'], new_to_stock - data['quantity'], new_to_stock,
              'transfer_in', transfer_id, 'stock_transfer', 
              f"Transfer from warehouse ID {data['from_warehouse_id']}", session.get('user_id')))
        
        conn.commit()
        return jsonify({'message': 'Stock transferred successfully', 'transfer_id': transfer_id}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK ADJUSTMENT ROUTES ====================

ADJUSTMENT_TYPES = {
    'shopee_sale': {'label': 'ขาย Shopee', 'direction': 'decrease'},
    'lazada_sale': {'label': 'ขาย Lazada', 'direction': 'decrease'},
    'tiktok_sale': {'label': 'ขาย TikTok', 'direction': 'decrease'},
    'facebook_sale': {'label': 'ขาย Facebook', 'direction': 'decrease'},
    'line_sale': {'label': 'ขาย LINE', 'direction': 'decrease'},
    'offline_sale': {'label': 'ขายหน้าร้าน', 'direction': 'decrease'},
    'other_sale': {'label': 'ขายช่องทางอื่น', 'direction': 'decrease'},
    'damaged': {'label': 'ชำรุด/เสียหาย', 'direction': 'decrease'},
    'lost': {'label': 'สูญหาย', 'direction': 'decrease'},
    'expired': {'label': 'หมดอายุ', 'direction': 'decrease'},
    'miscount_decrease': {'label': 'นับผิด (ลด)', 'direction': 'decrease'},
    'miscount_increase': {'label': 'นับผิด (เพิ่ม)', 'direction': 'increase'},
    'stock_in': {'label': 'รับเข้าสต็อก', 'direction': 'increase'},
    'return': {'label': 'รับคืนสินค้า', 'direction': 'increase'},
    'other_increase': {'label': 'อื่นๆ (เพิ่ม)', 'direction': 'increase'},
    'other_decrease': {'label': 'อื่นๆ (ลด)', 'direction': 'decrease'}
}

@app.route('/api/admin/adjustment-types', methods=['GET'])
@admin_required
def get_adjustment_types():
    """Get all available adjustment types"""
    types_list = []
    for key, val in ADJUSTMENT_TYPES.items():
        types_list.append({
            'value': key,
            'label': val['label'],
            'direction': val['direction']
        })
    return jsonify(types_list), 200

@app.route('/api/admin/stock-adjustments', methods=['GET'])
@admin_required
def get_stock_adjustments():
    """Get all stock adjustments with filters"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        sku_id = request.args.get('sku_id')
        warehouse_id = request.args.get('warehouse_id')
        adjustment_type = request.args.get('adjustment_type')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        query = '''
            SELECT sa.id, sa.sku_id, sa.warehouse_id, sa.quantity_change,
                   sa.adjustment_type, sa.sales_channel, sa.notes, 
                   sa.created_at, sa.created_by,
                   s.sku_code, p.name as product_name,
                   w.name as warehouse_name,
                   u.username as created_by_name
            FROM stock_adjustments sa
            JOIN skus s ON s.id = sa.sku_id
            JOIN products p ON p.id = s.product_id
            JOIN warehouses w ON w.id = sa.warehouse_id
            LEFT JOIN users u ON u.id = sa.created_by
            WHERE 1=1
        '''
        params = []
        
        if sku_id:
            query += ' AND sa.sku_id = %s'
            params.append(sku_id)
        if warehouse_id:
            query += ' AND sa.warehouse_id = %s'
            params.append(warehouse_id)
        if adjustment_type:
            query += ' AND sa.adjustment_type = %s'
            params.append(adjustment_type)
        if date_from:
            query += ' AND sa.created_at >= %s'
            params.append(date_from)
        if date_to:
            query += ' AND sa.created_at <= %s'
            params.append(date_to + ' 23:59:59')
        
        query += ' ORDER BY sa.created_at DESC LIMIT 500'
        
        cursor.execute(query, params)
        adjustments = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(adjustments), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock-adjustments', methods=['POST'])
@admin_required
def create_stock_adjustment():
    """Create a stock adjustment"""
    data = request.json
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    required = ['sku_id', 'warehouse_id', 'quantity', 'adjustment_type']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    if data['quantity'] <= 0:
        return jsonify({'error': 'Quantity must be greater than 0'}), 400
    
    adjustment_type = data['adjustment_type']
    if adjustment_type not in ADJUSTMENT_TYPES:
        return jsonify({'error': 'Invalid adjustment type'}), 400
    
    direction = ADJUSTMENT_TYPES[adjustment_type]['direction']
    quantity_change = data['quantity'] if direction == 'increase' else -data['quantity']
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT COALESCE(sws.stock, 0) as stock FROM sku_warehouse_stock sws
            WHERE sws.sku_id = %s AND sws.warehouse_id = %s
        ''', (data['sku_id'], data['warehouse_id']))
        stock_row = cursor.fetchone()
        current_stock = stock_row['stock'] if stock_row else 0
        
        new_stock = current_stock + quantity_change
        if new_stock < 0:
            return jsonify({'error': f'Insufficient stock. Available: {current_stock}'}), 400
        
        if direction == 'decrease':
            cursor.execute('''
                UPDATE sku_warehouse_stock 
                SET stock = stock + %s
                WHERE sku_id = %s AND warehouse_id = %s
            ''', (quantity_change, data['sku_id'], data['warehouse_id']))
        else:
            cursor.execute('''
                INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
                VALUES (%s, %s, %s)
                ON CONFLICT (sku_id, warehouse_id) 
                DO UPDATE SET stock = sku_warehouse_stock.stock + EXCLUDED.stock
            ''', (data['sku_id'], data['warehouse_id'], data['quantity']))
        
        sales_channel = None
        if adjustment_type.endswith('_sale'):
            sales_channel = adjustment_type.replace('_sale', '')
        
        cursor.execute('''
            INSERT INTO stock_adjustments (sku_id, warehouse_id, quantity_change, adjustment_type, sales_channel, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (data['sku_id'], data['warehouse_id'], quantity_change, adjustment_type, 
              sales_channel, data.get('notes', ''), session.get('user_id')))
        adjustment_id = cursor.fetchone()['id']
        
        cursor.execute('''
            INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, 
                                         change_type, reference_id, reference_type, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (data['sku_id'], data['warehouse_id'], current_stock, new_stock,
              adjustment_type, adjustment_id, 'stock_adjustment', 
              data.get('notes', ''), session.get('user_id')))
        
        cursor.execute('''
            UPDATE skus SET stock = (
                SELECT COALESCE(SUM(sws.stock), 0) 
                FROM sku_warehouse_stock sws 
                WHERE sws.sku_id = skus.id
            )
            WHERE id = %s
        ''', (data['sku_id'],))
        
        conn.commit()
        return jsonify({
            'message': 'Stock adjusted successfully', 
            'adjustment_id': adjustment_id,
            'new_stock': new_stock
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock-adjustments/bulk', methods=['POST'])
@admin_required
def create_bulk_stock_adjustment():
    """Create multiple stock adjustments at once - supports per-item warehouse_id"""
    data = request.json
    if not data:
        return jsonify({'error': 'ไม่ได้รับข้อมูล'}), 400
    
    if 'adjustments' not in data or not data['adjustments'] or len(data['adjustments']) == 0:
        return jsonify({'error': 'At least one adjustment is required'}), 400
    
    global_warehouse_id = data.get('warehouse_id')
    global_adjustment_type = data.get('adjustment_type')
    global_notes = data.get('notes', '')
    user_id = session.get('user_id')
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        success_count = 0
        errors = []
        
        for adj in data['adjustments']:
            sku_id = adj.get('sku_id')
            quantity = adj.get('quantity', 0)
            warehouse_id = adj.get('warehouse_id') or global_warehouse_id
            adjustment_type = adj.get('adjustment_type') or global_adjustment_type
            notes = adj.get('notes') or global_notes
            
            if not sku_id or quantity <= 0:
                errors.append({'sku_id': sku_id, 'error': 'Invalid data'})
                continue
            
            if not warehouse_id:
                errors.append({'sku_id': sku_id, 'error': 'warehouse_id is required'})
                continue
                
            if not adjustment_type or adjustment_type not in ADJUSTMENT_TYPES:
                errors.append({'sku_id': sku_id, 'error': 'Invalid adjustment type'})
                continue
            
            direction = ADJUSTMENT_TYPES[adjustment_type]['direction']
            quantity_change = quantity if direction == 'increase' else -quantity
            
            cursor.execute('''
                SELECT COALESCE(sws.stock, 0) as stock FROM sku_warehouse_stock sws
                WHERE sws.sku_id = %s AND sws.warehouse_id = %s
            ''', (sku_id, warehouse_id))
            stock_row = cursor.fetchone()
            current_stock = stock_row['stock'] if stock_row else 0
            
            new_stock = current_stock + quantity_change
            if new_stock < 0:
                errors.append({'sku_id': sku_id, 'error': f'Insufficient stock. Available: {current_stock}'})
                continue
            
            if direction == 'decrease':
                cursor.execute('''
                    UPDATE sku_warehouse_stock 
                    SET stock = stock + %s
                    WHERE sku_id = %s AND warehouse_id = %s
                ''', (quantity_change, sku_id, warehouse_id))
            else:
                cursor.execute('''
                    INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sku_id, warehouse_id) 
                    DO UPDATE SET stock = sku_warehouse_stock.stock + EXCLUDED.stock
                ''', (sku_id, warehouse_id, quantity))
            
            sales_channel = None
            if adjustment_type.endswith('_sale'):
                sales_channel = adjustment_type.replace('_sale', '')
            
            cursor.execute('''
                INSERT INTO stock_adjustments (sku_id, warehouse_id, quantity_change, adjustment_type, sales_channel, notes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (sku_id, warehouse_id, quantity_change, adjustment_type, 
                  sales_channel, notes, user_id))
            adjustment_id = cursor.fetchone()['id']
            
            cursor.execute('''
                INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, 
                                             change_type, reference_id, reference_type, notes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (sku_id, warehouse_id, current_stock, new_stock,
                  adjustment_type, adjustment_id, 'stock_adjustment', 
                  notes, user_id))
            
            cursor.execute('''
                UPDATE skus SET stock = (
                    SELECT COALESCE(SUM(sws.stock), 0) 
                    FROM sku_warehouse_stock sws 
                    WHERE sws.sku_id = skus.id
                )
                WHERE id = %s
            ''', (sku_id,))
            
            success_count += 1
        
        conn.commit()
        return jsonify({
            'message': 'Bulk stock adjustment completed', 
            'success_count': success_count,
            'errors': errors
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK AUDIT LOG ROUTES ====================

@app.route('/api/admin/stock-audit-log', methods=['GET'])
@admin_required
def get_stock_audit_log():
    """Get stock audit log with filters"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        sku_id = request.args.get('sku_id')
        warehouse_id = request.args.get('warehouse_id')
        change_type = request.args.get('change_type')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        product_id = request.args.get('product_id')
        
        query = '''
            SELECT sal.id, sal.sku_id, sal.warehouse_id, sal.quantity_before, sal.quantity_after,
                   sal.change_type, sal.reference_id, sal.reference_type, sal.notes,
                   sal.created_at, sal.created_by,
                   s.sku_code, p.name as product_name, p.id as product_id,
                   w.name as warehouse_name,
                   u.username as created_by_name
            FROM stock_audit_log sal
            JOIN skus s ON s.id = sal.sku_id
            JOIN products p ON p.id = s.product_id
            LEFT JOIN warehouses w ON w.id = sal.warehouse_id
            LEFT JOIN users u ON u.id = sal.created_by
            WHERE 1=1
        '''
        params = []
        
        if sku_id:
            query += ' AND sal.sku_id = %s'
            params.append(sku_id)
        if warehouse_id:
            query += ' AND sal.warehouse_id = %s'
            params.append(warehouse_id)
        if change_type:
            query += ' AND sal.change_type = %s'
            params.append(change_type)
        if product_id:
            query += ' AND p.id = %s'
            params.append(product_id)
        if date_from:
            query += ' AND sal.created_at >= %s'
            params.append(date_from)
        if date_to:
            query += ' AND sal.created_at <= %s'
            params.append(date_to + ' 23:59:59')
        
        query += ' ORDER BY sal.created_at DESC LIMIT 1000'
        
        cursor.execute(query, params)
        logs = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(logs), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock-audit-log/summary', methods=['GET'])
@admin_required
def get_stock_audit_summary():
    """Get stock audit summary by change type"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        warehouse_id = request.args.get('warehouse_id')
        
        query = '''
            SELECT sal.change_type, 
                   COUNT(*) as count,
                   SUM(ABS(sal.quantity_after - sal.quantity_before)) as total_quantity
            FROM stock_audit_log sal
            WHERE 1=1
        '''
        params = []
        
        if warehouse_id:
            query += ' AND sal.warehouse_id = %s'
            params.append(warehouse_id)
        if date_from:
            query += ' AND sal.created_at >= %s'
            params.append(date_from)
        if date_to:
            query += ' AND sal.created_at <= %s'
            params.append(date_to + ' 23:59:59')
        
        query += ' GROUP BY sal.change_type ORDER BY count DESC'
        
        cursor.execute(query, params)
        summary = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(summary), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SKU SEARCH FOR STOCK MANAGEMENT ====================

@app.route('/api/admin/skus/search', methods=['GET'])
@admin_required
def search_skus_for_stock():
    """Search SKUs for stock management"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        keyword = request.args.get('keyword', '')
        warehouse_id = request.args.get('warehouse_id')
        
        search_term = f'%{keyword}%'
        
        if warehouse_id:
            query = '''
                SELECT s.id, s.sku_code, s.stock as total_stock, s.price,
                       p.id as product_id, p.name as product_name, p.parent_sku,
                       COALESCE(sws.stock, 0) as warehouse_stock
                FROM skus s
                JOIN products p ON p.id = s.product_id
                LEFT JOIN sku_warehouse_stock sws ON sws.sku_id = s.id AND sws.warehouse_id = %s
                WHERE (s.sku_code ILIKE %s OR p.name ILIKE %s OR p.parent_sku ILIKE %s)
                ORDER BY p.name, s.sku_code
                LIMIT 50
            '''
            params = [warehouse_id, search_term, search_term, search_term]
        else:
            query = '''
                SELECT s.id, s.sku_code, s.stock as total_stock, s.price,
                       p.id as product_id, p.name as product_name, p.parent_sku,
                       0 as warehouse_stock
                FROM skus s
                JOIN products p ON p.id = s.product_id
                WHERE (s.sku_code ILIKE %s OR p.name ILIKE %s OR p.parent_sku ILIKE %s)
                ORDER BY p.name, s.sku_code
                LIMIT 50
            '''
            params = [search_term, search_term, search_term]
        
        cursor.execute(query, params)
        skus = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(skus), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/skus/<int:sku_id>/warehouse-stock', methods=['GET'])
@admin_required
def get_sku_warehouse_stock(sku_id):
    """Get warehouse stock for a specific SKU"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT s.id, s.sku_code, s.stock as total_stock,
                   p.name as product_name, p.spu
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = %s
        ''', (sku_id,))
        
        sku = cursor.fetchone()
        if not sku:
            return jsonify({'error': 'ไม่พบ SKU'}), 404
        
        cursor.execute('''
            SELECT w.id as warehouse_id, w.name as warehouse_name,
                   COALESCE(sws.stock, 0) as stock
            FROM warehouses w
            LEFT JOIN sku_warehouse_stock sws ON sws.warehouse_id = w.id AND sws.sku_id = %s
            WHERE w.is_active = TRUE
            ORDER BY w.name
        ''', (sku_id,))
        
        warehouses = [dict(row) for row in cursor.fetchall()]
        
        result = dict(sku)
        result['warehouses'] = warehouses
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK ALERTS & SUMMARY ====================

@app.route('/api/admin/stock/low-stock-count', methods=['GET'])
@admin_required
def get_low_stock_count():
    """Get count of SKUs with low stock for sidebar badge"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM (
                SELECT s.id 
                FROM skus s
                JOIN products p ON p.id = s.product_id
                WHERE s.stock > 0 AND s.stock <= COALESCE(p.low_stock_threshold, 5)
            ) as low_stock_skus
        ''')
        low_stock = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM skus WHERE stock = 0')
        out_of_stock = cursor.fetchone()['count']
        
        return jsonify({
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'total_alerts': low_stock + out_of_stock
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock/summary', methods=['GET'])
@admin_required
def get_stock_summary():
    """Get stock summary for dashboard"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Total stock value (from warehouse stock, not skus table)
        cursor.execute('SELECT COALESCE(SUM(stock), 0) as total_stock FROM sku_warehouse_stock')
        total_stock = cursor.fetchone()['total_stock']
        
        # Stock by warehouse
        cursor.execute('''
            SELECT w.id, w.name, COALESCE(SUM(sws.stock), 0) as stock,
                   COUNT(DISTINCT sws.sku_id) as sku_count
            FROM warehouses w
            LEFT JOIN sku_warehouse_stock sws ON sws.warehouse_id = w.id
            WHERE w.is_active = TRUE
            GROUP BY w.id, w.name
            ORDER BY w.name
        ''')
        by_warehouse = [dict(row) for row in cursor.fetchall()]
        
        # Low stock and out of stock counts
        cursor.execute('''
            SELECT 
                COUNT(*) FILTER (WHERE s.stock = 0) as out_of_stock,
                COUNT(*) FILTER (WHERE s.stock > 0 AND s.stock <= COALESCE(p.low_stock_threshold, 5)) as low_stock,
                COUNT(*) FILTER (WHERE s.stock > COALESCE(p.low_stock_threshold, 5)) as normal_stock
            FROM skus s
            JOIN products p ON p.id = s.product_id
        ''')
        stock_status = cursor.fetchone()
        
        # Recent stock movements (last 7 days)
        cursor.execute('''
            SELECT DATE(created_at) as date,
                   SUM(CASE WHEN quantity_after > quantity_before THEN quantity_after - quantity_before ELSE 0 END) as stock_in,
                   SUM(CASE WHEN quantity_after < quantity_before THEN quantity_before - quantity_after ELSE 0 END) as stock_out
            FROM stock_audit_log
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        movements = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'total_stock': int(total_stock),
            'by_warehouse': by_warehouse,
            'stock_status': dict(stock_status) if stock_status else {},
            'movements': movements
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock/export', methods=['GET'])
@admin_required
def export_stock():
    """Export stock data as CSV"""
    import io
    import csv
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        export_type = request.args.get('type', 'current')  # current, history
        warehouse_id = request.args.get('warehouse_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        if export_type == 'current':
            # Export current stock
            query = '''
                SELECT p.name as product_name, p.parent_sku, s.sku_code, 
                       s.stock as total_stock, s.price,
                       w.name as warehouse_name, COALESCE(sws.stock, 0) as warehouse_stock
                FROM skus s
                JOIN products p ON p.id = s.product_id
                CROSS JOIN warehouses w
                LEFT JOIN sku_warehouse_stock sws ON sws.sku_id = s.id AND sws.warehouse_id = w.id
                WHERE w.is_active = TRUE
            '''
            params = []
            if warehouse_id:
                query += ' AND w.id = %s'
                params.append(warehouse_id)
            query += ' ORDER BY p.name, s.sku_code, w.name'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            writer.writerow(['ชื่อสินค้า', 'Parent SKU', 'SKU Code', 'สต็อกรวม', 'ราคา', 'โกดัง', 'สต็อกในโกดัง'])
            for row in rows:
                writer.writerow([
                    row['product_name'], row['parent_sku'], row['sku_code'],
                    row['total_stock'], row['price'], row['warehouse_name'], row['warehouse_stock']
                ])
        else:
            # Export stock history
            query = '''
                SELECT sal.created_at, p.name as product_name, s.sku_code,
                       w.name as warehouse_name, sal.change_type,
                       sal.quantity_before, sal.quantity_after,
                       sal.quantity_after - sal.quantity_before as change,
                       u.username as created_by, sal.notes
                FROM stock_audit_log sal
                JOIN skus s ON s.id = sal.sku_id
                JOIN products p ON p.id = s.product_id
                LEFT JOIN warehouses w ON w.id = sal.warehouse_id
                LEFT JOIN users u ON u.id = sal.created_by
                WHERE 1=1
            '''
            params = []
            if warehouse_id:
                query += ' AND sal.warehouse_id = %s'
                params.append(warehouse_id)
            if date_from:
                query += ' AND sal.created_at >= %s'
                params.append(date_from)
            if date_to:
                query += ' AND sal.created_at <= %s'
                params.append(date_to + ' 23:59:59')
            query += ' ORDER BY sal.created_at DESC LIMIT 10000'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            writer.writerow(['วันที่', 'ชื่อสินค้า', 'SKU Code', 'โกดัง', 'ประเภท', 'ก่อน', 'หลัง', 'เปลี่ยนแปลง', 'ผู้ทำรายการ', 'หมายเหตุ'])
            for row in rows:
                writer.writerow([
                    row['created_at'].strftime('%Y-%m-%d %H:%M') if row['created_at'] else '',
                    row['product_name'], row['sku_code'], row['warehouse_name'] or '',
                    row['change_type'], row['quantity_before'], row['quantity_after'],
                    row['change'], row['created_by'] or '', row['notes'] or ''
                ])
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=stock_export_{export_type}.csv'}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock/import', methods=['POST'])
@admin_required
def import_stock():
    """Import stock from CSV"""
    import io
    import csv
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ไม่ได้เลือกไฟล์'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'Only CSV files are supported'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
        reader = csv.DictReader(stream)
        
        adjustment_type = request.form.get('adjustment_type', 'stock_in')
        notes = request.form.get('notes', 'Bulk import from CSV')
        user_id = session.get('user_id')
        
        success_count = 0
        error_count = 0
        errors = []
        
        for row_num, row in enumerate(reader, start=2):
            try:
                sku_code = row.get('sku_code', '').strip()
                warehouse_name = row.get('warehouse', '').strip()
                quantity = int(row.get('quantity', 0))
                
                if not sku_code or not warehouse_name or quantity <= 0:
                    errors.append(f"Row {row_num}: Missing required fields")
                    error_count += 1
                    continue
                
                # Find SKU
                cursor.execute('SELECT id FROM skus WHERE sku_code = %s', (sku_code,))
                sku = cursor.fetchone()
                if not sku:
                    errors.append(f"Row {row_num}: SKU '{sku_code}' not found")
                    error_count += 1
                    continue
                
                # Find warehouse
                cursor.execute('SELECT id FROM warehouses WHERE name = %s AND is_active = TRUE', (warehouse_name,))
                warehouse = cursor.fetchone()
                if not warehouse:
                    errors.append(f"Row {row_num}: Warehouse '{warehouse_name}' not found")
                    error_count += 1
                    continue
                
                sku_id = sku['id']
                warehouse_id = warehouse['id']
                
                # Get current stock
                cursor.execute('''
                    SELECT COALESCE(stock, 0) as stock FROM sku_warehouse_stock
                    WHERE sku_id = %s AND warehouse_id = %s
                ''', (sku_id, warehouse_id))
                stock_row = cursor.fetchone()
                current_stock = stock_row['stock'] if stock_row else 0
                
                # Determine direction
                direction = ADJUSTMENT_TYPES.get(adjustment_type, {}).get('direction', 'increase')
                if direction == 'decrease':
                    new_stock = max(0, current_stock - quantity)
                    stock_change = -(current_stock - new_stock)
                else:
                    new_stock = current_stock + quantity
                    stock_change = quantity
                
                # Update warehouse stock
                cursor.execute('''
                    INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sku_id, warehouse_id) DO UPDATE SET stock = %s
                ''', (sku_id, warehouse_id, new_stock, new_stock))
                
                # Update total SKU stock
                cursor.execute('''
                    UPDATE skus SET stock = (
                        SELECT COALESCE(SUM(stock), 0) FROM sku_warehouse_stock WHERE sku_id = %s
                    ) WHERE id = %s
                ''', (sku_id, sku_id))
                
                # Create audit log
                cursor.execute('''
                    INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after,
                                                 change_type, reference_type, notes, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (sku_id, warehouse_id, current_stock, new_stock, adjustment_type, 
                      'csv_import', notes, user_id))
                
                # Create adjustment record
                cursor.execute('''
                    INSERT INTO stock_adjustments (sku_id, warehouse_id, quantity_change, adjustment_type, notes, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (sku_id, warehouse_id, stock_change, adjustment_type, notes, user_id))
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                error_count += 1
        
        conn.commit()
        
        return jsonify({
            'message': f'Import completed: {success_count} success, {error_count} errors',
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors[:20]  # Return first 20 errors
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/stock/low-stock-items', methods=['GET'])
@admin_required
def get_low_stock_items():
    """Get list of low stock and out of stock items"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        filter_type = request.args.get('filter', 'all')  # all, low, out
        warehouse_id = request.args.get('warehouse_id')
        
        query = '''
            SELECT s.id, s.sku_code, s.stock as total_stock,
                   p.name as product_name, p.parent_sku,
                   COALESCE(p.low_stock_threshold, 5) as threshold,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE 1=1
        '''
        params = []
        
        if filter_type == 'out':
            query += ' AND s.stock = 0'
        elif filter_type == 'low':
            query += ' AND s.stock > 0 AND s.stock <= COALESCE(p.low_stock_threshold, 5)'
        else:
            query += ' AND s.stock <= COALESCE(p.low_stock_threshold, 5)'
        
        query += ' ORDER BY s.stock ASC, p.name LIMIT 100'
        
        cursor.execute(query, params)
        items = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(items), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==========================================
# Made-to-Order (สินค้าสั่งผลิต) APIs
# ==========================================

# Generate quotation request number
def generate_request_number():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM quotation_requests")
        count = cursor.fetchone()[0] + 1
        return f"REQ-{datetime.now().strftime('%y%m')}-{count:04d}"
    finally:
        cursor.close()
        conn.close()

# Generate quote number
def generate_quote_number():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM quotations")
        count = cursor.fetchone()[0] + 1
        return f"QT-{datetime.now().strftime('%y%m')}-{count:04d}"
    finally:
        cursor.close()
        conn.close()

# Generate MTO order number
def generate_mto_order_number():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM mto_orders")
        count = cursor.fetchone()[0] + 1
        return f"MTO-{datetime.now().strftime('%y%m')}-{count:04d}"
    finally:
        cursor.close()
        conn.close()

@app.route('/api/mto/products', methods=['GET'])
@login_required
def get_mto_products():
    """Get made-to-order products for reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        # Get user's tier
        cursor.execute('''
            SELECT t.id as tier_id, t.name as tier_name
            FROM users u
            LEFT JOIN reseller_tiers t ON u.reseller_tier_id = t.id
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        tier_id = user['tier_id'] if user else None
        
        # Get MTO products with tier pricing
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku, p.description, 
                   p.production_days, p.deposit_percent, p.product_type,
                   b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT MIN(COALESCE(tp.adjusted_price, s.price)) 
                    FROM skus s 
                    LEFT JOIN product_tier_pricing tp ON tp.sku_id = s.id AND tp.tier_id = %s
                    WHERE s.product_id = p.id) as min_price,
                   (SELECT MAX(COALESCE(tp.adjusted_price, s.price)) 
                    FROM skus s 
                    LEFT JOIN product_tier_pricing tp ON tp.sku_id = s.id AND tp.tier_id = %s
                    WHERE s.product_id = p.id) as max_price
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.product_type = 'made_to_order' AND p.status = 'active'
            ORDER BY p.created_at DESC
        ''', (tier_id, tier_id))
        products = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(products), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/products/<int:product_id>', methods=['GET'])
@login_required
def get_mto_product_detail(product_id):
    """Get MTO product details with SKUs and MOQ"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        # Get user's tier
        cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        tier_id = user['reseller_tier_id'] if user else None
        
        # Get product
        cursor.execute('''
            SELECT p.*, b.name as brand_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.id = %s AND p.product_type = 'made_to_order'
        ''', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Get SKUs with tier pricing and MOQ (exclude cost_price for resellers)
        cursor.execute('''
            SELECT s.id, s.product_id, s.sku_code, s.price, s.stock,
                   COALESCE(tp.adjusted_price, s.price) as final_price,
                   COALESCE(s.min_order_qty, 1) as min_order_qty
            FROM skus s
            LEFT JOIN product_tier_pricing tp ON tp.sku_id = s.id AND tp.tier_id = %s
            WHERE s.product_id = %s
            ORDER BY s.id
        ''', (tier_id, product_id))
        skus = [dict(row) for row in cursor.fetchall()]
        
        # Get option values for each SKU
        for sku in skus:
            cursor.execute('''
                SELECT o.name as option_name, ov.value as option_value
                FROM sku_values_map svm
                JOIN option_values ov ON svm.option_value_id = ov.id
                JOIN options o ON ov.option_id = o.id
                WHERE svm.sku_id = %s
                ORDER BY o.sort_order
            ''', (sku['id'],))
            sku['options'] = [dict(row) for row in cursor.fetchall()]
        
        # Get images
        cursor.execute('''
            SELECT id, image_url, sort_order FROM product_images
            WHERE product_id = %s ORDER BY sort_order
        ''', (product_id,))
        images = [dict(row) for row in cursor.fetchall()]
        
        product = dict(product)
        product['skus'] = skus
        product['images'] = images
        
        return jsonify(product), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/quotation-requests', methods=['POST'])
@login_required
@csrf_protect
def create_quotation_request():
    """Create new quotation request from reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        user_id = session['user_id']
        items = data.get('items', [])
        notes = data.get('notes', '')
        
        if not items:
            return jsonify({'error': 'กรุณาเลือกสินค้าอย่างน้อย 1 รายการ'}), 400
        
        # Generate request number
        request_number = generate_request_number()
        
        # Create request
        cursor.execute('''
            INSERT INTO quotation_requests (request_number, reseller_id, notes, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
        ''', (request_number, user_id, notes))
        request_id = cursor.fetchone()['id']
        
        # Add items
        for item in items:
            cursor.execute('''
                INSERT INTO quotation_request_items 
                (request_id, product_id, sku_id, sku_code, option_snapshot, quantity)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (request_id, item['product_id'], item.get('sku_id'), 
                  item.get('sku_code'), json.dumps(item.get('options', {})), item['quantity']))
        
        conn.commit()
        
        # Send notification to admin (optional - can add email later)
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'request_number': request_number,
            'message': 'ส่งคำขอใบเสนอราคาสำเร็จ'
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/quotation-requests', methods=['GET'])
@login_required
def get_my_quotation_requests():
    """Get reseller's quotation requests"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        status = request.args.get('status')
        
        query = '''
            SELECT qr.*, 
                   (SELECT COUNT(*) FROM quotation_request_items WHERE request_id = qr.id) as item_count,
                   (SELECT SUM(quantity) FROM quotation_request_items WHERE request_id = qr.id) as total_qty
            FROM quotation_requests qr
            WHERE qr.reseller_id = %s
        '''
        params = [user_id]
        
        if status:
            query += ' AND qr.status = %s'
            params.append(status)
        
        query += ' ORDER BY qr.created_at DESC'
        
        cursor.execute(query, params)
        requests = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(requests), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/quotations', methods=['GET'])
@login_required
def get_my_quotations():
    """Get reseller's quotations"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        status = request.args.get('status')
        
        query = '''
            SELECT q.*, 
                   (SELECT COUNT(*) FROM quotation_items WHERE quotation_id = q.id) as item_count
            FROM quotations q
            WHERE q.reseller_id = %s
        '''
        params = [user_id]
        
        if status:
            query += ' AND q.status = %s'
            params.append(status)
        
        query += ' ORDER BY q.created_at DESC'
        
        cursor.execute(query, params)
        quotations = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(quotations), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/quotations/<int:quote_id>', methods=['GET'])
@login_required
def get_quotation_detail(quote_id):
    """Get quotation details"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        role = session.get('role')
        
        # Get quotation
        cursor.execute('''
            SELECT q.*, u.full_name as reseller_name, u.email as reseller_email
            FROM quotations q
            JOIN users u ON q.reseller_id = u.id
            WHERE q.id = %s
        ''', (quote_id,))
        quotation = cursor.fetchone()
        
        if not quotation:
            return jsonify({'error': 'ไม่พบใบเสนอราคา'}), 404
        
        # Check access (reseller can only see their own, admin can see all)
        if role not in ['Super Admin', 'Assistant Admin'] and quotation['reseller_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        
        # Get items
        cursor.execute('''
            SELECT qi.*, p.name as product_name,
                   (SELECT image_url FROM product_images WHERE product_id = qi.product_id ORDER BY sort_order LIMIT 1) as image_url
            FROM quotation_items qi
            JOIN products p ON qi.product_id = p.id
            WHERE qi.quotation_id = %s
        ''', (quote_id,))
        items = [dict(row) for row in cursor.fetchall()]
        
        result = dict(quotation)
        result['items'] = items
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/orders', methods=['GET'])
@login_required
def get_my_mto_orders():
    """Get reseller's MTO orders"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        status = request.args.get('status')
        
        query = '''
            SELECT mo.*, q.quote_number,
                   (SELECT COUNT(*) FROM mto_order_items WHERE mto_order_id = mo.id) as item_count
            FROM mto_orders mo
            LEFT JOIN quotations q ON mo.quotation_id = q.id
            WHERE mo.reseller_id = %s
        '''
        params = [user_id]
        
        if status:
            query += ' AND mo.status = %s'
            params.append(status)
        
        query += ' ORDER BY mo.created_at DESC'
        
        cursor.execute(query, params)
        orders = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(orders), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/orders/<int:order_id>', methods=['GET'])
@login_required
def get_mto_order_detail(order_id):
    """Get MTO order details with timeline"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        role = session.get('role')
        
        # Get order
        cursor.execute('''
            SELECT mo.*, q.quote_number, u.full_name as reseller_name
            FROM mto_orders mo
            LEFT JOIN quotations q ON mo.quotation_id = q.id
            JOIN users u ON mo.reseller_id = u.id
            WHERE mo.id = %s
        ''', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        # Check access
        if role not in ['Super Admin', 'Assistant Admin'] and order['reseller_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        
        # Get items
        cursor.execute('''
            SELECT oi.*, 
                   (SELECT image_url FROM product_images WHERE product_id = oi.product_id ORDER BY sort_order LIMIT 1) as image_url
            FROM mto_order_items oi
            WHERE oi.mto_order_id = %s
        ''', (order_id,))
        items = [dict(row) for row in cursor.fetchall()]
        
        # Get payments
        cursor.execute('''
            SELECT * FROM mto_payments
            WHERE mto_order_id = %s
            ORDER BY created_at
        ''', (order_id,))
        payments = [dict(row) for row in cursor.fetchall()]
        
        # Build timeline
        timeline = []
        order_dict = dict(order)
        
        timeline.append({
            'status': 'created',
            'label': 'สร้างคำสั่งซื้อ',
            'date': order_dict['created_at'].isoformat() if order_dict['created_at'] else None,
            'completed': True
        })
        
        if order_dict['payment_confirmed_at']:
            timeline.append({
                'status': 'deposit_paid',
                'label': f"ชำระมัดจำ ฿{order_dict['deposit_paid']:,.0f}",
                'date': order_dict['payment_confirmed_at'].isoformat(),
                'completed': True
            })
        
        if order_dict['production_started_at']:
            timeline.append({
                'status': 'production',
                'label': f"กำลังผลิต ({order_dict['production_days']} วัน)",
                'date': order_dict['production_started_at'].isoformat(),
                'completed': order_dict['production_completed_at'] is not None
            })
        
        if order_dict['balance_requested_at']:
            timeline.append({
                'status': 'balance_requested',
                'label': f"เรียกเก็บยอดคงเหลือ ฿{order_dict['balance_amount']:,.0f}",
                'date': order_dict['balance_requested_at'].isoformat(),
                'completed': order_dict['balance_paid_at'] is not None
            })
        
        if order_dict['shipped_at']:
            timeline.append({
                'status': 'shipped',
                'label': 'จัดส่งแล้ว',
                'date': order_dict['shipped_at'].isoformat(),
                'completed': True,
                'tracking': order_dict['tracking_number'],
                'provider': order_dict['shipping_provider']
            })
        
        order_dict['items'] = items
        order_dict['payments'] = payments
        order_dict['timeline'] = timeline
        
        return jsonify(order_dict), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/mto/orders/<int:order_id>/pay', methods=['POST'])
@login_required
@csrf_protect
def submit_mto_payment(order_id):
    """Submit payment for MTO order (deposit or balance)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        
        # Get order
        cursor.execute('SELECT * FROM mto_orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['reseller_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์'}), 403
        
        data = request.get_json()
        payment_type = data.get('payment_type')  # deposit or balance
        amount = data.get('amount')
        slip_image_url = data.get('slip_image_url')
        payment_method = data.get('payment_method', 'bank_transfer')
        
        if payment_type not in ['deposit', 'balance']:
            return jsonify({'error': 'ประเภทการชำระไม่ถูกต้อง'}), 400
        
        # Create payment record
        cursor.execute('''
            INSERT INTO mto_payments (mto_order_id, payment_type, amount, payment_method, slip_image_url, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING id
        ''', (order_id, payment_type, amount, payment_method, slip_image_url))
        payment_id = cursor.fetchone()['id']
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'payment_id': payment_id,
            'message': 'ส่งหลักฐานการชำระเงินสำเร็จ รอการตรวจสอบ'
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==========================================
# Admin MTO Management APIs
# ==========================================

@app.route('/api/admin/mto/products', methods=['GET'])
@admin_required
def admin_get_mto_products():
    """Get all MTO products for admin"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        status = request.args.get('status')
        
        query = '''
            SELECT p.*, b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT COUNT(*) FROM skus WHERE product_id = p.id) as sku_count
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.product_type = 'made_to_order'
        '''
        params = []
        
        if status:
            query += ' AND p.status = %s'
            params.append(status)
        
        query += ' ORDER BY p.created_at DESC'
        
        cursor.execute(query, params)
        products = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(products), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/products', methods=['POST'])
@admin_required
def admin_create_mto_product():
    """Create a new MTO product"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        name = data.get('name')
        parent_sku = data.get('parent_sku')
        brand_id = data.get('brand_id')
        category_id = data.get('category_id')
        description = data.get('description', '')
        production_days = data.get('production_days', 7)
        deposit_percent = data.get('deposit_percent', 50)
        status = data.get('status', 'draft')
        options = data.get('options', [])
        images = data.get('images') or data.get('image_urls', [])
        size_chart_image_url = data.get('size_chart_image_url')
        skus_data = data.get('skus', [])
        
        if not name or not parent_sku or not brand_id:
            return jsonify({'error': 'กรุณากรอกข้อมูลที่จำเป็น'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM products WHERE parent_sku = %s', (parent_sku,))
        if cursor.fetchone():
            return jsonify({'error': 'รหัส SPU นี้มีอยู่แล้ว'}), 400
        
        cursor.execute('''
            INSERT INTO products (name, parent_sku, brand_id, category_id, description, product_type, production_days, deposit_percent, status, size_chart_image_url)
            VALUES (%s, %s, %s, %s, %s, 'made_to_order', %s, %s, %s, %s)
            RETURNING id
        ''', (name, parent_sku, brand_id, category_id, description, production_days, deposit_percent, status, size_chart_image_url))
        product_id = cursor.fetchone()['id']
        
        # Save images
        for i, img_url in enumerate(images):
            cursor.execute('''
                INSERT INTO product_images (product_id, image_url, sort_order)
                VALUES (%s, %s, %s)
            ''', (product_id, img_url, i))
        
        # Create options and generate SKUs
        option_values_map = []
        for opt_idx, opt in enumerate(options):
            opt_name = opt.get('name')
            values = opt.get('values', [])
            
            cursor.execute('''
                INSERT INTO options (product_id, name)
                VALUES (%s, %s)
                RETURNING id
            ''', (product_id, opt_name))
            option_id = cursor.fetchone()['id']
            
            opt_value_ids = []
            for val_idx, val in enumerate(values):
                val_name = val.get('value')
                min_qty = val.get('min_order_qty', 0) if opt_idx == 0 else 0
                
                cursor.execute('''
                    INSERT INTO option_values (option_id, value, sort_order, min_order_qty)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                ''', (option_id, val_name, val_idx, min_qty))
                opt_value_ids.append(cursor.fetchone()['id'])
            
            option_values_map.append(opt_value_ids)
        
        if skus_data:
            for i, sku_info in enumerate(skus_data):
                sku_code = sku_info.get('sku_code', f"{parent_sku}-{i}")
                price = sku_info.get('price', 0)
                cost_price = sku_info.get('cost_price', 0)
                
                cursor.execute('''
                    INSERT INTO skus (product_id, sku_code, price, cost_price, stock)
                    VALUES (%s, %s, %s, %s, 0)
                    RETURNING id
                ''', (product_id, sku_code, price, cost_price))
                sku_id = cursor.fetchone()['id']
                
                variant_values = sku_info.get('variant_values', [])
                for j, val_name in enumerate(variant_values):
                    if j < len(option_values_map):
                        for ov_id in option_values_map[j]:
                            cursor.execute('''
                                SELECT value FROM option_values WHERE id = %s
                            ''', (ov_id,))
                            row = cursor.fetchone()
                            if row and row['value'] == val_name:
                                cursor.execute('''
                                    INSERT INTO sku_values_map (sku_id, option_value_id)
                                    VALUES (%s, %s)
                                ''', (sku_id, ov_id))
                                break
        elif option_values_map:
            from itertools import product as cartesian
            combinations = list(cartesian(*option_values_map))
            
            for combo in combinations:
                sku_suffix = '-'.join([str(v) for v in combo])
                sku_code = f"{parent_sku}-{sku_suffix}"
                
                cursor.execute('''
                    INSERT INTO skus (product_id, sku_code, price, stock)
                    VALUES (%s, %s, 0, 0)
                    RETURNING id
                ''', (product_id, sku_code))
                sku_id = cursor.fetchone()['id']
                
                for ov_id in combo:
                    cursor.execute('''
                        INSERT INTO sku_values_map (sku_id, option_value_id)
                        VALUES (%s, %s)
                    ''', (sku_id, ov_id))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'product_id': product_id,
            'message': 'สร้างสินค้าสั่งผลิตสำเร็จ'
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/products/<int:product_id>', methods=['GET'])
@admin_required
def admin_get_mto_product(product_id):
    """Get single MTO product with details"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get product
        cursor.execute('''
            SELECT p.*, b.name as brand_name
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE p.id = %s AND p.product_type = 'made_to_order'
        ''', (product_id,))
        product = cursor.fetchone()
        
        if not product:
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        product = dict(product)
        
        # Get images
        cursor.execute('SELECT * FROM product_images WHERE product_id = %s ORDER BY sort_order', (product_id,))
        product['images'] = [dict(row) for row in cursor.fetchall()]
        
        # Get options with values
        cursor.execute('SELECT * FROM options WHERE product_id = %s ORDER BY id', (product_id,))
        options = [dict(row) for row in cursor.fetchall()]
        
        for opt in options:
            cursor.execute('SELECT * FROM option_values WHERE option_id = %s ORDER BY sort_order', (opt['id'],))
            opt['values'] = [dict(row) for row in cursor.fetchall()]
        
        product['options'] = options
        
        # Get SKUs
        cursor.execute('SELECT * FROM skus WHERE product_id = %s ORDER BY id', (product_id,))
        skus = [dict(row) for row in cursor.fetchall()]
        
        for sku in skus:
            cursor.execute('''
                SELECT ov.id, ov.value, o.name as option_name
                FROM sku_values_map svm
                JOIN option_values ov ON svm.option_value_id = ov.id
                JOIN options o ON ov.option_id = o.id
                WHERE svm.sku_id = %s
            ''', (sku['id'],))
            sku['option_values'] = [dict(row) for row in cursor.fetchall()]
        
        product['skus'] = skus
        
        return jsonify(product), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/products/<int:product_id>', methods=['PUT'])
@admin_required
def admin_update_mto_product(product_id):
    """Update MTO product"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM products WHERE id = %s AND product_type = %s', (product_id, 'made_to_order'))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        update_fields = []
        params = []
        
        for field in ['name', 'description', 'production_days', 'deposit_percent', 'status', 'brand_id', 'category_id', 'parent_sku', 'size_chart_image_url']:
            if field in data:
                update_fields.append(f'{field} = %s')
                params.append(data[field])
        
        if update_fields:
            update_fields.append('updated_at = CURRENT_TIMESTAMP')
            params.append(product_id)
            cursor.execute(f'''
                UPDATE products SET {', '.join(update_fields)}
                WHERE id = %s
            ''', params)
        
        image_urls = data.get('image_urls') or data.get('images')
        if image_urls is not None:
            cursor.execute('DELETE FROM product_images WHERE product_id = %s', (product_id,))
            for i, img_url in enumerate(image_urls):
                cursor.execute('''
                    INSERT INTO product_images (product_id, image_url, sort_order)
                    VALUES (%s, %s, %s)
                ''', (product_id, img_url, i))
        
        if 'options' in data:
            cursor.execute('SELECT id FROM options WHERE product_id = %s', (product_id,))
            old_opts = cursor.fetchall()
            for opt in old_opts:
                cursor.execute('DELETE FROM option_values WHERE option_id = %s', (opt['id'],))
            cursor.execute('DELETE FROM options WHERE product_id = %s', (product_id,))
            
            option_values_map = []
            for opt_idx, opt in enumerate(data['options']):
                opt_name = opt.get('name')
                values = opt.get('values', [])
                
                cursor.execute('''
                    INSERT INTO options (product_id, name)
                    VALUES (%s, %s)
                    RETURNING id
                ''', (product_id, opt_name))
                option_id = cursor.fetchone()['id']
                
                opt_value_ids = []
                for val_idx, val in enumerate(values):
                    val_name = val.get('value')
                    min_qty = val.get('min_order_qty', 0) if opt_idx == 0 else 0
                    
                    cursor.execute('''
                        INSERT INTO option_values (option_id, value, sort_order, min_order_qty)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    ''', (option_id, val_name, val_idx, min_qty))
                    opt_value_ids.append(cursor.fetchone()['id'])
                
                option_values_map.append(opt_value_ids)
            
            if 'skus' in data:
                cursor.execute('SELECT id FROM skus WHERE product_id = %s', (product_id,))
                old_skus = cursor.fetchall()
                for old_sku in old_skus:
                    cursor.execute('DELETE FROM sku_values_map WHERE sku_id = %s', (old_sku['id'],))
                cursor.execute('DELETE FROM skus WHERE product_id = %s', (product_id,))
                
                parent_sku = data.get('parent_sku', '')
                for i, sku_info in enumerate(data['skus']):
                    sku_code = sku_info.get('sku_code', f"{parent_sku}-{i}")
                    price = sku_info.get('price', 0)
                    cost_price = sku_info.get('cost_price', 0)
                    
                    cursor.execute('''
                        INSERT INTO skus (product_id, sku_code, price, cost_price, stock)
                        VALUES (%s, %s, %s, %s, 0)
                        RETURNING id
                    ''', (product_id, sku_code, price, cost_price))
                    new_sku_id = cursor.fetchone()['id']
                    
                    variant_values = sku_info.get('variant_values', [])
                    for j, val_name in enumerate(variant_values):
                        if j < len(option_values_map):
                            for ov_id in option_values_map[j]:
                                cursor.execute('SELECT value FROM option_values WHERE id = %s', (ov_id,))
                                row = cursor.fetchone()
                                if row and row['value'] == val_name:
                                    cursor.execute('''
                                        INSERT INTO sku_values_map (sku_id, option_value_id)
                                        VALUES (%s, %s)
                                    ''', (new_sku_id, ov_id))
                                    break
        
        conn.commit()
        
        return jsonify({'success': True, 'message': 'อัปเดตสินค้าสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/products/<int:product_id>', methods=['DELETE'])
@admin_required
def admin_delete_mto_product(product_id):
    """Delete MTO product"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s AND product_type = %s', (product_id, 'made_to_order'))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบสินค้า'}), 404
        
        # Check if product is used in quotations
        cursor.execute('SELECT id FROM quotation_request_items WHERE product_id = %s LIMIT 1', (product_id,))
        if cursor.fetchone():
            return jsonify({'error': 'ไม่สามารถลบได้ เนื่องจากมีการใช้ในคำขอใบเสนอราคา'}), 400
        
        cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'ลบสินค้าสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/quotation-requests', methods=['GET'])
@admin_required
def admin_get_quotation_requests():
    """Get all quotation requests for admin"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        status = request.args.get('status')
        
        query = '''
            SELECT qr.*, u.full_name as reseller_name, u.email,
                   (SELECT COUNT(*) FROM quotation_request_items WHERE request_id = qr.id) as item_count,
                   (SELECT SUM(quantity) FROM quotation_request_items WHERE request_id = qr.id) as total_qty
            FROM quotation_requests qr
            JOIN users u ON qr.reseller_id = u.id
        '''
        params = []
        
        if status:
            query += ' WHERE qr.status = %s'
            params.append(status)
        
        query += ' ORDER BY qr.created_at DESC'
        
        cursor.execute(query, params)
        requests = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(requests), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/quotation-requests/<int:request_id>', methods=['GET'])
@admin_required
def admin_get_quotation_request_detail(request_id):
    """Get quotation request details"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get request
        cursor.execute('''
            SELECT qr.*, u.full_name as reseller_name, u.email, u.phone,
                   t.name as tier_name
            FROM quotation_requests qr
            JOIN users u ON qr.reseller_id = u.id
            LEFT JOIN reseller_tiers t ON u.reseller_tier_id = t.id
            WHERE qr.id = %s
        ''', (request_id,))
        req = cursor.fetchone()
        
        if not req:
            return jsonify({'error': 'ไม่พบคำขอ'}), 404
        
        # Get items
        cursor.execute('''
            SELECT qri.*, p.name as product_name, p.production_days, p.deposit_percent,
                   s.sku_code, s.price as base_price,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url
            FROM quotation_request_items qri
            JOIN products p ON qri.product_id = p.id
            LEFT JOIN skus s ON qri.sku_id = s.id
            WHERE qri.request_id = %s
        ''', (request_id,))
        items = [dict(row) for row in cursor.fetchall()]
        
        result = dict(req)
        result['items'] = items
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/quotations', methods=['POST'])
@admin_required
@csrf_protect
def admin_create_quotation():
    """Create quotation from request or directly"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        admin_id = session['user_id']
        request_id = data.get('request_id')
        reseller_id = data.get('reseller_id')
        items = data.get('items', [])
        discount_amount = data.get('discount_amount', 0)
        deposit_percent = data.get('deposit_percent', 50)
        production_days = data.get('production_days', 14)
        valid_days = data.get('valid_days', 7)
        admin_notes = data.get('admin_notes', '')
        
        if not reseller_id:
            return jsonify({'error': 'กรุณาระบุ Reseller'}), 400
        
        if not items:
            return jsonify({'error': 'กรุณาเพิ่มรายการสินค้า'}), 400
        
        # Calculate totals
        subtotal = sum(item['final_price'] * item['quantity'] for item in items)
        total_amount = subtotal - discount_amount
        deposit_amount = total_amount * deposit_percent / 100
        balance_amount = total_amount - deposit_amount
        
        # Calculate expected completion date
        from datetime import date, timedelta
        expected_date = date.today() + timedelta(days=production_days + 7)  # +7 for payment processing
        valid_until = date.today() + timedelta(days=valid_days)
        
        # Generate quote number
        quote_number = generate_quote_number()
        
        # Create quotation
        cursor.execute('''
            INSERT INTO quotations (
                quote_number, request_id, reseller_id, admin_id, status,
                subtotal, discount_amount, total_amount,
                deposit_percent, deposit_amount, balance_amount,
                production_days, expected_completion_date, valid_until,
                admin_notes
            ) VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (quote_number, request_id, reseller_id, admin_id,
              subtotal, discount_amount, total_amount,
              deposit_percent, deposit_amount, balance_amount,
              production_days, expected_date, valid_until, admin_notes))
        quote_id = cursor.fetchone()['id']
        
        # Add items
        for item in items:
            line_total = item['final_price'] * item['quantity']
            cursor.execute('''
                INSERT INTO quotation_items (
                    quotation_id, product_id, sku_id, sku_code, product_name,
                    option_text, quantity, original_price, final_price, line_total, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (quote_id, item['product_id'], item.get('sku_id'), item.get('sku_code'),
                  item['product_name'], item.get('option_text', ''), item['quantity'],
                  item.get('original_price', item['final_price']), item['final_price'],
                  line_total, item.get('notes', '')))
        
        # Update request status if from request
        if request_id:
            cursor.execute('''
                UPDATE quotation_requests SET status = 'quoted', updated_at = NOW()
                WHERE id = %s
            ''', (request_id,))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'quotation_id': quote_id,
            'quote_number': quote_number,
            'message': 'สร้างใบเสนอราคาสำเร็จ'
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/quotations', methods=['GET'])
@admin_required
def admin_get_quotations():
    """Get all quotations for admin"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        status = request.args.get('status')
        
        query = '''
            SELECT q.*, u.full_name as reseller_name, u.email,
                   (SELECT COUNT(*) FROM quotation_items WHERE quotation_id = q.id) as item_count
            FROM quotations q
            JOIN users u ON q.reseller_id = u.id
        '''
        params = []
        
        if status:
            query += ' WHERE q.status = %s'
            params.append(status)
        
        query += ' ORDER BY q.created_at DESC'
        
        cursor.execute(query, params)
        quotations = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(quotations), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/quotations/<int:quote_id>/send', methods=['POST'])
@admin_required
@csrf_protect
def admin_send_quotation(quote_id):
    """Send quotation to reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get quotation and reseller info
        cursor.execute('''
            SELECT q.*, u.email, u.full_name as reseller_name
            FROM quotations q
            JOIN users u ON q.reseller_id = u.id
            WHERE q.id = %s
        ''', (quote_id,))
        quote = cursor.fetchone()
        
        if not quote:
            return jsonify({'error': 'ไม่พบใบเสนอราคา'}), 404
        
        # Update status
        cursor.execute('''
            UPDATE quotations SET status = 'sent', sent_at = NOW(), updated_at = NOW()
            WHERE id = %s
        ''', (quote_id,))
        
        # Update request status if exists
        if quote['request_id']:
            cursor.execute('''
                UPDATE quotation_requests SET status = 'quoted', updated_at = NOW()
                WHERE id = %s
            ''', (quote['request_id'],))
        
        conn.commit()
        
        # Send email notification (optional)
        try:
            send_quotation_email(quote)
        except:
            pass  # Don't fail if email fails
        
        return jsonify({
            'success': True,
            'message': 'ส่งใบเสนอราคาสำเร็จ'
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_quotation_email(quote):
    """Send quotation email to reseller"""
    try:
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        if not gmail_password:
            return
        
        sender_email = "ekgshops@gmail.com"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[EKG Shops] ใบเสนอราคา {quote['quote_number']}"
        msg['From'] = sender_email
        msg['To'] = quote['email']
        
        html = f"""
        <html>
        <body style="font-family: 'Sarabun', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">EKG Shops</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">ใบเสนอราคาสินค้าสั่งผลิต</p>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <p>สวัสดีคุณ {quote['reseller_name']},</p>
                <p>ใบเสนอราคาของคุณพร้อมแล้ว:</p>
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>เลขที่:</strong> {quote['quote_number']}</p>
                    <p><strong>ยอดรวม:</strong> ฿{quote['total_amount']:,.2f}</p>
                    <p><strong>มัดจำ ({quote['deposit_percent']}%):</strong> ฿{quote['deposit_amount']:,.2f}</p>
                    <p><strong>ระยะเวลาผลิต:</strong> {quote['production_days']} วัน</p>
                    <p><strong>ใช้ได้ถึง:</strong> {quote['valid_until']}</p>
                </div>
                <p>กรุณาเข้าสู่ระบบเพื่อดูรายละเอียดและชำระมัดจำ</p>
                <a href="https://ekgshops.com" style="display: inline-block; background: #667eea; color: white; padding: 12px 30px; border-radius: 5px; text-decoration: none; margin-top: 10px;">เข้าสู่ระบบ</a>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, gmail_password)
            server.send_message(msg)
            
    except Exception as e:
        print(f"Email error: {e}")

@app.route('/api/admin/mto/orders', methods=['GET'])
@admin_required
def admin_get_mto_orders():
    """Get all MTO orders for admin"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        status = request.args.get('status')
        
        query = '''
            SELECT mo.*, q.quote_number, u.full_name as reseller_name,
                   (SELECT COUNT(*) FROM mto_order_items WHERE mto_order_id = mo.id) as item_count
            FROM mto_orders mo
            LEFT JOIN quotations q ON mo.quotation_id = q.id
            JOIN users u ON mo.reseller_id = u.id
        '''
        params = []
        
        if status:
            query += ' WHERE mo.status = %s'
            params.append(status)
        
        query += ' ORDER BY mo.created_at DESC'
        
        cursor.execute(query, params)
        orders = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(orders), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/payments', methods=['GET'])
@admin_required
def admin_get_mto_payments():
    """Get pending MTO payments for admin"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        status = request.args.get('status', 'pending')
        
        cursor.execute('''
            SELECT p.*, mo.order_number, u.full_name as reseller_name
            FROM mto_payments p
            JOIN mto_orders mo ON p.mto_order_id = mo.id
            JOIN users u ON mo.reseller_id = u.id
            WHERE p.status = %s
            ORDER BY p.created_at DESC
        ''', (status,))
        payments = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(payments), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/payments/<int:payment_id>/confirm', methods=['POST'])
@admin_required
@csrf_protect
def admin_confirm_mto_payment(payment_id):
    """Confirm MTO payment"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        admin_id = session['user_id']
        
        # Get payment
        cursor.execute('SELECT * FROM mto_payments WHERE id = %s', (payment_id,))
        payment = cursor.fetchone()
        
        if not payment:
            return jsonify({'error': 'ไม่พบการชำระเงิน'}), 404
        
        # Update payment
        cursor.execute('''
            UPDATE mto_payments SET status = 'confirmed', confirmed_by = %s, confirmed_at = NOW()
            WHERE id = %s
        ''', (admin_id, payment_id))
        
        # Get order
        cursor.execute('SELECT * FROM mto_orders WHERE id = %s', (payment['mto_order_id'],))
        order = cursor.fetchone()
        
        # Update order based on payment type
        if payment['payment_type'] == 'deposit':
            new_deposit_paid = float(order['deposit_paid'] or 0) + float(payment['amount'])
            new_status = 'deposit_paid' if new_deposit_paid >= float(order['deposit_amount']) else order['status']
            
            # Calculate expected completion date
            from datetime import date, timedelta
            expected_date = date.today() + timedelta(days=order['production_days'])
            
            cursor.execute('''
                UPDATE mto_orders SET 
                    deposit_paid = %s, status = %s, 
                    payment_confirmed_at = NOW(), 
                    production_started_at = NOW(),
                    expected_completion_date = %s,
                    updated_at = NOW()
                WHERE id = %s
            ''', (new_deposit_paid, new_status, expected_date, order['id']))
            
        elif payment['payment_type'] == 'balance':
            new_balance_paid = float(order['balance_paid'] or 0) + float(payment['amount'])
            new_status = 'balance_paid' if new_balance_paid >= float(order['balance_amount']) else order['status']
            
            cursor.execute('''
                UPDATE mto_orders SET balance_paid = %s, status = %s, balance_paid_at = NOW(), updated_at = NOW()
                WHERE id = %s
            ''', (new_balance_paid, new_status, order['id']))
        
        conn.commit()
        
        # Send payment confirmation email
        try:
            send_mto_payment_confirmed_email(order, payment)
        except:
            pass
        
        return jsonify({
            'success': True,
            'message': 'ยืนยันการชำระเงินสำเร็จ'
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_mto_payment_confirmed_email(order, payment):
    """Send payment confirmation email to reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT email, full_name FROM users WHERE id = %s', (order['reseller_id'],))
        reseller = cursor.fetchone()
        
        if not reseller or not reseller.get('email'):
            return
        
        payment_type_text = "มัดจำ" if payment['payment_type'] == 'deposit' else "ยอดคงเหลือ"
        next_step = 'สินค้าของคุณจะเข้าสู่กระบวนการผลิต' if payment['payment_type'] == 'deposit' else 'สินค้าจะถูกจัดส่งให้คุณเร็วๆ นี้'
        
        html = f"""
        <div style="font-family: 'Sarabun', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">EKG Shops</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">ยืนยันการชำระเงินสำเร็จ</p>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <p>สวัสดีคุณ {reseller['full_name']},</p>
                <p>เราได้รับและยืนยันการชำระ{payment_type_text}ของคุณเรียบร้อยแล้ว</p>
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>เลขที่คำสั่งซื้อ:</strong> {order['order_number']}</p>
                    <p><strong>ประเภท:</strong> {payment_type_text}</p>
                    <p><strong>จำนวนเงิน:</strong> ฿{float(payment['amount']):,.2f}</p>
                </div>
                <p>{next_step}</p>
                <a href="https://ekgshops.com" style="display: inline-block; background: #10b981; color: white; padding: 12px 30px; border-radius: 5px; text-decoration: none; margin-top: 10px;">ติดตามสถานะ</a>
            </div>
        </div>
        """
        
        send_email(reseller['email'], f"[EKG Shops] ยืนยันการชำระ{payment_type_text} {order['order_number']}", html)
    except Exception as e:
        print(f"Error sending payment confirmed email: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/admin/mto/orders/<int:order_id>/update-status', methods=['POST'])
@admin_required
@csrf_protect
def admin_update_mto_order_status(order_id):
    """Update MTO order status"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        new_status = data.get('status')
        
        valid_statuses = ['awaiting_deposit', 'deposit_paid', 'production', 
                          'balance_requested', 'balance_paid', 'ready_to_ship', 'shipped', 'fulfilled']
        
        if new_status not in valid_statuses:
            return jsonify({'error': 'สถานะไม่ถูกต้อง'}), 400
        
        # Get order
        cursor.execute('SELECT * FROM mto_orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        update_fields = ['status = %s', 'updated_at = NOW()']
        params = [new_status]
        
        # Set timestamps based on status
        if new_status == 'production' and not order['production_started_at']:
            update_fields.append('production_started_at = NOW()')
        elif new_status == 'balance_requested':
            update_fields.append('production_completed_at = NOW()')
            update_fields.append('balance_requested_at = NOW()')
        elif new_status == 'shipped':
            tracking = data.get('tracking_number')
            provider = data.get('shipping_provider')
            update_fields.append('shipped_at = NOW()')
            if tracking:
                update_fields.append('tracking_number = %s')
                params.append(tracking)
            if provider:
                update_fields.append('shipping_provider = %s')
                params.append(provider)
        
        params.append(order_id)
        
        cursor.execute(f'''
            UPDATE mto_orders SET {', '.join(update_fields)} WHERE id = %s
        ''', params)
        
        # Update total_purchases when order transitions to fulfilled (first time only)
        if new_status == 'fulfilled' and order['status'] != 'fulfilled':
            reseller_id = order['reseller_id']
            order_total = float(order['total_amount'] or 0)
            
            # Add MTO order total to reseller's total_purchases
            cursor.execute('''
                UPDATE users SET total_purchases = COALESCE(total_purchases, 0) + %s
                WHERE id = %s
            ''', (order_total, reseller_id))
            
            # Check for tier upgrade using updated total (no double-count)
            cursor.execute('''
                SELECT u.id, u.reseller_tier_id, u.total_purchases, u.tier_manual_override,
                       (SELECT id FROM reseller_tiers 
                        WHERE upgrade_threshold <= u.total_purchases
                        AND is_manual_only = FALSE
                        ORDER BY level_rank DESC LIMIT 1) as eligible_tier_id
                FROM users u WHERE u.id = %s
            ''', (reseller_id,))
            user = cursor.fetchone()
            
            if user and not user['tier_manual_override']:
                eligible_tier = user['eligible_tier_id']
                if eligible_tier and eligible_tier != user['reseller_tier_id']:
                    cursor.execute('UPDATE users SET reseller_tier_id = %s WHERE id = %s',
                                   (eligible_tier, reseller_id))
        
        conn.commit()
        
        # Send email notifications based on status
        if new_status == 'balance_requested':
            try:
                send_balance_request_email(order)
            except:
                pass
        elif new_status == 'shipped':
            try:
                tracking = data.get('tracking_number', '')
                provider = data.get('shipping_provider', '')
                send_mto_shipped_email(order, tracking, provider)
            except:
                pass
        
        return jsonify({
            'success': True,
            'message': 'อัปเดตสถานะสำเร็จ'
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_mto_shipped_email(order, tracking_number, shipping_provider):
    """Send shipment notification email with tracking info"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT email, full_name FROM users WHERE id = %s', (order['reseller_id'],))
        reseller = cursor.fetchone()
        
        # Get tracking URL from shipping provider
        tracking_url = ''
        if shipping_provider and tracking_number:
            cursor.execute('SELECT tracking_url FROM shipping_providers WHERE name = %s', (shipping_provider,))
            provider = cursor.fetchone()
            if provider and provider.get('tracking_url'):
                # Handle both {tracking} placeholder and base URL formats
                base_url = provider['tracking_url']
                if '{tracking}' in base_url:
                    tracking_url = base_url.replace('{tracking}', tracking_number)
                elif base_url:
                    # Append tracking number if no placeholder
                    tracking_url = base_url + tracking_number if not base_url.endswith('/') else base_url + tracking_number
        
        if not reseller or not reseller.get('email'):
            return
        
        tracking_link_html = ''
        if tracking_url:
            tracking_link_html = f'<a href="{tracking_url}" style="display: inline-block; background: #3b82f6; color: white; padding: 12px 30px; border-radius: 5px; text-decoration: none; margin-top: 10px;">ติดตามพัสดุ</a>'
        
        html = f"""
        <div style="font-family: 'Sarabun', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">EKG Shops</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">จัดส่งสินค้าแล้ว!</p>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <p>สวัสดีคุณ {reseller['full_name']},</p>
                <p>สินค้าสั่งผลิตของคุณได้จัดส่งเรียบร้อยแล้ว</p>
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>เลขที่คำสั่งซื้อ:</strong> {order['order_number']}</p>
                    <p><strong>บริษัทขนส่ง:</strong> {shipping_provider or '-'}</p>
                    <p><strong>เลขพัสดุ:</strong> {tracking_number or '-'}</p>
                </div>
                {tracking_link_html}
            </div>
        </div>
        """
        
        send_email(reseller['email'], f"[EKG Shops] จัดส่งสินค้าแล้ว {order['order_number']}", html)
    except Exception as e:
        print(f"Error sending shipped email: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_balance_request_email(order):
    """Send balance payment request email"""
    try:
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        if not gmail_password:
            return
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT email, full_name FROM users WHERE id = %s', (order['reseller_id'],))
        reseller = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not reseller:
            return
        
        sender_email = "ekgshops@gmail.com"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[EKG Shops] เรียกเก็บยอดคงเหลือ {order['order_number']}"
        msg['From'] = sender_email
        msg['To'] = reseller['email']
        
        html = f"""
        <html>
        <body style="font-family: 'Sarabun', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">EKG Shops</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">สินค้าผลิตเสร็จแล้ว!</p>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <p>สวัสดีคุณ {reseller['full_name']},</p>
                <p>สินค้าสั่งผลิตของคุณผลิตเสร็จเรียบร้อยแล้ว กรุณาชำระยอดคงเหลือเพื่อจัดส่ง</p>
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>เลขที่:</strong> {order['order_number']}</p>
                    <p><strong>ยอดคงเหลือ:</strong> ฿{float(order['balance_amount']):,.2f}</p>
                </div>
                <a href="https://ekgshops.com" style="display: inline-block; background: #667eea; color: white; padding: 12px 30px; border-radius: 5px; text-decoration: none; margin-top: 10px;">ชำระเงิน</a>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, gmail_password)
            server.send_message(msg)
            
    except Exception as e:
        print(f"Email error: {e}")

@app.route('/api/admin/mto/stats', methods=['GET'])
@admin_required
def admin_get_mto_stats():
    """Get MTO dashboard statistics"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Count by status
        cursor.execute('''
            SELECT 
                COUNT(*) FILTER (WHERE status = 'pending') as pending_requests,
                COUNT(*) FILTER (WHERE status = 'quoted') as quoted_requests
            FROM quotation_requests
        ''')
        request_stats = cursor.fetchone()
        
        cursor.execute('''
            SELECT 
                COUNT(*) FILTER (WHERE status = 'draft') as draft_quotes,
                COUNT(*) FILTER (WHERE status = 'sent') as sent_quotes
            FROM quotations
        ''')
        quote_stats = cursor.fetchone()
        
        cursor.execute('''
            SELECT 
                COUNT(*) FILTER (WHERE status = 'awaiting_deposit') as awaiting_deposit,
                COUNT(*) FILTER (WHERE status = 'deposit_paid') as deposit_paid,
                COUNT(*) FILTER (WHERE status = 'production') as in_production,
                COUNT(*) FILTER (WHERE status = 'balance_requested') as balance_requested,
                COUNT(*) FILTER (WHERE status = 'balance_paid') as balance_paid,
                COUNT(*) FILTER (WHERE status = 'ready_to_ship') as ready_to_ship,
                COUNT(*) FILTER (WHERE status = 'shipped') as shipped
            FROM mto_orders
        ''')
        order_stats = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) as count FROM mto_payments WHERE status = %s', ('pending',))
        pending_payments = cursor.fetchone()['count']
        
        return jsonify({
            'requests': dict(request_stats) if request_stats else {},
            'quotations': dict(quote_stats) if quote_stats else {},
            'orders': dict(order_stats) if order_stats else {},
            'pending_payments': pending_payments
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== IN-APP CHAT SYSTEM ====================

@app.route('/api/chat/threads', methods=['GET'])
@login_required
def get_chat_threads():
    """Get chat threads for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        if role_name == 'Reseller':
            # Reseller sees only their own thread
            cursor.execute('''
                SELECT ct.id, ct.reseller_id, ct.last_message_at, ct.last_message_preview,
                       u.full_name as reseller_name,
                       (SELECT COUNT(*) FROM chat_messages cm 
                        WHERE cm.thread_id = ct.id 
                        AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                              WHERE thread_id = ct.id AND user_id = %s), 0)) as unread_count
                FROM chat_threads ct
                JOIN users u ON u.id = ct.reseller_id
                WHERE ct.reseller_id = %s AND ct.is_archived = FALSE
                ORDER BY ct.last_message_at DESC NULLS LAST
            ''', (user_id, user_id))
        else:
            # Admin sees all threads
            show_archived = request.args.get('archived', 'false') == 'true'
            cursor.execute('''
                SELECT ct.id, ct.reseller_id, ct.last_message_at, ct.last_message_preview,
                       u.full_name as reseller_name, u.username,
                       rt.name as tier_name, u.reseller_tier_id,
                       (SELECT COUNT(*) FROM chat_messages cm 
                        WHERE cm.thread_id = ct.id 
                        AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                              WHERE thread_id = ct.id AND user_id = %s), 0)) as unread_count
                FROM chat_threads ct
                JOIN users u ON u.id = ct.reseller_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                WHERE ct.is_archived = %s
                ORDER BY ct.last_message_at DESC NULLS LAST
            ''', (user_id, show_archived))
        
        threads = [dict(row) for row in cursor.fetchall()]
        return jsonify(threads), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/threads/<int:thread_id>/archive', methods=['POST'])
@login_required
def archive_chat_thread(thread_id):
    """Archive a chat thread (admin only)"""
    conn = None
    cursor = None
    try:
        if session.get('role') == 'Reseller':
            return jsonify({'error': 'Only admin can archive threads'}), 403
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_threads SET is_archived = TRUE WHERE id = %s', (thread_id,))
        conn.commit()
        return jsonify({'message': 'Thread archived'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/chat/threads/<int:thread_id>/unarchive', methods=['POST'])
@login_required  
def unarchive_chat_thread(thread_id):
    """Unarchive a chat thread"""
    conn = None
    cursor = None
    try:
        if session.get('role') == 'Reseller':
            return jsonify({'error': 'Only admin can unarchive threads'}), 403
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_threads SET is_archived = FALSE WHERE id = %s', (thread_id,))
        conn.commit()
        return jsonify({'message': 'Thread unarchived'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/chat/products/search', methods=['GET'])
@login_required
def search_chat_products():
    """Search products for attaching to chat messages"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        q = request.args.get('q', '').strip()
        reseller_tier_id = request.args.get('tier_id', None, type=int)
        
        # Auto-detect tier for resellers
        if not reseller_tier_id and session.get('role') == 'Reseller':
            cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (session['user_id'],))
            user_row = cursor.fetchone()
            if user_row:
                reseller_tier_id = user_row['reseller_tier_id']
        
        cursor.execute('''
            SELECT p.id, p.name, p.status,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url,
                   MIN(s.price) as min_price, MAX(s.price) as max_price,
                   b.name as brand_name,
                   COUNT(DISTINCT s.id) as sku_count,
                   COALESCE((SELECT SUM(sws.stock) FROM sku_warehouse_stock sws 
                             JOIN skus sk2 ON sk2.id = sws.sku_id 
                             WHERE sk2.product_id = p.id), 0) as total_stock
            FROM products p
            LEFT JOIN skus s ON s.product_id = p.id
            LEFT JOIN brands b ON b.id = p.brand_id
            WHERE p.status = 'active'
            AND (p.name ILIKE %s OR EXISTS (SELECT 1 FROM skus sk WHERE sk.product_id = p.id AND sk.sku_code ILIKE %s))
            GROUP BY p.id, p.name, p.status, b.name
            ORDER BY p.name
            LIMIT 20
        ''', (f'%{q}%', f'%{q}%'))
        
        products = [dict(row) for row in cursor.fetchall()]
        
        if reseller_tier_id:
            for product in products:
                cursor.execute('''
                    SELECT discount_percent FROM product_tier_pricing 
                    WHERE product_id = %s AND tier_id = %s
                ''', (product['id'], reseller_tier_id))
                tier_price = cursor.fetchone()
                if tier_price and tier_price['discount_percent']:
                    discount = float(tier_price['discount_percent'])
                    product['discount_percent'] = discount
                    if product['min_price']:
                        product['tier_min_price'] = round(float(product['min_price']) * (1 - discount/100), 2)
                    if product['max_price']:
                        product['tier_max_price'] = round(float(product['max_price']) * (1 - discount/100), 2)
                else:
                    product['discount_percent'] = 0
                    product['tier_min_price'] = float(product['min_price']) if product['min_price'] else 0
                    product['tier_max_price'] = float(product['max_price']) if product['max_price'] else 0
                
                if product['min_price']:
                    product['min_price'] = float(product['min_price'])
                if product['max_price']:
                    product['max_price'] = float(product['max_price'])
        else:
            for product in products:
                if product['min_price']:
                    product['min_price'] = float(product['min_price'])
                if product['max_price']:
                    product['max_price'] = float(product['max_price'])
        
        return jsonify(products), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/threads/<int:thread_id>/messages', methods=['GET'])
@login_required
def get_chat_messages(thread_id):
    """Get messages for a thread"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Verify access
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        since_id = request.args.get('since_id', 0, type=int)
        before_id = request.args.get('before_id', 0, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        if since_id > 0:
            cursor.execute('''
                SELECT cm.id, cm.sender_id, cm.sender_type, cm.content, cm.is_broadcast, cm.created_at, cm.product_id,
                       u.full_name as sender_name,
                       r.name as sender_role,
                       (SELECT json_agg(json_build_object('id', ca.id, 'file_url', ca.file_url, 
                        'file_name', ca.file_name, 'file_type', ca.file_type))
                        FROM chat_attachments ca WHERE ca.message_id = cm.id) as attachments
                FROM chat_messages cm
                JOIN users u ON u.id = cm.sender_id
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE cm.thread_id = %s AND cm.id > %s
                ORDER BY cm.id ASC
                LIMIT %s
            ''', (thread_id, since_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
        elif before_id > 0:
            cursor.execute('''
                SELECT cm.id, cm.sender_id, cm.sender_type, cm.content, cm.is_broadcast, cm.created_at, cm.product_id,
                       u.full_name as sender_name,
                       r.name as sender_role,
                       (SELECT json_agg(json_build_object('id', ca.id, 'file_url', ca.file_url, 
                        'file_name', ca.file_name, 'file_type', ca.file_type))
                        FROM chat_attachments ca WHERE ca.message_id = cm.id) as attachments
                FROM chat_messages cm
                JOIN users u ON u.id = cm.sender_id
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE cm.thread_id = %s AND cm.id < %s
                ORDER BY cm.id DESC
                LIMIT %s
            ''', (thread_id, before_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()
        else:
            cursor.execute('''
                SELECT cm.id, cm.sender_id, cm.sender_type, cm.content, cm.is_broadcast, cm.created_at, cm.product_id,
                       u.full_name as sender_name,
                       r.name as sender_role,
                       (SELECT json_agg(json_build_object('id', ca.id, 'file_url', ca.file_url, 
                        'file_name', ca.file_name, 'file_type', ca.file_type))
                        FROM chat_attachments ca WHERE ca.message_id = cm.id) as attachments
                FROM chat_messages cm
                JOIN users u ON u.id = cm.sender_id
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE cm.thread_id = %s
                ORDER BY cm.id DESC
                LIMIT %s
            ''', (thread_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()
        
        has_more = len(messages) == limit
        
        thread_reseller_id = thread['reseller_id']
        cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (thread_reseller_id,))
        reseller_user = cursor.fetchone()
        reseller_tier_id = reseller_user['reseller_tier_id'] if reseller_user else None
        
        for msg in messages:
            if msg.get('product_id'):
                cursor.execute('''
                    SELECT p.id, p.name,
                           (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url,
                           MIN(s.price) as min_price, MAX(s.price) as max_price
                    FROM products p
                    LEFT JOIN skus s ON s.product_id = p.id
                    WHERE p.id = %s
                    GROUP BY p.id, p.name
                ''', (msg['product_id'],))
                product = cursor.fetchone()
                if product:
                    product_data = dict(product)
                    if product_data['min_price']:
                        product_data['min_price'] = float(product_data['min_price'])
                    if product_data['max_price']:
                        product_data['max_price'] = float(product_data['max_price'])
                    
                    product_data['discount_percent'] = 0
                    product_data['tier_min_price'] = product_data.get('min_price') or 0
                    product_data['tier_max_price'] = product_data.get('max_price') or 0
                    
                    if reseller_tier_id:
                        cursor.execute('''
                            SELECT discount_percent FROM product_tier_pricing
                            WHERE product_id = %s AND tier_id = %s
                        ''', (msg['product_id'], reseller_tier_id))
                        tier_info = cursor.fetchone()
                        if tier_info and tier_info['discount_percent'] and float(tier_info['discount_percent']) > 0:
                            discount = float(tier_info['discount_percent'])
                            product_data['discount_percent'] = discount
                            if product_data['min_price']:
                                product_data['tier_min_price'] = round(product_data['min_price'] * (1 - discount/100), 2)
                            if product_data['max_price']:
                                product_data['tier_max_price'] = round(product_data['max_price'] * (1 - discount/100), 2)
                    
                    msg['product'] = product_data
        
        # Mark as read
        if messages:
            last_message_id = messages[-1]['id']
            cursor.execute('''
                INSERT INTO chat_read_status (thread_id, user_id, last_read_message_id, last_read_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (thread_id, user_id) 
                DO UPDATE SET last_read_message_id = GREATEST(chat_read_status.last_read_message_id, %s),
                              last_read_at = CURRENT_TIMESTAMP
            ''', (thread_id, user_id, last_message_id, last_message_id))
            conn.commit()
        
        other_last_read = 0
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT COALESCE(MAX(last_read_message_id), 0) as last_read
                FROM chat_read_status 
                WHERE thread_id = %s AND user_id != %s
            ''', (thread_id, user_id))
        else:
            cursor.execute('''
                SELECT COALESCE(last_read_message_id, 0) as last_read
                FROM chat_read_status 
                WHERE thread_id = %s AND user_id = %s
            ''', (thread_id, thread_reseller_id))
        read_row = cursor.fetchone()
        if read_row:
            other_last_read = read_row['last_read']
        
        return jsonify({'messages': messages, 'other_last_read': other_last_read, 'has_more': has_more}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/threads/<int:thread_id>/messages', methods=['POST'])
@login_required
def send_chat_message(thread_id):
    """Send a message to a thread"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Verify access
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        data = request.get_json()
        content = data.get('content', '').strip()
        attachments = data.get('attachments', [])
        product_id = data.get('product_id', None)
        
        if not content and not attachments and not product_id:
            return jsonify({'error': 'Message content, attachments or product required'}), 400
        
        sender_type = 'reseller' if role_name == 'Reseller' else 'admin'
        
        # Insert message
        cursor.execute('''
            INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, product_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at
        ''', (thread_id, user_id, sender_type, content, product_id))
        result = cursor.fetchone()
        message_id = result['id']
        
        # Insert attachments
        for attachment in attachments:
            cursor.execute('''
                INSERT INTO chat_attachments (message_id, file_url, file_name, file_type, file_size)
                VALUES (%s, %s, %s, %s, %s)
            ''', (message_id, attachment.get('file_url'), attachment.get('file_name'),
                  attachment.get('file_type'), attachment.get('file_size')))
        
        # Update thread last message
        preview = content[:100] if content else ('[📦 สินค้า]' if product_id else '[รูปภาพ]')
        cursor.execute('''
            UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s
            WHERE id = %s
        ''', (preview, thread_id))
        
        cursor.execute('UPDATE chat_threads SET is_archived = FALSE WHERE id = %s AND is_archived = TRUE', (thread_id,))
        
        # Schedule email notification for recipient
        recipient_id = thread['reseller_id'] if sender_type == 'admin' else None
        if recipient_id is None and sender_type == 'reseller':
            # Get any admin to notify (in real system, notify all admins or assigned admin)
            cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin') LIMIT 1")
            admin = cursor.fetchone()
            if admin:
                recipient_id = admin['id']
        
        if recipient_id:
            # Check user notification settings
            cursor.execute('''
                SELECT email_enabled, email_delay_minutes 
                FROM chat_notification_settings WHERE user_id = %s
            ''', (recipient_id,))
            settings = cursor.fetchone()
            
            if settings is None or settings['email_enabled']:
                delay_minutes = settings['email_delay_minutes'] if settings else 10
                cursor.execute('''
                    INSERT INTO chat_pending_emails (user_id, thread_id, message_id, scheduled_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '%s minutes')
                ''', (recipient_id, thread_id, message_id, delay_minutes))
        
        conn.commit()
        
        # Send push notification to recipient
        print(f"[CHAT-PUSH] sender={user_id} ({sender_type}), recipient={recipient_id}, thread={thread_id}")
        if recipient_id:
            cursor.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
            sender_info = cursor.fetchone()
            sender_name = sender_info['full_name'] if sender_info else 'ผู้ใช้'
            push_body = content[:100] if content else ('ส่งสินค้ามาให้ดู' if product_id else 'ส่งไฟล์แนบ')
            push_url = '/admin#chat' if sender_type == 'reseller' else '/reseller#chat'
            try:
                print(f"[CHAT-PUSH] Sending push to recipient {recipient_id}: {sender_name} -> {push_body[:30]}")
                import time as _t
                send_push_notification(
                    recipient_id,
                    f'💬 {sender_name}',
                    push_body,
                    url=push_url,
                    tag=f'chat-{thread_id}-{int(_t.time()*1000)}',
                    notification_type='chat'
                )
            except Exception as e:
                print(f"[CHAT-PUSH] Error sending to recipient: {str(e)[:200]}")
        else:
            print(f"[CHAT-PUSH] No recipient_id found, skipping push")
        
        if sender_type == 'reseller':
            try:
                cursor2 = conn.cursor()
                cursor2.execute('''
                    SELECT DISTINCT ps.user_id FROM push_subscriptions ps
                    JOIN users u ON u.id = ps.user_id
                    JOIN roles r ON r.id = u.role_id
                    WHERE r.name IN ('Super Admin', 'Assistant Admin') AND ps.user_id != %s
                ''', (recipient_id if recipient_id else 0,))
                other_admins = [row[0] for row in cursor2.fetchall()]
                cursor2.close()
                print(f"[CHAT-PUSH] Also notifying other admins: {other_admins}")
                
                cursor3 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor3.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
                rinfo = cursor3.fetchone()
                cursor3.close()
                rname = rinfo['full_name'] if rinfo else 'รีเซลเลอร์'
                
                for admin_id in other_admins:
                    try:
                        send_push_notification(admin_id, f'💬 {rname}', content[:100] if content else 'ส่งข้อความใหม่', url='/admin#chat', tag=f'chat-{thread_id}-{int(_t.time()*1000)}')
                    except Exception as e:
                        print(f"[CHAT-PUSH] Error notifying admin {admin_id}: {str(e)[:100]}")
            except Exception as e:
                print(f"[CHAT-PUSH] Error in admin broadcast: {str(e)[:200]}")
        
        return jsonify({
            'id': message_id,
            'created_at': result['created_at'].isoformat()
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/unread-count', methods=['GET'])
@login_required
def get_chat_unread_count():
    """Get total unread message count for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT COALESCE(SUM(
                    (SELECT COUNT(*) FROM chat_messages cm 
                     WHERE cm.thread_id = ct.id 
                     AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                           WHERE thread_id = ct.id AND user_id = %s), 0))
                ), 0) as total_unread
                FROM chat_threads ct
                WHERE ct.reseller_id = %s AND ct.is_archived = FALSE
            ''', (user_id, user_id))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(
                    (SELECT COUNT(*) FROM chat_messages cm 
                     WHERE cm.thread_id = ct.id 
                     AND cm.sender_type = 'reseller'
                     AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                           WHERE thread_id = ct.id AND user_id = %s), 0))
                ), 0) as total_unread
                FROM chat_threads ct
                WHERE ct.is_archived = FALSE
            ''', (user_id,))
        
        result = cursor.fetchone()
        return jsonify({'unread_count': result['total_unread']}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/new-messages', methods=['GET'])
@login_required
def get_chat_new_messages():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        since_id = request.args.get('since_id', 0, type=int)
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, cm.thread_id,
                       u.full_name as sender_name, cm.sender_type, cm.product_id
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE ct.reseller_id = %s 
                  AND cm.sender_type = 'admin'
                  AND cm.id > %s
                  AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                        WHERE thread_id = cm.thread_id AND user_id = %s), 0)
                ORDER BY cm.id ASC
                LIMIT 20
            ''', (user_id, since_id, user_id))
        else:
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, cm.thread_id,
                       u.full_name as sender_name, cm.sender_type, cm.product_id
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE cm.sender_type = 'reseller'
                  AND cm.id > %s
                  AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                        WHERE thread_id = cm.thread_id AND user_id = %s), 0)
                ORDER BY cm.id ASC
                LIMIT 20
            ''', (since_id, user_id))
        
        messages = cursor.fetchall()
        result = []
        for msg in messages:
            preview = msg['content'][:80] if msg['content'] else ('📦 ส่งสินค้ามาให้ดู' if msg['product_id'] else '📎 ส่งไฟล์แนบ')
            result.append({
                'id': msg['id'],
                'thread_id': msg['thread_id'],
                'sender_name': msg['sender_name'],
                'preview': preview,
                'created_at': msg['created_at'].isoformat()
            })
        
        chat_url = '/reseller#chat' if role_name == 'Reseller' else '/admin#chat'
        return jsonify({'messages': result, 'chat_url': chat_url}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/start/<int:reseller_id>', methods=['POST'])
@login_required
def start_chat_thread(reseller_id):
    """Start or get existing chat thread with a reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Reseller can only start chat for themselves
        if role_name == 'Reseller' and reseller_id != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if thread exists
        cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
        thread = cursor.fetchone()
        
        if thread:
            return jsonify({'thread_id': thread['id'], 'is_new': False}), 200
        
        # Create new thread
        cursor.execute('''
            INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id
        ''', (reseller_id,))
        new_thread = cursor.fetchone()
        conn.commit()
        
        return jsonify({'thread_id': new_thread['id'], 'is_new': True}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Quick Replies Management
@app.route('/api/chat/quick-replies', methods=['GET'])
@login_required
def get_quick_replies():
    """Get all quick reply templates"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, title, content, shortcut, sort_order
            FROM chat_quick_replies
            WHERE is_active = TRUE
            ORDER BY sort_order, title
        ''')
        
        replies = [dict(row) for row in cursor.fetchall()]
        return jsonify(replies), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/quick-replies', methods=['POST'])
@admin_required
def create_quick_reply():
    """Create a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        shortcut = data.get('shortcut', '').strip()
        
        if not title or not content:
            return jsonify({'error': 'Title and content required'}), 400
        
        cursor.execute('''
            INSERT INTO chat_quick_replies (title, content, shortcut, created_by)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (title, content, shortcut, session['user_id']))
        
        result = cursor.fetchone()
        conn.commit()
        
        return jsonify({'id': result['id'], 'message': 'Quick reply created'}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/quick-replies/<int:reply_id>', methods=['PUT'])
@admin_required
def update_quick_reply(reply_id):
    """Update a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        data = request.get_json()
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        shortcut = data.get('shortcut', '').strip()
        
        cursor.execute('''
            UPDATE chat_quick_replies 
            SET title = %s, content = %s, shortcut = %s
            WHERE id = %s
        ''', (title, content, shortcut, reply_id))
        
        conn.commit()
        return jsonify({'message': 'Quick reply updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/quick-replies/<int:reply_id>', methods=['DELETE'])
@admin_required
def delete_quick_reply(reply_id):
    """Delete a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE chat_quick_replies SET is_active = FALSE WHERE id = %s', (reply_id,))
        conn.commit()
        
        return jsonify({'message': 'Quick reply deleted'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Broadcast Messages
@app.route('/api/chat/broadcast', methods=['POST'])
@admin_required
def send_broadcast_message():
    """Send broadcast message to all or selected resellers"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        content = data.get('content', '').strip()
        title = data.get('title', '').strip()
        target_type = data.get('target_type', 'all')  # all, tier
        target_tier_id = data.get('target_tier_id')
        
        if not content:
            return jsonify({'error': 'Content required'}), 400
        
        user_id = session['user_id']
        
        # Create broadcast record
        cursor.execute('''
            INSERT INTO chat_broadcasts (sender_id, title, content, target_type, target_tier_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (user_id, title, content, target_type, target_tier_id))
        broadcast = cursor.fetchone()
        broadcast_id = broadcast['id']
        
        # Get target resellers
        if target_type == 'tier' and target_tier_id:
            cursor.execute('''
                SELECT id FROM users 
                WHERE role_id = (SELECT id FROM roles WHERE name = 'Reseller')
                AND tier_id = %s
            ''', (target_tier_id,))
        else:
            cursor.execute('''
                SELECT id FROM users 
                WHERE role_id = (SELECT id FROM roles WHERE name = 'Reseller')
            ''')
        
        resellers = cursor.fetchall()
        sent_count = 0
        
        for reseller in resellers:
            reseller_id = reseller['id']
            
            # Get or create thread
            cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
            thread = cursor.fetchone()
            
            if not thread:
                cursor.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (reseller_id,))
                thread = cursor.fetchone()
            
            thread_id = thread['id']
            
            # Insert broadcast message
            cursor.execute('''
                INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, is_broadcast, broadcast_id)
                VALUES (%s, %s, 'admin', %s, TRUE, %s)
            ''', (thread_id, user_id, content, broadcast_id))
            
            # Update thread
            preview = content[:100]
            cursor.execute('''
                UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s
                WHERE id = %s
            ''', (preview, thread_id))
            
            sent_count += 1
        
        # Update broadcast sent count
        cursor.execute('UPDATE chat_broadcasts SET sent_count = %s WHERE id = %s', (sent_count, broadcast_id))
        
        conn.commit()
        
        # Send push notifications to all target resellers
        broadcast_title = title if title else 'ประกาศจากแอดมิน'
        for reseller in resellers:
            try:
                send_push_notification(
                    reseller['id'],
                    f'📢 {broadcast_title}',
                    content[:100],
                    url='/reseller#chat',
                    tag=f'broadcast-{broadcast_id}',
                    notification_type='broadcast'
                )
            except Exception:
                pass
        
        return jsonify({
            'message': f'Broadcast sent to {sent_count} resellers',
            'broadcast_id': broadcast_id,
            'sent_count': sent_count
        }), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/broadcasts', methods=['GET'])
@admin_required
def get_broadcast_history():
    """Get broadcast message history"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT cb.id, cb.title, cb.content, cb.target_type, cb.sent_count, cb.created_at,
                   u.full_name as sender_name,
                   rt.name as target_tier_name
            FROM chat_broadcasts cb
            JOIN users u ON u.id = cb.sender_id
            LEFT JOIN reseller_tiers rt ON rt.id = cb.target_tier_id
            ORDER BY cb.created_at DESC
            LIMIT 50
        ''')
        
        broadcasts = [dict(row) for row in cursor.fetchall()]
        return jsonify(broadcasts), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Notification Settings
@app.route('/api/chat/notification-settings', methods=['GET'])
@login_required
def get_notification_settings():
    """Get notification settings for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        
        cursor.execute('SELECT * FROM chat_notification_settings WHERE user_id = %s', (user_id,))
        settings = cursor.fetchone()
        
        if not settings:
            # Return defaults
            return jsonify({
                'email_enabled': True,
                'email_frequency': 'smart',
                'email_delay_minutes': 10,
                'in_app_enabled': True
            }), 200
        
        return jsonify(dict(settings)), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/chat/notification-settings', methods=['PUT'])
@login_required
def update_notification_settings():
    """Update notification settings for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        user_id = session['user_id']
        data = request.get_json()
        
        email_enabled = data.get('email_enabled', True)
        email_frequency = data.get('email_frequency', 'smart')
        email_delay_minutes = data.get('email_delay_minutes', 10)
        in_app_enabled = data.get('in_app_enabled', True)
        
        cursor.execute('''
            INSERT INTO chat_notification_settings (user_id, email_enabled, email_frequency, email_delay_minutes, in_app_enabled)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET email_enabled = %s, email_frequency = %s, email_delay_minutes = %s, 
                          in_app_enabled = %s, updated_at = CURRENT_TIMESTAMP
        ''', (user_id, email_enabled, email_frequency, email_delay_minutes, in_app_enabled,
              email_enabled, email_frequency, email_delay_minutes, in_app_enabled))
        
        conn.commit()
        return jsonify({'message': 'Settings updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Chat attachment upload
@app.route('/api/chat/upload', methods=['POST'])
@login_required
def upload_chat_attachment():
    """Upload file for chat message"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 
                         'application/pdf', 'application/msword',
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        
        if file.content_type not in allowed_types:
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Generate unique filename
        import uuid
        ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else ''
        unique_filename = f"chat_{uuid.uuid4().hex}.{ext}"
        
        # Save to object storage or static folder
        upload_folder = 'static/uploads/chat'
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        file_url = f'/static/uploads/chat/{unique_filename}'
        
        return jsonify({
            'file_url': file_url,
            'file_name': file.filename,
            'file_type': file.content_type,
            'file_size': os.path.getsize(file_path)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Search messages
@app.route('/api/chat/search', methods=['GET'])
@login_required
def search_chat_messages():
    """Search chat messages"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        query = request.args.get('q', '').strip()
        
        if not query or len(query) < 2:
            return jsonify([]), 200
        
        search_pattern = f'%{query}%'
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, ct.id as thread_id,
                       u.full_name as sender_name
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE ct.reseller_id = %s AND cm.content ILIKE %s
                ORDER BY cm.created_at DESC
                LIMIT 50
            ''', (user_id, search_pattern))
        else:
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, ct.id as thread_id,
                       u.full_name as sender_name,
                       r.full_name as reseller_name
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                JOIN users r ON r.id = ct.reseller_id
                WHERE cm.content ILIKE %s
                ORDER BY cm.created_at DESC
                LIMIT 50
            ''', (search_pattern,))
        
        results = [dict(row) for row in cursor.fetchall()]
        return jsonify(results), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PWA & PUSH NOTIFICATIONS ====================

@app.route('/sw.js')
def service_worker():
    response = send_file('static/sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/manifest.json')
def manifest():
    import json
    with open('static/manifest.json', 'r') as f:
        data = json.load(f)
    
    ref = request.referrer or ''
    role_name = session.get('role', '')
    
    if '/admin' in ref or role_name in ('Super Admin', 'Assistant Admin'):
        data['start_url'] = '/admin'
        data['name'] = 'EKG Shops - Admin'
        data['short_name'] = 'EKG Admin'
    else:
        data['start_url'] = '/reseller'
    
    response = make_response(json.dumps(data, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/manifest-admin.json')
def manifest_admin():
    import json
    with open('static/manifest.json', 'r') as f:
        data = json.load(f)
    
    data['start_url'] = '/admin'
    data['name'] = 'EKG Shops - Admin'
    data['short_name'] = 'EKG Admin'
    data['scope'] = '/admin'
    
    response = make_response(json.dumps(data, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@app.route('/api/push/vapid-public-key', methods=['GET'])
@login_required
def get_vapid_public_key():
    public_key = os.environ.get('VAPID_PUBLIC_KEY', '')
    return jsonify({'publicKey': public_key}), 200

@app.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        subscription = data.get('subscription', {})
        endpoint = subscription.get('endpoint', '')
        keys = subscription.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')
        
        if not endpoint or not p256dh or not auth:
            return jsonify({'error': 'Invalid subscription data'}), 400
        
        user_id = session['user_id']
        user_agent = request.headers.get('User-Agent', '')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id != %s', (endpoint, user_id))
        
        cursor.execute('''
            DELETE FROM push_subscriptions 
            WHERE user_id = %s AND endpoint != %s AND user_agent = %s
        ''', (user_id, endpoint, user_agent))
        
        cursor.execute('''
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, endpoint) DO UPDATE SET
                p256dh = EXCLUDED.p256dh,
                auth = EXCLUDED.auth,
                user_agent = EXCLUDED.user_agent,
                created_at = CURRENT_TIMESTAMP
        ''', (user_id, endpoint, p256dh, auth, user_agent))
        conn.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        endpoint = data.get('endpoint', '')
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s', (user_id, endpoint))
        conn.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/push/status', methods=['GET'])
@login_required
def push_status():
    conn = None
    cursor = None
    try:
        user_id = session['user_id']
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM push_subscriptions WHERE user_id = %s', (user_id,))
        count = cursor.fetchone()[0]
        
        return jsonify({'subscribed': count > 0, 'count': count}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/push/test', methods=['POST'])
@login_required
def push_test():
    conn = None
    cursor = None
    try:
        user_id = session['user_id']
        vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
        vapid_subject = os.environ.get('VAPID_SUBJECT', 'mailto:admin@ekgshops.com')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, endpoint, p256dh, auth, user_agent FROM push_subscriptions WHERE user_id = %s', (user_id,))
        subscriptions = cursor.fetchall()
        
        if not subscriptions:
            return jsonify({'success': False, 'error': 'No subscriptions found', 'user_id': user_id}), 200
        
        import time
        payload = json.dumps({
            'title': '🔔 ทดสอบการแจ้งเตือน',
            'body': 'ถ้าเห็นข้อความนี้ แสดงว่าระบบแจ้งเตือนทำงานปกติ!',
            'icon': '/static/icons/icon-192x192.png',
            'url': '/',
            'tag': f'test-{int(time.time()*1000)}',
            'type': 'test'
        })
        
        results = []
        for sub in subscriptions:
            device = 'Mobile' if 'Mobile' in (sub.get('user_agent') or '') else 'PC'
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub['endpoint'],
                        'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']}
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={'sub': vapid_subject}
                )
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'sent'})
            except WebPushException as e:
                status_code = e.response.status_code if e.response else 'unknown'
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'failed', 'code': status_code, 'error': str(e)[:150]})
                if e.response and e.response.status_code in (404, 410):
                    cursor.execute('DELETE FROM push_subscriptions WHERE id = %s', (sub['id'],))
                    conn.commit()
            except Exception as e:
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'error', 'error': str(e)[:150]})
        
        return jsonify({'success': True, 'user_id': user_id, 'results': results}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def send_push_notification(user_id, title, body, url='/', tag='ekg-notification', notification_type='general'):
    conn = None
    cursor = None
    try:
        vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
        vapid_subject = os.environ.get('VAPID_SUBJECT', 'mailto:admin@ekgshops.com')
        
        if not vapid_private_key:
            print(f"[PUSH] No VAPID_PRIVATE_KEY set, skipping push for user {user_id}")
            return
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, endpoint, p256dh, auth, user_agent FROM push_subscriptions WHERE user_id = %s', (user_id,))
        subscriptions = cursor.fetchall()
        
        if not subscriptions:
            print(f"[PUSH] No subscriptions found for user {user_id}")
            return
        
        payload = json.dumps({
            'title': title,
            'body': body,
            'icon': '/static/icons/icon-192x192.png',
            'url': url,
            'tag': tag,
            'type': notification_type
        })
        
        print(f"[PUSH] Sending to user {user_id}: {title} - {body[:50]} ({len(subscriptions)} subscriptions)")
        
        expired_ids = []
        sent_count = 0
        for sub in subscriptions:
            device = 'Mobile' if 'Mobile' in (sub.get('user_agent') or '') else 'PC'
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub['endpoint'],
                        'keys': {
                            'p256dh': sub['p256dh'],
                            'auth': sub['auth']
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={'sub': vapid_subject}
                )
                sent_count += 1
                print(f"[PUSH] Sent successfully to sub {sub['id']} ({device})")
                try:
                    cursor.execute('''INSERT INTO push_delivery_log (user_id, subscription_id, device_info, status, status_code)
                        VALUES (%s, %s, %s, 'sent', '201')''', (user_id, sub['id'], device))
                    conn.commit()
                except: pass
            except WebPushException as e:
                status_code = str(e.response.status_code) if e.response else 'unknown'
                error_msg = str(e)[:300]
                print(f"[PUSH] WebPushException sub {sub['id']} ({device}): status={status_code}, {error_msg[:200]}")
                try:
                    cursor.execute('''INSERT INTO push_delivery_log (user_id, subscription_id, device_info, status, status_code, error_message)
                        VALUES (%s, %s, %s, 'failed', %s, %s)''', (user_id, sub['id'], device, status_code, error_msg))
                    conn.commit()
                except: pass
                if e.response and e.response.status_code in (404, 410):
                    expired_ids.append(sub['id'])
            except Exception as e:
                print(f"[PUSH] Error for sub {sub['id']} ({device}): {str(e)[:200]}")
                try:
                    cursor.execute('''INSERT INTO push_delivery_log (user_id, subscription_id, device_info, status, status_code, error_message)
                        VALUES (%s, %s, %s, 'error', 'unknown', %s)''', (user_id, sub['id'], device, str(e)[:300]))
                    conn.commit()
                except: pass
        
        print(f"[PUSH] Sent {sent_count}/{len(subscriptions)} to user {user_id}")
        
        if expired_ids:
            cursor.execute('DELETE FROM push_subscriptions WHERE id = ANY(%s)', (expired_ids,))
            conn.commit()
            print(f"[PUSH] Cleaned up {len(expired_ids)} expired subscriptions")
            
    except Exception as e:
        print(f"[PUSH] Fatal error sending to user {user_id}: {str(e)[:300]}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def send_push_to_admins(title, body, url='/', tag='admin-notification'):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT ps.user_id FROM push_subscriptions ps
            JOIN users u ON u.id = ps.user_id
            JOIN roles r ON r.id = u.role_id
            WHERE r.name IN ('Super Admin', 'Assistant Admin')
        ''')
        admin_ids = [row[0] for row in cursor.fetchall()]
        
        for admin_id in admin_ids:
            send_push_notification(admin_id, title, body, url, tag)
            
    except Exception:
        pass
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== END PWA & PUSH NOTIFICATIONS ====================

# ==================== iSHIP WEBHOOK ====================

@app.route('/api/webhook/iship', methods=['POST'])
def iship_webhook():
    """Receive shipping status updates from iShip logistics aggregator"""
    iship_key = os.environ.get('ISHIP_API_KEY', '')
    if iship_key:
        auth_header = request.headers.get('X-API-Key', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if auth_header != iship_key:
            print(f"[iSHIP] Unauthorized webhook attempt from {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    conn = None
    cursor = None
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No payload"}), 400
        
        print(f"[iSHIP] Received webhook: {payload}")
        
        tracking_no = payload.get('tracking')
        status = payload.get('status')
        status_desc = payload.get('status_desc', '')
        
        if not tracking_no:
            return jsonify({"status": "ignored", "message": "No tracking number"}), 200
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT os.id as shipment_id, os.order_id, os.status as shipment_status,
                   o.order_number, o.user_id, o.status as order_status
            FROM order_shipments os
            JOIN orders o ON o.id = os.order_id
            WHERE os.tracking_number = %s
        ''', (tracking_no,))
        shipment = cursor.fetchone()
        
        if not shipment:
            print(f"[iSHIP] No shipment found for tracking: {tracking_no}")
            return jsonify({"status": "ignored", "message": "Tracking not found"}), 200
        
        reseller_id = shipment['user_id']
        order_number = shipment['order_number'] or f"#{shipment['order_id']}"
        
        if status == 'delivered':
            cursor.execute('''
                UPDATE order_shipments SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status != 'delivered'
            ''', (shipment['shipment_id'],))
            
            cursor.execute('''
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = 'delivered' THEN 1 END) as delivered_count
                FROM order_shipments WHERE order_id = %s
            ''', (shipment['order_id'],))
            counts = cursor.fetchone()
            
            if counts and counts['total'] == counts['delivered_count']:
                cursor.execute('''
                    UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND status != 'delivered'
                ''', (shipment['order_id'],))
            
            conn.commit()
            
            extra = f"({status_desc})" if status_desc else ""
            try:
                send_order_status_chat(reseller_id, order_number, 'delivered', extra)
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
                
        elif status in ['shipped', 'in_transit', 'pickup']:
            cursor.execute('''
                UPDATE order_shipments SET status = 'shipped', shipped_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status NOT IN ('shipped', 'delivered')
            ''', (shipment['shipment_id'],))
            
            if shipment['order_status'] in ('paid', 'processing'):
                cursor.execute('''
                    UPDATE orders SET status = 'shipped', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (shipment['order_id'],))
            
            conn.commit()
            
            extra = f"({status_desc})" if status_desc else ""
            try:
                send_order_status_chat(reseller_id, order_number, 'shipped', extra)
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
        elif status in ['returned', 'exception', 'failed']:
            extra = f"({status_desc})" if status_desc else ""
            conn.commit()
            try:
                send_order_status_chat(reseller_id, order_number, 'shipping_issue', extra)
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
        else:
            print(f"[iSHIP] Unhandled status '{status}' for tracking {tracking_no}")
            conn.commit()
        
        print(f"[iSHIP] Processed: tracking={tracking_no}, status={status}, order={order_number}")
        return jsonify({"status": "success", "message": "Webhook processed"}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[iSHIP] Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== END iSHIP WEBHOOK ====================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
