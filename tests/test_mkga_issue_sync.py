import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class MkgaIssueSyncTests(unittest.TestCase):
    def test_workflow_syncs_issue_events_and_has_write_permission(self):
        text=(ROOT/'.github/workflows/mkga-issue-sync.yml').read_text()
        self.assertIn('issues: write',text)
        self.assertIn('schedule:',text)
        self.assertIn('MKGA_RELEASE_SYNC_TOKEN',text)
        self.assertIn('tools/sync-mkga-github-issues.py',text)

    def test_sync_never_exports_github_token_to_mkga(self):
        text=(ROOT/'tools/sync-mkga-github-issues.py').read_text()
        self.assertIn("headers.update({'Authorization': 'Bearer ' + GITHUB_TOKEN",text)
        self.assertIn("headers['Authorization'] = 'Bearer ' + MKGA_TOKEN",text)
        self.assertNotIn("'GITHUB_TOKEN': GITHUB_TOKEN",text)

    def test_resolution_is_idempotent_and_closes_only_after_mkga_action(self):
        text=(ROOT/'tools/sync-mkga-github-issues.py').read_text()
        self.assertIn('mkga-action:',text)
        self.assertIn("'state': 'closed', 'state_reason': 'completed'",text)
        self.assertIn("mkga('/actions')",text)
        self.assertIn("ack(action_id, True)",text)

if __name__=='__main__':
    unittest.main()
