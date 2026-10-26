"""Optional development check; pip install numpy shapely, then run from repo root.

Reads local licensed STLs only. Prints measurements, never mesh coordinates.
This sampled check is NOT a continuous collision or physical-fit certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from shapely import LineString, polygonize_full, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.joints import KEY, CAP, SIGNATURES, verified_joint


def triangles(path):
    data = path.read_bytes()
    count = int.from_bytes(data[80:84], 'little')
    if len(data) != 84 + count * 50:
        raise ValueError('Invalid binary STL')
    records = np.frombuffer(data, dtype=np.dtype([
        ('normal', '<f4', (3,)), ('points', '<f4', (3, 3)), ('attr', '<u2')]), offset=84)
    mesh = records['points'].astype(np.float64)
    lo, hi = mesh.min((0, 1)), mesh.max((0, 1))
    # Same normalization as readSTL; retain Z-up for horizontal sectioning.
    mesh -= [(lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2]]
    return mesh, hashlib.sha256(data).hexdigest()


def section(mesh, z):
    # A cut exactly through vertices can drop an entire boundary under the
    # half-open edge rule. Move a tiny amount (1e-6 mm) off that plane.
    if np.any(abs(mesh[:, :, 2]-z) < 1e-9):
        z += .000001
    mesh = mesh[(mesh[:, :, 2].min(1) < z) & (mesh[:, :, 2].max(1) > z)]
    if not len(mesh):
        return unary_union([])
    points = np.full((len(mesh), 3, 2), np.nan)
    for edge, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
        v, w = mesh[:, a], mesh[:, b]
        crossing = ((v[:, 2] < z) & (w[:, 2] >= z)) | ((w[:, 2] < z) & (v[:, 2] >= z))
        t = (z-v[crossing, 2])/(w[crossing, 2]-v[crossing, 2])
        points[crossing, edge] = v[crossing, :2] + t[:, None]*(w[crossing, :2]-v[crossing, :2])
    segments = points[np.isfinite(points[:, :, 0])].reshape(-1, 2, 2).round(4)
    lines = [LineString(s) for s in segments if np.linalg.norm(s[0]-s[1]) > 1e-5]
    # Node crossings/T-junctions before polygonizing. Otherwise a real cavity
    # can disappear or a valid section can be returned as empty.
    noded = unary_union(lines)
    polygons, cuts, dangles, invalid = polygonize_full(list(noded.geoms) if hasattr(noded, 'geoms') else [noded])
    if cuts.length+dangles.length+invalid.length > .005:
        raise ValueError(f'Unclosed section at {z:g} mm; cannot certify empty space')
    # Odd/even crossings preserve cavities instead of filling inner rings.
    inside = []
    a, b = segments[:, 0], segments[:, 1]
    for polygon in polygons.geoms:
        x, y = polygon.representative_point().coords[0]
        crossing = (a[:, 1] > y) != (b[:, 1] > y)
        hits = a[crossing, 0] + (y-a[crossing, 1])*(b[crossing, 0]-a[crossing, 0])/(b[crossing, 1]-a[crossing, 1])
        if (hits > x).sum() % 2:
            inside.append(polygon)
    return unary_union(inside)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    args = parser.parse_args()
    catalog = Catalog(args.root)
    parts = [catalog.match(name, kind='drawer').public() for name in (KEY, CAP)]
    profile = verified_joint(catalog, parts)
    if profile is None:
        raise ValueError('Files do not match the measured profile')
    key, key_hash = triangles(catalog.resolve(parts[0]['id']))
    cap, cap_hash = triangles(catalog.resolve(parts[1]['id']))
    assert key_hash == SIGNATURES[KEY] and cap_hash == SIGNATURES[CAP]
    cap[:, :, 1:] *= -1  # World X rotation 180 degrees, expressed Z-up.
    seat = profile['instances'][1]['position'][1]
    cap[:, :, 2] += seat
    # 194 interior samples across the overlapping handle/cap height.
    low = max(key[:, :, 2].min(), cap[:, :, 2].min()) + .005
    high = min(key[:, :, 2].max(), cap[:, :, 2].max())
    heights = np.arange(low, high, .05)
    key_sections = [section(key, z) for z in heights]
    results = {}
    for name, penetration in [('seated', 0), ('forced_1mm_penetration', 1)]:
        cap_sections = [section(cap, z+penetration) for z in heights]
        areas = [a.intersection(b).area for a, b in zip(key_sections, cap_sections)]
        results[name] = {'max_intersection_mm2': max(areas),
                         'sampled_intersection_mm3': sum(areas)*.05,
                         'empty_sections': sum(a.is_empty or b.is_empty for a, b in zip(key_sections, cap_sections))}
    assert len(heights) == 194
    assert results['seated']['empty_sections'] == 0
    assert results['seated']['max_intersection_mm2'] < 1e-6
    assert results['forced_1mm_penetration']['sampled_intersection_mm3'] > 1
    print(json.dumps({'profile': profile['id'], 'sha256': SIGNATURES,
                      'slice_spacing_mm': .05, 'slice_count': len(heights),
                      'segment_rounding_mm': .0001, 'results': results,
                      'limits': 'Sampled digital geometry only; no continuous collision or physical fit certification.'}, indent=2))


if __name__ == '__main__':
    main()
