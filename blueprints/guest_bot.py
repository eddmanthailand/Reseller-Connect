from flask import Blueprint, request, jsonify
from database import get_db
import psycopg2.extras
import os
import threading
from blueprints.bot_cache import _BOT_CACHE, _bot_cache_get
from blueprints.push_utils import notify_admins_guest_lead

guest_bot_bp = Blueprint('guest_bot', __name__)

@guest_bot_bp.route('/api/public/chat/message', methods=['POST'])
def public_chat_message():
    """Guest chat bot for public catalog page — no login required."""
    import json as _json, re as _re
    try:
        data = request.json or {}
        user_msg = (data.get('message') or '').strip()[:500]
        history = data.get('history') or []   # [{role:'user'|'bot', text:'...'}]
        if not user_msg:
            return jsonify({'error': 'ข้อความว่างเปล่า'}), 400

        from google import genai as _genai
        from google.genai import types as _genai_types
        _api_key = os.environ.get('GEMINI_API_KEY', '')
        if not _api_key:
            return jsonify({'reply': 'ขออภัยค่ะ ระบบขัดข้องชั่วคราว กรุณาติดต่อ 083-668-2211 ได้เลยค่ะ'}), 200

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Log question (dedup via pg_trgm similarity ≥ 0.6)
        try:
            _norm = _re.sub(r'[^\wก-๙]', ' ', user_msg.lower()).strip()[:200]
            cursor.execute("""
                UPDATE guest_chat_log SET count=count+1, last_seen=NOW()
                WHERE id=(SELECT id FROM guest_chat_log WHERE similarity(normalized_q,%s)>=0.6
                          ORDER BY similarity(normalized_q,%s) DESC LIMIT 1)
            """, (_norm, _norm))
            if cursor.rowcount == 0:
                cursor.execute("INSERT INTO guest_chat_log(question,normalized_q) VALUES(%s,%s)",
                               (user_msg[:500], _norm))
            conn.commit()
        except Exception as _le:
            print(f'[GuestBot] log error: {_le}')
            try:
                conn.rollback()
                cursor.close()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            except Exception:
                pass

        # Bot name + persona — from agent_settings (same source as member bot)
        def _fetch_agent_settings():
            try:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("SELECT * FROM agent_settings WHERE id = 1")
                return c.fetchone() or {}
            except Exception:
                try: conn.rollback()
                except Exception: pass
                return {}
        if 'guest_agent_settings' not in _BOT_CACHE:
            _BOT_CACHE['guest_agent_settings'] = {'data': None, 'expires': 0}
        _agent_cfg = _bot_cache_get('guest_agent_settings', 600, _fetch_agent_settings)
        bot_name = _agent_cfg.get('bot_chat_name') or 'น้องนุ่น'
        extra_persona = _agent_cfg.get('bot_chat_persona') or ''

        # Training Q&A from Admin (bot_training_examples)
        def _fetch_training():
            try:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("""SELECT question_pattern, answer_template
                             FROM bot_training_examples
                             WHERE is_active = TRUE
                             ORDER BY sort_order, id""")
                return c.fetchall()
            except Exception:
                try: conn.rollback()
                except Exception: pass
                return []
        if 'guest_training' not in _BOT_CACHE:
            _BOT_CACHE['guest_training'] = {'data': None, 'expires': 0}
        training_rows = _bot_cache_get('guest_training', 600, _fetch_training)
        training_block = ''
        if training_rows:
            qa_lines = '\n'.join(
                f'Q: {r["question_pattern"]}\nA: {r["answer_template"]}' for r in training_rows
            )
            training_block = f'\n\n⚡ กฎเพิ่มเติมจาก Admin (ความสำคัญสูงสุด — ใช้ข้อมูลนี้แทนที่ค่า default ด้านล่างเสมอ หากมีข้อมูลตรงกัน):\n{qa_lines}'

        # Categories
        def _fetch_cats():
            try:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("SELECT name FROM categories WHERE is_active=true ORDER BY name")
                return [r['name'] for r in c.fetchall()]
            except Exception:
                try: conn.rollback()
                except Exception: pass
                return []
        if 'categories' not in _BOT_CACHE:
            _BOT_CACHE['categories'] = {'data': None, 'expires': 0}
        cats_list = _bot_cache_get('categories', 1800, _fetch_cats)
        cats_str = ', '.join(cats_list) or 'ไม่มีข้อมูล'

        # Promotions
        def _fetch_promos():
            try:
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("""SELECT name, promo_type, reward_type, reward_value,
                               condition_min_spend, start_date, end_date
                             FROM promotions
                             WHERE is_active=true AND (end_date IS NULL OR end_date >= NOW())
                             ORDER BY created_at DESC LIMIT 5""")
                return c.fetchall()
            except Exception:
                try: conn.rollback()
                except Exception: pass
                import traceback; traceback.print_exc()
                return None  # don't cache on error — retry next request
        if 'promotions' not in _BOT_CACHE:
            _BOT_CACHE['promotions'] = {'data': None, 'expires': 0}
        promos = _bot_cache_get('promotions', 300, _fetch_promos)
        promos_text = ''
        for p in (promos or []):
            _rv = p.get('reward_value') or 0
            if p.get('reward_type') in ('percent', 'discount_percent'):
                _reward_str = f"ลด {_rv:.0f}%"
            elif p.get('reward_type') in ('fixed', 'fixed_discount', 'fixed_amount'):
                _reward_str = f"ลด ฿{_rv:.0f}"
            elif 'shipping' in (p.get('reward_type') or ''):
                _reward_str = "ส่งฟรี"
            else:
                _reward_str = f"ลด {_rv:.0f}%"
            _min = f" (ซื้อขั้นต่ำ ฿{p['condition_min_spend']:.0f})" if p.get('condition_min_spend') else ""
            _p_end = p.get('end_date')
            _end = f" หมดเขต {_p_end.strftime('%d/%m/%Y') if hasattr(_p_end,'strftime') else str(_p_end)[:10]}" if _p_end else ""
            promos_text += f"  • {p['name']}: {_reward_str}{_min}{_end}\n"

        # Shipping rates + free shipping promotion
        def _fetch_shipping():
            try:
                conn.rollback()  # clear any aborted-transaction state from earlier silently-caught errors
                c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                c.execute("SELECT min_weight, max_weight, rate FROM shipping_weight_rates ORDER BY sort_order")
                rates = c.fetchall()
                c.execute("SELECT name, promo_type, min_order_value FROM shipping_promotions WHERE is_active=true AND (end_date IS NULL OR end_date >= NOW()) LIMIT 3")
                promos_ship = c.fetchall()
                c.close()
                if not rates:
                    return None  # don't cache empty — will retry next request
                return {'rates': rates, 'promos': promos_ship}
            except Exception:
                import traceback; traceback.print_exc()
                return None  # don't cache on error — will retry next request
        if 'shipping_data' not in _BOT_CACHE:
            _BOT_CACHE['shipping_data'] = {'data': None, 'expires': 0}
        _ship_data = _bot_cache_get('shipping_data', 3600, _fetch_shipping)
        _ship_rates = (_ship_data or {}).get('rates', [])
        _ship_promos = (_ship_data or {}).get('promos', [])
        shipping_text = ''
        if _ship_rates:
            _rate_lines = []
            for r in _ship_rates:
                _max = f"{r['max_weight']}g" if r['max_weight'] else 'ขึ้นไป'
                _rate_lines.append(f"{r['min_weight']}-{_max}: {r['rate']:.0f} บาท")
            shipping_text = 'อัตราค่าส่ง: ' + ' | '.join(_rate_lines)
        if _ship_promos:
            for sp in _ship_promos:
                if sp.get('promo_type') == 'free_shipping' and sp.get('min_order_value'):
                    shipping_text += f"\n🎁 ส่งฟรีเมื่อซื้อครบ ฿{float(sp['min_order_value']):.0f}"
        if not shipping_text:
            shipping_text = 'ค่าส่งขึ้นอยู่กับน้ำหนักสินค้า สอบถามเพิ่มเติมได้ในแชทนี้ค่ะ'

        # Parse measurements from conversation history (session memory)
        _session_meas = {}
        for _h in history:
            if _h.get('role') == 'user':
                _ht = str(_h.get('text', ''))
                for _pat, _key in [(r'อก\s*(\d+)', 'chest'), (r'เอว\s*(\d+)', 'waist'), (r'สะโพก\s*(\d+)', 'hips')]:
                    _m = _re.search(_pat, _ht)
                    if _m:
                        _session_meas[_key] = int(_m.group(1))
        for _pat, _key in [(r'อก\s*(\d+)', 'chest'), (r'เอว\s*(\d+)', 'waist'), (r'สะโพก\s*(\d+)', 'hips')]:
            _m = _re.search(_pat, user_msg)
            if _m:
                _session_meas[_key] = int(_m.group(1))
        _meas_parts = []
        if _session_meas.get('chest'): _meas_parts.append(f"รอบอก {_session_meas['chest']} นิ้ว")
        if _session_meas.get('waist'): _meas_parts.append(f"รอบเอว {_session_meas['waist']} นิ้ว")
        if _session_meas.get('hips'):  _meas_parts.append(f"รอบสะโพก {_session_meas['hips']} นิ้ว")
        meas_text = ', '.join(_meas_parts) if _meas_parts else '(ยังไม่ได้บอกขนาด)'

        # Question count — upsell nudge after 5th question
        _user_q_count = sum(1 for _h in history if _h.get('role') == 'user') + 1
        _upsell_note = ''
        if _user_q_count >= 5:
            _upsell_note = (
                '\n\n[ใส่ท้ายคำตอบ] หลังตอบคำถามแล้ว ให้เพิ่มประโยคสั้นชวนสมัครสมาชิก'
                ' เช่น "สมัครสมาชิกฟรีเพื่อรับราคาพิเศษและสิทธิ์เพิ่มเติมได้เลยนะคะ 😊"'
                ' และให้ใส่ "สมัครสมาชิกฟรี" ใน quick_replies ด้วย'
            )

        # Product search — Bronze (tier_id=1) pricing + image_url
        try:
            conn.rollback()
            cursor.close()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except Exception:
            pass
        BRONZE_TIER_ID = 1
        keywords = _re.sub(r'[^\wก-๙\s]', ' ', user_msg).split()
        keywords = [k for k in keywords if len(k) >= 2][:6]
        # For Thai text without spaces, also check for known product category/name terms as substrings
        _KNOWN_CAT_TERMS = ['เสื้อพยาบาล', 'กระโปรงพยาบาล', 'ชุดพยาบาล', 'กาวน์', 'เสื้อกาวน์',
                            'กางเกงพยาบาล', 'ชุดเดรส', 'ชุดพิธีการ', 'ผ้ากันเปื้อน', 'หมวกพยาบาล',
                            'ชุดผ่าตัด', 'เสื้อผ่าตัด', 'เสื้อ', 'กระโปรง', 'ชุด',
                            'ปกเทเลอร์แหลม', 'ปกเทเลอร์', 'ปกบัว', 'ปกคอวี', 'ปกตั้ง', 'ปกปีน',
                            'พยาบาล', 'แพทย์', 'สครับ', 'ยูนิฟอร์ม', 'สเตรท', 'ทรงตรง', 'เอวยืด']
        for _ckt in _KNOWN_CAT_TERMS:
            if _ckt in user_msg and _ckt not in keywords:
                keywords.append(_ckt)
        keywords = keywords[:8]
        products_text = ''
        prod_list = []
        prod_rows = []
        kw_conditions = ''
        kw_count_params = []
        # Extract product IDs already shown in history (for "show more" pagination)
        _shown_hist_ids = set()
        for _sh in history:
            for _sid in _re.findall(r'\(#(\d+)\)', str(_sh.get('text', ''))):
                _shown_hist_ids.add(int(_sid))
        _SHOW_MORE_KW = ('ดูเพิ่ม', 'แสดงเพิ่ม', 'เพิ่มเติม', 'ดูทั้งหมด', 'อีกบ้าง', 'แสดงอีก',
                         'ต้องการดูเพิ่ม', 'มีอีกไหม', 'ดูเพิ่มเติม', 'อยากดูเพิ่ม', 'ดูสินค้าเพิ่ม')
        _is_show_more = any(kw in user_msg for kw in _SHOW_MORE_KW)
        _remaining_count = 0
        if keywords:
            _kw_cond_part = ('p.name ILIKE %s OR p.bot_description ILIKE %s OR p.keywords ILIKE %s OR '
                             'EXISTS (SELECT 1 FROM product_categories _pc '
                             'JOIN categories _c ON _c.id = _pc.category_id '
                             'WHERE _pc.product_id = p.id AND _c.name ILIKE %s)')
            kw_conditions = ' OR '.join([_kw_cond_part for _ in keywords])
            kw_params = [BRONZE_TIER_ID, BRONZE_TIER_ID]
            kw_count_params = []
            for k in keywords:
                kw_params += [f'%{k}%', f'%{k}%', f'%{k}%', f'%{k}%']
                kw_count_params += [f'%{k}%', f'%{k}%', f'%{k}%', f'%{k}%']
            try:
                cursor.execute(f"""
                    SELECT p.id, p.name, p.bot_description, p.size_chart_group_id,
                           b.name as brand_name,
                           (SELECT c2.name FROM categories c2
                            JOIN product_categories pc2 ON pc2.category_id = c2.id
                            WHERE pc2.product_id = p.id LIMIT 1) as cat_name,
                           (SELECT pi.image_url FROM product_images pi
                            WHERE pi.product_id = p.id
                            ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                           MIN(s.price) as min_price,
                           ROUND(MIN(s.price) * (1 - COALESCE(
                               (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                                WHERE ptp.product_id = p.id AND ptp.tier_id = %s), 0
                           ) / 100), 0) as member_price,
                           COALESCE(
                               (SELECT ptp2.discount_percent FROM product_tier_pricing ptp2
                                WHERE ptp2.product_id = p.id AND ptp2.tier_id = %s), 0
                           ) as discount_pct,
                           STRING_AGG(DISTINCT s.sku_code, ' | ' ORDER BY s.sku_code) as sku_list
                    FROM products p
                    LEFT JOIN brands b ON b.id = p.brand_id
                    JOIN skus s ON s.product_id = p.id
                    WHERE p.status = 'active' AND ({kw_conditions})
                    GROUP BY p.id, p.name, p.bot_description, p.size_chart_group_id, b.name
                    ORDER BY p.name
                    LIMIT 15
                """, kw_params)
                prod_rows = cursor.fetchall()
                for pr in prod_rows:
                    brand = pr.get('brand_name') or ''
                    price = float(pr.get('min_price') or 0)
                    member_price = float(pr.get('member_price') or 0)
                    disc = float(pr.get('discount_pct') or 0)
                    bot_desc = pr.get('bot_description') or ''
                    cat = pr.get('cat_name') or ''
                    skus = pr.get('sku_list') or ''
                    img = pr.get('image_url') or ''
                    prod_list.append({
                        'id': pr['id'],
                        'name': pr['name'],
                        'image_url': img,
                        'price': f'฿{price:.0f}',
                        'member_price': f'฿{member_price:.0f}' if member_price > 0 else '',
                    })
                    if disc > 0 and member_price > 0:
                        products_text += f"  - {pr['name']} ราคาปกติ฿{price:.0f} → ราคาสมาชิก฿{member_price:.0f} (ลด{disc:.0f}%)"
                    else:
                        products_text += f"  - {pr['name']} ราคา฿{price:.0f}"
                    if cat:
                        products_text += f" หมวด:{cat}"
                    if skus:
                        products_text += f" ไซส์:{skus}"
                    if bot_desc:
                        products_text += f" ({bot_desc})"
                    if pr.get('size_chart_group_id'):
                        products_text += " [มีตารางไซส์]"
                    products_text += f" (#{pr['id']})\n"
            except Exception as _e:
                print(f'[GuestBot] product search error: {_e}')

        # Fallback: load all products when query is generic ("ขายอะไร","มีอะไร","ประเภทไหน"...)
        # or when keyword search returned nothing but user seems to be asking about products
        _GENERIC_PRODUCT_KW = ('ขายอะไร', 'มีอะไร', 'ประเภทไหน', 'สินค้าทั้งหมด', 'สินค้าอะไร',
                               'แบบไหนบ้าง', 'มีอะไรบ้าง', 'มีรุ่นไหน', 'ขายอะไรบ้าง',
                               'สินค้าประเภท', 'ผลิตอะไร', 'จำหน่ายอะไร', 'ดูสินค้าทั้งหมด')
        _PRODUCT_INTEREST_KW = ('สินค้า', 'ชุด', 'เสื้อ', 'กระโปรง', 'กางเกง', 'กาวน์', 'เดรส')
        _is_generic_query = any(kw in user_msg for kw in _GENERIC_PRODUCT_KW)
        _is_product_interest = any(kw in user_msg for kw in _PRODUCT_INTEREST_KW)
        if not prod_rows and (_is_generic_query or _is_product_interest):
            try:
                cursor.execute(f"""
                    SELECT p.id, p.name, p.bot_description, p.size_chart_group_id,
                           b.name as brand_name,
                           (SELECT c2.name FROM categories c2
                            JOIN product_categories pc2 ON pc2.category_id = c2.id
                            WHERE pc2.product_id = p.id LIMIT 1) as cat_name,
                           (SELECT pi.image_url FROM product_images pi
                            WHERE pi.product_id = p.id
                            ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                           MIN(s.price) as min_price,
                           ROUND(MIN(s.price) * (1 - COALESCE(
                               (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                                WHERE ptp.product_id = p.id AND ptp.tier_id = %s), 0
                           ) / 100), 0) as member_price,
                           COALESCE(
                               (SELECT ptp2.discount_percent FROM product_tier_pricing ptp2
                                WHERE ptp2.product_id = p.id AND ptp2.tier_id = %s), 0
                           ) as discount_pct,
                           STRING_AGG(DISTINCT s.sku_code, ' | ' ORDER BY s.sku_code) as sku_list
                    FROM products p
                    LEFT JOIN brands b ON b.id = p.brand_id
                    JOIN skus s ON s.product_id = p.id
                    WHERE p.status = 'active'
                    GROUP BY p.id, p.name, p.bot_description, p.size_chart_group_id, b.name
                    ORDER BY p.name
                    LIMIT 12
                """, [BRONZE_TIER_ID, BRONZE_TIER_ID])
                prod_rows = cursor.fetchall()
                for pr in prod_rows:
                    brand = pr.get('brand_name') or ''
                    price = float(pr.get('min_price') or 0)
                    member_price = float(pr.get('member_price') or 0)
                    disc = float(pr.get('discount_pct') or 0)
                    bot_desc = pr.get('bot_description') or ''
                    cat = pr.get('cat_name') or ''
                    skus = pr.get('sku_list') or ''
                    img = pr.get('image_url') or ''
                    prod_list.append({
                        'id': pr['id'],
                        'name': pr['name'],
                        'image_url': img,
                        'price': f'฿{price:.0f}',
                        'member_price': f'฿{member_price:.0f}' if member_price > 0 else '',
                    })
                    if disc > 0 and member_price > 0:
                        products_text += f"  - {pr['name']} ราคาปกติ฿{price:.0f} → ราคาสมาชิก฿{member_price:.0f} (ลด{disc:.0f}%)"
                    else:
                        products_text += f"  - {pr['name']} ราคา฿{price:.0f}"
                    if cat:
                        products_text += f" หมวด:{cat}"
                    if skus:
                        products_text += f" ไซส์:{skus}"
                    if pr.get('size_chart_group_id'):
                        products_text += " [มีตารางไซส์]"
                    products_text += f" (#{pr['id']})\n"
            except Exception as _fe:
                print(f'[GuestBot] fallback product search error: {_fe}')

        # "Show more" products: user explicitly asks to see more, load next batch excluding shown IDs
        if _is_show_more and _shown_hist_ids and not prod_rows:
            try:
                conn.rollback()
                _excl_list = list(_shown_hist_ids)[:60]
                cursor.execute(f"""
                    SELECT p.id, p.name, p.bot_description, p.size_chart_group_id,
                           b.name as brand_name,
                           (SELECT c2.name FROM categories c2
                            JOIN product_categories pc2 ON pc2.category_id = c2.id
                            WHERE pc2.product_id = p.id LIMIT 1) as cat_name,
                           (SELECT pi.image_url FROM product_images pi
                            WHERE pi.product_id = p.id
                            ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                           MIN(s.price) as min_price,
                           ROUND(MIN(s.price) * (1 - COALESCE(
                               (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                                WHERE ptp.product_id = p.id AND ptp.tier_id = %s), 0
                           ) / 100), 0) as member_price,
                           COALESCE(
                               (SELECT ptp2.discount_percent FROM product_tier_pricing ptp2
                                WHERE ptp2.product_id = p.id AND ptp2.tier_id = %s), 0
                           ) as discount_pct,
                           STRING_AGG(DISTINCT s.sku_code, ' | ' ORDER BY s.sku_code) as sku_list
                    FROM products p LEFT JOIN brands b ON b.id = p.brand_id
                    JOIN skus s ON s.product_id = p.id
                    WHERE p.status = 'active' AND p.id != ALL(%s)
                    GROUP BY p.id, p.name, p.bot_description, p.size_chart_group_id, b.name
                    ORDER BY p.name LIMIT 15
                """, [BRONZE_TIER_ID, BRONZE_TIER_ID, _excl_list])
                _sm_rows = cursor.fetchall()
                for pr in _sm_rows:
                    _sm_brand = pr.get('brand_name') or ''
                    _sm_price = float(pr.get('min_price') or 0)
                    _sm_mprice = float(pr.get('member_price') or 0)
                    _sm_disc = float(pr.get('discount_pct') or 0)
                    _sm_cat = pr.get('cat_name') or ''
                    _sm_skus = pr.get('sku_list') or ''
                    _sm_img = pr.get('image_url') or ''
                    prod_list.append({'id': pr['id'], 'name': pr['name'], 'image_url': _sm_img,
                                      'price': f'฿{_sm_price:.0f}',
                                      'member_price': f'฿{_sm_mprice:.0f}' if _sm_mprice > 0 else ''})
                    if _sm_disc > 0 and _sm_mprice > 0:
                        products_text += f"  - {pr['name']} ราคาปกติ฿{_sm_price:.0f} → ราคาสมาชิก฿{_sm_mprice:.0f} (ลด{_sm_disc:.0f}%)"
                    else:
                        products_text += f"  - {pr['name']} ราคา฿{_sm_price:.0f}"
                    if _sm_cat:
                        products_text += f" หมวด:{_sm_cat}"
                    if _sm_skus:
                        products_text += f" ไซส์:{_sm_skus}"
                    if pr.get('size_chart_group_id'):
                        products_text += " [มีตารางไซส์]"
                    products_text += f" (#{pr['id']})\n"
                prod_rows = _sm_rows
            except Exception as _sme:
                print(f'[GuestBot] show-more error: {_sme}')
                try:
                    conn.rollback()
                except Exception:
                    pass

        # Count total matching products to notify user of remaining not shown
        if prod_rows and len(prod_rows) >= 15:
            try:
                conn.rollback()
                _all_shown_ids = {r['id'] for r in prod_rows} | _shown_hist_ids
                if kw_conditions and kw_count_params:
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT p.id) FROM products p JOIN skus s ON s.product_id = p.id WHERE p.status = 'active' AND ({kw_conditions})",
                        kw_count_params
                    )
                else:
                    cursor.execute("SELECT COUNT(DISTINCT p.id) FROM products p JOIN skus s ON s.product_id = p.id WHERE p.status = 'active'")
                _total_cnt_row = cursor.fetchone()
                _total_cnt = int((_total_cnt_row or [0])[0])
                _remaining_count = max(0, _total_cnt - len(_all_shown_ids))
            except Exception as _ce:
                print(f'[GuestBot] count error: {_ce}')
                try:
                    conn.rollback()
                except Exception:
                    pass

        # If prod_rows empty but history mentions product IDs → load those products for size chart
        if not prod_rows and history:
            _hist_text = ' '.join(str(h.get('text', '')) for h in history[-8:])
            _hist_pids = [int(x) for x in _re.findall(r'\(#(\d+)\)', _hist_text)]
            if _hist_pids:
                try:
                    conn.rollback()
                    _hcur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    _hcur.execute('''
                        SELECT p.id, p.name, p.bot_description, p.size_chart_group_id, b.name as brand_name
                        FROM products p LEFT JOIN brands b ON b.id = p.brand_id
                        WHERE p.id = ANY(%s) AND p.status = \'active\'
                    ''', (_hist_pids[:5],))
                    prod_rows = _hcur.fetchall()
                    _hcur.close()
                except Exception as _hpe:
                    print(f'[GuestBot] history prod load error: {_hpe}')

        # Load text-based size chart from size_chart_groups (guest bot)
        _guest_size_chart_section = ''
        _GUEST_SIZE_KW = ('ไซส์', 'size', 'เอว', 'สะโพก', 'อก', 'วัด', 'ขนาด', 'ตาราง', 'เลือก', 'ช่วย')
        _recent_msgs = ' '.join(str(h.get('text', '')) for h in history[-4:]) + ' ' + user_msg
        if any(kw in _recent_msgs.lower() for kw in _GUEST_SIZE_KW) and prod_rows:
            try:
                _prod_ids = [r['id'] for r in prod_rows if r.get('id')]
                if _prod_ids:
                    conn.rollback()
                    _sc = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    _sc.execute('''
                        SELECT DISTINCT scg.id, scg.name, scg.columns, scg.rows,
                               scg.fabric_type, scg.allowances,
                               p.name as product_name
                        FROM size_chart_groups scg
                        JOIN products p ON p.size_chart_group_id = scg.id
                        WHERE p.id = ANY(%s)
                    ''', (_prod_ids,))
                    _chart_rows = _sc.fetchall()
                    _sc.close()
                    _seen_charts = set()
                    for _cr in _chart_rows:
                        if _cr['id'] in _seen_charts:
                            continue
                        _seen_charts.add(_cr['id'])
                        _cols = _cr['columns'] if isinstance(_cr['columns'], list) else json.loads(_cr['columns'])
                        _trows = _cr['rows'] if isinstance(_cr['rows'], list) else json.loads(_cr['rows'])
                        if not _cols or not _trows:
                            continue
                        _col_labels = []
                        for _c in _cols:
                            if isinstance(_c, dict):
                                _u = _c.get('unit', '')
                                _col_labels.append(f"{_c.get('name','')} ({_u})" if _u else _c.get('name',''))
                            else:
                                _col_labels.append(_c)
                        _chart_lines = [' | '.join(_col_labels)]
                        for _tr in _trows:
                            _vals = _tr.get('values', [])
                            _line = [_tr.get('size', '')] + _vals
                            _chart_lines.append(' | '.join(str(v) for v in _line))
                        _fabric_type = _cr.get('fabric_type') or 'non-stretch'
                        _alw = _cr.get('allowances') or {}
                        if isinstance(_alw, str):
                            try: _alw = json.loads(_alw)
                            except: _alw = {}
                        _alw_chest = _alw.get('chest', 1)
                        _alw_waist = _alw.get('waist', 1)
                        _alw_hip = _alw.get('hip', 1.5)
                        _fabric_label = 'ผ้าไม่ยืด (non-stretch)' if _fabric_type == 'non-stretch' else 'ผ้ายืด (stretch)'
                        _alw_line = f"ประเภทผ้า: {_fabric_label} | ค่าเผื่อ: อก +{_alw_chest}\" | เอว +{_alw_waist}\" | สะโพก +{_alw_hip}\""
                        _guest_size_chart_section += f"\n[ตารางขนาด: {_cr['name']}]\n{_alw_line}\n" + '\n'.join(_chart_lines) + '\n'
            except Exception as _sc_err:
                print(f'[GuestBot] size chart text error: {_sc_err}')
                try: conn.rollback()
                except Exception: pass

        # (size chart image loading removed — using text-based size chart from DB only)

        # Save guest lead if phone number detected in message
        _phone_pat = r'0[689]\d{8}|0\d{8,9}'
        _phone_match = _re.search(_phone_pat, user_msg)
        if _phone_match:
            try:
                _lconn = get_db()
                _lc = _lconn.cursor()
                _phone_val = _phone_match.group()
                _interest_val = user_msg[:300]
                _conv_summary = ' | '.join(
                    f"{_h.get('role','?')}: {str(_h.get('text',''))[:80]}"
                    for _h in history[-4:]
                )
                _lc.execute(
                    "INSERT INTO guest_leads (phone, interest_text, conversation_summary) VALUES (%s, %s, %s)",
                    (_phone_val, _interest_val, _conv_summary)
                )
                _lconn.commit()
                _lc.close()
                _lconn.close()
                notify_admins_guest_lead(
                    '📞 Guest ทิ้งเบอร์ในแชท',
                    f'เบอร์: {_phone_val} | {_interest_val[:60]}',
                    notification_type='lead',
                    push_url='/admin#guest-leads',
                    push_tag=f'guest-lead-phone-{_phone_val}'
                )
            except Exception as _le2:
                print(f'[GuestBot] lead save error: {_le2}')

        # Log custom-order / high-intent guest leads (even without phone)
        _CUSTOM_ORDER_KW = ('สั่งผลิต', 'ผลิตตามสั่ง', 'สั่งตัด', 'ตัดชุด', 'ทำยูนิฟอร์ม',
                            'ทำเครื่องแบบ', 'ออกแบบ', 'สั่งทำ', 'ต้องการสั่ง', 'อยากสั่ง',
                            'จำนวนมาก', 'wholesale', 'bulk', 'ซื้อเยอะ', 'ราคาส่ง')
        if any(kw in user_msg for kw in _CUSTOM_ORDER_KW):
            try:
                _lconn2 = get_db()
                _lc2 = _lconn2.cursor()
                _conv2 = ' | '.join(
                    f"{_h.get('role','?')}: {str(_h.get('text',''))[:80]}"
                    for _h in history[-4:]
                )
                _lc2.execute(
                    "INSERT INTO guest_leads (phone, interest_text, conversation_summary) VALUES (%s, %s, %s)",
                    (None, f'[สั่งผลิต/สนใจสั่ง] {user_msg[:300]}', _conv2)
                )
                _lconn2.commit()
                _lc2.close()
                _lconn2.close()
                notify_admins_guest_lead(
                    '🏭 Guest สนใจสั่งผลิต/ราคาส่ง',
                    user_msg[:80],
                    notification_type='lead',
                    push_url='/admin#guest-leads',
                    push_tag=f'guest-custom-order-{int(__import__("time").time())}'
                )
            except Exception as _le3:
                print(f'[GuestBot] custom order lead save error: {_le3}')

        cursor.close()
        conn.close()

        _GUEST_FABRIC_KNOWLEDGE = """
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

        system_prompt = f"""คุณชื่อ "{bot_name}" เป็นผู้ช่วยขายสินค้าออนไลน์ที่เป็นมืออาชีพ สุภาพ อ่อนน้อม และเน้นการปิดการขาย ตอบภาษาไทยเสมอ ลงท้าย "ค่ะ" เสมอ
{extra_persona}{training_block}
{_GUEST_FABRIC_KNOWLEDGE}

ข้อมูลบริษัท:
- บริษัท เคาท์มีอินดีไซน์ จำกัด ผลิตเสื้อผ้าคุณภาพสูง ทั้งแฟชั่นและยูนิฟอร์ม มีทั้งสินค้าสำเร็จรูปและสั่งผลิต
- ผลิตเสื้อผ้าให้แบรนด์แฟชั่นชั้นนำหลายแบรนด์ เช่น Curvf, Laboutique, oOdinaryjun
- ลูกค้าองค์กร เช่น Impact เมืองทองธานี, Unilever, มูลนิธิแม่ฟ้าหลวงฯ
- โทรศัพท์ 083-668-2211 (คุณเอ็ด) | เว็บไซต์: ekgshops.com
- 👤 สมัครสมาชิกฟรีได้ที่: ekgshops.com/register (รับราคาสมาชิกทันที)
- 📦 ราคาส่ง/Wholesale: ตอบจากข้อมูลในระบบที่มีให้เสมอ หากต้องการข้อมูลเพิ่มเติมแนะนำให้แจ้งในแชทนี้

กฎสำคัญ:
- ตอบเฉพาะข้อมูลที่มีในระบบ ห้ามแต่งข้อมูลเพิ่มเด็ดขาด
- 💰 ราคาสินค้า (เด็ดขาด): ราคาทุกตัวต้องอ่านมาจากรายการ "สินค้าที่เกี่ยวข้อง" ด้านล่างเท่านั้น — ห้ามเดาราคา ห้ามใช้ราคาจากประวัติแชทเป็นข้อมูลราคา ห้ามระบุตัวเลขราคาที่ไม่ปรากฏในรายการสินค้าด้านล่างเด็ดขาด ถ้ารายการสินค้าว่าง → ห้ามบอกราคา ให้บอกว่า "ขอทราบสินค้าที่ต้องการด้วยนะคะ น้องนุ่นจะเช็คราคาให้ค่ะ"
- ราคาที่แสดง: ราคาปกติ / ราคาสมาชิก (ได้รับเมื่อสมัครสมาชิก)
- 💳 ช่องทางชำระเงิน: ดูจากหัวข้อ "กฎเพิ่มเติมจาก Admin" ด้านบน และตอบตามนั้นเท่านั้น ห้ามแต่งข้อมูลชำระเงินเพิ่มเอง
- 🚚 รองรับ Dropship — ไม่ต้องสต็อกสินค้าเอง
- 🏭 รับผลิตตามสั่ง: ถ้าสนใจ ถามทีละข้อ: 1)รูปแบบ 2)รูปตัวอย่าง 3)จำนวน 4)วันที่ 5)เบอร์โทร
- 🚫 ห้ามสร้างโปรโมชั่น ส่วนลด หรือข้อเสนอพิเศษที่ไม่มีอยู่ในหัวข้อ "โปรโมชั่นปัจจุบัน" ด้านล่างเด็ดขาด — ถ้าไม่มีโปรโมชั่นในระบบ ให้บอกตรงๆ ว่า "ขณะนี้ไม่มีโปรโมชั่นพิเศษค่ะ"
- ✅ การยืนยันสินค้า: ถ้าลูกค้าพิมพ์ชื่อสินค้าที่ตรงกับรายการด้านล่างอย่างชัดเจน (เช่น พิมพ์ชื่อเต็มหรือชื่อใกล้เคียง ≥70%) → ข้ามการถามยืนยัน "ใช่ไหมคะ" แสดงรายละเอียดสินค้านั้นได้เลยทันที เฉพาะเมื่อไม่แน่ใจ (คำกำกวมหรือตรงกับหลายสินค้า) จึงถามยืนยัน
- 🖼️ show_product_ids: ใส่ product ID ใน 2 กรณีนี้:
  1) ลูกค้าถามสินค้าประเภทใดประเภทหนึ่งชัดเจน เช่น "กระโปรงมีไหม" "มีเสื้ออะไรบ้าง" "กาวน์มีไหม" → ใส่ ID ทุกรายการที่ตรงประเภทนั้น
  2) ลูกค้า "ขอดูรูป/ดูสินค้า/ส่งรูป/ดูแบบ/อยากเห็น" ชัดเจน
  * product ID คือตัวเลขใน "(#XX)" ที่ต่อท้ายชื่อสินค้าในรายการด้านล่าง เช่น "(#42)" = ใส่ 42 ลงใน show_product_ids — นี่คือรหัสภายใน ห้ามนำไปแสดงในข้อความตอบเด็ดขาด
  * ❌ ห้ามเขียนตัวเลข/รหัสใดๆ ใน message เด็ดขาด: "(#22)", "ID:22", "(ID:22)", "รหัส 22", "#22" — ลูกค้าต้องไม่เห็นตัวเลขหรือรหัสสินค้าใดๆ ในข้อความ
  * ❌ ห้ามคัดลอก format จากรายการสินค้า (เช่น "(#XX)", "[มีตารางไซส์]", "หมวด:XX", "ไซส์:XX") ลงใน quick_replies
  * ✅ ถูกต้อง: reply และ quick_replies ใช้แค่ "ชื่อสินค้า" เท่านั้น เช่น "เสื้อพยาบาล-ปกบัว" — ไม่มีรหัส ไม่มี format พิเศษ
  * ✅ ถูกต้อง: รายการสินค้าด้านล่างมีรูปแบบ "ชื่อสินค้า ราคา (#XX)" — ใช้แค่ "ชื่อสินค้า" ในข้อความตอบ
- 🚫 ห้ามพูดถึงรูปภาพในการตอบทุกกรณี: ในบทสนทนานี้ไม่มีรูปภาพตารางไซส์ส่งมาเลย ข้อมูลตารางไซส์มาจากหัวข้อ "ตารางขนาดสินค้า" ในข้อความ — ห้ามพูดว่า "รูปภาพ" "รูปตาราง" "จากรูปที่ส่ง" หรือ "รูปของคุณ" ในทุกกรณี ให้พูดแทนว่า "ตามตารางขนาดสินค้า" หรือ "ตามข้อมูลในระบบ" เท่านั้น
- 📋 เมื่อถามว่ามีแบบไหนบ้าง/มีอะไรบ้าง: แสดงรายชื่อสินค้า**ทุกรายการ**จากรายการด้านล่าง ห้ามตัดหรือย่อ พร้อมใส่ show_product_ids ด้วยเพื่อให้ลูกค้าเห็นภาพ แล้วถามว่าสนใจชิ้นไหนเป็นพิเศษ
- 🎨 คำค้นเชิงสไตล์/สไตลิช (sexy, เซ็กซี่, เข้ารูป, ดูดี, สวย, เท่, น่ารัก, 2 piece, two piece, เซ็ต): ห้ามบอกว่า "ไม่มีข้อมูล" — ให้แนะนำสินค้าที่ใกล้เคียงที่สุดจากรายการ เช่น เดรสเข้ารูป ชุดพิธีการ และบอกจุดเด่นของสินค้าที่มี
- 📐 การเลือกไซส์ (ถามขนาดร่างกาย): เมื่อต้องถามขนาดร่างกายลูกค้าเพื่อแนะนำไซส์ ต้องถามครบทั้ง 3 จุดในครั้งเดียวเสมอ: **"รบกวนบอกขนาดรอบอก รอบเอว และรอบสะโพก (เป็นนิ้วหรือเซนติเมตร) ด้วยนะคะ"** ห้ามถามแค่ 1-2 จุด
- ❓ ถ้าถามไซส์แต่ยังไม่ได้ระบุว่าสนใจสินค้าชิ้นไหนหรือประเภทไหน → ให้ถามกลับก่อนเสมอ เช่น "สนใจสินค้าประเภทไหนคะ?" แล้วใส่ quick_replies เป็นชื่อหมวดหมู่จริงจากรายการ — ห้ามตอบตัวเลขไซส์โดยไม่รู้ก่อนว่าเป็นสินค้าอะไร
- 🗂️ ถ้าลูกค้าถามเกี่ยวกับสินค้าแบบกว้างๆ โดยไม่ระบุประเภทหรือชื่อสินค้าเลย (เช่น "มีอะไรบ้าง" "ขายอะไร" "อยากดูสินค้า") → แจ้งหมวดหมู่ที่มีในร้านจาก "หมวดหมู่สินค้าในร้าน" ด้านบน พร้อมใส่ quick_replies เป็นชื่อหมวดหมู่นั้น เพื่อให้ลูกค้าเลือก
- 📄 สินค้าที่เหลือ: ถ้า prompt แสดงข้อความ "[ℹ️ มีสินค้าที่เกี่ยวข้องอีก X รายการที่ยังไม่ได้แสดง]" → ให้บอกลูกค้าว่ามีสินค้าอีก X รายการที่ยังไม่แสดง พร้อมถามว่าต้องการดูเพิ่มไหม และใส่ quick_replies ["ดูสินค้าเพิ่มเติม", "ไม่ต้องแล้วค่ะ"] ด้วย
- 📏 เมื่อลูกค้าบอกขนาดตัวครบทั้ง 3 จุด (รอบอก+รอบเอว+รอบสะโพก) แล้ว → ตอบทันทีด้วย 3 ส่วน:
  1) สรุปขนาดที่ลูกค้าบอก เช่น "รับทราบแล้วค่ะ อก 34" เอว 28" สะโพก 36""
  2) แสดงการคำนวณทีละจุดจากตาราง (ดูกฎ "เลือกจากสัดส่วนใหญ่สุด" ด้านล่าง)
  3) แนะนำไซส์พร้อมอธิบายเหตุผลสั้นๆ เช่น "แนะนำไซส์ L เพราะสะโพก 36" ต้องการไซส์ที่รองรับอก ≥ 37" และไซส์ L ของสินค้านี้มีสะโพก 38" ค่ะ"
  — ถ้าไม่มีตารางไซส์ให้บอกตรงๆ ว่า "ขออภัยค่ะ ยังไม่มีตารางขนาดสำหรับสินค้านี้ในระบบ"
- ถ้าไม่มีข้อมูลสินค้า → แนะนำให้แจ้งความต้องการในแชทนี้ได้เลยค่ะ
- 📦 กฎสินค้า (เด็ดขาด): รายการ "สินค้าที่เกี่ยวข้อง" ด้านล่างคือข้อมูลจริงจากระบบ ณ ขณะนี้
  * ✅ ถ้ารายการมีสินค้า → ต้องตอบตามนั้น ห้ามบอกว่า "ไม่มี" หรือ "มีเฉพาะ..." อื่น ถึงแม้ประวัติแชทก่อนหน้าจะพูดถึงสินค้าอื่น
  * ✅ ให้ใช้ประวัติแชทเพื่อทำความเข้าใจบริบทว่าลูกค้ากำลังถามถึงสินค้าใดอยู่ แต่ข้อมูลสต็อก/ราคา/รายละเอียดสินค้า ต้องดึงมาจากรายการสินค้าด้านล่างเท่านั้น ห้ามสร้างข้อมูลขึ้นมาเอง
  * ✅ ถ้ารายการสินค้าว่าง → ถามลูกค้าด้วยชื่อหมวดหมู่จริงจาก "หมวดหมู่สินค้าในร้าน" พร้อม quick_replies
- 📏 ตารางขนาดสินค้า (เด็ดขาด): ข้อมูลตารางไซส์มาจากหัวข้อ "ตารางขนาดสินค้า" ในข้อความด้านล่าง ห้ามเดาหรือแต่งตัวเลขขนาดไซส์เอง ห้ามใช้ความรู้ทั่วไปหรือประมาณเอาเอง
  * ถ้าสินค้ามี [มีตารางไซส์] → หมายความว่ามีตารางขนาดในส่วน "ตารางขนาดสินค้า" ด้านล่าง ให้อ่านตัวเลขจากตารางนั้นและตอบลูกค้าได้เลยโดยตรง ห้ามบอกให้ลูกค้า "กดดูในหน้าสินค้า" ถ้ามีข้อมูลในตาราง
  * ถ้าสินค้าไม่มีตารางไซส์ (ไม่มีข้อมูลในส่วน "ตารางขนาดสินค้า") → บอกว่า "ขออภัยค่ะ ยังไม่มีตารางขนาดสำหรับสินค้านี้ในระบบ ลองบอกขนาดรอบอก รอบเอว รอบสะโพก น้องนุ่นจะช่วยแนะนำตามประสบการณ์ได้ค่ะ"
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
- 🔔 แจ้งเตือนสต็อกคืน (ขั้นตอนสำคัญ ห้ามข้าม):
  ขั้น 1 (ไซส์หมด): ตอบว่า "ขออภัยค่ะ ไซส์ [X] ของ [ชื่อสินค้า] หมดชั่วคราว ต้องการให้น้องนุ่นแจ้งเตือนเมื่อมีสต็อกคืนไหมคะ?" แล้ว quick_replies: ["ยืนยัน แจ้งเตือนฉัน 🔔", "ไม่ต้องค่ะ"]
  ขั้น 2 (ลูกค้ากด "ยืนยัน แจ้งเตือนฉัน 🔔"): ถามว่า "ขอเบอร์โทรของคุณพี่ไว้แจ้งได้เลยนะคะ 😊"
  ขั้น 3 (ลูกค้าให้เบอร์): ตอบรับว่า "น้องนุ่นบันทึกไว้แล้วค่ะ จะแจ้งทันทีที่มีสต็อกนะคะ 😊" แล้วใส่ restock_alert ใน JSON พร้อม confirmed=true และเสนอสินค้าทดแทน
  ⚠️ ห้ามใส่ restock_alert ใน JSON จนกว่าลูกค้าจะ: ยืนยัน AND ให้เบอร์โทรแล้ว เท่านั้น
- 🔍 เปรียบเทียบสินค้า: ถ้าลูกค้าถามเปรียบเทียบ 2 สินค้า → ตอบแบบข้อๆ เทียบ: ชื่อสินค้า | ผ้า/วัสดุ | ไซส์ที่มี | ราคา | จุดเด่น — ดึงข้อมูลจากรายการสินค้าด้านล่างเท่านั้น ห้ามแต่งข้อมูล
- 📐 ความยาวชุด: ถ้าลูกค้าถามว่า "ชุดยาวถึงไหน/ใส่แล้วคลุมแค่ไหน/ยาวแค่ไหน"
  * ขั้นตอน: ถามส่วนสูงก่อนถ้าไม่รู้ แล้วคำนวณ:
  * กระโปรง: เอวอยู่ที่ ~60% ของส่วนสูง เช่น สูง 160 → เอวสูง 96 cm จากพื้น ถ้าชุดยาว 65 cm → ปลายอยู่ที่ 96−65 = 31 cm จากพื้น
  * เสื้อ/เดรส: จุดข้างคออยู่ที่ ~85% ของส่วนสูง เช่น สูง 160 → คอสูง 136 cm จากพื้น ถ้าชุดยาว 110 cm → ปลายอยู่ที่ 136−110 = 26 cm จากพื้น
  * ตำแหน่งโดยประมาณ: 0-15 cm = ต้นขาสูง | 15-30 cm = กลางต้นขา | 30-40 cm = เหนือเข่า | 40-50 cm = ใต้เข่า | 50+ cm = กลางน่อง-ข้อเท้า
  * ตอบเป็นภาษาธรรมชาติ เช่น "น่าจะยาวคลุมเข่าค่ะ" หรือ "น่าจะอยู่กลางต้นขาค่ะ"
  * ถ้าลูกค้าถามความยาวชุดโดยทั่วไป (ยังไม่ได้ระบุสินค้า): อธิบายวิธีคำนวณและถามส่วนสูงของลูกค้าก่อน ห้ามตอบว่า "ไม่มีข้อมูล" ถ้ายังไม่รู้สินค้า
  * ถ้าระบุสินค้าแล้วแต่สเปคไม่มีตัวเลขความยาว → บอก "ไม่มีข้อมูลความยาวในสเปคสินค้าค่ะ ลองบอกส่วนสูงของคุณพี่ น้องนุ่นจะประมาณให้ค่ะ"
- 📵 กฎเบอร์โทร 083-668-2211 (เด็ดขาด): ห้ามให้เบอร์โทรในกรณีทั่วไป ให้เบอร์โทรได้เฉพาะ 3 กรณีนี้เท่านั้น: 1) ลูกค้าขอเบอร์ติดต่อโดยตรง 2) ลูกค้าแสดงความกังวลหรือลังเลเรื่องการชำระเงิน 3) ลูกค้าต้องการสั่งผลิตสินค้าและขอเบอร์เอง — ห้ามให้เบอร์เมื่อถามเรื่องค่าส่ง ไซส์ ราคา สินค้า หรือคำถามทั่วไปอื่นๆ
{_upsell_note}

=== ขนาดร่างกายที่บอกไว้ในการสนทนานี้ ===
{meas_text}
(ถ้ามีข้อมูลแล้ว ห้ามถามซ้ำ ให้ใช้ค่านี้ได้เลย)

=== หมวดหมู่สินค้าในร้าน ===
{cats_str}

=== โปรโมชั่นปัจจุบัน (หากมีรายการด้านล่าง ให้แจ้งทุกรายการเมื่อลูกค้าถาม — ห้ามบอกว่า "ไม่มีโปรโมชั่น" ถ้ายังมีข้อมูลด้านล่าง) ===
{promos_text or 'ไม่มีโปรโมชั่นในขณะนี้'}

=== ค่าส่งและการจัดส่ง (เมื่อลูกค้าถามค่าส่ง ต้องตอบด้วยตัวเลขจากส่วนนี้ทันที ห้ามบอกว่า "ขึ้นอยู่กับน้ำหนัก" โดยไม่ระบุราคา) ===
{shipping_text}
- ช่องทางจัดส่ง: Kerry / Flash Express / ไปรษณีย์ไทย (ขึ้นอยู่กับพื้นที่)

=== ตารางขนาดสินค้า (ขนาด = ไซส์ คืออันเดียวกัน — ใช้ข้อมูลนี้ตอบคำถามเรื่องขนาด/ไซส์ได้เลยทันที ห้ามบอกว่า "ไม่มีข้อมูล" ถ้ามีตารางด้านล่าง) ===
{_guest_size_chart_section or '(ยังไม่มีตารางขนาดสำหรับสินค้าที่แสดง)'}

=== สินค้าที่เกี่ยวข้องกับคำถาม ===
{products_text or '(ไม่พบสินค้าที่ตรงกับคำค้นหา)'}
{'[ℹ️ มีสินค้าที่เกี่ยวข้องอีก ' + str(_remaining_count) + ' รายการที่ยังไม่ได้แสดง]' if _remaining_count > 0 else ''}

⚠️ ตอบกลับเป็น JSON เท่านั้น ห้ามตอบเป็นข้อความธรรมดาเด็ดขาด:
{{
  "message": "ข้อความตอบกลับ (string)",
  "quick_replies": ["ตัวเลือก1", "ตัวเลือก2"],
  "show_product_ids": [id1, id2],
  "add_to_cart": {{"product_id": null, "size": null, "quantity": 0}},
  "restock_alert": {{"product_id": null, "product_name": null, "size": null, "phone": null, "confirmed": false}}
}}
- "quick_replies": ปุ่มตัวเลือกให้กด ไม่เกิน 4 ปุ่ม ([] ถ้าไม่ต้องการ)
- "show_product_ids": product ID ที่ต้องการแสดงรูปสินค้า ([] ถ้าไม่มี)
- "add_to_cart": ใส่เมื่อลูกค้าตัดสินใจสั่งซื้อชัดเจน (ระบุสินค้า+ไซส์+จำนวน) เช่น "เอา L 2 ตัว" หรือ "สั่งเลยค่ะ" → ใส่ product_id (จาก ID:ตัวเลข), size (ชื่อไซส์เช่น "L" หรือ "XL"), quantity (จำนวนเต็ม) ถ้าไม่ใช่การสั่งซื้อให้ใส่ null/0 — ลูกค้าจะต้อง login เพื่อชำระเงิน
- "restock_alert": ใส่เฉพาะเมื่อลูกค้า ยืนยัน + ให้เบอร์โทรแล้ว → confirmed=true, product_id, product_name, size, phone ครบทุก field ห้ามใส่ก่อนลูกค้ายืนยัน
- quick_replies เรื่องหมวดหมู่: ใช้ชื่อจริงจาก "หมวดหมู่สินค้าในร้าน" เท่านั้น
- quick_replies เรื่องสินค้า: ใช้ชื่อสินค้าจริงจากรายการด้านบน ห้ามตั้งชื่อเอง"""

        # Build conversation contents
        _contents = []
        for h in (history[-16:]):
            role = 'user' if h.get('role') == 'user' else 'model'
            _contents.append(_genai_types.Content(role=role, parts=[_genai_types.Part.from_text(text=str(h.get('text',''))[:300])]))
        _last_parts = [_genai_types.Part.from_text(text=user_msg)]
        _contents.append(_genai_types.Content(role='user', parts=_last_parts))

        _client = _genai.Client(api_key=_api_key)
        _cfg = _genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=2500,
            temperature=0.5,
        )
        _all_models = ['gemini-2.5-flash-lite', 'gemini-2.5-flash']
        _response = None
        _retryable = ('503', '429', 'overloaded', 'quota', 'resource_exhausted', 'rate limit')
        import time as _time
        for _model in _all_models:
            for _attempt in range(2):
                try:
                    _response = _client.models.generate_content(
                        model=_model,
                        contents=_contents,
                        config=_cfg,
                    )
                    if _response and _response.text:
                        break
                except Exception as _me:
                    _me_str = str(_me).lower()
                    if any(k in _me_str for k in _retryable):
                        if _attempt == 0:
                            _time.sleep(3)
                            continue
                        break
                    raise
            if _response and _response.text:
                break
        raw_text = (_response.text if _response else '') or ''

        # Parse JSON response
        bot_text = ''
        quick_replies = []
        show_product_ids = []
        add_to_cart_raw = {}
        _restock_raw = {}
        try:
            _json_match = _re.search(r'\{.*\}', raw_text, _re.DOTALL)
            if _json_match:
                _parsed = _json.loads(_json_match.group())
                bot_text = str(_parsed.get('message') or _parsed.get('reply') or '').strip()
                quick_replies = [str(x) for x in (_parsed.get('quick_replies') or []) if x][:4]
                show_product_ids = [int(x) for x in (_parsed.get('show_product_ids') or []) if str(x).isdigit()]
                add_to_cart_raw = _parsed.get('add_to_cart') or {}
                _restock_raw = _parsed.get('restock_alert') or {}
        except Exception:
            _restock_raw = {}
            pass
        if not bot_text:
            # Try to extract message field with regex when json.loads failed (truncated JSON)
            _msg_re = _re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.)*)', raw_text, _re.DOTALL)
            if _msg_re:
                bot_text = _msg_re.group(1).replace('\\"', '"').replace('\\n', '\n').strip()
        if not bot_text:
            bot_text = _re.sub(r'\{.*\}', '', raw_text, flags=_re.DOTALL).strip()
        if not bot_text or bot_text.lstrip().startswith('{'):
            bot_text = 'ขออภัยค่ะ ไม่สามารถตอบได้ในขณะนี้ กรุณาติดต่อ 083-668-2211 ได้เลยค่ะ'

        # Filter prod_list to only the IDs requested for image display
        _id_set = set(show_product_ids)
        show_products = [p for p in prod_list if p['id'] in _id_set][:4]

        # Handle add_to_cart — look up matching SKU by product_id + size
        add_to_cart_item = None
        if (isinstance(add_to_cart_raw, dict)
                and add_to_cart_raw.get('product_id')
                and add_to_cart_raw.get('size')):
            try:
                _atc_pid = int(add_to_cart_raw['product_id'])
                _atc_size = str(add_to_cart_raw['size']).strip()
                _atc_qty = max(1, int(add_to_cart_raw.get('quantity') or 1))
                cursor.execute('''
                    SELECT p.id, p.name,
                           (SELECT pi.image_url FROM product_images pi
                            WHERE pi.product_id = p.id ORDER BY pi.sort_order ASC LIMIT 1) as image_url,
                           (SELECT ptp.discount_percent FROM product_tier_pricing ptp
                             JOIN reseller_tiers rt ON rt.id = ptp.tier_id
                             WHERE ptp.product_id = p.id ORDER BY rt.upgrade_threshold ASC LIMIT 1) as tier1_discount
                    FROM products p WHERE p.id = %s AND p.status = %s
                ''', (_atc_pid, 'active'))
                _atc_prod = cursor.fetchone()
                if _atc_prod:
                    cursor.execute('''
                        SELECT s.id, s.sku_code, s.price, s.stock,
                               COALESCE(json_object_agg(o.name, ov.value)
                                        FILTER (WHERE o.id IS NOT NULL), '{}'::json) as options
                        FROM skus s
                        LEFT JOIN sku_values_map svm ON svm.sku_id = s.id
                        LEFT JOIN option_values ov ON ov.id = svm.option_value_id
                        LEFT JOIN options o ON o.id = ov.option_id
                        WHERE s.product_id = %s
                        GROUP BY s.id, s.sku_code, s.price, s.stock
                    ''', (_atc_pid,))
                    _atc_skus = cursor.fetchall()
                    _matched = None
                    # Try in-stock match first
                    for _s in _atc_skus:
                        _opts = _s['options'] or {}
                        for _ov in _opts.values():
                            if str(_ov).upper().strip() == _atc_size.upper():
                                if int(_s['stock'] or 0) > 0:
                                    _matched = _s
                                break
                        if _matched:
                            break
                    # Fall back to any matching SKU (regardless of stock)
                    if not _matched:
                        for _s in _atc_skus:
                            _opts = _s['options'] or {}
                            for _ov in _opts.values():
                                if str(_ov).upper().strip() == _atc_size.upper():
                                    _matched = _s
                                    break
                            if _matched:
                                break
                    if _matched:
                        _tier1 = float(_atc_prod['tier1_discount'] or 0)
                        _price = float(_matched['price'])
                        _member_price = round(_price * (1 - _tier1 / 100)) if _tier1 > 0 else _price
                        _opt_label = ' / '.join(str(v) for v in (_matched['options'] or {}).values())
                        add_to_cart_item = {
                            'productId': _atc_pid,
                            'name': _atc_prod['name'],
                            'imageUrl': _atc_prod['image_url'] or '',
                            'skuId': _matched['id'],
                            'skuCode': _matched['sku_code'],
                            'optionLabel': _opt_label,
                            'price': _price,
                            'memberPrice': _member_price,
                            'tier1Discount': _tier1,
                            'qty': _atc_qty,
                            'stock': int(_matched['stock'] or 0),
                        }
            except Exception as _atc_e:
                print(f'[GuestBot] add_to_cart lookup error: {_atc_e}')

        # Handle restock_alert — save to DB only when confirmed=True AND phone provided
        if (isinstance(_restock_raw, dict)
                and _restock_raw.get('confirmed') is True
                and _restock_raw.get('phone')
                and _restock_raw.get('product_id')):
            try:
                _ra_pid = int(_restock_raw['product_id'])
                _ra_size = str(_restock_raw.get('size') or '').strip()
                _ra_phone = str(_restock_raw['phone']).strip()
                _ra_pname = str(_restock_raw.get('product_name') or '').strip()
                _ra_session = request.headers.get('X-Session-Id', '') or str(request.remote_addr)
                cursor.execute('''
                    INSERT INTO restock_alerts (product_id, size, product_name, phone, session_id, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                ''', (_ra_pid, _ra_size, _ra_pname, _ra_phone, _ra_session))
                db_conn.commit()
                print(f'[GuestBot] Restock alert saved: pid={_ra_pid} size={_ra_size} phone={_ra_phone}')
                notify_admins_guest_lead(
                    '🔔 Guest ฝากแจ้งเตือนสต็อก',
                    f'{_ra_pname} ไซส์ {_ra_size} | เบอร์: {_ra_phone}',
                    notification_type='restock',
                    push_url='/admin#restock-alerts',
                    push_tag=f'guest-restock-{_ra_pid}-{_ra_size}'
                )
            except Exception as _ra_e:
                print(f'[GuestBot] restock_alert save error: {_ra_e}')

        # Save full conversation to DB for admin review (background, non-blocking)
        def _save_convo(_sid, _ip, _umsg, _breply):
            try:
                _sc = get_db()
                _cc = _sc.cursor()
                _cc.execute('''
                    INSERT INTO guest_chat_sessions (session_id, ip, last_seen, msg_count)
                    VALUES (%s, %s, NOW(), 1)
                    ON CONFLICT (session_id) DO UPDATE
                    SET last_seen = NOW(), msg_count = guest_chat_sessions.msg_count + 1
                ''', (_sid, _ip))
                _cc.execute('''
                    INSERT INTO guest_chat_messages (session_id, user_msg, bot_reply)
                    VALUES (%s, %s, %s)
                ''', (_sid, _umsg, _breply))
                _sc.commit()
                _cc.close()
                _sc.close()
            except Exception as _ce:
                print(f'[GuestBot] convo save error: {_ce}')
        _sess_id = request.headers.get('X-Session-Id', '') or str(request.remote_addr)
        _client_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        threading.Thread(target=_save_convo, args=(_sess_id, _client_ip, user_msg, bot_text), daemon=True).start()

        _resp = {
            'reply': bot_text,
            'quick_replies': quick_replies,
            'show_products': show_products,
        }
        if add_to_cart_item:
            _resp['add_to_cart_item'] = add_to_cart_item
        return jsonify(_resp), 200

    except Exception as e:
        print(f'[GuestBot] error: {e}')
        return jsonify({'reply': 'ขออภัยค่ะ ระบบขัดข้องชั่วคราว กรุณาติดต่อ 083-668-2211 ได้เลยค่ะ'}), 200


