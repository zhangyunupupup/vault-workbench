"""Measured subassemblies bound to exact source-file revisions.

Positions use the viewer's centered X/Z, floor-zero Y coordinates, in mm.
No claim is made about a whole kit's assembly or physical tolerances.
"""
from functools import lru_cache
import hashlib

KEY = 'Key (Turn On Supports).stl'
CAP = 'Key Cap.stl'
SIGNATURES = {
    KEY: '7953495ea17c6062c4f80233084ba7db1ad3c28b0927f9b20701fb1b0768a7c0',
    CAP: 'c5858b1e62cd00d119c108c246a3a352ba713a94ebd29b521495fea0d8a2c444',
}


@lru_cache(maxsize=8)
def digest(path, size, mtime_ns):
    with open(path, 'rb') as stream:
        result = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
        return result.hexdigest()


def verified_joint(catalog, parts):
    by_name = {p['name']: p for p in parts}
    if not all(n in by_name for n in SIGNATURES):
        return None
    for name, expected in SIGNATURES.items():
        path = catalog.resolve(by_name[name]['id'])
        stat = path.stat()
        if digest(str(path), stat.st_size, stat.st_mtime_ns) != expected:
            return None
    return {
        'id': 'standard-key-cap-v1', 'title': '标准旋钮与盖', 'status': 'geometry_checked',
        'doc': 2, 'page': 1,
        'note': '仅核对旋钮与盖的数字几何定位；未做实物压装测试。面板、弹簧和整箱接合仍待核对。',
        'method': '中心线对齐；盖绕 X 轴翻转 180°；内腔底面接触旋钮顶部。0.05 mm 间隔的 194 个截面采样未见相交，不能代替连续碰撞或实物公差验证。',
        'instances': [
            {'id': by_name[KEY]['id'], 'sha256': SIGNATURES[KEY], 'position': [0, 0, 0], 'rotation': [0, 0, 0], 'explode': [0, 0, 0]},
            {'id': by_name[CAP]['id'], 'sha256': SIGNATURES[CAP], 'position': [0, 35.41703558, 0], 'rotation': [180, 0, 0], 'explode': [0, 70, 0]},
        ],
    }
