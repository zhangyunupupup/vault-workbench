const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone = x => structuredClone(x);
const key='vault-builder-v1';
const defaults={body:'#8E9089',drawer:'#000000',facade:'#FFFFFF',accessory:'#FF6A13'};
const groups={body:'外壳 / 顶盖',drawer:'内抽 / 分隔',facade:'前面板',accessory:'机构 / 配件'};
export function initBuilder({api,getConfig,getCatalog,onExport,toast}) {
  let scene={version:1,name:'我的收纳组合',items:[]}, selected=null, checks=[], last=null, preview=null;
  let stage=null, sequence=0, undo=[], redo=[], busy=false, palette=[], details=null, active=false;
  const host=$('builder-view');
  host.innerHTML=`<div class="page-heading"><div><div class="eyebrow">COMPOSE YOUR SPACE / 组合搭建</div><h1>把想法，<span>搭成你的收纳。</span></h1><p>从一个模块开始，安排位置与颜色，带走整套打印文件。</p></div><span class="pill">01 / 布局与配色</span></div>
  <div class="builder-toolbar"><input type="text" id="build-name" maxlength="80" aria-label="组合方案名称" value="我的收纳组合"><button id="build-undo" class="outline-button">撤销</button><button id="build-redo" class="outline-button">重做</button><button id="build-save" class="outline-button">保存方案 ↓</button><button id="build-import" class="outline-button">导入方案 ↑</button><input type="file" id="build-file" accept=".json,application/json" hidden></div>
  <div class="builder-grid"><aside class="builder-library panel"><span class="eyebrow">01 / 添加模块</span><h2>挑一个起点</h2><button class="primary-button" id="build-current">加入当前配置 ＋</button><p class="field-description">使用「配置打印」页的尺寸、内抽及附件，每次加入1套。</p><label class="field-label" for="build-model">快速选择型号</label><select id="build-model"></select><button id="build-add" class="outline-button">加入基础款 ＋</button><p class="field-description">基础款：单内抽 / 留空翻盖箱，标准配件。</p><div class="builder-list-heading"><h3>场景中的箱体</h3><span id="build-count">0 / 60</span></div><div id="build-items"></div></aside>
  <section class="builder-canvas-panel panel"><div class="builder-stage-toolbar"><button id="build-mode" aria-pressed="false">↻ 旋转视角</button><button id="build-fit">适合画面</button><label>吸附 <select id="build-grid" aria-label="吸附网格"><option value="1">1 mm</option><option value="5" selected>5 mm</option><option value="10">10 mm</option></select></label></div><div id="build-stage"><div id="build-stage-fallback">正在准备离线三维画布…</div></div><div class="builder-stage-caption"><span>简化外形 · 参考包络</span><span>拖动旋转 / 滚轮或双指缩放</span></div><p class="builder-scope">布局不含提手、底座、轮组与开合空间。实际嵌合高度和连接扣位置需核对；这里不进行承载验证。</p></section>
  <aside class="builder-inspector panel"><span class="eyebrow">02 / 调整模块</span><h2 id="build-selection">选择一个箱体</h2><p id="build-size" class="field-description">在画布或列表中点击选择。</p><fieldset id="build-fields" disabled><legend class="sr-only">所选箱体属性</legend><div class="builder-coordinates">${['X','Y','Z'].map((a,i)=>`<label>${a} ${i===2?'离地':'位置'}<input id="build-pos-${i}" aria-label="${a} 位置毫米" type="number" step="0.01" min="-10000" max="10000" value="0"></label>`).join('')}</div><button id="build-position" class="outline-button">应用坐标</button><div class="builder-pair"><button id="build-ground" class="outline-button">落到地面</button><button id="build-copy" class="outline-button">复制箱体</button></div><div class="builder-stack-control"><label class="field-label" for="build-below">放在另一个箱体上</label><select id="build-below"></select><button id="build-stack" class="outline-button">对齐并叠放 ↑</button></div><h3 class="builder-colors-heading">给零件组配色</h3><p class="field-description">整份 STL 统一颜色，成对文件不能分别指定。色板仅预览颜色，材料仍遵循零件清单。</p>${Object.entries(groups).map(([g,n])=>`<div class="builder-color"><label for="build-color-${g}">${n}</label><input id="build-color-${g}" type="color" value="${defaults[g]}" aria-label="${n}颜色"><select id="build-palette-${g}" aria-label="${n}拓竹色号"><option value="">自定义颜色</option></select></div>`).join('')}<p class="field-description">拓竹 PLA Basic 官方色值 · 屏幕与实物可能存在色差。<a id="build-palette-source" target="_blank" rel="noopener noreferrer">色板来源 ↗</a></p><button id="build-delete" class="text-button">移除此箱体</button></fieldset></aside></div>
  <section class="builder-results panel"><div class="builder-result-heading"><div><span class="eyebrow">03 / CHECK & PRINT</span><h2>核对布局，准备打印</h2></div><div><button id="build-csv" class="outline-button" disabled>打印清单 CSV ↓</button><button id="build-export" class="primary-button" disabled>按颜色打包 ZIP ↗</button></div></div><div id="build-message" role="status"></div><div id="build-checks"></div><div id="build-totals"></div><div class="builder-table-wrap"><table class="data-table"><thead><tr><th>颜色 / 材料</th><th>零件与原始文件</th><th>整份打印次数</th><th>支撑</th></tr></thead><tbody id="build-parts"></tbody></table></div><details class="builder-hardware"><summary>五金用量与依据</summary><div id="build-hardware"></div></details><p class="field-description">颜色分别建目录；保留原始 STL 字节和文件名。打包同时附带组合方案、打印清单及五金清单。</p></section>`;

  const current=()=>scene.items.find(i=>i.id===selected);
  const realControls=document.createElement('div');realControls.className='builder-real-controls';
  realControls.innerHTML='<button id="build-real" aria-pressed="true">真实模型 · 开</button><button id="build-real-reload">重新读取</button><span id="build-detail-status" role="status">正在准备真实模型预览…</span>';
  $('build-stage').before(realControls);
  const scope=host.querySelector('.builder-scope');scope.textContent='真实模型仅用于查看已核对打印件的外观与参考定位。包络检查仍不包含突出件、开合空间和嵌合，不代表装配或承载认证；弹性件沿用装配页的形变示意，备用连接扣不安装在箱体上。';
  function detailChanged(){
    if(!details)return;
    const count=details.display.size,total=scene.items.length;
    host.querySelector('.builder-stage-caption span').textContent=count?`真实STL ${count} / ${total} · ${count===total?'全部已加载':'其他简化'}`:'简化外形 · 参考包络';
    $('build-detail-status').textContent=details.enabled?(details.states.get(selected)||'当前可选型号均支持基础箱体真实 STL；选配定位范围见说明。'):'已切换简化布局，可随时打开真实模型。';
    stage?.update(scene.items,selected,checks);
  }
  const assemblyButton=document.createElement('button');assemblyButton.id='build-assembly';assemblyButton.className='outline-button';assemblyButton.textContent='查看选中箱体的装配步骤 ↗';
  $('build-fields').prepend(assemblyButton);
  assemblyButton.onclick=()=>{const item=current();if(item)window.dispatchEvent(new CustomEvent('assembly-request',{detail:{config:clone(item.config),colors:clone(item.colors)}}));};
  const setMessage=(s,error=false)=>{ $('build-message').textContent=s; $('build-message').className=error?'notice warning':'field-description'; };
  function saveLocal() {try{localStorage.setItem(key,JSON.stringify(scene));}catch{toast('自动保存失败，请点击保存方案下载 JSON。',true);}}
  function refreshModels() {
    const old=$('build-model').value;
    const options=(getCatalog()?.models||[]).filter(m=>m.verified&&!(m.kind==='drawer'&&m.family==='XL')&&!m.family.includes('²')).flatMap(m=>m.heights.map(h=>({kind:m.kind,family:m.family,depth:m.depth,height:h})));
    $('build-model').replaceChildren(...options.map(c=>{const o=document.createElement('option');o.value=JSON.stringify(c);o.textContent=`${c.family}${c.depth} · ${c.height}F ${c.kind==='drawer'?'抽屉':'翻盖箱'}`;return o;}));
    if(options.some(c=>JSON.stringify(c)===old)) $('build-model').value=old;
    $('build-add').disabled=!options.length;
  }
  function render() {
    const item=current(); $('build-name').value=scene.name; $('build-count').textContent=`${scene.items.length} / 60`;
    $('build-undo').disabled=busy||!undo.length; $('build-redo').disabled=busy||!redo.length;
    $('build-current').disabled=busy||scene.items.length>=60; $('build-add').disabled=busy||scene.items.length>=60||!$('build-model').value;
    $('build-fields').disabled=busy||!item;
    $('build-items').innerHTML=scene.items.length?scene.items.map((i,index)=>`<button class="builder-item ${i.id===selected?'selected':''}" data-item="${esc(i.id)}"><span class="builder-swatch" style="background:${i.colors.body}"></span><span><strong>${index+1}. ${esc(i.title.replace(' × 1',''))}</strong><small>${i.position.join(' / ')} mm</small></span></button>`).join(''):'<p class="builder-empty">还没有箱体。<br>从上方加入第一个模块。</p>';
    $('build-selection').textContent=item?item.title.replace(' × 1',''):'选择一个箱体';
    $('build-size').textContent=item?`参考宽 × 深 × 高：${item.size.join(' × ')} mm`:'在画布或列表中点击选择。';
    if(item) {
      item.position.forEach((v,i)=>$('build-pos-'+i).value=v);
      for(const g of Object.keys(groups)) { $('build-color-'+g).value=item.colors[g]; $('build-palette-'+g).value=palette.some(c=>c.hex.toUpperCase()===item.colors[g])?item.colors[g]:''; }
    }
    const below=$('build-below').value;
    $('build-below').innerHTML='<option value="">选择支撑箱体</option>'+scene.items.filter(i=>i.id!==selected).map(i=>`<option value="${esc(i.id)}">${esc(i.title.replace(' × 1',''))} · ${esc(i.id.slice(-4))}</option>`).join('');
    if(scene.items.some(i=>i.id===below&&i.id!==selected))$('build-below').value=below;
    $('build-stack').disabled=busy||scene.items.length<2;
    $('build-checks').innerHTML=checks.map(c=>`<div class="builder-check ${c.level}"><strong>${esc(scene.items.find(i=>i.id===c.id)?.title.replace(' × 1','')||c.id)}</strong><span>${esc(c.message)}</span></div>`).join('');
    $('build-real-reload').disabled=busy||!stage;
    if(active&&!busy)details?.sync(scene.items,selected);
    if(details)detailChanged();else stage?.update(scene.items,selected,checks);
  }
  async function validate(next,{history=true,selection=selected}={}) {
    if(busy) return false;
    busy=true; preview=null; $('build-export').disabled=true;$('build-csv').disabled=true;render();setMessage('正在核对本地型号、布局与打印任务…');
    try {
      const result=await api('/api/scene',next);
      if(history){undo.push(clone(scene));if(undo.length>50)undo.shift();redo=[];}
      scene=result.scene;last=result;checks=result.checks;selected=scene.items.some(i=>i.id===selection)?selection:scene.items[0]?.id||null;
      saveLocal(); render(); await refreshPlan();return true;
    }catch(e){await refreshPlan();setMessage(e.message,true);return false;}
    finally{busy=false;render();}
  }
  async function refreshPlan(){
    const seq=++sequence;
    preview=null;$('build-export').disabled=true;$('build-csv').disabled=true;
    $('build-parts').innerHTML='';$('build-hardware').innerHTML='';$('build-totals').textContent='';
    if(!scene.items.length){setMessage('添加箱体后，这里会汇总零件和五金。');return;}
    if(!last?.valid){setMessage('红色问题会阻止打包。调整坐标、落地或选择支撑箱体后重新检查。',true);return;}
    try {
      const data=await api('/api/preview',{scene});if(seq!==sequence)return;preview=data;
      $('build-parts').innerHTML=data.parts.map(p=>`<tr><td><span class="builder-swatch" style="background:${p.color}"></span>${p.color}<small>${esc(p.material)}</small></td><td>${esc(p.title)}<small>${esc(p.name)} · ${esc(p.unit)}</small></td><td>${p.copies}</td><td>${p.supports?'开启':'未特别标注，切片时检查'}</td></tr>`).join('');
      $('build-hardware').innerHTML='<table class="data-table"><thead><tr><th>规格</th><th>实际用量</th><th>依据 / 核对状态</th></tr></thead><tbody>'+data.hardware.map(h=>`<tr><td>${esc(h.name)}</td><td>${h.quantity}</td><td>${esc(h.source)}<small>${esc(h.reason)} · ${esc(h.status)}</small></td></tr>`).join('')+'</tbody></table>';
      $('build-totals').textContent=`${scene.items.length} 个箱体 / ${new Set(data.parts.map(p=>p.color)).size} 种颜色 / ${data.file_count} 个文件颜色任务 / 整份打印 ${data.copies} 次`;
      setMessage(checks.some(c=>c.level==='warning')?'参考包络没有碰撞或悬空；请逐条核对黄色提示。':'参考包络检查通过，可以生成打印包。');
      $('build-export').disabled=false;$('build-csv').disabled=false;
    }catch(e){if(seq===sequence)setMessage(e.message,true);}
  }
  async function add(config) {
    if(busy||scene.items.length>=60)return;
    const c=clone(config);c.quantity=1;delete c.colors;
    const id=crypto.randomUUID();const x=scene.items.length?Math.max(...scene.items.map(i=>i.position[0]+i.size[0]))+10:0;
    const next=clone(scene);next.items.push({id,config:c,position:[x,0,0],colors:clone(defaults)});
    if(await validate(next,{selection:id})) stage?.fit();
  }
  function edit(fn) {if(busy||!current())return;const next=clone(scene);fn(next.items.find(i=>i.id===selected));return validate(next);}
  function download(text,name,type) {
    const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function snapMove(id,position) {
    if(busy)return;const item=scene.items.find(i=>i.id===id);if(!item)return;
    const step=+$('build-grid').value;
    const pos=position.map((v,i)=>i===2?v:Math.round(v/step)*step);
    // Edge alignment takes precedence within 8 mm, retaining measured decimal widths.
    for(let axis=0;axis<2;axis++){
      const edges=scene.items.filter(i=>i.id!==id).flatMap(i=>[i.position[axis],i.position[axis]+i.size[axis],i.position[axis]-item.size[axis],i.position[axis]+i.size[axis]-item.size[axis]]);
      const nearest=edges.sort((a,b)=>Math.abs(a-pos[axis])-Math.abs(b-pos[axis]))[0];if(nearest!==undefined&&Math.abs(nearest-pos[axis])<8)pos[axis]=nearest;
    }
    const next=clone(scene);next.items.find(i=>i.id===id).position=pos;validate(next,{selection:id});
  }
  $('build-current').onclick=()=>add(getConfig());
  $('build-add').onclick=()=>{if(!$('build-model').value)return;const c=JSON.parse($('build-model').value);add({...c,quantity:1,drawers:[c.height],roof:'grid',variant:['S','M'].includes(c.family)?'standard':'flat',interior:'none',labels:true,latches:1,base:'none'});};
  $('build-items').onclick=e=>{const b=e.target.closest('[data-item]');if(b&&!busy){selected=b.dataset.item;render();}};
  $('build-name').onchange=()=>{const next=clone(scene);next.name=$('build-name').value.trim()||'我的收纳组合';validate(next);};
  for(let i=0;i<3;i++)$('build-pos-'+i).onkeydown=e=>{if(e.key==='Enter'){$('build-position').click();}};
  for(const g of Object.keys(groups)){
    $('build-color-'+g).onchange=()=>edit(i=>i.colors[g]=$('build-color-'+g).value);
    $('build-palette-'+g).onchange=()=>{const value=$('build-palette-'+g).value;if(value)edit(i=>i.colors[g]=value);};
  }
  $('build-position').onclick=()=>{const values=[0,1,2].map(i=>$('build-pos-'+i).value);if(values.some(v=>v.trim()===''||!Number.isFinite(Number(v)))){toast('请输入有效的毫米坐标。',true);return;}edit(item=>item.position=values.map(Number));};
  $('build-ground').onclick=()=>edit(i=>i.position[2]=0);
  $('build-stack').onclick=()=>{const lower=scene.items.find(i=>i.id===$('build-below').value);if(lower)edit(i=>i.position=[lower.position[0],lower.position[1],lower.position[2]+lower.size[2]]);};
  $('build-copy').onclick=()=>{if(busy||!current())return;const item=clone(current());item.id=crypto.randomUUID();item.position=[Math.max(...scene.items.map(i=>i.position[0]+i.size[0]))+10,0,0];const next=clone(scene);next.items.push(item);validate(next,{selection:item.id}).then(ok=>{if(ok)stage?.fit();});};
  $('build-delete').onclick=()=>{if(busy)return;const next=clone(scene);next.items=next.items.filter(i=>i.id!==selected);validate(next);};
  async function travel(from,to){if(busy||!from.length)return;const target=clone(from.at(-1)),old=clone(scene);if(await validate(target,{history:false})){from.pop();to.push(old);render();}}
  $('build-undo').onclick=()=>travel(undo,redo);$('build-redo').onclick=()=>travel(redo,undo);
  $('build-save').onclick=()=>download(JSON.stringify(scene,null,2),'VAULT组合方案.json','application/json');
  $('build-import').onclick=()=>{if(!busy)$('build-file').click();};
  $('build-file').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;try{if(f.size>1024*1024)throw Error('方案文件不能超过1 MB。');const raw=JSON.parse(await f.text());if(await validate(raw))stage?.fit();}catch(err){toast('导入失败：'+err.message,true);}};
  $('build-csv').onclick=()=>{
    if(!preview)return;const rows=[['中文零件','原始文件名','整份打印次数','单位','材料','颜色HEX','支撑','依据'],...preview.parts.map(p=>[p.title,p.name,p.copies,p.unit,p.material,p.color,p.supports?'开启':'未特别标注，切片时检查',p.source])];
    const csv=rows.map(row=>row.map(v=>'"'+String(v).replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"').join(',')).join('\r\n');download('\ufeff'+csv,'VAULT组合打印清单.csv','text/csv;charset=utf-8');
  };
  $('build-export').onclick=async()=>{if(busy||!preview)return;busy=true;render();$('build-export').disabled=true;try{const job=await api('/api/export',{scene});onExport(job);}catch(e){toast(e.message,true);}finally{busy=false;render();$('build-export').disabled=!preview;}};
  $('build-fit').onclick=()=>stage?.fit();
  $('build-mode').onclick=()=>{if(!stage)return;stage.moving=!stage.moving;$('build-mode').setAttribute('aria-pressed',String(stage.moving));$('build-mode').textContent=stage.moving?'✥ 移动箱体':'↻ 旋转视角';};
  $('build-real').onclick=()=>{if(!details)return;details.enabled=!details.enabled;if(!details.enabled)details.clear();$('build-real').setAttribute('aria-pressed',String(details.enabled));$('build-real').textContent=details.enabled?'真实模型 · 开':'真实模型 · 关';render();};
  $('build-real-reload').onclick=()=>{details?.clear();render();};
  $('build-stage').addEventListener('stage-error',()=>{details?.clear();if(details)details.enabled=false;stage?.update([],null);stage=null;$('build-mode').disabled=true;$('build-real').disabled=true;$('build-real-reload').disabled=true;setMessage('三维画布不可用，可继续使用箱体列表和坐标编辑。',true);});
  host.addEventListener('builder-close',()=>{active=false;details?.clear();stage?.update([],null);});
  window.addEventListener('vault-catalog-change',()=>{details?.clear();if(active&&!busy)validate(scene,{history:false});});
  host.addEventListener('builder-open',()=>{active=true;refreshModels();stage?.resize();if(!busy&&getCatalog())validate(scene,{history:false});});
  refreshModels();render();
  api('/assets/palette.json').then(data=>{palette=data.colors;$('build-palette-source').href=data.source;for(const g of Object.keys(groups)){$('build-palette-'+g).innerHTML='<option value="">自定义颜色</option>'+palette.map(c=>`<option value="${c.hex.toUpperCase()}">${esc(c.name)} ${esc(c.code)}</option>`).join('');}render();}).catch(()=>toast('官方色板暂时不可用，仍可自定义颜色。',true));
  Promise.all([import('/assets/builder-detail-stage.js'),import('/assets/builder-detail.js')]).then(([{DetailedBuilderStage},{BuilderDetails}])=>{
    stage=new DetailedBuilderStage($('build-stage'),id=>{if(!busy){selected=id;render();}},snapMove);details=new BuilderDetails(api,detailChanged);stage.detailProvider=item=>details.object(item);$('build-stage-fallback').remove();render();stage.fit();
  }).catch(()=>{ $('build-stage-fallback').textContent='三维画布不可用。仍可通过左侧列表、右侧坐标编辑、保存与导出。';$('build-mode').disabled=true;});
  try{const saved=JSON.parse(localStorage.getItem(key));if(saved)validate(saved,{history:false}).then(ok=>{if(ok)stage?.fit();});else validate(scene,{history:false});}catch{setMessage('已保存的方案无法读取，请导入备份或重新添加箱体。',true);}
}
