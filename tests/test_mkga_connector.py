import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class MKGAConnectorTests(unittest.TestCase):
    def test_background_service_uses_explicit_addon_identity(self):
        service=(ROOT/'service.mkga.connector'/'service.py').read_text()
        self.assertIn('xbmcaddon.Addon(CONNECTOR_ID)', service)
    def test_url_build_install_is_safety_backed_and_http_only(self):
        service=(ROOT/'service.mkga.connector'/'service.py').read_text()
        self.assertIn("parsed.scheme.lower() not in ('http','https')", service)
        self.assertIn("safety_name='Before URL build", service)
        self.assertIn('create_backup(safety_name)', service)
        self.assertIn('safe_install_url_build', service)
        self.assertIn("action=='install_build_url'", service)

    def test_url_build_preserves_connector_identity(self):
        service=(ROOT/'service.mkga.connector'/'service.py').read_text()
        self.assertIn("addons/service.mkga.connector", service)
        self.assertIn("userdata/addon_data/service.mkga.connector", service)
        self.assertIn('MAX_BUILD_DOWNLOAD=4*1024*1024*1024', service)
        self.assertIn('MAX_BUILD_UNCOMPRESSED=20*1024*1024*1024', service)

