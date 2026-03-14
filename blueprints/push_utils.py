from database import get_db
import psycopg2.extras
import os, json, threading
from pywebpush import webpush, WebPushException

def create_notification(user_id, title, message, notification_type='info', reference_type=None, reference_id=None):
    """Create a notification for a user"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO notifications (user_id, title, message, type, reference_type, reference_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (user_id, title, message, notification_type, reference_type, reference_id))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def _do_send_push(user_id, title, body, url, tag, notification_type):
    """Internal: actually send push notifications (runs in background thread)."""
    import requests as _requests
    conn = None
    cursor = None
    try:
        vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY', '')
        vapid_subject = os.environ.get('VAPID_SUBJECT', 'mailto:admin@ekgshops.com')
        
        if not vapid_private_key:
            return
        
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('SELECT id, endpoint, p256dh, auth, user_agent FROM push_subscriptions WHERE user_id = %s', (user_id,))
        subscriptions = cursor.fetchall()
        
        if not subscriptions:
            return
        
        payload = json.dumps({
            'title': title,
            'body': body,
            'icon': '/static/icons/icon-192x192.png',
            'url': url,
            'tag': tag,
            'type': notification_type
        })
        
        print(f"[PUSH] Sending to user {user_id}: {title} - {body[:50]} ({len(subscriptions)} subscriptions)")
        
        expired_ids = []
        sent_count = 0
        for sub in subscriptions:
            device = 'Mobile' if 'Mobile' in (sub.get('user_agent') or '') else 'PC'
            try:
                push_session = _requests.Session()
                push_session.request = lambda method, url, timeout=8, **kwargs: (
                    _requests.Session.request(push_session, method, url, timeout=timeout, **kwargs)
                )
                webpush(
                    subscription_info={
                        'endpoint': sub['endpoint'],
                        'keys': {
                            'p256dh': sub['p256dh'],
                            'auth': sub['auth']
                        }
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims={'sub': vapid_subject},
                    requests_session=push_session
                )
                sent_count += 1
                print(f"[PUSH] Sent successfully to sub {sub['id']} ({device})")
                try:
                    cursor.execute('''INSERT INTO push_delivery_log (user_id, subscription_id, device_info, status, status_code)
                        VALUES (%s, %s, %s, 'sent', '201')''', (user_id, sub['id'], device))
                    conn.commit()
                except: pass
            except WebPushException as e:
                status_code = str(e.response.status_code) if e.response else 'unknown'
                error_msg = str(e)[:300]
                print(f"[PUSH] WebPushException sub {sub['id']} ({device}): status={status_code}, {error_msg[:200]}")
                try:
                    cursor.execute('''INSERT INTO push_delivery_log (user_id, subscription_id, device_info, status, status_code, error_message)
                        VALUES (%s, %s, %s, 'failed', %s, %s)''', (user_id, sub['id'], device, status_code, error_msg))
                    conn.commit()
                except: pass
                if e.response and e.response.status_code in (404, 410):
                    expired_ids.append(sub['id'])
            except Exception as e:
                print(f"[PUSH] Error for sub {sub['id']} ({device}): {str(e)[:200]}")
        
        print(f"[PUSH] Sent {sent_count}/{len(subscriptions)} to user {user_id}")
        
        if expired_ids:
            try:
                cursor.execute('DELETE FROM push_subscriptions WHERE id = ANY(%s)', (expired_ids,))
                conn.commit()
                print(f"[PUSH] Cleaned up {len(expired_ids)} expired subscriptions")
            except: pass
            
    except Exception as e:
        print(f"[PUSH] Fatal error sending to user {user_id}: {str(e)[:300]}")
    finally:
        if cursor:
            try: cursor.close()
            except: pass
        if conn:
            try: conn.close()
            except: pass


def send_push_notification(user_id, title, body, url='/', tag='ekg-notification', notification_type='general'):
    """Non-blocking push notification — runs in background thread so it never blocks a Gunicorn worker."""
    t = threading.Thread(
        target=_do_send_push,
        args=(user_id, title, body, url, tag, notification_type),
        daemon=True
    )
    t.start()

def send_push_to_admins(title, body, url='/', tag='admin-notification'):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT ps.user_id FROM push_subscriptions ps
            JOIN users u ON u.id = ps.user_id
            JOIN roles r ON r.id = u.role_id
            WHERE r.name IN ('Super Admin', 'Assistant Admin')
        ''')
        admin_ids = [row[0] for row in cursor.fetchall()]
        
        for admin_id in admin_ids:
            send_push_notification(admin_id, title, body, url, tag)
            
    except Exception:
        pass
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def notify_admins_guest_lead(title, message, notification_type='info', reference_type=None, reference_id=None, push_url='/admin', push_tag='admin-guest-lead'):
    """Send push notification + persist in-app notification bell for all admins. Runs in background thread."""
    def _run():
        conn = None
        cursor = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT u.id FROM users u
                JOIN roles r ON r.id = u.role_id
                WHERE r.name IN ('Super Admin', 'Assistant Admin')
            ''')
            admin_ids = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            for aid in admin_ids:
                create_notification(aid, title, message, notification_type, reference_type, reference_id)
                send_push_notification(aid, title, message[:100], url=push_url, tag=push_tag)
        except Exception as _e:
            print(f'[notify_admins_guest_lead] error: {_e}')
        finally:
            if cursor:
                try: cursor.close()
                except: pass
            if conn:
                try: conn.close()
                except: pass
    threading.Thread(target=_run, daemon=True).start()

# ==================== END PWA & PUSH NOTIFICATIONS ====================
