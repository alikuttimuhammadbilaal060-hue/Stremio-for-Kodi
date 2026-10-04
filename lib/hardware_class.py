"""Privacy-safe hardware classification for performance reports.

Never returns a hostname, serial, MAC, raw device-tree model or other unique identifier.
"""
from pathlib import Path


def classify(model_text='', platform=''):
    text = str(model_text or '').lower()
    plat = str(platform or '').lower()
    if 'raspberry pi 3' in text:
        return 'Raspberry Pi 3'
    if any(name in text for name in ('raspberry pi 4','raspberry pi 5','raspberry pi 400')):
        return 'Raspberry Pi 4+'
    if 'raspberry pi' in text:
        return 'Raspberry Pi'
    if 'android' in plat:
        return 'Android TV'
    if 'linux' in plat:
        return 'Generic Linux'
    if 'mac' in plat or 'osx' in plat:
        return 'macOS'
    if 'windows' in plat:
        return 'Windows'
    return 'Other'


def current(platform=''):
    raw = ''
    try:
        raw = Path('/proc/device-tree/model').read_text(errors='ignore').replace('\x00','').strip()
    except Exception:
        pass
    return classify(raw, platform)
