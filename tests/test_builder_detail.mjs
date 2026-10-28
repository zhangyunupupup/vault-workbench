import assert from 'node:assert/strict';
process.on('uncaughtException',e=>{console.error(e.message);console.error(e.stack?.split('\n').filter(s=>!s.includes('data:text')).slice(-5).join('\n'));process.exit(1);});
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import * as THREE from '../web/assets/vendor/three.module.js';
import {BuilderStage} from '../web/assets/builder-stage.js';
import {cameraDistance,DetailedBuilderStage} from '../web/assets/builder-detail-stage.js';
const assemblySource=(await readFile('web/assembly-stage.js','utf8')).replaceAll("'/assets/vendor/three.module.js'",JSON.stringify(new URL('../web/assets/vendor/three.module.js',import.meta.url).href)).replaceAll("'/assets/vendor/OrbitControls.js'",JSON.stringify(new URL('../web/assets/vendor/OrbitControls.js',import.meta.url).href)).replaceAll("'/assets/assembly-pose.js'",JSON.stringify(new URL('../web/assets/assembly-pose.js',import.meta.url).href));
const assemblyURL='data:text/javascript;base64,'+Buffer.from(assemblySource).toString('base64');
const detailSource=(await readFile('web/assets/builder-detail.js','utf8')).replaceAll("'./vendor/three.module.js'",JSON.stringify(new URL('../web/assets/vendor/three.module.js',import.meta.url).href)).replaceAll("'./assembly-pose.js'",JSON.stringify(new URL('../web/assets/assembly-pose.js',import.meta.url).href)).replaceAll("'./layout-mesh-loader.js'",JSON.stringify(new URL('../web/assets/layout-mesh-loader.js',import.meta.url).href)).replaceAll("'/assembly-stage.js'",JSON.stringify(assemblyURL));
const {modelKey,candidate,loadTemplate,instantiate,BuilderDetails,DRAW_BUDGET,CACHE_BUDGET}=await import('data:text/javascript;base64,'+Buffer.from(detailSource).toString('base64'));
const config={kind:'drawer',family:'S',depth:3,height:1,drawers:[1]},item={id:'a',config,position:[20,30,40],size:[164.8,156.1,57.01],title:'test',colors:{body:'#88AA77',drawer:'#000000',facade:'#FFFFFF',accessory:'#FF6A13'}};
assert.equal(modelKey({...config,colors:{body:'#FFF'},quantity:10}),modelKey({...config,quantity:1}));
assert.equal(modelKey(config),modelKey(Object.fromEntries(Object.entries(config).reverse())));
assert.ok(candidate(config));assert.ok(candidate({...config,family:'M'}));assert.ok(candidate({...config,top_handle:true}));
assert.ok(candidate({...config,key:'hidden',roof:'bowl',base:'whole',wheels:true,interior:'gridfinity'}));
assert.ok(candidate({kind:'sustainer',family:'XL',depth:7,height:1,variant:'sealed'}));
assert.ok(candidate({kind:'drawer',family:'L',depth:7,height:4,drawers:[2,1,1]}));
assert.ok(!candidate({...config,family:'XL'}));assert.ok(!candidate({...config,depth:8}));
assert.ok(!candidate({kind:'sustainer',family:'XL',height:2}));
for(const aspect of [.65,1.2,2]){
  const bounds=new THREE.Box3(new THREE.Vector3(-30,0,10),new THREE.Vector3(350,200,180)),direction=new THREE.Vector3(1.5,1.3,1.8).normalize(),center=bounds.getCenter(new THREE.Vector3()),camera=new THREE.PerspectiveCamera(38,aspect,.1,20000);
  camera.position.copy(center).addScaledVector(direction,cameraDistance(bounds,aspect,38,direction));camera.lookAt(center);camera.updateMatrixWorld();
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){const p=new THREE.Vector3(x,y,z).project(camera);assert.ok(Math.abs(p.x)<1&&Math.abs(p.y)<1);}
}
const buffer=new ArrayBuffer(134),view=new DataView(buffer);view.setUint32(80,1,true);[0,0,0,2,0,0,0,3,1].forEach((v,n)=>view.setFloat32(96+n*4,v,true));
const digest=createHash('sha256').update(new Uint8Array(buffer)).digest('hex');
const guide={coverage_complete:true,parts:[{id:'module',name:'S3 Module 1F.stl',color_group:'body',copies:1,faces:1,bytes:134,mtime_ns:'123'}],joints:[{mode:'composition',motion:'explode',composition:[{id:'module',sha256:digest,elements:[{key:'shell',matrix:[1,0,0,0,1,0,0,0,1],origin:[0,0,0],explode:[0,0,0],step:0,selection:{all:true,faces:1}}]}]}]};
const fetchMesh=async()=>({ok:true,arrayBuffer:async()=>buffer.slice(0)});
const threeConfigs=new BuilderDetails(async()=>guide,()=>{},{fetchMesh});
await threeConfigs.sync([item,{...item,id:'s4',config:{...config,depth:4}},{...item,id:'m3',config:{...config,family:'M'}}],item.id);
assert.equal(threeConfigs.cache.size,3);assert.equal(threeConfigs.display.size,3,'Keep three small configurations when all fit the face budget.');threeConfigs.clear();
const template=await loadTemplate(guide,{fetchMesh});
assert.ok(Math.abs(template.anchor.determinant()-1)<1e-10,'Use a rigid turn, never mirror lettering or part handedness.');
const mesh=instantiate(template,item),box=new THREE.Box3().setFromObject(mesh);
assert.ok(box.min.toArray().every(v=>Math.abs(v)<1e-10));assert.ok(box.max.toArray().every((v,n)=>Math.abs(v-[2,1,3][n])<1e-10));
assert.equal(mesh.children[0].material.color.getHexString(),'88aa77');
const tilted=structuredClone(guide),c=Math.SQRT1_2;
tilted.joints[0].composition[0].elements[0].matrix=[c,-c,0,c,c,0,0,0,1];
const tiltedTemplate=await loadTemplate(tilted,{fetchMesh});
const tiltedObject=instantiate(tiltedTemplate,item),tiltedBounds=new THREE.Box3().setFromObject(tiltedObject,true);
assert.ok(tiltedBounds.min.toArray().every(v=>Math.abs(v)<1e-9),'Rotated print orientation anchors actual installed vertices, never the conservative source bounding box.');
assert.deepEqual(tiltedTemplate.bounds.min.toArray(),tiltedBounds.min.toArray());tiltedObject.traverse(o=>o.material?.dispose());tiltedTemplate.dispose();
const withBase=structuredClone(guide);withBase.anchor_floor='assembly';
withBase.parts.push({...withBase.parts[0],id:'base',name:'S3 Base.stl'});
const baseDefinition=structuredClone(withBase.joints[0].composition[0]);baseDefinition.id='base';baseDefinition.elements[0].key='base';baseDefinition.elements[0].origin=[0,0,-20];withBase.joints[0].composition.push(baseDefinition);
const baseTemplate=await loadTemplate(withBase,{fetchMesh}),baseObject=instantiate(baseTemplate,item);
baseObject.updateMatrixWorld(true);assert.equal(new THREE.Box3().setFromObject(baseObject.children[0],true).min.y,20);assert.equal(new THREE.Box3().setFromObject(baseObject,true).min.y,0);baseObject.traverse(o=>o.material?.dispose());
const partialGuide={...guide,omitted:['Unknown attachment.stl'],omitted_details:[{title:'附件'}]};
const partialTemplate=await loadTemplate(partialGuide,{fetchMesh});assert.ok(partialTemplate.partial);assert.match(partialTemplate.note,/附件.*未显示/);partialTemplate.dispose();
const detailedStage=Object.create(DetailedBuilderStage.prototype);detailedStage.groups=[];detailedStage.scene=new THREE.Scene();detailedStage.keyLight=new THREE.DirectionalLight();detailedStage.draw=()=>{};detailedStage.detailProvider=i=>instantiate(baseTemplate,i);
detailedStage.update([item],item.id);
const outline=detailedStage.groups[0].children.find(c=>c.isLineSegments),outlineBox=new THREE.Box3().setFromObject(outline);
assert.ok(outlineBox.min.y<0&&outlineBox.max.y>20,'Selection contains both base and raised body.');detailedStage.update([],null);baseTemplate.dispose();
const second=instantiate(template,{...item,id:'b',colors:{...item.colors,body:'#123456'}});
assert.equal(mesh.children[0].geometry,second.children[0].geometry);assert.notEqual(mesh.children[0].material,second.children[0].material);
let disposed=0;template.nodes[0].geometry.addEventListener('dispose',()=>disposed++);
const stage=Object.create(BuilderStage.prototype);stage.groups=[];stage.scene=new THREE.Scene();stage.draw=()=>{};stage.detailProvider=i=>instantiate(template,i);
stage.update([item],item.id);stage.update([{...item,position:[60,70,80]}],item.id);
assert.equal(disposed,0);assert.deepEqual(stage.groups[0].position.toArray(),[60,80,70]);
stage.update([],null);template.dispose();assert.equal(disposed,1);
await assert.rejects(loadTemplate({...guide,coverage_complete:false},{fetchMesh}));
await assert.rejects(loadTemplate(guide,{fetchMesh:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(134)})}),/版本/);
let reads=0;const details=new BuilderDetails(async()=>{reads++;return guide;},()=>{},{fetchMesh});
await details.sync([item,{...item,id:'b'}],'b');assert.equal(reads,1);assert.equal(details.display.size,2);
await details.sync([{...item,colors:{...item.colors,body:'#123456'}},{...item,id:'b'}],'b');assert.equal(reads,1);
details.cache.get(modelKey(config)).triangles=DRAW_BUDGET*.6;details.signature=null;
await details.sync([item,{...item,id:'b'}],'b');assert.deepEqual([...details.display.keys()],['b']);
details.enabled=false;await details.sync([item],'a');assert.equal(details.display.size,0);details.clear();
let complete;const cancelled=new BuilderDetails(()=>new Promise(resolve=>complete=resolve),()=>{},{fetchMesh});const pending=cancelled.sync([item],'a');cancelled.clear();complete(guide);await pending;assert.equal(cancelled.cache.size,0);
let failures=0;const bad=new BuilderDetails(async()=>{failures++;throw Error('bad source');},()=>{},{fetchMesh});await bad.sync([item,{...item,id:'b'}],'a');assert.equal(failures,1);assert.equal(bad.display.size,0);
// Switching selection must evict a lower-priority cached model before refusing
// the newly selected model; repeated print copies do not inflate shared cache.
const selectedDetails=new BuilderDetails(async()=>guide,()=>{},{fetchMesh});
const akey=modelKey(config),bconfig={...config,family:'M'},bkey=modelKey(bconfig);
let oldDisposed=false;selectedDetails.cache.set(akey,{cacheFaces:CACHE_BUDGET,triangles:CACHE_BUDGET,dispose(){oldDisposed=true;}});
await selectedDetails.sync([item,{...item,id:'selected',config:bconfig}],'selected');
assert.ok(selectedDetails.display.has('selected'));assert.ok(oldDisposed);selectedDetails.clear();
console.log('Builder detail checks passed: anchoring/axis, shared geometry with independent colors, movement/disposal, versions, cache, selected-first budget, cancellation and fallback.');

if(process.argv.includes('--local')){
  const fixtures=JSON.parse(await readFile('tmp/composition-fixture.json','utf8'));
  for(const g of fixtures){
    const byId=new Map(g.parts.map(p=>[p.id,p]));
    const t=await loadTemplate(g,{fetchMesh:async url=>{const id=decodeURIComponent(url.split('/').at(-1).split('?')[0]),bytes=await readFile(byId.get(id).path);return {ok:true,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)};}});
    const object=instantiate(t,item),shell=object.children.find(n=>/\bModule\b/.test(t.nodes[object.children.indexOf(n)].name));object.updateMatrixWorld(true);
    const body=new THREE.Box3().setFromObject(shell);assert.ok(body.min.toArray().every(n=>Math.abs(n)<.0001));assert.ok(Math.abs(body.max.x-164.8)<.01);assert.ok(Math.abs(body.max.z-146.1)<.01);
    assert.equal(t.nodes.length,g.coverage.entities);assert.ok(Math.abs(t.anchor.determinant()-1)<1e-10);
    const labelIndex=t.nodes.findIndex(n=>n.name==='Label.stl');if(labelIndex>=0){const center=new THREE.Box3().setFromObject(object.children[labelIndex]).getCenter(new THREE.Vector3());assert.ok(center.x<82.4,'Label stays on the left when viewed from the front.');}
    console.log(g.title+': '+t.nodes.length+' exact installed meshes, shell bounds '+body.getSize(new THREE.Vector3()).toArray().map(v=>v.toFixed(3)).join(' / ')+'; rigid orientation and front-left label verified.');
    object.traverse(o=>o.material?.dispose());t.dispose();
  }
}
