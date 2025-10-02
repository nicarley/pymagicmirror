
import time
import calendar
import requests

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
        """Schedules the next update for the widget."""
        pass

    def draw(self, frame, app):
        """Draws the widget's text onto the frame."""
        win_width, win_height = frame.shape[1], frame.shape[0]
        x, y, anchor = self.get_position(win_width, win_height)
        app.draw_text(frame, self.text, (x, y), self.params["scale"], (255, 255, 255), thickness=self.params["thick"], anchor=anchor)

    def get_draw_params(self):
        """Returns the drawing parameters for the widget."""
        all_params = {
            "time": {"scale": 3, "thick": 3}, 
            "date": {"scale": 1.2, "thick": 2}, 
            "weather": {"scale": 1, "thick": 2}, 
            "calendar": {"scale": 0.8, "thick": 1}, 
            "news": {"scale": 0.8, "thick": 1}
        }
        return all_params.get(self.widget_name, {"scale": 1, "thick": 2})

class TimeWidget(BaseWidget):
    def __init__(self, config, widget_name="time"):
        super().__init__(config, widget_name)

    def _update_text(self):
        self.text = time.strftime('%H:%M:%S')

    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class DateWidget(BaseWidget):
    def __init__(self, config, widget_name="date"):
        super().__init__(config, widget_name)

    def _update_text(self):
        self.text = time.strftime('%A, %B %d, %Y')

    def update(self, app):
        self._update_text()
        app.after(1000, lambda: self.update(app))

class WeatherWidget(BaseWidget):
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

class NewsWidget(BaseWidget):
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

class CalendarWidget(BaseWidget):
    def __init__(self, config, widget_name="calendar"):
        super().__init__(config, widget_name)

    def _update_text(self):
        now = time.localtime()
        self.text = calendar.month(now.tm_year, now.tm_mon)

    def update(self, app):
        self._update_text()
        app.after(3600000, lambda: self.update(app))

class WidgetManager:
    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.widgets = {
            "time": TimeWidget(config),
            "date": DateWidget(config),
            "weather": WeatherWidget(config),
            "news": NewsWidget(config),
            "calendar": CalendarWidget(config)
        }
        self.start_updates()

    def start_updates(self):
        for widget in self.widgets.values():
            widget.update(self.app)

    def draw_all(self, frame):
        for widget in self.widgets.values():
            widget.draw(frame, self.app)
