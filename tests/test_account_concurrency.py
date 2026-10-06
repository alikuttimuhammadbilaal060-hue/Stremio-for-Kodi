import sys
import multiprocessing
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core'))
from account import Store, AccountConflict


def concurrent_writer(root, name, barrier, errors):
    try:
        store = Store(root)
        state = store.load()
        state[name] = name
        barrier.wait(timeout=10)
        store.save(state)
    except Exception as error:
        errors.put(type(error).__name__)
        raise


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.store.save({'token': 'fixture', 'library': [], 'theme': 'purple'})

    def test_unrelated_stale_writes_merge_without_losing_either_change(self):
        ui, worker = self.store.load(), self.store.load()
        ui['theme'] = 'blue'
        self.store.save(ui)
        worker['library'] = [{'id': 'movie'}]
        self.store.save(worker)
        self.assertEqual(self.store.load()['theme'], 'blue')
        self.assertEqual(self.store.load()['library'], [{'id': 'movie'}])
        worker['theme'] = 'green'
        self.store.save(worker)
        self.assertEqual(self.store.load()['theme'], 'green')

    def test_same_field_conflict_preserves_latest_saved_membership(self):
        left, right = self.store.load(), self.store.load()
        left['library'] = ['left']
        self.store.save(left)
        right['library'] = ['right']
        with self.assertRaises(AccountConflict):
            self.store.save(right)
        self.assertEqual(self.store.load()['library'], ['left'])

    def test_old_account_library_cannot_be_written_to_new_account(self):
        old = self.store.load()
        self.store.save({'token': 'new', 'library': ['new']})
        old['library'] = ['old']
        with self.assertRaises(AccountConflict):
            self.store.save(old)
        self.assertEqual(self.store.load()['token'], 'new')
        self.assertEqual(self.store.load()['library'], ['new'])

    def test_library_compare_and_set_preserves_new_settings_and_rejects_new_membership(self):
        old = self.store.load()
        settings = self.store.load()
        settings['theme'] = 'blue'
        self.store.save(settings)
        self.assertTrue(self.store.update_library(old['token'], old['library'], ['remote']))
        self.assertEqual(self.store.load()['theme'], 'blue')
        self.assertFalse(self.store.update_library(old['token'], old['library'], ['stale']))
        self.assertEqual(self.store.load()['library'], ['remote'])

    def test_two_processes_merge_simultaneous_unrelated_writes(self):
        context = multiprocessing.get_context('spawn')
        barrier, errors = context.Barrier(2), context.Queue()
        children = [context.Process(target=concurrent_writer, args=(self.tmp.name, name, barrier, errors))
                    for name in ('left', 'right')]
        try:
            for child in children:
                child.start()
            for child in children:
                child.join(timeout=15)
                self.assertEqual(child.exitcode, 0)
            current = self.store.load()
            self.assertEqual((current['left'], current['right']), ('left', 'right'))
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
            errors.close()
            errors.join_thread()

    def test_disconnect_is_serialized_and_cannot_be_undone_by_stale_progress(self):
        old = self.store.load()
        self.store.forget()
        old['library'] = ['stale']
        with self.assertRaises(AccountConflict):
            self.store.save(old)
        self.assertEqual(self.store.load(), {})

    def test_unlinked_or_blank_token_cannot_create_library_state(self):
        self.store.forget()
        before = self.store.path.read_bytes()
        for token in (None, False, '', ' '):
            with self.subTest(token=token):
                self.assertFalse(self.store.update_library(token, [], ['unlinked']))
                self.assertEqual(self.store.path.read_bytes(), before)

    def test_old_identity_or_premium_refresh_cannot_enter_new_account(self):
        fields = ('addons', 'verified_identity', 'vortexo_premium_session',
                  'vortexo_premium', 'mkga_stremio_hub', 'mkga_stremio_hub_checked_at')
        for field in fields:
            with self.subTest(field=field):
                self.store.save({'token': 'old', 'library': []})
                pending = self.store.load()
                self.store.save({'token': 'new', 'library': ['new-account']})
                before = self.store.path.read_bytes()
                pending[field] = {'old_account': True}
                with self.assertRaises(AccountConflict):
                    self.store.save(pending)
                self.assertEqual(self.store.path.read_bytes(), before)
