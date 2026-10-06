import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import types

spec = importlib.util.spec_from_file_location('update_notice', Path(__file__).resolve().parents[1]/'lib/update_notice.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class UpdateNoticeTests(unittest.TestCase):
    def test_only_newer_stable_canonical_releases_are_offered(self):
        data = {'release': {'version': 'v1.0.83', 'url': 'https://github.com/0eroiQ/Stremio-for-Kodi/releases/tag/v1.0.83', 'body': 'Changes'}}
        self.assertIsNotNone(module.newer_release(data, '1.0.82-preview1'))
        self.assertIsNone(module.newer_release(data, '1.0.83'))
        self.assertIsNone(module.newer_release(data, '1.0.84'))
        data['release']['url'] = 'https://other.example/release'
        self.assertIsNone(module.newer_release(data, '1.0.82'))
        self.assertIsNone(module.stable_version('v1.0.83-beta'))

    def notice(self):
        notice = object.__new__(module.UpdateNotice)
        notice.kodi, notice.gui, notice.store = Mock(), Mock(), Mock()
        notice.store.load.return_value = {}
        return notice

    def test_cancel_remembers_version_and_never_installs(self):
        notice = self.notice()
        ui = Mock()
        ui.yesno.return_value = False
        with patch.dict('sys.modules', {'lib.ui_dialogs': types.SimpleNamespace(dialog=lambda: ui)}):
            notice.prompt({'version': 'v1.0.83', 'body': 'Watermark disclosure'})
        notice.store.save.assert_called_once_with({'dismissed_version': 'v1.0.83'})
        notice.kodi.executebuiltin.assert_not_called()
        self.assertEqual(ui.yesno.call_args.kwargs, {'nolabel': 'Cancel', 'yeslabel': 'Update'})
        self.assertIn('Watermark disclosure', ui.yesno.call_args.args[1])

    def test_update_opens_native_kodi_updates_instead_of_overwriting_files(self):
        notice = self.notice()
        ui = Mock()
        ui.yesno.return_value = True
        with patch.dict('sys.modules', {'lib.ui_dialogs': types.SimpleNamespace(dialog=lambda: ui)}):
            notice.prompt({'version': 'v1.0.83', 'body': 'Changes'})
        self.assertEqual([call.args[0] for call in notice.kodi.executebuiltin.call_args_list], ['UpdateAddonRepos', 'ActivateWindow(AddonBrowser,addons://outdated/,return)'])
        notice.store.save.assert_not_called()

    def test_playback_defers_checks_and_dialogs(self):
        notice = self.notice()
        notice.kodi.Player.return_value.isPlayingVideo.return_value = True
        notice.tick()
        notice.gui.Window.assert_not_called()
        notice.store.load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
