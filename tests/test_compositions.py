from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from vault.assembly import assembly
from vault.catalog import Catalog, DEFAULT_ROOT
from vault import compositions, joints


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '需要本地VAULT资料库')
class CompositionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=Catalog(DEFAULT_ROOT)

    def test_both_kits_cover_every_file_and_preserve_print_counts(self):
        for kind,count in [('drawer',17),('sustainer',16)]:
            with self.subTest(kind=kind):
                guide=assembly(self.catalog,{'config':{'kind':kind,'height':1 if kind=='drawer' else 2}})
                self.assertTrue(guide['coverage_complete'])
                self.assertFalse(guide['precision_ready'])
                profile=guide['joints'][0]
                self.assertEqual(profile['motion'],'sequence')
                self.assertEqual(profile['display_count'],count)
                parts={p['id']:p for p in guide['parts']}
                self.assertEqual({p['id'] for p in profile['composition']},set(parts))
                keys=[]
                for p in profile['composition']:
                    self.assertEqual(sum(e['selection']['faces'] for e in p['elements']),parts[p['id']]['faces']*parts[p['id']]['copies'])
                    keys.extend(e['key'] for e in p['elements'])
                    self.assertTrue(all(compositions.valid_element(e) for e in p['elements']))
                self.assertEqual(len(keys),len(set(keys)))
                self.assertLessEqual(max(e['step'] for p in profile['composition'] for e in p['elements']),len(guide['steps'])-1)

    def test_optional_files_and_spares_do_not_become_duplicate_installed_parts(self):
        for cfg,count in [({'labels':False,'roof':'none','latches':0},15),({'latches':4},20)]:
            guide=assembly(self.catalog,{'config':cfg});profile=guide['joints'][0]
            self.assertEqual(profile['display_count'],count)
            if cfg.get('latches')==4:
                latch=next(p for p in profile['composition'] if any(e['key']=='latch0' for e in p['elements']))
                self.assertEqual(len(latch['elements']),4)
                self.assertEqual(sum(e.get('accuracy')=='spare' for e in latch['elements']),3)
        case=assembly(self.catalog,{'config':{'kind':'sustainer','height':2,'labels':False}})
        self.assertEqual(case['joints'][0]['display_count'],15)

    def test_changed_accessory_disables_only_complete_views(self):
        original=joints.digest
        def changed(path,size,mtime):
            return '0'*64 if Path(path).name=='Facade Cap.stl' else original(path,size,mtime)
        with patch('vault.joints.digest',side_effect=changed):
            guide=assembly(self.catalog,{'config':{}})
        self.assertFalse(guide['coverage_complete'])
        self.assertFalse(any(p.get('mode')=='composition' for p in guide['joints']))
        self.assertTrue(any(p['id']=='s3-1f-facade-motion-v1' for p in guide['joints']))

    def test_catalog_reload_invalid_data_and_mutation_isolation(self):
        guide=assembly(self.catalog,{'config':{}});parts=guide['parts']
        source=(compositions.DATA/'drawer.json').read_text(encoding='utf-8')
        with TemporaryDirectory() as tmp,patch.object(compositions,'DATA',Path(tmp)):
            path=Path(tmp)/'drawer.json';path.write_text(source,encoding='utf-8')
            profiles=compositions.composition_profiles(self.catalog,parts,'drawer')
            profiles[0]['composition'][0]['elements'][0]['origin'][0]=9000
            fresh=compositions.composition_profiles(self.catalog,parts,'drawer')
            self.assertNotEqual(fresh[0]['composition'][0]['elements'][0]['origin'][0],9000)
            path.write_text('{broken',encoding='utf-8')
            self.assertEqual(compositions.composition_profiles(self.catalog,parts,'drawer'),[])
            bad=json.loads(source);next(iter(bad['files'].values()))['elements'][0]['matrix'][0]=float('nan')
            path.write_text(json.dumps(bad),encoding='utf-8')
            self.assertEqual(compositions.composition_profiles(self.catalog,parts,'drawer'),[])
            path.write_text(source,encoding='utf-8')
            self.assertEqual(len(compositions.composition_profiles(self.catalog,parts,'drawer')),3)

    def test_case_axes_and_four_front_bolts_are_explicit(self):
        guide=assembly(self.catalog,{'config':{'kind':'sustainer','height':2}})
        profile=next(p for p in guide['joints'] if p['motion']=='hinge')
        lid=profile['rotations'][1]
        self.assertEqual(lid['axis'],[1,0,0])
        self.assertEqual(lid['pivot'],[0,-7.5,84.8])
        self.assertEqual(lid['start'],.2)
        self.assertEqual(profile['angle_deg'],110)
        hardware=next(h for h in guide['hardware'] if h['reason']=='前面板固定')
        self.assertEqual(hardware['quantity'],4)
        self.assertIn('四孔',hardware['source'])

    def test_label_and_covered_hole_cap_are_mutually_exclusive(self):
        for labels,caps in [(True,1),(False,2)]:
            guide=assembly(self.catalog,{'config':{'labels':labels}})
            part=next(p for p in guide['parts'] if p['name']=='Facade Cap.stl')
            self.assertEqual(part['copies'],caps)
            elements=next(p['elements'] for p in guide['joints'][0]['composition'] if p['id']==part['id'])
            self.assertEqual(len(elements),caps)
            if labels:self.assertEqual(elements[0]['key'],'facade_cap0')
            hardware=next(h for h in guide['hardware'] if h['reason']=='前面板固定')
            self.assertEqual(hardware['quantity'],2)
            self.assertRegex(hardware['source'],r'两孔|2孔')
