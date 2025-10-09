
import time
import calendar
import requests
from datetime import datetime, date
import cv2
import numpy as np
import math
import feedparser
from icalendar import Calendar
import pytz
import threading

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
        self.update_timer = None

    def get_position(self, win_width, win_height):
        pos_data = self.config["widget_positions"].get(self.widget_name)
        if not pos_data: return 0, 0, 'nw'
        x = int(pos_data['x'] * win_width)
        y = int(pos_data['y'] * win_height)
        return x, y, pos_data['anchor']

    def _update_text(self):
        # This method should be overridden by widgets
        # For non-threaded widgets, it sets self.text directly.
        # For threaded widgets, it should return the new text.
        pass

    def set_text(self, new_text, app):
        self.text = new_text
        if app and app.central_widget:
            app.central_widget.update()

    def update(self, app):
        # Default non-threaded update
        self._update_text()
        refresh_interval_ms = self.get_refresh_interval()
        self.update_timer = app.after(refresh_interval_ms, lambda: self.update(app))

    def get_refresh_interval(self):
        # Default to 1 hour
        return self.config.get("feed_refresh_interval_ms", 3600000)

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
            "calendar": {"scale": 0.8, "thick": 1}, 
            "ical": {"scale": 0.8, "thick": 1}, "rss": {"scale": 0.8, "thick": 1},
            "weatherforecast": {"scale": 0.9, "thick": 1}, "worldclock": {"scale": 1.5, "thick": 2}
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
        self.update_timer = app.after(1000, lambda: self.update(app))

class DateWidget(BaseWidget):
    def _update_text(self):
        self.text = time.strftime('%A, %B %d, %Y')
    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app))

class WorldClockWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        timezone_str = widget_settings.get("timezone", "UTC")
        try:
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            city = timezone_str.split('/')[-1].replace('_', ' ')
            self.text = f"{city}\n{now.strftime('%I:%M:%S %p')}"
        except pytz.exceptions.UnknownTimeZoneError:
            self.text = f"Unknown Zone:\n{timezone_str}"
        except Exception as e:
            self.text = "Clock Error"
            print(f"WorldClock update error: {e}")

    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app))

class WeatherForecastWidget(BaseWidget):
    def _update_text_worker(self, app):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        location = widget_settings.get("location")
        if not location:
            app.after(0, lambda: self.set_text("Set Location in Widget Settings", app))
            return

        forecast_url = get_nws_forecast_url(location)
        if not forecast_url:
            app.after(0, lambda: self.set_text(f"Invalid NWS Location:\n{location}", app))
            return
        try:
            headers = {'User-Agent': USER_AGENT, 'Accept': 'application/geo+json'}
            response = requests.get(forecast_url, headers=headers, timeout=10)
            data = response.json()
            
            periods = data.get('properties', {}).get('periods', [])
            if not periods:
                app.after(0, lambda: self.set_text(f"No forecast data for {location}", app))
                return
            
            current_forecast = periods[0]
            current_weather_line = f"{location}\n{current_forecast['temperature']}°{current_forecast['temperatureUnit']}, {current_forecast['shortForecast']}"

            daily_forecasts = {}
            for p in periods:
                day_name = datetime.fromisoformat(p['startTime']).strftime('%Y-%m-%d')
                if day_name not in daily_forecasts:
                    daily_forecasts[day_name] = {'high': -999, 'low': 999, 'desc': ''}
                daily_forecasts[day_name]['high'] = max(daily_forecasts[day_name]['high'], p['temperature'])
                daily_forecasts[day_name]['low'] = min(daily_forecasts[day_name]['low'], p['temperature'])
                if p.get('isDaytime', False) or not daily_forecasts[day_name]['desc']:
                    daily_forecasts[day_name]['desc'] = p['shortForecast']
            
            forecast_lines = []
            sorted_days = sorted(daily_forecasts.keys())
            for day_str in sorted_days[1:6]:
                values = daily_forecasts[day_str]
                day_name_short = datetime.strptime(day_str, '%Y-%m-%d').strftime('%a')
                forecast_lines.append(f"{day_name_short}: {values['desc']}, {values['low']}°/{values['high']}°F")
            
            forecast_text = "\n".join(forecast_lines)
            final_text = f"{current_weather_line}\n\n{forecast_text}"
            app.after(0, lambda: self.set_text(final_text, app))

        except requests.exceptions.RequestException:
            app.after(0, lambda: self.set_text("Weather: No Connection", app))
        except Exception as e:
            print(f"WeatherForecast update error: {e}")
            app.after(0, lambda: self.set_text("Weather: Error", app))

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        refresh_interval_ms = self.get_refresh_interval()
        self.update_timer = app.after(refresh_interval_ms, lambda: self.update(app))

class CalendarWidget(BaseWidget):
    def _update_text(self):
        calendar.setfirstweekday(calendar.SUNDAY)
        self.text = calendar.month(time.localtime().tm_year, time.localtime().tm_mon)

class ICalWidget(BaseWidget):
    def _update_text_worker(self, app):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        ical_urls = widget_settings.get("urls", [])
        display_tz_str = widget_settings.get("timezone", "UTC")
        try:
            display_tz = pytz.timezone(display_tz_str)
        except pytz.exceptions.UnknownTimeZoneError:
            display_tz = pytz.utc

        if not ical_urls:
            app.after(0, lambda: self.set_text("Set iCal URLs in widget settings", app))
            return

        all_events = []
        now = datetime.now(pytz.utc)

        for url in ical_urls:
            if not url or "YOUR_ICAL_URL_HERE" in url:
                continue
            try:
                response = requests.get(url, timeout=10)
                cal = Calendar.from_ical(response.content)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        dtstart_prop = component.get('dtstart')
                        if not dtstart_prop: continue
                        
                        dtstart_raw = dtstart_prop.dt
                        summary = component.get('summary')

                        event_dt_final = None
                        is_datetime_event = False

                        if isinstance(dtstart_raw, datetime):
                            event_dt_for_processing = dtstart_raw
                            is_datetime_event = True
                        elif isinstance(dtstart_raw, date):
                            event_dt_for_processing = datetime.combine(dtstart_raw, datetime.min.time())
                            is_datetime_event = False
                        else:
                            continue

                        if event_dt_for_processing.tzinfo is None:
                            event_dt_final = pytz.utc.localize(event_dt_for_processing)
                        else:
                            event_dt_final = event_dt_for_processing.astimezone(pytz.utc)

                        if event_dt_final and event_dt_final >= now:
                            all_events.append((event_dt_final, summary, is_datetime_event))

            except Exception as e:
                print(f"iCal update error for url {url}: {e}")
                app.after(0, lambda: self.set_text("iCal: Error", app))
        
        all_events.sort(key=lambda x: x[0])
        
        event_lines = []
        for event_time, summary, is_datetime in all_events[:5]:
            if is_datetime:
                event_time_local = event_time.astimezone(display_tz)
                event_lines.append(f"{event_time_local.strftime('%m/%d %I:%M %p')}: {summary}")
            else:
                event_lines.append(f"{event_time.strftime('%m/%d')}: {summary}")
        final_text = "\n".join(event_lines) or "No upcoming events."
        app.after(0, lambda: self.set_text(final_text, app))

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        refresh_interval_ms = self.get_refresh_interval()
        self.update_timer = app.after(refresh_interval_ms, lambda: self.update(app))

class RssWidget(BaseWidget):
    def _update_text_worker(self, app):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        rss_urls = widget_settings.get("urls", [])
        if not rss_urls:
            app.after(0, lambda: self.set_text("Set RSS URLs in widget settings", app))
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
                app.after(0, lambda: self.set_text("RSS: Error", app))

        all_entries.sort(key=lambda x: x.get("published_parsed", time.gmtime(0)), reverse=True)
        final_text = "\n".join([f"• {entry.title}" for entry in all_entries[:5]]) or "No RSS entries."
        app.after(0, lambda: self.set_text(final_text, app))

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        refresh_interval_ms = self.get_refresh_interval()
        self.update_timer = app.after(refresh_interval_ms, lambda: self.update(app))

WIDGET_CLASSES = {
    "time": TimeWidget, "date": DateWidget, "worldclock": WorldClockWidget,
    "calendar": CalendarWidget, "weatherforecast": WeatherForecastWidget,
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
        for widget_name in list(active_widget_names):
            widget_type = widget_name.split('_')[0]
            if widget_type not in WIDGET_CLASSES:
                print(f"Warning: Removing unknown widget type '{widget_type}' for widget '{widget_name}' from config.")
                del self.app.config["widget_positions"][widget_name]
                if widget_name in self.app.config["widget_settings"]:
                    del self.app.config["widget_settings"][widget_name]
        
        if self.app.config != self.config:
            self.app.save_config()

        active_widget_names = self.config.get("widget_positions", {}).keys()
        for widget_name in active_widget_names:
            widget_type = widget_name.split('_')[0]
            if widget_type in WIDGET_CLASSES:
                self.widgets[widget_name] = WIDGET_CLASSES[widget_type](self.config, widget_name)
        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def stop_updates(self):
        for widget in self.widgets.values():
            if widget.update_timer:
                widget.update_timer.stop()

    def restart_updates(self):
        self.stop_updates()
        self.start_updates()

    def draw_all(self, painter):
        for widget_name in list(self.config.get("widget_positions", {}).keys()):
            if widget_name in self.widgets:
                self.widgets[widget_name].draw(painter, self.app)
