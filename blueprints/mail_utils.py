import os, json, smtplib, threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import session, request
from database import get_db
from blueprints.push_utils import send_push_notification
import psycopg2.extras
import psycopg2

def send_email(to_email, subject, html_content):
    """Send email using Gmail SMTP"""
    try:
        gmail_user = os.environ.get('SENDER_EMAIL', 'cmidcoteam@gmail.com')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if not gmail_password:
            print("GMAIL_APP_PASSWORD not set")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"ระบบสมาชิก <{gmail_user}>"
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_order_notification_to_admin(order_number, reseller_name, total_amount, item_count):
    """Send email notification to admin when new order is created"""
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8b5cf6;">📦 คำสั่งซื้อใหม่</h2>
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <p><strong>หมายเลขคำสั่งซื้อ:</strong> {order_number}</p>
            <p><strong>สมาชิก:</strong> {reseller_name}</p>
            <p><strong>จำนวนรายการ:</strong> {item_count} รายการ</p>
            <p><strong>ยอดรวม:</strong> ฿{total_amount:,.2f}</p>
        </div>
        <p>กรุณาเข้าสู่ระบบเพื่อตรวจสอบคำสั่งซื้อ</p>
    </div>
    '''
    send_email(os.environ.get('SENDER_EMAIL', 'cmidcoteam@gmail.com'), f'[คำสั่งซื้อใหม่] {order_number} - {reseller_name}', html)

def send_order_status_email(to_email, reseller_name, order_number, status, message, extra_info=''):
    """Send order status update email to reseller"""
    status_colors = {
        'approved': '#22c55e',
        'request_new_slip': '#f59e0b',
        'shipped': '#3b82f6',
        'delivered': '#10b981',
        'cancelled': '#ef4444'
    }
    status_labels = {
        'approved': '✅ สลิปได้รับการยืนยัน',
        'request_new_slip': '⚠️ กรุณาอัปโหลดสลิปใหม่',
        'shipped': '🚚 จัดส่งสินค้าแล้ว',
        'delivered': '📦 ส่งถึงปลายทางแล้ว',
        'cancelled': '❌ คำสั่งซื้อถูกยกเลิก'
    }
    color = status_colors.get(status, '#6b7280')
    label = status_labels.get(status, 'อัปเดตสถานะ')
    
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: {color};">{label}</h2>
        <p>สวัสดี คุณ{reseller_name}</p>
        <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <p><strong>หมายเลขคำสั่งซื้อ:</strong> {order_number}</p>
            <p>{message}</p>
            {f'<p>{extra_info}</p>' if extra_info else ''}
        </div>
        <p>หากมีข้อสงสัย สามารถติดต่อได้ที่ Line: @cmidco</p>
        <p style="color: #666; margin-top: 20px;">ขอบคุณที่ใช้บริการ</p>
    </div>
    '''
    subject = f'[{label}] คำสั่งซื้อ {order_number}'
    send_email(to_email, subject, html)

def send_order_status_chat(reseller_id, order_number, status, extra_info='', order_id=None):
    """Send order status update as chat message"""
    status_messages = {
        'slip_uploaded': f'🧾 คำสั่งซื้อ {order_number} ส่งสลิปแล้ว รอตรวจสอบ',
        'approved': f'✅ คำสั่งซื้อ {order_number} สลิปได้รับการยืนยันแล้ว กำลังเตรียมจัดส่ง',
        'request_new_slip': f'⚠️ คำสั่งซื้อ {order_number} กรุณาส่งสลิปใหม่',
        'shipped': f'🚚 คำสั่งซื้อ {order_number} จัดส่งแล้ว',
        'delivered': f'📦 คำสั่งซื้อ {order_number} ส่งถึงปลายทางแล้ว',
        'cancelled': f'❌ คำสั่งซื้อ {order_number} ถูกยกเลิก',
        'shipping_issue': f'⚠️ คำสั่งซื้อ {order_number} มีปัญหาการจัดส่ง',
        'failed_delivery': f'❌ คำสั่งซื้อ {order_number} จัดส่งไม่สำเร็จ',
        'reship': f'🔄 คำสั่งซื้อ {order_number} กำลังจัดส่งใหม่',
        'refunded': f'💸 คำสั่งซื้อ {order_number} คืนเงินสำเร็จแล้ว',
        'pending_payment_reminder': f'🛒 คำสั่งซื้อ {order_number} สร้างเรียบร้อยแล้ว!\n⏰ กรุณาชำระเงินและส่งสลิปภายใน 24 ชั่วโมง มิฉะนั้นระบบจะยกเลิกอัตโนมัติและคืนสินค้าเข้าสต็อก',
        'auto_cancelled': f'🚫 คำสั่งซื้อ {order_number} ถูกยกเลิกอัตโนมัติ เนื่องจากไม่ได้รับการชำระเงินภายใน 24 ชั่วโมง สต็อกสินค้าได้รับการคืนเรียบร้อยแล้ว หากต้องการสั่งซื้ออีกครั้ง กรุณาสร้างคำสั่งซื้อใหม่',
        'restock': '',
    }
    message = status_messages.get(status, f'📋 คำสั่งซื้อ {order_number} อัปเดตสถานะ: {status}')
    if extra_info:
        message = (message + '\n' + extra_info).strip() if message else extra_info
    
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id FROM chat_threads WHERE reseller_id = %s', (reseller_id,))
        thread = cursor.fetchone()
        if not thread:
            cursor.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (reseller_id,))
            thread = cursor.fetchone()
        
        thread_id = thread['id']
        
        cursor.execute("SELECT id FROM users WHERE role_id = (SELECT id FROM roles WHERE name = 'Super Admin') LIMIT 1")
        admin = cursor.fetchone()
        admin_id = admin['id'] if admin else 1
        
        cursor.execute('''
            INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, order_id)
            VALUES (%s, %s, 'admin', %s, %s) RETURNING id
        ''', (thread_id, admin_id, message, order_id))
        
        preview = message[:100]
        cursor.execute('''
            UPDATE chat_threads SET last_message_at = CURRENT_TIMESTAMP, last_message_preview = %s, is_archived = FALSE
            WHERE id = %s
        ''', (preview, thread_id))
        
        conn.commit()
        
        send_push_notification(reseller_id, '📋 อัปเดตคำสั่งซื้อ', message[:100], url='/reseller#chat', tag=f'order-status-{order_number}')
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"[CHAT] Error sending order status chat: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

def send_low_stock_alert(admin_email, products):
    """Send email alert for low stock products"""
    items_html = ''
    for p in products:
        items_html += f'<tr><td style="padding: 8px; border-bottom: 1px solid #eee;">{p["name"]}</td><td style="padding: 8px; border-bottom: 1px solid #eee;">{p["sku_code"]}</td><td style="padding: 8px; border-bottom: 1px solid #eee; color: #ef4444;">{p["stock"]} ชิ้น</td></tr>'
    
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #f59e0b;">⚠️ แจ้งเตือนสินค้าใกล้หมด</h2>
        <p>สินค้าต่อไปนี้มีสต็อกต่ำกว่าที่กำหนด:</p>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; text-align: left;">สินค้า</th>
                    <th style="padding: 10px; text-align: left;">รหัส SKU</th>
                    <th style="padding: 10px; text-align: left;">สต็อกคงเหลือ</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
        <p>กรุณาเติมสต็อกโดยเร็ว</p>
    </div>
    '''
    send_email(admin_email, f'[แจ้งเตือน] สินค้าใกล้หมด {len(products)} รายการ', html)

def send_password_reset_email(to_email, full_name, reset_token, reset_link):
    """Send password reset email"""
    html = f'''
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #8b5cf6;">🔐 รีเซ็ตรหัสผ่าน</h2>
        <p>สวัสดี คุณ{full_name}</p>
        <p>เราได้รับคำขอรีเซ็ตรหัสผ่านสำหรับบัญชีของคุณ</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background: linear-gradient(135deg, #8b5cf6, #ec4899); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">รีเซ็ตรหัสผ่าน</a>
        </div>
        <p style="color: #666;">ลิงก์นี้จะหมดอายุใน 1 ชั่วโมง</p>
        <p style="color: #666;">หากคุณไม่ได้ขอรีเซ็ตรหัสผ่าน กรุณาเพิกเฉยอีเมลนี้</p>
        <hr style="margin: 20px 0; border: none; border-top: 1px solid #eee;">
        <p style="color: #999; font-size: 12px;">หากปุ่มไม่ทำงาน คัดลอกลิงก์นี้: {reset_link}</p>
    </div>
    '''
    send_email(to_email, 'รีเซ็ตรหัสผ่าน - ระบบสมาชิก', html)

def send_welcome_bot_chat(user_id, user_name):
    """Send welcome message from bot to new reseller's chat thread (non-blocking)."""
    def _run():
        conn = cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get bot name from agent_settings
            cursor.execute('SELECT bot_chat_name FROM agent_settings LIMIT 1')
            row = cursor.fetchone()
            bot_name = row['bot_chat_name'] if row and row['bot_chat_name'] else 'น้องนุ่น'

            # Get Super Admin id for sender_id
            cursor.execute("SELECT id FROM users WHERE role_id=(SELECT id FROM roles WHERE name='Super Admin') LIMIT 1")
            admin = cursor.fetchone()
            admin_id = admin['id'] if admin else 1

            # Get or create chat thread
            cursor.execute('SELECT id FROM chat_threads WHERE reseller_id=%s', (user_id,))
            thread = cursor.fetchone()
            if not thread:
                cursor.execute('INSERT INTO chat_threads (reseller_id) VALUES (%s) RETURNING id', (user_id,))
                thread = cursor.fetchone()
            thread_id = thread['id']

            welcome = (
                f'🎉 ยินดีต้อนรับสู่ครอบครัว EKG Shops นะคะ คุณพี่{user_name}!\n'
                f'บัญชี Reseller ของคุณพี่พร้อมใช้งานแล้วค่ะ 🎊\n'
                f'ตอนนี้คุณพี่สามารถเข้าดูสินค้าและสั่งซื้อในราคา Reseller ได้ทันทีเลยนะคะ\n'
                f'หากมีข้อสงสัยหรือต้องการความช่วยเหลืออะไร ทักหา{bot_name}ได้เลยค่ะ 😊'
            )

            cursor.execute('''
                INSERT INTO chat_messages (thread_id, sender_id, sender_type, content, is_bot)
                VALUES (%s, %s, 'admin', %s, TRUE) RETURNING id
            ''', (thread_id, admin_id, welcome))

            cursor.execute('''
                UPDATE chat_threads
                SET last_message_at=CURRENT_TIMESTAMP, last_message_preview=%s, is_archived=FALSE
                WHERE id=%s
            ''', (welcome[:100], thread_id))

            conn.commit()

            send_push_notification(
                user_id, f'🎉 ยินดีต้อนรับ!',
                f'{bot_name}: ยินดีต้อนรับสู่ครอบครัว EKG Shops ค่ะ คุณพี่{user_name}',
                url='/reseller#chat', tag=f'welcome-{user_id}'
            )
        except Exception as e:
            print(f'[WELCOME_CHAT] Error: {e}')
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    threading.Thread(target=_run, daemon=True).start()


def send_welcome_reseller_email(to_email, full_name):
    """Send welcome email to newly registered reseller (non-blocking)."""
    if not to_email:
        return
    def _run():
        try:
            domain = os.environ.get('REPLIT_DEV_DOMAIN') or 'ekg-shops.com'
            login_url = f'https://{domain}/login'
            html = f'''
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;background:#fff;">
  <div style="text-align:center;margin-bottom:24px;">
    <h1 style="color:#8b5cf6;margin:0;">🎉 ยินดีต้อนรับสู่ EKG Shops!</h1>
    <p style="color:#6b7280;margin-top:8px;">Reseller Family</p>
  </div>
  <div style="background:linear-gradient(135deg,#8b5cf6,#ec4899);border-radius:12px;padding:24px;color:#fff;margin-bottom:24px;">
    <p style="margin:0;font-size:18px;">สวัสดี คุณพี่{full_name} 👋</p>
    <p style="margin:8px 0 0;opacity:0.9;">บัญชี Reseller ของคุณพี่พร้อมใช้งานแล้วค่ะ</p>
  </div>
  <div style="background:#f9fafb;border-radius:8px;padding:20px;margin-bottom:20px;">
    <h3 style="margin-top:0;color:#374151;">สิทธิ์ที่คุณพี่ได้รับ</h3>
    <ul style="color:#6b7280;padding-left:20px;line-height:1.8;">
      <li>ราคา Reseller พิเศษสำหรับสมาชิก</li>
      <li>สั่งซื้อชุดพยาบาล / สครับ ได้ทันที</li>
      <li>ระบบติดตามออเดอร์ real-time</li>
      <li>แชทสอบถามข้อมูลกับทีมงานได้ตลอด</li>
    </ul>
  </div>
  <div style="text-align:center;margin:28px 0;">
    <a href="{login_url}"
       style="background:linear-gradient(135deg,#8b5cf6,#ec4899);color:#fff;padding:14px 32px;
              text-decoration:none;border-radius:8px;font-weight:bold;font-size:16px;display:inline-block;">
      เข้าสู่ระบบ
    </a>
  </div>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
  <p style="color:#9ca3af;font-size:13px;text-align:center;">
    หากมีข้อสงสัยติดต่อ Line: @ekgshops<br>
    ขอบคุณที่เลือกร่วมงานกับ EKG Shops ค่ะ 🙏
  </p>
</div>'''
            send_email(to_email, f'🎉 ยินดีต้อนรับสู่ EKG Shops Reseller — คุณพี่{full_name}', html)
        except Exception as e:
            print(f'[WELCOME_EMAIL] Error: {e}')
    threading.Thread(target=_run, daemon=True).start()


def log_activity(action_type, action_category, description, target_type=None, target_id=None, target_name=None, extra_data=None):
    """Log user activity to activity_logs table"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        user_id = session.get('user_id')
        user_name = session.get('full_name', 'ระบบ')
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:500] if request else None
        
        cursor.execute('''
            INSERT INTO activity_logs 
            (user_id, user_name, action_type, action_category, description, target_type, target_id, target_name, ip_address, user_agent, extra_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (user_id, user_name, action_type, action_category, description, 
              target_type, target_id, target_name, ip_address, user_agent, 
              json.dumps(extra_data) if extra_data else None))
        
        conn.commit()
    except Exception as e:
        print(f"Log activity error: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

