"""Validated layout envelopes; assembly engagement is deliberately not inferred."""
import math
import re
from .catalog import ValidationError
from .colors import validate_colors
from .recipes import Recipe

MAX_ITEMS = 60
EPS = 0.05
SOURCE = '01_Instructions Manual.pdf 第8页；本地261020外壳测量；官网尺寸表（参考包络）'


def dimensions(cfg):
    family, depth, height = cfg.get('family'), cfg.get('depth'), cfg.get('height')
    if family not in ('S', 'M', 'L', 'XL') or type(depth) is not int or depth not in range(3, 8) or type(height) is not int or height not in (1, 2, 4):
        raise ValidationError('此型号尚未建立布局参考尺寸。')
    width = {'S': 164.8, 'M': 254, 'L': 329.6, 'XL': 418.8}[family]
    # Drawer local shell height exceeds the website's nominal height by 5.51 mm.
    high = (48 * height + 9.01) if cfg['kind'] == 'drawer' else {1: 71, 2: 99.5, 4: 195.5}[height]
    return [width, round(156.1 + (depth - 3) * 42, 2), high]


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 10000:
        raise ValidationError('坐标必须为 -10000 至 10000 mm 的有限数字。')
    return round(value, 2)


def validate_scene(catalog, raw):
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw.get('version') != 1 or not isinstance(raw.get('items'), list) or len(raw['items']) > MAX_ITEMS:
        raise ValidationError('方案版本或格式无效；最多60个箱体。')
    name = raw.get('name', '我的组合')
    if not isinstance(name, str) or len(name) > 80:
        raise ValidationError('方案名称最多80个字符。')
    seen, items = set(), []
    for item in raw['items']:
        if not isinstance(item, dict):
            raise ValidationError('箱体条目格式无效。')
        ident = item.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', ident) or ident in seen:
            raise ValidationError('箱体编号重复或无效。')
        seen.add(ident)
        cfg = item.get('config')
        if not isinstance(cfg, dict) or cfg.get('quantity', 1) != 1:
            raise ValidationError('每个布局箱体必须为1套；多套请复制箱体。')
        cfg = {'kind': 'drawer', 'family': 'S', 'depth': 3, 'height': 1, **cfg}
        # Re-run exact local file resolution; never accept imported file lists.
        result = Recipe(catalog).build(cfg)
        pos = item.get('position')
        if not isinstance(pos, list) or len(pos) != 3:
            raise ValidationError('位置应为 [X, Y, Z]，Z 为离地高度。')
        pos = [number(v) for v in pos]
        colors = validate_colors(item.get('colors', {}))
        items.append({'id': ident, 'config': {**cfg, 'quantity': 1, 'colors': colors},
                      'position': pos, 'colors': colors, 'size': dimensions(cfg), 'title': result['title']})
    checks = check_layout(items)
    scene = {'version': 1, 'name': name, 'items': items}
    return {'scene': scene, 'checks': checks, 'source': SOURCE,
            'valid': not any(c['level'] == 'error' for c in checks),
            'note': '参考包络用于布局；不含提手、底座、轮组和开合空间，不代表精确嵌合或承载验证。'}


def check_layout(items):
    checks = []
    def issue(item, level, message):
        checks.append({'id': item['id'], 'level': level, 'message': message})
    for i, item in enumerate(items):
        x, y, z = item['position']; w, d, h = item['size']
        if z < -EPS:
            issue(item, 'error', '箱体低于地面。')
        for other in items[:i]:
            if all(min(p + s, q + t) - max(p, q) > EPS for p, s, q, t in zip(item['position'], item['size'], other['position'], other['size'])):
                issue(item, 'error', f'与 {other["id"]} 的参考包络相交。')
                issue(other, 'error', f'与 {item["id"]} 的参考包络相交。')
        if z > EPS:
            below = [o for o in items if o['id'] != item['id'] and abs(o['position'][2] + o['size'][2] - z) <= EPS
                     and o['position'][0] <= x + EPS and o['position'][1] <= y + EPS
                     and o['position'][0] + o['size'][0] >= x + w - EPS
                     and o['position'][1] + o['size'][1] >= y + d - EPS]
            if not below:
                issue(item, 'error', '悬空或底面没有单个完整支撑面；跨两个箱体的桥接暂不支持。')
            else:
                lower = below[0]
                same = abs(lower['size'][0] - w) <= EPS and abs(lower['size'][1] - d) <= EPS
                issue(item, 'warning', '同尺寸叠放见手册第8页；嵌合高度与连接扣位置仍需实物核对。' if same else '底面可容纳，但不同尺寸的连接接口尚未核实。')
                if lower['config']['kind'] == 'sustainer':
                    issue(lower, 'warning', '上方放置了箱体，取物前需移开，当前未检查翻盖开启空间。')
                if lower['config'].get('roof', 'none') != 'none' and lower['config']['kind'] == 'drawer':
                    issue(lower, 'warning', '中间层顶盖可能影响叠放；请在配置页调整并核对。')
        cfg = item['config']
        if cfg.get('wheels') or cfg.get('base', 'none') != 'none' or cfg.get('top_handle') or cfg.get('mount', 'none') != 'none' or cfg.get('roof') in ('heavy', 'bowl', 'under_table'):
            issue(item, 'warning', '所选外部附件未计入参考包络，请额外预留安装和活动空间。')
        if not any(c['id'] == item['id'] for c in checks):
            issue(item, 'ok', '落地与参考包络检查通过。')
    # A later overlapping pair can invalidate an earlier green entry.
    return [c for c in checks if c['level'] != 'ok' or not any(d['id'] == c['id'] and d['level'] != 'ok' for d in checks)]
