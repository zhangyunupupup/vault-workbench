"""Real-mesh layout references. Only fixed local metadata determines poses."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct

from .catalog import ValidationError
from .colors import colored, validate_colors
from .recipes import Recipe

DATA = Path(__file__).with_name('layout_data.json')
MAX_FACES = 3200000


def mesh_header(path):
    stat = path.stat()
    if not 134 <= stat.st_size <= 84 + MAX_FACES * 50:
        raise ValidationError('组合预览模型大小超出范围。')
    with path.open('rb') as stream:
        header = stream.read(84)
    faces = struct.unpack_from('<I', header, 80)[0]
    if not 0 < faces <= MAX_FACES or stat.st_size != 84 + faces * 50:
        raise ValidationError('组合预览仅支持完整二进制 STL。')
    return {'faces': faces, 'bytes': stat.st_size, 'mtime_ns': str(stat.st_mtime_ns)}


@lru_cache(maxsize=512)
def digest(path, size, mtime):
    result = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def model_key(cfg, height=None):
    kind, family = cfg.get('kind', 'drawer'), cfg.get('family', 'S')
    variant = cfg.get('variant', 'standard' if kind == 'drawer' or family in ('S', 'M') else 'flat')
    return f"{kind}:{family}:{cfg.get('depth',3)}:{height or cfg.get('height',1)}:{variant if kind == 'sustainer' else 'standard'}"


def valid_pose(e):
    try:
        r = e['matrix'];o = e['origin'];s = e['selection']
        if len(r) != 9 or len(o) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in r + o):
            return False
        rows = [r[i:i+3] for i in (0, 3, 6)]
        det = r[0]*(r[4]*r[8]-r[5]*r[7])-r[1]*(r[3]*r[8]-r[5]*r[6])+r[2]*(r[3]*r[7]-r[4]*r[6])
        return (abs(det-1) < 1e-5 and all(abs(sum(a*b for a,b in zip(rows[i],rows[j]))-(i == j)) < 1e-5 for i in range(3) for j in range(3))
                and type(s['faces']) is int and 0 < s['faces'] <= MAX_FACES)
    except (KeyError, TypeError):
        return False


def layout(catalog, payload):
    cfg = payload.get('config', {})
    if not isinstance(cfg, dict):
        raise ValidationError('组合配置必须是对象。')
    cfg = {**cfg, 'quantity': 1}
    recipe = Recipe(catalog).build(cfg)
    kind = cfg.get('kind', 'drawer')
    if (cfg.get('interior', 'none') != 'none' or cfg.get('base', 'none') != 'none'
            or cfg.get('mount', 'none') != 'none'
            or any(cfg.get(k) for k in ('wheels', 'top_handle', 'split_roof'))
            or kind == 'drawer' and (cfg.get('key', 'standard') != 'standard' or cfg.get('roof', 'grid') not in ('grid', 'none'))):
        raise ValidationError('当前附加选配尚未建立组合定位；显示简化外形。')
    # Preserve the two installation-checked baseline assemblies exactly.
    if (cfg.get('family', 'S') == 'S' and cfg.get('depth', 3) == 3
            and cfg.get('height', 1) == (1 if kind == 'drawer' else 2)
            and (kind != 'drawer' or cfg.get('drawers', [1]) == [1] and not cfg.get('rails'))):
        from .assembly import assembly
        original = assembly(catalog, {'config': cfg})
        if original.get('coverage_complete'):
            original['mesh_route'] = '/api/assembly-mesh'
            return original
    try:
        data = json.loads(DATA.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not data.get('ready'):
            raise ValueError('not ready')
        row = data['models'][model_key(cfg)]
    except (OSError, ValueError, KeyError):
        raise ValidationError('当前型号尚未建立真实模型定位。')
    elements = []
    if kind == 'drawer':
        elements.extend(deepcopy(e) for e in row['elements'] if e['scope'] == 'module')
        offset = 0
        for index, height in enumerate(cfg.get('drawers', [cfg.get('height', 1)])):
            inner = data['models'][model_key(cfg, height)]
            for e in inner['elements']:
                if e['scope'] != 'drawer' or e.get('label_covered') and cfg.get('labels', True):
                    continue
                e = deepcopy(e)
                e['origin'][2] += offset
                e['key'] = f"drawer{index}_{e['key']}"
                elements.append(e)
            offset += height * 48
    else:
        elements = deepcopy(row['elements'])
    # Merge whole-file print copies without confusing them with connected bodies.
    parts = {}
    colors = validate_colors(cfg.get('colors', {}))
    omitted = []
    for part in recipe['parts']:
        if part['id'] in parts:
            parts[part['id']]['copies'] += part['copies']
        else:
            parts[part['id']] = {**colored(part, colors)}
    selected = {ident: [] for ident in parts}
    for e in elements:
        if not valid_pose(e):
            raise ValidationError('定位目录含无效变换，请重新安装工作台。')
        if e['file'] in selected:
            selected[e.pop('file')].append(e)
    composition = []
    for ident, part in parts.items():
        if ident not in data['files']:
            if part['name'].endswith(' Rails.stl'):
                omitted.append(part['name'])
                continue
            raise ValidationError('所选零件尚未建立定位：' + part['name'])
        reference = data['files'][ident]
        source = catalog.resolve(ident)
        header = mesh_header(source)
        if header['faces'] != reference['faces'] or digest(str(source), header['bytes'], int(header['mtime_ns'])) != reference['sha256']:
            raise ValidationError('模型版本与定位目录不符，请使用对应版本模型库。')
        part.update(header)
        nodes = selected[ident]
        if reference['role'] == 'latch' and len(nodes) == 1:
            for i in range(1, part['copies']):
                spare = deepcopy(nodes[0]);spare.update(key=f'spare_latch{i}', accuracy='spare');nodes.append(spare)
        counts = Counter(e['selection'].get('connected', 'all') for e in nodes)
        expected = len(reference.get('components', [])) or 1
        if (sum(e['selection']['faces'] for e in nodes) != header['faces'] * part['copies']
                or len(counts) != expected or any(n != part['copies'] for n in counts.values())):
            raise ValidationError('真实模型实体与打印份数不一致：' + part['name'])
        composition.append({'id': ident, 'sha256': reference['sha256'], 'elements': nodes})
    shown = [p for ident, p in parts.items() if p['name'] not in omitted]
    note = '原始 STL 与实测孔位建立的组合外观参考；未开放此型号的安装动画。'
    if omitted:
        note += '齿条尚未定位，预览省略；打印清单仍完整保留。'
    profile = {'id': 'layout-reference-v1', 'mode': 'composition', 'motion': 'explode',
               'composition': composition, 'display_count': sum(len(p['elements']) for p in composition)}
    return {'version': 1, 'title': recipe['title'], 'layout_ready': True, 'coverage_complete': False,
            'precision_ready': False, 'parts': shown, 'joints': [profile], 'omitted': omitted,
            'mesh_route': '/api/layout-mesh', 'note': note}
