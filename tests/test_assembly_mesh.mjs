// Run with Node; uses the shipped Three.js, no browser or package install needed.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const source=await readFile(new URL('../web/assembly-stage.js',import.meta.url),'utf8');
const moduleSource=source.replaceAll("'/assets/vendor/three.module.js'",JSON.stringify(new URL('../web/assets/vendor/three.module.js',import.meta.url).href)).replaceAll("'/assets/vendor/OrbitControls.js'",JSON.stringify(new URL('../web/assets/vendor/OrbitControls.js',import.meta.url).href));
const {readSTL}=await import('data:text/javascript;base64,'+Buffer.from(moduleSource).toString('base64'));
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
