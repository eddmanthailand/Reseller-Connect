from flask import Blueprint, request, jsonify, session, render_template
from database import get_db
from utils import admin_required, is_trusted_origin
import psycopg2.extras
import hashlib
import json

analytics_bp = Blueprint('analytics', __name__)

# ─────────────────────────────────────────────
# POST /api/track  — log a user event
# ─────────────────────────────────────────────
@analytics_bp.route('/api/track', methods=['POST'])
def track_event():
    try:
        if not is_trusted_origin():
            return jsonify({'ok': False}), 403

        data = request.get_json(silent=True) or {}
        event_type = (data.get('event') or '').strip()[:50]
        if not event_type:
            return jsonify({'ok': False}), 400

        user_id    = session.get('user_id')
        session_id = (data.get('session_id') or '')[:64]
        page       = (data.get('page') or '')[:255]
        metadata   = data.get('metadata') or {}
        if not isinstance(metadata, dict):
            metadata = {}

        # Hash IP for privacy
        raw_ip  = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        ip_hash = hashlib.sha256(raw_ip.encode()).hexdigest()[:64]

        conn = cur = None
        try:
            conn = get_db()
            cur  = conn.cursor()
            cur.execute('''
                INSERT INTO user_events (user_id, session_id, event_type, page, metadata, ip_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user_id, session_id, event_type, page, json.dumps(metadata), ip_hash))
            conn.commit()
        finally:
            if cur:  cur.close()
            if conn: conn.close()

        return jsonify({'ok': True})
    except Exception:
        return jsonify({'ok': False}), 500


# ─────────────────────────────────────────────
# GET /admin/analytics  — analytics dashboard
# ─────────────────────────────────────────────
@analytics_bp.route('/admin/analytics')
@admin_required
def analytics_page():
    return render_template('admin_analytics.html')


# ─────────────────────────────────────────────
# GET /api/admin/analytics/data  — JSON data
# ─────────────────────────────────────────────
@analytics_bp.route('/api/admin/analytics/data')
@admin_required
def analytics_data():
    days  = min(int(request.args.get('days', 7)), 90)
    conn  = cur = None
    try:
        conn = get_db()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Summary counts
        cur.execute('''
            SELECT
                COUNT(DISTINCT CASE WHEN e.event_type = 'page_view'       THEN e.session_id END) AS sessions,
                COUNT(DISTINCT e.user_id)                                                          AS active_users,
                COUNT(*)                                                                           AS total_events,
                COUNT(DISTINCT CASE WHEN e.event_type = 'add_to_cart'     THEN e.user_id END)     AS cart_users,
                COUNT(DISTINCT CASE WHEN e.event_type = 'checkout_start'  THEN e.user_id END)     AS checkout_users,
                COUNT(DISTINCT CASE WHEN e.event_type = 'checkout_complete' THEN e.user_id END)   AS buyers
            FROM user_events e
            WHERE e.created_at >= NOW() - INTERVAL %s
              AND e.user_id IS NOT NULL
        ''', (f'{days} days',))
        summary = dict(cur.fetchone() or {})

        # Total registered members
        cur.execute("SELECT COUNT(*) AS total FROM users WHERE role_id != 1")
        summary['total_members'] = (cur.fetchone() or {}).get('total', 0)

        # 2. Events per day (sparkline)
        cur.execute('''
            SELECT DATE(created_at) AS day, COUNT(*) AS cnt
            FROM user_events
            WHERE created_at >= NOW() - INTERVAL %s
            GROUP BY day ORDER BY day
        ''', (f'{days} days',))
        daily = [dict(r) for r in cur.fetchall()]

        # 3. Top pages
        cur.execute('''
            SELECT page, COUNT(*) AS views, COUNT(DISTINCT session_id) AS sessions
            FROM user_events
            WHERE event_type = 'page_view'
              AND created_at >= NOW() - INTERVAL %s
              AND page IS NOT NULL AND page != ''
            GROUP BY page ORDER BY views DESC LIMIT 10
        ''', (f'{days} days',))
        top_pages = [dict(r) for r in cur.fetchall()]

        # 4. Top products viewed
        cur.execute('''
            SELECT metadata->>'product_name' AS product, COUNT(*) AS views
            FROM user_events
            WHERE event_type = 'product_view'
              AND created_at >= NOW() - INTERVAL %s
              AND metadata->>'product_name' IS NOT NULL
            GROUP BY product ORDER BY views DESC LIMIT 10
        ''', (f'{days} days',))
        top_products = [dict(r) for r in cur.fetchall()]

        # 5. Event type breakdown
        cur.execute('''
            SELECT event_type, COUNT(*) AS cnt
            FROM user_events
            WHERE created_at >= NOW() - INTERVAL %s
            GROUP BY event_type ORDER BY cnt DESC
        ''', (f'{days} days',))
        event_breakdown = [dict(r) for r in cur.fetchall()]

        # 6. Recent active users (last 50 events with user info)
        cur.execute('''
            SELECT e.user_id, u.full_name, u.username, u.reseller_tier,
                   e.event_type, e.page, e.metadata, e.created_at
            FROM user_events e
            LEFT JOIN users u ON u.id = e.user_id
            WHERE e.user_id IS NOT NULL
              AND e.created_at >= NOW() - INTERVAL %s
            ORDER BY e.created_at DESC LIMIT 60
        ''', (f'{days} days',))
        recent = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('created_at'):
                row['created_at'] = row['created_at'].isoformat()
            recent.append(row)

        # 7. Per-user funnel
        cur.execute('''
            SELECT
                u.id, u.full_name, u.username, u.reseller_tier,
                MAX(e.created_at)                                                       AS last_seen,
                COUNT(DISTINCT CASE WHEN e.event_type='page_view' THEN e.id END)       AS page_views,
                COUNT(DISTINCT CASE WHEN e.event_type='product_view' THEN e.id END)    AS product_views,
                COUNT(DISTINCT CASE WHEN e.event_type='add_to_cart' THEN e.id END)     AS cart_adds,
                COUNT(DISTINCT CASE WHEN e.event_type='checkout_start' THEN e.id END)  AS checkout_starts,
                COUNT(DISTINCT CASE WHEN e.event_type='search' THEN e.id END)          AS searches
            FROM users u
            JOIN user_events e ON e.user_id = u.id
            WHERE e.created_at >= NOW() - INTERVAL %s
            GROUP BY u.id, u.full_name, u.username, u.reseller_tier
            ORDER BY last_seen DESC LIMIT 30
        ''', (f'{days} days',))
        user_funnel = []
        for r in cur.fetchall():
            row = dict(r)
            if row.get('last_seen'):
                row['last_seen'] = row['last_seen'].isoformat()
            user_funnel.append(row)

        return jsonify({
            'summary': summary,
            'daily': daily,
            'top_pages': top_pages,
            'top_products': top_products,
            'event_breakdown': event_breakdown,
            'recent': recent,
            'user_funnel': user_funnel,
            'days': days
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cur:  cur.close()
        if conn: conn.close()
