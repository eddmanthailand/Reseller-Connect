"""
EKG Synapse API Blueprint
Full-access REST API for EKG Synapse to read & write everything in EKG Shops.
Auth: X-API-Key header (managed via /admin/synapse-keys)
"""
import os, hashlib, secrets, json
import psycopg2.extras
from functools import wraps
from datetime import datetime
from flask import Blueprint, request, jsonify, g
from database import get_db as _get_db_raw

def get_db_connection():
    return _get_db_raw()

def _cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

synapse_bp = Blueprint('synapse', __name__, url_prefix='/api/synapse')

# ══════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════

def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

def require_synapse_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        raw_key = (
            request.headers.get('X-API-Key') or
            request.headers.get('Authorization', '').removeprefix('Bearer ')
        ).strip()
        if not raw_key:
            return jsonify(error='Missing X-API-Key header'), 401
        prefix = raw_key[:8]
        key_hash = _hash_key(raw_key)
        try:
            with get_db_connection() as conn:
                with _cursor(conn) as cur:
                    cur.execute("""
                        SELECT id, name, is_active FROM synapse_api_keys
                        WHERE key_prefix = %s AND key_hash = %s
                    """, (prefix, key_hash))
                    row = cur.fetchone()
                    if not row or not row['is_active']:
                        return jsonify(error='Invalid or inactive API key'), 403
                    cur.execute("""
                        UPDATE synapse_api_keys SET last_used_at = NOW()
                        WHERE id = %s
                    """, (row['id'],))
                    conn.commit()
                    g.synapse_key_name = row['name']
        except Exception as e:
            return jsonify(error=f'Auth error: {str(e)}'), 500
        return f(*args, **kwargs)
    return decorated

# ── Admin: generate/list/revoke API keys (requires session login) ──

from flask import session

def _require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id') or session.get('role') not in ('admin', 'superadmin'):
            return jsonify(error='Admin required'), 403
        return f(*args, **kwargs)
    return decorated

@synapse_bp.route('/admin/keys', methods=['GET'])
@_require_admin
def list_keys():
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT id, name, key_prefix, is_active, created_at, last_used_at, notes
                FROM synapse_api_keys ORDER BY created_at DESC
            """)
            keys = cur.fetchall()
    return jsonify(keys=[dict(k) for k in keys])

@synapse_bp.route('/admin/keys', methods=['POST'])
@_require_admin
def create_key():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    notes = (data.get('notes') or '').strip()
    if not name:
        return jsonify(error='name required'), 400
    raw_key = 'syn_' + secrets.token_urlsafe(32)
    prefix = raw_key[:8]
    key_hash = _hash_key(raw_key)
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                INSERT INTO synapse_api_keys (name, key_prefix, key_hash, notes)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (name, prefix, key_hash, notes))
            new_id = cur.fetchone()['id']
        conn.commit()
    return jsonify(id=new_id, name=name, api_key=raw_key,
                   message='บันทึก API Key นี้ไว้ จะไม่แสดงอีก'), 201

@synapse_bp.route('/admin/keys/<int:key_id>', methods=['DELETE'])
@_require_admin
def revoke_key(key_id):
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("UPDATE synapse_api_keys SET is_active = FALSE WHERE id = %s", (key_id,))
        conn.commit()
    return jsonify(ok=True)

# ══════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════

@synapse_bp.route('/products', methods=['GET'])
@require_synapse_key
def get_products():
    search = request.args.get('q', '')
    status = request.args.get('status', 'active')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 50)))
    offset = (page - 1) * per_page
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            where = "WHERE p.status = %s" if status != 'all' else "WHERE 1=1"
            params = [status] if status != 'all' else []
            if search:
                where += " AND (p.name ILIKE %s OR p.parent_sku ILIKE %s)"
                params += [f'%{search}%', f'%{search}%']
            cur.execute(f"""
                SELECT p.id, p.name, p.parent_sku, p.status, p.product_type,
                       p.low_stock_threshold, p.created_at,
                       b.name AS brand_name,
                       COALESCE(SUM(s.stock), 0) AS total_stock,
                       COUNT(DISTINCT s.id) AS sku_count,
                       ARRAY_AGG(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) AS categories
                FROM products p
                LEFT JOIN brands b ON b.id = p.brand_id
                LEFT JOIN skus s ON s.product_id = p.id
                LEFT JOIN product_categories pc ON pc.product_id = p.id
                LEFT JOIN categories c ON c.id = pc.category_id
                {where}
                GROUP BY p.id, b.name
                ORDER BY p.name
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            products = cur.fetchall()
            cur.execute(f"SELECT COUNT(*) FROM products p {where}", params)
            total = cur.fetchone()['count']
    return jsonify(products=[dict(p) for p in products], total=total, page=page, per_page=per_page)

@synapse_bp.route('/products/<int:product_id>', methods=['GET'])
@require_synapse_key
def get_product_detail(product_id):
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT p.*, b.name AS brand_name
                FROM products p LEFT JOIN brands b ON b.id = p.brand_id
                WHERE p.id = %s
            """, (product_id,))
            product = cur.fetchone()
            if not product:
                return jsonify(error='Product not found'), 404
            cur.execute("""
                SELECT s.*, COALESCE(SUM(ws.stock), s.stock) AS warehouse_stock
                FROM skus s
                LEFT JOIN sku_warehouse_stock ws ON ws.sku_id = s.id
                WHERE s.product_id = %s
                GROUP BY s.id
                ORDER BY s.sku_code
            """, (product_id,))
            skus = cur.fetchall()
            cur.execute("""
                SELECT sv.sku_id, o.name AS option_name, ov.value
                FROM sku_values_map sv
                JOIN option_values ov ON ov.id = sv.option_value_id
                JOIN options o ON o.id = ov.option_id
                WHERE sv.sku_id IN (SELECT id FROM skus WHERE product_id = %s)
            """, (product_id,))
            sku_opts = cur.fetchall()
    # attach options to each sku
    opts_by_sku = {}
    for o in sku_opts:
        opts_by_sku.setdefault(o['sku_id'], {})[o['option_name']] = o['value']
    sku_list = []
    for s in skus:
        sd = dict(s)
        sd['options'] = opts_by_sku.get(s['id'], {})
        sku_list.append(sd)
    result = dict(product)
    result['skus'] = sku_list
    return jsonify(result)

# ══════════════════════════════════════════
# STOCK
# ══════════════════════════════════════════

@synapse_bp.route('/stock', methods=['GET'])
@require_synapse_key
def get_stock():
    low_only = request.args.get('low_only', 'false').lower() == 'true'
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            where = "AND s.stock <= p.low_stock_threshold" if low_only else ""
            cur.execute(f"""
                SELECT p.id AS product_id, p.name AS product_name, p.parent_sku,
                       s.id AS sku_id, s.sku_code, s.stock, p.low_stock_threshold,
                       CASE WHEN s.stock = 0 THEN 'out_of_stock'
                            WHEN s.stock <= p.low_stock_threshold THEN 'low_stock'
                            ELSE 'in_stock' END AS stock_status
                FROM skus s
                JOIN products p ON p.id = s.product_id
                WHERE p.status = 'active' {where}
                ORDER BY s.stock ASC, p.name
            """)
            rows = cur.fetchall()
    return jsonify(stock=[dict(r) for r in rows])

@synapse_bp.route('/stock/<int:sku_id>', methods=['PATCH'])
@require_synapse_key
def update_stock(sku_id):
    data = request.get_json() or {}
    if 'stock' not in data:
        return jsonify(error='stock field required'), 400
    new_stock = int(data['stock'])
    reason = data.get('reason', 'Synapse API update')
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT stock, product_id FROM skus WHERE id = %s", (sku_id,))
            sku = cur.fetchone()
            if not sku:
                return jsonify(error='SKU not found'), 404
            old_stock = sku['stock']
            cur.execute("UPDATE skus SET stock = %s, updated_at = NOW() WHERE id = %s",
                       (new_stock, sku_id))
            cur.execute("""
                INSERT INTO stock_audit_log (sku_id, change_type, quantity_before,
                    quantity_after, reason, created_at)
                VALUES (%s, 'adjustment', %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (sku_id, old_stock, new_stock, reason))
        conn.commit()
    return jsonify(ok=True, sku_id=sku_id, old_stock=old_stock, new_stock=new_stock)

@synapse_bp.route('/stock/warehouse', methods=['GET'])
@require_synapse_key
def get_warehouse_stock():
    warehouse_id = request.args.get('warehouse_id')
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            where = "AND ws.warehouse_id = %s" if warehouse_id else ""
            params = [warehouse_id] if warehouse_id else []
            cur.execute(f"""
                SELECT w.name AS warehouse, p.name AS product, s.sku_code,
                       ws.stock, p.low_stock_threshold
                FROM sku_warehouse_stock ws
                JOIN skus s ON s.id = ws.sku_id
                JOIN products p ON p.id = s.product_id
                JOIN warehouses w ON w.id = ws.warehouse_id
                WHERE p.status = 'active' {where}
                ORDER BY w.name, p.name
            """, params)
            rows = cur.fetchall()
    return jsonify(warehouse_stock=[dict(r) for r in rows])

# ══════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════

@synapse_bp.route('/orders', methods=['GET'])
@require_synapse_key
def get_orders():
    status = request.args.get('status')
    user_id = request.args.get('user_id')
    days = int(request.args.get('days', 30))
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 50)))
    offset = (page - 1) * per_page
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            conds = ["o.created_at >= NOW() - INTERVAL '%s days'" % days]
            params = []
            if status:
                conds.append("o.status = %s")
                params.append(status)
            if user_id:
                conds.append("o.user_id = %s")
                params.append(user_id)
            where = "WHERE " + " AND ".join(conds)
            cur.execute(f"""
                SELECT o.id, o.order_number, o.status, o.final_amount, o.total_amount,
                       o.discount_amount, o.shipping_fee, o.created_at, o.paid_at,
                       o.platform, o.is_quick_order,
                       u.full_name, u.username, u.phone,
                       rt.name AS tier_name,
                       o.shipping_name, o.shipping_province, o.notes
                FROM orders o
                JOIN users u ON u.id = o.user_id
                LEFT JOIN reseller_tiers rt ON rt.id = o.tier_id
                {where}
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            orders = cur.fetchall()
            cur.execute(f"SELECT COUNT(*) FROM orders o JOIN users u ON u.id=o.user_id {where}", params)
            total = cur.fetchone()['count']
    return jsonify(orders=[dict(o) for o in orders], total=total, page=page, per_page=per_page)

@synapse_bp.route('/orders/<int:order_id>', methods=['GET'])
@require_synapse_key
def get_order_detail(order_id):
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT o.*, u.full_name, u.username, u.phone, u.email,
                       rt.name AS tier_name
                FROM orders o
                JOIN users u ON u.id = o.user_id
                LEFT JOIN reseller_tiers rt ON rt.id = o.tier_id
                WHERE o.id = %s
            """, (order_id,))
            order = cur.fetchone()
            if not order:
                return jsonify(error='Order not found'), 404
            cur.execute("""
                SELECT oi.product_name, oi.sku_code, oi.quantity,
                       oi.unit_price, oi.subtotal
                FROM order_items oi WHERE oi.order_id = %s
            """, (order_id,))
            items = cur.fetchall()
            cur.execute("""
                SELECT ps.slip_image_url, ps.uploaded_at, ps.amount
                FROM payment_slips ps WHERE ps.order_id = %s
            """, (order_id,))
            slips = cur.fetchall()
    result = dict(order)
    result['items'] = [dict(i) for i in items]
    result['payment_slips'] = [dict(s) for s in slips]
    return jsonify(result)

@synapse_bp.route('/orders/<int:order_id>/status', methods=['PATCH'])
@require_synapse_key
def update_order_status(order_id):
    data = request.get_json() or {}
    new_status = data.get('status', '').strip()
    valid_statuses = [
        'pending_payment', 'payment_uploaded', 'confirmed',
        'processing', 'shipped', 'delivered', 'cancelled', 'returned'
    ]
    if new_status not in valid_statuses:
        return jsonify(error=f'Invalid status. Valid: {valid_statuses}'), 400
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Order not found'), 404
            old_status = row['status']
            cur.execute("""
                UPDATE orders SET status = %s, updated_at = NOW()
                WHERE id = %s
            """, (new_status, order_id))
            if new_status == 'cancelled':
                cur.execute("UPDATE orders SET cancelled_at = NOW() WHERE id = %s", (order_id,))
            cur.execute("""
                INSERT INTO activity_logs (user_id, action, entity_type, entity_id, details, created_at)
                SELECT created_by, 'synapse_status_update', 'order', %s,
                       %s::jsonb, NOW()
                FROM orders WHERE id = %s
            """, (order_id,
                  json.dumps({'old': old_status, 'new': new_status, 'by': 'Synapse API'}),
                  order_id))
        conn.commit()
    return jsonify(ok=True, order_id=order_id, old_status=old_status, new_status=new_status)

# ══════════════════════════════════════════
# USERS / RESELLERS
# ══════════════════════════════════════════

@synapse_bp.route('/users', methods=['GET'])
@require_synapse_key
def get_users():
    search = request.args.get('q', '')
    tier_id = request.args.get('tier_id')
    role = request.args.get('role', 'reseller')
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 50)))
    offset = (page - 1) * per_page
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            conds = ["r.name = %s"]
            params = [role]
            if search:
                conds.append("(u.full_name ILIKE %s OR u.username ILIKE %s OR u.phone ILIKE %s)")
                params += [f'%{search}%', f'%{search}%', f'%{search}%']
            if tier_id:
                conds.append("u.reseller_tier_id = %s")
                params.append(tier_id)
            where = "WHERE " + " AND ".join(conds)
            cur.execute(f"""
                SELECT u.id, u.full_name, u.username, u.phone, u.email,
                       u.province, u.brand_name, u.created_at, u.total_purchases,
                       rt.name AS tier_name, u.reseller_tier_id, u.tier_manual_override
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                {where}
                ORDER BY u.full_name
                LIMIT %s OFFSET %s
            """, params + [per_page, offset])
            users = cur.fetchall()
            cur.execute(f"""
                SELECT COUNT(*) FROM users u JOIN roles r ON r.id=u.role_id {where}
            """, params)
            total = cur.fetchone()['count']
    return jsonify(users=[dict(u) for u in users], total=total, page=page, per_page=per_page)

@synapse_bp.route('/users/<int:user_id>', methods=['GET'])
@require_synapse_key
def get_user_detail(user_id):
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT u.id, u.full_name, u.username, u.phone, u.email,
                       u.address, u.province, u.district, u.subdistrict, u.postal_code,
                       u.brand_name, u.logo_url, u.line_id,
                       u.bank_name, u.bank_account_number, u.bank_account_name,
                       u.created_at, u.total_purchases, u.tier_manual_override,
                       rt.name AS tier_name, rt.id AS tier_id,
                       r.name AS role
                FROM users u
                JOIN roles r ON r.id = u.role_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                WHERE u.id = %s
            """, (user_id,))
            user = cur.fetchone()
            if not user:
                return jsonify(error='User not found'), 404
            cur.execute("""
                SELECT id, order_number, status, final_amount, created_at
                FROM orders WHERE user_id = %s
                ORDER BY created_at DESC LIMIT 10
            """, (user_id,))
            recent_orders = cur.fetchall()
    result = dict(user)
    result['recent_orders'] = [dict(o) for o in recent_orders]
    return jsonify(result)

@synapse_bp.route('/users/<int:user_id>', methods=['PATCH'])
@require_synapse_key
def update_user(user_id):
    data = request.get_json() or {}
    allowed = ['full_name', 'phone', 'email', 'province', 'district', 'subdistrict',
               'postal_code', 'address', 'brand_name', 'line_id',
               'bank_name', 'bank_account_number', 'bank_account_name',
               'reseller_tier_id', 'tier_manual_override']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify(error='No valid fields to update'), 400
    set_clause = ', '.join(f"{k} = %s" for k in updates)
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(f"""
                UPDATE users SET {set_clause}, updated_at = NOW()
                WHERE id = %s
            """, list(updates.values()) + [user_id])
            if cur.rowcount == 0:
                return jsonify(error='User not found'), 404
        conn.commit()
    return jsonify(ok=True, updated=list(updates.keys()))

# ══════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════

@synapse_bp.route('/chat/threads', methods=['GET'])
@require_synapse_key
def get_chat_threads():
    needs_admin = request.args.get('needs_admin', 'false').lower() == 'true'
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(100, int(request.args.get('per_page', 50)))
    offset = (page - 1) * per_page
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            where = "WHERE ct.needs_admin = TRUE" if needs_admin else "WHERE 1=1"
            cur.execute(f"""
                SELECT ct.id, ct.reseller_id, ct.last_message_at,
                       ct.last_message_preview, ct.needs_admin, ct.is_archived,
                       u.full_name, u.username, u.phone,
                       rt.name AS tier_name
                FROM chat_threads ct
                JOIN users u ON u.id = ct.reseller_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                {where}
                ORDER BY ct.last_message_at DESC NULLS LAST
                LIMIT %s OFFSET %s
            """, [per_page, offset])
            threads = cur.fetchall()
    return jsonify(threads=[dict(t) for t in threads])

@synapse_bp.route('/chat/threads/<int:thread_id>/messages', methods=['GET'])
@require_synapse_key
def get_chat_messages(thread_id):
    limit = min(200, int(request.args.get('limit', 50)))
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT cm.id, cm.sender_type, cm.message, cm.created_at,
                       cm.is_read, cm.attachment_url
                FROM chat_messages cm
                WHERE cm.thread_id = %s
                ORDER BY cm.created_at DESC
                LIMIT %s
            """, (thread_id, limit))
            messages = cur.fetchall()
    return jsonify(messages=[dict(m) for m in reversed(messages)])

@synapse_bp.route('/chat/threads/<int:thread_id>/messages', methods=['POST'])
@require_synapse_key
def send_chat_message(thread_id):
    data = request.get_json() or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify(error='message required'), 400
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT reseller_id FROM chat_threads WHERE id = %s", (thread_id,))
            thread = cur.fetchone()
            if not thread:
                return jsonify(error='Thread not found'), 404
            cur.execute("""
                INSERT INTO chat_messages (thread_id, sender_type, message, created_at, is_read)
                VALUES (%s, 'admin', %s, NOW(), FALSE) RETURNING id
            """, (thread_id, message))
            msg_id = cur.fetchone()['id']
            cur.execute("""
                UPDATE chat_threads SET last_message_at = NOW(),
                    last_message_preview = %s, needs_admin = FALSE
                WHERE id = %s
            """, (message[:100], thread_id))
        conn.commit()
    return jsonify(ok=True, message_id=msg_id)

@synapse_bp.route('/chat/threads/<int:thread_id>/resolve', methods=['POST'])
@require_synapse_key
def resolve_chat_thread(thread_id):
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                UPDATE chat_threads SET needs_admin = FALSE WHERE id = %s
            """, (thread_id,))
        conn.commit()
    return jsonify(ok=True)

# ══════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════

@synapse_bp.route('/analytics/summary', methods=['GET'])
@require_synapse_key
def get_analytics_summary():
    days = int(request.args.get('days', 30))
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            # Revenue
            cur.execute("""
                SELECT COALESCE(SUM(final_amount),0) AS revenue,
                       COUNT(*) AS order_count
                FROM orders
                WHERE created_at >= NOW() - INTERVAL '%s days'
                AND status NOT IN ('cancelled','returned','stock_restored')
                AND is_quick_order = FALSE
            """ % days)
            rev = cur.fetchone()
            # Active users
            cur.execute("""
                SELECT COUNT(DISTINCT user_id) AS active_users
                FROM user_events
                WHERE created_at >= NOW() - INTERVAL '%s days'
            """ % days)
            act = cur.fetchone()
            # Total members
            cur.execute("""
                SELECT COUNT(*) AS total FROM users u JOIN roles r ON r.id=u.role_id
                WHERE r.name = 'reseller'
            """)
            total_members = cur.fetchone()['total']
            # Top products
            cur.execute("""
                SELECT oi.product_name, SUM(oi.quantity) AS qty,
                       SUM(oi.subtotal) AS revenue
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.created_at >= NOW() - INTERVAL '%s days'
                AND o.status NOT IN ('cancelled','returned')
                GROUP BY oi.product_name
                ORDER BY revenue DESC LIMIT 5
            """ % days)
            top_products = cur.fetchall()
            # Orders by status
            cur.execute("""
                SELECT status, COUNT(*) AS cnt
                FROM orders
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY status
            """ % days)
            by_status = cur.fetchall()
    return jsonify(
        period_days=days,
        revenue=float(rev['revenue']),
        order_count=rev['order_count'],
        active_users=act['active_users'],
        total_members=total_members,
        top_products=[dict(p) for p in top_products],
        orders_by_status={r['status']: r['cnt'] for r in by_status}
    )

# ══════════════════════════════════════════
# PROMOTIONS & COUPONS
# ══════════════════════════════════════════

@synapse_bp.route('/promotions', methods=['GET'])
@require_synapse_key
def get_promotions():
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT id, name, promotion_type, discount_value, discount_percent,
                       min_order_amount, max_discount_amount,
                       start_date, end_date, is_active,
                       usage_count, max_usage
                FROM promotions
                ORDER BY is_active DESC, end_date DESC
            """)
            rows = cur.fetchall()
    return jsonify(promotions=[dict(r) for r in rows])

@synapse_bp.route('/coupons', methods=['GET'])
@require_synapse_key
def get_coupons():
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT id, code, name, discount_type, discount_value,
                       min_order_amount, max_uses, used_count,
                       valid_from, valid_until, is_active
                FROM coupons
                ORDER BY is_active DESC, valid_until DESC
            """)
            rows = cur.fetchall()
    return jsonify(coupons=[dict(r) for r in rows])

# ══════════════════════════════════════════
# WAREHOUSES
# ══════════════════════════════════════════

@synapse_bp.route('/warehouses', methods=['GET'])
@require_synapse_key
def get_warehouses():
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                SELECT w.id, w.name, w.province, w.address, w.is_active,
                       COUNT(DISTINCT ws.sku_id) AS sku_count,
                       COALESCE(SUM(ws.stock), 0) AS total_stock
                FROM warehouses w
                LEFT JOIN sku_warehouse_stock ws ON ws.warehouse_id = w.id
                GROUP BY w.id
                ORDER BY w.name
            """)
            rows = cur.fetchall()
    return jsonify(warehouses=[dict(r) for r in rows])

# ══════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════

@synapse_bp.route('/notifications', methods=['POST'])
@require_synapse_key
def send_notification():
    data = request.get_json() or {}
    user_id = data.get('user_id')
    title = (data.get('title') or '').strip()
    body = (data.get('body') or '').strip()
    ntype = data.get('type', 'info')
    if not user_id or not title:
        return jsonify(error='user_id and title required'), 400
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("""
                INSERT INTO notifications (user_id, title, message, type, is_read, created_at)
                VALUES (%s, %s, %s, %s, FALSE, NOW()) RETURNING id
            """, (user_id, title, body, ntype))
            nid = cur.fetchone()['id']
        conn.commit()
    return jsonify(ok=True, notification_id=nid)

# ══════════════════════════════════════════
# TIERS (reference data)
# ══════════════════════════════════════════

@synapse_bp.route('/tiers', methods=['GET'])
@require_synapse_key
def get_tiers():
    with get_db_connection() as conn:
        with _cursor(conn) as cur:
            cur.execute("SELECT * FROM reseller_tiers ORDER BY upgrade_threshold")
            rows = cur.fetchall()
    return jsonify(tiers=[dict(r) for r in rows])

# ══════════════════════════════════════════
# HEALTH / SCHEMA INFO
# ══════════════════════════════════════════

@synapse_bp.route('/ping', methods=['GET'])
@require_synapse_key
def ping():
    return jsonify(
        status='ok',
        app='EKG Shops',
        version='1.0',
        endpoints={
            'products':      'GET /api/synapse/products?q=&status=active&page=1',
            'product_detail':'GET /api/synapse/products/<id>',
            'stock':         'GET /api/synapse/stock?low_only=false',
            'update_stock':  'PATCH /api/synapse/stock/<sku_id>  {stock, reason}',
            'warehouse_stock':'GET /api/synapse/stock/warehouse?warehouse_id=',
            'orders':        'GET /api/synapse/orders?status=&days=30&page=1',
            'order_detail':  'GET /api/synapse/orders/<id>',
            'update_order':  'PATCH /api/synapse/orders/<id>/status  {status}',
            'users':         'GET /api/synapse/users?q=&role=reseller&tier_id=',
            'user_detail':   'GET /api/synapse/users/<id>',
            'update_user':   'PATCH /api/synapse/users/<id>  {field:value}',
            'chat_threads':  'GET /api/synapse/chat/threads?needs_admin=false',
            'chat_messages': 'GET /api/synapse/chat/threads/<id>/messages',
            'send_message':  'POST /api/synapse/chat/threads/<id>/messages  {message}',
            'analytics':     'GET /api/synapse/analytics/summary?days=30',
            'promotions':    'GET /api/synapse/promotions',
            'coupons':       'GET /api/synapse/coupons',
            'warehouses':    'GET /api/synapse/warehouses',
            'tiers':         'GET /api/synapse/tiers',
            'notify':        'POST /api/synapse/notifications  {user_id, title, body}',
        }
    )
