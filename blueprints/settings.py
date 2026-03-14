from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, make_response
from database import get_db
from utils import login_required, admin_required, handle_error
from blueprints.push_utils import send_push_notification, create_notification
import psycopg2.extras
import psycopg2
import json, os, io
from datetime import datetime

settings_bp = Blueprint('settings', __name__)

# ==================== SALES CHANNELS API ====================

@settings_bp.route('/api/sales-channels', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/sales-channels', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/sales-channels/<int:channel_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/sales-channels/<int:channel_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PROMPTPAY SETTINGS API ====================

@settings_bp.route('/api/promptpay-settings', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/promptpay-settings', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/promptpay-qr', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SHIPPING SETTINGS API ====================

@settings_bp.route('/api/shipping-rates', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-rates', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-rates/<int:rate_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-rates/<int:rate_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-promotions', methods=['GET'])
@login_required
def get_shipping_promotions():
    """Get all shipping promotions with their associated brands"""
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
        
        # Load brand associations for each promo
        if promos:
            promo_ids = [p['id'] for p in promos]
            cursor.execute('''
                SELECT spb.promo_id, spb.brand_id, b.name as brand_name
                FROM shipping_promotion_brands spb
                JOIN brands b ON b.id = spb.brand_id
                WHERE spb.promo_id = ANY(%s)
            ''', (promo_ids,))
            brand_rows = cursor.fetchall()
            
            brands_by_promo = {}
            for row in brand_rows:
                pid = row['promo_id']
                if pid not in brands_by_promo:
                    brands_by_promo[pid] = []
                brands_by_promo[pid].append({'id': row['brand_id'], 'name': row['brand_name']})
            
            for p in promos:
                p['brands'] = brands_by_promo.get(p['id'], [])
        
        return jsonify(promos), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-promotions', methods=['POST'])
@admin_required
def create_shipping_promotion():
    """Create a new shipping promotion"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        brand_ids = data.get('brand_ids', [])
        
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
        promo_id = promo['id']
        
        if brand_ids:
            for bid in brand_ids:
                cursor.execute('''
                    INSERT INTO shipping_promotion_brands (promo_id, brand_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                ''', (promo_id, bid))
        
        conn.commit()
        promo['brands'] = []
        return jsonify(promo), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-promotions/<int:promo_id>', methods=['PUT'])
@admin_required
def update_shipping_promotion(promo_id):
    """Update a shipping promotion"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        brand_ids = data.get('brand_ids', [])
        
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
        
        # Replace brand associations
        cursor.execute('DELETE FROM shipping_promotion_brands WHERE promo_id = %s', (promo_id,))
        if brand_ids:
            for bid in brand_ids:
                cursor.execute('''
                    INSERT INTO shipping_promotion_brands (promo_id, brand_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                ''', (promo_id, bid))
        
        conn.commit()
        return jsonify(dict(promo)), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-promotions/<int:promo_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== SHIPPING PROVIDERS API ====================

@settings_bp.route('/api/shipping-providers', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-providers', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-providers/<int:provider_id>', methods=['PUT'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/shipping-providers/<int:provider_id>', methods=['DELETE'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/calculate-shipping', methods=['POST'])
@login_required
def calculate_shipping():
    """Calculate shipping cost based on weight and apply promotions"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        total_weight = data.get('total_weight', 0)
        order_total = data.get('order_total', 0)
        brand_ids = data.get('brand_ids', [])  # brand IDs from cart items
        
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
        
        # Find best applicable promotion:
        # - If promo has no brands → applies to all orders
        # - If promo has brands → only applies if cart contains items from those brands
        if brand_ids:
            cursor.execute('''
                SELECT sp.id, sp.promo_type, sp.min_order_value, sp.discount_amount, sp.name
                FROM shipping_promotions sp
                WHERE sp.is_active = TRUE
                  AND sp.min_order_value <= %s
                  AND (sp.start_date IS NULL OR sp.start_date <= CURRENT_TIMESTAMP)
                  AND (sp.end_date IS NULL OR sp.end_date >= CURRENT_TIMESTAMP)
                  AND (
                      NOT EXISTS (SELECT 1 FROM shipping_promotion_brands spb WHERE spb.promo_id = sp.id)
                      OR EXISTS (
                          SELECT 1 FROM shipping_promotion_brands spb
                          WHERE spb.promo_id = sp.id AND spb.brand_id = ANY(%s)
                      )
                  )
                ORDER BY sp.min_order_value DESC
                LIMIT 1
            ''', (order_total, brand_ids))
        else:
            cursor.execute('''
                SELECT id, promo_type, min_order_value, discount_amount, name
                FROM shipping_promotions
                WHERE is_active = TRUE
                  AND min_order_value <= %s
                  AND (start_date IS NULL OR start_date <= CURRENT_TIMESTAMP)
                  AND (end_date IS NULL OR end_date >= CURRENT_TIMESTAMP)
                  AND NOT EXISTS (
                      SELECT 1 FROM shipping_promotion_brands spb WHERE spb.promo_id = shipping_promotions.id
                  )
                ORDER BY min_order_value DESC
                LIMIT 1
            ''', (order_total,))
        
        promo = cursor.fetchone()
        promo_applied = None
        
        if promo:
            if promo['promo_type'] == 'free_shipping':
                shipping_cost = 0
                promo_applied = promo['name']
            elif promo['promo_type'] in ('discount_amount', 'discount'):
                discount = float(promo['discount_amount'])
                shipping_cost = max(0, shipping_cost - discount)
                promo_applied = promo['name']
            elif promo['promo_type'] == 'discount_percent':
                discount = float(promo['discount_amount'])
                shipping_cost = max(0, shipping_cost * (1 - discount / 100))
                promo_applied = promo['name']
        
        return jsonify({
            'shipping_cost': shipping_cost,
            'original_shipping': original_shipping,
            'promo_applied': promo_applied,
            'total_weight': total_weight
        }), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== ORDER NUMBER SETTINGS API ====================

@settings_bp.route('/api/order-number-settings', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/order-number-settings', methods=['POST'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== NOTIFICATIONS API ====================

@settings_bp.route('/api/notifications', methods=['GET'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/notifications/<int:notification_id>/read', methods=['PATCH'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@settings_bp.route('/api/notifications/read-all', methods=['PATCH'])
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
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Helper function to create notification
from blueprints.push_utils import create_notification, send_push_notification, send_push_to_admins, notify_admins_guest_lead


# ==================== ADMIN PAGES ====================

@settings_bp.route('/admin/settings')
@admin_required
def settings_page():
    """Admin settings page"""
    return render_template('settings.html')

@settings_bp.route('/admin/orders')
@admin_required
def admin_orders_page():
    """Admin orders management page"""
    return render_template('admin_orders.html')

@settings_bp.route('/admin/sales-channels')
@admin_required
def sales_channels_page():
    """Sales channels management page"""
    return render_template('sales_channels.html')

