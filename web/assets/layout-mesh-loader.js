import * as THREE from './vendor/three.module.js';
import {indexSTL} from './layout-mesh-codec.js';
export async function indexedGeometry(buffer,signal,supports){
  if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
  let result;
  if(typeof Worker==='undefined')result=indexSTL(buffer,supports);
  else result=await new Promise((resolve,reject)=>{
    const worker=new Worker(new URL('./layout-mesh-worker.js',import.meta.url),{type:'module'});
    const cleanup=()=>{signal?.removeEventListener('abort',abort);worker.terminate();};
    const abort=()=>{cleanup();reject(new DOMException('加载已取消','AbortError'));};
    worker.onmessage=e=>{cleanup();e.data.error?reject(Error(e.data.error)):resolve(e.data);};
    worker.onerror=()=>{cleanup();reject(Error('真实网格整理失败，请重新读取。'));};
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted){abort();return;}
    worker.postMessage({buffer,supports},[buffer]);
  });
  if(signal?.aborted)throw new DOMException('加载已取消','AbortError');
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(result.positions,3));geometry.setIndex(new THREE.BufferAttribute(result.index,1));geometry.userData={sourceFaces:result.faces,removedFaces:result.removed_faces};geometry.computeBoundingBox();geometry.computeBoundingSphere();return geometry;
}
