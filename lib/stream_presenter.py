"""Display-only stream rows. Never change resolver data or expose stream URLs."""
import re
from core.stream_ui import stream_card


def line(value, limit=350):
    text = re.sub(r'<[^>]*>', '', str(value or ''))
    text = re.sub(r'\[/?(?:B|I|CR|TAB|LIGHT|COLOR[^\]]*|UPPERCASE|LOWERCASE)\]', '', text, flags=re.I)
    text = re.sub(r'(?:https?|plugin|magnet)://\S+', '[source]', text, flags=re.I)
    text = ''.join(' ' if ord(ch) < 32 or ord(ch) == 127 else ch for ch in text)
    return ' '.join(text.split())[:limit]


def presentation(row):
    raw = row.get('card')
    card = raw if isinstance(raw, dict) else stream_card(row)
    quality = line(card.get('quality') or 'AUTO', 24)
    provider = line(card.get('provider') or row.get('provider') or 'Stream', 70)
    tech_parts = [line(part, 40) for part in line(card.get('tech')).split(' • ') if line(part, 40)]
    video_names = {'REMUX','BluRay','WEB-DL','WEBRip','AV1','H.265','H.264','Dolby Vision','HDR10','HDR','10bit'}
    video = [part for part in tech_parts if part in video_names]
    audio = [part for part in tech_parts if part not in video_names]
    title = line(' · '.join(dict.fromkeys([quality] + video + ([provider] if provider else []))), 180)
    detail_parts = []
    if audio:
        detail_parts.append('Audio: ' + ' / '.join(dict.fromkeys(audio)))
    languages = line(card.get('languages'), 80)
    if languages:
        detail_parts.append('Lang: ' + languages)
    if card.get('size'):
        detail_parts.append(line(card['size'], 24))
    filename = line(card.get('filename') or row.get('filename') or row.get('detail') or row.get('label'))
    if filename and filename not in detail_parts:
        detail_parts.append(filename)
    detail = line(' · '.join(detail_parts), 350)
    return {'title': title or provider, 'detail': detail or provider, 'quality': quality}


def stream_traits(row):
    view = presentation(row)
    text = ' '.join((view.get('title',''), view.get('detail',''))).upper()
    provider = line((row.get('card') or {}).get('provider') or row.get('provider') or 'Stream',70)
    codecs=[]
    if 'H.265' in text or 'HEVC' in text: codecs.append('HEVC / H.265')
    if 'H.264' in text or 'AVC' in text: codecs.append('H.264 / AVC')
    if 'AV1' in text: codecs.append('AV1')
    dynamic=[]
    if 'DOLBY VISION' in text or re.search(r'\bDV\b',text): dynamic.append('Dolby Vision')
    if 'HDR10' in text: dynamic.append('HDR10')
    elif re.search(r'\bHDR\b',text): dynamic.append('HDR')
    return {'provider':provider,'codecs':codecs,'dynamic':dynamic,'quality':view.get('quality','AUTO')}

def provider_choices(rows):
    return ['All'] + sorted({stream_traits(row)['provider'] for row in rows if stream_traits(row)['provider']})

def filter_rows(rows, provider='All', codec='All', dynamic='All'):
    out=[]
    for row in rows:
        t=stream_traits(row)
        if provider!='All' and t['provider']!=provider: continue
        if codec!='All' and codec not in t['codecs']: continue
        if dynamic!='All' and dynamic not in t['dynamic']: continue
        out.append(row)
    return out

def quality_choices(rows):
    values = {presentation(row)['quality'] for row in rows}
    order = ('4K', '1080p', '720p', '480p', '360p', 'AUTO')
    return ['All'] + sorted(values, key=lambda q: (order.index(q) if q in order else 99, q))


def target_label(meta, identity):
    if meta.get('type') != 'series':
        return line(meta.get('name') or meta.get('title'), 110)
    video = next((v for v in meta.get('videos', []) if v.get('id') == identity), {})
    season, episode = video.get('season'), video.get('episode')
    code = 'S{:02d}E{:02d}'.format(season, episode) if type(season) is int and type(episode) is int else ''
    return line(' · '.join(v for v in (code, video.get('name') or video.get('title') or meta.get('name')) if v), 110)


def playback_meta(meta, identity):
    result = dict(meta)
    if meta.get('type') == 'series':
        result['_stremio_meta_id'] = meta.get('_stremio_meta_id') or meta.get('id')
        video = next((v for v in meta.get('videos', []) if v.get('id') == identity), {})
        result.update(id=identity, name=video.get('name') or video.get('title') or meta.get('name'),
                      season=video.get('season'), episode=video.get('episode'),
                      tvshowtitle=meta.get('name'), _media_type='episode')
    return result
