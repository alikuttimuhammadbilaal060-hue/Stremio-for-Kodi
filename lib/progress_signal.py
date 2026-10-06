"""Kodi-session signal for playback state that was confirmed by Stremio."""
import time

SESSION_WINDOW_ID = 10000
REVISION_PROPERTY = 'stremioforkodi.progress.revision'
META_PROPERTY = 'stremioforkodi.progress.meta'
VIDEO_PROPERTY = 'stremioforkodi.progress.video'


def _window(gui=None):
    if gui is None:
        import xbmcgui as gui
    return gui.Window(SESSION_WINDOW_ID)


def snapshot(gui=None):
    try:
        window = _window(gui)
        return (window.getProperty(REVISION_PROPERTY),
                window.getProperty(META_PROPERTY),
                window.getProperty(VIDEO_PROPERTY))
    except Exception:
        return ('', '', '')


def publish(context, gui=None):
    try:
        window = _window(gui)
        revision = str(time.time_ns())
        window.setProperty(META_PROPERTY, str(context.get('meta_id') or ''))
        window.setProperty(VIDEO_PROPERTY, str(context.get('video_id') or ''))
        window.setProperty(REVISION_PROPERTY, revision)
        return revision
    except Exception:
        return ''
