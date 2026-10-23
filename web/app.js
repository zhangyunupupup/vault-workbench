import { MeshViewer } from '/viewer.js';

const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = n => n >= 1024 ** 3 ? (n / 1024 ** 3).toFixed(2) + ' GB' : n >= 1024 ** 2 ? (n / 1024 ** 2).toFixed(1) + ' MB' : Math.ceil(n / 1024) + ' KB';
const kindLabels = { drawer: '抽屉', sustainer: '翻盖箱', mod: '改装配件' };
const storageKey = 'vault-workbench-plan-v1';
let catalog = null, token = '', kind = 'drawer', family = 'S', currentPreview = null;
let previewSequence = 0, previewTimer, toastTimer, libraryLimit = 70, expanded = false, currentJob = null;
let presetDefaults = {}, presets = [];
let queue = { configs: [], manual: [] };
try {
  const saved = JSON.parse(localStorage.getItem(storageKey));
  if (saved && Array.isArray(saved.configs) && Array.isArray(saved.manual)) queue = saved;
} catch { /* Start with an empty plan if browser storage was cleared or corrupted. */ }
const viewer = new MeshViewer($('mesh-canvas'));
let meshSequence = 0;

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Vault-Token': token }, body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作未完成，请重试。');
  return data;
}
function toast(text, error = false) {
  clearTimeout(toastTimer); $('toast').textContent = text; $('toast').classList.toggle('error', error); $('toast').classList.remove('hidden');
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 6500 : 3200);
}
function show(id, visible) { $(id).classList.toggle('hidden', !visible); }
function saveQueue() {
  try { localStorage.setItem(storageKey, JSON.stringify(queue)); } catch { toast('浏览器未能保存计划，当前会话仍可导出。', true); }
  $('plan-count').textContent = queue.configs.length + queue.manual.length;
}
function view(name) {
  for (const item of document.querySelectorAll('.view')) item.classList.toggle('hidden', item.id !== name + '-view');
  for (const item of document.querySelectorAll('.nav-item')) item.classList.toggle('active', item.dataset.view === name);
  $('page-name').textContent = { configure: '配置打印', library: '模型库', manuals: '中文装配指引', history: '导出记录' }[name];
  history.replaceState(null, '', '#' + name);
  if (name === 'library') renderLibrary();
  if (name === 'history') loadHistory();
  window.scrollTo({ top: 0, behavior: 'instant' });
}
function fillSelect(id, options, preferred) {
  const select = $(id), old = preferred ?? select.value;
  select.replaceChildren(...options.map(([value, label]) => {
    const option = document.createElement('option'); option.value = value; option.textContent = label; return option;
  }));
  if (options.some(x => String(x[0]) === String(old))) select.value = old;
}
function modelsForKind() { return (catalog?.models || []).filter(m => m.kind === kind); }
function currentModel() { return modelsForKind().find(m => m.family === family && m.depth === +$('depth').value); }
function modelFiles() { const m = currentModel(); return catalog?.files.filter(f => f.kind === kind && f.model === m?.model) || []; }
function presetConfig(preset) { return structuredClone({ ...presetDefaults, ...preset.config }); }
function presetAvailable(preset) {
  const c = presetConfig(preset);
  return Boolean(catalog?.models.some(m => m.kind === c.kind && m.family === c.family && m.depth === c.depth && m.verified && m.heights.includes(c.height)));
}
function renderPresets() {
  $('preset-choices').replaceChildren(...presets.map(preset => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'preset-chip'; button.dataset.preset = preset.id;
    button.disabled = !presetAvailable(preset); button.setAttribute('aria-pressed', 'false');
    button.title = button.disabled ? '当前模型库没有此型号，请先连接对应的模型库。' : preset.summary;
    button.innerHTML = `<strong>${escapeHTML(preset.title)}</strong><small>${escapeHTML(preset.model)}</small>`;
    button.addEventListener('click', () => applyPreset(preset)); return button;
  }));
}
function refreshPresetSelection() {
  if (!presets.length) return;
  const current = config();
  const active = presets.find(p => presetAvailable(p) && Object.entries(presetConfig(p)).every(([key, value]) => JSON.stringify(current[key]) === JSON.stringify(value)));
  for (const button of $('preset-choices').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.preset === active?.id));
  $('preset-description').innerHTML = active ? `<strong>${escapeHTML(active.title)}</strong> · ${escapeHTML(active.summary)}` : '当前为自定义配置。也可以点选常用方案，核对零件后加入打印计划。';
}
function applyPreset(preset) {
  if (!presetAvailable(preset)) return;
  const c = presetConfig(preset);
  kind = c.kind; family = c.family; expanded = false;
  document.querySelectorAll('[data-kind]').forEach(b => b.classList.toggle('selected', b.dataset.kind === kind));
  refreshChoices();
  $('depth').value = c.depth; refreshChoices();
  $('height').value = c.height; refreshOptions();
  const fields = { 'drawer-layout': JSON.stringify(c.drawers), roof: c.roof, key: c.key, variant: c.variant,
    interior: c.interior, baseplate: c.baseplate, 'divider-height': c.divider_height,
    'width-dividers': c.width_dividers, 'depth-dividers': c.depth_dividers,
    latches: c.latches, mount: c.mount, base: c.base, quantity: c.quantity };
  for (const [id, value] of Object.entries(fields)) $(id).value = value;
  for (const [id, key] of [['split-roof', 'split_roof'], ['top-handle', 'top_handle'], ['rails', 'rails'], ['labels', 'labels'], ['wheels', 'wheels']]) $(id).checked = c[key];
  refreshVisibility(); schedulePreview();
}
function refreshChoices() {
  if (!catalog) return;
  const families = ['S', 'M', 'L', 'XL', 'L²', 'XL²'].filter(f => modelsForKind().some(m => m.family === f));
  if (!families.includes(family)) family = families[0];
  $('family-choices').replaceChildren(...families.map(f => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'choice-button';
    button.classList.toggle('selected', f === family); button.classList.toggle('special', f.includes('²'));
    button.setAttribute('aria-pressed', String(f === family)); button.textContent = f;
    button.addEventListener('click', () => { family = f; refreshChoices(); }); return button;
  }));
  fillSelect('depth', modelsForKind().filter(m => m.family === family).map(m => [m.depth, `${m.depth} 格深度`]).sort((a, b) => a[0] - b[0]));
  const m = currentModel();
  fillSelect('height', (m?.heights || []).map(h => [h, `${h}F · ${h === 1 ? '浅' : h === 2 ? '中' : '高'}款`]));
  refreshOptions();
}
function refreshOptions() {
  const m = currentModel(); if (!m) return;
  const height = +$('height').value, depth = +$('depth').value, files = modelFiles();
  const verified = m.verified && !(kind === 'drawer' && family === 'XL');
  show('special-warning', !verified);
  $('special-warning').textContent = family.includes('²') ? '双列外壳的配套规则待核对，可在模型库选择文件补打。' : 'XL 抽屉的双锁与后板配方待核对，可在模型库选择文件补打。';
  show('drawer-fields', kind === 'drawer'); show('drawer-extras', kind === 'drawer'); show('sustainer-fields', kind === 'sustainer');
  const layouts = height === 1 ? [[1]] : height === 2 ? [[2], [1, 1]] : [[4], [2, 2], [2, 1, 1], [1, 2, 1], [1, 1, 2], [1, 1, 1, 1]];
  fillSelect('drawer-layout', layouts.map(layout => [JSON.stringify(layout), layout.length === 1 ? `单内抽 · ${layout[0]}F` : `${layout.length} 个内抽 · ${layout.map(x => x + 'F').join(' + ')}`]));
  const roofTypes = [['none', '不加顶盖 · 用于中间层'], ['grid', 'Gridfinity 网格顶盖', 'Grid Roof'], ['table', '平面顶盖', 'Table Roof'], ['bowl', '托盘顶盖', 'Bowl Roof'], ['under_table', '桌下安装顶盖', 'Under Table Mount Roof'], ['heavy', '承重顶盖', 'Heawyweight Roof']];
  fillSelect('roof', roofTypes.filter(([key, label, match]) => key === 'none' || files.some(f => f.name.includes(match))).map(x => x.slice(0, 2)), $('roof').value || 'grid');
  fillSelect('variant', family === 'S' || family === 'M' ? [['standard', '标准箱体']] : [['flat', '空箱 · Flat'], ['dividers', '网格分隔 · Dividers'], ['sealed', '封闭分隔 · Sealed']]);
  show('split-roof-row', depth >= 6);
  if (depth < 6) $('split-roof').checked = false;
  const allPlain = [['none', '留空 · 自由放置'], ['gridfinity', 'Gridfinity 网格底板'], ['dividers', '可拆分隔片']];
  fillSelect('interior', allPlain);
  const baseplates = [['plain', '标准底板', `${m.model} Baseplate.stl`], ['one', '带单提手底板', `${m.model} Baseplate_With 1 Handle.stl`], ['two', '带双提手底板', `${m.model} Baseplate_With 2 Handles.stl`]];
  fillSelect('baseplate', baseplates.filter(x => files.some(f => f.name.toLowerCase() === x[2].toLowerCase())).map(x => x.slice(0, 2)));
  fillSelect('base', [['none', '不加底座'], ['whole', '完整底座'], ...(depth >= 6 ? [['split', '分体底座']] : [])]);
  refreshVisibility(); schedulePreview();
}
function refreshVisibility() {
  const interior = $('interior').value, caseSM = kind === 'sustainer' && ['S', 'M'].includes(family);
  show('baseplate-fields', interior === 'gridfinity' && kind === 'drawer');
  show('divider-fields', interior === 'dividers'); show('divider-height-row', kind === 'drawer');
  show('depth-divider-field', !caseSM);
  // CSS-hidden controls still participate in native form validation unless disabled.
  // Recompute from all ancestor groups so nested hidden options stay disabled.
  for (const field of $('config-form').querySelectorAll('input, select')) {
    field.disabled = Boolean(field.closest('.hidden'));
  }
  $('latches').min = kind === 'drawer' && $('roof').value === 'under_table' ? '1' : '0';
  const layout = JSON.parse($('drawer-layout').value || '[1]');
  $('drawer-description').textContent = layout.length > 1 ? `${layout.length} 个内抽共用一个外壳；自动加入锁定齿条。` : '一套外壳，一个内抽。';
  $('rails').disabled = kind !== 'drawer' || layout.length > 1;
  if (kind === 'drawer' && $('roof').value !== 'grid') { $('top-handle').checked = false; $('top-handle').disabled = true; }
  else $('top-handle').disabled = kind !== 'drawer';
  $('wheels').disabled = $('base').value === 'none';
  if ($('wheels').disabled) $('wheels').checked = false;
  const h = +$('height').value;
  $('model-pill').textContent = `${currentModel()?.model || ''} · ${h}F`;
  $('product-name').textContent = kind === 'drawer' ? '桌面小物，各得其所。' : '打开下一份井然有序。';
  $('product-subtitle').textContent = `${family} 系列${kindLabels[kind]} · ${$('depth').value} 格深度 · ${h}F 高度`;
  $('product-image').src = `/assets/${kind === 'drawer' ? 'drawer' : 'sustainer'}.jpg`;
  $('product-image').alt = `VAULT ${kindLabels[kind]}官方示意，非当前配置的精确渲染`;
  $('product-image').classList.toggle('case-image', kind === 'sustainer');
}
function config() {
  return { kind, family, depth: +$('depth').value, height: +$('height').value, quantity: +$('quantity').value,
    drawers: JSON.parse($('drawer-layout').value || '[1]'), roof: $('roof').value, key: $('key').value,
    variant: $('variant').value, split_roof: $('split-roof').checked,
    interior: $('interior').value, baseplate: $('baseplate').value || 'plain',
    divider_height: $('divider-height').value, width_dividers: +$('width-dividers').value, depth_dividers: +$('depth-dividers').value,
    top_handle: $('top-handle').checked, rails: $('rails').checked, labels: $('labels').checked,
    latches: +$('latches').value, mount: kind === 'drawer' ? $('mount').value : 'none', base: $('base').value, wheels: $('wheels').checked };
}
function schedulePreview() {
  refreshPresetSelection();
  clearTimeout(previewTimer); ++previewSequence; currentPreview = null; $('add-plan').disabled = true;
  $('preview-count').textContent = '匹配中'; show('preview-loading', true);
  previewTimer = setTimeout(updatePreview, 160);
}
async function updatePreview() {
  const seq = ++previewSequence;
  if (!catalog) { $('preview-loading').textContent = '连接模型库后即可开始配置。'; return; }
  show('preview-loading', true); show('preview-error', false);
  try {
    const result = await api('/api/preview', { configs: [config()] });
    if (seq !== previewSequence) return;
    currentPreview = result; $('add-plan').disabled = false;
    $('preview-count').textContent = `${result.file_count} 个文件`;
    $('preview-summary').innerHTML = summaryHTML(result);
    renderPreviewParts();
    $('preview-notes').innerHTML = result.notes.map(n => `<div class="notice">${escapeHTML(n)}</div>`).join('');
  } catch (e) {
    if (seq !== previewSequence) return;
    currentPreview = null; $('preview-count').textContent = '需核对'; $('preview-summary').replaceChildren(); $('preview-parts').replaceChildren(); $('preview-notes').replaceChildren();
    $('preview-error').textContent = e.message; show('preview-error', true);
  } finally { if (seq === previewSequence) show('preview-loading', false); }
}
function summaryHTML(result) {
  return `<div class="preview-summary"><div><strong>${result.file_count}</strong>个文件</div><div><strong>${result.copies}</strong>次打印</div><span class="muted">源文件 ${bytes(result.bytes)}</span></div>`;
}
function partsHTML(parts) {
  return parts.map(p => `<div class="part-row"><span class="part-file-icon">STL</span><div class="part-info"><strong>${escapeHTML(p.title)}${p.optional ? '<span class="optional-tag">选配</span>' : ''}${p.supports ? '<span class="tag-support">开支撑</span>' : ''}</strong><small title="${escapeHTML(p.relative)}">${escapeHTML(p.name)}</small></div><span class="part-copy" title="${escapeHTML(p.unit)}">× ${p.copies}</span><button class="part-preview" data-mesh="${p.id}" aria-label="预览 ${escapeHTML(p.name)}">↗</button><button class="part-preview" data-evidence="${p.id}" aria-label="查看 ${escapeHTML(p.name)} 的依据">ⓘ</button></div>`).join('');
}
function renderPreviewParts() {
  if (!currentPreview) return;
  $('preview-parts').innerHTML = partsHTML(currentPreview.parts.slice(0, expanded ? undefined : 6)) + (currentPreview.parts.length > 6 ? `<button class="expand-parts" id="expand-parts">${expanded ? '收起清单 ↑' : `展开全部 ${currentPreview.file_count} 个文件 ↓`}</button>` : '');
  $('expand-parts')?.addEventListener('click', () => { expanded = !expanded; renderPreviewParts(); });
}
function queueTitle(c) { return `${c.family.replace('²', '')}${c.depth}${c.family.includes('²') ? '²' : ''} · ${c.height}F ${kindLabels[c.kind]} × ${c.quantity}`; }
function describeConfig(c) {
  const interior = { none: '留空', gridfinity: 'Gridfinity 底板', dividers: '分隔片' }[c.interior];
  return [c.kind === 'drawer' ? c.drawers.map(x => x + 'F').join(' + ') + ' 内抽' : ({standard:'标准箱体',flat:'空箱',dividers:'网格分隔箱体',sealed:'封闭分隔箱体'}[c.variant] || ''), interior, c.wheels ? '双轮底座' : ''].filter(Boolean).join(' / ');
}
let queuePreview = null, queueSequence = 0;
async function renderQueue() {
  saveQueue();
  $('plan-items').innerHTML = queue.configs.map((c, i) => `<div class="plan-item"><div><strong>${escapeHTML(queueTitle(c))}</strong><small>${escapeHTML(describeConfig(c))}</small></div><button class="remove-item" data-remove-config="${i}" aria-label="移除此配置">×</button></div>`).join('') + queue.manual.map((m, i) => {
    const file = catalog?.files.find(f => f.id === m.id);
    return `<div class="plan-item"><div><strong>${escapeHTML(file?.title || '文件不在当前模型库')}</strong><small>${escapeHTML(file?.name || m.id)} · 独立补打</small></div><input type="number" value="${m.copies}" min="1" max="1000" data-manual-copies="${i}" aria-label="整份STL打印次数"><button class="remove-item" data-remove-manual="${i}" aria-label="移除此补打零件">×</button></div>`;
  }).join('');
  if (!queue.configs.length && !queue.manual.length) $('plan-items').innerHTML = '<div class="empty-state"><h2>从一个模块开始。</h2><p>配置好箱子后加入计划，或者到模型库选择要补打的零件。</p></div>';
  return refreshQueueSummary();
}
async function refreshQueueSummary() {
  const seq = ++queueSequence;
  $('export-button').disabled = true; show('plan-errors', false); $('plan-parts').replaceChildren();
  $('plan-summary').textContent = '正在核对计划…';
  try {
    const result = await api('/api/preview', queue);
    if (seq !== queueSequence) return;
    queuePreview = result;
    $('plan-summary').innerHTML = `<strong>${result.file_count}</strong> 个独立 STL · <strong>${result.copies}</strong> 次整份文件打印 · 源文件 ${bytes(result.bytes)}<br><span class="field-description">同一个文件只打包一次，所需打印份数已合并。</span>`;
    $('plan-parts').innerHTML = result.parts.length ? '<div class="parts-list">' + partsHTML(result.parts) + '</div>' : '';
    $('export-button').disabled = result.parts.length === 0 || Boolean(currentJob);
  } catch (e) {
    if (seq !== queueSequence) return;
    queuePreview = null; $('plan-summary').textContent = '计划尚未通过检查'; $('plan-errors').textContent = e.message; show('plan-errors', true);
  }
}
function renderLibrary() {
  if (!catalog) { $('library-body').innerHTML = '<tr><td colspan="4">请先连接模型库。</td></tr>'; return; }
  const words = $('library-search').value.toLowerCase().trim().split(/\s+/).filter(Boolean), filterKind = $('library-kind').value;
  const matches = catalog.files.filter(f => (!filterKind || f.kind === filterKind) && words.every(word => `${f.title} ${f.name} ${f.relative} ${kindLabels[f.kind]}`.toLowerCase().includes(word)));
  $('library-count').textContent = `${matches.length} 个结果 / ${catalog.count} 个模型`;
  $('library-body').innerHTML = matches.slice(0, libraryLimit).map(f => `<tr><td><strong>${escapeHTML(f.title)}${f.supports ? '<span class="tag-support">开支撑</span>' : ''}</strong><small>${escapeHTML(f.name)}</small><small class="file-path">${escapeHTML(f.relative)}</small></td><td>${kindLabels[f.kind]}<br><small>${escapeHTML(f.family || '共用 / 配件')}</small></td><td class="muted">${bytes(f.size)}</td><td><div class="table-actions"><button class="text-button" data-mesh="${f.id}" aria-label="预览 ${escapeHTML(f.name)}">预览 ↗</button><button class="add-file" data-add-file="${f.id}">加入补打 ＋</button></div></td></tr>`).join('');
  if (!matches.length) $('library-body').innerHTML = '<tr><td colspan="4" class="muted">没有匹配文件。可尝试英文型号或中文零件用途。</td></tr>';
  $('library-more').innerHTML = matches.length > libraryLimit ? '<button class="outline-button small" id="load-more">继续显示更多文件 ↓</button>' : `<span class="muted">已显示全部 ${matches.length} 个匹配文件</span>`;
  $('load-more')?.addEventListener('click', () => { libraryLimit += 100; renderLibrary(); });
}
function renderManuals() {
  const descriptions = ['认识型号、高度、顶盖与内部布局。查看零件命名和五金参考。', '先组装旋钮与弹簧，再安装内抽、滑轨和限位件。多内抽需要配套齿条。', '锁扣、锁销、上下铰链和铰链轴各有配套关系，注意上锁方向。', '轮组、底脚、背梁、固定把手和拉杆按整套配置选择。轮胎用 TPU。', '墙挂板可兼作定位模板；桌下安装使用对应顶盖并加堆叠连接扣。'];
  $('manual-grid').innerHTML = (catalog?.documents || []).map((doc, i) => `<article class="manual-card"><span class="manual-number">0${doc.id}</span><h2>${escapeHTML(doc.title)}</h2><p>${descriptions[i]}</p>${doc.exists ? `<a href="/api/docs/${doc.id}" target="_blank" rel="noopener">阅读官方图示 · ${doc.pages} 页 ↗</a>` : '<span class="muted">原 PDF 未在模型库找到</span>'}</article>`).join('');
}
async function loadHistory() {
  try { const history = await api('/api/history'); renderHistory(history); } catch (e) { toast(e.message, true); }
}
function renderHistory(entries) {
  $('history-list').innerHTML = entries.length ? entries.map(job => {
    const done = job.status === 'done', error = job.status === 'error';
    return `<article class="history-card"><div class="history-icon">${done ? 'ZIP' : error ? '!' : '…'}</div><div class="history-content"><h3>${escapeHTML(job.titles.join('、') || '独立零件补打')}</h3><p>${escapeHTML(new Date(job.created).toLocaleString('zh-CN'))} · ${job.file_count} 个文件 · ${job.copies} 次打印${done ? ' · ' + bytes(job.bytes) : ''}<br>${error ? escapeHTML(job.error) : done ? escapeHTML(job.name) : '正在打包，请稍候…'}</p></div><div class="history-actions">${done ? `<a href="/api/download/${job.id}" download>下载 ZIP ↗</a><button data-open-export="${job.id}">打开文件夹</button>` : `<span class="muted">${error ? '导出未完成' : '打包中'}</span>`}</div></article>`;
  }).join('') : '<div class="empty-state"><h2>下一次打印，从这里开始。</h2><p>把配置加入打印计划并导出，ZIP 和中文清单就会保存在这里。</p></div>';
}
async function pollJob(id) {
  currentJob = id;
  try {
    const job = await api('/api/jobs/' + id);
    if (job.status === 'done' || job.status === 'error') {
      currentJob = null; $('export-progress').replaceChildren();
      if (job.status === 'done') toast('打印包已生成。可下载 ZIP 或打开导出文件夹。');
      else toast('打包未完成：' + job.error, true);
      await loadHistory(); if ($('plan-dialog').open) renderQueue(); return;
    }
    $('export-progress').innerHTML = `<div class="progress-panel"><div class="progress-title"><strong>正在整理你的打印包…</strong><span>${job.progress}%</span></div><div class="progress-track"><div class="progress-bar" style="width:${job.progress}%"></div></div><p>${escapeHTML(job.current)}</p></div>`;
    setTimeout(() => pollJob(id), 900);
  } catch (e) { currentJob = null; toast(e.message, true); }
}
function info(title, html) { $('info-title').textContent = title; $('info-content').innerHTML = html; $('info-dialog').showModal(); }
async function openMesh(id) {
  const file = catalog?.files.find(f => f.id === id); if (!file) return;
  const seq = ++meshSequence;
  $('mesh-title').textContent = file.name; $('mesh-status').textContent = '正在读取完整模型尺寸并生成预览…'; $('mesh-details').replaceChildren(); viewer.clear();
  if (!$('mesh-dialog').open) $('mesh-dialog').showModal();
  try {
    const mesh = await api('/api/mesh/' + id);
    if (seq !== meshSequence) return;
    viewer.setData(mesh);
    $('mesh-status').textContent = `${mesh.faces.toLocaleString()} 个三角面 · 预览抽样 ${mesh.triangles.length.toLocaleString()} 面`;
    $('mesh-details').innerHTML = `<strong>STL 坐标轴尺寸：${mesh.dimensions.join(' × ')} mm</strong><br>${escapeHTML(file.title)} · ${bytes(file.size)} · ${escapeHTML(file.material)}${file.supports ? ' · 文件名明确要求开启支撑' : ''}<br><span class="muted">${escapeHTML(mesh.note)}<br>${escapeHTML(file.relative)}</span>`;
  } catch (e) { if (seq === meshSequence) $('mesh-status').textContent = e.message; }
}
function evidence(id, fromQueue) {
  const part = (fromQueue ? queuePreview : currentPreview)?.parts.find(p => p.id === id);
  if (!part) return;
  info(part.title, `<table class="data-table"><tr><th>文件</th><td>${escapeHTML(part.name)}</td></tr><tr><th>打印次数</th><td>${part.copies} 次整份 STL · ${escapeHTML(part.unit)}</td></tr><tr><th>用途</th><td>${escapeHTML(part.reason)}</td></tr><tr><th>依据</th><td>${escapeHTML(part.source)}</td></tr><tr><th>原始路径</th><td style="overflow-wrap:anywhere">${escapeHTML(part.relative)}</td></tr></table>`);
}
async function connect(root) {
  $('save-source').disabled = true; $('save-source').textContent = '扫描中…'; show('source-error', false);
  try {
    const result = await api('/api/scan', { root }); catalog = result.catalog; updateCatalogUI(); renderPresets(); refreshChoices(); renderManuals(); renderLibrary();
    $('source-dialog').close(); toast(`已连接 ${catalog.count} 个本地模型。`);
  } catch (e) { $('source-error').textContent = e.message; show('source-error', true); }
  finally { $('save-source').disabled = false; $('save-source').textContent = '扫描并连接 ↗'; }
}
function updateCatalogUI() {
  $('nav-file-count').textContent = catalog?.count || '—'; $('total-files').textContent = catalog?.count || '—';
  $('sidebar-source').textContent = catalog ? `${catalog.count} 个 STL · 已连接` : '未连接模型库';
  $('source-summary').textContent = catalog ? '源文件就绪 · 无需上传' : '请选择模型库路径';
  $('source-path').value = catalog?.root || 'D:\\261020_VAULT_USSA\\261020_VAULT_USSA';
  $('source-button').title = catalog?.root || '连接模型库';
}

document.querySelectorAll('.nav-item').forEach(button => button.addEventListener('click', () => view(button.dataset.view)));
document.querySelector('.brand').addEventListener('click', e => { e.preventDefault(); view('configure'); });
document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
  kind = button.dataset.kind;
  document.querySelectorAll('[data-kind]').forEach(b => b.classList.toggle('selected', b.dataset.kind === kind));
  expanded = false; refreshChoices();
}));
$('depth').addEventListener('change', refreshChoices);
$('height').addEventListener('change', refreshOptions);
$('config-form').addEventListener('input', e => {
  if (['depth', 'height'].includes(e.target.id)) return;
  if (e.target.id === 'variant') {
    if (['dividers', 'sealed'].includes(e.target.value)) $('interior').value = 'dividers';
    else if ($('interior').value === 'dividers' && kind === 'sustainer') $('interior').value = 'none';
  }
  if (e.target.id === 'interior' && kind === 'sustainer' && !['S', 'M'].includes(family)) {
    if (e.target.value === 'dividers' && $('variant').value === 'flat') $('variant').value = 'dividers';
    if (e.target.value === 'gridfinity') $('variant').value = 'flat';
  }
  refreshVisibility(); schedulePreview();
});
for (const [id, delta] of [['quantity-minus', -1], ['quantity-plus', 1]]) $(id).addEventListener('click', () => {
  $('quantity').value = Math.max(1, Math.min(100, +$('quantity').value + delta)); schedulePreview();
});
$('config-form').addEventListener('submit', async e => {
  e.preventDefault();
  if (!currentPreview || JSON.stringify(currentPreview.configs[0]) !== JSON.stringify(config())) return;
  queue.configs.push(structuredClone(config())); saveQueue(); toast('已加入打印计划，可以继续配置或打开计划打包。');
});
$('plan-button').addEventListener('click', () => { $('plan-dialog').showModal(); renderQueue(); });
$('clear-plan').addEventListener('click', () => { queue = { configs: [], manual: [] }; renderQueue(); });
$('export-button').addEventListener('click', async () => {
  $('export-button').disabled = true;
  try { const job = await api('/api/export', queue); $('plan-dialog').close(); view('history'); pollJob(job.id); }
  catch (e) { toast(e.message, true); $('export-button').disabled = false; }
});
document.addEventListener('click', e => {
  const button = e.target.closest('button'); if (!button) return;
  if (button.classList.contains('close-dialog')) { button.closest('dialog').close(); return; }
  if (button.dataset.mesh) openMesh(button.dataset.mesh);
  if (button.dataset.evidence) evidence(button.dataset.evidence, Boolean(button.closest('#plan-dialog')));
  if (button.dataset.removeConfig !== undefined) { queue.configs.splice(+button.dataset.removeConfig, 1); renderQueue(); }
  if (button.dataset.removeManual !== undefined) { queue.manual.splice(+button.dataset.removeManual, 1); renderQueue(); }
  if (button.dataset.addFile) {
    const id = button.dataset.addFile, existing = queue.manual.find(p => p.id === id);
    if (existing) existing.copies += 1; else queue.manual.push({ id, copies: 1 });
    saveQueue(); toast('已加入补打计划，默认整份 STL 打印 1 次。可在计划内修改。');
  }
  if (button.dataset.openExport) api('/api/open-output', { id: button.dataset.openExport }).catch(e => toast(e.message, true));
});
$('plan-dialog').addEventListener('input', e => {
  if (e.target.dataset.manualCopies !== undefined) {
    queue.manual[+e.target.dataset.manualCopies].copies = +e.target.value;
    saveQueue(); refreshQueueSummary();
  }
});
$('library-search').addEventListener('input', () => { libraryLimit = 70; renderLibrary(); });
$('library-kind').addEventListener('change', () => { libraryLimit = 70; renderLibrary(); });
$('source-button').addEventListener('click', () => { $('source-dialog').showModal(); });
$('save-source').addEventListener('click', () => connect($('source-path').value));
$('rescan-button').addEventListener('click', async () => {
  if (!catalog) return $('source-dialog').showModal();
  $('rescan-button').disabled = true;
  try { await connect(catalog.root); } finally { $('rescan-button').disabled = false; }
});
$('open-output').addEventListener('click', () => api('/api/open-output', {}).catch(e => toast(e.message, true)));
$('quick-guide').addEventListener('click', () => info('从选择到打印，只需要四步。', '<p>① 选择抽屉式或翻盖式，按官方型号选择宽度、深度和高度。</p><p>② 配置内抽、顶盖与内部收纳，右侧会显示所需文件和整份 STL 打印次数。</p><p>③ 加入打印计划。多个箱子、配件补打可以合并导出，同一文件只存一份。</p><p>④ 在打印计划中点击「整理并打包 ZIP」，到导出记录下载打印包，导入切片器。</p><div class="notice">不确定型号时，先阅读「中文装配指引」。只想补打某个零件，可以直接到模型库搜索。</div>'));
$('parts-guide').addEventListener('click', () => info(`${kindLabels[kind]}零件命名 · 官方示意`, `<img src="/assets/${kind === 'drawer' ? 'drawer' : 'sustainer'}-parts.jpg" alt="官方零件命名图"><p class="field-description">来源：01_Instructions Manual.pdf 第${kind === 'drawer' ? 11 : 12}页。图中型号用于说明部件名称，不代表当前配置。</p>`));
$('show-hardware').addEventListener('click', () => {
  if (!currentPreview) return toast('请先选择一个通过核对的配置。', true);
  info('本次五金参考清单', '<table class="data-table"><thead><tr><th>规格</th><th>数量</th><th>用途与依据</th></tr></thead><tbody>' + currentPreview.hardware.map(h => `<tr><td>${escapeHTML(h.name)}</td><td>${h.quantity}</td><td>${escapeHTML(h.reason)}<small>${escapeHTML(h.source)}<br>${escapeHTML(h.status)}</small></td></tr>`).join('') + '</tbody></table><div class="notice warning">官方总表和细分图存在数量差异。采购和装配前，请按实际型号孔位核对参考项。</div>');
});
$('mesh-dialog').addEventListener('close', () => { meshSequence++; viewer.clear(); });

async function init() {
  saveQueue();
  try {
    const [state, presetData] = await Promise.all([api('/api/state'), api('/assets/presets.json').catch(() => null)]);
    token = state.token; catalog = state.catalog;
    if (presetData) { presetDefaults = presetData.defaults; presets = presetData.presets; }
    else $('preset-description').textContent = '常用预选暂时无法读取，可使用下方配置选项。';
    updateCatalogUI(); renderPresets(); renderManuals(); renderHistory(state.history);
    if (catalog) refreshChoices();
    else { $('source-error').textContent = state.error || '请连接模型库'; show('source-error', true); $('source-dialog').showModal(); }
    const initialView = location.hash.slice(1); view(['configure', 'library', 'manuals', 'history'].includes(initialView) ? initialView : 'configure');
    const running = state.history.find(j => ['queued', 'running'].includes(j.status));
    if (running) pollJob(running.id);
  } catch (e) { toast('无法连接本地服务：' + e.message, true); $('sidebar-source').textContent = '连接失败，请重新启动工作台'; }
}
init();
