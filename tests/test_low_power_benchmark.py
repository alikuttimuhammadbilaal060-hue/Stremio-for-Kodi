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

class Pi3CouchValidationTests(unittest.TestCase):
    def test_pi3_couch_pass_is_saved_only_after_benchmark_passes_and_user_confirms(self):
        from lib.low_power_benchmark import confirm_couch_pass
        from lib.perf_report import load_validation
        class Dialog:
            def yesno(self,*args,**kwargs): return True
        with tempfile.TemporaryDirectory() as directory:
            profile=Path(directory)
            self.assertTrue(confirm_couch_pass(profile,{'passed':True},Dialog(),'Raspberry Pi 3'))
            self.assertEqual(load_validation(profile),{'couchPass':True})

    def test_failed_or_non_pi3_benchmark_never_saves_positive_couch_pass(self):
        from lib.low_power_benchmark import confirm_couch_pass
        from lib.perf_report import load_validation
        class Dialog:
            def yesno(self,*args,**kwargs): raise AssertionError('must not prompt')
        with tempfile.TemporaryDirectory() as directory:
            profile=Path(directory)
            self.assertFalse(confirm_couch_pass(profile,{'passed':False},Dialog(),'Raspberry Pi 3'))
            self.assertEqual(load_validation(profile),{'couchPass':False})
            self.assertFalse(confirm_couch_pass(profile,{'passed':True},Dialog(),'Generic Linux'))
            self.assertEqual(load_validation(profile),{'couchPass':False})

    def test_performance_payload_contains_only_boolean_couch_validation(self):
        from lib.perf_report import record,set_couch_pass,build_payload
        with tempfile.TemporaryDirectory() as directory:
            profile=Path(directory)
            record(profile,'benchmark.cached_home',100,rows=1,items=1)
            set_couch_pass(profile,True)
            payload=build_payload(profile,{'addonVersion':'1.0.80','kodiVersion':'21','platform':'Linux','pythonVersion':'3.11','hardwareClass':'Raspberry Pi 3'})
            self.assertEqual(payload['validation'],{'couchPass':True})

