import os
import json
import logging
import psycopg2.extras
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, render_template

from database import get_db
from utils import handle_error, login_required, admin_required

facebook_ads_bp = Blueprint('facebook_ads', __name__)


# ==================== HELPERS ====================

def _classify_traffic(utm_source, utm_medium, fbclid, referrer):
    """Classify traffic into source label and traffic_type category."""
    from urllib.parse import urlparse
    s = (utm_source or '').lower().strip()
    m = (utm_medium or '').lower().strip()
    if fbclid or s in ('facebook', 'fb', 'ig', 'instagram'):
        return 'facebook', 'facebook_ad'
    if s == 'google' and m in ('cpc', 'paid', 'ppc'):
        return 'google_ads', 'paid_search'
    if m in ('cpc', 'paid', 'ppc', 'banner', 'display', 'paidsocial'):
        return s or 'paid', 'paid_other'
    if s in ('email', 'sms', 'line_official', 'newsletter'):
        return s, 'crm'
    if s and s not in ('', 'direct'):
        return s, 'utm_other'
    if referrer:
        try:
            domain = urlparse(referrer).netloc.lower()
            if 'google.' in domain:
                return 'google', 'organic_search'
            if any(d in domain for d in ('bing.', 'yahoo.', 'duckduckgo.')):
                return 'organic_search', 'organic_search'
            if 'facebook.' in domain or 'fb.' in domain:
                return 'facebook', 'organic_social'
            if 'instagram.' in domain:
                return 'instagram', 'organic_social'
            if 'line.' in domain:
                return 'line', 'organic_social'
            if 'tiktok.' in domain:
                return 'tiktok', 'organic_social'
            if 'youtube.' in domain:
                return 'youtube', 'organic_social'
            if 'twitter.' in domain or 'x.com' in domain:
                return 'twitter', 'organic_social'
            return 'referral', 'referral'
        except Exception:
            return 'referral', 'referral'
    return 'direct', 'direct'


def _get_meta_credentials(cursor):
    """Get Meta API credentials: prefer DB, fallback to env vars."""
    cursor.execute('SELECT meta_access_token, meta_ad_account_id FROM facebook_pixel_settings LIMIT 1')
    row = cursor.fetchone()
    token = (row['meta_access_token'] if row else None) or os.environ.get('META_ACCESS_TOKEN', '')
    account_id = (row['meta_ad_account_id'] if row else None) or os.environ.get('META_AD_ACCOUNT_ID', '')
    return token.strip() if token else '', account_id.strip() if account_id else ''


# ==================== ADMIN PAGE ====================

@facebook_ads_bp.route('/admin/facebook-ads')
@login_required
@admin_required
def admin_facebook_ads_page():
    user_role = session.get('role', 'admin')
    return render_template('admin_facebook_ads.html', user_role=user_role)


# ==================== FACEBOOK PIXEL SETTINGS API ====================

@facebook_ads_bp.route('/api/facebook-pixel-settings', methods=['GET'])
@admin_required
def get_facebook_pixel_settings():
    """Get Facebook Pixel settings"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT id, pixel_id, access_token, is_active,
                   track_page_view, track_lead, track_complete_registration, updated_at
            FROM facebook_pixel_settings
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        if settings:
            if settings.get('access_token'):
                settings['access_token_masked'] = settings['access_token'][:10] + '...' if len(settings['access_token']) > 10 else settings['access_token']
            return jsonify(dict(settings)), 200
        return jsonify({}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-pixel-settings', methods=['POST'])
@admin_required
def save_facebook_pixel_settings():
    """Save Facebook Pixel settings"""
    conn = None
    cursor = None
    try:
        data = request.get_json()
        pixel_id = data.get('pixel_id', '').strip()
        access_token = data.get('access_token', '').strip()
        is_active = data.get('is_active', False)
        track_page_view = data.get('track_page_view', True)
        track_lead = data.get('track_lead', True)
        track_complete_registration = data.get('track_complete_registration', True)

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT id, access_token FROM facebook_pixel_settings LIMIT 1')
        existing = cursor.fetchone()

        if not access_token and existing and existing.get('access_token'):
            access_token = existing['access_token']

        if existing:
            cursor.execute('''
                UPDATE facebook_pixel_settings
                SET pixel_id = %s, access_token = %s, is_active = %s,
                    track_page_view = %s, track_lead = %s, track_complete_registration = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, pixel_id, is_active, track_page_view, track_lead, track_complete_registration
            ''', (pixel_id, access_token, is_active, track_page_view, track_lead,
                  track_complete_registration, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO facebook_pixel_settings (pixel_id, access_token, is_active, track_page_view, track_lead, track_complete_registration)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, pixel_id, is_active, track_page_view, track_lead, track_complete_registration
            ''', (pixel_id, access_token, is_active, track_page_view, track_lead, track_complete_registration))

        settings = dict(cursor.fetchone())
        conn.commit()
        return jsonify({'message': 'บันทึกการตั้งค่า Facebook Pixel สำเร็จ', 'settings': settings}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-pixel-settings/public', methods=['GET'])
def get_facebook_pixel_public():
    """Get Facebook Pixel ID for frontend (public endpoint)"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('''
            SELECT pixel_id, track_page_view, track_lead, track_complete_registration
            FROM facebook_pixel_settings
            WHERE is_active = TRUE
            LIMIT 1
        ''')
        settings = cursor.fetchone()
        if settings and settings.get('pixel_id'):
            return jsonify(dict(settings)), 200
        return jsonify({}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== PAGE VISITS TRACKING API ====================

@facebook_ads_bp.route('/api/track-visit', methods=['POST'])
def track_page_visit():
    """Track a page visit with traffic classification"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        page_name = data.get('page_name', 'unknown')
        utm_source = data.get('utm_source') or data.get('source', '')
        utm_campaign = data.get('utm_campaign') or None
        utm_medium = data.get('utm_medium') or None
        fbclid = data.get('fbclid') or None
        referrer = (data.get('referrer') or '')[:500]

        source, traffic_type = _classify_traffic(utm_source, utm_medium, fbclid, referrer)

        visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if visitor_ip:
            visitor_ip = visitor_ip.split(',')[0].strip()
        user_agent = request.headers.get('User-Agent', '')[:500]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO page_visits (page_name, source, visitor_ip, user_agent, utm_campaign, utm_medium, referrer, traffic_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (page_name, source, visitor_ip, user_agent, utm_campaign, utm_medium,
              referrer or None, traffic_type))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/track-event', methods=['POST'])
def track_conversion_event():
    """Track conversion funnel events (chatbot_open, register_click, register_complete, etc.)"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        event_type = data.get('event_type', '')
        if not event_type:
            return jsonify({'error': 'Missing event_type'}), 400
        valid_events = {'catalog_view', 'chatbot_open', 'register_click', 'register_complete', 'first_order'}
        if event_type not in valid_events:
            return jsonify({'error': 'Invalid event_type'}), 400

        visitor_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if visitor_ip:
            visitor_ip = visitor_ip.split(',')[0].strip()

        utm_source = data.get('utm_source') or data.get('source', '')
        utm_campaign = data.get('utm_campaign') or None
        utm_medium = data.get('utm_medium') or None
        fbclid = data.get('fbclid') or None
        referrer = (data.get('referrer') or '')[:500]
        session_id = data.get('session_id') or ''
        user_agent = request.headers.get('User-Agent', '')[:500]

        source, traffic_type = _classify_traffic(utm_source, utm_medium, fbclid, referrer)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversion_events (session_id, event_type, source, traffic_type, utm_campaign, visitor_ip, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (session_id or None, event_type, source, traffic_type, utm_campaign, visitor_ip, user_agent))
        conn.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== FACEBOOK ADS STATS API ====================

@facebook_ads_bp.route('/api/facebook-ads/stats', methods=['GET'])
@login_required
@admin_required
def get_facebook_ads_stats():
    """Get Facebook Ads statistics for admin dashboard"""
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_registrations = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_registrations = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_registrations = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
        ''')
        total_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
        ''')
        total_registrations = cursor.fetchone()['count']

        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        daily_visits = {str(row['date']): row['visits'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as registrations
            FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        ''')
        daily_registrations = {str(row['date']): row['registrations'] for row in cursor.fetchall()}

        chart_labels = []
        chart_visits = []
        chart_registrations = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            chart_labels.append((datetime.now() - timedelta(days=i)).strftime('%d/%m'))
            chart_visits.append(daily_visits.get(date, 0))
            chart_registrations.append(daily_registrations.get(date, 0))

        cursor.execute('''
            SELECT
                COALESCE(utm_campaign, '(ไม่ระบุแคมเปญ)') as campaign,
                COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook'
            GROUP BY utm_campaign
            ORDER BY visits DESC
            LIMIT 20
        ''')
        campaigns_raw = cursor.fetchall()
        campaign_breakdown = [{'campaign': r['campaign'], 'visits': r['visits']} for r in campaigns_raw]

        cursor.execute('''
            SELECT u.id, u.full_name, u.username, u.created_at, u.is_approved,
                   rt.name as tier_name
            FROM users u
            LEFT JOIN reseller_tiers rt ON u.reseller_tier_id = rt.id
            WHERE u.notes LIKE '%[source: facebook]%'
            ORDER BY u.created_at DESC
            LIMIT 10
        ''')
        recent_registrations = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            'today': {
                'visits': today_visits,
                'registrations': today_registrations,
                'conversion': round((today_registrations / today_visits * 100) if today_visits > 0 else 0, 1)
            },
            'week': {
                'visits': week_visits,
                'registrations': week_registrations,
                'conversion': round((week_registrations / week_visits * 100) if week_visits > 0 else 0, 1)
            },
            'month': {
                'visits': month_visits,
                'registrations': month_registrations,
                'conversion': round((month_registrations / month_visits * 100) if month_visits > 0 else 0, 1)
            },
            'total': {
                'visits': total_visits,
                'registrations': total_registrations,
                'conversion': round((total_registrations / total_visits * 100) if total_visits > 0 else 0, 1)
            },
            'chart': {
                'labels': chart_labels,
                'visits': chart_visits,
                'registrations': chart_registrations
            },
            'recent_registrations': recent_registrations,
            'campaign_breakdown': campaign_breakdown
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/campaign-detail', methods=['GET'])
@login_required
@admin_required
def get_campaign_detail():
    """Get detailed stats for a single Facebook Ads campaign"""
    conn = None
    cursor = None
    try:
        campaign = request.args.get('campaign', '')
        if not campaign:
            return jsonify({'error': 'Missing campaign'}), 400

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        where_campaign = "utm_campaign = %s" if campaign != '(ไม่ระบุแคมเปญ)' else "utm_campaign IS NULL"
        params_base = (campaign,) if campaign != '(ไม่ระบุแคมเปญ)' else ()
        page_filter = "page_name IN ('become-reseller','catalog') AND source = 'facebook'"

        cursor.execute(f'''
            SELECT COUNT(*) as cnt, MIN(created_at) as first_visit, MAX(created_at) as last_visit
            FROM page_visits WHERE {page_filter} AND {where_campaign}
        ''', params_base)
        row = cursor.fetchone()
        total_visits = row['cnt']
        date_first = row['first_visit']
        date_last = row['last_visit']
        duration_days = (date_last.date() - date_first.date()).days + 1 if date_first and date_last else 0

        cursor.execute(f'''
            SELECT DATE(created_at) as d, COUNT(*) as visits
            FROM page_visits
            WHERE {page_filter} AND {where_campaign}
            AND created_at >= CURRENT_DATE - INTERVAL '13 days'
            GROUP BY DATE(created_at) ORDER BY d
        ''', params_base)
        daily_raw = {str(r['d']): r['visits'] for r in cursor.fetchall()}
        trend_labels, trend_visits = [], []
        for i in range(13, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            trend_labels.append((datetime.now() - timedelta(days=i)).strftime('%d/%m'))
            trend_visits.append(daily_raw.get(d, 0))

        cursor.execute(f'''
            SELECT user_agent FROM page_visits
            WHERE {page_filter} AND {where_campaign} AND user_agent IS NOT NULL
        ''', params_base)
        agents = [r['user_agent'] for r in cursor.fetchall()]
        mobile_kw = ('mobile', 'android', 'iphone', 'ipad', 'ipod')
        mobile = sum(1 for a in agents if any(k in a.lower() for k in mobile_kw))
        desktop = len(agents) - mobile
        mobile_pct = round(mobile / len(agents) * 100) if agents else 0

        cursor.execute(f'''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr, COUNT(*) as cnt
            FROM page_visits
            WHERE {page_filter} AND {where_campaign}
            GROUP BY hr ORDER BY cnt DESC LIMIT 3
        ''', params_base)
        peak_hours = [{'hour': int(r['hr']), 'count': r['cnt']} for r in cursor.fetchall()]

        cursor.execute(f'''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr, COUNT(*) as cnt
            FROM page_visits WHERE {page_filter} AND {where_campaign}
            GROUP BY hr ORDER BY hr
        ''', params_base)
        hour_raw = {int(r['hr']): r['cnt'] for r in cursor.fetchall()}
        hour_dist = [hour_raw.get(h, 0) for h in range(24)]

        return jsonify({
            'campaign': campaign,
            'total_visits': total_visits,
            'date_first': str(date_first.date()) if date_first else None,
            'date_last': str(date_last.date()) if date_last else None,
            'duration_days': duration_days,
            'trend': {'labels': trend_labels, 'visits': trend_visits},
            'device': {'mobile': mobile, 'desktop': desktop, 'mobile_pct': mobile_pct},
            'peak_hours': peak_hours,
            'hour_dist': hour_dist
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/traffic-sources', methods=['GET'])
@login_required
@admin_required
def get_traffic_sources():
    """Phase 2A: Traffic source breakdown (organic vs paid vs direct vs referral)"""
    conn = None
    cursor = None
    try:
        period = request.args.get('period', 'total')
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if period == 'today':
            date_filter = "AND created_at >= CURRENT_DATE"
        elif period == 'week':
            date_filter = "AND created_at >= CURRENT_DATE - INTERVAL '6 days'"
        elif period == 'month':
            date_filter = "AND created_at >= DATE_TRUNC('month', CURRENT_DATE)"
        else:
            date_filter = ""

        cursor.execute(f'''
            SELECT
                COALESCE(traffic_type, 'direct') as type,
                COALESCE(source, 'direct') as source,
                COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller') {date_filter}
            GROUP BY traffic_type, source
            ORDER BY visits DESC
        ''')
        raw = cursor.fetchall()

        categories = {
            'facebook_ad': {'label': 'Facebook Ads', 'color': '#1877f2', 'visits': 0, 'sources': []},
            'paid_search': {'label': 'Google Ads', 'color': '#fbbc04', 'visits': 0, 'sources': []},
            'paid_other': {'label': 'โฆษณาอื่นๆ', 'color': '#ff9500', 'visits': 0, 'sources': []},
            'organic_search': {'label': 'Organic Search', 'color': '#34c759', 'visits': 0, 'sources': []},
            'organic_social': {'label': 'Organic Social', 'color': '#5856d6', 'visits': 0, 'sources': []},
            'direct': {'label': 'Direct / ไม่ทราบที่มา', 'color': '#8e8e93', 'visits': 0, 'sources': []},
            'referral': {'label': 'Referral', 'color': '#ff2d55', 'visits': 0, 'sources': []},
            'crm': {'label': 'Email / LINE', 'color': '#00c7be', 'visits': 0, 'sources': []},
            'utm_other': {'label': 'UTM อื่นๆ', 'color': '#af52de', 'visits': 0, 'sources': []},
        }
        for r in raw:
            t = r['type'] if r['type'] in categories else 'utm_other'
            categories[t]['visits'] += r['visits']
            categories[t]['sources'].append({'source': r['source'], 'visits': r['visits']})

        result = [dict(type=k, **v) for k, v in categories.items() if v['visits'] > 0]
        result.sort(key=lambda x: x['visits'], reverse=True)
        total = sum(r['visits'] for r in result)
        for r in result:
            r['pct'] = round(r['visits'] / total * 100) if total else 0

        cursor.execute('''
            SELECT DATE(created_at) as d,
                   COALESCE(traffic_type,'direct') as type,
                   COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller')
            AND created_at >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY d, traffic_type ORDER BY d
        ''')
        daily_data = {}
        for r in cursor.fetchall():
            ds = str(r['d'])
            t = r['type']
            if ds not in daily_data: daily_data[ds] = {}
            daily_data[ds][t] = r['visits']
        labels = [(datetime.now() - timedelta(days=i)).strftime('%d/%m') for i in range(29, -1, -1)]
        dates_keys = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]

        return jsonify({
            'breakdown': result,
            'total': total,
            'chart': {'labels': labels, 'dates': dates_keys, 'raw': daily_data}
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/funnel', methods=['GET'])
@login_required
@admin_required
def get_funnel_stats():
    """Phase 2C: Conversion funnel stats"""
    conn = None
    cursor = None
    try:
        period = request.args.get('period', 'total')
        campaign = request.args.get('campaign', None)
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if period == 'today':
            date_filter = "AND created_at >= CURRENT_DATE"
        elif period == 'week':
            date_filter = "AND created_at >= CURRENT_DATE - INTERVAL '6 days'"
        elif period == 'month':
            date_filter = "AND created_at >= DATE_TRUNC('month', CURRENT_DATE)"
        else:
            date_filter = ""

        camp_filter = ""
        camp_params = []
        if campaign:
            camp_filter = "AND utm_campaign = %s"
            camp_params = [campaign]

        steps = ['catalog_view', 'chatbot_open', 'register_click', 'register_complete']
        funnel = {}
        for step in steps:
            cursor.execute(f'''
                SELECT COUNT(DISTINCT COALESCE(session_id, visitor_ip)) as cnt
                FROM conversion_events
                WHERE event_type = %s {date_filter} {camp_filter}
            ''', [step] + camp_params)
            r = cursor.fetchone()
            funnel[step] = r['cnt'] if r else 0

        if funnel['catalog_view'] == 0:
            cursor.execute(f'''
                SELECT COUNT(*) as cnt FROM page_visits
                WHERE page_name IN ('catalog','become-reseller') {date_filter}
                {('AND utm_campaign = %s' if campaign else '')}
            ''', camp_params)
            r = cursor.fetchone()
            funnel['catalog_view'] = r['cnt'] if r else 0

        cursor.execute(f'''
            SELECT source, event_type, COUNT(DISTINCT COALESCE(session_id, visitor_ip)) as cnt
            FROM conversion_events
            WHERE event_type IN ('catalog_view','register_complete') {date_filter}
            GROUP BY source, event_type ORDER BY cnt DESC
        ''')
        by_source = {}
        for r in cursor.fetchall():
            s = r['source']
            if s not in by_source: by_source[s] = {}
            by_source[s][r['event_type']] = r['cnt']

        source_funnel = []
        for s, data in by_source.items():
            views = data.get('catalog_view', 0)
            regs = data.get('register_complete', 0)
            source_funnel.append({
                'source': s, 'views': views, 'registrations': regs,
                'conversion': round(regs / views * 100, 1) if views else 0
            })
        source_funnel.sort(key=lambda x: x['views'], reverse=True)

        steps_meta = [
            {'key': 'catalog_view', 'label': '👁 เข้าชม Catalog'},
            {'key': 'chatbot_open', 'label': '💬 เปิด Chatbot'},
            {'key': 'register_click', 'label': '👆 คลิกสมัคร'},
            {'key': 'register_complete', 'label': '✅ สมัครสำเร็จ'},
        ]
        top = funnel.get('catalog_view', 1) or 1
        steps_data = [{
            **m,
            'count': funnel.get(m['key'], 0),
            'pct': round(funnel.get(m['key'], 0) / top * 100) if top else 0
        } for m in steps_meta]

        return jsonify({'funnel': steps_data, 'by_source': source_funnel}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== AI ANALYSIS API ====================

@facebook_ads_bp.route('/api/facebook-ads/ai-analysis', methods=['GET'])
@login_required
@admin_required
def fb_ai_analysis():
    """Phase 2B: AI campaign analysis using Gemini"""
    conn = None
    cursor = None
    try:
        from google import genai as _g
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({'error': 'ไม่มี Gemini API Key'}), 503

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT utm_campaign, COUNT(*) as visits,
                   ROUND(AVG(EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok'))) as avg_hour,
                   COUNT(CASE WHEN user_agent ~* 'mobile|android|iphone|ipad' THEN 1 END)::float / NULLIF(COUNT(*),0) * 100 as mobile_pct
            FROM page_visits
            WHERE source = 'facebook' AND utm_campaign IS NOT NULL
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY utm_campaign ORDER BY visits DESC LIMIT 10
        ''')
        campaigns = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
            SELECT traffic_type, COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller')
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY traffic_type ORDER BY visits DESC
        ''')
        traffic_types = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr, COUNT(*) as cnt
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller')
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY hr ORDER BY cnt DESC LIMIT 5
        ''')
        peak_hours = [dict(r) for r in cursor.fetchall()]

        prompt = f"""คุณเป็น Digital Marketing Analyst ผู้เชี่ยวชาญ e-commerce ไทย
วิเคราะห์ข้อมูลโฆษณาร้านขายชุดพยาบาล EKG Shops นี้ และให้คำแนะนำเป็นภาษาไทยที่กระชับ ตรงประเด็น

ข้อมูลแคมเปญ Facebook (30 วันล่าสุด):
{campaigns}

การแบ่งประเภท traffic:
{traffic_types}

ชั่วโมงที่มี traffic สูงสุด:
{peak_hours}

กรุณาตอบในรูปแบบ JSON ดังนี้ (ตอบ JSON เท่านั้น ไม่มีข้อความอื่น):
{{
  "summary": "สรุปภาพรวม 2-3 ประโยค",
  "top_insight": "insight สำคัญที่สุด 1 ข้อ",
  "recommendations": ["คำแนะนำข้อ 1", "คำแนะนำข้อ 2", "คำแนะนำข้อ 3"],
  "best_time": "ช่วงเวลาที่ดีที่สุดในการยิงโฆษณา",
  "score": 75
}}
score คือคะแนนภาพรวมประสิทธิภาพ 0-100"""

        client = _g.Client(api_key=gemini_key)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        import json as _json
        result = _json.loads(text.strip())
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/ai-copy', methods=['POST'])
@login_required
@admin_required
def fb_ai_copy():
    """Phase 2B: AI ad copy generator"""
    try:
        from google import genai as _g
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({'error': 'ไม่มี Gemini API Key'}), 503

        data = request.get_json(silent=True) or {}
        product = data.get('product', 'ชุดพยาบาล EKG')
        tone = data.get('tone', 'friendly')
        goal = data.get('goal', 'สมัครสมาชิก')
        campaign = data.get('campaign', '')

        tone_map = {
            'friendly': 'เป็นกันเอง สบายๆ',
            'professional': 'มืออาชีพ น่าเชื่อถือ',
            'urgent': 'สร้างความเร่งด่วน มี deadline'
        }
        tone_desc = tone_map.get(tone, tone_map['friendly'])

        prompt = f"""คุณเป็น Copywriter มืออาชีพ เชี่ยวชาญ Facebook Ads สำหรับ e-commerce ไทย
สร้าง Facebook Ad Copy สำหรับร้าน EKG Shops (ขายชุดพยาบาลคุณภาพสูง ราคาพิเศษสำหรับ reseller)

สินค้า/แคมเปญ: {product} {('(' + campaign + ')' if campaign else '')}
โทน: {tone_desc}
เป้าหมาย: {goal}

ตอบเป็น JSON เท่านั้น:
{{
  "headline": "หัวข้อโฆษณา (ไม่เกิน 40 ตัวอักษร)",
  "primary_text": "เนื้อหาหลัก 3-4 ประโยค มี emoji เหมาะสม",
  "cta": "call-to-action สั้นๆ",
  "hashtags": ["#แฮชแท็ก1", "#แฮชแท็ก2", "#แฮชแท็ก3"],
  "tip": "เคล็ดลับการใช้ copy นี้ให้ได้ผล"
}}"""

        client = _g.Client(api_key=gemini_key)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        import json as _json
        result = _json.loads(text.strip())
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@facebook_ads_bp.route('/api/facebook-ads/ai-timing', methods=['GET'])
@login_required
@admin_required
def fb_ai_timing():
    """Phase 2B: AI timing recommendations"""
    conn = None
    cursor = None
    try:
        from google import genai as _g
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({'error': 'ไม่มี Gemini API Key'}), 503

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute('''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr,
                   TO_CHAR(created_at AT TIME ZONE 'Asia/Bangkok', 'Day') as dow,
                   COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller')
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY hr, dow ORDER BY visits DESC
        ''')
        hour_dow = [{'hr': int(r['hr']), 'dow': r['dow'].strip(), 'visits': r['visits']} for r in cursor.fetchall()]

        cursor.execute('''
            SELECT EXTRACT(DOW FROM created_at AT TIME ZONE 'Asia/Bangkok') as dow_num,
                   TO_CHAR(created_at AT TIME ZONE 'Asia/Bangkok', 'Day') as dow,
                   COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('catalog','become-reseller')
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY dow_num, dow ORDER BY dow_num
        ''')
        by_dow = [{'dow': r['dow'].strip(), 'visits': r['visits']} for r in cursor.fetchall()]

        prompt = f"""คุณเป็น Data Analyst สำหรับ Facebook Ads
วิเคราะห์ข้อมูลเวลาของร้านชุดพยาบาล EKG Shops และแนะนำเวลาที่ดีที่สุดในการยิงโฆษณา

ข้อมูล Hour x Day of Week (visits):
{hour_dow[:20]}

ยอด visit รายวัน:
{by_dow}

ตอบ JSON เท่านั้น:
{{
  "best_hours": [20, 21, 22],
  "best_days": ["วันจันทร์", "วันอังคาร"],
  "avoid_hours": [2, 3, 4],
  "schedule_suggestion": "คำแนะนำการตั้ง Ad Schedule 2-3 ประโยค",
  "budget_tip": "เคล็ดลับการจัดสรร budget ตามเวลา"
}}"""

        client = _g.Client(api_key=gemini_key)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        import json as _json
        result = _json.loads(text.strip())
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== FACEBOOK META API ====================

@facebook_ads_bp.route('/api/admin/facebook-ads/meta-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_meta_ads_settings():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if request.method == 'GET':
            token, account_id = _get_meta_credentials(cursor)
            masked = (token[:12] + '...' + token[-4:]) if len(token) > 16 else ('*' * len(token) if token else '')
            env_token = bool(os.environ.get('META_ACCESS_TOKEN'))
            env_account = bool(os.environ.get('META_AD_ACCOUNT_ID'))
            return jsonify({
                'meta_access_token_masked': masked,
                'meta_ad_account_id': account_id,
                'has_token': bool(token),
                'has_account': bool(account_id),
                'token_from_env': env_token,
                'account_from_env': env_account
            })
        else:
            data = request.get_json(silent=True) or {}
            new_token = (data.get('meta_access_token') or '').strip()
            new_account = (data.get('meta_ad_account_id') or '').strip()
            cursor.execute('SELECT id, meta_access_token FROM facebook_pixel_settings LIMIT 1')
            existing = cursor.fetchone()
            if not new_token and existing and existing.get('meta_access_token'):
                new_token = existing['meta_access_token']
            if existing:
                cursor.execute('''
                    UPDATE facebook_pixel_settings
                    SET meta_access_token = %s, meta_ad_account_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_token or None, new_account or None, existing['id']))
            else:
                cursor.execute('''
                    INSERT INTO facebook_pixel_settings (meta_access_token, meta_ad_account_id)
                    VALUES (%s, %s)
                ''', (new_token or None, new_account or None))
            conn.commit()
            return jsonify({'ok': True, 'message': 'บันทึกข้อมูล Meta API เรียบร้อย'})
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/admin/facebook-ads/meta-insights', methods=['GET'])
@login_required
@admin_required
def admin_meta_ads_insights():
    """Fetch real ad performance data from Meta Marketing API."""
    import urllib.request
    import urllib.parse
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        if not token or not account_id:
            return jsonify({'error': 'ยังไม่ได้ตั้งค่า Meta Access Token หรือ Ad Account ID'}), 400

        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'

        period = request.args.get('period', '30d')
        period_map = {'7d': 7, '30d': 30, '90d': 90}
        days = period_map.get(period, 30)
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        until = datetime.now().strftime('%Y-%m-%d')

        fields = 'impressions,clicks,spend,reach,cpm,cpc,ctr,actions,action_values'
        params = urllib.parse.urlencode({
            'fields': fields,
            'time_range': json.dumps({'since': since, 'until': until}),
            'level': 'account',
            'access_token': token
        })
        url = f'https://graph.facebook.com/v19.0/{account_id}/insights?{params}'

        req = urllib.request.Request(url, headers={'User-Agent': 'EKGShops/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode())

        data_rows = raw.get('data', [])
        if not data_rows:
            return jsonify({'ok': True, 'data': None, 'period': period, 'message': 'ยังไม่มีข้อมูลโฆษณาในช่วงเวลานี้'})

        row = data_rows[0]
        actions = {a['action_type']: float(a['value']) for a in (row.get('actions') or [])}
        action_values = {a['action_type']: float(a['value']) for a in (row.get('action_values') or [])}
        purchase_value = action_values.get('purchase', 0)
        purchase_count = int(actions.get('purchase', 0))
        spend = float(row.get('spend', 0))
        roas = round(purchase_value / spend, 2) if spend > 0 else 0

        return jsonify({
            'ok': True,
            'period': period,
            'since': since,
            'until': until,
            'data': {
                'impressions': int(row.get('impressions', 0)),
                'clicks': int(row.get('clicks', 0)),
                'spend': spend,
                'reach': int(row.get('reach', 0)),
                'cpm': float(row.get('cpm', 0)),
                'cpc': float(row.get('cpc', 0)),
                'ctr': float(row.get('ctr', 0)),
                'purchases': purchase_count,
                'purchase_value': purchase_value,
                'roas': roas
            }
        })
    except urllib.error.HTTPError as he:
        err_body = he.read().decode()
        try:
            err_json = json.loads(err_body)
            msg = err_json.get('error', {}).get('message', err_body)
        except Exception:
            msg = err_body
        return jsonify({'error': f'Meta API Error: {msg}'}), 400
    except urllib.error.URLError as ue:
        return jsonify({'error': f'ไม่สามารถเชื่อมต่อ Meta API: {ue.reason}'}), 503
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
