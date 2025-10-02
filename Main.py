
import tkinter as tk
from tkinter import simpledialog, messagebox
import cv2
from PIL import Image, ImageTk
import time
import json
import os
import requests
import calendar

CONFIG_FILE = "config.json"

class MagicMirrorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.video_rotation = 0
        self.edit_mode = False
        self.drag_data = {"widget": None, "offset_x": 0, "offset_y": 0}
        self.load_config()

        self.time_text = ""
        self.date_text = ""
        self.weather_text = "Loading..."
        self.news_text = "Loading..."
        self.calendar_text = ""

        self.title("Magic Mirror")
        self.attributes('-fullscreen', True)
        self.bind('<Escape>', self.toggle_fullscreen)
        self.configure(bg='black')

        self.camera_label = tk.Label(self)
        self.camera_label.pack(fill="both", expand=True)
        self.camera_label.bind("<Button-1>", self.on_mouse_press)
        self.camera_label.bind("<B1-Motion>", self.on_mouse_drag)
        self.camera_label.bind("<ButtonRelease-1>", self.on_mouse_release)

        self.setup_widgets()
        self.setup_settings_panel()

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.news_text = "Error: Could not open video device."
            return

        self.update_camera_feed()

    def load_config(self):
        # ... (same as before)
        default_config = {
            "weather_location": "New York, US",
            "weather_api_key": "YOUR_API_KEY_HERE",
            "news_api_key": "YOUR_API_KEY_HERE",
            "video_rotation": 0,
            "widget_positions": {
                "time": {"x": 0.5, "y": 0.15, "anchor": "center"},
                "date": {"x": 0.5, "y": 0.20, "anchor": "center"},
                "weather": {"x": 0.05, "y": 0.1, "anchor": "nw"},
                "calendar": {"x": 0.95, "y": 0.1, "anchor": "ne"},
                "news": {"x": 0.5, "y": 0.9, "anchor": "s"}
            }
        }
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
            for key, value in default_config["widget_positions"].items():
                 if key not in self.config.get("widget_positions", {}):
                      self.config["widget_positions"][key] = value
        else:
            self.config = default_config
        self.save_config() # Save to ensure new keys are written
        self.video_rotation = self.config.get("video_rotation", 0)

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def setup_widgets(self):
        self.update_time()
        self.update_weather()
        self.update_news()
        self.update_calendar()

    def setup_settings_panel(self):
        self.settings_visible = False
        self.settings_frame = tk.Frame(self, bg="#222", bd=2, relief="solid")

        # ... (other settings)
        tk.Label(self.settings_frame, text="Weather Location:", fg="white", bg="#222").pack(pady=5)
        self.location_entry = tk.Entry(self.settings_frame)
        self.location_entry.pack(pady=5, padx=10)
        self.location_entry.insert(0, self.config.get("weather_location", ""))

        tk.Label(self.settings_frame, text="Weather API Key:", fg="white", bg="#222").pack(pady=5)
        self.weather_api_key_entry = tk.Entry(self.settings_frame, width=40)
        self.weather_api_key_entry.pack(pady=5, padx=10)
        self.weather_api_key_entry.insert(0, self.config.get("weather_api_key", ""))

        tk.Label(self.settings_frame, text="News API Key:", fg="white", bg="#222").pack(pady=5)
        self.news_api_key_entry = tk.Entry(self.settings_frame, width=40)
        self.news_api_key_entry.pack(pady=5, padx=10)
        self.news_api_key_entry.insert(0, self.config.get("news_api_key", ""))

        save_button = tk.Button(self.settings_frame, text="Save Settings", command=self.save_settings_from_panel)
        save_button.pack(pady=10)

        rotate_button = tk.Button(self.settings_frame, text="Rotate Video", command=self.rotate_video)
        rotate_button.pack(pady=10)

        self.edit_layout_button = tk.Button(self.settings_frame, text="Edit Layout", command=self.toggle_edit_mode)
        self.edit_layout_button.pack(pady=10)

        settings_button = tk.Button(self, text="⚙️", font=("Helvetica", 20), command=self.toggle_settings_panel, relief="flat", bg="black", fg="white")
        settings_button.place(relx=1.0, rely=1.0, anchor="se")

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_layout_button.config(text="Save Layout")
            messagebox.showinfo("Layout Editing", "You can now drag and drop widgets. Click 'Save Layout' in the settings panel when you are done.")
        else:
            self.edit_layout_button.config(text="Edit Layout")
            self.save_config()
            messagebox.showinfo("Layout Saved", "Widget positions have been saved.")

    def get_widget_bbox(self, widget_name, win_width, win_height):
        widget_text = getattr(self, f"{widget_name}_text", "")
        if not widget_text: return None
        pos_data = self.config["widget_positions"][widget_name]
        params = {"time": {"scale": 3, "thick": 3}, "date": {"scale": 1.2, "thick": 2}, "weather": {"scale": 1, "thick": 2}, "calendar": {"scale": 0.8, "thick": 1}, "news": {"scale": 0.8, "thick": 1}}
        font_scale, thickness = params[widget_name]["scale"], params[widget_name]["thick"]
        font = cv2.FONT_HERSHEY_SIMPLEX
        max_width, total_height = 0, 0
        lines = widget_text.split('\n')
        for line in lines:
            size = cv2.getTextSize(line, font, font_scale, thickness)[0]
            max_width = max(max_width, size[0])
            total_height += size[1] + 10
        x0, y0 = int(pos_data['x'] * win_width), int(pos_data['y'] * win_height)
        anchor = pos_data['anchor']
        if 'e' in anchor: x0 -= max_width
        if 's' in anchor: y0 -= total_height
        if anchor == 'center':
            x0 -= max_width // 2
            y0 -= total_height // 2
        return (x0, y0, x0 + max_width, y0 + total_height)

    def on_mouse_press(self, event):
        if not self.edit_mode: return
        win_width, win_height = self.winfo_width(), self.winfo_height()
        for name in self.config["widget_positions"]:
            bbox = self.get_widget_bbox(name, win_width, win_height)
            if bbox and bbox[0] <= event.x <= bbox[2] and bbox[1] <= event.y <= bbox[3]:
                self.drag_data['widget'] = name
                self.drag_data['offset_x'] = event.x - bbox[0]
                self.drag_data['offset_y'] = event.y - bbox[1]
                return

    def on_mouse_drag(self, event):
        if not self.edit_mode or not self.drag_data.get("widget"): return
        widget_name = self.drag_data["widget"]
        win_width, win_height = self.winfo_width(), self.winfo_height()
        new_x0 = event.x - self.drag_data['offset_x']
        new_y0 = event.y - self.drag_data['offset_y']
        bbox = self.get_widget_bbox(widget_name, win_width, win_height)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        anchor = self.config["widget_positions"][widget_name]['anchor']
        anchor_x, anchor_y = new_x0, new_y0
        if 'e' in anchor: anchor_x += w
        if 's' in anchor: anchor_y += h
        if anchor == 'center':
            anchor_x += w // 2
            anchor_y += h // 2
        self.config["widget_positions"][widget_name]['x'] = anchor_x / win_width
        self.config["widget_positions"][widget_name]['y'] = anchor_y / win_height

    def on_mouse_release(self, event):
        self.drag_data["widget"] = None

    def update_camera_feed(self):
        ret, frame = self.cap.read() if self.cap and self.cap.isOpened() else (False, None)
        if ret:
            win_width, win_height = self.winfo_width(), self.winfo_height()
            if win_width < 2 or win_height < 2: 
                self.after(10, self.update_camera_feed)
                return
            if self.video_rotation == 1: frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.video_rotation == 2: frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.video_rotation == 3: frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            frame = cv2.resize(frame, (win_width, win_height))
            if self.edit_mode:
                for name in self.config["widget_positions"]:
                    bbox = self.get_widget_bbox(name, win_width, win_height)
                    if bbox:
                        overlay = frame.copy()
                        cv2.rectangle(overlay, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), -1)
                        frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
                        cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            positions = self.config["widget_positions"]
            for name, pos_data in positions.items():
                text = getattr(self, f"{name}_text", "")
                params = {"time": {"scale": 3, "thick": 3}, "date": {"scale": 1.2, "thick": 2}, "weather": {"scale": 1, "thick": 2}, "calendar": {"scale": 0.8, "thick": 1}, "news": {"scale": 0.8, "thick": 1}}
                self.draw_text(frame, text, (int(pos_data['x'] * win_width), int(pos_data['y'] * win_height)), params[name]["scale"], (255, 255, 255), thickness=params[name]["thick"], anchor=pos_data['anchor'])
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tk_image = ImageTk.PhotoImage(image=pil_image)
            self.camera_label.config(image=tk_image)
            self.camera_label.image = tk_image
        self.after(10, self.update_camera_feed)

    # ... (all other methods like draw_text, update_time, etc. are the same) ...
    def toggle_settings_panel(self):
        if self.settings_visible:
            self.settings_frame.place_forget()
        else:
            self.settings_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.settings_visible = not self.settings_visible

    def save_settings_from_panel(self):
        self.config["weather_location"] = self.location_entry.get()
        self.config["weather_api_key"] = self.weather_api_key_entry.get()
        self.config["news_api_key"] = self.news_api_key_entry.get()
        self.save_config()
        messagebox.showinfo("Settings Saved", "Settings have been saved.")
        self.toggle_settings_panel()
        self.update_weather()
        self.update_news()

    def rotate_video(self):
        self.video_rotation = (self.video_rotation + 1) % 4
        self.config["video_rotation"] = self.video_rotation
        self.save_config()
        messagebox.showinfo("Settings", f"Video rotation set. It will apply on the next frame.")

    def update_time(self):
        self.time_text = time.strftime('%H:%M:%S')
        self.date_text = time.strftime('%A, %B %d, %Y')
        self.after(1000, self.update_time)

    def update_weather(self):
        api_key = self.config.get("weather_api_key")
        location = self.config.get("weather_location")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            self.weather_text = "Set Weather API Key"
        elif not location:
            self.weather_text = "Set Weather Location"
        else:
            base_url = "http://api.openweathermap.org/data/2.5/weather?"
            complete_url = f"{base_url}appid={api_key}&q={location}&units=metric"
            try:
                response = requests.get(complete_url)
                weather_data = response.json()
                if weather_data.get("cod") != 200:
                    self.weather_text = f"Weather Error:\n{weather_data.get('message')}"
                else:
                    main = weather_data["main"]
                    weather = weather_data["weather"][0]
                    temp = main["temp"]
                    description = weather["description"].title()
                    self.weather_text = f"{location}\n{description}, {temp:.0f}°C"
            except requests.exceptions.RequestException:
                self.weather_text = "Weather: Conn Error"
            except Exception as e:
                self.weather_text = "Weather: Error"
                print(f"Weather update error: {e}")
        self.after(900000, self.update_weather)

    def update_news(self):
        api_key = self.config.get("news_api_key")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            self.news_text = "Set News API Key"
        else:
            location = self.config.get("weather_location", "")
            country = location.split(',')[-1].strip().lower() if ',' in location else "us"
            base_url = "https://newsapi.org/v2/top-headlines?"
            complete_url = f"{base_url}country={country}&apiKey={api_key}&pageSize=3"
            try:
                response = requests.get(complete_url)
                news_data = response.json()
                if news_data.get("status") != "ok":
                    self.news_text = f"News Error: {news_data.get('message')}"
                else:
                    articles = news_data.get("articles", [])
                    headlines = [f"• {article['title']}" for article in articles]
                    self.news_text = "\n".join(headlines) if headlines else "No news available."
            except requests.exceptions.RequestException:
                self.news_text = "News: Conn Error"
            except Exception as e:
                self.news_text = "News: Error"
                print(f"News update error: {e}")
        self.after(1800000, self.update_news)

    def update_calendar(self):
        now = time.localtime()
        self.calendar_text = calendar.month(now.tm_year, now.tm_mon)
        self.after(3600000, self.update_calendar)

    def draw_text(self, frame, text, pos, font_scale, color, thickness=2, shadow_offset=2, anchor='nw'):
        font = cv2.FONT_HERSHEY_SIMPLEX
        lines = text.split('\n')
        total_height, max_width = 0, 0
        line_sizes = []
        for line in lines:
            size = cv2.getTextSize(line, font, font_scale, thickness)[0]
            line_sizes.append(size)
            max_width = max(max_width, size[0])
            total_height += size[1] + 10
        x, y = pos
        if 'e' in anchor: x -= max_width
        if 's' in anchor: y -= total_height
        if anchor == 'center': 
            x -= max_width // 2
            y -= total_height // 2
        for i, line in enumerate(lines):
            line_y = y + line_sizes[i][1] + i * (line_sizes[i][1] + 10)
            line_x = x
            if anchor == 'center':
                line_x = x + (max_width - line_sizes[i][0]) // 2
            shadow_pos = (line_x + shadow_offset, line_y + shadow_offset)
            text_pos = (line_x, line_y)
            cv2.putText(frame, line, shadow_pos, font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
            cv2.putText(frame, line, text_pos, font, font_scale, color, thickness, cv2.LINE_AA)

    def toggle_fullscreen(self, event=None):
        self.attributes('-fullscreen', not self.attributes('-fullscreen'))

    def on_closing(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.destroy()

if __name__ == "__main__":
    app = MagicMirrorApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
