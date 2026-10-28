"""Measure the user's local library and compile layout-reference metadata only.

Development dependency: numpy/shapely. Runtime uses the generated JSON and stdlib.
No mesh, personal path or PDF is written to the public catalog.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from shapely import Polygon

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vault.catalog import Catalog,DEFAULT_ROOT
from vault.recipes import Recipe
from scripts.verify_key_cap import triangles,section
from scripts.verify_compositions import connected

BASE=Path(__file__).resolve().parents[1]
WIDTH={'S':164.8,'M':254.,'L':329.6,'XL':418.8}
RIM={1:50.8,2:84.8,4:180.8}
RX=np.array([[1.,0,0],[0,0,1],[0,-1,0]])
DRAW=np.array([[-1.,0,0],[0,0,1],[0,1,0]])
GRID=np.diag([-1.,-1,1])@RX
YP=np.array([[0.,0,1],[0,1,0],[-1,0,0]])
YN=YP.T
RIGHT=np.diag([1.,-1,-1])@YP
I=np.eye(3)
DTYPE=np.dtype([('normal','<f4',(3,)),('points','<f4',(3,3)),('attr','<u2')])

def rz(angle):
    a=np.radians(angle);return np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1.]])

def rx(angle):
    a=np.radians(angle);return np.array([[1.,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])

def role(p):
    name=p['name'].lower()
    if 'module' in name:return 'shell' if p['kind']=='drawer' else 'body'
    if ' box ' in name:return 'box'
    if 'grid roof' in name:return 'grid_roof'
    if 'roof' in name:return 'roof'
    if name=='facade cap.stl':return 'cap'
    if '/facades/' in p['relative'].lower() or 'facade.stl' in name:return 'facade'
    return {'key (turn on supports).stl':'key','key cap.stl':'key_cap','springs.stl':'springs',
        'runner stopper.stl':'stopper','label.stl':'label','label for sustainers.stl':'label_1f','latch.stl':'latch',
        'lock holder.stl':'holder','lock inner part.stl':'inner','lock outer part 1f.stl':'outer_1f',
        'lock outer part 2-4f.stl':'outer','1 set of pins for 1 lock.stl':'pins'}.get(name,
        'slides' if 'runner slides' in name else 'guides' if 'runner guides' in name else
        'top' if 'hinge top' in name else 'lower' if 'hinge' in name else 'rods' if 'rods' in name else 'unknown')

def matrix_for(p,raw_size):
    r=p['role'];fam=p['family'];h=int(re.search(r'([124])f',p['name'],re.I)[1]) if re.search(r'([124])f',p['name'],re.I) else 1
    if r=='shell':return DRAW@(rz(-45) if abs(raw_size[0]-WIDTH[fam])>.2 else I)
    if r=='body':return RX@(rz(-42.8) if fam=='XL' else I)
    if r=='box':return I
    if r=='facade':return RX
    if r=='grid_roof':return GRID@rz(-45)
    if r=='roof':return RX@rz(-42.8)
    return I

def measure(catalog,p):
    path=catalog.resolve(p['id']);data=path.read_bytes();faces=int.from_bytes(data[80:84],'little')
    if not 0<faces<=3200000 or len(data)!=84+50*faces:raise ValueError('Invalid/oversized STL: '+p['name'])
    raw=np.frombuffer(data,dtype=DTYPE,offset=84)['points'];lo=raw.min((0,1)).astype(float);hi=raw.max((0,1)).astype(float)
    origin=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
    r=matrix_for(p,hi-lo);bmin=np.array([np.inf]*3);bmax=-bmin
    for start in range(0,len(raw),60000):
        world=(raw[start:start+60000].astype(float)-origin)@r.T;bmin=np.minimum(bmin,world.min((0,1)));bmax=np.maximum(bmax,world.max((0,1)))
    result={k:p[k] for k in ['id','name','relative','kind','family','model','role']}
    result.update(sha256=hashlib.sha256(data).hexdigest(),faces=faces,bytes=len(data),matrix=r.round(12).reshape(-1).tolist(),min=bmin.tolist(),max=bmax.tolist(),
        raw_min=(lo-origin).tolist(),raw_max=(hi-origin).tolist())
    size=bmax-bmin
    if p['role'] in ('shell','body','box','facade','grid_roof','roof'):
        tolerance=.4 if p['role']=='roof' else .2
        if abs(size[0]-(WIDTH[p['family']]-(30.6 if p['role']=='box' else 0)))>tolerance:raise ValueError('Width/orientation mismatch: '+p['name']+' '+str(size))
        depth=int(re.search('[3-7]',p['model'])[0]) if p['model'] else 3
        if p['role'] in ('shell','body') and abs(size[1]-(146.1+42*(depth-3)))>.2:raise ValueError('Depth mismatch: '+p['name']+' '+str(size))
        if p['role']=='shell':
            h=int(re.search(r'([124])f',p['name'],re.I)[1])
            if abs(size[2]-(48*h+9.01))>.05:raise ValueError('Height mismatch: '+p['name'])
    if p['role']=='roof':
        world=(raw.astype(float)-origin)@r.T
        area=np.linalg.norm(np.cross(world[:,1]-world[:,0],world[:,2]-world[:,0]),axis=1)/2
        level=world[:,:,2].mean(1)
        mask=(np.ptp(world[:,:,2],axis=1)<.03)&(level>bmin[2]+7.3)&(level<bmin[2]+7.8)
        if area[mask].sum()<500:raise ValueError('Missing roof seating plane: '+p['name'])
        result['seat_z']=float(np.average(level[mask],weights=area[mask]))
    return result

def holes(mesh,axis,level,area):
    order=[i for i in range(3) if i!=axis]+[axis]
    shape=section(mesh[:,:,order],float(level));polys=list(getattr(shape,'geoms',[shape]))
    return [Polygon(r) for p in polys for r in p.interiors if area[0]<Polygon(r).area<area[1]]

def plane_features(mesh,axis,levels,expected,area):
    for level in levels:
        try:found=holes(mesh,axis,level,area)
        except ValueError:continue
        if len(found)==expected:
            axes=[i for i in range(3) if i!=axis];points=[]
            for h in found:
                point=np.zeros(3);point[axis]=level;point[axes]=h.centroid.coords[0];points.append(point.tolist())
            return points
    raise ValueError(f'Expected {expected} holes on axis {axis}, levels {levels}')

def at(meta,*,center_x=0.,back=0.,bottom=0.):
    lo=np.array(meta['min']);hi=np.array(meta['max']);return np.array([center_x-(lo[0]+hi[0])/2,back-lo[1],bottom-lo[2]])

def source_mesh(catalog,ident):return triangles(catalog.resolve(ident))[0]

def compile_catalog(root,output):
    c=Catalog(root);configs=[];parts={}
    for m in c.models.values():
        if not m['verified'] or m['kind']=='drawer' and m['family']=='XL':continue
        for h in m['heights']:
            for variant in (['flat','dividers','sealed'] if m['kind']=='sustainer' and m['family'] in ('L','XL') else ['standard']):
                cfg={k:m[k] for k in ['kind','family','depth']};cfg.update(height=h,variant=variant)
                recipe=Recipe(c).build(cfg);configs.append((cfg,recipe))
                for p in recipe['parts']:parts[p['id']]=p
    cachefile=BASE/'tmp/all-models/compiled-measurements.json'
    cache=json.loads(cachefile.read_text(encoding='utf-8')) if cachefile.exists() else {}
    meta={}
    for n,p in enumerate(parts.values()):
        p={**p,'role':role(p)};stat=c.resolve(p['id']).stat();stamp=[stat.st_size,stat.st_mtime_ns]
        entry=cache.get(p['id'])
        meta[p['id']]=entry['meta'] if entry and entry['stamp']==stamp and (p['role']!='roof' or 'seat_z' in entry['meta']) else measure(c,p)
        cache[p['id']]={'stamp':stamp,'meta':meta[p['id']]}
        cachefile.parent.mkdir(parents=True,exist_ok=True);cachefile.write_text(json.dumps(cache),encoding='utf-8')
        print('measured',n+1,len(parts),p['name'],flush=True)
    # Measured component bounds and complete face counts are used by the browser.
    for ident,p in meta.items():
        if p['role'] not in ('springs','slides','guides','lower','top','rods','pins'):continue
        print('components',p['name'],flush=True)
        mesh=source_mesh(c,ident);groups=connected(mesh) if p['role']!='top' or p['name'].startswith('L-XL') else [np.arange(len(mesh))]
        p['components']=[]
        for k,indices in enumerate(groups):
            t=mesh[indices];lo=t.min((0,1));hi=t.max((0,1));piece={'faces':len(t),'min':lo.tolist(),'max':hi.tolist()}
            if p['role'] in ('top','lower'):
                circle=plane_features(t,2,[lo[2]+1.113,(lo[2]+hi[2])/2,hi[2]-1.113],1,(48,60))[0];piece['axis']=circle
                ax=0 if p['role']=='top' else 1
                levels=[hi[ax]-d for d in [1.113,3.113,5.113,8.113]]+[lo[ax]+d for d in [1.113,3.113,5.113,8.113]]+[(lo[ax]+hi[ax])/2]
                piece['bolts']=plane_features(t,ax,levels,4,(8,15))
            if p['role']=='rods':
                cut=section(t[:,:,[1,2,0]],(lo[0]+hi[0])/2);poly=max(getattr(cut,'geoms',[cut]),key=lambda g:g.area);b=poly.bounds
                piece['axis']=[(lo[0]+hi[0])/2,(b[0]+b[2])/2,(b[1]+b[3])/2]
                ends=[]
                for x in [lo[0]+1.113,hi[0]-1.113]:ends.append(section(t[:,:,[1,2,0]],x).area)
                if abs(ends[0]-ends[1])<2:raise ValueError('Rod head side ambiguous: '+p['name'])
                piece['head_side']=-1 if ends[0]>ends[1] else 1
            p['components'].append(piece)
        if sum(g['faces'] for g in p['components'])!=p['faces']:raise ValueError('Incomplete components')
    # Facade interfaces are measured from independent depth sections.
    for ident,p in meta.items():
        if p['role']!='facade':continue
        t=source_mesh(c,ident);h=int(re.search(r'([124])f',p['name'],re.I)[1]);p['height']=h
        if p['kind']=='drawer':
            cap=holes(t,2,7.2,(70,85));p['cap_centers']=[[float(x),float(-y)] for g in cap for x,y in [g.centroid.coords[0]]]
            expected=2 if p['family']=='S' and h==1 else 4 if p['family']=='S' or h==1 else 6
            if len(cap)!=expected:raise ValueError('Facade hole count: '+p['name'])
            key=holes(t,2,8.6,(900,1000))
            if len(key)!=1 or np.linalg.norm(np.array(key[0].centroid.coords[0])-[0,(h-1)*24])>.08:raise ValueError('Key center: '+p['name'])
        else:
            expected=4 if p['family'] in ('S','M') else 8
            points=plane_features(t,2,[1.13,4.73],expected,(10.5,10.9));pairs=[points] if expected==4 else [[v for v in points if v[0]<0],[v for v in points if v[0]>0]]
            p['locks']=[[float(np.mean([v[0] for v in pair])),float(-np.mean([v[1] for v in pair]))] for pair in pairs]
            if h==1:
                diff=section(t,7.7).difference(section(t,9.3));pieces=[g for g in getattr(diff,'geoms',[diff]) if 650<g.area<800 and 35<g.bounds[2]-g.bounds[0]<40]
                if len(pieces)!=1:raise ValueError('1F label slot: '+p['name'])
                b=pieces[0].bounds;p['label_slot']=[(b[0]+b[2])/2,-(b[1]+b[3])/2]
    # A single-lock outer part has a different 1F shape; register its bore, not its bbox.
    for ident,p in meta.items():
        if p['role'] not in ('outer','outer_1f'):continue
        t=source_mesh(c,ident);axis=plane_features(t,2,[1.113,2.113],1,(24,31))[0];p['axis']=axis
    old_draw=json.loads((BASE/'vault/assembly_data/drawer.json').read_text())['files']
    old_case=json.loads((BASE/'vault/assembly_data/sustainer.json').read_text())['files']
    aliases={p['name']:p for p in meta.values() if p['role'] in ('key','key_cap','springs','stopper','cap','label','label_1f','latch','holder','inner','outer','outer_1f','pins')}
    supportfile=BASE/'tmp/all-models/support-cleanup.json'
    supportcache=json.loads(supportfile.read_text()) if supportfile.exists() else {}
    cases={};models={};calibration=[]
    def add(nodes,p,key,r,origin,component=None,**extra):
        faces=p['faces'] if component is None else p['components'][component]['faces']
        nodes.append({'file':p['id'],'key':key,'title':p['name'],'matrix':np.array(r).round(12).reshape(-1).tolist(),'origin':np.array(origin,dtype=float).tolist(),
                      'step':0,'explode':[0,0,0],'selection':{'all':True,'faces':faces} if component is None else {'connected':component,'faces':faces},**extra})
    def centroid(piece):return (np.array(piece['min'])+piece['max'])/2
    def old_nodes(name,kind='drawer'):return (old_draw if kind=='drawer' else old_case)[name]['elements']
    for cfg,recipe in configs:
        by_role=defaultdict(list)
        for part in recipe['parts']:by_role[meta[part['id']]['role']].append(meta[part['id']])
        fam=cfg['family'];height=cfg['height'];depth=146.1+42*(cfg['depth']-3);w=WIDTH[fam];nodes=[];kind=cfg['kind']
        body=by_role['shell' if kind=='drawer' else 'body'][0];body_o=at(body);body_r=np.array(body['matrix']).reshape(3,3)
        add(nodes,body,'shell' if kind=='drawer' else 'body',body_r,body_o,scope='module')
        if kind=='drawer':
            binmeta=by_role['box'][0];add(nodes,binmeta,'box',I,at(binmeta,back=2.4,bottom=10.20904712),scope='drawer')
            # Preview-only cleanup: source-space bounds follow measured side-slot datums.
            bin_node=nodes[-1];dw=(binmeta['max'][0]-binmeta['min'][0]-134.197265625)/2;dd=42*(cfg['depth']-3)/2;regions=[]
            for b in old_draw['S3 Box 1F.stl']['elements'][0]['supports']['remove_boxes']:
                low=np.array(b['min']);high=np.array(b['max']);sgn=-1 if high[0]<0 else 1
                low[0]+=sgn*dw;high[0]+=sgn*dw;low[2]-=dd;high[2]+=dd;regions.append({'min':low.tolist(),'max':high.tolist()})
            signature=hashlib.sha256(json.dumps([binmeta['sha256'],regions]).encode()).hexdigest()
            if signature not in supportcache:
                t=source_mesh(c,binmeta['id']);viewer=t[:,:,[0,2,1]].copy();viewer[:,:,2]*=-1;removed=np.zeros(len(t),dtype=bool)
                for b in regions:removed|=((viewer>=b['min'])&(viewer<=b['max'])).all((1,2))
                if not removed.any():raise ValueError('No side support faces: '+binmeta['name'])
                supportcache[signature]=int(removed.sum());supportfile.write_text(json.dumps(supportcache))
            bin_node['supports']={'remove_boxes':regions,'removed_faces':supportcache[signature]}
            facade=by_role['facade'][0];fo=at(facade,back=depth+.1,bottom=5.20965747);fr=np.array(facade['matrix']).reshape(3,3)
            add(nodes,facade,'facade',fr,fo,scope='drawer')
            for role_name in ('key','key_cap','springs'):
                p=by_role[role_name][0]
                for i,e in enumerate(old_nodes(p['name'])):
                    shift=np.array([0,depth-146.1+74.1,10.20904712]);origin=np.array(e['origin'])+shift
                    add(nodes,p,role_name+str(i),np.array(e['matrix']).reshape(3,3),origin,e['selection'].get('connected'),scope='drawer',**({'deform':e['deform']} if 'deform'in e else {}))
            label=by_role['label'][0];label_at=np.array([w/2-26.15,depth+8.02002441,28.70904712]);add(nodes,label,'label',RX,label_at,scope='drawer')
            label_half=(np.array(label['raw_max'])-label['raw_min'])/2
            for i,(x,z) in enumerate(facade['cap_centers']):
                target=np.array([x+fo[0],depth+6.,z+fo[2]]);covered=abs(target[0]-label_at[0])<label_half[0] and abs(target[2]-label_at[2])<label_half[1]
                add(nodes,by_role['cap'][0],'cap'+str(i),RX,target,scope='drawer',label_covered=bool(covered))
            if sum(e.get('label_covered',False) for e in nodes)!=1:raise ValueError('Label must replace exactly one cap: '+facade['name'])
            for role_name in ('slides','guides'):
                p=by_role[role_name][0];ref=next(m for m in meta.values() if m['name']==('x3 Runner Slides.stl' if role_name=='slides' else 'x3 Runner Guides.stl'))
                for i,e in enumerate(old_nodes(ref['name'])):
                    r=np.array(e['matrix']).reshape(3,3);center=centroid(ref['components'][i])@r.T+e['origin']+[0,74.1,10.20904712]
                    delta=((binmeta['max'][0]-binmeta['min'][0])-134.197265625)/2 if role_name=='slides' else ((body['max'][0]-body['min'][0])-164.8017578125)/2
                    center[0]+=(-1 if i==0 else 1)*delta;center[1]+=(depth-146.1)/2
                    add(nodes,p,role_name+str(i),r,center-centroid(p['components'][i])@r.T,i,scope='drawer')
            p=by_role['stopper'][0]
            for i,e in enumerate(old_nodes(p['name'])):
                origin=np.array(e['origin'])+[(-1 if i==0 else 1)*(body['max'][0]-body['min'][0]-164.8017578125)/2,depth-146.1+74.1,10.20904712]
                add(nodes,p,'stopper'+str(i),np.array(e['matrix']).reshape(3,3),origin,scope='drawer')
            roof=by_role['grid_roof'][0];add(nodes,roof,'roof',np.array(roof['matrix']).reshape(3,3),at(roof,back=.065,bottom=(body['max'][2]-body['min'][2])-4.78916577),scope='module')
            latch=by_role['latch'][0];add(nodes,latch,'latch',I,[0,57.1+(depth-146.1)/2,.70904712],scope='module')
        else:
            h=RIM[height];roof=by_role['roof'][0];rr=np.array(roof['matrix']).reshape(3,3);ro=at(roof);ro[2]=h-roof['seat_z']
            add(nodes,roof,'roof',rr,ro,scope='module')
            facade=by_role['facade'][0];fo=at(facade,back=depth+.10012,bottom=4.8023);add(nodes,facade,'facade',RX,fo,scope='module')
            for lock,(lx,lz) in enumerate(facade['locks']):
                bolt_z=lz+fo[2];x=lx+fo[0];offset=np.array([x,depth-146.1,bolt_z-67.10667])
                for role_name in ('holder','inner','pins'):
                    p=by_role[role_name][0]
                    for i,e in enumerate(old_nodes(p['name'],'sustainer')):
                        add(nodes,p,role_name+str(lock)+'_'+str(i),np.array(e['matrix']).reshape(3,3),np.array(e['origin'])+offset,e['selection'].get('connected'),scope='module')
                p=by_role['outer_1f' if height==1 else 'outer'][0];axis=np.array(p['axis']);target=np.array([x,depth+25.40107,bolt_z-12.30147]);bbcenter=(np.array(p['raw_min'])+p['raw_max'])/2
                origin=target-YN@axis;origin[0]=x-(YN@bbcenter)[0];turn=rx(-7);origin=turn@(origin-target)+target
                add(nodes,p,'outer'+str(lock),turn@YN,origin,scope='module')
            cachekey=f'{fam}:{height}'
            if cachekey not in cases:
                if cfg['depth']!=3 or cfg['variant'] not in ('standard','flat'):raise ValueError('Calibration order')
                world=source_mesh(c,body['id'])@body_r.T+body_o
                lowerholes=plane_features(world,1,[2.513,2.113,1.713],8,(10.3,11.1));lowergroups=[[v for v in lowerholes if v[0]<0],[v for v in lowerholes if v[0]>0]]
                roofworld=source_mesh(c,roof['id'])@rr.T+ro
                topcount=4 if fam in ('S','M') else 8;roofholes=[]
                for level in [h+8.137,h+10.127,h+12.137,h+6.137]:
                    try:found=holes(roofworld,2,level,(8,15))
                    except ValueError:continue
                    found=[v for v in found if v.centroid.y<45]
                    if len(found)==topcount:roofholes=[[v.centroid.x,v.centroid.y] for v in found];break
                if len(roofholes)!=topcount:raise ValueError('Roof mount holes: '+roof['name'])
                topgroups=[roofholes] if topcount==4 else [[v for v in roofholes if v[0]<0],[v for v in roofholes if v[0]>0]]
                calibrated=[];lower_bounds=[]
                for role_name,targets in [('lower',lowergroups),('top',topgroups)]:
                    p=by_role[role_name][0]
                    if len(targets)!=len(p['components']):raise ValueError('Hinge components/targets')
                    for k,(piece,target) in enumerate(zip(p['components'],targets)):
                        target=np.array(target);best=None
                        for r in [YN,RIGHT]:
                            axis=r@piece['axis'];origin=np.array([0.,-7.5-axis[1],h-axis[2]]);bolts=np.array(piece['bolts'])@r.T
                            origin[0]=target[:,0].mean()-bolts[:,0].mean();posed=bolts+origin
                            if role_name=='lower':
                                error=max(min(np.linalg.norm(v[[0,2]]-q[[0,2]]) for q in target) for v in posed)
                                if not 2<posed[:,1].mean()<15:error+=100
                            else:error=max(min(np.linalg.norm(v[:2]-q[:2]) for q in target) for v in posed)
                            if best is None or error<best[0]:best=(error,r,origin)
                        # S 1F body has a 22.75 mm pilot-hole pair; the hinge is
                        # 23 mm. Center the rigid part and retain the .125 mm
                        # per-hole offset; never stretch the STL to remove it.
                        if best[0]>.2:raise ValueError('Hinge datum mismatch: '+p['name']+' '+str(best[0])+' target='+str(target.tolist())+' posed='+str((np.array(piece['bolts'])@best[1].T+best[2]).tolist()))
                        calibration.append({'family':fam,'height':height,'file':p['id'],'component':k,'max_bolt_axis_offset_mm':float(best[0])})
                        _,r,origin=best;calibrated.append((p['id'],role_name+str(k),r.tolist(),origin.tolist(),k))
                        if role_name=='lower':
                            corners=np.array([[x,y,z] for x in [piece['min'][0],piece['max'][0]] for y in [piece['min'][1],piece['max'][1]] for z in [piece['min'][2],piece['max'][2]]])@r.T+origin;lower_bounds.append([corners[:,0].min(),corners[:,0].max()])
                p=by_role['rods'][0]
                for k,piece in enumerate(p['components']):
                    desired=-1 if k==0 else 1;r=I if piece['head_side']==desired else rz(180);axis=r@piece['axis'];head=(r@np.array([piece['min'][0] if piece['head_side']<0 else piece['max'][0],0,0]))[0]
                    outer=min(v[0] for v in lower_bounds) if k==0 else max(v[1] for v in lower_bounds);origin=[outer+desired*7.8187-head,-7.5-axis[1],h-axis[2]]
                    calibrated.append((p['id'],'rod'+str(k),r.tolist(),origin,k))
                cases[cachekey]=calibrated
            for ident,key,r,origin,component in cases[cachekey]:add(nodes,meta[ident],key,r,origin,component,scope='module')
            label=by_role['label_1f' if height==1 else 'label'][0]
            if height==1:
                lx,lz=facade['label_slot'];center=np.array([lx+fo[0],depth+8.02,lz+fo[2]]);bcenter=(np.array(label['min'])+label['max'])/2
                # label metadata uses native XYZ; RX turns the plaque toward the front.
                rawcenter=(np.array(label['raw_min'])+label['raw_max'])/2;origin=center-RX@rawcenter
            else:origin=[w/2-26.15,depth+8.02012,41.2008+(h-84.8)]
            add(nodes,label,'label',RX,origin,scope='module')
        key=f"{kind}:{fam}:{cfg['depth']}:{height}:{cfg['variant']}"
        models[key]={'config':cfg,'elements':nodes}
        print('positioned',key,len(nodes),flush=True)
    payload={'version':1,'ready':True,'model_count':len(models),'size_height_count':len({(p['kind'],p['family'],p['depth'],p['height']) for p,_ in configs}),
             'files':meta,'models':models,'hinge_checks':calibration,'method':'Original mesh dimensions; measured facade holes and hinge axes. Layout reference, not assembly/collision certification.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=output.with_suffix('.tmp');temporary.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temporary.replace(output)
    print('CATALOG',len(models),'models',len(meta),'files',output,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default=DEFAULT_ROOT);p.add_argument('--output',type=Path,default=BASE/'vault/layout_data.json');args=p.parse_args();compile_catalog(args.root,args.output)
