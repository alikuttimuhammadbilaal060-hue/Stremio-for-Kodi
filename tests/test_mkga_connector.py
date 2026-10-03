import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class MKGAConnectorTests(unittest.TestCase):
    def test_background_service_uses_explicit_addon_identity(self):
        service=(ROOT/'service.mkga.connector'/'service.py').read_text()
        self.assertIn('xbmcaddon.Addon(CONNECTOR_ID)', service)

