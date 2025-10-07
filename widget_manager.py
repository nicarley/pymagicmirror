
import time
import calendar
import requests
from datetime import datetime
import cv2
import numpy as np
import math
import feedparser
from icalendar import Calendar
from pytz import utc

# --- NWS API Helper --- 
NWS_CACHE = {}
USER_AGENT = "MagicMirrorApp/1.0 (your-email@example.com)" # NWS API requires a User-Agent

def get_nws_forecast_url(location):
    if location in NWS_CACHE and (time.time() - NWS_CACHE[location]['time']) < 3600:
        return NWS_CACHE[location]['url']

    try:
        geo_headers = {'User-Agent': USER_AGENT}
        geo_res = requests.get(f"https://nominatim.openstreetmap.org/search?q={location}&format=json&limit=1", headers=geo_headers, timeout=10)
        geo_data = geo_res.json()
        if not geo_data: return None
        lat, lon = geo_data[0]['lat'], geo_data[0]['lon']

        points_headers = {'User-Agent': USER_AGENT, 'Accept': 'application/geo+json'}
        points_res = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=points_headers, timeout=10)
        points_data = points_res.json()
        forecast_url = points_data.get('properties', {}).get('forecast')
        
        if forecast_url:
            NWS_CACHE[location] = {'url': forecast_url, 'time': time.time()}
            return forecast_url
    except Exception as e:
        print(f"NWS Helper Error: {e}")
    return None

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

    def _update_text(self):
        pass

    def update(self, app):
        self._update_text()
        app.after(3600000, lambda: self.update(app))

    def draw(self, painter, app):
        win_width = app.central_widget.width()
        win_height = app.central_widget.height()
        x, y, anchor = self.get_position(win_width, win_height)
        
        scale_multiplier = self.config.get("text_scale_multiplier", 1.0)
        final_scale = self.params["scale"] * scale_multiplier

        app.draw_text(painter, self.text, (x, y), final_scale, (255, 255, 255), thickness=self.params["thick"], anchor=anchor)

    def get_draw_params(self):
        widget_type = self.widget_name.split('_')[0]
        all_params = {
            "time": {"scale": 3, "thick": 3}, "date": {"scale": 1.2, "thick": 2}, 
            "weather": {"scale": 1, "thick": 2}, "calendar": {"scale": 0.8, "thick": 1}, 
            "forecast": {"scale": 0.8, "thick": 1},
            "radar": {"scale": 1, "thick": 1}, "ical": {"scale": 0.8, "thick": 1}, "rss": {"scale": 0.8, "thick": 1}
        }
        return all_params.get(widget_type, {"scale": 1, "thick": 2})

class TimeWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        time_format = widget_settings.get("format", "24h")
        if time_format == "12h":
            self.text = time.strftime('%I:%M:%S %p')
        else:
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
        location = self.config.get("weather_location")
        if not location: self.text = "Set Weather Location"; return
        forecast_url = get_nws_forecast_url(location)
        if not forecast_url: self.text = "Invalid Location for NWS"; return
        try:
            headers = {'User-Agent': USER_AGENT, 'Accept': 'application/geo+json'}
            response = requests.get(forecast_url, headers=headers, timeout=10)
            data = response.json()
            current_forecast = data.get('properties', {}).get('periods', [])[0]
            self.text = f"{location}\n{current_forecast['temperature']}°{current_forecast['temperatureUnit']}, {current_forecast['shortForecast']}"
        except requests.exceptions.RequestException: self.text = "Weather: No Connection"
        except Exception as e: self.text = "Weather: Error"; print(f"NWS Weather update error: {e}")
    def update(self, app):
        self._update_text()
        app.after(900000, lambda: self.update(app))

class FiveDayForecastWidget(BaseWidget):
    def _update_text(self):
        location = self.config.get("weather_location")
        if not location: self.text = "Set Weather Location"; return
        forecast_url = get_nws_forecast_url(location)
        if not forecast_url: self.text = "Invalid Location for NWS"; return
        try:
            headers = {'User-Agent': USER_AGENT, 'Accept': 'application/geo+json'}
            response = requests.get(forecast_url, headers=headers, timeout=10)
            data = response.json()
            periods = data.get('properties', {}).get('periods', [])
            daily_forecasts = {}
            for p in periods:
                day_name = datetime.fromisoformat(p['startTime']).strftime('%Y-%m-%d')
                if day_name not in daily_forecasts: daily_forecasts[day_name] = {'high': -999, 'low': 999, 'desc': ''}
                daily_forecasts[day_name]['high'] = max(daily_forecasts[day_name]['high'], p['temperature'])
                daily_forecasts[day_name]['low'] = min(daily_forecasts[day_name]['low'], p['temperature'])
                if p.get('isDaytime', False) or not daily_forecasts[day_name]['desc']: daily_forecasts[day_name]['desc'] = p['shortForecast']
            forecast_lines = []
            sorted_days = sorted(daily_forecasts.keys())
            for day_str in sorted_days[:5]:
                values = daily_forecasts[day_str]
                day_name = datetime.strptime(day_str, '%Y-%m-%d').strftime('%a')
                forecast_lines.append(f"{day_name}: {values['desc']}, {values['low']}°/{values['high']}°F")
            self.text = "\n".join(forecast_lines)
        except requests.exceptions.RequestException: self.text = "Forecast: No Connection"
        except Exception as e: self.text = "Forecast: Error"; print(f"NWS Forecast update error: {e}")
    def update(self, app):
        self._update_text()
        app.after(14400000, lambda: self.update(app))

class CalendarWidget(BaseWidget):
    def _update_text(self):
        self.text = calendar.month(time.localtime().tm_year, time.localtime().tm_mon)
    def update(self, app):
        self._update_text()
        app.after(3600000, lambda: self.update(app))

class ICalWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        ical_urls = widget_settings.get("urls", [])
        if not ical_urls:
            self.text = "Set iCal URLs in widget settings"
            return

        all_events = []
        now = datetime.now(utc)

        for url in ical_urls:
            if not url or "YOUR_ICAL_URL_HERE" in url:
                continue
            try:
                response = requests.get(url, timeout=10)
                cal = Calendar.from_ical(response.content)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        dtstart_prop = component.get('dtstart')
                        if not dtstart_prop:
                            continue
                        
                        dtstart = dtstart_prop.dt
                        
                        if isinstance(dtstart, datetime):
                            if dtstart.tzinfo is None or dtstart.tzinfo.utcoffset(dtstart) is None:
                                dtstart = utc.localize(dtstart)
                            if dtstart > now:
                                all_events.append((dtstart, component.get('summary')))
                        else: # is a date object
                            event_date = dtstart
                            today = now.date()
                            if event_date > today:
                                dtstart_as_datetime = utc.localize(datetime.combine(event_date, datetime.min.time()))
                                all_events.append((dtstart_as_datetime, component.get('summary')))

            except Exception as e:
                print(f"iCal update error for url {url}: {e}")
        
        all_events.sort()
        
        self.text = "\n".join([f"{e[0].strftime('%m/%d')}: {e[1]}" for e in all_events[:5]]) or "No upcoming events."

    def update(self, app):
        self._update_text()
        app.after(3600000, lambda: self.update(app))

class RssWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        rss_urls = widget_settings.get("urls", [])
        if not rss_urls:
            self.text = "Set RSS URLs in widget settings"
            return

        all_entries = []
        for url in rss_urls:
            if not url or "YOUR_RSS_FEED_URL_HERE" in url:
                continue
            try:
                feed = feedparser.parse(url)
                all_entries.extend(feed.entries)
            except Exception as e:
                print(f"RSS update error for url {url}: {e}")

        all_entries.sort(key=lambda x: x.get("published_parsed", time.gmtime(0)), reverse=True)

        self.text = "\n".join([f"• {entry.title}" for entry in all_entries[:5]]) or "No RSS entries."

    def update(self, app):
        self._update_text()
        app.after(1800000, lambda: self.update(app))

class RadarWidget(BaseWidget):
    def __init__(self, config, widget_name="radar"):
        super().__init__(config, widget_name)
        self.radar_image = None
        self.text = ""

    def _update_text(self):
        self.text = "NWS Radar Not Yet Implemented"
        self.radar_image = None

    def update(self, app):
        self._update_text()
        app.after(900000, lambda: self.update(app))

    def draw(self, painter, app):
        if self.text:
            super().draw(painter, app)

WIDGET_CLASSES = {
    "time": TimeWidget, "date": DateWidget, "weather": WeatherWidget,
    "calendar": CalendarWidget, "forecast": FiveDayForecastWidget, "radar": RadarWidget,
    "ical": ICalWidget, "rss": RssWidget
}

class WidgetManager:
    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.widgets = {}
        self.load_widgets()

    def load_widgets(self):
        self.widgets = {}
        active_widget_names = self.config.get("widget_positions", {}).keys()
        for widget_name in active_widget_names:
            widget_type = widget_name.split('_')[0]
            if widget_type in WIDGET_CLASSES:
                self.widgets[widget_name] = WIDGET_CLASSES[widget_type](self.config, widget_name)
            else:
                print(f"Warning: Unknown widget type '{widget_type}' for widget '{widget_name}' in config.")
        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def draw_all(self, painter):
        for widget_name in list(self.config.get("widget_positions", {}).keys()):
            if widget_name in self.widgets:
                self.widgets[widget_name].draw(painter, self.app)
