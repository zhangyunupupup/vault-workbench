// Run with Node; uses the shipped Three.js, no browser or package install needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source=await readFile(new URL('../web/assembly-stage.js',import.meta.url),'utf8');
const moduleSource=source.replaceAll("'/assets/vendor/three.module.js'",JSON.stringify(new URL('../web/assets/vendor/three.module.js',import.meta.url).href)).replaceAll("'/assets/vendor/OrbitControls.js'",JSON.stringify(new URL('../web/assets/vendor/OrbitControls.js',import.meta.url).href));
const {readSTL,AssemblyStage}=await import('data:text/javascript;base64,'+Buffer.from(moduleSource).toString('base64'));
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
stage.parts=['key','cap','panel'].map((id,rank)=>({id,rank,group:new THREE.Group()}));
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
