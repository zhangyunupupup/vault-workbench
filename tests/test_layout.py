from collections import Counter
from copy import deepcopy
import json
import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from vault.catalog import Catalog, DEFAULT_ROOT, ValidationError
from vault.recipes import Recipe
from vault import layout as module
from vault.assembly import assembly, mesh_header as assembly_header


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '需要本地模型库')
class RealLayoutContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(DEFAULT_ROOT)
        cls.data = json.loads(module.DATA.read_text(encoding='utf-8'))

    def guide(self, cfg):
        return module.layout(self.catalog, {'config': cfg})

    def assert_counts(self, guide, recipe):
        recipe_counts = Counter()
        for p in recipe['parts']:
            recipe_counts[p['id']] += p['copies']
        self.assertEqual({p['id'] for p in guide['parts']},set(recipe_counts))
        parts = {p['id']: p for p in guide['parts']}
        profile = next(p for p in guide['joints'] if p['motion'] == 'explode')
        keys = []
        for p in profile['composition']:
            part = parts[p['id']]
            self.assertEqual(part['copies'],recipe_counts[p['id']])
            self.assertEqual(sum(e['selection']['faces'] for e in p['elements']),part['faces']*part['copies'])
            self.assertTrue(all(module.valid_pose(e) for e in p['elements']))
            keys.extend(e['key'] for e in p['elements'])
        self.assertEqual(len(keys),len(set(keys)))

    def test_all_135_basic_versions_are_real_and_keep_recipe_counts(self):
        self.assertEqual(len(self.data['models']),135)
        self.assertEqual(self.data['size_height_count'],95)
        for row in self.data['models'].values():
            cfg = row['config']
            with self.subTest(cfg=cfg):
                guide = self.guide(cfg)
                self.assertTrue(guide.get('layout_ready') or guide.get('coverage_complete'))
                self.assertFalse(guide['precision_ready'])
                self.assert_counts(guide,Recipe(self.catalog).build(cfg))

    def test_large_mesh_has_separate_limit_and_revision(self):
        reference = max(self.data['files'].values(),key=lambda p:p['faces'])
        self.assertGreater(reference['faces'],800000)
        path = self.catalog.resolve(reference['id'])
        self.assertEqual(module.mesh_header(path)['faces'],reference['faces'])
        with self.assertRaises(ValidationError):assembly_header(path)

    def test_facade_cap_and_bolt_counts_all_nine_types(self):
        for family in ('S','M','L'):
            for h in (1,2,4):
                holes = 2 if family=='S' and h==1 else 4 if family=='S' or h==1 else 6
                for labels in (True,False):
                    cfg = {'kind':'drawer','family':family,'height':h,'labels':labels}
                    recipe = Recipe(self.catalog).build(cfg)
                    cap = next(p for p in recipe['parts'] if p['name']=='Facade Cap.stl')
                    self.assertEqual(cap['copies'],holes-int(labels))
                    self.assertEqual(next(p for p in recipe['hardware'] if p['reason']=='前面板固定')['quantity'],holes)
                    self.assert_counts(self.guide(cfg),recipe)

    def test_double_locks_and_hinges_have_every_source_component(self):
        for fam,h in [('L',1),('L',4),('XL',1)]:
            g=self.guide({'kind':'sustainer','family':fam,'depth':7,'height':h})
            p=next(p for p in g['parts'] if p['name']=='1 SET OF PINS FOR 1 LOCK.stl')
            nodes=next(s['elements'] for s in g['joints'][0]['composition'] if s['id']==p['id'])
            self.assertEqual(p['copies'],2)
            self.assertEqual(Counter(n['selection']['connected'] for n in nodes),{0:2,1:2,2:2,3:2})
            top=next(p for p in g['parts'] if p['name']=='L-XL Hinge Top.stl')
            nodes=next(s['elements'] for s in g['joints'][0]['composition'] if s['id']==top['id'])
            self.assertEqual(len(nodes),2)

    def test_optional_labels_roof_latches_and_multiple_inner_drawers(self):
        cfg={'kind':'drawer','family':'L','depth':5,'height':4,'drawers':[2,1,1],'labels':False,'roof':'none','latches':4}
        guide=self.guide(cfg)
        self.assertEqual(guide['omitted'],['L Rails.stl'])
        self.assertNotIn('Label.stl',[p['name'] for p in guide['parts']])
        latch=next(p for p in guide['joints'][0]['composition'] if any(e['key']=='latch' for e in p['elements']))
        self.assertEqual(sum(e.get('accuracy')=='spare' for e in latch['elements']),3)
        boxes=[e for p in guide['joints'][0]['composition'] for e in p['elements'] if e['key'].endswith('_box')]
        self.assertEqual(sorted(round(e['origin'][2],5) for e in boxes),[10.20905,106.20905,154.20905])
        cfg.update(drawers=[4],latches=0)
        guide=self.guide(cfg);self.assertFalse(guide['omitted'])
        self.assert_counts(guide,Recipe(self.catalog).build(cfg))

    def test_source_change_fails_closed_and_does_not_enable_animation(self):
        cfg={'kind':'drawer','family':'M','height':2}
        with patch.object(module,'digest',return_value='0'*64),self.assertRaisesRegex(ValidationError,'版本'):
            self.guide(cfg)
        self.assertFalse(assembly(self.catalog,{'config':cfg})['supported'])
        with self.assertRaises(ValidationError):self.guide({**cfg,'family':'XL'})
        with self.assertRaises(ValidationError):self.guide({**cfg,'key':'hidden'})

    def test_catalog_reloads_and_rejects_mirrored_or_nonfinite_pose(self):
        bad=deepcopy(self.data)
        row=bad['models']['drawer:M:3:2:standard']
        row['elements'][0]['matrix'][0]*=-1
        with tempfile.TemporaryDirectory() as folder,patch.object(module,'DATA',Path(folder)/'data.json'):
            module.DATA.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaisesRegex(ValidationError,'变换'):self.guide({'family':'M','height':2})
            module.DATA.write_text(json.dumps(self.data),encoding='utf-8')
            self.assertTrue(self.guide({'family':'M','height':2})['layout_ready'])
        e=deepcopy(row['elements'][0]);e['origin'][0]=float('nan');self.assertFalse(module.valid_pose(e))

    def test_local_http_layout_requires_token_and_mesh_revision(self):
        import server
        with patch.object(server,'CATALOG',self.catalog):
            httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
            try:
                conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=30)
                body=json.dumps({'config':{'kind':'sustainer','family':'L','height':1}})
                conn.request('POST','/api/layout',headers={'Content-Type':'application/json'})
                response=conn.getresponse();response.read();self.assertEqual(response.status,403)
                conn.request('POST','/api/layout',body,{'Content-Type':'application/json','X-Vault-Token':server.TOKEN})
                response=conn.getresponse();guide=json.loads(response.read());self.assertEqual(response.status,200);self.assertTrue(guide['layout_ready'])
                conn.request('GET','/api/layout-mesh/'+guide['parts'][0]['id']+'?revision=wrong')
                response=conn.getresponse();response.read();self.assertEqual(response.status,400)
                conn.close()
            finally:
                httpd.shutdown();httpd.server_close();thread.join()


if __name__=='__main__':unittest.main()
