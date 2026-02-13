# Magic Mirror

A customizable, modular smart mirror application built with Python and PySide6. This application uses a webcam feed as a dynamic background and overlays a variety of customizable widgets to create a personalized smart mirror experience.
<br/>
<img src="https://github.com/nicarley/pymagicmirror/blob/master/resources/screenshot.png" width="320px" />

## Key Features

*   **Live Video Background:** Uses any connected webcam to create a real-time mirror effect.
*   **Rich Widget Library:** Includes a variety of built-in widgets to display useful information at a glance:
    *   **Time:** A digital clock with 12-hour and 24-hour format options.
    *   **Date:** Displays the current day, date, and year.
    *   **Weather & Forecast:** Shows the current weather and a 5-day forecast for any location (powered by the National Weather Service).
    *   **Calendar:** A simple monthly calendar.
    *   **iCal Feed Aggregator:** Aggregates multiple iCal feeds into a single, unified list of upcoming events.
    *   **RSS Feed Aggregator:** Displays the latest headlines from your favorite RSS feeds.
    *   **Sports:** Live scores and game updates for major leagues (NFL, NBA, MLB, NHL, NCAAF, NCAAMB).
    *   **Stock:** Real-time stock prices and changes for your favorite symbols.
    *   **History:** "On This Day" historical events.
    *   **Countdown:** A countdown timer to a specific date and time.
    *   **Quotes:** Displays random inspirational quotes.
    *   **System Stats:** Shows CPU and RAM usage.
    *   **IP Address:** Displays the machine's local IP address for easy remote management access.
*   **Web Management Interface:** A built-in web server (port 815) allows you to configure the mirror from any device on your network.
    *   **Live Preview:** View a real-time screenshot of the mirror.
    *   **Remote Layout Editing:** Drag and drop widgets directly in the web browser.
    *   **Full Configuration:** Add, remove, and configure all widgets and general settings remotely.
*   **Drag-and-Drop Interface:** An intuitive edit mode allows you to easily reposition widgets by simply dragging and dropping them directly on the mirror.
*   **Real-Time Settings Panel:** A comprehensive settings panel allows you to customize the application in real-time, with no need to restart:
    *   **Webcam Selection:** Automatically detects and allows you to switch between multiple connected cameras.
    *   **Fullscreen Control:** Easily toggle between fullscreen and windowed mode.
    *   **Text Customization:** Adjust global text size, font family, color, and shadow.
    *   **Refresh Interval:** Customize how often data feeds are updated.
    *   **Background Opacity:** Dim the video background for better text readability.
*   **Persistent Configuration:** All your settings and widget layouts are automatically saved to a `config.json` file, so your setup is always just the way you left it.

## Getting Started

### Prerequisites

*   Python 3.x
*   A connected webcam

### Installation

1.  **Clone the repository:**
    
    ```sh
    git clone https://github.com/YOUR_USERNAME/MagicMirror.git
    cd MagicMirror
    ```
    
2.  **Install the required dependencies:**
    
    ```sh
    pip install -r requirements.txt
    ```
    
    *(Note: You will need to create a `requirements.txt` file. Based on the project, it should contain `PySide6`, `opencv-python`, `requests`, `pytz`, `icalendar`, `feedparser`, and `psutil`.)*

3.  **Run the application:**
    
    ```sh
    python Main.py
    ```

## How to Use

*   **Open Settings:** Click the gear icon (⚙️) in the top right corner to open the settings panel.
*   **Edit Layout:** Press the 'E' key or click the 'E' button to enter edit mode. You can then click and drag any widget to a new position. Press 'E' again to save the layout.
*   **Web Interface:** Open a web browser and navigate to `http://localhost:815` (or the machine's IP address) to access the remote management panel.
*   **Toggle Fullscreen:** Press `F11` to enter or exit fullscreen mode. `Escape` will also exit fullscreen.

## Configuration

The application automatically creates and manages a `config.json` file in the root directory. While most settings can be configured through the UI or Web Interface, you can also manually edit this file for advanced customization.

## Contributing

Contributions are welcome! If you have an idea for a new feature or have found a bug, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the `LICENSE.md` file for details.
