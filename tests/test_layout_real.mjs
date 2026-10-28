// Optional full-source contract. Fixture contains local paths and stays in tmp/.
import assert from 'node:assert/strict';
process.on('uncaughtException',e=>{console.error(e.message);console.error(e.stack?.split('\n').filter(s=>!s.includes('data:text')).slice(-5).join('\n'));process.exit(1);});
import {readFile} from 'node:fs/promises';
import * as THREE from '../web/assets/vendor/three.module.js';
const url=name=>new URL('../web/'+name,import.meta.url).href;
let source=await readFile('web/assembly-stage.js','utf8');
for(const name of ['assets/vendor/three.module.js','assets/vendor/OrbitControls.js','assets/assembly-pose.js'])source=source.replaceAll(JSON.stringify('/'+name).replaceAll('"',"'"),JSON.stringify(url(name)));
const assembly='data:text/javascript;base64,'+Buffer.from(source).toString('base64');
source=await readFile('web/assets/builder-detail.js','utf8');
for(const [name,path]of [['./vendor/three.module.js','assets/vendor/three.module.js'],['./assembly-pose.js','assets/assembly-pose.js'],['./layout-mesh-loader.js','assets/layout-mesh-loader.js']])source=source.replaceAll("'"+name+"'",JSON.stringify(url(path)));
source=source.replaceAll("'/assembly-stage.js'",JSON.stringify(assembly));
const {loadTemplate,instantiate}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const fixtures=JSON.parse(await readFile(process.argv[2]||'tmp/all-models/layout-fixtures.json','utf8'));
for(const guide of fixtures){
  const parts=new Map(guide.parts.map(p=>[p.id,p]));
  const template=await loadTemplate(guide,{fetchMesh:async url=>{
    const id=decodeURIComponent(url.split('/').at(-1).split('?')[0]);const b=await readFile(parts.get(id).path);
    return {ok:true,arrayBuffer:async()=>b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength)};
  }});
  assert.ok(Math.abs(template.anchor.determinant()-1)<1e-9);
  const object=instantiate(template,{id:'test',colors:{body:'#848987',drawer:'#000000',facade:'#FFFFFF',accessory:'#FF6A13'}});object.updateMatrixWorld(true);
  const index=template.nodes.findIndex(n=>/\bModule\b/i.test(n.name));
  const box=new THREE.Box3().setFromObject(object.children[index],true);
  if(guide.anchor_floor==='assembly'){
    assert.ok(box.min.y>0);assert.ok(Math.abs(box.min.x)<.0001&&Math.abs(box.min.z)<.0001);
    assert.ok(Math.abs(new THREE.Box3().setFromObject(object,true).min.y)<.0001,'Base reaches the floor while lifting the body.');
  }else assert.ok(box.min.toArray().every(v=>Math.abs(v)<.0001));
  assert.ok(Math.abs(box.max.x-guide.expected_width)<.2);
  assert.ok(Math.abs(box.max.z-guide.expected_depth)<.2);
  assert.equal(template.nodes.length,guide.expected_entities);
  assert.ok(template.nodes.every(n=>n.geometry.index?.count||n.geometry.attributes.normal));
  console.log(guide.title+': '+template.nodes.length+' meshes; '+template.triangles+' full source faces; '+template.cacheFaces+' cached faces.');
  object.traverse(o=>o.material?.dispose());template.dispose();
}
console.log('All representative full-source layout meshes loaded with original topology and rigid shell anchors.');
