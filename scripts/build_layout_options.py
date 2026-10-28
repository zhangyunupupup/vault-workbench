"""Compile measured option poses from the local licensed library (metadata only).

Development dependencies: NumPy/Shapely. Does not change source STL files.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from shapely.affinity import scale, translate

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vault.catalog import Catalog, DEFAULT_ROOT, ValidationError
from vault.recipes import Recipe
from scripts.build_layout_catalog import BASE, DTYPE, GRID, RX, WIDTH, RIM, rz, holes
from scripts.verify_key_cap import triangles, section

I=np.eye(3)


def variants(cfg):
    result=[{'base':'whole'},{'base':'split'},{'base':'whole','wheels':True}]
    if cfg['kind']=='drawer':
        result += [{'roof':r} for r in ['table','bowl','heavy','under_table']]
        result += [{'key':'hidden'},{'top_handle':True},{'rails':True},{'mount':'wall'}]
        result += [{'interior':'gridfinity','baseplate':v} for v in ['plain','one','two']]
        result += [{'interior':'dividers','divider_height':h} for h in ['20','34.5','82.5']]
    else:result += [{'split_roof':True},{'interior':'gridfinity'},{'interior':'dividers'}]
    return [{**cfg,**p} for p in result]


def category(p):
    name=p['name'].lower()
    if name=='heawyweight roof handle.stl':return 'heavy_handle'
    if name=='heawyweight roof insert.stl':return 'heavy_insert'
    if p['kind']=='drawer' and 'roof.stl' in name:return 'roof'
    if 'baseplate' in name and 'part ' not in name:return 'plate'
    if p['kind']=='mod' and re.search(r' base( whole| part [12])?\.stl$',name):return 'base'
    if p['kind']=='sustainer' and 'roof part ' in name:return 'split_roof'
    return None


def measured(catalog,p,cfg):
    role=category(p)
    if not role:return None
    source=catalog.resolve(p['id']);rawbytes=source.read_bytes()
    raw=np.frombuffer(rawbytes,dtype=DTYPE,offset=84)['points']
    lo=raw.min((0,1)).astype(float);hi=raw.max((0,1)).astype(float)
    origin=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
    fam=cfg['family'];kind=cfg['kind']
    if role=='roof':r=GRID@rz(-45)
    elif role=='split_roof':r=RX@rz(-42.8)
    elif role=='base':r=RX@(rz(-45) if fam=='L' else rz(-42.8) if fam=='XL' else I)
    elif kind=='sustainer' and fam=='XL':r=RX@rz(-42.8)
    else:r=I
    world=(raw.astype(float)-origin)@r.T
    low=world.min((0,1));high=world.max((0,1));size=high-low
    width=WIDTH[fam]-(39 if kind=='drawer' else 10) if role=='plate' else WIDTH[fam]
    if not role.startswith('heavy_') and abs(size[0]-width)>(1.5 if role=='plate' else .5):raise ValueError('Option width/orientation: '+p['name']+' '+str(size))
    result={k:p[k] for k in ('id','name','relative','kind','family','model')}
    result.update(role=role,sha256=hashlib.sha256(rawbytes).hexdigest(),faces=len(raw),bytes=len(rawbytes),
                  matrix=r.round(12).reshape(-1).tolist(),min=low.tolist(),max=high.tolist())
    if role.startswith('heavy_'):return result
    # Positive horizontal material faces establish a physical seating datum.
    normals=np.cross(world[:,1]-world[:,0],world[:,2]-world[:,0]);area=np.linalg.norm(normals,axis=1)/2
    flat=(normals[:,2]>area*1.9999)&(np.ptp(world[:,:,2],axis=1)<.04)&(area>.001)
    z=world[:,:,2].mean(1);bins=np.round(z[flat]/.05).astype(int)
    levels,index=np.unique(bins,return_inverse=True);weights=np.bincount(index,weights=area[flat])
    if not len(weights):raise ValueError('Missing seating plane: '+p['name'])
    group=index==weights.argmax();plane=float(np.average(z[flat][group],weights=area[flat][group]))
    result['deck_z']=plane
    if role=='roof':
        # The existing grid roof and all alternative roofs share the same
        # underside shoes: lowest pads, then a broad plane 4.8 mm above them.
        underside=(np.abs(normals[:,2])>area*1.9999)&(np.ptp(world[:,:,2],axis=1)<.04)&(area>.001)
        underlevels,underindex=np.unique(np.round(z[underside]/.05).astype(int),return_inverse=True)
        underweights=np.bincount(underindex,weights=area[underside])
        if not any(abs(float(v*.05)-low[2]-4.8)<.05 and w>1000 for v,w in zip(underlevels,underweights)):
            raise ValueError('Roof underside interface missing: '+p['name'])
        foot=world.reshape(-1,3);foot=foot[foot[:,2]<low[2]+.15]
        result['foot_xy']=[foot[:,:2].min(0).tolist(),foot[:,:2].max(0).tolist()]
    if role=='split_roof':result['seat_z']=plane-15
    print('measured option',p['name'],size.round(4).tolist(),flush=True)
    return result


def cylinder(t,axis,sign,mask=None):
    """Register a round groove from curved face normals; reject bevels/outliers."""
    normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);area=np.linalg.norm(normal,axis=1);normal/=np.maximum(area[:,None],1e-20)
    point=t.mean(1);axes=[i for i in range(3) if i!=axis]
    select=(abs(normal[:,axis])<.01)&(abs(normal[:,axes[0]])>.05)&(abs(normal[:,axes[1]])>.05)
    if mask is not None:select&=mask(point)
    v=point[select][:,axes];n=normal[select][:,axes];a=area[select];best=None
    for radius in np.arange(14.5,15.61,.05):
        centers=v+sign*radius*n;bins=np.round(centers/.1).astype(int);u,index=np.unique(bins,axis=0,return_inverse=True);weights=np.bincount(index,weights=a);j=weights.argmax()
        if best is None or weights[j]>best[0]:best=(weights[j],radius,u[j]*.1)
    near=np.linalg.norm(v+sign*best[1]*n-best[2],axis=1)<.3
    for _ in range(1):
        weight=np.sqrt(a[near]);matrix=np.zeros((near.sum()*2,3));matrix[::2,0]=weight;matrix[1::2,1]=weight
        matrix[::2,2]=-sign*n[near,0]*weight;matrix[1::2,2]=-sign*n[near,1]*weight
        value=np.column_stack([v[near,0]*weight,v[near,1]*weight]).reshape(-1)
        solved=np.linalg.lstsq(matrix,value,rcond=None)[0]
    # Export rounding makes normals of tiny triangles noisy. Refine against
    # actual surface vertices, retaining the full source mesh unchanged.
    points=t[select][:,:,axes].reshape(-1,2);weights=np.repeat(a/3,3)
    center=solved[:2];radius=solved[2]
    for _ in range(4):
        errors=abs(np.linalg.norm(points-center,axis=1)-radius);inside=errors<.04
        root=np.sqrt(weights[inside]);q=points[inside]
        design=np.column_stack([2*q[:,0],2*q[:,1],np.ones(len(q))])*root[:,None]
        solved=np.linalg.lstsq(design,(q*q).sum(1)*root,rcond=None)[0]
        center=solved[:2];radius=np.sqrt(solved[2]+center@center)
    errors=abs(np.linalg.norm(points-center,axis=1)-radius);inside=errors<.04
    if inside.sum()<300 or weights[inside].sum()/2<200 or not 14.9<radius<15.3:raise ValueError('Unverified cylinder datum')
    return {'center':center.tolist(),'radius':float(radius),'max_error':float(errors[inside].max()),'area':float(weights[inside].sum()/2)}


def heavy_datums(catalog,files):
    handle=next(p for p in files.values() if p['role']=='heavy_handle');insert=next(p for p in files.values() if p['role']=='heavy_insert')
    handle_mesh=triangles(catalog.resolve(handle['id']))[0];insert_mesh=triangles(catalog.resolve(insert['id']))[0]
    handle['cylinder']=cylinder(handle_mesh,1,-1);insert['cylinder']=cylinder(insert_mesh,1,1)
    for p in files.values():
        if p['role']!='roof' or 'Heawyweight' not in p['name']:continue
        t=triangles(catalog.resolve(p['id']))[0]@np.array(p['matrix']).reshape(3,3).T
        lo=np.array(p['min']);hi=np.array(p['max']);mid=(lo+hi)/2
        mask=lambda v:(abs(v[:,0])>50)&(abs(v[:,0])<110)&(abs(v[:,1]-mid[1])<25)&(v[:,2]>lo[2]+40)
        p['cylinder']=cylinder(t,0,1,mask)
        if not .1<p['cylinder']['radius']-handle['cylinder']['radius']<.3:raise ValueError('Heavy handle/groove radii mismatch')
        normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);area=np.linalg.norm(normal,axis=1)/2;level=t[:,:,0].mean(1)
        walls=[]
        for side in [-1,1]:
            select=(normal[:,0]*(-side)>area*1.9999)&(np.ptp(t[:,:,0],axis=1)<.03)&(level*side>50)&(level*side<110)&(area>.001)
            u,idx=np.unique(np.round(level[select]/.05).astype(int),return_inverse=True);weights=np.bincount(idx,weights=area[select]);j=weights.argmax()
            if weights[j]<1000:raise ValueError('Heavy insert seating wall missing')
            walls.append(float(np.average(level[select][idx==j],weights=area[select][idx==j])))
        p['insert_walls']=walls
        # Independently check the insert's offset peg against the roof hole.
        peg_shape=section(insert_mesh[:,:,[0,2,1]],insert['max'][1]-1.113)
        peg=min((g for g in getattr(peg_shape,'geoms',[peg_shape]) if 25<g.area<38),key=lambda g:abs(g.centroid.y-15))
        expected_offset=insert['cylinder']['center'][0]-peg.centroid.x
        residual=[];clearance=[]
        for side,wall in zip([-1,1],walls):
            bores=holes(t,0,wall+side*16.113,(40,55))
            if len(bores)!=1:raise ValueError('Heavy insert peg bore missing')
            target=np.array(p['cylinder']['center'])+[side*expected_offset,0]
            residual.append(float(np.linalg.norm(target-np.array(bores[0].centroid.coords[0]))))
            placed=scale(peg,xfact=-side,yfact=1,origin=(0,0))
            placed=translate(placed,xoff=p['cylinder']['center'][0]+side*insert['cylinder']['center'][0],
                             yoff=p['cylinder']['center'][1]-insert['cylinder']['center'][1])
            if not bores[0].buffer(-.03).covers(placed):raise ValueError('Heavy insert peg exceeds measured bore: '+p['name'])
            clearance.append(float(bores[0].boundary.distance(placed.boundary)))
        p['peg_residual_mm']=residual
        p['peg_section_clearance_mm']=clearance


def build(root=DEFAULT_ROOT):
    c=Catalog(root);base=json.loads((BASE/'vault/layout_data.json').read_text(encoding='utf-8'))
    parts={};examples={};configs=[]
    for row in base['models'].values():
        for cfg in variants(row['config']):
            try:recipe=Recipe(c).build(cfg)
            except ValidationError:continue
            configs.append(cfg)
            for p in recipe['parts']:
                if p['id'] not in base['files'] and category(p):parts[p['id']]=p;examples[p['id']]=cfg
    cachepath=BASE/'tmp/options/compiled.json'
    cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}
    files={}
    for ident,p in parts.items():
        stat=c.resolve(ident).stat();stamp=[stat.st_size,stat.st_mtime_ns];old=cache.get(ident)
        if old and old['stamp']==stamp:meta=old['meta']
        else:
            meta=measured(c,p,examples[ident]);cache[ident]={'stamp':stamp,'meta':meta}
            cachepath.parent.mkdir(parents=True,exist_ok=True);cachepath.write_text(json.dumps(cache),encoding='utf-8')
        meta['family']=examples[ident]['family'];meta['model']=meta['family']+str(examples[ident]['depth'])
        files[ident]=meta
    heavy_datums(c,files)
    poses={}
    for key,row in base['models'].items():
        cfg=row['config'];fam=cfg['family'];kind=cfg['kind'];depth=146.1+42*(cfg['depth']-3);height=cfg['height']
        body=next(e for e in row['elements'] if e['key'] in ('shell','body'));bodymeta=base['files'][body['file']]
        module_height=bodymeta['max'][2]-bodymeta['min'][2] if kind=='drawer' else RIM[height]
        selected={}
        for ident,p in files.items():
            if p['role'].startswith('heavy_'):continue
            if p['model']!=fam+str(cfg['depth']):continue
            if p['role'] in ('roof','split_roof','plate') and p['kind']!=kind:continue
            low=np.array(p['min']);high=np.array(p['max']);origin=np.array([-(low[0]+high[0])/2,-low[1],0.])
            scope='module'
            if p['role']=='roof':origin[1]+=.065;origin[2]=module_height-4.78916577-low[2]
            elif p['role']=='plate':
                # Floors measured independently on the inner bin and case body.
                center=depth/2+.25 if kind=='drawer' else depth/2
                origin[1]=center-(low[1]+high[1])/2
                origin[2]=(13.20904712 if kind=='drawer' else 9.8)-low[2]
                scope='drawer' if kind=='drawer' else 'module'
            elif p['role']=='base':
                if 'Part 2' in p['name']:
                    first=next(v for v in files.values() if v['name']==p['name'].replace('Part 2','Part 1'))
                    origin[1]+=first['max'][1]-first['min'][1]
                origin[2]=-p['deck_z']
            elif p['role']=='split_roof':
                if 'Part 2' in p['name']:
                    first=next(v for v in files.values() if v['name']==p['name'].replace('Part 2','Part 1'))
                    origin[1]+=first['max'][1]-first['min'][1]
                origin[2]=module_height-p['seat_z']
            else:continue
            selected[ident]=[{'file':ident,'key':'option_'+ident,'title':p['name'],'scope':scope,
                              'matrix':p['matrix'],'origin':origin.tolist(),'step':0,'explode':[0,0,0],
                              'selection':{'all':True,'faces':p['faces']}}]
        if kind=='drawer' and fam=='L':
            roof=next(p for p in files.values() if p['model']==fam+str(cfg['depth']) and p['role']=='roof' and 'Heawyweight' in p['name'])
            roof_pose=selected[roof['id']][0];target=np.array(roof['cylinder']['center'])+np.array(roof_pose['origin'])[1:]
            for p in files.values():
                if not p['role'].startswith('heavy_'):continue
                selected[p['id']]=[]
                for side in ([0] if p['role']=='heavy_handle' else [-1,1]):
                    r=rz(90 if side<=0 else -90);axis=np.array([p['cylinder']['center'][0],0,p['cylinder']['center'][1]])@r.T
                    origin=np.array([0.,target[0]-axis[1],target[1]-axis[2]])
                    if side:origin[0]=roof_pose['origin'][0]+roof['insert_walls'][0 if side<0 else 1]+(p['min'][1] if side<0 else -p['min'][1])
                    selected[p['id']].append({'file':p['id'],'key':'option_'+p['id']+str(side),'title':p['name'],'scope':'module',
                        'requires_roof':'heavy','matrix':r.round(12).reshape(-1).tolist(),'origin':origin.tolist(),'step':0,'explode':[0,0,0],
                        'selection':{'all':True,'faces':p['faces']}})
        poses[key]=selected
    data={'version':1,'files':files,'poses':poses,'configuration_checks':len(configs),
          'method':'Measured original dimensions and interface datums; layout reference only.'}
    path=BASE/'vault/layout_options.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');tmp.replace(path)
    print('OPTIONS',len(files),'files',len(poses),'models',len(configs),'checked configs',flush=True)


if __name__=='__main__':build(sys.argv[1] if len(sys.argv)>1 else DEFAULT_ROOT)
