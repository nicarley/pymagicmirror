
import time
import calendar
import requests
from datetime import datetime
import cv2
import numpy as np
import math

class BaseWidget:
    def __init__(self, config, widget_name):
        self.config = config
        self.widget_name = widget_name
        self.text = ""
        self.params = self.get_draw_params()

    def get_position(self, win_width, win_height):
        pos_data = self.config["widget_positions"][self.widget_name]
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
        all_params = {
            "time": {"scale": 3, "thick": 3}, 
            "date": {"scale": 1.2, "thick": 2}, 
            "weather": {"scale": 1, "thick": 2}, 
            "calendar": {"scale": 0.8, "thick": 1}, 
            "news": {"scale": 0.8, "thick": 1},
            "forecast": {"scale": 0.8, "thick": 1},
            "radar": {"scale": 1, "thick": 1} # Not used for text, but good practice
        }
        return all_params.get(self.widget_name, {"scale": 1, "thick": 2})

# ... Other widget classes (Time, Date, Weather, etc.) are the same ...
class TimeWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="time"):
        super().__init__(config, widget_name)

    def _update_text(self):
        self.text = time.strftime('%H:%M:%S')

    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class DateWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="date"):
        super().__init__(config, widget_name)

    def _update_text(self):
        self.text = time.strftime('%A, %B %d, %Y')

    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class WeatherWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="weather"):
        super().__init__(config, widget_name)

    def _update_text(self):
        api_key = self.config.get("weather_api_key")
        location = self.config.get("weather_location")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            self.text = "Set Weather API Key"
            return
        if not location:
            self.text = "Set Weather Location"
            return
        base_url = "http://api.openweathermap.org/data/2.5/weather?"
        complete_url = f"{base_url}appid={api_key}&q={location}&units=metric"
        try:
            response = requests.get(complete_url)
            weather_data = response.json()
            if weather_data.get("cod") != 200:
                self.text = f"Weather Error:\n{weather_data.get('message')}"
            else:
                main = weather_data["main"]
                weather = weather_data["weather"][0]
                temp = main["temp"]
                description = weather["description"].title()
                self.text = f"{location}\n{description}, {temp:.0f}°C"
        except requests.exceptions.RequestException:
            self.text = "Weather: Conn Error"
        except Exception as e:
            self.text = "Weather: Error"
            print(f"Weather update error: {e}")

    def update(self, app):
        self._update_text()
        app.after(900000, lambda: self.update(app))

class FiveDayForecastWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="forecast"):
        super().__init__(config, widget_name)

    def _update_text(self):
        api_key = self.config.get("weather_api_key")
        location = self.config.get("weather_location")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            self.text = "Set Weather API Key for Forecast"
            return
        if not location:
            self.text = "Set Weather Location for Forecast"
            return
        
        base_url = "http://api.openweathermap.org/data/2.5/forecast?"
        complete_url = f"{base_url}appid={api_key}&q={location}&units=metric"
        
        try:
            response = requests.get(complete_url)
            forecast_data = response.json()
            if forecast_data.get("cod") != "200":
                self.text = f"Forecast Error:\n{forecast_data.get('message')}"
                return

            daily_forecasts = {}
            for forecast in forecast_data['list']:
                day = datetime.fromtimestamp(forecast['dt']).strftime('%A')
                if day not in daily_forecasts:
                    daily_forecasts[day] = {
                        'temps': [],
                        'descs': []
                    }
                daily_forecasts[day]['temps'].append(forecast['main']['temp'])
                daily_forecasts[day]['descs'].append(forecast['weather'][0]['description'])

            forecast_lines = []
            today = datetime.now().strftime('%A')
            day_names = [today] + [(datetime.fromtimestamp(time.time() + 86400 * i)).strftime('%A') for i in range(1, 5)]

            for day in day_names:
                if day in daily_forecasts:
                    max_temp = max(daily_forecasts[day]['temps'])
                    min_temp = min(daily_forecasts[day]['temps'])
                    desc = max(set(daily_forecasts[day]['descs']), key=daily_forecasts[day]['descs'].count)
                    forecast_lines.append(f"{day[:3]}: {desc.title()}, {min_temp:.0f}°/{max_temp:.0f}°C")
            
            self.text = "\n".join(forecast_lines)

        except requests.exceptions.RequestException:
            self.text = "Forecast: Conn Error"
        except Exception as e:
            self.text = "Forecast: Error"
            print(f"Forecast update error: {e}")

    def update(self, app):
        self._update_text()
        app.after(14400000, lambda: self.update(app))

class NewsWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="news"):
        super().__init__(config, widget_name)

    def _update_text(self):
        api_key = self.config.get("news_api_key")
        if not api_key or api_key == "YOUR_API_KEY_HERE":
            self.text = "Set News API Key"
            return
        location = self.config.get("weather_location", "")
        country = location.split(',')[-1].strip().lower() if ',' in location else "us"
        base_url = "https://newsapi.org/v2/top-headlines?"
        complete_url = f"{base_url}country={country}&apiKey={api_key}&pageSize=3"
        try:
            response = requests.get(complete_url)
            news_data = response.json()
            if news_data.get("status") != "ok":
                self.text = f"News Error: {news_data.get('message')}"
            else:
                articles = news_data.get("articles", [])
                headlines = [f"• {article['title']}" for article in articles]
                self.text = "\n".join(headlines) if headlines else "No news available."
        except requests.exceptions.RequestException:
            self.text = "News: Conn Error"
        except Exception as e:
            self.text = "News: Error"
            print(f"News update error: {e}")

    def update(self, app):
        self._update_text()
        app.after(1800000, lambda: self.update(app))

class CalendarWidget(BaseWidget): # ...
    def __init__(self, config, widget_name="calendar"):
        super().__init__(config, widget_name)

    def _update_text(self):
        now = time.localtime()
        self.text = calendar.month(now.tm_year, now.tm_mon)

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

        geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={api_key}"
        try:
            response = requests.get(geocode_url)
            data = response.json()
            if data:
                lat, lon = data[0]['lat'], data[0]['lon']
                self.lat_lon_cache[location] = (lat, lon)
                return lat, lon
        except Exception as e:
            print(f"Geocoding error: {e}")
        return None, None

    def _latlon_to_tile_coords(self, lat, lon, zoom):
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return xtile, ytile

    def _update_radar_image(self):
        lat, lon = self._get_lat_lon()
        if lat is None or lon is None: 
            self.radar_image = None
            return

        zoom = self.config["radar_settings"]["zoom"]
        xtile, ytile = self._latlon_to_tile_coords(lat, lon, zoom)
        api_key = self.config.get("weather_api_key")

        tile_url = f"https://tile.openweathermap.org/map/precipitation_new/{zoom}/{xtile}/{ytile}.png?appid={api_key}"
        try:
            response = requests.get(tile_url)
            if response.status_code == 200:
                img_array = np.frombuffer(response.content, dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                self.radar_image = cv2.resize(img_gray, (self.config["radar_settings"]["size"], self.config["radar_settings"]["size"]))
            else:
                self.radar_image = None
        except Exception as e:
            print(f"Radar image fetch error: {e}")
            self.radar_image = None

    def update(self, app):
        self._update_radar_image()
        app.after(900000, lambda: self.update(app)) # Update every 15 minutes

    def draw(self, frame, app):
        if self.radar_image is None: return

        win_width, win_height = frame.shape[1], frame.shape[0]
        x, y, anchor = self.get_position(win_width, win_height)
        size = self.config["radar_settings"]["size"]

        x0, y0 = x, y
        if 'e' in anchor: x0 -= size
        if 's' in anchor: y0 -= size
        if anchor == 'center':
            x0 -= size // 2
            y0 -= size // 2

        if x0 + size > win_width or y0 + size > win_height or x0 < 0 or y0 < 0:
            return # Don't draw if out of bounds

        roi = frame[y0:y0+size, x0:x0+size]
        radar_3_channel = cv2.cvtColor(self.radar_image, cv2.COLOR_GRAY2BGR)
        
        # Create a mask of the radar image where pixels are not black
        mask = cv2.threshold(self.radar_image, 10, 255, cv2.THRESH_BINARY)[1]
        mask_inv = cv2.bitwise_not(mask)
        
        # Black-out the area of the radar image in the ROI
        frame_bg = cv2.bitwise_and(roi, roi, mask=mask_inv)
        
        # Take only region of radar image.
        radar_fg = cv2.bitwise_and(radar_3_channel, radar_3_channel, mask=mask)

        # Add the two images
        dst = cv2.add(frame_bg, radar_fg)
        frame[y0:y0+size, x0:x0+size] = dst

class WidgetManager:
    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.widgets = {
            "time": TimeWidget(config),
            "date": DateWidget(config),
            "weather": WeatherWidget(config),
            "news": NewsWidget(config),
            "calendar": CalendarWidget(config),
            "forecast": FiveDayForecastWidget(config),
            "radar": RadarWidget(config)
        }
        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def draw_all(self, frame):
        for widget in self.widgets.values():
            widget.draw(frame, self.app)
