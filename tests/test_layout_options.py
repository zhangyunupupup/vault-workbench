from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vault.catalog import Catalog, DEFAULT_ROOT
from vault.recipes import Recipe
from vault import layout as module


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(),'需要本地模型库')
class OptionLayoutContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=Catalog(DEFAULT_ROOT)
        cls.options=json.loads(module.OPTION_DATA.read_text(encoding='utf-8'))

    def guide(self,cfg):return module.layout(self.catalog,{'config':cfg})

    def test_all_existing_option_variants_preserve_every_print_copy(self):
        # Enumerate valid single-option variations across the 135 base versions.
        # Runtime remains stdlib-only; no development geometry imports here.
        base=json.loads(module.DATA.read_text(encoding='utf-8'));checked=0
        for row in base['models'].values():
            cfg=row['config'];kind=cfg['kind']
            variants=[{'base':'whole'},{'base':'split'},{'base':'whole','wheels':True}]
            if kind=='drawer':
                variants += [{'roof':r} for r in ['table','bowl','heavy','under_table']]+[{'key':'hidden'},{'top_handle':True},{'rails':True},{'mount':'wall'}]
                variants += [{'interior':'gridfinity','baseplate':v} for v in ['plain','one','two']]+[{'interior':'dividers','divider_height':h} for h in ['20','34.5','82.5']]
            else:variants += [{'split_roof':True},{'interior':'gridfinity'},{'interior':'dividers'}]
            for options in variants:
                new={**cfg,**options}
                try:recipe=Recipe(self.catalog).build(new)
                except module.ValidationError:continue
                with self.subTest(config=new):
                    guide=self.guide(new);self.assertTrue(guide.get('layout_ready') or guide.get('coverage_complete'))
                    original=Counter()
                    for p in recipe['parts']:original[p['id']]+=p['copies']
                    rendered=Counter({p['id']:p['copies'] for p in guide['parts']})
                    for p in guide.get('omitted_details',[])+guide.get('tools',[]):rendered[p['id']]+=p['copies']
                    self.assertEqual(rendered,original)
                    profile=next(p for p in guide['joints'] if p['motion']=='explode')
                    for part in guide['parts']:
                        nodes=next(p['elements'] for p in profile['composition'] if p['id']==part['id'])
                        self.assertEqual(sum(n['selection']['faces'] for n in nodes),part['faces']*part['copies'])
                        self.assertTrue(all(module.valid_pose(n) for n in nodes))
                checked+=1
        self.assertEqual(checked,1020)

    def test_replacement_roofs_are_real_and_never_substituted(self):
        for roof,name in [('table','Table Roof'),('bowl','Bowl Roof'),('under_table','Under Table Mount Roof'),('heavy','Heawyweight Roof')]:
            guide=self.guide({'family':'L','depth':4,'height':2,'roof':roof})
            names=[p['name'] for p in guide['parts']]
            self.assertIn('L4 '+name+'.stl',names);self.assertFalse(any('Grid Roof' in p for p in names))
            self.assertFalse(guide['omitted'])
            if roof=='heavy':self.assertEqual(next(p for p in guide['parts'] if p['name']=='Heawyweight Roof Insert.stl')['copies'],2)

    def test_gridfinity_plates_and_each_inner_floor(self):
        cfg={'family':'S','height':4,'drawers':[2,1,1],'interior':'gridfinity','baseplate':'two'}
        guide=self.guide(cfg);plate=next(p for p in guide['parts'] if 'Baseplate' in p['name'])
        nodes=next(p['elements'] for p in guide['joints'][0]['composition'] if p['id']==plate['id'])
        self.assertEqual(plate['copies'],3)
        self.assertEqual(sorted(round(p['origin'][2],5) for p in nodes),[13.20905,109.20905,157.20905])

    def test_base_and_split_roof_datums(self):
        cfg={'family':'M','depth':6,'height':2,'base':'split'};guide=self.guide(cfg)
        self.assertEqual(guide['anchor_floor'],'assembly');self.assertEqual(guide['omitted'],['Base Connector.stl'])
        poses=self.options['poses'][module.model_key(cfg)]
        base=[]
        for p in guide['parts']:
            reference=self.options['files'].get(p['id'])
            if not reference or reference['role']!='base':continue
            pose=poses[p['id']][0];self.assertAlmostEqual(pose['origin'][2]+reference['deck_z'],0,places=5)
            base.append((p['name'],pose['origin'][1]+reference['min'][1],pose['origin'][1]+reference['max'][1]))
        base.sort();self.assertAlmostEqual(base[0][2],base[1][1],places=4)
        cfg={'kind':'sustainer','family':'L','depth':7,'height':4,'split_roof':True}
        guide=self.guide(cfg);names=[p['name'] for p in guide['parts']]
        self.assertIn('L7 Roof Part 1.stl',names);self.assertIn('L7 Roof Part 2.stl',names);self.assertNotIn('L7 Roof Whole.stl',names)
        self.assertEqual(guide['omitted'],['Connector For Split Roof.stl'])

    def test_unknown_accessory_and_tools_leave_real_body_available(self):
        guide=self.guide({'base':'whole','wheels':True,'mount':'wall','key':'hidden'})
        self.assertTrue(guide['layout_ready']);self.assertIn('S3 Module 1F.stl',[p['name'] for p in guide['parts']])
        self.assertIn('Tyre (TPU).stl',guide['omitted']);self.assertIn('Hidden Key Part 2 (Turn on Supports).stl',guide['omitted'])
        self.assertEqual({p['name'] for p in guide['tools']},{'Jig.stl','S1F Wall Mount.stl'})

    def test_changed_option_source_omits_only_that_option(self):
        original=module.digest
        def changed(path,size,mtime):return '0'*64 if 'Bowl Roof' in path else original(path,size,mtime)
        with patch.object(module,'digest',side_effect=changed):guide=self.guide({'roof':'bowl'})
        self.assertTrue(guide['layout_ready']);self.assertEqual(guide['omitted'],['S3 Bowl Roof.stl'])
        self.assertIn('版本不符',guide['omitted_details'][0]['reason'])
        self.assertIn('S3 Module 1F.stl',[p['name'] for p in guide['parts']])

    def test_missing_options_catalog_does_not_disable_real_shell(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(module,'OPTION_DATA',Path(tmp)/'missing.json'):
            guide=self.guide({'roof':'table'})
        self.assertTrue(guide['layout_ready']);self.assertIn('S3 Table Roof.stl',guide['omitted'])

    def test_changed_original_accessory_preserves_real_shell(self):
        original=module.digest
        def changed(path,size,mtime):return '0'*64 if path.endswith('Facade Cap.stl') else original(path,size,mtime)
        with patch.object(module,'digest',side_effect=changed):guide=self.guide({'family':'M'})
        self.assertTrue(guide['layout_ready']);self.assertEqual(guide['omitted'],['Facade Cap.stl'])
        self.assertIn('M3 Module 1F.stl',[p['name'] for p in guide['parts']])


if __name__=='__main__':unittest.main()
