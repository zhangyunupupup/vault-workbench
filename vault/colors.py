"""Color applies to an entire STL print task, never to inferred connected pieces."""
import re
from .catalog import ValidationError

GROUPS = ('body', 'drawer', 'facade', 'accessory')
DEFAULTS = {'body': '#8E9089', 'drawer': '#000000', 'facade': '#FFFFFF', 'accessory': '#FF6A13'}


def validate_colors(value):
    if not isinstance(value, dict) or set(value) - set(GROUPS):
        raise ValidationError('配色格式无效。')
    result = {}
    for group in GROUPS:
        color = value.get(group, DEFAULTS[group])
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValidationError('颜色必须为六位 HEX 色值。')
        result[group] = color.upper()
    return result


def color_group(part):
    name = part['name'].lower()
    if 'facade' in name or '/facades/' in part['relative'].lower():
        return 'facade'
    if 'module' in name or ('roof' in name and 'handle' not in name and 'insert' not in name):
        return 'body'
    if 'box' in name or 'divider' in name or 'baseplate' in name:
        return 'drawer'
    return 'accessory'


def colored(part, colors):
    if colors is None:
        return part
    group = color_group(part)
    # Material is still supplied by the catalog (e.g. TPU tyres), not by the palette.
    return {**part, 'color': colors[group], 'color_group': group}


def task_key(part):
    return part['id'], part['material'], part.get('color', '')
