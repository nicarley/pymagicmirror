import time
import calendar
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, date, timedelta
import cv2
import numpy as np
import math
import feedparser
from icalendar import Calendar
import pytz
import threading
import certifi
import os
import random
import socket
import textwrap

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
    "nfl": "http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "nba": "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "mlb": "http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "nhl": "http://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "ncaaf": "http://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "ncaamb": "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard",
}

HISTORY_API_URL = "http://history.muffinlabs.com/date"

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
    def _get_emoji(self, desc):
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

            def _pub(e):
                return getattr(e, "published_parsed", None) or time.gmtime(0)
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

    def parse_event(self, event, display_tz):
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
            api_key = self.config.get("FMP_API_KEY", FMP_API_KEY)
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
                def get_year(e):
                    try:
                        return int(e.get('year', 0))
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
            date = datetime.now()
            year = date.year
            month = date.month
            day = date.day

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
