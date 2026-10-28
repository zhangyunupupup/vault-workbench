import assert from 'node:assert/strict';
import {indexSTL} from '../web/assets/layout-mesh-codec.js';
import {indexedGeometry} from '../web/assets/layout-mesh-loader.js';

function stl(triangles){
  const buffer=new ArrayBuffer(84+50*triangles.length),view=new DataView(buffer);view.setUint32(80,triangles.length,true);
  triangles.forEach((p,f)=>p.flat().forEach((n,i)=>view.setFloat32(96+50*f+4*i,n,true)));return buffer;
}
const triangles=[[[10,20,3],[12,20,3],[10,24,4]],[[12,20,3],[12,24,4],[10,24,4]]];
const buffer=stl(triangles),result=indexSTL(buffer);
assert.equal(result.faces,2);assert.equal(result.positions.length,12);assert.equal(result.index.length,6);
const normalized=triangles.flat().flatMap(([x,y,z])=>[x-11,z-3,22-y]);
assert.deepEqual([...result.index].flatMap(i=>[...result.positions.slice(i*3,i*3+3)]),normalized,'Retain all triangles, winding, and full-precision normalized coordinates.');
assert.deepEqual([...indexSTL(buffer).index],[...result.index]);
const supports={remove_boxes:[{min:[-1,0,-2],max:[1,1,0]}],removed_faces:0};
assert.equal(indexSTL(buffer,supports).index.length,6);
const cleanup={remove_boxes:[{min:[-1,0,-2],max:[1,1,2]}],removed_faces:2};
assert.equal(indexSTL(buffer,cleanup).index.length,0);
assert.throws(()=>indexSTL(buffer,{...cleanup,removed_faces:1}),/支撑/);
const invalid=buffer.slice(0);new DataView(invalid).setFloat32(96,NaN,true);assert.throws(()=>indexSTL(invalid),/无效/);
assert.throws(()=>indexSTL(buffer.slice(0,-1)));assert.throws(()=>indexSTL(new ArrayBuffer(0)));
const g=await indexedGeometry(buffer);assert.equal(g.index.count,6);assert.equal(g.attributes.position.count,4);assert.deepEqual(g.boundingBox.min.toArray(),[-1,0,-2]);g.dispose();
const signal=new AbortController();signal.abort();await assert.rejects(indexedGeometry(buffer,signal.signal),/取消/);
let terminated=0,posted;
globalThis.Worker=class {
  postMessage(message,transfer){posted={message,transfer};queueMicrotask(()=>this.onmessage({data:indexSTL(message.buffer,message.supports)}));}
  terminate(){terminated++;}
};
const workerGeometry=await indexedGeometry(buffer,undefined,supports);assert.equal(workerGeometry.index.count,6);assert.equal(terminated,1);assert.equal(posted.transfer[0],buffer);assert.equal(posted.message.supports,supports);workerGeometry.dispose();
const active=new AbortController();
globalThis.Worker=class {postMessage(){active.abort();}terminate(){terminated++;}};
await assert.rejects(indexedGeometry(buffer,active.signal),/取消/);assert.equal(terminated,2);
globalThis.Worker=class {postMessage(){this.onerror();}terminate(){terminated++;}};
await assert.rejects(indexedGeometry(buffer),/失败/);assert.equal(terminated,3);delete globalThis.Worker;
console.log('Layout mesh checks passed: lossless topology, shared vertices, source normalization, bounded support removal, malformed/finite checks and cancellation.');
