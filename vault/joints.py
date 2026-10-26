"""Measured subassemblies bound to exact source-file revisions.

Positions use the viewer's centered X/Z, floor-zero Y coordinates, in mm.
No claim is made about a whole kit's assembly or physical tolerances.
"""
from functools import lru_cache
from copy import deepcopy
import hashlib

KEY = 'Key (Turn On Supports).stl'
CAP = 'Key Cap.stl'
PANEL = 'S1F (Turn On Supports).stl'
PANEL_SHA256 = '7099f6d50adb8bfb6b714799820556fbdc3c9c546e139bb18c46c02f24587709'
SPRINGS = 'Springs.stl'
SPRINGS_SHA256 = '55f2736227703b6e37b0e5beb844019f067e6a7732fd7ae7d0dfc95ba73e1a2c'
KEY_PANEL_Y = -8.4006
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
        'instructions': ['盖的开口朝向旋钮，把两者中心对齐后合拢。', '这里只展示两个零件的接合。实际安装还需按手册将旋钮穿过面板，再安装盖子。'],
        'instances': [
            {'id': by_name[KEY]['id'], 'sha256': SIGNATURES[KEY], 'position': [0, 0, 0], 'rotation': [0, 0, 0], 'explode': [0, 0, 0]},
            {'id': by_name[CAP]['id'], 'sha256': SIGNATURES[CAP], 'position': [0, 35.41703558, 0], 'rotation': [180, 0, 0], 'explode': [0, 70, 0]},
        ],
    }


def verified_joints(catalog, parts, key_cap):
    """Expose each independently verified scope; a changed panel keeps key/cap usable."""
    if key_cap is None:
        return []
    profiles = [key_cap]
    panel = next((p for p in parts if p['name'] == PANEL), None)
    if panel is None:
        return profiles
    path = catalog.resolve(panel['id'])
    stat = path.stat()
    if digest(str(path), stat.st_size, stat.st_mtime_ns) != PANEL_SHA256:
        return profiles
    instances = deepcopy(key_cap['instances'])
    for instance in instances:
        instance['position'][1] += KEY_PANEL_Y
    instances[0]['explode'] = [0, -60, 0]
    instances.append({'id': panel['id'], 'sha256': PANEL_SHA256,
                      'position': [0, 0, 0], 'rotation': [0, 0, 0],
                      'explode': [0, 0, 0], 'label_offset': [-76, 5, 0]})
    profiles.insert(0, {
        'id': 's1f-panel-key-cap-v1', 'title': '前面板、旋钮与盖',
        'status': 'geometry_checked', 'doc': 2, 'page': 1,
        'note': '仅核对前面板、标准旋钮和盖的数字定位；未做实物压装测试。弹簧、抽屉和整箱机构仍待核对。',
        'method': '旋钮与面板中心对齐；两组台阶面的高度差均为约 -8.4006 mm。0.05 mm 间隔的 200 个截面采样未见相交，前后错位 1 mm 对照可检测到相交。',
        'instructions': ['旋钮从前面板背面穿入，盖从正面装在旋钮上。拖动画布旋转视角，可查看背面的旋钮台阶。',
                         '滑块展示三件的分解关系；实际安装顺序为先穿入旋钮，再安装盖。动画不模拟卡扣变形或压装过程。'],
        'instances': instances,
    })
    springs = next((p for p in parts if p['name'] == SPRINGS), None)
    if springs is not None:
        path = catalog.resolve(springs['id'])
        stat = path.stat()
        if digest(str(path), stat.st_size, stat.st_mtime_ns) == SPRINGS_SHA256:
            reference = deepcopy(profiles[0])
            reference.update({
                'id': 's1f-spring-orientation-v1', 'title': '左右弹簧 · 安装朝向参考',
                'status': 'orientation_only', 'page': 2, 'view': 'rear', 'min_gap': 40,
                'note': '弹簧按未变形状态展示，保留安装前距离。弹性接合尚待核对，暂不提供合拢。',
                'method': '按源文件中心 Y=0 分出两件完整网格；平整面朝向面板背面。自由弹簧与旋钮存在相交，不能用刚体合拢替代弹性压装。',
                'instructions': ['从背面查看：左右弹簧的卡口分别朝向两侧螺丝柱，平整面朝向面板背面外侧。',
                                 '此处显示安装前的朝向与对应位置，弹簧保留未变形几何。下压后的弯曲、卡接及旋钮转动尚待核对。'],
            })
            for instance in reference['instances']:
                instance['explode'] = [0, 0, 0]
            reference['instances'].append({
                'id': springs['id'], 'sha256': SPRINGS_SHA256,
                'position': [0, 0, 0], 'rotation': [0, 0, 0], 'explode': [0, 0, 0],
                'components': [
                    {'region': 'negative_y', 'faces': 20816, 'title': '左弹簧',
                     'position': [-38.35, .5951, 19.2951], 'rotation': [0, 180, 0], 'explode': [0, -60, 0]},
                    {'region': 'positive_y', 'faces': 20484, 'title': '右弹簧',
                     'position': [38.35, .5951, 19.2951], 'rotation': [0, 0, 0], 'explode': [0, -60, 0]},
                ],
            })
            profiles.insert(1, reference)
    return profiles
