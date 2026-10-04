"""Repeatable local benchmark for Raspberry Pi-class Kodi devices.

The benchmark intentionally performs no network I/O and records only durations and
row/item counts through the existing privacy-safe performance report store.
"""
import statistics
import time
from pathlib import Path

SAMPLES = 5
# Provisional engineering budgets. A real Pi 3 pass is still required before the
# tracking issue can be considered complete.
TARGET_MS = {
    'benchmark.cached_home': 350,
    'benchmark.snapshot_load': 150,
    'benchmark.continue_index': 120,
    'benchmark.account_load': 80,
    'benchmark.stream_cache': 120,
}


def _elapsed_ms(function):
    started = time.monotonic()
    value = function()
    return max(0, int(round((time.monotonic() - started) * 1000.0))), value


def _sample(function, samples=SAMPLES):
    values = []
    last = None
    # One warm-up avoids measuring Python/module/SQLite first-open cost as every
    # subsequent couch-navigation action.
    last = function()
    for _ in range(max(1, int(samples))):
        elapsed, last = _elapsed_ms(function)
        values.append(elapsed)
    return int(round(statistics.median(values))), last


def run(profile, account_home=None, snapshot_load=None, continue_rows=None, account_load=None, stream_cache_probe=None, recorder=None):
    profile = Path(profile)
    if account_home is None:
        from lib.backend import account_home
    if snapshot_load is None:
        from lib.home_snapshot import load as snapshot_load
    if continue_rows is None:
        from lib.continue_index import rows as continue_rows
    if account_load is None:
        from account import Store
        account_load = lambda root: Store(root).load()
    if stream_cache_probe is None:
        from lib.stream_index import _connect
        def stream_cache_probe(root):
            db = _connect(root)
            try:
                row = db.execute('SELECT COUNT(*) FROM streams').fetchone()
                return int((row or [0])[0] or 0)
            finally:
                db.close()
    if recorder is None:
        from lib.perf_report import record as recorder

    cached_ms, home = _sample(lambda: account_home(False))
    snapshot_ms, snapshot = _sample(lambda: snapshot_load(profile))
    continue_ms, continuing = _sample(lambda: continue_rows(profile, 100))
    account_ms, account_state = _sample(lambda: account_load(profile))
    stream_ms, stream_count = _sample(lambda: stream_cache_probe(profile))

    home = list(home or [])
    snapshot = list(snapshot or [])
    continuing = list(continuing or [])
    counts = {
        'benchmark.cached_home': (
            len(home), sum(len(row.get('items') or []) for row in home if isinstance(row, dict))),
        'benchmark.snapshot_load': (
            len(snapshot), sum(len(row.get('items') or []) for row in snapshot if isinstance(row, dict))),
        'benchmark.continue_index': (1 if continuing else 0, len(continuing)),
        'benchmark.account_load': (1 if isinstance(account_state, dict) else 0, len((account_state or {}).get('library') or []) if isinstance(account_state, dict) else 0),
        'benchmark.stream_cache': (1, max(0, int(stream_count or 0))),
    }
    metrics = {
        'benchmark.cached_home': cached_ms,
        'benchmark.snapshot_load': snapshot_ms,
        'benchmark.continue_index': continue_ms,
        'benchmark.account_load': account_ms,
        'benchmark.stream_cache': stream_ms,
    }
    for stage, elapsed in metrics.items():
        rows, items = counts[stage]
        recorder(profile, stage, elapsed, rows=rows, items=items)

    checks = {stage: elapsed <= TARGET_MS[stage] for stage, elapsed in metrics.items()}
    return {
        'metrics': metrics,
        'targets': dict(TARGET_MS),
        'checks': checks,
        'passed': all(checks.values()),
        'samples': SAMPLES,
    }
