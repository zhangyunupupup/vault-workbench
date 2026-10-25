from collections import Counter
from pathlib import Path
import struct
import tempfile
import unittest

from vault.assembly import assembly, mesh_header
from vault.catalog import Catalog, DEFAULT_ROOT, ValidationError


class MeshHeaderContracts(unittest.TestCase):
    def test_binary_header_rejects_truncation_empty_and_inconsistent_count(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'part.stl'
            for data in (b'bad', bytes(80) + struct.pack('<I', 0),
                         bytes(80) + struct.pack('<I', 2) + bytes(50)):
                path.write_bytes(data)
                with self.assertRaises(ValidationError):
                    mesh_header(path)
            path.write_bytes(bytes(80) + struct.pack('<I', 1) + bytes(50))
            meta = mesh_header(path)
            self.assertEqual(meta['faces'], 1)
            self.assertEqual(meta['bytes'], 134)
            self.assertEqual(meta['mtime_ns'], str(path.stat().st_mtime_ns))


@unittest.skipUnless(Path(DEFAULT_ROOT).is_dir(), '本地 VAULT 资料库未连接')
class AssemblyGuideContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(DEFAULT_ROOT)

    def guide(self, **cfg):
        return assembly(self.catalog, {'config': cfg})

    def test_all_files_covered_and_no_unverified_transforms(self):
        for kind, height, count in [('drawer', 1, 13), ('sustainer', 2, 11)]:
            with self.subTest(kind=kind):
                result = self.guide(kind=kind, height=height)
                self.assertTrue(result['supported'])
                self.assertFalse(result['precision_ready'])
                ids = {p['id'] for p in result['parts']}
                self.assertEqual(len(ids), count)
                self.assertEqual(ids, {i for s in result['steps'] for i in s['parts']})
                self.assertFalse(any('transform' in p or 'position' in p for p in result['parts']))
                self.assertLessEqual(sum(p['faces'] * p['copies'] for p in result['parts']), 3000000)

    def test_step_hardware_matches_whole_kit_totals(self):
        for cfg in ({}, {'kind': 'sustainer', 'height': 2}):
            result = self.guide(**cfg)
            expected = Counter()
            actual = Counter()
            for h in result['hardware']:
                expected[h['name']] += h['quantity']
            for step in result['steps']:
                for h in step['hardware']:
                    actual[h['name']] += h['quantity']
            self.assertEqual(actual, expected)

    def test_optional_files_and_pages_are_not_fabricated(self):
        result = self.guide(labels=False, roof='none', latches=0)
        self.assertEqual(len(result['parts']), 10)
        self.assertEqual(len(result['steps']), 7)
        self.assertFalse(any(s['doc'] == 1 for s in result['steps']))
        self.assertEqual(result['steps'][-1]['page'], 8)
        self.assertTrue(all(p['name'] not in ('Label.stl', 'Latch.stl', 'S3 Grid Roof.stl') for p in result['parts']))

    def test_one_kit_view_keeps_file_pair_counts_and_input_untouched(self):
        cfg = {'quantity': 5}
        result = assembly(self.catalog, {'config': cfg})
        parts = {p['name']: p['copies'] for p in result['parts']}
        self.assertEqual(cfg['quantity'], 5)
        self.assertEqual(parts['Springs.stl'], 1)
        self.assertEqual(parts['Facade Cap.stl'], 2)
        self.assertEqual(parts['Runner Stopper.stl'], 2)

    def test_variant_gates_do_not_silently_show_a_different_kit(self):
        unsupported = [dict(family='M'), dict(depth=4), dict(height=2),
                       dict(key='hidden'), dict(roof='table'), dict(rails=True),
                       dict(interior='gridfinity'), dict(base='whole'), dict(mount='wall'),
                       dict(kind='sustainer', height=2, depth=6, split_roof=True)]
        for cfg in unsupported:
            with self.subTest(cfg=cfg):
                result = self.guide(**cfg)
                self.assertFalse(result['supported'])
                self.assertEqual(result['parts'], [])
                self.assertEqual(result['steps'], [])
                self.assertIn('reason', result)

    def test_missing_model_is_rejected_instead_of_substituted(self):
        for cfg in ({'roof': 'heavy'}, {'kind': 'sustainer', 'height': 2, 'split_roof': True}):
            with self.assertRaisesRegex(ValidationError, '缺少文件'):
                self.guide(**cfg)

    def test_colors_preserved_and_invalid_colors_rejected(self):
        result = assembly(self.catalog, {'config': {}, 'colors': {'body': '#ff0000'}})
        self.assertEqual(next(p['color'] for p in result['parts'] if p['name']=='S3 Module 1F.stl'), '#FF0000')
        with self.assertRaises(ValidationError):
            assembly(self.catalog, {'config': {}, 'colors': {'body': 'red'}})

    def test_bad_config_and_client_paths_not_used(self):
        for config in ([], 'S3', None):
            with self.assertRaises(ValidationError):
                assembly(self.catalog, {'config': config})
        result = assembly(self.catalog, {'config': {}, 'parts': [{'id': '../../secret'}], 'precision_ready': True})
        self.assertFalse(result['precision_ready'])
        self.assertTrue(all(p['id'] in self.catalog.by_id for p in result['parts']))


if __name__ == '__main__':
    unittest.main()
