"""S3 1F body/runner preview, after the manual's support-removal step.

This deliberately excludes the facade, locking parts and physical stroke limits.
"""
from . import joints

BOX = 'S3 Box 1F.stl'
SLIDES = 'x3 Runner Slides.stl'
GUIDES = 'x3 Runner Guides.stl'
SHELL = 'S3 Module 1F.stl'
HASHES = {
    BOX: 'a91318efa047888a253658eb88cc14b2c70ed151cc42aedd3fb954c911791d6d',
    SLIDES: 'fc5486b8a346d1f73dec6fa1e028e1bed4b97bd359db55daeca8a8bb8cf9c9bb',
    GUIDES: '4234e1189bf4e7044a3992aa37ef269ad12e04cbae9e4c65ffc9549bd7ab797f',
    SHELL: 'af1043b8aba9597358c03b6fffcab1e8d0e4f282e8fa0e6dce5b889bc7ce3ac5',
}
SUPPORT_BOXES = [
    {'min': [-66.3985, 13.2156, -70.7398], 'max': [-65.8983, 23.7844, 43.8676]},
    {'min': [65.8983, 13.2156, -70.7398], 'max': [66.3985, 23.7844, 43.8676]},
]


def body_joints(catalog, parts):
    by_name = {p['name']: p for p in parts}
    if not all(n in by_name for n in HASHES):
        return []
    for name, expected in HASHES.items():
        path = catalog.resolve(by_name[name]['id'])
        stat = path.stat()
        if joints.digest(str(path), stat.st_size, stat.st_mtime_ns) != expected:
            return []
    def instance(name, **extra):
        return {'id': by_name[name]['id'], 'sha256': HASHES[name],
                'position': [0, 0, 0], 'rotation': [0, 0, 0], 'explode': [0, 0, 0], **extra}
    return [{
        'id': 's3-1f-body-runners-v1', 'title': '抽屉主体与滑轨',
        'status': 'geometry_checked', 'motion': 'drawer', 'stroke_mm': 50, 'view': 'drawer_front',
        'transparent_ids': [by_name[SHELL]['id']],
        'doc': 2, 'page': 7,
        'note': '画布显示已清理侧槽辅助支撑的主体，打印文件保留原始支撑。50 mm为本次检查的查看范围，非额定最大行程；面板、锁定与限位机构不包含在此视图中。',
        'method': '按侧槽、滑轨截面与外壳导向槽定位；清理支撑后检查闭合及0–50 mm的抽拉范围。',
        'instructions': ['先按官方手册第3页清理内抽两侧的辅助支撑，再按第4页装入内滑轨，第7页套上外导轨并装入外壳。',
                         '0%为收回位置，100%为抽出50 mm。此视图只展示六件主体与滑轨；尚未验证完整锁定、限位、承载及实物公差。',
                         '外壳半透明以便查看滑轨。预览隐藏指定支撑表面，切口外观未模拟；打印包始终使用未改动的原始STL。'],
        'instances': [
            instance(BOX, explode=[0, 0, -50], variant={
                'id': 'side-supports-removed', 'remove_boxes': SUPPORT_BOXES, 'removed_faces': 15892}),
            instance(SLIDES, components=[
                {'region': 'negative_x', 'title': '左内滑轨', 'faces': 93455,
                 'position': [-73.8797, 8.31103516, -12.9], 'rotation': [0, 0, -90], 'explode': [0, 0, -50]},
                {'region': 'positive_x', 'title': '右内滑轨', 'faces': 93276,
                 'position': [73.8797, 8.31103516, -12.9], 'rotation': [0, 0, 90], 'explode': [0, 0, -50]},
            ]),
            instance(GUIDES, components=[
                {'region': 'negative_x', 'title': '左外导轨', 'faces': 50316,
                 'position': [-78.6797, 4.17431640625, -.15], 'rotation': [0, 0, -90], 'explode': [0, 0, 0]},
                {'region': 'positive_x', 'title': '右外导轨', 'faces': 50316,
                 'position': [78.6797, 4.17431640625, -.15], 'rotation': [0, 0, 90], 'explode': [0, 0, 0]},
            ]),
            instance(SHELL, position=[0, 18.2955, 74.1], rotation=[90, 0, 180]),
        ],
    }]
