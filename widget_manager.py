
import time
import calendar
import requests
from datetime import datetime
import cv2
import numpy as np
import math

# ... (BaseWidget and other widget classes remain the same) ...
class BaseWidget:
    def __init__(self, config, widget_name):
        self.config = config
        self.widget_name = widget_name
        self.text = ""
        self.params = self.get_draw_params()

    def get_position(self, win_width, win_height):
        pos_data = self.config["widget_positions"].get(self.widget_name)
        if not pos_data: return 0, 0, 'nw'
        x = int(pos_data['x'] * win_width)
        y = int(pos_data['y'] * win_height)
        return x, y, pos_data['anchor']

    def update(self, app):
        pass

    def draw(self, frame, app):
        win_width, win_height = frame.shape[1], frame.shape[0]
        x, y, anchor = self.get_position(win_width, win_height)
        app.draw_text(frame, self.text, (x, y), self.params["scale"], (255, 255, 255), thickness=self.params["thick"], anchor=anchor)

    def get_draw_params(self):
        widget_type = self.widget_name.split('_')[0]
        all_params = {
            "time": {"scale": 3, "thick": 3}, 
            "date": {"scale": 1.2, "thick": 2}, 
            "weather": {"scale": 1, "thick": 2}, 
            "calendar": {"scale": 0.8, "thick": 1}, 
            "news": {"scale": 0.8, "thick": 1},
            "forecast": {"scale": 0.8, "thick": 1},
            "radar": {"scale": 1, "thick": 1}
        }
        return all_params.get(widget_type, {"scale": 1, "thick": 2})

class TimeWidget(BaseWidget):
    def _update_text(self):
        self.text = time.strftime('%H:%M:%S')
    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class DateWidget(BaseWidget):
    def _update_text(self):
        self.text = time.strftime('%A, %B %d, %Y')
    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class WeatherWidget(BaseWidget):
    def _update_text(self):
        api_key = self.config.get("weather_api_key")
        location = self.config.get("weather_location")
        if not api_key or api_key == "YOUR_API_KEY_HERE": self.text = "Set Weather API Key"; return
        if not location: self.text = "Set Weather Location"; return
        try:
            response = requests.get(f"http://api.openweathermap.org/data/2.5/weather?appid={api_key}&q={location}&units=metric")
            data = response.json()
            if data.get("cod") != 200: self.text = f"Weather Error:\n{data.get('message')}"; return
            self.text = f"{location}\n{data['weather'][0]['description'].title()}, {data['main']['temp']:.0f}°C"
        except Exception as e: self.text = "Weather: Conn Error"; print(f"Weather update error: {e}")
    def update(self, app):
        self._update_text()
        app.after(900000, lambda: self.update(app))

class FiveDayForecastWidget(BaseWidget):
    def _update_text(self):
        api_key = self.config.get("weather_api_key")
        location = self.config.get("weather_location")
        if not api_key or api_key == "YOUR_API_KEY_HERE": self.text = "Set Weather API Key"; return
        if not location: self.text = "Set Weather Location"; return
        try:
            response = requests.get(f"http://api.openweathermap.org/data/2.5/forecast?appid={api_key}&q={location}&units=metric")
            data = response.json()
            if data.get("cod") != "200": self.text = f"Forecast Error:\n{data.get('message')}"; return
            daily = {}
            for f in data['list']:
                day = datetime.fromtimestamp(f['dt']).strftime('%Y-%m-%d')
                if day not in daily: daily[day] = {'temps': [], 'descs': []}
                daily[day]['temps'].append(f['main']['temp'])
                daily[day]['descs'].append(f['weather'][0]['description'])
            lines = []
            for day_str, values in sorted(daily.items())[:5]:
                day_name = datetime.strptime(day_str, '%Y-%m-%d').strftime('%a')
                desc = max(set(values['descs']), key=values['descs'].count)
                lines.append(f"{day_name}: {desc.title()}, {min(values['temps']):.0f}°/{max(values['temps']):.0f}°C")
            self.text = "\n".join(lines)
        except Exception as e: self.text = "Forecast: Conn Error"; print(f"Forecast update error: {e}")
    def update(self, app):
        self._update_text()
        app.after(14400000, lambda: self.update(app))

class NewsWidget(BaseWidget):
    def _update_text(self):
        api_key = self.config.get("news_api_key")
        if not api_key or api_key == "YOUR_API_KEY_HERE": self.text = "Set News API Key"; return
        loc = self.config.get("weather_location", "")
        country = loc.split(',')[-1].strip().lower() if ',' in loc else "us"
        try:
            response = requests.get(f"https://newsapi.org/v2/top-headlines?country={country}&apiKey={api_key}&pageSize=3")
            data = response.json()
            if data.get("status") != "ok": self.text = f"News Error: {data.get('message')}"; return
            self.text = "\n".join([f"• {a['title']}" for a in data.get("articles", [])]) or "No news."
        except Exception as e: self.text = "News: Conn Error"; print(f"News update error: {e}")
    def update(self, app):
        self._update_text()
        app.after(1800000, lambda: self.update(app))

class CalendarWidget(BaseWidget):
    def _update_text(self):
        self.text = calendar.month(time.localtime().tm_year, time.localtime().tm_mon)
    def update(self, app):
        self._update_text()
        app.after(3600000, lambda: self.update(app))

class RadarWidget(BaseWidget):
    def __init__(self, config, widget_name="radar"):
        super().__init__(config, widget_name)
        self.radar_image = None
        self.lat_lon_cache = {}

    def _get_lat_lon(self):
        location = self.config.get("weather_location")
        if not location: return None, None
        if location in self.lat_lon_cache: return self.lat_lon_cache[location]
        api_key = self.config.get("weather_api_key")
        if not api_key or api_key == "YOUR_API_KEY_HERE": return None, None
        try:
            response = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={api_key}")
            data = response.json()
            if data: self.lat_lon_cache[location] = (data[0]['lat'], data[0]['lon']); return self.lat_lon_cache[location]
        except Exception as e: print(f"Geocoding error: {e}")
        return None, None

    def _latlon_to_tile_coords(self, lat, lon, zoom):
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return xtile, ytile

    def _update_radar_image(self):
        lat, lon = self._get_lat_lon()
        if lat is None: self.radar_image = None; return
        zoom = self.config["radar_settings"]["zoom"]
        xtile, ytile = self._latlon_to_tile_coords(lat, lon, zoom)
        api_key = self.config.get("weather_api_key")
        try:
            response = requests.get(f"https://tile.openweathermap.org/map/precipitation_new/{zoom}/{xtile}/{ytile}.png?appid={api_key}")
            if response.status_code == 200:
                img_array = np.frombuffer(response.content, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                self.radar_image = cv2.resize(img_gray, (self.config["radar_settings"]["size"], self.config["radar_settings"]["size"]))
            else: self.radar_image = None
        except Exception as e: self.radar_image = None; print(f"Radar image fetch error: {e}")

    def update(self, app):
        self._update_radar_image()
        app.after(900000, lambda: self.update(app))

    def draw(self, frame, app):
        if self.radar_image is None: return
        win_width, win_height = frame.shape[1], frame.shape[0]
        x, y, anchor = self.get_position(win_width, win_height)
        size = self.config["radar_settings"]["size"]
        x0, y0 = x, y
        if 'e' in anchor: x0 -= size
        if 's' in anchor: y0 -= size
        if anchor == 'center': x0 -= size // 2; y0 -= size // 2
        if x0 + size > win_width or y0 + size > win_height or x0 < 0 or y0 < 0: return
        roi = frame[y0:y0+size, x0:x0+size]
        radar_3_channel = cv2.cvtColor(self.radar_image, cv2.COLOR_GRAY2BGR)
        mask = cv2.threshold(self.radar_image, 10, 255, cv2.THRESH_BINARY)[1]
        mask_inv = cv2.bitwise_not(mask)
        frame_bg = cv2.bitwise_and(roi, roi, mask=mask_inv)
        radar_fg = cv2.bitwise_and(radar_3_channel, radar_3_channel, mask=mask)
        dst = cv2.add(frame_bg, radar_fg)
        frame[y0:y0+size, x0:x0+size] = dst

WIDGET_CLASSES = {
    "time": TimeWidget,
    "date": DateWidget,
    "weather": WeatherWidget,
    "news": NewsWidget,
    "calendar": CalendarWidget,
    "forecast": FiveDayForecastWidget,
    "radar": RadarWidget
}

class WidgetManager:
    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.widgets = {}
        self.load_widgets()

    def load_widgets(self):
        active_widgets = self.config.get("widget_positions", {}).keys()
        for widget_name in active_widgets:
            widget_type = widget_name.split('_')[0]
            if widget_type in WIDGET_CLASSES:
                self.widgets[widget_name] = WIDGET_CLASSES[widget_type](self.config, widget_name)
            else:
                print(f"Warning: Unknown widget type '{widget_type}' for widget '{widget_name}' in config.")
        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def draw_all(self, frame):
        for widget_name in self.config.get("widget_positions", {}).keys():
            if widget_name in self.widgets:
                self.widgets[widget_name].draw(frame, self.app)
