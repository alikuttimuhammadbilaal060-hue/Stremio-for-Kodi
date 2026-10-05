"""Playback branding independent of subtitles; supporter authority is MKGA.TV."""
import threading
import time

FULLSCREEN_VIDEO = 12005
REFRESH_SECONDS = 300
SUPPORTER_GRACE_SECONDS = 86400


def should_show(status, now):
    if not isinstance(status, dict) or status.get('premium') is not True:
        return True
    try:
        age = now - int(status.get('checked_at') or 0)
    except (TypeError, ValueError):
        return True
    return not 0 <= age <= SUPPORTER_GRACE_SECONDS


class PlaybackWatermark:
    def __init__(self, player, addon, gui=None, store_factory=None,
                 refresh_status=None, cached_status=None, clock=time.time):
        if gui is None:
            import xbmcgui as gui
        if store_factory is None:
            from lib.signin import account_store
            store_factory = account_store
        if refresh_status is None or cached_status is None:
            from lib.vortexo_premium import refresh, cached_state
            refresh_status = refresh_status or refresh
            cached_status = cached_status or cached_state
        self.player, self.addon, self.gui = player, addon, gui
        self.store_factory = store_factory
        self.refresh_status, self.cached_status = refresh_status, cached_status
        self.clock = clock
        self.window = self.label = None
        self.status = None
        self.next_check = 0
        self.worker = None
        self.identity = None
        self.last_diagnostic = None

    def _diagnostic(self, state):
        if state == self.last_diagnostic:
            return
        self.last_diagnostic = state
        try:
            import xbmc
            xbmc.log('Stremio for Kodi WATERMARK | ' + state, xbmc.LOGINFO)
        except Exception:
            pass

    def _owns_playback(self):
        if self.player._context:
            return True
        # Branding must not depend on valid metadata for progress write-back.
        try:
            import hashlib
            from account import Store
            digest = hashlib.sha256(self.player.getPlayingFile().encode()).hexdigest()
            context = Store(self.store_factory().directory / 'playback').load()
            return bool(context.get('url_hash') == digest)
        except Exception:
            return False

    def _refresh(self):
        try:
            store = self.store_factory()
            identity = store.load().get('token')
            status = self.refresh_status(store)
            # Discard responses for an account that changed during network I/O.
            if self.store_factory().load().get('token') == identity:
                self.identity, self.status = identity, status
        except Exception:
            pass  # Network failures never interrupt video playback.

    def _remove(self):
        if self.label is not None:
            try:
                self.window.removeControl(self.label)
            except Exception:
                pass
        self.window = self.label = None

    def _show(self):
        if self.label is not None:
            return
        window = self.gui.Window(FULLSCREEN_VIDEO)
        width = window.getWidth()
        label = self.gui.ControlLabel(max(0, width-172), 26, 136, 36, 'MKGA',
                                      font='font13', textColor='77FFFFFF',
                                      alignment=2)
        window.addControl(label)
        self.window, self.label = window, label
        # This control belongs to video fullscreen, not the subtitle stream.
        label.setVisibleCondition('Player.HasVideo + Window.IsActive(fullscreenvideo)')
        self.window, self.label = window, label

    def tick(self):
        try:
            # ProgressPlayer creates context only for Stremio-owned playback.
            if not self.player.isPlayingVideo():
                self._remove()
                self._diagnostic('idle')
                return
            if not self._owns_playback():
                self._remove()
                self._diagnostic('video without addon playback context')
                return
            now = self.clock()
            store = self.store_factory()
            identity = store.load().get('token')
            if identity != self.identity:
                self.identity, self.status = identity, None
                self.next_check = 0
            if self.status is None:
                self.status = self.cached_status(store)
            if now >= self.next_check and (self.worker is None or not self.worker.is_alive()):
                self.next_check = now + REFRESH_SECONDS
                self.worker = threading.Thread(target=self._refresh, daemon=True)
                self.worker.start()
            if should_show(self.status, now):
                self._show()
                self._diagnostic('overlay attached to fullscreen video')
            else:
                self._remove()
                self._diagnostic('hidden for supporter')
        except Exception as error:
            self._remove()
            # Log only the error type; URLs and account tokens stay private.
            self._diagnostic('overlay failed: ' + type(error).__name__)

    def close(self):
        self._remove()
