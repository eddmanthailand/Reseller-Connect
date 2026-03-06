from flask import Blueprint, request, jsonify, session, redirect, url_for
from functools import wraps
import psycopg2.extras
import psycopg2
import os
import json
import logging
from datetime import datetime, timedelta
from database import get_db

agent_bp = Blueprint('agent', __name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
            return redirect(url_for('login_page'))
        if session.get('role') not in ['Super Admin', 'Assistant Admin']:
            return jsonify({'error': 'คุณไม่มีสิทธิ์เข้าถึงส่วนนี้ (เฉพาะแอดมิน)'}), 403
        return f(*args, **kwargs)
    return decorated_function


def handle_error(e, user_msg='เกิดข้อผิดพลาดในระบบ กรุณาลองใหม่อีกครั้ง'):
    logging.error(e, exc_info=True)
    return jsonify({'error': user_msg}), 500


def _get_meta_credentials(cursor):
    cursor.execute('SELECT meta_access_token, meta_ad_account_id FROM facebook_pixel_settings LIMIT 1')
    row = cursor.fetchone()
    token = (row['meta_access_token'] if row else None) or os.environ.get('META_ACCESS_TOKEN', '')
    account_id = (row['meta_ad_account_id'] if row else None) or os.environ.get('META_AD_ACCOUNT_ID', '')
    return token.strip() if token else '', account_id.strip() if account_id else ''


def _agent_superadmin_required():
    return session.get('role') == 'Super Admin'

def _agent_load_settings(cursor):
    cursor.execute('SELECT * FROM agent_settings WHERE id = 1')
    row = cursor.fetchone()
    if row:
        return dict(row)
    return {'agent_name': 'น้องเอก', 'tone': 'friendly', 'ending_particle': 'ครับ', 'custom_prompt': ''}


def _agent_load_business_context(cursor):
    ctx = {}
    try:
        cursor.execute("SELECT id, name FROM brands ORDER BY name")
        ctx['brands'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['brands'] = []
    try:
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        ctx['categories'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['categories'] = []
    try:
        cursor.execute("SELECT id, name, province FROM warehouses WHERE is_active=TRUE ORDER BY name")
        ctx['warehouses'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['warehouses'] = []
    try:
        cursor.execute("SELECT id, name, level_rank FROM reseller_tiers ORDER BY level_rank")
        ctx['tiers'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['tiers'] = []
    try:
        cursor.execute("SELECT COUNT(*) as cnt FROM products WHERE status='active'")
        ctx['active_products'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE role_id=3")
        ctx['active_resellers'] = cursor.fetchone()['cnt']
    except Exception:
        ctx['active_products'] = 0
        ctx['active_resellers'] = 0
    try:
        cursor.execute("""
            SELECT p.id, p.name, p.parent_sku, p.product_type, b.name as brand_name,
                   STRING_AGG(DISTINCT c.name, ', ') as categories
            FROM products p
            LEFT JOIN brands b ON p.brand_id = b.id
            LEFT JOIN product_categories pc ON p.id = pc.product_id
            LEFT JOIN categories c ON pc.category_id = c.id
            WHERE p.status = 'active'
            GROUP BY p.id, p.name, p.parent_sku, p.product_type, b.name
            ORDER BY b.name, p.name
            LIMIT 200
        """)
        ctx['products'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['products'] = []
    try:
        cursor.execute("SELECT note_key, note_value FROM agent_notes ORDER BY updated_at DESC")
        ctx['notes'] = [dict(r) for r in cursor.fetchall()]
    except Exception:
        ctx['notes'] = []
    return ctx

def _agent_build_system_prompt(settings, context=None):
    name = settings.get('agent_name', 'น้องเอก')
    particle = settings.get('ending_particle', 'ครับ')
    tone_map = {'friendly': 'เป็นกันเอง สุภาพ', 'formal': 'เป็นทางการ มืออาชีพ', 'concise': 'กระชับสั้น ตรงประเด็น'}
    tone_desc = tone_map.get(settings.get('tone', 'friendly'), 'เป็นกันเอง สุภาพ')
    custom = settings.get('custom_prompt', '') or ''
    ctx = context or {}

    brand_names = ', '.join([b['name'] for b in ctx.get('brands', [])]) or 'ยังไม่มีข้อมูล'
    category_names = ', '.join([c['name'] for c in ctx.get('categories', [])]) or 'ยังไม่มีข้อมูล'
    warehouse_names = ', '.join([f"{w['name']} ({w.get('province','') or '-'})" for w in ctx.get('warehouses', [])]) or 'ยังไม่มีข้อมูล'
    tier_names = ', '.join([t['name'] for t in ctx.get('tiers', [])]) or 'Bronze, Silver, Gold, Platinum'
    active_products = ctx.get('active_products', '?')
    active_resellers = ctx.get('active_resellers', '?')

    # สร้าง product list แบ่งตามหมวดหมู่
    products_section = ''
    products = ctx.get('products', [])
    if products:
        from collections import defaultdict
        by_cat = defaultdict(list)
        for p in products:
            cat = p.get('categories') or 'ไม่มีหมวดหมู่'
            by_cat[cat].append(f"{p['name']} (SKU:{p.get('parent_sku','?')}, แบรนด์:{p.get('brand_name','?')}, ประเภท:{p.get('product_type','?')})")
        lines = ['\n=== รายชื่อสินค้า active ในระบบ (แยกตามหมวดหมู่) ===']
        for cat, items in sorted(by_cat.items()):
            lines.append(f'[{cat}]')
            for item in items:
                lines.append(f'  - {item}')
        products_section = '\n'.join(lines)

    last_response_section = ''
    last_resp = ctx.get('last_agent_response', '')
    if last_resp:
        last_response_section = f'\n=== ข้อความล่าสุดที่หนูตอบไป (ใช้เป็น context สำหรับคำสั่งต่อไปได้เลย) ===\n{last_resp}'

    notes_section = ''
    sandbox_section = ''
    notes = ctx.get('notes', [])
    if notes:
        import json as _j
        notes_lines = '\n'.join([f"- {n['note_key']}: {n['note_value']}" for n in notes])
        notes_section = f'\n=== บันทึก (สมุดโน้ต AI) ===\n{notes_lines}'
        for n in notes:
            if n['note_key'] == 'google_drive_sandbox':
                try:
                    sb = _j.loads(n['note_value']) if isinstance(n['note_value'], str) else n['note_value']
                    fid = sb.get('folder_id', '')
                    fname = sb.get('folder_name', 'Sandbox')
                    fdesc = sb.get('description', '')
                    sandbox_section = f'''\n=== Google Drive Sandbox ===
- Sandbox Folder: "{fname}" (ID: {fid})
- {fdesc}
- เมื่อทำงานกับ Google Drive/Sheets ให้ระบุ folder_id={fid} ใน query_google_drive เสมอ
- สามารถสร้าง Sheet ใหม่ อ่าน เขียน ค้นหาไฟล์ใน sandbox ได้เต็มที่'''
                except Exception:
                    pass

    return f"""คุณชื่อ "{name}" เป็น AI ผู้ช่วยส่วนตัวของ Superadmin ระบบร้านค้า EKG Shops
น้ำเสียง: {tone_desc} ใช้คำลงท้าย "{particle}" เสมอ
{('คำสั่งพิเศษ/บริบทธุรกิจ: ' + custom) if custom else ''}

=== ข้อมูลระบบ ===
- Models ที่ใช้ในระบบ:
  • Agent READ/chat (Phase 1): gemini-2.5-flash-lite (เร็ว ประหยัด)
  • Agent WRITE tools (Phase 2 verify): gemini-3.1-pro-preview (แม่นยำ ปลอดภัย)
  • Agent code explain: gemini-2.5-flash
  • search_web: gemini-2.5-flash (Google Search Grounding)
  • generate_image: Imagen 4
  • Auto-Chat Bot (ข้อความทั่วไป): gemini-2.5-flash-lite
  • Auto-Chat Bot (อ่านรูป size chart): gemini-2.5-flash
  • OCR ใบปะหน้า (Quick Order): gemini-2.5-flash
- Role: Developer Consultant + Business Assistant
- Backend: Flask 3.1.2 + PostgreSQL (Neon) + Gunicorn (gevent)
- Frontend: Vanilla JS SPA, Jinja2 templates
- Storage: Replit Object Storage (รูปสินค้า)
- ข้อจำกัด: อ่านได้ทุกอย่าง แต่แก้ไขโค้ด/DB โดยตรงไม่ได้ — ให้แนะนำ Superadmin แล้วใช้ Replit Agent ดำเนินการแทน

=== บริบทธุรกิจปัจจุบัน ===
- แบรนด์ที่ใช้งาน: {brand_names}
- หมวดหมู่สินค้า (Categories): {category_names}
- โกดัง: {warehouse_names}
- ระดับตัวแทน (Tier): {tier_names}
- สินค้า active: {active_products} รายการ | ตัวแทน active: {active_resellers} คน{products_section}{last_response_section}{notes_section}{sandbox_section}

=== TOOLS ที่ใช้ได้ ===
[READ — ธุรกิจ]
- query_sales_today: ยอดขายวันนี้/สัปดาห์/เดือน
- query_sales_by_brand: ยอดขายแยกตามแบรนด์
- query_top_products: สินค้าขายดี
- query_low_stock: สินค้าสต็อกต่ำ/ใกล้หมด (params: threshold=5)
- query_products: ดูรายชื่อสินค้าพร้อม filter (params: keyword, category, brand, product_type, limit) — ใช้แทนการ query_db เมื่อต้องการค้นสินค้า, รองรับ category เช่น "ชุดพยาบาล"
- query_stock_product: สต็อกสินค้าเฉพาะตัว (params: product_name)
- query_order_counts: จำนวนออเดอร์ทุกสถานะ
- query_pending_orders: ออเดอร์ที่รอดำเนินการ (params: limit=10)
- query_order_detail: รายละเอียดออเดอร์เฉพาะใบ (params: order_number หรือ order_id)
- query_customer: ค้นหาข้อมูลลูกค้า (params: name หรือ phone)
- query_resellers: รายชื่อตัวแทนและสถิติ (params: tier="Gold" optional)
- query_unread_chat: แชทที่ยังไม่ได้อ่าน
- query_mto_status: สถานะออเดอร์สั่งผลิต (MTO)
- read_notes: อ่านสมุดโน้ต AI ทั้งหมด
- query_facebook_ads: ดึงข้อมูล Meta Ads จริงจาก Marketing API (params: period="7d"/"30d"/"90d")
- search_web: ค้นหาข้อมูลจากอินเทอร์เน็ต (params: query)
- generate_image: สร้างภาพด้วย AI (Imagen 4) จาก prompt ที่กำหนด (params: prompt, aspect_ratio="1:1"/"16:9"/"9:16"/"4:3")
- chart_sales_trend: กราฟยอดขายรายวัน Line chart (params: days=7 หรือ 30)
- chart_sales_by_brand: กราฟยอดขายแยกแบรนด์ Doughnut chart
- chart_order_status: กราฟสัดส่วนสถานะออเดอร์ Pie chart
- chart_top_products: กราฟสินค้าขายดี Bar chart (params: limit=10)
- chart_low_stock: กราฟสต็อกสินค้าใกล้หมด Horizontal Bar

[READ — ตรวจสอบโค้ด (ห้ามแก้ไข)]
- list_files: รายการไฟล์ (params: path="." optional, pattern="*.py" optional)
- read_code: อ่านไฟล์โค้ด (params: file="app.py", offset=1, limit=80)
- search_code: ค้นหาในโค้ด (params: pattern, file optional, context_lines=2)
- query_db_schema: โครงสร้างตาราง DB (params: table optional)
- query_db: SQL SELECT อย่างเดียว (params: sql, limit=20)
- analyze_syntax: ตรวจ syntax error ในไฟล์ Python (params: file="app.py")
- count_code_metrics: สถิติโค้ด จำนวนบรรทัด/functions/routes (params: file optional)

[READ — ตรวจสอบระบบ]
- check_system_status: CPU load, RAM, disk, uptime ของ server
- read_server_logs: อ่าน server error log ล่าสุด (params: lines=50, level="ERROR" optional)
- check_db_health: สุขภาพ DB — connections, table sizes, index
- list_storage_files: รายการไฟล์ใน Object Storage (params: prefix="" optional)
- list_env_var_names: รายชื่อ environment variables (ชื่อเท่านั้น ไม่มีค่า)
- test_api_endpoint: ทดสอบ GET endpoint (params: path="/api/admin/brands")

[READ — Google Workspace]
- read_google_sheet: อ่านข้อมูลจาก Google Sheets (params: spreadsheet_id, range="Sheet1!A1:Z100", limit=50)
- query_google_drive: ค้นหาไฟล์ใน Google Drive (params: query="keyword" optional, folder_id="ID" optional สำหรับกรองเฉพาะ folder, limit=10)

[WRITE — Google Workspace (ต้องขออนุมัติก่อนเสมอ)]
- write_google_sheet: เขียน/อัปเดตข้อมูลลง Google Sheets (params: spreadsheet_id, range="Sheet1!A1", values=[["col1","col2",...]], mode="append"/"overwrite")

[WRITE — ต้อง Superadmin อนุมัติทุกครั้ง]
- adjust_stock: เพิ่ม/ลดสต็อก SKU (params: product_name, color, size, quantity, direction="add"/"subtract")
- update_order_status: เปลี่ยนสถานะออเดอร์ (params: order_number, new_status)
- toggle_product: เปิด/ปิดการขายสินค้า (params: product_name, active=true/false)
- send_chat_message: ส่งข้อความหาตัวแทน (params: reseller_name, message)
- save_note: บันทึกข้อมูลสำคัญลงสมุดโน้ต AI (params: key, value) — จำได้ข้ามเซสชัน
- toggle_facebook_ad: เปลี่ยนสถานะ Campaign/AdSet/Ad ใน Meta Ads (params: ad_id, status="ACTIVE"/"PAUSED"/"ARCHIVED") — ส่ง POST ไป Meta Marketing API จริง
- update_product_description: แก้ไขคำอธิบายสินค้าชิ้นเดียว (params: product_name, description, field="bot_description"|"description") — field="bot_description" คือสำหรับบอทแชทน้องนุ่น (default), field="description" คือหน้าสาธารณะ
- bulk_update_product_description: อัปเดตคำอธิบายสินค้าหลายชิ้นพร้อมกัน (params: keyword="คำที่อยู่ในชื่อสินค้า", description="คำอธิบาย", field="bot_description"|"description") — default field="bot_description"
- update_product_field: แก้ไข field อื่นๆ ของสินค้า (params: product_name, field="is_featured"|"low_stock_threshold"|"weight"|"name", value) — เช่น ตั้งเป็นสินค้าแนะนำ, เปลี่ยนชื่อ, ตั้งขีดแจ้งเตือนสต็อก

=== DB Schema สำคัญ (สำหรับ query_db) ===
- ค้นสินค้า: ใช้ query_products แทน query_db เสมอ (ง่าย ถูกต้อง ไม่ต้อง JOIN เอง)
- products: id, name, parent_sku, status, product_type, brand_id — ไม่มี column "category" หรือ "is_active" โดยตรง
- หมวดหมู่สินค้า: ต้อง JOIN product_categories pc ON pc.product_id=p.id JOIN categories c ON c.id=pc.category_id
- สถานะสินค้า: ใช้ status='active' ไม่ใช่ is_active=TRUE
- SQL ที่ส่งให้ query_db: ห้ามมี semicolon (;) ท้าย SQL

=== รูปแบบตอบกลับ (JSON เท่านั้น) ===
READ: {{"type":"answer","tool":"tool_name","params":{{...}},"message":"สรุปผลสั้น"}}
กราฟ: {{"type":"answer","tool":"chart_xxx","params":{{...}},"message":"หัวข้อกราฟ"}}
WRITE: {{"type":"plan","tool":"tool_name","params":{{...}},"message":"อธิบายสิ่งที่จะทำ"}}
ถามเพิ่ม: {{"type":"clarify","message":"คำถามกลับ"}}
สนทนา/แนะนำ: {{"type":"chat","message":"ข้อความ"}}

⚠️ [กฎเหล็ก — อ่านก่อนตอบทุกครั้ง]
1. ถ้าผู้ใช้ขอ "ดู" "ตรวจสอบ" "เช็ค" "หา" "แสดง" ข้อมูลใดๆ → ตอบ type=answer พร้อม tool ทันที ห้ามใช้ type=chat อธิบายก่อน
2. ห้ามถาม "ต้องการให้หนูลองใช้ tool X ไหมคะ?" เด็ดขาด — READ tool ไม่แก้ไขข้อมูล ไม่ต้องขออนุญาต
3. ห้ามอธิบายว่า "ต้องใช้ tool X เพื่อ..." แล้วรอ — ใช้ tool เลย
4. type=chat ใช้เฉพาะ: ทักทาย / คำถามนอกเรื่องงาน / ตอบโต้สั้นๆ ที่ไม่ต้องการข้อมูล DB
ตัวอย่าง ถูก: ผู้ใช้ "ดูว่าสินค้า A มีคำอธิบายบอทแชทไหม" → {{"type":"answer","tool":"query_db","params":{{"sql":"SELECT name, bot_description FROM products WHERE name ILIKE '%A%' LIMIT 5"}},"message":"ตรวจสอบ bot_description"}}
ตัวอย่าง ผิด: ผู้ใช้ "ดูว่าสินค้า A มีคำอธิบายบอทแชทไหม" → {{"type":"chat","message":"หนูต้องใช้ query_db เพื่อตรวจสอบ ต้องการให้หนูลองไหมคะ?"}}

=== กฎสำคัญ ===
- ตอบเป็น JSON เสมอ ห้ามมีข้อความอื่นนอก JSON
- ห้ามลบข้อมูล ห้ามแก้ไขโค้ดโดยตรง — บทบาทคือที่ปรึกษาและวิเคราะห์
- ถ้าพบปัญหาในโค้ด ให้อธิบายและแนะนำวิธีแก้ใน message แทน
- **ใช้บริบทจาก history เสมอ** — ถ้าบทสนทนาก่อนหน้ามีรายชื่อสินค้า/หมวดหมู่/สิ่งที่คุยกันไปแล้ว ให้นำมาใช้ใน params ทันที ห้ามถามซ้ำสิ่งที่รู้อยู่แล้วจาก history
- ตัวอย่าง: ถ้า history มีรายการสินค้ากระโปรง 3 ชิ้น แล้วผู้ใช้บอก "ใส่คำอธิบายสำหรับบอทแชท" → ให้ใช้ bulk_update_product_description พร้อม keyword="กระโปรง" จาก context ทันที โดยไม่ต้องถามอีก
- clarify ถามกลับ เฉพาะตอนที่ **ไม่มีข้อมูลเพียงพอแม้ดู history แล้ว** เท่านั้น
- ถ้าถามนอกเรื่องงาน ให้ type=chat ตอบสั้นๆ
- **ห้ามตอบเรื่องระบบ EKG Shops จากความจำ** — ถ้าถามว่า "X ทำงานอย่างไร" "ระบบมี Y ไหม" "โค้ดส่วน Z คืออะไร" ต้องใช้ search_code หรือ read_code ก่อนเสมอ ห้ามเดา
- ถ้าค้นหาแล้วไม่เจอผลลัพธ์ที่ตรง ให้ค้นหาด้วย keyword อื่นหรือ list_files ดูก่อน อย่าบอกว่า "ยังไม่มีในระบบ" โดยไม่ค้นจริง

=== Glossary — ชื่อจริงในโค้ด ===
(ถ้าผู้ใช้ถามคำเหล่านี้ ให้ค้นหาด้วยชื่อฟังก์ชัน/route ด้านขวา)
- checkout / สั่งซื้อ → search: "create_order" หรือ "reseller/checkout"
- ชำระเงิน / payment → search: "payment" หรือ "slip"
- คูปอง / coupon → search: "_calc_coupon_discount" หรือ "coupon"
- สต็อก / stock → search: "adjust_stock" หรือ "warehouse"
- แชท / chat → search: "chat_messages" หรือ "chat_threads"
- บอท / bot → search: "_auto_bot_reply" หรือ "bot"
- AI Agent → search: "_agent_call_gemini" หรือ "agent_chat"
- โปรโมชัน / promotion → search: "_apply_promotions" หรือ "promotions"
- ออเดอร์ / order → search: "create_order" หรือ "orders"
- MTO / สั่งผลิต → search: "mto_orders" หรือ "mto"
- iShip / ส่งของ → search: "iship" หรือ "webhook"
- PWA / push notification → search: "push_notification" หรือ "sw.js\""""


def _agent_call_gemini(message, context_page, settings, image_data=None, image_mime=None, model='gemini-2.5-flash', history=None, context=None):
    import json as _json, base64 as _b64
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
        gemini_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_key:
            return {'type': 'chat', 'message': 'ไม่พบ GEMINI_API_KEY'}
        client = google_genai.Client(api_key=gemini_key)
        system_prompt = _agent_build_system_prompt(settings, context=context)

        contents = []
        for h in (history or []):
            role = 'user' if h.get('role') == 'user' else 'model'
            txt = (h.get('text') or '').strip()
            if txt:
                contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=txt)]))

        current_text = f"=== หน้าปัจจุบัน: {context_page} ===\n\nคำสั่ง: {message}"
        if image_data:
            img_bytes = _b64.b64decode(image_data)
            current_parts = [genai_types.Part(text=current_text), genai_types.Part.from_bytes(data=img_bytes, mime_type=image_mime or 'image/jpeg')]
        else:
            current_parts = [genai_types.Part(text=current_text)]
        contents.append(genai_types.Content(role='user', parts=current_parts))

        config = genai_types.GenerateContentConfig(system_instruction=system_prompt)
        resp = client.models.generate_content(model=model, contents=contents, config=config)
        raw = (resp.text or '').strip()
        if not raw:
            return {'type': 'chat', 'message': 'AI ไม่ได้ตอบกลับ (empty response) กรุณาลองใหม่อีกครั้ง'}

        # ลอง parse JSON จาก response — รองรับทั้ง raw JSON, code block, และ mixed text+JSON
        def _extract_json(text):
            import re as _re
            # 1. ทั้ง response เป็น JSON โดยตรง
            try:
                return _json.loads(text)
            except _json.JSONDecodeError:
                pass
            # 2. หา ```json ... ``` block ที่อยู่ตรงไหนก็ได้ใน text
            m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, _re.DOTALL)
            if m:
                try:
                    return _json.loads(m.group(1))
                except _json.JSONDecodeError:
                    pass
            # 3. หา JSON object {...} ที่อยู่ใน text (เฉพาะ simple value ไม่มี nested obj)
            m2 = _re.search(r'\{[^{}]*"type"\s*:\s*"[^"]*"[^{}]*\}', text, _re.DOTALL)
            if m2:
                try:
                    return _json.loads(m2.group(0))
                except _json.JSONDecodeError:
                    pass
            # 4. Heuristic: Gemini ส่ง JSON ที่มี unescaped quotes ใน message (ภาษาไทยที่มี " " ในข้อความ)
            #    ดึง type ก่อน แล้วค่อย reconstruct message จาก raw text
            type_m = _re.search(r'"type"\s*:\s*"(\w+)"', text)
            if type_m:
                extracted_type = type_m.group(1)
                # ดึง message: หาตำแหน่งหลัง "message": " แล้วเอาทุกอย่างจนถึง "} หรือ end
                msg_pos = _re.search(r'"message"\s*:\s*"', text)
                if msg_pos:
                    raw_after = text[msg_pos.end():]
                    # ลบ trailing "} หรือ " จากท้าย
                    raw_msg = _re.sub(r'"\s*\}?\s*$', '', raw_after).strip()
                    return {'type': extracted_type, 'message': raw_msg}
                return {'type': extracted_type, 'message': text}
            return None

        parsed = _extract_json(raw)
        if parsed and isinstance(parsed, dict) and 'type' in parsed:
            parsed['_model_used'] = model
            return parsed

        # ไม่พบ JSON ที่ถูกต้อง — strip code blocks แล้ว return เป็น chat
        import re as _re
        clean = _re.sub(r'```(?:json)?\s*\{.*?\}\s*```', '', raw, flags=_re.DOTALL).strip()
        return {'type': 'chat', 'message': clean or raw, '_model_used': model}
    except Exception as e:
        return {'type': 'chat', 'message': f'เกิดข้อผิดพลาด: {str(e)}'}


def _agent_explain_workspace_result(original_question, tool_name, raw_result, settings):
    """Two-pass: ให้ AI สรุปผลจาก Google Workspace tools เป็นภาษาไทยที่เป็นธรรมชาติ"""
    try:
        from google import genai as google_genai
        gemini_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_key:
            return raw_result
        client = google_genai.Client(api_key=gemini_key)
        name = settings.get('agent_name', 'น้องเอก')
        particle = settings.get('ending_particle', 'ครับ')
        tool_label = {'query_google_drive': 'Google Drive', 'read_google_sheet': 'Google Sheets'}.get(tool_name, 'Google Workspace')
        prompt = f"""คุณชื่อ "{name}" เป็นผู้ช่วย AI ของระบบ EKG Shops
ผู้ใช้ถามว่า: "{original_question}"

ผลจาก {tool_label}:
{raw_result}

กรุณาสรุปและตอบเป็นภาษาไทยที่เป็นธรรมชาติ เป็นกันเอง ไม่ต้องแสดงข้อมูล raw ซ้ำทั้งหมด:
- บอกว่าพบอะไร มีกี่รายการ
- ถ้ามีไฟล์/sheet ให้บอกชื่อและข้อมูลสำคัญ
- ถ้าผู้ใช้ถามเรื่องใดเป็นพิเศษ ให้ตอบตรงจุด
- ใช้คำลงท้าย "{particle}" ตอบกระชับเป็นกันเอง"""
        resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt])
        return (resp.text or '').strip() or raw_result
    except Exception:
        return raw_result


def _agent_explain_code(original_question, code_result, settings):
    """Two-pass: ให้ AI อธิบายผลจาก code tool เป็นภาษาไทยแทนการส่ง raw code"""
    try:
        from google import genai as google_genai
        gemini_key = os.environ.get('GEMINI_API_KEY')
        if not gemini_key:
            return code_result
        client = google_genai.Client(api_key=gemini_key)
        name = settings.get('agent_name', 'น้องเอก')
        particle = settings.get('ending_particle', 'ครับ')
        prompt = f"""คุณชื่อ "{name}" เป็น Developer Consultant ของระบบ EKG Shops (Flask + PostgreSQL + Gunicorn)
ผู้ใช้ถามว่า: "{original_question}"

ผลจากการค้นหาในโค้ด:
{code_result}

กรุณาอธิบายเป็นภาษาไทยที่เข้าใจง่าย ไม่ต้องแสดงโค้ดซ้ำทั้งหมด:
1. ส่วนนี้ทำอะไร / ทำงานอย่างไร
2. จุดสำคัญที่น่าสังเกต
3. ถ้ามีปัญหาหรือสิ่งที่ควรปรับปรุง ให้แนะนำด้วย

ใช้คำลงท้าย "{particle}" ตอบสั้นกระชับได้เลย"""
        resp = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt])
        return resp.text.strip()
    except Exception:
        return code_result


def _get_replit_connector_token(connector_name):
    """ดึง OAuth access token จาก Replit Connectors API"""
    import urllib.request as _ur, urllib.error as _ue, json as _j
    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    if not hostname:
        raise Exception('ไม่พบ REPLIT_CONNECTORS_HOSTNAME — กรุณา connect Google integration ก่อน')
    repl_id  = os.environ.get('REPL_IDENTITY', '')
    web_tok  = os.environ.get('WEB_REPL_RENEWAL', '')
    x_token  = ('repl ' + repl_id) if repl_id else (('depl ' + web_tok) if web_tok else None)
    if not x_token:
        raise Exception('ไม่พบ Replit identity token')
    req = _ur.Request(
        f'https://{hostname}/api/v2/connection?include_secrets=true&connector_names={connector_name}',
        headers={'Accept': 'application/json', 'X-Replit-Token': x_token}
    )
    with _ur.urlopen(req, timeout=8) as resp:
        data = _j.loads(resp.read())
    items = data.get('items', [])
    if not items:
        raise Exception(f'ไม่พบ connection สำหรับ {connector_name} — กรุณา authorize ก่อน')
    s = items[0].get('settings', {})
    token = s.get('access_token') or s.get('oauth', {}).get('credentials', {}).get('access_token')
    if not token:
        raise Exception(f'ไม่พบ access_token สำหรับ {connector_name}')
    return token


def _get_service_account_token(scopes=None):
    """สร้าง access token จาก Google Service Account JSON"""
    import json as _j
    if scopes is None:
        scopes = [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
    sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    if not sa_json:
        return None, 'ไม่พบ GOOGLE_SERVICE_ACCOUNT_JSON'
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as _gatr
        sa_info = _j.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
        creds.refresh(_gatr.Request())
        return creds.token, None
    except Exception as e:
        return None, f'Service Account error: {str(e)}'


def _agent_read_google_sheet(params):
    """อ่านข้อมูลจาก Google Sheets ผ่าน Replit Connector"""
    import urllib.request as _ur, urllib.parse as _up, json as _j
    sheet_id = (params.get('spreadsheet_id') or '').strip()
    range_   = (params.get('range') or 'Sheet1').strip()
    limit    = int(params.get('limit') or 50)
    if not sheet_id:
        return {'text': '⚠️ กรุณาระบุ spreadsheet_id'}
    try:
        token = _get_replit_connector_token('google-sheet')
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{_up.quote(sheet_id, safe="")}/values/{_up.quote(range_, safe="!:")}'
        req = _ur.Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
        with _ur.urlopen(req, timeout=10) as resp:
            data = _j.loads(resp.read())
        rows = data.get('values', [])
        if not rows:
            return {'text': f'📋 ไม่พบข้อมูลใน {range_}'}
        header = rows[0] if rows else []
        data_rows = rows[1:limit+1] if len(rows) > 1 else []
        lines = [' | '.join(str(c) for c in header)]
        lines.append('-' * max(len(lines[0]), 20))
        for row in data_rows:
            padded = list(row) + [''] * (len(header) - len(row))
            lines.append(' | '.join(str(c) for c in padded[:len(header)]))
        total = len(rows) - 1
        note = f'\n_(แสดง {len(data_rows)}/{total} แถว)_' if total > len(data_rows) else ''
        return {'text': f'📊 **Google Sheet:** `{range_}`\n```\n' + '\n'.join(lines) + f'\n```{note}'}
    except Exception as e:
        return {'text': f'❌ อ่าน Google Sheet ไม่สำเร็จ: {str(e)}'}


def _agent_query_google_drive(params):
    """ค้นหาไฟล์ใน Google Drive — recursive, ใช้ Service Account หรือ fallback OAuth"""
    import urllib.request as _ur, urllib.parse as _up, json as _j
    query     = (params.get('query') or '').strip()
    folder_id = (params.get('folder_id') or '').strip()
    limit     = int(params.get('limit') or 30)
    if not query and not folder_id:
        return {'text': '⚠️ กรุณาระบุ query หรือ folder_id'}
    try:
        sa_token, sa_err = _get_service_account_token(['https://www.googleapis.com/auth/drive.readonly'])
        if sa_token:
            token = sa_token
            auth_mode = 'Service Account'
        else:
            token = _get_replit_connector_token('google-drive')
            auth_mode = 'OAuth'

        def _drive_list(fid, q_name='', max_items=100):
            """ดึงไฟล์/โฟลเดอร์ทุกชั้น (recursive) — filter ฝั่ง client เพื่อให้ recurse ได้ถูกต้อง"""
            all_files = []
            stack = [fid]
            visited = set()
            q_lower = q_name.lower() if q_name else ''
            while stack and len(all_files) < max_items:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                qs = _up.quote(f"trashed=false and '{cur}' in parents")
                url = (f'https://www.googleapis.com/drive/v3/files'
                       f'?q={qs}&pageSize=100'
                       f'&fields=files(id,name,mimeType,modifiedTime,size,webViewLink)')
                req = _ur.Request(url, headers={'Authorization': f'Bearer {token}'})
                with _ur.urlopen(req, timeout=10) as r:
                    items = _j.loads(r.read()).get('files', [])
                for item in items:
                    is_folder = item['mimeType'] == 'application/vnd.google-apps.folder'
                    name_match = (not q_lower) or (q_lower in item['name'].lower())
                    if is_folder:
                        stack.append(item['id'])  # เสมอ recurse เข้า subfolder
                    if name_match:
                        all_files.append(item)
                        if len(all_files) >= max_items:
                            return all_files
            return all_files

        if folder_id:
            files = _drive_list(folder_id, query, limit)
        else:
            sandbox_id = '14hvk11Edw6arLFOwGXex_Zm5hKSr4KlA'
            files = _drive_list(sandbox_id, query, limit)

        if not files:
            label = f'"{query}"' if query else 'folder'
            return {'text': f'🔍 ไม่พบไฟล์ใน {label} (ค้นหาแบบ recursive ทุกชั้นแล้ว)'}

        mime_icons = {
            'application/vnd.google-apps.spreadsheet': '📊',
            'application/vnd.google-apps.document': '📄',
            'application/vnd.google-apps.presentation': '📑',
            'application/vnd.google-apps.folder': '📁',
            'image/jpeg': '🖼️', 'image/png': '🖼️', 'image/tiff': '🖼️',
            'application/pdf': '📕',
        }
        label = f'"{query}"' if query else 'sandbox'
        lines = [f'🔍 ผลค้นหา {label} ({len(files)} รายการ) — via {auth_mode}\n']
        for f in files:
            icon = mime_icons.get(f.get('mimeType', ''), '📎')
            mod  = (f.get('modifiedTime', '')[:10]) or '-'
            size = f.get('size', '')
            size_str = f' ({int(size)//1024:,} KB)' if size else ''
            link = f.get('webViewLink', '')
            lines.append(f"{icon} **{f['name']}**{size_str}\n   ID: `{f['id']}` | {mod}" + (f"\n   🔗 {link}" if link else ''))
        return {'text': '\n\n'.join(lines)}
    except Exception as e:
        return {'text': f'❌ ค้นหา Google Drive ไม่สำเร็จ: {str(e)}'}


def _agent_write_google_sheet(params):
    """เขียน/append ข้อมูลลง Google Sheets ผ่าน Replit Connector"""
    import urllib.request as _ur, urllib.parse as _up, json as _j
    sheet_id = (params.get('spreadsheet_id') or '').strip()
    range_   = (params.get('range') or 'Sheet1!A1').strip()
    values   = params.get('values', [])
    mode     = (params.get('mode') or 'append').lower()
    if not sheet_id:
        return {'text': '⚠️ กรุณาระบุ spreadsheet_id'}
    if not values or not isinstance(values, list):
        return {'text': '⚠️ กรุณาระบุ values เป็น array 2D เช่น [["คอลัมน์1","คอลัมน์2"]]'}
    try:
        token = _get_replit_connector_token('google-sheet')
        body = _j.dumps({'values': values, 'majorDimension': 'ROWS'}).encode()
        if mode == 'overwrite':
            url = f'https://sheets.googleapis.com/v4/spreadsheets/{_up.quote(sheet_id, safe="")}/values/{_up.quote(range_, safe="!:")}?valueInputOption=USER_ENTERED'
            req = _ur.Request(url, data=body, headers={
                'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'
            }, method='PUT')
        else:
            url = f'https://sheets.googleapis.com/v4/spreadsheets/{_up.quote(sheet_id, safe="")}/values/{_up.quote(range_, safe="!:")}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS'
            req = _ur.Request(url, data=body, headers={
                'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'
            }, method='POST')
        with _ur.urlopen(req, timeout=10) as resp:
            result = _j.loads(resp.read())
        updated = result.get('updates', result).get('updatedRows', len(values))
        return {'text': f'✅ บันทึกข้อมูลสำเร็จ — อัปเดต {updated} แถว ใน `{range_}` (mode: {mode})'}
    except Exception as e:
        return {'text': f'❌ เขียน Google Sheet ไม่สำเร็จ: {str(e)}'}


def _agent_execute_read_tool(tool, params, cursor):
    import datetime as _dt
    today = _dt.date.today()
    status_labels = {
        'pending_payment': 'รอชำระ', 'processing': 'กำลังจัดเตรียม',
        'shipped': 'จัดส่งแล้ว', 'delivered': 'ส่งถึงแล้ว',
        'cancelled': 'ยกเลิก', 'returned': 'คืนสินค้า', 'stock_restored': 'คืนสต็อก'
    }

    if tool == 'query_sales_today':
        cursor.execute('''SELECT COUNT(*) as cnt, COALESCE(SUM(final_amount),0) as total FROM orders
            WHERE status NOT IN ('cancelled','returned','stock_restored') AND DATE(created_at) = %s AND is_quick_order = FALSE''', (today,))
        day = cursor.fetchone()
        cursor.execute('''SELECT COUNT(*) as cnt, COALESCE(SUM(final_amount),0) as total FROM orders
            WHERE status NOT IN ('cancelled','returned','stock_restored') AND DATE(created_at) >= DATE_TRUNC('week', CURRENT_DATE) AND is_quick_order = FALSE''')
        week = cursor.fetchone()
        cursor.execute('''SELECT COUNT(*) as cnt, COALESCE(SUM(final_amount),0) as total FROM orders
            WHERE status NOT IN ('cancelled','returned','stock_restored') AND DATE(created_at) >= DATE_TRUNC('month', CURRENT_DATE) AND is_quick_order = FALSE''')
        month = cursor.fetchone()
        return {'text': f"📊 ยอดขายวันนี้: {int(day['cnt'])} ออเดอร์ ฿{float(day['total']):,.0f}\n"
                        f"สัปดาห์นี้: {int(week['cnt'])} ออเดอร์ ฿{float(week['total']):,.0f}\n"
                        f"เดือนนี้: {int(month['cnt'])} ออเดอร์ ฿{float(month['total']):,.0f}"}

    elif tool == 'query_sales_by_brand':
        cursor.execute('''
            SELECT b.name as brand_name, COUNT(DISTINCT o.id) as order_cnt, COALESCE(SUM(oi.subtotal),0) as total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            JOIN brands b ON b.id = p.brand_id
            WHERE o.status NOT IN ('cancelled','returned','stock_restored')
            AND DATE(o.created_at) >= DATE_TRUNC('month', CURRENT_DATE)
            AND o.is_quick_order = FALSE
            GROUP BY b.name ORDER BY total DESC LIMIT 8
        ''')
        rows = cursor.fetchall()
        if not rows:
            return {'text': 'ยังไม่มีข้อมูลยอดขายแยกแบรนด์เดือนนี้'}
        lines = [f"• {r['brand_name']}: {int(r['order_cnt'])} ออเดอร์ ฿{float(r['total']):,.0f}" for r in rows]
        return {'text': "📦 ยอดขายแยกแบรนด์ (เดือนนี้):\n" + "\n".join(lines)}

    elif tool == 'query_top_products':
        limit = int(params.get('limit', 5))
        cursor.execute('''
            SELECT p.name as product_name, SUM(oi.quantity) as total_qty, COALESCE(SUM(oi.subtotal),0) as revenue
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE o.status NOT IN ('cancelled','returned','stock_restored')
            AND DATE(o.created_at) >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY p.name ORDER BY total_qty DESC LIMIT %s
        ''', (limit,))
        rows = cursor.fetchall()
        if not rows:
            return {'text': 'ยังไม่มีข้อมูลสินค้าขายดีเดือนนี้'}
        lines = [f"{i+1}. {r['product_name']} — {int(r['total_qty'])} ชิ้น ฿{float(r['revenue']):,.0f}" for i, r in enumerate(rows)]
        return {'text': f"🏆 Top {limit} สินค้าขายดี (เดือนนี้):\n" + "\n".join(lines)}

    elif tool == 'query_low_stock':
        threshold = int(params.get('threshold', 5))
        cursor.execute('''
            SELECT p.name as product_name, s.sku_code, s.stock
            FROM skus s JOIN products p ON p.id = s.product_id
            WHERE s.stock <= %s AND s.stock >= 0 AND p.status = 'active'
            ORDER BY s.stock ASC LIMIT 15
        ''', (threshold,))
        rows = cursor.fetchall()
        if not rows:
            return {'text': f'✅ ไม่มีสินค้าสต็อกต่ำกว่า {threshold} ชิ้น'}
        lines = [f"• {r['product_name']} [{r['sku_code']}] — {r['stock']} ชิ้น" for r in rows]
        return {'text': f"⚠️ สินค้าสต็อกต่ำกว่า {threshold} ชิ้น ({len(rows)} รายการ):\n" + "\n".join(lines)}

    elif tool == 'query_stock_product':
        name = params.get('product_name', '')
        cursor.execute('''SELECT p.name as product_name, s.sku_code, s.stock FROM skus s JOIN products p ON p.id = s.product_id
            WHERE p.name ILIKE %s ORDER BY s.sku_code LIMIT 20''', (f'%{name}%',))
        rows = cursor.fetchall()
        if not rows:
            return {'text': f'ไม่พบสินค้าที่ชื่อใกล้เคียง "{name}"'}
        lines = [f"• {r['sku_code']} — {r['stock']} ชิ้น" for r in rows]
        return {'text': f"📦 สต็อก {rows[0]['product_name']}:\n" + "\n".join(lines)}

    elif tool == 'query_products':
        keyword  = (params.get('keyword') or params.get('product_name') or '').strip()
        category = (params.get('category') or '').strip()
        brand    = (params.get('brand') or '').strip()
        prod_type = (params.get('product_type') or '').strip()
        limit    = min(50, max(1, int(params.get('limit') or 30)))
        conditions = ["p.status = 'active'"]
        values = []
        if keyword:
            conditions.append("p.name ILIKE %s")
            values.append(f'%{keyword}%')
        if category:
            conditions.append("c.name ILIKE %s")
            values.append(f'%{category}%')
        if brand:
            conditions.append("b.name ILIKE %s")
            values.append(f'%{brand}%')
        if prod_type:
            conditions.append("p.product_type = %s")
            values.append(prod_type)
        where = ' AND '.join(conditions)
        cursor.execute(f'''
            SELECT p.id, p.name, p.parent_sku, p.product_type, b.name as brand_name,
                   STRING_AGG(DISTINCT c.name, ', ') as categories
            FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN product_categories pc ON pc.product_id = p.id
            LEFT JOIN categories c ON c.id = pc.category_id
            WHERE {where}
            GROUP BY p.id, p.name, p.parent_sku, p.product_type, b.name
            ORDER BY b.name, p.name
            LIMIT %s
        ''', values + [limit])
        rows = cursor.fetchall()
        if not rows:
            filters = []
            if keyword: filters.append(f'ชื่อ "{keyword}"')
            if category: filters.append(f'หมวดหมู่ "{category}"')
            if brand: filters.append(f'แบรนด์ "{brand}"')
            return {'text': f'ไม่พบสินค้า ({", ".join(filters) or "ทั้งหมด"})'}
        lines = []
        for r in rows:
            cats = r['categories'] or '-'
            lines.append(f"• {r['name']} | SKU: {r['parent_sku']} | แบรนด์: {r['brand_name']} | หมวด: {cats} | ประเภท: {r['product_type']}")
        header_parts = []
        if keyword: header_parts.append(f'ชื่อ "{keyword}"')
        if category: header_parts.append(f'หมวด "{category}"')
        if brand: header_parts.append(f'แบรนด์ "{brand}"')
        header = f"🛍️ สินค้า ({', '.join(header_parts) or 'ทั้งหมด'}) — {len(rows)} รายการ:"
        return {'text': header + '\n' + '\n'.join(lines)}

    elif tool == 'query_order_counts':
        cursor.execute('''SELECT status, COUNT(*) as cnt FROM orders WHERE is_quick_order = FALSE GROUP BY status ORDER BY cnt DESC''')
        rows = cursor.fetchall()
        lines = [f"• {status_labels.get(r['status'], r['status'])}: {r['cnt']} รายการ" for r in rows]
        return {'text': "📋 จำนวนออเดอร์ทุกสถานะ:\n" + "\n".join(lines)}

    elif tool == 'query_pending_orders':
        limit = int(params.get('limit', 10))
        cursor.execute('''
            SELECT o.order_number, u.full_name as reseller_name, o.final_amount, o.status, o.created_at
            FROM orders o LEFT JOIN users u ON u.id = o.user_id
            WHERE o.status IN ('pending_payment','processing') AND o.is_quick_order = FALSE
            ORDER BY o.created_at DESC LIMIT %s
        ''', (limit,))
        rows = cursor.fetchall()
        if not rows:
            return {'text': '✅ ไม่มีออเดอร์ที่รอดำเนินการ'}
        lines = [f"• {r['order_number']} — {r['reseller_name'] or 'ไม่ระบุ'} ฿{float(r['final_amount']):,.0f} [{status_labels.get(r['status'], r['status'])}]" for r in rows]
        return {'text': f"⏳ ออเดอร์รอดำเนินการ ({len(rows)} รายการ):\n" + "\n".join(lines)}

    elif tool == 'query_order_detail':
        order_num = str(params.get('order_number', '') or params.get('order_id', ''))
        if order_num.isdigit():
            cursor.execute('''SELECT o.*, u.full_name as reseller_name FROM orders o LEFT JOIN users u ON u.id = o.user_id WHERE o.id = %s''', (int(order_num),))
        else:
            cursor.execute('''SELECT o.*, u.full_name as reseller_name FROM orders o LEFT JOIN users u ON u.id = o.user_id WHERE o.order_number ILIKE %s''', (f'%{order_num}%',))
        order = cursor.fetchone()
        if not order:
            return {'text': f'ไม่พบออเดอร์ {order_num}'}
        cursor.execute('''SELECT oi.product_name, oi.sku_code, oi.quantity, oi.unit_price FROM order_items oi WHERE oi.order_id = %s''', (order['id'],))
        items = cursor.fetchall()
        item_lines = [f"  • {it['product_name']} ({it['sku_code']}) x{it['quantity']} ฿{float(it['unit_price']):,.0f}" for it in items]
        return {'text': f"📋 ออเดอร์ {order['order_number']}\n"
                        f"ตัวแทน: {order['reseller_name'] or '-'}\n"
                        f"สถานะ: {status_labels.get(order['status'], order['status'])}\n"
                        f"ยอดรวม: ฿{float(order['final_amount']):,.0f}\n"
                        f"สินค้า:\n" + "\n".join(item_lines)}

    elif tool == 'query_customer':
        q = str(params.get('name', '') or params.get('phone', ''))
        cursor.execute('''SELECT name, phone, email, address, created_at FROM customers
            WHERE name ILIKE %s OR phone ILIKE %s ORDER BY created_at DESC LIMIT 5''', (f'%{q}%', f'%{q}%'))
        rows = cursor.fetchall()
        if not rows:
            return {'text': f'ไม่พบลูกค้าที่ค้นหา "{q}"'}
        lines = [f"• {r['name']} | {r['phone'] or '-'} | {r['email'] or '-'}" for r in rows]
        return {'text': f"👤 ผลค้นหาลูกค้า \"{q}\":\n" + "\n".join(lines)}

    elif tool == 'query_resellers':
        tier_filter = params.get('tier', '')
        if tier_filter:
            cursor.execute('''
                SELECT u.full_name, u.email, rt.name as tier_name,
                       COUNT(o.id) as order_cnt, COALESCE(SUM(o.final_amount),0) as total_spend
                FROM users u LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                LEFT JOIN orders o ON o.user_id = u.id AND o.status NOT IN ('cancelled','returned')
                WHERE u.role_name = 'Reseller' AND rt.name ILIKE %s
                GROUP BY u.full_name, u.email, rt.name ORDER BY total_spend DESC LIMIT 10
            ''', (f'%{tier_filter}%',))
        else:
            cursor.execute('''
                SELECT u.full_name, u.email, rt.name as tier_name,
                       COUNT(o.id) as order_cnt, COALESCE(SUM(o.final_amount),0) as total_spend
                FROM users u LEFT JOIN reseller_tiers rt ON rt.id = u.reseller_tier_id
                LEFT JOIN orders o ON o.user_id = u.id AND o.status NOT IN ('cancelled','returned')
                WHERE u.role_name = 'Reseller'
                GROUP BY u.full_name, u.email, rt.name ORDER BY total_spend DESC LIMIT 10
            ''')
        rows = cursor.fetchall()
        if not rows:
            return {'text': 'ไม่พบข้อมูลตัวแทน'}
        lines = [f"• {r['full_name']} [{r['tier_name'] or '-'}] {int(r['order_cnt'])} ออเดอร์ ฿{float(r['total_spend']):,.0f}" for r in rows]
        return {'text': f"👥 รายชื่อตัวแทน{' (' + tier_filter + ')' if tier_filter else ''}:\n" + "\n".join(lines)}

    elif tool == 'query_unread_chat':
        cursor.execute('''
            SELECT ct.id as thread_id, u.full_name as reseller_name, ct.last_message_preview,
                   ct.last_message_at, ct.needs_admin,
                   (SELECT COUNT(*) FROM chat_messages cm
                    WHERE cm.thread_id = ct.id AND cm.sender_type = 'reseller'
                    AND cm.created_at >= NOW() - INTERVAL '48 hours') as recent_msgs
            FROM chat_threads ct JOIN users u ON u.id = ct.reseller_id
            WHERE ct.is_archived = FALSE
              AND ct.last_message_at >= NOW() - INTERVAL '72 hours'
            ORDER BY ct.needs_admin DESC, ct.last_message_at DESC LIMIT 10
        ''')
        rows = cursor.fetchall()
        if not rows:
            return {'text': '✅ ไม่มีแชทที่มีกิจกรรมในช่วง 72 ชั่วโมงที่ผ่านมา'}
        lines = []
        for r in rows:
            flag = ' 🙋 ขอคุยกับ Admin' if r['needs_admin'] else ''
            lines.append(f"• {r['reseller_name']}{flag} — {int(r['recent_msgs'] or 0)} ข้อความ 48h: \"{(r['last_message_preview'] or '')[:40]}\"")
        return {'text': f"💬 แชทที่มีกิจกรรมล่าสุด ({len(rows)} ห้อง):\n" + "\n".join(lines)}

    elif tool == 'query_mto_status':
        cursor.execute('''
            SELECT mo.order_number, u.full_name as reseller_name, mo.status, mo.production_deadline,
                   COUNT(moi.id) as item_cnt
            FROM mto_orders mo LEFT JOIN users u ON u.id = mo.reseller_id
            LEFT JOIN mto_order_items moi ON moi.mto_order_id = mo.id
            WHERE mo.status NOT IN ('delivered','cancelled')
            GROUP BY mo.order_number, u.full_name, mo.status, mo.production_deadline
            ORDER BY mo.production_deadline ASC NULLS LAST LIMIT 10
        ''')
        rows = cursor.fetchall()
        if not rows:
            return {'text': '✅ ไม่มีออเดอร์ MTO ค้างอยู่'}
        mto_status_labels = {'pending': 'รอยืนยัน', 'confirmed': 'ยืนยันแล้ว', 'in_production': 'กำลังผลิต', 'ready': 'พร้อมส่ง', 'shipped': 'จัดส่งแล้ว'}
        lines = []
        for r in rows:
            deadline = r['production_deadline'].strftime('%d/%m/%Y') if r['production_deadline'] else '-'
            lines.append(f"• {r['order_number']} [{mto_status_labels.get(r['status'], r['status'])}] ตัวแทน: {r['reseller_name'] or '-'} ครบกำหนด: {deadline}")
        return {'text': f"🏭 ออเดอร์ MTO ค้างอยู่ ({len(rows)} รายการ):\n" + "\n".join(lines)}

    elif tool == 'chart_sales_trend':
        import datetime as _dt2
        days = int(params.get('days', 7))
        cursor.execute('''
            SELECT DATE(created_at) as day,
                   COUNT(*) as orders,
                   COALESCE(SUM(final_amount),0) as total
            FROM orders
            WHERE status NOT IN ('cancelled','returned','stock_restored')
              AND is_quick_order = FALSE
              AND DATE(created_at) >= CURRENT_DATE - INTERVAL %s
            GROUP BY day ORDER BY day
        ''', (f'{days} days',))
        rows = cursor.fetchall()
        labels = [r['day'].strftime('%d/%m') for r in rows]
        amounts = [float(r['total']) for r in rows]
        orders  = [int(r['orders']) for r in rows]
        chart = {
            'type': 'line',
            'data': {
                'labels': labels,
                'datasets': [
                    {'label': 'ยอดขาย (฿)', 'data': amounts, 'borderColor': '#8b5cf6', 'backgroundColor': 'rgba(139,92,246,0.1)', 'fill': True, 'tension': 0.4, 'yAxisID': 'y', 'pointRadius': 4, 'pointBackgroundColor': '#8b5cf6'},
                    {'label': 'จำนวนออเดอร์', 'data': orders, 'borderColor': '#ec4899', 'backgroundColor': 'rgba(236,72,153,0.1)', 'fill': False, 'tension': 0.4, 'yAxisID': 'y1', 'pointRadius': 4, 'pointBackgroundColor': '#ec4899', 'borderDash': [5,3]}
                ]
            },
            'options': {
                'responsive': True, 'interaction': {'mode': 'index', 'intersect': False},
                'plugins': {'legend': {'position': 'bottom', 'labels': {'font': {'size': 11}, 'usePointStyle': True}}},
                'scales': {
                    'y':  {'type': 'linear', 'display': True, 'position': 'left',  'ticks': {'callback': '__BAHT__', 'font': {'size': 10}}, 'grid': {'color': 'rgba(0,0,0,0.05)'}},
                    'y1': {'type': 'linear', 'display': True, 'position': 'right', 'ticks': {'font': {'size': 10}}, 'grid': {'drawOnChartArea': False}}
                }
            }
        }
        return {'text': f'📈 กราฟยอดขาย {days} วันที่ผ่านมา', 'chart': chart}

    elif tool == 'chart_sales_by_brand':
        cursor.execute('''
            SELECT b.name as brand_name, COALESCE(SUM(oi.subtotal),0) as total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            JOIN brands b ON b.id = p.brand_id
            WHERE o.status NOT IN ('cancelled','returned','stock_restored')
              AND DATE(o.created_at) >= DATE_TRUNC('month', CURRENT_DATE)
              AND o.is_quick_order = FALSE
            GROUP BY b.name ORDER BY total DESC LIMIT 8
        ''')
        rows = cursor.fetchall()
        if not rows:
            return {'text': 'ยังไม่มีข้อมูลยอดขายแบรนด์เดือนนี้'}
        labels = [r['brand_name'] for r in rows]
        data   = [float(r['total']) for r in rows]
        colors = ['#8b5cf6','#ec4899','#06b6d4','#10b981','#f59e0b','#ef4444','#6366f1','#84cc16']
        chart = {
            'type': 'doughnut',
            'data': {'labels': labels, 'datasets': [{'data': data, 'backgroundColor': colors[:len(data)], 'borderWidth': 2, 'borderColor': '#fff', 'hoverOffset': 8}]},
            'options': {
                'responsive': True, 'cutout': '60%',
                'plugins': {'legend': {'position': 'right', 'labels': {'font': {'size': 11}, 'usePointStyle': True, 'padding': 12}}}
            }
        }
        total = sum(data)
        return {'text': f'🍩 ยอดขายแยกแบรนด์เดือนนี้ รวม ฿{total:,.0f}', 'chart': chart}

    elif tool == 'chart_order_status':
        cursor.execute('''
            SELECT status, COUNT(*) as cnt FROM orders
            WHERE is_quick_order = FALSE GROUP BY status ORDER BY cnt DESC
        ''')
        rows = cursor.fetchall()
        sl = {'pending_payment': 'รอชำระ','processing': 'จัดเตรียม','shipped': 'จัดส่ง','delivered': 'ส่งถึง','cancelled': 'ยกเลิก','returned': 'คืนสินค้า','stock_restored': 'คืนสต็อก'}
        sc = {'pending_payment': '#f59e0b','processing': '#3b82f6','shipped': '#06b6d4','delivered': '#10b981','cancelled': '#ef4444','returned': '#f97316','stock_restored': '#8b5cf6'}
        labels = [sl.get(r['status'], r['status']) for r in rows]
        data   = [int(r['cnt']) for r in rows]
        bgcolors = [sc.get(r['status'], '#9ca3af') for r in rows]
        chart = {
            'type': 'pie',
            'data': {'labels': labels, 'datasets': [{'data': data, 'backgroundColor': bgcolors, 'borderWidth': 2, 'borderColor': '#fff', 'hoverOffset': 6}]},
            'options': {
                'responsive': True,
                'plugins': {'legend': {'position': 'right', 'labels': {'font': {'size': 11}, 'usePointStyle': True, 'padding': 12}}}
            }
        }
        return {'text': f'🥧 สัดส่วนสถานะออเดอร์ทั้งหมด ({sum(data):,} ออเดอร์)', 'chart': chart}

    elif tool == 'chart_top_products':
        limit = int(params.get('limit', 10))
        cursor.execute('''
            SELECT p.name, COALESCE(SUM(oi.quantity),0) as sold, COALESCE(SUM(oi.subtotal),0) as revenue
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN skus s ON s.id = oi.sku_id
            JOIN products p ON p.id = s.product_id
            WHERE o.status NOT IN ('cancelled','returned','stock_restored')
              AND DATE(o.created_at) >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY p.name ORDER BY sold DESC LIMIT %s
        ''', (limit,))
        rows = cursor.fetchall()
        if not rows:
            return {'text': 'ยังไม่มีข้อมูลยอดขายสินค้าเดือนนี้'}
        labels  = [r['name'][:20] for r in rows]
        sold    = [int(r['sold']) for r in rows]
        revenue = [float(r['revenue']) for r in rows]
        chart = {
            'type': 'bar',
            'data': {
                'labels': labels,
                'datasets': [
                    {'label': 'ชิ้นที่ขายได้', 'data': sold, 'backgroundColor': 'rgba(139,92,246,0.75)', 'borderColor': '#8b5cf6', 'borderWidth': 1.5, 'borderRadius': 6, 'yAxisID': 'y'},
                    {'label': 'รายได้ (฿)', 'data': revenue, 'backgroundColor': 'rgba(236,72,153,0.2)', 'borderColor': '#ec4899', 'borderWidth': 1.5, 'borderRadius': 6, 'type': 'line', 'tension': 0.4, 'yAxisID': 'y1', 'pointRadius': 4}
                ]
            },
            'options': {
                'responsive': True, 'indexAxis': 'x',
                'plugins': {'legend': {'position': 'bottom', 'labels': {'font': {'size': 10}, 'usePointStyle': True}}},
                'scales': {
                    'x':  {'ticks': {'font': {'size': 9}}, 'grid': {'display': False}},
                    'y':  {'ticks': {'font': {'size': 10}}, 'grid': {'color': 'rgba(0,0,0,0.05)'}},
                    'y1': {'display': True, 'position': 'right', 'ticks': {'callback': '__BAHT__', 'font': {'size': 10}}, 'grid': {'drawOnChartArea': False}}
                }
            }
        }
        return {'text': f'🏆 สินค้าขายดีสุด {len(rows)} อันดับเดือนนี้', 'chart': chart}

    elif tool == 'chart_low_stock':
        threshold = int(params.get('threshold', 10))
        cursor.execute('''
            SELECT p.name, s.sku_code, s.stock
            FROM skus s JOIN products p ON p.id = s.product_id
            WHERE s.stock <= %s AND p.status = 'active'
            ORDER BY s.stock ASC LIMIT 15
        ''', (threshold,))
        rows = cursor.fetchall()
        if not rows:
            return {'text': f'✅ ไม่มีสินค้าสต็อกต่ำกว่า {threshold} ชิ้น'}
        labels = [f"{r['name'][:15]} ({r['sku_code']})" for r in rows]
        stocks = [int(r['stock']) for r in rows]
        bgcolors = ['#ef4444' if s == 0 else '#f97316' if s <= 3 else '#f59e0b' if s <= 5 else '#84cc16' for s in stocks]
        chart = {
            'type': 'bar',
            'data': {'labels': labels, 'datasets': [{'label': 'สต็อกคงเหลือ (ชิ้น)', 'data': stocks, 'backgroundColor': bgcolors, 'borderRadius': 5, 'borderSkipped': False}]},
            'options': {
                'responsive': True, 'indexAxis': 'y',
                'plugins': {'legend': {'display': False}},
                'scales': {
                    'x': {'ticks': {'stepSize': 1, 'font': {'size': 10}}, 'grid': {'color': 'rgba(0,0,0,0.05)'}},
                    'y': {'ticks': {'font': {'size': 9}}, 'grid': {'display': False}}
                }
            }
        }
        return {'text': f'⚠️ สต็อกสินค้าใกล้หมด {len(rows)} รายการ (≤{threshold} ชิ้น)', 'chart': chart}

    elif tool == 'read_notes':
        try:
            cursor.execute('SELECT note_key, note_value, updated_at FROM agent_notes ORDER BY updated_at DESC')
            rows = cursor.fetchall()
            if not rows:
                return {'text': '📒 สมุดโน้ต AI ว่างเปล่า — ยังไม่มีบันทึกใดๆ'}
            lines = [f"• **{r['note_key']}**: {r['note_value']} _(บันทึกเมื่อ {str(r['updated_at'])[:16]})_" for r in rows]
            return {'text': f"📒 **สมุดโน้ต AI** ({len(rows)} รายการ)\n" + '\n'.join(lines)}
        except Exception as e:
            return {'text': f'ไม่สามารถอ่านสมุดโน้ตได้: {e}'}

    elif tool == 'query_facebook_ads':
        import urllib.request as _ur
        import urllib.parse as _up
        import urllib.error as _ue
        try:
            conn2 = get_db()
            cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            token, account_id = _get_meta_credentials(cur2)
            cur2.close(); conn2.close()
        except Exception as _ce:
            return {'text': f'ไม่สามารถอ่านข้อมูล Meta credentials: {_ce}'}
        if not token or not account_id:
            return {'text': '⚠️ ยังไม่ได้ตั้งค่า Meta Access Token หรือ Ad Account ID\nไปที่หน้า Facebook Ads → Meta Marketing API Settings เพื่อตั้งค่า'}
        period = str(params.get('period', '30d'))
        period_map = {'7d': 7, '30d': 30, '90d': 90}
        days_n = period_map.get(period, 30)
        since = (datetime.now() - timedelta(days=days_n)).strftime('%Y-%m-%d')
        until = datetime.now().strftime('%Y-%m-%d')
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'
        _qp = _up.urlencode({
            'fields': 'impressions,clicks,spend,reach,cpm,cpc,ctr,actions,action_values',
            'time_range': json.dumps({'since': since, 'until': until}),
            'level': 'account',
            'access_token': token
        })
        _url = f'https://graph.facebook.com/v19.0/{account_id}/insights?{_qp}'
        try:
            _req = _ur.Request(_url, headers={'User-Agent': 'EKGShops/1.0'})
            with _ur.urlopen(_req, timeout=15) as _resp:
                _raw = json.loads(_resp.read().decode())
            _rows = _raw.get('data', [])
            if not _rows:
                return {'text': f'📊 ไม่มีข้อมูลโฆษณา Meta ในช่วง {since} — {until}'}
            _r = _rows[0]
            _actions = {a['action_type']: float(a['value']) for a in (_r.get('actions') or [])}
            _av = {a['action_type']: float(a['value']) for a in (_r.get('action_values') or [])}
            _spend = float(_r.get('spend', 0))
            _pval = _av.get('purchase', 0)
            _pcnt = int(_actions.get('purchase', 0))
            _roas = round(_pval / _spend, 2) if _spend > 0 else 0
            return {'text': (
                f"📘 Meta Ads — {period} ({since} ถึง {until})\n"
                f"💰 งบโฆษณา: ฿{_spend:,.2f}\n"
                f"👁 Impressions: {int(_r.get('impressions',0)):,}\n"
                f"🖱 Clicks: {int(_r.get('clicks',0)):,}\n"
                f"📈 CTR: {float(_r.get('ctr',0)):.2f}%\n"
                f"💵 CPC: ฿{float(_r.get('cpc',0)):,.2f}\n"
                f"📢 CPM: ฿{float(_r.get('cpm',0)):,.2f}\n"
                f"🛒 ยอดซื้อ: {_pcnt} ครั้ง มูลค่า ฿{_pval:,.0f}\n"
                f"📊 ROAS: {_roas}x"
            )}
        except _ue.HTTPError as _he:
            _eb = _he.read().decode()
            try:
                _ej = json.loads(_eb).get('error', {}).get('message', _eb)
            except Exception:
                _ej = _eb
            return {'text': f'❌ Meta API Error: {_ej}'}
        except Exception as _me:
            return {'text': f'ไม่สามารถดึงข้อมูล Meta Ads ได้: {_me}'}

    elif tool == 'search_web':
        query = params.get('query', '').strip()
        if not query:
            return {'text': 'กรุณาระบุ query ที่ต้องการค้นหา'}
        try:
            from google import genai as _sg
            from google.genai import types as _sgt
            _key = os.environ.get('GEMINI_API_KEY', '')
            if not _key:
                return {'text': 'ไม่พบ GEMINI_API_KEY สำหรับค้นหาเว็บ'}
            _sc = _sg.Client(api_key=_key)
            _scfg = _sgt.GenerateContentConfig(
                tools=[_sgt.Tool(google_search=_sgt.GoogleSearch())]
            )
            _sr = _sc.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"ค้นหา: {query} — ตอบเป็นภาษาไทย สรุปสั้นๆ ชัดเจน พร้อมแหล่งอ้างอิงถ้ามี",
                config=_scfg
            )
            return {'text': f"🔍 ผลค้นหา: {query}\n\n{_sr.text.strip()}"}
        except Exception as _se:
            return {'text': f'ค้นหาไม่สำเร็จ: {str(_se)}'}

    # ─── Code Inspector Tools (READ-ONLY) ────────────────────────────────────
    elif tool == 'list_files':
        import glob as _glob, os as _os
        _root = '/home/runner/workspace'
        _path = params.get('path', '.').strip().lstrip('/')
        _pattern = params.get('pattern', '*')
        _safe_dir = _os.path.realpath(_os.path.join(_root, _path))
        if not _safe_dir.startswith(_root):
            return {'text': '⛔ ไม่อนุญาตให้เข้าถึงนอก project directory'}
        _files = _glob.glob(_os.path.join(_safe_dir, '**', _pattern), recursive=True)
        _files += _glob.glob(_os.path.join(_safe_dir, _pattern))
        _files = sorted(set(f.replace(_root + '/', '') for f in _files if _os.path.isfile(f)))
        _files = [f for f in _files if not any(s in f for s in ['/.git/', '/__pycache__/', '/.pythonlibs/', '/node_modules/'])]
        if not _files:
            return {'text': f'ไม่พบไฟล์ที่ตรง pattern "{_pattern}" ใน {_path or "/"}'}
        _lines = [f'📁 ไฟล์ใน {_path or "/"} (pattern: {_pattern}) — {len(_files)} ไฟล์:']
        _lines += [f'  {f}' for f in _files[:100]]
        if len(_files) > 100:
            _lines.append(f'  … และอีก {len(_files)-100} ไฟล์')
        return {'text': '\n'.join(_lines)}

    elif tool == 'read_code':
        import os as _os
        _root = '/home/runner/workspace'
        _file = (params.get('file') or '').strip().lstrip('/')
        if not _file:
            return {'text': 'กรุณาระบุ file เช่น "app.py" หรือ "static/js/dashboard.js"'}
        _safe = _os.path.realpath(_os.path.join(_root, _file))
        if not _safe.startswith(_root):
            return {'text': '⛔ ไม่อนุญาตให้เข้าถึงนอก project directory'}
        if not _os.path.isfile(_safe):
            return {'text': f'ไม่พบไฟล์: {_file}'}
        _offset = max(1, int(params.get('offset') or 1))
        _limit = min(200, max(10, int(params.get('limit') or 80)))
        try:
            with open(_safe, 'r', encoding='utf-8', errors='replace') as _fh:
                _all = _fh.readlines()
            _total = len(_all)
            _slice = _all[_offset - 1: _offset - 1 + _limit]
            _numbered = ''.join(f'{_offset + i:5d}│ {ln}' for i, ln in enumerate(_slice))
            _header = f'📄 {_file} (บรรทัด {_offset}–{_offset+len(_slice)-1} จากทั้งหมด {_total} บรรทัด)\n'
            return {'text': _header + '```\n' + _numbered + '\n```'}
        except Exception as _e:
            return {'text': f'อ่านไฟล์ไม่สำเร็จ: {str(_e)}'}

    elif tool == 'search_code':
        import subprocess as _sp, os as _os
        _root = '/home/runner/workspace'
        _pattern = (params.get('pattern') or '').strip()
        if not _pattern:
            return {'text': 'กรุณาระบุ pattern เช่น "def create_order" หรือ "coupon_discount"'}
        _file_glob = (params.get('file') or '').strip() or '.'
        _ctx = min(10, max(0, int(params.get('context_lines') or 2)))
        _safe_path = _os.path.join(_root, _file_glob.lstrip('/'))
        try:
            _args = ['grep', '-rn', '--include=*.py', '--include=*.js', '--include=*.html',
                     '--include=*.css', '--include=*.json', f'-C{_ctx}', _pattern, _safe_path]
            _res = _sp.run(_args, capture_output=True, text=True, timeout=10, cwd=_root)
            _out = _res.stdout.strip()
            if not _out:
                return {'text': f'ไม่พบ "{_pattern}" ในโค้ด'}
            _lines_out = _out.split('\n')
            _preview = '\n'.join(_lines_out[:150])
            _extra = f'\n… (แสดง 150/{len(_lines_out)} บรรทัด)' if len(_lines_out) > 150 else ''
            return {'text': f'🔎 ค้นหา "{_pattern}":\n```\n{_preview}\n```{_extra}'}
        except Exception as _e:
            return {'text': f'ค้นหาไม่สำเร็จ: {str(_e)}'}

    elif tool == 'query_db_schema':
        _table = (params.get('table') or '').strip().lower()
        if _table:
            cursor.execute('''
                SELECT c.column_name, c.data_type, c.column_default, c.is_nullable,
                       c.character_maximum_length
                FROM information_schema.columns c
                WHERE c.table_name = %s
                ORDER BY c.ordinal_position
            ''', (_table,))
            _cols = cursor.fetchall()
            if not _cols:
                return {'text': f'ไม่พบตาราง "{_table}" ใน database'}
            cursor.execute('''
                SELECT tc.constraint_type, kcu.column_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name AND tc.table_name = kcu.table_name
                WHERE tc.table_name = %s
                ORDER BY tc.constraint_type, kcu.column_name
            ''', (_table,))
            _constraints = cursor.fetchall()
            _lines = [f'📋 โครงสร้างตาราง `{_table}`:']
            for col in _cols:
                _null = '' if col['is_nullable'] == 'NO' else ' NULL'
                _def = f' DEFAULT {col["column_default"]}' if col['column_default'] else ''
                _len = f'({col["character_maximum_length"]})' if col.get('character_maximum_length') else ''
                _lines.append(f'  {col["column_name"]}: {col["data_type"]}{_len}{_null}{_def}')
            if _constraints:
                _lines.append('\nConstraints:')
                for con in _constraints:
                    _lines.append(f'  [{con["constraint_type"]}] {con["column_name"]} ({con["constraint_name"]})')
            return {'text': '\n'.join(_lines)}
        else:
            cursor.execute('''
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
            ''')
            _tables = [r['table_name'] for r in cursor.fetchall()]
            return {'text': f'📊 ตารางทั้งหมดใน DB ({len(_tables)} ตาราง):\n' + '\n'.join(f'  • {t}' for t in _tables)}

    elif tool == 'query_db':
        _sql = (params.get('sql') or '').strip().rstrip(';').strip()
        if not _sql:
            return {'text': 'กรุณาระบุ SQL เช่น "SELECT * FROM orders LIMIT 5"'}
        _sql_upper = _sql.upper().lstrip()
        _allowed = ('SELECT ', 'WITH ', 'SHOW ', 'EXPLAIN ')
        if not any(_sql_upper.startswith(k) for k in _allowed):
            return {'text': '⛔ อนุญาตเฉพาะ SELECT/WITH/SHOW/EXPLAIN เท่านั้น — ห้ามแก้ไขข้อมูล'}
        _danger = ['INSERT ', 'UPDATE ', 'DELETE ', 'DROP ', 'TRUNCATE ', 'ALTER ', 'CREATE ', 'GRANT ', 'REVOKE ']
        if any(d in _sql_upper for d in _danger):
            return {'text': '⛔ SQL มีคำสั่งที่อาจแก้ไขข้อมูล — ถูก block เพื่อความปลอดภัย'}
        _limit = min(50, max(1, int(params.get('limit') or 20)))
        if 'LIMIT' not in _sql_upper:
            _sql = f'{_sql} LIMIT {_limit}'
        try:
            cursor.execute(_sql)
            _rows = cursor.fetchall()
            if not _rows:
                return {'text': 'Query สำเร็จ — ไม่มีข้อมูล (0 แถว)'}
            _cols = list(_rows[0].keys()) if _rows else []
            _header = ' | '.join(_cols)
            _sep = '-' * min(len(_header), 120)
            _data = '\n'.join(' | '.join(str(r[c])[:40] for c in _cols) for r in _rows)
            return {'text': f'📊 Query Result ({len(_rows)} แถว):\n```\n{_header}\n{_sep}\n{_data}\n```'}
        except Exception as _e:
            return {'text': f'SQL Error: {str(_e)}\n\n💡 หมายเหตุ: ตาราง products ไม่มี column "category" โดยตรง — ใช้ JOIN กับ product_categories และ categories แทน หรือค้นหาจากชื่อสินค้าด้วย p.name ILIKE \'%กระโปรง%\''}

    # ─── System Status Tools ──────────────────────────────────────────────────
    elif tool == 'check_system_status':
        import os as _os, time as _time
        try:
            with open('/proc/meminfo', 'r') as _f:
                _mem = {}
                for _ln in _f:
                    _k, _v = _ln.split(':', 1)
                    _mem[_k.strip()] = int(_v.strip().split()[0])
            _mem_total = _mem.get('MemTotal', 0) // 1024
            _mem_free = (_mem.get('MemAvailable', 0)) // 1024
            _mem_used = _mem_total - _mem_free
            _mem_pct = round(_mem_used / _mem_total * 100, 1) if _mem_total else 0
        except:
            _mem_total = _mem_used = _mem_pct = 0
        try:
            with open('/proc/loadavg', 'r') as _f:
                _load1, _load5, _load15 = _f.read().split()[:3]
        except:
            _load1 = _load5 = _load15 = 'N/A'
        try:
            import shutil as _sh
            _disk = _sh.disk_usage('/')
            _disk_total = _disk.total // 1024 // 1024 // 1024
            _disk_free = _disk.free // 1024 // 1024 // 1024
            _disk_pct = round((_disk.used / _disk.total) * 100, 1)
        except:
            _disk_total = _disk_free = _disk_pct = 0
        try:
            with open('/proc/uptime', 'r') as _f:
                _up_sec = float(_f.read().split()[0])
            _up_h = int(_up_sec // 3600)
            _up_m = int((_up_sec % 3600) // 60)
            _uptime = f'{_up_h}h {_up_m}m'
        except:
            _uptime = 'N/A'
        import subprocess as _sp
        _proc = _sp.run(['pgrep', '-c', 'gunicorn'], capture_output=True, text=True)
        _gworkers = _proc.stdout.strip() or '?'
        _lines = [
            '🖥️ System Status:',
            f'  RAM: {_mem_used}MB / {_mem_total}MB ใช้ไป {_mem_pct}%',
            f'  CPU Load: {_load1} (1m) / {_load5} (5m) / {_load15} (15m)',
            f'  Disk: {_disk_free}GB free / {_disk_total}GB ({_disk_pct}% ใช้แล้ว)',
            f'  Uptime: {_uptime}',
            f'  Gunicorn workers: {_gworkers} processes',
        ]
        return {'text': '\n'.join(_lines)}

    elif tool == 'read_server_logs':
        import os as _os
        _log_path = '/tmp/app.log'
        _lines_req = min(200, max(10, int(params.get('lines') or 50)))
        _level_filter = (params.get('level') or '').upper()
        if not _os.path.isfile(_log_path):
            return {'text': f'ยังไม่มี log file ที่ {_log_path} — server ยังไม่มี error/warning บันทึก'}
        try:
            with open(_log_path, 'r', encoding='utf-8', errors='replace') as _f:
                _all = _f.readlines()
            if _level_filter in ('ERROR', 'WARNING', 'CRITICAL', 'INFO'):
                _all = [l for l in _all if _level_filter in l]
            _tail = _all[-_lines_req:]
            _content = ''.join(_tail).strip()
            if not _content:
                return {'text': f'✅ Log ว่างเปล่า — ไม่พบ{"  " + _level_filter if _level_filter else ""} ใน {_log_path}'}
            _total = len(_all)
            return {'text': f'📋 Server Log (แสดง {len(_tail)}/{_total} บรรทัด{" [" + _level_filter + "]" if _level_filter else ""}):\n```\n{_content}\n```'}
        except Exception as _e:
            return {'text': f'อ่าน log ไม่สำเร็จ: {str(_e)}'}

    elif tool == 'check_db_health':
        try:
            cursor.execute('SELECT count(*) as cnt FROM pg_stat_activity')
            _conns = cursor.fetchone()['cnt']
            cursor.execute('SELECT count(*) as cnt FROM pg_stat_activity WHERE state=%s', ('active',))
            _active = cursor.fetchone()['cnt']
            cursor.execute('''
                SELECT tablename,
                       pg_size_pretty(pg_total_relation_size('public.' || tablename)) as total_size,
                       pg_total_relation_size('public.' || tablename) as raw_size
                FROM pg_tables WHERE schemaname='public'
                ORDER BY raw_size DESC LIMIT 10
            ''')
            _sizes = cursor.fetchall()
            cursor.execute('''
                SELECT indexname, tablename, pg_size_pretty(pg_relation_size(indexname::regclass)) as idx_size
                FROM pg_indexes WHERE schemaname='public'
                ORDER BY pg_relation_size(indexname::regclass) DESC LIMIT 5
            ''')
            _idx = cursor.fetchall()
            _lines = [
                f'🗄️ DB Health:',
                f'  Connections: {_conns} total, {_active} active',
                '',
                'Top 10 ตาราง (ขนาด):',
            ]
            for r in _sizes:
                _lines.append(f'  • {r["tablename"]}: {r["total_size"]}')
            _lines.append('\nTop 5 Index:')
            for r in _idx:
                _lines.append(f'  • {r["indexname"]} ({r["tablename"]}): {r["idx_size"]}')
            return {'text': '\n'.join(_lines)}
        except Exception as _e:
            return {'text': f'ดู DB health ไม่สำเร็จ: {str(_e)}'}

    elif tool == 'list_storage_files':
        try:
            from replit.object_storage import Client as _OSC
            _osc = _OSC()
            _prefix = (params.get('prefix') or '').strip()
            _objs = _osc.list()
            _keys = [o.name for o in _objs if o.name.startswith(_prefix)]
            if not _keys:
                return {'text': f'ไม่พบไฟล์ใน Object Storage{(" ที่ขึ้นต้นด้วย " + _prefix) if _prefix else ""}'}
            _lines = [f'☁️ Object Storage ({len(_keys)} ไฟล์):']
            for k in _keys[:80]:
                _lines.append(f'  {k}')
            if len(_keys) > 80:
                _lines.append(f'  … และอีก {len(_keys)-80} ไฟล์')
            return {'text': '\n'.join(_lines)}
        except Exception as _e:
            return {'text': f'เข้าถึง Object Storage ไม่สำเร็จ: {str(_e)}'}

    elif tool == 'list_env_var_names':
        import os as _os
        _keys = sorted(_os.environ.keys())
        _app_keys = [k for k in _keys if not k.startswith('_') and k not in ('PATH', 'HOME', 'USER', 'SHELL', 'TERM', 'LANG', 'LC_ALL', 'PWD', 'OLDPWD', 'SHLVL', 'LOGNAME', 'MAIL')]
        _lines = [f'🔑 Environment Variables ({len(_app_keys)} รายการ) — แสดงชื่อเท่านั้น:']
        for k in _app_keys:
            _masked = '●●●●●●●●' if any(x in k.upper() for x in ('KEY', 'SECRET', 'PASSWORD', 'TOKEN', 'PASS')) else f'(set, len={len(_os.environ[k])})'
            _lines.append(f'  {k}: {_masked}')
        return {'text': '\n'.join(_lines)}

    elif tool == 'analyze_syntax':
        import subprocess as _sp, os as _os
        _root = '/home/runner/workspace'
        _file = (params.get('file') or 'app.py').strip().lstrip('/')
        _safe = _os.path.realpath(_os.path.join(_root, _file))
        if not _safe.startswith(_root) or not _os.path.isfile(_safe):
            return {'text': f'ไม่พบไฟล์: {_file}'}
        _res = _sp.run(['python3', '-m', 'py_compile', _safe], capture_output=True, text=True)
        if _res.returncode == 0:
            _wc = _sp.run(['wc', '-l', _safe], capture_output=True, text=True)
            _lines_count = _wc.stdout.strip().split()[0] if _wc.returncode == 0 else '?'
            return {'text': f'✅ {_file} — Syntax OK ({_lines_count} บรรทัด ไม่มี error)'}
        else:
            _err = (_res.stderr or _res.stdout or 'ไม่ทราบ error').strip()
            return {'text': f'❌ Syntax Error ใน {_file}:\n```\n{_err}\n```'}

    elif tool == 'count_code_metrics':
        import os as _os, re as _re, glob as _glob
        _root = '/home/runner/workspace'
        _target = (params.get('file') or '').strip().lstrip('/')
        if _target:
            _files = [_os.path.join(_root, _target)] if _os.path.isfile(_os.path.join(_root, _target)) else []
        else:
            _py = _glob.glob(_os.path.join(_root, '*.py'))
            _js = _glob.glob(_os.path.join(_root, 'static', 'js', '*.js'))
            _files = _py + _js
        _results = []
        _total_lines = 0
        for _fp in _files:
            try:
                with open(_fp, 'r', encoding='utf-8', errors='replace') as _f:
                    _content = _f.read()
                _lc = _content.count('\n')
                _funcs = len(_re.findall(r'^def \w+', _content, _re.MULTILINE))
                _classes = len(_re.findall(r'^class \w+', _content, _re.MULTILINE))
                _routes = len(_re.findall(r'@app\.route\(', _content))
                _fn = _fp.replace(_root + '/', '')
                _detail = f'{_lc:,} lines'
                if _funcs: _detail += f', {_funcs} fn'
                if _classes: _detail += f', {_classes} cls'
                if _routes: _detail += f', {_routes} routes'
                _results.append(f'  {_fn}: {_detail}')
                _total_lines += _lc
            except:
                pass
        if not _results:
            return {'text': 'ไม่พบไฟล์ที่จะวิเคราะห์'}
        _lines_out = [f'📊 Code Metrics ({len(_results)} ไฟล์, รวม {_total_lines:,} บรรทัด):'] + _results
        return {'text': '\n'.join(_lines_out)}

    elif tool == 'test_api_endpoint':
        import urllib.request as _ur, urllib.error as _ue, json as _js
        _path = (params.get('path') or '/api/admin/brands').strip()
        if not _path.startswith('/'):
            _path = '/' + _path
        _url = f'http://127.0.0.1:5000{_path}'
        try:
            _req = _ur.Request(_url, headers={'User-Agent': 'AgentInspector/1.0', 'X-Internal-Test': '1'})
            with _ur.urlopen(_req, timeout=8) as _resp:
                _status = _resp.status
                _body = _resp.read().decode('utf-8', errors='replace')
                try:
                    _parsed = _js.loads(_body)
                    if isinstance(_parsed, list):
                        _preview = f'Array [{len(_parsed)} items]\nตัวอย่าง: {_js.dumps(_parsed[0], ensure_ascii=False)[:200]}' if _parsed else 'Array [0 items]'
                    elif isinstance(_parsed, dict):
                        _preview = _js.dumps(_parsed, ensure_ascii=False, indent=2)[:500]
                    else:
                        _preview = str(_parsed)[:300]
                except:
                    _preview = _body[:300]
            return {'text': f'✅ GET {_path} → HTTP {_status}\n```json\n{_preview}\n```'}
        except _ue.HTTPError as _e:
            return {'text': f'⚠️ GET {_path} → HTTP {_e.code} {_e.reason}'}
        except Exception as _e:
            return {'text': f'เรียก {_path} ไม่สำเร็จ: {str(_e)}'}

    # ─── Google Workspace Tools ─────────────────────────────────────────────
    elif tool == 'read_google_sheet':
        return _agent_read_google_sheet(params)

    elif tool == 'query_google_drive':
        return _agent_query_google_drive(params)

    elif tool == 'generate_image':
        import base64 as _b64
        _prompt        = (params.get('prompt') or '').strip()
        _aspect        = (params.get('aspect_ratio') or '1:1').strip()
        if not _prompt:
            return {'text': '⚠️ กรุณาระบุ prompt สำหรับสร้างภาพ'}
        _aspect_map = {'1:1': 'IMAGE_ASPECT_RATIO_SQUARE', '16:9': 'IMAGE_ASPECT_RATIO_LANDSCAPE_16_9',
                       '9:16': 'IMAGE_ASPECT_RATIO_PORTRAIT_9_16', '4:3': 'IMAGE_ASPECT_RATIO_LANDSCAPE_4_3',
                       '3:4': 'IMAGE_ASPECT_RATIO_PORTRAIT_3_4'}
        _ar_enum = _aspect_map.get(_aspect, 'IMAGE_ASPECT_RATIO_SQUARE')
        _models_to_try = ['imagen-4.0-generate-preview-05-20', 'imagen-4.0-generate-preview-06-06',
                          'imagen-4.0-fast-generate-preview-06-05', 'imagen-4.0-fast-generate-preview-05-20',
                          'imagen-4.0-ultra-generate-preview-05-20', 'imagen-3.0-generate-002']
        _img_bytes = None
        _mime_type = 'image/png'
        _used_model = None
        _last_err = None
        try:
            from google import genai as _gai
            from google.genai import types as _gai_types
            import os as _os2
            _gclient = _gai.Client(api_key=_os2.environ.get('GEMINI_API_KEY', ''))
            for _m in _models_to_try:
                try:
                    _gen_cfg = {'number_of_images': 1, 'output_mime_type': 'image/png',
                                'aspect_ratio': _ar_enum}
                    _resp = _gclient.models.generate_images(
                        model=_m,
                        prompt=_prompt,
                        config=_gai_types.GenerateImagesConfig(**_gen_cfg)
                    )
                    if _resp.generated_images:
                        _img_bytes = _resp.generated_images[0].image.image_bytes
                        _mime_type = 'image/png'
                        _used_model = _m
                        break
                except Exception as _me:
                    _last_err = str(_me)
                    continue
        except Exception as _import_err:
            return {'text': f'❌ โหลด google-genai ไม่สำเร็จ: {_import_err}'}
        if not _img_bytes:
            return {'text': f'❌ สร้างภาพไม่สำเร็จ: {_last_err}'}
        _b64_str = _b64.b64encode(_img_bytes).decode('utf-8')
        _short_model = _used_model.split('/')[-1] if _used_model else 'Imagen'
        return {
            'text': f'🎨 สร้างภาพสำเร็จด้วย {_short_model}\n📝 Prompt: {_prompt[:80]}{"..." if len(_prompt)>80 else ""}',
            'image_b64': _b64_str,
            'mime_type': _mime_type,
            'prompt': _prompt,
            'model': _used_model
        }

    return {'text': 'ไม่รู้จัก tool นี้'}


def _agent_find_sku(params, cursor):
    name = params.get('product_name', '')
    size = params.get('size', '')
    color = params.get('color', '')
    cursor.execute('''SELECT s.id as sku_id, s.sku_code, s.stock, p.name as product_name
        FROM skus s JOIN products p ON p.id = s.product_id WHERE p.name ILIKE %s ORDER BY s.sku_code''', (f'%{name}%',))
    skus = cursor.fetchall()
    if not skus:
        return None, f'ไม่พบสินค้าที่ชื่อใกล้เคียง "{name}"'
    matched = list(skus)
    if size:
        f2 = [r for r in matched if size.upper() in r['sku_code'].upper()]
        if f2: matched = f2
    if color:
        f3 = [r for r in matched if color.upper() in r['sku_code'].upper()]
        if f3: matched = f3
    if len(matched) == 1:
        return dict(matched[0]), None
    if len(matched) > 1:
        return None, f'พบหลาย SKU: {", ".join([r["sku_code"] for r in matched[:6]])} — กรุณาระบุให้ชัดขึ้น'
    return None, f'ไม่พบ SKU ที่ตรงกับ {name}'


def _agent_log_plan(cursor, conn, admin_id, admin_name, message, tool, context_page, params, before_data):
    import json as _json
    cursor.execute('''INSERT INTO agent_action_logs
        (admin_id, admin_name, command_text, tool_name, context_page, plan_data, before_data, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'pending') RETURNING id''',
        (admin_id, admin_name, message, tool, context_page, _json.dumps(params), _json.dumps(before_data)))
    log_id = cursor.fetchone()[0]
    conn.commit()
    return log_id


@agent_bp.route('/api/admin/agent/chat', methods=['POST'])
@admin_required
def agent_chat():
    import json as _json
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        data = request.get_json()
        message     = (data.get('message') or '').strip()
        context_page = data.get('context_page', 'dashboard')
        image_data  = data.get('image_data')
        image_mime  = data.get('image_mime', 'image/jpeg')
        history     = data.get('history') or []
        if not message and not image_data:
            return jsonify({'error': 'ไม่มีข้อความ'}), 400

        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        settings = _agent_load_settings(cursor)
        biz_context = _agent_load_business_context(cursor)

        # ดึง AI response ล่าสุดจาก history มาใส่ใน context ตรงๆ เพื่อให้ Agent ไม่ต้องถามซ้ำ
        last_ai_texts = [h.get('text', '') for h in history if h.get('role') == 'model' and h.get('text')]
        if last_ai_texts:
            biz_context['last_agent_response'] = last_ai_texts[-1][:800]

        # Phase 1: Flash Lite สำหรับ READ/chat (เร็ว ประหยัด)
        intent = _agent_call_gemini(message, context_page, settings, image_data, image_mime, model='gemini-2.5-flash-lite', history=history, context=biz_context)
        itype  = intent.get('type', 'chat')
        model_used = 'Flash Lite'

        # Phase 2: ถ้าเป็น WRITE tool ให้ 3.1 Pro ตรวจสอบ params ให้รอบคอบและปลอดภัย
        if itype == 'plan':
            pro_intent = _agent_call_gemini(message, context_page, settings, image_data, image_mime, model='gemini-3.1-pro-preview', history=history, context=biz_context)
            if pro_intent.get('type') in ('plan', 'clarify'):
                intent = pro_intent
                itype  = intent.get('type', 'plan')
                model_used = '3.1 Pro'
            else:
                itype  = pro_intent.get('type', 'chat')
                intent = pro_intent
                model_used = '3.1 Pro'

        tool   = intent.get('tool', '')
        params = intent.get('params') or {}
        admin_id   = session.get('user_id')
        admin_name = session.get('full_name') or session.get('username') or 'Admin'

        _code_tools = {'read_code', 'search_code', 'list_files', 'analyze_syntax', 'count_code_metrics'}
        _workspace_tools = {'query_google_drive', 'read_google_sheet'}
        if itype == 'answer':
            result = _agent_execute_read_tool(tool, params, cursor)
            if result.get('chart'):
                return jsonify({'type': 'chart', 'message': result['text'], 'chart': result['chart'], 'model_used': model_used}), 200
            if result.get('image_b64'):
                return jsonify({'type': 'image', 'message': result['text'],
                                'image_b64': result['image_b64'], 'mime_type': result.get('mime_type', 'image/png'),
                                'prompt': result.get('prompt', ''), 'image_model': result.get('model', ''),
                                'model_used': model_used}), 200
            if tool in _code_tools:
                explanation = _agent_explain_code(message, result['text'], settings)
                return jsonify({'type': 'answer', 'message': explanation, 'model_used': model_used}), 200
            if tool in _workspace_tools:
                explanation = _agent_explain_workspace_result(message, tool, result['text'], settings)
                return jsonify({'type': 'answer', 'message': explanation, 'model_used': 'gemini-2.5-flash'}), 200
            return jsonify({'type': 'answer', 'message': result['text'], 'model_used': model_used}), 200

        elif itype == 'plan':
            if tool == 'adjust_stock':
                sku, err = _agent_find_sku(params, cursor)
                if err:
                    return jsonify({'type': 'answer', 'message': err}), 200
                qty = abs(int(params.get('quantity', 0)))
                direction = params.get('direction', 'add')
                new_stock = sku['stock'] + qty if direction == 'add' else max(0, sku['stock'] - qty)
                plan = {
                    'before': {'SKU': sku['sku_code'], 'สต็อกปัจจุบัน': f"{sku['stock']} ชิ้น"},
                    'after':  {'SKU': sku['sku_code'], 'สต็อกใหม่': f"{new_stock} ชิ้น ({'+' if direction=='add' else '-'}{qty})"}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'sku_id': sku['sku_id'], 'stock': sku['stock']})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'sku_id': sku['sku_id'], 'quantity': qty},
                                'message': intent.get('message', f"จะ{'เพิ่ม' if direction=='add' else 'ลด'}สต็อก {sku['sku_code']} → {new_stock} ชิ้น"),
                                'model_used': model_used}), 200

            elif tool == 'update_order_status':
                order_num = str(params.get('order_number', '') or params.get('order_id', ''))
                new_status = params.get('new_status', '')
                allowed_statuses = ['processing', 'shipped', 'delivered', 'cancelled']
                if new_status not in allowed_statuses:
                    return jsonify({'type': 'answer', 'message': f'สถานะ "{new_status}" ไม่ถูกต้อง ใช้ได้: {", ".join(allowed_statuses)}'}), 200
                cursor.execute('SELECT id, order_number, status, final_amount FROM orders WHERE order_number ILIKE %s OR id::text = %s', (f'%{order_num}%', order_num))
                order = cursor.fetchone()
                if not order:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบออเดอร์ {order_num}'}), 200
                sl = {'pending_payment': 'รอชำระ', 'processing': 'กำลังจัดเตรียม', 'shipped': 'จัดส่งแล้ว', 'delivered': 'ส่งถึงแล้ว', 'cancelled': 'ยกเลิก'}
                plan = {
                    'before': {'ออเดอร์': order['order_number'], 'สถานะ': sl.get(order['status'], order['status'])},
                    'after':  {'ออเดอร์': order['order_number'], 'สถานะใหม่': sl.get(new_status, new_status)}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'order_id': order['id'], 'old_status': order['status']})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'order_id': order['id']},
                                'message': intent.get('message', f"จะเปลี่ยนสถานะออเดอร์ {order['order_number']} เป็น {sl.get(new_status, new_status)}"),
                                'model_used': model_used}), 200

            elif tool == 'toggle_product':
                prod_name = params.get('product_name', '')
                active = bool(params.get('active', True))
                cursor.execute('SELECT id, name, status FROM products WHERE name ILIKE %s LIMIT 3', (f'%{prod_name}%',))
                products = cursor.fetchall()
                if not products:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบสินค้าชื่อใกล้เคียง "{prod_name}"'}), 200
                if len(products) > 1:
                    opts = ', '.join([p['name'] for p in products])
                    return jsonify({'type': 'answer', 'message': f'พบหลายสินค้า: {opts} — กรุณาระบุชื่อให้ชัดขึ้น'}), 200
                prod = products[0]
                plan = {
                    'before': {'สินค้า': prod['name'], 'สถานะ': 'เปิดขาย' if prod['status'] == 'active' else 'ปิดขาย'},
                    'after':  {'สินค้า': prod['name'], 'สถานะใหม่': 'เปิดขาย' if active else 'ปิดขาย'}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'product_id': prod['id'], 'old_status': prod['status']})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'product_id': prod['id']},
                                'message': intent.get('message', f"จะ{'เปิด' if active else 'ปิด'}การขายสินค้า {prod['name']}"),
                                'model_used': model_used}), 200

            elif tool == 'send_chat_message':
                reseller_name = params.get('reseller_name', '')
                msg_text = params.get('message', '')
                cursor.execute('''SELECT u.id, u.full_name FROM users u WHERE u.full_name ILIKE %s AND u.role_name = 'Reseller' LIMIT 3''', (f'%{reseller_name}%',))
                resellers = cursor.fetchall()
                if not resellers:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบตัวแทนชื่อ "{reseller_name}"'}), 200
                if len(resellers) > 1:
                    opts = ', '.join([r['full_name'] for r in resellers])
                    return jsonify({'type': 'answer', 'message': f'พบหลายคน: {opts} — ระบุให้ชัดขึ้น'}), 200
                reseller = resellers[0]
                plan = {
                    'before': {'ผู้รับ': reseller['full_name']},
                    'after':  {'ข้อความ': msg_text[:80]}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'reseller_id': reseller['id']})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'reseller_id': reseller['id']},
                                'message': intent.get('message', f"จะส่งข้อความหา {reseller['full_name']}: \"{msg_text[:60]}\""),
                                'model_used': model_used}), 200

            elif tool == 'save_note':
                note_key   = (params.get('key') or '').strip()
                note_value = (params.get('value') or '').strip()
                if not note_key or not note_value:
                    return jsonify({'type': 'answer', 'message': 'กรุณาระบุ key และ value สำหรับสมุดโน้ต'}), 200
                cursor.execute('SELECT note_value FROM agent_notes WHERE note_key = %s', (note_key,))
                existing = cursor.fetchone()
                plan = {
                    'before': {'หัวข้อ': note_key, 'ค่าเดิม': existing['note_value'] if existing else '(ใหม่)'},
                    'after':  {'หัวข้อ': note_key, 'ค่าใหม่': note_value}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'key': note_key, 'value': note_value})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {'key': note_key, 'value': note_value},
                                'message': intent.get('message', f"จะบันทึกลงสมุดโน้ต: **{note_key}** = {note_value[:60]}"),
                                'model_used': model_used}), 200

            elif tool == 'update_product_description':
                prod_name = (params.get('product_name') or '').strip()
                new_desc  = (params.get('description') or '').strip()
                db_field  = params.get('field', 'bot_description')
                if db_field not in ('description', 'bot_description'):
                    db_field = 'bot_description'
                if not prod_name or not new_desc:
                    return jsonify({'type': 'answer', 'message': 'กรุณาระบุ product_name และ description'}), 200
                cursor.execute(f"SELECT id, name, description, bot_description FROM products WHERE name ILIKE %s AND status='active' LIMIT 3", (f'%{prod_name}%',))
                prods = cursor.fetchall()
                if not prods:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบสินค้าชื่อ "{prod_name}"'}), 200
                if len(prods) > 1:
                    opts = ', '.join([p['name'] for p in prods])
                    return jsonify({'type': 'answer', 'message': f'พบหลายสินค้า: {opts} — ระบุให้ชัดขึ้น'}), 200
                prod = prods[0]
                field_label = 'คำอธิบายบอท (bot_description)' if db_field == 'bot_description' else 'คำอธิบายสาธารณะ (description)'
                plan = {
                    'before': {'สินค้า': prod['name'], f'{field_label} เดิม': (prod[db_field] or '')[:100] or '(ว่าง)'},
                    'after':  {'สินค้า': prod['name'], f'{field_label} ใหม่': new_desc[:100]}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'product_id': prod['id'], 'old_desc': prod[db_field], 'db_field': db_field})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'product_id': prod['id'], 'db_field': db_field},
                                'message': intent.get('message', f"จะอัปเดต {field_label} ของ **{prod['name']}**"),
                                'model_used': model_used}), 200

            elif tool == 'bulk_update_product_description':
                keyword  = (params.get('keyword') or '').strip()
                new_desc = (params.get('description') or '').strip()
                db_field = params.get('field', 'bot_description')
                if db_field not in ('description', 'bot_description'):
                    db_field = 'bot_description'
                if not keyword or not new_desc:
                    return jsonify({'type': 'answer', 'message': 'กรุณาระบุ keyword และ description'}), 200
                cursor.execute("SELECT id, name FROM products WHERE name ILIKE %s AND status='active' ORDER BY name", (f'%{keyword}%',))
                prods = cursor.fetchall()
                if not prods:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบสินค้าที่ชื่อมีคำว่า "{keyword}"'}), 200
                prod_ids = [p['id'] for p in prods]
                prod_names = [p['name'] for p in prods]
                field_label = 'คำอธิบายบอท' if db_field == 'bot_description' else 'คำอธิบายสาธารณะ'
                plan = {
                    'before': {'สินค้าที่จะอัปเดต': f'{len(prods)} รายการ: ' + ', '.join(prod_names[:5]) + (f' ... และอีก {len(prods)-5} รายการ' if len(prods) > 5 else '')},
                    'after':  {f'{field_label} ใหม่ (ทุกรายการ)': new_desc[:120]}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'product_ids': prod_ids, 'count': len(prods), 'db_field': db_field})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'product_ids': prod_ids, 'db_field': db_field},
                                'message': intent.get('message', f"จะอัปเดต{field_label}ของสินค้าที่มีคำว่า **{keyword}** จำนวน {len(prods)} รายการ"),
                                'model_used': model_used}), 200

            elif tool == 'update_product_field':
                prod_name  = (params.get('product_name') or '').strip()
                db_field   = (params.get('field') or '').strip()
                new_value  = params.get('value')
                allowed_fields = {
                    'is_featured':        ('boolean', 'สินค้าแนะนำ (is_featured)'),
                    'low_stock_threshold':('integer', 'ขีดแจ้งเตือนสต็อกต่ำ'),
                    'weight':             ('numeric', 'น้ำหนัก (kg)'),
                    'length':             ('numeric', 'ความยาว (cm)'),
                    'width':              ('numeric', 'ความกว้าง (cm)'),
                    'height':             ('numeric', 'ความสูง (cm)'),
                    'name':               ('text',    'ชื่อสินค้า'),
                    'production_days':    ('integer', 'จำนวนวันผลิต'),
                    'deposit_percent':    ('integer', 'มัดจำ (%)'),
                }
                if db_field not in allowed_fields:
                    opts = ', '.join(allowed_fields.keys())
                    return jsonify({'type': 'answer', 'message': f'field ที่รองรับ: {opts}'}), 200
                if not prod_name or new_value is None:
                    return jsonify({'type': 'answer', 'message': 'กรุณาระบุ product_name, field และ value'}), 200
                cursor.execute("SELECT id, name FROM products WHERE name ILIKE %s AND status='active' LIMIT 3", (f'%{prod_name}%',))
                prods = cursor.fetchall()
                if not prods:
                    return jsonify({'type': 'answer', 'message': f'ไม่พบสินค้าชื่อ "{prod_name}"'}), 200
                if len(prods) > 1:
                    opts = ', '.join([p['name'] for p in prods])
                    return jsonify({'type': 'answer', 'message': f'พบหลายสินค้า: {opts} — ระบุให้ชัดขึ้น'}), 200
                prod = prods[0]
                field_label = allowed_fields[db_field][1]
                cursor.execute(f'SELECT {db_field} FROM products WHERE id=%s', (prod['id'],))
                old_row = cursor.fetchone()
                old_val = old_row[db_field] if old_row else None
                plan = {
                    'before': {'สินค้า': prod['name'], field_label: str(old_val)},
                    'after':  {'สินค้า': prod['name'], field_label: str(new_value)}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'product_id': prod['id'], 'old_val': old_val, 'db_field': db_field})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {**params, 'product_id': prod['id'], 'db_field': db_field},
                                'message': intent.get('message', f"จะแก้ไข {field_label} ของ **{prod['name']}** เป็น {new_value}"),
                                'model_used': model_used}), 200

            elif tool == 'toggle_facebook_ad':
                import urllib.request as _ur2
                import urllib.parse as _up2
                import urllib.error as _ue2
                ad_id  = str(params.get('ad_id', '')).strip()
                status = str(params.get('status', 'PAUSED')).upper().strip()
                allowed_statuses = ['ACTIVE', 'PAUSED', 'ARCHIVED', 'DELETED']
                if not ad_id:
                    return jsonify({'type': 'answer', 'message': 'กรุณาระบุ ad_id (Campaign ID / AdSet ID / Ad ID)'}), 200
                if status not in allowed_statuses:
                    return jsonify({'type': 'answer', 'message': f'status "{status}" ไม่ถูกต้อง ใช้ได้: {", ".join(allowed_statuses)}'}), 200
                # Get Meta credentials
                try:
                    _mc2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                    _tok2, _acc2 = _get_meta_credentials(_mc2)
                    _mc2.close()
                except Exception as _ce2:
                    return jsonify({'type': 'answer', 'message': f'ไม่สามารถอ่าน Meta credentials: {_ce2}'}), 200
                if not _tok2:
                    return jsonify({'type': 'answer', 'message': '⚠️ ยังไม่ได้ตั้งค่า Meta Access Token — ไปที่หน้า Facebook Ads เพื่อตั้งค่า'}), 200
                # Fetch current ad info from Meta API
                try:
                    _fq = _up2.urlencode({'fields': 'name,status,effective_status,objective', 'access_token': _tok2})
                    _fr = _ur2.Request(f'https://graph.facebook.com/v19.0/{ad_id}?{_fq}', headers={'User-Agent': 'EKGShops/1.0'})
                    with _ur2.urlopen(_fr, timeout=10) as _fresp:
                        _fdata = json.loads(_fresp.read().decode())
                    ad_name       = _fdata.get('name', ad_id)
                    current_status = _fdata.get('status', 'UNKNOWN')
                    effective_status = _fdata.get('effective_status', current_status)
                except _ue2.HTTPError as _fhe:
                    try:
                        _ferr = json.loads(_fhe.read().decode()).get('error', {}).get('message', str(_fhe))
                    except Exception:
                        _ferr = str(_fhe)
                    return jsonify({'type': 'answer', 'message': f'❌ Meta API ไม่พบ ad_id "{ad_id}": {_ferr}'}), 200
                except Exception as _fe:
                    return jsonify({'type': 'answer', 'message': f'ไม่สามารถดึงข้อมูลโฆษณา: {_fe}'}), 200
                # Build plan for approval
                status_th = {'ACTIVE': '▶️ เปิดอยู่', 'PAUSED': '⏸ หยุดชั่วคราว', 'ARCHIVED': '📦 เก็บถาวร', 'DELETED': '🗑 ลบแล้ว'}
                plan = {
                    'before': {'ID': ad_id, 'ชื่อ': ad_name, 'สถานะปัจจุบัน': status_th.get(current_status, current_status)},
                    'after':  {'ID': ad_id, 'ชื่อ': ad_name, 'สถานะใหม่': status_th.get(status, status),
                               '⚠️ หมายเหตุ': 'คำสั่งนี้จะส่ง POST จริงไปยัง Meta Marketing API'}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'ad_id': ad_id, 'old_status': current_status, 'ad_name': ad_name})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': {'ad_id': ad_id, 'status': status, 'ad_name': ad_name},
                                'message': intent.get('message', f"จะเปลี่ยนสถานะโฆษณา **{ad_name}** → {status_th.get(status, status)}"),
                                'model_used': model_used}), 200

            elif tool == 'write_google_sheet':
                sheet_id = (params.get('spreadsheet_id') or '').strip()
                range_   = (params.get('range') or 'Sheet1!A1').strip()
                values   = params.get('values', [])
                mode     = (params.get('mode') or 'append').lower()
                if not sheet_id:
                    return jsonify({'type': 'answer', 'message': '⚠️ กรุณาระบุ spreadsheet_id'}), 200
                if not values:
                    return jsonify({'type': 'answer', 'message': '⚠️ กรุณาระบุ values'}), 200
                rows_preview = str(values[:3])[:120] + ('...' if len(str(values)) > 120 else '')
                plan = {
                    'before': {'Spreadsheet ID': sheet_id, 'Range': range_},
                    'after':  {'Mode': mode, 'จำนวนแถว': len(values), 'ตัวอย่าง': rows_preview}
                }
                log_id = _agent_log_plan(conn.cursor(), conn, admin_id, admin_name, message, tool, context_page,
                                          params, {'spreadsheet_id': sheet_id, 'range': range_})
                return jsonify({'type': 'plan', 'tool': tool, 'log_id': log_id, 'plan': plan,
                                'params': params,
                                'message': intent.get('message', f"จะเขียน {len(values)} แถว ลง Google Sheet `{range_}` (mode: {mode})"),
                                'model_used': model_used}), 200

            return jsonify({'type': 'answer', 'message': f'tool "{tool}" ยังไม่รองรับ'}), 200

        elif itype == 'clarify':
            return jsonify({'type': 'answer', 'message': intent.get('message', '')}), 200
        else:
            return jsonify({'type': 'answer', 'message': intent.get('message', '')}), 200

    except Exception as e:
        import traceback; traceback.print_exc()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@agent_bp.route('/api/admin/agent/execute', methods=['POST'])
@admin_required
def agent_execute():
    import json as _json
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        data   = request.get_json()
        log_id = data.get('log_id')
        tool   = data.get('tool')
        params = data.get('params') or {}
        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        admin_id = session.get('user_id')
        admin_name = session.get('full_name') or session.get('username') or 'Admin'

        if tool == 'adjust_stock':
            sku_id    = int(params.get('sku_id', 0))
            qty       = abs(int(params.get('quantity', 0)))
            direction = params.get('direction', 'add')
            cursor.execute('SELECT s.id, s.sku_code, s.stock, p.name FROM skus s JOIN products p ON p.id = s.product_id WHERE s.id = %s', (sku_id,))
            sku = cursor.fetchone()
            if not sku: return jsonify({'error': 'ไม่พบ SKU'}), 404
            before_stock = sku['stock']
            new_stock = before_stock + qty if direction == 'add' else max(0, before_stock - qty)
            cur2 = conn.cursor()
            cur2.execute('UPDATE skus SET stock = %s WHERE id = %s', (new_stock, sku_id))
            cur2.execute('INSERT INTO sku_warehouse_stock (sku_id, warehouse_id, stock) VALUES (%s, 2, %s) ON CONFLICT (sku_id, warehouse_id) DO UPDATE SET stock = %s', (sku_id, new_stock, new_stock))
            before_data = {'SKU': sku['sku_code'], 'สต็อกก่อน': f"{before_stock} ชิ้น"}
            after_data  = {'SKU': sku['sku_code'], 'สต็อกหลัง': f"{new_stock} ชิ้น"}
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"{'เพิ่ม' if direction=='add' else 'ลด'}สต็อก {sku['sku_code']} ({before_stock} → {new_stock} ชิ้น)",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'update_order_status':
            order_id   = int(params.get('order_id', 0))
            new_status = params.get('new_status', '')
            cursor.execute('SELECT id, order_number, status FROM orders WHERE id = %s', (order_id,))
            order = cursor.fetchone()
            if not order: return jsonify({'error': 'ไม่พบออเดอร์'}), 404
            old_status = order['status']
            sl = {'pending_payment': 'รอชำระ', 'processing': 'กำลังจัดเตรียม', 'shipped': 'จัดส่งแล้ว', 'delivered': 'ส่งถึงแล้ว', 'cancelled': 'ยกเลิก'}
            cur2 = conn.cursor()
            cur2.execute('UPDATE orders SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (new_status, order_id))
            before_data = {'ออเดอร์': order['order_number'], 'สถานะเดิม': sl.get(old_status, old_status)}
            after_data  = {'ออเดอร์': order['order_number'], 'สถานะใหม่': sl.get(new_status, new_status)}
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"เปลี่ยนสถานะออเดอร์ {order['order_number']} → {sl.get(new_status, new_status)} สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'toggle_product':
            product_id = int(params.get('product_id', 0))
            active     = bool(params.get('active', True))
            cursor.execute('SELECT id, name, status FROM products WHERE id = %s', (product_id,))
            prod = cursor.fetchone()
            if not prod: return jsonify({'error': 'ไม่พบสินค้า'}), 404
            cur2 = conn.cursor()
            new_status_val = 'active' if active else 'inactive'
            cur2.execute('UPDATE products SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (new_status_val, product_id))
            before_data = {'สินค้า': prod['name'], 'สถานะเดิม': 'เปิดขาย' if prod['status'] == 'active' else 'ปิดขาย'}
            after_data  = {'สินค้า': prod['name'], 'สถานะใหม่': 'เปิดขาย' if active else 'ปิดขาย'}
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"{'เปิด' if active else 'ปิด'}การขาย {prod['name']} สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'send_chat_message':
            reseller_id = int(params.get('reseller_id', 0))
            msg_text    = params.get('message', '')
            cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
            thread = cursor.fetchone()
            cur2 = conn.cursor()
            if not thread:
                cur2.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (reseller_id,))
                thread_id = cur2.fetchone()[0]
            else:
                thread_id = thread['id']
            cur2.execute('INSERT INTO chat_messages (thread_id, sender_id, sender_type, content) VALUES (%s, %s, %s, %s)',
                         (thread_id, admin_id, 'admin', msg_text))
            cur2.execute('UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s, is_archived = FALSE WHERE id = %s',
                         (msg_text[:100], thread_id))
            cursor.execute('SELECT full_name FROM users WHERE id = %s', (reseller_id,))
            reseller = cursor.fetchone()
            before_data = {'ผู้รับ': reseller['full_name'] if reseller else '-'}
            after_data  = {'ข้อความ': msg_text[:80]}
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"ส่งข้อความหา {reseller['full_name'] if reseller else 'ตัวแทน'} สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'save_note':
            note_key   = (params.get('key') or '').strip()
            note_value = (params.get('value') or '').strip()
            cursor.execute('SELECT note_value FROM agent_notes WHERE note_key = %s', (note_key,))
            existing = cursor.fetchone()
            cur2 = conn.cursor()
            cur2.execute('''INSERT INTO agent_notes (note_key, note_value, created_by, updated_at)
                            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (note_key) DO UPDATE SET note_value=%s, updated_at=CURRENT_TIMESTAMP, created_by=%s''',
                         (note_key, note_value, admin_name, note_value, admin_name))
            before_data = {'หัวข้อ': note_key, 'ค่าเดิม': existing['note_value'] if existing else '(ใหม่)'}
            after_data  = {'หัวข้อ': note_key, 'ค่าใหม่': note_value}
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"📝 บันทึกสมุดโน้ตสำเร็จ: **{note_key}**",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'update_product_description':
            product_id = params.get('product_id')
            new_desc   = (params.get('description') or '').strip()
            db_field   = params.get('db_field', params.get('field', 'bot_description'))
            if db_field not in ('description', 'bot_description'):
                db_field = 'bot_description'
            if not product_id or not new_desc:
                return jsonify({'message': 'ข้อมูลไม่ครบ — ต้องการ product_id และ description'}), 200
            cursor.execute(f'SELECT id, name, {db_field} as cur_val FROM products WHERE id = %s', (product_id,))
            prod = cursor.fetchone()
            if not prod:
                return jsonify({'message': f'ไม่พบสินค้า ID {product_id}'}), 200
            old_val = prod['cur_val'] or ''
            field_label = 'คำอธิบายบอท' if db_field == 'bot_description' else 'คำอธิบายสาธารณะ'
            cursor.execute(f'UPDATE products SET {db_field} = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (new_desc, product_id))
            before_data = {'สินค้า': prod['name'], f'{field_label} เดิม': old_val[:120] or '(ว่าง)'}
            after_data  = {'สินค้า': prod['name'], f'{field_label} ใหม่': new_desc[:120]}
            if log_id:
                cursor.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                               ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"✅ อัปเดต{field_label}ของ **{prod['name']}** สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'bulk_update_product_description':
            product_ids = params.get('product_ids', [])
            new_desc    = (params.get('description') or '').strip()
            keyword     = (params.get('keyword') or '').strip()
            db_field    = params.get('db_field', params.get('field', 'bot_description'))
            if db_field not in ('description', 'bot_description'):
                db_field = 'bot_description'
            if not product_ids or not new_desc:
                return jsonify({'message': 'ข้อมูลไม่ครบ — ต้องการ product_ids และ description'}), 200
            cursor.execute('SELECT id, name FROM products WHERE id = ANY(%s)', (product_ids,))
            prods = cursor.fetchall()
            if not prods:
                return jsonify({'message': 'ไม่พบสินค้าที่ระบุ'}), 200
            cursor.execute(f'UPDATE products SET {db_field} = %s, updated_at = CURRENT_TIMESTAMP WHERE id = ANY(%s)', (new_desc, product_ids))
            updated_count = cursor.rowcount
            prod_names = [p['name'] for p in prods]
            field_label = 'คำอธิบายบอท' if db_field == 'bot_description' else 'คำอธิบายสาธารณะ'
            before_data = {'จำนวนสินค้า': f'{len(prods)} รายการ', 'keyword': keyword}
            after_data  = {'อัปเดตสำเร็จ': f'{updated_count} รายการ', f'{field_label} ใหม่': new_desc[:100],
                           'สินค้า': ', '.join(prod_names[:5]) + (f' ... +{len(prod_names)-5}' if len(prod_names) > 5 else '')}
            if log_id:
                cursor.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                               ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"✅ อัปเดต{field_label}สำเร็จ **{updated_count} สินค้า** (keyword: {keyword})",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'update_product_field':
            product_id = params.get('product_id')
            db_field   = (params.get('db_field') or params.get('field') or '').strip()
            new_value  = params.get('value')
            allowed_fields = {
                'is_featured':         ('boolean', 'สินค้าแนะนำ'),
                'low_stock_threshold': ('integer', 'ขีดแจ้งเตือนสต็อกต่ำ'),
                'weight':              ('numeric', 'น้ำหนัก (kg)'),
                'length':              ('numeric', 'ความยาว (cm)'),
                'width':               ('numeric', 'ความกว้าง (cm)'),
                'height':              ('numeric', 'ความสูง (cm)'),
                'name':                ('text',    'ชื่อสินค้า'),
                'production_days':     ('integer', 'จำนวนวันผลิต'),
                'deposit_percent':     ('integer', 'มัดจำ (%)'),
            }
            if db_field not in allowed_fields or not product_id or new_value is None:
                return jsonify({'message': 'ข้อมูลไม่ครบหรือ field ไม่รองรับ'}), 200
            dtype, field_label = allowed_fields[db_field]
            if dtype == 'boolean':
                typed_val = str(new_value).lower() in ('true', '1', 'yes')
            elif dtype == 'integer':
                typed_val = int(new_value)
            elif dtype == 'numeric':
                typed_val = float(new_value)
            else:
                typed_val = str(new_value)
            cursor.execute(f'SELECT id, name, {db_field} as cur_val FROM products WHERE id = %s', (product_id,))
            prod = cursor.fetchone()
            if not prod:
                return jsonify({'message': f'ไม่พบสินค้า ID {product_id}'}), 200
            old_val = prod['cur_val']
            cursor.execute(f'UPDATE products SET {db_field} = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (typed_val, product_id))
            before_data = {'สินค้า': prod['name'], f'{field_label} เดิม': str(old_val)}
            after_data  = {'สินค้า': prod['name'], f'{field_label} ใหม่': str(typed_val)}
            if log_id:
                cursor.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                               ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"✅ อัปเดต{field_label}ของ **{prod['name']}** สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'toggle_facebook_ad':
            import urllib.request as _ur3
            import urllib.parse as _up3
            import urllib.error as _ue3
            ad_id  = str(params.get('ad_id', '')).strip()
            status = str(params.get('status', 'PAUSED')).upper().strip()
            ad_name = params.get('ad_name', ad_id)
            if not ad_id:
                return jsonify({'error': 'ขาด ad_id'}), 400
            # Get Meta credentials
            try:
                _mc3 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                _tok3, _ = _get_meta_credentials(_mc3)
                _mc3.close()
            except Exception as _ce3:
                return jsonify({'error': f'ไม่สามารถอ่าน Meta credentials: {_ce3}'}), 500
            if not _tok3:
                return jsonify({'error': 'ยังไม่ได้ตั้งค่า Meta Access Token'}), 400
            # POST to Meta Marketing API to update status
            status_th = {'ACTIVE': '▶️ เปิดอยู่', 'PAUSED': '⏸ หยุดชั่วคราว', 'ARCHIVED': '📦 เก็บถาวร', 'DELETED': '🗑 ลบแล้ว'}
            try:
                _post_body = _up3.urlencode({'status': status, 'access_token': _tok3}).encode('utf-8')
                _post_req = _ur3.Request(
                    f'https://graph.facebook.com/v19.0/{ad_id}',
                    data=_post_body,
                    headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'EKGShops/1.0'},
                    method='POST'
                )
                with _ur3.urlopen(_post_req, timeout=15) as _post_resp:
                    _post_data = json.loads(_post_resp.read().decode())
                success = _post_data.get('success', False)
                if not success:
                    return jsonify({'error': f'Meta API ตอบกลับว่าไม่สำเร็จ: {_post_data}'}), 400
            except _ue3.HTTPError as _phe:
                try:
                    _perr = json.loads(_phe.read().decode()).get('error', {}).get('message', str(_phe))
                except Exception:
                    _perr = str(_phe)
                if log_id:
                    cur2 = conn.cursor()
                    cur2.execute('UPDATE agent_action_logs SET status=%s WHERE id=%s', ('failed', log_id))
                    conn.commit()
                return jsonify({'error': f'Meta API Error: {_perr}'}), 400
            except Exception as _pe:
                return jsonify({'error': f'ไม่สามารถส่ง POST ไป Meta ได้: {_pe}'}), 500
            # Log success
            before_data = {'ID': ad_id, 'ชื่อ': ad_name, 'สถานะเดิม': '(ก่อนเปลี่ยน)'}
            after_data  = {'ID': ad_id, 'ชื่อ': ad_name, 'สถานะใหม่': status_th.get(status, status)}
            cur2 = conn.cursor()
            if log_id:
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
            conn.commit()
            return jsonify({'message': f"✅ เปลี่ยนสถานะโฆษณา **{ad_name}** (ID: {ad_id}) → {status_th.get(status, status)} สำเร็จ",
                            'before': before_data, 'after': after_data}), 200

        elif tool == 'write_google_sheet':
            result = _agent_write_google_sheet(params)
            before_data = {'Spreadsheet': params.get('spreadsheet_id', ''), 'Range': params.get('range', '')}
            after_data  = {'Mode': params.get('mode', 'append'), 'แถวที่เขียน': len(params.get('values', []))}
            if log_id:
                cur2 = conn.cursor()
                cur2.execute('UPDATE agent_action_logs SET status=%s, before_data=%s, after_data=%s, executed_at=CURRENT_TIMESTAMP WHERE id=%s',
                             ('executed', _json.dumps(before_data), _json.dumps(after_data), log_id))
                conn.commit()
            return jsonify({'message': result['text'], 'before': before_data, 'after': after_data}), 200

        return jsonify({'error': f'ไม่รองรับ tool "{tool}"'}), 400

    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@agent_bp.route('/api/admin/agent/briefing', methods=['GET'])
@admin_required
def agent_briefing():
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT COUNT(*) as cnt FROM orders WHERE status IN ('pending_payment','processing') AND is_quick_order = FALSE")
        pending_orders = int(cursor.fetchone()['cnt'])
        cursor.execute("SELECT COUNT(*) as cnt FROM skus s JOIN products p ON p.id = s.product_id WHERE s.stock <= 5 AND s.stock >= 0 AND p.status = 'active'")
        low_stock = int(cursor.fetchone()['cnt'])
        cursor.execute("""SELECT COUNT(*) as cnt FROM chat_threads ct
            WHERE ct.is_archived = FALSE AND (ct.needs_admin = TRUE
              OR ct.last_message_at >= NOW() - INTERVAL '24 hours')""")
        unread_chat = int(cursor.fetchone()['cnt'])
        cursor.execute("SELECT COUNT(*) as cnt FROM mto_orders WHERE status NOT IN ('delivered','cancelled')")
        mto_pending = int(cursor.fetchone()['cnt'])
        cursor.execute("SELECT COUNT(*) as cnt,COALESCE(SUM(final_amount),0) as total FROM orders WHERE status NOT IN ('cancelled','returned','stock_restored') AND DATE(created_at) = CURRENT_DATE AND is_quick_order = FALSE")
        sales_today = cursor.fetchone()
        alerts = []
        if pending_orders > 0:
            alerts.append(f"📋 ออเดอร์รอดำเนินการ {pending_orders} รายการ")
        if low_stock > 0:
            alerts.append(f"⚠️ สินค้าสต็อกต่ำ {low_stock} รายการ")
        if unread_chat > 0:
            alerts.append(f"💬 แชทรอตอบ {unread_chat} ห้อง")
        if mto_pending > 0:
            alerts.append(f"🏭 MTO ค้างอยู่ {mto_pending} ออเดอร์")
        return jsonify({
            'pending_orders': pending_orders, 'low_stock': low_stock,
            'unread_chat': unread_chat, 'mto_pending': mto_pending,
            'sales_today_count': int(sales_today['cnt']),
            'sales_today_total': float(sales_today['total']),
            'alerts': alerts
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@agent_bp.route('/api/admin/agent/settings', methods=['GET', 'PUT'])
@admin_required
def agent_settings_api():
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'GET':
            settings = _agent_load_settings(cursor)
            return jsonify(settings), 200
        data = request.get_json()
        cursor.execute('''UPDATE agent_settings SET agent_name=%s, tone=%s, ending_particle=%s, custom_prompt=%s, updated_at=CURRENT_TIMESTAMP WHERE id=1''',
                       (data.get('agent_name', 'น้องเอก'), data.get('tone', 'friendly'),
                        data.get('ending_particle', 'ครับ'), data.get('custom_prompt', '')))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@agent_bp.route('/api/admin/agent/feedback', methods=['POST'])
@admin_required
def agent_feedback_api():
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor()
        data   = request.get_json()
        cursor.execute('INSERT INTO agent_feedback (command_text, response_text, rating, correction, context_page) VALUES (%s,%s,%s,%s,%s)',
                       (data.get('command_text'), data.get('response_text'), int(data.get('rating', 1)),
                        data.get('correction'), data.get('context_page')))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@agent_bp.route('/api/admin/agent/logs', methods=['GET'])
@admin_required
def agent_logs():
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, admin_name, command_text, tool_name, context_page, before_data, after_data, status, executed_at, created_at FROM agent_action_logs ORDER BY created_at DESC LIMIT 50')
        logs = [dict(r) for r in cursor.fetchall()]
        return jsonify(logs), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@agent_bp.route('/api/admin/agent/notes', methods=['GET', 'POST', 'DELETE'])
@admin_required
def agent_notes_api():
    if not _agent_superadmin_required():
        return jsonify({'error': 'สำหรับ Superadmin เท่านั้น'}), 403
    conn = None
    cursor = None
    try:
        conn   = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'GET':
            cursor.execute('SELECT id, note_key, note_value, created_by, updated_at FROM agent_notes ORDER BY updated_at DESC')
            return jsonify([dict(r) for r in cursor.fetchall()])
        elif request.method == 'POST':
            data = request.get_json()
            key = (data.get('key') or '').strip()
            value = (data.get('value') or '').strip()
            if not key or not value:
                return jsonify({'error': 'ต้องระบุ key และ value'}), 400
            admin_name = session.get('full_name') or session.get('username') or 'Admin'
            cursor.execute('''INSERT INTO agent_notes (note_key, note_value, created_by, updated_at)
                              VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                              ON CONFLICT (note_key) DO UPDATE SET note_value=%s, updated_at=CURRENT_TIMESTAMP, created_by=%s
                              RETURNING *''',
                           (key, value, admin_name, value, admin_name))
            conn.commit()
            return jsonify(dict(cursor.fetchone())), 200
        elif request.method == 'DELETE':
            data = request.get_json()
            key = (data.get('key') or '').strip()
            if not key:
                return jsonify({'error': 'ต้องระบุ key'}), 400
            cursor.execute('DELETE FROM agent_notes WHERE note_key = %s', (key,))
            conn.commit()
            return jsonify({'ok': True})
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
