"""Per-request device proof. Private keys never enter Kodi profile storage."""
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import uuid


def validate_pairing_response(result, protected=False):
    if not isinstance(result, dict):
        raise ValueError('Invalid pairing response')
    identity = result.get('deviceId')
    token = result.get('deviceToken')
    if (not isinstance(identity, str) or str(uuid.UUID(identity)) != identity or
            not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,512}', token)):
        raise ValueError('Invalid pairing credentials')
    if protected and result.get('deviceProofRequired') is not True:
        raise ValueError('Server did not confirm protected pairing')
    return identity, token


def helper_path(vfs):
    # Application-owned executable, never a path supplied by copied settings.
    return vfs.translatePath('special://xbmc/bin/mkga-device-key')


def run_helper(helper, action, identity, challenge=None):
    if str(uuid.UUID(identity)) != identity:
        raise ValueError('Invalid protected install identity')
    result = subprocess.run([helper, action, identity], input=challenge,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=15, check=True)
    if len(result.stdout) > 2048:
        raise ValueError('Invalid device key response')
    value = json.loads(result.stdout)
    if value.get('installId') != identity:
        raise ValueError('Device key identity mismatch')
    return value


def pairing_identity(addon, vfs):
    helper = helper_path(vfs)
    if not os.path.isfile(helper):
        return None  # Existing ordinary Connector remains supported.
    identity = addon.getSetting('device_install_id') or str(uuid.uuid4())
    public = run_helper(helper, 'create', identity)
    addon.setSetting('device_install_id', identity)
    if addon.getSetting('device_install_id') != identity:
        raise ValueError('Cannot persist protected install identity')
    return public['publicKey']


def prepare_new_pairing(vfs):
    """Explicit re-pairing uses a new identity without changing current settings."""
    helper = helper_path(vfs)
    if not os.path.isfile(helper):
        return None
    identity = str(uuid.uuid4())
    public = run_helper(helper, 'create', identity)
    return {'installId': identity, 'publicKey': public['publicKey']}


def signed_headers(addon, vfs, base, path, method, raw, headers):
    identity = addon.getSetting('device_install_id')
    # Only pairing acknowledgement enables proof. Old pairings are not upgraded
    # by merely copying a helper into an app.
    if addon.getSetting('device_proof_enabled') != 'true':
        return headers
    if not identity:
        raise ValueError('Protected device identity missing')
    helper = helper_path(vfs)
    if not os.path.isfile(helper):
        raise ValueError('Protected device key helper missing')
    payload = {'method': method, 'path': '/api/kodi/agent' + path,
               'bodySha256': hashlib.sha256(raw or b'').hexdigest()}
    challenge_req = urllib.request.Request(base + '/proof/challenge',
        data=json.dumps(payload).encode(), method='POST',
        headers={'Authorization': headers['Authorization'],
                 'Content-Type': 'application/json',
                 'User-Agent': headers.get('User-Agent', 'MKGA-Connector')})
    with urllib.request.urlopen(challenge_req, timeout=20) as response:
        challenge = json.loads(response.read(8193))
    message = challenge.get('message', '')
    # Reconstruct the entire expected message locally before asking Keychain to
    # sign it. A challenge endpoint cannot request arbitrary message signatures.
    device = addon.getSetting('device_id')
    challenge_id = challenge.get('id', '')
    if str(uuid.UUID(challenge_id)) != challenge_id:
        raise ValueError('Invalid server challenge identity')
    expiry = challenge.get('expiresAt')
    if not isinstance(expiry, int) or isinstance(expiry, bool):
        raise ValueError('Invalid server challenge expiry')
    expected = '\n'.join(['MKGA-DEVICE-PROOF-V1', device, challenge_id,
                          method, payload['path'], payload['bodySha256'], str(expiry)])
    if message != expected:
        raise ValueError('Server challenge does not match this request')
    signed = run_helper(helper, 'sign', identity, message.encode())
    return dict(headers, **{'X-MKGA-Challenge': challenge_id,
                           'X-MKGA-Signature': signed['signature']})
