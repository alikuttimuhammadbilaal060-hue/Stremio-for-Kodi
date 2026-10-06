"""Read-only source aggregation; no account token is sent to providers."""
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import time
from protocol import fetch, resource_url


def supports(manifest, kind, identity, resource_name='stream'):
    for resource in manifest.get('resources', []):
        spec = manifest if resource == resource_name else resource
        if not isinstance(spec, dict):
            continue
        if resource != resource_name and spec.get('name') != resource_name:
            continue
        types = spec.get('types', manifest.get('types', []))
        prefixes = spec.get('idPrefixes')
        if kind in types and (prefixes is None or any(identity.startswith(p) for p in prefixes)):
            return True
    return False


def direct_url(stream):
    url = stream.get('url', '')
    if not isinstance(url, str) or '|' in url or any(ord(c) < 32 for c in url):
        return False
    parsed = urlsplit(url)
    hints = stream.get('behaviorHints') or {}
    # A playable direct URL remains valid even when a Stremio provider also
    # includes infoHash/externalUrl metadata. Some debrid providers do this
    # (for example Torrentio-style responses). Only reject URLs that Kodi
    # cannot safely play without extra proxy/header handling.
    return (parsed.scheme in ('http', 'https') and bool(parsed.netloc)
            and not parsed.username and not parsed.password
            and isinstance(hints, dict) and not hints.get('proxyHeaders'))


def embedded_sources(meta, identity):
    """Return exclusive video streams, or None when aggregation is needed."""
    video = next((v for v in meta.get('videos', [])
                  if isinstance(v, dict) and v.get('id') == identity), None)
    if not video or not isinstance(video.get('streams'), list):
        return None
    rows, skipped = [], 0
    for stream in video['streams']:
        if not isinstance(stream, dict) or not direct_url(stream):
            skipped += 1
            continue
        hints = stream.get('behaviorHints') or {}
        detail = stream.get('title') or stream.get('name') or video.get('title') or 'Stream'
        name = stream.get('name') or 'Stored video'
        rows.append({'url': stream['url'], 'label': '{} · {}'.format(name, detail),
                     'provider': name, 'detail': detail,
                     'subtitles': stream.get('subtitles', []),
                     'filename': hints.get('filename', '')})
    return rows, skipped, 0


def collect(providers, kind, identity, fetcher=fetch, timing=None):
    selected, seen = [], set()
    for provider in providers:
        url = provider.get('transportUrl')
        if url and url not in seen and supports(provider.get('manifest', {}), kind, identity):
            seen.add(url)
            selected.append(provider)

    def query(provider):
        started = time.monotonic()
        name = provider.get('manifest', {}).get('name') or 'Addon'
        try:
            result = fetcher(resource_url(provider['transportUrl'], 'stream', kind, identity))
            streams = result.get('streams', [])
            if not isinstance(streams, list):
                raise ValueError('Invalid streams')
            good, skipped = [], 0
            for stream in streams:
                if not isinstance(stream, dict) or not direct_url(stream):
                    skipped += 1
                    continue
                detail = stream.get('title') or stream.get('name') or 'Stream'
                hints = stream.get('behaviorHints') or {}
                good.append({'url': stream['url'],
                             'label': '{} · {}'.format(name, detail),
                             'provider': name,
                             'detail': detail,
                             'subtitles': stream.get('subtitles', []),
                             'filename': hints.get('filename', '')})
            return good, skipped, 0, name, int((time.monotonic()-started)*1000)
        except Exception:
            # Never expose configured URLs or provider exception messages.
            return [], 0, 1, name, int((time.monotonic()-started)*1000)

    output, skipped, failed = [], 0, 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entries, ignored, errors, provider_name, elapsed_ms in pool.map(query, selected):
            output.extend(entries)
            skipped += ignored
            failed += errors
            if timing is not None:
                timing.append({'provider': str(provider_name)[:80], 'ms': max(0, elapsed_ms), 'failed': bool(errors), 'rows': len(entries)})
    return output, skipped, failed
