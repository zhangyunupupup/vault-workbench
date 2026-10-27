"""Explicit assembly recipes with source evidence and file-set quantities.

`copies` always means copies of the entire STL, never disconnected objects.
"""
from .catalog import ValidationError

MANUAL = "01_Instructions Manual.pdf"
DRAWER = "02_Drawer Assembly.pdf"
CASE = "03_Sustainers Assembly.pdf"
MODS = "04_Modifications.pdf"
MOUNT = "05_Mounting Instructions.pdf"
ROOFS = {"grid": "Grid Roof", "table": "Table Roof", "bowl": "Bowl Roof",
         "under_table": "Under Table Mount Roof", "heavy": "Heawyweight Roof"}


def integer(value, title, minimum=1, maximum=100):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{title}必须是 {minimum}–{maximum} 的整数。")
    return value


class Recipe:
    def __init__(self, catalog):
        self.catalog = catalog
        self.parts = []
        self.hardware = []
        self.notes = []

    def add(self, file, copies=1, *, title=None, reason="", source="", optional=False, unit="件 / 文件"):
        integer(copies, "文件打印份数", maximum=10000)
        self.parts.append({**file.public(), "copies": copies, "title": title or file.title,
                           "reason": reason, "source": source, "optional": optional, "unit": unit})

    def named(self, name, copies=1, *, kind=None, model=None, family=None, folder=None, **kwargs):
        self.add(self.catalog.match(name, kind=kind, model=model, family=family, folder=folder), copies, **kwargs)

    def bolt(self, name, quantity, reason, source, status="按装配图 / 结构核对"):
        self.hardware.append({"name": name, "quantity": quantity, "reason": reason,
                              "source": source, "status": status})

    def drawer(self, cfg, family, model, height):
        if family == "XL":
            raise ValidationError("XL 抽屉的双锁与后板配方仍待核对。可在模型库中选择文件补打；暂不生成完整套件。")
        self.named(f"{model} Module {height}F.stl", kind="drawer", model=model,
                   title="抽屉外壳", reason="所选外壳尺寸", source=f"{MANUAL} 第11、14页")
        drawer_heights = cfg.get("drawers", [height])
        if not isinstance(drawer_heights, list) or not drawer_heights:
            raise ValidationError("至少选择一个内抽。")
        if any(type(h) is not int or h not in (1, 2, 4) for h in drawer_heights) or sum(drawer_heights) != height:
            raise ValidationError("内抽高度之和必须等于外壳高度；仅支持 1F、2F、4F 内抽。")
        key = cfg.get("key", "standard")
        if key not in ("standard", "hidden"):
            raise ValidationError("未知的旋钮类型。")
        rails = cfg.get("rails", False) or len(drawer_heights) > 1
        for inner_height in drawer_heights:
            self.named(f"{model} Box {inner_height}F.stl", kind="drawer", model=model,
                       title=f"{inner_height}F 内抽盒", reason="每个内抽 1 份", source=f"{DRAWER} 第3–8页")
            self.named(f"{family}{inner_height}F (Turn On Supports).stl", kind="drawer", family=family,
                       title=f"{inner_height}F 前面板", reason="与内抽高度匹配；开启支撑", source=f"{DRAWER} 第1、6页")
            if key == "hidden":
                self.named("Hidden Key (Turn On Supports).stl", kind="drawer", title="隐藏式旋钮主体",
                           reason="每个内抽一套", source=f"{MANUAL} 第15页；替代普通旋钮")
                self.named("Hidden Key Part 2 (Turn on Supports).stl", kind="drawer",
                           reason="隐藏式旋钮配套第二件", source=f"{MANUAL} 第15页")
            else:
                self.named("Key (Turn On Supports).stl", kind="drawer", reason="每个内抽 1 个旋钮", source=f"{DRAWER} 第1页")
                self.named("Key Cap.stl", kind="drawer", reason="旋钮配套盖", source=f"{DRAWER} 第1页")
            self.named("Springs.stl", kind="drawer", reason="文件内已有左右弹簧，整份打印 1 次",
                       source=f"{DRAWER} 第2页；STL 连通体核对为2件", unit="对 / 文件")
            label_covers_hole = family == 'S' and inner_height == 1 and cfg.get('labels', True)
            self.named("Facade Cap.stl", 1 if label_covers_hole else 2, kind="drawer",
                       reason="S1F 标签替代一侧孔盖，另一侧 1 个孔盖" if label_covers_hole else "面板左右各 1 个孔盖",
                       source=f"{DRAWER} 第6页；S1F 标签槽与孔盖互斥几何核对" if label_covers_hole else f"{DRAWER} 第6页")
            depth = model[-1]
            self.named(f"x{depth} Runner Slides.stl", kind="drawer", reason="文件内包含左右内滑轨",
                       source=f"{DRAWER} 第4页；STL 连通体核对为2件", unit="对 / 文件")
            self.named(f"x{depth} Runner Guides.stl", kind="drawer", reason="文件内包含左右外导轨",
                       source=f"{DRAWER} 第7页；STL 连通体核对为2件", unit="对 / 文件")
            self.named("Runner Stopper.stl", 2, kind="drawer", reason="左右各一个限位块", source=f"{DRAWER} 第8页")
            if rails:
                self.named(f"{family} Rails.stl", kind="drawer", reason="多内抽时加入；普通单内抽可选加强锁定",
                           source=f"{DRAWER} 第4页；STL 内含上下2条", optional=len(drawer_heights) == 1, unit="组 / 文件")
            if cfg.get("labels", True):
                self.named("Label.stl", kind="drawer", optional=True, reason="每个面板一个，可在切片器添加文字", source=f"{DRAWER} 第5–6页")
            self.drawer_interior(cfg, family, model, inner_height)
            s1f = family == 'S' and inner_height == 1
            self.bolt("M4 × 14 mm 螺栓", 2 if s1f else 4 if inner_height == 1 else 6, "前面板固定",
                      f"{DRAWER} 第6页；S1F 面板及内抽两孔定位核对" if s1f else f"{MANUAL} 第18页；第3页总表有差异",
                      "数量按两孔核对；安装前复核打印孔径及螺栓长度" if s1f else "按细分图；打印前核对实际孔数")
        roof = cfg.get("roof", "grid")
        if roof != "none":
            if roof not in ROOFS:
                raise ValidationError("未知的顶盖。")
            self.named(f"{model} {ROOFS[roof]}.stl", kind="drawer", model=model,
                       reason="顶盖只选一种；叠放中间层可不选", source=f"{MANUAL} 第10页", optional=True)
            if roof == "heavy":
                self.named("Heawyweight Roof Handle.stl", kind="drawer",
                           reason="承重顶盖中央握把，整份打印 1 次",
                           source=f"{MANUAL} 第10页；Universal 专用附件与顶盖结构核对")
                self.named("Heawyweight Roof Insert.stl", 2, kind="drawer",
                           reason="承重顶盖握把两端各 1 个插片；文件只有单件",
                           source="承重顶盖两端安装位与单件 Insert STL 结构核对")
        if cfg.get("top_handle", False):
            if roof != "grid":
                raise ValidationError("顶部提手仅与网格顶盖一起加入。")
            self.named("Top Handle (Turn On Supports).stl", kind="drawer", optional=True,
                       reason="顶盖提手；开启支撑", source=f"{MANUAL} 第11、18页")
            self.bolt("M6 × 50 mm 螺栓", 2, "顶部提手", f"{MANUAL} 第3、18页")
        latches = integer(cfg.get("latches", 1), "堆叠连接扣数量", minimum=0, maximum=4)
        if roof == "under_table" and latches < 1:
            raise ValidationError("桌下安装至少需要 1 个堆叠连接扣，用于锁定外壳与安装顶盖。")
        if latches:
            self.named("Latch.stl", latches, kind="drawer", optional=True,
                       reason="所需堆叠连接扣数量", source=f"{DRAWER} 第8页")

    def drawer_interior(self, cfg, family, model, height):
        interior = cfg.get("interior", "none")
        if interior == "none":
            return
        if interior == "gridfinity":
            style = cfg.get("baseplate", "plain")
            names = {"plain": f"{model} Baseplate.stl", "one": f"{model} Baseplate_With 1 Handle.stl",
                     "two": f"{model} Baseplate_With 2 Handles.stl"}
            if style not in names:
                raise ValidationError("未知底板类型。")
            self.named(names[style], kind="drawer", model=model, optional=True,
                       reason="内部 Gridfinity 底板", source=f"{MANUAL} 第9、11页")
        elif interior == "dividers":
            divider_height = cfg.get("divider_height", "20")
            folders = {"20": "20MM TALL/", "34.5": "34.5MM TALL", "82.5": "82.5MM TALL"}
            if divider_height not in folders:
                raise ValidationError("未知分隔条高度。")
            if divider_height == "82.5" and height < 2:
                raise ValidationError("82.5 mm 分隔条不能用于 1F 内抽。")
            width = {"S": "10-S, x3", "M": "18-M, x5", "L": "26-L, x7"}[family]
            depth = {"3": "10-S, x3", "4": "14, x4", "5": "18-M, x5", "6": "22, x6", "7": "26-L, x7"}[model[-1]]
            for name, count_key, title in [(width, "width_dividers", "横向分隔条"), (depth, "depth_dividers", "纵向分隔条")]:
                count = integer(cfg.get(count_key, 1), title + "数量", minimum=0, maximum=20)
                if count:
                    self.named(name + ".stl", count, kind="drawer", folder=folders[divider_height], title=title,
                               optional=True, reason="按所选方向与条数加入；交叉位置在装配时选择",
                               source="Grid Dividers/01. INSTRUCTIONS 尺寸对照图")
        else:
            raise ValidationError("未知内部布局。")

    def sustainer(self, cfg, family, model, height):
        variant = cfg.get("variant", "standard" if family in ("S", "M") else "flat")
        if family in ("S", "M"):
            if variant != "standard":
                raise ValidationError("S/M 系列只有标准箱体文件。")
            body = f"{model} {height}F Module.stl"
        else:
            if variant not in ("flat", "dividers", "sealed"):
                raise ValidationError("请选择空箱、网格分隔或封闭分隔箱体。")
            body = f"{model} {height}F {variant.title()} Module.stl"
        self.named(body, kind="sustainer", model=model, title="翻盖箱箱体", reason="箱体高度与内部版本匹配", source=f"{MANUAL} 第9、12页")
        split = cfg.get("split_roof", False)
        if split:
            self.named(f"{model} Roof Part 1.stl", kind="sustainer", model=model, reason="分体顶盖第一半", source=f"{MANUAL} 第12页；文件版本核对")
            self.named(f"{model} Roof Part 2.stl", kind="sustainer", model=model, reason="分体顶盖第二半", source="模型库分体版本")
            connectors = 1 if family in ("S", "M") else 2
            self.named("Connector For Split Roof.stl", connectors, kind="sustainer", model=model,
                       reason=f"分体顶盖有 {connectors} 组连接槽，每槽 1 个连接片", source="分体顶盖 STL 接合面槽位核对：S/M 1槽，L/XL 2槽")
            self.notes.append(f"分体顶盖连接片按实际接合槽加入 {connectors} 份（结构核对）。")
        else:
            self.named(f"{model} Roof{' Whole' if int(model[-1]) >= 6 else ''}.stl", kind="sustainer", model=model,
                       reason="完整顶盖，与分体版本互斥", source=f"{CASE} 第3–4页")
        self.named(f"{family}{height}F Facade.stl", kind="sustainer", family=family,
                   title="翻盖箱前面板", reason="选择家族目录的面板版本；不混用 Universal 旧版候选", source=f"{CASE} 第2、5页")
        locks = 1 if family in ("S", "M") else 2
        for name, title, unit in [
            ("LOCK HOLDER.stl", "翻盖锁座", "件 / 文件"),
            ("LOCK INNER PART.stl", "翻盖锁内扣", "件 / 文件"),
            (f"LOCK OUTER PART {'1F' if height == 1 else '2-4F'}.stl", "翻盖锁外扣", "件 / 文件"),
            ("1 SET OF PINS FOR 1 LOCK.stl", "翻盖锁销（一整套）", "套 / 文件（4根销）"),
        ]:
            self.named(name, locks, kind="sustainer", title=title, reason=f"{locks} 套翻盖锁；锁销文件已有一整套",
                       source=f"{CASE} 第1–2页；家族面板锁位与 STL 连通体核对", unit=unit)
        bottom = f"{'S-M' if family in ('S', 'M') else 'L-XL' if height == 1 else 'L'} {'1F' if height == 1 else '2-4F'} Hinge.stl"
        self.named(bottom, kind="sustainer", reason="文件已有左右下铰链 2 件，只需整份打印 1 次",
                   source=f"{CASE} 第3页；STL 连通体核对为2件", unit="对 / 文件")
        top = f"{family if family in ('S', 'M') else 'L-XL'} Hinge Top.stl"
        self.named(top, kind="sustainer",
                   reason="S/M 顶盖只有一个宽上铰链座；L/XL 有两个，文件内已包含一对",
                   source=f"{CASE} 第3页；顶盖安装座与 STL 连通体核对", unit="件 / 文件" if family in ("S", "M") else "对 / 文件")
        self.named(f"{'S-M' if family in ('S', 'M') else 'L-XL'} Rods.stl", kind="sustainer",
                   reason="文件内已有 2 根铰链轴", source=f"{CASE} 第4页；STL 连通体核对为2件", unit="对 / 文件")
        if cfg.get("labels", True):
            if height == 1:
                self.named("Label for Sustainers.stl", kind="sustainer", optional=True,
                           reason="1F 面板中央标签片；不按锁扣个数相乘", source=f"{MANUAL} 第12页左下示意")
            else:
                self.named("Label.stl", kind="drawer", optional=True,
                           reason="2F/4F 面板标签；与 1F 标签版本互斥", source=f"{MANUAL} 第12页右上示意")
        interior = cfg.get("interior", "none")
        if interior == "gridfinity":
            if variant not in ("standard", "flat"):
                raise ValidationError("Gridfinity 底板请选择标准或空箱箱体，避免与分隔槽冲突。")
            if family == "XL":
                if int(model[-1]) >= 6:
                    for part in (1, 2):
                        self.named(f"{model} Part {part} Gridfinity Baseplate.stl", kind="sustainer", optional=True,
                                   reason="XL 长型号底板分为两片", source="Universal/Baseplates 实际文件")
                else:
                    self.named(f"{model} Gridfinity Baseplate.stl", kind="sustainer", optional=True, source="Universal/Baseplates 实际文件")
            else:
                self.named(f"{model} Baseplate.stl", kind="sustainer", optional=True, source=f"{MANUAL} 第9页")
        elif interior == "dividers":
            if family in ("S", "M"):
                count = integer(cfg.get("width_dividers", 1), "分隔片数量", minimum=1, maximum=20)
                self.named(f"{family}{height}F Divider.stl", count, kind="sustainer", optional=True,
                           reason="所选横向分隔片数量", source=f"{CASE} 第7页")
            else:
                if variant not in ("dividers", "sealed"):
                    raise ValidationError("分隔片需要配套分隔箱体，请选择网格分隔或封闭分隔版本。")
                for direction, count_key in [("Width", "width_dividers"), ("Depth", "depth_dividers")]:
                    count = integer(cfg.get(count_key, 1), "分隔片数量", minimum=0, maximum=20)
                    if not count:
                        continue
                    name = f"L-{height}F Width Divider.stl" if direction == "Width" else f"{model}-{height}F Depth Divider.stl"
                    if family == "XL":
                        name = "XL Width Divider.stl" if direction == "Width" else f"{model} Depth Divider.stl"
                    if variant == "sealed" and direction == "Width":
                        if family == "XL":
                            self.named("XL Seal Divider (Center).stl", count, kind="sustainer", optional=True,
                                       reason="封闭分隔中央片", source=f"{MANUAL} 第12页；实际模型版本")
                            self.named("XL Seal Divider (Sides).stl", count, kind="sustainer", optional=True,
                                       reason="封闭分隔侧片组合文件", source="实际模型版本；文件内物体数请在预览中核对")
                            continue
                        name = f"L-{height}F Seal Divider.stl"
                    self.named(name, count, kind="sustainer", optional=True, source=f"{CASE} 第7页", reason="所选分隔片条数")
        elif interior != "none":
            raise ValidationError("未知内部布局。")
        self.bolt("M4 × 10 mm 螺栓", 8, "下铰链", f"{CASE} 第3页")
        top_bolts = 4 if family in ("S", "M") else 8
        self.bolt("M4 × 14 mm 螺栓", top_bolts + 4 * locks, f"上铰链 {top_bolts} 颗 + 每套锁 4 颗", f"{CASE} 第2–3页；家族顶盖安装座与面板锁位核对")
        self.bolt("M4 × 20 mm 螺栓", 7 if family in ("L", "XL") else 4, "前面板固定",
                  f"{MANUAL} 第17页为 L 示例", "需按所选面板孔数核对；S/M 暂为参考")
        self.notes.append("五金数量来自装配图和家族结构；不同高度的面板孔数仍请对照实际模型确认。")

    def attachments(self, cfg, family, model, height, kind):
        mount = cfg.get("mount", "none")
        if mount == "wall":
            if kind != "drawer":
                raise ValidationError("墙挂套件仅针对抽屉配置开放。")
            if cfg.get("roof") == "under_table":
                raise ValidationError("请在墙挂和桌下安装之间选择一种安装方式。")
            self.named(f"{family}{height}F Wall Mount.stl", kind="mod", optional=True,
                       reason="与外壳高度对应，兼作安装定位模板", source=f"{MOUNT} 第1–5页")
            self.named("Wall Mount Second Part.stl", 2, kind="mod", optional=True,
                       reason="挂板上下两处配套连接片", source=f"{MOUNT} 第6–9页")
            self.notes.append("墙面紧固件取决于墙体。此包只整理模型，不替代安装承载核验。")
        elif mount != "none":
            raise ValidationError("未知安装方式。")
        base = cfg.get("base", "none")
        if base not in ("none", "whole", "split"):
            raise ValidationError("未知底座方式。")
        if base == "whole":
            self.named(f"{model} Base{' Whole' if int(model[-1]) >= 6 else ''}.stl", kind="mod", optional=True,
                       reason="底座，作为整个叠放组合的底部使用", source=f"{MODS} 第2页")
        elif base == "split":
            for part in (1, 2):
                self.named(f"{model} Base Part {part}.stl", kind="mod", optional=True, source="模型库分体底座版本")
            self.named("Base Connector.stl", 1 if family in ("S", "M") else 2, kind="mod", optional=True,
                       reason="S/M 一个接合槽，L/XL 两个接合槽", source="分体底座 STL 接合面槽位核对")
        if cfg.get("wheels", False):
            if base == "none":
                raise ValidationError("轮组需要同时选择底座。")
            for name in ("Bushing.stl", "Disk.stl", "Cover.stl", "Tyre (TPU).stl"):
                self.named(name, 2, kind="mod", optional=True, reason="左右轮各一件；轮胎使用 TPU", source=f"{MODS} 第2–6页")
            self.named("Jig.stl", kind="mod", optional=True, reason="两侧衬套共用一个装配治具", source=f"{MODS} 第3页")
            self.named(f"{family} Feet.stl", kind="mod", optional=True, reason="底座前脚", source=f"{MODS} 第6页")
            self.bolt("M4 × 25 mm 螺栓", 12, "每个轮盖 6 颗", f"{MODS} 第6页")
            self.bolt("M6 × 90 mm 螺栓", 2, "底脚", f"{MODS} 第6页")
            self.bolt("6205ZZ 轴承", 2, "每轮一个", f"{MODS} 第4页")
            self.bolt("SCSAW 止动环", 2, "每轮一个；尺寸详见手册", f"{MODS} 第5页", "手册尺寸有差异，采购前核对")
            rod = {"S": 248, "M": 338, "L": 414, "XL": 504}[family]
            self.bolt(f"M16 杆，长度 {rod} mm", 1, "轮轴", f"{MODS} 第2页")
            self.notes.append("移动塔还需按实际堆叠规划背梁；本次轮组不自动推断整塔背梁与拉杆。可在模型库补选。")

    def build(self, cfg):
        if not isinstance(cfg, dict):
            raise ValidationError("配置必须是对象。")
        kind = cfg.get("kind", "drawer")
        family = cfg.get("family", "S")
        depth = integer(cfg.get("depth", 3), "深度编号", minimum=3, maximum=7)
        height = integer(cfg.get("height", 1), "高度编号", maximum=4)
        count = integer(cfg.get("quantity", 1), "套数", maximum=100)
        if height not in (1, 2, 4) or family not in ("S", "M", "L", "XL", "L²", "XL²"):
            raise ValidationError("无效的型号尺寸。")
        if kind not in ("drawer", "sustainer"):
            raise ValidationError("请选择抽屉或翻盖箱。")
        model = family.replace("²", "") + str(depth) + ("²" if "²" in family else "")
        available = self.catalog.models.get(f"{kind}:{model}")
        if not available or height not in available["heights"]:
            raise ValidationError("当前模型库中没有这个尺寸组合。")
        if not available["verified"]:
            raise ValidationError("双列外壳配方待核对，请在模型库按文件补打。")
        if kind == "drawer":
            self.drawer(cfg, family, model, height)
        else:
            self.sustainer(cfg, family, model, height)
        self.attachments(cfg, family, model, height, kind)
        for p in self.parts:
            p["copies"] *= count
        for h in self.hardware:
            h["quantity"] *= count
        return {"config": cfg, "title": f"{model} · {height}F {'抽屉' if kind == 'drawer' else '翻盖箱'} × {count}",
                "parts": self.parts, "hardware": self.hardware, "notes": list(dict.fromkeys(self.notes))}


def plan(catalog, payload):
    if not isinstance(payload, dict):
        raise ValidationError("计划格式无效。")
    from .colors import validate_colors, colored, task_key
    layout = None
    if 'scene' in payload:
        from .scene import validate_scene
        layout = validate_scene(catalog, payload['scene'])
        if not layout['valid']:
            raise ValidationError('组合存在碰撞或悬空，请先修正布局再生成打印计划。')
        payload = {'configs': [i['config'] for i in layout['scene']['items']], 'manual': []}
    configs = payload.get("configs", [])
    manual = payload.get("manual", [])
    if not isinstance(configs, list) or not isinstance(manual, list) or len(configs) > 100 or len(manual) > 1000:
        raise ValidationError("计划条目过多或格式错误。")
    results = [Recipe(catalog).build(cfg) for cfg in configs]
    combined = {}
    hardware = {}
    notes = []
    for result in results:
        notes.extend(result["notes"])
        colors = validate_colors(result['config']['colors']) if 'colors' in result['config'] else None
        for part in result["parts"]:
            part = colored(part, colors)
            key = task_key(part)
            if key not in combined:
                combined[key] = {**part, "copies": 0}
            combined[key]["copies"] += part["copies"]
        for h in result["hardware"]:
            key = (h["name"], h["status"], h["reason"])
            if key not in hardware:
                hardware[key] = {**h, "quantity": 0}
            hardware[key]["quantity"] += h["quantity"]
    for item in manual:
        if not isinstance(item, dict):
            raise ValidationError("补打条目格式无效。")
        copies = integer(item.get("copies", 1), "补打份数", maximum=1000)
        entry = catalog.by_id.get(item.get("id"))
        if not entry:
            raise ValidationError("补打文件已不在索引中，请重新选择。")
        key = task_key(entry.public())
        if key not in combined:
            combined[key] = {**entry.public(), "copies": 0, "reason": "用户手动选择补打",
                                  "source": "手动选择，不代表完整装配套件", "optional": True, "unit": "整份 STL / 次"}
        combined[key]["copies"] += copies
    if manual:
        notes.append("手动补打文件按整份 STL 计算。数量与兼容性由所选补打需求决定，不自动补齐依赖。")
    parts = list(combined.values())
    for part in parts:
        catalog.resolve(part["id"])
    if layout:
        notes.extend(c['message'] for c in layout['checks'] if c['level'] == 'warning')
        notes.append(layout['note'])
    return {**({'scene': layout['scene'], 'layout_checks': layout['checks']} if layout else {}),
            "configs": configs, "manual": manual, "titles": [r["title"] for r in results],
            "parts": parts, "hardware": list(hardware.values()), "notes": list(dict.fromkeys(notes)),
            "file_count": len(parts), "copies": sum(p["copies"] for p in parts),
            "bytes": sum(p["size"] for p in parts)}
