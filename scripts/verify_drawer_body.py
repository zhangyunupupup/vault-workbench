"""Optional sampled S3 body/runner check: numpy + shapely, local source files only."""
import argparse
import json
from pathlib import Path
import sys
from itertools import combinations

import numpy as np
import shapely
from shapely import box, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_key_cap import triangles, section
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.drawer_body import BOX, SLIDES, GUIDES, SHELL, body_joints


def pose(mesh, description):
    # Same [source X, source Z, -source Y] mapping and XYZ Euler order as Three.
    world = mesh[:, :, [0, 2, 1]].copy()
    world[:, :, 2] *= -1
    x, y, z = np.radians(description['rotation'])
    rx = np.array([[1,0,0], [0,np.cos(x),-np.sin(x)], [0,np.sin(x),np.cos(x)]])
    ry = np.array([[np.cos(y),0,np.sin(y)], [0,1,0], [-np.sin(y),0,np.cos(y)]])
    rz = np.array([[np.cos(z),-np.sin(z),0], [np.sin(z),np.cos(z),0], [0,0,1]])
    world = world @ (rx @ ry @ rz).T + description['position']
    # Z-up, depth along +Y, for cross-sections perpendicular to the drawer path.
    result = world[:, :, [0, 2, 1]].copy()
    result[:, :, 1] *= -1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    args = parser.parse_args()
    catalog = Catalog(args.root)
    parts = [catalog.match(n, kind='drawer').public() for n in (BOX, SLIDES, GUIDES, SHELL)]
    profile = body_joints(catalog, parts)[0]
    parts = {p['id']: p for p in parts}
    bodies, hashes = [], {}
    support_boxes = None
    removed = 0
    for instance in profile['instances']:
        part = parts[instance['id']]
        mesh, hashes[part['name']] = triangles(catalog.resolve(part['id']))
        if instance.get('variant'):
            world = mesh[:, :, [0,2,1]].copy(); world[:, :, 2] *= -1
            support_boxes = instance['variant']['remove_boxes']
            keep = np.ones(len(mesh), dtype=bool)
            for region in support_boxes:
                keep &= ~((world >= region['min']) & (world <= region['max'])).all((1,2))
            removed = int((~keep).sum())
            assert removed == instance['variant']['removed_faces']
        descriptions = instance.get('components') or [instance]
        for description in descriptions:
            selected = mesh
            if description.get('region'):
                negative = description['region'] == 'negative_x'
                mask = (mesh[:,:,0] < 0).all(1) if negative else (mesh[:,:,0] > 0).all(1)
                selected = mesh[mask]
                assert len(selected) == description['faces']
            bodies.append({'name': description.get('title', part['name']),
                           'mesh': pose(selected, description), 'moving': description['explode'][2] != 0,
                           'clean': part['name'] == BOX})
    ys = np.arange(-124.25, 72.26, .5)
    empty = unary_union([])
    arrays = []
    raw_box_cuts = []
    for body in bodies:
        mesh = body['mesh'][:, :, [0,2,1]]
        lo, hi = mesh[:,:,2].min(), mesh[:,:,2].max()
        cuts = []
        for y in ys:
            cut = section(mesh, y) if lo < y < hi else empty
            if body['clean']:
                raw_box_cuts.append(cut)
                for region in support_boxes:
                    if -region['max'][2] < y < -region['min'][2]:
                        cut = cut.difference(box(region['min'][0], region['min'][1], region['max'][0], region['max'][1]))
            cuts.append(cut)
        assert sum(not cut.is_empty for cut in cuts) > .9*(hi-lo)/.5
        arrays.append(np.array(cuts, dtype=object))
        print('checked sections:', body['name'], flush=True, file=sys.stderr)
    # Static shell/outer guides use the same 294 section planes at every step.
    base = 100
    count = len(ys)-base
    moving = [i for i, body in enumerate(bodies) if body['moving']]
    fixed = [i for i, body in enumerate(bodies) if not body['moving']]
    worst_area, worst_volume = 0., 0.
    for travel in range(profile['stroke_mm']+1):
        spans = [a[base-2*travel:base-2*travel+count] if body['moving'] else a[base:] for body,a in zip(bodies,arrays)]
        pairs = combinations(range(len(bodies)), 2) if travel == 0 else ((a,b) for a in moving for b in fixed)
        for a,b in pairs:
            areas = shapely.area(shapely.intersection(spans[a], spans[b]))
            peak, volume = float(areas.max()), float(areas.sum()*.5)
            worst_area, worst_volume = max(worst_area,peak), max(worst_volume,volume)
            if peak > 1e-6:
                raise AssertionError((travel, bodies[a]['name'], bodies[b]['name'], peak, volume))
    raw_control=sum(float(shapely.area(shapely.intersection(np.array(raw_box_cuts[base:],dtype=object),arrays[i][base:])).sum()*.5) for i in (1,2))
    from shapely.affinity import translate
    shifted=np.array([translate(cut,xoff=1) for cut in arrays[2][base:]],dtype=object)
    wrong_offset=float(shapely.area(shapely.intersection(shifted,arrays[4][base:])).sum()*.5)
    assert raw_control > 1 and wrong_offset > 1
    print(json.dumps({'raw_support_control_mm3': raw_control, 'wrong_rail_x_offset_1mm_mm3': wrong_offset, 'profile': profile['id'], 'sha256': hashes, 'bodies': len(bodies),
                      'removed_preview_faces': removed, 'slice_spacing_mm': .5, 'section_planes_per_pose': count,
                      'travel_step_mm': 1, 'travel_positions': profile['stroke_mm']+1,
                      'max_intersection_mm2': worst_area, 'max_sampled_pair_volume_mm3': worst_volume,
                      'limits': 'Sampled post-support-removal rigid geometry only. Not continuous collision, full assembly, physical stroke, tolerance or load validation.'}, indent=2))


if __name__ == '__main__':
    main()
