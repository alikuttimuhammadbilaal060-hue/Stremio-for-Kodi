"""Opt-in update notice: release notes from MKGA, installation through Kodi."""
import json
import re
import threading
import time
from urllib.request import Request, HTTPRedirectHandler, build_opener

ENDPOINT = 'https://mkga.tv/api/projects/stremio-for-kodi/detail'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Unexpected release redirect')


def stable_version(value):
    match = re.fullmatch(r'v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})', str(value or ''))
    return tuple(map(int, match.groups())) if match else None


def newer_release(payload, installed):
    release = payload.get('release') if isinstance(payload, dict) else None
    if not isinstance(release, dict):
        return None
    candidate = stable_version(release.get('version'))
    # Preview versions compare against their base; never downgrade to old stable.
    current = stable_version(str(installed).split('-')[0])
    if not candidate or not current or candidate <= current:
        return None
    expected = 'https://github.com/0eroiQ/Stremio-for-Kodi/releases/tag/v' + '.'.join(map(str, candidate))
    if release.get('url') != expected:
        return None
    return {'version': release['version'], 'body': str(release.get('body') or 'Bug fixes and improvements.')[:3000]}


class UpdateNotice:
    def __init__(self, addon, profile, gui=None, kodi=None, fetch_release=None, clock=time.time):
        if gui is None:
            import xbmcgui as gui
        if kodi is None:
            import xbmc as kodi
        from account import Store
        self.addon, self.gui, self.kodi = addon, gui, kodi
        self.store = Store(profile / 'update-notice')
        self.fetch_release = fetch_release or self._fetch
        self.clock = clock
        self.next_check = 0
        self.worker = None
        self.pending = None

    def _fetch(self):
        request = Request(ENDPOINT, headers={'Accept': 'application/json', 'User-Agent': 'Stremio-for-Kodi update check'})
        with build_opener(NoRedirect()).open(request, timeout=6) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Release metadata too large')
        return json.loads(raw)

    def _check(self):
        try:
            candidate = newer_release(self.fetch_release(), self.addon.getAddonInfo('version'))
            if candidate and self.store.load().get('dismissed_version') != candidate['version']:
                self.pending = candidate
        except Exception:
            pass

    def tick(self):
        try:
            # Never interrupt video, Info, streams, typing or another addon.
            if self.kodi.Player().isPlayingVideo():
                return
            window = self.gui.Window(self.gui.getCurrentWindowId())
            if window.getProperty('stremioforkodi.window.owner') != 'script.stremioelec' or window.getProperty('stremioforkodi.window.role') != 'home':
                return
            now = self.clock()
            if now >= self.next_check and (self.worker is None or not self.worker.is_alive()):
                self.next_check = now + 900
                self.worker = threading.Thread(target=self._check, daemon=True)
                self.worker.start()
            if self.pending:
                release, self.pending = self.pending, None
                self.prompt(release)
        except Exception:
            pass

    def prompt(self, release):
        from lib.ui_dialogs import dialog
        message = 'Stremio for Kodi ' + release['version'] + '\n\n' + release['body']
        chosen = dialog().yesno('New version available', message, nolabel='Cancel', yeslabel='Update')
        if chosen:
            self.kodi.executebuiltin('UpdateAddonRepos')
            self.kodi.executebuiltin('ActivateWindow(AddonBrowser,addons://outdated/,return)')
        else:
            state = self.store.load()
            state['dismissed_version'] = release['version']
            self.store.save(state)
