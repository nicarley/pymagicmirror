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
const tab=document.getElementById('tab-general');tab.innerHTML='';createTabIntro(tab,'Display','Choose a background and fine-tune how your mirror runs.');
const camera=createSection('Camera and background'),cg=document.createElement('div');cg.className='grid-2';camera.appendChild(cg);
addField(cg,'Background mode',()=>buildSelect(meta.background_mode_options,config.background_mode==='Camera'&&meta.background_mode_options.includes(`Camera ${config.camera_index}`)?`Camera ${config.camera_index}`:config.background_mode,e=>{const v=e.target.value;if(v.startsWith('Camera ')){config.background_mode='Camera';config.camera_index=parseInt(v.split(' ')[1],10)||0}else{config.background_mode=v}renderAll()}));
if(config.background_mode==='Camera')addField(cg,'Camera index',()=>buildInput('number',config.camera_index,e=>{config.camera_index=parseInt(e.target.value,10)||0}));
if(['Image','Video','YouTube'].includes(config.background_mode))addField(cg,'File path / URL',()=>buildInput('text',config.background_file,e=>{config.background_file=e.target.value}));
addField(cg,'YouTube quality',()=>buildSelect(meta.youtube_quality_options,config.youtube_quality,e=>{config.youtube_quality=e.target.value}));
addField(cg,'Background rotation',()=>buildSelect([{value:'0',label:'0 degrees'},{value:'1',label:'90 degrees'},{value:'2',label:'180 degrees'},{value:'3',label:'270 degrees'}],String(config.video_rotation??0),e=>{config.video_rotation=parseInt(e.target.value,10)||0}));
addField(cg,'Background fit',()=>buildSelect([{value:'fill',label:'Fill frame'},{value:'fit',label:'Fit inside frame'}],config.background_fit_mode,e=>{config.background_fit_mode=e.target.value}));
addField(cg,'Background blur',()=>buildInput('number',config.background_blur,e=>{config.background_blur=parseInt(e.target.value,10)||0}));
addField(cg,'Background brightness',()=>buildInput('number',config.background_brightness,e=>{config.background_brightness=Number(e.target.value)},{min:0,max:2,step:0.05}));
addField(cg,'Background volume',()=>buildInput('number',config.background_volume,e=>{config.background_volume=parseInt(e.target.value,10)||0}));
addField(cg,'Mirror video',()=>buildInput('checkbox',config.mirror_video,e=>{config.mirror_video=e.target.checked}));
addField(cg,'Start in fullscreen',()=>buildInput('checkbox',config.fullscreen,e=>{config.fullscreen=e.target.checked}));
tab.appendChild(camera);
const system=createSection('System'),sg=document.createElement('div');sg.className='grid-2';system.appendChild(sg);
addField(sg,'Feed refresh',()=>buildSelect(meta.feed_refresh_options,String(config.feed_refresh_interval_ms),e=>{config.feed_refresh_interval_ms=parseInt(e.target.value,10)||3600000}));
addField(sg,'Render FPS',()=>buildSelect(['15','24','30','60'],String(config.camera_fps||30),e=>{config.camera_fps=parseInt(e.target.value,10)||30}));
addField(sg,'Enable web management',()=>buildInput('checkbox',config.web_server_enabled,e=>{config.web_server_enabled=e.target.checked}));
addField(sg,'Low power mode',()=>buildInput('checkbox',config.low_power_mode,e=>{config.low_power_mode=e.target.checked}));
addField(sg,'Auto relaunch on crash',()=>buildInput('checkbox',config.auto_relaunch_on_crash,e=>{config.auto_relaunch_on_crash=e.target.checked}));
addField(sg,'Snap widgets to grid',()=>buildInput('checkbox',config.snap_to_grid,e=>{config.snap_to_grid=e.target.checked}));
addField(sg,'Active page',()=>buildSelect(meta.layout_pages,config.active_page,e=>{config.active_page=e.target.value;renderPreviewWidgets()}));
tab.appendChild(system);
const profiles=createSection('Profiles');
const nameRow=document.createElement('div');nameRow.className='inline-row';const nameInput=document.createElement('input');nameInput.type='text';nameInput.value=config.active_profile_name||'default';
nameInput.setAttribute('aria-label','Profile name');const saveBtn=document.createElement('button');saveBtn.textContent='Save profile';saveBtn.onclick=()=>callAction('save_profile',{name:nameInput.value});nameRow.appendChild(nameInput);nameRow.appendChild(saveBtn);profiles.appendChild(nameRow);
const loadRow=document.createElement('div');loadRow.className='inline-row';const loadSelect=buildSelect(meta.profiles,meta.current_profile||'',()=>{},true,false);loadSelect.setAttribute('aria-label','Saved profile');const loadBtn=document.createElement('button');loadBtn.className='secondary';loadBtn.textContent='Load profile';loadBtn.onclick=()=>{if(loadSelect.value)callAction('load_profile',{name:loadSelect.value})};loadRow.appendChild(loadSelect);loadRow.appendChild(loadBtn);profiles.appendChild(loadRow);tab.appendChild(profiles);
"""

APPEARANCE_JS = r"""
const tab=document.getElementById('tab-appearance');tab.innerHTML='';createTabIntro(tab,'Style','Make your display feel at home.');
const appSection=createSection('Appearance'),grid=document.createElement('div');grid.className='grid-2';appSection.appendChild(grid);
addField(grid,'Font family',()=>buildSelect(meta.available_fonts,config.font_family,e=>{config.font_family=e.target.value}));
addField(grid,'Global text size',()=>buildInput('number',config.text_scale_multiplier,e=>{config.text_scale_multiplier=parseFloat(e.target.value)||1.0}));
addField(grid,'Background dimming',()=>buildInput('number',config.background_opacity,e=>{config.background_opacity=parseFloat(e.target.value)||0.0}));
addField(grid,'Text color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_color);i.oninput=e=>{config.text_color=hexToRgb(e.target.value);setDirty()};return i});
addField(grid,'Shadow color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.text_shadow_color);i.oninput=e=>{config.text_shadow_color=hexToRgb(e.target.value);setDirty()};return i});
addField(grid,'Background color',()=>{const i=document.createElement('input');i.type='color';i.value=rgbToHex(config.background_color);i.oninput=e=>{config.background_color=hexToRgb(e.target.value);setDirty()};return i});
tab.appendChild(appSection);
const presetSection=createSection('Presets'),pg=document.createElement('div');pg.className='grid-2';presetSection.appendChild(pg);
addField(pg,'Theme preset',()=>buildSelect(Object.keys(THEME_PRESETS),'',e=>{const p=THEME_PRESETS[e.target.value];if(p){Object.assign(config,JSON.parse(JSON.stringify(p)));renderAppearanceTab()}},true));
addField(pg,'Readability preset',()=>buildSelect(ACCESSIBILITY_PRESETS,'',e=>{const n=e.target.value;if(!n)return;if(n==='Night Mode'){config.text_scale_multiplier=1.0;config.text_color=[255,80,80];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}else if(n==='Matrix Mode'){config.text_scale_multiplier=1.0;config.text_color=[80,255,120];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.25,config.background_opacity||0)}else{config.text_scale_multiplier=n.includes('Large')?1.3:1.0;if(n.includes('High Contrast')){config.text_color=[255,255,0];config.text_shadow_color=[0,0,0];config.background_opacity=Math.max(0.2,config.background_opacity||0)}}renderAppearanceTab()},true));
tab.appendChild(presetSection);
"""

WIDGETS_JS = r"""
const tab=document.getElementById('tab-widgets');tab.innerHTML='';createTabIntro(tab,'Content','Add widgets and arrange the information that matters to you.');
const templates=createSection('Templates');
const applyRow=document.createElement('div');applyRow.className='inline-row';const templateSelect=buildSelect(meta.templates,'',()=>{},true,false);templateSelect.setAttribute('aria-label','Saved template');const applyBtn=document.createElement('button');applyBtn.textContent='Apply template';applyBtn.onclick=()=>{if(templateSelect.value)callAction('apply_template',{name:templateSelect.value})};applyRow.appendChild(templateSelect);applyRow.appendChild(applyBtn);templates.appendChild(applyRow);
const saveRow=document.createElement('div');saveRow.className='inline-row';const templateName=document.createElement('input');templateName.type='text';templateName.placeholder='Template name';templateName.setAttribute('aria-label','Template name');const saveTemplateBtn=document.createElement('button');saveTemplateBtn.className='secondary';saveTemplateBtn.textContent='Save as template';saveTemplateBtn.onclick=()=>callAction('save_template',{name:templateName.value});const removeTemplateBtn=document.createElement('button');removeTemplateBtn.className='danger';removeTemplateBtn.textContent='Remove template';removeTemplateBtn.onclick=()=>{if(templateSelect.value)callAction('remove_template',{name:templateSelect.value})};saveRow.appendChild(templateName);saveRow.appendChild(saveTemplateBtn);saveRow.appendChild(removeTemplateBtn);templates.appendChild(saveRow);tab.appendChild(templates);
const manage=createSection('Add a widget');const addRow=document.createElement('div');addRow.className='inline-row';const widgetTypeSelect=buildSelect(meta.widget_types,'',()=>{},true,false);widgetTypeSelect.setAttribute('aria-label','Widget type');const addBtn=document.createElement('button');addBtn.className='success';addBtn.textContent='Add widget';addBtn.onclick=()=>{if(widgetTypeSelect.value)callAction('add_widget',{widget_type:widgetTypeSelect.value})};addRow.appendChild(widgetTypeSelect);addRow.appendChild(addBtn);manage.appendChild(addRow);tab.appendChild(manage);
const widgets=createSection('Your widgets'),shell=document.createElement('div');shell.className='widget-editor';widgets.appendChild(shell);
const widgetNames=sortedWidgetNames();if(!widgetNames.includes(selectedWidgetName))selectedWidgetName=widgetNames[0]||null;
const nav=document.createElement('div');nav.className='widget-list';
for(const name of widgetNames){const item=document.createElement('button');item.className='widget-nav-item secondary';if(name===selectedWidgetName)item.classList.add('selected');item.setAttribute('aria-pressed',String(name===selectedWidgetName));const status=meta.widget_statuses?.[name]||'Ready';item.innerHTML=`<strong>${escapeHtml(humanizeKey(name))}</strong><span>${escapeHtml(status)}</span>`;item.onclick=()=>{selectedWidgetName=name;renderWidgetsTab();renderPreviewWidgets()};nav.appendChild(item)}shell.appendChild(nav);
const editor=document.createElement('div');editor.className='widget-properties';shell.appendChild(editor);
if(selectedWidgetName){const widgetName=selectedWidgetName,settings=config.widget_settings?.[widgetName]||{},layout=config.widget_positions?.[widgetName]||{};
const header=document.createElement('div');header.className='widget-header';const titleWrap=document.createElement('div');const title=document.createElement('div');title.className='widget-title';title.textContent=humanizeKey(widgetName);titleWrap.appendChild(title);const subtitle=document.createElement('div');subtitle.className='muted';subtitle.textContent=`${widgetName} | ${meta.widget_statuses?.[widgetName]||'Ready'}`;titleWrap.appendChild(subtitle);header.appendChild(titleWrap);
const headerButtons=document.createElement('div');headerButtons.className='inline-row compact';const renameInput=document.createElement('input');renameInput.type='text';renameInput.value=widgetName;renameInput.setAttribute('aria-label','Widget name');const renameBtn=document.createElement('button');renameBtn.className='secondary';renameBtn.textContent='Rename';renameBtn.onclick=()=>{if(renameInput.value&&renameInput.value!==widgetName)callAction('rename_widget',{old_name:widgetName,new_name:renameInput.value})};const removeBtn=document.createElement('button');removeBtn.className='danger';removeBtn.textContent='Remove';removeBtn.onclick=()=>callAction('remove_widget',{widget_name:widgetName});headerButtons.appendChild(renameInput);headerButtons.appendChild(renameBtn);headerButtons.appendChild(removeBtn);header.appendChild(headerButtons);editor.appendChild(header);
const layoutDetails=document.createElement('details');layoutDetails.className='layout-details';const layoutTitle=document.createElement('summary');layoutTitle.textContent='Layout and visibility';layoutDetails.appendChild(layoutTitle);const lg=document.createElement('div');lg.className='grid-2';
addField(lg,'Anchor',()=>buildSelect(['nw','n','ne','w','center','e','sw','s','se'],layout.anchor||'nw',e=>{config.widget_positions[widgetName].anchor=e.target.value;renderPreviewWidgets()}));
addField(lg,'Layer',()=>buildInput('number',layout.z??0,e=>{config.widget_positions[widgetName].z=parseInt(e.target.value,10)||0;renderPreviewWidgets()}));
addField(lg,'Page',()=>buildSelect(meta.layout_pages,layout.page||'default',e=>{config.widget_positions[widgetName].page=e.target.value||'default';renderPreviewWidgets()}));
addField(lg,'Group',()=>buildInput('text',layout.group||'',e=>{config.widget_positions[widgetName].group=e.target.value}));
addField(lg,'Lock widget',()=>buildInput('checkbox',layout.locked,e=>{config.widget_positions[widgetName].locked=e.target.checked;renderPreviewWidgets()}));
addField(lg,'Conditional visibility',()=>buildInput('checkbox',layout.visibility_rules?.enabled,e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.enabled=e.target.checked}));
addField(lg,'Visible from',()=>buildInput('text',layout.visibility_rules?.start_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.start_time=e.target.value}));
addField(lg,'Visible to',()=>buildInput('text',layout.visibility_rules?.end_time||'',e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.end_time=e.target.value}));
addField(lg,'Days',()=>buildInput('text',(layout.visibility_rules?.days||[]).join(', '),e=>{config.widget_positions[widgetName].visibility_rules=config.widget_positions[widgetName].visibility_rules||{};config.widget_positions[widgetName].visibility_rules.days=e.target.value.split(',').map(v=>v.trim()).filter(Boolean)}));layoutDetails.appendChild(lg);
const settingsTitle=document.createElement('h3');settingsTitle.textContent='Content';editor.appendChild(settingsTitle);const sg=document.createElement('div');sg.className='grid-2';const isSports=widgetName.split('_')[0]==='sports';if(isSports)editor.appendChild(createSportsEditor(settings,widgetName));for(const key of Object.keys(settings).sort()){if(isSports&&key==='configs')continue;addField(sg,humanizeKey(key),()=>isSports&&key==='style'?buildSelect(['Normal','Ticker'],settings[key],e=>{settings[key]=e.target.value}):createGenericValueEditor(settings[key],newValue=>{config.widget_settings[widgetName][key]=newValue},{forceJson:key==='feeds',key:`${widgetName}.${key}`}))}editor.appendChild(sg);editor.appendChild(layoutDetails)}else{const empty=document.createElement('p');empty.className='empty-state';empty.textContent='Your display has no widgets yet. Choose a widget type above to get started.';editor.appendChild(empty)}
tab.appendChild(widgets);
"""

DIAGNOSTICS_JS = r"""
const tab=document.getElementById('tab-diagnostics');tab.innerHTML='';createTabIntro(tab,'System','Keep an eye on your display and widget health.');const section=createSection('Diagnostics');const pre=document.createElement('pre');pre.textContent=(meta.diagnostics_lines||[]).join('\n');section.appendChild(pre);const row=document.createElement('div');row.className='inline-row';row.style.marginTop='16px';const refreshBtn=document.createElement('button');refreshBtn.className='secondary';refreshBtn.textContent='Refresh diagnostics';refreshBtn.onclick=()=>loadState();row.appendChild(refreshBtn);section.appendChild(row);tab.appendChild(section);
"""

HTML_TEMPLATE = r"""
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MagicMirror Display Manager</title>
<style>
:root{color-scheme:light dark;--bg:#f5f5f7;--panel:#f5f5f7;--panel2:#fff;--panel3:#fafafa;--line:#dedee3;--control-line:#85858e;--text:#1d1d1f;--muted:#62626b;--accent:#0066cc;--accent-hi:#0058b2;--accent-text:#0066cc;--selection:#e8f1fc;--selection-line:#9cbfe7;--button:#e9e9ed;--button-hover:#dddde3;--danger:#b42327;--danger-bg:#fff0f0;--danger-line:#e0b0b2;--warn:#82580a;--focus:#0066cc;--shadow:0 2px 10px rgba(0,0,0,.025)}
@media(prefers-color-scheme:dark){:root{--bg:#161618;--panel:#1a1a1d;--panel2:#222225;--panel3:#29292d;--line:#3a3a40;--control-line:#797981;--text:#f5f5f7;--muted:#b5b5bf;--accent:#0069d9;--accent-hi:#0063ce;--accent-text:#8ec5ff;--selection:#213550;--selection-line:#527fb4;--button:#333338;--button-hover:#404047;--danger:#ffb1b4;--danger-bg:#402528;--danger-line:#94565d;--warn:#f0c674;--focus:#8ec5ff;--shadow:0 2px 10px rgba(0,0,0,.1)}}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;font-size:.875rem;line-height:1.5;background:var(--bg);color:var(--text);height:100vh;height:100dvh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 28px;border-bottom:1px solid var(--line);background:var(--panel2)}
.brand{display:flex;flex-direction:column;gap:2px;min-width:0}.brand strong{font-size:1.1875rem;letter-spacing:-.5px;font-weight:650}.brand span{color:var(--muted);font-size:.8125rem}
#container{flex:1;display:grid;grid-template-columns:minmax(300px,1fr) minmax(560px,1fr);min-height:0}
#preview-pane{position:relative;min-width:0;overflow:hidden;background:#09090b;display:flex;align-items:center;justify-content:center;border-right:1px solid var(--line)}
#preview-img{width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain}#overlay{position:absolute;pointer-events:none}
.widget-box{position:absolute;display:flex;align-items:center;justify-content:center;min-width:28px;min-height:28px;padding:5px 9px;border:1px solid #74b8ff;border-radius:7px;background:rgba(0,74,151,.65);color:#fff;font-size:.75rem;cursor:move;pointer-events:auto;user-select:none;overflow:hidden;white-space:nowrap;touch-action:none}
.widget-box.locked{cursor:default;border-style:dashed;border-color:#f0c674;background:rgba(86,60,16,.75)}.widget-box.active{border:2px solid #fff;background:rgba(0,74,151,.85)}.widget-box:focus-visible{outline:3px solid #fff;outline-offset:3px}
.preview-note{position:absolute;left:24px;bottom:22px;right:24px;color:#ededf3;font-size:.8125rem;pointer-events:none;line-height:1.6;text-align:center}.preview-note span{display:inline-block;background:rgba(28,28,31,.94);border:1px solid #55555e;border-radius:10px;padding:10px 16px;box-shadow:0 4px 16px #0003}
.preview-error{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:36px;text-align:center;color:#d9d9e1;background:#161618}.preview-error[hidden]{display:none}
#settings-pane{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--panel)}
.tabs{display:flex;gap:5px;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--panel2)}
button{min-height:40px;border:1px solid transparent;border-radius:9px;padding:9px 16px;cursor:pointer;background:var(--accent);color:#fff;font:inherit;font-weight:600;line-height:1.4;transition:background-color .15s ease,border-color .15s ease}
button:hover{background:var(--accent-hi)}button.secondary{background:var(--button);color:var(--text)}button.secondary:hover{background:var(--button-hover)}button.danger{background:var(--danger-bg);border-color:var(--danger-line);color:var(--danger)}button.danger:hover{border-color:var(--danger)}button.success{background:var(--accent)}button.success:hover{background:var(--accent-hi)}
button:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:3px}button:disabled,button:disabled:hover{background:var(--button);border-color:var(--line);color:var(--muted);cursor:default}
.tab-btn{flex:1;background:transparent;color:var(--muted);border:1px solid transparent;padding:9px 12px;font-weight:550}.tab-btn:hover{background:var(--button);color:var(--text)}.tab-btn.active{color:var(--accent-text);border-color:var(--selection-line);background:var(--selection);font-weight:650}
#settings-content{flex:1;min-height:0;overflow:auto;padding:28px;scrollbar-gutter:stable}#settings-footer{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 26px;border-top:1px solid var(--line);background:var(--panel2)}
#settings-footer>div{display:flex;flex-direction:column;gap:4px;min-width:0}#settings-footer>button{flex-shrink:0}#status:empty{display:none}#dirty-indicator{color:var(--muted);font-size:.8125rem}#dirty-indicator.changed{color:var(--warn)}#dirty-indicator.changed:before{content:'●';font-size:9px;margin-right:7px}
.tab-panel{display:none}.tab-panel.active{display:block}.tab-intro{margin:0 2px 24px}.tab-intro h1{font-size:1.75rem;line-height:1.2;letter-spacing:-.8px;font-weight:650;margin:0 0 8px}.tab-intro p{margin:0;color:var(--muted);font-size:.875rem;max-width:48ch}
.section{background:var(--panel2);border:1px solid var(--line);border-radius:15px;padding:22px;margin-bottom:20px;box-shadow:var(--shadow)}.section:last-child{margin-bottom:0}.section h2{margin:0 0 20px;font-size:1rem;letter-spacing:-.2px;font-weight:650}.section h3,.widget-properties h3{margin:22px 0 14px;font-size:.875rem;font-weight:650;color:var(--text)}
.grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px 18px}.form-group{min-width:0;margin-bottom:18px}.grid-2 .form-group{margin:0}label{display:block;margin-bottom:8px;color:var(--muted);font-size:.8125rem;font-weight:500;line-height:1.4}
input[type=text],input[type=password],input[type=number],select,textarea{width:100%;min-width:0;min-height:42px;padding:10px 12px;border:1px solid var(--control-line);border-radius:8px;background:var(--panel3);color:var(--text);font:inherit;line-height:1.4}input::placeholder,textarea::placeholder{color:var(--muted);opacity:1}input:focus,select:focus,textarea:focus{outline:3px solid var(--focus);outline-offset:2px;border-color:var(--focus)}textarea{min-height:110px;resize:vertical}
.form-group input[type=checkbox]{width:20px;height:20px;accent-color:var(--accent);margin:0;cursor:pointer}.form-group:has(>input[type=checkbox]){display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;padding:8px 0;border-top:1px solid var(--line)}.form-group:has(>input[type=checkbox]) label{display:flex;align-items:center;min-height:44px;margin:0;flex:1;cursor:pointer;color:var(--text)}
.form-group input[type=color]{width:100%;min-height:42px;border:1px solid var(--control-line);border-radius:8px;background:var(--panel3);padding:5px;cursor:pointer}
.inline-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:12px}.inline-row>*{flex:1;min-width:0}.inline-row>button{flex:0 0 auto}.inline-row>input,.inline-row>select{min-width:130px;width:auto;flex:1 1 140px}.header-actions{flex:0 0 auto;margin:0;gap:8px}
.widget-editor{display:grid;grid-template-columns:140px minmax(0,1fr);gap:20px;min-height:360px}.widget-list{display:flex;flex-direction:column;gap:7px;border-right:1px solid var(--line);padding-right:16px}.widget-nav-item{display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:5px;padding:12px;min-width:0;overflow-wrap:anywhere}.widget-nav-item strong,.widget-nav-item span{max-width:100%}.widget-nav-item strong{font-size:.875rem;font-weight:600}.widget-nav-item span{font-size:.75rem;color:var(--muted);font-weight:400}.widget-nav-item.selected{background:var(--selection);border-color:var(--selection-line);color:var(--accent-text)}.widget-nav-item.selected:hover{background:var(--selection)}.widget-properties{min-width:0}
.widget-header{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;margin-bottom:18px}.widget-header .compact{width:100%;margin-top:0}.widget-header .compact input{min-width:110px;flex:1}.widget-title{font-size:1.125rem;font-weight:650;letter-spacing:-.3px}.muted{color:var(--muted);font-size:.8125rem;line-height:1.5}
.layout-details{margin-top:24px;border-top:1px solid var(--line);padding-top:8px}.layout-details summary{min-height:44px;padding:12px 0;font-weight:600;cursor:pointer}.layout-details[open] summary{margin-bottom:14px}.helper-text,.empty-state{font-size:.8125rem;color:var(--muted);line-height:1.6;margin:0 0 16px}.league-row{border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px;background:var(--panel3)}.league-fields{display:grid;grid-template-columns:1fr 1.4fr;gap:14px}.league-row .form-group{margin-bottom:0}.league-row .danger{font-size:.8125rem;padding:8px 12px}.field-error{color:var(--danger);font-size:.8125rem;line-height:1.5;margin-top:8px}.field-error:empty{display:none}[aria-invalid=true]{border-color:var(--danger)!important}
pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:var(--panel3);border:1px solid var(--line);border-radius:9px;padding:16px;font-size:.8125rem;line-height:1.7;font-family:ui-monospace,"Cascadia Code",Consolas,monospace}
#container.streaming{grid-template-columns:1fr}#fullscreen-modal{position:fixed;inset:0;background:#000;z-index:9999;align-items:center;justify-content:center}#fullscreen-modal[hidden]{display:none}#fullscreen-modal:not([hidden]){display:flex}#fullscreen-close{position:absolute;right:24px;top:24px;z-index:1;background:#303036;color:#fff;border-color:#73737d}#fullscreen-img{width:100%;height:100%;object-fit:contain}
@media(max-width:1300px){.widget-editor{grid-template-columns:1fr}.widget-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border-right:0;border-bottom:1px solid var(--line);padding:0 0 16px;max-height:210px;overflow:auto}}
@media(max-width:1000px){body{height:auto;min-height:100dvh}#container{display:flex;flex-direction:column;flex:1}#preview-pane{height:40vh;min-height:220px;border-right:0;border-bottom:1px solid var(--line)}#settings-pane{min-height:60vh;flex:1}#settings-content{overflow:visible;padding:24px}#settings-footer{position:sticky;bottom:0;z-index:4;box-shadow:0 -4px 16px #0001}#container.streaming #preview-pane{height:calc(100dvh - 100px);flex:1}.tabs{position:sticky;top:0;z-index:4}.widget-editor{grid-template-columns:190px minmax(0,1fr)}.widget-list{display:flex;border-right:1px solid var(--line);border-bottom:0;padding:0 16px 0 0;max-height:none;overflow:visible}}
@media(max-width:600px){header{padding:16px;align-items:flex-start;flex-direction:column;gap:14px}.header-actions{width:100%;gap:6px}.header-actions>button{flex:1;padding:10px 8px;font-size:.8125rem}button{min-height:44px}input[type=text],input[type=password],input[type=number],select,textarea{min-height:44px;font-size:1rem}#settings-content{padding:22px 16px}.tab-intro{margin-bottom:22px}.tab-intro h1{font-size:1.625rem}.section{padding:18px;margin-bottom:16px;border-radius:13px}.tabs{padding:12px}.tab-btn{padding:10px 6px}.grid-2,.league-fields{grid-template-columns:1fr;gap:18px}.widget-editor{grid-template-columns:1fr}.widget-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));border-right:0;border-bottom:1px solid var(--line);padding:0 0 16px;max-height:210px;overflow:auto}#settings-footer{padding:14px 16px;padding-bottom:max(14px,env(safe-area-inset-bottom));gap:12px}#settings-footer>button{padding:11px 13px}#preview-pane{height:31vh;min-height:180px}.preview-note{left:12px;bottom:12px;right:12px}.preview-note span{font-size:.75rem;padding:8px 10px}.inline-row>button{flex:1 1 auto}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;scroll-behavior:auto!important}}
@media(prefers-contrast:more){:root{--line:var(--control-line);--muted:var(--text);--selection-line:var(--accent-text)}button{border-color:currentColor}}
@media(forced-colors:active){.tab-btn.active,.widget-nav-item.selected{outline:2px solid Highlight;outline-offset:-2px}.widget-box{background:Canvas;color:CanvasText}.widget-box.active{outline:2px solid Highlight}}
</style></head><body>
<header><div class="brand"><strong>Magic Mirror</strong><span>Your display, just the way you like it.</span></div><div class="inline-row header-actions"><button id="start-stream-btn" class="secondary" onclick="startStream()">Live preview</button><button id="stop-stream-btn" class="secondary" onclick="stopStream()" style="display:none">Stop preview</button><button class="secondary" onclick="refreshPreview()">Refresh preview</button><button id="fullscreen-open" class="secondary" onclick="openFullscreen()">Full screen</button></div></header>
<div id="container">
  <div id="preview-pane">
    <img id="preview-img" src="/api/preview" alt="Current Magic Mirror display">
    <div id="preview-error" class="preview-error" role="status" hidden>Preview unavailable. Check that Magic Mirror is running, then refresh the preview.</div>
    <div id="overlay" aria-label="Widget positions"></div>
    <div class="preview-note"><span id="preview-hint">Drag a widget to arrange your display. Save when you’re ready.</span></div>
  </div>
  <div id="settings-pane">
    <div class="tabs" role="tablist" aria-label="Display settings">
      <button id="nav-general" class="tab-btn active" role="tab" aria-selected="true" aria-controls="tab-general" data-tab="general" onclick="switchTab('general')">Display</button>
      <button id="nav-appearance" class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-appearance" tabindex="-1" data-tab="appearance" onclick="switchTab('appearance')">Style</button>
      <button id="nav-widgets" class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-widgets" tabindex="-1" data-tab="widgets" onclick="switchTab('widgets')">Content</button>
      <button id="nav-diagnostics" class="tab-btn" role="tab" aria-selected="false" aria-controls="tab-diagnostics" tabindex="-1" data-tab="diagnostics" onclick="switchTab('diagnostics')">System</button>
    </div>
    <div id="settings-content">
      <div id="tab-general" class="tab-panel active" role="tabpanel" aria-labelledby="nav-general"><span class="muted">Loading settings...</span></div>
      <div id="tab-appearance" class="tab-panel" role="tabpanel" aria-labelledby="nav-appearance"></div>
      <div id="tab-widgets" class="tab-panel" role="tabpanel" aria-labelledby="nav-widgets"></div>
      <div id="tab-diagnostics" class="tab-panel" role="tabpanel" aria-labelledby="nav-diagnostics"></div>
    </div>
    <div id="settings-footer"><div><span id="status" class="muted" role="status" aria-live="polite"></span><span id="dirty-indicator">Loading settings…</span></div><button id="save-config-btn" onclick="saveConfig()" disabled>Save changes</button></div>
  </div>
</div>
<div id="fullscreen-modal" role="dialog" aria-modal="true" aria-label="Full screen display preview" hidden><button id="fullscreen-close" onclick="closeFullscreen()">Close preview</button><img id="fullscreen-img" alt="Full screen Magic Mirror display"></div>
<script>
const THEME_PRESETS=__THEME_PRESETS__,ACCESSIBILITY_PRESETS=__ACCESSIBILITY_PRESETS__;
const SPORTS_LEAGUES=[{value:'nfl',label:'NFL'},{value:'nba',label:'NBA'},{value:'mlb',label:'MLB'},{value:'nhl',label:'NHL'},{value:'ncaaf',label:'College football'},{value:'ncaamb',label:'College basketball'}];
let state=null,config={},meta={},draggedEl=null,dragState=null,streamInterval=null,fullscreenInterval=null,activeTab='general',selectedWidgetName=null,dirty=false,busy=false,fieldId=0;
const invalidDrafts=new Map();
const img=document.getElementById('preview-img'),overlay=document.getElementById('overlay');
function setStatus(message,error=false){
  const status=document.getElementById('status');status.textContent=message||'';status.style.color=error?'var(--danger)':'var(--muted)';
}
function updateSaveButton(){document.getElementById('save-config-btn').disabled=busy||!state||!dirty}
function setBusy(value){busy=value;document.getElementById('settings-content').inert=value;document.querySelector('.tabs').inert=value;updateSaveButton()}
function setDirty(value=true){
  if(value&&!dirty)setStatus('');
  dirty=value;const indicator=document.getElementById('dirty-indicator');
  indicator.textContent=value?'Unsaved changes':'All changes saved';indicator.classList.toggle('changed',value);updateSaveButton();
}
function rgbToHex(rgb){if(!Array.isArray(rgb)||rgb.length<3)return'#000000';return'#'+rgb.slice(0,3).map(n=>Math.round(Math.max(0,Math.min(255,Number(n)||0))).toString(16).padStart(2,'0')).join('')}
function hexToRgb(hex){const match=/^#?([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})$/i.exec(hex||'');return match?match.slice(1).map(v=>parseInt(v,16)):[0,0,0]}
function humanizeKey(value){return String(value||'').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function fetchJson(url,options={}){
  const response=await fetch(url,{...options,signal:AbortSignal.timeout(20000)});
  if(!response.ok){const body=await response.text();let message=body;try{message=JSON.parse(body).error||body}catch(_){}throw new Error(message||`${response.status} ${response.statusText}`)}
  return response.json();
}
async function loadState({replaceConfig=false}={}){
  try{
    const next=await fetchJson('/api/state');state=next;meta=next.meta;
    if(replaceConfig||!dirty){config=next.config;invalidDrafts.clear();setDirty(false)}
    renderAll();return true;
  }catch(error){setStatus(`Could not load settings: ${error.message}`,true);return false}
}
async function saveConfig(){
  if(busy||!state)return false;
  if(invalidDrafts.size){setStatus('Fix the highlighted fields before saving. Your edits have been kept.',true);document.querySelector('[aria-invalid="true"]')?.focus();return false}
  if(!dirty)return true;
  setBusy(true);setStatus('Saving changes…');
  try{
    await fetchJson('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
    setDirty(false);const refreshed=await loadState({replaceConfig:true});
    setStatus(refreshed?'Changes saved.': 'Changes saved, but settings could not be refreshed. Refresh the page to reconnect.',!refreshed);
    refreshPreview();return true;
  }catch(error){setStatus(`Could not save: ${error.message}. Your edits have been kept.`,true);return false}
  finally{setBusy(false)}
}
async function callAction(action,payload={}){
  if(busy||!state)return false;
  if(dirty&&!await saveConfig())return false;
  setBusy(true);setStatus('Updating your display…');
  try{
    const result=await fetchJson('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,payload})});
    const refreshed=await loadState({replaceConfig:true});
    if(refreshed)setStatus(result.message||'Display updated.');
    refreshPreview();return true;
  }catch(error){setStatus(`Could not ${action.replace(/_/g,' ')}: ${error.message}`,true);return false}
  finally{setBusy(false)}
}
function switchTab(tab){
  if(busy)return;activeTab=tab;
  document.querySelectorAll('.tab-btn').forEach(button=>{const selected=button.dataset.tab===tab;button.classList.toggle('active',selected);button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1});
  document.querySelectorAll('.tab-panel').forEach(panel=>panel.classList.toggle('active',panel.id===`tab-${tab}`));
  if(state)renderActiveTab();
}
function refreshPreview(){
  const source=`/api/preview?t=${Date.now()}`;img.src=source;
  if(!document.getElementById('fullscreen-modal').hidden)document.getElementById('fullscreen-img').src=source;
}
function openFullscreen(){
  const modal=document.getElementById('fullscreen-modal');if(!modal.hidden)return;modal.hidden=false;
  document.querySelector('header').inert=true;document.getElementById('container').inert=true;
  refreshPreview();fullscreenInterval=setInterval(refreshPreview,1000);document.getElementById('fullscreen-close').focus();
}
function closeFullscreen(){
  const modal=document.getElementById('fullscreen-modal');if(modal.hidden)return;modal.hidden=true;
  document.querySelector('header').inert=false;document.getElementById('container').inert=false;
  if(fullscreenInterval)clearInterval(fullscreenInterval);fullscreenInterval=null;document.getElementById('fullscreen-open').focus();
}
function startStream(){
  if(streamInterval)return;refreshPreview();streamInterval=setInterval(refreshPreview,500);
  document.getElementById('start-stream-btn').style.display='none';document.getElementById('stop-stream-btn').style.display='inline-block';
  document.getElementById('settings-pane').style.display='none';document.getElementById('container').classList.add('streaming');
  document.getElementById('preview-hint').textContent='Live preview · Updates every half second';overlay.innerHTML='';
}
function stopStream(){
  if(streamInterval)clearInterval(streamInterval);streamInterval=null;
  document.getElementById('start-stream-btn').style.display='inline-block';document.getElementById('stop-stream-btn').style.display='none';
  document.getElementById('settings-pane').style.display='flex';document.getElementById('container').classList.remove('streaming');
  document.getElementById('preview-hint').textContent='Drag a widget to arrange your display. Save when you’re ready.';resizeOverlay();
}
function resizeOverlay(){
  if(!img.complete||img.naturalWidth===0)return;
  const pane=document.getElementById('preview-pane').getBoundingClientRect(),ratio=img.naturalWidth/img.naturalHeight;
  const width=Math.min(pane.width,pane.height*ratio),height=width/ratio;
  overlay.style.width=`${width}px`;overlay.style.height=`${height}px`;overlay.style.left=`${(pane.width-width)/2}px`;overlay.style.top=`${(pane.height-height)/2}px`;
  if(!streamInterval&&!draggedEl)renderPreviewWidgets();
}
function sortedWidgetNames(){return Object.keys(config.widget_positions||{}).sort((a,b)=>((config.widget_positions[a]?.z||0)-(config.widget_positions[b]?.z||0))||a.localeCompare(b))}
function renderPreviewWidgets(){
  overlay.innerHTML='';if(!config.widget_positions||streamInterval)return;
  const transforms={nw:'',n:'translate(-50%,0)',ne:'translate(-100%,0)',w:'translate(0,-50%)',center:'translate(-50%,-50%)',e:'translate(-100%,-50%)',sw:'translate(0,-100%)',s:'translate(-50%,-100%)',se:'translate(-100%,-100%)'};
  for(const name of sortedWidgetNames()){
    const position=config.widget_positions[name];if((position.page||'default')!==(config.active_page||'default'))continue;
    const element=document.createElement('div');element.className='widget-box';element.classList.toggle('locked',!!position.locked);element.classList.toggle('active',name===selectedWidgetName);
    element.textContent=humanizeKey(name);element.dataset.name=name;element.tabIndex=0;element.setAttribute('role','button');element.setAttribute('aria-label',`${humanizeKey(name)}${position.locked?', locked':', use arrow keys to move; Enter to edit'}`);
    element.style.left=`${(position.x||0)*100}%`;element.style.top=`${(position.y||0)*100}%`;element.style.width=`${(position.width||0.18)*overlay.clientWidth}px`;element.style.height=`${(position.height||0.08)*overlay.clientHeight}px`;element.style.zIndex=String(position.z||0);element.style.transform=transforms[position.anchor]||'';
    element.onpointerdown=startDrag;element.onkeydown=event=>{
      if(busy)return;
      if(event.key==='Enter'||event.key===' '){event.preventDefault();selectedWidgetName=name;switchTab('widgets');renderPreviewWidgets();document.getElementById('nav-widgets').focus();return}
      if(position.locked||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
      event.preventDefault();const step=event.shiftKey?0.05:0.01;
      position.x=Math.max(0,Math.min(1,(position.x||0)+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0)));
      position.y=Math.max(0,Math.min(1,(position.y||0)+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0)));
      element.style.left=`${position.x*100}%`;element.style.top=`${position.y*100}%`;setDirty();
    };overlay.appendChild(element);
  }
}
function startDrag(event){
  if(busy||event.button!==0)return;const name=event.currentTarget.dataset.name,position=config.widget_positions[name];
  selectedWidgetName=name;if(activeTab==='widgets')renderWidgetsTab();
  if(position.locked)return;
  draggedEl=event.currentTarget;draggedEl.classList.add('active');draggedEl.focus();
  const rect=overlay.getBoundingClientRect();dragState={pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,x:position.x||0,y:position.y||0,width:rect.width,height:rect.height};
  draggedEl.setPointerCapture?.(event.pointerId);event.preventDefault();
}
document.addEventListener('pointermove',event=>{
  if(!draggedEl||event.pointerId!==dragState.pointerId||!dragState.width||!dragState.height)return;
  const position=config.widget_positions[draggedEl.dataset.name];
  let x=dragState.x+(event.clientX-dragState.startX)/dragState.width,y=dragState.y+(event.clientY-dragState.startY)/dragState.height;
  if(config.snap_to_grid){x=Math.round(x*100)/100;y=Math.round(y*100)/100}
  x=Math.max(0,Math.min(1,x));y=Math.max(0,Math.min(1,y));
  if(position.x!==x||position.y!==y){position.x=x;position.y=y;draggedEl.style.left=`${x*100}%`;draggedEl.style.top=`${y*100}%`;setDirty()}
});
function endDrag(event){if(!draggedEl||event.pointerId!==dragState.pointerId)return;const name=draggedEl.dataset.name;draggedEl=null;dragState=null;renderPreviewWidgets();Array.from(overlay.children).find(element=>element.dataset.name===name)?.focus()}
document.addEventListener('pointerup',endDrag);document.addEventListener('pointercancel',endDrag);
function createTabIntro(tab,title,description){const intro=document.createElement('div');intro.className='tab-intro';const heading=document.createElement('h1');heading.textContent=title;const detail=document.createElement('p');detail.textContent=description;intro.appendChild(heading);intro.appendChild(detail);tab.appendChild(intro)}
function createSection(title){const section=document.createElement('div');section.className='section';const heading=document.createElement('h2');heading.textContent=title;section.appendChild(heading);return section}
function addField(container,label,builder){
  const group=document.createElement('div');group.className='form-group';const caption=document.createElement('label');caption.textContent=label;
  const editor=builder(),control=editor.matches('input,select,textarea')?editor:editor.querySelector('input,select,textarea');
  if(control){control.id=control.id||`field-${++fieldId}`;caption.htmlFor=control.id;control.dataset.validationKey=`${activeTab}:${activeTab==='widgets'?selectedWidgetName:''}:${label}`;if(control.type==='number'&&invalidDrafts.has(control.dataset.validationKey)){control.value=invalidDrafts.get(control.dataset.validationKey);control.setAttribute('aria-invalid','true')}}
  group.appendChild(caption);group.appendChild(editor);container.appendChild(group);
}
function buildSelect(options,value,onChange,allowBlank=false,trackDirty=true){
  const select=document.createElement('select');if(allowBlank){const blank=document.createElement('option');blank.value='';blank.textContent='Choose…';select.appendChild(blank)}
  const normalized=(options||[]).map(option=>typeof option==='object'?option:{value:option,label:option});
  if(value!==undefined&&value!==null&&value!==''&&!normalized.some(option=>String(option.value)===String(value)))normalized.unshift({value,label:value});
  normalized.forEach(data=>{const option=document.createElement('option');option.value=data.value;option.textContent=data.label;if(String(data.value)===String(value))option.selected=true;select.appendChild(option)});
  select.onchange=event=>{onChange(event);if(trackDirty)setDirty()};return select;
}
function buildInput(type,value,onChange,attributes={}){
  const input=document.createElement('input');input.type=value==='__CONFIGURED__'?'password':type;
  if(type==='checkbox')input.checked=!!value;else input.value=value??'';
  if(value==='__CONFIGURED__'){input.title='Configured. Enter a new value to replace it.';input.autocomplete='new-password'}
  if(type==='number')input.step='any';Object.assign(input,attributes);
  input.oninput=event=>{const key=input.dataset.validationKey||input.id;if(type==='number'&&(input.value===''||!input.checkValidity())){invalidDrafts.set(key,input.value);input.setAttribute('aria-invalid','true');setDirty();setStatus('Enter a valid number before saving.',true);return}invalidDrafts.delete(key);input.removeAttribute('aria-invalid');onChange(event);setDirty()};return input;
}
function createGenericValueEditor(value,onChange,options={}){
  const nestedArray=Array.isArray(value)&&value.some(item=>item!==null&&typeof item==='object');
  if((typeof value==='object'&&value!==null&&!Array.isArray(value))||options.forceJson||nestedArray){
    const wrap=document.createElement('div'),input=document.createElement('textarea'),error=document.createElement('div');
    const key=options.key||`json-${++fieldId}`;input.value=invalidDrafts.get(key)??JSON.stringify(value??[],null,2);input.spellcheck=false;
    error.className='field-error';error.id=`error-${++fieldId}`;input.setAttribute('aria-describedby',error.id);
    const validate=()=>{try{const parsed=JSON.parse(input.value);onChange(parsed);invalidDrafts.delete(key);input.removeAttribute('aria-invalid');error.textContent=''}catch(_){invalidDrafts.set(key,input.value);input.setAttribute('aria-invalid','true');error.textContent='Enter valid JSON. Your edits will be kept until this is corrected.'}};
    input.oninput=()=>{validate();setDirty()};if(invalidDrafts.has(key)){input.setAttribute('aria-invalid','true');error.textContent='Enter valid JSON. Your edits will be kept until this is corrected.'}
    wrap.appendChild(input);wrap.appendChild(error);return wrap;
  }
  if(Array.isArray(value)){const input=document.createElement('textarea');input.value=value.join(', ');input.oninput=event=>{onChange(event.target.value.split(',').map(v=>v.trim()).filter(Boolean));setDirty()};return input}
  if(typeof value==='boolean')return buildInput('checkbox',value,event=>onChange(event.target.checked));
  if(typeof value==='number')return buildInput('number',value,event=>onChange(Number(event.target.value)));
  return buildInput('text',value??'',event=>onChange(event.target.value));
}
function createSportsEditor(settings,widgetName){
  const editor=document.createElement('div');editor.className='sports-editor';
  const help=document.createElement('p');help.className='helper-text';help.textContent='Choose the leagues you follow. Leave teams blank for every team, or enter abbreviations separated by commas (for example, CHI, GB).';editor.appendChild(help);
  const configs=Array.isArray(settings.configs)?settings.configs:[];
  if(!configs.length){const empty=document.createElement('p');empty.className='empty-state';empty.textContent='No leagues selected. Add a league to show scores on your display.';editor.appendChild(empty)}
  configs.forEach((entry,index)=>{
    const row=document.createElement('div');row.className='league-row';
    if(!entry||typeof entry!=='object'||Array.isArray(entry)){
      const warning=document.createElement('p');warning.className='field-error';warning.textContent='This saved league is invalid. Remove it and add a league below.';row.appendChild(warning);
    }else{
      const fields=document.createElement('div');fields.className='league-fields';
      addField(fields,'League',()=>buildSelect(SPORTS_LEAGUES,entry.league||'',event=>{entry.league=event.target.value},true));
      addField(fields,'Teams (optional)',()=>{const teams=Array.isArray(entry.teams)?entry.teams.join(', '):String(entry.teams||'');const input=buildInput('text',teams,event=>{entry.teams=Array.from(new Set(event.target.value.split(/[\s,;]+/).map(v=>v.trim().toUpperCase()).filter(Boolean)))});input.placeholder='All teams';input.autocomplete='off';return input});row.appendChild(fields);
    }
    const actions=document.createElement('div');actions.className='inline-row';const remove=document.createElement('button');remove.className='danger';remove.textContent='Remove league';remove.setAttribute('aria-label',`Remove league ${index+1}`);
    remove.onclick=()=>{settings.configs=configs.filter((_,i)=>i!==index);setDirty();renderWidgetsTab()};actions.appendChild(remove);row.appendChild(actions);editor.appendChild(row);
  });
  const add=document.createElement('button');add.className='secondary';add.textContent='Add league';add.onclick=()=>{const unused=SPORTS_LEAGUES.find(league=>!configs.some(entry=>entry?.league===league.value));settings.configs=[...configs,{league:unused?.value||'nfl',teams:[]}];setDirty();renderWidgetsTab()};editor.appendChild(add);return editor;
}
function renderGeneralTab(){/*__GENERAL__*/}
function renderAppearanceTab(){/*__APPEARANCE__*/}
function renderWidgetsTab(){/*__WIDGETS__*/}
function renderDiagnosticsTab(){/*__DIAGNOSTICS__*/}
function renderActiveTab(){if(activeTab==='general')renderGeneralTab();else if(activeTab==='appearance')renderAppearanceTab();else if(activeTab==='widgets')renderWidgetsTab();else renderDiagnosticsTab()}
function renderAll(){renderActiveTab();renderPreviewWidgets()}
img.onload=()=>{document.getElementById('preview-error').hidden=true;resizeOverlay()};
img.onerror=()=>{document.getElementById('preview-error').hidden=false;overlay.innerHTML=''};
window.addEventListener('resize',resizeOverlay);
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue=''}});
document.querySelector('.tabs').addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)||busy)return;
  const tabs=Array.from(document.querySelectorAll('.tab-btn')),current=tabs.findIndex(tab=>tab.dataset.tab===activeTab);
  const index=event.key==='Home'?0:event.key==='End'?tabs.length-1:(current+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  event.preventDefault();switchTab(tabs[index].dataset.tab);tabs[index].focus();
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape')closeFullscreen();
  if(event.key==='Tab'&&!document.getElementById('fullscreen-modal').hidden){event.preventDefault();document.getElementById('fullscreen-close').focus()}
  if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveConfig()}
});
setInterval(()=>{if(!document.hidden&&!draggedEl&&!streamInterval&&!fullscreenInterval)refreshPreview()},10000);
loadState();
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
