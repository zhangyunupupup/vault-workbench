const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const samples={drawer:{kind:'drawer',family:'S',depth:3,height:1,drawers:[1],roof:'grid',key:'standard',interior:'none',labels:true,latches:1},sustainer:{kind:'sustainer',family:'S',depth:3,height:2,variant:'standard',split_roof:false,interior:'none',labels:true}};

export function initAssembly({api,getConfig,openView}){
  const host=$('assembly-view');let data=null,step=0,selected=null,stage=null,sequence=0,timer=null,ready=false;
  host.innerHTML=`<div class="page-heading"><div><div class="eyebrow">UNDERSTAND EVERY PART / 装配演示</div><h1>看清零件，<span>一步步装起来。</span></h1><p>从本机模型读取真实几何，对照中文步骤与官方图示。</p></div><span class="pill">02 / 零件与步骤</span></div>
  <div class="assembly-presets"><button id="assembly-drawer" class="outline-button">S3 · 1F 标准抽屉</button><button id="assembly-case" class="outline-button">S3 · 2F 翻盖箱</button><button id="assembly-current" class="text-button">使用配置页的选型 ↗</button></div>
  <div id="assembly-status" class="notice" role="status" aria-live="polite">选择一个示例开始。</div>
  <div class="assembly-layout"><section class="panel assembly-viewport"><div class="assembly-tools"><strong id="assembly-title">零件分解</strong><div><button id="assembly-fit" class="text-button">视角复位</button><button id="assembly-focus" class="text-button" disabled>聚焦选中</button></div></div>
  <div id="assembly-stage"><p id="assembly-fallback">三维视图按需加载；下方步骤和零件清单可独立使用。</p></div>
  <div class="assembly-slider"><label for="assembly-gap">分解间距</label><input id="assembly-gap" type="range" min="0" max="100" value="35" disabled><output id="assembly-gap-value">35%</output></div>
  <div class="assembly-disclosure"><strong>分解排布 ≠ 装配定位</strong><p>零件保持同一毫米比例；成对零件保留 STL 内的打印排布。步骤切换抬高当前零件以便识别，不表示安装运动轨迹。</p><button class="outline-button" disabled>精确合拢 / 机构运动 · 待核对</button><p id="assembly-precision"></p></div></section>
  <aside class="panel assembly-guide"><div class="eyebrow">FOLLOW THE MANUAL</div><h2>安装步骤</h2><div class="assembly-playback"><button id="assembly-prev" class="outline-button" disabled aria-label="上一步">←</button><button id="assembly-play" class="primary-button" disabled>播放步骤</button><button id="assembly-next" class="outline-button" disabled aria-label="下一步">→</button></div><div id="assembly-steps"></div>
  <article id="assembly-instruction" aria-live="polite"></article><div id="assembly-step-hardware"></div><a id="assembly-manual" class="text-button" target="_blank" rel="noopener noreferrer">打开此步官方图示 ↗</a><p class="field-description">每步停留 6 秒，随时暂停查看。官方 PDF 由本机读取。</p></aside></div>
  <section class="panel assembly-inventory"><div class="assembly-inventory-heading"><div><span class="eyebrow">PART INDEX</span><h2>点击零件，互相定位</h2></div><span id="assembly-count"></span></div><div id="assembly-parts"></div><details><summary>整套五金与核对依据</summary><div id="assembly-hardware"></div></details><details id="assembly-document"><summary>在工作台中查看本步官方手册</summary><iframe id="assembly-pdf" title="本机官方装配手册" loading="lazy"></iframe></details></section>`;
  function stop(){clearTimeout(timer);timer=null;$('assembly-play').textContent='播放步骤';$('assembly-play').setAttribute('aria-pressed','false');}
  function hardware(items){return items.length?items.map(h=>`<div class="assembly-bolt"><strong>${esc(h.name)} × ${h.quantity}</strong><span>${esc(h.reason)}</span><small>${esc(h.source)} · ${esc(h.status)}</small></div>`).join(''):'<p class="field-description">本步无另列外购五金；打印件见高亮清单。</p>';}
  function highlight(){const ids=data?.steps[step]?.parts||[];stage?.emphasize(ids,selected);document.querySelectorAll('[data-assembly-part]').forEach(b=>{b.classList.toggle('selected',b.dataset.assemblyPart===selected);b.classList.toggle('active',ids.includes(b.dataset.assemblyPart));b.setAttribute('aria-pressed',String(b.dataset.assemblyPart===selected));});$('assembly-focus').disabled=!ready||!selected;}
  function choose(id){selected=id;highlight();const part=data?.parts.find(p=>p.id===id);if(part){$('assembly-selected').textContent=`已选：${part.title} · ${part.copies} 份整份 STL · ${part.unit}`;}}
  function showStep(index){
    if(!data?.steps.length)return;step=Math.max(0,Math.min(index,data.steps.length-1));const s=data.steps[step];
    $('assembly-steps').innerHTML=data.steps.map((s,i)=>`<button type="button" data-assembly-step="${i}" ${i===step?'aria-current="step"':''}><span>${String(i+1).padStart(2,'0')}</span>${esc(s.title)}</button>`).join('');
    $('assembly-instruction').innerHTML=`<span class="eyebrow">STEP ${step+1} / ${data.steps.length}</span><h3>${esc(s.title)}</h3><p>${esc(s.text)}</p>`;
    $('assembly-step-hardware').innerHTML=hardware(s.hardware);$('assembly-manual').href=`/api/docs/${s.doc}#page=${s.page}`;$('assembly-manual').textContent=`官方${s.doc===1?'总说明':'装配手册'} · 第 ${s.page} 页 ↗`;
    if($('assembly-document').open)$('assembly-pdf').src=$('assembly-manual').href;
    $('assembly-prev').disabled=step===0;$('assembly-next').disabled=step===data.steps.length-1;
    highlight();
  }
  function inventory(){
    $('assembly-parts').innerHTML='<p id="assembly-selected" role="status">在画布或下方清单中选择零件；小零件可用“聚焦选中”放大查看。</p><div class="assembly-part-grid">'+data.parts.map((p,i)=>`<button data-assembly-part="${p.id}" type="button"><span class="assembly-part-number">${String(i+1).padStart(2,'0')}</span><span><strong>${esc(p.title)}</strong><small>${esc(p.name)}</small><small>${p.copies} 份 · ${esc(p.unit)} · ${esc(p.material)}</small></span><i style="background:${p.color}"></i></button>`).join('')+'</div>';
    $('assembly-count').textContent=`${data.parts.length} 个文件 / 整份打印 ${data.parts.reduce((n,p)=>n+p.copies,0)} 次`;
    $('assembly-hardware').innerHTML=hardware(data.hardware);
  }
  async function load(config,colors){
    stop();const seq=++sequence;ready=false;data=null;selected=null;stage?.clear();
    $('assembly-stage').classList.remove('failed');$('assembly-fallback').hidden=false;$('assembly-fallback').textContent='正在核对型号与本地文件…';
    $('assembly-status').textContent='正在核对配置…';$('assembly-title').textContent='零件分解';
    for(const id of ['assembly-play','assembly-prev','assembly-next','assembly-gap','assembly-focus'])$(id).disabled=true;
    for(const id of ['assembly-parts','assembly-steps','assembly-instruction','assembly-step-hardware','assembly-hardware','assembly-count'])$(id).replaceChildren();
    $('assembly-document').open=false;$('assembly-pdf').removeAttribute('src');$('assembly-manual').href=`/api/docs/${config?.kind==='sustainer'?3:2}`;$('assembly-manual').textContent='查看对应官方手册 ↗';$('assembly-precision').textContent='';
    try{
      const response=await api('/api/assembly',{config,...(colors?{colors}:{})});if(seq!==sequence)return;data=response;
      $('assembly-title').textContent=data.title;$('assembly-precision').textContent=data.precision_reason;
      if(!data.supported){$('assembly-status').textContent=data.reason;$('assembly-fallback').textContent='当前配置尚未建立装配步骤。可继续选型、打印或查阅官方手册。';$('assembly-manual').href=`/api/docs/${data.doc}`;$('assembly-manual').textContent='查看对应官方手册 ↗';return;}
      inventory();showStep(0);$('assembly-play').disabled=false;
      $('assembly-status').textContent=data.note;
      try{
        if(!stage){const {AssemblyStage}=await import('/assembly-stage.js');if(seq!==sequence)return;stage=new AssemblyStage($('assembly-stage'),choose,message=>{ready=false;stop();$('assembly-gap').disabled=true;$('assembly-focus').disabled=true;$('assembly-status').textContent=message;});}
        const complete=await stage.load(data.parts,(n,total)=>{if(seq===sequence)$('assembly-fallback').textContent=`读取本地模型 ${n} / ${total}…`;});
        if(seq!==sequence||!complete)return;
        ready=true;$('assembly-fallback').hidden=true;$('assembly-gap').disabled=false;stage.layout(+$('assembly-gap').value/100);stage.fit();highlight();
      }catch(e){if(seq!==sequence)return;$('assembly-stage').classList.add('failed');$('assembly-fallback').textContent='三维预览不可用：'+e.message+' 仍可使用右侧步骤与手册。';$('assembly-status').textContent='真实几何加载未完成，未显示不完整装配。可重新选择示例重试。';}
    }catch(e){if(seq!==sequence)return;$('assembly-status').textContent=e.message;$('assembly-fallback').textContent='无法加载。请检查模型库连接后重新选择。';}
  }
  $('assembly-drawer').onclick=()=>load(samples.drawer);$('assembly-case').onclick=()=>load(samples.sustainer);
  $('assembly-current').onclick=()=>load(getConfig());
  $('assembly-prev').onclick=()=>{stop();showStep(step-1);};$('assembly-next').onclick=()=>{stop();showStep(step+1);};
  $('assembly-play').onclick=()=>{
    if(timer){stop();return;}if(!data?.steps.length)return;if(step===data.steps.length-1)showStep(0);
    $('assembly-play').textContent='暂停';$('assembly-play').setAttribute('aria-pressed','true');
    const tick=()=>{if(step>=data.steps.length-1){stop();return;}showStep(step+1);if(step===data.steps.length-1)stop();else timer=setTimeout(tick,6000);};timer=setTimeout(tick,6000);
  };
  $('assembly-steps').onclick=e=>{const b=e.target.closest('[data-assembly-step]');if(b){stop();showStep(+b.dataset.assemblyStep);}};
  $('assembly-parts').onclick=e=>{const b=e.target.closest('[data-assembly-part]');if(b)choose(b.dataset.assemblyPart);};
  $('assembly-fit').onclick=()=>stage?.fit();$('assembly-focus').onclick=()=>stage?.fit(selected);
  $('assembly-gap').oninput=()=>{const value=+$('assembly-gap').value;$('assembly-gap-value').value=value+'%';stage?.layout(value/100);};
  $('assembly-gap').onchange=()=>stage?.fit();
  $('assembly-document').ontoggle=()=>{if($('assembly-document').open&&data?.supported)$('assembly-pdf').src=$('assembly-manual').href;else $('assembly-pdf').removeAttribute('src');};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  host.addEventListener('assembly-close',()=>{stop();++sequence;stage?.clear();ready=false;data=null;$('assembly-pdf').removeAttribute('src');});
  host.addEventListener('assembly-open',()=>{stage?.resize();if(!data)load(samples.drawer);});
  window.addEventListener('assembly-request',e=>{openView('assembly');load(e.detail.config,e.detail.colors);});
}
