from pathlib import Path
import math
import struct
import unittest
from unittest.mock import patch

from vault.catalog import Catalog, DEFAULT_ROOT
from vault.assembly import assembly
from vault.joints import KEY, CAP, PANEL, PANEL_SHA256, KEY_PANEL_Y, SPRINGS, SPRINGS_SHA256, SIGNATURES, verified_joint, verified_joints


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '本地 VAULT 资料库未连接')
class JointContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(DEFAULT_ROOT)
        cls.parts = [cls.catalog.match(n, kind='drawer').public() for n in (KEY, CAP)]

    def test_supported_subassembly_does_not_certify_whole_kit(self):
        result = assembly(self.catalog, {'config': {}})
        self.assertFalse(result['precision_ready'])
        self.assertEqual(result['joint']['status'], 'geometry_checked')
        self.assertEqual({i['sha256'] for i in result['joint']['instances']}, set(SIGNATURES.values()))
        self.assertEqual(len(result['joint']['instances']), 2)
        self.assertIsNone(assembly(self.catalog, {'config': {'kind': 'sustainer', 'height': 2}})['joint'])

    def test_other_revision_or_missing_part_never_gets_old_transform(self):
        self.assertIsNone(verified_joint(self.catalog, self.parts[:1]))
        with patch('vault.joints.digest', return_value='0' * 64):
            self.assertIsNone(verified_joint(self.catalog, self.parts))

    def test_panel_profile_is_independent_and_preserves_original_pair(self):
        guide = assembly(self.catalog, {'config': {}})
        panel = next(p for p in guide['joints'] if p['id'] == 's1f-panel-key-cap-v1')
        pair = guide['joint']
        self.assertEqual(panel['id'], 's1f-panel-key-cap-v1')
        self.assertEqual(len(panel['instances']), 3)
        self.assertEqual(pair, guide['joint'])
        self.assertEqual(pair['instances'][0]['position'], [0, 0, 0])
        self.assertEqual(panel['instances'][0]['position'], [0, KEY_PANEL_Y, 0])
        self.assertAlmostEqual(panel['instances'][1]['position'][1]-panel['instances'][0]['position'][1],
                               pair['instances'][1]['position'][1])
        self.assertEqual(panel['instances'][2]['sha256'], PANEL_SHA256)
        self.assertLess(panel['instances'][0]['explode'][1], 0)
        self.assertFalse(guide['precision_ready'])

    def test_changed_or_missing_panel_falls_back_to_pair_only(self):
        pair = verified_joint(self.catalog, self.parts)
        self.assertEqual(verified_joints(self.catalog, self.parts, pair), [pair])
        all_parts = self.parts + [self.catalog.match(PANEL, kind='drawer').public()]
        with patch('vault.joints.digest', return_value='0'*64):
            self.assertEqual(verified_joints(self.catalog, all_parts, pair), [pair])
        self.assertEqual(verified_joints(self.catalog, all_parts, None), [])

    def test_spring_reference_has_complete_regions_and_never_certifies_closure(self):
        guide = assembly(self.catalog, {'config': {}})
        reference = next(p for p in guide['joints'] if p['status'] == 'orientation_only')
        self.assertEqual(reference['status'], 'orientation_only')
        self.assertGreaterEqual(reference['min_gap'], 40)
        self.assertEqual(reference['page'], 2)
        spring = reference['instances'][-1]
        self.assertEqual(spring['sha256'], SPRINGS_SHA256)
        part = next(p for p in guide['parts'] if p['name'] == SPRINGS)
        self.assertEqual(part['copies'], 1)
        self.assertEqual(sum(c['faces'] for c in spring['components']), part['faces'])
        self.assertEqual({c['region'] for c in spring['components']}, {'negative_y', 'positive_y'})
        # At the closest allowed view position, both unbent springs stay wholly
        # behind the key's rear-most point. This is not a nominal seated pose.
        mesh = list(struct.iter_unpack('<12fH', self.catalog.resolve(part['id']).read_bytes()[84:]))
        height = max(v[a] for v in mesh for a in (5,8,11))-min(v[a] for v in mesh for a in (5,8,11))
        key = reference['instances'][0]
        for component in spring['components']:
            front = component['position'][1] + component['explode'][1]*reference['min_gap']/100 + height
            self.assertLess(front, key['position'][1])

    def test_spring_version_change_removes_only_orientation_reference(self):
        guide = assembly(self.catalog, {'config': {}})
        from vault.joints import digest
        def changed_spring(path, size, mtime):
            return '0'*64 if Path(path).name == SPRINGS else digest(path, size, mtime)
        with patch('vault.joints.digest', side_effect=changed_spring):
            result = assembly(self.catalog, {'config': {}})
        self.assertEqual([p['id'] for p in result['joints']], ['s3-1f-body-runners-v1', 's1f-panel-key-cap-v1', 'standard-key-cap-v1'])

    def test_measured_seating_plane_and_opening_direction(self):
        bounds = {}
        for p in self.parts:
            values = list(struct.iter_unpack('<12fH', self.catalog.resolve(p['id']).read_bytes()[84:]))
            bounds[p['name']] = ([min(v[a] for v in values for a in (3+i, 6+i, 9+i)) for i in range(3)],
                                 [max(v[a] for v in values for a in (3+i, 6+i, 9+i)) for i in range(3)])
            if p['name'] == CAP:
                # Verify a real planar inner floor exists 2 mm above the cap base.
                plane = bounds[CAP][0][2] + 2
                area = 0
                for v in values:
                    if max(abs(v[a]-plane) for a in (5, 8, 11)) < .001:
                        ax,ay=v[6]-v[3],v[7]-v[4];bx,by=v[9]-v[3],v[10]-v[4]
                        area += abs(ax*by-ay*bx)/2
                self.assertGreater(area, 200)
        joint = verified_joint(self.catalog, self.parts)
        cap = joint['instances'][1]
        self.assertEqual(cap['rotation'], [180, 0, 0])
        key_top = bounds[KEY][1][2]-bounds[KEY][0][2]
        # After flipping, the cap's inner floor sits on the handle top.
        self.assertAlmostEqual(cap['position'][1]-2, key_top, places=4)
        self.assertGreater(cap['explode'][1], key_top)
        self.assertTrue(all(math.isfinite(x) for i in joint['instances'] for k in ('rotation','position','explode') for x in i[k]))
