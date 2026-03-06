import time
import calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, date, timedelta
import feedparser
from icalendar import Calendar
import pytz
import threading
import certifi
import os
import random
import socket
import textwrap
import math

# Try to import psutil for system stats
try:
    import psutil
except ImportError:
    psutil = None

# shared network session with retries and a real UA
USER_AGENT = "MagicMirrorApp/2025.1013"
NWS_CACHE = {}

# Using the free, public ESPN APIs
SPORTS_API_URLS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "ncaaf": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "ncaamb": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
}

HISTORY_API_URL = "https://history.muffinlabs.com/date"
SUN_API_URL = "https://api.sunrise-sunset.org/json"
RAINVIEWER_API_URL = "https://api.rainviewer.com/public/weather-maps.json"
AFTERSHIP_API_BASE = "https://api.aftership.com/tracking/2024-07/trackings"

FMP_API_KEY = os.environ.get("FMP_API_KEY") 
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3/quote/"

WEATHER_EMOJI_MAP = {
    "Sunny": "☀️",
    "Clear": "☀️",
    "Mostly Sunny": "🌤️",
    "Partly Cloudy": "⛅",
    "Mostly Cloudy": "🌥️",
    "Cloudy": "☁️",
    "Overcast": "☁️",
    "Rain": "🌧️",
    "Light Rain": "🌦️",
    "Showers": "🌧️",
    "Thunderstorm": "⛈️",
    "Snow": "❄️",
    "Fog": "🌫️",
    "Mist": "🌫️",
    "Haze": "🌫️",
    "Windy": "💨",
}

DEFAULT_QUOTES = [
    "Believe you can and you're halfway there.",
    "You look great today!",
    "Make it a great day.",
    "The best way to predict the future is to create it.",
    "Do something today that your future self will thank you for.",
    "Smile, it confuses people.",
    "You are enough.",
    "Carpe Diem.",
]

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"}

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

def collect_ical_urls(config, widget_name):
    widget_settings = config.get("widget_settings", {}).get(widget_name, {})
    urls = widget_settings.get("urls", [])
    if urls:
        return urls

    # Fallback: reuse URLs from any configured iCal widgets.
    fallback_urls = []
    for key, settings in config.get("widget_settings", {}).items():
        if key.split("_")[0] == "ical":
            fallback_urls.extend(settings.get("urls", []))
    return fallback_urls

def fetch_ical_events(urls):
    all_events = []
    had_errors = False
    now = datetime.now(pytz.utc)

    for url in urls:
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
                summary = str(component.get("summary", "(No title)"))
                location = str(component.get("location", "")).strip()

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
                    all_events.append((event_dt, summary, is_dt, location))
        except Exception as e:
            print(f"iCal fetch parse error {url}: {e}")
            had_errors = True

    all_events.sort(key=lambda x: x[0])
    return all_events, had_errors

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
        self.ticker_scroll_x = 0

    def get_position(self, win_width, win_height):
        pos_data = self.config["widget_positions"].get(self.widget_name)
        if not pos_data:
            return 0, 0, "nw"
        x = int(pos_data["x"] * win_width)
        y = int(pos_data["y"] * win_height)
        return x, y, pos_data.get("anchor", "nw")

    def _update_text(self):
        pass

    def _decorate_text(self, core_text):
        if self.last_error:
            return f"{core_text}\n\nError: {self.last_error}"
        return core_text

    def set_text(self, new_text, app):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        is_ticker = widget_settings.get("style") == "Ticker"
        
        decorated_text = self._decorate_text(new_text)

        if is_ticker:
            self.text = "   |   ".join(decorated_text.split("\n")).strip()
        else:
            self.text = decorated_text

        if app and hasattr(app, 'central_widget') and app.central_widget:
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
        if not hasattr(app, 'central_widget') or not app.central_widget:
            return
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
            thickness=self.params["thick"],
            anchor=anchor,
            widget_name=self.widget_name
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
            "sports": {"scale": 0.9, "thick": 1},
            "stock": {"scale": 0.9, "thick": 1},
            "history": {"scale": 0.8, "thick": 1},
            "countdown": {"scale": 1.5, "thick": 2},
            "quotes": {"scale": 1.0, "thick": 1},
            "system": {"scale": 0.8, "thick": 1},
            "ip": {"scale": 0.8, "thick": 1},
            "moon": {"scale": 0.9, "thick": 1},
            "commute": {"scale": 0.9, "thick": 1},
            "dailyagenda": {"scale": 0.9, "thick": 1},
            "photomemories": {"scale": 0.9, "thick": 1},
            "flightboard": {"scale": 0.9, "thick": 1},
            "energyprice": {"scale": 1.0, "thick": 1},
            "package": {"scale": 0.9, "thick": 1},
            "sunrise": {"scale": 1.0, "thick": 1},
            "sunrisesunset": {"scale": 1.0, "thick": 1},
            "astronomy": {"scale": 0.9, "thick": 1},
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
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        date_format = widget_settings.get("format", "%A, %B %d, %Y")
        self.mark_updated()
        self.text = self._decorate_text(time.strftime(date_format))
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
    @staticmethod
    def _get_emoji(desc):
        for key, emoji in WEATHER_EMOJI_MAP.items():
            if key.lower() in desc.lower():
                return emoji
        return ""

    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            location = widget_settings.get("location") or "Salem, IL"
            style = widget_settings.get("style", "Normal")

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

            if style == "Ticker":
                ticker_items = []
                for p in periods[:5]:
                    emoji = self._get_emoji(p['shortForecast'])
                    ticker_items.append(f"{p['name']}: {emoji} {p['shortForecast']}, {p['temperature']}°{p['temperatureUnit']}")
                self.mark_updated()
                self.set_text("\n".join(ticker_items), app)
                return

            current_forecast = periods[0]
            curr_emoji = self._get_emoji(current_forecast['shortForecast'])
            current_line = f"{location}\n{curr_emoji} {current_forecast['temperature']}°{current_forecast['temperatureUnit']}, {current_forecast['shortForecast']}"

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
            for day_str in sorted(daily.keys())[:5]:
                v = daily[day_str]
                day_short = datetime.strptime(day_str, "%Y-%m-%d").strftime("%a")
                emoji = self._get_emoji(v['desc'])
                lines.append(f"{day_short}: {emoji} {v['low']}°/{v['high']}°F")

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
        now = datetime.now()
        cal = calendar.TextCalendar(calendar.SUNDAY)
        cal_str = cal.formatmonth(now.year, now.month)
        
        # The user wants to remove the day of the week from the header.
        # formatmonth returns "Month Year" as the first line, which is what we want.
        # So we just use cal_str directly.
        self.text = self._decorate_text(cal_str)
        self.mark_updated()

    def update(self, app):
        self._update_text()
        self.update_timer = app.after(3600000, lambda: self.update(app)) # Update every hour

class ICalWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            ical_urls = collect_ical_urls(self.config, self.widget_name)
            display_tz_str = widget_settings.get("timezone", "UTC")
            try:
                display_tz = pytz.timezone(display_tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                display_tz = pytz.utc

            if not ical_urls:
                self.set_error("no urls", app, "Set iCal URLs in widget settings")
                return

            all_events, had_errors = fetch_ical_events(ical_urls)

            if not all_events and had_errors:
                self.set_error("fetch", app, "iCal  Error")
                return

            lines = []
            for event_time, summary, is_dt, _location in all_events[:5]:
                if is_dt:
                    local = event_time.astimezone(display_tz)
                    lines.append(f"{local.strftime('%a %m/%d %I:%M %p')}: {summary}")
                else:
                    local = event_time.astimezone(display_tz)
                    lines.append(f"{local.strftime('%a %m/%d')}: {summary}")

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

class CommuteWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            ical_urls = collect_ical_urls(self.config, self.widget_name)
            display_tz_str = widget_settings.get("timezone", "UTC")
            commute_minutes = int(widget_settings.get("commute_minutes", 25))
            prep_minutes = int(widget_settings.get("prep_minutes", 10))
            lookahead_hours = int(widget_settings.get("lookahead_hours", 24))

            try:
                display_tz = pytz.timezone(display_tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                display_tz = pytz.utc
                self.set_error("unknown timezone", app, f"Unknown Zone:\n{display_tz_str}")
                return

            if not ical_urls:
                self.set_error("no urls", app, "Set iCal URLs in widget settings")
                return

            all_events, had_errors = fetch_ical_events(ical_urls)
            now_utc = datetime.now(pytz.utc)
            cutoff = now_utc + timedelta(hours=lookahead_hours)

            commute_event = None
            for event_time, summary, is_dt, location in all_events:
                if not is_dt:
                    continue
                if not location:
                    continue
                if event_time > cutoff:
                    continue
                commute_event = (event_time, summary, location)
                break

            if not commute_event and had_errors:
                self.set_error("fetch", app, "Commute  Error")
                return
            if not commute_event:
                self.set_text("Commute\nNo upcoming events with a location.", app)
                return

            event_utc, summary, location = commute_event
            now_local = now_utc.astimezone(display_tz)
            start_local = event_utc.astimezone(display_tz)
            leave_local = start_local - timedelta(minutes=(commute_minutes + prep_minutes))

            delta_minutes = int((leave_local - now_local).total_seconds() / 60)
            if delta_minutes > 0:
                leave_status = f"Leave in {delta_minutes} min"
            elif delta_minutes >= -5:
                leave_status = "Leave now"
            else:
                leave_status = f"Running late by {abs(delta_minutes)} min"

            text = (
                "Commute\n"
                f"{leave_status}\n"
                f"{summary}\n"
                f"{start_local.strftime('%a %I:%M %p')} @ {location}\n"
                f"ETA {commute_minutes}m + prep {prep_minutes}m"
            )
            self.mark_updated()
            self.set_text(text, app)
        except Exception as e:
            print(f"Commute widget update error: {e}")
            self.set_error("error", app, "Commute  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        # Keep this fresher than normal feeds so leave-time countdown feels live.
        self.update_timer = app.after(60000, lambda: self.update(app))

class DailyAgendaWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            ical_urls = collect_ical_urls(self.config, self.widget_name)
            display_tz_str = widget_settings.get("timezone", "UTC")
            max_events = int(widget_settings.get("max_events", 6))
            days_ahead = int(widget_settings.get("days_ahead", 3))

            try:
                display_tz = pytz.timezone(display_tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                display_tz = pytz.utc
                self.set_error("unknown timezone", app, f"Unknown Zone:\n{display_tz_str}")
                return

            if not ical_urls:
                self.set_error("no urls", app, "Set iCal URLs in widget settings")
                return

            all_events, had_errors = fetch_ical_events(ical_urls)
            now = datetime.now(pytz.utc)
            cutoff = now + timedelta(days=days_ahead)
            items = []

            for event_time, summary, is_dt, location in all_events:
                if event_time > cutoff:
                    continue
                local = event_time.astimezone(display_tz)
                if is_dt:
                    line = f"{local.strftime('%a %m/%d %I:%M %p')}  {summary}"
                else:
                    line = f"{local.strftime('%a %m/%d')}  {summary}"
                if location:
                    line += f" @ {location}"
                items.append(line)
                if len(items) >= max_events:
                    break

            if not items and had_errors:
                self.set_error("fetch", app, "Agenda  Error")
                return

            header = "Daily Agenda"
            body = "\n".join(items) if items else "No events scheduled."
            self.mark_updated()
            self.set_text(f"{header}\n{body}", app)
        except Exception as e:
            print(f"Daily agenda update error: {e}")
            self.set_error("error", app, "Agenda  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class PhotoMemoriesWidget(BaseWidget):
    def __init__(self, config, widget_name):
        super().__init__(config, widget_name)
        self.current_photo_path = ""
        self.current_caption = ""

    @staticmethod
    def _parse_date_from_filename(filename):
        # Supports names containing YYYY-MM-DD, YYYY_MM_DD, or YYYYMMDD.
        stem = os.path.splitext(os.path.basename(filename))[0]
        normalized = stem.replace("_", "-").replace(".", "-")
        tokens = normalized.split("-")

        for i in range(len(tokens) - 2):
            y, m, d = tokens[i:i+3]
            if len(y) == 4 and len(m) in (1, 2) and len(d) in (1, 2):
                if y.isdigit() and m.isdigit() and d.isdigit():
                    try:
                        return date(int(y), int(m), int(d))
                    except ValueError:
                        pass

        digits = "".join(ch for ch in stem if ch.isdigit())
        if len(digits) >= 8:
            for i in range(len(digits) - 7):
                chunk = digits[i:i+8]
                y = int(chunk[0:4]); m = int(chunk[4:6]); d = int(chunk[6:8])
                try:
                    return date(y, m, d)
                except ValueError:
                    continue
        return None

    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        source_mode = widget_settings.get("source_mode", "folder")
        single_file = widget_settings.get("single_file", "")
        folder = widget_settings.get("folder", "")
        max_name_chars = int(widget_settings.get("max_name_chars", 45))
        self.current_photo_path = ""
        self.current_caption = ""

        if source_mode == "single":
            if not single_file:
                self.text = "Photo Memories\nSet single photo in widget settings"
                return
            if not os.path.isfile(single_file):
                self.text = "Photo Memories\nSelected photo not found"
                return
            filename = os.path.basename(single_file)
            if len(filename) > max_name_chars:
                filename = filename[:max_name_chars - 3] + "..."
            self.mark_updated()
            self.current_photo_path = single_file
            self.current_caption = f"Photo - {filename}"
            self.text = f"Photo\n{filename}"
            return

        if not folder:
            self.text = "Photo Memories\nSet folder in widget settings"
            return
        if not os.path.isdir(folder):
            self.text = "Photo Memories\nFolder not found"
            return

        files = []
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in PHOTO_EXTENSIONS:
                files.append(path)

        if not files:
            self.text = "Photo Memories\nNo photos found"
            return

        today = date.today()
        today_matches = []
        fallback = []
        for path in files:
            parsed = self._parse_date_from_filename(path)
            if parsed:
                if parsed.month == today.month and parsed.day == today.day:
                    today_matches.append((path, parsed))
                else:
                    fallback.append((path, parsed))
            else:
                fallback.append((path, None))

        chosen_path, parsed_date = random.choice(today_matches if today_matches else fallback)
        filename = os.path.basename(chosen_path)
        if len(filename) > max_name_chars:
            filename = filename[:max_name_chars - 3] + "..."

        if parsed_date:
            years = max(0, today.year - parsed_date.year)
            age_line = f"{years} year(s) ago" if years else "From this year"
        else:
            age_line = "Favorite memory"

        prefix = "On This Day" if today_matches else "Memory"
        self.mark_updated()
        self.current_photo_path = chosen_path
        self.current_caption = f"{prefix} - {filename} - {age_line}"
        self.text = f"{prefix}\n{filename}\n{age_line}"

    def draw(self, painter, app):
        if self.current_photo_path:
            win_width = app.central_widget.width()
            win_height = app.central_widget.height()
            x, y, anchor = self.get_position(win_width, win_height)
            app.draw_photo_widget(
                painter,
                self.widget_name,
                self.current_photo_path,
                (x, y),
                anchor
            )
            return
        super().draw(painter, app)

    def update(self, app):
        self._update_text()
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        source_mode = widget_settings.get("source_mode", "folder")
        if source_mode == "single":
            refresh_ms = 3600000
        else:
            try:
                refresh_minutes = int(widget_settings.get("refresh_minutes", 60))
            except (TypeError, ValueError):
                refresh_minutes = 60
            refresh_minutes = max(1, min(1440, refresh_minutes))
            refresh_ms = refresh_minutes * 60000
        self.update_timer = app.after(refresh_ms, lambda: self.update(app))

class RssWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            rss_urls = widget_settings.get("urls", [])
            title = widget_settings.get("title", "")
            style = widget_settings.get("style", "Normal")
            article_count = int(widget_settings.get("article_count", 5))
            max_width_chars = int(widget_settings.get("max_width_chars", 50))

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

            def _pub(entry):
                return getattr(entry, "published_parsed", None) or time.gmtime(0)
            entries.sort(key=_pub, reverse=True)

            titles = []
            for e in entries[:article_count]:
                raw_title = getattr(e, 'title', '(untitled)')
                wrapped_title = textwrap.fill(raw_title, width=max_width_chars)
                # Indent subsequent lines for better readability if wrapped
                indented_title = wrapped_title.replace("\n", "\n  ")
                titles.append(f"• {indented_title}")
            
            if style == "Ticker":
                ticker_text = "   |   ".join([getattr(e, 'title', '(untitled)') for e in entries[:article_count]])
                if title:
                    ticker_text = f"{title}: {ticker_text}"
                self.mark_updated()
                self.set_text(ticker_text, app)
                return

            full_text = "\n".join(titles) or "No RSS entries."
            if title:
                full_text = f"{title}\n{full_text}"

            self.mark_updated()
            self.set_text(full_text, app)

        except Exception as e:
            print(f"RSS update error: {e}")
            self.set_error("error", app, "RSS  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class SportsWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            league_configs = widget_settings.get("configs", [])
            display_tz_str = widget_settings.get("timezone", "UTC")
            style = widget_settings.get("style", "Normal")
            
            try:
                display_tz = pytz.timezone(display_tz_str)
            except pytz.exceptions.UnknownTimeZoneError:
                display_tz = pytz.utc
                self.set_error("unknown timezone", app, f"Unknown Zone:\n{display_tz_str}")
                return

            if not league_configs:
                self.set_text("No leagues configured for this widget.", app)
                return

            all_scores_text = []
            ticker_items = []
            had_errors = False

            for config in league_configs:
                league = config.get("league", "").lower()
                teams = [team.lower() for team in config.get("teams", [])]
                
                url = SPORTS_API_URLS.get(league)
                if not url:
                    all_scores_text.append(f"Unknown league: {league.upper()}")
                    had_errors = True
                    continue

                try:
                    response = SESSION.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    header = league.upper()
                    
                    if style == "Ticker":
                        events = data.get("events", [])
                        if teams and teams != ['']:
                            filtered_events = []
                            for event in events:
                                for competition in event.get("competitions", []):
                                    for competitor in competition.get("competitors", []):
                                        if competitor.get("team", {}).get("abbreviation", "").lower() in teams:
                                            filtered_events.append(event)
                                            break
                                    else:
                                        continue
                                    break
                            events = filtered_events
                        
                        for event in events:
                            game_info = self.parse_event(event, display_tz)
                            if game_info:
                                ticker_items.append(f"{header}: {game_info}")
                    else:
                        formatted_scores = self.format_scores(data, league, teams, display_tz)
                        if formatted_scores and "No " not in formatted_scores:
                            all_scores_text.append(f"--- {header} ---")
                            all_scores_text.append(formatted_scores)

                except requests.exceptions.RequestException:
                    had_errors = True
                    print(f"Sports widget network error for {league}")
                except Exception as e:
                    had_errors = True
                    print(f"Sports widget update error for {league}: {e}")

            if style == "Ticker":
                if not ticker_items and had_errors:
                     self.set_error("network", app, "Sports Error")
                else:
                    self.mark_updated()
                    self.set_text("\n".join(ticker_items) or "No games.", app)
                return

            if not all_scores_text and had_errors:
                self.set_error("network", app, "Sports Error")
            
            self.mark_updated()
            self.set_text("\n".join(all_scores_text) or "No games for selected leagues/teams.", app)

        except Exception as e:
            print(f"Sports widget update error: {e}")
            self.set_error("error", app, "Sports Error")

    def format_scores(self, data, league, teams, display_tz):
        output = []
        events = data.get("events", [])
        
        if teams and teams != ['']:
            filtered_events = []
            for event in events:
                for competition in event.get("competitions", []):
                    for competitor in competition.get("competitors", []):
                        if competitor.get("team", {}).get("abbreviation", "").lower() in teams:
                            filtered_events.append(event)
                            break
                    else:
                        continue
                    break
            events = filtered_events

        if not events:
            return f"No {league.upper()} games today."

        for event in events:
            game_info = self.parse_event(event, display_tz)
            if game_info:
                output.append(game_info)
        
        return "\n".join(output) if output else f"No {league.upper()} games for selected teams."

    @staticmethod
    def parse_event(event, display_tz):
        competitions = event.get("competitions", [])
        if not competitions:
            return None
            
        competition = competitions[0]
        status = competition.get("status", {}).get("type", {}).get("name", "STATUS_UNKNOWN")
        
        competitors = competition.get("competitors", [])
        if len(competitors) != 2:
            return None

        team1 = competitors[0].get("team", {})
        team2 = competitors[1].get("team", {})
        
        score1 = competitors[0].get("score", "0")
        score2 = competitors[1].get("score", "0")

        team1_name = team1.get("abbreviation", "TBD")
        team2_name = team2.get("abbreviation", "TBD")

        if status == "STATUS_FINAL":
            return f"{team1_name} {score1} - {team2_name} {score2} (Final)"
        elif status == "STATUS_IN_PROGRESS":
            detail = competition.get("status", {}).get("type", {}).get("detail", "In Progress")
            return f"{team1_name} {score1} - {team2_name} {score2} ({detail})"
        elif status == "STATUS_SCHEDULED":
            game_time_utc = datetime.fromisoformat(competition.get("date").replace("Z", "+00:00"))
            game_time_local = game_time_utc.astimezone(display_tz).strftime("%I:%M %p %Z")
            return f"{team1_name} vs {team2_name} at {game_time_local}"
        
        return None

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class StockWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            symbols = widget_settings.get("symbols", ["AAPL", "GOOG"])
            # Check widget settings for API key first, then global config
            api_key = widget_settings.get("api_key") or self.config.get("FMP_API_KEY", FMP_API_KEY)
            style = widget_settings.get("style", "Normal")

            if not api_key or api_key == "YOUR_FMP_API_KEY":
                self.set_error("api_key", app, "Stock Widget: API Key Needed")
                return

            stock_data = []
            for symbol in symbols:
                if not symbol.strip():
                    continue
                url = f"{FMP_BASE_URL}{symbol.strip().upper()}?apikey={api_key}"
                response = SESSION.get(url)
                response.raise_for_status()
                data = response.json()
                if data:
                    price = data[0].get("price", 0)
                    change = data[0].get("changesPercentage", 0)
                    change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
                    stock_data.append(f"{symbol.upper()}: ${price:.2f} ({change_str})")
            
            if stock_data:
                self.mark_updated()
                if style == "Ticker":
                    self.set_text("\n".join(stock_data), app) # Ticker logic handles joining with separators
                else:
                    self.set_text("\n".join(stock_data), app)
            else:
                self.set_error("no_data", app, "No stock data found.")

        except requests.exceptions.RequestException as e:
            print(f"Stock widget error: {e}")
            self.set_error("network", app, "Stocks  No Connection")
        except Exception as e:
            print(f"Stock widget update error: {e}")
            self.set_error("error", app, "Stocks  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class HistoryWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            max_width_chars = int(widget_settings.get("max_width_chars", 50))

            response = SESSION.get(HISTORY_API_URL)
            response.raise_for_status()
            data = response.json()

            events = data.get("data", {}).get("Events", [])
            if events:
                # Sort events by year (oldest to newest)
                def get_year(event):
                    try:
                        return int(event.get('year', 0))
                    except ValueError:
                        return 0
                
                events.sort(key=get_year, reverse=True)
                
                # Take the first 10 items
                event_texts = []
                for e in events[:10]:
                    raw_text = f"{e['year']}: {e['text']}"
                    wrapped_text = textwrap.fill(raw_text, width=max_width_chars)
                    # Indent subsequent lines
                    indented_text = wrapped_text.replace("\n", "\n    ")
                    event_texts.append(indented_text)

                self.mark_updated()
                self.set_text("On This Day:\n" + "\n".join(event_texts), app)
            else:
                self.set_error("no_events", app, "No historical events found.")

        except requests.exceptions.RequestException as e:
            print(f"History widget error: {e}")
            self.set_error("network", app, "History  No Connection")
        except Exception as e:
            print(f"History widget update error: {e}")
            self.set_error("error", app, "History  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class CountdownWidget(BaseWidget):
    def _update_text(self):
        widget_settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
        name = widget_settings.get("name", "Countdown")
        target_str = widget_settings.get("datetime", "")

        if not target_str:
            self.text = f"{name}\nSet date and time"
            return

        try:
            target_dt = datetime.strptime(target_str, "%Y-%m-%d %H:%M")
            now = datetime.now()
            
            if now > target_dt:
                self.text = f"{name}\nTime's up!"
                return

            delta = target_dt - now
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            self.text = f"{name}\n{days}d {hours}h {minutes}m"

        except ValueError:
            self.text = f"{name}\nInvalid date format"
        except Exception as e:
            self.text = f"{name}\nError: {e}"

    def update(self, app):
        self._update_text()
        self.update_timer = app.after(1000, lambda: self.update(app)) # Update every second

class QuotesWidget(BaseWidget):
    def _update_text(self):
        self.mark_updated()
        self.text = random.choice(DEFAULT_QUOTES)

    def update(self, app):
        self._update_text()
        # Update every 4 hours
        self.update_timer = app.after(14400000, lambda: self.update(app))

class SystemStatsWidget(BaseWidget):
    def _update_text(self):
        if not psutil:
            self.text = "System Stats\n(psutil not installed)"
            return

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        self.text = f"CPU: {cpu}%\nRAM: {mem}%"

    def update(self, app):
        self._update_text()
        self.update_timer = app.after(2000, lambda: self.update(app))

class IPWidget(BaseWidget):
    def _update_text(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connect to a public DNS server to determine the local IP used for internet access
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self.text = f"Management IP: {ip}:815"
        except Exception:
            self.text = "IP: Unavailable"

    def update(self, app):
        self._update_text()
        # Update every minute
        self.update_timer = app.after(60000, lambda: self.update(app))

class MoonWidget(BaseWidget):
    def _update_text(self):
        try:
            # Simple moon phase calculation
            # Based on Conway's method
            now_date = datetime.now()
            year = now_date.year
            month = now_date.month
            day = now_date.day

            if month < 3:
                year -= 1
                month += 12

            month += 1
            c = 365.25 * year
            e = 30.6 * month
            jd = c + e + day - 694039.09
            jd /= 29.5305882
            b = int(jd)
            jd -= b
            b = round(jd * 8)
            
            if b >= 8:
                b = 0

            phases = {
                0: "New Moon 🌑",
                1: "Waxing Crescent 🌒",
                2: "First Quarter 🌓",
                3: "Waxing Gibbous 🌔",
                4: "Full Moon 🌕",
                5: "Waning Gibbous 🌖",
                6: "Last Quarter 🌗",
                7: "Waning Crescent 🌘"
            }
            
            self.text = phases[b]
            self.mark_updated()
        except Exception as e:
            print(f"Moon widget error: {e}")
            self.text = "Moon: Error"

    def update(self, app):
        self._update_text()
        # Update every 4 hours
        self.update_timer = app.after(14400000, lambda: self.update(app))

class FlightBoardWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            api_key = settings.get("api_key", "").strip()
            flight_number = settings.get("flight_number", "").strip()
            if not api_key:
                self.set_error("api_key", app, "Flight Board\nSet aviationstack API key")
                return
            if not flight_number:
                self.set_error("flight", app, "Flight Board\nSet a flight number")
                return

            url = "http://api.aviationstack.com/v1/flights"
            resp = SESSION.get(
                url,
                params={"access_key": api_key, "flight_iata": flight_number, "limit": 1},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                self.set_text(f"Flight Board\n{flight_number}: No data", app)
                return

            f = data[0]
            dep_iata = f.get("departure", {}).get("iata", "???")
            arr_iata = f.get("arrival", {}).get("iata", "???")
            dep_t = f.get("departure", {}).get("scheduled", "")
            arr_t = f.get("arrival", {}).get("scheduled", "")
            status = f.get("flight_status", "unknown")

            def fmt(ts):
                if not ts:
                    return "N/A"
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    return dt.strftime("%m/%d %I:%M %p")
                except Exception:
                    return ts

            self.mark_updated()
            self.set_text(
                f"Flight {flight_number}\n{dep_iata} -> {arr_iata}\nDep {fmt(dep_t)}\nArr {fmt(arr_t)}\nStatus: {status}",
                app,
            )
        except Exception as e:
            print(f"Flight board error: {e}")
            self.set_error("error", app, "Flight Board  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class EnergyPriceWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            mode = settings.get("mode", "manual")
            unit = settings.get("unit", "kWh")
            symbol = settings.get("currency_symbol", "$")

            if mode == "manual":
                try:
                    price = float(settings.get("manual_price", 0.0))
                except (TypeError, ValueError):
                    price = 0.0
                self.mark_updated()
                self.set_text(f"Energy Price\n{symbol}{price:.3f}/{unit}\nMode: Manual", app)
                return

            url = settings.get("price_url", "").strip()
            json_key = settings.get("json_key", "").strip()
            if not url or not json_key:
                self.set_error("config", app, "Energy Price\nSet URL + JSON key")
                return

            resp = SESSION.get(url, timeout=10)
            resp.raise_for_status()
            payload = resp.json()
            value = payload
            for part in json_key.split("."):
                if isinstance(value, list):
                    value = value[int(part)]
                else:
                    value = value.get(part)
            price = float(value)
            self.mark_updated()
            self.set_text(f"Energy Price\n{symbol}{price:.3f}/{unit}\nMode: URL", app)
        except Exception as e:
            print(f"Energy price error: {e}")
            self.set_error("error", app, "Energy Price  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class PackageWidget(BaseWidget):
    def _update_text_worker(self, app):
        try:
            settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            api_key = settings.get("api_key", "").strip()
            slug = settings.get("company", "").strip().lower()
            tracking_number = settings.get("tracking_number", "").strip()

            if not api_key:
                self.set_error("api_key", app, "Package\nSet AfterShip API key")
                return
            if not slug or not tracking_number:
                self.set_error("tracking", app, "Package\nSet company + tracking number")
                return

            url = f"{AFTERSHIP_API_BASE}/{slug}/{tracking_number}"
            resp = SESSION.get(url, headers={"aftership-api-key": api_key}, timeout=10)
            resp.raise_for_status()
            tracking = resp.json().get("data", {}).get("tracking", {})
            tag = tracking.get("tag", "Unknown")
            checkpoints = tracking.get("checkpoints", [])
            last_msg = checkpoints[0].get("message", "") if checkpoints else "No status updates"
            self.mark_updated()
            self.set_text(f"Package ({slug.upper()})\n{tracking_number}\nStatus: {tag}\n{last_msg}", app)
        except Exception as e:
            print(f"Package widget error: {e}")
            self.set_error("error", app, "Package  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(self.get_refresh_interval(), lambda: self.update(app))

class SunriseWidget(BaseWidget):
    @staticmethod
    def _format_day_length(day_length_raw):
        # API may return "HH:MM:SS" or raw seconds depending on provider/version.
        if day_length_raw is None:
            return "N/A"
        day_length_str = str(day_length_raw).strip()
        if ":" in day_length_str:
            return day_length_str
        try:
            total_seconds = int(float(day_length_str))
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except (TypeError, ValueError):
            return day_length_str

    def _update_text_worker(self, app):
        try:
            settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            lat = float(settings.get("lat", 38.624))
            lon = float(settings.get("lon", -90.184))
            resp = SESSION.get(SUN_API_URL, params={"lat": lat, "lng": lon, "formatted": 0}, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", {})
            sunrise = datetime.fromisoformat(results.get("sunrise").replace("Z", "+00:00")).astimezone()
            sunset = datetime.fromisoformat(results.get("sunset").replace("Z", "+00:00")).astimezone()
            day_len = self._format_day_length(results.get("day_length", ""))
            self.mark_updated()
            self.set_text(
                f"Sunrise / Sunset\nSunrise: {sunrise.strftime('%I:%M %p')}\nSunset: {sunset.strftime('%I:%M %p')}\nDay: {day_len}",
                app,
            )
        except Exception as e:
            print(f"Sunrise widget error: {e}")
            self.set_error("error", app, "Sunrise  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(900000, lambda: self.update(app))

class AstronomyWidget(BaseWidget):
    @staticmethod
    def _moon_illumination_fraction(now_dt):
        # Approximate moon illumination using synodic month.
        known_new_moon = datetime(2000, 1, 6, 18, 14)
        synodic = 29.53058867
        days = (now_dt - known_new_moon).total_seconds() / 86400.0
        phase = (days % synodic) / synodic
        return 0.5 * (1 - math.cos(2 * math.pi * phase))

    def _update_text_worker(self, app):
        try:
            settings = self.config.get("widget_settings", {}).get(self.widget_name, {})
            lat = float(settings.get("lat", 38.624))
            lon = float(settings.get("lon", -90.184))
            now = datetime.now()
            illum = self._moon_illumination_fraction(now) * 100.0

            resp = SESSION.get(SUN_API_URL, params={"lat": lat, "lng": lon, "formatted": 0}, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", {})
            civil_twilight_end = datetime.fromisoformat(
                results.get("civil_twilight_end").replace("Z", "+00:00")
            ).astimezone()
            astronomical_twilight_end = datetime.fromisoformat(
                results.get("astronomical_twilight_end").replace("Z", "+00:00")
            ).astimezone()

            # ISS pass times from Open Notify (best-effort; service can be intermittently unavailable).
            iss_line = "ISS Next Pass: unavailable"
            try:
                iss_resp = SESSION.get(
                    "http://api.open-notify.org/iss-pass.json",
                    params={"lat": lat, "lon": lon, "n": 1},
                    timeout=10
                )
                iss_resp.raise_for_status()
                iss_data = iss_resp.json()
                passes = iss_data.get("response", [])
                if passes:
                    next_pass = passes[0]
                    rise_dt = datetime.fromtimestamp(int(next_pass.get("risetime", 0))).astimezone()
                    duration = int(next_pass.get("duration", 0))
                    iss_line = f"ISS: {rise_dt.strftime('%a %I:%M %p')} ({duration//60}m {duration%60}s)"
            except Exception as e:
                print(f"Astronomy ISS lookup error: {e}")

            self.mark_updated()
            self.set_text(
                "Astronomy\n"
                f"Moon Illumination: {illum:.0f}%\n"
                f"Civil Dark: {civil_twilight_end.strftime('%I:%M %p')}\n"
                f"Astro Dark: {astronomical_twilight_end.strftime('%I:%M %p')}\n"
                f"{iss_line}",
                app,
            )
        except Exception as e:
            print(f"Astronomy widget error: {e}")
            self.set_error("error", app, "Astronomy  Error")

    def update(self, app):
        thread = threading.Thread(target=self._update_text_worker, args=(app,))
        thread.daemon = True
        thread.start()
        self.update_timer = app.after(3600000, lambda: self.update(app))

WIDGET_CLASSES = {
    "time": TimeWidget,
    "date": DateWidget,
    "worldclock": WorldClockWidget,
    "calendar": CalendarWidget,
    "weatherforecast": WeatherForecastWidget,
    "ical": ICalWidget,
    "rss": RssWidget,
    "sports": SportsWidget,
    "stock": StockWidget,
    "history": HistoryWidget,
    "countdown": CountdownWidget,
    "quotes": QuotesWidget,
    "system": SystemStatsWidget,
    "ip": IPWidget,
    "moon": MoonWidget,
    "commute": CommuteWidget,
    "dailyagenda": DailyAgendaWidget,
    "photomemories": PhotoMemoriesWidget,
    "flightboard": FlightBoardWidget,
    "energyprice": EnergyPriceWidget,
    "package": PackageWidget,
    "sunrise": SunriseWidget,
    "sunrisesunset": SunriseWidget,
    "astronomy": AstronomyWidget,
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

        self.start_updates(self.app)

    def start_updates(self, app):
        for widget in self.widgets.values():
            widget.update(app)

    def stop_updates(self):
        for widget in self.widgets.values():
            try:
                if widget.update_timer and hasattr(widget.update_timer, "stop"):
                    widget.update_timer.stop()
            except Exception as e:
                print("stop_updates error:", e)

    def restart_updates(self):
        self.stop_updates()
        self.start_updates(self.app)

    def draw_all(self, painter, app):
        for widget_name in list(self.config.get("widget_positions", {}).keys()):
            w = self.widgets.get(widget_name)
            if w:
                w.draw(painter, app)
