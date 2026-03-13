import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from PySide6.QtGui import QFontDatabase

from widget_manager import WIDGET_CLASSES


THEME_PRESETS = {
    "Default": {"background_color": [0, 0, 0], "text_color": [255, 255, 255], "text_shadow_color": [0, 0, 0], "background_opacity": 0.0, "text_scale_multiplier": 1.0},
    "Black Background": {"background_color": [0, 0, 0], "text_color": [240, 240, 240], "text_shadow_color": [0, 0, 0], "background_opacity": 0.35, "text_scale_multiplier": 1.0},
    "High Contrast": {"background_color": [0, 0, 0], "text_color": [255, 255, 0], "text_shadow_color": [0, 0, 0], "background_opacity": 0.25, "text_scale_multiplier": 1.2},
    "Soft Glass": {"background_color": [18, 24, 32], "text_color": [235, 245, 255], "text_shadow_color": [10, 10, 14], "background_opacity": 0.18, "text_scale_multiplier": 1.0},
}

ACCESSIBILITY_PRESETS = ["Standard", "Large Text", "High Contrast", "Large + High Contrast", "Night Mode", "Matrix Mode"]

GENERAL_JS = r"""
const tab=document.getElementById('tab-general');tab.innerHTML='';
const camera=createSection('Camera & Display'),cg=document.createElement('div');cg.className='grid-2';camera.appendChild(cg);
addField(cg,'Background Mode',()=>buildSelect(meta.background_mode_options,config.background_mode==='Camera'&&meta.background_mode_options.includes(`Camera ${config.camera_index}`)?`Camera ${config.camera_index}`:config.background_mode,e=>{const v=e.target.value;if(v.startsWith('Camera ')){config.background_mode='Camera';config.camera_index=parseInt(v.split(' ')[1],10)||0}else{config.background_mode=v}renderAll()}));
if(config.background_mode==='Camera')addField(cg,'Camera Index',()=>buildInput('number',config.camera_index,e=>{config.camera_index=parseInt(e.target.value,10)||0}));
if(['Image','Video','YouTube'].includes(config.background_mode))addField(cg,'File Path / URL',()=>buildInput('text',config.background_file,e=>{config.background_file=e.target.value}));
addField(cg,'YouTube Quality',()=>buildSelect(meta.youtube_quality_options,config.youtube_quality,e=>{config.youtube_quality=e.target.value}));
addField(cg,'Background Rotation',()=>buildSelect(['0','1','2','3'],String(config.video_rotation??0),e=>{config.video_rotation=parseInt(e.target.value,10)||0}));
addField(cg,'Background Fit',()=>buildSelect(['fill','fit'],config.background_fit_mode,e=>{config.background_fit_mode=e.target.value}));
addField(cg,'Background Blur',()=>buildInput('number',config.background_blur,e=>{config.background_blur=parseInt(e.target.value,10)||0}));
addField(cg,'Background Brightness',()=>buildInput('number',config.background_brightness,e=>{config.background_brightness=parseFloat(e.target.value)||1.0}));
addField(cg,'Background Volume',()=>buildInput('number',config.background_volume,e=>{config.background_volume=parseInt(e.target.value,10)||0}));
addField(cg,'Mirror Video',()=>buildInput('checkbox',config.mirror_video,e=>{config.mirror_video=e.target.checked}));
addField(cg,'Start in Fullscreen',()=>buildInput('checkbox',config.fullscreen,e=>{config.fullscreen=e.target.checked}));
tab.appendChild(camera);
const system=createSection('System'),sg=document.createElement('div');sg.className='grid-2';system.appendChild(sg);
addField(sg,'Feed Refresh',()=>buildSelect(meta.feed_refresh_options,String(config.feed_refresh_interval_ms),e=>{config.feed_refresh_interval_ms=parseInt(e.target.value,10)||3600000}));
addField(sg,'Render FPS',()=>buildSelect(['15','24','30','60'],String(config.camera_fps||30),e=>{config.camera_fps=parseInt(e.target.value,10)||30}));
addField(sg,'Enable Web Management',()=>buildInput('checkbox',config.web_server_enabled,e=>{config.web_server_enabled=e.target.checked}));
addField(sg,'Low Power Mode',()=>buildInput('checkbox',config.low_power_mode,e=>{config.low_power_mode=e.target.checked}));
addField(sg,'Auto Relaunch on Crash',()=>buildInput('checkbox',config.auto_relaunch_on_crash,e=>{config.auto_relaunch_on_crash=e.target.checked}));
addField(sg,'Snap Widgets to Grid',()=>buildInput('checkbox',config.snap_to_grid,e=>{config.snap_to_grid=e.target.checked}));
addField(sg,'Active Page',()=>buildSelect(meta.layout_pages,config.active_page,e=>{config.active_page=e.target.value;renderPreviewWidgets()}));
tab.appendChild(system);
const profiles=createSection('Profiles');
const nameRow=document.createElement('div');nameRow.className='inline-row';const nameInput=document.createElement('input');nameInput.type='text';nameInput.value=config.active_profile_name||'default';
const saveBtn=document.createElement('button');saveBtn.textContent='Save Profile';saveBtn.onclick=async()=>{await saveConfig();await callAction('save_profile',{name:nameInput.value})};nameRow.appendChild(nameInput);nameRow.appendChild(saveBtn);profiles.appendChild(nameRow);
const loadRow=document.createElement('div');loadRow.className='inline-row';const loadSelect=buildSelect(meta.profiles,meta.current_profile||'',()=>{},true);const loadBtn=document.createElement('button');loadBtn.className='secondary';loadBtn.textContent='Load Profile';loadBtn.onclick=()=>{if(loadSelect.value)callAction('load_profile',{name:loadSelect.value})};loadRow.appendChild(loadSelect);loadRow.appendChild(loadBtn);profiles.appendChild(loadRow);tab.appendChild(profiles);
"""

APPEARANCE_JS = r"""
const tab=document.getElementById('tab-appearance');tab.innerHTML='';
const appSection=createSection('Appearance'),grid=document.createElement('div');grid.className='grid-2';appSection.appendChild(grid);
addField(grid,'Font Family',()=>buildSelect(meta.available_fonts,config.font_family,e=>{config.font_family=e.target.value}));
addField(grid,'Global Text Size',()=>buildInput('number',config.text_scale_multiplier,e=>{config.text_scale_multiplier=parseFloat(e.target.value)||1.0}));
addField(grid,'Background Dimming',()=>buildInput('number',config.background_opacity,e=>{config.background_opacity=parseFloat(e.target.value)||0.0}));
addField(grid,'Text Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_color);i.oninput=e=>{config.text_color=hexToRgb(e.target.value)};return i});
addField(grid,'Shadow Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_shadow_color);i.oninput=e=>{config.text_shadow_color=hexToRgb(e.target.value)};return i});
addField(grid,'Background Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.background_color);i.oninput=e=>{config.background_color=hexToRgb(e.target.value)};return i});
tab.appendChild(appSection);
const presetSection=createSection('Presets'),pg=document.createElement('div');pg.className='grid-2';presetSection.appendChild(pg);
addField(pg,'Theme Preset',()=>buildSelect(Object.keys(THEME_PRESETS),'',e=>{const p=THEME_PRESETS[e.target.value];if(p){Object.assign(config,JSON.parse(JSON.stringify(p)));renderAppearanceTab()}},true));
addField(pg,'Readability Preset',()=>buildSelect(ACCESSIBILITY_PRESETS,'',e=>{const n=e.target.value;if(!n)return;if(n==='Night Mode'){config.text_scale_multiplier=1.0;config.text_color=[255,80,80];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}else if(n==='Matrix Mode'){config.text_scale_multiplier=1.0;config.text_color=[80,255,120];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.25,config.background_opacity||0)}else{config.text_scale_multiplier=n.includes('Large')?1.3:1.0;if(n.includes('High Contrast')){config.text_color=[255,255,0];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}}renderAppearanceTab()},true));
tab.appendChild(presetSection);
"""

WIDGETS_JS = r"""
const tab=document.getElementById('tab-widgets');tab.innerHTML='';
const templates=createSection('Templates');
const applyRow=document.createElement('div');applyRow.className='inline-row';const templateSelect=buildSelect(meta.templates,'',()=>{},true);const applyBtn=document.createElement('button');applyBtn.textContent='Apply Template';applyBtn.onclick=()=>{if(templateSelect.value)callAction('apply_template',{name:templateSelect.value})};applyRow.appendChild(templateSelect);applyRow.appendChild(applyBtn);templates.appendChild(applyRow);
const saveRow=document.createElement('div');saveRow.className='inline-row';const templateName=document.createElement('input');templateName.type='text';templateName.placeholder='Template name';const saveTemplateBtn=document.createElement('button');saveTemplateBtn.className='secondary';saveTemplateBtn.textContent='Save Current as Template';saveTemplateBtn.onclick=async()=>{await saveConfig();await callAction('save_template',{name:templateName.value})};const removeTemplateBtn=document.createElement('button');removeTemplateBtn.className='danger';removeTemplateBtn.textContent='Remove Template';removeTemplateBtn.onclick=()=>{if(templateSelect.value)callAction('remove_template',{name:templateSelect.value})};saveRow.appendChild(templateName);saveRow.appendChild(saveTemplateBtn);saveRow.appendChild(removeTemplateBtn);templates.appendChild(saveRow);tab.appendChild(templates);
const manage=createSection('Manage Widgets');const addRow=document.createElement('div');addRow.className='inline-row';const widgetTypeSelect=buildSelect(meta.widget_types,'',()=>{},true);const addBtn=document.createElement('button');addBtn.className='success';addBtn.textContent='Add Widget';addBtn.onclick=()=>{if(widgetTypeSelect.value)callAction('add_widget',{widget_type:widgetTypeSelect.value})};addRow.appendChild(widgetTypeSelect);addRow.appendChild(addBtn);manage.appendChild(addRow);tab.appendChild(manage);
const widgets=createSection('Widget Settings');
for(const widgetName of sortedWidgetNames()){const settings=config.widget_settings?.[widgetName]||{},layout=config.widget_positions?.[widgetName]||{},card=document.createElement('div');card.className='widget-card';
const header=document.createElement('div');header.className='widget-header';const titleWrap=document.createElement('div');const title=document.createElement('div');title.className='widget-title';title.textContent=widgetName;titleWrap.appendChild(title);const subtitle=document.createElement('div');subtitle.className='muted';subtitle.textContent=`Status: ${meta.widget_statuses?.[widgetName]||'OK'}`;titleWrap.appendChild(subtitle);header.appendChild(titleWrap);
const headerButtons=document.createElement('div');headerButtons.className='inline-row';headerButtons.style.flex='0 0 auto';const renameInput=document.createElement('input');renameInput.type='text';renameInput.value=widgetName;renameInput.style.width='170px';const renameBtn=document.createElement('button');renameBtn.className='secondary';renameBtn.textContent='Rename';renameBtn.onclick=()=>{if(renameInput.value&&renameInput.value!==widgetName)callAction('rename_widget',{old_name:widgetName,new_name:renameInput.value})};const removeBtn=document.createElement('button');removeBtn.className='danger';removeBtn.textContent='Remove';removeBtn.onclick=()=>callAction('remove_widget',{widget_name:widgetName});headerButtons.appendChild(renameInput);headerButtons.appendChild(renameBtn);headerButtons.appendChild(removeBtn);header.appendChild(headerButtons);card.appendChild(header);
const lg=document.createElement('div');lg.className='grid-2';
addField(lg,'Anchor',()=>buildSelect(['nw','n','ne','w','center','e','sw','s','se'],layout.anchor||'nw',e=>{config.widget_positions[widgetName].anchor=e.target.value;renderPreviewWidgets()}));
addField(lg,'Layer',()=>buildInput('number',layout.z??0,e=>{config.widget_positions[widgetName].z=parseInt(e.target.value,10)||0;renderPreviewWidgets()}));
addField(lg,'Page',()=>buildSelect(meta.layout_pages,layout.page||'default',e=>{config.widget_positions[widgetName].page=e.target.value||'default';renderPreviewWidgets()}));
addField(lg,'Group',()=>buildInput('text',layout.group||'',e=>{config.widget_positions[widgetName].group=e.target.value}));
addField(lg,'Lock Widget',()=>buildInput('checkbox',layout.locked,e=>{config.widget_positions[widgetName].locked=e.target.checked;renderPreviewWidgets()}));
addField(lg,'Conditional Visibility',()=>buildInput('checkbox',layout.visibility_rules?.enabled,e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.enabled=e.target.checked}));
addField(lg,'Visible From',()=>buildInput('text',layout.visibility_rules?.start_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.start_time=e.target.value}));
addField(lg,'Visible To',()=>buildInput('text',layout.visibility_rules?.end_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.end_time=e.target.value}));
addField(lg,'Days',()=>buildInput('text',(layout.visibility_rules?.days||[]).join(', '),e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.days=e.target.value.split(',').map(v=>v.trim()).filter(Boolean)}));
card.appendChild(lg);
const sg=document.createElement('div');sg.className='grid-2';for(const key of Object.keys(settings).sort()){addField(sg,key,()=>createGenericValueEditor(settings[key],newValue=>{config.widget_settings[widgetName][key]=newValue}))}card.appendChild(sg);widgets.appendChild(card)}
tab.appendChild(widgets);
"""

DIAGNOSTICS_JS = r"""
const tab=document.getElementById('tab-diagnostics');tab.innerHTML='';const section=createSection('Diagnostics');const pre=document.createElement('pre');pre.textContent=(meta.diagnostics_lines||[]).join('\n');section.appendChild(pre);const row=document.createElement('div');row.className='inline-row';row.style.marginTop='10px';const refreshBtn=document.createElement('button');refreshBtn.className='secondary';refreshBtn.textContent='Refresh Diagnostics';refreshBtn.onclick=()=>loadState();row.appendChild(refreshBtn);section.appendChild(row);tab.appendChild(section);
"""

HTML_TEMPLATE = """
<!doctype html><html><head><meta charset="utf-8"><title>MagicMirror Web Manager</title>
<style>
:root{--bg:#171717;--panel:#232323;--panel2:#2d2d2d;--line:#424242;--text:#f0f0f0;--muted:#b0b0b0;--accent:#1988ff;--danger:#d9534f;--ok:#22a05a}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",sans-serif;background:#111;color:var(--text);height:100vh;display:flex;flex-direction:column}
header{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid var(--line);background:#111}
#container{flex:1;display:grid;grid-template-columns:minmax(360px,1.8fr) minmax(420px,1.2fr);min-height:0}
#preview-pane{position:relative;overflow:hidden;background:#000;display:flex;align-items:center;justify-content:center;border-right:1px solid var(--line)}
#preview-img{max-width:100%;max-height:100%;object-fit:contain}#overlay{position:absolute;pointer-events:none}
.widget-box{position:absolute;display:flex;align-items:center;justify-content:center;padding:4px 8px;border:1px solid rgba(77,178,255,.75);background:rgba(25,136,255,.18);color:#fff;font-size:11px;cursor:move;pointer-events:auto;user-select:none;overflow:hidden;white-space:nowrap}
.widget-box.locked{cursor:default;border-style:dashed;border-color:rgba(255,212,102,.9);background:rgba(255,212,102,.1)}.widget-box.active{border-color:#fff}
#settings-pane{display:flex;flex-direction:column;min-height:0;background:var(--panel)}.tabs{display:flex;gap:6px;padding:10px 14px;border-bottom:1px solid var(--line);background:#1d1d1d}
.tab-btn{background:#343434;color:var(--muted);border:1px solid transparent;border-radius:999px;padding:8px 14px;cursor:pointer}.tab-btn.active{color:#fff;border-color:rgba(77,178,255,.65);background:rgba(25,136,255,.22)}
#settings-content{flex:1;min-height:0;overflow:auto;padding:16px}#settings-footer{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-top:1px solid var(--line);background:#1d1d1d}
.tab-panel{display:none}.tab-panel.active{display:block}.section{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}.section h2{margin:0 0 12px;font-size:15px}
.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.form-group{margin-bottom:10px}label{display:block;margin-bottom:5px;color:var(--muted);font-size:12px}
input[type=text],input[type=number],select,textarea{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:#171717;color:#fff;font:inherit}textarea{min-height:78px;resize:vertical}input[type=checkbox]{transform:scale(1.15)}button{border:none;border-radius:8px;padding:9px 14px;cursor:pointer;background:var(--accent);color:#fff;font:inherit}button.secondary{background:#4a4a4a}button.danger{background:var(--danger)}button.success{background:var(--ok)}
.inline-row{display:flex;gap:8px;align-items:center}.inline-row>*{flex:1}.inline-row>button{flex:0 0 auto}.widget-card{background:#202020;border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:12px}.widget-header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}.widget-title{font-weight:600}.muted{color:var(--muted);font-size:12px}pre{margin:0;white-space:pre-wrap;word-break:break-word;background:#151515;border:1px solid var(--line);border-radius:8px;padding:12px}
@media(max-width:1100px){#container{grid-template-columns:1fr}#preview-pane{min-height:38vh}}
</style></head><body>
<header><div>MagicMirror Web Manager</div><div class="inline-row" style="flex:0 0 auto"><button id="start-stream-btn" class="secondary" onclick="startStream()">Start Stream</button><button id="stop-stream-btn" class="secondary" onclick="stopStream()" style="display:none">Stop Stream</button><button class="secondary" onclick="refreshPreview()">Refresh Preview</button><button class="secondary" onclick="openFullscreen()">Full Preview</button><button onclick="saveConfig()">Save Changes</button></div></header>
<div id="container"><div id="preview-pane"><img id="preview-img" src="/api/preview"><div id="overlay"></div></div><div id="settings-pane"><div class="tabs"><button class="tab-btn active" data-tab="general" onclick="switchTab('general')">General</button><button class="tab-btn" data-tab="appearance" onclick="switchTab('appearance')">Appearance</button><button class="tab-btn" data-tab="widgets" onclick="switchTab('widgets')">Widgets</button><button class="tab-btn" data-tab="diagnostics" onclick="switchTab('diagnostics')">Diagnostics</button></div><div id="settings-content"><div id="tab-general" class="tab-panel active"></div><div id="tab-appearance" class="tab-panel"></div><div id="tab-widgets" class="tab-panel"></div><div id="tab-diagnostics" class="tab-panel"></div></div><div id="settings-footer"><span id="status" class="muted"></span><button onclick="saveConfig()">Save</button></div></div></div>
<div id="fullscreen-modal" onclick="closeFullscreen()" style="display:none;position:fixed;inset:0;background:black;z-index:9999;align-items:center;justify-content:center"><img id="fullscreen-img" style="max-width:100%;max-height:100%;object-fit:contain"></div>
<script>
const THEME_PRESETS=__THEME_PRESETS__,ACCESSIBILITY_PRESETS=__ACCESSIBILITY_PRESETS__;
let state=null,config={},meta={},draggedEl=null,streamInterval=null,fullscreenInterval=null;const img=document.getElementById('preview-img'),overlay=document.getElementById('overlay');
function setStatus(m,e=false){const s=document.getElementById('status');s.textContent=m||'';s.style.color=e?'#ff9f9f':'#b0b0b0'}function rgbToHex(rgb){if(!Array.isArray(rgb)||rgb.length<3)return'#000000';const c=n=>Math.max(0,Math.min(255,Number(n)||0));return'#'+[c(rgb[0]),c(rgb[1]),c(rgb[2])].map(v=>v.toString(16).padStart(2,'0')).join('')}function hexToRgb(hex){const m=/^#?([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i.exec(hex||'');if(!m)return[0,0,0];return[parseInt(m[1],16),parseInt(m[2],16),parseInt(m[3],16)]}
async function fetchJson(url,options={}){const r=await fetch(url,options);if(!r.ok){throw new Error(await r.text()||(`${r.status} ${r.statusText}`))}return r.json()}
async function loadState(){try{state=await fetchJson('/api/state');config=state.config;meta=state.meta;renderAll()}catch(err){console.error(err);setStatus(`Load failed: ${err.message}`,true)}}
async function saveConfig(){try{setStatus('Saving...');await fetchJson('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});setStatus('Saved');await loadState();refreshPreview()}catch(err){console.error(err);setStatus(`Save failed: ${err.message}`,true)}}
async function callAction(action,payload={}){try{setStatus(`${action}...`);const r=await fetchJson('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload})});setStatus(r.message||'Done');await loadState();refreshPreview()}catch(err){console.error(err);setStatus(`${action} failed: ${err.message}`,true)}}
function switchTab(tab){document.querySelectorAll('.tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.id===`tab-${tab}`))}
function refreshPreview(){const t=Date.now();img.src=`/api/preview?t=${t}`;if(document.getElementById('fullscreen-modal').style.display==='flex'){document.getElementById('fullscreen-img').src=`/api/preview?t=${t}`}}
function openFullscreen(){const m=document.getElementById('fullscreen-modal');m.style.display='flex';refreshPreview();fullscreenInterval=setInterval(refreshPreview,1000)}function closeFullscreen(){document.getElementById('fullscreen-modal').style.display='none';if(fullscreenInterval)clearInterval(fullscreenInterval);fullscreenInterval=null}
function startStream(){if(streamInterval)return;streamInterval=setInterval(refreshPreview,100);document.getElementById('start-stream-btn').style.display='none';document.getElementById('stop-stream-btn').style.display='inline-block';document.getElementById('settings-pane').style.display='none';overlay.innerHTML=''}
function stopStream(){if(streamInterval)clearInterval(streamInterval);streamInterval=null;document.getElementById('start-stream-btn').style.display='inline-block';document.getElementById('stop-stream-btn').style.display='none';document.getElementById('settings-pane').style.display='flex';resizeOverlay()}
function resizeOverlay(){if(!img.complete||img.naturalWidth===0)return;const pane=document.getElementById('preview-pane').getBoundingClientRect(),imgRatio=img.naturalWidth/img.naturalHeight,paneRatio=pane.width/pane.height;let width,height,top,left;if(imgRatio>paneRatio){width=pane.width;height=width/imgRatio;left=0;top=(pane.height-height)/2}else{height=pane.height;width=height*imgRatio;top=0;left=(pane.width-width)/2}overlay.style.width=`${width}px`;overlay.style.height=`${height}px`;overlay.style.left=`${left}px`;overlay.style.top=`${top}px`;if(!streamInterval)renderPreviewWidgets()}
function sortedWidgetNames(){return Object.keys(config.widget_positions||{}).sort((a,b)=>((config.widget_positions[a]?.z||0)-(config.widget_positions[b]?.z||0))||a.localeCompare(b))}
function renderPreviewWidgets(){overlay.innerHTML='';if(!config.widget_positions)return;for(const name of sortedWidgetNames()){const pos=config.widget_positions[name];if((pos.page||'default')!==(config.active_page||'default'))continue;const el=document.createElement('div');el.className='widget-box';if(pos.locked)el.classList.add('locked');const status=meta.widget_statuses?.[name]||'';el.textContent=status?`${name} [${status}]`:name;el.dataset.name=name;el.style.left=`${(pos.x||0)*100}%`;el.style.top=`${(pos.y||0)*100}%`;el.style.width=`${(pos.width||0.18)*overlay.clientWidth}px`;el.style.height=`${(pos.height||0.08)*overlay.clientHeight}px`;el.style.zIndex=String(pos.z||0);if(pos.anchor==='center')el.style.transform='translate(-50%, -50%)';else if(pos.anchor==='ne')el.style.transform='translate(-100%, 0)';else if(pos.anchor==='se')el.style.transform='translate(-100%, -100%)';else if(pos.anchor==='sw')el.style.transform='translate(0, -100%)';el.onmousedown=startDrag;overlay.appendChild(el)}}
function startDrag(e){const name=e.currentTarget.dataset.name;if((config.widget_positions?.[name]||{}).locked)return;draggedEl=e.currentTarget;draggedEl.classList.add('active');e.preventDefault()}
document.addEventListener('mousemove',e=>{if(!draggedEl)return;const r=overlay.getBoundingClientRect();let x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;x=Math.max(0,Math.min(1,x));y=Math.max(0,Math.min(1,y));const name=draggedEl.dataset.name;config.widget_positions[name].x=x;config.widget_positions[name].y=y;config.widget_positions[name].anchor='nw';renderPreviewWidgets()});document.addEventListener('mouseup',()=>{if(!draggedEl)return;draggedEl.classList.remove('active');draggedEl=null});
function createSection(title){const s=document.createElement('div');s.className='section';const h=document.createElement('h2');h.textContent=title;s.appendChild(h);return s}
function addField(container,label,builder){const g=document.createElement('div');g.className='form-group';const l=document.createElement('label');l.textContent=label;g.appendChild(l);g.appendChild(builder());container.appendChild(g)}
function buildSelect(options,value,onChange,allowBlank=false){const s=document.createElement('select');if(allowBlank){const b=document.createElement('option');b.value='';b.textContent='';s.appendChild(b)}(options||[]).forEach(opt=>{const o=document.createElement('option');o.value=opt;o.textContent=opt;if(String(opt)===String(value))o.selected=true;s.appendChild(o)});s.onchange=onChange;return s}
function buildInput(type,value,onChange){const i=document.createElement('input');i.type=type;if(type==='checkbox')i.checked=!!value;else i.value=value??'';i.onchange=onChange;return i}
function createGenericValueEditor(value,onChange){if(Array.isArray(value)){const i=document.createElement('textarea');i.value=value.join(', ');i.onchange=e=>onChange(e.target.value.split(',').map(v=>v.trim()).filter(Boolean));return i}if(typeof value==='boolean')return buildInput('checkbox',value,e=>onChange(e.target.checked));if(typeof value==='number')return buildInput('number',value,e=>onChange(parseFloat(e.target.value)));if(typeof value==='object'&&value!==null){const i=document.createElement('textarea');i.value=JSON.stringify(value,null,2);i.onchange=e=>{try{onChange(JSON.parse(e.target.value));e.target.style.borderColor='#424242'}catch(_){e.target.style.borderColor='#d9534f'}};return i}return buildInput('text',value??'',e=>onChange(e.target.value))}
function renderGeneralTab(){/*__GENERAL__*/}
function renderAppearanceTab(){/*__APPEARANCE__*/}
function renderWidgetsTab(){/*__WIDGETS__*/}
function renderDiagnosticsTab(){/*__DIAGNOSTICS__*/}
function renderAll(){renderGeneralTab();renderAppearanceTab();renderWidgetsTab();renderDiagnosticsTab();renderPreviewWidgets()}
img.onload=resizeOverlay;window.onresize=resizeOverlay;document.addEventListener('keydown',e=>{if(e.key==='Escape')closeFullscreen()});setInterval(()=>{if(!draggedEl&&!streamInterval)refreshPreview()},5000);loadState();
</script></body></html>
"""


def _profiles_dir():
    return os.path.join(os.path.dirname(os.path.abspath("config.json")), "profiles")


def _list_profiles():
    os.makedirs(_profiles_dir(), exist_ok=True)
    return sorted(os.path.splitext(name)[0] for name in os.listdir(_profiles_dir()) if name.lower().endswith(".json"))


def _safe_copy_config(app):
    return json.loads(json.dumps(app.config))


def _build_diagnostics(app):
    lines = [
        f"Background Mode: {app.config.get('background_mode', 'Camera')}",
        f"Render FPS: {app.config.get('camera_fps', 30)}",
        f"Source FPS: {getattr(app, 'source_fps', 0.0):.1f}",
        f"Low Power Mode: {'ON' if app.config.get('low_power_mode') else 'OFF'}",
        f"Render Path: {getattr(app, 'media_backend_name', 'none').upper()}",
        f"Active Page: {app.config.get('active_page', 'default')}",
        "",
        "Per-widget diagnostics:",
    ]
    for name in app.get_sorted_widget_names():
        widget = app.widget_manager.widgets.get(name)
        layout = app.get_widget_layout(name)
        last_updated = getattr(widget, "last_updated", None)
        refresh_text = last_updated.strftime("%Y-%m-%d %H:%M:%S") if last_updated else "never"
        failure_count = getattr(widget, "refresh_failures", 0) if widget else 0
        last_error = getattr(widget, "last_error", "") if widget else ""
        visible = "yes" if app.widget_is_visible(name) else "no"
        lines.append(f"{name}: page={layout.get('page')} z={layout.get('z')} visible={visible} locked={layout.get('locked')} last_refresh={refresh_text} failures={failure_count} error={last_error or 'none'}")
    return lines


def _build_state(app):
    config = _safe_copy_config(app)
    return {
        "config": config,
        "meta": {
            "available_fonts": sorted(QFontDatabase.families()),
            "widget_types": [w for w in sorted(WIDGET_CLASSES.keys()) if w not in {"sunrise"}],
            "templates": app.get_available_template_names(),
            "profiles": _list_profiles(),
            "current_profile": config.get("active_profile_name", "default"),
            "layout_pages": app.get_layout_pages(),
            "widget_statuses": {name: app.get_widget_status(name) for name in config.get("widget_positions", {})},
            "diagnostics_lines": _build_diagnostics(app),
            "background_mode_options": ["None"] + [f"Camera {i}" for i in app.detect_available_cameras()] + ["Camera", "Image", "Video", "YouTube"],
            "youtube_quality_options": ["Best Available", "1080p", "720p", "480p"],
            "feed_refresh_options": ["900000", "1800000", "3600000", "7200000", "21600000", "43200000", "86400000"],
        },
    }


def _save_profile(app, name):
    safe = "".join(ch for ch in (name or "default").strip() if ch.isalnum() or ch in ("-", "_")).strip() or "default"
    os.makedirs(_profiles_dir(), exist_ok=True)
    with open(os.path.join(_profiles_dir(), f"{safe}.json"), "w", encoding="utf-8") as f:
        app.migrate_config_schema()
        app.config["active_profile_name"] = safe
        json.dump(app.config, f, indent=2)
    app.save_config()
    return f"Saved profile: {safe}"


def _load_profile(app, name):
    safe = "".join(ch for ch in (name or "").strip() if ch.isalnum() or ch in ("-", "_")).strip()
    if not safe:
        raise ValueError("Profile name is required")
    path = os.path.join(_profiles_dir(), f"{safe}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile not found: {safe}")
    with open(path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    app.config.clear()
    app.config.update(loaded)
    app.migrate_config_schema()
    app.handle_remote_config_update()
    return f"Loaded profile: {safe}"


def _handle_action(app, action, payload):
    if action == "save_profile":
        return _save_profile(app, payload.get("name"))
    if action == "load_profile":
        return _load_profile(app, payload.get("name"))
    if action == "apply_template":
        app.apply_template((payload.get("name") or "").strip())
        return f"Applied template: {(payload.get('name') or '').strip()}"
    if action == "save_template":
        safe = app.save_current_as_template((payload.get("name") or "").strip())
        app.save_config()
        return f"Saved template: {safe}"
    if action == "remove_template":
        name = (payload.get("name") or "").strip()
        if not app.remove_saved_template(name):
            raise ValueError(f"Could not remove template: {name}")
        return f"Removed template: {name}"
    if action == "add_widget":
        widget_type = (payload.get("widget_type") or "").strip()
        if not widget_type:
            raise ValueError("Widget type is required")
        name = app.add_widget_by_type(widget_type)
        return f"Added widget: {name}"
    if action == "remove_widget":
        widget_name = (payload.get("widget_name") or "").strip()
        if not app.remove_widget_by_name(widget_name, confirm=False):
            raise ValueError(f"Could not remove widget: {widget_name}")
        return f"Removed widget: {widget_name}"
    if action == "rename_widget":
        old_name = (payload.get("old_name") or "").strip()
        new_name = (payload.get("new_name") or "").strip()
        if not old_name or not new_name:
            raise ValueError("Both old_name and new_name are required")
        if new_name in app.config.get("widget_positions", {}):
            raise ValueError("New widget name already exists")
        app.config["widget_positions"][new_name] = app.config["widget_positions"].pop(old_name)
        app.config["widget_settings"][new_name] = app.config["widget_settings"].pop(old_name)
        app.widget_manager.load_widgets()
        app.central_widget.update()
        app.save_config()
        return f"Renamed widget: {old_name} -> {new_name}"
    raise ValueError(f"Unknown action: {action}")


class MagicMirrorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html = HTML_TEMPLATE.replace("__THEME_PRESETS__", json.dumps(THEME_PRESETS)).replace("__ACCESSIBILITY_PRESETS__", json.dumps(ACCESSIBILITY_PRESETS))
            html = html.replace("/*__GENERAL__*/", self.server.general_js)
            html = html.replace("/*__APPEARANCE__*/", self.server.appearance_js)
            html = html.replace("/*__WIDGETS__*/", self.server.widgets_js)
            html = html.replace("/*__DIAGNOSTICS__*/", self.server.diagnostics_js)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_build_state(self.server.app)).encode("utf-8"))
            return
        if parsed.path == "/api/preview":
            self.handle_preview()
            return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) if length else b"{}")
        if self.path == "/api/config":
            try:
                self.server.app.config.clear()
                self.server.app.config.update(payload)
                self.server.app.migrate_config_schema()
                self.server.app.save_config()
                self.server.app.handle_remote_config_update()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, str(e))
            return
        if self.path == "/api/action":
            try:
                message = _handle_action(self.server.app, payload.get("action", ""), payload.get("payload", {}))
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": message}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, str(e))
            return
        self.send_error(404)

    def handle_preview(self):
        img_bytes = self.server.app.get_preview_image()
        if img_bytes:
            self.send_response(200)
            self.send_header("Content-type", "image/jpeg")
            self.end_headers()
            self.wfile.write(img_bytes)
        else:
            self.send_error(503, "Preview not available")

    def log_message(self, format, *args):
        pass


class MagicMirrorServer(HTTPServer):
    def __init__(self, server_address, request_handler_class, app):
        super().__init__(server_address, request_handler_class)
        self.app = app
        self.general_js = GENERAL_JS
        self.appearance_js = APPEARANCE_JS
        self.widgets_js = WIDGETS_JS
        self.diagnostics_js = DIAGNOSTICS_JS


def start_server(app, port=815):
    server = MagicMirrorServer(("0.0.0.0", port), MagicMirrorHandler, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server
