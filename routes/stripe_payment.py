import os
import stripe
import requests
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, redirect, url_for, render_template_string

stripe_bp = Blueprint('stripe_payment', __name__)

# ── ดึง Stripe credentials จาก Replit Connectors ──────────────────────────────
def _get_stripe_secret_key():
    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    if not hostname:
        raise Exception('REPLIT_CONNECTORS_HOSTNAME not set')

    repl_identity    = os.environ.get('REPL_IDENTITY')
    web_repl_renewal = os.environ.get('WEB_REPL_RENEWAL')
    if repl_identity:
        token = 'repl ' + repl_identity
    elif web_repl_renewal:
        token = 'depl ' + web_repl_renewal
    else:
        raise Exception('No Replit identity token found')

    is_prod    = os.environ.get('REPLIT_DEPLOYMENT') == '1'
    target_env = 'production' if is_prod else 'development'

    resp = requests.get(
        f'https://{hostname}/api/v2/connection',
        params={'include_secrets': 'true', 'connector_names': 'stripe', 'environment': target_env},
        headers={'Accept': 'application/json', 'X-Replit-Token': token},
        timeout=10
    )
    data = resp.json()
    item = (data.get('items') or [None])[0]
    if not item:
        raise Exception(f'Stripe {target_env} connection not found')
    return item['settings']['secret']


def _get_stripe_client():
    key = _get_stripe_secret_key()
    stripe.api_key = key
    return stripe


def _get_db():
    from database import get_db_connection
    return get_db_connection()


# ── สร้าง Checkout Session ────────────────────────────────────────────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-checkout', methods=['POST'])
def create_stripe_checkout(order_id):
    from flask import session as flask_session
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute('''
            SELECT o.id, o.order_number, o.final_amount, o.status, o.user_id
            FROM orders o WHERE o.id = %s
        ''', (order_id,))
        order = cur.fetchone()

        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        if order['status'] != 'pending_payment':
            return jsonify({'error': f'คำสั่งซื้อสถานะ {order["status"]} ไม่สามารถชำระได้'}), 400

        amount_satangs = int(float(order['final_amount']) * 100)
        if amount_satangs <= 0:
            return jsonify({'error': 'ยอดชำระต้องมากกว่า 0'}), 400

        domain = request.host_url.rstrip('/')
        client = _get_stripe_client()

        checkout_session = client.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'thb',
                    'unit_amount': amount_satangs,
                    'product_data': {
                        'name': f'คำสั่งซื้อ {order["order_number"]}',
                        'description': 'EKG Shops',
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{domain}/stripe/checkout/success?session_id={{CHECKOUT_SESSION_ID}}&order_id={order_id}',
            cancel_url=f'{domain}/stripe/checkout/cancel?order_id={order_id}',
            metadata={'order_id': str(order_id), 'order_number': order['order_number']},
        )

        cur.execute('''
            UPDATE orders
            SET stripe_session_id = %s, payment_method = 'stripe', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (checkout_session.id, order_id))
        conn.commit()

        return jsonify({'checkout_url': checkout_session.url})

    except stripe.error.StripeError as e:
        return jsonify({'error': f'Stripe error: {str(e)}'}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


# ── Stripe Webhook ─────────────────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload   = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    conn = None
    try:
        secret_key = _get_stripe_secret_key()
        stripe.api_key = secret_key

        # ดึง webhook secret จาก env (ถ้ามี) หรือตรวจสอบแบบ raw
        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json
            event = stripe.Event.construct_from(json.loads(payload), secret_key)

        if event['type'] == 'checkout.session.completed':
            session_obj = event['data']['object']
            if session_obj.get('payment_status') == 'paid':
                _handle_payment_success(session_obj)

        elif event['type'] == 'payment_intent.payment_failed':
            pi = event['data']['object']
            print(f'[STRIPE] payment_intent.payment_failed pi={pi.get("id")}')

        return jsonify({'received': True})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 400
    finally:
        if conn:
            conn.close()


def _handle_payment_success(session_obj):
    session_id = session_obj.get('id')
    order_id   = session_obj.get('metadata', {}).get('order_id')
    pi_id      = session_obj.get('payment_intent')

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if order_id:
            cur.execute('SELECT id, status, user_id FROM orders WHERE id = %s', (int(order_id),))
        else:
            cur.execute('SELECT id, status, user_id FROM orders WHERE stripe_session_id = %s', (session_id,))

        order = cur.fetchone()
        if not order:
            print(f'[STRIPE] webhook: order not found session={session_id}')
            return
        if order['status'] not in ('pending_payment', 'under_review'):
            print(f'[STRIPE] webhook: order {order["id"]} already {order["status"]}')
            return

        cur.execute('''
            UPDATE orders
            SET status = 'preparing',
                payment_method = 'stripe',
                stripe_session_id = %s,
                stripe_payment_intent_id = %s,
                paid_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (session_id, pi_id, order['id']))

        # บันทึก payment slip อัตโนมัติ (Stripe)
        cur.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status, verified_at)
            SELECT %s, 'stripe_payment', final_amount, 'approved', CURRENT_TIMESTAMP
            FROM orders WHERE id = %s
        ''', (order['id'], order['id']))

        conn.commit()
        print(f'[STRIPE] order {order["id"]} paid and set to preparing')

    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
    finally:
        if conn:
            conn.close()


# ── Success / Cancel redirect pages ───────────────────────────────────────────
SUCCESS_HTML = '''
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ชำระเงินสำเร็จ</title>
<style>
  body { margin:0; font-family: 'Prompt', sans-serif; background: #0a0a0a; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { text-align: center; padding: 40px; max-width: 420px; }
  .icon { font-size: 64px; margin-bottom: 16px; }
  h1 { font-size: 24px; color: #22c55e; margin-bottom: 8px; }
  p { color: rgba(255,255,255,0.6); margin-bottom: 24px; }
  .order-num { font-size: 20px; font-weight: 700; color: #fff; background: #1a1a2e; padding: 12px 24px; border-radius: 8px; display: inline-block; margin-bottom: 24px; }
  a { display: inline-block; background: #6366f1; color: #fff; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 600; }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h1>ชำระเงินสำเร็จ!</h1>
    <p>ระบบได้รับการชำระเงินของคุณแล้ว<br>เราจะเริ่มดำเนินการคำสั่งซื้อทันที</p>
    <div class="order-num">{{ order_number }}</div>
    <br>
    <a href="/reseller/orders">ดูคำสั่งซื้อ</a>
  </div>
</body>
</html>
'''

CANCEL_HTML = '''
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ยกเลิกการชำระเงิน</title>
<style>
  body { margin:0; font-family: 'Prompt', sans-serif; background: #0a0a0a; color: #fff; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { text-align: center; padding: 40px; max-width: 420px; }
  .icon { font-size: 64px; margin-bottom: 16px; }
  h1 { font-size: 24px; color: #f59e0b; margin-bottom: 8px; }
  p { color: rgba(255,255,255,0.6); margin-bottom: 24px; }
  .actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
  a { display: inline-block; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; }
  .btn-primary { background: #6366f1; color: #fff; }
  .btn-secondary { background: #2a2a3e; color: #fff; }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">⚠️</div>
    <h1>ยกเลิกการชำระเงิน</h1>
    <p>คุณยกเลิกการชำระเงินแล้ว<br>คำสั่งซื้อยังอยู่ในระบบ สามารถชำระภายหลังได้</p>
    <div class="actions">
      <a class="btn-primary" href="/reseller/checkout">กลับหน้าชำระเงิน</a>
      <a class="btn-secondary" href="/reseller/orders">ดูคำสั่งซื้อ</a>
    </div>
  </div>
</body>
</html>
'''


@stripe_bp.route('/stripe/checkout/success')
def stripe_success():
    session_id = request.args.get('session_id', '')
    order_id   = request.args.get('order_id')

    order_number = ''
    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if order_id:
            cur.execute('SELECT order_number FROM orders WHERE id = %s', (int(order_id),))
        else:
            cur.execute('SELECT order_number FROM orders WHERE stripe_session_id = %s', (session_id,))
        row = cur.fetchone()
        if row:
            order_number = row['order_number']
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    return render_template_string(SUCCESS_HTML, order_number=order_number)


@stripe_bp.route('/stripe/checkout/cancel')
def stripe_cancel():
    return render_template_string(CANCEL_HTML)
