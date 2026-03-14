from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from database import get_db
from utils import login_required, admin_required, handle_error
from blueprints.marketing import _calc_best_promotion, _calc_coupon_discount, _enrich_applies_to_names
import psycopg2.extras
import psycopg2
import json, os, io
from datetime import datetime, timedelta

reseller_bp = Blueprint('reseller', __name__)

# ==================== RESELLER DASHBOARD APIs ====================

@reseller_bp.route('/api/reseller/dashboard-stats', methods=['GET'])
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
            WHERE user_id = %s AND paid_at IS NOT NULL
            AND DATE(paid_at) >= %s AND DATE(paid_at) <= %s
        ''', (user_id, first_of_month, today))
        month_stats = cursor.fetchone()
        
        # Get all-time stats
        cursor.execute('''
            SELECT COALESCE(SUM(final_amount), 0) as all_time_total,
                   COUNT(*) as all_time_orders
            FROM orders
            WHERE user_id = %s AND paid_at IS NOT NULL
        ''', (user_id,))
        all_time_stats = cursor.fetchone()
        
        # Get pending orders count (by status)
        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM orders
            WHERE user_id = %s AND status IN ('pending_payment', 'under_review')
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/recent-orders', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/featured-products', methods=['GET'])
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
            LEFT JOIN orders o ON o.id = oi.order_id AND o.paid_at IS NOT NULL
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== THAILAND ADDRESS DATA ====================

@reseller_bp.route('/api/thailand/provinces', methods=['GET'])
def get_thailand_provinces():
    """Get all Thailand provinces"""
    try:
        import json
        with open('static/data/provinces.json', 'r', encoding='utf-8') as f:
            provinces = json.load(f)
        return jsonify(provinces), 200
    except Exception as e:
        return handle_error(e)

@reseller_bp.route('/api/thailand/districts/<int:province_code>', methods=['GET'])
def get_thailand_districts(province_code):
    """Get districts by province code"""
    try:
        import json
        with open('static/data/districts.json', 'r', encoding='utf-8') as f:
            all_districts = json.load(f)
        districts = [d for d in all_districts if d['provinceCode'] == province_code]
        return jsonify(districts), 200
    except Exception as e:
        return handle_error(e)

@reseller_bp.route('/api/thailand/subdistricts/<int:district_code>', methods=['GET'])
def get_thailand_subdistricts(district_code):
    """Get subdistricts by district code"""
    try:
        import json
        with open('static/data/subdistricts.json', 'r', encoding='utf-8') as f:
            all_subdistricts = json.load(f)
        subdistricts = [s for s in all_subdistricts if s['districtCode'] == district_code]
        return jsonify(subdistricts), 200
    except Exception as e:
        return handle_error(e)

# ==================== RESELLER CUSTOMERS ====================

@reseller_bp.route('/api/reseller/customers', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/customers', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/customers/<int:customer_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/customers/<int:customer_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/customers/<int:customer_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/profile', methods=['GET'])
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
                   u.brand_name, u.logo_url, u.line_id,
                   u.bank_name, u.bank_account_number, u.bank_account_name, u.promptpay_number,
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/profile', methods=['PUT'])
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
                brand_name = %s, logo_url = %s,
                bank_name = %s, bank_account_number = %s, bank_account_name = %s, promptpay_number = %s
            WHERE id = %s
            RETURNING id, full_name, phone, email, address, province, district, subdistrict, postal_code,
                      brand_name, logo_url, bank_name, bank_account_number, bank_account_name, promptpay_number
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
            data.get('bank_name'),
            data.get('bank_account_number'),
            data.get('bank_account_name'),
            data.get('promptpay_number'),
            user_id
        ))
        
        profile = cursor.fetchone()
        conn.commit()
        
        return jsonify({'message': 'อัปเดตข้อมูลสำเร็จ', 'profile': dict(profile)}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER PRODUCT CATALOG ====================

@reseller_bp.route('/api/reseller/products', methods=['GET'])
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
        
        # Get active products with tier pricing and category info
        cursor.execute('''
            SELECT p.id, p.name, p.parent_sku, p.description, p.status,
                   b.name as brand_name,
                   (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY sort_order LIMIT 1) as image_url,
                   (SELECT MIN(price) FROM skus WHERE product_id = p.id) as min_price,
                   (SELECT MAX(price) FROM skus WHERE product_id = p.id) as max_price,
                   (SELECT SUM(stock) FROM skus WHERE product_id = p.id) as total_stock,
                   (SELECT COUNT(*) FROM skus WHERE product_id = p.id) as sku_count,
                   ptp.discount_percent,
                   (SELECT STRING_AGG(c.name, '|||' ORDER BY c.name)
                    FROM product_categories pc JOIN categories c ON c.id = pc.category_id
                    WHERE pc.product_id = p.id) as category_names_str,
                   (SELECT STRING_AGG(pc.category_id::text, ',')
                    FROM product_categories pc WHERE pc.product_id = p.id) as category_ids_str
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
            product['category_names'] = product['category_names_str'].split('|||') if product['category_names_str'] else []
            product['category_ids'] = [int(x) for x in product['category_ids_str'].split(',')] if product['category_ids_str'] else []
            del product['category_names_str']
            del product['category_ids_str']
            
            # Calculate discounted prices
            if product['discount_percent'] > 0:
                product['discounted_min_price'] = round(product['min_price'] * (1 - product['discount_percent'] / 100), 2)
                product['discounted_max_price'] = round(product['max_price'] * (1 - product['discount_percent'] / 100), 2)
            else:
                product['discounted_min_price'] = product['min_price']
                product['discounted_max_price'] = product['max_price']
            
            products.append(product)
        
        # Get all active categories that have at least one active product
        cursor.execute('''
            SELECT DISTINCT c.id, c.name
            FROM categories c
            JOIN product_categories pc ON pc.category_id = c.id
            JOIN products p ON p.id = pc.product_id
            WHERE p.status = 'active'
            ORDER BY c.name
        ''')
        categories = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'tier': user,
            'products': products,
            'categories': categories
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/products/<int:product_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER CART API ====================
from blueprints.marketing import _calc_best_promotion, _calc_coupon_discount, _enrich_applies_to_names

@reseller_bp.route('/api/reseller/cart', methods=['GET'])
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
                   p.brand_id, p.weight,
                   (SELECT pc.category_id FROM product_categories pc WHERE pc.product_id = p.id ORDER BY pc.id LIMIT 1) as category_id,
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/cart', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/cart/<int:item_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/cart/<int:item_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/cart/count', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER MTO API ====================

@reseller_bp.route('/api/reseller/mto/products', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/products/<int:product_id>/details', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/products/<int:product_id>/skus', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/quotation-requests', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/quotations', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/quotations/<int:quotation_id>/accept', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/quotations/<int:quotation_id>/reject', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/orders', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/orders/<int:order_id>/qr-code', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@reseller_bp.route('/api/reseller/mto/orders/<int:order_id>/payment', methods=['POST'])
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
        
        import base64
        file_data = slip_file.read()
        max_size = 5 * 1024 * 1024
        if len(file_data) > max_size:
            return jsonify({'error': 'ไฟล์ใหญ่เกิน 5MB'}), 400
        original_ext = slip_file.filename.rsplit('.', 1)[-1].lower() if '.' in slip_file.filename else 'png'
        mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'}
        mime_type = mime_map.get(original_ext, 'image/png')
        b64_data = base64.b64encode(file_data).decode('utf-8')
        slip_url = f'data:{mime_type};base64,{b64_data}'
        
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== RESELLER PAGES ====================

@reseller_bp.route('/reseller')
@login_required
def reseller_spa_root():
    """Reseller SPA root"""
    return render_template('reseller_spa.html')

@reseller_bp.route('/reseller/dashboard')
@login_required
def reseller_dashboard_page():
    """Reseller dashboard SPA"""
    return render_template('reseller_spa.html')

@reseller_bp.route('/reseller/catalog')
@login_required
def reseller_catalog_page():
    """Redirect to SPA with catalog hash"""
    return redirect('/dashboard#catalog')

@reseller_bp.route('/reseller/cart')
@login_required
def reseller_cart_page():
    """Redirect to SPA with cart hash"""
    return redirect('/dashboard#cart')

@reseller_bp.route('/reseller/checkout')
@login_required
def reseller_checkout_page():
    """Reseller checkout page"""
    return render_template('reseller_checkout.html')

@reseller_bp.route('/reseller/orders')
@login_required
def reseller_orders_page():
    """Redirect to SPA with orders hash"""
    return redirect('/dashboard#orders')

@reseller_bp.route('/reseller/customers')
@login_required
def reseller_customers_page():
    """Redirect to SPA with customers hash"""
    return redirect('/dashboard#customers')

@reseller_bp.route('/reseller/profile')
@login_required
def reseller_profile_page():
    """Redirect to SPA with profile hash"""
    return redirect('/dashboard#profile')

