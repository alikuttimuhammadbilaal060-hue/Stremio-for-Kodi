"""Explicit, privacy-safe Home performance report.

Only allowlisted PERF stage durations/counts plus broad environment versions are
submitted. kodi.log, URLs, account data, titles, keys and device IDs are never read.
"""
import hashlib
import json
from pathlib import Path

from account import Store
from lib.error_report import _environment, send_report

STAGES = (
    'home.cached', 'home.cached.total', 'ui.home.initial',
    'home.refresh.account.local', 'home.refresh.catalogs', 'home.refresh.library.local',
    'ui.home.full', 'ui.home.incremental', 'ui.home.background.total', 'home.refresh.total',
    'benchmark.cached_home', 'benchmark.snapshot_load', 'benchmark.continue_index',
    'benchmark.account_load', 'benchmark.stream_cache',
)
MAX_MS = 30 * 60 * 1000
MAX_COUNT = 10000


def _store(profile):
    return Store(Path(profile) / 'performance')


def record(profile, stage, elapsed=None, **counts):
    if stage not in STAGES:
        return
    row = {}
    if elapsed is not None:
        row['ms'] = max(0, min(MAX_MS, int(elapsed)))
    for key in ('rows', 'items'):
        if key in counts:
            row[key] = max(0, min(MAX_COUNT, int(counts[key])))
    state = _store(profile).load()
    timings = state.get('timings') if isinstance(state.get('timings'), dict) else {}
    timings[stage] = row
    state['timings'] = timings
    _store(profile).save(state)


def record_stream_providers(profile, rows):
    """Persist only provider display name + duration/status/count; never URLs."""
    safe = []
    for row in list(rows or [])[:40]:
        safe.append({
            'provider': str(row.get('provider') or 'Addon')[:80],
            'ms': max(0, min(MAX_MS, int(row.get('ms') or 0))),
            'failed': bool(row.get('failed')),
            'rows': max(0, min(MAX_COUNT, int(row.get('rows') or 0))),
        })
    state = _store(profile).load()
    state['streamProviders'] = safe
    _store(profile).save(state)


def load(profile):
    state = _store(profile).load()
    timings = state.get('timings')
    if not isinstance(timings, dict):
        return {}
    return {stage: dict(timings[stage]) for stage in STAGES
            if stage in timings and isinstance(timings[stage], dict)}



def set_couch_pass(profile, value):
    state = _store(profile).load()
    timings = state.get('timings') if isinstance(state.get('timings'), dict) else {}
    state = {'timings': timings, 'validation': {'couchPass': bool(value)}}
    _store(profile).save(state)


def load_validation(profile):
    state = _store(profile).load()
    value = state.get('validation')
    return {'couchPass': bool(value.get('couchPass'))} if isinstance(value, dict) else {}

def build_payload(profile, environment=None):
    timings = load(profile)
    if not timings:
        return None
    env = dict(environment or _environment())
    if not env.get('hardwareClass'):
        from lib.hardware_class import current
        env['hardwareClass'] = current(env.get('platform'))
    report = {
        'reportVersion': 1,
        'context': 'Home performance',
        'errorType': 'PerformanceReport',
        'addonVersion': str(env.get('addonVersion') or 'unknown')[:40],
        'kodiVersion': str(env.get('kodiVersion') or 'unknown')[:80],
        'platform': str(env.get('platform') or 'unknown')[:40],
        'pythonVersion': str(env.get('pythonVersion') or 'unknown')[:40],
        'hardwareClass': str(env.get('hardwareClass') or 'Other')[:40],
        'stack': [],
        'performance': timings,
    }
    provider_rows = _store(profile).load().get('streamProviders')
    if isinstance(provider_rows, list) and provider_rows:
        report['streamProviders'] = provider_rows[:40]
    validation = load_validation(profile)
    if validation:
        report['validation'] = validation
    identity = dict(report)
    identity['performance'] = {k: sorted(v) for k, v in timings.items()}
    report['fingerprint'] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()[:12]
    return report


def send(profile):
    payload = build_payload(profile)
    return bool(payload and send_report(payload))
