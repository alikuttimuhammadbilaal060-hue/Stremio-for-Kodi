import copy
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

from core.playback_progress import apply_progress
from lib.playback_refresh import refresh_continue_index
from lib import continue_index
from lib.progress_signal import publish, snapshot

VIDEOS=[
 {'id':'ttcw:1:1','season':1,'episode':1,'released':'2026-01-01T00:00:00Z'},
 {'id':'ttcw:1:2','season':1,'episode':2,'released':'2026-01-08T00:00:00Z'},
 {'id':'ttcw:1:3','season':1,'episode':3,'released':'2026-01-15T00:00:00Z'},
]
CTX={'meta_id':'ttcw','video_id':'ttcw:1:1','kind':'series','name':'Show','poster':'poster.jpg','posterShape':'poster','behaviorHints':{},'videos':VIDEOS}
NOW=datetime(2026,9,29,10,0,0,tzinfo=timezone.utc)

class Store:
 def __init__(self,directory,library):self.directory=Path(directory);self.state={'library':copy.deepcopy(library)}
 def load(self):return copy.deepcopy(self.state)

class LocalContinueRefreshTests(unittest.TestCase):
 def test_completed_episode_resolves_next_aired_episode_immediately(self):
  remote=apply_progress([],CTX,95_000,100_000,80_000,now=NOW)
  self.assertEqual(remote['state']['video_id'],'ttcw:1:2');self.assertEqual(remote['state']['timeOffset'],1)
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(tmp,[remote]);refresh_continue_index(store,CTX,remote)
   rows=continue_index.rows(Path(tmp),10)
   self.assertEqual(len(rows),1)
   self.assertEqual(rows[0]['id'],'ttcw')
   self.assertEqual(rows[0]['state']['video_id'],'ttcw:1:2')
   self.assertEqual(rows[0]['state']['timeOffset'],1)

 def test_partial_episode_is_visible_without_waiting_for_maintenance(self):
  remote=apply_progress([],CTX,30_000,100_000,30_000,now=NOW)
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(tmp,[remote]);refresh_continue_index(store,CTX,remote)
   rows=continue_index.rows(Path(tmp),10)
   self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state']['video_id'],'ttcw:1:1');self.assertEqual(rows[0]['state']['timeOffset'],30_000)

class SignalTests(unittest.TestCase):
 def test_signal_contains_only_revision_and_media_ids(self):
  props={}
  class Window:
   def setProperty(self,k,v):props[k]=v
   def getProperty(self,k):return props.get(k,'')
  gui=types.SimpleNamespace(Window=lambda _:Window())
  revision=publish(CTX,gui)
  self.assertTrue(revision)
  snap=snapshot(gui)
  self.assertEqual(snap[0],revision);self.assertEqual(snap[1:],(CTX['meta_id'],CTX['video_id']))
  self.assertNotIn('poster.jpg',str(props))

class WiringTests(unittest.TestCase):
 def test_observer_refreshes_local_cw_then_publishes_signal(self):
  text=(ROOT/'lib/playback_observer.py').read_text()
  block=text.split('def flush_pending',1)[1]
  self.assertIn('refresh_continue_index(store, pending[\'context\'], remote)',block)
  self.assertIn('if remote is not None:',block)
  self.assertIn("publish(pending['context'])",block)
  self.assertLess(block.index('refresh_continue_index'),block.index("publish(pending['context'])"))

 def test_home_and_info_watch_confirmed_progress(self):
  text=(ROOT/'lib/nimbus.py').read_text()
  self.assertIn('def refresh_home_local(self):',text)
  self.assertIn("fresh = api.account_home(False)",text)
  self.assertGreaterEqual(text.count('def _start_progress_watch(self):'),2)
  self.assertIn("current_meta = str(self.meta.get('id') or '')",text)
  self.assertIn('meta_id != current_meta',text)
  self.assertIn('self._refresh_episode_cards(pos, focus_episode=keep_focus)',text)
  # A post-playback refresh updates the next play target without jumping the
  # currently visible season away from the episode the viewer just finished.
  refresh=text.split('    def refresh_resume_state(self):',1)[1].split('    def onFocus',1)[0]
  self.assertIn("self.play_target = next_video['id']",refresh)
  self.assertNotIn('self.season =',refresh)

if __name__=='__main__':unittest.main()
