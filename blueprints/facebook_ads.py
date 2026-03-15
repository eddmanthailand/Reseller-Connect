import os
import json
import logging
import psycopg2.extras
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, render_template

from database import get_db
from utils import handle_error, login_required, admin_required

facebook_ads_bp = Blueprint('facebook_ads', __name__)

# Filter out private/internal IPs (test data from localhost)
_REAL_IP_FILTER = r"visitor_ip !~ '^(10\.|127\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|\:\:1$)'"


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


def _get_meta_campaign_insights(period='last_30d'):
    """
    Fetch campaign list + spend/clicks/impressions from Meta Ads API.
    Returns list of dicts, or [] on failure. Cached 10 minutes.
    Each dict: {name, status, spend, impressions, clicks, cpc, reach}
    """
    import time, urllib.request, json as _json, urllib.parse
    cache_key = f'_cache_{period}'
    cache = getattr(_get_meta_campaign_insights, cache_key, None)
    if cache and time.time() - cache['ts'] < 600:
        return cache['data']

    def _set_cache(val):
        setattr(_get_meta_campaign_insights, cache_key, {'ts': time.time(), 'data': val})

    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        cursor.close(); conn.close()

        if not token or not account_id:
            _set_cache([]); return []

        acc = account_id if account_id.startswith('act_') else f'act_{account_id}'

        # Step 1: campaign list (name + status + budget from Facebook settings)
        camp_url = (f'https://graph.facebook.com/v19.0/{acc}/campaigns'
                    f'?fields=id,name,status,effective_status,lifetime_budget,daily_budget&limit=200&access_token={token}')
        req = urllib.request.Request(camp_url, headers={'User-Agent': 'EKG-Server/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            camp_data = _json.loads(resp.read())
        campaigns = {c['id']: c for c in camp_data.get('data', [])}

        # Step 2: insights (spend/clicks/impressions/frequency/actions) per campaign
        ins_params = urllib.parse.urlencode({
            'level': 'campaign',
            'fields': 'campaign_id,campaign_name,spend,impressions,clicks,reach,cpc,'
                      'frequency,unique_clicks,cost_per_unique_click,actions,cost_per_action_type',
            'date_preset': period,
            'limit': 200,
            'access_token': token
        })
        ins_url = f'https://graph.facebook.com/v19.0/{acc}/insights?{ins_params}'
        req2 = urllib.request.Request(ins_url, headers={'User-Agent': 'EKG-Server/1.0'})
        with urllib.request.urlopen(req2, timeout=10) as resp:
            ins_data = _json.loads(resp.read())

        # Merge by campaign_id
        insights_map = {r['campaign_id']: r for r in ins_data.get('data', [])}
        result = []
        for cid, c in campaigns.items():
            ins = insights_map.get(cid, {})
            # lifetime_budget / daily_budget from Meta are in cents (÷100 = THB)
            raw_lifetime = c.get('lifetime_budget')
            raw_daily    = c.get('daily_budget')
            lifetime_budget = round(int(raw_lifetime) / 100, 2) if raw_lifetime else None
            daily_budget    = round(int(raw_daily)    / 100, 2) if raw_daily    else None
            impr = int(ins.get('impressions') or 0)
            clks = int(ins.get('clicks') or 0)
            result.append({
                'id': cid,
                'name': c['name'],
                'status': c['effective_status'],
                'spend': float(ins.get('spend') or 0),
                'impressions': impr,
                'clicks': clks,
                'reach': int(ins.get('reach') or 0),
                'cpc': float(ins.get('cpc') or 0),
                'frequency': float(ins.get('frequency') or 0),
                'unique_clicks': int(ins.get('unique_clicks') or 0),
                'cost_per_unique_click': float(ins.get('cost_per_unique_click') or 0),
                'ctr': round(clks / impr * 100, 2) if impr > 0 else 0,
                'actions': ins.get('actions', []),
                'cost_per_action_type': ins.get('cost_per_action_type', []),
                'lifetime_budget': lifetime_budget,
                'daily_budget': daily_budget,
            })
        result.sort(key=lambda x: x['spend'], reverse=True)
        _set_cache(result)
        return result
    except Exception as e:
        print(f'[META INSIGHTS] fetch error: {e}')
        _set_cache([]); return []


def _get_meta_campaign_names():
    """Returns set of lowercase campaign names from Meta API (all-time, for filter use)."""
    insights = _get_meta_campaign_insights('maximum')
    if not insights:
        return None
    return {c['name'].lower().strip() for c in insights}


def _get_meta_demographics(period='maximum'):
    """
    Fetch age+gender breakdown per campaign from Meta API. Cached 15 min.
    Returns dict keyed by lowercase campaign name → list of {age, gender, spend, impressions, clicks, actions}
    """
    import time, urllib.request, json as _json, urllib.parse
    cache = getattr(_get_meta_demographics, '_cache', None)
    if cache and time.time() - cache['ts'] < 900:
        return cache['data']

    def _set_cache(val):
        _get_meta_demographics._cache = {'ts': time.time(), 'data': val}

    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        cursor.close(); conn.close()
        if not token or not account_id:
            _set_cache({}); return {}
        acc = account_id if account_id.startswith('act_') else f'act_{account_id}'
        params = urllib.parse.urlencode({
            'level': 'campaign',
            'fields': 'campaign_name,spend,impressions,clicks,reach,actions',
            'breakdowns': 'age,gender',
            'date_preset': period,
            'limit': 500,
            'access_token': token
        })
        url = f'https://graph.facebook.com/v19.0/{acc}/insights?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'EKG-Server/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        result = {}
        for r in data.get('data', []):
            key = r.get('campaign_name', '').lower().strip()
            if key not in result:
                result[key] = []
            result[key].append({
                'age': r.get('age', ''),
                'gender': r.get('gender', ''),
                'spend': float(r.get('spend') or 0),
                'impressions': int(r.get('impressions') or 0),
                'clicks': int(r.get('clicks') or 0),
                'reach': int(r.get('reach') or 0),
                'actions': r.get('actions', []),
            })
        _set_cache(result)
        return result
    except Exception as e:
        print(f'[META DEMOGRAPHICS] fetch error: {e}')
        _set_cache({}); return {}


def _get_meta_regions(period='maximum'):
    """
    Fetch region (province) breakdown per campaign from Meta API. Cached 15 min.
    Returns dict keyed by lowercase campaign name → list of {region, spend, impressions, clicks}
    """
    import time, urllib.request, json as _json, urllib.parse
    cache = getattr(_get_meta_regions, '_cache', None)
    if cache and time.time() - cache['ts'] < 900:
        return cache['data']

    def _set_cache(val):
        _get_meta_regions._cache = {'ts': time.time(), 'data': val}

    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        cursor.close(); conn.close()
        if not token or not account_id:
            _set_cache({}); return {}
        acc = account_id if account_id.startswith('act_') else f'act_{account_id}'
        params = urllib.parse.urlencode({
            'level': 'campaign',
            'fields': 'campaign_name,spend,impressions,clicks,reach',
            'breakdowns': 'region',
            'date_preset': period,
            'limit': 500,
            'access_token': token
        })
        url = f'https://graph.facebook.com/v19.0/{acc}/insights?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'EKG-Server/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        result = {}
        for r in data.get('data', []):
            key = r.get('campaign_name', '').lower().strip()
            if key not in result:
                result[key] = []
            result[key].append({
                'region': r.get('region', ''),
                'spend': float(r.get('spend') or 0),
                'impressions': int(r.get('impressions') or 0),
                'clicks': int(r.get('clicks') or 0),
                'reach': int(r.get('reach') or 0),
            })
        # sort each campaign's regions by impressions desc
        for key in result:
            result[key].sort(key=lambda x: x['impressions'], reverse=True)
        _set_cache(result)
        return result
    except Exception as e:
        print(f'[META REGIONS] fetch error: {e}')
        _set_cache({}); return {}


def _get_pixel_settings():
    """Get pixel_id, access_token, test_event_code from DB (cached 60s)."""
    import time
    cache = getattr(_get_pixel_settings, '_cache', None)
    if cache and time.time() - cache['ts'] < 60:
        return cache['data']
    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute('SELECT pixel_id, access_token, test_event_code FROM facebook_pixel_settings WHERE is_active = true LIMIT 1')
        row = cursor.fetchone()
        data = dict(row) if row else {}
        _get_pixel_settings._cache = {'ts': time.time(), 'data': data}
        return data
    except Exception:
        return {}
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def _send_capi_event(event_name, event_source_url, visitor_ip=None, user_agent=None,
                     fbc=None, fbp=None, extra_data=None):
    """Send server-side event to Meta Conversions API asynchronously."""
    import threading, hashlib, time, urllib.request

    def _fire():
        try:
            settings = _get_pixel_settings()
            pixel_id = settings.get('pixel_id', '')
            access_token = settings.get('access_token', '')
            test_event_code = settings.get('test_event_code', '')
            if not pixel_id or not access_token:
                return

            user_data = {'client_ip_address': visitor_ip or '', 'client_user_agent': user_agent or ''}
            if fbc: user_data['fbc'] = fbc
            if fbp: user_data['fbp'] = fbp

            event = {
                'event_name': event_name,
                'event_time': int(time.time()),
                'action_source': 'website',
                'event_source_url': event_source_url or '',
                'user_data': user_data,
            }
            if extra_data:
                event['custom_data'] = extra_data

            payload = {'data': [event]}
            if test_event_code:
                payload['test_event_code'] = test_event_code

            url = f'https://graph.facebook.com/v19.0/{pixel_id}/events?access_token={access_token}'
            body = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req, timeout=5) as resp:
                logging.info(f'[CAPI] {event_name} sent → {resp.status}')
        except Exception as ex:
            logging.warning(f'[CAPI] Failed to send {event_name}: {ex}')

    threading.Thread(target=_fire, daemon=True).start()


# ==================== ADMIN PAGE ====================

@facebook_ads_bp.route('/admin/facebook-ads')
@login_required
@admin_required
def admin_facebook_ads_page():
    user_role = session.get('role', 'admin')
    return render_template('admin_facebook_ads.html', user_role=user_role)


@facebook_ads_bp.route('/admin/facebook-ads/settings')
@login_required
@admin_required
def admin_facebook_ads_settings():
    user_role = session.get('role', 'admin')
    return render_template('admin_facebook_ads_settings.html', user_role=user_role)


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

        active_pixel = _get_pixel_settings().get('pixel_id') or None

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO page_visits (page_name, source, visitor_ip, user_agent, utm_campaign, utm_medium, referrer, traffic_type, pixel_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (page_name, source, visitor_ip, user_agent, utm_campaign, utm_medium,
              referrer or None, traffic_type, active_pixel))
        conn.commit()

        # Server-side PageView → Meta CAPI
        fbc = data.get('fbc') or None
        fbp = data.get('fbp') or None
        event_url = data.get('event_source_url') or referrer or ''
        _send_capi_event('PageView', event_url, visitor_ip=visitor_ip,
                         user_agent=user_agent, fbc=fbc, fbp=fbp)

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
        valid_events = {'catalog_view', 'chatbot_open', 'register_click', 'register_complete',
                        'first_order', 'view_content', 'add_to_cart', 'initiate_checkout'}
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

        active_pixel = _get_pixel_settings().get('pixel_id') or None

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversion_events (session_id, event_type, source, traffic_type, utm_campaign, visitor_ip, user_agent, pixel_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (session_id or None, event_type, source, traffic_type, utm_campaign, visitor_ip, user_agent, active_pixel))
        conn.commit()

        # Map internal event → Meta standard event name then send via CAPI
        _capi_map = {
            'catalog_view':       'ViewContent',
            'chatbot_open':       None,  # no standard Meta event
            'register_click':     'Lead',
            'register_complete':  'CompleteRegistration',
            'first_order':        'Purchase',
            'view_content':       'ViewContent',
            'add_to_cart':        'AddToCart',
            'initiate_checkout':  'InitiateCheckout',
        }
        meta_event = _capi_map.get(event_type)
        if meta_event:
            fbc = data.get('fbc') or None
            fbp = data.get('fbp') or None
            event_url = data.get('event_source_url') or referrer or ''
            # Build product custom_data if provided
            extra_data = None
            content_ids = data.get('content_ids')
            if content_ids:
                extra_data = {
                    'content_ids':  content_ids,
                    'content_name': data.get('content_name', ''),
                    'content_type': 'product',
                    'currency':     data.get('currency', 'THB'),
                }
                if data.get('value') is not None:
                    extra_data['value'] = float(data['value'])
            _send_capi_event(meta_event, event_url, visitor_ip=visitor_ip,
                             user_agent=user_agent, fbc=fbc, fbp=fbp,
                             extra_data=extra_data)

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
        active_pixel = _get_pixel_settings().get('pixel_id') or None
        # pixel filter: match current pixel OR legacy rows (pixel_id IS NULL)
        pixel_clause = "pv.pixel_id = %s" if active_pixel else "TRUE"
        pixel_params = [active_pixel] if active_pixel else []

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(f'''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook' AND {_REAL_IP_FILTER}
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND DATE(created_at) = CURRENT_DATE
        ''')
        today_registrations = cursor.fetchone()['count']

        cursor.execute(f'''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook' AND {_REAL_IP_FILTER}
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        ''')
        week_registrations = cursor.fetchone()['count']

        cursor.execute(f'''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook' AND {_REAL_IP_FILTER}
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
        ''')
        month_registrations = cursor.fetchone()['count']

        cursor.execute(f'''
            SELECT COUNT(*) as count FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook' AND {_REAL_IP_FILTER}
        ''')
        total_visits = cursor.fetchone()['count']

        cursor.execute('''
            SELECT COUNT(*) as count FROM users
            WHERE notes LIKE '%[source: facebook]%'
        ''')
        total_registrations = cursor.fetchone()['count']

        cursor.execute(f'''
            SELECT DATE(created_at) as date, COUNT(*) as visits
            FROM page_visits
            WHERE page_name IN ('become-reseller', 'catalog')
            AND source = 'facebook' AND {_REAL_IP_FILTER}
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at) ORDER BY date
        ''')
        daily_visits = {str(row['date']): row['visits'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT DATE(created_at) as date, COUNT(*) as registrations
            FROM users
            WHERE notes LIKE '%[source: facebook]%'
            AND created_at >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY DATE(created_at) ORDER BY date
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

        cursor.execute(f'''
            SELECT
                COALESCE(pv.utm_campaign, '(ไม่ระบุแคมเปญ)') as campaign,
                COUNT(*) as visits,
                MAX(pv.created_at) as last_visit,
                COALESCE(cb.total_budget, 0) as budget,
                cb.notes as budget_notes,
                COALESCE(cb.is_hidden, false) as is_hidden
            FROM page_visits pv
            LEFT JOIN campaign_budgets cb ON cb.campaign_name = COALESCE(pv.utm_campaign, '(ไม่ระบุแคมเปญ)')
            WHERE pv.page_name IN ('become-reseller', 'catalog')
            AND pv.source = 'facebook'
            AND {pixel_clause}
            AND {_REAL_IP_FILTER}
            AND COALESCE(cb.is_hidden, false) = false
            GROUP BY pv.utm_campaign, cb.total_budget, cb.notes, cb.is_hidden
            ORDER BY visits DESC
            LIMIT 20
        ''', pixel_params)
        campaigns_raw = cursor.fetchall()
        # Build Meta spend lookup — use 'maximum' for all-time spend
        meta_insights = _get_meta_campaign_insights('maximum')
        # Index by both lowercase name AND campaign ID (Facebook sometimes sets utm_campaign to the campaign ID)
        meta_spend_map = {}
        for c in meta_insights:
            meta_spend_map[c['name'].lower().strip()] = c
            if c.get('id'):
                meta_spend_map[str(c['id'])] = c          # match by campaign ID
        # Active keys = names + IDs for ACTIVE campaigns only
        active_meta_keys = set()
        for c in meta_insights:
            if c.get('status') == 'ACTIVE':
                active_meta_keys.add(c['name'].lower().strip())
                if c.get('id'):
                    active_meta_keys.add(str(c['id']))

        now = datetime.now()
        campaign_breakdown = []
        for r in campaigns_raw:
            camp_name = r['campaign']
            camp_key  = camp_name.lower().strip()

            # Filter: only include campaigns that are ACTIVE in Meta Ads Manager
            # Match by name OR campaign ID (Facebook sometimes stores utm_campaign as the ID)
            # Always include '(ไม่ระบุแคมเปญ)' so untagged Facebook traffic is visible
            if camp_name != '(ไม่ระบุแคมเปญ)' and active_meta_keys and camp_key not in active_meta_keys:
                continue

            visits = r['visits']
            budget = float(r['budget'] or 0)
            last_visit = r['last_visit']
            hours_since = (now - last_visit).total_seconds() / 3600 if last_visit else 9999
            if hours_since <= 48:
                active_status = 'active'
            elif hours_since <= 168:
                active_status = 'pausing'
            else:
                active_status = 'inactive'

            # Merge Meta API data (actual spend + all metrics — all-time)
            meta = meta_spend_map.get(camp_key, {})
            # If UTM is a campaign ID, show the Meta campaign name as display name
            display_name = meta.get('name', camp_name) if meta and camp_key.isdigit() else camp_name
            meta_spend               = meta.get('spend', 0) or 0
            meta_impressions         = meta.get('impressions', 0) or 0
            meta_clicks              = meta.get('clicks', 0) or 0
            meta_cpc                 = meta.get('cpc', 0) or 0
            meta_reach               = meta.get('reach', 0) or 0
            meta_frequency           = meta.get('frequency', 0) or 0
            meta_unique_clicks       = meta.get('unique_clicks', 0) or 0
            meta_cost_per_unique_click = meta.get('cost_per_unique_click', 0) or 0
            meta_ctr                 = meta.get('ctr', 0) or 0
            meta_actions             = meta.get('actions', [])
            meta_cost_per_action     = meta.get('cost_per_action_type', [])
            meta_lifetime_budget     = meta.get('lifetime_budget')
            meta_daily_budget        = meta.get('daily_budget')

            # CPV: prefer actual Meta spend, fall back to manual budget
            effective_budget = meta_spend if meta_spend > 0 else budget
            cpv = round(effective_budget / visits, 2) if effective_budget > 0 and visits > 0 else None

            # Use meta campaign ID as merge key to prevent duplicate rows
            # when both UTM name and UTM ID point to the same Meta campaign
            merge_key = str(meta.get('id', '')) if meta.get('id') else display_name
            campaign_breakdown.append({
                '_merge_key': merge_key,
                'campaign': camp_name,
                'display_name': display_name,
                'visits': visits,
                'budget': budget,
                'cpv': cpv,
                'cpv_source': 'meta' if meta_spend > 0 else 'manual',
                'active_status': active_status,
                'last_visit_hours': round(hours_since, 1),
                'budget_notes': r['budget_notes'],
                'meta_spend': meta_spend,
                'meta_impressions': meta_impressions,
                'meta_clicks': meta_clicks,
                'meta_cpc': meta_cpc,
                'meta_reach': meta_reach,
                'meta_frequency': meta_frequency,
                'meta_unique_clicks': meta_unique_clicks,
                'meta_cost_per_unique_click': meta_cost_per_unique_click,
                'meta_ctr': meta_ctr,
                'meta_actions': meta_actions,
                'meta_cost_per_action': meta_cost_per_action,
                'meta_lifetime_budget': meta_lifetime_budget,
                'meta_daily_budget': meta_daily_budget,
                'meta_status': meta.get('status', ''),
            })

        # Merge duplicate rows that map to the same Meta campaign (name-based + ID-based UTMs)
        merged = {}
        for item in campaign_breakdown:
            key = item['_merge_key']
            if key not in merged:
                merged[key] = item.copy()
            else:
                # Sum visits only; keep Meta data from whichever row has it (they're the same campaign)
                merged[key]['visits'] += item['visits']
                if not merged[key]['meta_spend'] and item['meta_spend']:
                    for f in ('meta_spend','meta_impressions','meta_clicks','meta_cpc','meta_reach',
                              'meta_frequency','meta_unique_clicks','meta_cost_per_unique_click',
                              'meta_ctr','meta_actions','meta_cost_per_action',
                              'meta_lifetime_budget','meta_daily_budget','meta_status'):
                        merged[key][f] = item[f]
        campaign_breakdown = sorted(merged.values(), key=lambda x: -x['visits'])
        for item in campaign_breakdown:
            item.pop('_merge_key', None)
            # Recalculate CPV with merged visit count
            eff = item['meta_spend'] if item['meta_spend'] > 0 else item['budget']
            item['cpv'] = round(eff / item['visits'], 2) if eff > 0 and item['visits'] > 0 else None

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
            'campaign_breakdown': campaign_breakdown,
            'meta_campaigns': _get_meta_campaign_insights('maximum')
        }), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/campaign-demographics', methods=['GET'])
@login_required
@admin_required
def get_campaign_demographics():
    """Get age/gender and region breakdown for a single campaign from Meta Ads API"""
    campaign_name = request.args.get('name', '').strip().lower()
    if not campaign_name:
        return jsonify({'error': 'name required'}), 400

    # If the caller passed a numeric campaign ID, resolve it to the actual campaign name
    if campaign_name.isdigit():
        insights = _get_meta_campaign_insights('maximum')
        for c in insights:
            if str(c.get('id', '')) == campaign_name:
                campaign_name = c['name'].lower().strip()
                break

    demo_map    = _get_meta_demographics()
    region_map  = _get_meta_regions()

    demo_rows   = demo_map.get(campaign_name, [])
    region_rows = region_map.get(campaign_name, [])

    # Aggregate gender totals
    gender_totals = {}
    for r in demo_rows:
        g = r['gender']
        if g == 'unknown':
            continue
        if g not in gender_totals:
            gender_totals[g] = {'spend': 0, 'impressions': 0, 'clicks': 0, 'reach': 0, 'actions': []}
        gender_totals[g]['spend']       += r['spend']
        gender_totals[g]['impressions'] += r['impressions']
        gender_totals[g]['clicks']      += r['clicks']
        gender_totals[g]['reach']       += r['reach']
        gender_totals[g]['actions']     += r.get('actions', [])

    # Aggregate age totals (across genders)
    age_totals = {}
    for r in demo_rows:
        if r['gender'] == 'unknown':
            continue
        a = r['age']
        if a not in age_totals:
            age_totals[a] = {'spend': 0, 'impressions': 0, 'clicks': 0}
        age_totals[a]['spend']       += r['spend']
        age_totals[a]['impressions'] += r['impressions']
        age_totals[a]['clicks']      += r['clicks']

    # Aggregate actions from gender totals into readable list
    def _agg_actions(action_list):
        agg = {}
        for act in action_list:
            t = act.get('action_type', '')
            v = float(act.get('value', 0))
            agg[t] = agg.get(t, 0) + v
        return [{'type': k, 'value': int(v)} for k, v in sorted(agg.items(), key=lambda x: -x[1])]

    all_actions = []
    for g_data in gender_totals.values():
        all_actions += g_data.get('actions', [])
    aggregated_actions = _agg_actions(all_actions)

    # Clean gender list
    gender_list = []
    total_impr = sum(v['impressions'] for v in gender_totals.values()) or 1
    total_spend = sum(v['spend'] for v in gender_totals.values()) or 1
    for g, v in gender_totals.items():
        gender_list.append({
            'gender': g,
            'label': 'หญิง' if g == 'female' else 'ชาย',
            'spend': round(v['spend'], 2),
            'impressions': v['impressions'],
            'clicks': v['clicks'],
            'reach': v['reach'],
            'spend_pct': round(v['spend'] / total_spend * 100, 1),
            'impr_pct': round(v['impressions'] / total_impr * 100, 1),
        })
    gender_list.sort(key=lambda x: -x['impressions'])

    # Age breakdown sorted
    age_order = ['13-17','18-24','25-34','35-44','45-54','55-64','65+']
    total_age_impr = sum(v['impressions'] for v in age_totals.values()) or 1
    age_list = []
    for a in age_order:
        if a not in age_totals:
            continue
        v = age_totals[a]
        age_list.append({
            'age': a,
            'spend': round(v['spend'], 2),
            'impressions': v['impressions'],
            'clicks': v['clicks'],
            'impr_pct': round(v['impressions'] / total_age_impr * 100, 1),
            'ctr': round(v['clicks'] / v['impressions'] * 100, 2) if v['impressions'] > 0 else 0,
        })

    return jsonify({
        'campaign': campaign_name,
        'gender': gender_list,
        'age': age_list,
        'regions': region_rows[:15],
        'actions': aggregated_actions,
    })


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

        active_pixel = _get_pixel_settings().get('pixel_id') or None
        pixel_clause = "pixel_id = %s" if active_pixel else "TRUE"

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        where_campaign = "utm_campaign = %s" if campaign != '(ไม่ระบุแคมเปญ)' else "utm_campaign IS NULL"
        campaign_param = (campaign,) if campaign != '(ไม่ระบุแคมเปญ)' else ()
        pixel_param = (active_pixel,) if active_pixel else ()
        # pixel_clause is in page_filter (comes first), campaign param comes after → pixel first
        params_base = pixel_param + campaign_param
        page_filter = f"page_name IN ('become-reseller','catalog') AND source = 'facebook' AND {pixel_clause} AND {_REAL_IP_FILTER}"

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
                WHERE event_type = %s AND {_REAL_IP_FILTER} {date_filter} {camp_filter}
            ''', [step] + camp_params)
            r = cursor.fetchone()
            funnel[step] = r['cnt'] if r else 0

        if funnel['catalog_view'] == 0:
            cursor.execute(f'''
                SELECT COUNT(*) as cnt FROM page_visits
                WHERE page_name IN ('catalog','become-reseller') AND {_REAL_IP_FILTER} {date_filter}
                {('AND utm_campaign = %s' if campaign else '')}
            ''', camp_params)
            r = cursor.fetchone()
            funnel['catalog_view'] = r['cnt'] if r else 0

        cursor.execute(f'''
            SELECT source, event_type, COUNT(DISTINCT COALESCE(session_id, visitor_ip)) as cnt
            FROM conversion_events
            WHERE event_type IN ('catalog_view','register_complete') AND {_REAL_IP_FILTER} {date_filter}
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

        # --- Meta API: real spend/clicks/impressions (all-time) ---
        meta_camps = _get_meta_campaign_insights('maximum')
        meta_by_name = {c['name'].lower().strip(): c for c in meta_camps}
        meta_total_spend = sum(c['spend'] for c in meta_camps)
        meta_total_clicks = sum(c['clicks'] for c in meta_camps)
        meta_total_impressions = sum(c['impressions'] for c in meta_camps)

        # --- DB: UTM-based visit breakdown (all-time, real IPs only) ---
        cursor.execute(f'''
            SELECT
                pv.utm_campaign,
                COUNT(*) as visits,
                ROUND(AVG(EXTRACT(HOUR FROM pv.created_at AT TIME ZONE 'Asia/Bangkok'))) as avg_hour,
                COUNT(CASE WHEN pv.user_agent ~* 'mobile|android|iphone|ipad' THEN 1 END)::float / NULLIF(COUNT(*),0) * 100 as mobile_pct,
                MAX(pv.created_at) as last_visit
            FROM page_visits pv
            WHERE pv.source = 'facebook' AND pv.utm_campaign IS NOT NULL AND {_REAL_IP_FILTER}
            GROUP BY pv.utm_campaign ORDER BY visits DESC LIMIT 10
        ''')
        campaigns_raw = cursor.fetchall()
        now = datetime.now()
        campaigns = []
        total_visits_all = 0
        for r in campaigns_raw:
            visits = r['visits']
            total_visits_all += visits
            hours_since = (now - r['last_visit']).total_seconds() / 3600 if r['last_visit'] else 9999
            meta = meta_by_name.get((r['utm_campaign'] or '').lower().strip(), {})
            spend = meta.get('spend', 0)
            clicks = meta.get('clicks', 0)
            campaigns.append({
                'campaign': r['utm_campaign'],
                'visits': visits,
                'avg_hour': int(r['avg_hour']) if r['avg_hour'] else None,
                'mobile_pct': round(float(r['mobile_pct'] or 0), 1),
                'active': hours_since <= 48,
                'meta_spend': spend,
                'meta_clicks': clicks,
                'cpv': round(spend / visits, 2) if spend > 0 and visits > 0 else None,
            })

        # --- Funnel (all-time, real IPs only) ---
        cursor.execute(f'''
            SELECT event_type, COUNT(DISTINCT COALESCE(session_id, visitor_ip)) as cnt
            FROM conversion_events WHERE {_REAL_IP_FILTER} GROUP BY event_type
        ''')
        funnel = {r['event_type']: r['cnt'] for r in cursor.fetchall()}

        cursor.execute(f'''
            SELECT traffic_type, COUNT(*) as visits FROM page_visits
            WHERE page_name IN ('catalog','become-reseller') AND {_REAL_IP_FILTER}
            GROUP BY traffic_type ORDER BY visits DESC
        ''')
        traffic_types = [dict(r) for r in cursor.fetchall()]

        cursor.execute(f'''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr, COUNT(*) as cnt
            FROM page_visits WHERE page_name IN ('catalog','become-reseller') AND {_REAL_IP_FILTER}
            GROUP BY hr ORDER BY cnt DESC LIMIT 5
        ''')
        peak_hours = [dict(r) for r in cursor.fetchall()]

        # --- Meta campaign summary for prompt ---
        meta_section = "ข้อมูลจาก Meta Ads API (ทั้งหมดตั้งแต่เริ่มแคมเปญ):\n"
        if meta_camps:
            meta_section += f"- ยอดใช้จ่ายรวม: ฿{meta_total_spend:,.2f}\n"
            meta_section += f"- Impressions รวม: {meta_total_impressions:,}\n"
            meta_section += f"- Clicks รวม: {meta_total_clicks:,}\n"
            meta_section += f"- CTR รวม: {round(meta_total_clicks/meta_total_impressions*100,2) if meta_total_impressions else 0}%\n"
            for c in meta_camps:
                meta_section += (f"  • {c['name']} [{c['status']}]: "
                                 f"฿{c['spend']:,.2f} spend, {c['impressions']:,} impressions, "
                                 f"{c['clicks']} clicks, CPC=฿{c['cpc']:.2f}\n")
        else:
            meta_section += "- ไม่พบข้อมูลจาก Meta API\n"

        budget_section = f"""
{meta_section}
Funnel: Catalog Views={funnel.get('catalog_view','?')}, Chatbot={funnel.get('chatbot_open','?')}, คลิกสมัคร={funnel.get('register_click','?')}, สมัครสำเร็จ={funnel.get('register_complete','?')}
"""

        prompt = f"""คุณเป็น Digital Marketing Analyst ผู้เชี่ยวชาญ e-commerce ไทย
วิเคราะห์ข้อมูลโฆษณาร้านขายชุดพยาบาล EKG Shops นี้ และให้คำแนะนำเป็นภาษาไทยที่กระชับ ตรงประเด็น

ข้อมูลแคมเปญ Facebook (ทั้งหมดตั้งแต่เริ่มแคมเปญ):
{campaigns}

การแบ่งประเภท traffic:
{traffic_types}

ชั่วโมงที่มี traffic สูงสุด:
{peak_hours}
{budget_section}
กรุณาตอบในรูปแบบ JSON ดังนี้ (ตอบ JSON เท่านั้น ไม่มีข้อความอื่น):
{{
  "summary": "สรุปภาพรวม 2-3 ประโยค",
  "top_insight": "insight สำคัญที่สุด 1 ข้อ",
  "recommendations": ["คำแนะนำข้อ 1", "คำแนะนำข้อ 2", "คำแนะนำข้อ 3"],
  "roi_summary": "ประเมินความคุ้มค่าของงบที่ใช้ (ถ้าไม่มีข้อมูลงบให้แนะนำให้ตั้งค่า)",
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


# ==================== CAMPAIGN BUDGET API ====================

@facebook_ads_bp.route('/api/facebook-ads/campaign-budgets', methods=['GET'])
@login_required
@admin_required
def get_campaign_budgets():
    """Get all campaigns with budget, visits, CPV, and active status"""
    conn = None
    cursor = None
    try:
        active_pixel = _get_pixel_settings().get('pixel_id') or None
        pixel_clause = "pv.pixel_id = %s" if active_pixel else "TRUE"
        pixel_params = [active_pixel] if active_pixel else []

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cursor.execute(f'''
            SELECT
                COALESCE(pv.utm_campaign, '(ไม่ระบุแคมเปญ)') as campaign_name,
                COUNT(*) as visits,
                MAX(pv.created_at) as last_visit,
                COALESCE(cb.total_budget, 0) as total_budget,
                cb.notes
            FROM page_visits pv
            LEFT JOIN campaign_budgets cb
                ON cb.campaign_name = COALESCE(pv.utm_campaign, '(ไม่ระบุแคมเปญ)')
            WHERE pv.page_name IN ('become-reseller','catalog')
            AND pv.source = 'facebook'
            AND {pixel_clause}
            AND COALESCE(cb.is_hidden, false) = false
            GROUP BY pv.utm_campaign, cb.total_budget, cb.notes
            ORDER BY visits DESC
        ''', pixel_params)
        rows = cursor.fetchall()
        now = datetime.now()
        result = []
        for r in rows:
            camp_name = r['campaign_name']
            visits = r['visits']
            budget = float(r['total_budget'] or 0)
            last_visit = r['last_visit']
            hours_since = (now - last_visit).total_seconds() / 3600 if last_visit else 9999
            if hours_since <= 48:
                status = 'active'
            elif hours_since <= 168:
                status = 'pausing'
            else:
                status = 'inactive'
            cpv = round(budget / visits, 2) if budget > 0 and visits > 0 else None
            result.append({
                'campaign_name': camp_name,
                'visits': visits,
                'total_budget': budget,
                'cpv': cpv,
                'active_status': status,
                'last_visit_hours': round(hours_since, 1),
                'notes': r['notes'],
            })
        return jsonify({'campaigns': result}), 200
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@facebook_ads_bp.route('/api/facebook-ads/campaign-budgets', methods=['POST'])
@login_required
@admin_required
def save_campaign_budget():
    """Upsert budget for a campaign"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        campaign_name = (data.get('campaign_name') or '').strip()
        total_budget = float(data.get('total_budget') or 0)
        notes = (data.get('notes') or '').strip() or None
        if not campaign_name:
            return jsonify({'error': 'Missing campaign_name'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO campaign_budgets (campaign_name, total_budget, notes, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (campaign_name) DO UPDATE
                SET total_budget = EXCLUDED.total_budget,
                    notes = EXCLUDED.notes,
                    updated_at = CURRENT_TIMESTAMP
        ''', (campaign_name, total_budget, notes))
        conn.commit()
        return jsonify({'success': True, 'campaign_name': campaign_name, 'total_budget': total_budget}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== HIDE / UNHIDE CAMPAIGN ====================

@facebook_ads_bp.route('/api/facebook-ads/campaign-hide', methods=['POST'])
@login_required
@admin_required
def toggle_campaign_visibility():
    """Hide or unhide a campaign from the dashboard"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        campaign_name = (data.get('campaign_name') or '').strip()
        is_hidden = bool(data.get('is_hidden', True))
        if not campaign_name:
            return jsonify({'error': 'Missing campaign_name'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO campaign_budgets (campaign_name, total_budget, is_hidden, updated_at)
            VALUES (%s, 0, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (campaign_name) DO UPDATE
                SET is_hidden = EXCLUDED.is_hidden,
                    updated_at = CURRENT_TIMESTAMP
        ''', (campaign_name, is_hidden))
        conn.commit()
        return jsonify({'success': True, 'campaign_name': campaign_name, 'is_hidden': is_hidden}), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== DELETE CAMPAIGN DATA ====================

@facebook_ads_bp.route('/api/facebook-ads/campaign-delete', methods=['POST'])
@login_required
@admin_required
def delete_campaign_data():
    """Permanently delete all tracking data for a specific campaign"""
    conn = None
    cursor = None
    try:
        data = request.get_json(silent=True) or {}
        campaign_name = (data.get('campaign_name') or '').strip()
        if not campaign_name:
            return jsonify({'error': 'Missing campaign_name'}), 400
        if campaign_name == '(ไม่ระบุแคมเปญ)':
            return jsonify({'error': 'ไม่สามารถลบแคมเปญกลุ่ม "ไม่ระบุ" ได้'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # Count before delete
        cursor.execute('SELECT COUNT(*) FROM page_visits WHERE utm_campaign = %s', (campaign_name,))
        pv_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM conversion_events WHERE utm_campaign = %s', (campaign_name,))
        ce_count = cursor.fetchone()[0]

        # Delete tracking data
        cursor.execute('DELETE FROM page_visits WHERE utm_campaign = %s', (campaign_name,))
        cursor.execute('DELETE FROM conversion_events WHERE utm_campaign = %s', (campaign_name,))
        # Remove from campaign_budgets if exists
        cursor.execute('DELETE FROM campaign_budgets WHERE campaign_name = %s', (campaign_name,))
        conn.commit()

        return jsonify({
            'success': True,
            'campaign_name': campaign_name,
            'deleted_visits': pv_count,
            'deleted_conversions': ce_count
        }), 200
    except Exception as e:
        if conn: conn.rollback()
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== AI PER-CAMPAIGN ANALYSIS ====================

@facebook_ads_bp.route('/api/facebook-ads/ai-campaign-analysis', methods=['GET'])
@login_required
@admin_required
def fb_ai_campaign_analysis():
    """On-demand AI analysis for a specific campaign"""
    conn = None
    cursor = None
    try:
        from google import genai as _g
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({'error': 'ไม่มี Gemini API Key'}), 503

        campaign = request.args.get('campaign', '').strip()
        if not campaign:
            return jsonify({'error': 'Missing campaign'}), 400

        active_pixel = _get_pixel_settings().get('pixel_id') or None
        pixel_clause = "pixel_id = %s" if active_pixel else "TRUE"
        pixel_param = (active_pixel,) if active_pixel else ()

        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        where_campaign = "utm_campaign = %s" if campaign != '(ไม่ระบุแคมเปญ)' else "utm_campaign IS NULL"
        campaign_param = (campaign,) if campaign != '(ไม่ระบุแคมเปญ)' else ()
        # pixel_clause first in page_filter → pixel param first
        params = pixel_param + campaign_param
        page_filter = f"page_name IN ('become-reseller','catalog') AND source = 'facebook' AND {pixel_clause} AND {_REAL_IP_FILTER}"

        # Visits stats
        cursor.execute(f'''
            SELECT COUNT(*) as total_visits,
                   MIN(created_at) as first_visit, MAX(created_at) as last_visit,
                   COUNT(CASE WHEN user_agent ~* 'mobile|android|iphone|ipad' THEN 1 END)::float / NULLIF(COUNT(*),0) * 100 as mobile_pct
            FROM page_visits WHERE {page_filter} AND {where_campaign}
        ''', params)
        stats = cursor.fetchone()
        total_visits = stats['total_visits'] or 0
        first_visit = stats['first_visit']
        last_visit = stats['last_visit']
        mobile_pct = round(float(stats['mobile_pct'] or 0), 1)
        duration_days = (last_visit.date() - first_visit.date()).days + 1 if first_visit and last_visit else 0

        # Peak hours
        cursor.execute(f'''
            SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Asia/Bangkok') as hr, COUNT(*) as cnt
            FROM page_visits WHERE {page_filter} AND {where_campaign}
            GROUP BY hr ORDER BY cnt DESC LIMIT 3
        ''', params)
        peak_hours = [{'hour': int(r['hr']), 'count': r['cnt']} for r in cursor.fetchall()]

        # Day of week
        cursor.execute(f'''
            SELECT TO_CHAR(created_at AT TIME ZONE 'Asia/Bangkok', 'Day') as dow, COUNT(*) as cnt
            FROM page_visits WHERE {page_filter} AND {where_campaign}
            GROUP BY dow ORDER BY cnt DESC LIMIT 3
        ''', params)
        peak_days = [r['dow'].strip() for r in cursor.fetchall()]

        # Active status
        now = datetime.now()
        hours_since = (now - last_visit).total_seconds() / 3600 if last_visit else 9999
        if hours_since <= 48:
            active_status = 'กำลังทำงาน'
        elif hours_since <= 168:
            active_status = 'หยุดพักชั่วคราว (ไม่มี visit ใน 2-7 วัน)'
        else:
            active_status = 'น่าจะหยุดแล้ว (ไม่มี visit เกิน 7 วัน)'

        # Budget from DB
        cursor.execute('SELECT total_budget, notes FROM campaign_budgets WHERE campaign_name = %s', (campaign,))
        budget_row = cursor.fetchone()
        budget = float(budget_row['total_budget']) if budget_row else 0
        cpv = round(budget / total_visits, 2) if budget > 0 and total_visits > 0 else None

        # Conversion events
        cursor.execute('''
            SELECT event_type, COUNT(DISTINCT COALESCE(session_id, visitor_ip)) as cnt
            FROM conversion_events WHERE utm_campaign = %s
            GROUP BY event_type
        ''', (campaign,))
        funnel = {r['event_type']: r['cnt'] for r in cursor.fetchall()}

        prompt = f"""คุณเป็น Digital Marketing Analyst ผู้เชี่ยวชาญ Facebook Ads สำหรับ e-commerce ไทย
วิเคราะห์แคมเปญ Facebook Ads ชื่อ "{campaign}" ของร้านชุดพยาบาล EKG Shops

ข้อมูลแคมเปญ:
- ยอด Visits: {total_visits:,} ครั้ง
- ระยะเวลา: {duration_days} วัน (เริ่ม {str(first_visit.date()) if first_visit else '-'})
- สถานะ: {active_status}
- มือถือ: {mobile_pct}% | คอมพิวเตอร์: {100-mobile_pct}%
- Peak hours: {[f"{h['hour']}:00" for h in peak_hours]}
- Peak days: {peak_days}
- งบประมาณรวม: {f'{budget:,.0f} บาท' if budget > 0 else 'ยังไม่ได้ตั้งค่า'}
- Cost Per Visit (CPV): {f'{cpv:.2f} บาท/visit' if cpv else 'ไม่มีข้อมูลงบ'}

Conversion Funnel:
- เข้าชม Catalog: {funnel.get('catalog_view', '-')}
- เปิด Chatbot: {funnel.get('chatbot_open', '-')}
- คลิกสมัคร: {funnel.get('register_click', '-')}
- สมัครสำเร็จ: {funnel.get('register_complete', '-')}

ตอบเป็น JSON เท่านั้น:
{{
  "verdict": "ประเมินแคมเปญนี้ใน 1 ประโยค",
  "performance_score": 75,
  "roi_assessment": "ประเมินความคุ้มค่าของงบที่ใช้ (ถ้าไม่มีข้อมูลงบให้แนะนำให้ตั้งค่า)",
  "strengths": ["จุดแข็ง 1", "จุดแข็ง 2"],
  "weaknesses": ["จุดอ่อน 1", "จุดอ่อน 2"],
  "actions": ["สิ่งที่ควรทำต่อ 1", "สิ่งที่ควรทำต่อ 2", "สิ่งที่ควรทำต่อ 3"],
  "budget_advice": "คำแนะนำด้านงบประมาณ"
}}"""

        client = _g.Client(api_key=gemini_key)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = response.text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'): text = text[4:]
        import json as _json
        result = _json.loads(text.strip())
        result['campaign'] = campaign
        result['stats'] = {
            'total_visits': total_visits, 'duration_days': duration_days,
            'mobile_pct': mobile_pct, 'budget': budget, 'cpv': cpv,
            'active_status': active_status,
        }
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


# ==================== LIVE CAMPAIGN DASHBOARD ====================

@facebook_ads_bp.route('/api/facebook-ads/meta-live-campaigns', methods=['GET'])
@login_required
@admin_required
def meta_live_campaigns():
    """Fetch all campaigns with per-campaign insights + age/gender breakdown from Meta API."""
    import urllib.request, urllib.parse, urllib.error
    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        if not token or not account_id:
            return jsonify({'error': 'ยังไม่ได้ตั้งค่า Meta Access Token หรือ Ad Account ID'}), 400
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'

        def _api(url):
            req = urllib.request.Request(url, headers={'User-Agent': 'EKGShops/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())

        # 1) Get all campaigns (active + paused)
        camp_fields = 'id,name,status,effective_status,objective,daily_budget,lifetime_budget,start_time,created_time'
        camps_url = (f'https://graph.facebook.com/v19.0/{account_id}/campaigns'
                     f'?fields={camp_fields}&limit=50&access_token={token}')
        camps_data = _api(camps_url).get('data', [])

        # 2) For each campaign — insights + age/gender breakdown (parallel via threads)
        import threading
        ins_fields = 'impressions,reach,clicks,unique_clicks,ctr,cpc,cpm,spend,frequency,actions,cost_per_action_type'
        age_fields = 'impressions,clicks,spend,ctr,reach'

        results = {}
        lock = threading.Lock()

        def _fetch_campaign(c):
            cid = c['id']
            try:
                ins_url = (f'https://graph.facebook.com/v19.0/{cid}/insights'
                           f'?fields={ins_fields}&date_preset=maximum&access_token={token}')
                ins = _api(ins_url).get('data', [{}])
                ins_row = ins[0] if ins else {}

                age_url = (f'https://graph.facebook.com/v19.0/{cid}/insights'
                           f'?fields={age_fields}&breakdowns=age,gender'
                           f'&date_preset=maximum&access_token={token}')
                age_rows = _api(age_url).get('data', [])

                def _actions(row, key):
                    for a in (row.get('actions') or []):
                        if a['action_type'] == key:
                            return float(a['value'])
                    return 0.0

                spend = float(ins_row.get('spend', 0))
                reach = int(ins_row.get('reach', 0))
                impressions = int(ins_row.get('impressions', 0))
                clicks = int(ins_row.get('clicks', 0))
                ctr = float(ins_row.get('ctr', 0))
                cpc = float(ins_row.get('cpc', 0))
                cpm = float(ins_row.get('cpm', 0))
                frequency = float(ins_row.get('frequency', 0))
                landing_views = int(_actions(ins_row, 'landing_page_view'))
                view_content = int(_actions(ins_row, 'view_content'))
                leads = int(_actions(ins_row, 'lead'))
                link_clicks = int(_actions(ins_row, 'link_click'))

                cpl = round(spend / leads, 2) if leads > 0 else None
                cpc_landing = round(spend / landing_views, 2) if landing_views > 0 else None

                # Funnel drop-off rates
                funnel = [
                    {'label': 'Reach', 'value': reach, 'pct': 100},
                    {'label': 'Link Clicks', 'value': link_clicks,
                     'pct': round(link_clicks / reach * 100, 1) if reach else 0},
                    {'label': 'Landing Page', 'value': landing_views,
                     'pct': round(landing_views / reach * 100, 1) if reach else 0},
                    {'label': 'ViewContent', 'value': view_content,
                     'pct': round(view_content / reach * 100, 1) if reach else 0},
                    {'label': 'Lead', 'value': leads,
                     'pct': round(leads / reach * 100, 1) if reach else 0},
                ]

                # Top 5 age/gender by CTR (min 50 impressions)
                top_demo = sorted(
                    [r for r in age_rows if int(r.get('impressions', 0)) >= 50],
                    key=lambda r: float(r.get('ctr', 0)), reverse=True
                )[:5]

                with lock:
                    results[cid] = {
                        'spend': spend, 'reach': reach, 'impressions': impressions,
                        'clicks': clicks, 'ctr': ctr, 'cpc': cpc, 'cpm': cpm,
                        'frequency': frequency, 'landing_views': landing_views,
                        'view_content': view_content, 'leads': leads,
                        'link_clicks': link_clicks, 'cpl': cpl,
                        'cpc_landing': cpc_landing, 'funnel': funnel,
                        'top_demographics': [
                            {'age': r['age'], 'gender': r['gender'],
                             'impressions': int(r['impressions']),
                             'clicks': int(r.get('clicks', 0)),
                             'ctr': float(r.get('ctr', 0)),
                             'spend': float(r.get('spend', 0))}
                            for r in top_demo
                        ],
                    }
            except Exception as ex:
                with lock:
                    results[cid] = {'error': str(ex)}

        threads = [threading.Thread(target=_fetch_campaign, args=(c,)) for c in camps_data]
        for t in threads: t.start()
        for t in threads: t.join(timeout=20)

        # Build response
        campaigns = []
        for c in camps_data:
            cid = c['id']
            metrics = results.get(cid, {})
            budget_satang = int(c.get('daily_budget') or c.get('lifetime_budget') or 0)
            campaigns.append({
                'id': cid,
                'name': c['name'],
                'status': c['status'],
                'effective_status': c['effective_status'],
                'objective': c.get('objective', ''),
                'daily_budget': budget_satang,
                'daily_budget_thb': round(budget_satang / 100, 2),
                'is_lifetime': bool(c.get('lifetime_budget') and not c.get('daily_budget')),
                'start_time': c.get('start_time', ''),
                **metrics,
            })

        total_spend = sum(c.get('spend', 0) for c in campaigns)
        total_leads = sum(c.get('leads', 0) for c in campaigns)
        return jsonify({
            'campaigns': campaigns,
            'summary': {
                'total_spend': round(total_spend, 2),
                'total_leads': int(total_leads),
                'overall_cpl': round(total_spend / total_leads, 2) if total_leads else None,
            }
        }), 200

    except urllib.error.HTTPError as he:
        err_body = he.read().decode()
        try:
            msg = json.loads(err_body).get('error', {}).get('message', err_body)
        except Exception:
            msg = err_body
        return jsonify({'error': f'Meta API: {msg}'}), 400
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ==================== CAMPAIGN CONTROL (TOGGLE / BUDGET / DUPLICATE) ====================

@facebook_ads_bp.route('/api/facebook-ads/meta-campaign-control', methods=['POST'])
@login_required
@admin_required
def meta_campaign_control():
    """Toggle status, update daily budget, or duplicate a campaign via Meta API."""
    import urllib.request, urllib.parse, urllib.error
    conn = cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        token, account_id = _get_meta_credentials(cursor)
        if not token or not account_id:
            return jsonify({'error': 'ยังไม่ได้ตั้งค่า Meta Access Token'}), 400
        if not account_id.startswith('act_'):
            account_id = f'act_{account_id}'

        data = request.get_json(silent=True) or {}
        action = data.get('action', '')
        campaign_id = (data.get('campaign_id') or '').strip()
        if not campaign_id:
            return jsonify({'error': 'Missing campaign_id'}), 400

        def _post(url, payload):
            body = urllib.parse.urlencode(payload).encode('utf-8')
            req = urllib.request.Request(url, data=body, method='POST',
                                          headers={'User-Agent': 'EKGShops/1.0',
                                                   'Content-Type': 'application/x-www-form-urlencoded'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())

        if action == 'toggle':
            new_status = data.get('new_status', 'PAUSED')
            if new_status not in ('ACTIVE', 'PAUSED'):
                return jsonify({'error': 'new_status ต้องเป็น ACTIVE หรือ PAUSED'}), 400
            url = f'https://graph.facebook.com/v19.0/{campaign_id}'
            result = _post(url, {'status': new_status, 'access_token': token})
            return jsonify({'success': True, 'campaign_id': campaign_id,
                            'new_status': new_status, 'meta_response': result}), 200

        elif action == 'update_budget':
            budget_thb = float(data.get('daily_budget_thb', 0))
            if budget_thb <= 0:
                return jsonify({'error': 'งบต้องมากกว่า 0'}), 400
            budget_satang = int(budget_thb * 100)
            url = f'https://graph.facebook.com/v19.0/{campaign_id}'
            result = _post(url, {'daily_budget': budget_satang, 'access_token': token})
            return jsonify({'success': True, 'campaign_id': campaign_id,
                            'daily_budget_thb': budget_thb, 'meta_response': result}), 200

        elif action == 'duplicate':
            # Use Meta /copies endpoint — creates a paused copy with all ad sets and ads
            url = f'https://graph.facebook.com/v19.0/{campaign_id}/copies'
            result = _post(url, {
                'deep_copy': 'true',
                'status_option': 'PAUSED',
                'access_token': token
            })
            return jsonify({'success': True, 'original_id': campaign_id,
                            'new_campaign_id': result.get('copied_campaign_id') or result.get('id'),
                            'meta_response': result}), 200

        else:
            return jsonify({'error': f'Unknown action: {action}'}), 400

    except urllib.error.HTTPError as he:
        err_body = he.read().decode()
        try:
            msg = json.loads(err_body).get('error', {}).get('message', err_body)
        except Exception:
            msg = err_body
        return jsonify({'error': f'Meta API: {msg}'}), 400
    except Exception as e:
        return handle_error(e)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
