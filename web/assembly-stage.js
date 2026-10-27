import * as THREE from '/assets/vendor/three.module.js';
import { OrbitControls } from '/assets/vendor/OrbitControls.js';
import {prepareElements,applyElement,elementMatrix} from '/assets/assembly-pose.js';

// Full triangles, no sampling. Source meshes remain in their own print layout.
export function readSTL(buffer) {
  const view=new DataView(buffer);
  if(buffer.byteLength<134)throw Error('STL 文件不完整。');
  const count=view.getUint32(80,true);
  if(count>800000||84+count*50!==buffer.byteLength)throw Error('STL 格式或面数超出预览范围。');
  const positions=new Float32Array(count*9), min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity];
  for(let f=0;f<count;f++)for(let v=0;v<3;v++)for(let a=0;a<3;a++){
    const value=view.getFloat32(84+f*50+12+v*12+a*4,true);
    if(!Number.isFinite(value))throw Error('STL 含无效坐标。');
    positions[f*9+v*3+a]=value;min[a]=Math.min(min[a],value);max[a]=Math.max(max[a],value);
  }
  const cx=(min[0]+max[0])/2,cy=(min[1]+max[1])/2;
  for(let i=0;i<positions.length;i+=3){const y=positions[i+1];positions[i]-=cx;positions[i+1]=positions[i+2]-min[2];positions[i+2]=cy-y;}
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  geometry.computeVertexNormals();geometry.computeBoundingSphere();geometry.computeBoundingBox();
  return {geometry,size:max.map((v,i)=>v-min[i])};
}

function copyFaces(geometry,indices){
  const positions=geometry.attributes.position.array,normals=geometry.attributes.normal.array,points=new Float32Array(indices.length*9),normal=new Float32Array(indices.length*9);
  indices.forEach((source,n)=>{points.set(positions.subarray(source,source+9),n*9);normal.set(normals.subarray(source,source+9),n*9);});
  const result=new THREE.BufferGeometry();result.setAttribute('position',new THREE.BufferAttribute(points,3));result.setAttribute('normal',new THREE.BufferAttribute(normal,3));result.computeBoundingBox();result.computeBoundingSphere();return result;
}

// Used only for exact hash-verified files. Keep the full-file origin and every
// triangle; source X separates runners, source Y separates the springs.
export function splitSpringGeometry(geometry,regions){
  const positions=geometry.attributes.position.array,axis=regions.every(r=>r.region.endsWith('_x'))?'x':'y';
  const indices=axis==='x'?{negative_x:[],positive_x:[]}:{negative_y:[],positive_y:[]};
  for(let i=0;i<positions.length;i+=9){
    const offset=axis==='x'?0:2,z=[positions[i+offset],positions[i+3+offset],positions[i+6+offset]];
    const sign=z.every(v=>v>0)?(axis==='x'?'positive':'negative'):z.every(v=>v<0)?(axis==='x'?'negative':'positive'):null;
    const region=sign?sign+'_'+axis:null;
    if(!region)throw Error('成对零件的分界不符合已核对版本，未切割或丢弃三角形。');
    indices[region].push(i);
  }
  if(regions.length!==2||new Set(regions.map(r=>r.region)).size!==2||regions.some(r=>!indices[r.region]||indices[r.region].length!==r.faces))throw Error('成对零件面数不符合已核对版本。');
  return regions.map(region=>({region:region.region,geometry:copyFaces(geometry,indices[region.region])}));
}

export function supportRemovedGeometry(geometry,description){
  const points=geometry.attributes.position.array,keep=[];
  for(let i=0;i<points.length;i+=9){
    const remove=description.remove_boxes.some(box=>[0,3,6].every(v=>[0,1,2].every(a=>points[i+v+a]>=box.min[a]&&points[i+v+a]<=box.max[a])));
    if(!remove)keep.push(i);
  }
  if(points.length/9-keep.length!==description.removed_faces)throw Error('辅助支撑区域与已核对版本不一致。');
  return copyFaces(geometry,keep);
}

function activeMeshes(part){return part.activeComposition?part.composition.elements.filter(c=>c.group.visible).map(c=>c.mesh):part.activeComponents?part.components.filter(c=>c.group.visible).flatMap(c=>c.group.children):part.activeVariant?[part.variantMesh]:part.galleryMeshes;}

function partBounds(part){
  const box=new THREE.Box3();
  for(const mesh of activeMeshes(part))box.expandByObject(mesh);
  return box;
}

export class AssemblyStage {
  constructor(host,onSelect,onError){
    this.host=host;this.onSelect=onSelect;this.parts=[];this.epoch=0;
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#e8ece5');
    this.camera=new THREE.PerspectiveCamera(38,1,.1,12000);
    this.renderer=new THREE.WebGLRenderer({antialias:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
    this.renderer.domElement.setAttribute('aria-label','真实 STL 零件分解视图，点击零件可与清单联动');
    host.prepend(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.minDistance=20;this.controls.maxDistance=6000;
    this.controls.addEventListener('change',()=>this.draw());
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x65735b,2.6));
    const light=new THREE.DirectionalLight(0xffffff,2.8);light.position.set(-500,1000,600);this.scene.add(light);
    const rearLight=new THREE.DirectionalLight(0xffffff,1.7);rearLight.position.set(500,-900,-500);this.scene.add(rearLight);
    this.ray=new THREE.Raycaster();this.pointer=new THREE.Vector2();
    this.renderer.domElement.addEventListener('pointerdown',e=>this.down=[e.clientX,e.clientY]);
    this.renderer.domElement.addEventListener('pointerup',e=>{
      if(e.button!==0||!this.down||Math.hypot(e.clientX-this.down[0],e.clientY-this.down[1])>5)return;
      const r=this.renderer.domElement.getBoundingClientRect();this.pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);
      const targets=this.parts.filter(p=>p.group.visible&&p.material.opacity>=.5).flatMap(p=>activeMeshes(p).filter(m=>m.visible));
      this.ray.setFromCamera(this.pointer,this.camera);const hit=this.ray.intersectObjects(targets,false)[0];
      if(hit)this.onSelect(hit.object.userData.id);
    });
    this.renderer.domElement.addEventListener('webglcontextlost',e=>{e.preventDefault();this.clear();onError('三维画布已暂停，请重新加载页面。文字步骤和手册仍可使用。');});
    this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(host);
    this.fit();
  }
  clear(){
    this.epoch++;this.abort?.abort();cancelAnimationFrame(this.frame);
    for(const p of this.parts){this.scene.remove(p.group);p.geometry.dispose();p.variantMesh?.geometry.dispose();p.material.dispose();p.label.remove();for(const c of p.components){c.geometry.dispose();c.label.remove();}if(p.composition){for(const g of p.composition.owned)g.dispose();for(const c of p.composition.elements)c.label.remove();}}
    this.parts=[];this.joint=null;this.draw();
  }
  async load(parts,onProgress,joint=null){
    this.clear();const epoch=this.epoch;this.abort=new AbortController();const signal=this.abort.signal;let index=0,completed=0;
    const worker=async()=>{
      while(index<parts.length){
        if(epoch!==this.epoch)return;
        const rank=index++,part=parts[rank];
        const response=await fetch(`/api/assembly-mesh/${part.id}?revision=${encodeURIComponent(part.mtime_ns)}`,{signal});
        if(!response.ok){let data;try{data=await response.json();}catch{}throw Error(data?.error||'无法读取本地模型。');}
        const buffer=await response.arrayBuffer();if(epoch!==this.epoch)return;
        if(buffer.byteLength!==part.bytes)throw Error('模型大小已变化，请重新扫描模型库。');
        const expected=joint?.instances.find(i=>i.id===part.id)?.sha256;
        if(expected){
          const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),b=>b.toString(16).padStart(2,'0')).join('');
          if(epoch!==this.epoch)return;
          if(hash!==expected)throw Error('装配零件版本已变化，不能使用已核对的定位数据。');
        }
        const {geometry,size}=readSTL(buffer);
        const regions=joint?.instances.find(i=>i.id===part.id&&i.components)?.components;
        const variant=joint?.instances.find(i=>i.id===part.id&&i.variant)?.variant;
        let pieces,variantGeometry;
        try{pieces=regions?splitSpringGeometry(geometry,regions):[];variantGeometry=variant?supportRemovedGeometry(geometry,variant):null;}catch(e){geometry.dispose();for(const piece of pieces||[])piece.geometry.dispose();throw e;}
        const group=new THREE.Group(),material=new THREE.MeshStandardMaterial({color:part.color,roughness:.66,metalness:.04,side:THREE.DoubleSide});
        for(let c=0;c<part.copies;c++){const mesh=new THREE.Mesh(geometry,material);mesh.userData.id=part.id;mesh.position.x=(c-(part.copies-1)/2)*(size[0]+12);group.add(mesh);}
        const label=document.createElement('button');label.className='assembly-label';label.type='button';label.textContent=`${rank+1} · ${part.title}`;
        label.onclick=()=>this.onSelect(part.id);this.host.append(label);
        const galleryMeshes=[...group.children];
        const variantMesh=variantGeometry?new THREE.Mesh(variantGeometry,material):null;
        if(variantMesh){variantMesh.visible=false;variantMesh.userData.id=part.id;group.add(variantMesh);}
        const components=pieces.map(piece=>{
          const child=new THREE.Group(),mesh=new THREE.Mesh(piece.geometry,material);mesh.userData.id=part.id;child.add(mesh);child.visible=false;group.add(child);
          const componentLabel=document.createElement('button');componentLabel.type='button';componentLabel.className='assembly-label';componentLabel.hidden=true;
          const description=regions.find(r=>r.region===piece.region);componentLabel.textContent=`${rank+1} · ${description.title}`;componentLabel.onclick=()=>this.onSelect(part.id);this.host.append(componentLabel);
          return {...piece,group:child,label:componentLabel};
        });
        this.parts.push({id:part.id,rank,group,geometry,material,label,size,color:part.color,copies:part.copies,galleryMeshes,components,activeComponents:false,variantMesh,activeVariant:false});this.scene.add(group);
        this.layout(this.gap??.35);onProgress(++completed,parts.length);this.fit();
        // Yield between complete files so selection and cancellation stay responsive.
        await new Promise(resolve=>setTimeout(resolve,0));
      }
    };
    try{await Promise.all([worker(),worker()]);return epoch===this.epoch;}
    catch(e){if(epoch!==this.epoch)return false;this.clear();throw e;}
  }
  layout(gap){
    gap=Math.min(1,Math.max(gap,(this.joint?.min_gap||0)/100));
    this.gap=gap;
    if(this.joint?.mode==='composition'){
      for(const p of this.parts)if(p.activeComposition)for(const c of p.composition.elements)applyElement(c,this.joint,gap,this.assemblyStep??0);
      this.draw();return;
    }
    if(this.joint){
      for(const p of this.parts){const i=this.joint.instances.find(i=>i.id===p.id);if(i){p.group.position.fromArray(i.position.map((v,a)=>v+gap*i.explode[a]));for(const c of p.components){const pose=i.components?.find(r=>r.region===c.region);if(pose)c.group.position.fromArray(pose.position.map((v,a)=>v+gap*pose.explode[a]));}}}
      this.draw();return;
    }
    // Cells are reading positions, not joint transforms. Same mm scale for all.
    for(const p of this.parts){p.group.position.x=(p.rank%4-1.5)*(230+gap*140);p.group.position.z=(Math.floor(p.rank/4)-1)*(225+gap*140);}
    this.draw();
  }
  emphasize(ids,selected,animate=true){
    cancelAnimationFrame(this.frame);const active=new Set(ids),start=performance.now();
    const from=this.parts.map(p=>p.group.position.y);
    for(const p of this.parts){const chosen=p.id===selected,now=active.has(p.id);p.material.color.set(now||chosen?p.color:'#9da69b');p.material.emissive.set(chosen?'#6e2d0f':now?'#25321b':'#000000');p.label.classList.toggle('selected',chosen);p.label.classList.toggle('active',now);}
    for(const p of this.parts)for(const c of p.components){c.label.classList.toggle('selected',p.id===selected);c.label.classList.toggle('active',p.group.visible&&p.activeComponents);}
    for(const p of this.parts)for(const c of p.composition?.elements||[]){c.label.classList.toggle('selected',p.id===selected);c.label.classList.toggle('active',active.has(p.id));}
    if(this.joint){for(const p of this.parts){if(p.group.visible){p.material.color.set(p.color);p.label.classList.add('active');}}this.layout(this.gap);return;}
    const duration=animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches?320:0;
    const tick=time=>{const t=duration?Math.min((time-start)/duration,1):1;this.parts.forEach((p,i)=>p.group.position.y=THREE.MathUtils.lerp(from[i],active.has(p.id)?22:0,t*t*(3-2*t)));this.draw();if(t<1)this.frame=requestAnimationFrame(tick);};tick(start);
  }
  fit(id,includeMotion=false){
    const box=new THREE.Box3();this.parts.filter(p=>p.group.visible&&(!id||p.id===id)).forEach(p=>{
      const bounds=partBounds(p);box.union(bounds);
      if(includeMotion&&p.activeComposition){for(const c of p.composition.elements){if(!c.group.visible)continue;for(const gap of [0,.5,1]){const matrix=p.group.matrixWorld.clone().multiply(elementMatrix(c.description,this.joint,gap,this.assemblyStep??0));box.union(c.geometry.boundingBox.clone().applyMatrix4(matrix));}}return;}
      const instance=includeMotion&&this.joint?.instances.find(i=>i.id===p.id);
      if(instance){
        const offset=new THREE.Vector3().fromArray(instance.position).sub(p.group.position);
        box.union(bounds.clone().translate(offset));
        box.union(bounds.clone().translate(offset.add(new THREE.Vector3().fromArray(instance.explode))));
      }
    });
    const center=box.isEmpty()?new THREE.Vector3():box.getCenter(new THREE.Vector3());
    const extent=box.isEmpty()?400:Math.max(...box.getSize(new THREE.Vector3()).toArray(),40);
    const view=this.joint?.motion==='sequence'?(this.joint.step_views?.[this.assemblyStep]||this.joint.view):this.joint?.view;
    const rear=view==='rear'||view==='bottom'?-1:1;
    const depth=view==='front'||view==='bottom'||view==='drawer_front'?-1:view==='back'?1:rear;
    const scale=extent*Math.max(1,1/this.camera.aspect);this.controls.target.copy(center);this.camera.position.copy(center).add(new THREE.Vector3(scale*.7,rear*scale*1.4,depth*scale*1.35));this.controls.update();this.resize();
  }
  resize(){const r=this.host.getBoundingClientRect();if(!r.width||!r.height)return;this.camera.aspect=r.width/r.height;this.camera.updateProjectionMatrix();this.renderer.setSize(r.width,r.height);this.draw();}
  draw(){
    this.renderer.render(this.scene,this.camera);const w=this.host.clientWidth,h=this.host.clientHeight;
    for(const p of this.parts){
      for(const c of p.composition?.elements||[]){
        c.label.hidden=true;
        if(p.group.visible&&p.activeComposition&&c.group.visible){const v=new THREE.Box3().setFromObject(c.group).getCenter(new THREE.Vector3()).project(this.camera),margin=c.label.offsetWidth/2+8;c.label.style.left=`${THREE.MathUtils.clamp((v.x+1)*w/2,margin,w-margin)}px`;c.label.style.top=`${(1-v.y)*h/2}px`;c.label.hidden=v.z>1||v.z< -1||Math.abs(v.x)>1||Math.abs(v.y)>1;}
      }
      for(const c of p.components){
        c.label.hidden=true;
        if(p.group.visible&&p.activeComponents&&c.group.visible){
          const v=new THREE.Box3().setFromObject(c.group).getCenter(new THREE.Vector3()).project(this.camera),margin=c.label.offsetWidth/2+8;
          c.label.style.left=`${THREE.MathUtils.clamp((v.x+1)*w/2,margin,w-margin)}px`;c.label.style.top=`${(1-v.y)*h/2}px`;c.label.hidden=v.z>1||v.z< -1||Math.abs(v.x)>1||Math.abs(v.y)>1;
        }
      }
      if(!p.group.visible||p.activeComponents||p.activeComposition){p.label.hidden=true;continue;}
      const anchor=this.joint?partBounds(p).getCenter(new THREE.Vector3()):new THREE.Vector3(p.group.position.x,p.group.position.y+p.size[2]+14,p.group.position.z);
      if(this.joint){const instance=this.joint.instances.find(i=>i.id===p.id);anchor.add(new THREE.Vector3().fromArray(instance.label_offset??[p.id===this.joint.instances[0].id?-30:30,0,0]));}
      const v=anchor.project(this.camera);let left=(v.x+1)*w/2;
      if(this.joint){const margin=p.label.offsetWidth/2+8;left=THREE.MathUtils.clamp(left,margin,w-margin);}
      p.label.style.left=`${left}px`;p.label.style.top=`${(1-v.y)*h/2}px`;p.label.hidden=v.z>1||v.z< -1||Math.abs(v.x)>1||Math.abs(v.y)>1;
    }
    if(this.joint){
      const labels=this.parts.flatMap(p=>[p.label,...p.components.map(c=>c.label),...(p.composition?.elements||[]).map(c=>c.label)]).filter(label=>!label.hidden).sort((a,b)=>parseFloat(a.style.top)-parseFloat(b.style.top));
      const placed=[];
      for(const label of labels){
        const width=label.offsetWidth,height=label.offsetHeight,left=parseFloat(label.style.left)-width/2;let bottom=parseFloat(label.style.top);
        for(const previous of placed)if(left<previous.right+4&&left+width>previous.left-4&&bottom-height<previous.bottom+4&&bottom>previous.top-4)bottom=previous.bottom+height+4;
        bottom=Math.min(h-4,Math.max(height+4,bottom));label.style.top=`${bottom}px`;placed.push({left,right:left+width,top:bottom-height,bottom});
      }
    }
    if(this.labelsVisible===false)for(const p of this.parts)for(const label of [p.label,...p.components.map(c=>c.label),...(p.composition?.elements||[]).map(c=>c.label)])label.hidden=true;
  }
  setJoint(joint){
    cancelAnimationFrame(this.frame);this.joint=joint;
    if(joint?.motion==='sequence')this.assemblyStep=0;
    for(const p of this.parts){
      const instance=joint?.instances.find(i=>i.id===p.id);p.group.visible=!joint||!!instance;
      const composition=joint?.composition?.find(i=>i.id===p.id);p.activeComposition=!!composition;
      if(composition&&!p.composition){
        const prepared=prepareElements(p,composition,copyFaces,supportRemovedGeometry);
        for(const c of prepared.elements){p.group.add(c.group);const label=document.createElement('button');label.type='button';label.className='assembly-label';label.textContent=c.description.title;label.onclick=()=>this.onSelect(p.id);this.host.append(label);c.label=label;}
        p.composition=prepared;
      }
      for(const c of p.composition?.elements||[])c.group.visible=!!composition;
      p.group.rotation.set(...(instance?.rotation?instance.rotation.map(x=>x*Math.PI/180):[0,0,0]));if(composition)p.group.position.set(0,0,0);else p.group.position.y=0;
      p.activeComponents=!!instance?.components;
      p.activeVariant=!!instance?.variant&&!!p.variantMesh;if(p.variantMesh)p.variantMesh.visible=p.activeVariant;
      if(p.material){const transparent=joint?.transparent_ids?.includes(p.id)||false;p.material.transparent=transparent;p.material.opacity=transparent?0.22:1;p.material.depthWrite=!transparent;}
      for(const mesh of p.galleryMeshes)mesh.visible=!p.activeComponents&&!p.activeVariant&&!p.activeComposition;
      for(const c of p.components){const pose=instance?.components?.find(r=>r.region===c.region);c.group.visible=!!pose;c.group.rotation.set(...(pose?pose.rotation.map(x=>x*Math.PI/180):[0,0,0]));}
    }
    this.layout(joint?1:.35);this.fit();
  }
  setAssemblyStep(step){this.assemblyStep=step;this.layout(this.gap??1);this.fit(undefined,true);}
  setLabelsVisible(on){this.labelsVisible=on;this.draw();}
  setXray(on){for(const p of this.parts){const transparent=on&&this.joint?.xray_ids?.includes(p.id);p.material.transparent=!!transparent;p.material.opacity=transparent ? 0.22 : 1;p.material.depthWrite=!transparent;}this.draw();}
}
