"""Run only the reviewed packaged collector inside Kodi's embedded Python.

RunScript(<driver>,<packaged-collector.py>,<new-private-evidence.json>)
This fixture does not start Connector, pair, sign, make network requests or
modify settings. Its single write creates a new inventory evidence file.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import xbmc
import xbmcvfs

EXPECTED_COLLECTOR_SHA256 = '1f8eca2f7ed358e89fbef54570fa6e8d793ff84052313c865ec5a52b21465389'


def main():
    if len(sys.argv) != 3:
        raise ValueError('Expected collector and new evidence file arguments')
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    if not source.is_absolute() or not source.is_file() or source.is_symlink():
        raise ValueError('Expected local collector file')
    if (not output.is_absolute() or not output.name.startswith('mkga-runtime-inventory-') or
            output.suffix != '.json' or not output.parent.is_dir()):
        raise ValueError('Expected a dedicated new local inventory evidence file')
    raw = source.read_bytes()
    if len(raw) > 32768 or hashlib.sha256(raw).hexdigest() != EXPECTED_COLLECTOR_SHA256:
        raise ValueError('Collector differs from reviewed Connector 0.3.9 package')
    spec = importlib.util.spec_from_file_location('mkga_inventory_fixture_collector', str(source))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = {'schema': 1, 'connectorVersion': '0.3.9',
              'collectorSha256': EXPECTED_COLLECTOR_SHA256,
              'runtime': module.collect(xbmc, xbmcvfs)}
    payload = json.dumps(report, sort_keys=True, indent=2).encode('utf-8') + b'\n'
    if len(payload) > 4096:
        raise ValueError('Inventory unexpectedly exceeds fixture evidence bound')
    descriptor = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(payload)


if __name__ == '__main__':
    main()
