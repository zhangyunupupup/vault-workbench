// Run with Node; uses the shipped Three.js, no browser or package install needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source=await readFile(new URL('../web/assembly-stage.js',import.meta.url),'utf8');
const moduleSource=source.replaceAll("'/assets/vendor/three.module.js'",JSON.stringify(new URL('../web/assets/vendor/three.module.js',import.meta.url).href)).replaceAll("'/assets/vendor/OrbitControls.js'",JSON.stringify(new URL('../web/assets/vendor/OrbitControls.js',import.meta.url).href));
const {readSTL,AssemblyStage,splitSpringGeometry}=await import('data:text/javascript;base64,'+Buffer.from(moduleSource).toString('base64'));
const buffer=new ArrayBuffer(134),view=new DataView(buffer);view.setUint32(80,1,true);
const points=[10000,20000,30000,10010,20000,30000,10000,20020,30030];
points.forEach((v,i)=>view.setFloat32(96+i*4,v,true));
const mesh=readSTL(buffer);
assert.deepEqual(mesh.size,[10,20,30]);
assert.deepEqual([...mesh.geometry.attributes.position.array],[-5,0,10,5,0,10,-5,30,-10]);
assert.equal(mesh.geometry.attributes.position.count,3);
assert.ok([...mesh.geometry.attributes.normal.array].every(Number.isFinite));
mesh.geometry.dispose();
assert.throws(()=>readSTL(buffer.slice(0,133)));
view.setUint32(80,2,true);assert.throws(()=>readSTL(buffer));view.setUint32(80,1,true);
view.setFloat32(96,NaN,true);assert.throws(()=>readSTL(buffer));
console.log('Mesh checks passed: complete triangles, mm scale, far-origin recentering, finite normals, malformed input rejection.');

// Exercise actual scene transforms without a GPU or the production models.
const THREE=await import('../web/assets/vendor/three.module.js');
globalThis.cancelAnimationFrame=()=>{};
const stage=Object.create(AssemblyStage.prototype);
stage.parts=['key','cap','panel'].map((id,rank)=>({id,rank,group:new THREE.Group(),galleryMeshes:[],components:[]}));
stage.draw=()=>{};stage.fit=()=>{};
const joint={instances:[
  {id:'key',position:[0,0,0],rotation:[0,0,0],explode:[0,0,0]},
  {id:'cap',position:[0,35.41703558,0],rotation:[180,0,0],explode:[0,70,0]}
]};
stage.setJoint(joint);
const [key,cap,panel]=stage.parts.map(p=>p.group);
assert.equal(panel.visible,false);
for(const fraction of [1,.5,0]){
  stage.layout(fraction);
  assert.deepEqual(key.position.toArray(),[0,0,0]);
  // A point on the cap inner floor meets the key top when closed.
  const floor=new THREE.Vector3(0,2,0).applyEuler(cap.rotation).add(cap.position);
  assert.ok(Math.abs(floor.y-(33.41703558+70*fraction))<1e-8);
}
stage.setJoint(null);
for(const p of stage.parts){
  assert.equal(p.group.visible,true);
  assert.deepEqual(p.group.rotation.toArray().slice(0,3),[0,0,0]);
  assert.equal(p.group.position.y,0);
}
assert.notEqual(key.position.x,cap.position.x);
console.log('Joint checks passed: seating plane, explode interpolation, hidden unrelated parts, restored gallery transforms.');

const pair=new THREE.BufferGeometry();
pair.setAttribute('position',new THREE.Float32BufferAttribute([0,0,2,1,0,2,0,1,2,0,0,-2,1,0,-2,0,1,-2],3));pair.computeVertexNormals();
const regions=[{region:'negative_y',faces:1},{region:'positive_y',faces:1}];
const pieces=splitSpringGeometry(pair,regions);
assert.equal(pieces.reduce((n,p)=>n+p.geometry.attributes.position.count,0),pair.attributes.position.count);
assert.deepEqual([...pieces[0].geometry.attributes.position.array],[...pair.attributes.position.array.slice(0,9)]);
assert.deepEqual([...pieces[1].geometry.attributes.position.array],[...pair.attributes.position.array.slice(9)]);
assert.throws(()=>splitSpringGeometry(pair,[{region:'negative_y',faces:2},{region:'positive_y',faces:1}]));
pair.attributes.position.array[2]=-1;assert.throws(()=>splitSpringGeometry(pair,regions));
const gallery=new THREE.Mesh(new THREE.BoxGeometry(1,1,1)),springGroup=new THREE.Group();springGroup.add(gallery);
const components=pieces.map(piece=>{const group=new THREE.Group();group.add(new THREE.Mesh(piece.geometry));springGroup.add(group);return {...piece,group};});
stage.parts.push({id:'springs',rank:3,group:springGroup,galleryMeshes:[gallery],components});
const reference={...joint,min_gap:40,instances:[...joint.instances,{id:'springs',position:[0,0,0],rotation:[0,0,0],explode:[0,0,0],components:regions.map((r,i)=>({...r,position:[i?38:-38,.6,19],rotation:[0,i?0:180,0],explode:[0,-60,0]}))}]};
stage.setJoint(reference);stage.layout(0);
assert.equal(stage.gap,.4);assert.equal(gallery.visible,false);
for(const component of components){assert.equal(component.group.visible,true);assert.ok(component.group.position.y< -23);}
stage.setJoint(joint);assert.equal(springGroup.visible,false);
stage.setJoint(null);assert.equal(gallery.visible,true);
for(const component of components)assert.equal(component.group.visible,false);
pair.dispose();gallery.geometry.dispose();for(const piece of pieces)piece.geometry.dispose();
console.log('Spring checks passed: complete partition, unchanged coordinates, bad counts/crossing triangles rejected, reference gap enforced, gallery restored.');
