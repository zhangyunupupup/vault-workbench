import * as THREE from './vendor/three.module.js';
import {prepareElements,elementMatrix} from './assembly-pose.js';
import {readSTL,copyFaces,supportRemovedGeometry} from '/assembly-stage.js';

export const DRAW_BUDGET=6000000,CACHE_BUDGET=5000000;
const clone=v=>structuredClone(v);
function sorted(value){return Array.isArray(value)?value.map(sorted):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().filter(k=>!['colors','quantity'].includes(k)).map(k=>[k,sorted(value[k])])):value;}
export const modelKey=config=>JSON.stringify(sorted(config));
const hash=async buffer=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),b=>b.toString(16).padStart(2,'0')).join('');
export function candidate(c){
  const kind=c.kind??'drawer';
  return ['drawer','sustainer'].includes(kind)&&(c.family??'S')==='S'&&(c.depth??3)===3&&(c.height??1)===(kind==='drawer'?1:2)
    &&(c.interior??'none')==='none'&&(c.base??'none')==='none'&&(c.mount??'none')==='none'
    &&!['wheels','top_handle','split_roof','rails'].some(k=>c[k])
    &&(kind==='drawer'?(c.key??'standard')==='standard'&&JSON.stringify(c.drawers??[1])==='[1]'&&['none','grid'].includes(c.roof??'grid'):(c.variant??'standard')==='standard');
}
export function instantiate(template,item){
  const root=new THREE.Group(),materials={};root.matrix.copy(template.anchor);root.matrixAutoUpdate=false;
  for(const node of template.nodes){
    const color=item.colors[node.colorGroup];
    materials[node.colorGroup]??=new THREE.MeshStandardMaterial({color,roughness:.62,metalness:.02,side:THREE.DoubleSide});
    const mesh=new THREE.Mesh(node.geometry,materials[node.colorGroup]);mesh.matrix.copy(node.matrix);mesh.matrixAutoUpdate=false;
    mesh.userData={id:item.id,sharedGeometry:true};mesh.castShadow=true;mesh.receiveShadow=true;root.add(mesh);
  }
  return root;
}
export async function loadTemplate(guide,{fetchMesh=fetch,signal}={}){
  const profile=guide.joints?.find(p=>p.mode==='composition'&&p.motion==='explode');
  if(!guide.coverage_complete||!profile)throw Error('当前配置或文件版本未建立完整定位。');
  const triangles=profile.composition.reduce((sum,p)=>sum+p.elements.filter(e=>e.accuracy!=='spare').reduce((n,e)=>n+e.selection.faces,0),0);
  if(triangles>CACHE_BUDGET)throw Error('单套模型超过真实网格预算。');
  const geometry=new Set(),nodes=[];let shell;
  try{
    for(const definition of profile.composition){
      if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
      const part=guide.parts.find(p=>p.id===definition.id);if(!part)throw Error('装配文件映射缺失。');
      const response=await fetchMesh(`/api/assembly-mesh/${encodeURIComponent(part.id)}?revision=${encodeURIComponent(part.mtime_ns)}`,{signal});
      if(!response.ok)throw Error('本地模型读取失败，请重新扫描模型库。');
      const buffer=await response.arrayBuffer();
      if(buffer.byteLength!==part.bytes||await hash(buffer)!==definition.sha256)throw Error('模型版本已变化，请重新扫描并加载真实模型。');
      if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
      const source=readSTL(buffer).geometry;geometry.add(source);
      const material=new THREE.MeshBasicMaterial();let prepared;
      try{prepared=prepareElements({...part,geometry:source,material},definition,copyFaces,supportRemovedGeometry);}finally{material.dispose();}
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
    const box=shell.geometry.boundingBox.clone().applyMatrix4(shell.matrix).applyMatrix4(anchor);
    anchor.setPosition(-box.min.x,-box.min.y,-box.min.z);
    return {nodes,anchor,triangles,geometry,dispose(){geometry.forEach(g=>g.dispose());geometry.clear();}};
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
    const keys=[...new Set(priority.filter(i=>candidate(i.config)).map(i=>modelKey(i.config)))].slice(0,2);
    // Evict templates not being used by this update before allocating new meshes.
    for(const [key,value]of this.cache)if(!keys.includes(key)){value.dispose();this.cache.delete(key);}
    const failures=new Map();let drawn=0,cached=[...this.cache.values()].reduce((n,v)=>n+v.triangles,0);
    for(const item of priority){
      if(epoch!==this.epoch)return;
      const key=modelKey(item.config);
      if(!candidate(item.config)){this.states.set(item.id,'此型号 / 选配尚未核对，显示简化外形。');continue;}
      if(!keys.includes(key)){this.states.set(item.id,'真实模型缓存预算已满，选中后优先加载。');continue;}
      if(failures.has(key)){this.states.set(item.id,failures.get(key));continue;}
      let template=this.cache.get(key);
      if(!template){
        this.states.set(item.id,'正在读取真实打印件…');this.notify();
        try{
          const guide=await this.api('/api/assembly',{config:item.config});
          if(epoch!==this.epoch)return;
          const faces=guide.parts.reduce((n,p)=>n+p.faces*p.copies,0);
          if(cached+faces>CACHE_BUDGET)throw Error('真实模型缓存预算已满，选中后优先加载。');
          template=await loadTemplate(guide,{fetchMesh:this.fetchMesh,signal});
          if(epoch!==this.epoch){template.dispose();return;}
          this.cache.set(key,template);cached+=template.triangles;
        }catch(e){if(epoch!==this.epoch)return;failures.set(key,e.message);this.states.set(item.id,e.message);continue;}
      }
      if(drawn+template.triangles>DRAW_BUDGET){this.states.set(item.id,'场景网格预算已满，选中后优先显示真实模型。');continue;}
      this.display.set(item.id,key);this.states.set(item.id,'真实STL · 已核对参考定位');drawn+=template.triangles;
    }
    if(epoch===this.epoch)this.notify();
  }
}
