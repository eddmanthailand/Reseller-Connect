from flask import Blueprint, request, jsonify, session
from database import get_db
from utils import login_required, admin_required, handle_error
import psycopg2.extras
import psycopg2
import json, os
from datetime import datetime
from blueprints.bot_cache import bot_cache_invalidate

marketing_bp = Blueprint('marketing', __name__)

# ==================== MARKETING MODULE ====================

def _calc_best_promotion(cursor, cart_total, cart_brand_ids, cart_category_ids, user_tier_rank, cart_qty=0, user_id=None):
    """
    Layer 2: Find the single best auto-promotion eligible for this cart.
    Returns: (promotion_row, discount_amount) or (None, 0)
    """
    now_sql = 'CURRENT_TIMESTAMP'
    cursor.execute(f'''
        SELECT p.*, rt.level_rank as min_tier_rank
        FROM promotions p
        LEFT JOIN reseller_tiers rt ON rt.id = p.min_tier_id
        WHERE p.is_active = TRUE
          AND (p.start_date IS NULL OR p.start_date <= {now_sql})
          AND (p.end_date IS NULL OR p.end_date >= {now_sql})
        ORDER BY p.priority DESC, p.id
    ''')
    promotions = cursor.fetchall()

    best_promo = None
    best_discount = 0

    for promo in promotions:
        # Tier check
        if promo['min_tier_rank'] and user_tier_rank < promo['min_tier_rank']:
            continue
        # Minimum spend check
        if promo['condition_min_spend'] and cart_total < float(promo['condition_min_spend']):
            continue
        # Minimum quantity check
        if promo['condition_min_qty'] and int(promo['condition_min_qty']) > 0 and cart_qty < int(promo['condition_min_qty']):
            continue
        # Brand/category targeting
        if promo['target_brand_id'] and promo['target_brand_id'] not in cart_brand_ids:
            continue
        if promo['target_category_id'] and promo['target_category_id'] not in cart_category_ids:
            continue
        # Once-per-user check
        if promo.get('once_per_user') and user_id:
            cursor.execute('''
                SELECT 1 FROM orders
                WHERE user_id = %s AND promotion_id = %s
                  AND status NOT IN ('cancelled', 'rejected', 'failed_delivery')
                LIMIT 1
            ''', (user_id, promo['id']))
            if cursor.fetchone():
                continue

        # Calculate discount value
        reward_type = promo['reward_type']
        reward_value = float(promo['reward_value'] or 0)
        if reward_type == 'discount_percent':
            discount = round(cart_total * reward_value / 100, 2)
        elif reward_type == 'discount_fixed':
            discount = min(reward_value, cart_total)
        elif reward_type == 'free_item':
            discount = 0  # GWP: value tracked separately
        else:
            discount = 0

        if discount > best_discount or (discount == best_discount and best_promo is None):
            best_discount = discount
            best_promo = promo

    return (dict(best_promo) if best_promo else None, best_discount)


def _enrich_applies_to_names(cursor, rows):
    """Add applies_to_names list to each coupon row based on applies_to and applies_to_ids."""
    brand_ids_needed = set()
    product_ids_needed = set()
    for r in rows:
        ids = list(r.get('applies_to_ids') or [])
        if r.get('applies_to') == 'brand' and ids:
            brand_ids_needed.update(int(x) for x in ids)
        elif r.get('applies_to') == 'product' and ids:
            product_ids_needed.update(int(x) for x in ids)

    brand_name_map = {}
    product_name_map = {}

    if brand_ids_needed:
        cursor.execute('SELECT id, name FROM brands WHERE id = ANY(%s)', (list(brand_ids_needed),))
        brand_name_map = {row['id']: row['name'] for row in cursor.fetchall()}

    if product_ids_needed:
        cursor.execute('SELECT id, name FROM products WHERE id = ANY(%s)', (list(product_ids_needed),))
        product_name_map = {row['id']: row['name'] for row in cursor.fetchall()}

    for r in rows:
        ids = [int(x) for x in (r.get('applies_to_ids') or [])]
        at = r.get('applies_to', 'all') or 'all'
        if at == 'brand':
            r['applies_to_names'] = [brand_name_map.get(i, f'Brand#{i}') for i in ids]
        elif at == 'product':
            r['applies_to_names'] = [product_name_map.get(i, f'Product#{i}') for i in ids]
        else:
            r['applies_to_names'] = []


def _calc_coupon_discount(cursor, coupon_code, cart_total, user_id, user_tier_rank, cart_brand_ids=None, cart_product_ids=None):
    """
    Layer 3: Validate and calculate coupon discount.
    Returns: (coupon_row, discount_amount, error_message)
    """
    if not coupon_code:
        return (None, 0, None)
    if cart_brand_ids is None:
        cart_brand_ids = []
    if cart_product_ids is None:
        cart_product_ids = []

    cursor.execute('''
        SELECT c.*, rt.level_rank as min_tier_rank
        FROM coupons c
        LEFT JOIN reseller_tiers rt ON rt.id = c.min_tier_id
        WHERE UPPER(c.code) = UPPER(%s)
    ''', (coupon_code,))
    coupon = cursor.fetchone()

    if not coupon:
        return (None, 0, 'ไม่พบคูปองนี้')
    if not coupon['is_active']:
        return (None, 0, 'คูปองนี้ไม่ได้เปิดใช้งาน')
    if coupon['start_date'] and coupon['start_date'] > datetime.now():
        return (None, 0, 'คูปองยังไม่เริ่มใช้งาน')
    if coupon['end_date'] and coupon['end_date'] < datetime.now():
        return (None, 0, 'คูปองหมดอายุแล้ว')
    if coupon['total_quota'] > 0 and coupon['usage_count'] >= coupon['total_quota']:
        return (None, 0, 'คูปองถูกใช้ครบแล้ว')
    if coupon['min_spend'] and cart_total < float(coupon['min_spend']):
        return (None, 0, f'ต้องซื้อขั้นต่ำ {float(coupon["min_spend"]):,.0f} บาท')
    if coupon['min_tier_rank'] and user_tier_rank < coupon['min_tier_rank']:
        return (None, 0, 'ระดับสมาชิกของคุณไม่ตรงกับเงื่อนไขคูปองนี้')

    # Check applies_to restriction
    applies_to = coupon.get('applies_to', 'all') or 'all'
    applies_to_ids = list(coupon.get('applies_to_ids') or [])
    if applies_to == 'brand' and applies_to_ids:
        if not set(applies_to_ids) & set(int(x) for x in cart_brand_ids if x):
            return (None, 0, 'คูปองนี้ใช้ได้เฉพาะสินค้าบางแบรนด์เท่านั้น')
    elif applies_to == 'product' and applies_to_ids:
        if not set(applies_to_ids) & set(int(x) for x in cart_product_ids if x):
            return (None, 0, 'คูปองนี้ใช้ได้เฉพาะสินค้าที่กำหนดเท่านั้น')

    # Check user has claimed this coupon
    cursor.execute('''
        SELECT id, status FROM user_coupons
        WHERE user_id = %s AND coupon_id = %s
    ''', (user_id, coupon['id']))
    uc = cursor.fetchone()
    if not uc:
        return (None, 0, 'คุณยังไม่ได้เก็บคูปองนี้')
    if uc['status'] == 'used':
        return (None, 0, 'คูปองนี้ถูกใช้แล้ว')
    if uc['status'] == 'expired':
        return (None, 0, 'คูปองหมดอายุแล้ว')

    discount_type = coupon['discount_type']
    discount_value = float(coupon['discount_value'])
    max_discount = float(coupon['max_discount'] or 0)

    if discount_type == 'percent':
        discount = round(cart_total * discount_value / 100, 2)
        if max_discount > 0:
            discount = min(discount, max_discount)
    elif discount_type == 'fixed':
        discount = min(discount_value, cart_total)
    elif discount_type == 'free_shipping':
        discount = 0  # Applied at shipping level
    else:
        discount = 0

    return (dict(coupon), discount, None)


# ── Admin: Promotions ──────────────────────────────────────

@marketing_bp.route('/api/admin/promotions', methods=['GET'])
@admin_required
def admin_get_promotions():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT p.*,
                   rt.name as min_tier_name,
                   b.name as target_brand_name,
                   cat.name as target_category_name,
                   sk.sku_code as reward_sku_code,
                   pr.name as reward_product_name
            FROM promotions p
            LEFT JOIN reseller_tiers rt ON rt.id = p.min_tier_id
            LEFT JOIN brands b ON b.id = p.target_brand_id
            LEFT JOIN categories cat ON cat.id = p.target_category_id
            LEFT JOIN skus sk ON sk.id = p.reward_sku_id
            LEFT JOIN products pr ON pr.id = sk.product_id
            ORDER BY p.is_active DESC, p.priority DESC, p.created_at DESC
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for f in ['condition_min_spend', 'reward_value']:
                if r[f] is not None:
                    r[f] = float(r[f])
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/promotions', methods=['POST'])
@admin_required
def admin_create_promotion():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            INSERT INTO promotions (name, promo_type, condition_min_spend, condition_min_qty,
                reward_type, reward_value, reward_sku_id, reward_qty,
                target_brand_id, target_category_id, min_tier_id,
                is_stackable, once_per_user, priority, start_date, end_date, is_active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        ''', (
            data.get('name'), data.get('promo_type', 'discount_percent'),
            data.get('condition_min_spend', 0), data.get('condition_min_qty', 0),
            data.get('reward_type', 'discount_percent'), data.get('reward_value', 0),
            data.get('reward_sku_id'), data.get('reward_qty', 1),
            data.get('target_brand_id'), data.get('target_category_id'), data.get('min_tier_id'),
            data.get('is_stackable', False), data.get('once_per_user', False),
            data.get('priority', 0),
            data.get('start_date'), data.get('end_date'), data.get('is_active', True)
        ))
        promo = dict(cursor.fetchone())
        conn.commit()
        return jsonify(promo), 201
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/promotions/<int:promo_id>', methods=['PUT'])
@admin_required
def admin_update_promotion(promo_id):
    conn = None
    cursor = None
    try:
        data = request.get_json()
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            UPDATE promotions SET
                name=%s, promo_type=%s, condition_min_spend=%s, condition_min_qty=%s,
                reward_type=%s, reward_value=%s, reward_sku_id=%s, reward_qty=%s,
                target_brand_id=%s, target_category_id=%s, min_tier_id=%s,
                is_stackable=%s, once_per_user=%s, priority=%s, start_date=%s, end_date=%s, is_active=%s
            WHERE id=%s RETURNING *
        ''', (
            data.get('name'), data.get('promo_type'),
            data.get('condition_min_spend', 0), data.get('condition_min_qty', 0),
            data.get('reward_type'), data.get('reward_value', 0),
            data.get('reward_sku_id'), data.get('reward_qty', 1),
            data.get('target_brand_id'), data.get('target_category_id'), data.get('min_tier_id'),
            data.get('is_stackable', False), data.get('once_per_user', False),
            data.get('priority', 0),
            data.get('start_date'), data.get('end_date'), data.get('is_active', True),
            promo_id
        ))
        promo = cursor.fetchone()
        if not promo:
            return jsonify({'error': 'ไม่พบโปรโมชัน'}), 404
        conn.commit()
        return jsonify(dict(promo)), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/promotions/<int:promo_id>', methods=['DELETE'])
@admin_required
def admin_delete_promotion(promo_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM promotions WHERE id=%s', (promo_id,))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ── Admin: Size Chart Groups ───────────────────────────────

@marketing_bp.route('/api/admin/size-chart-groups', methods=['GET'])
@admin_required
def admin_get_size_chart_groups():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT scg.*,
                   COUNT(p.id) as product_count
            FROM size_chart_groups scg
            LEFT JOIN products p ON p.size_chart_group_id = scg.id AND p.status != 'deleted'
            GROUP BY scg.id
            ORDER BY scg.name
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/size-chart-groups', methods=['POST'])
@admin_required
def admin_create_size_chart_group():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        if not data.get('name'):
            return jsonify({'error': 'กรุณาระบุชื่อตารางขนาด'}), 400
        columns = data.get('columns', ['ขนาด', 'รอบอก', 'รอบเอว', 'ความยาว'])
        rows = data.get('rows', [])
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        fabric_type = data.get('fabric_type', 'non-stretch') or 'non-stretch'
        fabric_composition = (data.get('fabric_composition') or '').strip()
        allowances = data.get('allowances') or {'chest': 1, 'waist': 1, 'hip': 1.5}
        cursor.execute('''
            INSERT INTO size_chart_groups (name, description, columns, rows, fabric_type, fabric_composition, allowances)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *
        ''', (data['name'], data.get('description', ''),
              json.dumps(columns, ensure_ascii=False),
              json.dumps(rows, ensure_ascii=False),
              fabric_type,
              fabric_composition or None,
              json.dumps(allowances)))
        row = dict(cursor.fetchone())
        conn.commit()
        return jsonify(row), 201
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/size-chart-groups/<int:group_id>', methods=['GET'])
@admin_required
def admin_get_size_chart_group(group_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT * FROM size_chart_groups WHERE id=%s', (group_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'ไม่พบตารางขนาด'}), 404
        result = dict(row)
        cursor.execute('''
            SELECT id, name FROM products
            WHERE size_chart_group_id = %s AND status != 'deleted'
            ORDER BY name
        ''', (group_id,))
        result['products'] = [dict(r) for r in cursor.fetchall()]
        return jsonify(result), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/size-chart-groups/<int:group_id>', methods=['PUT'])
@admin_required
def admin_update_size_chart_group(group_id):
    conn = None
    cursor = None
    try:
        data = request.get_json()
        if not data.get('name'):
            return jsonify({'error': 'กรุณาระบุชื่อตารางขนาด'}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        _ft = data.get('fabric_type', 'non-stretch') or 'non-stretch'
        _fc = (data.get('fabric_composition') or '').strip() or None
        _al = data.get('allowances') or {'chest': 1, 'waist': 1, 'hip': 1.5}
        cursor.execute('''
            UPDATE size_chart_groups
            SET name=%s, description=%s, columns=%s, rows=%s,
                fabric_type=%s, fabric_composition=%s, allowances=%s, updated_at=NOW()
            WHERE id=%s RETURNING *
        ''', (data['name'], data.get('description', ''),
              json.dumps(data.get('columns', []), ensure_ascii=False),
              json.dumps(data.get('rows', []), ensure_ascii=False),
              _ft, _fc, json.dumps(_al),
              group_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'ไม่พบตารางขนาด'}), 404
        if 'product_ids' in data:
            cursor.execute('UPDATE products SET size_chart_group_id=NULL WHERE size_chart_group_id=%s', (group_id,))
            if data['product_ids']:
                cursor.execute(
                    'UPDATE products SET size_chart_group_id=%s WHERE id = ANY(%s)',
                    (group_id, data['product_ids'])
                )
        conn.commit()
        return jsonify(dict(row)), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/size-chart-groups/<int:group_id>', methods=['DELETE'])
@admin_required
def admin_delete_size_chart_group(group_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE products SET size_chart_group_id=NULL WHERE size_chart_group_id=%s', (group_id,))
        cursor.execute('DELETE FROM size_chart_groups WHERE id=%s', (group_id,))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/products-for-size-chart', methods=['GET'])
@admin_required
def admin_products_for_size_chart():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT p.id, p.name, p.size_chart_group_id, scg.name as chart_group_name
            FROM products p
            LEFT JOIN size_chart_groups scg ON scg.id = p.size_chart_group_id
            WHERE p.status != 'deleted'
            ORDER BY p.name
        ''')
        return jsonify([dict(r) for r in cursor.fetchall()]), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ── Admin: Coupons ─────────────────────────────────────────

@marketing_bp.route('/api/admin/coupons', methods=['GET'])
@admin_required
def admin_get_coupons():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT c.*,
                   rt.name as min_tier_name,
                   COUNT(uc.id) as claimed_count,
                   COUNT(CASE WHEN uc.status='used' THEN 1 END) as used_count
            FROM coupons c
            LEFT JOIN reseller_tiers rt ON rt.id = c.min_tier_id
            LEFT JOIN user_coupons uc ON uc.coupon_id = c.id
            GROUP BY c.id, rt.name
            ORDER BY c.is_active DESC, c.created_at DESC
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for f in ['discount_value', 'max_discount', 'min_spend']:
                if r[f] is not None:
                    r[f] = float(r[f])
        _enrich_applies_to_names(cursor, rows)
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons', methods=['POST'])
@admin_required
def admin_create_coupon():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        code = (data.get('code') or '').strip().upper()
        if not code:
            return jsonify({'error': 'กรุณาระบุรหัสคูปอง'}), 400
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        applies_to = data.get('applies_to', 'all') or 'all'
        applies_to_ids = [int(x) for x in (data.get('applies_to_ids') or []) if x]
        cursor.execute('''
            INSERT INTO coupons (code, name, discount_type, discount_value, max_discount,
                min_spend, total_quota, per_user_limit, target_type, min_tier_id,
                is_stackable, start_date, end_date, is_active, applies_to, applies_to_ids)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        ''', (
            code, data.get('name'), data.get('discount_type', 'fixed'),
            data.get('discount_value', 0), data.get('max_discount', 0),
            data.get('min_spend', 0), data.get('total_quota', 0),
            data.get('per_user_limit', 1), data.get('target_type', 'all'),
            data.get('min_tier_id'), data.get('is_stackable', False),
            data.get('start_date'), data.get('end_date'), data.get('is_active', True),
            applies_to, applies_to_ids
        ))
        coupon = dict(cursor.fetchone())
        conn.commit()
        return jsonify(coupon), 201
    except psycopg2.errors.UniqueViolation:
        if conn: conn.rollback()
        return jsonify({'error': 'รหัสคูปองนี้ถูกใช้ไปแล้ว'}), 400
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons/<int:coupon_id>', methods=['PUT'])
@admin_required
def admin_update_coupon(coupon_id):
    conn = None
    cursor = None
    try:
        data = request.get_json()
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        applies_to = data.get('applies_to', 'all') or 'all'
        applies_to_ids = [int(x) for x in (data.get('applies_to_ids') or []) if x]
        cursor.execute('''
            UPDATE coupons SET
                name=%s, discount_type=%s, discount_value=%s, max_discount=%s,
                min_spend=%s, total_quota=%s, per_user_limit=%s, target_type=%s,
                min_tier_id=%s, is_stackable=%s, start_date=%s, end_date=%s, is_active=%s,
                applies_to=%s, applies_to_ids=%s
            WHERE id=%s RETURNING *
        ''', (
            data.get('name'), data.get('discount_type'), data.get('discount_value'),
            data.get('max_discount', 0), data.get('min_spend', 0),
            data.get('total_quota', 0), data.get('per_user_limit', 1),
            data.get('target_type', 'all'), data.get('min_tier_id'),
            data.get('is_stackable', False),
            data.get('start_date'), data.get('end_date'), data.get('is_active', True),
            applies_to, applies_to_ids, coupon_id
        ))
        coupon = cursor.fetchone()
        if not coupon:
            return jsonify({'error': 'ไม่พบคูปอง'}), 404
        conn.commit()
        return jsonify(dict(coupon)), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons/<int:coupon_id>', methods=['DELETE'])
@admin_required
def admin_delete_coupon(coupon_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_coupons WHERE coupon_id=%s', (coupon_id,))
        cursor.execute('DELETE FROM coupons WHERE id=%s', (coupon_id,))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons/<int:coupon_id>/assign-preview', methods=['GET'])
@admin_required
def admin_assign_coupon_preview(coupon_id):
    """Preview how many resellers would receive this coupon (excluding those who already have it ready)"""
    conn = None
    cursor = None
    try:
        tier_ids_raw = request.args.get('tier_ids', '')
        tier_ids = [int(x) for x in tier_ids_raw.split(',') if x.strip().isdigit()]
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id FROM coupons WHERE id=%s', (coupon_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบคูปอง'}), 404
        if tier_ids:
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM users u
                WHERE u.role='reseller' AND u.is_active=TRUE
                  AND u.reseller_tier_id = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM user_coupons uc
                      WHERE uc.user_id=u.id AND uc.coupon_id=%s AND uc.status='ready'
                  )
            ''', (tier_ids, coupon_id))
        else:
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM users u
                WHERE u.role='reseller' AND u.is_active=TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM user_coupons uc
                      WHERE uc.user_id=u.id AND uc.coupon_id=%s AND uc.status='ready'
                  )
            ''', (coupon_id,))
        count = cursor.fetchone()['cnt']
        return jsonify({'count': count}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons/<int:coupon_id>/assign', methods=['POST'])
@admin_required
def admin_assign_coupon(coupon_id):
    """Directly give a coupon to resellers filtered by tier, skipping those who already have it (ready)"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        tier_ids = data.get('tier_ids', [])  # empty = all tiers
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('SELECT id FROM coupons WHERE id=%s', (coupon_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'ไม่พบคูปอง'}), 404

        if tier_ids:
            cursor.execute('''
                SELECT u.id FROM users u
                WHERE u.role='reseller' AND u.is_active=TRUE
                  AND u.reseller_tier_id = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM user_coupons uc
                      WHERE uc.user_id=u.id AND uc.coupon_id=%s AND uc.status='ready'
                  )
            ''', (tier_ids, coupon_id))
        else:
            cursor.execute('''
                SELECT u.id FROM users u
                WHERE u.role='reseller' AND u.is_active=TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM user_coupons uc
                      WHERE uc.user_id=u.id AND uc.coupon_id=%s AND uc.status='ready'
                  )
            ''', (coupon_id,))
        user_ids = [r['id'] for r in cursor.fetchall()]

        assigned = 0
        for uid in user_ids:
            cursor.execute('''
                INSERT INTO user_coupons (user_id, coupon_id, status)
                VALUES (%s, %s, 'ready')
                ON CONFLICT (user_id, coupon_id) DO NOTHING
            ''', (uid, coupon_id))
            if cursor.rowcount > 0:
                assigned += 1
        conn.commit()
        return jsonify({'assigned': assigned}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/admin/coupons/<int:coupon_id>/users', methods=['GET'])
@admin_required
def admin_get_coupon_users(coupon_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT uc.*, u.full_name, u.email,
                   rt.name as tier_name, o.order_number as used_in_order_number
            FROM user_coupons uc
            JOIN users u ON u.id = uc.user_id
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            LEFT JOIN orders o ON o.id = uc.used_in_order_id
            WHERE uc.coupon_id = %s
            ORDER BY uc.collected_at DESC
        ''', (coupon_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ── Reseller: Promotions & Coupons ────────────────────────

@marketing_bp.route('/api/reseller/promotions/active', methods=['GET'])
@login_required
def reseller_get_active_promotions():
    """Return all currently active auto-promotions for display purposes"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT p.id, p.name, p.promo_type, p.condition_min_spend, p.condition_min_qty,
                   p.reward_type, p.reward_value, p.reward_qty, p.is_stackable,
                   p.start_date, p.end_date,
                   rt.name as min_tier_name, b.name as target_brand_name,
                   sk.sku_code as reward_sku_code, pr.name as reward_product_name
            FROM promotions p
            LEFT JOIN reseller_tiers rt ON rt.id = p.min_tier_id
            LEFT JOIN brands b ON b.id = p.target_brand_id
            LEFT JOIN skus sk ON sk.id = p.reward_sku_id
            LEFT JOIN products pr ON pr.id = sk.product_id
            WHERE p.is_active = TRUE
              AND (p.start_date IS NULL OR p.start_date <= CURRENT_TIMESTAMP)
              AND (p.end_date IS NULL OR p.end_date >= CURRENT_TIMESTAMP)
            ORDER BY p.priority DESC, p.condition_min_spend
        ''')
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for f in ['condition_min_spend', 'reward_value']:
                if r[f] is not None:
                    r[f] = float(r[f])
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/reseller/coupons/available', methods=['GET'])
@login_required
def reseller_get_available_coupons():
    """Coupons the user can still claim"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT c.id, c.code, c.name, c.discount_type, c.discount_value, c.max_discount,
                   c.min_spend, c.total_quota, c.usage_count, c.per_user_limit,
                   c.start_date, c.end_date, c.is_stackable, c.applies_to, c.applies_to_ids,
                   rt.name as min_tier_name,
                   COALESCE(uc_count.times_claimed, 0) as times_claimed,
                   (uc_mine.id IS NOT NULL) as already_claimed
            FROM coupons c
            LEFT JOIN reseller_tiers rt ON rt.id = c.min_tier_id
            LEFT JOIN (
                SELECT coupon_id, COUNT(*) as times_claimed
                FROM user_coupons WHERE user_id = %s
                GROUP BY coupon_id
            ) uc_count ON uc_count.coupon_id = c.id
            LEFT JOIN user_coupons uc_mine ON uc_mine.coupon_id = c.id AND uc_mine.user_id = %s
            WHERE c.is_active = TRUE
              AND (c.start_date IS NULL OR c.start_date <= CURRENT_TIMESTAMP)
              AND (c.end_date IS NULL OR c.end_date >= CURRENT_TIMESTAMP)
              AND (c.total_quota = 0 OR c.usage_count < c.total_quota)
            ORDER BY c.created_at DESC
        ''', (user_id, user_id))
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for f in ['discount_value', 'max_discount', 'min_spend']:
                if r[f] is not None:
                    r[f] = float(r[f])
        _enrich_applies_to_names(cursor, rows)
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/reseller/coupons/wallet', methods=['GET'])
@login_required
def reseller_get_coupon_wallet():
    """Coupons the user has already claimed"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT uc.id, uc.status, uc.collected_at, uc.used_at,
                   c.id as coupon_id, c.code, c.name, c.discount_type,
                   c.discount_value, c.max_discount, c.min_spend,
                   c.end_date, c.is_stackable, c.is_active, c.applies_to, c.applies_to_ids,
                   o.order_number as used_in_order_number
            FROM user_coupons uc
            JOIN coupons c ON c.id = uc.coupon_id
            LEFT JOIN orders o ON o.id = uc.used_in_order_id
            WHERE uc.user_id = %s
            ORDER BY
                CASE uc.status WHEN 'ready' THEN 0 WHEN 'used' THEN 1 ELSE 2 END,
                uc.collected_at DESC
        ''', (user_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for f in ['discount_value', 'max_discount', 'min_spend']:
                if r[f] is not None:
                    r[f] = float(r[f])
            # Mark expired
            if r['status'] == 'ready' and r['end_date'] and r['end_date'] < datetime.now():
                r['status'] = 'expired'
        _enrich_applies_to_names(cursor, rows)
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/reseller/coupons/<int:coupon_id>/claim', methods=['POST'])
@login_required
def reseller_claim_coupon(coupon_id):
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('SELECT * FROM coupons WHERE id=%s', (coupon_id,))
        coupon = cursor.fetchone()
        if not coupon:
            return jsonify({'error': 'ไม่พบคูปอง'}), 404
        if not coupon['is_active']:
            return jsonify({'error': 'คูปองนี้ไม่ได้เปิดใช้งาน'}), 400
        if coupon['total_quota'] > 0 and coupon['usage_count'] >= coupon['total_quota']:
            return jsonify({'error': 'คูปองถูกเก็บครบแล้ว'}), 400

        cursor.execute('''
            SELECT COUNT(*) as cnt FROM user_coupons WHERE user_id=%s AND coupon_id=%s
        ''', (user_id, coupon_id))
        existing = cursor.fetchone()['cnt']
        if existing >= coupon['per_user_limit']:
            return jsonify({'error': 'คุณเก็บคูปองนี้ครบแล้ว'}), 400

        cursor.execute('''
            INSERT INTO user_coupons (user_id, coupon_id, status)
            VALUES (%s, %s, 'ready')
            ON CONFLICT (user_id, coupon_id) DO NOTHING
        ''', (user_id, coupon_id))
        if cursor.rowcount == 0:
            return jsonify({'error': 'คุณเก็บคูปองนี้ไปแล้ว'}), 400

        conn.commit()
        return jsonify({'success': True, 'message': 'เก็บคูปองสำเร็จ'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@marketing_bp.route('/api/reseller/cart/preview-discount', methods=['POST'])
@login_required
def reseller_preview_discount():
    """Preview promotion + coupon discounts for current cart total"""
    conn = None
    cursor = None
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        cart_total = float(data.get('cart_total', 0))          # tier-discounted total
        retail_total = float(data.get('retail_total', 0))      # retail total before tier discount
        tier_savings = float(data.get('tier_savings', 0))      # = retail_total - cart_total
        if retail_total <= 0:
            retail_total = cart_total                           # fallback: no tier info sent
            tier_savings = 0
        coupon_code = (data.get('coupon_code') or '').strip()
        brand_ids = data.get('brand_ids', [])
        category_ids = data.get('category_ids', [])
        product_ids = data.get('product_ids', [])
        cart_qty = int(data.get('cart_qty', 0))

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get user tier rank
        cursor.execute('''
            SELECT rt.level_rank FROM users u
            LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (user_id,))
        u = cursor.fetchone()
        user_tier_rank = int(u['level_rank']) if u and u['level_rank'] else 1

        # "Best discount wins": compare promo on RETAIL price vs tier savings — pick higher, no stacking
        promo_candidate, promo_on_retail = _calc_best_promotion(cursor, retail_total, brand_ids, category_ids, user_tier_rank, cart_qty, user_id=user_id)
        use_tier = (tier_savings >= promo_on_retail) or (promo_on_retail == 0)
        if use_tier:
            promo = None
            promo_discount = 0
            effective_total = cart_total        # already tier-discounted
        else:
            promo = promo_candidate
            promo_discount = promo_on_retail
            effective_total = retail_total - promo_on_retail   # retail - promo

        coupon, coupon_discount, coupon_error = (None, 0, None)
        if coupon_code:
            if promo is None or promo.get('is_stackable'):
                coupon, coupon_discount, coupon_error = _calc_coupon_discount(
                    cursor, coupon_code, effective_total, user_id, user_tier_rank,
                    cart_brand_ids=brand_ids, cart_product_ids=product_ids)
            else:
                coupon_error = 'โปรโมชันที่ใช้อยู่ไม่รองรับการใช้คูปองร่วมกัน'

        final_total = max(0, effective_total - coupon_discount)

        return jsonify({
            'cart_total': cart_total,
            'retail_total': retail_total,
            'effective_total': effective_total,
            'promotion': {
                'id': promo['id'] if promo else None,
                'name': promo['name'] if promo else None,
                'discount': promo_discount
            } if promo else None,
            'coupon': {
                'id': coupon['id'] if coupon else None,
                'code': coupon['code'] if coupon else None,
                'discount': coupon_discount,
                'is_free_shipping': coupon['discount_type'] == 'free_shipping' if coupon else False
            } if coupon else None,
            'coupon_error': coupon_error,
            'total_discount': promo_discount + coupon_discount,
            'final_total': final_total
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== END MARKETING MODULE ====================
