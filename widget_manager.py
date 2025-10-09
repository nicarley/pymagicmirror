import time
import calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, date
import cv2
import numpy as np
import math
import feedparser
from icalendar import Calendar
import pytz
import threading
import certifi

# shared network session with retries and a real UA
USER_AGENT = "MagicMirrorApp/1.0 (nic.farley@salemil.us)"
NWS_CACHE = {}

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    retries = Retry(
        total=3,
        backoff_factor=0.4,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.verify = certifi.where()
    return s

SESSION = make_session()

def get_nws_forecast_url(location):
    if location in NWS_CACHE and (time.time() - NWS_CACHE[location]["time"]) < 3600:
        return NWS_CACHE[location]["url"]
    try:
        geo_res = SESSION.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"Referer": "https://magicmirror.local"},
            timeout=10,
        )
        geo_res.raise_for_status()
        geo_data = geo_res.json()
        if not geo_data:
            return None
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]

        points_res = SESSION.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers={"Accept": "application/geo+json"},
            timeout=10,
        )
        points_res.raise_for_status()
        points_data = points_res.json()
        forecast_url = points_data.get("properties", {}).get("forecast")
        if forecast_url:
            NWS_CACHE[location] = {"url": forecast_url, "time": time.time()}
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
        self.last_error = ""
        self.last_updated = None

    def get_position(self, win_width, win_height):
        pos_data = self.config["widget_positions"].get(self.widget_name)
        if not pos_data:
            return 0, 0, "nw"
        x = int(pos_data["x"] * win_width)
        y = int(pos_data["y"] * win_height)
        return x, y, pos_data["anchor"]

    def _update_text(self):
        pass

    def _decorate_text(self, core_text):
        if self.last_error:
            return f"{core_text}\n\nError: {self.last_error}"
        return core_text

    def set_text(self, new_text, app):
        self.text = self._decorate_text(new_text)
        if app and app.central_widget:
            app.central_widget.update()

    def set_error(self, err, app, prefix):
        self.last_error = err
        self.set_text(prefix, app)

    def mark_updated(self):
        self.last_updated = datetime.now()

    def update(self, app):
        self._update_text()
        refresh_interval_ms = self.get_refresh_interval()
        self.update_timer = app.after(refresh_interval_ms, lambda: self.update(app))

    def get_refresh_interval(self):
        return self.config.get("feed_refresh_interval_ms", 3600000)

    def draw(self, painter, app):
        win_width = app.central_widget.width()
        win_height = app.central_widget.height()
        x, y, anchor = self.get_position(win_width, win_height)
        scale_multiplier = self.config.get("text_scale_multiplier", 1.0)
        final_scale = self.params["scale"] * scale_multiplier
        app.draw_text(
            painter,
            self.text,
            (x, y),
            final_scale,
            (255, 255, 255),
            thickness=self.params["thick"],
            anchor=anchor,
        )

    def get_draw_params(self):
        widget_type = self.widget_name.split("_")[0]
        all_params = {
            "time": {"scale": 3, "thick": 3},
            "date": {"scale": 1.2, "thick": 2},
            "calendar": {"scale": 0.8, "thick": 1},
            "ical": {"scale": 0.8, "thick": 1},
            "rss": {"scale": 0.8, "thick": 1},
            "weatherforecast": {"scale": 0.9, "thick": 1},
            "worldclock": {"scale": 1.5, "thick": 2},
        }
        return all_params.get(widget_type, {"scale": 1, "thick": 2})

class TimeWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        time_format = widget_settings.get("format", "24h")
        self.mark_updated()
        self.text = self._decorate_text(time.strftime("%I:%M %p" if time_format == "12h" else "%H:%M"))
    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app))

class DateWidget(BaseWidget):
    def _update_text(self):
        self.mark_updated()
        self.text = self._decorate_text(time.strftime("%A, %B %d, %Y"))
    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app))

class WorldClockWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        timezone_str = widget_settings.get("timezone", "UTC")
        display_name = widget_settings.get("display_name", timezone_str.split("/")[-1].replace("_", " "))
        try:
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
            self.mark_updated()
            self.text = self._decorate_text(f"{display_name}\n{now.strftime('%I:%M %p')}")
        except pytz.exceptions.UnknownTimeZoneError:
            self.set_error("unknown timezone", None, f"Unknown Zone:\n{timezone_str}")
        except Exception as e:
            print(f"WorldClock update error: {e}")
            self.set_error("clock error", None, "Clock Error")
    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app))

class WeatherForecastWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            location = widget_settings.get("location") or "Salem, IL"

            forecast_url = get_nws_forecast_url(location)
            if not forecast_url:
                self.set_error("nws location", app, f"Invalid NWS Location:\n{location}")
                return

            resp = SESSION.get(forecast_url, headers={"Accept": "application/geo+json"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            periods = data.get("properties", {}).get("periods", [])
            if not periods:
                self.set_error("no periods", app, f"No forecast data for {location}")
                return

            current_forecast = periods[0]
            current_line = f"{location}\n{current_forecast['temperature']}°{current_forecast['temperatureUnit']}, {current_forecast['shortForecast']}"

            central_tz = pytz.timezone("US/Central")
            daily = {}
            for p in periods:
                dt = datetime.fromisoformat(p["startTime"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                local = dt.astimezone(central_tz)
                key = local.strftime("%Y-%m-%d")
                if key not in daily:
                    daily[key] = {"high": -999, "low": 999, "desc": ""}
                t = p["temperature"]
                daily[key]["high"] = max(daily[key]["high"], t)
                daily[key]["low"] = min(daily[key]["low"], t)
                if p.get("isDaytime", False) or not daily[key]["desc"]:
                    daily[key]["desc"] = p["shortForecast"]

            lines = []
            for day_str in sorted(daily.keys())[1:6]:
                v = daily[day_str]
                day_short = datetime.strptime(day_str, "%Y-%m-%d").strftime("%a")
                lines.append(f"{day_short}: {v['desc']}, {v['low']}°/{v['high']}°F")

            self.mark_updated()
            self.set_text(f"{current_line}\n\n" + "\n".join(lines), app)

        except requests.exceptions.SSLError as e:
            print(f"Weather SSL error: {e}")
            self.set_error("ssl", app, "Weather  SSL")
        except requests.exceptions.RequestException as e:
            print(f"Weather request error: {e}")
            self.set_error("network", app, "Weather  No Connection")
        except Exception as e:
            print(f"WeatherForecast update error: {e}")
            self.set_error("error", app, "Weather  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class CalendarWidget(BaseWidget):
    def _update_text(self):
        calendar.setfirstweekday(calendar.SUNDAY)
        self.mark_updated()
        self.text = self._decorate_text(calendar.month(time.localtime().tm_year, time.localtime().tm_mon))

class ICalWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            ical_urls = widget_settings.get("urls", [])
            display_tz_str = widget_settings.get("timezone", "UTC")
            try:
                display_tz = pytz.timezone(display_tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                display_tz = pytz.utc

            if not ical_urls:
                self.set_error("no urls", app, "Set iCal URLs in widget settings")
                return

            all_events = []
            now = datetime.now(pytz.utc)
            had_errors = False

            for url in ical_urls:
                if not url or "YOUR_ICAL_URL_HERE" in url:
                    continue
                try:
                    r = SESSION.get(url, timeout=10)
                    r.raise_for_status()
                    cal = Calendar.from_ical(r.content)
                    for component in cal.walk():
                        if component.name != "VEVENT":
                            continue
                        dtstart_prop = component.get("dtstart")
                        if not dtstart_prop:
                            continue
                        dtstart_raw = dtstart_prop.dt
                        summary = component.get("summary")

                        if isinstance(dtstart_raw, datetime):
                            event_dt = dtstart_raw
                            is_dt = True
                        elif isinstance(dtstart_raw, date):
                            event_dt = datetime.combine(dtstart_raw, datetime.min.time())
                            is_dt = False
                        else:
                            continue

                        if event_dt.tzinfo is None:
                            event_dt = pytz.utc.localize(event_dt)
                        else:
                            event_dt = event_dt.astimezone(pytz.utc)

                        if event_dt >= now:
                            all_events.append((event_dt, summary, is_dt))
                except Exception as e:
                    print(f"iCal fetch parse error {url}: {e}")
                    had_errors = True

            all_events.sort(key=lambda x: x[0])

            if not all_events and had_errors:
                self.set_error("fetch", app, "iCal  Error")
                return

            lines = []
            for event_time, summary, is_dt in all_events[:5]:
                if is_dt:
                    local = event_time.astimezone(display_tz)
                    lines.append(f"{local.strftime('%m/%d %I:%M %p')}: {summary}")
                else:
                    local = event_time.astimezone(display_tz)
                    lines.append(f"{local.strftime('%m/%d')}: {summary}")

            self.mark_updated()
            self.set_text("\n".join(lines) or "No upcoming events.", app)

        except Exception as e:
            print(f"iCal update error: {e}")
            self.set_error("error", app, "iCal  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class RssWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            rss_urls = widget_settings.get("urls", [])
            if not rss_urls:
                self.set_error("no urls", app, "Set RSS URLs in widget settings")
                return

            entries = []
            had_errors = False
            for url in rss_urls:
                if not url or "YOUR_RSS_FEED_URL_HERE" in url:
                    continue
                try:
                    r = SESSION.get(url, timeout=10)
                    r.raise_for_status()
                    fp = feedparser.parse(r.content)
                    if getattr(fp, "bozo", False):
                        print(f"RSS parse warning {url}: {getattr(fp, 'bozo_exception', '')}")
                    entries.extend(fp.entries)
                except Exception as e:
                    print(f"RSS error for {url}: {e}")
                    had_errors = True

            if not entries and had_errors:
                self.set_error("fetch", app, "RSS  Error")
                return

            def _pub(e):
                return getattr(e, "published_parsed", None) or time.gmtime(0)
            entries.sort(key=_pub, reverse=True)

            titles = [f"• {getattr(e, 'title', '(untitled)')}" for e in entries[:5]]
            self.mark_updated()
            self.set_text("\n".join(titles) or "No RSS entries.", app)

        except Exception as e:
            print(f"RSS update error: {e}")
            self.set_error("error", app, "RSS  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

WIDGET_CLASSES = {
    "time": TimeWidget,
    "date": DateWidget,
    "worldclock": WorldClockWidget,
    "calendar": CalendarWidget,
    "weatherforecast": WeatherForecastWidget,
    "ical": ICalWidget,
    "rss": RssWidget,
}

class WidgetManager:
    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.widgets = {}
        self.load_widgets()

    def load_widgets(self):
        self.widgets = {}
        active = list(self.config.get("widget_positions", {}).keys())

        for widget_name in list(active):
            widget_type = widget_name.split("_")[0]
            if widget_type not in WIDGET_CLASSES:
                print(f"Removing unknown widget {widget_name}")
                self.app.config["widget_positions"].pop(widget_name, None)
                self.app.config["widget_settings"].pop(widget_name, None)

        self.app.save_config()

        for widget_name in self.config.get("widget_positions", {}).keys():
            widget_type = widget_name.split("_")[0]
            self.widgets[widget_name] = WIDGET_CLASSES[widget_type](self.config, widget_name)

        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def stop_updates(self):
        for widget in self.widgets.values():
            try:
                if widget.update_timer and hasattr(widget.update_timer, "stop"):
                    widget.update_timer.stop()
            except Exception as e:
                print("stop_updates error:", e)

    def restart_updates(self):
        self.stop_updates()
        self.start_updates()

    def draw_all(self, painter):
        for widget_name in list(self.config.get("widget_positions", {}).keys()):
            w = self.widgets.get(widget_name)
            if w:
                w.draw(painter, self.app)
