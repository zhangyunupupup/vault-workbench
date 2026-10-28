import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';

export class BuilderStage {
  constructor(host, select, move) {
    this.host = host; this.select = select; this.move = move; this.groups = []; this.items = [];
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color('#ebece5');
    this.camera = new THREE.PerspectiveCamera(38, 1, 1, 30000);
    this.renderer = new THREE.WebGLRenderer({antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); host.append(this.renderer.domElement);
    this.renderer.domElement.setAttribute('aria-label', '组合三维预览，使用右侧位置输入也可移动箱体');
    this.renderer.domElement.style.touchAction = 'none';
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.maxPolarAngle = Math.PI * .49; this.controls.minDistance = 80; this.controls.maxDistance = 16000;
    this.controls.addEventListener('change', () => this.draw());
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x777b68, 2.6));
    const sun = new THREE.DirectionalLight(0xffffff, 2.5); sun.position.set(-500, 1000, 700); this.scene.add(sun);
    const grid = new THREE.GridHelper(6000, 120, 0xa6ad9b, 0xd4d7ca); this.scene.add(grid);
    this.ray = new THREE.Raycaster(); this.pointer = new THREE.Vector2();
    const canvas = this.renderer.domElement;
    canvas.addEventListener('pointerdown', e => this.down(e));
    canvas.addEventListener('pointermove', e => this.dragMove(e));
    canvas.addEventListener('pointerup', e => this.up(e));
    canvas.addEventListener('pointercancel', () => this.cancel());
    canvas.addEventListener('lostpointercapture', () => this.cancel());
    canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); this.host.dispatchEvent(new CustomEvent('stage-error')); });
    this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(host);
    this.fit();
  }
  resize() {
    const {width, height} = this.host.getBoundingClientRect(); if (!width || !height) return;
    this.camera.aspect = width / height; this.camera.updateProjectionMatrix(); this.renderer.setSize(width, height); this.draw();
  }
  draw() { this.renderer.render(this.scene, this.camera); }
  fit() {
    let box = new THREE.Box3(); this.groups.forEach(g => box.expandByObject(g));
    const center = box.isEmpty() ? new THREE.Vector3(120,50,100) : box.getCenter(new THREE.Vector3());
    const size = box.isEmpty() ? 350 : Math.max(...box.getSize(new THREE.Vector3()).toArray(), 200);
    this.controls.target.copy(center); this.camera.position.copy(center).add(new THREE.Vector3(size*1.5,size*1.3,size*1.8));
    this.controls.update(); this.resize();
  }
  update(items, selected, checks=[]) {
    this.items = items;
    for (const group of this.groups) {
      this.scene.remove(group); group.traverse(o => {o.geometry?.dispose(); o.material?.dispose();});
    }
    this.groups = items.map(item => {
      const g = new THREE.Group(), [w,d,h] = item.size, c=item.colors;
      g.userData.id=item.id; g.position.set(item.position[0],item.position[2],item.position[1]);
      const box=(sx,sy,sz,x,y,z,color)=>{
        const m=new THREE.Mesh(new THREE.BoxGeometry(sx,sy,sz),new THREE.MeshStandardMaterial({color,roughness:.65}));
        m.position.set(x,y,z); m.userData.id=item.id; g.add(m); return m;
      };
      box(w,3,d,w/2,1.5,d/2,c.body);
      box(4,h,d,2,h/2,d/2,c.body); box(4,h,d,w-2,h/2,d/2,c.body);
      box(w,h,4,w/2,h/2,2,c.body); box(w,3,d,w/2,h-1.5,d/2,c.body);
      if(item.config.kind==='drawer') {
        let offset=4; const inner=item.config.drawers || [item.config.height];
        for(const f of inner) {
          const ih=(h-8)*f/item.config.height;
          box(w-12,ih-3,10,w/2,offset+ih/2,d-9,c.drawer);
          box(w-18,ih-7,4,w/2,offset+ih/2,d-2,c.facade);
          box(Math.min(30,w*.2),6,5,w/2,offset+ih/2,d+1,c.accessory); offset+=ih;
        }
      } else {
        box(w-12,h-18,4,w/2,h/2,d-2,c.facade);
        box(w,7,d,w/2,h-3.5,d/2,c.body);
        box(22,14,5,w/2,h-17,d+1,c.accessory);
      }
      const state=checks.some(x=>x.id===item.id&&x.level==='error')?'error':checks.some(x=>x.id===item.id&&x.level==='warning')?'warning':'ok';
      const geometry=new THREE.EdgesGeometry(new THREE.BoxGeometry(w+2,h+2,d+2));
      const outline=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:state==='error'?0xc44732:item.id===selected?0xe86634:state==='warning'?0xaa822d:0x71866d}));
      outline.position.set(w/2,h/2,d/2); g.add(outline); this.scene.add(g); return g;
    });
    this.draw();
  }
  cast(e) {
    const r=this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);
    this.ray.setFromCamera(this.pointer,this.camera);
  }
  down(e) {
    if(e.button!==0 || !e.isPrimary) return;
    this.cast(e); const hit=this.ray.intersectObjects(this.groups,true).find(x=>x.object.isMesh);
    if(!hit) return;
    const id=hit.object.userData.id, item=this.items.find(x=>x.id===id);
    this.select(id);
    if(!this.moving) return;
    this.controls.enabled=false;
    const plane=new THREE.Plane(new THREE.Vector3(0,1,0),-item.position[2]);
    const start=this.ray.ray.intersectPlane(plane,new THREE.Vector3()); if(!start) {this.controls.enabled=true;return;}
    this.drag={id,plane,start,position:[...item.position],pointer:e.pointerId,moved:false};
    this.renderer.domElement.setPointerCapture(e.pointerId);
  }
  dragMove(e) {
    if(!this.drag || e.pointerId!==this.drag.pointer) return;
    this.cast(e); const p=this.ray.ray.intersectPlane(this.drag.plane,new THREE.Vector3()); if(!p) return;
    const pos=[this.drag.position[0]+p.x-this.drag.start.x,this.drag.position[1]+p.z-this.drag.start.z,this.drag.position[2]];
    this.drag.next=pos; this.drag.moved=true;
    const g=this.groups.find(g=>g.userData.id===this.drag.id); g.position.set(pos[0],pos[2],pos[1]); this.draw();
  }
  up(e) {
    if(!this.drag || e.pointerId!==this.drag.pointer) return;
    const d=this.drag; this.drag=null; this.controls.enabled=true;
    if(d.moved) this.move(d.id,d.next); else this.update(this.items,this.items.find(x=>x.id===d.id)?.id);
  }
  cancel() {if(this.drag){this.drag=null;this.controls.enabled=true;this.update(this.items,null);}}
}
