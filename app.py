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
            
            # Insert SKU with cost_price
            cursor.execute('''
                INSERT INTO skus (product_id, sku_code, price, stock, cost_price)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                product_id,
                sku_data['sku_code'],
                sku_data.get('price', 0),
                sku_data.get('stock', 0),
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
    """Update an existing product with options, values, and SKUs using diff-based approach.
    This preserves sku_id to maintain referential integrity with order_items."""
    data = request.json
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Missing required field: name'}), 400
    
    brand_id = data.get('brand_id')
    if not brand_id:
        return jsonify({'error': 'Missing required field: brand_id'}), 400
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Validate brand exists
        cursor.execute('SELECT id FROM brands WHERE id = %s', (brand_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Brand not found'}), 400
        
        # Validate product exists
        cursor.execute('SELECT id FROM products WHERE id = %s', (product_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Product not found'}), 404
        
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
            new_stock = sku_data.get('stock', 0)
            new_cost_price = sku_data.get('cost_price')
            variant_values = sku_data.get('variant_values', [])
            
            if sku_code in existing_skus:
                # SKU exists - UPDATE price, stock, and cost_price (preserve sku_id)
                sku_id = existing_skus[sku_code]['id']
                cursor.execute('''
                    UPDATE skus SET price = %s, stock = %s, cost_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_price, new_stock, new_cost_price, sku_id))
                
                # Update sku_values_map if variant_values changed
                cursor.execute('DELETE FROM sku_values_map WHERE sku_id = %s', (sku_id,))
                if len(variant_values) == len(options_map):
                    for idx, value_name in enumerate(variant_values):
                        if value_name in options_map[idx]['value_to_id']:
                            value_id = options_map[idx]['value_to_id'][value_name]
                            cursor.execute('INSERT INTO sku_values_map (sku_id, option_value_id) VALUES (%s, %s)',
                                          (sku_id, value_id))
            else:
                # New SKU - INSERT with cost_price
                cursor.execute('''
                    INSERT INTO skus (product_id, sku_code, price, stock, cost_price)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                ''', (product_id, sku_code, new_price, new_stock, new_cost_price))
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
            return jsonify({'error': 'Product not found'}), 404
        
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

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_single_file():
    """Upload a single file to Replit Object Storage"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Allowed extensions
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'File type not allowed'}), 400
        
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
            'message': 'File uploaded successfully',
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
            return jsonify({'error': 'Tier not found'}), 404
        
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
            'message': 'Tier updated successfully',
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
            'message': 'Tiers updated successfully',
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
            return jsonify({'error': 'User not found'}), 404
        
        if user['role_name'] != 'Reseller':
            return jsonify({'error': 'User is not a reseller'}), 400
        
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
            'message': 'Purchase added successfully',
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
            return jsonify({'error': 'Channel not found'}), 404
        
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
            return jsonify({'error': 'Channel not found'}), 404
        
        conn.commit()
        return jsonify({'message': 'Channel deleted successfully'}), 200
        
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
            'message': 'PromptPay settings saved successfully',
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
            'message': 'Order number settings saved successfully',
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
            return jsonify({'error': 'Product not found'}), 404
        
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

# ==================== RESELLER PAGES ====================

@app.route('/reseller/catalog')
@login_required
def reseller_catalog_page():
    """Reseller product catalog page"""
    return render_template('reseller_catalog.html')

@app.route('/reseller/cart')
@login_required
def reseller_cart_page():
    """Reseller cart page"""
    return render_template('reseller_cart.html')

@app.route('/reseller/checkout')
@login_required
def reseller_checkout_page():
    """Reseller checkout page"""
    return render_template('reseller_checkout.html')

@app.route('/reseller/orders')
@login_required
def reseller_orders_page():
    """Reseller orders page"""
    return render_template('reseller_orders.html')

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
    """Create order from cart"""
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
        
        # Validate stock (show available stock, don't deduct yet)
        for item in items:
            if item['stock'] < item['quantity']:
                return jsonify({
                    'error': f'สินค้า {item["product_name"]} ({item["sku_code"]}) สต็อกไม่พอ เหลือ {item["stock"]} ชิ้น'
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
        
        # Create order with new order number format (ORD-YYMM-XXXX)
        order_number = generate_order_number(cursor)
        cursor.execute('''
            INSERT INTO orders (order_number, user_id, sales_channel_id, status, total_amount, discount_amount, final_amount, notes)
            VALUES (%s, %s, %s, 'pending_payment', %s, %s, %s, %s)
            RETURNING id, order_number, status, final_amount, created_at
        ''', (order_number, user_id, channel_id, total_amount, total_discount, final_amount, notes))
        order = dict(cursor.fetchone())
        
        # Create order items
        for item in items:
            unit_price = float(item['unit_price'])
            discount_pct = float(item['tier_discount_percent'] or 0)
            discounted_price = round(unit_price * (1 - discount_pct / 100), 2)
            
            cursor.execute('''
                INSERT INTO order_items (order_id, sku_id, quantity, unit_price, discount_percent, final_price, customization_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (order['id'], item['sku_id'], item['quantity'], unit_price, discount_pct, discounted_price, item['customization_data']))
        
        # Clear cart items
        cursor.execute('DELETE FROM cart_items WHERE cart_id = %s', (cart['cart_id'],))
        
        conn.commit()
        
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
            LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
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
            SELECT o.*, sc.name as channel_name, u.full_name as customer_name
            FROM orders o
            LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
            LEFT JOIN users u ON u.id = o.user_id
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
        
        # Get order items
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
            item_dict['final_price'] = float(item_dict['final_price']) if item_dict['final_price'] else 0
            item_dict['discount_percent'] = float(item_dict['discount_percent']) if item_dict['discount_percent'] else 0
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
        
        return jsonify(order), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/api/orders/<int:order_id>/payment-slip', methods=['POST'])
@login_required
def upload_payment_slip(order_id):
    """Upload payment slip for order"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        slip_image_url = data.get('slip_image_url')
        amount = data.get('amount')
        
        if not slip_image_url:
            return jsonify({'error': 'Slip image URL is required'}), 400
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Verify order belongs to user and is pending payment
        cursor.execute('''
            SELECT id, status, final_amount FROM orders
            WHERE id = %s AND user_id = %s
        ''', (order_id, user_id))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        if order['status'] not in ['pending_payment', 'rejected']:
            return jsonify({'error': 'Cannot upload slip for this order status'}), 400
        
        # Create payment slip
        cursor.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
        ''', (order_id, slip_image_url, amount or order['final_amount']))
        
        # Update order status
        cursor.execute('''
            UPDATE orders SET status = 'under_review', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (order_id,))
        
        conn.commit()
        
        # Notify admins
        cursor.execute("SELECT id FROM users WHERE role_id IN (SELECT id FROM roles WHERE name IN ('Super Admin', 'Assistant Admin'))")
        admins = cursor.fetchall()
        for admin in admins:
            create_notification(
                admin['id'],
                'สลิปการชำระเงินใหม่',
                f'มีสลิปใหม่รอตรวจสอบ คำสั่งซื้อ #{order_id}',
                'payment',
                'order',
                order_id
            )
        
        return jsonify({'message': 'Payment slip uploaded successfully'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
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
                LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
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
                LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
                WHERE DATE(o.created_at) >= %s AND DATE(o.created_at) <= %s
            '''
            params = [start, end]
        
        if channel_id:
            query += ' AND o.sales_channel_id = %s'
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
                       u.full_name as customer_name, u.username,
                       sc.name as channel_name,
                       (SELECT COUNT(*) FROM order_items oi2 
                        JOIN skus s2 ON s2.id = oi2.sku_id 
                        JOIN products p2 ON p2.id = s2.product_id 
                        WHERE oi2.order_id = o.id AND p2.brand_id IN %s) as item_count,
                       (SELECT COUNT(*) FROM payment_slips WHERE order_id = o.id AND status = 'pending') as pending_slips
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
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
                       u.full_name as customer_name, u.username,
                       sc.name as channel_name,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                       (SELECT COUNT(*) FROM payment_slips WHERE order_id = o.id AND status = 'pending') as pending_slips
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN sales_channels sc ON sc.id = o.sales_channel_id
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
        
        # Update order status
        cursor.execute('''
            UPDATE orders SET status = 'paid', updated_at = CURRENT_TIMESTAMP
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

@app.route('/api/admin/orders/<int:order_id>/reject', methods=['POST'])
@admin_required
def reject_order(order_id):
    """Reject order payment"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order
        cursor.execute('SELECT id, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        if order['status'] != 'under_review':
            return jsonify({'error': 'Order is not under review'}), 400
        
        # Update order status
        cursor.execute('''
            UPDATE orders SET status = 'rejected', notes = CONCAT(COALESCE(notes, ''), ' [Rejected: ', %s, ']'), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (reason, order_id))
        
        # Update slip status
        cursor.execute('''
            UPDATE payment_slips SET status = 'rejected', admin_notes = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND status = 'pending'
        ''', (reason, admin_id, order_id))
        
        conn.commit()
        
        # Notify user
        create_notification(
            order['user_id'],
            'สลิปไม่ถูกต้อง',
            f'คำสั่งซื้อ #{order_id} ไม่ผ่านการตรวจสอบ: {reason}',
            'warning',
            'order',
            order_id
        )
        
        return jsonify({'message': 'Order rejected'}), 200
        
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
    """Cancel order"""
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE orders SET status = 'cancelled', notes = CONCAT(COALESCE(notes, ''), ' [Cancelled: ', %s, ']'), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status IN ('pending_payment', 'under_review', 'rejected')
            RETURNING id
        ''', (reason, order_id))
        
        if cursor.fetchone() is None:
            return jsonify({'error': 'Cannot cancel this order'}), 400
        
        conn.commit()
        return jsonify({'message': 'Order cancelled'}), 200
        
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
