
import requests
from datetime import datetime

# Using a free, public API for historical events
API_URL = "http://history.muffinlabs.com/date"

class HistoryWidget:
    def __init__(self, config, widget_config):
        self.params = {**config, **widget_config}
        self.text = "Loading history..."

    def update(self):
        try:
            response = requests.get(API_URL)
            response.raise_for_status()
            data = response.json()

            events = data.get("data", {}).get("Events", [])
            if events:
                # Display the first 3 events
                event_texts = [f"{e['year']}: {e['text']}" for e in events[:3]]
                self.text = "On This Day:\n" + "\n".join(event_texts)
            else:
                self.text = "No historical events found for today."

        except requests.exceptions.RequestException as e:
            self.text = f"Error fetching history: {e}"
        except Exception as e:
            self.text = f"An error occurred: {e}"

    def get_draw_params(self):
        return {"scale": 0.8, "thick": 1}
