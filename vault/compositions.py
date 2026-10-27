"""Fixed local assembly catalogs; source versions are checked per request."""
from copy import deepcopy
import json
import math
from pathlib import Path

from . import joints

DATA = Path(__file__).with_name('assembly_data')


def vector(value, size):
    return isinstance(value,list) and len(value)==size and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in value)


def valid_element(element):
    if not isinstance(element,dict) or not all(vector(element.get(k),n) for k,n in [('matrix',9),('origin',3),('explode',3)]):
        return False
    matrix=element['matrix'];rows=[matrix[i:i+3] for i in (0,3,6)]
    if any(abs(sum(a*b for a,b in zip(rows[i],rows[j]))-(1 if i==j else 0))>1e-5 for i in range(3) for j in range(3)):
        return False
    selection=element.get('selection',{})
    return (isinstance(element.get('key'),str) and isinstance(element.get('title'),str)
            and type(element.get('step')) is int and 0<=element['step']<8
            and isinstance(selection,dict) and type(selection.get('faces')) is int and 0<selection['faces']<=800000
            and (selection.get('all') is True or type(selection.get('connected')) is int and selection['connected']>=0))


def composition_profiles(catalog, parts, kind):
    if kind not in ('drawer', 'sustainer'):
        return []
    path = DATA / (kind + '.json')
    if not path.is_file():
        return []
    try:
        source = json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return []
    if not isinstance(source,dict) or source.get('version') != 1 or not source.get('ready'):
        return []
    if not isinstance(source.get('files'),dict) or not isinstance(source.get('profiles'),list):
        return []
    if not all(isinstance(d,dict) for d in source['files'].values()):
        return []
    by_name = {p['name']: p for p in parts}
    selected = []
    for name, part in by_name.items():
        definition = source['files'].get(name)
        if not isinstance(definition,dict) or not isinstance(definition.get('elements'),list) or not definition['elements'] or not all(valid_element(e) for e in definition['elements']):
            return []
        file = catalog.resolve(part['id'])
        stat = file.stat()
        if joints.digest(str(file),stat.st_size,stat.st_mtime_ns) != definition.get('sha256'):
            return []
        elements = deepcopy(definition['elements'])
        if definition.get('copies'):
            if part['copies'] > len(elements):
                return []
            elements = elements[:part['copies']]
        elif part['copies'] != 1:
            return []
        selected.append({'id':part['id'],'sha256':definition['sha256'],'elements':elements})
    required = {n for n,d in source['files'].items() if not d.get('optional')}
    if not required.issubset(by_name):
        return []
    profiles = []
    for variant in source['profiles']:
        if not isinstance(variant,dict) or not all(isinstance(variant.get(k),str) for k in ('id','title','motion','note','limits')):
            return []
        profile = {**deepcopy(variant),'mode':'composition','composition':deepcopy(selected),
                   'instances':[{'id':p['id'],'sha256':p['sha256']} for p in selected],
                   'display_count':sum(len(p['elements']) for p in selected)}
        profile['xray_ids'] = [by_name[n]['id'] for n in variant.get('xray_names',[]) if n in by_name]
        profiles.append(profile)
    return profiles
