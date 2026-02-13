
import os
import requests

API_KEY = os.environ.get("FMP_API_KEY") 
BASE_URL = "https://financialmodelingprep.com/api/v3/quote/"

class StockWidget:
    def __init__(self, config, widget_config):
        self.params = {**config, **widget_config}
        self.symbols = self.params.get("symbols", ["AAPL", "GOOG"])
        self.api_key = self.params.get("api_key", API_KEY)
        self.text = "Loading stocks..."

    def update(self):
        if not self.api_key or self.api_key == "YOUR_FMP_API_KEY":
            self.text = "Stock Widget: API Key Needed (financialmodelingprep.com)"
            return

        stock_data = []
        try:
            for symbol in self.symbols:
                if not symbol.strip():
                    continue
                url = f"{BASE_URL}{symbol.strip().upper()}?apikey={self.api_key}"
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                if data:
                    price = data[0].get("price", "N/A")
                    change = data[0].get("changesPercentage", 0)
                    change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
                    stock_data.append(f"{symbol.upper()}: ${price:.2f} ({change_str})")
            
            if stock_data:
                self.text = "\n".join(stock_data)
            else:
                self.text = "No stock data found."

        except requests.exceptions.RequestException as e:
            self.text = f"Error fetching stocks: {e}"
        except Exception as e:
            self.text = f"An error occurred: {e}"

    def get_draw_params(self):
        return {"scale": 0.9, "thick": 1}
