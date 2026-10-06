"""RatingPosterDB artwork helper for MKGA-synced Stremio for Kodi settings."""
import re
import time
from urllib.parse import quote

_IMDB = re.compile(r'(tt\d{5,12})', re.I)
_CACHE = {'at': 0, 'enabled': False, 'key': ''}


def imdb_id(row):
    row = row if isinstance(row, dict) else {}
    hints = row.get('behaviorHints') if isinstance(row.get('behaviorHints'), dict) else {}
    values = (
        row.get('imdb_id'), row.get('imdbId'), hints.get('imdbId'),
        row.get('id'), row.get('_id'), row.get('video_id')
    )
    for value in values:
        match = _IMDB.search(str(value or ''))
        if match:
            return match.group(1).lower()
    return ''


def _remote_settings(refresh=False):
    now = int(time.time())
    if not refresh and now - int(_CACHE.get('at') or 0) < 60:
        return {'rpdbEnabled': _CACHE['enabled'], 'rpdbApiKey': _CACHE['key']}
    enabled, key = False, ''
    try:
        from lib.signin import account_store
        from lib.vortexo_premium import hub_state
        hub = hub_state(account_store(), refresh_remote=refresh, max_age=300)
        settings = hub.get('mkgaSettings') if isinstance(hub, dict) else None
        if isinstance(settings, dict):
            raw = settings.get('rpdbApiKey')
            key = raw.strip() if isinstance(raw, str) else ''
            enabled = bool(settings.get('rpdbEnabled')) and bool(key)
    except Exception:
        enabled, key = False, ''
    _CACHE.update({'at': now, 'enabled': enabled, 'key': key})
    return {'rpdbEnabled': enabled, 'rpdbApiKey': key}


def poster_url(row, fallback=None, settings=None):
    row = row if isinstance(row, dict) else {}
    fallback = row.get('poster') if fallback is None else fallback
    config = settings if isinstance(settings, dict) else _remote_settings()
    key = str(config.get('rpdbApiKey') or '').strip()
    identity = imdb_id(row)
    if not config.get('rpdbEnabled') or not key or not identity:
        return fallback or ''
    return 'https://api.ratingposterdb.com/{}/imdb/poster-default/{}.jpg'.format(
        quote(key, safe=''), identity
    )


def clear_cache():
    _CACHE.update({'at': 0, 'enabled': False, 'key': ''})
