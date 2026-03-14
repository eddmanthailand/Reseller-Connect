from flask import Blueprint, request, jsonify, session, render_template, send_file
from database import get_db
from utils import login_required, admin_required, handle_error
from blueprints.bot_cache import bot_cache_invalidate
from replit.object_storage import Client
import psycopg2.extras
import psycopg2
import json, os, io
from datetime import datetime

products_bp = Blueprint('products', __name__)

# ==================== BRAND MANAGEMENT ROUTES ====================

@products_bp.route('/api/brands', methods=['GET'])
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

@products_bp.route('/api/brands', methods=['POST'])
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

@products_bp.route('/api/brands/<int:brand_id>', methods=['PUT'])
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

@products_bp.route('/api/brands/<int:brand_id>', methods=['DELETE'])
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

@products_bp.route('/api/admin-brand-access/<int:user_id>', methods=['GET'])
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

@products_bp.route('/api/admin-brand-access/<int:user_id>', methods=['PUT'])
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

@products_bp.route('/api/categories', methods=['GET'])
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

@products_bp.route('/api/categories', methods=['POST'])
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

@products_bp.route('/api/categories/<int:category_id>', methods=['PUT'])
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

@products_bp.route('/api/categories/<int:category_id>', methods=['DELETE'])
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

@products_bp.route('/api/products', methods=['GET'])
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

@products_bp.route('/api/products/<int:product_id>', methods=['GET'])
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

@products_bp.route('/api/products', methods=['POST'])
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

@products_bp.route('/api/products/<int:product_id>/images/reorder', methods=['PUT'])
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

@products_bp.route('/api/products/<int:product_id>', methods=['PUT'])
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

@products_bp.route('/api/products/<int:product_id>/status', methods=['PATCH'])
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

@products_bp.route('/api/products/<int:product_id>/featured', methods=['PATCH'])
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

@products_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
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

@products_bp.route('/api/skus/<int:sku_id>', methods=['PATCH'])
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

@products_bp.route('/api/products/<int:product_id>/customizations', methods=['GET'])
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

@products_bp.route('/api/products/<int:product_id>/customizations', methods=['POST'])
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

@products_bp.route('/api/customizations/<int:customization_id>', methods=['PUT'])
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

@products_bp.route('/api/customizations/<int:customization_id>', methods=['DELETE'])
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

@products_bp.route('/api/upload', methods=['POST'])
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

@products_bp.route('/api/upload-images', methods=['POST'])
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

@products_bp.route('/storage/<path:filename>')
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

@products_bp.route('/api/products/<int:product_id>/tier-pricing', methods=['GET'])
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

@products_bp.route('/api/products/<int:product_id>/tier-pricing', methods=['POST', 'PUT'])
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

@products_bp.route('/api/users/<int:user_id>/tier-override', methods=['PATCH'])
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

@products_bp.route('/admin/tier-settings')
@admin_required
def tier_settings_page():
    """Tier settings management page"""
    return render_template('tier_settings.html')

@products_bp.route('/api/reseller-tiers/<int:tier_id>', methods=['PUT'])
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

@products_bp.route('/api/reseller-tiers/bulk', methods=['PUT'])
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

@products_bp.route('/api/users/<int:user_id>/add-purchase', methods=['POST'])
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

@products_bp.route('/api/users/check-tier-upgrades', methods=['POST'])
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

@products_bp.route('/api/resellers', methods=['GET'])
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

