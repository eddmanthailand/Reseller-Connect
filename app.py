from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
import psycopg2.extras
import bcrypt
from functools import wraps
from database import get_db, init_db
import os
from replit.object_storage import Client

app = Flask(__name__)

# SESSION_SECRET is required for production security
session_secret = os.environ.get('SESSION_SECRET')
if not session_secret:
    raise RuntimeError(
        "SESSION_SECRET environment variable is required. "
        "Please configure a strong session secret for security."
    )
app.secret_key = session_secret

CORS(app)

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

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        if session.get('role') not in ['Super Admin', 'Assistant Admin']:
            return jsonify({'error': 'Unauthorized - Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Redirect to dashboard if logged in, otherwise to login page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login')
def login_page():
    """Render login page"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard after login - routes based on role"""
    role = session.get('role')
    
    if role in ['Super Admin', 'Assistant Admin']:
        return redirect(url_for('admin_management'))
    elif role == 'Reseller':
        return render_template('reseller_dashboard.html')
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

@app.route('/api/login', methods=['POST'])
def login():
    """Handle user login"""
    data = request.json
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Missing username or password'}), 400
    
    username = data['username']
    password = data['password']
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user by username
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
            WHERE u.username = %s
        ''', (username,))
        
        user = cursor.fetchone()
        
        # Verify password with bcrypt
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            return jsonify({'error': 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'}), 401
        
        # Set session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role']
        session['reseller_tier'] = user['reseller_tier']
        
        # Determine redirect URL based on role
        if user['role'] in ['Super Admin', 'Assistant Admin']:
            redirect_url = '/admin'
        elif user['role'] == 'Reseller':
            redirect_url = '/dashboard'
        else:
            redirect_url = '/dashboard'
        
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
    session.clear()
    return jsonify({'message': 'ออกจากระบบสำเร็จ'}), 200

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

@app.route('/api/reseller/products', methods=['GET'])
@login_required
def get_reseller_products():
    """Get active products for resellers with basic info and tier pricing"""
    user_role = session.get('role')
    if user_role not in ['Reseller', 'Super Admin', 'Assistant Admin']:
        return jsonify({'error': 'Unauthorized access'}), 403
    
    user_id = session.get('user_id')
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get user's reseller tier
        user_tier_id = None
        discount_percent = 0
        
        cursor.execute('''
            SELECT reseller_tier_id FROM users WHERE id = %s
        ''', (user_id,))
        user_result = cursor.fetchone()
        if user_result and user_result['reseller_tier_id']:
            user_tier_id = user_result['reseller_tier_id']
        
        cursor.execute('''
            SELECT 
                p.id,
                p.name,
                p.parent_sku,
                b.name as brand_name,
                (
                    SELECT pi.image_url 
                    FROM product_images pi 
                    WHERE pi.product_id = p.id 
                    ORDER BY pi.sort_order ASC 
                    LIMIT 1
                ) as image_url,
                COUNT(DISTINCT s.id) as sku_count,
                MIN(s.price) as min_price,
                MAX(s.price) as max_price,
                (
                    SELECT ptp.discount_percent
                    FROM product_tier_pricing ptp
                    WHERE ptp.product_id = p.id AND ptp.tier_id = %s
                ) as discount_percent
            FROM products p
            LEFT JOIN skus s ON p.id = s.product_id
            LEFT JOIN brands b ON p.brand_id = b.id
            WHERE COALESCE(p.status, 'active') = 'active'
            GROUP BY p.id, p.name, p.parent_sku, b.name
            ORDER BY p.name ASC
        ''', (user_tier_id,))
        
        products = []
        for row in cursor.fetchall():
            product = dict(row)
            discount = float(product['discount_percent']) if product['discount_percent'] else 0
            
            # Calculate discounted prices
            if product['min_price']:
                min_price = float(product['min_price'])
                product['min_price_discounted'] = min_price * (1 - discount / 100)
            else:
                product['min_price_discounted'] = None
                
            if product['max_price']:
                max_price = float(product['max_price'])
                product['max_price_discounted'] = max_price * (1 - discount / 100)
            else:
                product['max_price_discounted'] = None
            
            product['discount_percent'] = discount
            products.append(product)
        
        return jsonify(products), 200
        
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
        return jsonify({'error': 'Unauthorized access'}), 403
    
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
    """Get all users with their role information"""
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
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['full_name', 'username', 'password', 'role_id']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
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
            return jsonify({'error': 'Username already exists'}), 400
        
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
            'message': 'User created successfully',
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
                   u.tier_manual_override,
                   r.name as role, rt.name as reseller_tier
            FROM users u
            JOIN roles r ON u.role_id = r.id
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.id = %s
        ''', (user_id,))
        
        user = cursor.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
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
        return jsonify({'error': 'No data provided'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if user exists
        cursor.execute('SELECT id, username FROM users WHERE id = %s', (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if username is being changed and if it's already taken
        if 'username' in data and data['username'] != existing_user['username']:
            cursor.execute('SELECT id FROM users WHERE username = %s AND id != %s', (data['username'], user_id))
            if cursor.fetchone():
                return jsonify({'error': 'Username already exists'}), 400
        
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
        
        if 'password' in data and data['password']:
            password_hash = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            update_fields.append('password = %s')
            update_values.append(password_hash)
        
        if not update_fields:
            return jsonify({'error': 'No fields to update'}), 400
        
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
            'message': 'User updated successfully',
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
            return jsonify({'error': 'User not found'}), 404
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        conn.commit()
        
        return jsonify({'message': 'User deleted successfully'}), 200
        
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
        return jsonify({'error': 'Only Super Admin can create brands'}), 403
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Brand name is required'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand already exists
        cursor.execute('SELECT id FROM brands WHERE name = %s', (data['name'],))
        if cursor.fetchone():
            return jsonify({'error': 'Brand name already exists'}), 400
        
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
        return jsonify({'error': 'Only Super Admin can update brands'}), 403
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Brand name is required'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Brand not found'}), 404
        
        # Check for duplicate name
        cursor.execute('SELECT id FROM brands WHERE name = %s AND id != %s', (data['name'], brand_id))
        if cursor.fetchone():
            return jsonify({'error': 'Brand name already exists'}), 400
        
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
        return jsonify({'error': 'Only Super Admin can delete brands'}), 403
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Brand not found'}), 404
        
        # Check if brand has products
        cursor.execute('SELECT COUNT(*) as count FROM products WHERE brand_id = %s', (brand_id,))
        count = cursor.fetchone()['count']
        if count > 0:
            return jsonify({'error': f'Cannot delete brand with {count} products. Please move or delete products first.'}), 400
        
        # Delete brand
        cursor.execute('DELETE FROM brands WHERE id = %s', (brand_id,))
        conn.commit()
        
        return jsonify({'message': 'Brand deleted successfully'}), 200
        
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
        return jsonify({'error': 'Only Super Admin can assign brands'}), 403
    
    data = request.json
    if not data or 'brand_ids' not in data:
        return jsonify({'error': 'Brand IDs required'}), 400
    
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
            return jsonify({'error': 'User not found'}), 404
        
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
        
        return jsonify({'message': 'Brands assigned successfully'}), 200
        
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
            return jsonify({'error': 'Category name is required'}), 400
        
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
        return jsonify({'error': 'Category with this name already exists'}), 409
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
            return jsonify({'error': 'Category name is required'}), 400
        
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
            return jsonify({'error': 'Category not found'}), 404
        
        conn.commit()
        return jsonify(dict(category)), 200
        
    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({'error': 'Category with this name already exists'}), 409
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
            return jsonify({'error': 'Category not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Category deleted successfully'}), 200
        
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
                COUNT(DISTINCT s.id) as sku_count,
                COALESCE(MIN(s.price), 0) as min_price,
                COALESCE(MAX(s.price), 0) as max_price,
                COALESCE(SUM(s.stock), 0) as total_stock,
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
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at
                ORDER BY p.created_at DESC
            '''
            cursor.execute(base_query, (user_id,))
        else:
            base_query += '''
                GROUP BY p.id, p.name, p.parent_sku, p.description, p.size_chart_image_url, p.brand_id, b.name, p.status, p.created_at
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
            return jsonify({'error': 'Product not found'}), 404
        
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
            GROUP BY s.id, s.sku_code, s.price, s.stock
            ORDER BY s.sku_code
        ''', (product_id,))
        
        skus = [dict(row) for row in cursor.fetchall()]
        product['skus'] = skus
        
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
        return jsonify({'error': 'Missing required fields: name, parent_sku'}), 400
    
    # Validate brand_id is provided
    brand_id = data.get('brand_id')
    if not brand_id:
        return jsonify({'error': 'Missing required field: brand_id'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Brand not found'}), 400
        
        # Check if parent_sku already exists
        cursor.execute('SELECT id FROM products WHERE parent_sku = %s', (data['parent_sku'],))
        if cursor.fetchone():
            return jsonify({'error': 'Parent SKU already exists'}), 400
        
        # Insert product with brand_id and status
        status = data.get('status', 'active')
        cursor.execute('''
            INSERT INTO products (brand_id, name, parent_sku, description, size_chart_image_url, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (brand_id, data['name'], data['parent_sku'], data.get('description', ''), data.get('size_chart_image_url'), status))
        
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
            
            # Insert SKU
            cursor.execute('''
                INSERT INTO skus (product_id, sku_code, price, stock)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (
                product_id,
                sku_data['sku_code'],
                sku_data.get('price', 0),
                sku_data.get('stock', 0)
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
            'message': 'Product created successfully',
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
        return jsonify({'error': 'Missing image_ids array'}), 400
    
    image_ids = data['image_ids']
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
        # Update sort_order for each image
        for idx, image_id in enumerate(image_ids):
            cursor.execute('''
                UPDATE product_images 
                SET sort_order = %s 
                WHERE id = %s AND product_id = %s
            ''', (idx, image_id, product_id))
        
        conn.commit()
        
        return jsonify({'message': 'Images reordered successfully'}), 200
        
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
    """Update an existing product with options, values, and SKUs"""
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400
    
    # Validate brand_id is provided
    brand_id = data.get('brand_id')
    if not brand_id:
        return jsonify({'error': 'Missing required field: brand_id'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Brand not found'}), 400
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
        # Update basic product information including brand_id and status
        status = data.get('status', 'active')
        cursor.execute('''
            UPDATE products 
            SET brand_id = %s, name = %s, description = %s, size_chart_image_url = %s, status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (brand_id, data['name'], data.get('description', ''), data.get('size_chart_image_url'), status, product_id))
        
        # Update product category
        cursor.execute('DELETE FROM product_categories WHERE product_id = %s', (product_id,))
        category_id = data.get('category_id')
        if category_id:
            cursor.execute('SELECT id FROM categories WHERE id = %s', (category_id,))
            if cursor.fetchone():
                cursor.execute('''
                    INSERT INTO product_categories (product_id, category_id)
                    VALUES (%s, %s)
                ''', (product_id, category_id))
        
        # Delete existing SKUs (cascade deletes sku_values_map)
        cursor.execute('DELETE FROM skus WHERE product_id = %s', (product_id,))
        
        # Delete existing options (cascade deletes option_values)
        cursor.execute('DELETE FROM options WHERE product_id = %s', (product_id,))
        
        # Delete existing product images
        cursor.execute('DELETE FROM product_images WHERE product_id = %s', (product_id,))
        
        # Insert new product images
        image_urls = data.get('image_urls', [])
        for idx, image_url in enumerate(image_urls):
            cursor.execute('''
                INSERT INTO product_images (product_id, image_url, sort_order)
                VALUES (%s, %s, %s)
            ''', (product_id, image_url, idx))
        
        # Insert new options and values
        options_data = data.get('options', [])
        options_map = []  # List of {name, value_ids} for ordered lookup
        
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
            option_name = option['name']
            value_to_id = {}  # Map for this option: {value_name: value_id}
            
            # Insert option values with sort_order
            for idx, value_data in enumerate(option['values']):
                value_name = value_data['value']
                cursor.execute('''
                    INSERT INTO option_values (option_id, value, sort_order)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (option_id, value_name, value_data.get('sort_order', idx)))
                
                value_id = cursor.fetchone()['id']
                value_to_id[value_name] = value_id
            
            options_map.append({
                'name': option_name,
                'value_to_id': value_to_id,
                'values_order': [v['value'] for v in option['values']]
            })
        
        # Insert new SKUs
        skus_data = data.get('skus', [])
        for sku_data in skus_data:
            if not sku_data.get('sku_code'):
                continue
            
            # Insert SKU
            cursor.execute('''
                INSERT INTO skus (product_id, sku_code, price, stock)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (
                product_id,
                sku_data['sku_code'],
                sku_data.get('price', 0),
                sku_data.get('stock', 0)
            ))
            
            sku_id = cursor.fetchone()['id']
            
            # Map SKU to option values using variant_values (maintains option context)
            variant_values = sku_data.get('variant_values', [])
            if len(variant_values) == len(options_map):
                for idx, value_name in enumerate(variant_values):
                    option = options_map[idx]
                    if value_name in option['value_to_id']:
                        value_id = option['value_to_id'][value_name]
                        cursor.execute('''
                            INSERT INTO sku_values_map (sku_id, option_value_id)
                            VALUES (%s, %s)
                        ''', (sku_id, value_id))
        
        conn.commit()
        
        return jsonify({
            'message': 'Product updated successfully',
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
            return jsonify({'error': 'Invalid status. Must be active, inactive, or draft'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE products SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        ''', (status, product_id))
        
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Status updated successfully', 'status': status}), 200
        
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
    """Delete a product and all related data (cascade)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
        # Delete product (cascade will handle related data)
        cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
        conn.commit()
        
        return jsonify({'message': 'Product deleted successfully'}), 200
        
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
            return jsonify({'error': 'No data provided'}), 400
        
        updates = []
        params = []
        
        if 'price' in data:
            try:
                price = round(float(data['price']), 2)
                if price < 0:
                    return jsonify({'error': 'Price cannot be negative'}), 400
                updates.append('price = %s')
                params.append(price)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid price value'}), 400
        
        if 'stock' in data:
            try:
                stock = int(data['stock'])
                if stock < 0:
                    return jsonify({'error': 'Stock cannot be negative'}), 400
                updates.append('stock = %s')
                params.append(stock)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid stock value'}), 400
        
        if not updates:
            return jsonify({'error': 'No valid fields to update'}), 400
        
        params.append(sku_id)
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute(f'''
            UPDATE skus SET {', '.join(updates)}
            WHERE id = %s
            RETURNING id
        ''', tuple(params))
        
        if not cursor.fetchone():
            return jsonify({'error': 'SKU not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'SKU updated successfully'}), 200
        
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
            return jsonify({'error': 'Customization name is required'}), 400
        
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
            return jsonify({'error': 'Customization name is required'}), 400
        
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
            return jsonify({'error': 'Customization not found'}), 404
        
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
            return jsonify({'error': 'Customization not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Customization deleted successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/upload-images', methods=['POST'])
@admin_required
def upload_images():
    """Upload multiple product images to Replit Object Storage"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'No image files provided'}), 400
        
        files = request.files.getlist('images')
        
        if not files or len(files) == 0:
            return jsonify({'error': 'No files selected'}), 400
        
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
            return jsonify({'error': 'No valid images uploaded'}), 400
        
        return jsonify({
            'message': f'{len(uploaded_images)} image(s) uploaded successfully',
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
        return jsonify({'error': 'Image not found'}), 404

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
            return jsonify({'error': 'Product not found'}), 404
        
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
            return jsonify({'error': 'Missing pricing data'}), 400
        
        pricing_data = data['pricing']
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Check if product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
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
            'message': 'Tier pricing saved successfully',
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
            return jsonify({'error': 'User not found'}), 404
        
        if user['role_name'] != 'Reseller':
            return jsonify({'error': 'User is not a reseller'}), 400
        
        tier_id = data.get('reseller_tier_id')
        manual_override = data.get('tier_manual_override', False)
        
        if tier_id:
            # Verify tier exists
            cursor.execute('SELECT id FROM reseller_tiers WHERE id = %s', (tier_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Tier not found'}), 404
        
        cursor.execute('''
            UPDATE users 
            SET reseller_tier_id = %s, tier_manual_override = %s
            WHERE id = %s
            RETURNING id, reseller_tier_id, tier_manual_override
        ''', (tier_id, manual_override, user_id))
        
        updated = dict(cursor.fetchone())
        conn.commit()
        
        return jsonify({
            'message': 'User tier updated successfully',
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
