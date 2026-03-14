from flask import Blueprint, request, jsonify, session
from database import get_db
from utils import login_required, admin_required, handle_error
import psycopg2.extras
import psycopg2
import json, os, csv, io

warehouse_bp = Blueprint('warehouse', __name__)

# ==================== WAREHOUSE MANAGEMENT ROUTES ====================

@warehouse_bp.route('/api/admin/warehouses', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/warehouses', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/warehouses/<int:warehouse_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/warehouses/<int:warehouse_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/warehouses/<int:warehouse_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/products', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/products/<int:product_id>/warehouse-stock', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/products/<int:product_id>/warehouse-stock', methods=['PUT'])
@admin_required
def update_product_warehouse_stock(product_id):
    """Disabled - Stock updates must go through Stock Adjustment page for audit trail"""
    return jsonify({
        'error': 'การแก้ไขสต็อกโดยตรงถูกปิดใช้งาน กรุณาใช้หน้าปรับสต็อกเพื่อให้มีประวัติการเปลี่ยนแปลง'
    }), 400

@warehouse_bp.route('/api/admin/products/<int:product_id>/skus-with-stock', methods=['GET'])
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
        # ORDER BY size suffix (XS<S<M<L<XL<2XL<3XL) then sku_code for consistent display
        cursor.execute('''
            SELECT s.id, s.sku_code, s.stock as total_stock, s.price,
                   json_agg(DISTINCT jsonb_build_object('option_name', o.name, 'value', ov.value)) as variant_values
            FROM skus s
            LEFT JOIN sku_values_map svm ON s.id = svm.sku_id
            LEFT JOIN option_values ov ON svm.option_value_id = ov.id
            LEFT JOIN options o ON ov.option_id = o.id
            WHERE s.product_id = %s
            GROUP BY s.id, s.sku_code, s.stock, s.price
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK TRANSFER ROUTES ====================

@warehouse_bp.route('/api/admin/stock-transfers', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock-transfers', methods=['POST'])
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
            WHERE sku_id = %s AND warehouse_id = %s AND stock >= %s
        ''', (data['quantity'], data['sku_id'], data['from_warehouse_id'], data['quantity']))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({'error': 'สต็อกไม่เพียงพอ กรุณาตรวจสอบใหม่'}), 400
        
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
        return handle_error(e)
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

@warehouse_bp.route('/api/admin/adjustment-types', methods=['GET'])
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

@warehouse_bp.route('/api/admin/stock-adjustments', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock-adjustments', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock-adjustments/bulk', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK AUDIT LOG ROUTES ====================

@warehouse_bp.route('/api/admin/stock-audit-log', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock-audit-log/summary', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SKU SEARCH FOR STOCK MANAGEMENT ====================

@warehouse_bp.route('/api/admin/skus/search', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/skus/<int:sku_id>/warehouse-stock', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== STOCK ALERTS & SUMMARY ====================

@warehouse_bp.route('/api/admin/stock/low-stock-count', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock/summary', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock/export', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock/import', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@warehouse_bp.route('/api/admin/stock/low-stock-items', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

