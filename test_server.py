import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import server

class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        server.DB = Path(self.temp.name) / 'test.sqlite3'
        server.initialize()
        self.token = server.api('oxygen_login', {'p_pin': server.PIN}, 'test')[0]['token']
        self.counter = 0
    def tearDown(self):
        self.temp.cleanup()
    def record(self, kind='initial', side='left', pressure=180, expected=None, request_id=None):
        self.counter += 1
        return server.api('oxygen_record', {'p_token': self.token, 'p_expected': expected,
            'p_request_id': request_id or f'test-request-{self.counter:08}',
            'p_entry': {'kind':kind,'side':side,'pressure':pressure,
                        'serial':'G-1','operator':'Test','notes':'Session'}}, 'test')[0]
    def test_history_usage_replacement_persistence(self):
        initial = self.record()['cylinders']['left']
        reading = self.record('reading', pressure=90, expected=initial['id'])['cylinders']['left']
        self.assertEqual(reading['used'], 4500)
        replaced = self.record('replacement', pressure=190, expected=reading['id'])['cylinders']['left']
        self.assertIsNone(replaced['used'])
        self.assertEqual(replaced['startingPressure'],190)
        self.assertEqual(replaced['previousPressure'],90)
        self.record(side='right', pressure=160)
        server.initialize()
        data = server.api('oxygen_state', {'p_token':self.token}, 'test')[0]
        self.assertEqual(len(data['events']),4)
        self.assertEqual(data['cylinders']['left']['pressure'],190)
        self.assertEqual(data['cylinders']['right']['pressure'],160)
    def test_conflicts_and_idempotency(self):
        first = self.record(request_id='idempotent-request-01')
        retry = self.record(request_id='idempotent-request-01')
        self.assertEqual(len(retry['events']),1)
        with self.assertRaises(server.APIError):
            self.record('reading', pressure=100, expected='stale')
        expected = first['cylinders']['left']['id']
        def concurrent(i):
            try:
                return self.record('reading', pressure=100-i, expected=expected,request_id=f'concurrent-request-{i}')
            except server.APIError as e:
                return e.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(concurrent, [1,2]))
        self.assertEqual(sum(isinstance(x,dict) for x in results),1)
        self.assertIn(409,results)
    def test_validation_and_authentication(self):
        first=self.record()['cylinders']['left']
        for pressure in [-1,201,float('nan'),True,'100']:
            with self.assertRaises(server.APIError):
                self.record('reading',pressure=pressure,expected=first['id'])
        with self.assertRaises(server.APIError):
            server.api('oxygen_state',{'p_token':'fake'},'test')
        server.api('oxygen_logout',{'p_token':self.token},'test')
        with self.assertRaises(server.APIError):
            server.api('oxygen_state',{'p_token':self.token},'test')
    def test_pin_rate_limit(self):
        for _ in range(10):
            self.assertEqual(server.api('oxygen_login',{'p_pin':'bad'},'attacker')[1],401)
        self.assertEqual(server.api('oxygen_login',{'p_pin':server.PIN},'attacker')[1],429)

if __name__ == '__main__': unittest.main()
