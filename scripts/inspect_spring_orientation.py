"""Inspect the unbent spring candidate and the enforced installation-before view.

Optional numpy/shapely development dependencies. Does not certify seating.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_key_cap import triangles, section
from vault.assembly import assembly
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.joints import KEY, PANEL, SPRINGS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    args = parser.parse_args()
    catalog = Catalog(args.root)
    guide = assembly(catalog, {'config': {}})
    profile = next(p for p in guide['joints'] if p['status'] == 'orientation_only')
    parts = {p['name']: p for p in guide['parts']}
    key, _ = triangles(catalog.resolve(parts[KEY]['id']))
    panel, _ = triangles(catalog.resolve(parts[PANEL]['id']))
    springs, digest = triangles(catalog.resolve(parts[SPRINGS]['id']))
    key[:, :, 2] += profile['instances'][0]['position'][1]
    description = profile['instances'][-1]
    split = []
    for pose in description['components']:
        negative = pose['region'] == 'negative_y'
        mask = (springs[:, :, 1] < 0).all(1) if negative else (springs[:, :, 1] > 0).all(1)
        mesh = springs[mask].copy()
        assert len(mesh) == pose['faces']
        if pose['rotation'][1] == 180:
            mesh[:, :, :2] *= -1
        x, y, z = pose['position']
        mesh += [x, -z, y]
        closest_front = mesh[:, :, 2].max() + pose['explode'][1]*profile['min_gap']/100
        assert closest_front < min(key[:, :, 2].min(), panel[:, :, 2].min())
        split.append((pose['title'], mesh, float(closest_front)))
    assert sum(len(t) for _, t, _ in split) == len(springs)
    heights = np.arange(.625, 5.76, .05)
    key_cuts = [section(key, z) for z in heights]
    panel_cuts = [section(panel, z) for z in heights]
    report = []
    for title, mesh, closest_front in split:
        cuts = [section(mesh, z) for z in heights]
        intersections = {}
        for label, other in [('key', key_cuts), ('panel', panel_cuts)]:
            areas = [a.intersection(b).area for a, b in zip(cuts, other)]
            intersections[label] = {'max_area_mm2': max(areas), 'sampled_volume_mm3': sum(areas)*.05}
        assert intersections['key']['sampled_volume_mm3'] > 20
        report.append({'title': title, 'faces': len(mesh),
                       'closest_display_front_z_mm': closest_front,
                       'unbent_candidate_intersections': intersections})
    print(json.dumps({'sha256': digest, 'faces': len(springs),
                      'slice_count': len(heights), 'slice_spacing_mm': .05,
                      'min_display_gap_percent': profile['min_gap'], 'components': report,
                      'limits': 'Candidate intersections do not prove installed preload or physical deformation. Only separated orientation view is enabled.'}, indent=2))


if __name__ == '__main__':
    main()
