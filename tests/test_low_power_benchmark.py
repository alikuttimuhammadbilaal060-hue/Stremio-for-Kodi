import tempfile
import unittest
from pathlib import Path

from lib.low_power_benchmark import run, TARGET_MS, SAMPLES
from lib.hardware_class import classify


class LowPowerBenchmarkTests(unittest.TestCase):
    def test_benchmark_records_only_allowlisted_local_timing_stages(self):
        calls=[]
        def record(profile,stage,elapsed,**counts):
            calls.append((Path(profile),stage,elapsed,counts))
        with tempfile.TemporaryDirectory() as directory:
            result=run(
                Path(directory),
                account_home=lambda refresh:[{'label':'Home','items':[{'id':'1'},{'id':'2'}]}],
                snapshot_load=lambda profile:[{'label':'Popular','items':[{'id':'1'}]}],
                continue_rows=lambda profile,limit:[{'id':'series'}],
                account_load=lambda profile:{'library':[{'id':'one'}]},
                stream_cache_probe=lambda profile:3,
                recorder=record)
        self.assertEqual(set(result['metrics']),set(TARGET_MS))
        self.assertEqual(len(calls),5)
        self.assertTrue(all(stage in TARGET_MS for _,stage,_,_ in calls))
        self.assertTrue(all(value>=0 for value in result['metrics'].values()))
        self.assertEqual(result['samples'],SAMPLES)
        self.assertEqual(calls[0][3],{'rows':1,'items':2})
        self.assertEqual(calls[2][3],{'rows':1,'items':1})
        self.assertEqual(calls[3][3],{'rows':1,'items':1})
        self.assertEqual(calls[4][3],{'rows':1,'items':3})

    def test_benchmark_never_requests_network_refresh(self):
        refresh_values=[]
        with tempfile.TemporaryDirectory() as directory:
            run(
                Path(directory),
                account_home=lambda refresh:(refresh_values.append(refresh) or []),
                snapshot_load=lambda profile:[],
                continue_rows=lambda profile,limit:[],
                account_load=lambda profile:{},
                stream_cache_probe=lambda profile:0,
                recorder=lambda *args,**kwargs:None)
        self.assertTrue(refresh_values)
        self.assertEqual(set(refresh_values),{False})

    def test_provisional_budgets_are_explicit_and_positive(self):
        self.assertEqual(set(TARGET_MS),{
            'benchmark.cached_home','benchmark.snapshot_load','benchmark.continue_index',
            'benchmark.account_load','benchmark.stream_cache'})
        self.assertTrue(all(isinstance(value,int) and value>0 for value in TARGET_MS.values()))

    def test_hardware_class_never_returns_raw_model(self):
        from lib.hardware_class import classify
        self.assertEqual(classify('Raspberry Pi 3 Model B Rev 1.2','Linux'),'Raspberry Pi 3')
        self.assertEqual(classify('Raspberry Pi 5 Model B Rev 1.0','Linux'),'Raspberry Pi 4+')
        self.assertEqual(classify('SecretBoard serial-like model name','Linux'),'Generic Linux')
        self.assertNotIn('SecretBoard',classify('SecretBoard serial-like model name','Linux'))


class BenchmarkWiringTests(unittest.TestCase):
    def test_support_exposes_benchmark_before_performance_report(self):
        root=Path(__file__).resolve().parents[1]
        page=(root/'lib/settings_page.py').read_text()
        self.assertIn('Run low-power benchmark',page)
        self.assertIn('run_low_power_benchmark',page)
        self.assertLess(page.index('Run low-power benchmark'),page.index('Send performance report'))
        report=(root/'lib/perf_report.py').read_text()
        for stage in TARGET_MS:
            self.assertIn(repr(stage),report)

if __name__=='__main__':
    unittest.main()


class HardwareClassTests(unittest.TestCase):
    def test_raspberry_pi_models_are_coarsely_classified(self):
        self.assertEqual(classify('Raspberry Pi 3 Model B Plus Rev 1.3','Linux'),'Raspberry Pi 3')
        self.assertEqual(classify('Raspberry Pi 5 Model B Rev 1.0','Linux'),'Raspberry Pi 4+')

    def test_raw_unknown_model_is_never_returned(self):
        raw='Unique Vendor Box Serial-Like Model 12345'
        self.assertEqual(classify(raw,'Linux'),'Generic Linux')
        self.assertNotIn('12345',classify(raw,'Linux'))

    def test_android_is_broad_only(self):
        self.assertEqual(classify('', 'Android'),'Android TV')

