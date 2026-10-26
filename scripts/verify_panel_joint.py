"""Optional sampled panel/key collision check (numpy + shapely; local STLs only)."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_key_cap import triangles, section
from vault.assembly import assembly
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.joints import KEY, CAP, PANEL


def plane(mesh, height):
    areas = np.linalg.norm(np.cross(mesh[:, 1]-mesh[:, 0], mesh[:, 2]-mesh[:, 0]), axis=1)/2
    mask = (np.ptp(mesh[:, :, 2], axis=1) < .0001) & (abs(mesh[:, :, 2].mean(1)-height) < .001)
    return {'height': float(np.average(mesh[mask, :, 2].mean(1), weights=areas[mask])),
            'area_mm2': float(areas[mask].sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    args = parser.parse_args()
    catalog = Catalog(args.root)
    guide = assembly(catalog, {'config': {}})
    profile = next(p for p in guide['joints'] if p['id'] == 's1f-panel-key-cap-v1')
    parts = {p['name']: p for p in guide['parts']}
    meshes, hashes = {}, {}
    for name in (PANEL, KEY, CAP):
        meshes[name], hashes[name] = triangles(catalog.resolve(parts[name]['id']))
    panel, key, cap = (meshes[n] for n in (PANEL, KEY, CAP))
    poses = {i['id']: i for i in profile['instances']}
    shift = poses[parts[KEY]['id']]['position'][1]
    cap_floor = poses[parts[CAP]['id']]['position'][1]-cap[:, :, 2].max()
    assert cap_floor > panel[:, :, 2].max()  # Cap and panel have disjoint axial bounds.
    planes = {'panel_inner': plane(panel, 2.4), 'panel_front': plane(panel, 10),
              'key_flange': plane(key, 10.8006), 'key_front': plane(key, 18.4006)}
    for a, b in [('panel_inner', 'key_flange'), ('panel_front', 'key_front')]:
        assert abs(planes[a]['height']-planes[b]['height']-shift) < .0001
    heights = np.arange(.025, 10, .05)
    panel_sections = [section(panel, z) for z in heights]
    results = {}
    for offset in (0, -1, 1):
        key_sections = [section(key, z-shift-offset) for z in heights]
        areas = [a.intersection(b).area for a, b in zip(panel_sections, key_sections)]
        results[str(offset)] = {
            'max_intersection_mm2': max(areas), 'sampled_intersection_mm3': sum(areas)*.05,
            'empty_sections': sum(a.is_empty or b.is_empty for a, b in zip(panel_sections, key_sections))}
    assert results['0']['max_intersection_mm2'] < 1e-6 and results['0']['empty_sections'] == 0
    assert all(results[str(o)]['sampled_intersection_mm3'] > 1 for o in (-1, 1))
    print(json.dumps({'profile': profile['id'], 'sha256': hashes, 'planes': planes,
                      'key_y_mm': shift, 'slice_count': len(heights), 'slice_spacing_mm': .05,
                      'segment_rounding_mm': .0001, 'key_offset_controls_mm': results,
                      'limits': 'Seated pose only, sampled sections; not insertion-path, elastic snap-fit or physical validation.'}, indent=2))


if __name__ == '__main__':
    main()
