"""Evidence-backed steps; deliberately no unverified assembly transforms.

Layout offsets are a frontend reading aid. They are never assembly coordinates.
"""
import struct
from .catalog import ValidationError
from .recipes import Recipe
from .colors import validate_colors, colored

MAX_BYTES = 40 * 1024 * 1024
MAX_FACES = 800000

# Every filename is matched against the current recipe, never a client path.
DRAWER_STEPS = [
    ('装入旋钮与旋钮盖', 1, ['S1F (Turn On Supports).stl', 'Key (Turn On Supports).stl', 'Key Cap.stl'],
     '按图确认旋钮方向，再压入配套盖。', []),
    ('装入左右弹簧', 2, ['Springs.stl'],
     '弹簧平面朝上。一份 STL 已包含左右两件，不要重复打印两份。', []),
    ('清理内抽辅助支撑', 3, ['S3 Box 1F.stl'],
     '按手册去除内抽侧边的手工辅助支撑，检查滑轨槽。', []),
    ('安装内滑轨', 4, ['x3 Runner Slides.stl'],
     '左右滑轨分别滑入槽内直到限位。当前标准单内抽不含可选齿条。', []),
    ('固定面板并装入标签', 6, ['S1F (Turn On Supports).stl', 'Facade Cap.stl', 'Label.stl'],
     '旋钮保持打开状态。固定面板后装孔盖和可选标签；标签文字制作见手册第 5 页。', ['前面板固定']),
    ('套上外导轨并推入外壳', 7, ['x3 Runner Guides.stl', 'S3 Module 1F.stl', 'S3 Box 1F.stl'],
     '先把左右外导轨套在内滑轨上，再将整个内抽推入外壳。', []),
    ('安装限位块与连接扣', 8, ['Runner Stopper.stl', 'Latch.stl'],
     '内抽完全推入后再装左右限位块。按手册翻转外壳装连接扣。', []),
    ('检查可选顶盖', 10, ['S3 Grid Roof.stl'],
     '网格顶盖选型参见总说明第 10 页；这一步是配件核对，不代表已验证的顶盖装配动作。', []),
]
CASE_STEPS = [
    ('组装翻盖锁', 1, ['LOCK HOLDER.stl', 'LOCK INNER PART.stl', 'LOCK OUTER PART 2-4F.stl', '1 SET OF PINS FOR 1 LOCK.stl'],
     '先用小销连接内扣与锁座，再用大销连接外扣。注意 UP 方向；锁销文件内已有四根销。', []),
    ('把锁固定在面板上', 2, ['S2F Facade.stl', 'LOCK HOLDER.stl'],
     '锁上的 UP 朝上。手册示例可能为双锁宽箱；S3 仅使用一套锁。', ['锁座固定']),
    ('安装上下铰链', 3, ['S3 Roof.stl', 'S3 2F Module.stl', 'S-M 2-4F Hinge.stl', 'S Hinge Top.stl'],
     '区分箱体与顶盖铰链。S3 上铰链一件，下铰链文件包含两件；按实际孔位核对螺栓。', ['上铰链固定', '下铰链固定']),
    ('连接顶盖和箱体', 4, ['S-M Rods.stl', 'S3 Roof.stl', 'S3 2F Module.stl'],
     '铰链对齐后从两侧穿入轴。一份轴文件已有两根。精确轴线和开盖动画尚未验证。', []),
    ('固定面板并装入标签', 5, ['S2F Facade.stl', 'Label.stl'],
     '将已装好锁的面板固定到箱体，再滑入标签。用 M4 × 20 mm，勿混用锁座的 14 mm 螺栓。', ['前面板固定']),
    ('检查内部与活动机构', 6, ['S3 2F Module.stl'],
     '核对内部辅助支撑，按需清理；当前方案无分隔片。分隔片的安装位置另见第 7 页。检查锁扣及铰链是否顺畅。', []),
]


def mesh_header(path):
    size = path.stat().st_size
    if size > MAX_BYTES or size < 134:
        raise ValidationError('装配预览文件大小超出范围，请使用模型库预览。')
    with path.open('rb') as stream:
        header = stream.read(84)
    count = struct.unpack_from('<I', header, 80)[0]
    if not 0 < count <= MAX_FACES or size != 84 + count * 50:
        raise ValidationError('装配预览仅支持预算内的完整二进制 STL。')
    return {'bytes': size, 'faces': count, 'mtime_ns': str(path.stat().st_mtime_ns)}


def assembly(catalog, payload):
    cfg = payload.get('config', {})
    if not isinstance(cfg, dict):
        raise ValidationError('装配配置必须是对象。')
    cfg = dict(cfg)
    cfg['quantity'] = 1  # This view always explains one kit, never changes print queue.
    recipe = Recipe(catalog).build(cfg)
    colors = validate_colors(payload.get('colors', cfg.get('colors', {})))
    kind = cfg.get('kind', 'drawer')
    supported = (cfg.get('family', 'S') == 'S' and cfg.get('depth', 3) == 3
                 and cfg.get('height', 1) == (1 if kind == 'drawer' else 2)
                 and cfg.get('interior', 'none') == 'none'
                 and cfg.get('base', 'none') == 'none'
                 and cfg.get('mount', 'none') == 'none'
                 and not any(cfg.get(k, False) for k in ('wheels', 'top_handle', 'split_roof', 'rails')))
    if kind == 'drawer':
        supported = supported and cfg.get('key', 'standard') == 'standard' and cfg.get('drawers', [1]) == [1] and cfg.get('roof', 'grid') in ('grid', 'none')
    else:
        supported = supported and cfg.get('variant', 'standard') == 'standard'
    doc = 2 if kind == 'drawer' else 3
    result = {'version': 1, 'title': recipe['title'].replace(' × 1', ''), 'supported': bool(supported),
              'precision_ready': False, 'doc': doc, 'hardware': recipe['hardware'],
              'note': '真实 STL 按步骤分解排布，间距只用于看清零件；不是装配坐标。成对零件保留整份文件布局。',
              'precision_reason': '尚缺经验证的局部装配基准与接合变换；精确合拢、开盖和抽拉动画暂未开放。',
              'parts': [], 'steps': []}
    if not supported:
        result['reason'] = '目前步骤演示支持 S3 1F 标准旋钮单抽屉（网格顶盖或无顶盖）和 S3 2F 标准整盖翻盖箱，均不含分隔及改装配件。请使用下方示例或查阅对应手册。'
        return result
    for p in recipe['parts']:
        result['parts'].append({**colored(p, colors), **mesh_header(catalog.resolve(p['id']))})
    definitions = DRAWER_STEPS if kind == 'drawer' else CASE_STEPS
    covered = set()
    for title, page, names, text, reasons in definitions:
        ids = [p['id'] for p in result['parts'] if p['name'] in names]
        if not ids:
            continue
        covered.update(ids)
        result['steps'].append({'title': title, 'page': page, 'doc': 1 if kind == 'drawer' and page == 10 else doc,
                                'parts': ids, 'text': text,
                                'hardware': [h for h in recipe['hardware'] if h['reason'] in reasons]})
    if kind == 'sustainer':
        # The print recipe combines M4x14 totals; show its two uses separately
        # without changing that total or multiplying by the wide manual example.
        common = {'name': 'M4 × 14 mm 螺栓', 'quantity': 4,
                  'source': '03_Sustainers Assembly.pdf 第2–3页；S 家族结构核对',
                  'status': '安装前按实际孔位核对'}
        result['steps'][1]['hardware'] = [{**common, 'reason': 'S3 单锁锁座'}]
        result['steps'][2]['hardware'] = [{**common, 'reason': 'S3 上铰链'},
                                        *[h for h in recipe['hardware'] if h['reason'] == '下铰链']]
    if covered != {p['id'] for p in result['parts']}:
        raise ValidationError('该配置含有未建立步骤映射的零件，请使用模型库和官方手册。')
    if sum(p['faces'] * p['copies'] for p in result['parts']) > 3000000:
        raise ValidationError('当前套件超出三维预览预算，请减少可选连接扣。')
    return result
