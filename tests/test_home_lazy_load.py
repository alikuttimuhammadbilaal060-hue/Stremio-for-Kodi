import unittest
from pathlib import Path
from lib.home_catalogs import load_more
class HomeLazyLoadTests(unittest.TestCase):
 def test_uses_skip_and_caps_page(self):
  seen=[]
  def url(manifest,res,kind,identity,extras=None):seen.append(extras);return 'x'
  def fetch(_):return {'metas':[{'id':str(i)} for i in range(30)]}
  spec={'url':'https://x/manifest.json','kind':'movie','catalog_id':'top'}
  rows,advanced=load_more(spec,fetch,url,16)
  self.assertEqual(seen,[{'skip':'16'}]);self.assertEqual(len(rows),16);self.assertEqual(advanced,16)

class HomeLazyRuntimeSpecTests(unittest.TestCase):
 def test_refresh_keeps_catalog_spec_for_runtime_pagination(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/backend.py').read_text()
  self.assertIn('save_snapshot(STORE.directory, catalog_rows)',source)
  self.assertNotIn('catalog_rows = save_snapshot(STORE.directory, catalog_rows)',source)

class HomePaginationCursorTests(unittest.TestCase):
 def test_runtime_uses_provider_cursor_not_unique_row_count(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/nimbus.py').read_text()
  self.assertIn('skip=self.home_row_cursor.get(cid,len(rows))',source)
  self.assertIn('self.home_row_cursor[cid]=skip+advanced',source)
  self.assertIn('if advanced<16:self.home_row_exhausted.add(cid)',source)
  self.assertNotIn('if not fresh:self.home_row_exhausted.add(cid)',source)
 def test_home_repopulate_resets_pagination_state(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/nimbus.py').read_text()
  self.assertIn('self.home_row_exhausted.clear()',source)
  self.assertIn('self.home_row_cursor.clear()',source)

class IncrementalHomeRefreshTests(unittest.TestCase):
 def test_incremental_refresh_skips_unchanged_rows_and_has_full_fallback(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/nimbus.py').read_text()
  self.assertIn('def patch_home_rows(self, fresh):',source)
  self.assertIn('if old == new: continue',source)
  self.assertIn('if patched is False:',source)
  self.assertIn("self.populate_rows('Home',fresh)",source)

class HomePaginationDeviceIndependenceTests(unittest.TestCase):
 def test_home_watcher_checks_pagination_without_relying_on_dpad_onaction(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/nimbus.py').read_text()
  watch=source.split('    def _start_progress_watch(self):',1)[1].split('    def refresh_home_async',1)[0]
  self.assertIn("self.getProperty('page') == 'Home'",watch)
  self.assertIn('self.maybe_load_more_home()',watch)
  self.assertIn('xbmc.sleep(250)',watch)

 def test_lazy_load_still_waits_until_selection_is_near_row_end(self):
  source=Path(__file__).resolve().parents[1].joinpath('lib/nimbus.py').read_text()
  block=source.split('    def maybe_load_more_home(self):',1)[1].split('    def update_hero',1)[0]
  self.assertIn("len(rows)-self.getControl(cid).getSelectedPosition()>4",block)
  self.assertIn('self.home_row_loading.add(cid)',block)
  self.assertIn('threading.Thread(target=work,daemon=True).start()',block)
