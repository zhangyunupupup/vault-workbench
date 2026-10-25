import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from vault.catalog import Catalog, DEFAULT_ROOT, ValidationError
from vault.colors import validate_colors, colored
from vault.recipes import plan
from vault.scene import check_layout, validate_scene, dimensions
from vault.exporter import ExportManager


def item(ident='a', pos=None, size=None):
    return {'id': ident, 'position': pos or [0, 0, 0], 'size': size or [100, 100, 50],
            'config': {'kind': 'drawer', 'roof': 'none'}}


class LayoutContracts(unittest.TestCase):
    def test_touching_edges_do_not_collide(self):
        result = check_layout([item(), item('b', [100, 0, 0])])
        self.assertTrue(all(c['level'] == 'ok' for c in result))

    def test_overlap_marks_both_and_removes_green(self):
        result = check_layout([item(), item('b', [99, 0, 0])])
        self.assertEqual({c['id'] for c in result if c['level'] == 'error'}, {'a', 'b'})
        self.assertFalse(any(c['level'] == 'ok' for c in result))

    def test_ground_float_negative_and_partial_support(self):
        for pos in ([0,0,-1], [0,0,51], [10,0,50]):
            with self.subTest(pos=pos):
                self.assertTrue(any(c['level']=='error' for c in check_layout([item(),item('b',pos)])))

    def test_aligned_stack_is_warning_not_certification(self):
        result = check_layout([item(),item('b',[0,0,50])])
        self.assertFalse(any(c['level']=='error' for c in result))
        self.assertTrue(any(c['id']=='b' and c['level']=='warning' for c in result))

    def test_lid_access_and_unknown_interface_are_reported(self):
        bottom=item();bottom['config']['kind']='sustainer'
        result=check_layout([bottom,item('b',[0,0,50],[50,100,50])])
        self.assertTrue(any('翻盖' in c['message'] for c in result))
        self.assertTrue(any('不同尺寸' in c['message'] for c in result))

    def test_color_validation_and_tpu_material_preserved(self):
        with self.assertRaises(ValidationError): validate_colors({'body':'../../bad'})
        with self.assertRaises(ValidationError): validate_colors({'unknown':'#000000'})
        p={'name':'Tyre (TPU).stl','relative':'Tyre (TPU).stl','material':'TPU'}
        self.assertEqual(colored(p,validate_colors({}))['material'],'TPU')


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '本地资料库未连接')
class SceneContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.catalog=Catalog(DEFAULT_ROOT)

    def scene(self):
        return {'version':1,'name':'测试组合','items':[{'id':'a','position':[0,0,0],
                'config':{'kind':'drawer','family':'S','depth':3,'height':1,'quantity':1},'colors':{}}]}

    def test_normalized_scene_roundtrip_and_untrusted_files_ignored(self):
        raw=self.scene();raw['items'][0]['size']=[1,1,1];raw['items'][0]['files']=['../../secret']
        result=validate_scene(self.catalog,raw)
        self.assertEqual(result['scene']['items'][0]['size'],[164.8,156.1,57.01])
        self.assertNotIn('files',result['scene']['items'][0])
        self.assertEqual(validate_scene(self.catalog,result['scene'])['scene'],result['scene'])

    def test_invalid_import_fails_closed(self):
        for field,value in [('position',[float('nan'),0,0]),('position',[0,float('inf'),0]),('position',[10001,0,0]),('position',[True,0,0]),('colors',[]),('id','../a')]:
            raw=self.scene();raw['items'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError):validate_scene(self.catalog,raw)
        raw=self.scene();raw['items']*=2
        with self.assertRaises(ValidationError):validate_scene(self.catalog,raw)
        raw=self.scene();raw['items'][0]['config']['family']='XL'
        with self.assertRaises(ValidationError):validate_scene(self.catalog,raw)
        raw=self.scene();raw['items'][0]['config']['quantity']=2
        with self.assertRaises(ValidationError):validate_scene(self.catalog,raw)
        for raw in [{'version':2,'items':[]},{'version':True,'items':[]},{'version':1,'items':[{}]*61}]:
            with self.assertRaises(ValidationError):validate_scene(self.catalog,raw)
        raw=self.scene();raw['items'][0]['config']={}
        self.assertEqual(validate_scene(self.catalog,raw)['scene']['items'][0]['size'],[164.8,156.1,57.01])

    def test_same_color_merges_different_color_splits_and_counts_hardware(self):
        cfg=self.scene()['items'][0]['config'];a={**cfg,'colors':{'body':'#ffffff'}};b={**cfg,'colors':{'body':'#000000'}}
        one=plan(self.catalog,{'configs':[a]});mixed=plan(self.catalog,{'configs':[a,a,b]})
        shells=[p for p in mixed['parts'] if p['title']=='抽屉外壳']
        self.assertEqual({p['color']:p['copies'] for p in shells},{'#FFFFFF':2,'#000000':1})
        self.assertEqual(sum(h['quantity'] for h in mixed['hardware']),3*sum(h['quantity'] for h in one['hardware']))
        self.assertEqual(sum(p['copies'] for p in mixed['parts']),3*sum(p['copies'] for p in one['parts']))

    def test_collision_blocks_export_plan_even_with_forged_valid_flag(self):
        raw=self.scene();second=copy.deepcopy(raw['items'][0]);second['id']='b';raw['items'].append(second);raw['valid']=True
        with self.assertRaises(ValidationError):plan(self.catalog,{'scene':raw})


class ColorExportContracts(unittest.TestCase):
    def test_zip_color_directories_counts_hashes_and_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';source=root/'01. DRAWERS'/'Springs.stl';source.parent.mkdir(parents=True);source.write_bytes(b'unchanged-stl')
            catalog=Catalog(root);p={**catalog.files[0].public(),'copies':1,'unit':'对 / 文件','reason':'test','source':'test','optional':False}
            def build(_self,cfg):return {'config':cfg,'title':'test','parts':[p],'hardware':[],'notes':[]}
            manager=ExportManager(Path(tmp)/'out')
            with patch('vault.recipes.Recipe.build',build):
                job=manager.start(catalog,{'configs':[{'colors':{'accessory':'#ffffff'}},{'colors':{'accessory':'#000000'}},{'colors':{'accessory':'#ffffff'}}]})
            for _ in range(100):
                state=manager.get(job['id'])
                if state['status'] in ('done','error'):break
                time.sleep(.02)
            self.assertEqual(state['status'],'done',state)
            with zipfile.ZipFile(manager.download_path(job['id'])) as archive:
                manifest=json.loads(archive.read('manifest.json'));parts=manifest['parts']
                self.assertEqual(len(parts),2);self.assertEqual(sorted(p['copies'] for p in parts),[1,2])
                self.assertEqual(len(archive.namelist()),len(set(archive.namelist())))
                for p in parts:
                    self.assertIn(p['color'][1:]+'/',p['archive_path'])
                    self.assertEqual(archive.read(p['archive_path']),source.read_bytes())
                    self.assertEqual(p['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertIn('颜色HEX',archive.read('打印清单.csv').decode('utf-8-sig'))


if __name__=='__main__':unittest.main()
