import time as _time_mod
_BOT_CACHE = {
    'bot_settings': {'data': None, 'expires': 0},
    'colors':       {'data': None, 'expires': 0},
    'sizes':        {'data': None, 'expires': 0},
    'categories':   {'data': None, 'expires': 0},
    'promotions':   {'data': None, 'expires': 0},
}

def _bot_cache_get(key, ttl_seconds, fetch_fn):
    """Return cached data if still valid, otherwise fetch fresh and cache it."""
    entry = _BOT_CACHE[key]
    if entry['data'] is None or _time_mod.time() > entry['expires']:
        entry['data'] = fetch_fn()
        entry['expires'] = _time_mod.time() + ttl_seconds
    return entry['data']

def bot_cache_invalidate(*keys):
    """Call after Admin saves data to expire specific cache keys immediately."""
    for k in (keys or _BOT_CACHE.keys()):
        if k in _BOT_CACHE:
            _BOT_CACHE[k]['expires'] = 0
