"""Stored-video protocol and Kodi startup context regressions."""
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
from sources import embedded_sources


class StoredVideoTests(unittest.TestCase):
    def test_selected_video_is_exclusive_and_preserves_playback_data(self):
        stream = {'url': 'https://example.org/file.mkv', 'name': 'TorBox',
                  'subtitles': [{'url': 'https://example.org/sub.srt'}],
                  'behaviorHints': {'filename': 'file.mkv'}}
        meta = {'videos': [{'id': 'stored:one', 'streams': [stream]},
                           {'id': 'stored:two', 'streams': []}]}
        rows, skipped, failed = embedded_sources(meta, 'stored:one')
        self.assertEqual(rows[0]['url'], stream['url'])
        self.assertEqual(rows[0]['filename'], 'file.mkv')
        self.assertEqual(rows[0]['subtitles'], stream['subtitles'])
        self.assertEqual((skipped, failed), (0, 0))
        self.assertEqual(embedded_sources(meta, 'stored:two'), ([], 0, 0))
        self.assertIsNone(embedded_sources(meta, 'other'))

    def test_unsupported_embedded_streams_do_not_trigger_other_providers(self):
        self.assertEqual(embedded_sources({'videos': [{'id': 'x', 'streams': [
            {'infoHash': 'abc'}, {'url': 'https://example.org/f',
                                  'behaviorHints': {'proxyHeaders': {'request': {}}}}
        ]}]}, 'x'), ([], 2, 0))

    def test_backend_does_not_collect_when_video_supplies_streams(self):
        tree = ast.parse((ROOT / 'lib/backend.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'source_rows')
        collect = Mock(side_effect=AssertionError('must not scrape'))
        scope = {'embedded_sources': embedded_sources, 'stream_card': lambda r: {}, 'collect': collect}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<backend>', 'exec'), scope)
        meta = {'videos': [{'id': 'x', 'streams': [{'url': 'https://example.org/f'}]}]}
        self.assertEqual(len(scope['source_rows'](meta, 'x')[0]), 1)
        collect.assert_not_called()


class StartupContextTests(unittest.TestCase):
    def load(self, context_id):
        addon = Mock()
        addon.getAddonInfo.side_effect = lambda key: context_id if key == 'id' else '/profile'
        factory = Mock(side_effect=[RuntimeError('unavailable'), addon])
        with patch.dict(sys.modules, {'xbmcaddon': types.SimpleNamespace(Addon=factory),
                                     'xbmcvfs': types.SimpleNamespace(translatePath=lambda v: v)}):
            spec = importlib.util.spec_from_file_location('issue91_state', ROOT / 'core/addon_state.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        module.migrate_profile = Mock()
        return module, addon, factory

    def test_running_script_context_recovers_explicit_lookup_failure(self):
        module, addon, factory = self.load('script.stremioelec')
        self.assertIs(module.get_addon(), addon)
        self.assertEqual(factory.call_args_list[-1].args, ())
        module.migrate_profile.assert_called_once()

    def test_foreign_context_is_rejected_without_migrating(self):
        module, _, _ = self.load('other.addon')
        with self.assertRaises(RuntimeError):
            module.get_addon()
        module.migrate_profile.assert_not_called()
