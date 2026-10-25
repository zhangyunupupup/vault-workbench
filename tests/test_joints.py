from pathlib import Path
import math
import struct
import unittest
from unittest.mock import patch

from vault.catalog import Catalog, DEFAULT_ROOT
from vault.assembly import assembly
from vault.joints import KEY, CAP, SIGNATURES, verified_joint


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
