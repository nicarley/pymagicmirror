
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

        self.setup_widgets()
        self.setup_settings_panel()

        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.news_text = "Error: Could not open video device."
            return

        self.update_camera_feed()

    def load_config(self):
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
            # Ensure all keys from default_config are present
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
            for key, value in default_config["widget_positions"].items():
                 if key not in self.config["widget_positions"]:
                      self.config["widget_positions"][key] = value
        else:
            self.config = default_config
            self.save_config()
        
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

        settings_button = tk.Button(self, text="⚙️", font=("Helvetica", 20), command=self.toggle_settings_panel, relief="flat", bg="black", fg="white")
        settings_button.place(relx=1.0, rely=1.0, anchor="se")

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
        # ... (logic remains the same)
        self.after(900000, self.update_weather)

    def update_news(self):
        # ... (logic remains the same)
        self.after(1800000, self.update_news)

    def update_calendar(self):
        now = time.localtime()
        self.calendar_text = calendar.month(now.tm_year, now.tm_mon)
        self.after(3600000, self.update_calendar)

    def draw_text(self, frame, text, pos, font_scale, color, thickness=2, shadow_offset=2, anchor='nw'):
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Handle multiline text
        lines = text.split('\n')
        total_height = 0
        max_width = 0
        line_sizes = []
        for line in lines:
            size = cv2.getTextSize(line, font, font_scale, thickness)[0]
            line_sizes.append(size)
            max_width = max(max_width, size[0])
            total_height += size[1] + 10 # Add some line spacing

        # Calculate start position based on anchor
        x, y = pos
        if 'e' in anchor: x -= max_width
        if 's' in anchor: y -= total_height
        if anchor == 'center': 
            x -= max_width // 2
            y -= total_height // 2

        # Draw each line
        for i, line in enumerate(lines):
            line_y = y + line_sizes[i][1] + i * (line_sizes[i][1] + 10)
            line_x = x
            # Center each line individually if anchor is center
            if anchor == 'center':
                line_x = x + (max_width - line_sizes[i][0]) // 2

            shadow_pos = (line_x + shadow_offset, line_y + shadow_offset)
            text_pos = (line_x, line_y)

            cv2.putText(frame, line, shadow_pos, font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
            cv2.putText(frame, line, text_pos, font, font_scale, color, thickness, cv2.LINE_AA)

    def update_camera_feed(self):
        ret, frame = self.cap.read() if self.cap and self.cap.isOpened() else (False, None)
        if ret:
            win_width = self.winfo_width()
            win_height = self.winfo_height()

            if win_width < 2 or win_height < 2: # Avoid errors on startup
                self.after(10, self.update_camera_feed)
                return

            if self.video_rotation == 1: frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.video_rotation == 2: frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.video_rotation == 3: frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # Resize frame to fit window
            frame = cv2.resize(frame, (win_width, win_height))

            # --- Draw Widgets using relative positions ---
            positions = self.config["widget_positions"]
            self.draw_text(frame, self.time_text, (int(positions['time']['x'] * win_width), int(positions['time']['y'] * win_height)), 3, (255, 255, 255), thickness=3, anchor=positions['time']['anchor'])
            self.draw_text(frame, self.date_text, (int(positions['date']['x'] * win_width), int(positions['date']['y'] * win_height)), 1.2, (255, 255, 255), anchor=positions['date']['anchor'])
            self.draw_text(frame, self.weather_text, (int(positions['weather']['x'] * win_width), int(positions['weather']['y'] * win_height)), 1, (255, 255, 255), anchor=positions['weather']['anchor'])
            self.draw_text(frame, self.calendar_text, (int(positions['calendar']['x'] * win_width), int(positions['calendar']['y'] * win_height)), 0.8, (255, 255, 255), thickness=1, anchor=positions['calendar']['anchor'])
            self.draw_text(frame, self.news_text, (int(positions['news']['x'] * win_width), int(positions['news']['y'] * win_height)), 0.8, (255, 255, 255), thickness=1, anchor=positions['news']['anchor'])

            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            tk_image = ImageTk.PhotoImage(image=pil_image)

            self.camera_label.config(image=tk_image)
            self.camera_label.image = tk_image

        self.after(10, self.update_camera_feed)

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
