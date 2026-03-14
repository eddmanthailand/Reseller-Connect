from flask import Blueprint, request, jsonify, session, make_response, render_template, redirect, url_for
from database import get_db
from utils import login_required, admin_required, handle_error, csrf_protect
from blueprints.push_utils import send_push_notification, create_notification, send_push_to_admins
from blueprints.mail_utils import (send_email, send_order_status_chat,
    send_order_notification_to_admin, send_order_status_email,
    send_low_stock_alert, log_activity)
from blueprints.marketing import _calc_best_promotion, _calc_coupon_discount
import psycopg2.extras
import psycopg2
import json, os, io, re, csv
from datetime import datetime, timedelta

orders_bp = Blueprint('orders', __name__)

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

@orders_bp.route('/api/orders', methods=['POST'])
@login_required
def create_order():
    """Create order from cart with automatic shipment splitting by warehouse"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        notes = data.get('notes', '')
        payment_method = data.get('payment_method', 'stripe')
        
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
                   s.stock, s.sku_code, p.name as product_name, p.brand_id, p.id as product_id,
                   (SELECT pc.category_id FROM product_categories pc WHERE pc.product_id = p.id ORDER BY pc.id LIMIT 1) as category_id
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
        
        # Get warehouse stock for all SKUs — FOR UPDATE locks rows to prevent race conditions
        cursor.execute('''
            SELECT sws.sku_id, sws.warehouse_id, sws.stock, w.name as warehouse_name, w.is_active
            FROM sku_warehouse_stock sws
            JOIN warehouses w ON w.id = sws.warehouse_id
            WHERE sws.sku_id = ANY(%s) AND sws.stock > 0 AND w.is_active = TRUE
            ORDER BY sws.warehouse_id, sws.sku_id
            FOR UPDATE OF sws
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
        
        item_total = total_amount - total_discount   # tier-discounted total
        shipping_fee = float(data.get('shipping_fee', 0) or 0)

        # Layer 2 & 3: Apply promotion + coupon discounts
        coupon_code = (data.get('coupon_code') or '').strip()
        cart_brand_ids = list({item.get('brand_id') for item in items if item.get('brand_id')})
        cart_category_ids = list({item.get('category_id') for item in items if item.get('category_id')})
        cart_product_ids = list({item.get('product_id') for item in items if item.get('product_id')})
        cart_total_qty = sum(item['quantity'] for item in items)

        cursor.execute('''
            SELECT rt.level_rank FROM users u
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (user_id,))
        tier_row = cursor.fetchone()
        user_tier_rank = int(tier_row['level_rank']) if tier_row and tier_row['level_rank'] else 1

        # "Best discount wins": compare promo on RETAIL price vs tier savings — pick higher, no stacking
        promo_candidate, promo_on_retail = _calc_best_promotion(cursor, total_amount, cart_brand_ids, cart_category_ids, user_tier_rank, cart_total_qty, user_id=user_id)
        use_tier = (total_discount >= promo_on_retail) or (promo_on_retail == 0)
        if use_tier:
            applied_promo = None
            promo_discount = 0
            effective_item_total = item_total        # retail - tier discount
            effective_discount = total_discount      # tier savings go to discount_amount column
        else:
            applied_promo = promo_candidate
            promo_discount = promo_on_retail
            effective_item_total = total_amount - promo_on_retail  # retail - promo
            effective_discount = 0                   # tier waived; promo goes to promotion_discount column

        applied_coupon, coupon_discount, coupon_error = (None, 0, None)
        if coupon_code:
            if applied_promo is None or applied_promo.get('is_stackable'):
                applied_coupon, coupon_discount, coupon_error = _calc_coupon_discount(
                    cursor, coupon_code, effective_item_total, user_id, user_tier_rank,
                    cart_brand_ids=cart_brand_ids, cart_product_ids=cart_product_ids)

        # Check free_shipping coupon
        free_shipping_coupon = applied_coupon and applied_coupon.get('discount_type') == 'free_shipping'
        effective_shipping = 0.0 if free_shipping_coupon else shipping_fee

        final_amount = max(0, effective_item_total - coupon_discount) + effective_shipping

        # Get default online channel
        cursor.execute("SELECT id FROM sales_channels WHERE name = 'ระบบออนไลน์' LIMIT 1")
        channel = cursor.fetchone()
        channel_id = channel['id'] if channel else None
        
        # Get customer_id if provided
        customer_id = data.get('customer_id')
        
        # Create order with new order number format (ORD-YYMM-XXXX)
        order_number = generate_order_number(cursor)
        cursor.execute('''
            INSERT INTO orders (order_number, user_id, channel_id, status, payment_method, total_amount, discount_amount, shipping_fee, final_amount, notes, customer_id,
                                coupon_id, coupon_discount, promotion_id, promotion_discount)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, order_number, status, final_amount, created_at
        ''', (order_number, user_id, channel_id,
              'preparing' if payment_method == 'cod' else 'pending_payment',
              payment_method,
              total_amount, effective_discount, effective_shipping, final_amount, notes, customer_id,
              applied_coupon['id'] if applied_coupon else None, coupon_discount,
              applied_promo['id'] if applied_promo else None, promo_discount))
        order = dict(cursor.fetchone())
        
        # Create order items and track their IDs using cart_item_id as unique key
        order_item_map = {}  # {cart_item_id: order_item_id}
        for item in items:
            unit_price = float(item['unit_price'])
            if use_tier:
                discount_pct = float(item['tier_discount_percent'] or 0)
                discounted_price = round(unit_price * (1 - discount_pct / 100), 2)
                discount_amount = round(unit_price * discount_pct / 100, 2)
            else:
                # Promo wins → bill at retail price, tier waived for this order
                discount_pct = 0
                discounted_price = unit_price
                discount_amount = 0
            subtotal = round(discounted_price * item['quantity'], 2)
            
            # Convert customization_data to JSON string if it's a dict
            cust_data = item['customization_data']
            if isinstance(cust_data, dict):
                cust_data = json.dumps(cust_data)
            
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
        
        # Deduct stock from warehouses (atomic check prevents negative stock)
        for sku_id, wh_id, qty in stock_deductions:
            cursor.execute('''
                UPDATE sku_warehouse_stock
                SET stock = stock - %s
                WHERE sku_id = %s AND warehouse_id = %s AND stock >= %s
            ''', (qty, sku_id, wh_id, qty))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่อีกครั้ง'}), 400
        
        # Also update the main SKU stock in skus table (atomic check)
        for item in items:
            cursor.execute('''
                UPDATE skus SET stock = stock - %s WHERE id = %s AND stock >= %s
            ''', (item['quantity'], item['sku_id'], item['quantity']))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่อีกครั้ง'}), 400
        
        # Clear cart items
        cursor.execute('DELETE FROM cart_items WHERE cart_id = %s', (cart['cart_id'],))

        # Mark coupon as used (Layer 3)
        if applied_coupon:
            cursor.execute('''
                UPDATE user_coupons SET status='used', used_at=CURRENT_TIMESTAMP, used_in_order_id=%s
                WHERE user_id=%s AND coupon_id=%s AND status='ready'
            ''', (order['id'], user_id, applied_coupon['id']))
            cursor.execute('UPDATE coupons SET usage_count = usage_count + 1 WHERE id=%s', (applied_coupon['id'],))

        conn.commit()
        
        # Add shipment count to response
        order['shipment_count'] = len(warehouse_shipments)
        
        # Notify reseller via bot chat: payment deadline reminder
        try:
            send_order_status_chat(user_id, order['order_number'], 'pending_payment_reminder', order_id=order['id'])
        except Exception:
            pass

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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/orders', methods=['GET'])
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
                   o.payment_method, o.stripe_payment_intent_id,
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/orders/<int:order_id>', methods=['GET'])
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
        order['shipping_fee'] = float(order['shipping_fee']) if order['shipping_fee'] else 0
        order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
        order['promotion_discount'] = float(order['promotion_discount']) if order.get('promotion_discount') else 0
        order['coupon_discount'] = float(order['coupon_discount']) if order.get('coupon_discount') else 0
        
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
                    tracking_number = shipment_dict['tracking_number']
                    if '{tracking}' in tracking_template:
                        shipment_dict['tracking_url'] = tracking_template.replace('{tracking}', tracking_number)
                    else:
                        shipment_dict['tracking_url'] = tracking_template + tracking_number
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

        # Get refund info if exists
        cursor.execute('''
            SELECT refund_amount, slip_url, status, notes, created_at, completed_at,
                   bank_name, bank_account_number, bank_account_name, promptpay_number
            FROM order_refunds WHERE order_id = %s
            ORDER BY created_at DESC LIMIT 1
        ''', (order_id,))
        refund_row = cursor.fetchone()
        if refund_row:
            r = dict(refund_row)
            r['refund_amount'] = float(r['refund_amount']) if r['refund_amount'] else 0
            order['refund'] = r
        else:
            order['refund'] = None
        
        return jsonify(order), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/orders/<int:order_id>/shipments/<int:shipment_id>', methods=['PATCH'])
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
                    cursor.execute('''
                        UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND status != 'delivered'
                    ''', (order_id,))
                    if cursor.rowcount > 0:
                        cursor.execute('SELECT final_amount, user_id FROM orders WHERE id = %s', (order_id,))
                        ord_info = cursor.fetchone()
                        if ord_info and ord_info['final_amount']:
                            cursor.execute('UPDATE users SET total_purchases = COALESCE(total_purchases,0) + %s WHERE id = %s',
                                           (ord_info['final_amount'], ord_info['user_id']))
                            cursor.execute('''SELECT u.id, u.reseller_tier_id, u.tier_manual_override,
                                (SELECT id FROM reseller_tiers WHERE upgrade_threshold <= u.total_purchases
                                 AND is_manual_only=FALSE ORDER BY level_rank DESC LIMIT 1) as new_tier_id
                                FROM users u WHERE u.id = %s''', (ord_info['user_id'],))
                            u = cursor.fetchone()
                            if u and u['new_tier_id'] and not u['tier_manual_override'] and u['new_tier_id'] != u['reseller_tier_id']:
                                cursor.execute('UPDATE users SET reseller_tier_id=%s WHERE id=%s', (u['new_tier_id'], u['id']))
                                cursor.execute('SELECT name FROM reseller_tiers WHERE id=%s', (u['new_tier_id'],))
                                t = cursor.fetchone()
                                if t:
                                    create_notification(u['id'], 'ยินดีด้วย! คุณได้รับการอัพเกรดระดับ',
                                        f'คุณได้รับการอัพเกรดเป็นระดับ {t["name"]}', 'success', 'tier', u['new_tier_id'])
        
        # Check if any shipment is shipped -> update order status to shipped
        elif data.get('status') == 'shipped':
            cursor.execute('''
                SELECT status FROM orders WHERE id = %s
            ''', (order_id,))
            current_order = cursor.fetchone()
            
            if current_order and current_order['status'] in ('paid', 'preparing'):
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
                            send_order_status_chat(reseller_info['user_id'], reseller_info['order_number'] or f'#{order_id}', 'shipped', tracking_info, order_id=order_id)
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
                            send_order_status_chat(reseller_info['user_id'], reseller_info['order_number'] or f'#{order_id}', 'delivered', order_id=order_id)
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/orders/<int:order_id>/payment-slip', methods=['POST'])
@orders_bp.route('/api/orders/<int:order_id>/payment-slips', methods=['POST'])
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
                
                import base64
                file_data = slip_file.read()
                
                max_size = 5 * 1024 * 1024
                if len(file_data) > max_size:
                    return jsonify({'error': 'ไฟล์ใหญ่เกิน 5MB กรุณาลดขนาดรูป'}), 400
                
                mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp', 'heic': 'image/heic'}
                mime_type = mime_map.get(original_ext, 'image/jpeg')
                b64_data = base64.b64encode(file_data).decode('utf-8')
                slip_image_url = f'data:{mime_type};base64,{b64_data}'
            else:
                return jsonify({'error': 'กรุณาเลือกรูปสลิป'}), 400
        else:
            data = request.get_json(silent=True) or {}
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
        admins = [dict(a) for a in cursor.fetchall()]
        order_num = order.get('order_number') or f'#{order_id}'

        cursor.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
        reseller = cursor.fetchone()
        reseller_name = reseller['full_name'] if reseller else 'Reseller'

        def _notify():
            try:
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
                            url='/admin#orders',
                            tag=f'slip-{order_id}'
                        )
                    except Exception as push_err:
                        print(f"[PUSH] Admin push error: {push_err}")
                try:
                    send_order_status_chat(user_id, order_num, 'slip_uploaded', order_id=order_id)
                except Exception as chat_err:
                    print(f"[CHAT] Slip upload chat notification error: {chat_err}")
            except Exception as e:
                print(f"[SLIP] Background notify error: {e}")

        threading.Thread(target=_notify, daemon=True).start()

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

@orders_bp.route('/api/admin/dashboard-stats', methods=['GET'])
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
        
        # Sales today (approved orders with paid_at set - filtered by brand for Assistant Admin)
        if is_assistant_admin and brand_ids_tuple:
            cursor.execute('''
                SELECT COALESCE(SUM(oi.subtotal), 0) as total,
                       COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE o.paid_at IS NOT NULL
                AND DATE(o.paid_at) = %s
                AND p.brand_id IN %s
            ''', (today, brand_ids_tuple))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE paid_at IS NOT NULL
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
                WHERE o.paid_at IS NOT NULL
                AND EXTRACT(YEAR FROM o.paid_at) = EXTRACT(YEAR FROM CURRENT_DATE)
                AND EXTRACT(MONTH FROM o.paid_at) = EXTRACT(MONTH FROM CURRENT_DATE)
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE paid_at IS NOT NULL
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
                WHERE o.paid_at IS NOT NULL
                AND p.brand_id IN %s
            ''', (brand_ids_tuple,))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(final_amount), 0) as total,
                       COUNT(*) as count
                FROM orders 
                WHERE paid_at IS NOT NULL
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
                WHERE o.paid_at IS NOT NULL
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
                WHERE paid_at IS NOT NULL
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
                WHERE o.paid_at IS NOT NULL
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
                WHERE o.paid_at IS NOT NULL
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/sales-history', methods=['GET'])
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
                       COUNT(DISTINCT CASE WHEN o.paid_at IS NOT NULL THEN o.id END) as paid_count,
                       COALESCE(SUM(CASE WHEN o.paid_at IS NOT NULL THEN oi.subtotal END), 0) as paid_total
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
                       COUNT(CASE WHEN paid_at IS NOT NULL THEN 1 END) as paid_count,
                       COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN final_amount END), 0) as paid_total
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/brand-sales', methods=['GET'])
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
            LEFT JOIN orders o ON o.id = oi.order_id AND o.paid_at IS NOT NULL
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ADMIN ORDER MANAGEMENT ====================

@orders_bp.route('/api/admin/quick-order/parse-label', methods=['POST'])
@admin_required
def parse_shipping_label():
    """Use Gemini Vision to extract info from a Shopee/Lazada shipping label image"""
    try:
        from google import genai as google_genai
        import base64

        gemini_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_key:
            return jsonify({'error': 'ไม่พบ GEMINI_API_KEY กรุณาตั้งค่า API Key ก่อน'}), 500

        if 'image' not in request.files:
            return jsonify({'error': 'กรุณาแนบรูปภาพใบปะหน้า'}), 400

        image_file = request.files['image']
        if not image_file.filename:
            return jsonify({'error': 'ไม่พบไฟล์รูปภาพ'}), 400

        allowed = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
        ext = image_file.filename.rsplit('.', 1)[-1].lower() if '.' in image_file.filename else ''
        if ext not in allowed:
            return jsonify({'error': 'รองรับเฉพาะไฟล์รูปภาพ (jpg, jpeg, png, webp)'}), 400

        image_data = image_file.read()
        mime_type = image_file.mimetype or f'image/{ext}'

        client = google_genai.Client(api_key=gemini_key)

        prompt = """วิเคราะห์ใบปะหน้าพัสดุนี้และดึงข้อมูลต่อไปนี้เป็น JSON:
{
  "platform": "shopee หรือ lazada หรือ other (ระบุจากโลโก้/สีบนใบปะหน้า)",
  "tracking_number": "เลข tracking/หมายเลขพัสดุ (ตัวอักษรและตัวเลข เช่น TH123456789)",
  "customer_name": "ชื่อผู้รับ",
  "customer_phone": "เบอร์โทรผู้รับ (ถ้ามี)",
  "address": "ที่อยู่จัดส่งเต็ม",
  "province": "จังหวัด",
  "district": "อำเภอ/เขต",
  "subdistrict": "ตำบล/แขวง",
  "postal_code": "รหัสไปรษณีย์"
}
ถ้าไม่พบข้อมูลใดให้ใส่ null
ตอบเป็น JSON เท่านั้น ไม่ต้องมีคำอธิบายเพิ่มเติม"""

        from google.genai import types as genai_types
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                genai_types.Part.from_bytes(data=image_data, mime_type=mime_type),
                prompt
            ]
        )

        raw = response.text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]
            raw = raw.strip()

        import json as _json
        extracted = _json.loads(raw)

        phone_val = (extracted.get('customer_phone') or '').strip() or None
        customer_status = 'new'
        existing_customer = None
        if phone_val:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT id, name FROM customers WHERE phone = %s', (phone_val,))
            row = cursor.fetchone()
            if row:
                existing_customer = dict(row)
                customer_status = 'existing'
            cursor.close()
            conn.close()

        extracted['customer_status'] = customer_status
        extracted['existing_customer'] = existing_customer
        return jsonify({'success': True, 'data': extracted}), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'ไม่สามารถอ่านใบปะหน้าได้: {str(e)}'}), 500


@orders_bp.route('/api/admin/quick-order', methods=['POST'])
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
        platform = data.get('platform')
        tracking_number = data.get('tracking_number', '').strip() if data.get('tracking_number') else None
        shipping_name = (data.get('shipping_name') or '').strip() or None
        shipping_phone = (data.get('shipping_phone') or '').strip() or None
        shipping_address = (data.get('shipping_address') or '').strip() or None
        shipping_province = (data.get('shipping_province') or '').strip() or None
        shipping_district = (data.get('shipping_district') or '').strip() or None
        shipping_subdistrict = (data.get('shipping_subdistrict') or '').strip() or None
        shipping_postal = (data.get('shipping_postal') or '').strip() or None
        
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

        # Upsert customer by phone (or name-only) and link to order
        customer_id = None
        customer_status = 'none'
        if customer_name or customer_phone:
            phone_val = (customer_phone or '').strip() or None
            name_val = (customer_name or '').strip() or None
            src = platform or 'manual'
            if phone_val:
                cursor.execute('''
                    INSERT INTO customers (name, phone, source)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (phone) WHERE phone IS NOT NULL AND phone <> ''
                    DO UPDATE SET
                        name = COALESCE(EXCLUDED.name, customers.name),
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, (xmax = 0) AS is_new
                ''', (name_val, phone_val, src))
                row = cursor.fetchone()
                customer_id = row['id']
                customer_status = 'new' if row['is_new'] else 'existing'
            elif name_val:
                cursor.execute('''
                    INSERT INTO customers (name, source) VALUES (%s, %s) RETURNING id
                ''', (name_val, src))
                customer_id = cursor.fetchone()['id']
                customer_status = 'new'

        # Generate order number
        order_number = generate_order_number(cursor)
        
        # Create order with shipping address
        cursor.execute('''
            INSERT INTO orders (order_number, user_id, channel_id, status, total_amount, discount_amount, final_amount,
                notes, is_quick_order, platform, customer_id,
                shipping_name, shipping_phone, shipping_address, shipping_province,
                shipping_district, shipping_subdistrict, shipping_postal)
            VALUES (%s, %s, %s, 'paid', %s, 0, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, order_number, status, final_amount, created_at
        ''', (order_number, session.get('user_id'), sales_channel_id, total_amount, total_amount, final_notes, platform, customer_id,
              shipping_name or customer_name, shipping_phone or customer_phone,
              shipping_address, shipping_province, shipping_district, shipping_subdistrict, shipping_postal))
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
        shipment_status_init = 'shipped' if tracking_number else 'pending'
        for wh_id, shipment_items in warehouse_shipments.items():
            if tracking_number:
                cursor.execute('''
                    INSERT INTO order_shipments (order_id, warehouse_id, status, tracking_number, shipped_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                ''', (order['id'], wh_id, shipment_status_init, tracking_number))
            else:
                cursor.execute('''
                    INSERT INTO order_shipments (order_id, warehouse_id, status)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (order['id'], wh_id, shipment_status_init))
            shipment_id = cursor.fetchone()['id']
            
            for ship_item in shipment_items:
                cursor.execute('''
                    INSERT INTO order_shipment_items (shipment_id, order_item_id, quantity)
                    VALUES (%s, %s, %s)
                ''', (shipment_id, ship_item['order_item_id'], ship_item['quantity']))
        
        # Deduct stock from warehouses (atomic check prevents negative stock)
        for sku_id, wh_id, qty in stock_deductions:
            cursor.execute('''
                UPDATE sku_warehouse_stock
                SET stock = stock - %s
                WHERE sku_id = %s AND warehouse_id = %s AND stock >= %s
            ''', (qty, sku_id, wh_id, qty))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่อีกครั้ง'}), 400
        
        # Update main SKU stock (atomic check)
        for item in items:
            cursor.execute('''
                UPDATE skus SET stock = stock - %s WHERE id = %s AND stock >= %s
            ''', (item['quantity'], item['sku_id'], item['quantity']))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่อีกครั้ง'}), 400
        
        # If tracking number provided, update order status to shipped
        if tracking_number:
            cursor.execute('''
                UPDATE orders SET status = 'shipped', updated_at = CURRENT_TIMESTAMP WHERE id = %s
            ''', (order['id'],))
        
        conn.commit()
        
        return jsonify({
            'message': 'สร้างคำสั่งซื้อสำเร็จ',
            'order_number': order['order_number'],
            'order_id': order['id'],
            'customer_status': customer_status
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

@orders_bp.route('/api/admin/quick-orders', methods=['GET'])
@admin_required
def get_quick_orders():
    """Get all quick orders with shipment info"""
    conn = None
    cursor = None
    try:
        status_filter = request.args.get('status')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        query = '''
            SELECT o.id, o.order_number, o.status, o.total_amount, o.final_amount,
                   o.notes, o.created_at, o.platform,
                   sc.name as channel_name,
                   u.full_name as created_by_name,
                   (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as item_count,
                   (SELECT os.tracking_number FROM order_shipments os WHERE os.order_id = o.id ORDER BY os.id ASC LIMIT 1) as tracking_number,
                   (SELECT os.shipping_provider FROM order_shipments os WHERE os.order_id = o.id ORDER BY os.id ASC LIMIT 1) as shipping_provider,
                   (SELECT os.status FROM order_shipments os WHERE os.order_id = o.id ORDER BY os.id ASC LIMIT 1) as shipment_status
            FROM orders o
            LEFT JOIN sales_channels sc ON sc.id = o.channel_id
            LEFT JOIN users u ON u.id = o.user_id
            WHERE o.is_quick_order = TRUE
        '''
        params = []
        if status_filter:
            query += ' AND o.status = %s'
            params.append(status_filter)
        query += ' ORDER BY o.created_at DESC'
        cursor.execute(query, params)
        orders = []
        for row in cursor.fetchall():
            order = dict(row)
            order['total_amount'] = float(order['total_amount']) if order['total_amount'] else 0
            order['final_amount'] = float(order['final_amount']) if order['final_amount'] else 0
            orders.append(order)
        return jsonify(orders), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/quick-orders/<int:order_id>/status', methods=['POST'])
@admin_required
def update_quick_order_status(order_id):
    """Update quick order status: shipped / delivered / returned"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        new_status = data.get('status')
        tracking_number = data.get('tracking_number', '').strip() if data.get('tracking_number') else None
        if new_status not in ('shipped', 'delivered', 'returned'):
            return jsonify({'error': 'สถานะไม่ถูกต้อง'}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, status, is_quick_order FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        if not order or not order['is_quick_order']:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if new_status == 'shipped':
            if not tracking_number:
                return jsonify({'error': 'กรุณากรอกเลข Tracking'}), 400
            cursor.execute('''
                UPDATE order_shipments
                SET tracking_number = %s, status = 'shipped', shipped_at = CURRENT_TIMESTAMP
                WHERE order_id = %s
            ''', (tracking_number, order_id))
            cursor.execute('''
                UPDATE orders SET status = 'shipped', updated_at = CURRENT_TIMESTAMP WHERE id = %s
            ''', (order_id,))
        elif new_status == 'delivered':
            cursor.execute('''
                UPDATE order_shipments SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP WHERE order_id = %s
            ''', (order_id,))
            cursor.execute('''
                UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP WHERE id = %s
            ''', (order_id,))
        elif new_status == 'returned':
            cursor.execute('''
                UPDATE order_shipments SET status = 'returned' WHERE order_id = %s
            ''', (order_id,))
            cursor.execute('''
                UPDATE orders SET status = 'returned', updated_at = CURRENT_TIMESTAMP WHERE id = %s
            ''', (order_id,))
        conn.commit()
        return jsonify({'message': 'อัปเดตสถานะสำเร็จ'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/quick-orders/<int:order_id>/restore-stock', methods=['POST'])
@admin_required
def restore_quick_order_stock(order_id):
    """Restore stock for a returned quick order"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, status, is_quick_order FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        if not order or not order['is_quick_order']:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] != 'returned':
            return jsonify({'error': 'สามารถคืนสต็อกได้เฉพาะออเดอร์ที่มีสถานะ "ตีกลับ" เท่านั้น'}), 400
        cursor.execute('''
            SELECT oi.sku_id, SUM(oi.quantity) as qty
            FROM order_items oi WHERE oi.order_id = %s GROUP BY oi.sku_id
        ''', (order_id,))
        items = cursor.fetchall()
        for item in items:
            cursor.execute('UPDATE skus SET stock = stock + %s WHERE id = %s', (item['qty'], item['sku_id']))
            cursor.execute('''
                SELECT warehouse_id, SUM(quantity) as qty
                FROM order_shipment_items osi
                JOIN order_shipments os ON os.id = osi.shipment_id
                JOIN order_items oi2 ON oi2.id = osi.order_item_id
                WHERE os.order_id = %s AND oi2.sku_id = %s
                GROUP BY warehouse_id
            ''', (order_id, item['sku_id']))
            wh_rows = cursor.fetchall()
            for wh in wh_rows:
                cursor.execute('''
                    INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sku_id, warehouse_id) DO UPDATE SET stock = sku_warehouse_stock.stock + EXCLUDED.stock
                ''', (item['sku_id'], wh['warehouse_id'], wh['qty']))
        cursor.execute('''
            UPDATE orders SET status = 'stock_restored', updated_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (order_id,))
        conn.commit()
        return jsonify({'message': 'คืนสต็อกสำเร็จ'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/customers', methods=['GET'])
@admin_required
def get_customers():
    """Get all customers — UNION of quick-order customers + reseller contact books"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # === Quick-order / admin customers ===
        cursor.execute('''
            SELECT
                'admin_' || c.id::text AS uid,
                'admin' AS source_type,
                c.id, c.name, c.phone, c.address, c.province, c.district,
                c.subdistrict, c.postal_code, c.source, c.tags, c.note,
                c.created_at, c.updated_at,
                NULL::text AS reseller_name,
                COUNT(DISTINCT o.id) AS order_count,
                COALESCE(SUM(o.final_amount), 0) AS total_spent,
                MAX(o.created_at) AS last_order_at,
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT o.platform), NULL) AS platforms
            FROM customers c
            LEFT JOIN orders o ON o.customer_id = c.id AND o.is_quick_order = TRUE
                AND o.status NOT IN ('cancelled', 'returned', 'stock_restored')
            GROUP BY c.id
        ''')
        admin_rows = [dict(r) for r in cursor.fetchall()]

        # === Reseller contact-book customers ===
        cursor.execute('''
            SELECT
                'rc_' || rc.id::text AS uid,
                'reseller' AS source_type,
                rc.id,
                rc.full_name AS name,
                rc.phone,
                rc.address,
                rc.province,
                rc.district,
                rc.subdistrict,
                rc.postal_code,
                'reseller'::text AS source,
                '{}'::text[] AS tags,
                rc.notes AS note,
                rc.created_at,
                rc.updated_at,
                u.full_name AS reseller_name,
                0::bigint AS order_count,
                0::numeric AS total_spent,
                NULL::timestamp AS last_order_at,
                '{}'::text[] AS platforms
            FROM reseller_customers rc
            JOIN users u ON u.id = rc.reseller_id
        ''')
        reseller_rows = [dict(r) for r in cursor.fetchall()]

        all_rows = admin_rows + reseller_rows
        customers = []
        for c in all_rows:
            c['total_spent'] = float(c['total_spent'] or 0)
            c['order_count'] = int(c['order_count'] or 0)
            c['platforms'] = list(c['platforms'] or [])
            c['tags'] = list(c['tags'] or [])
            if c['source_type'] == 'reseller':
                c['auto_tag'] = 'reseller'
            elif not c['tags']:
                if c['order_count'] == 0:
                    c['auto_tag'] = 'inactive'
                elif c['order_count'] >= 3:
                    c['auto_tag'] = 'frequent'
                else:
                    c['auto_tag'] = 'new'
            else:
                c['auto_tag'] = c['tags'][0]
            customers.append(c)

        # Sort: most recent first (handle datetime vs None)
        import datetime as _dt
        _epoch = _dt.datetime(2000, 1, 1)
        customers.sort(key=lambda x: (x['last_order_at'] or x['updated_at'] or x['created_at'] or _epoch), reverse=True)
        return jsonify(customers), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/customers', methods=['POST'])
@admin_required
def upsert_customer():
    """Create or update customer by phone (upsert)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        phone = (data.get('phone') or '').strip()
        name = (data.get('name') or '').strip() or None
        address = (data.get('address') or '').strip() or None
        province = (data.get('province') or '').strip() or None
        district = (data.get('district') or '').strip() or None
        subdistrict = (data.get('subdistrict') or '').strip() or None
        postal_code = (data.get('postal_code') or '').strip() or None
        source = data.get('source') or 'manual'
        note = (data.get('note') or '').strip() or None
        customer_id = data.get('id')

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if customer_id:
            cursor.execute('''
                UPDATE customers SET name=%s, phone=%s, address=%s, province=%s, district=%s,
                    subdistrict=%s, postal_code=%s, source=%s, note=%s, updated_at=CURRENT_TIMESTAMP
                WHERE id=%s RETURNING id
            ''', (name, phone or None, address, province, district, subdistrict, postal_code, source, note, customer_id))
            row = cursor.fetchone()
            cid = row['id'] if row else customer_id
        elif phone:
            cursor.execute('''
                INSERT INTO customers (name, phone, address, province, district, subdistrict, postal_code, source, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (phone) WHERE phone IS NOT NULL AND phone <> ''
                DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, customers.name),
                    address = COALESCE(EXCLUDED.address, customers.address),
                    province = COALESCE(EXCLUDED.province, customers.province),
                    district = COALESCE(EXCLUDED.district, customers.district),
                    subdistrict = COALESCE(EXCLUDED.subdistrict, customers.subdistrict),
                    postal_code = COALESCE(EXCLUDED.postal_code, customers.postal_code),
                    source = COALESCE(EXCLUDED.source, customers.source),
                    note = COALESCE(EXCLUDED.note, customers.note),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            ''', (name, phone, address, province, district, subdistrict, postal_code, source, note))
            cid = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO customers (name, address, province, district, subdistrict, postal_code, source, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            ''', (name, address, province, district, subdistrict, postal_code, source, note))
            cid = cursor.fetchone()['id']

        conn.commit()
        return jsonify({'message': 'บันทึกสำเร็จ', 'id': cid}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/customers/check-phone', methods=['GET'])
@admin_required
def check_customer_phone():
    """Check if phone already exists in customers"""
    conn = None
    cursor = None
    try:
        phone = request.args.get('phone', '').strip()
        if not phone:
            return jsonify({'exists': False}), 200
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, name FROM customers WHERE phone = %s', (phone,))
        row = cursor.fetchone()
        if row:
            return jsonify({'exists': True, 'id': row['id'], 'name': row['name']}), 200
        return jsonify({'exists': False}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/customers/<int:customer_id>', methods=['DELETE'])
@admin_required
def admin_delete_customer(customer_id):
    """Delete an admin-created customer from the customers table"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM customers WHERE id = %s RETURNING id', (customer_id,))
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


@orders_bp.route('/api/admin/orders/counts', methods=['GET'])
@admin_required
def get_order_counts():
    """Get order counts grouped by status"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_role = session.get('role')
        user_id = session.get('user_id')
        is_assistant_admin = user_role == 'Assistant Admin'

        if is_assistant_admin:
            cursor.execute('SELECT brand_id FROM admin_brand_access WHERE user_id = %s', (user_id,))
            brand_ids = [row['brand_id'] for row in cursor.fetchall()]
            if not brand_ids:
                return jsonify({}), 200
            cursor.execute('''
                SELECT o.status, COUNT(DISTINCT o.id) as count
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN skus s ON s.id = oi.sku_id
                JOIN products p ON p.id = s.product_id
                WHERE p.brand_id = ANY(%s)
                GROUP BY o.status
            ''', (brand_ids,))
        else:
            cursor.execute('SELECT status, COUNT(*) as count FROM orders GROUP BY status')

        rows = cursor.fetchall()
        counts = {row['status']: row['count'] for row in rows}
        return jsonify(counts), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders', methods=['GET'])
@admin_required
def get_all_orders():
    """Get all orders for admin"""
    conn = None
    cursor = None
    try:
        status_filter = request.args.get('status')
        reseller_id_filter = request.args.get('reseller_id', type=int)
        limit_filter = request.args.get('limit', type=int)
        
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
                       (SELECT ps.amount FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_amount,
                       (SELECT ps.created_at FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_created_at
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
                       (SELECT ps.amount FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_amount,
                       (SELECT ps.created_at FROM payment_slips ps WHERE ps.order_id = o.id ORDER BY ps.created_at DESC LIMIT 1) as slip_created_at
                FROM orders o
                LEFT JOIN users u ON u.id = o.user_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                LEFT JOIN sales_channels sc ON sc.id = o.channel_id
            '''
            params = []
            conditions = ['(o.is_quick_order = FALSE OR o.is_quick_order IS NULL)']
            if status_filter:
                conditions.append('o.status = %s')
                params.append(status_filter)
            if reseller_id_filter:
                conditions.append('o.user_id = %s')
                params.append(reseller_id_filter)
            if conditions:
                query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY o.created_at DESC'
        if limit_filter:
            query += f' LIMIT {int(limit_filter)}'
        
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/approve', methods=['POST'])
@admin_required
def approve_order(order_id):
    """Approve order payment (stock was already deducted at order creation)"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
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
        
        # Update order status to preparing + set paid_at timestamp
        cursor.execute('''
            UPDATE orders SET status = 'preparing', paid_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (order_id,))
        
        # Update slip status if provided
        if slip_id:
            cursor.execute('''
                UPDATE payment_slips SET status = 'approved', verified_by = %s, verified_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (admin_id, slip_id))
        else:
            cursor.execute('''
                UPDATE payment_slips SET status = 'approved', verified_by = %s, verified_at = CURRENT_TIMESTAMP
                WHERE order_id = %s AND status = 'pending'
            ''', (admin_id, order_id))
        
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
                send_order_status_chat(order['user_id'], order_info['order_number'] if order_info else f'#{order_id}', 'approved', order_id=order_id)
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
        
        return jsonify({'message': 'ยืนยันการชำระเงินสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/reject', methods=['POST'])
@admin_required
def reject_order(order_id):
    """Reject order payment slip — status → rejected, notify reseller"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        reason = data.get('reason', '')

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()

        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] != 'under_review':
            return jsonify({'error': 'ออเดอร์นี้ไม่ได้อยู่ในสถานะรอตรวจสอบ'}), 400

        # Update order status back to pending_payment so reseller can re-upload slip
        cursor.execute('''
            UPDATE orders SET status = 'pending_payment',
                notes = CONCAT(COALESCE(notes, ''), ' [ปฏิเสธสลิป: ', %s, ']'),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (reason, order_id))

        # Mark pending payment slip as rejected
        cursor.execute('''
            UPDATE payment_slips SET status = 'rejected', verified_by = %s, verified_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND status = 'pending'
        ''', (admin_id, order_id))

        conn.commit()

        order_number = order['order_number'] or f'#{order_id}'
        extra = f'เหตุผล: {reason} — กรุณาอัปโหลดสลิปใหม่' if reason else 'กรุณาอัปโหลดสลิปการชำระเงินใหม่'
        # Notify reseller via chat
        try:
            send_order_status_chat(order['user_id'], order_number, 'pending_payment',
                                   extra, order_id=order_id)
        except Exception as chat_err:
            print(f'Reject chat notification error: {chat_err}')

        # In-app notification
        create_notification(order['user_id'], 'สลิปการชำระเงินถูกปฏิเสธ — กรุณาอัปโหลดใหม่',
                            f'คำสั่งซื้อ {order_number}: {reason}' if reason else f'คำสั่งซื้อ {order_number} กรุณาอัปโหลดสลิปใหม่',
                            'warning', 'order', order_id)

        return jsonify({'message': 'ปฏิเสธสลิปและรีเซ็ตเป็นรอชำระเงินสำเร็จ'}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/request-new-slip', methods=['POST'])
@admin_required
def request_new_slip(order_id):
    """Request new payment slip - delete old slip and reset to pending_payment"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
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
        
        cursor.execute('SELECT slip_image_url FROM payment_slips WHERE order_id = %s', (order_id,))
        old_slips = cursor.fetchall()
        for old_slip in old_slips:
            url = old_slip.get('slip_image_url', '')
            if url and url.startswith('/static/uploads/'):
                try:
                    file_path = url.lstrip('/')
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
        
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
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'request_new_slip', f'เหตุผล: {reason}', order_id=order_id)
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/cancel', methods=['POST'])
@admin_required
def cancel_order(order_id):
    """Cancel order and restore stock"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        reason = data.get('reason', '')
        admin_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Get order status + paid_at to know if total_purchases was already added
        cursor.execute('SELECT id, status, user_id, final_amount, paid_at FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        CANCELLABLE_STATUSES = ('pending_payment', 'under_review', 'rejected', 'paid', 'preparing', 'failed_delivery', 'shipped')
        if order['status'] not in CANCELLABLE_STATUSES:
            return jsonify({'error': 'ไม่สามารถยกเลิกคำสั่งซื้อนี้ได้'}), 400
        
        current_status = order['status']
        # Orders that were shipped/failed_delivery: stock NOT auto-restored (item still in transit or returned)
        stock_in_transit = current_status in ('shipped', 'failed_delivery')
        # Orders that were paid/preparing: stock restored automatically (item still in warehouse)
        needs_refund = current_status in ('paid', 'preparing', 'shipped', 'failed_delivery')
        # New status after cancel
        new_status = 'pending_refund' if needs_refund else 'cancelled'
        # If order was already delivered, deduct from total_purchases
        was_delivered = order['status'] == 'delivered'
        
        if not stock_in_transit:
            # Get order items and shipments to restore stock (only for non-shipped orders)
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
            UPDATE orders SET status = %s, notes = CONCAT(COALESCE(notes, ''), ' [ยกเลิก: ', %s, ']'), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (new_status, reason, order_id))
        
        # Deduct total_purchases only if order was already delivered
        if was_delivered and order['final_amount']:
            cursor.execute('''
                UPDATE users SET total_purchases = GREATEST(0, COALESCE(total_purchases, 0) - %s)
                WHERE id = %s
            ''', (order['final_amount'], order['user_id']))
        
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
            send_order_status_chat(reseller_info.get('user_id') or order.get('user_id', 0), reseller_info['order_number'] or f'#{order_id}', 'cancelled', f'เหตุผล: {reason}' if reason else '', order_id=order_id)
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
        
        return jsonify({'message': 'ยกเลิกคำสั่งซื้อสำเร็จ', 'requires_refund': needs_refund, 'new_status': new_status, 'stock_in_transit': stock_in_transit}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/ship', methods=['POST'])
@admin_required
def admin_ship_order(order_id):
    """Save tracking number and mark order as shipped"""
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        tracking_number = (data.get('tracking_number') or '').strip()
        if not tracking_number:
            return jsonify({'error': 'กรุณากรอกเลข Tracking'}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, status, user_id, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] != 'preparing':
            return jsonify({'error': 'สถานะออเดอร์ต้องเป็น "เตรียมสินค้า" ก่อนจัดส่ง'}), 400
        cursor.execute('''
            UPDATE orders SET status = 'shipped', tracking_number = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (tracking_number, order_id))
        cursor.execute('''
            UPDATE order_shipments
            SET tracking_number = %s, status = 'shipped', shipped_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
        ''', (tracking_number, order_id))
        conn.commit()
        try:
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'shipped', f'เลข Tracking: {tracking_number}', order_id=order_id)
        except Exception as chat_err:
            print(f"[SHIP] Chat error: {chat_err}")
        return jsonify({'message': 'อัปเดตสถานะจัดส่งสำเร็จ', 'tracking_number': tracking_number}), 200
    except Exception as e:
        try:
            if conn: conn.rollback()
        except Exception:
            pass
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/refund-info', methods=['GET'])
@admin_required
def get_refund_info(order_id):
    """Get refund calculation and reseller bank info for a cancelled shipped order"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT o.id, o.order_number, o.status, o.final_amount, o.shipping_fee,
                   u.id as reseller_id, u.full_name, u.phone, u.email,
                   u.bank_name, u.bank_account_number, u.bank_account_name, u.promptpay_number
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = %s
        ''', (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        cursor.execute('SELECT * FROM order_refunds WHERE order_id = %s ORDER BY created_at DESC LIMIT 1', (order_id,))
        existing_refund = cursor.fetchone()

        # Calculate total weight from order items × product weight
        cursor.execute('''
            SELECT COALESCE(SUM(COALESCE(p.weight, 0) * oi.quantity), 0) AS total_weight_g
            FROM order_items oi
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE oi.order_id = %s
        ''', (order_id,))
        weight_row = cursor.fetchone()
        total_weight_g = float(weight_row['total_weight_g'] or 0)

        # Look up shipping rate from weight table
        cursor.execute('''
            SELECT rate, min_weight, max_weight
            FROM shipping_weight_rates
            WHERE is_active = true
              AND min_weight <= %s
              AND (max_weight IS NULL OR max_weight >= %s)
            ORDER BY min_weight DESC
            LIMIT 1
        ''', (total_weight_g, total_weight_g))
        rate_row = cursor.fetchone()
        calculated_shipping_fee = float(rate_row['rate']) if rate_row else 0.0
        rate_tier = {
            'min_weight': int(rate_row['min_weight']) if rate_row else 0,
            'max_weight': int(rate_row['max_weight']) if rate_row and rate_row['max_weight'] else None,
            'rate': calculated_shipping_fee
        } if rate_row else None

        final_amount = float(order['final_amount'] or 0)
        refund_amount = max(0, final_amount - calculated_shipping_fee)

        return jsonify({
            'order_id': order_id,
            'order_number': order['order_number'],
            'status': order['status'],
            'final_amount': final_amount,
            'shipping_fee': calculated_shipping_fee,
            'total_weight_g': total_weight_g,
            'rate_tier': rate_tier,
            'refund_amount': refund_amount,
            'reseller': {
                'id': order['reseller_id'],
                'full_name': order['full_name'],
                'phone': order['phone'],
                'email': order['email'],
                'bank_name': order['bank_name'],
                'bank_account_number': order['bank_account_number'],
                'bank_account_name': order['bank_account_name'],
                'promptpay_number': order['promptpay_number'],
            },
            'existing_refund': dict(existing_refund) if existing_refund else None
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/refund', methods=['POST'])
@admin_required
def process_refund(order_id):
    """Process a refund: save slip + update status + notify reseller via chat"""
    import base64, io, uuid
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        refund_amount = float(data.get('refund_amount', 0))
        shipping_deducted = float(data.get('shipping_deducted', 0))
        total_paid = float(data.get('total_paid', 0))
        bank_name = data.get('bank_name', '')
        bank_account_number = data.get('bank_account_number', '')
        bank_account_name = data.get('bank_account_name', '')
        promptpay_number = data.get('promptpay_number', '')
        slip_data = data.get('slip_data', '')  # base64 encoded image
        notes = data.get('notes', '')

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT o.id, o.order_number, o.user_id, o.status FROM orders o WHERE o.id = %s', (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404

        slip_url = None
        if slip_data and slip_data.startswith('data:image'):
            try:
                header, encoded = slip_data.split(',', 1)
                img_bytes = base64.b64decode(encoded)
                ext = 'jpg' if 'jpeg' in header else 'png'
                filename = f'refund_slip_{order_id}_{uuid.uuid4().hex[:8]}.{ext}'
                upload_dir = os.path.join('static', 'uploads', 'refund_slips')
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                slip_url = f'/static/uploads/refund_slips/{filename}'
            except Exception as img_err:
                print(f'Slip upload error: {img_err}')

        cursor.execute('''
            INSERT INTO order_refunds (order_id, refund_amount, shipping_deducted, total_paid,
                bank_name, bank_account_number, bank_account_name, promptpay_number,
                slip_url, status, notes, created_by, completed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'completed',%s,%s,CURRENT_TIMESTAMP)
            RETURNING id
        ''', (order_id, refund_amount, shipping_deducted, total_paid,
              bank_name, bank_account_number, bank_account_name, promptpay_number,
              slip_url, notes, admin_id))
        # Update order status to refunded
        cursor.execute("UPDATE orders SET status = 'refunded', updated_at = CURRENT_TIMESTAMP WHERE id = %s", (order_id,))
        conn.commit()

        # Send chat notification with slip
        try:
            chat_msg = f'💸 คืนเงินสำเร็จ ฿{refund_amount:,.2f}\n'
            chat_msg += f'(หักค่าขนส่ง ฿{shipping_deducted:,.2f} จากยอดจ่าย ฿{total_paid:,.2f})'
            if bank_account_number:
                chat_msg += f'\nโอนไปยัง: {bank_name} {bank_account_number} ({bank_account_name})'
            send_order_status_chat(
                order['user_id'],
                order['order_number'] or f'#{order_id}',
                'refunded',
                chat_msg,
                order_id=order_id
            )
        except Exception as chat_err:
            print(f'Refund chat notification error: {chat_err}')

        return jsonify({'message': 'บันทึกการคืนเงินสำเร็จ', 'slip_url': slip_url}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/refund-qr', methods=['GET'])
@admin_required
def generate_refund_qr(order_id):
    """Generate PromptPay QR for refund using reseller's promptpay_number"""
    import qrcode, io, base64
    conn = None
    cursor = None
    try:
        amount = request.args.get('amount', type=float)
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT u.promptpay_number, u.full_name
            FROM orders o JOIN users u ON u.id = o.user_id WHERE o.id = %s
        ''', (order_id,))
        row = cursor.fetchone()
        if not row or not row['promptpay_number']:
            return jsonify({'error': 'สมาชิกยังไม่ได้ตั้งค่าเบอร์ PromptPay'}), 400

        phone_or_id = row['promptpay_number'].replace('-', '').replace(' ', '')
        if len(phone_or_id) == 10 and phone_or_id.startswith('0'):
            formatted_id = '0066' + phone_or_id[1:]
            aid = '01'
        elif len(phone_or_id) == 13:
            formatted_id = phone_or_id
            aid = '02'
        else:
            return jsonify({'error': 'รูปแบบเบอร์ PromptPay ไม่ถูกต้อง'}), 400

        def crc16(data):
            crc = 0xFFFF
            for byte in data.encode('ascii'):
                crc ^= byte << 8
                for _ in range(8):
                    if crc & 0x8000: crc = (crc << 1) ^ 0x1021
                    else: crc <<= 1
                    crc &= 0xFFFF
            return format(crc, '04X')

        aid_field = f'00{len("A000000677010111"):02d}A000000677010111{aid}{len(formatted_id):02d}{formatted_id}'
        merchant_field = f'29{len(aid_field):02d}{aid_field}'
        payload_parts = ['000201', '010212', merchant_field, '52040000', '5303764']
        if amount and amount > 0:
            amount_str = f'{amount:.2f}'
            payload_parts.append(f'54{len(amount_str):02d}{amount_str}')
        payload_parts += ['5802TH', '6304']
        payload = ''.join(payload_parts)
        payload += crc16(payload)

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        return jsonify({
            'qr_image': f'data:image/png;base64,{img_b64}',
            'promptpay_number': row['promptpay_number'],
            'account_name': row['full_name'],
            'amount': amount
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/return-stock-info', methods=['GET'])
@admin_required
def get_return_stock_info(order_id):
    """Get order items info for return-to-stock modal (pending_refund orders that were shipped)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT o.id, o.order_number, o.status,
                   EXISTS(SELECT 1 FROM order_shipments os WHERE os.order_id = o.id AND os.tracking_number IS NOT NULL AND os.tracking_number != '') as was_shipped
            FROM orders o WHERE o.id = %s
        ''', (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] != 'pending_refund':
            return jsonify({'error': 'ออเดอร์นี้ไม่อยู่ในสถานะรอคืนเงิน'}), 400

        cursor.execute('''
            SELECT oi.id as order_item_id, oi.sku_id, oi.quantity as ordered_qty,
                   s.sku_code,
                   p.name as product_name,
                   os.warehouse_id, COALESCE(osi.quantity, oi.quantity) as shipped_qty,
                   w.name as warehouse_name,
                   COALESCE(sws.stock, 0) as current_stock,
                   (SELECT STRING_AGG(o.name || ': ' || ov.value, ', ' ORDER BY o.name)
                    FROM sku_values_map svm2
                    JOIN option_values ov ON ov.id = svm2.option_value_id
                    JOIN options o ON o.id = ov.option_id
                    WHERE svm2.sku_id = s.id) as variant_options
            FROM order_items oi
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            LEFT JOIN order_shipment_items osi ON osi.order_item_id = oi.id
            LEFT JOIN order_shipments os ON os.id = osi.shipment_id
            LEFT JOIN warehouses w ON w.id = os.warehouse_id
            LEFT JOIN sku_warehouse_stock sws ON sws.sku_id = oi.sku_id AND sws.warehouse_id = os.warehouse_id
            WHERE oi.order_id = %s
            ORDER BY oi.id
        ''', (order_id,))
        items = cursor.fetchall()

        # Get all return history records (good returns + damaged/lost)
        cursor.execute('''
            SELECT sal.sku_id, sal.warehouse_id, sal.change_type,
                   CASE WHEN sal.change_type = 'return_from_order'
                        THEN (sal.quantity_after - sal.quantity_before)
                        ELSE sal.quantity_after END as qty,
                   sal.notes, sal.created_at,
                   u.full_name as admin_name
            FROM stock_audit_log sal
            LEFT JOIN users u ON u.id = sal.created_by
            WHERE sal.reference_id = %s AND sal.reference_type = 'order'
              AND sal.change_type IN ('return_from_order', 'order_damaged')
            ORDER BY sal.created_at ASC
        ''', (order_id,))
        history_rows = cursor.fetchall()

        history_map = {}
        accounted_map = {}
        for row in history_rows:
            key = (row['sku_id'], row['warehouse_id'])
            qty = int(row['qty'] or 0)
            if key not in history_map:
                history_map[key] = []
            label = 'บันทึกคืนคลัง' if row['change_type'] == 'return_from_order' else 'ไม่คืนคลัง'
            history_map[key].append({
                'date': row['created_at'].strftime('%d/%m/%Y %H:%M') if row['created_at'] else '-',
                'qty': qty,
                'type': row['change_type'],
                'label': label,
                'notes': row['notes'] or '-',
                'admin_name': row['admin_name'] or '-'
            })
            accounted_map[key] = accounted_map.get(key, 0) + qty

        items_list = []
        for item in items:
            key = (item['sku_id'], item['warehouse_id'])
            already_accounted = int(accounted_map.get(key, 0))
            max_ret = max(0, int(item['shipped_qty'] or 0) - already_accounted)
            items_list.append({
                'order_item_id': item['order_item_id'],
                'sku_id': item['sku_id'],
                'sku_code': item['sku_code'],
                'variant_options': item['variant_options'],
                'product_name': item['product_name'],
                'ordered_qty': item['ordered_qty'],
                'shipped_qty': item['shipped_qty'],
                'warehouse_id': item['warehouse_id'],
                'warehouse_name': item['warehouse_name'],
                'current_stock': item['current_stock'],
                'already_accounted': already_accounted,
                'max_returnable': max_ret,
                'return_history': history_map.get(key, [])
            })

        return jsonify({
            'order_id': order_id,
            'order_number': order['order_number'],
            'was_shipped': order['was_shipped'],
            'items': items_list
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/return-stock', methods=['POST'])
@admin_required
def process_return_stock(order_id):
    """Process partial/full stock return for a pending_refund order"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
        items = data.get('items', [])

        if not items:
            return jsonify({'error': 'กรุณาระบุสินค้าที่ต้องการคืน'}), 400

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, status, order_number FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] != 'pending_refund':
            return jsonify({'error': 'ออเดอร์นี้ไม่อยู่ในสถานะรอคืนเงิน'}), 400

        # Get shipped qty per SKU+warehouse
        cursor.execute('''
            SELECT oi.sku_id, os.warehouse_id, COALESCE(osi.quantity, oi.quantity) as shipped_qty
            FROM order_items oi
            JOIN order_shipment_items osi ON osi.order_item_id = oi.id
            JOIN order_shipments os ON os.id = osi.shipment_id
            WHERE oi.order_id = %s
        ''', (order_id,))
        shipped_map = {(r['sku_id'], r['warehouse_id']): int(r['shipped_qty']) for r in cursor.fetchall()}

        # Get already accounted qty per SKU+warehouse (both good returns and damaged/lost)
        cursor.execute('''
            SELECT sku_id, warehouse_id,
                   SUM(CASE WHEN change_type = 'return_from_order' THEN (quantity_after - quantity_before)
                            ELSE quantity_after END) as accounted_qty
            FROM stock_audit_log
            WHERE reference_id = %s AND reference_type = 'order'
              AND change_type IN ('return_from_order', 'order_damaged')
            GROUP BY sku_id, warehouse_id
        ''', (order_id,))
        accounted_map = {(r['sku_id'], r['warehouse_id']): int(r['accounted_qty'] or 0) for r in cursor.fetchall()}

        # Validate all items first
        for item in items:
            sku_id = item.get('sku_id')
            warehouse_id = item.get('warehouse_id')
            return_qty = int(item.get('return_qty', 0))
            if return_qty <= 0:
                continue
            shipped = shipped_map.get((sku_id, warehouse_id), 0)
            accounted = accounted_map.get((sku_id, warehouse_id), 0)
            if accounted + return_qty > shipped:
                return jsonify({'error': f'จำนวนสินค้าเกินที่จัดส่งไป (จัดส่ง {shipped} ชิ้น, รับคืนแล้ว {accounted} ชิ้น)'}), 400

        order_num = order['order_number'] or f'#{order_id}'
        good_return_count = 0
        damaged_count = 0

        for item in items:
            sku_id = item.get('sku_id')
            warehouse_id = item.get('warehouse_id')
            return_qty = int(item.get('return_qty', 0))
            reason = item.get('reason', 'good')
            custom_note = item.get('custom_note', '').strip()
            if not sku_id or not warehouse_id or return_qty <= 0:
                continue

            is_good_return = reason in ('good', 'other')
            reason_labels = {
                'good': 'สินค้าสภาพดี',
                'damaged': 'สินค้ามีตำหนิ',
                'lost': 'สินค้าสูญหาย',
                'other': f'อื่นๆ: {custom_note}' if custom_note else 'อื่นๆ'
            }
            reason_text = reason_labels.get(reason, reason)

            if is_good_return:
                # Restore stock to warehouse and main SKU
                cursor.execute('''
                    INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (sku_id, warehouse_id) DO UPDATE SET stock = sku_warehouse_stock.stock + EXCLUDED.stock
                ''', (sku_id, warehouse_id, return_qty))

                cursor.execute('''
                    INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, change_type, reference_id, reference_type, notes, created_by)
                    SELECT %s, %s, stock - %s, stock, 'return_from_order', %s, 'order', %s, %s
                    FROM sku_warehouse_stock WHERE sku_id = %s AND warehouse_id = %s
                ''', (sku_id, warehouse_id, return_qty, order_id,
                      f'{return_qty} ชิ้น | {reason_text} | ออเดอร์ {order_num}',
                      admin_id, sku_id, warehouse_id))

                cursor.execute('UPDATE skus SET stock = stock + %s WHERE id = %s', (return_qty, sku_id))
                good_return_count += return_qty
            else:
                # Damaged/lost: log only, do NOT restore stock
                # Store qty in quantity_after (quantity_before=0) for easy aggregation
                cursor.execute('''
                    INSERT INTO stock_audit_log (sku_id, warehouse_id, quantity_before, quantity_after, change_type, reference_id, reference_type, notes, created_by)
                    VALUES (%s, %s, 0, %s, 'order_damaged', %s, 'order', %s, %s)
                ''', (sku_id, warehouse_id, return_qty, order_id,
                      f'{return_qty} ชิ้น | {reason_text} | ออเดอร์ {order_num}',
                      admin_id))
                damaged_count += return_qty

        conn.commit()
        parts = []
        if good_return_count > 0:
            parts.append(f'คืนคลัง {good_return_count} ชิ้น')
        if damaged_count > 0:
            parts.append(f'บันทึกตำหนิ/สูญหาย {damaged_count} ชิ้น')
        msg = ' | '.join(parts) if parts else 'ไม่มีการเปลี่ยนแปลง'
        return jsonify({'message': f'บันทึกสำเร็จ: {msg}'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@orders_bp.route('/api/admin/orders/shipped', methods=['GET'])
@admin_required
def get_shipped_orders():
    """Get all orders currently being shipped, with shipment data"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('SELECT name, tracking_url FROM shipping_providers WHERE is_active = TRUE')
        provider_tracking_map = {p['name']: p['tracking_url'] for p in cursor.fetchall()}

        cursor.execute('''
            SELECT o.id, o.order_number, o.status, o.final_amount, o.updated_at,
                   u.full_name AS reseller_name, u.id AS reseller_id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.status = 'shipped'
            ORDER BY o.updated_at DESC
        ''')
        orders = [dict(r) for r in cursor.fetchall()]

        for order in orders:
            order['final_amount'] = float(order['final_amount'] or 0)
            cursor.execute('''
                SELECT os.id, os.tracking_number, os.shipping_provider, os.shipped_at,
                       w.name AS warehouse_name
                FROM order_shipments os
                JOIN warehouses w ON w.id = os.warehouse_id
                WHERE os.order_id = %s
                ORDER BY os.id
            ''', (order['id'],))
            shipments = []
            for sh in cursor.fetchall():
                sh = dict(sh)
                if sh.get('shipping_provider') and sh.get('tracking_number'):
                    tmpl = provider_tracking_map.get(sh['shipping_provider'], '')
                    if tmpl:
                        if '{tracking}' in tmpl:
                            sh['tracking_url'] = tmpl.replace('{tracking}', sh['tracking_number'])
                        else:
                            sh['tracking_url'] = tmpl + sh['tracking_number']
                shipments.append(sh)
            order['shipments'] = shipments

        return jsonify(orders), 200

    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@orders_bp.route('/api/admin/orders/<int:order_id>/mark-delivered', methods=['POST'])
@admin_required
def mark_order_delivered(order_id):
    """Mark order as delivered"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, status, user_id, order_number, final_amount FROM orders WHERE id = %s', (order_id,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        
        if order['status'] != 'shipped':
            return jsonify({'error': 'คำสั่งซื้อนี้ยังไม่ได้จัดส่ง'}), 400
        
        cursor.execute('''
            UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status != 'delivered'
        ''', (order_id,))
        
        if cursor.rowcount > 0 and order['final_amount']:
            cursor.execute('UPDATE users SET total_purchases = COALESCE(total_purchases,0) + %s WHERE id = %s',
                           (order['final_amount'], order['user_id']))
            cursor.execute('''SELECT u.id, u.reseller_tier_id, u.tier_manual_override,
                (SELECT id FROM reseller_tiers WHERE upgrade_threshold <= u.total_purchases
                 AND is_manual_only=FALSE ORDER BY level_rank DESC LIMIT 1) as new_tier_id
                FROM users u WHERE u.id = %s''', (order['user_id'],))
            u = cursor.fetchone()
            if u and u['new_tier_id'] and not u['tier_manual_override'] and u['new_tier_id'] != u['reseller_tier_id']:
                cursor.execute('UPDATE users SET reseller_tier_id=%s WHERE id=%s', (u['new_tier_id'], u['id']))
                cursor.execute('SELECT name FROM reseller_tiers WHERE id=%s', (u['new_tier_id'],))
                t = cursor.fetchone()
                if t:
                    create_notification(u['id'], 'ยินดีด้วย! คุณได้รับการอัพเกรดระดับ',
                        f'คุณได้รับการอัพเกรดเป็นระดับ {t["name"]}', 'success', 'tier', u['new_tier_id'])
        
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
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'delivered', order_id=order_id)
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'อัปเดตสถานะสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/mark-failed-delivery', methods=['POST'])
@admin_required
def mark_order_failed_delivery(order_id):
    """Mark order as failed delivery (returned)"""
    conn = None
    cursor = None
    try:
        admin_id = session.get('user_id')
        data = request.get_json(silent=True) or {}
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
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'failed_delivery', f'เหตุผล: {reason}' if reason else '', order_id=order_id)
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'อัปเดตสถานะสำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/orders/<int:order_id>/reship', methods=['POST'])
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
            send_order_status_chat(order['user_id'], order['order_number'] or f'#{order_id}', 'reship', order_id=order_id)
        except Exception as chat_err:
            print(f"Chat notification error: {chat_err}")
        
        return jsonify({'message': 'เริ่มจัดส่งใหม่สำเร็จ'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
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

@orders_bp.route('/api/mto/products', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/products/<int:product_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/quotation-requests', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/quotation-requests', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/quotations', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/quotations/<int:quote_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/orders', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/orders/<int:order_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/mto/orders/<int:order_id>/pay', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==========================================
# Admin MTO Management APIs
# ==========================================

@orders_bp.route('/api/admin/mto/products', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/products', methods=['POST'])
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
            INSERT INTO products (name, parent_sku, brand_id, description, product_type, production_days, deposit_percent, status, size_chart_image_url)
            VALUES (%s, %s, %s, %s, 'made_to_order', %s, %s, %s, %s)
            RETURNING id
        ''', (name, parent_sku, brand_id, description, production_days, deposit_percent, status, size_chart_image_url))
        product_id = cursor.fetchone()['id']

        if category_id:
            cursor.execute('SELECT id FROM categories WHERE id = %s', (category_id,))
            if cursor.fetchone():
                cursor.execute('''
                    INSERT INTO product_categories (product_id, category_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                ''', (product_id, category_id))

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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/products/<int:product_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/products/<int:product_id>', methods=['PUT'])
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
        
        for field in ['name', 'description', 'production_days', 'deposit_percent', 'status', 'brand_id', 'parent_sku', 'size_chart_image_url']:
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

        if 'category_id' in data:
            category_id = data['category_id']
            cursor.execute('DELETE FROM product_categories WHERE product_id = %s', (product_id,))
            if category_id:
                cursor.execute('SELECT id FROM categories WHERE id = %s', (category_id,))
                if cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO product_categories (product_id, category_id)
                        VALUES (%s, %s) ON CONFLICT DO NOTHING
                    ''', (product_id, category_id))
        
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/products/<int:product_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/quotation-requests', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/quotation-requests/<int:request_id>', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/quotations', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/quotations', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/quotations/<int:quote_id>/send', methods=['POST'])
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
        return handle_error(e)
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

@orders_bp.route('/api/admin/mto/orders', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/payments', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@orders_bp.route('/api/admin/mto/payments/<int:payment_id>/confirm', methods=['POST'])
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
        return handle_error(e)
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

@orders_bp.route('/api/admin/mto/orders/<int:order_id>/update-status', methods=['POST'])
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
        return handle_error(e)
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

@orders_bp.route('/api/admin/mto/stats', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

