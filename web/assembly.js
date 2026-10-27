const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const samples={drawer:{kind:'drawer',family:'S',depth:3,height:1,drawers:[1],roof:'grid',key:'standard',interior:'none',labels:true,latches:1},sustainer:{kind:'sustainer',family:'S',depth:3,height:2,variant:'standard',split_roof:false,interior:'none',labels:true}};

export function initAssembly({api,getConfig,openView}){
  const host=$('assembly-view');let data=null,step=0,selected=null,stage=null,sequence=0,timer=null,ready=false,jointMode=false,jointFrame=null,jointTarget=null,autoSequence=false;
  const isSequence=()=>jointMode&&data?.joint?.motion==='sequence';
  host.innerHTML=`<div class="page-heading"><div><div class="eyebrow">UNDERSTAND EVERY PART / 装配演示</div><h1>看清零件，<span>一步步装起来。</span></h1><p>从本机模型读取真实几何，对照中文步骤与官方图示。</p></div><span class="pill">02 / 零件与步骤</span></div>
  <div class="assembly-presets"><button id="assembly-drawer" class="outline-button">S3 · 1F 标准抽屉</button><button id="assembly-case" class="outline-button">S3 · 2F 翻盖箱</button><button id="assembly-current" class="text-button">使用配置页的选型 ↗</button></div>
  <div id="assembly-status" class="notice" role="status" aria-live="polite">选择一个示例开始。</div>
  <div class="assembly-layout"><section class="panel assembly-viewport"><div class="assembly-tools"><strong id="assembly-title">零件分解</strong><div><button id="assembly-fit" class="text-button">视角复位</button><button id="assembly-focus" class="text-button" disabled>聚焦选中</button><button id="assembly-labels" class="text-button" aria-pressed="true">隐藏标签</button><button id="assembly-xray" class="text-button" aria-pressed="false" hidden>外壳透视</button></div></div>
  <div id="assembly-stage"><p id="assembly-fallback">三维视图按需加载；下方步骤和零件清单可独立使用。</p></div>
  <div class="assembly-slider"><label for="assembly-gap">分解间距</label><input id="assembly-gap" type="range" min="0" max="100" value="35" disabled><output id="assembly-gap-value">35%</output></div>
  <div class="assembly-joint-controls"><label for="assembly-joint-select">装配视图</label><select id="assembly-joint-select" disabled aria-label="选择装配视图"><option>等待模型核对</option></select><button id="assembly-joint" class="outline-button" disabled>查看合拢演示</button><button id="assembly-joint-play" class="primary-button" hidden>播放合拢</button><p id="assembly-joint-note" class="field-description">仅当本地文件与已核对版本一致时开放装配定位。</p></div>
  <div class="assembly-disclosure" id="assembly-disclosure-text"><strong>原始零件排布</strong><p>当前保持文件中的打印排布。选择装配视图可查看安装位置和步骤；弹性变形示意及接触限制会另行标明。</p><p id="assembly-precision"></p></div></section>
  <aside class="panel assembly-guide"><div class="eyebrow">FOLLOW THE MANUAL</div><h2>安装步骤</h2><div class="assembly-playback"><button id="assembly-prev" class="outline-button" disabled aria-label="上一步">←</button><button id="assembly-play" class="primary-button" disabled>播放步骤</button><button id="assembly-next" class="outline-button" disabled aria-label="下一步">→</button></div><div id="assembly-steps"></div>
  <article id="assembly-instruction" aria-live="polite"></article><div id="assembly-step-hardware"></div><a id="assembly-manual" class="text-button" target="_blank" rel="noopener noreferrer">打开此步官方图示 ↗</a><p id="assembly-playback-note" class="field-description">每步停留 6 秒，随时暂停查看。官方 PDF 由本机读取。</p></aside></div>
  <section class="panel assembly-inventory"><div class="assembly-inventory-heading"><div><span class="eyebrow">PART INDEX</span><h2>点击零件，互相定位</h2></div><span id="assembly-count"></span></div><div id="assembly-parts"></div><details><summary>整套五金与核对依据</summary><div id="assembly-hardware"></div></details><details id="assembly-document"><summary>在工作台中查看本步官方手册</summary><iframe id="assembly-pdf" title="本机官方装配手册" loading="lazy"></iframe></details></section>`;
  function stop(){clearTimeout(timer);timer=null;if(autoSequence){autoSequence=false;stopJoint(false);}$('assembly-play').textContent='播放步骤';$('assembly-play').setAttribute('aria-pressed','false');}
  function jointButton(){const b=$('assembly-joint-play'),motion=data?.joint?.motion,verbs=motion==='drawer'?['推回','抽出']:motion==='hinge'?['合盖','开盖']:motion==='latch'?['收起锁扣','翻开锁扣']:motion==='sequence'?['安装本步','展开本步']:['合拢','拆开'];b.textContent=jointFrame?'暂停动画':jointTarget!==null?'继续'+verbs[jointTarget===0?0:1]:'播放'+verbs[+$('assembly-gap').value>0?0:1];b.setAttribute('aria-pressed',String(!!jointFrame));}
  function stopJoint(reset=true){cancelAnimationFrame(jointFrame);jointFrame=null;if(reset)jointTarget=null;jointButton();}
  function setGap(value){value=Math.max(jointMode?(data?.joint?.min_gap||0):0,Math.min(100,value));$('assembly-gap').value=value;const motion=jointMode&&data?.joint?.motion,start=data?.joint?.angle_start||0;$('assembly-gap-value').value=motion==='drawer'?Math.round(value*data.joint.stroke_mm/100)+' mm':motion==='hinge'?Math.round(Math.max(0,(value/100-start)/(1-start))*data.joint.angle_deg)+'°':Math.round(value)+'%';stage?.layout(value/100);}
  function jointAction(){return data?.joint?.motion==='sequence'?'开始分步安装':data?.joint?.mode==='composition'?'查看'+data.joint.title:data?.joint?.motion==='drawer'?'查看主体抽拉':data?.joint?.status==='orientation_only'?'查看安装朝向':'查看合拢演示';}
  function toggleJoint(on){
    if(on&&(!ready||!data?.joint))return;stop();stopJoint();jointMode=on;selected=null;$('assembly-gap').min=on?(data.joint.min_gap||0):0;
    try{stage?.setJoint(on?data.joint:null);}catch(error){jointMode=false;toggleJoint(false);$('assembly-status').textContent='装配定位不可用：'+error.message+' 可返回原始零件或查阅手册。';return;}
    if(isSequence())step=0;setGap(on?100:35);
    $('assembly-joint').textContent=on?'返回整套零件':jointAction();$('assembly-joint-play').hidden=!on||data.joint?.status==='orientation_only';$('assembly-joint-play').disabled=data.joint?.status==='orientation_only';
    $('assembly-xray').hidden=!on||data.joint?.mode!=='composition';$('assembly-xray').setAttribute('aria-pressed','false');
    $('assembly-title').textContent=on?data.joint.title+(data.joint.mode==='composition'||data.joint.status==='orientation_only'?'':' · 子装配'):data.title;
    $('assembly-status').textContent=on?(data.joint.mode==='composition'?data.joint.note:data.joint.motion==='drawer'?`主体抽拉查看范围 0–${data.joint.stroke_mm} mm；完整锁定与限位机构尚待核对。`:data.joint.status==='orientation_only'?'安装朝向参考：保留安装前距离，弹簧的弹性接合尚待核对。':`当前展示${data.joint.title}；滑块 0% 为合拢位置，100% 为拆开查看。`):data.note;
    $('assembly-selected').textContent=on?`此视图包含${data.joint.display_count??data.joint.instances.reduce((n,i)=>n+(i.components?.length||1),0)}个零件；点击标签与清单互相定位。`:'在画布或下方清单中选择零件；小零件可用“聚焦选中”放大查看。';
    host.querySelector('.assembly-guide h2').textContent=isSequence()?'分步安装':on?'装配说明':'安装步骤';
    for(const el of host.querySelectorAll('.assembly-playback, #assembly-steps, #assembly-playback-note'))el.hidden=on&&!isSequence();
    $('assembly-joint-note').textContent=on?(data.joint.instances.length===2?'本视图仅展示旋钮与盖；未做实物压装测试。完整锁定机构仍待核对。':data.joint.note):'仅当本地文件与已核对版本一致时开放子装配。';
    $('assembly-disclosure-text').hidden=on;
    $('assembly-gap').min=on?(data.joint.min_gap||0):0;$('assembly-gap').labels[0].textContent=on?(isSequence()?'本步分解程度':data.joint.motion==='hinge'?'开盖进度':data.joint.motion==='drawer'?'抽出距离':data.joint.status==='orientation_only'?'安装前间距':'爆炸程度'):'分解间距';
    showStep(step);$('assembly-play').disabled=on&&!isSequence();$('assembly-prev').disabled=(on&&!isSequence())||step===0;$('assembly-next').disabled=(on&&!isSequence())||step===data.steps.length-1;
    if(on&&!isSequence()){$('assembly-instruction').innerHTML=`<span class="eyebrow">${data.joint.mode==='composition'?'ASSEMBLY / 参考定位':data.joint.motion==='drawer'?'MOTION / 主体抽拉几何核对':data.joint.status==='orientation_only'?'ORIENTATION / 安装朝向参考':'SUBASSEMBLY / 数字几何核对'}</span><h3>${esc(data.joint.title)}</h3>${(data.joint.instructions||[]).map(text=>`<p>${esc(text)}</p>`).join('')}<p>播放中可暂停；拖动画布可旋转查看。</p>`;$('assembly-step-hardware').innerHTML=data.joint.mode==='composition'?`<p class="field-description">${esc(data.joint.limits)}</p>`:data.joint.status==='orientation_only'?'<p class="field-description">一份 Springs.stl 含左右两件；打印清单仍按一份文件计算。</p>':'<p class="field-description">数字几何核对不能代替连续碰撞、打印公差或实物压装验证。</p>';$('assembly-manual').href=`/api/docs/${data.joint.doc||2}#page=${data.joint.page||1}`;$('assembly-manual').textContent=`官方${data.joint.doc===3?'翻盖箱':'抽屉'}装配手册 · 第 ${data.joint.page||1} 页 ↗`;}
    if($('assembly-document').open)$('assembly-pdf').src=$('assembly-manual').href;
    jointButton();stage?.fit();
  }
  function hardware(items){return items.length?items.map(h=>`<div class="assembly-bolt"><strong>${esc(h.name)} × ${h.quantity}</strong><span>${esc(h.reason)}</span><small>${esc(h.source)} · ${esc(h.status)}</small></div>`).join(''):'<p class="field-description">本步无另列外购五金；打印件见高亮清单。</p>';}
  function highlight(){const ids=jointMode&&!isSequence()?data.joint.instances.map(i=>i.id):data?.steps[step]?.parts||[];stage?.emphasize(ids,selected);document.querySelectorAll('[data-assembly-part]').forEach(b=>{b.classList.toggle('selected',b.dataset.assemblyPart===selected);b.classList.toggle('active',ids.includes(b.dataset.assemblyPart));b.setAttribute('aria-pressed',String(b.dataset.assemblyPart===selected));});$('assembly-focus').disabled=!ready||!selected;}
  function choose(id){if(jointMode&&!data.joint.instances.some(i=>i.id===id))toggleJoint(false);if(isSequence()){const first=Math.min(...data.joint.composition.find(p=>p.id===id).elements.map(e=>e.step));if(first>step){stop();stopJoint();showStep(first);}}selected=id;highlight();const part=data?.parts.find(p=>p.id===id);if(part){$('assembly-selected').textContent=`已选：${part.title} · ${part.copies} 份整份 STL · ${part.unit}`;}}
  function showStep(index){
    if(!data?.steps.length)return;step=Math.max(0,Math.min(index,data.steps.length-1));const s=data.steps[step];
    $('assembly-steps').innerHTML=data.steps.map((s,i)=>`<button type="button" data-assembly-step="${i}" ${i===step?'aria-current="step"':''}><span>${String(i+1).padStart(2,'0')}</span>${esc(s.title)}</button>`).join('');
    $('assembly-instruction').innerHTML=`<span class="eyebrow">STEP ${step+1} / ${data.steps.length}</span><h3>${esc(s.title)}</h3><p>${esc(s.text)}</p>${isSequence()?`<p class="field-description">${esc(data.joint.step_notes?.[step]||data.joint.limits)}</p>`:''}`;
    $('assembly-step-hardware').innerHTML=hardware(s.hardware);$('assembly-manual').href=`/api/docs/${s.doc}#page=${s.page}`;$('assembly-manual').textContent=`官方${s.doc===1?'总说明':'装配手册'} · 第 ${s.page} 页 ↗`;
    if($('assembly-document').open)$('assembly-pdf').src=$('assembly-manual').href;
    $('assembly-prev').disabled=step===0;$('assembly-next').disabled=step===data.steps.length-1;
    if(isSequence()){setGap(100);stage?.setAssemblyStep?.(step);jointButton();$('assembly-playback-note').textContent='滑块控制本步安装。播放步骤可连续安装，随时暂停；官方PDF由本机读取。';}
    else $('assembly-playback-note').textContent='每步停留6秒，随时暂停查看。官方PDF由本机读取。';
    highlight();
  }
  function inventory(){
    $('assembly-parts').innerHTML='<p id="assembly-selected" role="status">在画布或下方清单中选择零件；小零件可用“聚焦选中”放大查看。</p><div class="assembly-part-grid">'+data.parts.map((p,i)=>`<button data-assembly-part="${p.id}" type="button"><span class="assembly-part-number">${String(i+1).padStart(2,'0')}</span><span><strong>${esc(p.title)}</strong><small>${esc(p.name)}</small><small>${p.copies} 份 · ${esc(p.unit)} · ${esc(p.material)}</small></span><i style="background:${p.color}"></i></button>`).join('')+'</div>';
    $('assembly-count').textContent=`${data.parts.length} 个文件 / 整份打印 ${data.parts.reduce((n,p)=>n+p.copies,0)} 次`;
    $('assembly-hardware').innerHTML=hardware(data.hardware);
  }
  async function load(config,colors){
    $('assembly-xray').hidden=true;$('assembly-xray').setAttribute('aria-pressed','false');
    host.querySelector('.assembly-guide h2').textContent='安装步骤';for(const el of host.querySelectorAll('.assembly-playback, #assembly-steps, #assembly-playback-note'))el.hidden=false;
    stop();stopJoint();jointMode=false;$('assembly-joint').disabled=true;$('assembly-joint').textContent='查看合拢演示';$('assembly-joint-select').disabled=true;$('assembly-joint-select').innerHTML='<option>等待模型核对</option>';$('assembly-joint-play').hidden=true;$('assembly-disclosure-text').hidden=false;$('assembly-gap').min=0;$('assembly-gap').labels[0].textContent='分解间距';$('assembly-joint-note').textContent='仅当本地文件与已核对版本一致时开放子装配。';const seq=++sequence;ready=false;data=null;selected=null;stage?.clear();
    $('assembly-stage').classList.remove('failed');$('assembly-fallback').hidden=false;$('assembly-fallback').textContent='正在核对型号与本地文件…';
    $('assembly-status').textContent='正在核对配置…';$('assembly-title').textContent='零件分解';
    for(const id of ['assembly-play','assembly-prev','assembly-next','assembly-gap','assembly-focus'])$(id).disabled=true;
    for(const id of ['assembly-parts','assembly-steps','assembly-instruction','assembly-step-hardware','assembly-hardware','assembly-count'])$(id).replaceChildren();
    $('assembly-document').open=false;$('assembly-pdf').removeAttribute('src');$('assembly-manual').href=`/api/docs/${config?.kind==='sustainer'?3:2}`;$('assembly-manual').textContent='查看对应官方手册 ↗';$('assembly-precision').textContent='';
    try{
      const response=await api('/api/assembly',{config,...(colors?{colors}:{})});if(seq!==sequence)return;data=response;
      $('assembly-title').textContent=data.title;$('assembly-precision').textContent=data.precision_reason;
      if(!data.supported){$('assembly-status').textContent=data.reason;$('assembly-fallback').textContent='当前配置尚未建立装配步骤。可继续选型、打印或查阅官方手册。';$('assembly-manual').href=`/api/docs/${data.doc}`;$('assembly-manual').textContent='查看对应官方手册 ↗';return;}
      data.joints=data.joints??(data.joint?[data.joint]:[]);data.joint=data.joints[0]??null;
      $('assembly-joint-select').innerHTML=data.joints.length?data.joints.map(p=>`<option value="${esc(p.id)}">${esc(p.title)}</option>`).join(''):'<option>当前套件无已核对子装配</option>';
      inventory();showStep(0);$('assembly-play').disabled=false;
      $('assembly-status').textContent=data.note;
      try{
        if(!stage){const {AssemblyStage}=await import('/assembly-stage.js');if(seq!==sequence)return;stage=new AssemblyStage($('assembly-stage'),choose,message=>{ready=false;stop();stopJoint();if(jointMode)toggleJoint(false);$('assembly-joint').disabled=true;$('assembly-joint-select').disabled=true;$('assembly-gap').disabled=true;$('assembly-focus').disabled=true;$('assembly-status').textContent=message;});}
        const complete=await stage.load(data.parts,(n,total)=>{if(seq===sequence)$('assembly-fallback').textContent=`读取本地模型 ${n} / ${total}…`;},{instances:data.joints.flatMap(p=>p.instances)});
        if(seq!==sequence||!complete)return;
        ready=true;$('assembly-joint').textContent=jointAction();$('assembly-joint').disabled=!data.joint;$('assembly-joint-select').disabled=!data.joint;$('assembly-fallback').hidden=true;$('assembly-gap').disabled=false;stage.layout(+$('assembly-gap').value/100);stage.fit();highlight();
      }catch(e){if(seq!==sequence)return;$('assembly-stage').classList.add('failed');$('assembly-fallback').textContent='三维预览不可用：'+e.message+' 仍可使用右侧步骤与手册。';$('assembly-status').textContent='真实几何加载未完成，未显示不完整装配。可重新选择示例重试。';}
    }catch(e){if(seq!==sequence)return;$('assembly-status').textContent=e.message;$('assembly-fallback').textContent='无法加载。请检查模型库连接后重新选择。';}
  }
  $('assembly-drawer').onclick=()=>load(samples.drawer);$('assembly-case').onclick=()=>load(samples.sustainer);
  $('assembly-current').onclick=()=>load(getConfig());
  $('assembly-prev').onclick=()=>{stop();stopJoint();showStep(step-1);};$('assembly-next').onclick=()=>{stop();stopJoint();showStep(step+1);};
  $('assembly-play').onclick=()=>{
    if(isSequence()){
      if(autoSequence){stop();return;}if(step===data.steps.length-1&&+$('assembly-gap').value===0)showStep(0);
      autoSequence=true;$('assembly-play').textContent='暂停流程';$('assembly-play').setAttribute('aria-pressed','true');startJoint(0);return;
    }
    if(timer){stop();return;}if(!data?.steps.length)return;if(step===data.steps.length-1)showStep(0);
    $('assembly-play').textContent='暂停';$('assembly-play').setAttribute('aria-pressed','true');
    const tick=()=>{if(step>=data.steps.length-1){stop();return;}showStep(step+1);if(step===data.steps.length-1)stop();else timer=setTimeout(tick,6000);};timer=setTimeout(tick,6000);
  };
  $('assembly-steps').onclick=e=>{const b=e.target.closest('[data-assembly-step]');if(b){if(jointMode&&!isSequence())toggleJoint(false);stop();stopJoint();showStep(+b.dataset.assemblyStep);}};
  $('assembly-parts').onclick=e=>{const b=e.target.closest('[data-assembly-part]');if(b)choose(b.dataset.assemblyPart);};
  $('assembly-fit').onclick=()=>stage?.fit();$('assembly-focus').onclick=()=>stage?.fit(selected);
  $('assembly-labels').onclick=()=>{const show=$('assembly-labels').getAttribute('aria-pressed')!=='true';$('assembly-labels').setAttribute('aria-pressed',String(show));$('assembly-labels').textContent=show?'隐藏标签':'显示标签';stage?.setLabelsVisible?.(show);};
  $('assembly-xray').onclick=()=>{const on=$('assembly-xray').getAttribute('aria-pressed')!=='true';$('assembly-xray').setAttribute('aria-pressed',String(on));stage?.setXray?.(on);};
  $('assembly-joint').onclick=()=>toggleJoint(!jointMode);
  $('assembly-joint-select').onchange=()=>{if(!ready)return;const profile=data.joints.find(p=>p.id===$('assembly-joint-select').value);if(!profile)return;data.joint=profile;toggleJoint(true);};
  function finishJoint(){
    jointFrame=null;jointTarget=null;jointButton();
    if(autoSequence&&isSequence()){
      if(step===data.steps.length-1){stop();return;}
      timer=setTimeout(()=>{timer=null;if(!autoSequence||!isSequence())return;showStep(step+1);startJoint(0);},600);
    }
  }
  function startJoint(target=null){
    if(!jointMode||!ready||data.joint.status==='orientation_only')return;
    stage?.fit(undefined,true);
    const from=+$('assembly-gap').value,to=target??jointTarget??(from>0?0:100),start=performance.now();jointTarget=to;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches){setGap(to);finishJoint();return;}
    const duration=Math.max(300,1800*Math.abs(to-from)/100);
    const tick=now=>{const t=Math.min(1,(now-start)/duration);setGap(from+(to-from)*t*t*(3-2*t));if(t<1)jointFrame=requestAnimationFrame(tick);else finishJoint();};
    jointFrame=requestAnimationFrame(tick);jointButton();
  }
  $('assembly-joint-play').onclick=()=>{if(autoSequence){stop();return;}if(jointFrame){stopJoint(false);return;}startJoint();};
  $('assembly-gap').oninput=()=>{stop();stopJoint();setGap(+$('assembly-gap').value);jointButton();};
  $('assembly-gap').onchange=()=>stage?.fit();
  $('assembly-document').ontoggle=()=>{if($('assembly-document').open&&data?.supported)$('assembly-pdf').src=$('assembly-manual').href;else $('assembly-pdf').removeAttribute('src');};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();stopJoint(false);}});
  host.addEventListener('assembly-close',()=>{stop();stopJoint();++sequence;stage?.clear();ready=false;data=null;$('assembly-pdf').removeAttribute('src');});
  host.addEventListener('assembly-open',()=>{stage?.resize();if(!data)load(samples.drawer);});
  window.addEventListener('assembly-request',e=>{openView('assembly');load(e.detail.config,e.detail.colors);});
}
