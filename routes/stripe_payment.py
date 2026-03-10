import os
import stripe
import requests
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, redirect, url_for, render_template_string, session as flask_session

stripe_bp = Blueprint('stripe_payment', __name__)


def _get_stripe_keys():
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
    settings = item['settings']
    return settings['secret'], settings.get('publishable', '')


def _get_stripe_client():
    secret, _ = _get_stripe_keys()
    stripe.api_key = secret
    return stripe


def _get_db():
    from database import get_db
    return get_db()


def _require_user():
    user_id = flask_session.get('user_id')
    if not user_id:
        return None, jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
    return user_id, None, None


# ── Config (publishable key) ──────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/config', methods=['GET'])
def stripe_config():
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        _, publishable = _get_stripe_keys()
        return jsonify({'publishable_key': publishable})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Ensure Stripe Customer for user ──────────────────────────────────────────
@stripe_bp.route('/api/stripe/ensure-customer', methods=['POST'])
def ensure_stripe_customer():
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT id, full_name, email, stripe_customer_id FROM users WHERE id = %s', (user_id,))
        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if user['stripe_customer_id']:
            return jsonify({'customer_id': user['stripe_customer_id']})

        client = _get_stripe_client()
        customer = client.Customer.create(
            name=user['full_name'] or '',
            email=user['email'] or '',
            metadata={'user_id': str(user_id)}
        )
        cur.execute('UPDATE users SET stripe_customer_id = %s WHERE id = %s',
                    (customer.id, user_id))
        conn.commit()
        return jsonify({'customer_id': customer.id})
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── List saved cards ──────────────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/saved-cards', methods=['GET'])
def list_saved_cards():
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT stripe_customer_id FROM users WHERE id = %s', (user_id,))
        row = cur.fetchone()
        if not row or not row['stripe_customer_id']:
            return jsonify({'cards': []})

        client = _get_stripe_client()
        pms = client.PaymentMethod.list(
            customer=row['stripe_customer_id'],
            type='card'
        )
        cards = []
        for pm in pms.data:
            card = pm.card
            cards.append({
                'id': pm.id,
                'brand': card.brand,
                'last4': card.last4,
                'exp_month': card.exp_month,
                'exp_year': card.exp_year,
            })
        return jsonify({'cards': cards})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Delete saved card ─────────────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/saved-cards/<pm_id>', methods=['DELETE'])
def delete_saved_card(pm_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        client = _get_stripe_client()
        client.PaymentMethod.detach(pm_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Create PaymentIntent for card payment ─────────────────────────────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-card-intent', methods=['POST'])
def create_card_payment_intent(order_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json() or {}
    save_card = body.get('save_card', False)

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute('SELECT id, order_number, final_amount, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        if order['status'] != 'pending_payment':
            return jsonify({'error': f'คำสั่งซื้อสถานะ {order["status"]} ชำระไม่ได้'}), 400

        amount_satangs = int(float(order['final_amount']) * 100)
        if amount_satangs <= 0:
            return jsonify({'error': 'ยอดชำระต้องมากกว่า 0'}), 400

        client = _get_stripe_client()

        cur.execute('SELECT stripe_customer_id, full_name, email FROM users WHERE id = %s', (user_id,))
        urow = cur.fetchone()
        customer_id = urow['stripe_customer_id'] if urow else None
        if not customer_id:
            customer = client.Customer.create(
                name=(urow['full_name'] or '') if urow else '',
                email=(urow['email'] or '') if urow else '',
                metadata={'user_id': str(user_id)}
            )
            customer_id = customer.id
            cur.execute('UPDATE users SET stripe_customer_id = %s WHERE id = %s', (customer_id, user_id))

        pi_params = {
            'amount': amount_satangs,
            'currency': 'thb',
            'payment_method_types': ['card'],
            'customer': customer_id,
            'metadata': {'order_id': str(order_id), 'order_number': order['order_number']},
            'description': f'EKG Shops - {order["order_number"]}',
        }

        if save_card:
            pi_params['setup_future_usage'] = 'off_session'

        pi = client.PaymentIntent.create(**pi_params)

        cur.execute('''
            UPDATE orders
            SET stripe_payment_intent_id = %s, payment_method = 'stripe', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (pi.id, order_id))
        conn.commit()

        _, publishable = _get_stripe_keys()
        return jsonify({'client_secret': pi.client_secret, 'publishable_key': publishable, 'pi_id': pi.id})

    except stripe.error.StripeError as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return jsonify({'error': f'Stripe: {str(e)}'}), 400
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Unified PaymentIntent (card + PromptPay via Payment Element) ─────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-payment-intent', methods=['POST'])
def create_unified_payment_intent(order_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute('SELECT id, order_number, final_amount, status, user_id, stripe_payment_intent_id FROM orders WHERE id = %s', (order_id,))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        if order['status'] != 'pending_payment':
            return jsonify({'error': f'คำสั่งซื้อสถานะ {order["status"]} ชำระไม่ได้'}), 400

        amount_satangs = int(float(order['final_amount']) * 100)
        if amount_satangs <= 0:
            return jsonify({'error': 'ยอดชำระต้องมากกว่า 0'}), 400

        client = _get_stripe_client()

        cur.execute('SELECT stripe_customer_id, full_name, email FROM users WHERE id = %s', (user_id,))
        urow = cur.fetchone()
        customer_id = urow['stripe_customer_id'] if urow else None
        if not customer_id:
            customer = client.Customer.create(
                name=(urow['full_name'] or '') if urow else '',
                email=(urow['email'] or '') if urow else '',
                metadata={'user_id': str(user_id)}
            )
            customer_id = customer.id
            cur.execute('UPDATE users SET stripe_customer_id = %s WHERE id = %s', (customer_id, user_id))

        pi = client.PaymentIntent.create(
            amount=amount_satangs,
            currency='thb',
            automatic_payment_methods={'enabled': True},
            customer=customer_id,
            metadata={'order_id': str(order_id), 'order_number': order['order_number']},
            description=f'EKG Shops - {order["order_number"]}',
        )

        cur.execute('''
            UPDATE orders
            SET stripe_payment_intent_id = %s, payment_method = 'stripe', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (pi.id, order_id))
        conn.commit()

        _, publishable = _get_stripe_keys()
        return jsonify({'client_secret': pi.client_secret, 'publishable_key': publishable, 'pi_id': pi.id})

    except stripe.error.StripeError as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return jsonify({'error': f'Stripe: {str(e)}'}), 400
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Verify Stripe return after redirect (PromptPay) ──────────────────────────
@stripe_bp.route('/api/stripe/verify-return', methods=['POST'])
def verify_stripe_return():
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body = request.get_json() or {}
    pi_id = body.get('pi_id', '').strip()
    if not pi_id:
        return jsonify({'error': 'pi_id required'}), 400

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        client = _get_stripe_client()
        pi = client.PaymentIntent.retrieve(pi_id)

        if pi.status != 'succeeded':
            return jsonify({'success': False, 'status': pi.status, 'message': f'การชำระเงินยังไม่สำเร็จ (สถานะ: {pi.status})'}), 200

        order_id_meta = pi.metadata.get('order_id')
        if not order_id_meta:
            return jsonify({'error': 'ไม่พบ order_id ใน payment intent'}), 400

        cur.execute('''
            SELECT id, order_number, status, user_id FROM orders
            WHERE id = %s AND stripe_payment_intent_id = %s
        ''', (int(order_id_meta), pi_id))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์'}), 403

        if order['status'] == 'pending_payment':
            cur.execute('''
                UPDATE orders
                SET status = 'preparing', paid_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (order['id'],))
            conn.commit()

        return jsonify({'success': True, 'order_id': order['id'], 'order_number': order['order_number']})

    except stripe.error.StripeError as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return jsonify({'error': f'Stripe: {str(e)}'}), 400
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Create PaymentIntent for PromptPay ───────────────────────────────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-promptpay-intent', methods=['POST'])
def create_promptpay_intent(order_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute('SELECT id, order_number, final_amount, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        if order['status'] != 'pending_payment':
            return jsonify({'error': f'คำสั่งซื้อสถานะ {order["status"]} ชำระไม่ได้'}), 400

        amount_satangs = int(float(order['final_amount']) * 100)
        if amount_satangs <= 0:
            return jsonify({'error': 'ยอดชำระต้องมากกว่า 0'}), 400

        client = _get_stripe_client()
        pi = client.PaymentIntent.create(
            amount=amount_satangs,
            currency='thb',
            payment_method_types=['promptpay'],
            metadata={'order_id': str(order_id), 'order_number': order['order_number']},
            description=f'EKG Shops - {order["order_number"]}',
        )
        pm = client.PaymentMethod.create(type='promptpay')
        pi = client.PaymentIntent.confirm(pi.id, payment_method=pm.id)

        qr_url = ''
        if pi.next_action and pi.next_action.get('type') == 'promptpay_display_qr_code':
            qr_url = pi.next_action['promptpay_display_qr_code'].get('image_url_png', '')

        cur.execute('''
            UPDATE orders
            SET stripe_payment_intent_id = %s, payment_method = 'stripe_promptpay', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (pi.id, order_id))
        conn.commit()

        return jsonify({
            'pi_id': pi.id,
            'qr_url': qr_url,
            'amount': float(order['final_amount']),
            'order_number': order['order_number'],
        })

    except stripe.error.StripeError as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return jsonify({'error': f'Stripe: {str(e)}'}), 400
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Confirm card payment from frontend (no-webhook fallback) ─────────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-card-confirm', methods=['POST'])
def confirm_card_payment(order_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    body  = request.get_json() or {}
    pi_id = body.get('pi_id')
    if not pi_id:
        return jsonify({'error': 'pi_id required'}), 400

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute('SELECT id, order_number, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403

        if order['status'] == 'preparing':
            return jsonify({'success': True, 'already_confirmed': True, 'order_number': order['order_number']})

        if order['status'] != 'pending_payment':
            return jsonify({'error': f'สถานะ {order["status"]} ไม่สามารถยืนยันได้'}), 400

        client = _get_stripe_client()
        pi = client.PaymentIntent.retrieve(pi_id)

        if pi.status != 'succeeded':
            return jsonify({'error': f'การชำระเงินยังไม่สำเร็จ (status: {pi.status})'}), 400

        cur.execute('''
            UPDATE orders
            SET status = 'preparing',
                stripe_payment_intent_id = %s,
                payment_method = 'stripe',
                paid_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (pi_id, order_id))

        cur.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status, verified_at)
            SELECT %s, 'stripe_payment', final_amount, 'approved', CURRENT_TIMESTAMP
            FROM orders WHERE id = %s
        ''', (order_id, order_id))

        conn.commit()
        print(f'[STRIPE] order {order_id} confirmed via frontend → preparing')
        return jsonify({'success': True, 'order_number': order['order_number']})

    except stripe.error.StripeError as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return jsonify({'error': f'Stripe: {str(e)}'}), 400
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()


# ── Poll PaymentIntent status ─────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/payment-intent/<pi_id>/status', methods=['GET'])
def get_payment_intent_status(pi_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        client = _get_stripe_client()
        pi = client.PaymentIntent.retrieve(pi_id)
        return jsonify({'status': pi.status})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Legacy: Stripe Checkout Session (redirect) ────────────────────────────────
@stripe_bp.route('/api/orders/<int:order_id>/stripe-checkout', methods=['POST'])
def create_stripe_checkout(order_id):
    user_id = flask_session.get('user_id')
    if not user_id:
        return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401

    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT id, order_number, final_amount, status, user_id FROM orders WHERE id = %s', (order_id,))
        order = cur.fetchone()
        if not order:
            return jsonify({'error': 'ไม่พบคำสั่งซื้อ'}), 404
        if order['user_id'] != user_id:
            return jsonify({'error': 'ไม่มีสิทธิ์เข้าถึง'}), 403
        if order['status'] != 'pending_payment':
            return jsonify({'error': f'คำสั่งซื้อสถานะ {order["status"]} ไม่สามารถชำระได้'}), 400

        amount_satangs = int(float(order['final_amount']) * 100)
        domain = request.host_url.rstrip('/')
        client = _get_stripe_client()

        checkout_session = client.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'thb',
                    'unit_amount': amount_satangs,
                    'product_data': {'name': f'คำสั่งซื้อ {order["order_number"]}', 'description': 'EKG Shops'},
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{domain}/stripe/checkout/success?session_id={{CHECKOUT_SESSION_ID}}&order_id={order_id}',
            cancel_url=f'{domain}/stripe/checkout/cancel?order_id={order_id}',
            metadata={'order_id': str(order_id), 'order_number': order['order_number']},
        )

        cur.execute('''
            UPDATE orders SET stripe_session_id = %s, payment_method = 'stripe', updated_at = CURRENT_TIMESTAMP
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
        if conn: conn.close()


# ── Stripe Webhook ─────────────────────────────────────────────────────────────
@stripe_bp.route('/api/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        secret_key, _ = _get_stripe_keys()
        stripe.api_key = secret_key

        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json
            event = stripe.Event.construct_from(json.loads(payload), secret_key)

        if event['type'] == 'checkout.session.completed':
            session_obj = event['data']['object']
            if session_obj.get('payment_status') == 'paid':
                _handle_checkout_success(session_obj)

        elif event['type'] == 'payment_intent.succeeded':
            pi = event['data']['object']
            _handle_payment_intent_success(pi)

        elif event['type'] == 'payment_intent.payment_failed':
            pi = event['data']['object']
            print(f'[STRIPE] payment_intent.payment_failed pi={pi.get("id")}')

        return jsonify({'received': True})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 400


def _handle_checkout_success(session_obj):
    session_id = session_obj.get('id')
    order_id   = session_obj.get('metadata', {}).get('order_id')
    pi_id      = session_obj.get('payment_intent')
    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if order_id:
            cur.execute('SELECT id, status FROM orders WHERE id = %s', (int(order_id),))
        else:
            cur.execute('SELECT id, status FROM orders WHERE stripe_session_id = %s', (session_id,))
        order = cur.fetchone()
        if not order or order['status'] not in ('pending_payment', 'under_review'):
            return
        cur.execute('''
            UPDATE orders SET status='preparing', payment_method='stripe',
            stripe_session_id=%s, stripe_payment_intent_id=%s,
            paid_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=%s
        ''', (session_id, pi_id, order['id']))
        cur.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status, verified_at)
            SELECT %s, 'stripe_payment', final_amount, 'approved', CURRENT_TIMESTAMP
            FROM orders WHERE id = %s
        ''', (order['id'], order['id']))
        conn.commit()
        print(f'[STRIPE] checkout success order {order["id"]} → preparing')
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
    finally:
        if conn: conn.close()


def _handle_payment_intent_success(pi):
    pi_id    = pi.get('id')
    order_id = pi.get('metadata', {}).get('order_id')
    conn = None
    try:
        conn = _get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if order_id:
            cur.execute('SELECT id, status FROM orders WHERE id = %s', (int(order_id),))
        else:
            cur.execute('SELECT id, status FROM orders WHERE stripe_payment_intent_id = %s', (pi_id,))
        order = cur.fetchone()
        if not order or order['status'] not in ('pending_payment', 'under_review'):
            return
        payment_method = 'stripe_promptpay' if pi.get('payment_method_types') == ['promptpay'] else 'stripe'
        cur.execute('''
            UPDATE orders SET status='preparing', payment_method=%s,
            stripe_payment_intent_id=%s, paid_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
        ''', (payment_method, pi_id, order['id']))
        cur.execute('''
            INSERT INTO payment_slips (order_id, slip_image_url, amount, status, verified_at)
            SELECT %s, 'stripe_payment', final_amount, 'approved', CURRENT_TIMESTAMP
            FROM orders WHERE id = %s
        ''', (order['id'], order['id']))
        conn.commit()
        print(f'[STRIPE] payment_intent success order {order["id"]} → preparing')
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        import traceback; traceback.print_exc()
    finally:
        if conn: conn.close()


# Keep old _handle_payment_success name for backwards compat
_handle_payment_success = _handle_checkout_success


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
        if row: order_number = row['order_number']
    except Exception:
        pass
    finally:
        if conn: conn.close()
    return render_template_string(SUCCESS_HTML, order_number=order_number)


@stripe_bp.route('/stripe/checkout/cancel')
def stripe_cancel():
    return render_template_string(CANCEL_HTML)
