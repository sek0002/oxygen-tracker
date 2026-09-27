import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import server

class FastAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = server.DB
        server.DB = Path(self.temp.name) / 'test.sqlite3'
        self.client = TestClient(server.app)
        self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None, None, None)
        server.DB = self.old_db
        self.temp.cleanup()
    def test_login_save_persist_and_security(self):
        c = self.client
        self.assertEqual(c.get('/health').json(), {'ok': True})
        self.assertEqual(c.post('/api/oxygen_login', json={'p_pin': 'bad'}).status_code, 401)
        token = c.post('/api/oxygen_login', json={'p_pin': server.PIN}).json()['token']
        data = {'p_token':token, 'p_expected':None, 'p_request_id':'fastapi-request-001',
                'p_entry':{'side':'left','kind':'initial','pressure':180}}
        response = c.post('/api/oxygen_record', json=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['cylinders']['left']['pressure'],180)
        self.assertEqual(len(c.post('/api/oxygen_state',json={'p_token':token}).json()['events']),1)
        self.assertEqual(c.post('/api/oxygen_record', json={**data,'p_request_id':'fastapi-request-002'}).status_code,409)
        c.post('/api/oxygen_logout',json={'p_token':token})
        self.assertEqual(c.post('/api/oxygen_state',json={'p_token':token}).status_code,401)
        for path in ['/data/oxygen.sqlite3','/server.py','/.env','/DEPLOY.md']:
            self.assertEqual(c.get(path).status_code,404)
            self.assertEqual(c.head(path).status_code,404)
        self.assertEqual(c.get('/manifest.webmanifest').headers['content-type'],'application/manifest+json')
        response=c.get('/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
    def test_malformed_and_oversized_requests(self):
        c=self.client
        self.assertEqual(c.post('/api/oxygen_login',content='x').status_code,415)
        for body in ['{', '[]', '', '\\xff']:
            self.assertEqual(c.post('/api/oxygen_login',content=body,headers={'content-type':'application/json'}).status_code,400)
        self.assertEqual(c.post('/api/oxygen_login',content='x'*16385,headers={'content-type':'application/json'}).status_code,413)

if __name__=='__main__':unittest.main()
