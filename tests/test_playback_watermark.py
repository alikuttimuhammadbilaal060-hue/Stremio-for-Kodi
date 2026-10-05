"""No Kodi installation or network is needed for overlay lifecycle checks."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch, create_autospec

spec = importlib.util.spec_from_file_location('playback_watermark', Path(__file__).resolve().parents[1]/'lib/playback_watermark.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WatermarkTests(unittest.TestCase):
    def make(self, premium=False, preview=False):
        gui = Mock()
        # Kodi 21 ControlLabel constructor: no shadowColor keyword.
        def control_label(x, y, width, height, label, font=None,
                          textColor=None, disabledColor=None,
                          alignment=0, hasPath=False, angle=0):
            pass
        gui.ControlLabel = create_autospec(control_label, return_value=Mock())
        gui.Window.return_value.getWidth.return_value = 1920
        player = Mock()
        player._context = {'video_id': 'test'}
        player.isPlayingVideo.return_value = True
        addon = Mock()
        addon.getSetting.return_value = 'true' if preview else 'false'
        store = Mock()
        store.load.return_value = {'token': 'test-only'}
        status = {'premium': premium, 'checked_at': 1000}
        overlay = module.PlaybackWatermark(player, addon, gui=gui,
                    store_factory=lambda: store, refresh_status=lambda _: status,
                    cached_status=lambda _: status, clock=lambda: 1000)
        overlay.next_check = 2000
        overlay.identity = 'test-only'
        return overlay, gui, player, store

    def test_free_watermark_does_not_read_or_change_subtitles(self):
        overlay, gui, player, _ = self.make()
        overlay.tick()
        self.assertIsNotNone(overlay.label)
        gui.Window.assert_called_once_with(12005)
        player.getSubtitles.assert_not_called()
        player.showSubtitles.assert_not_called()
        player.setSubtitles.assert_not_called()
        first = overlay.label
        overlay.tick()
        self.assertIs(first, overlay.label)
        self.assertEqual(gui.ControlLabel.call_count, 1)

    def test_supporter_removes_overlay_even_with_saved_preview_setting(self):
        overlay, gui, _, _ = self.make(preview=True)
        overlay.tick()
        self.assertIsNotNone(overlay.label)
        overlay.status = {'premium': True, 'checked_at': 1000}
        overlay.tick()
        self.assertIsNone(overlay.label)
        gui.Window.return_value.removeControl.assert_called_once()

    def test_other_addon_playback_and_stop_remove_mark(self):
        overlay, _, player, _ = self.make()
        overlay.tick()
        player._context = None
        overlay.tick()
        self.assertIsNone(overlay.label)
        player._context = {'video_id': 'test'}
        overlay.tick()
        player.isPlayingVideo.return_value = False
        overlay.tick()
        self.assertIsNone(overlay.label)

    def test_offline_supporter_grace_is_bounded_and_unknown_is_free(self):
        self.assertFalse(module.should_show({'premium': True, 'checked_at': 1000}, 1100))
        self.assertTrue(module.should_show({'premium': True, 'checked_at': 1000}, 1000+86401))
        self.assertTrue(module.should_show({'premium': True, 'checked_at': 2000}, 1000))
        self.assertTrue(module.should_show(None, 1000))

    def test_failed_status_check_never_stops_playback(self):
        overlay, _, player, _ = self.make()
        overlay.refresh_status = Mock(side_effect=RuntimeError('offline'))
        overlay._refresh()
        overlay.tick()
        self.assertIsNotNone(overlay.label)
        player.stop.assert_not_called()

    def test_stream_without_progress_metadata_still_has_branding(self):
        import hashlib
        import sys
        overlay, _, player, store = self.make()
        player._context = None
        player.getPlayingFile.return_value = 'test-stream'
        store.directory = Path('/test-profile')
        playback = Mock()
        playback.load.return_value = {
            'url_hash': hashlib.sha256(b'test-stream').hexdigest()}
        with patch.dict(sys.modules, {'account': types.SimpleNamespace(Store=lambda _: playback)}):
            overlay.tick()
            self.assertIsNotNone(overlay.label)
            player.getPlayingFile.return_value = 'another-addon-stream'
            overlay.tick()
            self.assertIsNone(overlay.label)

    def test_close_removes_overlay(self):
        overlay, _, _, _ = self.make()
        overlay.tick()
        overlay.close()
        self.assertIsNone(overlay.label)


if __name__ == '__main__':
    unittest.main()
