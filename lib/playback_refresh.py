"""Immediate local UI indexes after a confirmed Stremio playback write-back."""


def refresh_continue_index(store, context, remote):
    """Refresh local Continue Watching from the already-verified account state.

    No network calls happen here. For a completed series episode, use the
    playback metadata we already had to resolve Stremio's 1ms next-episode
    pointer immediately instead of waiting for the 15-minute maintenance pass.
    """
    from lib import continue_index

    state = store.load()
    library = state.get('library', []) if isinstance(state, dict) else []
    continue_index.seed(store.directory, library)

    if not isinstance(remote, dict) or context.get('kind') != 'series':
        return
    media_id = str(context.get('meta_id') or '')
    videos = context.get('videos') if isinstance(context.get('videos'), list) else []
    if not media_id or not videos:
        return

    from core.continue_playback import continue_series_target
    target, resume_ms = continue_series_target(videos, remote)
    # A partial episode is already visible after seed(). Only resolve the
    # completed/sentinel case when we can positively identify an aired target.
    state_row = remote.get('state') if isinstance(remote.get('state'), dict) else {}
    try:
        offset = max(0, int(float(state_row.get('timeOffset') or 0)))
    except (TypeError, ValueError):
        offset = 0
    if offset > 1 and target is not None and str(target.get('id') or '') == str(state_row.get('video_id') or ''):
        return
    if target is None:
        return

    projected = dict(remote)
    projected['id'] = media_id
    for key in ('name', 'poster', 'posterShape', 'behaviorHints'):
        if projected.get(key) in (None, '', {}, []):
            value = context.get(key)
            if value not in (None, '', {}, []):
                projected[key] = value
    continue_index.resolve_series(store.directory, media_id, projected, target, resume_ms, False)
