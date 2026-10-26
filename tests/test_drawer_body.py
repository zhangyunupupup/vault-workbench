from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from vault.catalog import Catalog, DEFAULT_ROOT
from vault.assembly import assembly
from vault.drawer_body import BOX, SLIDES, GUIDES, SHELL, HASHES, body_joints
from vault import joints


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '本地 VAULT 资料库未连接')
class DrawerBodyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(DEFAULT_ROOT)

    def test_scope_motion_and_print_quantities(self):
        guide = assembly(self.catalog, {'config': {}})
        body = guide['joints'][0]
        self.assertEqual(body['id'], 's3-1f-body-runners-v1')
        self.assertEqual(body['motion'], 'drawer')
        self.assertEqual(body['stroke_mm'], 50)
        self.assertEqual(body['page'], 7)
        self.assertFalse(guide['precision_ready'])
        self.assertEqual(len(body['instances']), 4)
        self.assertEqual(sum(len(i.get('components', [i])) for i in body['instances']), 6)
        parts = {p['id']:p for p in guide['parts']}
        self.assertEqual({parts[i['id']]['name'] for i in body['instances']}, set(HASHES))
        self.assertTrue(all(parts[i['id']]['copies'] == 1 for i in body['instances']))
        self.assertEqual(body['instances'][0]['explode'], [0,0,-50])
        self.assertTrue(all(c['explode'] == [0,0,-50] for c in body['instances'][1]['components']))
        self.assertTrue(all(c['explode'] == [0,0,0] for c in body['instances'][2]['components']))

    def test_body_is_independent_from_key_revision_and_other_profiles_survive_body_change(self):
        original = joints.digest
        for changed, present in [(joints.KEY, True), (BOX, False)]:
            def digest(path, size, mtime):
                return '0'*64 if Path(path).name == changed else original(path, size, mtime)
            with patch('vault.joints.digest', side_effect=digest):
                guide = assembly(self.catalog, {'config': {}})
            self.assertEqual(any(p['motion'] == 'drawer' for p in guide['joints'] if 'motion' in p), present)
            if changed == BOX:
                self.assertTrue(any(p['id'] == 's1f-panel-key-cap-v1' for p in guide['joints']))
        self.assertEqual(body_joints(self.catalog, []), [])

    def test_exact_partitions_and_preview_support_faces(self):
        guide = assembly(self.catalog, {'config': {}})
        profile = guide['joints'][0]
        parts = {p['id']:p for p in guide['parts']}
        for instance in profile['instances']:
            part = parts[instance['id']]
            values = list(struct.iter_unpack('<12fH', self.catalog.resolve(part['id']).read_bytes()[84:]))
            if instance.get('components'):
                lo = min(v[a] for v in values for a in (3,6,9))
                hi = max(v[a] for v in values for a in (3,6,9))
                center = (lo+hi)/2
                counts = {'negative_x':0,'positive_x':0}
                for v in values:
                    xs = [v[a]-center for a in (3,6,9)]
                    region = 'negative_x' if max(xs)<0 else 'positive_x' if min(xs)>0 else None
                    self.assertIsNotNone(region)
                    counts[region] += 1
                self.assertEqual(counts, {c['region']:c['faces'] for c in instance['components']})
                self.assertEqual(sum(counts.values()), part['faces'])
            if instance.get('variant'):
                self.assertEqual(part['name'], BOX)
                self.assertEqual(instance['variant']['removed_faces'], 15892)
                self.assertEqual(len(instance['variant']['remove_boxes']), 2)
