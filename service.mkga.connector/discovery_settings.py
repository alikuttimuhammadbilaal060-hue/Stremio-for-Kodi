"""Apply account discovery settings without storing credentials in sync receipts."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def apply_settings(payload,device_id,engine,path):
    if not isinstance(payload,dict) or set(payload)!={'mdblist'}:raise ValueError('Invalid discovery settings')
    value=payload['mdblist']
    if not isinstance(value,dict) or set(value)!={'connected','apiKey'} or type(value['connected'])!=bool:raise ValueError('Invalid discovery settings')
    target=value['apiKey']
    if not isinstance(target,str) or (value['connected'] and not re.fullmatch(r'[a-zA-Z0-9_-]{8,256}',target)) or (not value['connected'] and target!=''):
        raise ValueError('Invalid discovery settings')
    if not isinstance(device_id,str) or not device_id:raise ValueError('Device identity required')
    path=Path(path)
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Invalid discovery receipt location')
    previous=[]
    try:
        with path.open('rb') as source:raw=source.read(4097)
        state=json.loads(raw) if len(raw)<=4096 else {}
        if state.get('schema')==1 and isinstance(state.get('managedHashes'),list):
            previous=[item for item in state['managedHashes'] if isinstance(item,str) and re.fullmatch(r'[0-9a-f]{64}',item)][:2]
    except (OSError,ValueError,AttributeError):pass
    current=engine.getSetting('mdblist_api_key')
    owned=digest(current) in previous
    # An unconfigured account does not erase a user's unrelated local key.
    if not value['connected'] and not owned:return False
    hashes=[digest(target)] if target else []
    if owned and current and digest(current) not in hashes:hashes.append(digest(current))
    state={'schema':1,'deviceHash':digest(device_id),'managedHashes':hashes}
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.discovery-',delete=False) as output:
            temporary=Path(output.name);json.dump(state,output);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()
    if current==target:return False
    engine.setSetting('mdblist_api_key',target)
    if engine.getSetting('mdblist_api_key')!=target:
        raise RuntimeError('Discovery settings were not applied by Kodi')
    return True
