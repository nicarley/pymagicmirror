
import tkinter as tk
from tkinter import simpledialog, messagebox, Listbox, Toplevel, Checkbutton, BooleanVar
import cv2
from PIL import Image, ImageTk
import time
import json
import os
import requests
from widget_manager import WidgetManager, WIDGET_CLASSES
import sys

CONFIG_FILE = "config.json"

class WidgetManagerDialog(Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.title("Widget Manager")
        self.config = parent.config
        self.parent = parent
        self.geometry("400x350")

        tk.Label(self, text="Available Widgets").pack(pady=5)
        self.available_list = Listbox(self)
        self.available_list.pack(fill="both", expand=True, padx=10, pady=5)
        for name in sorted(WIDGET_CLASSES.keys()):
            self.available_list.insert("end", name)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=5)
        add_btn = tk.Button(btn_frame, text="<< Add", command=self.add_widget)
        add_btn.pack(side="left", padx=5)
        remove_btn = tk.Button(btn_frame, text="Remove >>", command=self.remove_widget)
        remove_btn.pack(side="left", padx=5)

        tk.Label(self, text="Active Widgets").pack(pady=5)
        self.active_list = Listbox(self)
        self.active_list.pack(fill="both", expand=True, padx=10, pady=5)
        for name in sorted(self.config.get("widget_positions", {})):
            self.active_list.insert("end", name)

        save_btn = tk.Button(self, text="Save and Restart", command=self.save_and_restart)
        save_btn.pack(pady=10)

    def add_widget(self):
        selected_indices = self.available_list.curselection()
        if not selected_indices: return
        widget_type = self.available_list.get(selected_indices[0])
        
        i = 1
        while True:
            new_name = f"{widget_type}_{i}"
            if new_name not in self.active_list.get(0, "end"):
                break
            i += 1

        self.active_list.insert("end", new_name)

    def remove_widget(self):
        selected_indices = self.active_list.curselection()
        if not selected_indices: return
        self.active_list.delete(selected_indices[0])

    def save_and_restart(self):
        self.config["widget_positions"] = {}
        for widget_name in self.active_list.get(0, "end"):
            self.config["widget_positions"][widget_name] = self.parent.config["widget_positions"].get(widget_name, {"x": 0.5, "y": 0.5, "anchor": "center"})
        
        self.parent.save_config()
        messagebox.showinfo("Restart Required", "The application needs to be restarted for widget changes to take effect.")
        self.parent.on_closing(restart=True)

class MagicMirrorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.edit_mode = False
        self.drag_data = {"widget": None, "offset_x": 0, "offset_y": 0}
        self.load_config()

        self.title("Magic Mirror")
        self.attributes('-fullscreen', True)
        self.bind('<Escape>', lambda e: self.toggle_fullscreen(True))
        self.configure(bg='black')

        self.camera_label = tk.Label(self)
        self.camera_label.pack(fill="both", expand=True)
        self.camera_label.bind("<Button-1>", self.on_mouse_press)
        self.camera_label.bind("<B1-Motion>", self.on_mouse_drag)
        self.camera_label.bind("<ButtonRelease-1>", self.on_mouse_release)

        self.widget_manager = WidgetManager(self, self.config)
        self.setup_settings_panel()

        self.cap = cv2.VideoCapture(0)
        self.update_camera_feed()

    def load_config(self):
        default_config = {
            "weather_location": "New York, US", "weather_api_key": "YOUR_API_KEY_HERE",
            "news_api_key": "YOUR_API_KEY_HERE", "video_rotation": 0, "mirror_video": False,
            "widget_positions": {
                "time_1": {"x": 0.5, "y": 0.1, "anchor": "n"},
                "date_1": {"x": 0.5, "y": 0.18, "anchor": "n"},
                "weather_1": {"x": 0.05, "y": 0.1, "anchor": "nw"},
                "calendar_1": {"x": 0.95, "y": 0.1, "anchor": "ne"},
                "news_1": {"x": 0.5, "y": 0.9, "anchor": "s"}
            },
            "radar_settings": {"zoom": 5, "size": 256}
        }
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f: self.config = json.load(f)
            for key, value in default_config.items():
                if key not in self.config: self.config[key] = value
                elif isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in self.config[key]: self.config[key][sub_key] = sub_value
        else: self.config = default_config
        self.save_config()
        self.video_rotation = self.config.get("video_rotation", 0)
        self.mirror_video = self.config.get("mirror_video", False)

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f: json.dump(self.config, f, indent=4)

    def setup_settings_panel(self):
        self.settings_visible = False
        self.settings_frame = tk.Frame(self, bg="#222", bd=2, relief="solid")
        self.mirror_video_var = BooleanVar(value=self.mirror_video)

        # Title bar for the settings panel
        title_bar = tk.Frame(self.settings_frame, bg="#222")
        title_bar.pack(side="top", fill="x", pady=5)

        tk.Label(title_bar, text="Settings", fg="white", bg="#222", font=("Helvetica", 16, "bold")).pack(side="left", padx=10)
        
        close_btn_x = tk.Button(title_bar, text="X", command=self.toggle_settings_panel, bg="#222", fg="white", relief="flat", font=("Helvetica", 12, "bold"))
        close_btn_x.pack(side="right", padx=5)

        # Settings content
        content_frame = tk.Frame(self.settings_frame, bg="#222")
        content_frame.pack(fill="both", expand=True, padx=10)

        tk.Label(content_frame, text="Weather Location:", fg="white", bg="#222").pack(pady=(10, 5))
        self.location_entry = tk.Entry(content_frame)
        self.location_entry.pack(pady=5, fill="x", expand=True)
        self.location_entry.insert(0, self.config.get("weather_location", ""))

        tk.Label(content_frame, text="Weather API Key:", fg="white", bg="#222").pack(pady=5)
        self.weather_api_key_entry = tk.Entry(content_frame, width=40)
        self.weather_api_key_entry.pack(pady=5, fill="x", expand=True)
        self.weather_api_key_entry.insert(0, self.config.get("weather_api_key", ""))

        tk.Label(content_frame, text="News API Key:", fg="white", bg="#222").pack(pady=5)
        self.news_api_key_entry = tk.Entry(content_frame, width=40)
        self.news_api_key_entry.pack(pady=5, fill="x", expand=True)
        self.news_api_key_entry.insert(0, self.config.get("news_api_key", ""))

        Checkbutton(content_frame, text="Mirror Video", variable=self.mirror_video_var, onvalue=True, offvalue=False, bg="#222", fg="white", selectcolor="#555").pack(pady=10)

        tk.Button(content_frame, text="Save Settings", command=self.save_settings_from_panel).pack(pady=10)
        tk.Button(content_frame, text="Rotate Video", command=self.rotate_video).pack(pady=5)
        self.edit_layout_button = tk.Button(content_frame, text="Edit Layout", command=self.toggle_edit_mode)
        self.edit_layout_button.pack(pady=5)
        tk.Button(content_frame, text="Manage Widgets", command=self.open_widget_manager).pack(pady=10)
        tk.Button(content_frame, text="Close", command=self.toggle_settings_panel).pack(pady=(5,10))

        self.settings_button = tk.Button(self, text="⚙️", font=("Helvetica", 20), command=self.toggle_settings_panel, relief="flat", bg="black", fg="white"); self.settings_button.place(relx=1.0, rely=1.0, anchor="se")

    def open_widget_manager(self):
        dialog = WidgetManagerDialog(self); self.wait_window(dialog)

    def save_settings_from_panel(self):
        self.config["weather_location"] = self.location_entry.get()
        self.config["weather_api_key"] = self.weather_api_key_entry.get()
        self.config["news_api_key"] = self.news_api_key_entry.get()
        self.config["mirror_video"] = self.mirror_video_var.get()
        self.mirror_video = self.mirror_video_var.get()
        self.save_config()
        messagebox.showinfo("Settings Saved", "Settings have been saved. API key changes may require a restart.")
        self.toggle_settings_panel()

    def get_widget_bbox(self, widget_name, win_width, win_height):
        widget = self.widget_manager.widgets.get(widget_name)
        if not widget: return None
        if hasattr(widget, 'text') and widget.text:
            font = cv2.FONT_HERSHEY_SIMPLEX; font_scale = widget.params['scale']; thickness = widget.params['thick']
            max_width, total_height = 0, 0
            for line in widget.text.split('\n'):
                size = cv2.getTextSize(line, font, font_scale, thickness)[0]
                max_width = max(max_width, size[0]); total_height += size[1] + 10
        elif hasattr(widget, 'radar_image') and widget.radar_image is not None:
            max_width = total_height = self.config["radar_settings"]["size"]
        else: return None
        pos_data = self.config["widget_positions"][widget_name]; x0, y0 = int(pos_data['x'] * win_width), int(pos_data['y'] * win_height); anchor = pos_data['anchor']
        if 'e' in anchor: x0 -= max_width
        if 's' in anchor: y0 -= total_height
        if anchor == 'center': x0 -= max_width // 2; y0 -= total_height // 2
        return (x0, y0, x0 + max_width, y0 + total_height)

    def on_mouse_press(self, event):
        if self.exit_fullscreen_btn_bbox and self.exit_fullscreen_btn_bbox[0] <= event.x <= self.exit_fullscreen_btn_bbox[2] and self.exit_fullscreen_btn_bbox[1] <= event.y <= self.exit_fullscreen_btn_bbox[3]:
            self.toggle_fullscreen(True); return
        if not self.edit_mode: return
        win_width, win_height = self.winfo_width(), self.winfo_height()
        for name in reversed(list(self.config["widget_positions"])):
            bbox = self.get_widget_bbox(name, win_width, win_height)
            if bbox and bbox[0] <= event.x <= bbox[2] and bbox[1] <= event.y <= bbox[3]:
                self.drag_data = {'widget': name, 'offset_x': event.x - bbox[0], 'offset_y': event.y - bbox[1]}; return

    def on_mouse_drag(self, event):
        if not self.edit_mode or not self.drag_data.get("widget"): return
        widget_name = self.drag_data["widget"]; win_width, win_height = self.winfo_width(), self.winfo_height()
        new_x0 = event.x - self.drag_data['offset_x']; new_y0 = event.y - self.drag_data['offset_y']
        bbox = self.get_widget_bbox(widget_name, win_width, win_height); w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        anchor = self.config["widget_positions"][widget_name]['anchor']; anchor_x, anchor_y = new_x0, new_y0
        if 'e' in anchor: anchor_x += w
        if 's' in anchor: anchor_y += h
        if anchor == 'center': anchor_x += w // 2; anchor_y += h // 2
        self.config["widget_positions"][widget_name]['x'] = anchor_x / win_width
        self.config["widget_positions"][widget_name]['y'] = anchor_y / win_height

    def on_mouse_release(self, event):
        self.drag_data["widget"] = None

    def draw_text(self, frame, text, pos, font_scale, color, thickness=2, shadow_offset=2, anchor='nw'):
        font = cv2.FONT_HERSHEY_SIMPLEX; lines = text.split('\n'); total_height, max_width = 0, 0; line_sizes = []
        for line in lines:
            size = cv2.getTextSize(line, font, font_scale, thickness)[0]; line_sizes.append(size)
            max_width = max(max_width, size[0]); total_height += size[1] + 10
        x, y = pos
        if 'e' in anchor: x -= max_width
        if 's' in anchor: y -= total_height
        if anchor == 'center': x -= max_width // 2; y -= total_height // 2
        for i, line in enumerate(lines):
            line_y = y + line_sizes[i][1] + i * (line_sizes[i][1] + 10)
            line_x = x + (max_width - line_sizes[i][0]) // 2 if anchor == 'center' else x
            cv2.putText(frame, line, (line_x + shadow_offset, line_y + shadow_offset), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
            cv2.putText(frame, line, (line_x, line_y), font, font_scale, color, thickness, cv2.LINE_AA)

    def update_camera_feed(self):
        ret, frame = self.cap.read() if self.cap and self.cap.isOpened() else (False, None)
        if ret:
            if self.mirror_video: frame = cv2.flip(frame, 1)
            rot = self.config.get("video_rotation", 0)
            if rot == 1: frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rot == 2: frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rot == 3: frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            win_width, win_height = self.winfo_width(), self.winfo_height()
            if win_width < 2 or win_height < 2: self.after(10, self.update_camera_feed); return
            frame = cv2.resize(frame, (win_width, win_height))
            if self.edit_mode:
                for name in self.config["widget_positions"]:
                    bbox = self.get_widget_bbox(name, win_width, win_height)
                    if bbox: cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            self.widget_manager.draw_all(frame)
            is_fullscreen = self.attributes('-fullscreen')
            if is_fullscreen:
                btn_size = 30; padding = 10; shadow_offset = 2
                self.exit_fullscreen_btn_bbox = (win_width - btn_size - padding, padding, win_width - padding, btn_size + padding)
                
                # Shadow for the button
                cv2.rectangle(frame, (self.exit_fullscreen_btn_bbox[0] + shadow_offset, self.exit_fullscreen_btn_bbox[1] + shadow_offset), (self.exit_fullscreen_btn_bbox[2] + shadow_offset, self.exit_fullscreen_btn_bbox[3] + shadow_offset), (0,0,0), 1)
                cv2.line(frame, (self.exit_fullscreen_btn_bbox[0]+5 + shadow_offset, self.exit_fullscreen_btn_bbox[1]+5 + shadow_offset), (self.exit_fullscreen_btn_bbox[2]-5 + shadow_offset, self.exit_fullscreen_btn_bbox[3]-5 + shadow_offset), (0,0,0), 2)
                cv2.line(frame, (self.exit_fullscreen_btn_bbox[0]+5 + shadow_offset, self.exit_fullscreen_btn_bbox[3]-5 + shadow_offset), (self.exit_fullscreen_btn_bbox[2]-5 + shadow_offset, self.exit_fullscreen_btn_bbox[1]+5 + shadow_offset), (0,0,0), 2)

                # Foreground button
                cv2.rectangle(frame, (self.exit_fullscreen_btn_bbox[0], self.exit_fullscreen_btn_bbox[1]), (self.exit_fullscreen_btn_bbox[2], self.exit_fullscreen_btn_bbox[3]), (255,255,255), 1)
                cv2.line(frame, (self.exit_fullscreen_btn_bbox[0]+5, self.exit_fullscreen_btn_bbox[1]+5), (self.exit_fullscreen_btn_bbox[2]-5, self.exit_fullscreen_btn_bbox[3]-5), (255,255,255), 2)
                cv2.line(frame, (self.exit_fullscreen_btn_bbox[0]+5, self.exit_fullscreen_btn_bbox[3]-5), (self.exit_fullscreen_btn_bbox[2]-5, self.exit_fullscreen_btn_bbox[1]+5), (255,255,255), 2)
            else: self.exit_fullscreen_btn_bbox = None
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)); tk_image = ImageTk.PhotoImage(image=pil_image)
            self.camera_label.config(image=tk_image); self.camera_label.image = tk_image
        self.after(10, self.update_camera_feed)

    def toggle_fullscreen(self, is_fullscreen):
        self.attributes('-fullscreen', not is_fullscreen)
        if is_fullscreen: self.geometry("1280x720")

    def on_closing(self, restart=False):
        if self.cap and self.cap.isOpened(): self.cap.release()
        self.destroy()
        if restart: os.execv(sys.executable, ['python'] + sys.argv)

    def toggle_settings_panel(self): self.settings_visible = not self.settings_visible; self.settings_frame.place(relx=0.5, rely=0.5, anchor="center") if self.settings_visible else self.settings_frame.place_forget()
    def rotate_video(self): self.config["video_rotation"] = (self.config.get("video_rotation", 0) + 1) % 4; self.save_config(); messagebox.showinfo("Settings", "Video rotation set.")
    def toggle_edit_mode(self): self.edit_mode = not self.edit_mode; self.edit_layout_button.config(text="Save Layout" if self.edit_mode else "Edit Layout"); self.save_config() if not self.edit_mode else messagebox.showinfo("Layout Editing", "Drag widgets to move them. Click 'Save Layout' when done.")

if __name__ == "__main__":
    app = MagicMirrorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
