import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import vm from 'node:vm';
import {configFor,normalize,checkLayout,snap,DEFAULT_COLORS} from '../web/assets/demo/model.js';
const item=(id,kind='drawer',position=[0,0,0])=>({id,config:configFor(kind),position,colors:DEFAULT_COLORS});
const base={version:1,name:'手机与桌面',items:[item('drawer'),item('case','sustainer',[0,0,57.01])]};
const scene=normalize(base);
assert.deepEqual(scene.items[0].size,[164.8,156.1,57.01]);
assert.equal(checkLayout(scene.items).filter(c=>c.level==='error').length,0);
assert.ok(checkLayout(scene.items).some(c=>c.level==='warning'));
const manipulated=structuredClone(base);manipulated.items[0].size=[1,1,1];manipulated.items[0].path='C:/private.stl';manipulated.items[0].parts=[{id:'secret'}];
const clean=normalize(manipulated);assert.deepEqual(clean.items[0].size,scene.items[0].size);assert.equal(clean.items[0].path,undefined);assert.equal(clean.items[0].parts,undefined);
for(const config of [{family:'M'},{height:2},{depth:4},{key:'hidden'},{roof:'heavy'},{interior:'dividers'},{top_handle:true},{split_roof:true},{drawers:[true]},{quantity:true},{__invalid:'x'}]){
  const raw=structuredClone(base);Object.assign(raw.items[0].config,config);assert.throws(()=>normalize(raw));
}
for(const position of [[NaN,0,0],[Infinity,0,0],[10001,0,0],['0',0,0],[0,0]]){const raw=structuredClone(base);raw.items[0].position=position;assert.throws(()=>normalize(raw));}
for(const color of ['red','#12345','url(x)','<img>']){const raw=structuredClone(base);raw.items[0].colors={body:color};assert.throws(()=>normalize(raw));}
assert.throws(()=>normalize({...base,items:[item('same'),item('same')]}));
assert.throws(()=>normalize({...base,items:Array.from({length:61},(_,n)=>item('x'+n))}));
assert.throws(()=>normalize({...base,name:'x'.repeat(81)}));
assert.ok(checkLayout(normalize({...base,items:[item('a'),item('b','drawer',[0,0,1])]}).items).some(c=>c.level==='error'));
assert.ok(checkLayout(normalize({...base,items:[item('a','drawer',[0,0,3])]}).items).some(c=>c.message.includes('悬空')));
assert.deepEqual(snap(scene.items,'case',[166,1,57.01]),[164.8,0,57.01]);
// Write a concrete interchange fixture for Python's existing desktop validator.
if(process.argv.includes('--fixture'))await writeFile('tmp/demo-scene-fixture.json',JSON.stringify(scene));
console.log('Demo checks passed: import whitelist, source-path stripping, desktop schema, bounds/colors, overlap/support and snapping.');

const code=await readFile('web/assets/demo/sw.js','utf8'),handlers={},store=new Map();let offline=false,claimed=false;
const origin='https://example.test/project/assets/demo/sw.js';
const caches={async open(name){if(!store.has(name))store.set(name,new Map());const data=store.get(name);return {
  async addAll(requests){const fresh=[];for(const request of requests){if(offline)throw Error('offline');const path=new URL(request.url).pathname.replace('/project/','web/');fresh.push([request.url,await readFile(path)]);}fresh.forEach(([k,v])=>data.set(k,v));},
  async match(url){return data.get(url);}
};},async delete(name){return store.delete(name);},async keys(){return [...store.keys()];}};
const context={URL,Request,caches,fetch:()=>{throw Error('Unexpected network');},self:{location:new URL(origin),addEventListener:(name,fn)=>handlers[name]=fn,skipWaiting:async()=>{},clients:{claim:async()=>{claimed=true;}}}};
vm.runInNewContext(code,context);
let pending;handlers.install({waitUntil:p=>pending=p});await pending;
const cache=store.get('vault-demo-v2.2.0-r1');assert.equal(cache.size,11);
assert.ok([...cache.keys()].every(k=>!k.includes('/api/')&&!/\.stl|\.pdf/.test(k)));
store.set('unrelated-user-cache',new Map());store.set('vault-demo-old',new Map());
handlers.activate({waitUntil:p=>pending=p});await pending;assert.ok(claimed);assert.ok(store.has('unrelated-user-cache'));assert.ok(!store.has('vault-demo-old'));
offline=true;
for(const url of cache.keys()){
  let result;handlers.fetch({request:{url,method:'GET',mode:'cors'},respondWith:p=>result=p});assert.ok((await result).length);
}
let nav;handlers.fetch({request:{url:'https://example.test/project/assets/demo/',method:'GET',mode:'navigate'},respondWith:p=>nav=p});assert.ok((await nav).toString().includes('随手搭'));
let intercepted=false;handlers.fetch({request:{url:'https://example.test/api/state',method:'GET',mode:'cors'},respondWith:()=>intercepted=true});assert.equal(intercepted,false);
handlers.install({waitUntil:p=>pending=p});await assert.rejects(pending);assert.equal(store.get('vault-demo-v2.2.0-r1').size,11);
store.delete('vault-demo-v2.2.0-r1');handlers.install({waitUntil:p=>pending=p});await assert.rejects(pending);assert.ok(!store.has('vault-demo-v2.2.0-r1'));
console.log('Offline checks passed: all 11 assets exist under a subpath, offline reads work, API is untouched, failed install rejected and unrelated caches retained.');
