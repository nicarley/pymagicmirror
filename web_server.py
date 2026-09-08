import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

from PySide6.QtGui import QFontDatabase

from widget_manager import WIDGET_CLASSES


THEME_PRESETS = {
    "Default": {"background_color": [0, 0, 0], "text_color": [255, 255, 255], "text_shadow_color": [0, 0, 0], "background_opacity": 0.0, "text_scale_multiplier": 1.0},
    "Mirror Pro": {"background_color": [10, 12, 15], "text_color": [236, 242, 248], "text_shadow_color": [4, 6, 10], "background_opacity": 0.45, "text_scale_multiplier": 1.0},
    "Black Background": {"background_color": [0, 0, 0], "text_color": [240, 240, 240], "text_shadow_color": [0, 0, 0], "background_opacity": 0.35, "text_scale_multiplier": 1.0},
    "High Contrast": {"background_color": [0, 0, 0], "text_color": [255, 255, 0], "text_shadow_color": [0, 0, 0], "background_opacity": 0.25, "text_scale_multiplier": 1.2},
    "Soft Glass": {"background_color": [18, 24, 32], "text_color": [235, 245, 255], "text_shadow_color": [10, 10, 14], "background_opacity": 0.18, "text_scale_multiplier": 1.0},
}

ACCESSIBILITY_PRESETS = ["Standard", "Large Text", "High Contrast", "Large + High Contrast", "Night Mode", "Matrix Mode"]
REDACTED_VALUE = "__CONFIGURED__"
SENSITIVE_KEYS = {"api_key", "fmp_api_key", "web_server_token", "tracking_number"}

GENERAL_JS = r"""
const tab=document.getElementById('tab-general');tab.innerHTML='';
const camera=createSection('Camera & Display'),cg=document.createElement('div');cg.className='grid-2';camera.appendChild(cg);
addField(cg,'Background Mode',()=>buildSelect(meta.background_mode_options,config.background_mode==='Camera'&&meta.background_mode_options.includes(`Camera ${config.camera_index}`)?`Camera ${config.camera_index}`:config.background_mode,e=>{const v=e.target.value;if(v.startsWith('Camera ')){config.background_mode='Camera';config.camera_index=parseInt(v.split(' ')[1],10)||0}else{config.background_mode=v}renderAll()}));
if(config.background_mode==='Camera')addField(cg,'Camera Index',()=>buildInput('number',config.camera_index,e=>{config.camera_index=parseInt(e.target.value,10)||0}));
if(['Image','Video','YouTube'].includes(config.background_mode))addField(cg,'File Path / URL',()=>buildInput('text',config.background_file,e=>{config.background_file=e.target.value}));
addField(cg,'YouTube Quality',()=>buildSelect(meta.youtube_quality_options,config.youtube_quality,e=>{config.youtube_quality=e.target.value}));
addField(cg,'Background Rotation',()=>buildSelect([{value:'0',label:'0 degrees'},{value:'1',label:'90 degrees'},{value:'2',label:'180 degrees'},{value:'3',label:'270 degrees'}],String(config.video_rotation??0),e=>{config.video_rotation=parseInt(e.target.value,10)||0}));
addField(cg,'Background Fit',()=>buildSelect([{value:'fill',label:'Fill frame'},{value:'fit',label:'Fit inside frame'}],config.background_fit_mode,e=>{config.background_fit_mode=e.target.value}));
addField(cg,'Background Blur',()=>buildInput('number',config.background_blur,e=>{config.background_blur=parseInt(e.target.value,10)||0}));
addField(cg,'Background Brightness',()=>buildInput('number',config.background_brightness,e=>{config.background_brightness=Number(e.target.value)},{min:0,max:2,step:0.05}));
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
nameInput.setAttribute('aria-label','Profile name');const saveBtn=document.createElement('button');saveBtn.textContent='Save Profile';saveBtn.onclick=()=>callAction('save_profile',{name:nameInput.value});nameRow.appendChild(nameInput);nameRow.appendChild(saveBtn);profiles.appendChild(nameRow);
const loadRow=document.createElement('div');loadRow.className='inline-row';const loadSelect=buildSelect(meta.profiles,meta.current_profile||'',()=>{},true,false);loadSelect.setAttribute('aria-label','Saved profile');const loadBtn=document.createElement('button');loadBtn.className='secondary';loadBtn.textContent='Load Profile';loadBtn.onclick=()=>{if(loadSelect.value)callAction('load_profile',{name:loadSelect.value})};loadRow.appendChild(loadSelect);loadRow.appendChild(loadBtn);profiles.appendChild(loadRow);tab.appendChild(profiles);
"""

APPEARANCE_JS = r"""
const tab=document.getElementById('tab-appearance');tab.innerHTML='';
const appSection=createSection('Appearance'),grid=document.createElement('div');grid.className='grid-2';appSection.appendChild(grid);
addField(grid,'Font Family',()=>buildSelect(meta.available_fonts,config.font_family,e=>{config.font_family=e.target.value}));
addField(grid,'Global Text Size',()=>buildInput('number',config.text_scale_multiplier,e=>{config.text_scale_multiplier=parseFloat(e.target.value)||1.0}));
addField(grid,'Background Dimming',()=>buildInput('number',config.background_opacity,e=>{config.background_opacity=parseFloat(e.target.value)||0.0}));
addField(grid,'Text Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_color);i.oninput=e=>{config.text_color=hexToRgb(e.target.value);setDirty()};return i});
addField(grid,'Shadow Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_shadow_color);i.oninput=e=>{config.text_shadow_color=hexToRgb(e.target.value);setDirty()};return i});
addField(grid,'Background Color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.background_color);i.oninput=e=>{config.background_color=hexToRgb(e.target.value);setDirty()};return i});
tab.appendChild(appSection);
const presetSection=createSection('Presets'),pg=document.createElement('div');pg.className='grid-2';presetSection.appendChild(pg);
addField(pg,'Theme Preset',()=>buildSelect(Object.keys(THEME_PRESETS),'',e=>{const p=THEME_PRESETS[e.target.value];if(p){Object.assign(config,JSON.parse(JSON.stringify(p)));renderAppearanceTab()}},true));
addField(pg,'Readability Preset',()=>buildSelect(ACCESSIBILITY_PRESETS,'',e=>{const n=e.target.value;if(!n)return;if(n==='Night Mode'){config.text_scale_multiplier=1.0;config.text_color=[255,80,80];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}else if(n==='Matrix Mode'){config.text_scale_multiplier=1.0;config.text_color=[80,255,120];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.25,config.background_opacity||0)}else{config.text_scale_multiplier=n.includes('Large')?1.3:1.0;if(n.includes('High Contrast')){config.text_color=[255,255,0];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}}renderAppearanceTab()},true));
tab.appendChild(presetSection);
"""

WIDGETS_JS = r"""
const tab=document.getElementById('tab-widgets');tab.innerHTML='';
const templates=createSection('Templates');
const applyRow=document.createElement('div');applyRow.className='inline-row';const templateSelect=buildSelect(meta.templates,'',()=>{},true,false);templateSelect.setAttribute('aria-label','Saved template');const applyBtn=document.createElement('button');applyBtn.textContent='Apply Template';applyBtn.onclick=()=>{if(templateSelect.value)callAction('apply_template',{name:templateSelect.value})};applyRow.appendChild(templateSelect);applyRow.appendChild(applyBtn);templates.appendChild(applyRow);
const saveRow=document.createElement('div');saveRow.className='inline-row';const templateName=document.createElement('input');templateName.type='text';templateName.placeholder='Template name';templateName.setAttribute('aria-label','Template name');const saveTemplateBtn=document.createElement('button');saveTemplateBtn.className='secondary';saveTemplateBtn.textContent='Save Current as Template';saveTemplateBtn.onclick=()=>callAction('save_template',{name:templateName.value});const removeTemplateBtn=document.createElement('button');removeTemplateBtn.className='danger';removeTemplateBtn.textContent='Remove Template';removeTemplateBtn.onclick=()=>{if(templateSelect.value)callAction('remove_template',{name:templateSelect.value})};saveRow.appendChild(templateName);saveRow.appendChild(saveTemplateBtn);saveRow.appendChild(removeTemplateBtn);templates.appendChild(saveRow);tab.appendChild(templates);
const manage=createSection('Manage Widgets');const addRow=document.createElement('div');addRow.className='inline-row';const widgetTypeSelect=buildSelect(meta.widget_types,'',()=>{},true,false);widgetTypeSelect.setAttribute('aria-label','Widget type');const addBtn=document.createElement('button');addBtn.className='success';addBtn.textContent='Add Widget';addBtn.onclick=()=>{if(widgetTypeSelect.value)callAction('add_widget',{widget_type:widgetTypeSelect.value})};addRow.appendChild(widgetTypeSelect);addRow.appendChild(addBtn);manage.appendChild(addRow);tab.appendChild(manage);
const widgets=createSection('Widget Settings'),shell=document.createElement('div');shell.className='widget-editor';widgets.appendChild(shell);
const widgetNames=sortedWidgetNames();if(!widgetNames.includes(selectedWidgetName))selectedWidgetName=widgetNames[0]||null;
const nav=document.createElement('div');nav.className='widget-list';
for(const name of widgetNames){const item=document.createElement('button');item.className='widget-nav-item secondary';if(name===selectedWidgetName)item.classList.add('selected');item.setAttribute('aria-pressed',String(name===selectedWidgetName));const status=meta.widget_statuses?.[name]||'Ready';item.innerHTML=`<strong>${escapeHtml(humanizeKey(name))}</strong><span>${escapeHtml(status)}</span>`;item.onclick=()=>{selectedWidgetName=name;renderWidgetsTab();renderPreviewWidgets()};nav.appendChild(item)}shell.appendChild(nav);
const editor=document.createElement('div');editor.className='widget-properties';shell.appendChild(editor);
if(selectedWidgetName){const widgetName=selectedWidgetName,settings=config.widget_settings?.[widgetName]||{},layout=config.widget_positions?.[widgetName]||{};
const header=document.createElement('div');header.className='widget-header';const titleWrap=document.createElement('div');const title=document.createElement('div');title.className='widget-title';title.textContent=humanizeKey(widgetName);titleWrap.appendChild(title);const subtitle=document.createElement('div');subtitle.className='muted';subtitle.textContent=`${widgetName} | ${meta.widget_statuses?.[widgetName]||'Ready'}`;titleWrap.appendChild(subtitle);header.appendChild(titleWrap);
const headerButtons=document.createElement('div');headerButtons.className='inline-row compact';const renameInput=document.createElement('input');renameInput.type='text';renameInput.value=widgetName;renameInput.setAttribute('aria-label','Widget name');const renameBtn=document.createElement('button');renameBtn.className='secondary';renameBtn.textContent='Rename';renameBtn.onclick=()=>{if(renameInput.value&&renameInput.value!==widgetName)callAction('rename_widget',{old_name:widgetName,new_name:renameInput.value})};const removeBtn=document.createElement('button');removeBtn.className='danger';removeBtn.textContent='Remove';removeBtn.onclick=()=>callAction('remove_widget',{widget_name:widgetName});headerButtons.appendChild(renameInput);headerButtons.appendChild(renameBtn);headerButtons.appendChild(removeBtn);header.appendChild(headerButtons);editor.appendChild(header);
const layoutTitle=document.createElement('h3');layoutTitle.textContent='Layout';editor.appendChild(layoutTitle);const lg=document.createElement('div');lg.className='grid-2';
addField(lg,'Anchor',()=>buildSelect(['nw','n','ne','w','center','e','sw','s','se'],layout.anchor||'nw',e=>{config.widget_positions[widgetName].anchor=e.target.value;renderPreviewWidgets()}));
addField(lg,'Layer',()=>buildInput('number',layout.z??0,e=>{config.widget_positions[widgetName].z=parseInt(e.target.value,10)||0;renderPreviewWidgets()}));
addField(lg,'Page',()=>buildSelect(meta.layout_pages,layout.page||'default',e=>{config.widget_positions[widgetName].page=e.target.value||'default';renderPreviewWidgets()}));
addField(lg,'Group',()=>buildInput('text',layout.group||'',e=>{config.widget_positions[widgetName].group=e.target.value}));
addField(lg,'Lock Widget',()=>buildInput('checkbox',layout.locked,e=>{config.widget_positions[widgetName].locked=e.target.checked;renderPreviewWidgets()}));
addField(lg,'Conditional Visibility',()=>buildInput('checkbox',layout.visibility_rules?.enabled,e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.enabled=e.target.checked}));
addField(lg,'Visible From',()=>buildInput('text',layout.visibility_rules?.start_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.start_time=e.target.value}));
addField(lg,'Visible To',()=>buildInput('text',layout.visibility_rules?.end_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.end_time=e.target.value}));
addField(lg,'Days',()=>buildInput('text',(layout.visibility_rules?.days||[]).join(', '),e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.days=e.target.value.split(',').map(v=>v.trim()).filter(Boolean)}));editor.appendChild(lg);
const settingsTitle=document.createElement('h3');settingsTitle.textContent='Content';editor.appendChild(settingsTitle);const sg=document.createElement('div');sg.className='grid-2';const isSports=widgetName.split('_')[0]==='sports';if(isSports)editor.appendChild(createSportsEditor(settings,widgetName));for(const key of Object.keys(settings).sort()){if(isSports&&key==='configs')continue;addField(sg,humanizeKey(key),()=>isSports&&key==='style'?buildSelect(['Normal','Ticker'],settings[key],e=>{settings[key]=e.target.value}):createGenericValueEditor(settings[key],newValue=>{config.widget_settings[widgetName][key]=newValue},{forceJson:key==='feeds',key:`${widgetName}.${key}`}))}editor.appendChild(sg)}else{const empty=document.createElement('p');empty.className='empty-state';empty.textContent='Your display has no widgets yet. Choose a widget type above to get started.';editor.appendChild(empty)}
tab.appendChild(widgets);
"""

DIAGNOSTICS_JS = r"""
const tab=document.getElementById('tab-diagnostics');tab.innerHTML='';const section=createSection('Diagnostics');const pre=document.createElement('pre');pre.textContent=(meta.diagnostics_lines||[]).join('\n');section.appendChild(pre);const row=document.createElement('div');row.className='inline-row';row.style.marginTop='10px';const refreshBtn=document.createElement('button');refreshBtn.className='secondary';refreshBtn.textContent='Refresh Diagnostics';refreshBtn.onclick=()=>loadState();row.appendChild(refreshBtn);section.appendChild(row);tab.appendChild(section);
"""

HTML_TEMPLATE = """
<!doctype html><html><head><meta charset="utf-8"><title>MagicMirror Web Manager</title>
<style>
:root{--bg:#edf1f4;--panel:#f4f7fa;--panel2:#ffffff;--panel3:#ffffff;--line:#d5dde5;--text:#202833;--muted:#647284;--accent:#2f8f6b;--accent-hi:#3ca77e;--danger:#c94f49;--ok:#2f8f6b;--warn:#d79b45}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line);background:#ffffff;box-shadow:0 1px 2px rgba(32,40,51,.06)}
.brand{display:flex;flex-direction:column;gap:2px}.brand strong{font-size:16px}.brand span{color:var(--muted);font-size:12px}
#container{flex:1;display:grid;grid-template-columns:minmax(360px,1.8fr) minmax(420px,1.2fr);min-height:0}
#preview-pane{position:relative;overflow:hidden;background:#000;display:flex;align-items:center;justify-content:center;border-right:1px solid var(--line)}
#preview-img{max-width:100%;max-height:100%;object-fit:contain}#overlay{position:absolute;pointer-events:none}
.widget-box{position:absolute;display:flex;align-items:center;justify-content:center;padding:4px 8px;border:1px solid rgba(72,172,130,.78);border-radius:6px;background:rgba(47,143,107,.18);color:#fff;font-size:11px;cursor:move;pointer-events:auto;user-select:none;overflow:hidden;white-space:nowrap;box-shadow:0 8px 18px rgba(0,0,0,.2)}
.widget-box.locked{cursor:default;border-style:dashed;border-color:rgba(215,155,69,.9);background:rgba(215,155,69,.12)}.widget-box.active{border-color:#fff;background:rgba(47,143,107,.28)}
#settings-pane{display:flex;flex-direction:column;min-height:0;background:var(--panel)}.tabs{display:flex;gap:8px;padding:14px 18px;border-bottom:1px solid var(--line);background:#ffffff}
.tab-btn{background:transparent;color:var(--muted);border:1px solid transparent;border-radius:6px;padding:9px 14px;cursor:pointer}.tab-btn.active{color:#173427;border-color:#b8d9cc;background:#e4f2ed}
#settings-content{flex:1;min-height:0;overflow:auto;padding:22px}#settings-footer{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-top:1px solid var(--line);background:#ffffff}
.tab-panel{display:none}.tab-panel.active{display:block}.section{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:20px;margin-bottom:18px}.section h2{margin:0 0 16px;font-size:15px}.section h3,.widget-properties h3{margin:20px 0 12px;font-size:12px;color:var(--muted);text-transform:uppercase}
.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.form-group{margin-bottom:14px}label{display:block;margin-bottom:7px;color:var(--muted);font-size:12px}
input[type=text],input[type=password],input[type=number],select,textarea{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:6px;background:var(--panel3);color:var(--text);font:inherit}input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent-hi);box-shadow:0 0 0 2px rgba(60,167,126,.14)}textarea{min-height:92px;resize:vertical}input[type=checkbox]{transform:scale(1.15)}button{border:1px solid rgba(32,40,51,.08);border-radius:6px;padding:10px 15px;cursor:pointer;background:var(--accent);color:#fff;font:inherit;font-weight:600}button:hover{background:var(--accent-hi)}button.secondary{background:#e2e8ee;color:#25313d}button.secondary:hover{background:#d5dee6}button.danger{background:#fff2f1;border-color:#e8b1ad;color:#a43e38}button.danger:hover{background:#f9dfdd}button.success{background:var(--ok)}
.inline-row{display:flex;gap:10px;align-items:center}.inline-row>*{flex:1}.inline-row>button{flex:0 0 auto}.inline-row.compact input{width:150px}.widget-header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.widget-title{font-weight:700}.muted{color:var(--muted);font-size:12px}.widget-editor{display:grid;grid-template-columns:190px minmax(0,1fr);gap:20px;min-height:360px}.widget-list{display:flex;flex-direction:column;gap:6px;border-right:1px solid var(--line);padding-right:14px}.widget-nav-item{display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:3px;padding:10px 12px}.widget-nav-item span{font-size:11px;color:var(--muted);font-weight:400}.widget-nav-item.selected{background:#dcefe7;border-color:#9fcab9;color:#173427}.widget-properties{min-width:0}#dirty-indicator{color:var(--muted);font-size:12px}#dirty-indicator.changed{color:#8a641f}pre{margin:0;white-space:pre-wrap;word-break:break-word;background:#f7f9fb;border:1px solid var(--line);border-radius:6px;padding:14px}
@media(max-width:1100px){#container{grid-template-columns:1fr}#preview-pane{min-height:38vh}.widget-editor{grid-template-columns:1fr}.widget-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border-right:0;border-bottom:1px solid var(--line);padding:0 0 14px}}
</style></head><body>
<header><div class="brand"><strong>Magic Mirror</strong><span>Display manager</span></div><div class="inline-row" style="flex:0 0 auto"><button id="start-stream-btn" class="secondary" onclick="startStream()">Live Preview</button><button id="stop-stream-btn" class="secondary" onclick="stopStream()" style="display:none">Stop Preview</button><button class="secondary" onclick="refreshPreview()">Refresh</button><button class="secondary" onclick="openFullscreen()">Full Screen</button></div></header>
<div id="container"><div id="preview-pane"><img id="preview-img" src="/api/preview"><div id="overlay"></div></div><div id="settings-pane"><div class="tabs"><button class="tab-btn active" data-tab="general" onclick="switchTab('general')">Display</button><button class="tab-btn" data-tab="appearance" onclick="switchTab('appearance')">Style</button><button class="tab-btn" data-tab="widgets" onclick="switchTab('widgets')">Content</button><button class="tab-btn" data-tab="diagnostics" onclick="switchTab('diagnostics')">System</button></div><div id="settings-content"><div id="tab-general" class="tab-panel active"><span class="muted">Loading settings...</span></div><div id="tab-appearance" class="tab-panel"></div><div id="tab-widgets" class="tab-panel"></div><div id="tab-diagnostics" class="tab-panel"></div></div><div id="settings-footer"><div><span id="status" class="muted"></span><span id="dirty-indicator">All changes saved</span></div><button id="save-config-btn" onclick="saveConfig()">Save Changes</button></div></div></div>
<div id="fullscreen-modal" onclick="closeFullscreen()" style="display:none;position:fixed;inset:0;background:black;z-index:9999;align-items:center;justify-content:center"><img id="fullscreen-img" style="max-width:100%;max-height:100%;object-fit:contain"></div>
<script>
const THEME_PRESETS=__THEME_PRESETS__,ACCESSIBILITY_PRESETS=__ACCESSIBILITY_PRESETS__;
let state=null,config={},meta={},draggedEl=null,streamInterval=null,fullscreenInterval=null,activeTab='general',selectedWidgetName=null,dirty=false;const img=document.getElementById('preview-img'),overlay=document.getElementById('overlay');
function setStatus(m,e=false){const s=document.getElementById('status');s.textContent=m?`${m}  `:'';s.style.color=e?'#a43e38':'#647284'}function setDirty(value=true){dirty=value;const i=document.getElementById('dirty-indicator');i.textContent=value?'Unsaved changes':'All changes saved';i.classList.toggle('changed',value)}function rgbToHex(rgb){if(!Array.isArray(rgb)||rgb.length<3)return'#000000';const c=n=>Math.max(0,Math.min(255,Number(n)||0));return'#'+[c(rgb[0]),c(rgb[1]),c(rgb[2])].map(v=>v.toString(16).padStart(2,'0')).join('')}function hexToRgb(hex){const m=/^#?([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i.exec(hex||'');if(!m)return[0,0,0];return[parseInt(m[1],16),parseInt(m[2],16),parseInt(m[3],16)]}function humanizeKey(value){return String(value||'').replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase())}function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function fetchJson(url,options={}){const r=await fetch(url,options);if(!r.ok){throw new Error(await r.text()||(`${r.status} ${r.statusText}`))}return r.json()}
async function loadState(){try{state=await fetchJson('/api/state');config=state.config;meta=state.meta;renderAll();setDirty(false)}catch(err){console.error(err);setStatus(`Load failed: ${err.message}`,true)}}
async function saveConfig(){try{setStatus('Saving...');await fetchJson('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});await loadState();setStatus('Saved');refreshPreview()}catch(err){console.error(err);setStatus(`Save failed: ${err.message}`,true)}}
async function callAction(action,payload={}){try{setStatus(`${action}...`);const r=await fetchJson('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload})});setStatus(r.message||'Done');await loadState();refreshPreview()}catch(err){console.error(err);setStatus(`${action} failed: ${err.message}`,true)}}
function switchTab(tab){activeTab=tab;document.querySelectorAll('.tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.id===`tab-${tab}`));renderActiveTab()}
function refreshPreview(){const t=Date.now();img.src=`/api/preview?t=${t}`;if(document.getElementById('fullscreen-modal').style.display==='flex'){document.getElementById('fullscreen-img').src=`/api/preview?t=${t}`}}
function openFullscreen(){const m=document.getElementById('fullscreen-modal');m.style.display='flex';refreshPreview();fullscreenInterval=setInterval(refreshPreview,1000)}function closeFullscreen(){document.getElementById('fullscreen-modal').style.display='none';if(fullscreenInterval)clearInterval(fullscreenInterval);fullscreenInterval=null}
function startStream(){if(streamInterval)return;refreshPreview();streamInterval=setInterval(refreshPreview,500);document.getElementById('start-stream-btn').style.display='none';document.getElementById('stop-stream-btn').style.display='inline-block';document.getElementById('settings-pane').style.display='none';overlay.innerHTML=''}
function stopStream(){if(streamInterval)clearInterval(streamInterval);streamInterval=null;document.getElementById('start-stream-btn').style.display='inline-block';document.getElementById('stop-stream-btn').style.display='none';document.getElementById('settings-pane').style.display='flex';resizeOverlay()}
function resizeOverlay(){if(!img.complete||img.naturalWidth===0)return;const pane=document.getElementById('preview-pane').getBoundingClientRect(),imgRatio=img.naturalWidth/img.naturalHeight,paneRatio=pane.width/pane.height;let width,height,top,left;if(imgRatio>paneRatio){width=pane.width;height=width/imgRatio;left=0;top=(pane.height-height)/2}else{height=pane.height;width=height*imgRatio;top=0;left=(pane.width-width)/2}overlay.style.width=`${width}px`;overlay.style.height=`${height}px`;overlay.style.left=`${left}px`;overlay.style.top=`${top}px`;if(!streamInterval)renderPreviewWidgets()}
function sortedWidgetNames(){return Object.keys(config.widget_positions||{}).sort((a,b)=>((config.widget_positions[a]?.z||0)-(config.widget_positions[b]?.z||0))||a.localeCompare(b))}
function renderPreviewWidgets(){overlay.innerHTML='';if(!config.widget_positions)return;for(const name of sortedWidgetNames()){const pos=config.widget_positions[name];if((pos.page||'default')!==(config.active_page||'default'))continue;const el=document.createElement('div');el.className='widget-box';if(pos.locked)el.classList.add('locked');if(name===selectedWidgetName)el.classList.add('active');el.textContent=humanizeKey(name);el.dataset.name=name;el.style.left=`${(pos.x||0)*100}%`;el.style.top=`${(pos.y||0)*100}%`;el.style.width=`${(pos.width||0.18)*overlay.clientWidth}px`;el.style.height=`${(pos.height||0.08)*overlay.clientHeight}px`;el.style.zIndex=String(pos.z||0);if(pos.anchor==='center')el.style.transform='translate(-50%, -50%)';else if(pos.anchor==='ne')el.style.transform='translate(-100%, 0)';else if(pos.anchor==='se')el.style.transform='translate(-100%, -100%)';else if(pos.anchor==='sw')el.style.transform='translate(0, -100%)';el.onmousedown=startDrag;overlay.appendChild(el)}}
function startDrag(e){const name=e.currentTarget.dataset.name;if((config.widget_positions?.[name]||{}).locked)return;draggedEl=e.currentTarget;draggedEl.classList.add('active');e.preventDefault()}
document.addEventListener('mousemove',e=>{if(!draggedEl)return;const r=overlay.getBoundingClientRect();let x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;x=Math.max(0,Math.min(1,x));y=Math.max(0,Math.min(1,y));const name=draggedEl.dataset.name;config.widget_positions[name].x=x;config.widget_positions[name].y=y;config.widget_positions[name].anchor='nw';renderPreviewWidgets()});document.addEventListener('mouseup',()=>{if(!draggedEl)return;draggedEl.classList.remove('active');draggedEl=null});
function createSection(title){const s=document.createElement('div');s.className='section';const h=document.createElement('h2');h.textContent=title;s.appendChild(h);return s}
function addField(container,label,builder){const g=document.createElement('div');g.className='form-group';const l=document.createElement('label');l.textContent=label;g.appendChild(l);g.appendChild(builder());container.appendChild(g)}
function buildSelect(options,value,onChange,allowBlank=false){const s=document.createElement('select');if(allowBlank){const b=document.createElement('option');b.value='';b.textContent='Select...';s.appendChild(b)}(options||[]).forEach(opt=>{const data=typeof opt==='object'?opt:{value:opt,label:opt},o=document.createElement('option');o.value=data.value;o.textContent=data.label;if(String(data.value)===String(value))o.selected=true;s.appendChild(o)});s.onchange=e=>{onChange(e);setDirty()};return s}
function buildInput(type,value,onChange){const i=document.createElement('input');if(value==='__CONFIGURED__'){i.type='password';i.value=value;i.title='Configured. Enter a new value to replace it.'}else{i.type=type;if(type==='checkbox')i.checked=!!value;else i.value=value??''}i.onchange=e=>{onChange(e);setDirty()};return i}
function createGenericValueEditor(value,onChange,options={}){if(Array.isArray(value)&&!options.forceJson){const i=document.createElement('textarea');i.value=value.join(', ');i.onchange=e=>{onChange(e.target.value.split(',').map(v=>v.trim()).filter(Boolean));setDirty()};return i}if(typeof value==='boolean')return buildInput('checkbox',value,e=>onChange(e.target.checked));if(typeof value==='number')return buildInput('number',value,e=>onChange(parseFloat(e.target.value)));if((typeof value==='object'&&value!==null)||options.forceJson){const i=document.createElement('textarea');i.value=JSON.stringify(value??[],null,2);i.onchange=e=>{try{onChange(JSON.parse(e.target.value));e.target.style.borderColor='';setDirty()}catch(_){e.target.style.borderColor='#d9534f'}};return i}return buildInput('text',value??'',e=>onChange(e.target.value))}
function renderGeneralTab(){/*__GENERAL__*/}
function renderAppearanceTab(){/*__APPEARANCE__*/}
function renderWidgetsTab(){/*__WIDGETS__*/}
function renderDiagnosticsTab(){/*__DIAGNOSTICS__*/}
function renderActiveTab(){if(activeTab==='general')renderGeneralTab();else if(activeTab==='appearance')renderAppearanceTab();else if(activeTab==='widgets')renderWidgetsTab();else renderDiagnosticsTab()}
function renderAll(){renderActiveTab();renderPreviewWidgets()}
img.onload=resizeOverlay;window.onresize=resizeOverlay;document.addEventListener('keydown',e=>{if(e.key==='Escape')closeFullscreen();if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveConfig()}});setInterval(()=>{if(!draggedEl&&!streamInterval)refreshPreview()},10000);loadState();
</script></body></html>
"""


def _profiles_dir():
    return os.path.join(os.path.dirname(os.path.abspath("config.json")), "profiles")


def _list_profiles():
    os.makedirs(_profiles_dir(), exist_ok=True)
    return sorted(os.path.splitext(name)[0] for name in os.listdir(_profiles_dir()) if name.lower().endswith(".json"))


def _redact_config(config):
    safe = json.loads(json.dumps(config))
    for key in list(safe):
        if key.lower() in SENSITIVE_KEYS and safe.get(key):
            safe[key] = REDACTED_VALUE

    for widget_name, settings in safe.get("widget_settings", {}).items():
        if not isinstance(settings, dict):
            continue
        for key in list(settings):
            if key.lower() in SENSITIVE_KEYS and settings.get(key):
                settings[key] = REDACTED_VALUE

        widget_type = widget_name.split("_", 1)[0]
        if widget_type == "ical":
            for feed in settings.get("feeds", []):
                if isinstance(feed, dict) and feed.get("url"):
                    feed["url"] = REDACTED_VALUE
        if widget_type in {"commute", "dailyagenda"} and isinstance(settings.get("urls"), list):
            settings["urls"] = [REDACTED_VALUE if url else url for url in settings["urls"]]
    return safe


def _restore_redacted_values(incoming, current):
    if incoming == REDACTED_VALUE:
        return json.loads(json.dumps(current))
    if isinstance(incoming, dict):
        current_dict = current if isinstance(current, dict) else {}
        return {
            key: _restore_redacted_values(value, current_dict.get(key))
            for key, value in incoming.items()
        }
    if isinstance(incoming, list):
        current_list = current if isinstance(current, list) else []
        return [
            _restore_redacted_values(value, current_list[index] if index < len(current_list) else None)
            for index, value in enumerate(incoming)
        ]
    return incoming


def _safe_copy_config(app):
    return _redact_config(app.config)


def _client_is_loopback(client_address):
    host = client_address[0] if client_address else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def _build_diagnostics(app):
    lines = [
        f"Background Mode: {app.config.get('background_mode', 'Camera')}",
        f"Render FPS: {app.config.get('camera_fps', 30)}",
        f"Source FPS: {getattr(app, 'source_fps', 0.0):.1f}",
        f"Low Power Mode: {'ON' if app.config.get('low_power_mode') else 'OFF'}",
        f"Render Path: {getattr(app, 'media_backend_name', 'none').upper()}",
        f"Active Page: {app.config.get('active_page', 'default')}",
        f"Current Scene: {getattr(app, 'current_scene_name', '') or 'none'}",
        f"Scene Scheduler: {'ON' if app.config.get('scene_schedule_enabled') else 'OFF'}",
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
            "widget_registry": app.get_widget_registry_summary() if hasattr(app, "get_widget_registry_summary") else {},
            "templates": app.get_available_template_names(),
            "profiles": _list_profiles(),
            "current_profile": config.get("active_profile_name", "default"),
            "current_scene": getattr(app, "current_scene_name", ""),
            "layout_pages": app.get_layout_pages(),
            "widget_statuses": {name: app.get_widget_status(name) for name in config.get("widget_positions", {})},
            "diagnostics_lines": _build_diagnostics(app),
            "background_mode_options": ["None"] + [f"Camera {i}" for i in app.detect_available_cameras()] + ["Camera", "Image", "Video", "YouTube"],
            "youtube_quality_options": ["Best Available", "1080p", "720p", "480p"],
            "feed_refresh_options": [
                {"value": "900000", "label": "15 minutes"},
                {"value": "1800000", "label": "30 minutes"},
                {"value": "3600000", "label": "1 hour"},
                {"value": "7200000", "label": "2 hours"},
                {"value": "21600000", "label": "6 hours"},
                {"value": "43200000", "label": "12 hours"},
                {"value": "86400000", "label": "24 hours"},
            ],
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
    def _configured_token(self):
        return (self.server.app.config.get("web_server_token") or "").strip()

    def _request_token(self, parsed):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        query_token = (parse_qs(parsed.query).get("token") or [""])[0].strip()
        if query_token:
            return query_token
        raw_cookie = self.headers.get("Cookie", "")
        if raw_cookie:
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            if "magicmirror_token" in cookie:
                return cookie["magicmirror_token"].value.strip()
        return ""

    def _is_authorized(self, parsed):
        token = self._configured_token()
        if not token or _client_is_loopback(self.client_address):
            return True
        request_token = self._request_token(parsed)
        return bool(request_token) and secrets.compare_digest(request_token, token)

    def _send_security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'",
        )

    def _origin_is_allowed(self):
        origin = self.headers.get("Origin", "").strip()
        if not origin:
            return True
        host = self.headers.get("Host", "").strip().lower()
        return urlparse(origin).netloc.lower() == host

    def _send_json(self, status, payload):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self._send_security_headers()
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _read_json_payload(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 1024 * 1024:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        if not self._is_authorized(parsed):
            self.send_error(401, "Unauthorized")
            return
        if parsed.path == "/":
            query_token = (parse_qs(parsed.query).get("token") or [""])[0].strip()
            configured_token = self._configured_token()
            if query_token and configured_token and secrets.compare_digest(query_token, configured_token):
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header(
                    "Set-Cookie",
                    f"magicmirror_token={query_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000",
                )
                self._send_security_headers()
                self.end_headers()
                return
            html = HTML_TEMPLATE.replace("__THEME_PRESETS__", json.dumps(THEME_PRESETS)).replace("__ACCESSIBILITY_PRESETS__", json.dumps(ACCESSIBILITY_PRESETS))
            html = html.replace("/*__GENERAL__*/", self.server.general_js)
            html = html.replace("/*__APPEARANCE__*/", self.server.appearance_js)
            html = html.replace("/*__WIDGETS__*/", self.server.widgets_js)
            html = html.replace("/*__DIAGNOSTICS__*/", self.server.diagnostics_js)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if parsed.path == "/api/state":
            self._send_json(200, _build_state(self.server.app))
            return
        if parsed.path == "/api/preview":
            self.handle_preview()
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not self._is_authorized(parsed):
            self.send_error(401, "Unauthorized")
            return
        if not self._origin_is_allowed():
            self.send_error(403, "Origin not allowed")
            return
        try:
            payload = self._read_json_payload()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if parsed.path == "/api/config":
            try:
                restored = _restore_redacted_values(payload, self.server.app.config)
                validated = self.server.app.normalized_config(restored)
                self.server.app.call_on_ui_thread(lambda: self.server.app.replace_remote_config(validated), timeout=15)
                self._send_json(200, {"status": "ok"})
            except Exception as e:
                self.send_error(500, str(e))
            return
        if parsed.path == "/api/action":
            try:
                message = self.server.app.call_on_ui_thread(
                    lambda: _handle_action(self.server.app, payload.get("action", ""), payload.get("payload", {})),
                    timeout=20,
                )
                self._send_json(200, {"status": "ok", "message": message})
            except Exception as e:
                self.send_error(500, str(e))
            return
        self.send_error(404)

    def handle_preview(self):
        img_bytes = self.server.app.call_on_ui_thread(
            self.server.app.capture_preview_image,
            timeout=5,
        )
        if img_bytes:
            self.send_response(200)
            self.send_header("Content-type", "image/jpeg")
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(img_bytes)
        else:
            self.send_error(503, "Preview not available")

    def log_message(self, format, *args):
        pass


class MagicMirrorServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, server_address, request_handler_class, app):
        super().__init__(server_address, request_handler_class)
        self.app = app
        self.general_js = GENERAL_JS
        self.appearance_js = APPEARANCE_JS
        self.widgets_js = WIDGETS_JS
        self.diagnostics_js = DIAGNOSTICS_JS


def start_server(app, host="127.0.0.1", port=815):
    server = MagicMirrorServer((host, port), MagicMirrorHandler, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server
