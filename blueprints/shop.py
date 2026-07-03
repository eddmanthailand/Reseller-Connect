"""Retail (B2C) storefront for walk-in customers (e.g. nursing students).

Guest checkout — no login required. Orders are attached to a dedicated retail
system user to satisfy the orders.user_id FK, and marked with order_type='retail'.
Pricing uses the Bronze (entry) reseller tier discount, shown as full price + discount.
Payment: PromptPay QR + slip with Thunder auto-verify (reuses orders.py helpers).
"""
from flask import Blueprint, request, jsonify, render_template
from database import get_db
from utils import handle_error
from blueprints.orders import (
    generate_promptpay_payload, call_thunder_verify, generate_order_number
)
from blueprints.push_utils import send_push_to_admins, create_notification
from blueprints.mail_utils import send_order_notification_to_admin
import psycopg2.extras
import psycopg2
import json, os, io, base64, secrets, threading

shop_bp = Blueprint('shop', __name__)

RETAIL_USERNAME = 'retail_guest_system'


def _get_retail_user_id(cursor):
    """Return the id of the dedicated retail system user."""
    cursor.execute("SELECT id FROM users WHERE username = %s", (RETAIL_USERNAME,))
    row = cursor.fetchone()
    return row['id'] if row else None


def _get_bronze_tier_id(cursor):
    """Bronze = entry tier = lowest level_rank."""
    cursor.execute("SELECT id FROM reseller_tiers ORDER BY level_rank ASC LIMIT 1")
    row = cursor.fetchone()
    return row['id'] if row else None


def _calc_shipping_fee(cursor, total_weight_g):
    """Match total weight (grams) against shipping_weight_rates.

    Mirrors the existing /api/calculate-shipping behavior: charge the matched
    bracket's rate, or 0 when no bracket matches (no heaviest-bracket fallback,
    which would silently overcharge on gapped/above-zero weight ranges).
    """
    cursor.execute('''
        SELECT rate FROM shipping_weight_rates
        WHERE is_active = TRUE
          AND min_weight <= %s
          AND (max_weight IS NULL OR max_weight >= %s)
        ORDER BY min_weight DESC
        LIMIT 1
    ''', (total_weight_g, total_weight_g))
    row = cursor.fetchone()
    return float(row['rate']) if row else 0.0


# ==================== PAGE ROUTES ====================

@shop_bp.route('/shop')
def shop_page():
    """Public retail storefront."""
    return render_template('shop.html')


@shop_bp.route('/shop/track')
def shop_track_page():
    """Guest order tracking page."""
    return render_template('shop_track.html')


# ==================== PRODUCT APIs (Bronze pricing) ====================

@shop_bp.route('/api/shop/products', methods=['GET'])
def shop_products():
    """All active products with Bronze-tier pricing (full price + discount)."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        bronze_id = _get_bronze_tier_id(cursor)

        brand_id = request.args.get('brand')
        category_id = request.args.get('category')
        featured_only = request.args.get('featured') == '1'
        search = (request.args.get('search') or '').strip()

        query = '''
            SELECT p.id, p.name, p.is_featured,
                   b.id as brand_id, b.name as brand_name,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                   (SELECT MIN(s.price) FROM skus s WHERE s.product_id = p.id) as min_price,
                   (SELECT MAX(s.price) FROM skus s WHERE s.product_id = p.id) as max_price,
                   COALESCE((SELECT SUM(s.stock) FROM skus s WHERE s.product_id = p.id), 0) as total_stock,
                   (SELECT STRING_AGG(c.name, ', ') FROM product_categories pc JOIN categories c ON c.id = pc.category_id WHERE pc.product_id = p.id) as category_names,
                   COALESCE(ptp.discount_percent, 0) as discount_percent
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            LEFT JOIN product_tier_pricing ptp ON ptp.product_id = p.id AND ptp.tier_id = %s
            WHERE p.status = 'active'
        '''
        params = [bronze_id]

        if brand_id:
            query += ' AND p.brand_id = %s'
            params.append(int(brand_id))
        if category_id:
            query += ' AND EXISTS (SELECT 1 FROM product_categories pc WHERE pc.product_id = p.id AND pc.category_id = %s)'
            params.append(int(category_id))
        if featured_only:
            query += ' AND p.is_featured = TRUE'
        if search:
            query += ' AND (p.name ILIKE %s OR b.name ILIKE %s)'
            params.extend([f'%{search}%', f'%{search}%'])

        query += ' ORDER BY p.is_featured DESC, p.created_at DESC'

        cursor.execute(query, params)
        products = []
        for r in cursor.fetchall():
            d = dict(r)
            d['min_price'] = float(d['min_price']) if d.get('min_price') is not None else 0
            d['max_price'] = float(d['max_price']) if d.get('max_price') is not None else 0
            d['total_stock'] = int(d['total_stock']) if d.get('total_stock') is not None else 0
            disc = float(d['discount_percent'] or 0)
            d['discount_percent'] = disc
            d['discounted_min_price'] = round(d['min_price'] * (1 - disc / 100), 2)
            d['discounted_max_price'] = round(d['max_price'] * (1 - disc / 100), 2)
            products.append(d)

        return jsonify({'products': products}), 200
    except Exception as e:
        print(f"[SHOP] products error: {e}")
        return jsonify({'products': [], 'error': 'ไม่สามารถโหลดสินค้าได้'}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@shop_bp.route('/api/shop/product/<int:product_id>/skus', methods=['GET'])
def shop_product_skus(product_id):
    """SKU variants for a product with Bronze discount."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        bronze_id = _get_bronze_tier_id(cursor)

        cursor.execute('''
            SELECT p.id, p.name, p.product_type, p.size_chart_image_url,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                   COALESCE((SELECT discount_percent FROM product_tier_pricing WHERE product_id = p.id AND tier_id = %s), 0) as discount_percent
            FROM products p
            WHERE p.id = %s AND p.status = 'active'
        ''', (bronze_id, product_id))
        product = cursor.fetchone()
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        cursor.execute('''
            SELECT s.id, s.sku_code, s.price, s.stock,
                   COALESCE(json_object_agg(o.name, ov.value) FILTER (WHERE o.id IS NOT NULL), '{}'::json) as options
            FROM skus s
            LEFT JOIN sku_values_map svm ON svm.sku_id = s.id
            LEFT JOIN option_values ov ON ov.id = svm.option_value_id
            LEFT JOIN options o ON o.id = ov.option_id
            WHERE s.product_id = %s
            GROUP BY s.id, s.sku_code, s.price, s.stock
            ORDER BY s.price ASC, s.id ASC
        ''', (product_id,))
        disc = float(product['discount_percent'] or 0)
        skus = []
        for r in cursor.fetchall():
            d = dict(r)
            price = float(d['price']) if d.get('price') else 0
            d['price'] = price
            d['discounted_price'] = round(price * (1 - disc / 100), 2)
            d['stock'] = int(d['stock']) if d.get('stock') else 0
            if d.get('options') is None:
                d['options'] = {}
            skus.append(d)

        p = dict(product)
        p['discount_percent'] = disc

        cursor.execute('''
            SELECT scg.id, scg.name, scg.columns, scg.rows
            FROM size_chart_groups scg
            JOIN products pr ON pr.size_chart_group_id = scg.id
            WHERE pr.id = %s
        ''', (product_id,))
        sc = cursor.fetchone()
        if sc:
            p['size_chart_group'] = {
                'id': sc['id'], 'name': sc['name'],
                'columns': sc['columns'] if isinstance(sc['columns'], list) else json.loads(sc['columns'] or '[]'),
                'rows': sc['rows'] if isinstance(sc['rows'], list) else json.loads(sc['rows'] or '[]'),
            }
        else:
            p['size_chart_group'] = None

        return jsonify({'product': p, 'skus': skus}), 200
    except Exception as e:
        print(f"[SHOP] skus error: {e}")
        return jsonify({'error': 'ไม่สามารถโหลดข้อมูลสินค้าได้'}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== GUEST ORDER CREATION ====================

@shop_bp.route('/api/shop/order', methods=['POST'])
def shop_create_order():
    """Create a guest retail order (no login). Body:
    { items:[{sku_id, quantity}], name, phone, email, address,
      province, district, subdistrict, postal, notes }
    Returns order summary + guest_token.
    """
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        items_in = data.get('items') or []
        if not items_in:
            return jsonify({'error': 'ตะกร้าว่างเปล่า'}), 400

        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        email = (data.get('email') or '').strip()
        address = (data.get('address') or '').strip()
        province = (data.get('province') or '').strip()
        district = (data.get('district') or '').strip()
        subdistrict = (data.get('subdistrict') or '').strip()
        postal = (data.get('postal') or '').strip()
        notes = (data.get('notes') or '').strip()

        if not name or not phone or not address or not email:
            return jsonify({'error': 'กรุณากรอกชื่อ เบอร์โทร อีเมล และที่อยู่ให้ครบ'}), 400

        # normalize + validate item quantities
        req_map = {}
        for it in items_in:
            try:
                sid = int(it.get('sku_id'))
                qty = int(it.get('quantity'))
            except (TypeError, ValueError):
                return jsonify({'error': 'ข้อมูลสินค้าไม่ถูกต้อง'}), 400
            if qty <= 0:
                continue
            req_map[sid] = req_map.get(sid, 0) + qty
        if not req_map:
            return jsonify({'error': 'ตะกร้าว่างเปล่า'}), 400

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        retail_user_id = _get_retail_user_id(cursor)
        bronze_id = _get_bronze_tier_id(cursor)
        if not retail_user_id:
            return jsonify({'error': 'ระบบขายปลีกยังไม่พร้อมใช้งาน'}), 503

        sku_ids = list(req_map.keys())

        # Fetch sku + product + Bronze discount + weight
        cursor.execute('''
            SELECT s.id as sku_id, s.sku_code, s.price, s.product_id,
                   p.name as product_name, p.brand_id, p.weight,
                   COALESCE((SELECT discount_percent FROM product_tier_pricing WHERE product_id = p.id AND tier_id = %s), 0) as discount_percent
            FROM skus s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = ANY(%s) AND p.status = 'active'
        ''', (bronze_id, sku_ids))
        sku_rows = {r['sku_id']: r for r in cursor.fetchall()}
        if len(sku_rows) != len(sku_ids):
            return jsonify({'error': 'พบสินค้าบางรายการไม่พร้อมจำหน่าย'}), 400

        # Lock warehouse stock rows
        cursor.execute('''
            SELECT sws.sku_id, sws.warehouse_id, sws.stock
            FROM sku_warehouse_stock sws
            JOIN warehouses w ON w.id = sws.warehouse_id
            WHERE sws.sku_id = ANY(%s) AND sws.stock > 0 AND w.is_active = TRUE
            ORDER BY sws.warehouse_id, sws.sku_id
            FOR UPDATE OF sws
        ''', (sku_ids,))
        sku_wh_map = {}
        for ws in cursor.fetchall():
            sku_wh_map.setdefault(ws['sku_id'], []).append(
                {'warehouse_id': ws['warehouse_id'], 'stock': ws['stock']})

        # stock check + totals
        total_amount = 0.0
        total_discount = 0.0
        total_weight = 0.0
        for sid, qty in req_map.items():
            row = sku_rows[sid]
            avail = sum(w['stock'] for w in sku_wh_map.get(sid, []))
            if avail < qty:
                return jsonify({'error': f'สินค้า {row["product_name"]} ({row["sku_code"]}) สต็อกไม่พอ เหลือ {avail} ชิ้น'}), 400
            unit_price = float(row['price'])
            disc_pct = float(row['discount_percent'] or 0)
            discounted = unit_price * (1 - disc_pct / 100)
            total_amount += unit_price * qty
            total_discount += (unit_price - discounted) * qty
            total_weight += float(row['weight'] or 0) * qty

        item_total = total_amount - total_discount
        shipping_fee = _calc_shipping_fee(cursor, total_weight)
        final_amount = round(item_total + shipping_fee, 2)

        # default online channel
        cursor.execute("SELECT id FROM sales_channels WHERE name = 'ระบบออนไลน์' LIMIT 1")
        ch = cursor.fetchone()
        channel_id = ch['id'] if ch else None

        guest_token = secrets.token_urlsafe(24)
        order_number = generate_order_number(cursor)

        cursor.execute('''
            INSERT INTO orders (order_number, user_id, channel_id, status, payment_method,
                                total_amount, discount_amount, shipping_fee, final_amount, notes,
                                order_type, guest_email, guest_token, tier_id,
                                shipping_name, shipping_phone, shipping_address,
                                shipping_province, shipping_district, shipping_subdistrict, shipping_postal)
            VALUES (%s,%s,%s,'pending_payment','promptpay',%s,%s,%s,%s,%s,'retail',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id, order_number, final_amount, created_at
        ''', (order_number, retail_user_id, channel_id,
              round(total_amount, 2), round(total_discount, 2), shipping_fee, final_amount, notes,
              email, guest_token, bronze_id,
              name, phone, address, province, district, subdistrict, postal))
        order = dict(cursor.fetchone())
        order_id = order['id']

        # order items
        order_item_map = {}
        for sid, qty in req_map.items():
            row = sku_rows[sid]
            unit_price = float(row['price'])
            disc_pct = float(row['discount_percent'] or 0)
            discounted = round(unit_price * (1 - disc_pct / 100), 2)
            discount_amount = round(unit_price * disc_pct / 100, 2)
            subtotal = round(discounted * qty, 2)
            cursor.execute('''
                INSERT INTO order_items (order_id, sku_id, product_name, sku_code, quantity,
                                         unit_price, tier_discount_percent, discount_amount, subtotal)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            ''', (order_id, sid, row['product_name'], row['sku_code'], qty,
                  unit_price, disc_pct, discount_amount, subtotal))
            order_item_map[sid] = cursor.fetchone()['id']

        # allocate to warehouses + deduct
        warehouse_shipments = {}
        stock_deductions = []
        for sid, qty in req_map.items():
            remaining = qty
            for wh in sku_wh_map.get(sid, []):
                if remaining <= 0:
                    break
                alloc = min(remaining, wh['stock'])
                if alloc > 0:
                    warehouse_shipments.setdefault(wh['warehouse_id'], []).append(
                        {'order_item_id': order_item_map[sid], 'quantity': alloc})
                    stock_deductions.append((sid, wh['warehouse_id'], alloc))
                    wh['stock'] -= alloc
                    remaining -= alloc

        for wh_id, ship_items in warehouse_shipments.items():
            cursor.execute('''
                INSERT INTO order_shipments (order_id, warehouse_id, status)
                VALUES (%s,%s,'pending') RETURNING id
            ''', (order_id, wh_id))
            shipment_id = cursor.fetchone()['id']
            for si in ship_items:
                cursor.execute('''
                    INSERT INTO order_shipment_items (shipment_id, order_item_id, quantity)
                    VALUES (%s,%s,%s)
                ''', (shipment_id, si['order_item_id'], si['quantity']))

        for sid, wh_id, qty in stock_deductions:
            cursor.execute('''
                UPDATE sku_warehouse_stock SET stock = stock - %s
                WHERE sku_id = %s AND warehouse_id = %s AND stock >= %s
            ''', (qty, sid, wh_id, qty))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่'}), 400

        for sid, qty in req_map.items():
            cursor.execute('UPDATE skus SET stock = stock - %s WHERE id = %s AND stock >= %s', (qty, sid, qty))
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'error': 'สต็อกสินค้าไม่เพียงพอ กรุณาลองใหม่'}), 400

        conn.commit()

        # notify admins (best-effort)
        def _notify():
            try:
                send_order_notification_to_admin(order['order_number'], f'ขายปลีก: {name}',
                                                  float(order['final_amount']), len(req_map))
            except Exception:
                pass
            try:
                fmt = f"{float(order['final_amount']):,.0f}"
                send_push_to_admins('🛍️ ออเดอร์ขายปลีกใหม่!',
                                    f'{name} สั่งซื้อ {order["order_number"]} (฿{fmt})',
                                    url='/admin#orders', tag=f'order-{order_id}')
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True).start()

        return jsonify({
            'message': 'สร้างคำสั่งซื้อสำเร็จ',
            'order': {
                'id': order_id,
                'order_number': order['order_number'],
                'final_amount': float(order['final_amount']),
                'guest_token': guest_token,
            }
        }), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== GUEST ORDER LOOKUP / TRACKING ====================

def _fetch_guest_order(cursor, token):
    cursor.execute('''
        SELECT o.id, o.order_number, o.status, o.final_amount, o.total_amount, o.discount_amount,
               o.shipping_fee, o.guest_email, o.guest_token,
               o.shipping_name, o.shipping_phone, o.shipping_address, o.shipping_province,
               o.shipping_district, o.shipping_subdistrict, o.shipping_postal, o.created_at,
               (SELECT os.tracking_number FROM order_shipments os
                WHERE os.order_id = o.id AND os.tracking_number IS NOT NULL
                ORDER BY os.id LIMIT 1) as tracking_number
        FROM orders o WHERE o.guest_token = %s AND o.order_type = 'retail'
    ''', (token,))
    return cursor.fetchone()


@shop_bp.route('/api/shop/order/<token>', methods=['GET'])
def shop_get_order(token):
    """Fetch a guest order by its token (status page, QR, slip flow)."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        order = _fetch_guest_order(cursor, token)
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        o = dict(order)
        for k in ('final_amount', 'total_amount', 'discount_amount', 'shipping_fee'):
            o[k] = float(o[k]) if o.get(k) is not None else 0
        cursor.execute('''
            SELECT product_name, sku_code, quantity, unit_price, tier_discount_percent, subtotal
            FROM order_items WHERE order_id = %s ORDER BY id
        ''', (order['id'],))
        items = []
        for r in cursor.fetchall():
            d = dict(r)
            d['unit_price'] = float(d['unit_price']) if d.get('unit_price') else 0
            d['subtotal'] = float(d['subtotal']) if d.get('subtotal') else 0
            d['tier_discount_percent'] = float(d['tier_discount_percent'] or 0)
            items.append(d)
        o['items'] = items
        return jsonify({'order': o}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@shop_bp.route('/api/shop/track', methods=['POST'])
def shop_track():
    """Look up an order by order_number + email (returns token for status view)."""
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        order_number = (data.get('order_number') or '').strip()
        email = (data.get('email') or '').strip().lower()
        if not order_number or not email:
            return jsonify({'error': 'กรุณากรอกเลขคำสั่งซื้อและอีเมล'}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT guest_token FROM orders
            WHERE order_number = %s AND LOWER(guest_email) = %s AND order_type = 'retail'
        ''', (order_number, email))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อที่ตรงกับข้อมูล'}), 404
        return jsonify({'guest_token': row['guest_token']}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== GUEST PROMPTPAY QR ====================

@shop_bp.route('/api/shop/order/<token>/promptpay-qr', methods=['GET'])
def shop_promptpay_qr(token):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        order = _fetch_guest_order(cursor, token)
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404

        cursor.execute("SELECT account_number, account_name FROM promptpay_settings WHERE is_active = TRUE LIMIT 1")
        pp = cursor.fetchone()
        if pp and pp.get('account_number'):
            pp_number, pp_name = pp['account_number'], pp.get('account_name', '')
        else:
            pp_number, pp_name = os.environ.get('PROMPTPAY_NUMBER', ''), ''
        if not pp_number:
            return jsonify({'error': 'ระบบ PromptPay ยังไม่ได้ตั้งค่า'}), 503

        amount = float(order['final_amount'])
        try:
            payload = generate_promptpay_payload(pp_number, amount)
        except ValueError as e:
            return jsonify({'error': f'PromptPay config ผิดพลาด: {e}'}), 500

        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_data_url = f'data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}'

        return jsonify({
            'qr_data_url': qr_data_url, 'amount': amount,
            'order_number': order['order_number'],
            'promptpay_number': pp_number, 'account_name': pp_name,
        })
    except Exception as e:
        print(f'[SHOP QR] {e}')
        return jsonify({'error': 'ไม่สามารถสร้าง QR Code ได้'}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== GUEST SLIP UPLOAD (Thunder verify) ====================

@shop_bp.route('/api/shop/order/<token>/payment-slip', methods=['POST'])
def shop_upload_slip(token):
    conn = None
    cursor = None
    try:
        if not (request.content_type and 'multipart/form-data' in request.content_type):
            return jsonify({'error': 'กรุณาแนบไฟล์รูปสลิป'}), 400
        slip_file = request.files.get('slip_image')
        if not slip_file or not slip_file.filename:
            return jsonify({'error': 'กรุณาเลือกรูปสลิป'}), 400

        allowed_ext = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'}
        ext = slip_file.filename.rsplit('.', 1)[-1].lower() if '.' in slip_file.filename else 'jpg'
        if ext not in allowed_ext:
            return jsonify({'error': 'ไฟล์ไม่รองรับ กรุณาอัปโหลดรูปภาพ'}), 400
        file_data = slip_file.read()
        if len(file_data) > 5 * 1024 * 1024:
            return jsonify({'error': 'ไฟล์ใหญ่เกิน 5MB กรุณาลดขนาดรูป'}), 400
        mime_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'gif': 'image/gif', 'webp': 'image/webp', 'heic': 'image/heic'}
        mime_type = mime_map.get(ext, 'image/jpeg')
        slip_image_url = f'data:{mime_type};base64,{base64.b64encode(file_data).decode()}'

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        order = _fetch_guest_order(cursor, token)
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['status'] not in ('pending_payment', 'rejected'):
            return jsonify({'error': 'ไม่สามารถอัปโหลดสลิปสำหรับสถานะนี้ได้'}), 400

        order_id = order['id']

        # Abuse guard: cap slips per order to prevent public-endpoint storage DoS
        cursor.execute('SELECT COUNT(*) AS c FROM payment_slips WHERE order_id = %s', (order_id,))
        if (cursor.fetchone()['c'] or 0) >= 10:
            return jsonify({'error': 'อัปโหลดสลิปเกินจำนวนที่กำหนด กรุณาติดต่อแอดมิน'}), 429
        expected_thb = float(order['final_amount'])

        thunder = call_thunder_verify(file_data, mime_type, expected_thb)
        print(f"[SHOP THUNDER] order={order_id} ok={thunder['ok']} manual={thunder.get('pending_manual')} reason={thunder.get('reason')}")

        if thunder['ok']:
            slip_status, new_status, auto_verified = 'approved', 'preparing', True
        elif thunder.get('pending_manual'):
            slip_status, new_status, auto_verified = 'pending', 'under_review', False
        else:
            slip_status, new_status, auto_verified = 'rejected', order['status'], False
        thunder_json = json.dumps(thunder['thunder_raw'], ensure_ascii=False)

        cursor.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status, auto_verified, thunder_response)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        ''', (order_id, slip_image_url, expected_thb, slip_status, auto_verified, thunder_json))
        slip_id = cursor.fetchone()['id']

        if new_status != order['status']:
            cursor.execute('UPDATE orders SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s',
                           (new_status, order_id))
            if new_status == 'preparing':
                cursor.execute('UPDATE payment_slips SET verified_at = CURRENT_TIMESTAMP WHERE id = %s', (slip_id,))
        conn.commit()

        if not thunder['ok'] and not thunder.get('pending_manual'):
            return jsonify({'error': thunder['reason'], 'thunder_rejected': True}), 422

        # notify admins for manual review
        if not auto_verified:
            def _notify():
                try:
                    cursor2 = None
                    conn2 = get_db()
                    cursor2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    cursor2.execute("SELECT id FROM users WHERE role_id IN (SELECT id FROM roles WHERE name IN ('Super Admin','Assistant Admin'))")
                    for a in cursor2.fetchall():
                        try:
                            create_notification(a['id'], '🧾 สลิปขายปลีกใหม่',
                                f'ลูกค้าขายปลีกอัปโหลดสลิป {order["order_number"]}', 'payment', 'order', order_id)
                        except Exception:
                            pass
                    cursor2.close(); conn2.close()
                except Exception as e:
                    print(f'[SHOP SLIP] notify err: {e}')
            threading.Thread(target=_notify, daemon=True).start()

        if auto_verified:
            return jsonify({'message': '✅ ตรวจสอบสลิปสำเร็จ! คำสั่งซื้อได้รับการยืนยันแล้ว',
                            'auto_verified': True, 'new_status': 'preparing'}), 200
        return jsonify({'message': 'อัปโหลดสลิปสำเร็จ รอแอดมินตรวจสอบ',
                        'auto_verified': False, 'pending_manual': True}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        print(f'[SHOP SLIP] error: {e}')
        return jsonify({'error': 'เกิดข้อผิดพลาดในการอัปโหลดสลิป กรุณาลองใหม่'}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
