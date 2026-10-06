"""Build Welcome and account changes without Kodi, credentials or network."""
import ast
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
from account import AccountError, AccountStorageError, Store
from addons_core import merge_account


def signin_function(name):
    tree = ast.parse((ROOT / 'lib/signin.py').read_text())
    if name == 'link_account':
        nodes = next(node.body for node in tree.body if isinstance(node, ast.ClassDef))
    else:
        nodes = tree.body
    return next(node for node in nodes if isinstance(node, ast.FunctionDef) and node.name == name)


class BuildSigninTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = Store(temporary.name)
        self.state = {
            'token': 'old-fixture-token',
            'verified_identity': {'user_id': 'old-user', 'token_sha256': hashlib.sha256(b'old-fixture-token').hexdigest()},
            'library': [{'_id': 'old-movie'}],
            'addons': [{'id': 'old-addon', 'account': True}, {'id': 'local-addon'}],
            'theme': 'purple',
            'vortexo_premium_session': {'access_token': 'old-fixture-session'},
            'mkga_stremio_hub': {'linked': True},
        }
        self.store.save(self.state)

    def link(self, identity, cancelled=False):
        window = Mock()
        window.cancel = threading.Event()
        window.refresh = threading.Event()
        window.authenticated = False
        captured = []
        save = self.store.save
        def capture(value):
            captured.append(deepcopy(value))
            save(value)
        def verify(token):
            self.assertEqual(token, 'new-fixture-token')
            self.assertEqual(self.store.load()['token'], 'old-fixture-token')
            if cancelled:
                window.cancel.set()
            if isinstance(identity, Exception):
                raise identity
            return identity
        scope = {
            'create_link_details': lambda: ('fixture', 'https://link.stremio.com/fixture', ''),
            'read_link': lambda code: 'new-fixture-token', 'account_store': lambda: self.store,
            'pull_addons': Mock(side_effect=AccountError('fixture sync unavailable')),
            'pull_library': Mock(), 'merge_account': merge_account,
            'time': __import__('time'), 'threading': threading, 'xbmc': Mock(),
            'AccountError': AccountError, 'AccountStorageError': AccountStorageError,
        }
        scope['xbmc'].Monitor.return_value.abortRequested.return_value = False
        exec(compile(ast.Module(body=[signin_function('link_account')], type_ignores=[]), '<build-signin>', 'exec'), scope)
        with patch.object(self.store, 'save', side_effect=capture), patch.dict('sys.modules', {
            'account': types.SimpleNamespace(pull_user_id=verify),
            'lib.vortexo_premium': types.SimpleNamespace(refresh_quiet=Mock()),
        }):
            scope['link_account'](window)
        self.assertIsNone(window.last_error)
        return window, captured, scope

    def test_new_account_cannot_show_old_library_when_initial_sync_fails(self):
        window, captured, scope = self.link('new-user')
        current = self.store.load()
        self.assertTrue(window.authenticated)
        self.assertEqual(current['token'], 'new-fixture-token')
        self.assertEqual(current['library'], [])
        self.assertEqual(current['addons'], [{'id': 'local-addon'}])
        self.assertEqual(current['theme'], 'purple')
        self.assertNotIn('vortexo_premium_session', current)
        self.assertNotIn('mkga_stremio_hub', current)
        self.assertEqual(captured[0]['verified_identity'], {
            'user_id': 'new-user', 'token_sha256': hashlib.sha256(b'new-fixture-token').hexdigest()})
        scope['pull_library'].assert_not_called()

    def test_verified_token_rotation_preserves_same_account_library(self):
        window, _, _ = self.link('old-user')
        current = self.store.load()
        self.assertTrue(window.authenticated)
        self.assertEqual(current['library'], self.state['library'])
        self.assertEqual(current['addons'], self.state['addons'])
        self.assertNotIn('vortexo_premium_session', current)

    def test_unverified_identity_does_not_preserve_previous_account_cache(self):
        window, _, _ = self.link(AccountError('fixture identity unavailable'))
        current = self.store.load()
        self.assertTrue(window.authenticated)
        self.assertEqual(current['library'], [])
        self.assertNotIn('verified_identity', current)

    def test_identity_bound_to_another_token_cannot_preserve_old_library(self):
        self.state['verified_identity']['token_sha256'] = hashlib.sha256(b'another-fixture-token').hexdigest()
        self.store.save(self.state)
        _, _, _ = self.link('old-user')
        self.assertEqual(self.store.load()['library'], [])

    def test_cancel_during_identity_lookup_writes_no_account_state(self):
        before = self.store.path.read_bytes()
        window, captured, scope = self.link('new-user', cancelled=True)
        self.assertFalse(window.authenticated)
        self.assertEqual(captured, [])
        self.assertEqual(self.store.path.read_bytes(), before)
        scope['pull_addons'].assert_not_called()

    def test_default_and_build_welcome_use_their_own_xml(self):
        scope = {'WelcomeWindow': object(), 'get_addon': Mock(), 'themed_window': Mock()}
        scope['get_addon'].return_value.getAddonInfo.return_value = '/engine'
        window = scope['themed_window'].return_value
        window.authenticated, window.last_error = True, None
        guard = types.SimpleNamespace(mark_window=Mock(), unmark_window=Mock())
        exec(compile(ast.Module(body=[signin_function('show_signin')], type_ignores=[]), '<build-welcome>', 'exec'), scope)
        with patch.dict('sys.modules', {'lib.launch_guard': guard}):
            self.assertTrue(scope['show_signin']())
            scope['themed_window'].assert_called_with(scope['WelcomeWindow'], 'script-stremio-welcome.xml', '/engine', 'Main', '1080i')
            self.assertTrue(scope['show_signin']('mkga-welcome.xml', '/build-service'))
            scope['themed_window'].assert_called_with(scope['WelcomeWindow'], 'mkga-welcome.xml', '/build-service', 'Main', '1080i')
        self.assertEqual(guard.unmark_window.call_count, 2)
        self.assertEqual(window.cancel.set.call_count, 2)


if __name__ == '__main__':
    unittest.main()
