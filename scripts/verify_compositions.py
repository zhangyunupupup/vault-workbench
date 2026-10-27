"""Optional numpy/shapely diagnostics for the complete reference assemblies.

Reports intersections rather than treating contact or elastic preload as clearance.
Requires the user's local licensed library; never writes mesh files.
"""
import argparse
from itertools import combinations
import json
from pathlib import Path
import sys

import numpy as np
import shapely
from shapely import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.verify_key_cap import triangles, section
from vault.catalog import Catalog, DEFAULT_ROOT
from vault.assembly import assembly


def connected(mesh):
    vertices,indices=np.unique(mesh.reshape(-1,3),axis=0,return_inverse=True)
    indices=indices.reshape(-1,3);parent=np.arange(len(vertices));sizes=np.ones(len(vertices),dtype=int)
    def root(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for triangle in indices:
        a=root(triangle[0])
        for b in triangle[1:]:
            b=root(b)
            if a!=b:
                if sizes[a]<sizes[b]:a,b=b,a
                parent[b]=a;sizes[a]+=sizes[b]
    labels=np.array([root(i) for i in indices[:,0]])
    groups=[np.flatnonzero(labels==label) for label in np.unique(labels)]
    return sorted(groups,key=lambda g:tuple(mesh[g].min((0,1))))


def bodies(catalog,guide):
    profile=guide['joints'][0];parts={p['id']:p for p in guide['parts']};result=[]
    for source in profile['composition']:
        part=parts[source['id']];raw,digest=triangles(catalog.resolve(part['id']))
        assert digest==source['sha256']
        groups=connected(raw) if any('connected' in e['selection'] for e in source['elements']) else None
        assert sum(e['selection']['faces'] for e in source['elements'])==len(raw)*part['copies']
        for description in source['elements']:
            selection=description['selection'];mesh=raw[groups[selection['connected']]].copy() if 'connected' in selection else raw.copy()
            assert len(mesh)==selection['faces']
            if description.get('deform'):
                deformation=description['deform'];x=mesh[:,:,0]
                mesh[:,:,0]+=deformation['amount_mm']*np.clip((deformation['fixed_x']-x)/(deformation['fixed_x']-deformation['min_x']),0,1)
            matrix=np.array(description['matrix']).reshape(3,3);origin=np.array(description['origin'])
            world=mesh@matrix.T+origin;support_regions=[]
            for region in description.get('supports',{}).get('remove_boxes',[]):
                # Support bounds are in the original viewer coordinates X,Z,-Y.
                lo,hi=np.array(region['min']),np.array(region['max'])
                # Correct inverse viewer mapping: raw [viewer X,-viewer Z,viewer Y].
                corners=np.array([[x,-z,y] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])@matrix.T+origin
                support_regions.append((corners.min(0),corners.max(0)))
            result.append({'key':description['key'],'name':part['name'],'mesh':world,
                           'description':description,'supports':support_regions})
    return result


def cuts_for(bodies,xs):
    arrays={}
    for body in bodies:
        mesh=body['mesh'][:,:,[1,2,0]];lo,hi=mesh[:,:,2].min(),mesh[:,:,2].max();cuts=[]
        for x in xs:
            cut=section(mesh,x) if lo<x<hi else shapely.Polygon()
            for lower,upper in body['supports']:
                if lower[0]<x<upper[0]:cut=cut.difference(box(lower[1],lower[2],upper[1],upper[2]))
            cuts.append(cut)
        assert sum(not cut.is_empty for cut in cuts)>.85*(hi-lo)/(xs[1]-xs[0])
        arrays[body['key']]=np.array(cuts,dtype=object)
        print('sectioned',body['key'],file=sys.stderr,flush=True)
    return arrays


def intersections(arrays,spacing):
    result=[]
    for a,b in combinations(arrays,2):
        areas=shapely.area(shapely.intersection(arrays[a],arrays[b]));peak,volume=float(areas.max()),float(areas.sum()*spacing)
        if peak>1e-6:result.append({'a':a,'b':b,'peak_mm2':peak,'sampled_mm3':volume})
    return sorted(result,key=lambda p:-p['sampled_mm3'])


def turn(shapes,pivot,degrees):
    angle=np.radians(degrees);matrix=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    pivot=np.asarray(pivot)
    return shapely.transform(shapes,lambda xy:(xy-pivot)@matrix.T+pivot)


def motion(arrays,bodies,profile,spacing):
    worst={};samples=51
    for gap in np.linspace(0,1,samples):
        current=dict(arrays)
        for body in bodies:
            key=body['key'];description=body['description']
            if profile['motion']=='drawer' and description.get('travel'):
                dy,dz=np.array(description['travel'])[1:]*gap
                current[key]=shapely.transform(current[key],lambda xy:xy+[dy,dz])
            for rotation in profile.get('rotations',[]):
                if key in rotation['keys']:
                    assert rotation['axis']==[1,0,0]
                    fraction=np.clip((gap-rotation['start'])/(rotation['end']-rotation['start']),0,1)
                    current[key]=turn(current[key],rotation['pivot'][1:],fraction*rotation['degrees'])
        for pair in intersections(current,spacing):
            key=(pair['a'],pair['b'])
            if key not in worst or pair['sampled_mm3']>worst[key]['sampled_mm3']:worst[key]={**pair,'progress':float(gap)}
    return {'positions':samples,'pairs_with_intersection':sorted(worst.values(),key=lambda p:-p['sampled_mm3'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=DEFAULT_ROOT)
    parser.add_argument('--kind',choices=['drawer','sustainer'],required=True)
    parser.add_argument('--spacing',type=float,default=.5)
    parser.add_argument('--no-motion',action='store_true')
    args=parser.parse_args()
    if not .1<=args.spacing<=2:parser.error('spacing must be between .1 and 2 mm')
    catalog=Catalog(args.root);guide=assembly(catalog,{'config':{'kind':args.kind,'height':1 if args.kind=='drawer' else 2}})
    assert guide.get('coverage_complete'),'Complete source catalog not available for these versions'
    all_bodies=bodies(catalog,guide);excluded=[]
    # This exact roof contains 15 non-manifold edges. Do not turn failed cuts
    # into empty space or claim whole-roof collision clearance.
    checked=[]
    for body in all_bodies:
        if body['key']=='grid_roof':excluded.append({'key':body['key'],'reason':'Source has 15 non-manifold edges; closed material section not certified. Placement checked separately with contact planes and seven representative cuts.'})
        else:checked.append(body)
    # Avoid the drawer floor's exact .25 mm grid vertex planes, where rounding
    # the intersection immediately beside a vertex can collapse a segment.
    start=-82.237 if args.kind=='drawer' else -82.25
    xs=np.arange(start,82.264,args.spacing);arrays=cuts_for(checked,xs)
    result={'kind':args.kind,'source_files':len(guide['parts']),'entities':len(all_bodies),'checked_entities':len(checked),
            'section_axis':'world X','spacing_mm':args.spacing,'planes':len(xs),'excluded':excluded,
            'closed_pairs_with_intersection':intersections(arrays,args.spacing),
            'limits':'Reference geometry only; intersections are reported, not silently removed. Not continuous collision, elastic-force, tolerance, locking preload or physical validation.'}
    if not args.no_motion:
        profile=next(p for p in guide['joints'] if p.get('mode')=='composition' and p['motion']==('drawer' if args.kind=='drawer' else 'hinge'))
        result['motion']=motion(arrays,checked,profile,args.spacing)
        if args.kind=='sustainer':
            bad=turn(arrays['hinge_top'],[-6.5,84.8],55)
            areas=shapely.area(shapely.intersection(bad,arrays['rod_left']))
            control=float(areas.sum()*args.spacing);assert control>1
            result['wrong_hinge_pivot_depth_plus_1mm_control_mm3']=control
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
