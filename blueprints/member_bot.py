from flask import Blueprint, request, jsonify, session, send_file
from database import get_db
from utils import login_required, admin_required, handle_error
import psycopg2.extras
import psycopg2
import os, json, re, threading
from blueprints.bot_cache import _BOT_CACHE, _bot_cache_get, bot_cache_invalidate
from blueprints.push_utils import send_push_notification

member_bot_bp = Blueprint('member_bot', __name__)

@member_bot_bp.route('/api/chat/threads', methods=['GET'])
@login_required
def get_chat_threads():
    """Get chat threads for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        if role_name == 'Reseller':
            # Reseller sees only their own thread
            cursor.execute('''
                SELECT ct.id, ct.reseller_id, ct.last_message_at, ct.last_message_preview,
                       COALESCE(u.full_name, u.username, 'สมาชิก #' || u.id::text) as reseller_name,
                       ct.needs_admin, ct.needs_admin_at,
                       (SELECT COUNT(*) FROM chat_messages cm 
                        WHERE cm.thread_id = ct.id 
                        AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                              WHERE thread_id = ct.id AND user_id = %s), 0)) as unread_count
                FROM chat_threads ct
                JOIN users u ON u.id = ct.reseller_id
                WHERE ct.reseller_id = %s AND ct.is_archived = FALSE
                ORDER BY ct.last_message_at DESC NULLS LAST
            ''', (user_id, user_id))
        else:
            # Admin sees all threads
            show_archived = request.args.get('archived', 'false') == 'true'
            cursor.execute('''
                SELECT ct.id, ct.reseller_id, ct.last_message_at, ct.last_message_preview,
                       COALESCE(u.full_name, u.username, 'สมาชิก #' || u.id::text) as reseller_name,
                       u.username, rt.name as tier_name, u.reseller_tier_id,
                       ct.needs_admin, ct.needs_admin_at, ct.bot_paused_until,
                       (ct.bot_paused_until IS NOT NULL AND ct.bot_paused_until > CURRENT_TIMESTAMP) as bot_paused,
                       (SELECT COUNT(*) FROM chat_messages cm 
                        WHERE cm.thread_id = ct.id 
                        AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                              WHERE thread_id = ct.id AND user_id = %s), 0)) as unread_count
                FROM chat_threads ct
                JOIN users u ON u.id = ct.reseller_id
                LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                WHERE ct.is_archived = %s
                ORDER BY CASE WHEN ct.needs_admin THEN 0 ELSE 1 END, ct.last_message_at DESC NULLS LAST
                LIMIT 300
            ''', (user_id, show_archived))
        
        threads = [dict(row) for row in cursor.fetchall()]
        return jsonify(threads), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/threads/<int:thread_id>/archive', methods=['POST'])
@login_required
def archive_chat_thread(thread_id):
    """Archive a chat thread (admin only)"""
    conn = None
    cursor = None
    try:
        if session.get('role') == 'Reseller':
            return jsonify({'error': 'Only admin can archive threads'}), 403
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_threads SET is_archived = TRUE WHERE id = %s', (thread_id,))
        conn.commit()
        return jsonify({'message': 'Thread archived'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@member_bot_bp.route('/api/chat/threads/<int:thread_id>/unarchive', methods=['POST'])
@login_required  
def unarchive_chat_thread(thread_id):
    """Unarchive a chat thread"""
    conn = None
    cursor = None
    try:
        if session.get('role') == 'Reseller':
            return jsonify({'error': 'Only admin can unarchive threads'}), 403
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE chat_threads SET is_archived = FALSE WHERE id = %s', (thread_id,))
        conn.commit()
        return jsonify({'message': 'Thread unarchived'}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@member_bot_bp.route('/api/chat/threads/<int:thread_id>/reseller-coupon-wallet', methods=['GET'])
@login_required
def get_thread_reseller_coupon_wallet(thread_id):
    """Return wallet status of all coupons for the reseller in this thread (admin only)"""
    conn = None
    cursor = None
    try:
        if session.get('role') == 'Reseller':
            return jsonify({'error': 'Forbidden'}), 403
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({}), 200
        reseller_id = thread['reseller_id']
        cursor.execute('''
            SELECT uc.coupon_id, uc.status, uc.used_at, uc.collected_at,
                   o.order_number as used_in_order_number
            FROM user_coupons uc
            LEFT JOIN orders o ON o.id = uc.used_in_order_id
            WHERE uc.user_id = %s
        ''', (reseller_id,))
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            result[r['coupon_id']] = {
                'status': r['status'],
                'used_at': r['used_at'].isoformat() if r['used_at'] else None,
                'collected_at': r['collected_at'].isoformat() if r['collected_at'] else None,
                'used_in_order_number': r['used_in_order_number']
            }
        return jsonify(result), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@member_bot_bp.route('/api/chat/products/search', methods=['GET'])
@login_required
def search_chat_products():
    """Search products for attaching to chat messages"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        q = request.args.get('q', '').strip()
        reseller_tier_id = request.args.get('tier_id', None, type=int)
        
        # Auto-detect tier for resellers
        if not reseller_tier_id and session.get('role') == 'Reseller':
            cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (session['user_id'],))
            user_row = cursor.fetchone()
            if user_row:
                reseller_tier_id = user_row['reseller_tier_id']
        
        cursor.execute('''
            SELECT p.id, p.name, p.status,
                   (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url,
                   MIN(s.price) as min_price, MAX(s.price) as max_price,
                   b.name as brand_name,
                   COUNT(DISTINCT s.id) as sku_count,
                   COALESCE((SELECT SUM(sws.stock) FROM sku_warehouse_stock sws 
                             JOIN skus sk2 ON sk2.id = sws.sku_id 
                             WHERE sk2.product_id = p.id), 0) as total_stock
            FROM products p
            LEFT JOIN skus s ON s.product_id = p.id
            LEFT JOIN brands b ON b.id = p.brand_id
            WHERE p.status = 'active'
            AND (p.name ILIKE %s OR EXISTS (SELECT 1 FROM skus sk WHERE sk.product_id = p.id AND sk.sku_code ILIKE %s))
            GROUP BY p.id, p.name, p.status, b.name
            ORDER BY p.name
            LIMIT 20
        ''', (f'%{q}%', f'%{q}%'))
        
        products = [dict(row) for row in cursor.fetchall()]
        
        if reseller_tier_id:
            for product in products:
                cursor.execute('''
                    SELECT discount_percent FROM product_tier_pricing 
                    WHERE product_id = %s AND tier_id = %s
                ''', (product['id'], reseller_tier_id))
                tier_price = cursor.fetchone()
                if tier_price and tier_price['discount_percent']:
                    discount = float(tier_price['discount_percent'])
                    product['discount_percent'] = discount
                    if product['min_price']:
                        product['tier_min_price'] = round(float(product['min_price']) * (1 - discount/100), 2)
                    if product['max_price']:
                        product['tier_max_price'] = round(float(product['max_price']) * (1 - discount/100), 2)
                else:
                    product['discount_percent'] = 0
                    product['tier_min_price'] = float(product['min_price']) if product['min_price'] else 0
                    product['tier_max_price'] = float(product['max_price']) if product['max_price'] else 0
                
                if product['min_price']:
                    product['min_price'] = float(product['min_price'])
                if product['max_price']:
                    product['max_price'] = float(product['max_price'])
        else:
            for product in products:
                if product['min_price']:
                    product['min_price'] = float(product['min_price'])
                if product['max_price']:
                    product['max_price'] = float(product['max_price'])
        
        return jsonify(products), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/threads/<int:thread_id>/messages', methods=['GET'])
@login_required
def get_chat_messages(thread_id):
    """Get messages for a thread"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Verify access
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        since_id = request.args.get('since_id', 0, type=int)
        before_id = request.args.get('before_id', 0, type=int)
        limit = request.args.get('limit', 50, type=int)
        
        msg_select = '''
                SELECT cm.id, cm.sender_id, cm.sender_type, cm.content, cm.is_broadcast, cm.created_at, cm.product_id, cm.order_id, cm.coupon_id,
                       COALESCE(cm.is_bot, FALSE) as is_bot,
                       cm.quick_replies,
                       u.full_name as sender_name,
                       r.name as sender_role,
                       (SELECT json_agg(json_build_object('id', ca.id, 'file_url', ca.file_url, 
                        'file_name', ca.file_name, 'file_type', ca.file_type))
                        FROM chat_attachments ca WHERE ca.message_id = cm.id) as attachments
                FROM chat_messages cm
                JOIN users u ON u.id = cm.sender_id
                LEFT JOIN roles r ON r.id = u.role_id
        '''
        if since_id > 0:
            cursor.execute(msg_select + ' WHERE cm.thread_id = %s AND cm.id > %s ORDER BY cm.id ASC LIMIT %s',
                           (thread_id, since_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
        elif before_id > 0:
            cursor.execute(msg_select + ' WHERE cm.thread_id = %s AND cm.id < %s ORDER BY cm.id DESC LIMIT %s',
                           (thread_id, before_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()
        else:
            cursor.execute(msg_select + ' WHERE cm.thread_id = %s ORDER BY cm.id DESC LIMIT %s',
                           (thread_id, limit))
            messages = [dict(row) for row in cursor.fetchall()]
            messages.reverse()
        
        has_more = len(messages) == limit
        
        thread_reseller_id = thread['reseller_id']
        cursor.execute('SELECT reseller_tier_id FROM users WHERE id = %s', (thread_reseller_id,))
        reseller_user = cursor.fetchone()
        reseller_tier_id = reseller_user['reseller_tier_id'] if reseller_user else None
        
        for msg in messages:
            if msg.get('product_id'):
                cursor.execute('''
                    SELECT p.id, p.name,
                           (SELECT pi.image_url FROM product_images pi WHERE pi.product_id = p.id ORDER BY pi.sort_order LIMIT 1) as image_url,
                           MIN(s.price) as min_price, MAX(s.price) as max_price
                    FROM products p
                    LEFT JOIN skus s ON s.product_id = p.id
                    WHERE p.id = %s
                    GROUP BY p.id, p.name
                ''', (msg['product_id'],))
                product = cursor.fetchone()
                if product:
                    product_data = dict(product)
                    if product_data['min_price']:
                        product_data['min_price'] = float(product_data['min_price'])
                    if product_data['max_price']:
                        product_data['max_price'] = float(product_data['max_price'])
                    
                    product_data['discount_percent'] = 0
                    product_data['tier_min_price'] = product_data.get('min_price') or 0
                    product_data['tier_max_price'] = product_data.get('max_price') or 0
                    
                    if reseller_tier_id:
                        cursor.execute('''
                            SELECT discount_percent FROM product_tier_pricing
                            WHERE product_id = %s AND tier_id = %s
                        ''', (msg['product_id'], reseller_tier_id))
                        tier_info = cursor.fetchone()
                        if tier_info and tier_info['discount_percent'] and float(tier_info['discount_percent']) > 0:
                            discount = float(tier_info['discount_percent'])
                            product_data['discount_percent'] = discount
                            if product_data['min_price']:
                                product_data['tier_min_price'] = round(product_data['min_price'] * (1 - discount/100), 2)
                            if product_data['max_price']:
                                product_data['tier_max_price'] = round(product_data['max_price'] * (1 - discount/100), 2)
                    
                    msg['product'] = product_data
            if msg.get('order_id'):
                cursor.execute('''
                    SELECT o.id, o.order_number, o.status, o.total_amount, o.discount_amount,
                           o.shipping_fee, o.final_amount,
                           json_agg(json_build_object(
                               'product_name', oi.product_name,
                               'quantity', oi.quantity,
                               'subtotal', oi.subtotal,
                               'image_url', (SELECT pi.image_url FROM product_images pi
                                             JOIN products p2 ON p2.id = pi.product_id
                                             JOIN skus s2 ON s2.product_id = p2.id
                                             WHERE s2.id = oi.sku_id
                                             ORDER BY pi.sort_order LIMIT 1)
                           ) ORDER BY oi.id) as items
                    FROM orders o
                    LEFT JOIN order_items oi ON oi.order_id = o.id
                    WHERE o.id = %s
                    GROUP BY o.id
                ''', (msg['order_id'],))
                order_row = cursor.fetchone()
                if order_row:
                    od = dict(order_row)
                    od['total_amount'] = float(od['total_amount'] or 0)
                    od['discount_amount'] = float(od['discount_amount'] or 0)
                    od['shipping_fee'] = float(od['shipping_fee'] or 0)
                    od['final_amount'] = float(od['final_amount'] or 0)
                    msg['order'] = od
            if msg.get('coupon_id'):
                cursor.execute('''
                    SELECT id, code, name, discount_type, discount_value, max_discount, min_spend, end_date
                    FROM coupons WHERE id = %s
                ''', (msg['coupon_id'],))
                coupon_row = cursor.fetchone()
                if coupon_row:
                    cd = dict(coupon_row)
                    cd['discount_value'] = float(cd['discount_value'] or 0)
                    cd['max_discount'] = float(cd['max_discount'] or 0) if cd['max_discount'] else None
                    cd['min_spend'] = float(cd['min_spend'] or 0) if cd['min_spend'] else None
                    cd['end_date'] = cd['end_date'].isoformat() if cd['end_date'] else None
                    msg['coupon'] = cd
        
        # Mark as read
        if messages:
            last_message_id = messages[-1]['id']
            cursor.execute('''
                INSERT INTO chat_read_status (thread_id, user_id, last_read_message_id, last_read_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (thread_id, user_id) 
                DO UPDATE SET last_read_message_id = GREATEST(chat_read_status.last_read_message_id, %s),
                              last_read_at = CURRENT_TIMESTAMP
            ''', (thread_id, user_id, last_message_id, last_message_id))
            conn.commit()
        
        other_last_read = 0
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT COALESCE(MAX(last_read_message_id), 0) as last_read
                FROM chat_read_status 
                WHERE thread_id = %s AND user_id != %s
            ''', (thread_id, user_id))
        else:
            cursor.execute('''
                SELECT COALESCE(last_read_message_id, 0) as last_read
                FROM chat_read_status 
                WHERE thread_id = %s AND user_id = %s
            ''', (thread_id, thread_reseller_id))
        read_row = cursor.fetchone()
        if read_row:
            other_last_read = read_row['last_read']
        
        return jsonify({'messages': messages, 'other_last_read': other_last_read, 'has_more': has_more}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def _bot_save_message(cursor, conn, thread_id, bot_user_id, text, quick_replies=None, product_id=None):
    """Save one bot message and return its id + created_at"""
    import json as _json
    qr_json = _json.dumps(quick_replies, ensure_ascii=False) if quick_replies else None
    cursor.execute('''
        INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, product_id, is_bot, quick_replies)
        VALUES (%s, %s, 'admin', %s, %s, TRUE, %s::jsonb) RETURNING id, created_at
    ''', (thread_id, bot_user_id, text, product_id, qr_json))
    row = cursor.fetchone()
    preview = f'🤖 {text[:80]}' if text else '🤖 [สินค้า]'
    cursor.execute('''
        UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s WHERE id = %s
    ''', (preview[:100], thread_id))
    return row


# ── Bot in-memory cache (per worker process) ──────────────────────────────
# ────────────────────────────────────────────────────────────────────────────


def _bot_chat_reply(thread_id, reseller_id, user_message_text, conn):
    """Generate and save an auto-reply from the bot using Gemini Flash Lite."""
    import json as _json, re as _re
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Bot settings (cached 10 min — Admin rarely changes this)
        def _fetch_settings():
            cursor.execute('SELECT * FROM agent_settings WHERE id = 1')
            return cursor.fetchone() or {}
        settings = _bot_cache_get('bot_settings', 600, _fetch_settings)
        bot_name = settings.get('bot_chat_name') or 'น้องนุ่น'
        bot_enabled = settings.get('bot_chat_enabled', True)
        extra_persona = settings.get('bot_chat_persona') or ''
        if not bot_enabled:
            return []

        # 1b. Load active training examples (Q&A pairs)
        cursor.execute('''
            SELECT question_pattern, answer_template FROM bot_training_examples
            WHERE is_active = TRUE ORDER BY sort_order, id
        ''')
        training_rows = cursor.fetchall()
        training_block = ''
        if training_rows:
            qa_lines = '\n'.join(
                f'Q: {r["question_pattern"]}\nA: {r["answer_template"]}'
                for r in training_rows
            )
            training_block = f'\n\n⚡ กฎเพิ่มเติมจาก Admin (ความสำคัญสูงสุด — ใช้ข้อมูลนี้แทนที่ค่า default ด้านล่างเสมอ หากมีข้อมูลตรงกัน):\n{qa_lines}'

        # 2. Check if bot is paused (admin replied recently)
        cursor.execute('SELECT bot_paused_until FROM chat_threads WHERE id = %s', (thread_id,))
        trow = cursor.fetchone()
        if trow and trow.get('bot_paused_until'):
            from datetime import datetime as _dt
            if trow['bot_paused_until'] > _dt.utcnow():
                return []

        # 3. Get bot user id (Super Admin account)
        cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name='Super Admin') ORDER BY id LIMIT 1")
        admin_row = cursor.fetchone()
        if not admin_row:
            return []
        bot_user_id = admin_row['id']

        # 4. Session state
        cursor.execute('SELECT bot_session_data FROM chat_threads WHERE id = %s', (thread_id,))
        thread_row = cursor.fetchone()
        session_data = {}
        if thread_row and thread_row.get('bot_session_data'):
            try:
                sd = thread_row['bot_session_data']
                session_data = sd if isinstance(sd, dict) else _json.loads(sd)
            except Exception:
                session_data = {}

        # 4b. Load customer measurements — session first, fallback to permanent DB storage
        from datetime import datetime as _dt, timedelta as _td
        _ordering_for = session_data.get('ordering_for') or 'self'  # 'self' or friend name
        _meas = session_data.get('measurements') or {}
        _meas_age_ok = False
        if _meas.get('measured_at'):
            try:
                _meas_time = _dt.fromisoformat(_meas['measured_at'])
                _meas_age_ok = (_dt.utcnow() - _meas_time) < _td(hours=24)
            except Exception:
                pass
        if not _meas_age_ok:
            _meas = {}
            session_data.pop('measurements', None)
            # Fallback: load from permanent body_measurements in users table
            cursor.execute('SELECT body_measurements FROM users WHERE id = %s', (reseller_id,))
            _bm_row = cursor.fetchone()
            if _bm_row and _bm_row.get('body_measurements'):
                _bm = _bm_row['body_measurements'] if isinstance(_bm_row['body_measurements'], dict) else {}
                if _ordering_for == 'self':
                    _meas = _bm.get('self') or {}
                else:
                    _meas = (_bm.get('friends') or {}).get(_ordering_for) or {}
        customer_chest = _meas.get('chest')
        customer_waist = _meas.get('waist')
        customer_hips  = _meas.get('hips')
        # Build readable measurements string for prompt
        _meas_parts = []
        if customer_chest: _meas_parts.append(f"รอบอก {customer_chest} นิ้ว")
        if customer_waist: _meas_parts.append(f"รอบเอว {customer_waist} นิ้ว")
        if customer_hips:  _meas_parts.append(f"รอบสะโพก {customer_hips} นิ้ว")
        # Load self_name and friends from body_measurements (one query covers both)
        _self_name = 'self'
        _all_friends_text = '(ยังไม่มี)'
        try:
            cursor.execute('SELECT body_measurements FROM users WHERE id = %s', (reseller_id,))
            _bm2 = cursor.fetchone()
            if _bm2 and _bm2.get('body_measurements'):
                _bmd = _bm2['body_measurements'] if isinstance(_bm2['body_measurements'], dict) else {}
                _self_name = _bmd.get('self_name') or 'self'
                _fr = _bmd.get('friends') or {}
                if _fr:
                    _all_friends_text = '\n'.join(
                        f'- {fn}: อก={fd.get("chest","?")} เอว={fd.get("waist","?")} สะโพก={fd.get("hips","?")}'
                        for fn, fd in _fr.items()
                    )
        except Exception:
            pass
        _self_display = _self_name if _self_name != 'self' else 'ตัวเอง (ยังไม่ทราบชื่อ)'
        _ordering_for_label = f'ของตัวเอง ({_self_display})' if _ordering_for == 'self' else f'ของเพื่อน "{_ordering_for}"'
        measurements_text = (', '.join(_meas_parts) + f' ({_ordering_for_label})') if _meas_parts else '(ยังไม่มีข้อมูล)'

        # 5. Recent conversation history (last 8 messages)
        cursor.execute('''
            SELECT sender_type, COALESCE(cm.is_bot, FALSE) as is_bot, content
            FROM chat_messages cm
            WHERE thread_id = %s AND content IS NOT NULL AND content != ''
            ORDER BY id DESC LIMIT 8
        ''', (thread_id,))
        history_rows = list(reversed(cursor.fetchall()))
        # ถือว่า "ข้อความแรก" ถ้าบอทยังไม่เคยตอบในประวัติล่าสุด (8 ข้อความ)
        is_first_message = not any(h.get('is_bot') for h in history_rows)
        # Extract product IDs already shown in reseller chat history (for "show more" pagination)
        _shown_hist_ids = set()
        for _sh in history_rows:
            for _sid in _re.findall(r'\bID:(\d+)\b', str(_sh.get('content', ''))):
                _shown_hist_ids.add(int(_sid))
        _SHOW_MORE_KW = ('ดูเพิ่ม', 'แสดงเพิ่ม', 'เพิ่มเติม', 'ดูทั้งหมด', 'อีกบ้าง', 'แสดงอีก',
                         'ต้องการดูเพิ่ม', 'มีอีกไหม', 'ดูเพิ่มเติม', 'อยากดูเพิ่ม', 'ดูสินค้าเพิ่ม')
        _is_show_more_r = any(kw in user_message_text for kw in _SHOW_MORE_KW)
        _remaining_count_r = 0
        history_text = ''
        for h in history_rows:
            who = f'🤖 {bot_name}' if h.get('is_bot') else ('👤 สมาชิก' if h['sender_type'] == 'reseller' else '👩‍💼 Admin')
            history_text += f'{who}: {(h["content"] or "")[:200]}\n'

        # 6. Reseller tier info (for tier pricing)
        cursor.execute('''
            SELECT u.reseller_tier_id, rt.name as tier_name, rt.level_rank, u.full_name
            FROM users u LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
            WHERE u.id = %s
        ''', (reseller_id,))
        reseller_row = cursor.fetchone()
        reseller_tier_id = reseller_row['reseller_tier_id'] if reseller_row else None
        reseller_tier_name = reseller_row['tier_name'] if reseller_row else 'Bronze'
        reseller_tier_rank = reseller_row['level_rank'] if reseller_row else 1
        reseller_name = reseller_row['full_name'] if reseller_row else ''

        # 6a. All tiers — build tier info text for bot
        cursor.execute('SELECT id, name, level_rank, upgrade_threshold, is_manual_only FROM reseller_tiers ORDER BY level_rank')
        all_tiers = cursor.fetchall()
        _tier_lines = []
        for t in all_tiers:
            _is_current = (t['id'] == reseller_tier_id)
            _marker = ' ← เกรดปัจจุบัน' if _is_current else ''
            if t['level_rank'] == 1 or t['upgrade_threshold'] == 0:
                _cond = 'เกรดเริ่มต้น'
            elif t['is_manual_only']:
                _cond = f'ยอดสะสมถึง ฿{t["upgrade_threshold"]:,.0f} (ต้องให้ Admin อัปเกรด)'
            else:
                _cond = f'ยอดสะสมถึง ฿{t["upgrade_threshold"]:,.0f}'
            _tier_lines.append(f'  • {t["name"]}: {_cond}{_marker}')
        tier_info_text = '\n'.join(_tier_lines) if _tier_lines else '(ไม่มีข้อมูล)'

        # Find next tier
        _next_tier = next((t for t in all_tiers if t['level_rank'] > reseller_tier_rank), None)
        if _next_tier and not _next_tier['is_manual_only']:
            _next_tier_text = f'อัปเกรดเป็น {_next_tier["name"]} ได้เมื่อยอดสะสมถึง ฿{_next_tier["upgrade_threshold"]:,.0f}'
        elif _next_tier and _next_tier['is_manual_only']:
            _next_tier_text = f'อัปเกรดเป็น {_next_tier["name"]} ต้องให้ Admin อัปเกรดให้ (ยอดสะสม ฿{_next_tier["upgrade_threshold"]:,.0f})'
        else:
            _next_tier_text = 'อยู่ในเกรดสูงสุดแล้ว'

        # 6b. Reseller orders — active (not done) + last 3 completed
        _STATUS_TH = {
            'pending_payment': 'รอชำระเงิน',
            'pending': 'รอดำเนินการ',
            'payment_review': 'ตรวจสอบหลักฐานชำระเงิน',
            'confirmed': 'ยืนยันแล้ว กำลังเตรียมสินค้า',
            'processing': 'กำลังผลิต/เตรียมสินค้า',
            'shipped': 'จัดส่งแล้ว',
            'delivered': 'ส่งถึงผู้รับแล้ว',
            'cancelled': 'ยกเลิก',
            'refunded': 'คืนเงินแล้ว',
        }
        def _fmt_order_block(o, label=''):
            status_th = _STATUS_TH.get(o.get('status', ''), o.get('status', '-'))
            lines = [f"  {'[' + label + '] ' if label else ''}ออเดอร์ #{o.get('order_number','-')}"]
            lines.append(f"    สถานะ: {status_th}")
            lines.append(f"    วันสั่ง: {o.get('order_date', '-')}")
            if o.get('paid_at'):
                lines.append(f"    ชำระเงิน: {str(o['paid_at'])[:16]}")
            if o.get('shipped_at'):
                lines.append(f"    จัดส่ง: {str(o['shipped_at'])[:16]}")
            if o.get('delivered_at'):
                lines.append(f"    ส่งถึง: {str(o['delivered_at'])[:16]}")
            if o.get('tracking_number'):
                sp = f" ({o['shipping_provider']})" if o.get('shipping_provider') else ''
                lines.append(f"    เลขพัสดุ: {o['tracking_number']}{sp}")
            if o.get('final_amount'):
                lines.append(f"    ยอดรวม: ฿{float(o['final_amount']):,.0f}")
            if o.get('items'):
                lines.append(f"    สินค้า: {o['items']}")
            return '\n'.join(lines)

        cursor.execute('''
            SELECT o.id, o.order_number, o.status, o.final_amount,
                   o.created_at::date as order_date, o.paid_at,
                   (SELECT string_agg(oi.product_name || ' x' || oi.quantity::text, ', ')
                    FROM order_items oi WHERE oi.order_id = o.id) as items,
                   (SELECT os2.tracking_number FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as tracking_number,
                   (SELECT os2.shipping_provider FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as shipping_provider,
                   (SELECT os2.shipped_at FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as shipped_at,
                   (SELECT os2.delivered_at FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as delivered_at
            FROM orders o
            WHERE o.user_id = %s
              AND o.status NOT IN ('delivered', 'cancelled', 'refunded')
            ORDER BY o.id DESC LIMIT 10
        ''', (reseller_id,))
        _active_orders = cursor.fetchall()

        cursor.execute('''
            SELECT o.id, o.order_number, o.status, o.final_amount,
                   o.created_at::date as order_date, o.paid_at,
                   (SELECT string_agg(oi.product_name || ' x' || oi.quantity::text, ', ')
                    FROM order_items oi WHERE oi.order_id = o.id) as items,
                   (SELECT os2.tracking_number FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as tracking_number,
                   (SELECT os2.shipping_provider FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as shipping_provider,
                   (SELECT os2.shipped_at FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as shipped_at,
                   (SELECT os2.delivered_at FROM order_shipments os2
                    WHERE os2.order_id = o.id ORDER BY os2.id DESC LIMIT 1) as delivered_at
            FROM orders o
            WHERE o.user_id = %s
              AND o.status IN ('delivered', 'cancelled', 'refunded')
            ORDER BY o.id DESC LIMIT 3
        ''', (reseller_id,))
        _done_orders = cursor.fetchall()

        _active_text = '\n'.join(_fmt_order_block(o) for o in _active_orders) if _active_orders else '  (ไม่มีออเดอร์ที่ค้างอยู่)'
        _done_text = '\n'.join(_fmt_order_block(o) for o in _done_orders) if _done_orders else '  (ไม่มี)'
        orders_text = f"[ออเดอร์ที่ยังไม่จบ]\n{_active_text}\n\n[ออเดอร์ที่จบแล้ว — 3 รายการล่าสุด]\n{_done_text}"

        # 6c. Pending restock alerts for this member
        cursor.execute('''
            SELECT ra.id, ra.size, ra.product_name,
                   COALESCE(p.name, ra.product_name) as pname,
                   ra.created_at::date as alert_date
            FROM restock_alerts ra
            LEFT JOIN products p ON p.id = ra.product_id
            WHERE ra.user_id = %s AND ra.status = 'pending'
            ORDER BY ra.created_at ASC
        ''', (reseller_id,))
        _pending_alerts = cursor.fetchall()
        if _pending_alerts:
            _alert_lines = []
            for _a in _pending_alerts:
                _size_part = f' ไซส์ {_a["size"]}' if _a.get('size') else ''
                _alert_lines.append(f"  - {_a['pname']}{_size_part} (ขอแจ้งเมื่อ {_a['alert_date']})")
            _restock_pending_text = '\n'.join(_alert_lines)
        else:
            _restock_pending_text = '  (ไม่มีรายการรอแจ้งเตือนสต็อก)'

        # 7. Active promotions (cached 5 min)
        def _fetch_promos():
            try:
                conn.rollback()  # clear any aborted-transaction state
                _pc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                _pc.execute('''
                    SELECT name, promo_type, reward_type, reward_value, condition_min_spend,
                           start_date, end_date FROM promotions
                    WHERE is_active = TRUE AND (end_date IS NULL OR end_date >= CURRENT_DATE)
                    LIMIT 5
                ''')
                _rows = _pc.fetchall()
                _pc.close()
                return _rows
            except Exception:
                import traceback; traceback.print_exc()
                return None  # don't cache on error — retry next request
        promos = _bot_cache_get('promotions', 300, _fetch_promos)
        if promos:
            _promo_lines = []
            for p in promos:
                _rv = p['reward_value']
                if p['reward_type'] in ('percent', 'discount_percent'):
                    _reward_str = f"ลด {_rv:.0f}%"
                elif p['reward_type'] in ('fixed', 'fixed_discount', 'fixed_amount'):
                    _reward_str = f"ลด ฿{_rv:.0f}"
                elif 'shipping' in (p['reward_type'] or ''):
                    _reward_str = "ส่งฟรี"
                else:
                    _reward_str = f"ลด {_rv:.0f}%"
                _min = f" (ซื้อขั้นต่ำ ฿{p['condition_min_spend']:.0f})" if p.get('condition_min_spend') else ""
                _p_end = p.get('end_date')
                _end = f" หมดเขต {_p_end.strftime('%d/%m/%Y') if hasattr(_p_end,'strftime') else str(_p_end)[:10]}" if _p_end else ""
                _promo_lines.append(f"  • {p['name']}: {_reward_str}{_min}{_end}")
            promos_text = '\n'.join(_promo_lines)
        else:
            promos_text = '  (ไม่มีโปรโมชั่น)'

        # 7b. Reseller's own coupons (ready to use)
        cursor.execute('''
            SELECT c.code, c.name, c.discount_type, c.discount_value, c.min_spend,
                   c.max_discount, c.end_date, uc.status
            FROM user_coupons uc
            JOIN coupons c ON c.id = uc.coupon_id
            WHERE uc.user_id = %s AND uc.status = 'ready'
              AND (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
            ORDER BY c.end_date NULLS LAST
            LIMIT 10
        ''', (reseller_id,))
        reseller_coupons = cursor.fetchall()
        if reseller_coupons:
            _cpn_lines = []
            for cp in reseller_coupons:
                _dv = cp['discount_value']
                if cp['discount_type'] == 'percent':
                    _d_str = f"ลด {_dv:.0f}%"
                elif cp['discount_type'] == 'fixed':
                    _d_str = f"ลด ฿{_dv:.0f}"
                elif cp['discount_type'] == 'free_shipping':
                    _d_str = "ส่งฟรี"
                else:
                    _d_str = str(_dv)
                _min_s = f" ซื้อขั้นต่ำ ฿{cp['min_spend']:.0f}" if cp.get('min_spend') else ""
                _max_d = f" (ลดสูงสุด ฿{cp['max_discount']:.0f})" if cp.get('max_discount') else ""
                _end_d = cp.get('end_date')
                _exp = f" หมดอายุ {_end_d.strftime('%d/%m/%Y') if hasattr(_end_d,'strftime') else str(_end_d)[:10]}" if _end_d else ""
                _cpn_lines.append(f"  • โค้ด [{cp['code']}] {cp['name']}: {_d_str}{_min_s}{_max_d}{_exp}")
            coupons_text = '\n'.join(_cpn_lines)
        else:
            coupons_text = '  (สมาชิกยังไม่มีคูปอง)'

        # 7c. Shipping rates — reuse guest bot cache ('shipping_data' key, format: {'rates':[], 'promos':[]})
        def _member_fetch_shipping():
            try:
                conn.rollback()  # clear any aborted-transaction state
                _mc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                _mc.execute("SELECT min_weight, max_weight, rate FROM shipping_weight_rates ORDER BY sort_order")
                _rates = _mc.fetchall()
                _mc.execute("SELECT name, promo_type, min_order_value FROM shipping_promotions WHERE is_active=TRUE AND (end_date IS NULL OR end_date >= NOW()) LIMIT 3")
                _promos = _mc.fetchall()
                _mc.close()
                if not _rates:
                    return None  # don't cache empty — will retry next request
                return {'rates': _rates, 'promos': _promos}
            except Exception:
                import traceback; traceback.print_exc()
                return None  # don't cache on error — will retry next request
        if 'shipping_data' not in _BOT_CACHE:
            _BOT_CACHE['shipping_data'] = {'data': None, 'expires': 0}
        _member_ship_data = _bot_cache_get('shipping_data', 3600, _member_fetch_shipping)
        _member_ship_rates = (_member_ship_data or {}).get('rates', [])
        _member_ship_promos = (_member_ship_data or {}).get('promos', [])
        _member_ship_text = ''
        if _member_ship_rates:
            _msl = []
            for _mr in _member_ship_rates:
                _mmax = f"{_mr['max_weight']}g" if _mr.get('max_weight') else 'ขึ้นไป'
                _msl.append(f"{_mr['min_weight']}-{_mmax}: {_mr['rate']:.0f} บาท")
            _member_ship_text = 'อัตราค่าส่ง: ' + ' | '.join(_msl[:5])
        if _member_ship_promos:
            for _msp in _member_ship_promos:
                if _msp.get('promo_type') == 'free_shipping' and _msp.get('min_order_value'):
                    _member_ship_text += f"\n🎁 ส่งฟรีเมื่อซื้อครบ ฿{float(_msp['min_order_value']):.0f}"
        if not _member_ship_text:
            _member_ship_text = 'ค่าส่งขึ้นอยู่กับน้ำหนักสินค้า สอบถามเพิ่มเติมได้ในแชทนี้ค่ะ'

        # 8. Product search based on current session or message keywords
        # Safely cast to int — Gemini sometimes stores text like "เสื้อพยาบาล" instead of an integer
        def _safe_int(v):
            try: return int(v) if v is not None else None
            except (ValueError, TypeError): return None

        current_cat_id = _safe_int(session_data.get('category_id'))
        current_product_id = _safe_int(session_data.get('current_product_id'))
        desired_size = session_data.get('desired_size')

        # ── Context-switch detection ───────────────────────────────────────
        # If user's message doesn't reference the current product at all but
        # DOES match a different product → clear context so keyword search runs.
        # _ngram_cleared_context: tracked for Fix 3 (backend AI state validation)
        _ngram_cleared_context = False
        if current_product_id:
            cursor.execute('SELECT name FROM products WHERE id = %s', (current_product_id,))
            _cp_row = cursor.fetchone()
            _cp_name = (_cp_row['name'] if _cp_row else '') or ''

            # Stop words: generic domain words common to most products — remove before N-gram
            # so they don't accidentally match other product names and trigger false context switch
            _NGRAM_STOP = {'พยาบาล', 'ekg', 'ekgshops', 'ekgshop', 'ขาว', 'สีขาว', 'ชุด',
                           'เสื้อ', 'ผ้า', 'ใส่', 'ราคา', 'ไซส์', 'size', 'แบบ', 'สี', 'รุ่น'}
            # Also skip context switch if message looks like a follow-up/property question
            _FOLLOWUP_KW = ('ยาว', 'แน่น', 'หลวม', 'กว้าง', 'ใส่ได้', 'เนื้อผ้า', 'ผ้ายืด',
                            'ผ้าไม่ยืด', 'ซิป', 'ซับใน', 'ราคา', 'ส่วนลด', 'สต็อก', 'เหลือ',
                            'ตารางไซส์', 'วัดตัว', 'อก', 'เอว', 'สะโพก', 'ส่วนสูง',
                            'ส่งได้ไหม', 'ค่าส่ง', 'นัด', 'ยืนยัน', 'สั่ง', 'โอน')
            _is_followup = any(kw in user_message_text for kw in _FOLLOWUP_KW)

            if not _is_followup:
                _msg_words_raw = user_message_text.split()
                _msg_words_filtered = [w for w in _msg_words_raw if w.lower() not in _NGRAM_STOP]
                _msg_c = ''.join(_msg_words_filtered) if _msg_words_filtered else ''.join(_msg_words_raw)
                if len(_msg_c) >= 4:
                    _msg_ngs = set()
                    for _nl in (6, 5, 4):
                        for _i in range(len(_msg_c) - _nl + 1):
                            _msg_ngs.add(_msg_c[_i:_i + _nl])
                    _hits_current = sum(1 for ng in _msg_ngs if ng in _cp_name)
                    # Generic-hit guard: N-gram hits that match many products are too generic
                    if _hits_current > 0:
                        _has_specific = False
                        for _hng in [ng for ng in _msg_ngs if ng in _cp_name]:
                            cursor.execute(
                                "SELECT COUNT(*) as cnt FROM products WHERE status='active' AND name ILIKE %s",
                                (f'%{_hng}%',)
                            )
                            if (_safe_int((cursor.fetchone() or {}).get('cnt')) or 0) <= 3:
                                _has_specific = True
                                break
                        if not _has_specific:
                            _hits_current = 0
                    if _hits_current == 0 and _msg_ngs:
                        # Only clear context if a SIGNIFICANT N-gram (>=5 chars) matches another product
                        # This prevents short/generic N-grams from causing false context switches
                        _significant_ngs = [ng for ng in sorted(_msg_ngs, key=len, reverse=True)
                                            if len(ng) >= 5][:6]
                        for _ng in _significant_ngs:
                            cursor.execute(
                                "SELECT id FROM products WHERE status='active' AND id != %s AND name ILIKE %s LIMIT 1",
                                (current_product_id, f'%{_ng}%')
                            )
                            if cursor.fetchone():
                                current_product_id = None
                                current_cat_id = None
                                _ngram_cleared_context = True
                                break

        def _fmt_product_row(pr, detailed=False):
            brand = pr.get('brand_name') or ''
            cat = pr.get('cat_name') or ''
            options_str = pr.get('options_summary') or ''
            sku_info = pr.get('sku_info') or ''
            price = pr.get('min_price') or 0
            tier_price = pr.get('tier_price') or 0
            tier_disc = float(pr.get('tier_discount_pct') or 0)
            bot_desc = pr.get('bot_description') or ''
            if tier_disc > 0 and tier_price > 0:
                line = f"  - ID:{pr['id']} [{brand}] {pr['name']} ราคาปกติ฿{price:.0f} → ราคาสมาชิก{reseller_tier_name}฿{tier_price:.0f} (ส่วนลด{tier_disc:.0f}%)"
            else:
                line = f"  - ID:{pr['id']} [{brand}] {pr['name']} ราคาเริ่ม฿{price:.0f} (ยังไม่มีส่วนลดพิเศษสำหรับเกรด{reseller_tier_name})"
            if cat:
                line += f" หมวด:{cat}"
            if sku_info:
                line += f" ไซส์/สต็อก:{sku_info}"
            if options_str:
                line += f" สี/ลาย:{options_str}"
            if bot_desc:
                line += f" ({bot_desc})"
            if detailed and pr.get('size_chart_image_url'):
                line += " [มีตารางไซส์]"
            return line + '\n'

        # Base SELECT — uses sku_values_map for size label, falls back to sku_code + stock
        _SIZE_OPT_NAMES = ('ไซส์', 'size', 'sz', 'ขนาด')
        _product_base_select = """
            SELECT p.id, p.name, p.bot_description, p.size_chart_image_url,
                   b.name as brand_name,
                   (SELECT c2.name FROM categories c2
                    JOIN product_categories pc2 ON pc2.category_id = c2.id
                    WHERE pc2.product_id = p.id LIMIT 1) as cat_name,
                   MIN(s.price) as min_price,
                   ROUND(MIN(s.price) * (1 - COALESCE(
                       (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                        WHERE ptp.product_id = p.id AND ptp.tier_id = {tier_id}), 0
                   ) / 100), 0) as tier_price,
                   COALESCE(
                       (SELECT ptp2.discount_percent FROM product_tier_pricing ptp2
                        WHERE ptp2.product_id = p.id AND ptp2.tier_id = {tier_id}), 0
                   ) as tier_discount_pct,
                   COALESCE(
                       NULLIF((SELECT STRING_AGG(ov2.value || ':' || s2.stock::text, ' | ' ORDER BY ov2.value)
                        FROM skus s2
                        JOIN sku_values_map svm2 ON svm2.sku_id = s2.id
                        JOIN option_values ov2 ON ov2.id = svm2.option_value_id
                        JOIN options o2 ON o2.id = ov2.option_id
                        WHERE s2.product_id = p.id
                          AND LOWER(o2.name) IN ('ไซส์','size','sz','ขนาด')), ''),
                       STRING_AGG(DISTINCT s.sku_code || ':' || s.stock::text, ' | ')
                   ) as sku_info,
                   (SELECT STRING_AGG(DISTINCT ov3.value, '/' ORDER BY ov3.value)
                    FROM options o3 JOIN option_values ov3 ON ov3.option_id = o3.id
                    WHERE o3.product_id = p.id
                      AND LOWER(o3.name) NOT IN ('ไซส์','size','sz','ขนาด')) as options_summary
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            JOIN skus s ON s.product_id = p.id
        """
        # Inject reseller tier_id safely (integer only, not user input)
        _safe_tier_id = int(reseller_tier_id) if reseller_tier_id else 0
        _product_base_select = _product_base_select.replace('{tier_id}', str(_safe_tier_id))

        products_text = ''
        if current_cat_id:
            cursor.execute(_product_base_select + '''
                JOIN product_categories pc ON pc.product_id = p.id
                WHERE pc.category_id = %s AND p.status = 'active'
                GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
                LIMIT 10
            ''', (current_cat_id,))
            prods = cursor.fetchall()
            for pr in prods:
                products_text += _fmt_product_row(pr)
        elif current_product_id:
            cursor.execute(_product_base_select + '''
                WHERE p.id = %s
                GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
            ''', (current_product_id,))
            pr = cursor.fetchone()
            if pr:
                products_text = _fmt_product_row(pr, detailed=True)
        else:
            # IDLE state: keyword search — handles Thai text (no spaces between words)
            import re as _re2

            _prod_where = '''
                WHERE p.status = 'active'
                  AND (p.name ILIKE %s OR p.description ILIKE %s OR p.bot_description ILIKE %s OR p.keywords ILIKE %s OR b.name ILIKE %s)
                GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
                LIMIT 15
            '''
            prods = []
            seen_ids = set()

            def _run_kw_search(kw, limit=15):
                """Search by a single keyword and merge into prods/seen_ids."""
                pat = f'%{kw}%'
                cursor.execute(_product_base_select + f'''
                    WHERE p.status = 'active'
                      AND (p.name ILIKE %s OR p.description ILIKE %s OR p.bot_description ILIKE %s OR p.keywords ILIKE %s OR b.name ILIKE %s)
                    GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
                    LIMIT {limit}
                ''', (pat, pat, pat, pat, pat))
                for _pr in cursor.fetchall():
                    if _pr['id'] not in seen_ids:
                        seen_ids.add(_pr['id'])
                        prods.append(_pr)

            # Step 1: split on whitespace (works when user typed with spaces)
            space_kws = [w for w in _re2.findall(r'\S+', user_message_text) if len(w) >= 3]
            if len(space_kws) > 1:
                # Multiple space-separated words — try combined then each word
                _run_kw_search(' '.join(space_kws[:5]))
                if not prods:
                    for _kw in space_kws[:4]:
                        _run_kw_search(_kw, limit=5)
            elif space_kws:
                # Single long word (typical Thai: no spaces) — try whole, then N-grams
                _run_kw_search(space_kws[0])

            # Step 2: N-gram fallback — extract overlapping 5-6 char chunks from message
            # Handles Thai text like "มีเสื้อกาวน์จำหน่ายไหม" → "เสื้อกาวน์" → matches product
            if not prods:
                _msg_clean = ''.join(user_message_text.split())
                _ngrams_tried = set()
                for _ng_len in (6, 5, 4):
                    if prods:
                        break
                    for _i in range(len(_msg_clean) - _ng_len + 1):
                        _ng = _msg_clean[_i:_i + _ng_len]
                        if _ng not in _ngrams_tried:
                            _ngrams_tried.add(_ng)
                            _run_kw_search(_ng, limit=15)
                        if prods:
                            break

            # Step 3: Fallback — load all active products for generic/broad queries
            # e.g. "ขายอะไรบ้าง", "มีสินค้าอะไรบ้าง", "ดูทั้งหมด"
            if not prods:
                _GENERIC_RESELLER_KW = ('ขายอะไร', 'มีอะไร', 'ประเภทไหน', 'สินค้าทั้งหมด',
                                        'สินค้าอะไร', 'แบบไหนบ้าง', 'มีอะไรบ้าง', 'มีรุ่นไหน',
                                        'ขายอะไรบ้าง', 'สินค้าประเภท', 'จำหน่ายอะไร',
                                        'ดูสินค้าทั้งหมด', 'ดูสินค้า', 'มีสินค้า')
                _PRODUCT_TYPE_KW = ('ชุด', 'เสื้อ', 'กระโปรง', 'กางเกง', 'กาวน์', 'เดรส',
                                    'สคับ', 'ยูนิฟอร์ม', 'พยาบาล', 'เภสัช', 'หมอ')
                _need_fallback = (any(kw in user_message_text for kw in _GENERIC_RESELLER_KW)
                                  or any(kw in user_message_text for kw in _PRODUCT_TYPE_KW))
                if _need_fallback:
                    try:
                        cursor.execute(_product_base_select + '''
                            WHERE p.status = 'active'
                            GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
                            ORDER BY p.name
                            LIMIT 15
                        ''')
                        for _pr in cursor.fetchall():
                            if _pr['id'] not in seen_ids:
                                seen_ids.add(_pr['id'])
                                prods.append(_pr)
                    except Exception as _fb_err:
                        print(f'[ResellerBot] fallback search error: {_fb_err}')

            # "Show more" products: load next batch excluding already shown IDs
            if _is_show_more_r and _shown_hist_ids and not prods:
                try:
                    conn.rollback()
                    _excl_r = list(_shown_hist_ids)[:60]
                    cursor.execute(_product_base_select + '''
                        WHERE p.status = 'active' AND p.id != ALL(%s)
                        GROUP BY p.id, p.name, p.bot_description, p.size_chart_image_url, b.name
                        ORDER BY p.name LIMIT 15
                    ''', (_excl_r,))
                    for _spr in cursor.fetchall():
                        if _spr['id'] not in seen_ids:
                            seen_ids.add(_spr['id'])
                            prods.append(_spr)
                except Exception as _sme_r:
                    print(f'[ResellerBot] show-more error: {_sme_r}')
                    try:
                        conn.rollback()
                    except Exception:
                        pass

            # Count remaining products not yet shown (only when hit limit)
            if prods and len(prods) >= 15:
                try:
                    conn.rollback()
                    _all_shown_r = {p['id'] for p in prods} | _shown_hist_ids
                    cursor.execute("SELECT COUNT(DISTINCT p.id) FROM products p JOIN skus s ON s.product_id = p.id WHERE p.status = 'active'")
                    _total_cnt_r = int((cursor.fetchone() or [0])[0])
                    _remaining_count_r = max(0, _total_cnt_r - len(_all_shown_r))
                except Exception as _ce_r:
                    print(f'[ResellerBot] count error: {_ce_r}')
                    try:
                        conn.rollback()
                    except Exception:
                        pass

            for pr in prods:
                products_text += _fmt_product_row(pr)

        # Suggest alternatives if size is out of stock
        alt_products_text = ''
        if desired_size and current_product_id:
            cursor.execute("""
                SELECT p.id, p.name, b.name as brand_name, MIN(s.price) as min_price,
                       p.bot_description, p.size_chart_image_url,
                       COALESCE(
                           NULLIF((SELECT STRING_AGG(ov2.value || ':' || s2.stock::text, ' | ' ORDER BY ov2.value)
                            FROM skus s2
                            JOIN sku_values_map svm2 ON svm2.sku_id = s2.id
                            JOIN option_values ov2 ON ov2.id = svm2.option_value_id
                            JOIN options o2 ON o2.id = ov2.option_id
                            WHERE s2.product_id = p.id
                              AND LOWER(o2.name) IN ('ไซส์','size','sz','ขนาด') AND s2.stock > 0), ''),
                           STRING_AGG(DISTINCT s.sku_code || ':' || s.stock::text, ' | ')
                       ) as sku_info,
                       NULL::text as options_summary
                FROM products p
                LEFT JOIN brands b ON b.id = p.brand_id
                JOIN skus s ON s.product_id = p.id
                WHERE p.id IN (
                    SELECT product_id FROM product_categories WHERE category_id IN
                        (SELECT category_id FROM product_categories WHERE product_id = %s)
                )
                  AND p.id != %s AND p.status = 'active' AND s.stock > 0
                GROUP BY p.id, p.name, b.name, p.bot_description, p.size_chart_image_url
                LIMIT 3
            """, (current_product_id, current_product_id))
            alts = cursor.fetchall()
            for a in alts:
                alt_products_text += _fmt_product_row(a)

        # 8b. Collect option values — cached (colors 10 min, sizes 2 min, cats 30 min)
        def _fetch_colors():
            cursor.execute("""
                SELECT DISTINCT ov.value FROM option_values ov
                JOIN options o ON o.id = ov.option_id
                JOIN products p ON p.id = o.product_id
                WHERE p.status = 'active'
                  AND LOWER(o.name) NOT IN ('ไซส์','size','sz','ขนาด')
                ORDER BY ov.value
            """)
            return list(dict.fromkeys(r['value'] for r in cursor.fetchall()))
        _color_values = _bot_cache_get('colors', 600, _fetch_colors)
        _available_colors_str = ', '.join(_color_values) if _color_values else 'ไม่มีข้อมูล'

        def _fetch_sizes():
            cursor.execute("""
                SELECT DISTINCT ov.value FROM option_values ov
                JOIN options o ON o.id = ov.option_id
                JOIN sku_values_map svm ON svm.option_value_id = ov.id
                JOIN skus s ON s.id = svm.sku_id
                JOIN products p ON p.id = o.product_id
                WHERE p.status = 'active'
                  AND LOWER(o.name) IN ('ไซส์','size','sz','ขนาด')
                  AND s.stock > 0
                ORDER BY ov.value
            """)
            return [r['value'] for r in cursor.fetchall()]
        _all_size_opts = _bot_cache_get('sizes', 120, _fetch_sizes)
        _available_sizes_str = ', '.join(_all_size_opts) if _all_size_opts else 'ไม่มีข้อมูล'

        # 8c. Category names (cached 30 min)
        def _fetch_cats():
            cursor.execute("SELECT name FROM categories WHERE parent_id IS NULL ORDER BY sort_order, name LIMIT 15")
            return [r['name'] for r in cursor.fetchall()]
        _available_cats_str = ', '.join(_bot_cache_get('categories', 1800, _fetch_cats)) or 'ไม่มีข้อมูล'

        # 9. Load size chart image for Vision (when viewing a product with size chart)
        size_chart_image_bytes = None
        size_chart_mime = 'image/jpeg'
        size_chart_hint = ''
        _size_keywords = ('ไซส์', 'size', 'เอว', 'สะโพก', 'อก', 'วัด', 'ขนาด', 'ตาราง', 'เลือก')
        _user_asks_size = any(kw in user_message_text.lower() for kw in _size_keywords)
        if current_product_id and _user_asks_size:
            cursor.execute('SELECT size_chart_image_url FROM products WHERE id = %s', (current_product_id,))
            _prow = cursor.fetchone()
            _chart_url = _prow['size_chart_image_url'] if _prow else None
            if _chart_url and _chart_url.startswith('/storage/'):
                try:
                    from replit.object_storage import Client as _OSClient
                    _storage_key = _chart_url.replace('/storage/', '')
                    size_chart_image_bytes = _OSClient().download_as_bytes(_storage_key)
                    if _chart_url.endswith('.png'):
                        size_chart_mime = 'image/png'
                    elif _chart_url.endswith('.webp'):
                        size_chart_mime = 'image/webp'
                    size_chart_hint = '\n[ตารางไซส์แนบเป็นรูปภาพ — ใช้ข้อมูลในรูปตอบคำถามเรื่องไซส์ได้เลยค่ะ]'
                except Exception as _img_err:
                    print(f'[BOT] Cannot load size chart: {_img_err}')

        # 9b. Load text-based size chart from size_chart_groups (member bot)
        _member_size_chart_section = ''
        if _user_asks_size:
            try:
                _mchart_ids = []
                if current_product_id:
                    _mchart_ids = [current_product_id]
                elif prods:
                    _mchart_ids = [r['id'] for r in prods if r.get('id')]
                if _mchart_ids:
                    conn.rollback()
                    _msc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    _msc.execute('''
                        SELECT DISTINCT scg.id, scg.name, scg.columns, scg.rows,
                               scg.fabric_type, scg.allowances
                        FROM size_chart_groups scg
                        JOIN products p ON p.size_chart_group_id = scg.id
                        WHERE p.id = ANY(%s)
                    ''', (_mchart_ids,))
                    _mcharts = _msc.fetchall()
                    _msc.close()
                    _mseen = set()
                    for _mc in _mcharts:
                        if _mc['id'] in _mseen:
                            continue
                        _mseen.add(_mc['id'])
                        _mcols = _mc['columns'] if isinstance(_mc['columns'], list) else json.loads(_mc['columns'])
                        _mrows = _mc['rows'] if isinstance(_mc['rows'], list) else json.loads(_mc['rows'])
                        if not _mcols or not _mrows:
                            continue
                        _mcol_labels = []
                        for _mc2 in _mcols:
                            if isinstance(_mc2, dict):
                                _mu = _mc2.get('unit', '')
                                _mcol_labels.append(f"{_mc2.get('name','')} ({_mu})" if _mu else _mc2.get('name',''))
                            else:
                                _mcol_labels.append(_mc2)
                        _mlines = [' | '.join(_mcol_labels)]
                        for _mr in _mrows:
                            _mvals = _mr.get('values', [])
                            _mline = [_mr.get('size', '')] + _mvals
                            _mlines.append(' | '.join(str(v) for v in _mline))
                        _mfabric = _mc.get('fabric_type') or 'non-stretch'
                        _malw = _mc.get('allowances') or {}
                        if isinstance(_malw, str):
                            try: _malw = json.loads(_malw)
                            except: _malw = {}
                        _mfabric_label = 'ผ้าไม่ยืด (non-stretch)' if _mfabric == 'non-stretch' else 'ผ้ายืด (stretch)'
                        _malw_line = f"ประเภทผ้า: {_mfabric_label} | ค่าเผื่อ: อก +{_malw.get('chest',1)}\" | เอว +{_malw.get('waist',1)}\" | สะโพก +{_malw.get('hip',1.5)}\""
                        _member_size_chart_section += f"\n[ตารางขนาด: {_mc['name']}]\n{_malw_line}\n" + '\n'.join(_mlines) + '\n'
                    if _member_size_chart_section and not size_chart_hint:
                        size_chart_hint = '\n[มีตารางขนาดแนบในส่วน "ตารางขนาดสินค้า" — ใช้ข้อมูลนั้นตอบคำถามเรื่องขนาด/ไซส์ได้เลยค่ะ]'
            except Exception as _msc_err:
                print(f'[MemberBot] size chart text error: {_msc_err}')
                try: conn.rollback()
                except Exception: pass

        # 10. Build prompt for Flash Lite
        # ── Static knowledge base (pre-cached, no extra API call needed) ──────
        _FABRIC_KNOWLEDGE = """
=== ความรู้เรื่องผ้าและหลักสรีรศาสตร์การเลือกเสื้อผ้า ===

[หลักสรีรศาสตร์การเคลื่อนไหว]
• เมื่อนั่ง: สะโพกขยายขึ้น 1"–1.5" จากท่ายืน
• กระโปรงทรงสอบ/เข้ารูป: ช่วงสะโพกสำคัญที่สุด

[ประเภทผ้าและการเผื่อขนาดสะโพก]
• ผ้าไม่ยืด (non-stretch เช่น วาเลนติโน่ ซาติน ฝ้าย ลินิน โพลีเอสเตอร์ทอ):
  - เผื่อสะโพก 1.5"–2" เพื่อให้ใส่สบาย (ตามมาตรฐานสากลและหลักสรีรศาสตร์)
  - เหตุผล: เมื่อนั่งสะโพกขยาย 1"–1.5" ดังนั้น 1.5"–2" คือค่าต่ำสุดที่ยังขยับได้
  - ถ้าเผื่อ < 1.5" = แน่น ใส่ยืนได้แต่นั่งไม่สบาย
  - ถ้าเผื่อ 1.5"–2" = พอดี ยืนและนั่งสบาย (แต่ควรแจ้งว่าเวลานั่งจะรู้สึกกระชับ)
  - ถ้าเผื่อ > 2" = สบายมาก ขยับตัวได้คล่อง
• ผ้ายืด (stretch/jersey/spandex): เผื่อ 0.5"–1" ก็พอ

[เกณฑ์การเลือกไซส์ ผ้าไม่ยืด — ช่องว่างสะโพก = ขนาดในตาราง − สะโพกลูกค้า]
  ✗ ช่องว่าง < 1.5" → แน่นมาก นั่งไม่ได้สบาย → ห้ามแนะนำ
  ✓ ช่องว่าง 1.5"–2" → พอดี ยืนสบาย (เวลานั่งจะกระชับขึ้นเล็กน้อย → ต้องแจ้งลูกค้าด้วย)
  ✓ ช่องว่าง 2"–4" → สบายมาก ขยับตัวได้คล่อง
  △ ช่องว่าง > 4" → หลวม ดูไม่ทรง

[เอว — ผ้าไม่ยืด]
  ช่องว่าง 0"–1" = พอดี (ซิปปิดได้ สวมใส่ได้)
  ช่องว่าง < 0" = ใส่ไม่ได้ → เลือกไซส์ใหญ่ขึ้น
  ช่องว่าง > 2" = หลวมเกิน → แจ้งให้ทราบ

[ตัวอย่างที่ถูกต้อง สำหรับผ้าไม่ยืด]
ลูกค้า เอว 28" สะโพก 37" | ตาราง: M=เอว28/สะโพก37.5, L=เอว29/สะโพก39
  M: สะโพก 37.5−37 = 0.5" < 1.5" → แน่นมาก ❌
  L: สะโพก 39−37 = 2" = พอดี ✓ เอว 29−28 = 1" = พอดี ✓
→ แนะนำ L พร้อมแจ้งว่า "เวลานั่งนานๆ อาจรู้สึกกระชับที่สะโพกบ้างนะคะ เพราะผ้าไม่ยืด"
"""
        _greeting_rule = f"""
⚠️ ข้อความแรกของการสนทนา (ยังไม่มีประวัติแชท):
- ต้องทักทายสมาชิกชื่อ "{reseller_name}" ด้วยความอบอุ่น
- แนะนำตัวเองว่าชื่อ "{bot_name}" เป็นผู้ช่วยของร้าน
- ถามว่าสนใจสินค้าประเภทไหน หรือมีอะไรให้ช่วยได้บ้าง
- quick_replies ให้ใส่หมวดหมู่/ประเภทสินค้าที่น่าสนใจ (2-4 ปุ่ม) เช่น สินค้าขายดี, ดูสินค้าทั้งหมด
""" if is_first_message else ""
        system_prompt = f"""คุณชื่อ "{bot_name}" เป็นผู้ช่วยขายสินค้าออนไลน์ที่เป็นมืออาชีพ สุภาพ อ่อนน้อม และเน้นการปิดการขาย
{extra_persona}{training_block}
{_FABRIC_KNOWLEDGE}
{_greeting_rule}
กฎสำคัญ:
- ตอบเป็นภาษาไทย ลงท้าย "ค่ะ" เสมอ
- 🖼️ การแสดงรูปสินค้า (show_product_ids): ใส่ product ID ใน 2 กรณีนี้:
  1) สมาชิกถามสินค้าประเภทใดประเภทหนึ่งชัดเจน เช่น "กระโปรงมีไหม" "มีเสื้ออะไรบ้าง" "กาวน์มีไหม" "ดูสินค้าทั้งหมด" → ใส่ ID ทุกรายการที่ตรงประเภทนั้น
  2) สมาชิก "ขอดูรูป/แบบ/รูปถ่าย/ภาพ/อยากเห็น" อย่างชัดเจน
  * Product ID คือตัวเลขหลัง "ID:" ในรายการสินค้าด้านล่าง เช่น "ID:42" = ใส่ 42 ใน show_product_ids
  * ❌ ห้ามพูดคำว่า "Product ID" หรือ "รหัสสินค้า" ในข้อความตอบสมาชิกเด็ดขาด — สมาชิกไม่รู้และไม่ควรต้องรู้ ID
  * ❌ ห้ามเขียนในข้อความว่า "ระบบไม่สามารถแสดงรูปภาพได้" หรือ "ขออภัยที่ไม่สามารถแสดงรูป" เด็ดขาด
  * ❌ ห้ามใส่ show_product_ids เมื่อ: ถามไซส์, ถามราคา, ถามโปรโมชั่น, ถามคูปอง, ถามสต็อก, สั่งซื้อ, หรือคำถามต่อเนื่องที่ไม่ได้ขอดูรูปหรือเปลี่ยนสินค้า
- 📦 กฎสินค้า (เด็ดขาด): รายการ "สินค้าที่เกี่ยวข้อง" ด้านล่างคือข้อมูลจริงจากระบบ ณ ขณะนี้
  * ✅ ถ้ารายการมีสินค้า → ต้องตอบตามนั้น ห้ามบอกว่า "ไม่มี" หรือ "มีเฉพาะ..." อื่น ถึงแม้ประวัติแชทก่อนหน้าจะพูดถึงสินค้าอื่น
  * ✅ ให้ใช้ประวัติแชทเพื่อทำความเข้าใจบริบทว่าสมาชิกกำลังถามถึงสินค้าใดอยู่ แต่ข้อมูลสต็อก/ราคา/รายละเอียดสินค้า ต้องดึงมาจากรายการสินค้าด้านล่างเท่านั้น ห้ามสร้างข้อมูลขึ้นมาเอง
  * ✅ ถ้ารายการสินค้าว่าง → ถามสมาชิกด้วยชื่อหมวดหมู่จริงจาก "หมวดหมู่สินค้าในร้าน" แล้วใส่ quick_replies
- 🔍 เมื่อค้นหาสินค้าไม่เจอ (รายการสินค้าด้านล่างว่างเปล่า): ห้ามบอกว่า "ไม่พบสินค้า" แล้วหยุด และห้ามพูดคำว่า "Product ID" เด็ดขาด — ให้ถามสมาชิกด้วยชื่อหมวดหมู่จริงจาก "หมวดหมู่สินค้าในร้าน" ด้านบน เช่น "ขอทราบว่าสนใจประเภทไหนคะ?" แล้วใส่ quick_replies เป็นชื่อหมวดหมู่จริงจากรายการ
- 🖼️ เมื่อลูกค้าถามดูตารางไซส์หรือรูปสินค้า: ให้ตอบพร้อมบอกว่า "กดดูในรายละเอียดสินค้าที่ส่งให้ได้เลยนะคะ ถ้าไม่แน่ใจการเลือกไซส์ น้องนุ่นช่วยได้ค่ะ" เสมอ
- 📋 เมื่อลูกค้าถามหาแบบสินค้า/มีกี่แบบ/แบบไหนบ้าง: ให้แสดงเฉพาะรายชื่อสินค้าทั้งหมดเป็นข้อๆ ก่อน ห้ามใส่ show_product_ids ตอนนี้ แล้วถามว่า "สนใจตัวไหนคะ?" ให้ลูกค้าเลือก รอให้ลูกค้าระบุตัวที่สนใจก่อนค่อยส่ง show_product_ids
- 📏 ตารางไซส์: ห้ามบอกให้สมาชิก "แนบรูปตารางไซส์" หรือเขียน "(กรุณาแนบรูปตารางไซส์ที่นี่)" ในทุกกรณีเด็ดขาด — ระบบจะส่งรูปตารางไซส์ให้บอทอัตโนมัติถ้ามี ถ้ามี[ตารางไซส์แนบเป็นรูปภาพ]ให้อ่านและตอบได้เลย ถ้าไม่มีให้บอกว่า "ไม่มีตารางไซส์สำหรับสินค้านี้ค่ะ"
- 🚫 ห้ามเดาหรือแต่งตัวเลขขนาดไซส์เด็ดขาด (เช่น อก/เอว/สะโพกของแต่ละไซส์) — ตัวเลขเหล่านี้ต้องอ่านมาจากตารางไซส์รูปภาพที่ระบบส่งมาเท่านั้น ห้ามใช้ความรู้ทั่วไปหรือประมาณเอาเอง ถ้าไม่มีตารางไซส์ในรูปภาพ → ให้บอกว่า "ต้องดูตารางไซส์ของสินค้านั้นก่อนค่ะ น้องนุ่นจะเทียบไซส์ได้ถูกต้องก็ต่อเมื่อเห็นตารางไซส์ของสินค้านั้นจริงๆ ค่ะ" แล้วถามสมาชิกว่าสนใจสินค้าประเภทไหน/แบบไหน
- ❓ ถ้าสมาชิกถามเรื่องไซส์แต่ยังไม่ได้ระบุว่าสนใจสินค้าชิ้นไหนหรือประเภทไหน → ให้ถามกลับก่อนเสมอ เช่น "สนใจสินค้าประเภทไหนคะ? (เช่น ชุดพยาบาล ชุดเภสัช เสื้อสคับ ฯลฯ) น้องนุ่นจะได้ดึงตารางไซส์ที่ถูกต้องมาเทียบให้ค่ะ" แล้วใส่ quick_replies เป็นชื่อหมวดหมู่จริงจากรายการ — ห้ามตอบตัวเลขไซส์โดยไม่รู้ก่อนว่าเป็นสินค้าอะไร
- ⚠️ กฎการเลือกไซส์ (บังคับใช้ทุกครั้งที่แนะนำไซส์ — ห้ามข้ามขั้นตอนหรือใช้วิธีอื่น):
  ขั้น 1 — คำนวณ "ค่าต้องการ" แต่ละจุด (อก/เอว/สะโพก) โดยอ่านค่าเผื่อจากบรรทัด "ค่าเผื่อ:" ในหัวข้อ [ตารางขนาด] ด้านล่าง:
    • เช่น "ค่าเผื่อ: อก +1" | เอว +1" | สะโพก +1.5"" → ใช้ค่าเหล่านั้นตรงๆ
    • อก: ลูกค้า + ค่าเผื่ออก   เช่น อก 32" + 1" → ต้องการ ≥ 33"
    • เอว: ลูกค้า + ค่าเผื่อเอว   เช่น เอว 30" + 1" → ต้องการ ≥ 31"
    • สะโพก: ลูกค้า + ค่าเผื่อสะโพก   เช่น สะโพก 40" + 1.5" → ต้องการ ≥ 41.5"
    (ถ้าไม่มีข้อมูล "ค่าเผื่อ" ในตาราง → ใช้ค่าเริ่มต้น: อก +1" | เอว +1" | สะโพก ผ้าไม่ยืด +1.5", ผ้ายืด +1")
    ⚠️ ค่าเผื่อติดลบ = รัดรูปโดยเจตนา เช่น สะโพก -1" หมายความว่าแนะนำไซส์ที่มีสะโพก ≥ ลูกค้า -1" (เสื้อเล็กกว่าตัวลูกค้า 1") — บอทต้องแจ้งลูกค้าด้วยว่า "สินค้านี้ออกแบบให้ใส่รัดรูป" ก่อนแนะนำไซส์
  ขั้น 2 — สแกนตารางทีละแถวจากเล็กสุด: แถวใดที่ค่าตาราง ≥ ค่าต้องการ **ครบทุกจุดในแถวเดียวกัน** → แถวนั้น "ผ่าน"
    กฎเกณฑ์: ค่าตาราง ≥ ค่าต้องการ = ✓ | ค่าตาราง < ค่าต้องการ = ✗ (แม้ต่างกันแค่ 0.5" ก็ถือว่าไม่ผ่าน)
  ขั้น 3 — ไซส์ที่แนะนำ = แถวแรก (เล็กสุด) ที่ผ่านทุกจุด
  ขั้น 4 — แสดงผลต้องมีรูปแบบนี้เสมอ:
    "ค่าต้องการ: อก ≥ 33" | เอว ≥ 31" | สะโพก ≥ 41.5""
    "XS: อก 32 ✗ → ไม่ผ่าน"
    "S: อก 34 ✓, เอว 29 ✗ → ไม่ผ่าน"
    "M: อก 36 ✓, เอว 31 ✓, สะโพก 40 ✗ (40 < 41.5) → ไม่ผ่าน"
    "L: อก 38 ✓, เอว 33 ✓, สะโพก 42 ✓ (42 ≥ 41.5) → ✅ ผ่านทุกจุด"
    "แนะนำ: ไซส์ L ค่ะ"
  * ห้ามแนะนำไซส์โดยไม่แสดงตารางการเทียบด้านบน — ลูกค้าต้องเห็นขั้นตอนครบทุกแถว
  * ⚠️ ต้องใช้ค่าเผื่อจากบรรทัด "ค่าเผื่อ:" ในตารางเสมอ — ห้ามใช้ค่าตายตัว เพราะแต่ละสินค้าอาจตั้งค่าเผื่อต่างกัน (ตามประเภทผ้าและสไตล์การใส่)
- ถ้าลูกค้าสนใจสินค้า → ถามไซส์และจำนวน → ชวนสั่งซื้อทันที
- 🔔 แจ้งเตือนสต็อกคืน (ขั้นตอนสำคัญ ห้ามข้าม):
  ขั้น 1 (ไซส์หมด): ตอบว่า "ขออภัยค่ะ ไซส์ [X] ของ [ชื่อสินค้า] หมดชั่วคราว ต้องการให้น้องนุ่นแจ้งเตือนเมื่อมีสต็อกคืนไหมคะ?" แล้ว quick_replies: ["ยืนยัน แจ้งเตือนฉัน 🔔", "ไม่ต้องค่ะ"]
  ขั้น 2 (สมาชิกกด "ยืนยัน แจ้งเตือนฉัน 🔔"): ตอบรับว่า "น้องนุ่นบันทึกไว้แล้วค่ะ จะแจ้งทันทีเมื่อมีสต็อกนะคะ 😊 (ระบบแจ้งผ่านแชทนี้เลย)" แล้วใส่ restock_alert ใน JSON พร้อม confirmed=true ทันที (ไม่ต้องถามเบอร์เพราะแจ้งผ่านแชทได้เลย) พร้อมเสนอสินค้าทดแทน
  ⚠️ ห้ามใส่ restock_alert ใน JSON จนกว่าสมาชิกจะกด "ยืนยัน" ก่อน
- 🔍 เปรียบเทียบสินค้า: ถ้าลูกค้าถามเปรียบเทียบ 2 สินค้า → ตอบแบบข้อๆ เทียบ: ชื่อสินค้า | ผ้า/วัสดุ | ไซส์ที่มี | ราคา | จุดเด่น — ดึงข้อมูลจากรายการสินค้าด้านล่างเท่านั้น ห้ามแต่งข้อมูล
- 📐 ความยาวชุด: ถ้าลูกค้าถามว่า "ชุดยาวถึงไหน/ใส่แล้วคลุมแค่ไหน/ยาวแค่ไหน" → ถามส่วนสูงก่อนถ้าไม่รู้ แล้วคำนวณ:
  * กระโปรง: วัดจากเอวลงมา เช่น ส่วนสูง 160 cm เอวอยู่ที่ ~60% = 96 cm จากพื้น ถ้าชุดยาว 65 cm → ปลายชุดอยู่ที่ 96-65 = 31 cm จากพื้น = คลุมแค่ 31 cm เหนือพื้น → ประมาณตำแหน่ง เช่น "น่าจะยาวคลุมเข่าพอดีค่ะ" หรือ "น่าจะอยู่กลางต้นขาค่ะ"
  * เสื้อ/เดรส/ชุดตัวยาว: วัดจากจุดข้างคอ (ไหล่ต่อคอ) ลงมา เช่น ส่วนสูง 160 cm จุดข้างคออยู่ที่ ~85% = 136 cm จากพื้น ถ้าชุดยาว 110 cm → ปลายอยู่ที่ 136-110 = 26 cm จากพื้น → ประมาณตำแหน่ง
  * ตอบเป็นภาษาธรรมชาติ เช่น "น่าจะยาวคลุมเข่าคุณพี่พอดีค่ะ" หรือ "น่าจะอยู่กลางน่องค่ะ"
  * ถ้าสเปคสินค้าไม่มีตัวเลขความยาว → บอกว่า "ไม่มีข้อมูลความยาวในสเปคสินค้าค่ะ ลองบอกส่วนสูงของคุณพี่ น้องนุ่นจะประมาณให้ค่ะ"
- 📵 กฎเบอร์โทร 083-668-2211 (เด็ดขาด): ห้ามให้เบอร์โทรในกรณีทั่วไป ให้เบอร์โทรได้เฉพาะ 3 กรณีนี้เท่านั้น: 1) สมาชิกขอเบอร์ติดต่อโดยตรง 2) สมาชิกแสดงความกังวลหรือลังเลเรื่องการชำระเงิน 3) สมาชิกต้องการสั่งผลิตสินค้าและขอเบอร์เอง — ห้ามให้เบอร์เมื่อถามเรื่องค่าส่ง ไซส์ ราคา สินค้า เวลาทำการ หรือคำถามทั่วไปอื่นๆ
- 🚚 ระบบ Dropship & การสต็อกสินค้า: ร้านของเรารองรับระบบ Dropship อย่างเต็มรูปแบบ — สมาชิกไม่จำเป็นต้องสต็อกสินค้าเองเลยค่ะ เพราะบริษัทฯ ผลิตสินค้าเองทั้งหมด จึงสามารถเติมสต็อกได้ตลอดเวลา ถ้าสมาชิกต้องการเปิดหน้าร้านก็ไม่จำเป็นต้องสั่งสต็อกจำนวนมาก สั่งตามออเดอร์ลูกค้าได้เลย — ห้ามบอกว่า "สินค้ามีจำนวนจำกัด" หรือกดดันให้สต็อกของ เพราะเราเติมได้เสมอ
- 🎁 โปรโมชั่น (เด็ดขาด): ถ้าส่วน "=== โปรโมชั่นที่มีอยู่ ===" มีข้อมูล → ต้องแจ้งทุกรายการเสมอเมื่อลูกค้าถามถึงโปรโมชั่น ห้ามบอกว่า "ไม่มีโปรโมชั่น" ถ้าส่วนนั้นมีข้อมูลอยู่ นอกจากนี้ให้แจ้งโปรโมชั่นเชิงรุกก่อนลูกค้าถาม
- 🚫 ห้ามสร้างโปรโมชั่น ส่วนลด หรือข้อเสนอพิเศษที่ไม่มีอยู่ในหัวข้อ "โปรโมชั่นที่มีอยู่" เด็ดขาด — ถ้าไม่มีโปรโมชั่น ให้บอกตรงๆ ว่า "ขณะนี้ไม่มีโปรโมชั่นพิเศษค่ะ"
- ✅ การยืนยันสินค้า: ถ้าสมาชิกพิมพ์ชื่อสินค้าที่ตรงกับรายการสินค้าด้านล่างอย่างชัดเจน (≥70%) → ข้ามการถามยืนยัน "ใช่ไหมคะ" แสดงรายละเอียดสินค้านั้นได้เลยทันที เฉพาะเมื่อชื่อกำกวมหรือตรงกับหลายสินค้าจึงถามยืนยัน
- 🗂️ ถ้าสมาชิกถามกว้างๆ ไม่ระบุสินค้าหรือประเภท (เช่น "มีอะไรบ้าง" "ขายอะไร" "อยากดูสินค้า") → แจ้งหมวดหมู่จาก "✅ หมวดหมู่สินค้าในร้าน" ด้านบน พร้อมใส่ quick_replies เป็นชื่อหมวดหมู่เพื่อให้เลือก
- 📄 สินค้าที่เหลือ: ถ้า prompt แสดง "[ℹ️ มีสินค้าที่เกี่ยวข้องอีก X รายการที่ยังไม่ได้แสดง]" → ให้แจ้งสมาชิกว่ามีสินค้าอีก X รายการ พร้อมถามว่าต้องการดูเพิ่มไหม และใส่ quick_replies ["ดูสินค้าเพิ่มเติม", "ไม่ต้องค่ะ"] ด้วย
- 📐 การขอขนาดร่างกาย: ถ้ายังไม่มีขนาดร่างกายใดๆ เลยในหัวข้อ "ขนาดร่างกายของสมาชิก" → ต้องถามครบทั้ง 3 จุดในครั้งเดียว: "รบกวนบอกขนาดรอบอก รอบเอว และรอบสะโพก (เป็นนิ้วหรือเซนติเมตร) ด้วยนะคะ" ห้ามถามแค่ 1-2 จุด (ถ้ามีบางจุดแล้ว ให้ถามเฉพาะที่ขาดตามกฎด้านบน)
- 📏 เมื่อทราบขนาดตัวครบทั้ง 3 จุด (รอบอก+รอบเอว+รอบสะโพก) → ตอบทันทีด้วย: 1) สรุปขนาดที่ทราบ 2) เทียบตารางไซส์จากหัวข้อ "ตารางขนาดสินค้า" แล้วแนะนำไซส์ที่เหมาะสมพร้อมเหตุผล — ถ้าไม่มีตารางไซส์ให้บอกตรงๆ ว่า "ยังไม่มีตารางไซส์ค่ะ"
- 💳 วิธีชำระเงิน: ดูจากหัวข้อ "กฎเพิ่มเติมจาก Admin" ด้านบน และตอบตามนั้นเท่านั้น ห้ามแต่งข้อมูลช่องทางชำระเงินเพิ่มเอง
- 🕐 เวลาทำการ: ดูจากหัวข้อ "กฎเพิ่มเติมจาก Admin" ด้านบน และตอบตามนั้นเท่านั้น ห้ามแต่งข้อมูลเวลาทำการเพิ่มเอง
- 🚚 ข้อมูลการจัดส่ง (ใช้ข้อมูลนี้เมื่อลูกค้าถามค่าส่ง): {_member_ship_text}
  * บริษัทขนส่งที่ใช้: Kerry Express, Flash Express, ไปรษณีย์ไทย
  * ระยะเวลาจัดส่ง/วันส่ง: ดูจากหัวข้อ "กฎเพิ่มเติมจาก Admin" ด้านบน
  * ไม่มีบริการส่งต่างประเทศ
- 🏢 ข้อมูลบริษัท (ใช้เมื่อถูกถามถึงที่มา ความน่าเชื่อถือ หรือประวัติบริษัท):
  * บริษัท เคาท์มีอินดีไซน์ จำกัด ผลิตเสื้อผ้าคุณภาพสูง ทั้งแฟชั่นและยูนิฟอร์ม มีทั้งสินค้าสำเร็จรูปและสั่งผลิต
  * ผลิตเสื้อผ้าให้แบรนด์แฟชั่นชั้นนำหลายแบรนด์ เช่น Curvf, Laboutique, oOdinaryjun
  * ลูกค้าองค์กร เช่น Impact เมืองทองธานี, Unilever, มูลนิธิแม่ฟ้าหลวงฯ
  * โทรศัพท์ 083-668-2211 (คุณเอ็ด) | เว็บไซต์: ekgshops.com
- 🏢 สร้างความมั่นใจเรื่องการชำระเงิน: ถ้าลูกค้าแสดงความกังวล ไม่มั่นใจ หรือลังเลเรื่องการโอนเงิน ให้แจ้งว่า "ร้านของเราดำเนินการโดย บริษัท เคาท์มีอินดีไซน์ จำกัด ค่ะ จดทะเบียนถูกต้องตามกฎหมาย มีลูกค้าองค์กรชั้นนำอย่าง Impact เมืองทองธานี และ Unilever ค่ะ สามารถโทรสอบถามได้โดยตรงที่ 083-668-2211 ค่ะ มั่นใจได้เลยนะคะ" — ใช้เฉพาะเมื่อลูกค้าแสดงความกังวลหรือถามถึงความน่าเชื่อถือเท่านั้น ห้ามพูดโดยไม่มีเหตุ
- 🏭 รับผลิตสินค้าตามสั่ง (Custom Order): บริษัทฯ รับผลิตเสื้อผ้าคุณภาพสูงตามสั่งได้ ถ้าลูกค้าสนใจสั่งผลิต ให้ถามข้อมูลต่อไปนี้ทีละข้อตามลำดับ: 1) รูปแบบที่ต้องการ (สไตล์/ดีไซน์) 2) รูปตัวอย่างสินค้าที่ลูกค้าต้องการอ้างอิง 3) จำนวนที่ต้องการ 4) วันที่ต้องการรับสินค้า 5) เบอร์โทรติดต่อกลับ — เมื่อได้ครบทุกข้อให้แจ้งว่า "น้องนุ่นรับข้อมูลไว้แล้วค่ะ ทีมงานจะติดต่อกลับโดยเร็วที่สุดค่ะ 😊" ถ้าลูกค้าขอเบอร์ติดต่อเองให้ส่ง 083-668-2211 และแจ้งว่า "ติดต่อคุณเอ็ดได้โดยตรงเลยค่ะ"
- 🏅 ส่วนลดตามเกรดสมาชิก: ราคาในรายการสินค้าด้านล่างเป็นราคาที่คำนวณตามเกรด {reseller_tier_name} ของสมาชิกแล้ว — เมื่อแจ้งราคาให้บอกราคาสมาชิกนั้นเสมอ พร้อมระบุว่าเป็นราคาเกรด {reseller_tier_name} ถ้าสมาชิกถามว่า "เกรดสูงกว่าได้ราคาดีกว่าไหม" → ให้ตอบว่าใช่ และบอกเงื่อนไขการอัปเกรดจากหัวข้อ "เกรดสมาชิกและส่วนลด" ด้านบน
- 📦 สั่งจำนวนมาก/ขอส่วนลดพิเศษ:
  * ถ้าลูกค้าบอกว่าจะสั่งจำนวนมาก หรือถามส่วนลดพิเศษ → ให้ดูส่วนลดสูงสุดของสินค้าตัวนั้นจากข้อมูลสินค้าด้านล่าง แล้วแจ้งให้ลูกค้าทราบ เช่น "สินค้าตัวนี้ส่วนลดสูงสุดที่ได้รับได้คือ X% ค่ะ"
  * ถ้าลูกค้ายังดูไม่พอใจหรือต้องการต่อรองเพิ่ม → ให้บอกว่า "น้องนุ่นจะรายงานให้คุณเอ็ดทราบค่ะ ขอเบอร์โทรของคุณพี่ไว้ได้ไหมคะ ทางร้านจะโทรกลับโดยเร็วที่สุดค่ะ" แล้วรอรับเบอร์โทรจากลูกค้า เมื่อได้รับเบอร์แล้วให้ตอบรับว่า "น้องนุ่นบันทึกเบอร์ไว้แล้วค่ะ คุณเอ็ดจะติดต่อกลับโดยเร็วที่สุดเลยนะคะ 😊"
  * ถ้าลูกค้าขอเบอร์ติดต่อเองหรืออยากโทรหาเอง → ส่งเบอร์ 083-668-2211 และแจ้งว่า "ติดต่อคุณเอ็ดได้โดยตรงเลยค่ะ"
- 📦 สถานะออเดอร์: เมื่อสมาชิกถามถึงออเดอร์/การสั่งซื้อ/พัสดุ → ดูจากหัวข้อ "สถานะออเดอร์ของสมาชิก" ด้านล่าง แล้วแจ้งทุกออเดอร์ที่ค้างอยู่พร้อมลำดับเหตุการณ์ครบถ้วน ดังนี้:
  * ลำดับสถานะตามปกติ: วันสั่งซื้อ → ชำระเงิน → ยืนยันคำสั่ง → เตรียมสินค้า → จัดส่ง → ส่งถึง
  * บอกสถานะปัจจุบันอยู่ขั้นไหน เช่น "ตอนนี้อยู่ขั้นจัดส่งแล้วค่ะ"
  * ถ้ามีเลขพัสดุ → แจ้งเลขพัสดุและบริษัทขนส่งให้ด้วยเสมอ
  * ถ้าไม่มีออเดอร์ค้างอยู่ → แจ้งว่า "ไม่มีออเดอร์ที่รอดำเนินการค่ะ"
  * ถ้าสมาชิกถามถึงออเดอร์เฉพาะเจาะจง → หาจากออเดอร์ที่จบแล้วด้วย
- 🎟️ คูปองของสมาชิก: ถ้าสมาชิกถามว่า "มีคูปองไหม" หรือ "คูปองของฉัน" → ดูจากหัวข้อ "คูปองของสมาชิกคนนี้" ด้านล่าง แล้วตอบรายละเอียดที่ถูกต้อง ถ้าไม่มีให้บอกว่า "ยังไม่มีคูปองค่ะ" อย่าบอกว่า "สามารถแจ้งทางร้านได้"
- 📏 ขนาดร่างกายสมาชิก: ดูจากหัวข้อ "ขนาดร่างกายของสมาชิก" ด้านล่าง
  * ถ้ามีข้อมูลแล้ว → ห้ามถามซ้ำ ใช้ค่านั้นได้เลย (เช่น ถ้ามีรอบเอวแล้วไม่ต้องถามรอบเอวอีก)
  * ถ้าขาดข้อมูลบางส่วน → ถามเฉพาะที่ขาด (เช่น มีเอว+สะโพกแล้ว ถามแค่รอบอก)
  * ถ้าสมาชิกบอกขนาดใหม่ในข้อความนี้ → บันทึกลง new_state.measurements ทันที **ทุกครั้ง**
  * ⚠️ ห้ามลืม return new_state.measurements แม้จะได้รับขนาดเพียงบางส่วน (เช่น บอกแค่สะโพก)
  * เมื่อบันทึกขนาดสำเร็จ → แจ้งสมาชิกว่า "น้องนุ่นจำไว้ในระบบแล้วค่ะ ครั้งหน้าไม่ต้องบอกซ้ำนะคะ 😊" พร้อมเสนอว่า "ถ้าคราวหน้าจะสั่งให้เพื่อน แจ้งชื่อเพื่อนมาพร้อมขนาดได้เลย น้องนุ่นจะจำไว้ให้ด้วยค่ะ"
- 👥 การสั่งให้เพื่อน (ordering_for):
  * ถ้าสมาชิกบอกว่าจะ "สั่งให้เพื่อน/น้อง/พี่ [ชื่อ]" → ถามชื่อถ้าไม่ได้บอก แล้วตั้ง new_state.ordering_for = ชื่อนั้น
  * เมื่อ ordering_for ≠ "self" → ใช้ขนาดของเพื่อนคนนั้นจากหัวข้อ "ขนาดร่างกายของเพื่อน" ด้านล่าง ไม่ใช่ขนาดของสมาชิก
  * เมื่อได้รับขนาดของเพื่อน → บันทึกใน new_state.measurements เหมือนเดิม แล้วระบุ new_state.ordering_for = ชื่อเพื่อน
  * ถ้ากลับมาสั่งเพื่อตัวเอง → ตั้ง new_state.ordering_for = "self"
  * ⚠️ กฎเด็ดขาด — ห้ามสับสนชื่อตัวเองกับชื่อเพื่อน:
    - ถ้าสมาชิกบอกว่า "ฉันชื่อ X" หรือ "ชื่อของฉันคือ X" ขณะที่ ordering_for = ชื่อเพื่อนอยู่ → นั่นคือสมาชิกแค่บอกชื่อตัวเอง ห้ามเปลี่ยน ordering_for ห้ามบันทึก measurements ใหม่ ให้บันทึกแค่ new_state.self_name = "X" แล้วตอบรับชื่อ
    - ห้ามนำขนาดของเพื่อนไปบันทึกเป็นขนาดของตัวเองเด็ดขาด
    - การเปลี่ยน ordering_for กลับ "self" ต้องเกิดจากสมาชิกพูดถึงการสั่งให้ตัวเองชัดเจน เช่น "สั่งให้ตัวเอง" "ของฉันเอง" ไม่ใช่แค่บอกชื่อ
  * 🔍 Fuzzy match ชื่อเพื่อน: ถ้าสมาชิกพิมพ์ชื่อที่ไม่ตรงกับรายชื่อในหัวข้อ "ขนาดร่างกายของเพื่อน" แต่คล้ายกัน → ถามว่า "หมายถึง [ชื่อที่ใกล้เคียงที่สุด] ใช่ไหมคะ?" ใส่ quick_replies ["ใช่ค่ะ", "ไม่ใช่ค่ะ"] ถ้ายืนยัน → ใช้ชื่อเดิมในระบบ ห้ามสร้างรายการซ้ำ
  * 📊 ถ้าสมาชิกถามว่า "มีเพื่อนกี่คน" หรือ "บันทึกเพื่อนไว้กี่คน" → นับจากหัวข้อ "ขนาดร่างกายของเพื่อน" แล้วตอบพร้อมรายชื่อทั้งหมด
  * ✏️ อัปเดตขนาด: ถ้าสมาชิกบอกว่า "ขนาดเปลี่ยนแล้ว" หรือ "ขอแก้ขนาด" หรือบอกขนาดใหม่ทับของเดิม → รับค่าใหม่ บันทึกทับ แจ้งสมาชิกว่า "น้องนุ่นอัปเดตแล้วค่ะ"
- 🏷️ ชื่อตัวเองของสมาชิก: ดูจาก "ชื่อที่สมาชิกใช้เรียกตัวเอง" ด้านล่าง ถ้าสมาชิกบอกชื่อที่ต้องการให้เรียก → บันทึกใน new_state.self_name และเรียกด้วยชื่อนั้นทุกครั้ง
- ถ้าสต็อกเหลือน้อย (≤3) → บอกว่า "เหลือน้อยนะคะ"
- ถ้าไม่รู้คำตอบหรือลูกค้าต้องการคุยเรื่องพิเศษ (ต่อรอง/ปัญหาออเดอร์) → แนะนำให้กดปุ่ม "ขอคุยกับ Admin"
- ข้อความต้องสั้นกระชับ ไม่เกิน 3 บรรทัด{size_chart_hint}

กฎ quick_replies (เด็ดขาด — ห้ามฝ่าฝืน):
❌ ห้ามเดาสีหรือตัวเลือกจากความรู้ทั่วไป เช่น ห้ามใส่ "สีกรม" ถ้าไม่มีในข้อมูลด้านล่าง
✅ สีและลายที่มีในร้านทั้งหมด: {_available_colors_str}
✅ ไซส์ที่มีสต็อก: {_available_sizes_str}
✅ หมวดหมู่สินค้าในร้าน: {_available_cats_str}
- quick_replies เรื่องสี: ใช้ได้เฉพาะค่าที่อยู่ใน "สีและลายที่มีในร้านทั้งหมด" เท่านั้น
- quick_replies เรื่องไซส์: ใช้ได้เฉพาะค่าที่อยู่ใน "ไซส์ที่มีสต็อก" เท่านั้น
- quick_replies เรื่องสินค้า: ใช้ชื่อสินค้าจริงจากรายการข้อมูลสินค้าด้านล่าง ห้ามตั้งชื่อขึ้นเอง
- ถ้ายังไม่มีข้อมูลสินค้าที่ match → quick_replies ให้เป็นคำถามถามลูกค้า เช่น "บอกประเภทที่ต้องการ" ไม่ใช่เดาตัวเลือก

=== ข้อมูลสถานการณ์ปัจจุบัน ===
State: {session_data.get('state','IDLE')}
สินค้าที่กำลังดู ID: {current_product_id or 'ไม่มี'}
ไซส์ที่ต้องการ: {desired_size or 'ยังไม่ได้ระบุ'}

=== ขนาดร่างกายของสมาชิก (บันทึกถาวรในระบบ — ใช้ได้ทุกครั้ง ไม่ต้องถามซ้ำ) ===
ชื่อที่สมาชิกใช้เรียกตัวเอง: {_self_display}
กำลังสั่งซื้อให้: {_ordering_for_label}
{measurements_text}

=== ขนาดร่างกายของเพื่อน (ที่เคยบันทึกไว้) ===
{_all_friends_text}

=== สถานะออเดอร์ของสมาชิก (ข้อมูลจริงจากระบบ ณ ขณะนี้) ===
{orders_text}

=== โปรโมชั่นที่มีอยู่ (หากมีรายการด้านล่าง ให้แจ้งทุกรายการเมื่อลูกค้าถามถึงโปรโมชั่น — ห้ามบอกว่า "ไม่มีโปรโมชั่น" ถ้ายังมีข้อมูลด้านล่าง) ===
{promos_text}

=== คูปองของสมาชิกคนนี้ (พร้อมใช้) ===
{coupons_text}

=== สิ่งที่ต้องทำ — รอแจ้งเตือนสต็อกคืน ===
{_restock_pending_text}
(รายการนี้คืองานที่รอดำเนินการอยู่ เมื่อระบบแจ้งสต็อกคืนแล้ว รายการจะหายไปเองอัตโนมัติ)

=== เกรดสมาชิกและส่วนลด ===
เกรดปัจจุบัน: {reseller_tier_name}
เงื่อนไขการอัปเกรด: {_next_tier_text}
ตารางเกรดทั้งหมด:
{tier_info_text}
⚠️ ราคาในรายการสินค้าด้านล่างเป็นราคาสำหรับเกรด {reseller_tier_name} แล้ว ใช้ราคานั้นเป็นราคาที่สมาชิกจะได้รับจริง

=== ตารางขนาดสินค้า (ขนาด = ไซส์ คืออันเดียวกัน — ใช้ข้อมูลนี้ตอบคำถามเรื่องขนาด/ไซส์ได้เลยทันที ห้ามบอกว่า "ไม่มีข้อมูล" ถ้ามีตารางด้านล่าง) ===
{_member_size_chart_section or '(ยังไม่มีตารางขนาดสำหรับสินค้าที่แสดง)'}

=== รายการสินค้าที่เกี่ยวข้อง (ข้อมูลจริงจากระบบ — ใช้ข้อมูลนี้เท่านั้น ห้ามอ้างอิงประวัติแชท) ===
⚠️ ไซส์และสต็อกของแต่ละสินค้า ให้ใช้ข้อมูลจากสินค้านั้นๆ เท่านั้น ห้ามนำไซส์หรือสต็อกจากสินค้าอื่นมาระบุ และห้ามเพิ่มไซส์ที่ไม่ปรากฏในข้อมูลด้านล่าง
{products_text or '(ไม่พบสินค้าที่ตรงกับคำค้นหา)'}
{'[ℹ️ มีสินค้าที่เกี่ยวข้องอีก ' + str(_remaining_count_r) + ' รายการที่ยังไม่ได้แสดง]' if _remaining_count_r > 0 else ''}

=== สินค้าทดแทน ===
{alt_products_text or '(ไม่มี หรือยังไม่ได้ระบุไซส์)'}

⚠️ ตอบกลับเป็น JSON เท่านั้น ห้ามตอบเป็นข้อความธรรมดาเด็ดขาด แม้จะมีรูปภาพแนบมา:
{{
  "message": "ข้อความตอบกลับ (string)",
  "quick_replies": ["ตัวเลือก1", "ตัวเลือก2"],
  "show_product_ids": [id1, id2],
  "new_state": {{
    "state": "IDLE|BROWSING_CATEGORY|VIEWING_PRODUCT|SUGGEST_ALTERNATIVE",
    "current_product_id": null,
    "category_id": null,
    "desired_size": null,
    "ordering_for": "self"
  }},
  "add_to_cart": {{"product_id": null, "size": null, "quantity": 0}},
  "restock_alert": {{"product_id": null, "product_name": null, "size": null, "phone": null, "confirmed": false}},
  "needs_admin": false
}}
- "quick_replies": ปุ่มตัวเลือกให้กด (ไม่เกิน 4 ปุ่ม หรือ [] ถ้าไม่ต้องการ)
- "show_product_ids": รายการ product ID ที่ต้องการแสดงรูป ([] ถ้าไม่มี) — ดึง ID จากรายการสินค้าด้านบน (ตัวเลขหลัง "ID:") ห้ามถามสมาชิก
- "add_to_cart": ใส่ข้อมูลเมื่อลูกค้าตัดสินใจสั่งซื้อชัดเจน (ระบุสินค้า+ไซส์+จำนวน) เช่น "ขอ L 2 ตัว" หรือ "สั่งเลยค่ะ" — ให้ใส่ product_id (จากรายการสินค้า), size (ชื่อไซส์เช่น "L"), quantity (จำนวน) ถ้าไม่ใช่การสั่งซื้อให้ใส่ null/0
- "needs_admin": true ถ้าต้องการให้ Admin มาช่วย
- "restock_alert": ใส่เฉพาะเมื่อสมาชิกกด "ยืนยัน แจ้งเตือนฉัน 🔔" แล้ว → confirmed=true, product_id, product_name, size (phone ไม่บังคับ เพราะระบบแจ้งผ่านแชทได้เลย) ห้ามใส่ก่อนยืนยัน
- "new_state.ordering_for": "self" (ซื้อให้ตัวเอง) หรือ ชื่อเพื่อน เช่น "น้อง" (ซื้อให้เพื่อน) — ใส่ทุกครั้งที่ส่ง new_state
- "new_state.current_product_id": ⚠️ ถ้าตอบเกี่ยวกับสินค้าใดสินค้าหนึ่ง → ต้องใส่ ID ของสินค้านั้นเสมอ (ตัวเลขหลัง "ID:" ในรายการสินค้า) ห้ามปล่อยเป็น null ถ้ากำลังพูดถึงสินค้าอยู่ — ตั้ง null ได้เฉพาะเมื่อสมาชิกพูดถึงสินค้าหรือหมวดหมู่อื่นอย่างชัดเจนเท่านั้น (เช่น "ขอดูกระโปรงแทน" "เปลี่ยนเป็นเสื้อกาวน์") การถามต่อเนื่อง เช่น ไซส์/ราคา/ผ้า/ความยาว ห้าม null
- "new_state.measurements": ⚠️ ถ้าสมาชิกบอกขนาดร่างกาย (รอบอก/เอว/สะโพก) ในข้อความนี้ → ต้องอัปเดตทันที **ห้ามลืมใส่** รูปแบบ: {{"chest": 32, "waist": 28, "hips": 35}} ใส่เฉพาะค่าที่บอกมา ถ้าไม่มีการบอกขนาดให้ละ field นี้ทิ้งไป
- "new_state.self_name": ถ้าสมาชิกบอกชื่อตัวเอง (เช่น "ฉันชื่ออรนภา") → ใส่ชื่อนั้น ใช้แทนชื่อ Account ในการทักทาย ถ้าไม่มีการบอกชื่อให้ละ field นี้ทิ้งไป"""

        # 11. Call Flash Lite (with Vision if size chart available)
        import os as _os
        from google import genai as _genai
        from google.genai import types as _genai_types
        _api_key = _os.environ.get('GEMINI_API_KEY', '')
        if not _api_key:
            return []
        _client = _genai.Client(api_key=_api_key)
        conversation = f"=== ประวัติแชท ===\n{history_text}\n👤 สมาชิก: {user_message_text}"
        _contents = [conversation]
        if size_chart_image_bytes:
            _contents.append(_genai_types.Part.from_bytes(data=size_chart_image_bytes, mime_type=size_chart_mime))
        # Use Flash (full) model when size chart vision is needed — better multi-step arithmetic
        _bot_model = 'gemini-2.5-flash' if size_chart_image_bytes else 'gemini-2.5-flash-lite'
        # Fallback model chain if primary is overloaded (503)
        _fallback_models = ['gemini-2.5-flash'] if not size_chart_image_bytes else []
        _all_models = [_bot_model] + _fallback_models
        _cfg = _genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3 if size_chart_image_bytes else 0.7,
            max_output_tokens=3000
        )
        raw = ''
        for _try_model in _all_models:
            try:
                _resp = _client.models.generate_content(
                    model=_try_model, contents=_contents, config=_cfg
                )
                raw = _resp.text or ''
                _bot_model = _try_model  # update for logging
                break
            except Exception as _api_err:
                _err_str = str(_api_err)
                if any(x in _err_str for x in ('503', 'UNAVAILABLE', '429', '404', 'NOT_FOUND', 'no longer available')):
                    print(f'[BOT] Model {_try_model} unavailable, trying next...')
                    continue
                raise  # re-raise other unexpected errors

        # 11. Parse JSON — handles: valid JSON, truncated JSON, plain text
        def _sanitize_json_str(s):
            """Fix unescaped newlines/tabs inside JSON string values (common Gemini issue)"""
            out, in_str, esc = [], False, False
            for c in s:
                if esc:
                    out.append(c); esc = False
                elif c == '\\':
                    out.append(c); esc = True
                elif c == '"':
                    out.append(c); in_str = not in_str
                elif in_str and c == '\n':
                    out.append('\\n')
                elif in_str and c == '\r':
                    out.append('\\r')
                elif in_str and c == '\t':
                    out.append('\\t')
                else:
                    out.append(c)
            return ''.join(out)

        m = _re.search(r'\{[\s\S]*\}', raw)
        parsed = {}
        _plain_text_fallback = ''
        if m:
            try:
                parsed = _json.loads(m.group())
            except Exception:
                try:
                    parsed = _json.loads(_sanitize_json_str(m.group()))
                except Exception:
                    # JSON truncated or malformed — try to extract "message" field directly
                    _msg_match = _re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', m.group())
                    if _msg_match:
                        _plain_text_fallback = _msg_match.group(1).replace('\\n', '\n').replace('\\"', '"')
                    else:
                        _plain_text_fallback = raw.strip()
                    print(f'[BOT] Truncated/invalid JSON | extracted={_plain_text_fallback[:80]}')
        else:
            raw_stripped = raw.strip()
            # Check if it looks like JSON that got split (starts with { but no closing })
            if raw_stripped.startswith('{') and '"message"' in raw_stripped:
                _msg_match = _re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_stripped)
                if _msg_match:
                    _plain_text_fallback = _msg_match.group(1).replace('\\n', '\n').replace('\\"', '"')
                    print(f'[BOT] Extracted message from truncated JSON | text={_plain_text_fallback[:80]}')
                else:
                    _plain_text_fallback = raw_stripped
            else:
                # Gemini returned genuine plain text — use directly
                _plain_text_fallback = raw_stripped
                if _plain_text_fallback:
                    print(f'[BOT] Plain text response | model={_bot_model} | text={_plain_text_fallback[:120]}')

        _raw_fallback = _plain_text_fallback
        # Safety net: if fallback looks like raw JSON (starts with { and contains "message":)
        # it means truncation happened and extraction failed — never show raw JSON to user
        if _raw_fallback and _raw_fallback.lstrip().startswith('{') and '"message"' in _raw_fallback:
            print(f'[BOT] Raw JSON leaked into fallback — suppressing | model={_bot_model} | len={len(_raw_fallback)}')
            _raw_fallback = ''
        bot_text = (parsed.get('message', '').strip()
                    or _raw_fallback
                    or 'ขอโทษนะคะ ลองใหม่อีกครั้งได้เลยค่ะ')
        if not bot_text or bot_text == 'ขอโทษนะคะ ลองใหม่อีกครั้งได้เลยค่ะ':
            print(f'[BOT] Empty/fallback | model={_bot_model} | user_msg={user_message_text[:80]}')
        quick_replies = parsed.get('quick_replies') or []
        show_product_ids = [int(x) for x in (parsed.get('show_product_ids') or []) if x]
        new_state = parsed.get('new_state') or {}
        needs_admin_flag = bool(parsed.get('needs_admin', False))
        add_to_cart_data = parsed.get('add_to_cart') or {}
        _member_restock_raw = parsed.get('restock_alert') or {}

        # Handle restock_alert from member bot — save only when confirmed=True
        if (isinstance(_member_restock_raw, dict)
                and _member_restock_raw.get('confirmed') is True
                and _member_restock_raw.get('product_id')):
            try:
                _mra_pid = int(_member_restock_raw['product_id'])
                _mra_size = str(_member_restock_raw.get('size') or '').strip()
                _mra_phone = str(_member_restock_raw.get('phone') or '').strip() or None
                _mra_pname = str(_member_restock_raw.get('product_name') or '').strip()
                with get_db_connection() as _mra_conn:
                    with _mra_conn.cursor() as _mra_cur:
                        _mra_cur.execute('''
                            INSERT INTO restock_alerts (product_id, size, product_name, user_id, phone, status)
                            VALUES (%s, %s, %s, %s, %s, 'pending')
                        ''', (_mra_pid, _mra_size, _mra_pname, reseller_id, _mra_phone))
                        _mra_conn.commit()
                print(f'[MemberBot] Restock alert saved: pid={_mra_pid} size={_mra_size} user={reseller_id}')
            except Exception as _mra_e:
                print(f'[MemberBot] restock_alert save error: {_mra_e}')

        # 12a. Auto add to cart if bot detected purchase intent
        cart_confirm_text = None
        atc_product_id = add_to_cart_data.get('product_id')
        atc_size = add_to_cart_data.get('size')
        atc_qty = int(add_to_cart_data.get('quantity') or 0)

        # Fallback: use current product from session if bot didn't specify
        if not atc_product_id and session_data.get('current_product_id'):
            atc_product_id = session_data['current_product_id']

        if atc_product_id and atc_size and atc_qty > 0:
            try:
                import time as _time
                atc_product_id = int(atc_product_id)

                # Deduplication: skip if same SKU was added by bot within the last 60 seconds
                _last_bot_cart = session_data.get('last_bot_cart') or {}
                _last_sku_key = f'{atc_product_id}_{str(atc_size).lower()}'
                _last_added_at = _last_bot_cart.get('key') == _last_sku_key and _last_bot_cart.get('added_at', 0)
                _now_ts = _time.time()
                if _last_added_at and (_now_ts - float(_last_added_at)) < 60:
                    # Duplicate within 60 s — skip cart add silently
                    pass
                else:
                    # Find SKU by product + size value (via option values OR sku_code suffix)
                    cursor.execute('''
                        SELECT s.id as sku_id, s.price, s.stock, ptp.discount_percent
                        FROM skus s
                        LEFT JOIN product_tier_pricing ptp
                            ON ptp.product_id = s.product_id AND ptp.tier_id = %s
                        WHERE s.product_id = %s AND (
                            s.id IN (
                                SELECT svm.sku_id FROM sku_values_map svm
                                JOIN option_values ov ON ov.id = svm.option_value_id
                                JOIN options o ON o.id = ov.option_id
                                WHERE LOWER(o.name) IN ('ไซส์','size','sz','ขนาด')
                                  AND LOWER(ov.value) = LOWER(%s)
                            )
                            OR s.sku_code ILIKE %s
                        )
                        ORDER BY s.id
                        LIMIT 1
                    ''', (reseller_tier_id or 0, atc_product_id, str(atc_size), '%-' + str(atc_size)))
                    sku_row = cursor.fetchone()

                    if sku_row and sku_row['stock'] >= atc_qty:
                        # Get/create cart
                        cursor.execute('''
                            INSERT INTO carts (user_id, status)
                            VALUES (%s, 'active')
                            ON CONFLICT (user_id, status) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                            RETURNING id
                        ''', (reseller_id,))
                        cart_id = cursor.fetchone()['id']

                        retail_price = float(sku_row['price'])
                        discount_pct = float(sku_row['discount_percent'] or 0)

                        # Upsert: SET quantity = EXCLUDED.quantity (idempotent — not cumulative)
                        # so if bot fires twice for same intent, cart quantity won't double
                        cursor.execute('''
                            INSERT INTO cart_items (cart_id, sku_id, quantity, unit_price, tier_discount_percent)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (cart_id, sku_id) DO UPDATE
                              SET quantity = EXCLUDED.quantity,
                                  unit_price = EXCLUDED.unit_price,
                                  tier_discount_percent = EXCLUDED.tier_discount_percent,
                                  updated_at = CURRENT_TIMESTAMP
                        ''', (cart_id, sku_row['sku_id'], atc_qty, retail_price, discount_pct))

                        # Record in session so duplicate bot fire within 60 s is skipped
                        session_data['last_bot_cart'] = {
                            'key': _last_sku_key,
                            'added_at': _now_ts
                        }

                        cart_confirm_text = (
                            f'น้องนุ่นนำสินค้าใส่ตะกร้าให้แล้วนะคะ 🛒 ({atc_size} x{atc_qty} ชิ้น) '
                            f'ขอบคุณที่ให้ความไว้วางใจอุดหนุนนะคะ 🙏 '
                            f'ยังสนใจสินค้าอื่นเพิ่มเติมไหมคะ?'
                        )
                    elif sku_row and sku_row['stock'] < atc_qty:
                        cart_confirm_text = f'ขอโทษนะคะ ไซส์ {atc_size} เหลือสต็อกแค่ {sku_row["stock"]} ชิ้นค่ะ ต้องการปรับจำนวนไหมคะ?'
                    else:
                        cart_confirm_text = f'ขอโทษนะคะ ไม่พบสินค้าไซส์ {atc_size} ในระบบค่ะ กรุณาตรวจสอบไซส์อีกครั้งนะคะ'
            except Exception as _cart_err:
                print(f'[BOT] Cart add error: {_cart_err}')

        # 12. Save bot message(s)
        saved_msgs = []
        row = _bot_save_message(cursor, conn, thread_id, bot_user_id, bot_text, quick_replies if quick_replies else None)
        saved_msgs.append({'id': row['id'], 'created_at': row['created_at'].isoformat()})

        for pid in show_product_ids[:3]:
            row2 = _bot_save_message(cursor, conn, thread_id, bot_user_id, '', None, product_id=pid)
            saved_msgs.append({'id': row2['id'], 'created_at': row2['created_at'].isoformat()})

        # 12b. Save cart confirmation message (shown after main bot reply)
        if cart_confirm_text:
            cart_qr = ['ดูสินค้าอื่น', 'ไปที่ตะกร้า', 'ชำระเงิน']
            row_cart = _bot_save_message(cursor, conn, thread_id, bot_user_id, cart_confirm_text, cart_qr)
            saved_msgs.append({'id': row_cart['id'], 'created_at': row_cart['created_at'].isoformat()})

        # 13. Update session state + needs_admin
        # Sanitize new_state — Gemini may return text IDs; coerce to int or None
        for _k in ('category_id', 'current_product_id'):
            if _k in new_state:
                try: new_state[_k] = int(new_state[_k]) if new_state[_k] not in (None, 'null', '') else None
                except (ValueError, TypeError): new_state[_k] = None
        # Fix 3: Protect current_product_id from AI nullification when context was NOT switched
        # If N-gram did NOT detect a context switch (_ngram_cleared_context=False) AND Gemini
        # returned current_product_id=None, but the session had a valid product → restore it.
        _session_product_id = _safe_int(session_data.get('current_product_id'))
        if (_session_product_id
                and not _ngram_cleared_context
                and 'current_product_id' in new_state
                and new_state.get('current_product_id') is None):
            new_state['current_product_id'] = _session_product_id
        # Auto-fill current_product_id from show_product_ids if Gemini forgot to set it
        if show_product_ids and not new_state.get('current_product_id'):
            new_state['current_product_id'] = show_product_ids[0]
            if not new_state.get('state'):
                new_state['state'] = 'VIEWING_PRODUCT'

        # Merge measurements: preserve existing + override with new values from this turn
        _new_meas = new_state.pop('measurements', None)
        _new_self_name = new_state.pop('self_name', None)
        # Extract ordering_for from new_state (keep 'self' as default)
        _new_ordering_for = new_state.get('ordering_for') or _ordering_for or 'self'
        merged_state = {**session_data, **new_state}
        merged_state['ordering_for'] = _new_ordering_for
        # Persist self_name to DB if provided
        if _new_self_name and isinstance(_new_self_name, str) and _new_self_name.strip():
            try:
                cursor.execute('SELECT body_measurements FROM users WHERE id = %s', (reseller_id,))
                _bm_sn = cursor.fetchone()
                _bm_sn_dict = {}
                if _bm_sn and _bm_sn.get('body_measurements'):
                    _bm_sn_dict = _bm_sn['body_measurements'] if isinstance(_bm_sn['body_measurements'], dict) else {}
                _bm_sn_dict['self_name'] = _new_self_name.strip()
                cursor.execute('UPDATE users SET body_measurements = %s::jsonb WHERE id = %s',
                               (_json.dumps(_bm_sn_dict), reseller_id))
            except Exception as _sn_err:
                print(f'[BOT] self_name save error: {_sn_err}')
        if _new_meas and isinstance(_new_meas, dict):
            # Remove Gemini-supplied measured_at (server sets it)
            _new_meas.pop('measured_at', None)
            # Merge individual fields so partial update doesn't wipe other measurements
            _existing_meas = merged_state.get('measurements') or {}
            _merged_meas = {**_existing_meas, **_new_meas}
            _merged_meas['measured_at'] = _dt.utcnow().isoformat()
            merged_state['measurements'] = _merged_meas
            # Persist to users.body_measurements (permanent, no TTL)
            try:
                cursor.execute('SELECT body_measurements FROM users WHERE id = %s', (reseller_id,))
                _bm_cur = cursor.fetchone()
                _bm_dict = {}
                if _bm_cur and _bm_cur.get('body_measurements'):
                    _bm_dict = _bm_cur['body_measurements'] if isinstance(_bm_cur['body_measurements'], dict) else {}
                _save_meas = {k: v for k, v in _merged_meas.items() if k != 'measured_at'}
                if _new_ordering_for == 'self':
                    _bm_dict['self'] = _save_meas
                else:
                    if 'friends' not in _bm_dict:
                        _bm_dict['friends'] = {}
                    _bm_dict['friends'][_new_ordering_for] = _save_meas
                cursor.execute('UPDATE users SET body_measurements = %s::jsonb WHERE id = %s',
                               (_json.dumps(_bm_dict), reseller_id))
            except Exception as _bm_err:
                print(f'[BOT] body_measurements save error: {_bm_err}')
        elif _meas:
            # Keep existing valid measurements (already loaded above)
            merged_state['measurements'] = _meas
        cursor.execute('''
            UPDATE chat_threads SET bot_session_data = %s::jsonb,
                needs_admin = %s, needs_admin_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE needs_admin_at END
            WHERE id = %s
        ''', (_json.dumps(merged_state), needs_admin_flag, needs_admin_flag, thread_id))

        conn.commit()

        # 14. Push notification to reseller
        try:
            send_push_notification(reseller_id, f'💬 {bot_name}', bot_text[:100], url='/reseller#chat', tag=f'bot-{thread_id}', notification_type='chat')
        except Exception:
            pass

        cursor.close()
        return saved_msgs

    except Exception as e:
        import traceback as _tb
        print(f'[BOT] Error: {e}')
        _tb.print_exc()
        return []


@member_bot_bp.route('/api/chat/threads/<int:thread_id>/messages', methods=['POST'])
@login_required
def send_chat_message(thread_id):
    """Send a message to a thread"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Verify access
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        data = request.get_json()
        content = data.get('content', '').strip()
        attachments = data.get('attachments', [])
        product_id = data.get('product_id', None)
        order_id = data.get('order_id', None)
        coupon_id = data.get('coupon_id', None)
        
        if not content and not attachments and not product_id and not order_id and not coupon_id:
            return jsonify({'error': 'Message content, attachments or product required'}), 400
        
        sender_type = 'reseller' if role_name == 'Reseller' else 'admin'
        
        # If admin sends a coupon, auto-assign it to the reseller
        if coupon_id and sender_type == 'admin':
            reseller_id = thread['reseller_id']
            cursor.execute('''
                INSERT INTO user_coupons (user_id, coupon_id, status)
                VALUES (%s, %s, 'ready')
                ON CONFLICT (user_id, coupon_id) DO NOTHING
            ''', (reseller_id, coupon_id))
        
        # Insert message
        cursor.execute('''
            INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, product_id, order_id, coupon_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at
        ''', (thread_id, user_id, sender_type, content, product_id, order_id, coupon_id))
        result = cursor.fetchone()
        message_id = result['id']
        
        # Insert attachments
        for attachment in attachments:
            cursor.execute('''
                INSERT INTO chat_attachments (message_id, file_url, file_name, file_type, file_size)
                VALUES (%s, %s, %s, %s, %s)
            ''', (message_id, attachment.get('file_url'), attachment.get('file_name'),
                  attachment.get('file_type'), attachment.get('file_size')))
        
        # Update thread last message
        if content:
            preview = content[:100]
        elif order_id:
            preview = '[🧾 คำสั่งซื้อ]'
        elif product_id:
            preview = '[📦 สินค้า]'
        elif coupon_id:
            preview = '[🎟️ คูปอง]'
        else:
            preview = '[รูปภาพ]'
        cursor.execute('''
            UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s
            WHERE id = %s
        ''', (preview, thread_id))
        
        cursor.execute('UPDATE chat_threads SET is_archived = FALSE WHERE id = %s AND is_archived = TRUE', (thread_id,))
        
        # Schedule email notification for recipient
        recipient_id = thread['reseller_id'] if sender_type == 'admin' else None
        if recipient_id is None and sender_type == 'reseller':
            # Get any admin to notify (in real system, notify all admins or assigned admin)
            cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin') LIMIT 1")
            admin = cursor.fetchone()
            if admin:
                recipient_id = admin['id']
        
        if recipient_id:
            # Check user notification settings
            cursor.execute('''
                SELECT email_enabled, email_delay_minutes 
                FROM chat_notification_settings WHERE user_id = %s
            ''', (recipient_id,))
            settings = cursor.fetchone()
            
            if settings is None or settings['email_enabled']:
                delay_minutes = settings['email_delay_minutes'] if settings else 10
                cursor.execute('''
                    INSERT INTO chat_pending_emails (user_id, thread_id, message_id, scheduled_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '%s minutes')
                ''', (recipient_id, thread_id, message_id, delay_minutes))
        
        conn.commit()
        
        # Send push notification to recipient
        print(f"[CHAT-PUSH] sender={user_id} ({sender_type}), recipient={recipient_id}, thread={thread_id}")
        if recipient_id:
            cursor.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
            sender_info = cursor.fetchone()
            sender_name = sender_info['full_name'] if sender_info else 'ผู้ใช้'
            push_body = content[:100] if content else ('ส่งสินค้ามาให้ดู' if product_id else 'ส่งไฟล์แนบ')
            push_url = '/admin#chat' if sender_type == 'reseller' else '/reseller#chat'
            try:
                print(f"[CHAT-PUSH] Sending push to recipient {recipient_id}: {sender_name} -> {push_body[:30]}")
                import time as _t
                send_push_notification(
                    recipient_id,
                    f'💬 {sender_name}',
                    push_body,
                    url=push_url,
                    tag=f'chat-{thread_id}-{int(_t.time()*1000)}',
                    notification_type='chat'
                )
            except Exception as e:
                print(f"[CHAT-PUSH] Error sending to recipient: {str(e)[:200]}")
        else:
            print(f"[CHAT-PUSH] No recipient_id found, skipping push")
        
        if sender_type == 'reseller':
            try:
                cursor2 = conn.cursor()
                cursor2.execute('''
                    SELECT DISTINCT ps.user_id FROM push_subscriptions ps
                    JOIN users u ON u.id = ps.user_id
                    JOIN roles r ON r.id = u.role_id
                    WHERE r.name IN ('Super Admin', 'Assistant Admin') AND ps.user_id != %s
                ''', (recipient_id if recipient_id else 0,))
                other_admins = [row[0] for row in cursor2.fetchall()]
                cursor2.close()
                print(f"[CHAT-PUSH] Also notifying other admins: {other_admins}")
                
                cursor3 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor3.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
                rinfo = cursor3.fetchone()
                cursor3.close()
                rname = rinfo['full_name'] if rinfo else 'รีเซลเลอร์'
                
                for admin_id in other_admins:
                    try:
                        send_push_notification(admin_id, f'💬 {rname}', content[:100] if content else 'ส่งข้อความใหม่', url='/admin#chat', tag=f'chat-{thread_id}-{int(_t.time()*1000)}')
                    except Exception as e:
                        print(f"[CHAT-PUSH] Error notifying admin {admin_id}: {str(e)[:100]}")
            except Exception as e:
                print(f"[CHAT-PUSH] Error in admin broadcast: {str(e)[:200]}")
        
        # Trigger bot auto-reply in background thread (non-blocking)
        reseller_id_for_bot = thread['reseller_id']
        if sender_type == 'reseller' and content:
            def _run_bot_async(tid, rid, msg_text):
                bot_conn = None
                try:
                    bot_conn = get_db()
                    _bot_chat_reply(tid, rid, msg_text, bot_conn)
                except Exception as e:
                    print(f'[BOT] Auto-reply error: {e}')
                finally:
                    if bot_conn:
                        try: bot_conn.close()
                        except: pass
            threading.Thread(
                target=_run_bot_async,
                args=(thread_id, reseller_id_for_bot, content),
                daemon=True
            ).start()

        # When admin sends manually → pause bot for 2 hours
        if sender_type == 'admin':
            try:
                cursor.execute('''
                    UPDATE chat_threads SET bot_paused_until = CURRENT_TIMESTAMP + INTERVAL '2 hours',
                        needs_admin = FALSE WHERE id = %s
                ''', (thread_id,))
                conn.commit()
            except Exception:
                pass

        return jsonify({
            'id': message_id,
            'created_at': result['created_at'].isoformat(),
            'bot_messages': []
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


@member_bot_bp.route('/api/chat/threads/<int:thread_id>/request-admin', methods=['POST'])
@login_required
def chat_request_admin(thread_id):
    """Reseller presses 'ขอคุยกับ Admin' button"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session['user_id']
        role_name = session.get('role', '')
        cursor.execute('SELECT reseller_id FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403
        cursor.execute('''
            UPDATE chat_threads SET needs_admin = TRUE, needs_admin_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (thread_id,))
        # Send system message
        cursor.execute("SELECT id FROM users WHERE role_id=(SELECT id FROM roles WHERE name='Super Admin') ORDER BY id LIMIT 1")
        admin_row = cursor.fetchone()
        bot_user_id = admin_row['id'] if admin_row else user_id
        cursor.execute('''
            INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, is_bot)
            VALUES (%s, %s, 'admin', %s, TRUE) RETURNING id, created_at
        ''', (thread_id, bot_user_id, '🙋 สมาชิกต้องการคุยกับ Admin กรุณารอสักครู่นะคะ'))
        row = cursor.fetchone()
        cursor.execute('''
            UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = '🙋 รอ Admin' WHERE id = %s
        ''', (thread_id,))
        conn.commit()
        # Notify all admins via push
        try:
            cursor.execute('SELECT full_name FROM users WHERE id = %s', (user_id,))
            rinfo = cursor.fetchone()
            rname = rinfo['full_name'] if rinfo else 'สมาชิก'
            cursor.execute('''
                SELECT DISTINCT ps.user_id FROM push_subscriptions ps
                JOIN users u ON u.id = ps.user_id
                JOIN roles r ON r.id = u.role_id
                WHERE r.name IN ('Super Admin', 'Assistant Admin')
            ''')
            admins = [r['user_id'] for r in cursor.fetchall()]
            for aid in admins:
                try:
                    send_push_notification(aid, f'🙋 {rname} ขอคุยกับ Admin', 'กดเพื่อเปิดแชท', url='/admin#chat', tag=f'req-admin-{thread_id}', notification_type='chat')
                except Exception:
                    pass
        except Exception as e:
            print(f'[BOT] Request admin notify error: {e}')
        return jsonify({'id': row['id'], 'created_at': row['created_at'].isoformat()}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@member_bot_bp.route('/api/chat/threads/<int:thread_id>/bot-status', methods=['GET'])
@login_required
def chat_bot_status(thread_id):
    """Return bot status for a thread — accessible by both Admin and Reseller."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        user_id = session.get('user_id')
        role_name = session.get('role', '')

        cursor.execute('SELECT reseller_id, bot_paused_until FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        if role_name == 'Reseller' and thread['reseller_id'] != user_id:
            return jsonify({'error': 'Access denied'}), 403

        cursor.execute('SELECT bot_chat_enabled, bot_chat_name FROM agent_settings WHERE id = 1')
        settings = cursor.fetchone() or {}
        global_enabled = bool(settings.get('bot_chat_enabled', True))
        bot_name = settings.get('bot_chat_name') or 'น้องนุ่น'

        from datetime import datetime as _dt2
        paused_until = thread.get('bot_paused_until')
        is_paused = bool(paused_until and paused_until > _dt2.utcnow())

        if not global_enabled:
            status = 'disabled'
        elif is_paused:
            status = 'paused'
        else:
            status = 'active'

        return jsonify({'status': status, 'bot_name': bot_name, 'global_enabled': global_enabled}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@member_bot_bp.route('/api/chat/threads/<int:thread_id>/toggle-bot', methods=['POST'])
@admin_required
def chat_toggle_bot(thread_id):
    """Admin manually pauses or resumes the bot for a specific thread."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT bot_paused_until FROM chat_threads WHERE id = %s', (thread_id,))
        thread = cursor.fetchone()
        if not thread:
            return jsonify({'error': 'Thread not found'}), 404
        from datetime import datetime as _dt
        currently_paused = thread.get('bot_paused_until') and thread['bot_paused_until'] > _dt.utcnow()
        if currently_paused:
            cursor.execute('UPDATE chat_threads SET bot_paused_until = NULL WHERE id = %s', (thread_id,))
            bot_active = True
        else:
            cursor.execute(
                "UPDATE chat_threads SET bot_paused_until = CURRENT_TIMESTAMP + INTERVAL '10 years' WHERE id = %s",
                (thread_id,)
            )
            bot_active = False
        conn.commit()
        return jsonify({'bot_active': bot_active}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@member_bot_bp.route('/api/admin/bot-settings', methods=['GET', 'POST'])
@admin_required
def admin_bot_settings():
    """Get or update bot chat settings"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'GET':
            cursor.execute('SELECT bot_chat_enabled, bot_chat_name, bot_chat_persona FROM agent_settings WHERE id = 1')
            row = cursor.fetchone()
            return jsonify(dict(row) if row else {'bot_chat_enabled': True, 'bot_chat_name': 'น้องนุ่น', 'bot_chat_persona': ''}), 200
        data = request.get_json()
        cursor.execute('''
            UPDATE agent_settings SET bot_chat_enabled = %s, bot_chat_name = %s, bot_chat_persona = %s WHERE id = 1
        ''', (bool(data.get('bot_chat_enabled', True)), (data.get('bot_chat_name') or 'น้องนุ่น')[:100], data.get('bot_chat_persona') or ''))
        conn.commit()
        return jsonify({'ok': True}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@member_bot_bp.route('/api/admin/bot-training', methods=['GET', 'POST'])
@login_required
def admin_bot_training():
    """List or create bot training examples (Q&A pairs)."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'GET':
            cursor.execute('SELECT * FROM bot_training_examples ORDER BY sort_order, id')
            rows = [dict(r) for r in cursor.fetchall()]
            return jsonify(rows), 200
        data = request.get_json() or {}
        q = (data.get('question_pattern') or '').strip()
        a = (data.get('answer_template') or '').strip()
        if not q or not a:
            return jsonify({'error': 'กรุณาระบุคำถามและคำตอบ'}), 400
        cursor.execute('''
            INSERT INTO bot_training_examples (question_pattern, answer_template, is_active, sort_order)
            VALUES (%s, %s, %s, %s) RETURNING *
        ''', (q, a, bool(data.get('is_active', True)), int(data.get('sort_order') or 0)))
        row = dict(cursor.fetchone())
        conn.commit()
        return jsonify(row), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@member_bot_bp.route('/api/admin/bot-training/<int:example_id>', methods=['PUT', 'DELETE'])
@login_required
def admin_bot_training_item(example_id):
    """Update or delete a bot training example."""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'DELETE':
            cursor.execute('DELETE FROM bot_training_examples WHERE id = %s', (example_id,))
            conn.commit()
            return jsonify({'ok': True}), 200
        data = request.get_json() or {}
        q = (data.get('question_pattern') or '').strip()
        a = (data.get('answer_template') or '').strip()
        if not q or not a:
            return jsonify({'error': 'กรุณาระบุคำถามและคำตอบ'}), 400
        cursor.execute('''
            UPDATE bot_training_examples
            SET question_pattern=%s, answer_template=%s, is_active=%s, sort_order=%s
            WHERE id=%s RETURNING *
        ''', (q, a, bool(data.get('is_active', True)), int(data.get('sort_order') or 0), example_id))
        row = cursor.fetchone()
        conn.commit()
        return jsonify(dict(row) if row else {}), 200
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@member_bot_bp.route('/api/chat/unread-count', methods=['GET'])
@login_required
def get_chat_unread_count():
    """Get total unread message count for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT COALESCE(SUM(
                    (SELECT COUNT(*) FROM chat_messages cm 
                     WHERE cm.thread_id = ct.id 
                     AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                           WHERE thread_id = ct.id AND user_id = %s), 0))
                ), 0) as total_unread
                FROM chat_threads ct
                WHERE ct.reseller_id = %s AND ct.is_archived = FALSE
            ''', (user_id, user_id))
        else:
            cursor.execute('''
                SELECT COALESCE(SUM(
                    (SELECT COUNT(*) FROM chat_messages cm 
                     WHERE cm.thread_id = ct.id 
                     AND cm.sender_type = 'reseller'
                     AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                           WHERE thread_id = ct.id AND user_id = %s), 0))
                ), 0) as total_unread
                FROM chat_threads ct
                WHERE ct.is_archived = FALSE
            ''', (user_id,))
        
        result = cursor.fetchone()
        return jsonify({'unread_count': result['total_unread']}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/new-messages', methods=['GET'])
@login_required
def get_chat_new_messages():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        since_id = request.args.get('since_id', 0, type=int)
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, cm.thread_id,
                       u.full_name as sender_name, cm.sender_type, cm.product_id
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE ct.reseller_id = %s 
                  AND cm.sender_type = 'admin'
                  AND cm.id > %s
                  AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                        WHERE thread_id = cm.thread_id AND user_id = %s), 0)
                ORDER BY cm.id ASC
                LIMIT 20
            ''', (user_id, since_id, user_id))
        else:
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, cm.thread_id,
                       u.full_name as sender_name, cm.sender_type, cm.product_id
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE cm.sender_type = 'reseller'
                  AND cm.id > %s
                  AND cm.id > COALESCE((SELECT last_read_message_id FROM chat_read_status 
                                        WHERE thread_id = cm.thread_id AND user_id = %s), 0)
                ORDER BY cm.id ASC
                LIMIT 20
            ''', (since_id, user_id))
        
        messages = cursor.fetchall()
        result = []
        for msg in messages:
            preview = msg['content'][:80] if msg['content'] else ('📦 ส่งสินค้ามาให้ดู' if msg['product_id'] else '📎 ส่งไฟล์แนบ')
            result.append({
                'id': msg['id'],
                'thread_id': msg['thread_id'],
                'sender_name': msg['sender_name'],
                'preview': preview,
                'created_at': msg['created_at'].isoformat()
            })
        
        chat_url = '/reseller#chat' if role_name == 'Reseller' else '/admin#chat'
        return jsonify({'messages': result, 'chat_url': chat_url}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/start/<int:reseller_id>', methods=['POST'])
@login_required
def start_chat_thread(reseller_id):
    """Start or get existing chat thread with a reseller"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        
        # Reseller can only start chat for themselves
        if role_name == 'Reseller' and reseller_id != user_id:
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if thread exists
        cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
        thread = cursor.fetchone()
        
        if thread:
            return jsonify({'thread_id': thread['id'], 'is_new': False}), 200
        
        # Create new thread
        cursor.execute('''
            INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id
        ''', (reseller_id,))
        new_thread = cursor.fetchone()
        conn.commit()
        
        return jsonify({'thread_id': new_thread['id'], 'is_new': True}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Quick Replies Management
@member_bot_bp.route('/api/chat/quick-replies', methods=['GET'])
@login_required
def get_quick_replies():
    """Get all quick reply templates"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT id, title, content, shortcut, sort_order
            FROM chat_quick_replies
            WHERE is_active = TRUE
            ORDER BY sort_order, title
        ''')
        
        replies = [dict(row) for row in cursor.fetchall()]
        return jsonify(replies), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/quick-replies', methods=['POST'])
@admin_required
def create_quick_reply():
    """Create a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        shortcut = data.get('shortcut', '').strip()
        
        if not title or not content:
            return jsonify({'error': 'Title and content required'}), 400
        
        cursor.execute('''
            INSERT INTO chat_quick_replies (title, content, shortcut, created_by)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (title, content, shortcut, session['user_id']))
        
        result = cursor.fetchone()
        conn.commit()
        
        return jsonify({'id': result['id'], 'message': 'Quick reply created'}), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/quick-replies/<int:reply_id>', methods=['PUT'])
@admin_required
def update_quick_reply(reply_id):
    """Update a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        data = request.get_json()
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        shortcut = data.get('shortcut', '').strip()
        
        cursor.execute('''
            UPDATE chat_quick_replies 
            SET title = %s, content = %s, shortcut = %s
            WHERE id = %s
        ''', (title, content, shortcut, reply_id))
        
        conn.commit()
        return jsonify({'message': 'Quick reply updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/quick-replies/<int:reply_id>', methods=['DELETE'])
@admin_required
def delete_quick_reply(reply_id):
    """Delete a quick reply template"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('UPDATE chat_quick_replies SET is_active = FALSE WHERE id = %s', (reply_id,))
        conn.commit()
        
        return jsonify({'message': 'Quick reply deleted'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Broadcast Messages
@member_bot_bp.route('/api/chat/broadcast', methods=['POST'])
@admin_required
def send_broadcast_message():
    """Send broadcast message to all or selected resellers"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        data = request.get_json()
        content = data.get('content', '').strip()
        title = data.get('title', '').strip()
        target_type = data.get('target_type', 'all')  # all, tier
        target_tier_id = data.get('target_tier_id')
        
        if not content:
            return jsonify({'error': 'Content required'}), 400
        
        user_id = session['user_id']
        
        # Create broadcast record
        cursor.execute('''
            INSERT INTO chat_broadcasts (sender_id, title, content, target_type, target_tier_id)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        ''', (user_id, title, content, target_type, target_tier_id))
        broadcast = cursor.fetchone()
        broadcast_id = broadcast['id']
        
        # Get target resellers
        if target_type == 'tier' and target_tier_id:
            cursor.execute('''
                SELECT id FROM users 
                WHERE role_id = (SELECT id FROM roles WHERE name = 'Reseller')
                AND tier_id = %s
            ''', (target_tier_id,))
        else:
            cursor.execute('''
                SELECT id FROM users 
                WHERE role_id = (SELECT id FROM roles WHERE name = 'Reseller')
            ''')
        
        resellers = cursor.fetchall()
        sent_count = 0
        
        for reseller in resellers:
            reseller_id = reseller['id']
            
            # Get or create thread
            cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
            thread = cursor.fetchone()
            
            if not thread:
                cursor.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (reseller_id,))
                thread = cursor.fetchone()
            
            thread_id = thread['id']
            
            # Insert broadcast message
            cursor.execute('''
                INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, is_broadcast, broadcast_id)
                VALUES (%s, %s, 'admin', %s, TRUE, %s)
            ''', (thread_id, user_id, content, broadcast_id))
            
            # Update thread
            preview = content[:100]
            cursor.execute('''
                UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s
                WHERE id = %s
            ''', (preview, thread_id))
            
            sent_count += 1
        
        # Update broadcast sent count
        cursor.execute('UPDATE chat_broadcasts SET sent_count = %s WHERE id = %s', (sent_count, broadcast_id))
        
        conn.commit()
        
        # Send push notifications to all target resellers
        broadcast_title = title if title else 'ประกาศจากแอดมิน'
        for reseller in resellers:
            try:
                send_push_notification(
                    reseller['id'],
                    f'📢 {broadcast_title}',
                    content[:100],
                    url='/reseller#chat',
                    tag=f'broadcast-{broadcast_id}',
                    notification_type='broadcast'
                )
            except Exception:
                pass
        
        return jsonify({
            'message': f'Broadcast sent to {sent_count} resellers',
            'broadcast_id': broadcast_id,
            'sent_count': sent_count
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

@member_bot_bp.route('/api/chat/broadcasts', methods=['GET'])
@admin_required
def get_broadcast_history():
    """Get broadcast message history"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT cb.id, cb.title, cb.content, cb.target_type, cb.sent_count, cb.created_at,
                   u.full_name as sender_name,
                   rt.name as target_tier_name
            FROM chat_broadcasts cb
            JOIN users u ON u.id = cb.sender_id
            LEFT JOIN reseller_tiers rt ON rt.id = cb.target_tier_id
            ORDER BY cb.created_at DESC
            LIMIT 50
        ''')
        
        broadcasts = [dict(row) for row in cursor.fetchall()]
        return jsonify(broadcasts), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Notification Settings
@member_bot_bp.route('/api/chat/notification-settings', methods=['GET'])
@login_required
def get_notification_settings():
    """Get notification settings for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        
        cursor.execute('SELECT * FROM chat_notification_settings WHERE user_id = %s', (user_id,))
        settings = cursor.fetchone()
        
        if not settings:
            # Return defaults
            return jsonify({
                'email_enabled': True,
                'email_frequency': 'smart',
                'email_delay_minutes': 10,
                'in_app_enabled': True
            }), 200
        
        return jsonify(dict(settings)), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@member_bot_bp.route('/api/chat/notification-settings', methods=['PUT'])
@login_required
def update_notification_settings():
    """Update notification settings for current user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        user_id = session['user_id']
        data = request.get_json()
        
        email_enabled = data.get('email_enabled', True)
        email_frequency = data.get('email_frequency', 'smart')
        email_delay_minutes = data.get('email_delay_minutes', 10)
        in_app_enabled = data.get('in_app_enabled', True)
        
        cursor.execute('''
            INSERT INTO chat_notification_settings (user_id, email_enabled, email_frequency, email_delay_minutes, in_app_enabled)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET email_enabled = %s, email_frequency = %s, email_delay_minutes = %s, 
                          in_app_enabled = %s, updated_at = CURRENT_TIMESTAMP
        ''', (user_id, email_enabled, email_frequency, email_delay_minutes, in_app_enabled,
              email_enabled, email_frequency, email_delay_minutes, in_app_enabled))
        
        conn.commit()
        return jsonify({'message': 'Settings updated'}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Chat attachment upload
@member_bot_bp.route('/api/chat/upload', methods=['POST'])
@login_required
def upload_chat_attachment():
    """Upload file for chat message"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 
                         'application/pdf', 'application/msword',
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        
        if file.content_type not in allowed_types:
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Generate unique filename
        import uuid
        ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else ''
        unique_filename = f"chat_{uuid.uuid4().hex}.{ext}"
        
        # Save to object storage or static folder
        upload_folder = 'static/uploads/chat'
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        file_url = f'/static/uploads/chat/{unique_filename}'
        
        return jsonify({
            'file_url': file_url,
            'file_name': file.filename,
            'file_type': file.content_type,
            'file_size': os.path.getsize(file_path)
        }), 200
        
    except Exception as e:
        return handle_error(e)

# Search messages
@member_bot_bp.route('/api/chat/search', methods=['GET'])
@login_required
def search_chat_messages():
    """Search chat messages"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        user_id = session['user_id']
        role_name = session.get('role', '')
        query = request.args.get('q', '').strip()
        
        if not query or len(query) < 2:
            return jsonify([]), 200
        
        search_pattern = f'%{query}%'
        
        if role_name == 'Reseller':
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, ct.id as thread_id,
                       u.full_name as sender_name
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                WHERE ct.reseller_id = %s AND cm.content ILIKE %s
                ORDER BY cm.created_at DESC
                LIMIT 50
            ''', (user_id, search_pattern))
        else:
            cursor.execute('''
                SELECT cm.id, cm.content, cm.created_at, ct.id as thread_id,
                       u.full_name as sender_name,
                       r.full_name as reseller_name
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                JOIN users u ON u.id = cm.sender_id
                JOIN users r ON r.id = ct.reseller_id
                WHERE cm.content ILIKE %s
                ORDER BY cm.created_at DESC
                LIMIT 50
            ''', (search_pattern,))
        
        results = [dict(row) for row in cursor.fetchall()]
        return jsonify(results), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== PWA & PUSH NOTIFICATIONS ====================

