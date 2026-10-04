import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class LowPowerSettingsWiringTests(unittest.TestCase):
    def test_custom_and_legacy_settings_expose_benchmark(self):
        page=(ROOT/'lib/settings_page.py').read_text()
        xml=(ROOT/'resources/settings.xml').read_text()
        default=(ROOT/'default.py').read_text()
        self.assertIn('Run low-power benchmark',page)
        self.assertIn('run_low_power_benchmark',page)
        self.assertIn('run_low_power_benchmark',xml)
        self.assertIn("'run_low_power_benchmark' in sys.argv[1:]",default)

    def test_benchmark_copy_does_not_claim_pi3_certification(self):
        page=(ROOT/'lib/settings_page.py').read_text()
        default=(ROOT/'default.py').read_text()
        self.assertIn('not a Pi 3 certification by itself',page)
        self.assertIn('real Pi 3 run is required for certification',default)

if __name__=='__main__':unittest.main()
