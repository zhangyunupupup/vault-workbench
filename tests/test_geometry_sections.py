"""Optional development geometry checks; production remains standard-library-only."""
from pathlib import Path
import unittest

try:
    import numpy as np
    import shapely
    from scripts.verify_key_cap import section, triangles
except ImportError:
    np = None

from vault.catalog import Catalog, DEFAULT_ROOT


@unittest.skipUnless(np is not None and Path(DEFAULT_ROOT).is_dir(), '需要可选 numpy/shapely 与本地模型库')
class SectionRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = Catalog(DEFAULT_ROOT)
        cls.panel, _ = triangles(catalog.resolve(catalog.match('S1F (Turn On Supports).stl', kind='drawer').id))
        cls.springs, _ = triangles(catalog.resolve(catalog.match('Springs.stl', kind='drawer').id))

    def test_vertex_plane_never_silently_fills_the_open_panel_cavity(self):
        # Before avoiding exact vertex planes, z=.5 filled the cavity (~7621
        # mm2). Neighbouring valid sections and the corrected one are ~3213.
        for z in (.4999, .5, .5001):
            self.assertGreater(section(self.panel, z).area, 3100)
            self.assertLess(section(self.panel, z).area, 3300)

    def test_noding_retains_spring_top_sections(self):
        upper = self.springs[self.springs[:, :, 1].mean(1) > 0]
        self.assertGreater(section(upper, 5).area, 320)
        self.assertLess(section(upper, 5).area, 340)

    def test_open_contours_fail_instead_of_reporting_clearance(self):
        mesh = np.array([[[0,0,0], [1,0,2], [0,1,2]]], dtype=float)
        with self.assertRaises(ValueError):
            section(mesh, 1)
