// Controller unit test: minimal DOM and deterministic animation clock; no browser.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const elements=new Map(),frames=new Map(),timers=new Map();let now=0,nextFrame=0,nextTimer=0,reduced=false;
const element=id=>{
  if(!elements.has(id))elements.set(id,{
    value:id==='assembly-gap'?'35':'',disabled:false,hidden:false,open:false,
    textContent:'',innerHTML:'',dataset:{},labels:[{}],style:{},events:{},
    classList:{add(){},remove(){},toggle(){}},replaceChildren(){},
    setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];},
    getAttribute(k){return this[k]??null;},
    addEventListener(k,fn){this.events[k]=fn;},
    querySelector:selector=>element(selector),
    querySelectorAll:selector=>selector.split(',').map(s=>element(s.trim().replace(/^#/,'')))
  });return elements.get(id);
};
class Stage {
  constructor(host,choose,onError){this.onError=onError;Stage.current=this;}
  clear(){this.joint=null;}
  async load(){return true;}
  layout(value){this.gap=value;}
  setJoint(value){if(Stage.failComposition&&value?.mode==='composition')throw Error('bad composition');this.joint=value;}
  setAssemblyStep(step){this.step=step;}
  setLabelsVisible(on){this.labels=on;} setXray(on){this.xray=on;}
  fit(){} emphasize(){} resize(){}
}
const joint={id:'pair',title:'标准旋钮与盖',note:'scope',instances:[{id:'key'},{id:'cap'}]};
const panelJoint={...joint,id:'panel',title:'前面板、旋钮与盖',instances:[...joint.instances,{id:'panel'}]};
const reference={...panelJoint,id:'reference',title:'左右弹簧 · 安装朝向参考',status:'orientation_only',min_gap:40,page:2,instances:[...panelJoint.instances,{id:'springs',components:[{},{}]}]};
const bodyMotion={...panelJoint,id:'body',motion:'drawer',stroke_mm:50,status:'geometry_checked',page:7};
const complete={...panelJoint,id:'complete',title:'完整步骤',mode:'composition',motion:'sequence',limits:'弹性示意',display_count:3,composition:[{id:'key',elements:[{step:0}]},{id:'cap',elements:[{step:0}]},{id:'panel',elements:[{step:1}]}]};
const hinge={...complete,id:'hinge',title:'开盖',motion:'hinge',angle_deg:110,angle_start:.2};
const guide={supported:true,title:'drawer',note:'gallery',precision_reason:'pending',joint,joints:[panelJoint,reference,joint,bodyMotion,complete,hinge],
  parts:[{id:'key',copies:1},{id:'cap',copies:1},{id:'panel',copies:1}],hardware:[],
  steps:[{title:'first',parts:['key'],hardware:[],doc:2,page:1},{title:'second',parts:['cap'],hardware:[],doc:2,page:2}]};
const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>[],addEventListener(){}},
  window:{addEventListener(){}},Stage,performance:{now:()=>now},
  matchMedia:()=>({matches:reduced}),setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id),
  requestAnimationFrame:fn=>{frames.set(++nextFrame,fn);return nextFrame;},
  cancelAnimationFrame:id=>frames.delete(id)});
const source=(await readFile(new URL('../web/assembly.js',import.meta.url),'utf8'))
  .replace('export function initAssembly','function initAssembly')
  .replace("await import('/assembly-stage.js')",'({AssemblyStage:Stage})');
vm.runInContext(source,context);
context.initAssembly({api:async(_,body)=>({...guide,joint:body.config.kind==='sustainer'?null:joint,joints:body.config.kind==='sustainer'?[]:guide.joints}),getConfig:()=>({}),openView(){}});
await element('assembly-drawer').onclick();
element('assembly-joint').onclick();
assert.equal(element('assembly-gap').value,100);
assert.equal(element('assembly-steps').hidden,true);
assert.equal(element('assembly-title').textContent,'前面板、旋钮与盖 · 子装配');
element('assembly-joint-play').onclick();
assert.equal(frames.size,1);
element('assembly-joint-select').value='pair';element('assembly-joint-select').onchange();
assert.equal(frames.size,0);
assert.equal(element('assembly-title').textContent,'标准旋钮与盖 · 子装配');
assert.equal(element('assembly-gap').value,100);
element('assembly-parts').onclick({target:{closest:()=>({dataset:{assemblyPart:'panel'}})}});
assert.equal(element('assembly-steps').hidden,false);
element('assembly-joint-select').value='panel';element('assembly-joint-select').onchange();
assert.equal(element('assembly-steps').hidden,true);
const tick=time=>{now=time;const callbacks=[...frames.values()];frames.clear();for(const fn of callbacks)fn(now);};
element('assembly-joint-play').onclick();tick(900);
assert.equal(element('assembly-gap').value,50);
element('assembly-joint-play').onclick();
assert.equal(frames.size,0);
assert.equal(element('assembly-joint-play').textContent,'继续合拢');
element('assembly-joint-play').onclick();tick(1800);
assert.equal(element('assembly-gap').value,0);
assert.equal(element('assembly-joint-play').textContent,'播放拆开');
element('assembly-joint-play').onclick();tick(2700);
element('assembly-joint-play').onclick();
assert.equal(element('assembly-joint-play').textContent,'继续拆开');
element('assembly-joint-play').onclick();tick(3600);
assert.equal(element('assembly-gap').value,100);
element('assembly-joint-play').onclick();
element('assembly-gap').value=25;element('assembly-gap').oninput();
assert.equal(frames.size,0);
assert.equal(element('assembly-joint-play').textContent,'播放合拢');
reduced=true;element('assembly-joint-play').onclick();
assert.equal(element('assembly-gap').value,0);
assert.equal(frames.size,0);
element('assembly-joint-select').value='reference';element('assembly-joint-select').onchange();
assert.equal(element('assembly-joint-play').hidden,true);
assert.equal(element('assembly-joint-play').disabled,true);
assert.equal(element('assembly-gap').min,40);
element('assembly-gap').value=0;element('assembly-gap').oninput();
assert.equal(element('assembly-gap').value,40);
element('assembly-joint-play').onclick();assert.equal(frames.size,0);
assert.equal(element('assembly-gap').value,40);
assert.equal(element('assembly-manual').href,'/api/docs/2#page=2');
element('assembly-joint').onclick();
assert.equal(element('assembly-gap').min,0);
assert.equal(element('assembly-gap').value,35);
assert.equal(element('assembly-steps').hidden,false);
assert.equal(element('assembly-play').disabled,false);
element('assembly-joint').onclick();
element('assembly-joint-select').value='panel';element('assembly-joint-select').onchange();
assert.equal(element('assembly-joint-play').disabled,false);
Stage.current.clear();Stage.current.onError('context lost');
assert.equal(element('assembly-steps').hidden,false);
assert.equal(element('assembly-joint').disabled,true);
assert.equal(element('assembly-play').disabled,false);
await element('assembly-drawer').onclick();
element('assembly-joint-select').value='body';element('assembly-joint-select').onchange();
assert.equal(element('assembly-gap-value').value,'50 mm');
assert.equal(element('assembly-joint-play').textContent,'播放推回');
element('assembly-joint-play').onclick();
assert.equal(element('assembly-gap-value').value,'0 mm');
assert.equal(element('assembly-joint-play').textContent,'播放抽出');
assert.equal(element('assembly-manual').href,'/api/docs/2#page=7');
await element('assembly-case').onclick();
assert.equal(element('assembly-joint').disabled,true);
assert.equal(element('assembly-joint-select').disabled,true);
console.log('Control checks passed: bidirectional play, pause/resume direction, slider cancellation, reduced motion, gallery restore, context-loss fallback, unsupported joint.');

await element('assembly-drawer').onclick();reduced=false;
element('assembly-joint-select').value='complete';element('assembly-joint-select').onchange();
assert.equal(element('assembly-steps').hidden,false);assert.equal(Stage.current.step,0);
element('assembly-play').onclick();tick(now+900);assert.equal(element('assembly-gap').value,50);
element('assembly-play').onclick();assert.equal(frames.size,0);assert.equal(timers.size,0);
element('assembly-play').onclick();tick(now+900);assert.equal(element('assembly-gap').value,0);assert.equal(timers.size,1);
const scheduled=[...timers.values()];timers.clear();scheduled.forEach(fn=>fn());
assert.equal(Stage.current.step,1);assert.equal(element('assembly-gap').value,100);
tick(now+1800);assert.equal(element('assembly-gap').value,0);assert.equal(element('assembly-play').textContent,'播放步骤');assert.equal(timers.size,0);
element('assembly-joint-select').value='hinge';element('assembly-joint-select').onchange();
assert.equal(element('assembly-gap-value').value,'110°');element('assembly-gap').value=20;element('assembly-gap').oninput();assert.equal(element('assembly-gap-value').value,'0°');
element('assembly-xray').onclick();assert.equal(Stage.current.xray,true);
element('assembly-labels').setAttribute('aria-pressed','true');element('assembly-labels').onclick();assert.equal(Stage.current.labels,false);
Stage.failComposition=true;element('assembly-joint-select').value='complete';element('assembly-joint-select').onchange();
assert.equal(Stage.current.joint,null);assert.equal(element('assembly-steps').hidden,false);assert.equal(element('assembly-title').textContent,'drawer');assert.match(element('assembly-status').textContent,/bad composition/);
console.log('Complete-flow checks passed: sequential install, pause/resume/advance, phased hinge units, view controls and composition-error fallback.');
