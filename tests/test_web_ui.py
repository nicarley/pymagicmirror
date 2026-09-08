"""Behavioral regression checks for the embedded manager's JavaScript."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import unittest


DOM = r"""
const assert=require('node:assert/strict');
class Element {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.dataset={};this.attributes={};this.value='';this.id='';this.classList={toggle(){},add(){},remove(){}};this.clientWidth=1000;this.clientHeight=500}
  appendChild(child){this.children.push(child);return child}
  set innerHTML(value){this.children=[]}
  setAttribute(key,value){this.attributes[key]=value}
  removeAttribute(key){delete this.attributes[key]}
  matches(selector){return selector.split(',').includes(this.tagName.toLowerCase())}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(child.matches(selector)?[child]:[]),...child.querySelectorAll(selector)])}
  getBoundingClientRect(){return {left:0,top:0,width:this.clientWidth,height:this.clientHeight}}
  checkValidity(){return Number.isFinite(Number(this.value))}
  focus(){}
  setPointerCapture(){}
}
const nodes=new Map(),listeners={};
const document={
  getElementById(id){if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)},
  createElement(tag){return new Element(tag)},
  querySelector(selector){return this.getElementById(selector)},
  querySelectorAll(){return []},
  addEventListener(name,callback){listeners[name]=callback}
};
"""


@unittest.skipUnless(shutil.which("node"), "Node.js is needed to check browser JavaScript")
class WebUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[1] / "web_server.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        values = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, (ast.Constant, ast.Dict, ast.List))
        }
        html = values["HTML_TEMPLATE"]
        for name in ("THEME_PRESETS", "ACCESSIBILITY_PRESETS"):
            html = html.replace(f"__{name}__", json.dumps(values[name]))
        for name in ("GENERAL", "APPEARANCE", "WIDGETS", "DIAGNOSTICS"):
            html = html.replace(f"/*__{name}__*/", values[f"{name}_JS"])
        cls.script = html.split("<script>", 1)[1].split("</script>", 1)[0]

    def run_js(self, assertions):
        # Avoid automatic page initialization; exercise the same page functions.
        script = DOM + self.script.split("img.onload=", 1)[0]
        result = subprocess.run(
            [shutil.which("node"), "-"],
            input=script + "\n(async()=>{\n" + assertions + "\n})().catch(error=>{console.error(error);process.exitCode=1});",
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_page_javascript_parses(self):
        result = subprocess.run(
            [shutil.which("node"), "--check", "-"], input=self.script,
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_arrays_remain_objects_and_invalid_json_blocks_save(self):
        self.run_js(r"""
          state={};let result;const inputValue=[{league:'nfl',teams:['CHI']}];
          const editor=createGenericValueEditor(inputValue,value=>result=value,{key:'sports.configs'});
          const input=editor.querySelector('textarea');assert.deepEqual(JSON.parse(input.value),inputValue);
          input.value='[{"league":"mlb","teams":["CHC"]}]';input.oninput();
          assert.deepEqual(result,[{league:'mlb',teams:['CHC']}]);
          input.value='[{';input.oninput();let calls=0;fetch=async()=>{calls++;throw Error('unexpected')};
          assert.equal(await saveConfig(),false);assert.equal(calls,0);assert.equal(dirty,true);
          const restored=createGenericValueEditor(result,()=>{},{key:'sports.configs'});
          assert.equal(restored.querySelector('textarea').value,'[{');
        """)

    def test_sports_controls_save_team_arrays(self):
        self.run_js(r"""
          state={};const settings={configs:[{league:'nfl',teams:['CHI']}]};
          const editor=createSportsEditor(settings,'sports_1');
          const teams=editor.querySelector('input');teams.value='chi, GB; chi';teams.oninput({target:teams});
          assert.deepEqual(settings.configs,[{league:'nfl',teams:['CHI','GB']}]);assert.equal(dirty,true);
          const league=editor.querySelector('select');league.value='mlb';league.onchange({target:league});
          assert.equal(settings.configs[0].league,'mlb');
        """)

    def test_failed_save_stops_dependent_action_and_keeps_edits(self):
        self.run_js(r"""
          state={};config={background_mode:'Image'};setDirty();const calls=[];
          fetch=async(url)=>{calls.push(url);return {ok:false,text:async()=>'{"error":"Unavailable"}'}};
          assert.equal(await callAction('save_profile',{name:'home'}),false);
          assert.deepEqual(calls,['/api/config']);assert.equal(dirty,true);assert.equal(busy,false);
          assert.equal(config.background_mode,'Image');
        """)

    def test_diagnostics_refresh_keeps_unsaved_config(self):
        self.run_js(r"""
          state={};config={background_mode:'Image'};setDirty();renderAll=()=>{};
          fetch=async()=>({ok:true,json:async()=>({config:{background_mode:'None'},meta:{diagnostics_lines:['new']}})});
          assert.equal(await loadState(),true);assert.equal(config.background_mode,'Image');
          assert.deepEqual(meta.diagnostics_lines,['new']);assert.equal(dirty,true);
        """)

    def test_drag_preserves_anchor_and_marks_layout_dirty(self):
        self.run_js(r"""
          state={};config={widget_positions:{sports_1:{x:0.7,y:0.2,anchor:'ne'}}};
          const element=new Element();element.dataset.name='sports_1';
          startDrag({button:0,currentTarget:element,clientX:500,clientY:100,pointerId:1,preventDefault(){}});
          listeners.pointermove({pointerId:1,clientX:600,clientY:150});
          const position=config.widget_positions.sports_1;
          assert.ok(Math.abs(position.x-0.8)<1e-9);assert.ok(Math.abs(position.y-0.3)<1e-9);
          assert.equal(position.anchor,'ne');assert.equal(dirty,true);
        """)


if __name__ == "__main__":
    unittest.main()
