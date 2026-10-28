import assert from 'node:assert/strict';
import * as THREE from '../web/assets/vendor/three.module.js';
import {connectedFaces,deformPreview,prepareElements,elementMatrix,applyElement} from '../web/assets/assembly-pose.js';

const geometry=new THREE.BoxGeometry(2,2,2).toNonIndexed(),second=geometry.clone();second.translate(5,0,0);
const merged=new THREE.BufferGeometry();merged.setAttribute('position',new THREE.Float32BufferAttribute([...geometry.attributes.position.array,...second.attributes.position.array],3));merged.computeVertexNormals();merged.computeBoundingBox();
const groups=connectedFaces(merged);assert.equal(groups.length,2);assert.deepEqual(groups.map(a=>a.length),[12,12]);
const coordinates=[...merged.attributes.position.array];
const deformed=deformPreview(merged,{kind:'spring_compression',min_x:-1,fixed_x:4,amount_mm:1});
assert.deepEqual([...merged.attributes.position.array],coordinates);
assert.ok(Math.abs(deformed.attributes.position.array[0]-merged.attributes.position.array[0]-.6)<1e-6);
assert.ok([...deformed.attributes.normal.array].every(Number.isFinite));
assert.throws(()=>deformPreview(merged,{kind:'unknown'}));

const identity=[1,0,0,0,1,0,0,0,1],description={key:'lid',origin:[2,3,4],matrix:identity,step:1,explode:[0,10,0],selection:{all:true,faces:24}};
const sequence={motion:'sequence'};
const element={description,group:new THREE.Group()};
applyElement(element,sequence,1,0);assert.equal(element.group.visible,false);
applyElement(element,sequence,.5,1);assert.equal(element.group.visible,true);
const origin=new THREE.Vector3(0,0,0).applyMatrix4(element.group.matrix);
assert.deepEqual(origin.toArray(),[2,4,-8]);
applyElement(element,sequence,1,2);assert.deepEqual(new THREE.Vector3().applyMatrix4(element.group.matrix).toArray(),[2,4,-3]);

const hinge={motion:'hinge',rotations:[{keys:['lid'],pivot:[0,0,0],axis:[1,0,0],degrees:90,start:.2,end:1}]};
const before=elementMatrix(description,hinge,0,0),after=elementMatrix(description,hinge,1,0);
const p=new THREE.Vector3().applyMatrix4(before),q=new THREE.Vector3().applyMatrix4(after);
assert.ok(Math.abs(p.length()-q.length())<1e-9);assert.ok(Math.abs(q.x-2)<1e-9);assert.ok(Math.abs(q.y-3)<1e-9);assert.ok(Math.abs(q.z-4)<1e-9);
assert.deepEqual(elementMatrix(description,hinge,.1,0).elements,before.elements);
const drawer={motion:'drawer'};const withTravel={...description,travel:[0,50,0]};
assert.deepEqual(new THREE.Vector3().applyMatrix4(elementMatrix(withTravel,drawer,.5,0)).toArray(),[2,4,-28]);

const groupAttach={motion:'sequence',sequence_groups:[{keys:['lid'],attach_step:2,offset:[0,100,0]}]};
assert.deepEqual(new THREE.Vector3().applyMatrix4(elementMatrix(description,groupAttach,0,1)).toArray(),[2,4,-103]);
assert.deepEqual(new THREE.Vector3().applyMatrix4(elementMatrix(description,groupAttach,.5,2)).toArray(),[2,4,-53]);

const part={geometry:merged,material:new THREE.MeshBasicMaterial(),id:'pair',copies:1};
const copy=(g,faces)=>{const r=new THREE.BufferGeometry(),a=g.attributes.position.array;r.setAttribute('position',new THREE.Float32BufferAttribute(faces.flatMap(i=>[...a.slice(i,i+9)]),3));r.computeVertexNormals();r.computeBoundingBox();return r;};
const definition={elements:groups.map((faces,i)=>({...description,key:'piece'+i,selection:{connected:i,faces:faces.length}}))};
const prepared=prepareElements(part,definition,copy,()=>{});assert.equal(prepared.elements.length,2);assert.equal(prepared.owned.size,2);assert.equal(prepared.owned.has(merged),false);
const doubled=prepareElements({...part,copies:2},{elements:[...definition.elements,...definition.elements]},copy,()=>{});
assert.equal(doubled.elements.length,4);for(const g of doubled.owned)g.dispose();
assert.throws(()=>prepareElements({...part,copies:2},{elements:[definition.elements[0],definition.elements[0],definition.elements[0],definition.elements[1]]},copy,()=>{}));
assert.throws(()=>prepareElements(part,{elements:[definition.elements[0],definition.elements[0]]},copy,()=>{}));
assert.throws(()=>prepareElements(part,{elements:[{...description,selection:{all:true,faces:23}}]},copy,()=>{}));
for(const g of prepared.owned)g.dispose();geometry.dispose();second.dispose();merged.dispose();deformed.dispose();part.material.dispose();
console.log('Composition checks passed: connected coverage, unchanged originals, deformation cache, timeline visibility, attachment groups, pivot distance, phased motion and copy accounting.');
