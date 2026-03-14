from flask import Blueprint, request, jsonify
from database import get_db
from utils import login_required, admin_required, handle_error
import psycopg2.extras
from decimal import Decimal
import datetime

product_analytics_bp = Blueprint('product_analytics', __name__)


def _serialize(obj):
    """Recursively convert non-JSON-serializable types in a dict/list."""
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


@product_analytics_bp.route('/api/product-views/track', methods=['POST'])
def track_product_view():
    """Track when a visitor opens a product detail modal"""
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    if not product_id:
        return jsonify({'error': 'product_id required'}), 400

    session_id   = data.get('session_id')
    utm_campaign = data.get('utm_campaign') or None
    utm_medium   = data.get('utm_medium') or None
    referrer     = data.get('referrer') or None
    traffic_type = data.get('traffic_type') or None
    visitor_ip   = (request.headers.get('X-Forwarded-For', '') or '').split(',')[0].strip() or request.remote_addr
    user_agent   = request.headers.get('User-Agent', '')[:512]

    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO product_views
                (product_id, session_id, visitor_ip, user_agent,
                 utm_campaign, utm_medium, referrer, traffic_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (product_id, session_id, visitor_ip, user_agent,
              utm_campaign, utm_medium, referrer, traffic_type))
        conn.commit()
        return jsonify({'ok': True}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@product_analytics_bp.route('/api/product-analytics/summary', methods=['GET'])
@login_required
@admin_required
def get_product_analytics_summary():
    """Summary stats: total views, unique products, sessions, paid sessions, top campaigns"""
    days = int(request.args.get('days', 30))
    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT
                COUNT(*)                                                       AS total_views,
                COUNT(DISTINCT product_id)                                     AS unique_products,
                COUNT(DISTINCT session_id)                                     AS unique_sessions,
                COUNT(DISTINCT CASE WHEN utm_campaign IS NOT NULL THEN session_id END) AS paid_sessions
            FROM product_views
            WHERE viewed_at >= NOW() - INTERVAL '%s days'
        ''', (days,))
        summary = _serialize(dict(cursor.fetchone() or {}))

        cursor.execute('''
            SELECT utm_campaign, COUNT(*) AS views
            FROM product_views
            WHERE viewed_at >= NOW() - INTERVAL '%s days'
              AND utm_campaign IS NOT NULL
            GROUP BY utm_campaign
            ORDER BY views DESC
            LIMIT 10
        ''', (days,))
        summary['top_campaigns'] = _serialize([dict(r) for r in cursor.fetchall()])

        return jsonify(summary), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@product_analytics_bp.route('/api/product-analytics/top-products', methods=['GET'])
@login_required
@admin_required
def get_top_products():
    """Top products by view count with order count and conversion rate"""
    days     = int(request.args.get('days', 30))
    limit    = min(int(request.args.get('limit', 50)), 200)
    campaign = request.args.get('campaign', '').strip() or None

    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if campaign:
            cursor.execute('''
                SELECT
                    p.id,
                    p.name,
                    p.product_type,
                    pi.image_url,
                    COUNT(pv.id)                                            AS views,
                    COUNT(DISTINCT pv.session_id)                           AS unique_viewers,
                    COUNT(DISTINCT oi.order_id)                             AS orders,
                    CASE WHEN COUNT(DISTINCT pv.session_id) > 0
                         THEN ROUND(COUNT(DISTINCT oi.order_id)::NUMERIC
                                    / COUNT(DISTINCT pv.session_id) * 100, 1)
                         ELSE 0 END                                         AS conversion_pct
                FROM product_views pv
                JOIN products p ON p.id = pv.product_id
                LEFT JOIN (
                    SELECT DISTINCT ON (product_id) product_id, image_url
                    FROM product_images ORDER BY product_id, id ASC
                ) pi ON pi.product_id = p.id
                LEFT JOIN order_items oi ON oi.product_id = p.id
                    AND oi.created_at >= NOW() - INTERVAL '%s days'
                WHERE pv.viewed_at >= NOW() - INTERVAL '%s days'
                  AND pv.utm_campaign = %s
                GROUP BY p.id, p.name, p.product_type, pi.image_url
                ORDER BY views DESC
                LIMIT %s
            ''', (days, days, campaign, limit))
        else:
            cursor.execute('''
                SELECT
                    p.id,
                    p.name,
                    p.product_type,
                    pi.image_url,
                    COUNT(pv.id)                                            AS views,
                    COUNT(DISTINCT pv.session_id)                           AS unique_viewers,
                    COUNT(DISTINCT oi.order_id)                             AS orders,
                    CASE WHEN COUNT(DISTINCT pv.session_id) > 0
                         THEN ROUND(COUNT(DISTINCT oi.order_id)::NUMERIC
                                    / COUNT(DISTINCT pv.session_id) * 100, 1)
                         ELSE 0 END                                         AS conversion_pct
                FROM product_views pv
                JOIN products p ON p.id = pv.product_id
                LEFT JOIN (
                    SELECT DISTINCT ON (product_id) product_id, image_url
                    FROM product_images ORDER BY product_id, id ASC
                ) pi ON pi.product_id = p.id
                LEFT JOIN order_items oi ON oi.product_id = p.id
                    AND oi.created_at >= NOW() - INTERVAL '%s days'
                WHERE pv.viewed_at >= NOW() - INTERVAL '%s days'
                GROUP BY p.id, p.name, p.product_type, pi.image_url
                ORDER BY views DESC
                LIMIT %s
            ''', (days, days, limit))

        rows = _serialize([dict(r) for r in cursor.fetchall()])
        return jsonify(rows), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@product_analytics_bp.route('/api/product-analytics/daily-trend', methods=['GET'])
@login_required
@admin_required
def get_daily_trend():
    """Daily view counts for the past N days"""
    days     = int(request.args.get('days', 30))
    campaign = request.args.get('campaign', '').strip() or None

    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if campaign:
            cursor.execute('''
                SELECT
                    TO_CHAR(viewed_at AT TIME ZONE 'Asia/Bangkok', 'YYYY-MM-DD') AS day,
                    COUNT(*)                                                       AS views,
                    COUNT(DISTINCT session_id)                                     AS unique_viewers
                FROM product_views
                WHERE viewed_at >= NOW() - INTERVAL '%s days'
                  AND utm_campaign = %s
                GROUP BY day
                ORDER BY day
            ''', (days, campaign))
        else:
            cursor.execute('''
                SELECT
                    TO_CHAR(viewed_at AT TIME ZONE 'Asia/Bangkok', 'YYYY-MM-DD') AS day,
                    COUNT(*)                                                       AS views,
                    COUNT(DISTINCT session_id)                                     AS unique_viewers
                FROM product_views
                WHERE viewed_at >= NOW() - INTERVAL '%s days'
                GROUP BY day
                ORDER BY day
            ''', (days,))

        return jsonify(_serialize([dict(r) for r in cursor.fetchall()])), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@product_analytics_bp.route('/api/product-analytics/campaign-breakdown', methods=['GET'])
@login_required
@admin_required
def get_campaign_breakdown():
    """Views per campaign"""
    days  = int(request.args.get('days', 30))
    limit = min(int(request.args.get('limit', 20)), 100)

    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT
                COALESCE(utm_campaign, '(ไม่มี UTM)')  AS campaign,
                COUNT(*)                                AS views,
                COUNT(DISTINCT product_id)              AS unique_products,
                COUNT(DISTINCT session_id)              AS unique_viewers
            FROM product_views
            WHERE viewed_at >= NOW() - INTERVAL '%s days'
            GROUP BY utm_campaign
            ORDER BY views DESC
            LIMIT %s
        ''', (days, limit))

        return jsonify(_serialize([dict(r) for r in cursor.fetchall()])), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()
