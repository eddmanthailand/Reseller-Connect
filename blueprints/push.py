from flask import Blueprint, request, jsonify, session, send_from_directory, send_file, make_response
from database import get_db
from utils import login_required, admin_required, handle_error
from blueprints.push_utils import send_push_notification, create_notification, send_push_to_admins
import psycopg2.extras
import psycopg2
import json, os
try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception

push_bp = Blueprint('push', __name__)

# ==================== IN-APP CHAT SYSTEM ====================

@push_bp.route('/sw.js')
def service_worker():
    response = send_file('static/sw.js', mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@push_bp.route('/manifest.json')
def manifest():
    import json
    with open('static/manifest.json', 'r') as f:
        data = json.load(f)
    
    ref = request.referrer or ''
    role_name = session.get('role', '')
    
    if '/admin' in ref or role_name in ('Super Admin', 'Assistant Admin'):
        data['start_url'] = '/admin'
        data['name'] = 'EKG Shops - Admin'
        data['short_name'] = 'EKG Admin'
    else:
        data['start_url'] = '/reseller'
    
    response = make_response(json.dumps(data, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@push_bp.route('/manifest-admin.json')
def manifest_admin():
    import json
    with open('static/manifest.json', 'r') as f:
        data = json.load(f)
    
    data['start_url'] = '/admin'
    data['name'] = 'EKG Shops - Admin'
    data['short_name'] = 'EKG Admin'
    data['scope'] = '/admin'
    
    response = make_response(json.dumps(data, ensure_ascii=False))
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

@push_bp.route('/api/push/vapid-public-key', methods=['GET'])
@login_required
def get_vapid_public_key():
    public_key = os.environ.get('VAPID_PUBLIC_KEY', '')
    return jsonify({'publicKey': public_key}), 200

@push_bp.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        subscription = data.get('subscription', {})
        endpoint = subscription.get('endpoint', '')
        keys = subscription.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')
        
        if not endpoint or not p256dh or not auth:
            return jsonify({'error': 'Invalid subscription data'}), 400
        
        user_id = session['user_id']
        user_agent = request.headers.get('User-Agent', '')
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id != %s', (endpoint, user_id))
        
        cursor.execute('''
            DELETE FROM push_subscriptions 
            WHERE user_id = %s AND endpoint != %s AND user_agent = %s
        ''', (user_id, endpoint, user_agent))
        
        cursor.execute('''
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, endpoint) DO UPDATE SET
                p256dh = EXCLUDED.p256dh,
                auth = EXCLUDED.auth,
                user_agent = EXCLUDED.user_agent,
                created_at = CURRENT_TIMESTAMP
        ''', (user_id, endpoint, p256dh, auth, user_agent))
        conn.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@push_bp.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    conn = None
    cursor = None
    try:
        data = request.get_json()
        endpoint = data.get('endpoint', '')
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM push_subscriptions WHERE user_id = %s AND endpoint = %s', (user_id, endpoint))
        conn.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@push_bp.route('/api/push/status', methods=['GET'])
@login_required
def push_status():
    conn = None
    cursor = None
    try:
        user_id = session['user_id']
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM push_subscriptions WHERE user_id = %s', (user_id,))
        count = cursor.fetchone()[0]
        
        return jsonify({'subscribed': count > 0, 'count': count}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@push_bp.route('/api/push/test', methods=['POST'])
@login_required
def push_test():
    conn = None
    cursor = None
    try:
        user_id = session['user_id']
        vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
        vapid_subject = os.environ.get('VAPID_SUBJECT', 'mailto:admin@ekgshops.com')
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, endpoint, p256dh, auth, user_agent FROM push_subscriptions WHERE user_id = %s', (user_id,))
        subscriptions = cursor.fetchall()
        
        if not subscriptions:
            return jsonify({'success': False, 'error': 'No subscriptions found', 'user_id': user_id}), 200
        
        import time
        payload = json.dumps({
            'title': '🔔 ทดสอบการแจ้งเตือน',
            'body': 'ถ้าเห็นข้อความนี้ แสดงว่าระบบแจ้งเตือนทำงานปกติ!',
            'icon': '/static/icons/icon-192x192.png',
            'url': '/',
            'tag': f'test-{int(time.time()*1000)}',
            'type': 'test'
        })
        
        results = []
        for sub in subscriptions:
            device = 'Mobile' if 'Mobile' in (sub.get('user_agent') or '') else 'PC'
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub['endpoint'],
                        'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']}
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={'sub': vapid_subject}
                )
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'sent'})
            except WebPushException as e:
                status_code = e.response.status_code if e.response else 'unknown'
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'failed', 'code': status_code, 'error': str(e)[:150]})
                if e.response and e.response.status_code in (404, 410):
                    cursor.execute('DELETE FROM push_subscriptions WHERE id = %s', (sub['id'],))
                    conn.commit()
            except Exception as e:
                results.append({'sub_id': sub['id'], 'device': device, 'status': 'error', 'error': str(e)[:150]})
        
        return jsonify({'success': True, 'user_id': user_id, 'results': results}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# push notification functions moved to blueprints/push_utils.py


# ==================== iSHIP WEBHOOK ====================

@push_bp.route('/api/webhook/iship', methods=['POST'])
def iship_webhook():
    """Receive shipping status updates from iShip logistics aggregator"""
    iship_key = os.environ.get('ISHIP_API_KEY', '')
    if iship_key:
        auth_header = request.headers.get('X-API-Key', '') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if auth_header != iship_key:
            print(f"[iSHIP] Unauthorized webhook attempt from {request.remote_addr}")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    conn = None
    cursor = None
    try:
        payload = request.json
        if not payload:
            return jsonify({"status": "error", "message": "No payload"}), 400
        
        print(f"[iSHIP] Received webhook: {payload}")
        
        tracking_no = payload.get('tracking')
        status = payload.get('status')
        status_desc = payload.get('status_desc', '')
        
        if not tracking_no:
            return jsonify({"status": "ignored", "message": "No tracking number"}), 200
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT os.id as shipment_id, os.order_id, os.status as shipment_status,
                   o.order_number, o.user_id, o.status as order_status
            FROM order_shipments os
            JOIN orders o ON o.id = os.order_id
            WHERE os.tracking_number = %s
        ''', (tracking_no,))
        shipment = cursor.fetchone()
        
        if not shipment:
            print(f"[iSHIP] No shipment found for tracking: {tracking_no}")
            return jsonify({"status": "ignored", "message": "Tracking not found"}), 200
        
        reseller_id = shipment['user_id']
        order_number = shipment['order_number'] or f"#{shipment['order_id']}"
        
        if status == 'delivered':
            cursor.execute('''
                UPDATE order_shipments SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status != 'delivered'
            ''', (shipment['shipment_id'],))
            
            cursor.execute('''
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN status = 'delivered' THEN 1 END) as delivered_count
                FROM order_shipments WHERE order_id = %s
            ''', (shipment['order_id'],))
            counts = cursor.fetchone()
            
            if counts and counts['total'] == counts['delivered_count']:
                cursor.execute('''
                    UPDATE orders SET status = 'delivered', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND status != 'delivered'
                ''', (shipment['order_id'],))
                if cursor.rowcount > 0:
                    cursor.execute('SELECT final_amount, user_id FROM orders WHERE id = %s', (shipment['order_id'],))
                    ord_info = cursor.fetchone()
                    if ord_info and ord_info['final_amount']:
                        cursor.execute('UPDATE users SET total_purchases = COALESCE(total_purchases,0) + %s WHERE id = %s',
                                       (ord_info['final_amount'], ord_info['user_id']))
                        cursor.execute('''SELECT u.id, u.reseller_tier_id, u.tier_manual_override,
                            (SELECT id FROM reseller_tiers WHERE upgrade_threshold <= u.total_purchases
                             AND is_manual_only=FALSE ORDER BY level_rank DESC LIMIT 1) as new_tier_id
                            FROM users u WHERE u.id = %s''', (ord_info['user_id'],))
                        u = cursor.fetchone()
                        if u and u['new_tier_id'] and not u['tier_manual_override'] and u['new_tier_id'] != u['reseller_tier_id']:
                            cursor.execute('UPDATE users SET reseller_tier_id=%s WHERE id=%s', (u['new_tier_id'], u['id']))
            
            conn.commit()
            
            extra = f"({status_desc})" if status_desc else ""
            try:
                send_order_status_chat(reseller_id, order_number, 'delivered', extra, order_id=shipment['order_id'])
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
                
        elif status in ['shipped', 'in_transit', 'pickup']:
            cursor.execute('''
                UPDATE order_shipments SET status = 'shipped', shipped_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status NOT IN ('shipped', 'delivered')
            ''', (shipment['shipment_id'],))
            
            if shipment['order_status'] in ('paid', 'processing'):
                cursor.execute('''
                    UPDATE orders SET status = 'shipped', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (shipment['order_id'],))
            
            conn.commit()
            
            extra = f"({status_desc})" if status_desc else ""
            try:
                send_order_status_chat(reseller_id, order_number, 'shipped', extra, order_id=shipment['order_id'])
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
        elif status in ['returned', 'exception', 'failed']:
            if status == 'returned':
                cursor.execute('''
                    UPDATE order_shipments SET status = 'returned'
                    WHERE id = %s AND status NOT IN ('delivered', 'returned')
                ''', (shipment['shipment_id'],))
                cursor.execute('''
                    UPDATE orders SET status = 'returned', updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND status NOT IN ('delivered', 'returned', 'stock_restored')
                ''', (shipment['order_id'],))
            extra = f"({status_desc})" if status_desc else ""
            conn.commit()
            try:
                send_order_status_chat(reseller_id, order_number, 'shipping_issue', extra, order_id=shipment['order_id'])
            except Exception as ce:
                print(f"[iSHIP] Chat notification error: {ce}")
        else:
            print(f"[iSHIP] Unhandled status '{status}' for tracking {tracking_no}")
            conn.commit()
        
        print(f"[iSHIP] Processed: tracking={tracking_no}, status={status}, order={order_number}")
        return jsonify({"status": "success", "message": "Webhook processed"}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[iSHIP] Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== END iSHIP WEBHOOK ====================





