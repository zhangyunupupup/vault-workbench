import * as THREE from './vendor/three.module.js';
import {prepareElements,elementMatrix} from './assembly-pose.js';
import {readSTL,copyFaces,supportRemovedGeometry} from '/assembly-stage.js';
import {indexedGeometry} from './layout-mesh-loader.js';

export const DRAW_BUDGET=20000000,CACHE_BUDGET=12000000;
const clone=v=>structuredClone(v);
function sorted(value){return Array.isArray(value)?value.map(sorted):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().filter(k=>!['colors','quantity'].includes(k)).map(k=>[k,sorted(value[k])])):value;}
export const modelKey=config=>JSON.stringify(sorted(config));
export function transformedBounds(geometry,matrix){
  const bounds=new THREE.Box3(),point=new THREE.Vector3(),positions=geometry.attributes.position;
  for(let i=0;i<positions.count;i++)bounds.expandByPoint(point.fromBufferAttribute(positions,i).applyMatrix4(matrix));
  return bounds;
}
const hash=async buffer=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),b=>b.toString(16).padStart(2,'0')).join('');
export function candidate(c){
  const kind=c.kind??'drawer',family=c.family??'S',height=c.height??1,drawers=c.drawers??[height];
  return ['drawer','sustainer'].includes(kind)&&['S','M','L','XL'].includes(family)&&[3,4,5,6,7].includes(c.depth??3)&&[1,2,4].includes(height)
    &&(kind==='drawer'?family!=='XL'&&Array.isArray(drawers)&&drawers.length>0&&drawers.every(h=>[1,2,4].includes(h))&&drawers.reduce((a,b)=>a+b,0)===height
      :(['S','M'].includes(family)?(c.variant??'standard')==='standard':(family!=='XL'||height===1)&&['flat','dividers','sealed'].includes(c.variant??'flat')));
}
export function instantiate(template,item){
  const root=new THREE.Group(),materials={};root.matrix.copy(template.anchor);root.matrixAutoUpdate=false;
  root.userData.layoutBounds=template.bounds;
  for(const node of template.nodes){
    const color=item.colors[node.colorGroup];
    materials[node.colorGroup]??=new THREE.MeshStandardMaterial({color,roughness:.62,metalness:.02,side:THREE.DoubleSide,flatShading:true});
    const mesh=new THREE.Mesh(node.geometry,materials[node.colorGroup]);mesh.matrix.copy(node.matrix);mesh.matrixAutoUpdate=false;
    mesh.userData={id:item.id,sharedGeometry:true};mesh.castShadow=true;mesh.receiveShadow=true;root.add(mesh);
  }
  return root;
}
export async function loadTemplate(guide,{fetchMesh=fetch,signal}={}){
  const profile=guide.joints?.find(p=>p.mode==='composition'&&p.motion==='explode');
  if(!(guide.coverage_complete||guide.layout_ready)||!profile)throw Error('当前配置或文件版本未建立完整定位。');
  const triangles=profile.composition.reduce((sum,p)=>sum+p.elements.filter(e=>e.accuracy!=='spare').reduce((n,e)=>n+e.selection.faces,0),0);
  if(guide.parts.reduce((sum,p)=>sum+p.faces,0)>CACHE_BUDGET||triangles>DRAW_BUDGET)throw Error('单套模型超过真实网格预算。');
  const geometry=new Set(),nodes=[];let shell;
  try{
    for(const definition of profile.composition){
      if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
      const part=guide.parts.find(p=>p.id===definition.id);if(!part)throw Error('装配文件映射缺失。');
      const response=await fetchMesh(`${guide.mesh_route||'/api/assembly-mesh'}/${encodeURIComponent(part.id)}?revision=${encodeURIComponent(part.mtime_ns)}`,{signal});
      if(!response.ok)throw Error('本地模型读取失败，请重新扫描模型库。');
      const buffer=await response.arrayBuffer();
      if(buffer.byteLength!==part.bytes||await hash(buffer)!==definition.sha256)throw Error('模型版本已变化，请重新扫描并加载真实模型。');
      if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
      const indexed=part.faces>500000&&definition.elements.every(e=>e.selection.all&&!e.deform&&JSON.stringify(e.supports)===JSON.stringify(definition.elements[0].supports));
      const source=indexed?await indexedGeometry(buffer,signal,definition.elements[0].supports):readSTL(buffer).geometry;geometry.add(source);
      const material=new THREE.MeshBasicMaterial();let prepared;
      try{
        if(indexed){
          if(source.index.count/3+source.userData.removedFaces!==part.faces||definition.elements.some(e=>e.selection.faces!==part.faces)||definition.elements.length!==part.copies)throw Error('完整模型面数或份数不一致。');
          prepared={owned:new Set(),elements:definition.elements.map(description=>({description,geometry:source}))};
        }else prepared=prepareElements({...part,geometry:source,material},definition,copyFaces,supportRemovedGeometry);
      }finally{material.dispose();}
      for(const g of prepared.owned)geometry.add(g);
      const used=new Set();
      for(const element of prepared.elements){
        if(element.description.accuracy==='spare')continue;
        const node={geometry:element.geometry,matrix:elementMatrix(element.description,profile,0),colorGroup:part.color_group,name:part.name,key:element.description.key};
        if(!['body','drawer','facade','accessory'].includes(node.colorGroup))throw Error('零件配色分组无效。');
        used.add(node.geometry);nodes.push(node);
        if(/\bModule\b/i.test(part.name))shell=node;
      }
      for(const g of [source,...prepared.owned])if(!used.has(g)&&geometry.delete(g))g.dispose();
      await new Promise(resolve=>setTimeout(resolve,0));
    }
    if(!shell)throw Error('缺少箱体定位基准。');
    // Turn the assembly around the vertical axis so its front faces layout +Z.
    // A rotation preserves handedness, lettering and left/right part geometry.
    const anchor=new THREE.Matrix4().makeRotationY(Math.PI);
    // Rotated print orientations make a transformed source AABB too large.
    // Measure installed vertices themselves before anchoring to the floor.
    const box=transformedBounds(shell.geometry,anchor.clone().multiply(shell.matrix));
    if(guide.anchor_floor==='assembly')for(const node of nodes)box.min.y=Math.min(box.min.y,transformedBounds(node.geometry,anchor.clone().multiply(node.matrix)).min.y);
    anchor.setPosition(-box.min.x,-box.min.y,-box.min.z);
    const bounds=new THREE.Box3();for(const node of nodes)bounds.union(transformedBounds(node.geometry,anchor.clone().multiply(node.matrix)));
    const cacheFaces=[...geometry].reduce((n,g)=>n+(g.index?.count??g.attributes.position.count)/3,0);
    const missing=guide.omitted_details?.map(p=>p.title)||guide.omitted||[],partial=missing.length>0;
    const note=partial?`真实箱体 · ${missing.length}项附件未显示，打印清单保留`:'真实STL · 已核对参考定位';
    return {nodes,anchor,bounds,triangles,cacheFaces,geometry,partial,note,omissions:guide.omitted_details||[],tools:guide.tools||[],dispose(){geometry.forEach(g=>g.dispose());geometry.clear();}};
  }catch(e){geometry.forEach(g=>g.dispose());throw e;}
}

export class BuilderDetails {
  constructor(api,notify,{fetchMesh=fetch}={}){this.api=api;this.notify=notify;this.fetchMesh=fetchMesh;this.cache=new Map();this.display=new Map();this.states=new Map();this.epoch=0;this.enabled=true;}
  clear(){this.epoch++;this.abort?.abort();this.signature=null;this.display.clear();this.states.clear();for(const v of this.cache.values())v.dispose();this.cache.clear();}
  object(item){const key=this.display.get(item.id),template=this.cache.get(key);return this.enabled&&template?instantiate(template,item):null;}
  sync(items,selected){
    const signature=JSON.stringify([this.enabled,selected,items.map(i=>[i.id,modelKey(i.config)])]);
    if(signature===this.signature)return this.pending;
    this.signature=signature;const epoch=++this.epoch;this.abort?.abort();this.abort=new AbortController();
    this.pending=this.update(clone(items),selected,epoch,this.abort.signal);return this.pending;
  }
  async update(items,selected,epoch,signal){
    this.display.clear();this.states.clear();
    if(!this.enabled){this.notify();return;}
    const priority=[...items].sort((a,b)=>Number(b.id===selected)-Number(a.id===selected));
    const keys=[...new Set(priority.filter(i=>candidate(i.config)).map(i=>modelKey(i.config)))];
    // Evict templates not being used by this update before allocating new meshes.
    for(const [key,value]of this.cache)if(!keys.includes(key)){value.dispose();this.cache.delete(key);}
    const failures=new Map();let drawn=0,cached=[...this.cache.values()].reduce((n,v)=>n+(v.cacheFaces??v.triangles),0);
    const makeRoom=faces=>{
      for(const [key,value]of this.cache){
        if(cached+faces<=CACHE_BUDGET)break;
        if([...this.display.values()].includes(key))continue;
        cached-=value.cacheFaces??value.triangles;value.dispose();this.cache.delete(key);
      }
      if(cached+faces>CACHE_BUDGET)throw Error('真实模型缓存预算已满，选中后优先加载。');
    };
    for(const item of priority){
      if(epoch!==this.epoch)return;
      const key=modelKey(item.config);
      if(!candidate(item.config)){this.states.set(item.id,'此型号 / 选配尚未核对，显示简化外形。');continue;}
      if(drawn>=DRAW_BUDGET){this.states.set(item.id,'场景网格预算已满，选中后优先显示真实模型。');continue;}
      if(failures.has(key)){this.states.set(item.id,failures.get(key));continue;}
      let template=this.cache.get(key);
      if(!template){
        this.states.set(item.id,'正在读取真实打印件…');this.notify();
        try{
          const guide=await this.api('/api/layout',{config:item.config});
          if(epoch!==this.epoch)return;
          const profile=guide.joints?.find(p=>p.mode==='composition'&&p.motion==='explode');
          const drawFaces=profile?.composition.reduce((n,p)=>n+p.elements.filter(e=>e.accuracy!=='spare').reduce((sum,e)=>sum+e.selection.faces,0),0);
          if(drawn+(drawFaces||0)>DRAW_BUDGET)throw Error('场景网格预算已满，选中后优先显示真实模型。');
          const faces=guide.parts.reduce((n,p)=>n+p.faces,0);makeRoom(faces);
          template=await loadTemplate(guide,{fetchMesh:this.fetchMesh,signal});
          if(epoch!==this.epoch){template.dispose();return;}
          try{makeRoom(template.cacheFaces);}catch(e){template.dispose();throw e;}
          this.cache.set(key,template);cached+=template.cacheFaces;
        }catch(e){if(epoch!==this.epoch)return;failures.set(key,e.message);this.states.set(item.id,e.message);continue;}
      }
      if(drawn+template.triangles>DRAW_BUDGET){this.states.set(item.id,'场景网格预算已满，选中后优先显示真实模型。');continue;}
      this.display.set(item.id,key);this.states.set(item.id,template.note);drawn+=template.triangles;
    }
    if(epoch===this.epoch)this.notify();
  }
}
