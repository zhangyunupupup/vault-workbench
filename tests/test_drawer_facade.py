from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from vault.assembly import assembly
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.drawer_body import BOX
from vault.drawer_facade import facade_joints, PROFILE_ID, CLOSED_OFFSET, FRONT_Y, AXIS_HEIGHT
from vault import joints


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '本地 VAULT 资料库未连接')
class DrawerFacadeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(DEFAULT_ROOT)
        cls.guide = assembly(cls.catalog, {'config': {}})

    def test_composed_scope_and_rigid_motion(self):
        guide = self.guide
        facade = guide['joints'][0]
        self.assertEqual(facade['id'], PROFILE_ID)
        self.assertEqual(len(facade['instances']), 7)
        self.assertEqual(sum(len(i.get('components', [i])) for i in facade['instances']), 9)
        self.assertFalse(guide['precision_ready'])
        parts = {p['id']: p for p in guide['parts']}
        poses = {parts[i['id']]['name']: i for i in facade['instances']}
        self.assertNotIn(joints.SPRINGS, poses)
        self.assertEqual(poses[joints.PANEL]['position'], [0, AXIS_HEIGHT, -FRONT_Y-CLOSED_OFFSET])
        self.assertEqual(poses[joints.PANEL]['rotation'], [-90,0,0])
        self.assertEqual(poses[joints.CAP]['rotation'], [90,0,0])
        moving = [p for i in facade['instances'] for p in i.get('components', [i]) if p['explode'][2]]
        self.assertEqual(len(moving), 6)
        self.assertTrue(all(p['explode'] == [0,0,-50] for p in moving))
        self.assertTrue(all(parts[i['id']]['copies'] == 1 for i in facade['instances']))
        self.assertEqual(facade['page'], 6)

    def test_composition_preserves_independent_profiles(self):
        profiles = self.guide['joints'][1:]
        original = deepcopy(profiles)
        composed = facade_joints(profiles, profiles)[0]
        self.assertEqual(profiles, original)
        body = next(p for p in profiles if p['id'] == 's3-1f-body-runners-v1')
        self.assertEqual(composed['instances'][0]['position'][2], body['instances'][0]['position'][2]-CLOSED_OFFSET)
        composed['instances'][0]['variant']['remove_boxes'][0]['min'][0] = 0
        self.assertEqual(profiles, original)
        self.assertEqual(facade_joints([], profiles), [])
        self.assertEqual(facade_joints(profiles, []), [])

    def test_revision_mismatch_only_removes_dependent_profiles(self):
        original = joints.digest
        for name in (BOX, joints.PANEL, joints.KEY, joints.CAP, joints.SPRINGS):
            with self.subTest(name=name):
                def digest(path, size, mtime):
                    return '0'*64 if Path(path).name == name else original(path,size,mtime)
                with patch('vault.joints.digest', side_effect=digest):
                    profiles = assembly(self.catalog, {'config': {}})['joints']
                ids = {p['id'] for p in profiles}
                self.assertEqual(PROFILE_ID in ids, name == joints.SPRINGS)
                self.assertEqual('s3-1f-body-runners-v1' in ids, name != BOX)
                self.assertEqual('s1f-panel-key-cap-v1' in ids, name not in (joints.PANEL,joints.KEY,joints.CAP))
