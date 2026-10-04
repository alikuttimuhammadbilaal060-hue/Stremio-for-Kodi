
"""Stremio-native metadata aggregation for the skin.

No Kodi helper addons are required. Installed Stremio meta/catalog providers
are queried first and Cinemeta is used only as a Stremio protocol fallback.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from protocol import fetch, resource_url
from sources import supports

HOME_MANIFEST = 'https://v3-cinemeta.strem.io/manifest.json'
MERGE_FIELDS = (
    'name', 'description', 'poster', 'background', 'landscape', 'logo',
    'releaseInfo', 'released', 'year', 'runtime', 'imdbRating', 'country',
    'awards', 'status', 'imdb_id', 'moviedb_id', 'tvdb_id', 'behaviorHints',
    'languages', 'language', 'spokenLanguages', 'audioLanguages',
)


def _list(value):
    if isinstance(value, list):
        return [item for item in value if item not in (None, '')]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values):
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _person_image(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if re.fullmatch(r'/[A-Za-z0-9._/-]+', value):
        return 'https://image.tmdb.org/t/p/w342' + value
    return value if re.match(r'^https?://', value, re.I) else ''


def _person_rows(value, default_job):
    rows = []
    for entry in _list(value):
        if isinstance(entry, dict):
            nested = entry.get('person') if isinstance(entry.get('person'), dict) else entry
            name = str(nested.get('name') or nested.get('title') or entry.get('name') or '').strip()
            image = _person_image(nested.get('photo') or nested.get('image') or nested.get('profile')
                                  or nested.get('profile_path') or nested.get('poster') or nested.get('thumbnail'))
            specific = entry.get('character') or entry.get('job') or entry.get('role') or nested.get('character') or nested.get('job')
            job = ('as ' + str(specific).strip()) if entry.get('character') and str(specific).strip() else str(specific or default_job).strip()
        else:
            name, image, job = str(entry).strip(), '', default_job
        if name:
            rows.append({'name': name, 'job': job or default_job, 'poster': image})
    return rows


def _merge_people(rows):
    merged, order = {}, []
    generic = {'Cast', 'Director', 'Writer'}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        key = name.casefold()
        if key not in merged:
            merged[key] = {'name': name, 'job': str(row.get('job') or '').strip(),
                           'poster': _person_image(row.get('poster'))}
            order.append(key)
            continue
        current = merged[key]
        if not current.get('poster') and row.get('poster'):
            current['poster'] = _person_image(row.get('poster'))
        old_job, new_job = current.get('job') or '', str(row.get('job') or '').strip()
        if new_job and new_job != old_job:
            if old_job in generic and new_job not in generic:
                current['job'] = new_job
            elif new_job in generic and old_job not in generic:
                pass
            elif new_job not in old_job.split(' / '):
                current['job'] = ' / '.join(v for v in (old_job, new_job) if v)
    return [merged[key] for key in order]


def languages(meta):
    """Return provider-supplied spoken/audio languages as label/code rows.

    Metadata addons do not agree on one field name or value shape, so this is
    deliberately tolerant.  It never guesses from a production country.
    """
    meta = meta if isinstance(meta, dict) else {}
    source = (meta.get('languages') or meta.get('spokenLanguages')
              or meta.get('audioLanguages') or meta.get('language') or [])
    rows = []
    for value in _list(source):
        if isinstance(value, dict):
            code = str(value.get('code') or value.get('iso_639_1')
                       or value.get('iso639_1') or '').strip().lower()
            label = str(value.get('name') or value.get('english_name')
                        or value.get('label') or code).strip()
        else:
            label = str(value).strip()
            code = label.lower() if len(label) in (2, 3) else ''
        if not label:
            continue
        row = {'label': label, 'code': code.upper()}
        if row not in rows:
            rows.append(row)
    return rows
def normalize(meta, kind='', identity=''):
    meta = dict(meta) if isinstance(meta, dict) else {}
    if identity:
        meta.setdefault('id', identity)
    if kind:
        meta.setdefault('type', kind)
    genres = _list(meta.get('genres') or meta.get('genre'))
    meta['genres'] = _dedupe([str(v) for v in genres])
    cast_people = _merge_people(_person_rows(meta.get('castPeople'), 'Cast') + _person_rows(meta.get('cast'), 'Cast'))
    director_people = _merge_people(_person_rows(meta.get('directorPeople'), 'Director') + _person_rows(meta.get('director'), 'Director'))
    writer_people = _merge_people(_person_rows(meta.get('writerPeople'), 'Writer') + _person_rows(meta.get('writer'), 'Writer'))
    meta['castPeople'], meta['directorPeople'], meta['writerPeople'] = cast_people, director_people, writer_people
    meta['cast'] = [row['name'] for row in cast_people]
    meta['director'] = [row['name'] for row in director_people]
    meta['writer'] = [row['name'] for row in writer_people]
    videos = meta.get('videos')
    meta['videos'] = [v for v in videos if isinstance(v, dict)] if isinstance(videos, list) else []
    links = meta.get('links')
    meta['links'] = [v for v in links if isinstance(v, dict)] if isinstance(links, list) else []
    return meta


def _home_descriptor(fetcher=fetch):
    manifest = fetcher(HOME_MANIFEST)
    return {'transportUrl': HOME_MANIFEST, 'manifest': manifest, 'fallback': True}


def candidates(providers, kind, identity, fetcher=fetch):
    rows, seen = [], set()
    for provider in providers or []:
        url = provider.get('transportUrl') if isinstance(provider, dict) else None
        manifest = provider.get('manifest', {}) if isinstance(provider, dict) else {}
        if url and url not in seen and supports(manifest, kind, identity, 'meta'):
            seen.add(url)
            rows.append(provider)
    if HOME_MANIFEST not in seen:
        try:
            rows.append(_home_descriptor(fetcher))
        except Exception:
            pass
    return rows
def merged_meta(kind, identity, providers=(), fetcher=fetch):
    rows = candidates(providers, kind, identity, fetcher)
    def one(provider):
        try:
            payload = fetcher(resource_url(provider['transportUrl'], 'meta', kind, identity))
            meta = payload.get('meta') if isinstance(payload, dict) else None
            if not isinstance(meta, dict) or str(meta.get('id', identity)) != str(identity):
                return {}
            return normalize(meta, kind, identity)
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(rows)))) as pool:
        results = list(pool.map(one, rows)) if rows else []

    merged = {'id': identity, 'type': kind, 'genres': [], 'cast': [],
              'director': [], 'writer': [], 'castPeople': [], 'directorPeople': [], 'writerPeople': [], 'videos': [], 'links': []}
    for meta in results:
        if not meta:
            continue
        for field in MERGE_FIELDS:
            value = meta.get(field)
            if value not in (None, '', [], {}) and merged.get(field) in (None, '', [], {}):
                merged[field] = value
        for field in ('genres', 'cast', 'director', 'writer', 'links'):
            merged[field] = _dedupe(merged.get(field, []) + meta.get(field, []))
        for field in ('castPeople', 'directorPeople', 'writerPeople'):
            merged[field] = _merge_people(merged.get(field, []) + meta.get(field, []))
        if len(meta.get('videos', [])) > len(merged.get('videos', [])):
            merged['videos'] = meta['videos']
        if not merged.get('trailers') and meta.get('trailers'):
            merged['trailers'] = meta.get('trailers')
        if not merged.get('trailerStreams') and meta.get('trailerStreams'):
            merged['trailerStreams'] = meta.get('trailerStreams')
    return normalize(merged, kind, identity)
def resolve_identity(kind, identity='', query='', fetcher=fetch):
    identity = str(identity or '').strip()
    if identity:
        return identity, {}
    query = str(query or '').strip()
    if not query:
        return '', {}
    try:
        payload = fetcher(resource_url(HOME_MANIFEST, 'catalog', kind, 'top', {'search': query}))
        rows = [normalize(v, kind) for v in payload.get('metas', []) if isinstance(v, dict)]
    except Exception:
        return '', {}
    if not rows:
        return '', {}
    key = re.sub(r'\W+', '', query).casefold()
    best = next((row for row in rows
                 if re.sub(r'\W+', '', str(row.get('name', ''))).casefold() == key), rows[0])
    return str(best.get('id', '')), best


def details(kind, identity='', query='', providers=(), fetcher=fetch):
    resolved, preview = resolve_identity(kind, identity, query, fetcher)
    if not resolved:
        return normalize(preview, kind)
    meta = merged_meta(kind, resolved, providers, fetcher)
    for key, value in preview.items():
        if meta.get(key) in (None, '', [], {}):
            meta[key] = value
    return normalize(meta, kind, resolved)


def people(meta, role='cast'):
    if role == 'crew':
        rows = list(meta.get('directorPeople') or _person_rows(meta.get('director'), 'Director'))
        rows += list(meta.get('writerPeople') or _person_rows(meta.get('writer'), 'Writer'))
    else:
        rows = list(meta.get('castPeople') or _person_rows(meta.get('cast'), 'Cast'))
    return _merge_people(rows)

def trailer_rows(meta):
    rows, seen = [], set()
    for row in meta.get('trailerStreams') or []:
        if not isinstance(row, dict):
            continue
        yt = str(row.get('ytId', ''))
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', yt) and yt not in seen:
            seen.add(yt)
            rows.append({'id': yt, 'name': row.get('title') or 'Trailer'})
    for row in meta.get('trailers') or []:
        if not isinstance(row, dict):
            continue
        yt = str(row.get('source', ''))
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', yt) and yt not in seen:
            seen.add(yt)
            rows.append({'id': yt, 'name': row.get('type') or 'Trailer'})
    return rows


def seasons(meta):
    counts = {}
    for video in meta.get('videos', []):
        try:
            season = int(video.get('season', 0))
        except (TypeError, ValueError):
            continue
        counts[season] = counts.get(season, 0) + 1
    return [{'season': season, 'count': counts[season]} for season in sorted(counts)]


def episodes(meta, season):
    try:
        season = int(season)
    except (TypeError, ValueError):
        return []
    rows = []
    for video in meta.get('videos', []):
        try:
            current = int(video.get('season', 0))
        except (TypeError, ValueError):
            continue
        if current == season and video.get('id'):
            rows.append(dict(video))
    return sorted(rows, key=lambda row: int(row.get('episode') or row.get('number') or 0))
def _catalogs_for(provider, kind):
    manifest = provider.get('manifest', {})
    for catalog in manifest.get('catalogs', []):
        if not isinstance(catalog, dict) or catalog.get('type') != kind or not catalog.get('id'):
            continue
        extras = {str(e.get('name')) for e in catalog.get('extra', []) if isinstance(e, dict)}
        yield catalog, extras


def search(query, providers=(), kinds=('movie', 'series'), limit=60, fetcher=fetch):
    query = str(query or '').strip()
    if not query:
        return []
    try:
        home = _home_descriptor(fetcher)
    except Exception:
        home = None

    pool, seen_urls = [], set()
    for provider in list(providers or []) + ([home] if home else []):
        if not provider:
            continue
        url = provider.get('transportUrl')
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        pool.append(provider)

    output, seen_ids = [], set()
    for provider in pool:
        manifest = provider.get('manifest', {})
        for kind in kinds:
            for catalog, extras in _catalogs_for(provider, kind):
                if 'search' not in extras:
                    continue
                try:
                    payload = fetcher(resource_url(
                        provider['transportUrl'], 'catalog', kind, catalog['id'],
                        {'search': query}))
                except Exception:
                    continue
                for row in payload.get('metas', []):
                    if not isinstance(row, dict):
                        continue
                    rid = str(row.get('id', ''))
                    key = (kind, rid)
                    if not rid or key in seen_ids:
                        continue
                    seen_ids.add(key)
                    output.append(normalize(row, row.get('type') or kind, rid))
                    if len(output) >= limit:
                        return output
    return output


def recommendations(meta, providers=(), limit=24, fetcher=fetch):
    kind, identity = meta.get('type'), meta.get('id')
    if kind not in ('movie', 'series') or not identity:
        return []
    try:
        home = _home_descriptor(fetcher)
    except Exception:
        home = None
    pool, seen_urls = [], set()
    for provider in list(providers or []) + ([home] if home else []):
        if not provider:
            continue
        url = provider.get('transportUrl')
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        pool.append(provider)

    genre = (meta.get('genres') or [''])[0]
    output, seen_ids = [], {identity}
    for provider in pool[:4]:
        for catalog, extras in _catalogs_for(provider, kind):
            params = {'genre': genre} if genre and 'genre' in extras else None
            try:
                payload = fetcher(resource_url(provider['transportUrl'], 'catalog', kind, catalog['id'], params))
            except Exception:
                continue
            for row in payload.get('metas', []):
                if not isinstance(row, dict):
                    continue
                rid = str(row.get('id', ''))
                if not rid or rid in seen_ids:
                    continue
                seen_ids.add(rid)
                output.append(normalize(row, kind, rid))
                if len(output) >= limit:
                    return output
            if output:
                break
    return output


def runtime_seconds(value):
    match = re.search(r'(\d+)\s*min', str(value or ''), re.I)
    return int(match.group(1)) * 60 if match else 0
