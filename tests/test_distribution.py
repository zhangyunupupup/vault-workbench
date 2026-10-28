import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.build_release import BASE, VERSION, source_files, demo_files, verified_python
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.scene import validate_scene


class DistributionContracts(unittest.TestCase):
    def test_source_and_demo_scope(self):
        files=source_files()
        self.assertTrue(any(p.name=='server.py' for p in files))
        self.assertTrue(any(p.name=='layout_options.json' for p in files))
        self.assertFalse(any(p.suffix.lower() in ('.stl','.pdf','.3mf','.pyc') or {'runtime','exports','tmp','python'}&set(p.relative_to(BASE).parts) for p in files))
        demo=demo_files()
        self.assertTrue(any(p.name=='sw.js' for p in demo))
        self.assertFalse(any(p.name in ('server.py','recipes.py','drawer.jpg','builder-detail.js','layout-mesh-worker.js','layout_data.json') for p in demo))

    def test_modified_runtime_rejected(self):
        with tempfile.TemporaryDirectory(dir=BASE/'tmp') as folder:
            path=Path(folder)/'wrong.zip';path.write_bytes(b'not the official runtime')
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                verified_python(path)

    @unittest.skipUnless((BASE/'tmp/demo-scene-fixture.json').is_file() and Path(DEFAULT_ROOT).is_dir(),'Run Node demo --fixture with a connected model library first')
    def test_phone_scene_revalidated_by_desktop(self):
        raw=json.loads((BASE/'tmp/demo-scene-fixture.json').read_text(encoding='utf-8'))
        result=validate_scene(Catalog(DEFAULT_ROOT),raw)
        self.assertTrue(result['valid'])
        self.assertEqual([i['size'] for i in result['scene']['items']],[[164.8,156.1,57.01],[164.8,156.1,99.5]])
        self.assertEqual(result['scene']['items'][1]['colors'],raw['items'][1]['colors'])

    @unittest.skipUnless(os.name=='nt' and (BASE/f'dist/VAULT-Workbench-{VERSION}-windows-x64.zip').is_file(),'Build Windows portable ZIP first')
    def test_portable_isolated_runtime_and_http(self):
        with tempfile.TemporaryDirectory(prefix='portable smoke 中文 ',dir=BASE/'tmp') as folder:
            with zipfile.ZipFile(BASE/f'dist/VAULT-Workbench-{VERSION}-windows-x64.zip') as archive:
                names=archive.namelist()
                self.assertFalse(any('/runtime/' in n or '/exports/' in n or n.lower().endswith(('.stl','.pdf','.3mf','.pyc')) for n in names))
                self.assertTrue(any(n.endswith('/python/LICENSE.txt') for n in names))
                archive.extractall(folder)
            app=Path(folder)/f'VAULT-Workbench-{VERSION}'
            script=app/'smoke.py'
            script.write_text('''import json, sys, threading, http.client
import server
assert sys.flags.isolated == 1
assert sys.version_info[:3] == (3,14,10)
assert all('poison' not in p for p in sys.path)
httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
try:
    conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
    for path,expected in [('/api/health',b'vault-workbench'),('/assets/demo/index.html','随手搭'.encode())]:
        conn.request('GET',path);response=conn.getresponse();body=response.read()
        assert response.status==200,(path,response.status)
        assert expected in body
    conn.close()
finally:
    httpd.shutdown();httpd.server_close();thread.join()
print('PORTABLE_OK')
''',encoding='utf-8')
            env={**os.environ,'PYTHONHOME':'Z:/poison','PYTHONPATH':'Z:/poison','PATH':str(app/'python')}
            run=subprocess.run([str(app/'python/python.exe'),'-X','utf8',str(script)],cwd=app,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            self.assertEqual(run.returncode,0,run.stderr+run.stdout)
            self.assertIn('PORTABLE_OK',run.stdout)


if __name__=='__main__':
    unittest.main()
