// Offline layout data only. No source paths, print recipes or official mesh data.
export const DEFAULT_COLORS={body:'#8E9089',drawer:'#202621',facade:'#F7F5ED',accessory:'#FF6A13'};
export const TYPES={drawer:{title:'S3 · 1F 抽屉',size:[164.8,156.1,57.01]},sustainer:{title:'S3 · 2F 翻盖箱',size:[164.8,156.1,99.5]}};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const fail=s=>{throw new Error(s);};
const number=v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=10000?Math.round(v*100)/100:fail('坐标须为 -10000 至 10000 mm 的有限数字。');
const allowed=new Set(['kind','family','depth','height','quantity','drawers','roof','key','variant','split_roof','interior','baseplate','divider_height','width_dividers','depth_dividers','top_handle','rails','labels','latches','mount','base','wheels','colors']);
export function configFor(kind){
  if(!Object.hasOwn(TYPES,kind))fail('演示仅支持S3 1F抽屉与S3 2F整盖翻盖箱。');
  return {kind,family:'S',depth:3,height:kind==='drawer'?1:2,quantity:1,drawers:[kind==='drawer'?1:2],roof:'grid',key:'standard',variant:'standard',split_roof:false,interior:'none',labels:true,latches:1,base:'none',mount:'none'};
}
function config(raw){
  if(!object(raw)||Object.keys(raw).some(k=>!allowed.has(k)))fail('配置包含演示不支持的字段；请在桌面工作台打开。');
  const c={...configFor(raw.kind??'drawer'),...raw};
  if(c.family!=='S'||c.depth!==3||c.height!==(c.kind==='drawer'?1:2)||c.quantity!==1)fail('演示仅支持S3 1F单抽屉和S3 2F整盖翻盖箱，每个条目1套。');
  if(c.key!=='standard'||c.variant!=='standard'||c.split_roof!==false||c.interior!=='none'||c.base!=='none'||c.mount!=='none'||c.top_handle||c.rails||c.wheels||c.width_dividers||c.depth_dividers)fail('此方案含改装或内部配置，请在桌面工作台打开，演示不会自动改型。');
  if(!Array.isArray(c.drawers)||c.drawers.length!==1||c.drawers[0]!==c.height||!['grid','none'].includes(c.roof)||typeof c.labels!=='boolean'||!Number.isInteger(c.latches)||c.latches<0||c.latches>4)fail('此选配尚未接入演示，请在桌面工作台打开。');
  // Preserve the options this simplified view can describe; discard inactive UI fields.
  return {...configFor(c.kind),roof:c.roof,labels:c.labels,latches:c.latches};
}
function colors(raw){
  if(!object(raw)||Object.keys(raw).some(k=>!Object.hasOwn(DEFAULT_COLORS,k)))fail('配色分组无效。');
  return Object.fromEntries(Object.entries({...DEFAULT_COLORS,...raw}).map(([k,v])=>{
    if(typeof v!=='string'||!/^#[\da-f]{6}$/i.test(v))fail('颜色须为六位HEX色值。');
    return [k,v.toUpperCase()];
  }));
}
export function normalize(raw){
  if(!object(raw)||raw.version!==1||!Array.isArray(raw.items)||raw.items.length>60)fail('方案须为version:1，最多60个箱体。');
  if(typeof raw.name!=='string'||raw.name.length>80)fail('方案名称须为80字以内。');
  const seen=new Set();
  return {version:1,name:raw.name,items:raw.items.map(item=>{
    if(!object(item)||typeof item.id!=='string'||!/^[\w-]{1,64}$/.test(item.id)||seen.has(item.id))fail('箱体编号重复或无效。');
    seen.add(item.id);
    const c=config(item.config);
    if(!Array.isArray(item.position)||item.position.length!==3)fail('位置须为[X,Y,Z]。');
    return {id:item.id,config:c,position:item.position.map(number),colors:colors(item.colors??item.config.colors??{}),size:[...TYPES[c.kind].size],title:TYPES[c.kind].title};
  })};
}
export function checkLayout(items){
  const checks=[],eps=.05;
  const issue=(i,level,message)=>checks.push({id:i.id,level,message});
  items.forEach((item,index)=>{
    const [x,y,z]=item.position,[w,d]=item.size;
    if(z < -eps)issue(item,'error','箱体低于地面。');
    for(const other of items.slice(0,index))if(item.position.every((v,a)=>Math.min(v+item.size[a],other.position[a]+other.size[a])-Math.max(v,other.position[a])>eps)){
      issue(item,'error','参考包络与另一箱体相交。');issue(other,'error','参考包络与另一箱体相交。');
    }
    if(z>eps){
      const lower=items.find(o=>o.id!==item.id&&Math.abs(o.position[2]+o.size[2]-z)<=eps&&o.position[0]<=x+eps&&o.position[1]<=y+eps&&o.position[0]+o.size[0]>=x+w-eps&&o.position[1]+o.size[1]>=y+d-eps);
      if(!lower)issue(item,'error','悬空或底面缺少单个完整支撑面。');
      else {issue(item,'warning','叠放仅按包络对齐；嵌合高度、连接扣与承载需核对。');if(lower.config.kind==='sustainer')issue(lower,'warning','取物前需移开上方箱体，未计算翻盖空间。');}
    }
  });
  return checks;
}
export function snap(items,id,position,step=5){
  const item=items.find(i=>i.id===id);if(!item)fail('箱体不存在。');
  const p=position.map((v,a)=>a===2?v:Math.round(v/step)*step);
  for(let a=0;a<2;a++){
    const edges=items.filter(i=>i.id!==id).flatMap(i=>[i.position[a],i.position[a]+i.size[a],i.position[a]-item.size[a],i.position[a]+i.size[a]-item.size[a]]);
    const near=edges.sort((x,y)=>Math.abs(x-p[a])-Math.abs(y-p[a]))[0];if(near!==undefined&&Math.abs(near-p[a])<8)p[a]=near;
  }
  return p.map(number);
}
