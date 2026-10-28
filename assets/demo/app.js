import {DEFAULT_COLORS,TYPES,configFor,normalize,checkLayout,snap} from './model.js';
const $=id=>document.getElementById(id),clone=v=>structuredClone(v);
const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const groups={body:'外壳 / 顶盖',drawer:'内抽 / 分隔',facade:'前面板',accessory:'机构 / 配件'};
const key='vault-demo-scene-v1';
let scene={version:1,name:'我的随手搭方案',items:[]},selected=null,stage=null,undo=[],redo=[];
const current=()=>scene.items.find(i=>i.id===selected);
const message=(text,error=false)=>{$('message').textContent=text;$('message').className=error?'error':'';};
function render(){
  const item=current(),checks=checkLayout(scene.items);
  $('name').value=scene.name;$('scene-count').textContent=`${scene.items.length} / 60 个箱体`;
  $('undo').disabled=!undo.length;$('redo').disabled=!redo.length;$('fields').disabled=!item;
  $('add-drawer').disabled=$('add-case').disabled=scene.items.length>=60;
  $('copy').disabled=scene.items.length>=60;
  $('selection').textContent=item?item.title:'选择一个箱体';
  $('size').textContent=item?`参考宽 × 深 × 高：${item.size.join(' × ')} mm`:'点击画布或列表选择。';
  $('items').innerHTML=scene.items.map((i,n)=>`<button class="item ${selected===i.id?'selected':''}" data-id="${esc(i.id)}" aria-pressed="${selected===i.id}"><span class="swatch" style="background:${i.colors.body}"></span><span>${n+1}. ${i.title}<small>${i.position.join(' / ')} mm</small></span></button>`).join('');
  const below=$('below').value;
  $('below').innerHTML='<option value="">选择支撑箱体</option>'+scene.items.filter(i=>i.id!==selected).map((i,n)=>`<option value="${esc(i.id)}">${i.title} · ${esc(i.id.slice(-4))}</option>`).join('');
  if(scene.items.some(i=>i.id===below))$('below').value=below;
  $('stack').disabled=scene.items.length<2;
  if(item){item.position.forEach((v,n)=>$('pos-'+n).value=v);for(const g of Object.keys(groups)){$('color-'+g).value=item.colors[g];$('palette-'+g).value=[...$('palette-'+g).options].some(o=>o.value===item.colors[g])?item.colors[g]:'';}}
  $('checks').innerHTML=checks.map(c=>`<div class="check ${c.level}">${esc(scene.items.find(i=>i.id===c.id).title)}：${esc(c.message)}</div>`).join('');
  stage?.update(scene.items,selected,checks);
}
function setScene(raw,{history=true,selection=selected}={}){
  try{
    const next=normalize(raw);
    if(history){undo.push(clone(scene));if(undo.length>50)undo.shift();redo=[];}
    scene=next;selected=scene.items.some(i=>i.id===selection)?selection:scene.items[0]?.id??null;
    render();
    try{localStorage.setItem(key,JSON.stringify(scene));message('方案已保存在本设备。保存JSON后，可在桌面工作台重新核对并导出。');}catch{message('无法自动保存，请用「保存方案」下载JSON备份。',true);}
    return true;
  }catch(e){message(e.message,true);return false;}
}
function add(kind){
  if(scene.items.length>=60)return;
  const next=clone(scene),id=crypto.randomUUID(),x=scene.items.length?Math.max(...scene.items.map(i=>i.position[0]+i.size[0]))+10:0;
  next.items.push({id,config:configFor(kind),position:[x,0,0],colors:clone(DEFAULT_COLORS)});
  if(setScene(next,{selection:id}))stage?.fit();
}
function edit(fn){if(!current())return;const next=clone(scene);fn(next.items.find(i=>i.id===selected));setScene(next);}
function travel(from,to){if(!from.length)return;const next=from.at(-1),old=clone(scene);if(setScene(next,{history:false})){from.pop();to.push(old);render();}}
$('add-drawer').onclick=()=>add('drawer');$('add-case').onclick=()=>add('sustainer');
$('items').onclick=e=>{const b=e.target.closest('[data-id]');if(b){selected=b.dataset.id;render();}};
$('position').onclick=()=>{const p=[0,1,2].map(n=>$('pos-'+n).value);if(p.some(v=>!v.trim()))return message('请填写三个有效坐标。',true);edit(i=>i.position=p.map(Number));};
for(let n=0;n<3;n++)$('pos-'+n).onkeydown=e=>{if(e.key==='Enter')$('position').click();};
$('ground').onclick=()=>edit(i=>i.position[2]=0);
$('stack').onclick=()=>{const lower=scene.items.find(i=>i.id===$('below').value);if(!lower)return message('请先选择一个支撑箱体。',true);edit(i=>i.position=[lower.position[0],lower.position[1],lower.position[2]+lower.size[2]]);stage?.fit();};
$('copy').onclick=()=>{if(!current()||scene.items.length>=60)return;const next=clone(scene),item=clone(current());item.id=crypto.randomUUID();item.position=[Math.max(...scene.items.map(i=>i.position[0]+i.size[0]))+10,0,0];next.items.push(item);if(setScene(next,{selection:item.id}))stage?.fit();};
$('remove').onclick=()=>{const next=clone(scene);next.items=next.items.filter(i=>i.id!==selected);setScene(next);stage?.fit();};
$('undo').onclick=()=>travel(undo,redo);$('redo').onclick=()=>travel(redo,undo);
$('name').onchange=()=>setScene({...clone(scene),name:$('name').value.trim()||'我的随手搭方案'});
$('save').onclick=()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(scene,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='VAULT组合方案.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  message('方案文件已准备下载。请在电脑「组合搭建」中导入，并用本地资料库重新核对。');
};
$('import').onclick=()=>$('file').click();
$('file').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;try{if(f.size>1024*1024)throw Error('方案文件不能超过1 MB。');if(setScene(JSON.parse(await f.text())))stage?.fit();}catch(e){message('导入失败：'+e.message,true);}};
$('fit').onclick=()=>stage?.fit();
$('mode').onclick=()=>{if(!stage)return;stage.moving=!stage.moving;$('mode').setAttribute('aria-pressed',String(stage.moving));$('mode').textContent=stage.moving?'移动箱体':'旋转视角';};
$('stage').addEventListener('stage-error',()=>{message('三维画布不可用，仍可用列表、坐标与JSON保存方案。',true);$('mode').disabled=true;});
$('colors').innerHTML=Object.entries(groups).map(([g,title])=>`<div class="color-row"><label for="color-${g}">${title}</label><input id="color-${g}" type="color" value="${DEFAULT_COLORS[g]}"><select id="palette-${g}" aria-label="${title}色板"><option value="">自定义颜色</option></select></div>`).join('');
for(const g of Object.keys(groups)){$('color-'+g).onchange=()=>edit(i=>i.colors[g]=$('color-'+g).value);$('palette-'+g).onchange=()=>{if($('palette-'+g).value)edit(i=>i.colors[g]=$('palette-'+g).value);};}
fetch('../palette.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(p=>{for(const g of Object.keys(groups))$('palette-'+g).innerHTML='<option value="">自定义颜色</option>'+p.colors.map(c=>`<option value="${c.hex.toUpperCase()}">${esc(c.name)} · ${esc(c.code)}</option>`).join('');render();}).catch(()=>message('色板未载入，仍可使用自定义颜色。',true));
let stored=null;
try{stored=JSON.parse(localStorage.getItem(key));}catch{message('本地方案无法读取，请导入JSON备份。',true);}
if(stored){if(!setScene(stored,{history:false}))render();}
else{scene=normalize({version:1,name:'我的随手搭方案',items:[{id:'demo-drawer',config:configFor('drawer'),position:[0,0,0],colors:DEFAULT_COLORS},{id:'demo-case',config:configFor('sustainer'),position:[0,0,57.01],colors:{...DEFAULT_COLORS,body:'#69816A'}}]});selected=scene.items[0].id;render();message('从这组示例开始，或加入你自己的模块。修改后自动保存在本设备。');}
import('../builder-stage.js').then(({BuilderStage})=>{stage=new BuilderStage($('stage'),id=>{selected=id;render();},(id,p)=>{try{const next=clone(scene);next.items.find(i=>i.id===id).position=snap(scene.items,id,p);setScene(next,{selection:id});}catch(e){message(e.message,true);render();}});$('stage-fallback').remove();render();stage.fit();}).catch(()=>{$('stage-fallback').textContent='三维画布不可用。仍可通过列表、坐标、叠放、配色和方案文件操作。';$('mode').disabled=true;});
async function offlineStatus(){
  try{
    const cache=await caches.open('vault-demo-v2.1.0-r2');
    if(await cache.match(new URL('index.html',location.href).href))$('offline-status').textContent='离线已就绪 · 可添加到主屏幕';
  }catch{$('offline-status').textContent='此浏览器未提供离线缓存，请保持联网。';}
}
if('serviceWorker'in navigator&&window.isSecureContext){navigator.serviceWorker.addEventListener('controllerchange',offlineStatus);navigator.serviceWorker.register('./sw.js').then(()=>navigator.serviceWorker.ready).then(offlineStatus).catch(()=>{$('offline-status').textContent='离线缓存未成功，仍可联网编辑并保存JSON。';});}
else $('offline-status').textContent='离线缓存需要HTTPS或本机访问。';
let installEvent;
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installEvent=e;$('install').hidden=false;});
$('install').onclick=async()=>{if(installEvent){await installEvent.prompt();installEvent=null;$('install').hidden=true;}};
