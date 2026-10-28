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
OPTION_DATA = Path(__file__).with_name('layout_options.json')
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
    plain = (cfg.get('interior', 'none') == 'none' and cfg.get('base', 'none') == 'none'
             and cfg.get('mount', 'none') == 'none' and not any(cfg.get(k) for k in ('wheels','top_handle','split_roof'))
             and (kind != 'drawer' or cfg.get('key', 'standard') == 'standard' and cfg.get('roof', 'grid') in ('grid','none')))
    # Preserve the two installation-checked baseline assemblies exactly.
    if (plain and cfg.get('family', 'S') == 'S' and cfg.get('depth', 3) == 3
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
    try:
        options = json.loads(OPTION_DATA.read_text(encoding='utf-8'))
        if options.get('version') != 1 or not all(isinstance(options.get(k),dict) for k in ('files','poses')):raise ValueError('invalid options')
    except (OSError,ValueError):
        options = {'files':{},'poses':{}}
    references = {**data['files'], **options['files']}
    def option_nodes(height=None):
        return [deepcopy(e) for nodes in options['poses'].get(model_key(cfg,height),{}).values() for e in nodes]
    elements = []
    if kind == 'drawer':
        elements.extend(deepcopy(e) for e in row['elements'] if e['scope'] == 'module')
        elements.extend(e for e in option_nodes() if e['scope']=='module')
        offset = 0
        for index, height in enumerate(cfg.get('drawers', [cfg.get('height', 1)])):
            inner = data['models'][model_key(cfg, height)]
            for e in [*inner['elements'],*option_nodes(height)]:
                if e['scope'] != 'drawer' or e.get('label_covered') and cfg.get('labels', True):
                    continue
                e = deepcopy(e)
                e['origin'][2] += offset
                e['key'] = f"drawer{index}_{e['key']}"
                elements.append(e)
            offset += height * 48
    else:
        elements = deepcopy(row['elements']) + option_nodes()
    # Merge whole-file print copies without confusing them with connected bodies.
    parts = {}
    colors = validate_colors(cfg.get('colors', {}))
    omitted = []
    omitted_details = []
    tools = []
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
    estimated_cache = 0
    def omit(part,reason):
        omitted.append(part['name'])
        omitted_details.append({'id':part['id'],'name':part['name'],'title':part['title'],'copies':part['copies'],'reason':reason})
    for ident, part in parts.items():
        if part['name']=='Jig.stl' or part['name'].endswith('F Wall Mount.stl'):
            tools.append({'id':ident,'name':part['name'],'title':part['title'],'copies':part['copies'],
                          'reason':'安装治具 / 定位模板，不装在成品上'})
            continue
        if ident not in references or not selected[ident]:
            omit(part,'安装定位待核对；打印清单保留')
            continue
        reference = references[ident]
        try:
            source = catalog.resolve(ident)
            header = mesh_header(source)
            if header['faces'] != reference['faces'] or digest(str(source), header['bytes'], int(header['mtime_ns'])) != reference['sha256']:
                raise ValidationError('模型版本与定位目录不符，请使用对应版本模型库。')
        except ValidationError:
            if reference['role'] in ('shell','body'):raise
            omit(part,'零件读取失败或版本不符；打印清单保留')
            continue
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
        estimate=header['faces']*(part['copies'] if 'components' in reference else 1)
        if ident in options['files'] and estimated_cache+estimate>8000000:
            omit(part,'超过真实模型缓存预算；打印清单保留')
            continue
        estimated_cache+=estimate
        composition.append({'id': ident, 'sha256': reference['sha256'], 'elements': nodes})
    shown_ids={p['id'] for p in composition}
    shown = [p for ident, p in parts.items() if ident in shown_ids]
    note = '原始 STL 与实测孔位建立的组合外观参考；未开放此型号的安装动画。'
    if omitted:
        note += '部分附件未显示，打印清单仍完整保留。'
    profile = {'id': 'layout-reference-v1', 'mode': 'composition', 'motion': 'explode',
               'composition': composition, 'display_count': sum(len(p['elements']) for p in composition)}
    return {'version': 1, 'title': recipe['title'], 'layout_ready': True, 'coverage_complete': False,
            'precision_ready': False, 'parts': shown, 'joints': [profile], 'omitted': omitted,
            'omitted_details':omitted_details,'tools':tools,
            'anchor_floor':'assembly' if any(references[p['id']]['role']=='base' for p in composition) else 'shell',
            'mesh_route': '/api/layout-mesh', 'note': note}
