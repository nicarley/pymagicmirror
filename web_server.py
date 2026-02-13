import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MagicMirror Settings</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; background: #222; color: #eee; height: 100vh; display: flex; flex-direction: column; }
        header { background: #111; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #444; }
        h1 { margin: 0; font-size: 1.2rem; }
        #container { display: flex; flex: 1; overflow: hidden; }
        #preview-pane { flex: 2; background: #000; position: relative; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        #settings-pane { flex: 1; min-width: 350px; max-width: 450px; background: #2d2d2d; border-left: 1px solid #444; display: flex; flex-direction: column; }
        #settings-content { flex: 1; overflow-y: auto; padding: 20px; }
        #settings-footer { padding: 15px; background: #222; border-top: 1px solid #444; text-align: right; }
        
        #preview-img { max-width: 100%; max-height: 100%; object-fit: contain; }
        #overlay { position: absolute; pointer-events: none; }
        .widget-box { 
            position: absolute; 
            border: 1px solid rgba(0, 255, 255, 0.5); 
            background: rgba(0, 255, 255, 0.1); 
            cursor: move; 
            color: rgba(255,255,255,0.8); 
            font-size: 10px; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            pointer-events: auto;
            user-select: none;
            overflow: hidden;
            white-space: nowrap;
        }
        .widget-box:hover { background: rgba(0, 255, 255, 0.3); border-color: rgba(0, 255, 255, 0.9); z-index: 10; }
        .widget-box.active { background: rgba(0, 255, 255, 0.4); border-color: #fff; z-index: 20; }

        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-size: 0.9rem; color: #aaa; }
        input[type="text"], input[type="number"], select, textarea { 
            width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; color: white; border-radius: 4px; box-sizing: border-box; font-family: inherit;
        }
        input[type="checkbox"] { transform: scale(1.2); }
        button { padding: 8px 16px; background: #0078d7; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
        button:hover { background: #1084e3; }
        button.secondary { background: #444; margin-right: 10px; }
        button.secondary:hover { background: #555; }
        button.danger { background: #d9534f; }
        button.danger:hover { background: #c9302c; }
        
        .section-title { font-weight: bold; margin-top: 20px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 1px solid #444; color: #fff; }
        .widget-settings-box { background: #333; padding: 10px; border-radius: 4px; margin-bottom: 10px; }
        .widget-settings-title { font-weight: bold; margin-bottom: 8px; color: #ddd; border-bottom: 1px solid #444; padding-bottom: 4px; display: flex; justify-content: space-between; align-items: center; }
        .remove-widget-btn { background: transparent; color: #d9534f; border: 1px solid #d9534f; padding: 2px 6px; font-size: 0.7rem; }
        .remove-widget-btn:hover { background: #d9534f; color: white; }
        
        #add-widget-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid #444; }
        .add-widget-row { display: flex; gap: 10px; }

        /* Fullscreen Preview Modal */
        #fullscreen-modal {
            display: none;
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: black;
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        #fullscreen-img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        
        /* Grid Layout for Settings */
        .settings-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
    </style>
</head>
<body>
    <header>
        <h1>MagicMirror Control</h1>
        <div>
            <button class="secondary" onclick="openFullscreen()">Full Preview</button>
            <button class="secondary" onclick="refreshPreview()">Refresh Preview</button>
            <button onclick="saveConfig()">Save Changes</button>
        </div>
    </header>
    <div id="container">
        <div id="preview-pane">
            <img id="preview-img" src="/api/preview" />
            <div id="overlay"></div>
        </div>
        <div id="settings-pane">
            <div id="settings-content">
                <div id="config-form"></div>
            </div>
            <div id="settings-footer">
                <span id="status" style="margin-right: 10px; font-size: 0.8rem; color: #aaa;"></span>
                <button onclick="saveConfig()">Save</button>
            </div>
        </div>
    </div>

    <div id="fullscreen-modal" onclick="closeFullscreen()">
        <img id="fullscreen-img" />
    </div>

    <script>
        let config = {};
        let draggedEl = null;
        let dragOffset = {x: 0, y: 0};
        let fullscreenInterval = null;
        
        // Available widget types (hardcoded for now, could be fetched)
        const WIDGET_TYPES = [
            "time", "date", "worldclock", "calendar", "weatherforecast", 
            "ical", "rss", "sports", "stock", "history", "countdown", 
            "quotes", "system", "ip"
        ];

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                config = await response.json();
                renderForm();
                renderWidgets();
            } catch (e) {
                console.error("Failed to load config", e);
            }
        }

        function refreshPreview() {
            const t = new Date().getTime();
            const img = document.getElementById('preview-img');
            img.src = '/api/preview?t=' + t;
            
            const fsImg = document.getElementById('fullscreen-img');
            if (document.getElementById('fullscreen-modal').style.display === 'flex') {
                fsImg.src = '/api/preview?t=' + t;
            }
        }

        function openFullscreen() {
            const modal = document.getElementById('fullscreen-modal');
            modal.style.display = 'flex';
            refreshPreview();
            fullscreenInterval = setInterval(refreshPreview, 1000); // Faster refresh in fullscreen
        }

        function closeFullscreen() {
            const modal = document.getElementById('fullscreen-modal');
            modal.style.display = 'none';
            if (fullscreenInterval) clearInterval(fullscreenInterval);
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === "Escape") closeFullscreen();
        });

        const img = document.getElementById('preview-img');
        const overlay = document.getElementById('overlay');

        function resizeOverlay() {
            if (!img.complete || img.naturalWidth === 0) return;
            
            const rect = img.getBoundingClientRect();
            const pane = document.getElementById('preview-pane').getBoundingClientRect();
            
            const imgRatio = img.naturalWidth / img.naturalHeight;
            const paneRatio = pane.width / pane.height;
            
            let width, height, top, left;
            
            if (imgRatio > paneRatio) {
                width = pane.width;
                height = width / imgRatio;
                left = 0;
                top = (pane.height - height) / 2;
            } else {
                height = pane.height;
                width = height * imgRatio;
                top = 0;
                left = (pane.width - width) / 2;
            }
            
            overlay.style.width = width + 'px';
            overlay.style.height = height + 'px';
            overlay.style.left = left + 'px';
            overlay.style.top = top + 'px';
            
            renderWidgets();
        }

        img.onload = resizeOverlay;
        window.onresize = resizeOverlay;

        function renderWidgets() {
            overlay.innerHTML = '';
            if (!config.widget_positions) return;

            for (const [name, pos] of Object.entries(config.widget_positions)) {
                const el = document.createElement('div');
                el.className = 'widget-box';
                el.innerText = name;
                el.dataset.name = name;
                
                el.style.left = (pos.x * 100) + '%';
                el.style.top = (pos.y * 100) + '%';
                el.style.width = '100px';
                el.style.height = '40px';
                
                if (pos.anchor === 'center') {
                    el.style.transform = 'translate(-50%, -50%)';
                } else if (pos.anchor === 'ne') {
                    el.style.transform = 'translate(-100%, 0)';
                } else if (pos.anchor === 'se') {
                    el.style.transform = 'translate(-100%, -100%)';
                } else if (pos.anchor === 'sw') {
                    el.style.transform = 'translate(0, -100%)';
                }

                el.onmousedown = startDrag;
                overlay.appendChild(el);
            }
        }

        function startDrag(e) {
            draggedEl = e.target;
            draggedEl.classList.add('active');
            e.preventDefault();
        }

        document.addEventListener('mousemove', (e) => {
            if (draggedEl) {
                const overlayRect = overlay.getBoundingClientRect();
                
                let x = (e.clientX - overlayRect.left) / overlayRect.width;
                let y = (e.clientY - overlayRect.top) / overlayRect.height;
                
                x = Math.max(0, Math.min(1, x));
                y = Math.max(0, Math.min(1, y));
                
                draggedEl.style.left = (x * 100) + '%';
                draggedEl.style.top = (y * 100) + '%';
                
                const name = draggedEl.dataset.name;
                if (config.widget_positions[name]) {
                    config.widget_positions[name].x = x;
                    config.widget_positions[name].y = y;
                    config.widget_positions[name].anchor = 'nw';
                    draggedEl.style.transform = 'none';
                }
            }
        });

        document.addEventListener('mouseup', () => {
            if (draggedEl) {
                draggedEl.classList.remove('active');
                draggedEl = null;
            }
        });

        function addWidget() {
            const typeSelect = document.getElementById('new-widget-type');
            const type = typeSelect.value;
            
            // Find a unique name
            let i = 1;
            while (config.widget_positions[`${type}_${i}`]) {
                i++;
            }
            const name = `${type}_${i}`;
            
            // Initialize position
            if (!config.widget_positions) config.widget_positions = {};
            config.widget_positions[name] = { x: 0.5, y: 0.5, anchor: "center" };
            
            // Initialize settings based on type (mimicking Main.py logic)
            if (!config.widget_settings) config.widget_settings = {};
            
            const defaults = {};
            if (type === "ical") defaults.urls = [], defaults.timezone = "US/Central";
            else if (type === "rss") { defaults.urls = []; defaults.style = "Normal"; defaults.title = ""; defaults.article_count = 5; defaults.max_width_chars = 50; }
            else if (type === "weatherforecast") { defaults.location = "Salem, IL"; defaults.style = "Normal"; }
            else if (type === "worldclock") defaults.timezone = "UTC";
            else if (type === "sports") { defaults.configs = []; defaults.style = "Normal"; defaults.timezone = "UTC"; }
            else if (type === "stock") { defaults.symbols = ["AAPL", "GOOG"]; defaults.api_key = config.FMP_API_KEY || ""; defaults.style = "Normal"; }
            else if (type === "date") defaults.format = "%A, %B %d, %Y";
            else if (type === "history") { defaults.max_width_chars = 50; }
            else if (type === "countdown") { defaults.name = "New Event"; defaults.datetime = ""; }
            
            config.widget_settings[name] = defaults;
            
            renderForm();
            renderWidgets();
        }

        function removeWidget(name) {
            if (confirm(`Remove widget ${name}?`)) {
                delete config.widget_positions[name];
                delete config.widget_settings[name];
                renderForm();
                renderWidgets();
            }
        }

        function renderForm() {
            const form = document.getElementById('config-form');
            form.innerHTML = '';
            
            const createSection = (title) => {
                const el = document.createElement('div');
                el.className = 'section-title';
                el.innerText = title;
                form.appendChild(el);
            };

            createSection("General");
            
            const addInput = (label, key, type='text', options=null) => {
                const div = document.createElement('div');
                div.className = 'form-group';
                const lbl = document.createElement('label');
                lbl.innerText = label;
                div.appendChild(lbl);
                
                let input;
                if (options) {
                    input = document.createElement('select');
                    options.forEach(opt => {
                        const o = document.createElement('option');
                        o.value = opt;
                        o.innerText = opt;
                        if (config[key] == opt) o.selected = true;
                        input.appendChild(o);
                    });
                    input.onchange = (e) => config[key] = e.target.value;
                } else if (type === 'checkbox') {
                    input = document.createElement('input');
                    input.type = 'checkbox';
                    input.checked = config[key];
                    input.onchange = (e) => config[key] = e.target.checked;
                } else {
                    input = document.createElement('input');
                    input.type = type;
                    input.value = config[key];
                    input.onchange = (e) => config[key] = type === 'number' ? parseFloat(e.target.value) : e.target.value;
                }
                div.appendChild(input);
                form.appendChild(div);
            };

            addInput("Fullscreen", "fullscreen", "checkbox");
            addInput("Mirror Video", "mirror_video", "checkbox");
            addInput("Text Scale", "text_scale_multiplier", "number");
            addInput("Background Opacity", "background_opacity", "number");
            
            // Add Widget Section
            const addSection = document.createElement('div');
            addSection.id = 'add-widget-section';
            const addTitle = document.createElement('div');
            addTitle.className = 'section-title';
            addTitle.innerText = "Add Widget";
            addSection.appendChild(addTitle);
            
            const addRow = document.createElement('div');
            addRow.className = 'add-widget-row';
            
            const typeSelect = document.createElement('select');
            typeSelect.id = 'new-widget-type';
            WIDGET_TYPES.sort().forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.innerText = t;
                typeSelect.appendChild(opt);
            });
            addRow.appendChild(typeSelect);
            
            const addBtn = document.createElement('button');
            addBtn.innerText = "Add";
            addBtn.onclick = addWidget;
            addRow.appendChild(addBtn);
            
            addSection.appendChild(addRow);
            form.appendChild(addSection);

            createSection("Widget Settings");
            
            const settingsGrid = document.createElement('div');
            settingsGrid.className = 'settings-grid';
            form.appendChild(settingsGrid);

            if (config.widget_settings) {
                // Sort widgets by name
                const sortedWidgets = Object.keys(config.widget_settings).sort().reduce(
                    (obj, key) => { 
                        obj[key] = config.widget_settings[key]; 
                        return obj;
                    }, 
                    {}
                );

                for (const [widgetName, settings] of Object.entries(sortedWidgets)) {
                    // Only show settings for active widgets (those in widget_positions)
                    if (!config.widget_positions || !config.widget_positions[widgetName]) continue;

                    const widgetDiv = document.createElement('div');
                    widgetDiv.className = 'widget-settings-box';
                    
                    const title = document.createElement('div');
                    title.className = 'widget-settings-title';
                    
                    const nameSpan = document.createElement('span');
                    nameSpan.innerText = widgetName;
                    title.appendChild(nameSpan);
                    
                    const removeBtn = document.createElement('button');
                    removeBtn.className = 'remove-widget-btn';
                    removeBtn.innerText = 'Remove';
                    removeBtn.onclick = () => removeWidget(widgetName);
                    title.appendChild(removeBtn);

                    widgetDiv.appendChild(title);

                    if (Object.keys(settings).length === 0) {
                        const empty = document.createElement('div');
                        empty.style.fontSize = '0.8rem';
                        empty.style.color = '#777';
                        empty.innerText = 'No settings available';
                        widgetDiv.appendChild(empty);
                    }

                    for (const [key, value] of Object.entries(settings)) {
                        const row = document.createElement('div');
                        row.style.marginBottom = '8px';
                        
                        const lbl = document.createElement('label');
                        lbl.innerText = key;
                        lbl.style.fontSize = '0.8rem';
                        row.appendChild(lbl);

                        let input;
                        if (Array.isArray(value)) {
                            input = document.createElement('input');
                            input.type = 'text';
                            input.value = value.join(', ');
                            input.onchange = (e) => config.widget_settings[widgetName][key] = e.target.value.split(',').map(s => s.trim());
                        } else if (typeof value === 'boolean') {
                            input = document.createElement('input');
                            input.type = 'checkbox';
                            input.checked = value;
                            input.onchange = (e) => config.widget_settings[widgetName][key] = e.target.checked;
                        } else if (typeof value === 'number') {
                            input = document.createElement('input');
                            input.type = 'number';
                            input.value = value;
                            input.onchange = (e) => config.widget_settings[widgetName][key] = parseFloat(e.target.value);
                        } else if (typeof value === 'object' && value !== null) {
                             input = document.createElement('textarea');
                             input.rows = 3;
                             input.value = JSON.stringify(value, null, 2);
                             input.onchange = (e) => {
                                 try {
                                     config.widget_settings[widgetName][key] = JSON.parse(e.target.value);
                                     e.target.style.borderColor = '#444';
                                 } catch(err) {
                                     e.target.style.borderColor = 'red';
                                 }
                             };
                        } else {
                            input = document.createElement('input');
                            input.type = 'text';
                            input.value = value;
                            input.onchange = (e) => config.widget_settings[widgetName][key] = e.target.value;
                        }
                        
                        row.appendChild(input);
                        widgetDiv.appendChild(row);
                    }
                    settingsGrid.appendChild(widgetDiv);
                }
            }
        }

        async function saveConfig() {
            const status = document.getElementById('status');
            status.innerText = "Saving...";
            try {
                await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                status.innerText = "Saved!";
                setTimeout(() => status.innerText = "", 2000);
                refreshPreview();
            } catch (e) {
                status.innerText = "Error saving";
                console.error(e);
            }
        }

        loadConfig();
        
        setInterval(() => {
            if (!draggedEl) refreshPreview();
        }, 5000);
    </script>
</body>
</html>
"""

class MagicMirrorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.server.app.config).encode("utf-8"))
        elif parsed.path == "/api/preview":
            self.handle_preview()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/config":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                new_config = json.loads(post_data)
                self.server.app.config.update(new_config)
                self.server.app.save_config()
                self.server.app.handle_remote_config_update()
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            except Exception as e:
                self.send_error(500, str(e))
        else:
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
        pass # Suppress logging

class MagicMirrorServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, app):
        super().__init__(server_address, RequestHandlerClass)
        self.app = app

def start_server(app, port=815):
    server = MagicMirrorServer(('0.0.0.0', port), MagicMirrorHandler, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server
