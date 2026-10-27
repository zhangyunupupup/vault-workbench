import * as THREE from './vendor/three.module.js';

// All catalog matrices act on normalized source XYZ (Z up). The viewer is X,Z,-Y.
const Q=new THREE.Matrix4().set(1,0,0,0,0,0,1,0,0,-1,0,0,0,0,0,1),QI=Q.clone().invert();
const rawPoint=(p,i)=>[p[i],-p[i+2],p[i+1]];
const keyOf=(p,i)=>`${p[i]},${p[i+1]},${p[i+2]}`;

export function connectedFaces(geometry){
  const points=geometry.attributes.position.array,count=points.length/9,parent=new Int32Array(count),sizes=new Int32Array(count);sizes.fill(1);for(let i=0;i<count;i++)parent[i]=i;
  function root(i){while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i];}return i;}
  const vertices=new Map();
  for(let face=0;face<count;face++)for(let v=0;v<3;v++){
    const key=keyOf(points,face*9+v*3),previous=vertices.get(key);
    if(previous===undefined){vertices.set(key,face);continue;}
    let a=root(face),b=root(previous);if(a!==b){if(sizes[a]<sizes[b])[a,b]=[b,a];parent[b]=a;sizes[a]+=sizes[b];}
  }
  const groups=new Map();
  for(let face=0;face<count;face++){
    const r=root(face);if(!groups.has(r))groups.set(r,{faces:[],min:[Infinity,Infinity,Infinity]});
    const group=groups.get(r);group.faces.push(face*9);
    for(let v=0;v<3;v++){const point=rawPoint(points,face*9+v*3);group.min=group.min.map((n,a)=>Math.min(n,point[a]));}
  }
  return [...groups.values()].sort((a,b)=>a.min[0]-b.min[0]||a.min[1]-b.min[1]||a.min[2]-b.min[2]).map(g=>g.faces);
}

export function deformPreview(geometry,description){
  if(description.kind!=='spring_compression')throw Error('未知弹性预览类型。');
  const result=geometry.clone(),points=result.attributes.position.array;
  for(let i=0;i<points.length;i+=3){
    const x=points[i],weight=THREE.MathUtils.clamp((description.fixed_x-x)/(description.fixed_x-description.min_x),0,1);
    points[i]=x+description.amount_mm*weight;
  }
  result.computeVertexNormals();result.computeBoundingBox();result.computeBoundingSphere();return result;
}

export function prepareElements(part,definition,copyFaces,removeSupports){
  const needed=definition.elements.some(e=>e.selection.connected!==undefined),groups=needed?connectedFaces(part.geometry):null;
  const total=definition.elements.reduce((n,e)=>n+e.selection.faces,0);
  if(total!==part.geometry.attributes.position.count/3*part.copies)throw Error('安装实体数量与原文件打印份数不一致。');
  if(needed&&(definition.elements.length!==groups.length||new Set(definition.elements.map(e=>e.selection.connected)).size!==groups.length))throw Error('组合文件必须完整且不重复地覆盖每个实体。');
  const owned=new Set(),result=[];
  try{
    for(const element of definition.elements){
      let geometry=part.geometry;const selection=element.selection;
      if(selection.connected!==undefined){const faces=groups[selection.connected];if(!faces||faces.length!==selection.faces)throw Error('组合文件的实体面数与已核对版本不符。');geometry=copyFaces(geometry,faces);owned.add(geometry);}
      else if(!selection.all||geometry.attributes.position.count!==selection.faces*3)throw Error('整件几何与已核对版本不符。');
      if(element.supports){const clean=removeSupports(geometry,element.supports);if(owned.delete(geometry))geometry.dispose();geometry=clean;owned.add(geometry);}
      if(element.deform){const preview=deformPreview(geometry,element.deform);if(owned.delete(geometry))geometry.dispose();geometry=preview;owned.add(geometry);}
      const group=new THREE.Group(),mesh=new THREE.Mesh(geometry,part.material);mesh.userData.id=part.id;group.add(mesh);
      result.push({description:element,geometry,group,mesh});
    }
    return {elements:result,owned};
  }catch(error){for(const g of owned)g.dispose();throw error;}
}

function rotationMatrix(values){return new THREE.Matrix4().set(values[0],values[1],values[2],0,values[3],values[4],values[5],0,values[6],values[7],values[8],0,0,0,0,1);}

export function elementMatrix(element,profile,gap,step){
  const matrix=rotationMatrix(element.matrix),origin=new THREE.Vector3().fromArray(element.origin);
  matrix.setPosition(origin);
  if(profile.motion==='sequence'||profile.motion==='explode'){
    const amount=profile.motion==='sequence'?(element.step===step?gap:0):gap;
    matrix.setPosition(origin.add(new THREE.Vector3().fromArray(element.explode).multiplyScalar(amount)));
  }else if(profile.motion==='drawer'&&element.travel){
    matrix.setPosition(origin.add(new THREE.Vector3().fromArray(element.travel).multiplyScalar(gap)));
  }
  if(profile.motion==='sequence'){
    for(const group of profile.sequence_groups||[]){
      if(!group.keys.includes(element.key)||step>group.attach_step)continue;
      const amount=step<group.attach_step?1:gap;
      const current=new THREE.Vector3().setFromMatrixPosition(matrix).add(new THREE.Vector3().fromArray(group.offset).multiplyScalar(amount));matrix.setPosition(current);
    }
  }
  for(const motion of profile.rotations||[]){
    if(!motion.keys.includes(element.key))continue;
    const fraction=THREE.MathUtils.clamp((gap-motion.start)/(motion.end-motion.start),0,1),pivot=new THREE.Vector3().fromArray(motion.pivot);
    const turn=new THREE.Matrix4().makeRotationAxis(new THREE.Vector3().fromArray(motion.axis),fraction*motion.degrees*Math.PI/180);
    matrix.premultiply(new THREE.Matrix4().makeTranslation(...pivot.toArray().map(n=>-n))).premultiply(turn).premultiply(new THREE.Matrix4().makeTranslation(...pivot.toArray()));
  }
  if(profile.motion==='sequence')for(const motion of profile.sequence_rotations||[]){
    if(!motion.keys.includes(element.key)||step<motion.from_step)continue;
    const fraction=step<motion.close_step?1:step===motion.close_step?gap:0,pivot=new THREE.Vector3().fromArray(motion.pivot);
    const turn=new THREE.Matrix4().makeRotationAxis(new THREE.Vector3().fromArray(motion.axis),fraction*motion.degrees*Math.PI/180);
    matrix.premultiply(new THREE.Matrix4().makeTranslation(...pivot.toArray().map(n=>-n))).premultiply(turn).premultiply(new THREE.Matrix4().makeTranslation(...pivot.toArray()));
  }
  return Q.clone().multiply(matrix).multiply(QI);
}

export function applyElement(element,profile,gap,step){
  element.group.visible=profile.motion!=='sequence'||element.description.step<=step;
  element.group.matrix.copy(elementMatrix(element.description,profile,gap,step));element.group.matrixAutoUpdate=false;
}
