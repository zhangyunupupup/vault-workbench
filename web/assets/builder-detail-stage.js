import * as THREE from './vendor/three.module.js';
import {BuilderStage} from './builder-stage.js';

export function cameraDistance(box,aspect,fov,direction){
  const center=box.getCenter(new THREE.Vector3()),right=new THREE.Vector3(0,1,0).cross(direction).normalize(),up=direction.clone().cross(right).normalize(),tan=Math.tan(fov*Math.PI/360);
  let distance=1;
  for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
    const p=new THREE.Vector3(x,y,z).sub(center),depth=p.dot(direction);
    distance=Math.max(distance,depth+Math.abs(p.dot(right))/(tan*aspect),depth+Math.abs(p.dot(up))/tan);
  }
  return distance*1.12;
}
export class DetailedBuilderStage extends BuilderStage {
  constructor(host,select,move){
    super(host,select,move);
    this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.1;
    this.keyLight=this.scene.children.find(o=>o.isDirectionalLight);this.keyLight.castShadow=true;this.keyLight.shadow.mapSize.set(2048,2048);this.keyLight.shadow.bias=-.0002;this.keyLight.shadow.normalBias=.12;
    this.scene.add(this.keyLight.target);
    this.floor=new THREE.Mesh(new THREE.PlaneGeometry(6000,6000),new THREE.ShadowMaterial({opacity:.18}));this.floor.rotation.x=-Math.PI/2;this.floor.position.y=-.15;this.floor.receiveShadow=true;this.scene.add(this.floor);
    this.draw();
  }
  fit(){
    const box=new THREE.Box3();this.groups.forEach(g=>box.expandByObject(g));
    if(box.isEmpty()){super.fit();return;}
    const rect=this.host.getBoundingClientRect(),aspect=rect.width&&rect.height?rect.width/rect.height:1,direction=new THREE.Vector3(1.5,1.3,1.8).normalize();
    const center=box.getCenter(new THREE.Vector3()),distance=Math.max(80,cameraDistance(box,aspect,this.camera.fov,direction));
    this.controls.target.copy(center);this.camera.position.copy(center).addScaledVector(direction,distance);this.controls.update();this.resize();
  }
  update(items,selected,checks=[]){
    if(!this.keyLight){super.update(items,selected,checks);return;}
    const box=new THREE.Box3();items.forEach(i=>{box.expandByPoint(new THREE.Vector3(i.position[0],i.position[2],i.position[1]));box.expandByPoint(new THREE.Vector3(i.position[0]+i.size[0],i.position[2]+i.size[2],i.position[1]+i.size[1]));});
    const center=box.isEmpty()?new THREE.Vector3():box.getCenter(new THREE.Vector3()),radius=box.isEmpty()?250:Math.max(...box.getSize(new THREE.Vector3()).toArray(),200)*.8;
    this.keyLight.target.position.copy(center);this.keyLight.position.copy(center).add(new THREE.Vector3(-radius*1.5,radius*2,radius*1.5));
    Object.assign(this.keyLight.shadow.camera,{left:-radius,right:radius,top:radius,bottom:-radius,near:1,far:radius*8});this.keyLight.shadow.camera.updateProjectionMatrix();super.update(items,selected,checks);
  }
}
