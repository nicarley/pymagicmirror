import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QDialog, QVBoxLayout, QListWidget,
    QPushButton, QLineEdit, QCheckBox, QDialogButtonBox, QWidget, QHBoxLayout,
    QMessageBox, QSizePolicy, QTabWidget, QComboBox, QInputDialog, QSlider, QColorDialog,
    QListWidgetItem
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics, QIcon, QFontDatabase
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
import cv2
import pytz
import certifi
from widget_manager import WidgetManager, WIDGET_CLASSES

# ensure requests and feedparser see a CA bundle in a bundled app
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

CONFIG_FILE = "config.json"

class VideoLabel(QLabel):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self._pixmap = QPixmap()

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap.isNull() or not self.main_app.is_camera_active():
            painter.fillRect(self.rect(), Qt.black)
        else:
            scaled = self._pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(self.rect(), scaled)
            
            # Draw background overlay
            opacity = self.main_app.config.get("background_opacity", 0.0)
            if opacity > 0:
                painter.fillRect(self.rect(), QColor(0, 0, 0, int(opacity * 255)))

        self.main_app.draw_all_widgets(painter)
        if self.main_app.error_message:
            painter.setPen(QColor(255, 80, 80))
            font = QFont(self.main_app.config.get("font_family", "Helvetica")); font.setPointSizeF(14)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            lines = self.main_app.error_message.split("\n")
            w = max(metrics.horizontalAdvance(l) for l in lines) + 20
            h = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5 + 20
            x, y = 20, 20
            painter.fillRect(QRect(x, y, w, h), QColor(0, 0, 0, 160))
            painter.setPen(QColor(255, 255, 255))
            for i, line in enumerate(lines):
                baseline = y + 20 + i * (metrics.height() + 5) + metrics.ascent()
                painter.drawText(QPoint(x + 10, baseline), line)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings and Widgets")
        self.parent = parent
        self.original_config = json.loads(json.dumps(parent.config))
        self.config = parent.config
        self.setMinimumSize(500, 400)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        self.general_tab = QWidget()
        self.general_layout = QVBoxLayout(self.general_tab)
        self.tabs.addTab(self.general_tab, "General")
        self.setup_general_tab()

        self.widget_tab = QWidget()
        self.widget_layout = QVBoxLayout(self.widget_tab)
        self.tabs.addTab(self.widget_tab, "Widgets")
        self.setup_widget_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def setup_general_tab(self):
        self.general_layout.addWidget(QLabel("Webcam Device"))
        self.camera_combo = QComboBox()
        self.available_cameras = self.parent.detect_available_cameras()
        self.camera_combo.addItem("No Video")
        self.camera_combo.addItems([f"Camera {i}" for i in self.available_cameras])
        current_cam_index = self.config.get("camera_index", -1)
        if current_cam_index == -1:
            self.camera_combo.setCurrentIndex(0)
        elif current_cam_index in self.available_cameras:
            self.camera_combo.setCurrentIndex(self.available_cameras.index(current_cam_index) + 1)
        self.camera_combo.currentIndexChanged.connect(self.live_update_camera)
        self.general_layout.addWidget(self.camera_combo)

        self.mirror_video_check = QCheckBox("Mirror Video")
        self.mirror_video_check.setChecked(self.config.get("mirror_video", False))
        self.mirror_video_check.stateChanged.connect(self.live_update_mirror_video)
        self.general_layout.addWidget(self.mirror_video_check)

        self.fullscreen_check = QCheckBox("Start in Fullscreen")
        self.fullscreen_check.setChecked(self.config.get("fullscreen", True))
        self.fullscreen_check.stateChanged.connect(self.live_update_fullscreen)
        self.general_layout.addWidget(self.fullscreen_check)

        self.rotate_button = QPushButton("Rotate Video 90°")
        self.rotate_button.clicked.connect(lambda: self.parent.rotate_video())
        self.general_layout.addWidget(self.rotate_button)

        # Font Selection
        self.general_layout.addWidget(QLabel("Font Family"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(QFontDatabase.families())
        current_font = self.config.get("font_family", "Helvetica")
        self.font_combo.setCurrentText(current_font)
        self.font_combo.currentTextChanged.connect(self.live_update_font)
        self.general_layout.addWidget(self.font_combo)

        # Background Opacity
        self.general_layout.addWidget(QLabel("Background Dimming"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
        self.opacity_slider.valueChanged.connect(self.live_update_opacity)
        self.general_layout.addWidget(self.opacity_slider)

        self.general_layout.addWidget(QLabel("Global Text Size"))
        self.text_size_slider = QSlider(Qt.Horizontal)
        self.text_size_slider.setRange(50, 200)
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.text_size_slider.valueChanged.connect(self.live_update_text_size)
        self.general_layout.addWidget(self.text_size_slider)

        self.general_layout.addWidget(QLabel("Feed Refresh Interval"))
        self.refresh_interval_combo = QComboBox()
        self.refresh_intervals = {
            "15 Minutes": 900000,
            "30 Minutes": 1800000,
            "1 Hour": 3600000,
            "2 Hours": 7200000,
            "6 Hours": 21600000,
            "12 Hours": 43200000,
            "24 Hours": 86400000,
        }
        self.refresh_interval_combo.addItems(self.refresh_intervals.keys())
        current_interval_ms = self.config.get("feed_refresh_interval_ms", 3600000)
        for name, ms in self.refresh_intervals.items():
            if ms == current_interval_ms:
                self.refresh_interval_combo.setCurrentText(name)
        self.refresh_interval_combo.currentTextChanged.connect(self.live_update_refresh_interval)
        self.general_layout.addWidget(self.refresh_interval_combo)

        self.text_color_button = QPushButton("Text Color")
        self.text_color_button.clicked.connect(self.open_text_color_picker)
        self.general_layout.addWidget(self.text_color_button)

        self.shadow_color_button = QPushButton("Text Shadow Color")
        self.shadow_color_button.clicked.connect(self.open_shadow_color_picker)
        self.general_layout.addWidget(self.shadow_color_button)

    def open_text_color_picker(self):
        current_color = QColor(*self.config.get("text_color", [255, 255, 255]))
        color = QColorDialog.getColor(current_color, self)
        if color.isValid():
            self.config["text_color"] = [color.red(), color.green(), color.blue()]
            self.parent.central_widget.update()

    def open_shadow_color_picker(self):
        current_color = QColor(*self.config.get("text_shadow_color", [0, 0, 0]))
        color = QColorDialog.getColor(current_color, self)
        if color.isValid():
            self.config["text_shadow_color"] = [color.red(), color.green(), color.blue()]
            self.parent.central_widget.update()

    def live_update_camera(self, index):
        if index == 0:
            selected = -1
        else:
            selected = self.available_cameras[index - 1]
        if self.config.get("camera_index") != selected:
            self.config["camera_index"] = selected
            self.parent.clear_error_message()
            self.parent.restart_camera()

    def live_update_mirror_video(self, state):
        self.config["mirror_video"] = self.mirror_video_check.isChecked()

    def live_update_fullscreen(self, state):
        is_fullscreen = self.fullscreen_check.isChecked()
        self.config["fullscreen"] = is_fullscreen
        self.parent.set_fullscreen(is_fullscreen)

    def live_update_font(self, font_family):
        self.config["font_family"] = font_family
        self.parent.central_widget.update()

    def live_update_opacity(self, value):
        self.config["background_opacity"] = value / 100.0
        self.parent.central_widget.update()

    def live_update_text_size(self, value):
        self.config["text_scale_multiplier"] = value / 100.0
        self.parent.central_widget.update()

    def live_update_refresh_interval(self, text):
        self.config["feed_refresh_interval_ms"] = self.refresh_intervals[text]
        self.parent.widget_manager.restart_updates()

    def setup_widget_tab(self):
        add_remove = QHBoxLayout()
        self.widget_combo = QComboBox()
        self.widget_combo.addItems(sorted(WIDGET_CLASSES.keys()))
        add_remove.addWidget(self.widget_combo)

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_widget)
        add_remove.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_widget)
        add_remove.addWidget(self.remove_button)
        self.widget_layout.addLayout(add_remove)

        self.widget_list = QListWidget()
        self.widget_list.itemClicked.connect(self.display_widget_settings)
        self.widget_layout.addWidget(self.widget_list)

        self.widget_settings_area = QWidget()
        self.widget_settings_area.setObjectName("settings_area")
        self.widget_settings_layout = QVBoxLayout(self.widget_settings_area)
        self.widget_layout.addWidget(self.widget_settings_area)

        self.refresh_widget_list()

    def refresh_widget_list(self):
        current = self.widget_list.currentItem().text() if self.widget_list.currentItem() else None
        self.widget_list.clear()
        for name in sorted(self.config.get("widget_positions", {})):
            self.widget_list.addItem(name)
            if name == current:
                self.widget_list.setCurrentRow(self.widget_list.count() - 1)

    def add_widget(self):
        widget_type = self.widget_combo.currentText()
        i = 1
        while f"{widget_type}_{i}" in self.config["widget_positions"]:
            i += 1
        widget_name = f"{widget_type}_{i}"

        self.config["widget_positions"][widget_name] = {"x": 0.5, "y": 0.5, "anchor": "center"}
        if widget_type == "ical":
            self.config["widget_settings"][widget_name] = {"urls": [], "timezone": "US/Central"}
        elif widget_type == "rss":
            self.config["widget_settings"][widget_name] = {"urls": [], "style": "Normal", "title": ""}
        elif widget_type == "weatherforecast":
            self.config["widget_settings"][widget_name] = {"location": "Salem, IL", "style": "Normal"}
        elif widget_type == "worldclock":
            self.config["widget_settings"][widget_name] = {"timezone": "UTC"}
        elif widget_type == "sports":
            self.config["widget_settings"][widget_name] = {"configs": [], "style": "Normal", "timezone": "UTC"}
        elif widget_type == "stock":
            self.config["widget_settings"][widget_name] = {"symbols": ["AAPL", "GOOG"], "api_key": self.config.get("FMP_API_KEY", ""), "style": "Normal"}
        elif widget_type == "date":
            self.config["widget_settings"][widget_name] = {"format": "%A, %B %d, %Y"}
        elif widget_type == "history":
            pass # No settings for history widget
        elif widget_type == "countdown":
            self.config["widget_settings"][widget_name] = {"name": "New Event", "datetime": ""}

        self.parent.widget_manager.load_widgets()
        self.refresh_widget_list()
        items = self.widget_list.findItems(widget_name, Qt.MatchExactly)
        if items:
            self.widget_list.setCurrentItem(items[0])
            self.display_widget_settings(items[0])

    def remove_widget(self):
        current_item = self.widget_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a widget to remove.")
            return
        widget_name = current_item.text()
        reply = QMessageBox.question(self, "Confirm", f"Remove {widget_name}?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.config["widget_positions"].pop(widget_name, None)
            self.config["widget_settings"].pop(widget_name, None)
            self.parent.widget_manager.load_widgets()
            self.refresh_widget_list()
            self.clear_layout(self.widget_settings_layout)

    def display_widget_settings(self, item):
        self.save_current_widget_ui_to_config()
        self.clear_layout(self.widget_settings_layout)

        widget_name = item.text()
        self.widget_settings_area.setProperty("current_widget", widget_name)
        widget_type = widget_name.split("_")[0]
        settings = self.config.get("widget_settings", {}).get(widget_name, {})

        if widget_type == "time":
            self.widget_settings_layout.addWidget(QLabel("Time Format"))
            combo = QComboBox(); combo.setObjectName("time_format_combo")
            combo.addItems(["24h", "12h"])
            combo.setCurrentText(settings.get("format", "24h"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(combo)
        elif widget_type == "date":
            self.widget_settings_layout.addWidget(QLabel("Date Format"))
            combo = QComboBox(); combo.setObjectName("date_format_combo")
            formats = [
                "%A, %B %d, %Y", # Monday, January 01, 2024
                "%a, %b %d, %Y", # Mon, Jan 01, 2024
                "%m/%d/%Y",      # 01/01/2024
                "%d.%m.%Y",      # 01.01.2024
                "%Y-%m-%d"       # 2024-01-01
            ]
            combo.addItems(formats)
            combo.setEditable(True)
            combo.setCurrentText(settings.get("format", "%A, %B %d, %Y"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(combo)
        elif widget_type == "worldclock":
            self.widget_settings_layout.addWidget(QLabel("Timezone"))
            tz_combo = QComboBox(); tz_combo.setObjectName("tz_combo")
            tz_combo.addItems(pytz.all_timezones)
            tz_combo.setCurrentText(settings.get("timezone", "UTC"))
            tz_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(tz_combo)
        elif widget_type == "weatherforecast":
            self.widget_settings_layout.addWidget(QLabel("Location"))
            location_entry = QLineEdit(settings.get("location", ""))
            location_entry.setObjectName("location_entry")
            location_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(location_entry)

            self.widget_settings_layout.addWidget(QLabel("Display Style"))
            style_combo = QComboBox(); style_combo.setObjectName("style_combo")
            style_combo.addItems(["Normal", "Ticker"])
            style_combo.setCurrentText(settings.get("style", "Normal"))
            style_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(style_combo)
        elif widget_type == "ical":
            self.widget_settings_layout.addWidget(QLabel("Timezone"))
            tz_combo = QComboBox(); tz_combo.setObjectName("tz_combo")
            tz_combo.addItems(pytz.all_timezones)
            tz_combo.setCurrentText(settings.get("timezone", "US/Central"))
            tz_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(tz_combo)

            self.widget_settings_layout.addWidget(QLabel("iCal Feed URLs"))
            url_list = QListWidget(); url_list.setObjectName("url_list")
            url_list.addItems(settings.get("urls", []))
            self.widget_settings_layout.addWidget(url_list)

            add_url_button = QPushButton("Add URL"); remove_url_button = QPushButton("Remove Selected URL")
            add_url_button.clicked.connect(self.add_url)
            remove_url_button.clicked.connect(self.remove_url)
            self.widget_settings_layout.addWidget(add_url_button)
            self.widget_settings_layout.addWidget(remove_url_button)
        elif widget_type == "rss":
            self.widget_settings_layout.addWidget(QLabel("Title"))
            title_entry = QLineEdit(settings.get("title", ""))
            title_entry.setObjectName("title_entry")
            title_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(title_entry)

            self.widget_settings_layout.addWidget(QLabel("Display Style"))
            style_combo = QComboBox(); style_combo.setObjectName("style_combo")
            style_combo.addItems(["Normal", "Ticker"])
            style_combo.setCurrentText(settings.get("style", "Normal"))
            style_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(style_combo)

            self.widget_settings_layout.addWidget(QLabel("RSS Feed URLs"))
            url_list = QListWidget(); url_list.setObjectName("url_list")
            url_list.addItems(settings.get("urls", []))
            self.widget_settings_layout.addWidget(url_list)

            add_url_button = QPushButton("Add URL"); remove_url_button = QPushButton("Remove Selected URL")
            add_url_button.clicked.connect(self.add_url)
            remove_url_button.clicked.connect(self.remove_url)
            self.widget_settings_layout.addWidget(add_url_button)
            self.widget_settings_layout.addWidget(remove_url_button)
        elif widget_type == "sports":
            self.setup_sports_settings(settings)
        elif widget_type == "stock":
            self.widget_settings_layout.addWidget(QLabel("API Key"))
            api_key_entry = QLineEdit(settings.get("api_key", self.config.get("FMP_API_KEY", "")))
            api_key_entry.setObjectName("api_key_entry")
            api_key_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(api_key_entry)

            self.widget_settings_layout.addWidget(QLabel("Symbols (comma-separated)"))
            symbols_entry = QLineEdit(",".join(settings.get("symbols", [])))
            symbols_entry.setObjectName("symbols_entry")
            symbols_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(symbols_entry)

            self.widget_settings_layout.addWidget(QLabel("Display Style"))
            style_combo = QComboBox(); style_combo.setObjectName("style_combo")
            style_combo.addItems(["Normal", "Ticker"])
            style_combo.setCurrentText(settings.get("style", "Normal"))
            style_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(style_combo)
        elif widget_type == "countdown":
            self.widget_settings_layout.addWidget(QLabel("Event Name"))
            name_entry = QLineEdit(settings.get("name", "New Event"))
            name_entry.setObjectName("countdown_name_entry")
            name_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(name_entry)

            self.widget_settings_layout.addWidget(QLabel("Target Date and Time (YYYY-MM-DD HH:MM)"))
            datetime_entry = QLineEdit(settings.get("datetime", ""))
            datetime_entry.setObjectName("countdown_datetime_entry")
            datetime_entry.setPlaceholderText("e.g., 2024-12-31 23:59")
            datetime_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            self.widget_settings_layout.addWidget(datetime_entry)


    def setup_sports_settings(self, settings):
        self.widget_settings_layout.addWidget(QLabel("League Configurations"))
        
        self.sports_config_list = QListWidget()
        self.sports_config_list.setObjectName("sports_config_list")
        for config in settings.get("configs", []):
            league = config.get("league", "N/A")
            teams = ", ".join(config.get("teams", []))
            self.sports_config_list.addItem(f"{league.upper()}: {teams if teams else 'All'}")
        self.widget_settings_layout.addWidget(self.sports_config_list)

        # Add new config section
        add_layout = QHBoxLayout()
        self.new_sport_league_combo = QComboBox()
        self.new_sport_league_combo.addItems(["NFL", "NBA", "MLB", "NHL", "NCAAF", "NCAAMB"])
        add_layout.addWidget(self.new_sport_league_combo)
        self.new_sport_teams_entry = QLineEdit()
        self.new_sport_teams_entry.setPlaceholderText("Teams (e.g. CHI,STL)")
        add_layout.addWidget(self.new_sport_teams_entry)
        self.widget_settings_layout.addLayout(add_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        add_sport_btn = QPushButton("Add League/Teams")
        add_sport_btn.clicked.connect(self.add_sports_config)
        btn_layout.addWidget(add_sport_btn)
        remove_sport_btn = QPushButton("Remove Selected")
        remove_sport_btn.clicked.connect(self.remove_sports_config)
        btn_layout.addWidget(remove_sport_btn)
        self.widget_settings_layout.addLayout(btn_layout)

        # Timezone
        self.widget_settings_layout.addWidget(QLabel("Timezone"))
        tz_combo = QComboBox(); tz_combo.setObjectName("tz_combo")
        tz_combo.addItems(pytz.all_timezones)
        tz_combo.setCurrentText(settings.get("timezone", "UTC"))
        tz_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
        self.widget_settings_layout.addWidget(tz_combo)

        # Style
        self.widget_settings_layout.addWidget(QLabel("Display Style"))
        style_combo = QComboBox(); style_combo.setObjectName("style_combo")
        style_combo.addItems(["Normal", "Ticker"])
        style_combo.setCurrentText(settings.get("style", "Normal"))
        style_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
        self.widget_settings_layout.addWidget(style_combo)

    def add_sports_config(self):
        league = self.new_sport_league_combo.currentText()
        teams_text = self.new_sport_teams_entry.text()
        
        if not league:
            return

        teams = [team.strip().upper() for team in teams_text.split(",") if team.strip()]
        
        # Add to UI list
        self.sports_config_list.addItem(f"{league.upper()}: {', '.join(teams) if teams else 'All'}")
        self.new_sport_teams_entry.clear()
        self.save_current_widget_ui_to_config()

    def remove_sports_config(self):
        current_item = self.sports_config_list.currentItem()
        if current_item:
            self.sports_config_list.takeItem(self.sports_config_list.row(current_item))
            self.save_current_widget_ui_to_config()

    def add_url(self):
        url, ok = QInputDialog.getText(self, "Add URL", "Enter the new URL")
        if ok and url:
            url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
            if url_list:
                url_list.addItem(url)
                self.save_current_widget_ui_to_config()

    def remove_url(self):
        url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
        if url_list and url_list.currentItem():
            url_list.takeItem(url_list.row(url_list.currentItem()))
            self.save_current_widget_ui_to_config()

    def save_current_widget_ui_to_config(self, *args):
        widget_name = self.widget_settings_area.property("current_widget")
        if not widget_name:
            return

        widget_type = widget_name.split("_")[0]
        self.config.setdefault("widget_settings", {}).setdefault(widget_name, {})

        if widget_type == "time":
            combo = self.widget_settings_area.findChild(QComboBox, "time_format_combo")
            if combo:
                self.config["widget_settings"][widget_name]["format"] = combo.currentText()
        elif widget_type == "date":
            combo = self.widget_settings_area.findChild(QComboBox, "date_format_combo")
            if combo:
                self.config["widget_settings"][widget_name]["format"] = combo.currentText()
        elif widget_type == "worldclock":
            tz_combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if tz_combo:
                self.config["widget_settings"][widget_name]["timezone"] = tz_combo.currentText()
        elif widget_type == "weatherforecast":
            location_entry = self.widget_settings_area.findChild(QLineEdit, "location_entry")
            if location_entry:
                self.config["widget_settings"][widget_name]["location"] = location_entry.text()
            style_combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if style_combo:
                self.config["widget_settings"][widget_name]["style"] = style_combo.currentText()
        elif widget_type == "ical":
            tz_combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if tz_combo:
                self.config["widget_settings"][widget_name]["timezone"] = tz_combo.currentText()
            url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
            if url_list:
                self.config["widget_settings"][widget_name]["urls"] = [
                    url_list.item(i).text() for i in range(url_list.count())
                ]
        elif widget_type == "rss":
            title_entry = self.widget_settings_area.findChild(QLineEdit, "title_entry")
            if title_entry:
                self.config["widget_settings"][widget_name]["title"] = title_entry.text()
            url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
            if url_list:
                self.config["widget_settings"][widget_name]["urls"] = [
                    url_list.item(i).text() for i in range(url_list.count())
                ]
            style_combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if style_combo:
                self.config["widget_settings"][widget_name]["style"] = style_combo.currentText()
        elif widget_type == "sports":
            configs = []
            config_list_widget = self.widget_settings_area.findChild(QListWidget, "sports_config_list")
            if config_list_widget:
                for i in range(config_list_widget.count()):
                    item_text = config_list_widget.item(i).text()
                    parts = item_text.split(":", 1)
                    league = parts[0].strip()
                    teams_str = parts[1].strip()
                    teams = [t.strip() for t in teams_str.split(",")] if teams_str.lower() != 'all' else []
                    configs.append({"league": league, "teams": teams})
            self.config["widget_settings"][widget_name]["configs"] = configs
            
            tz_combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if tz_combo:
                self.config["widget_settings"][widget_name]["timezone"] = tz_combo.currentText()

            style_combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if style_combo:
                self.config["widget_settings"][widget_name]["style"] = style_combo.currentText()
        elif widget_type == "stock":
            api_key_entry = self.widget_settings_area.findChild(QLineEdit, "api_key_entry")
            if api_key_entry:
                self.config["widget_settings"][widget_name]["api_key"] = api_key_entry.text()
            symbols_entry = self.widget_settings_area.findChild(QLineEdit, "symbols_entry")
            if symbols_entry:
                self.config["widget_settings"][widget_name]["symbols"] = [s.strip() for s in symbols_entry.text().split(",")]
            
            style_combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if style_combo:
                self.config["widget_settings"][widget_name]["style"] = style_combo.currentText()
        elif widget_type == "countdown":
            name_entry = self.widget_settings_area.findChild(QLineEdit, "countdown_name_entry")
            if name_entry:
                self.config["widget_settings"][widget_name]["name"] = name_entry.text()
            datetime_entry = self.widget_settings_area.findChild(QLineEdit, "countdown_datetime_entry")
            if datetime_entry:
                self.config["widget_settings"][widget_name]["datetime"] = datetime_entry.text()

        self.parent.widget_manager.restart_updates()

    def accept(self):
        self.save_current_widget_ui_to_config()
        self.parent.save_config()
        super().accept()

    def reject(self):
        self.parent.config.clear()
        self.parent.config.update(self.original_config)
        self.parent.set_fullscreen(self.parent.config.get("fullscreen", True))
        self.parent.restart_camera()
        self.parent.widget_manager.config = self.parent.config
        self.parent.widget_manager.load_widgets()
        super().reject()

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

class MagicMirrorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.edit_mode = False
        self.drag_data = {"widget": None, "start_pos": None, "start_widget_pos": None}
        self.error_message = ""
        self.load_config()

        self.setWindowTitle("Magic Mirror")
        self.central_widget = VideoLabel(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setAlignment(Qt.AlignLeft)
        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.central_widget.setMouseTracking(True)
        self.central_widget.mousePressEvent = self.central_widget_mouse_press
        self.central_widget.mouseMoveEvent = self.central_widget_mouse_move
        self.central_widget.mouseReleaseEvent = self.central_widget_mouse_release

        self.widget_manager = WidgetManager(self, self.config)
        self.setup_camera()
        self.setup_overlay()
        self.set_fullscreen(self.config.get("fullscreen", True))
        
        # Ticker timer
        self.ticker_timer = QTimer(self)
        self.ticker_timer.timeout.connect(self.update_tickers)
        self.ticker_timer.start(30)

    def detect_available_cameras(self):
        available = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def is_camera_active(self):
        return self.config.get("camera_index", -1) != -1 and hasattr(self, "cap") and self.cap.isOpened()

    def load_config(self):
        default_config = {
            "camera_index": 0,
            "video_rotation": 0,
            "mirror_video": False,
            "fullscreen": True,
            "text_scale_multiplier": 1.0,
            "feed_refresh_interval_ms": 3600000,
            "widget_positions": {},
            "widget_settings": {},
            "text_color": [255, 255, 255],
            "text_shadow_color": [0, 0, 0],
            "FMP_API_KEY": "YOUR_FMP_API_KEY",
            "font_family": "Helvetica",
            "background_opacity": 0.0
        }
        if not os.path.exists(CONFIG_FILE):
            self.config = default_config
        else:
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
            for k, v in default_config.items():
                if k not in self.config:
                    self.config[k] = v
        self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def setup_camera(self, camera_index=None):
        if camera_index is None:
            camera_index = self.config.get("camera_index", 0)

        if hasattr(self, "cap") and self.cap.isOpened():
            self.cap.release()

        if camera_index == -1:
            if not (hasattr(self, "timer") and self.timer.isActive()):
                self.timer = QTimer(self)
                self.timer.timeout.connect(self.update_camera_feed)
                self.timer.start(30)
            self.central_widget.set_pixmap(QPixmap())
            return

        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            self.show_error("Could not open camera. Use Settings to pick another device.")
            return

        if not hasattr(self, "timer") or not self.timer.isActive():
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_camera_feed)
            self.timer.start(30)

        self.clear_error_message()

    def restart_camera(self):
        self.setup_camera()

    def rotate_video(self):
        self.config["video_rotation"] = (self.config.get("video_rotation", 0) + 1) % 4

    def set_fullscreen(self, fullscreen):
        if fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()

    def setup_overlay(self):
        self.settings_button = QPushButton("⚙️", self)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.settings_button.setStyleSheet(
            "background-color: rgba(0,0,0,0.5); color: white; border: none; font-size: 24px; padding: 5px;"
        )
        self.settings_button.setFixedSize(40, 40)

        self.edit_button = QPushButton("E", self)
        self.edit_button.setCheckable(True)
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        self.edit_button.setStyleSheet(
            "background-color: rgba(0,0,0,0.5); color: white; border: 1px solid white; font-size: 18px;"
        )
        self.edit_button.setFixedSize(40, 40)

    def update_camera_feed(self):
        if not self.is_camera_active():
            self.central_widget.update()
            return

        ret, frame = self.cap.read()
        if not ret:
            self.central_widget.update()
            return

        if self.config.get("mirror_video", False):
            frame = cv2.flip(frame, 1)
        rot = self.config.get("video_rotation", 0)
        if rot != 0:
            frame = cv2.rotate(frame, [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE][rot - 1])

        h, w, ch = frame.shape
        q_img = QImage(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        self.central_widget.set_pixmap(pixmap)

    def update_tickers(self):
        needs_update = False
        for widget_name, widget in self.widget_manager.widgets.items():
            settings = self.config.get("widget_settings", {}).get(widget_name, {})
            if settings.get("style") == "Ticker":
                widget.ticker_scroll_x -= 2  # Scroll speed
                needs_update = True
        
        if needs_update:
            self.central_widget.update()

    def draw_all_widgets(self, painter):
        self.widget_manager.draw_all(painter)
        if self.edit_mode:
            painter.setPen(QColor(0, 255, 0, 200))
            painter.setBrush(QColor(0, 255, 0, 50))
            for name in self.config["widget_positions"]:
                bbox = self.get_widget_bbox(name)
                if bbox:
                    painter.drawRect(bbox)

    def _get_top_left_for_anchor(self, anchor, anchor_point, width, height):
        x, y = anchor_point
        if "e" in anchor:
            x -= width
        elif "w" not in anchor:
            x -= width / 2
        if "s" in anchor:
            y -= height
        elif "n" not in anchor:
            y -= height / 2
        return x, y

    def get_widget_bbox(self, widget_name):
        widget = self.widget_manager.widgets.get(widget_name)
        if not widget:
            return None
        scale_multiplier = self.config.get("text_scale_multiplier", 1.0)
        final_scale = widget.params["scale"] * scale_multiplier
        font = QFont(self.config.get("font_family", "Helvetica")); font.setPointSizeF(final_scale * 10)
        metrics = QFontMetrics(font)
        text_content = widget.text if getattr(widget, "text", "") else f"({widget_name})"
        
        settings = self.config.get("widget_settings", {}).get(widget_name, {})
        if settings.get("style") == "Ticker":
             # For ticker, bbox is just a placeholder strip
             text_width = self.central_widget.width() * 0.8
             text_height = metrics.height() + 10
        else:
            lines = text_content.split("\n")
            if not lines:
                return None
            text_width = max(metrics.horizontalAdvance(line) for line in lines) if lines else 0
            text_height = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5

        pos = self.config["widget_positions"][widget_name]
        anchor_x = int(pos["x"] * self.central_widget.width())
        anchor_y = int(pos["y"] * self.central_widget.height())
        anchor = pos.get("anchor", "nw")
        x0, y0 = self._get_top_left_for_anchor(anchor, (anchor_x, anchor_y), text_width, text_height)
        return QRect(int(x0), int(y0), int(text_width) + 2, int(text_height) + 2)

    def draw_text(self, painter, text, pos, font_scale, **kwargs):
        if not text:
            return
        
        widget_name = kwargs.get("widget_name")
        settings = self.config.get("widget_settings", {}).get(widget_name, {})
        is_ticker = settings.get("style") == "Ticker"

        font = QFont(self.config.get("font_family", "Helvetica")); font.setPointSizeF(font_scale * 10)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        if is_ticker:
            # Ticker drawing logic
            text_width = metrics.horizontalAdvance(text)
            widget = self.widget_manager.widgets.get(widget_name)
            
            # Reset scroll if it's gone too far left
            if widget.ticker_scroll_x < -text_width:
                widget.ticker_scroll_x = self.central_widget.width()

            # Initialize scroll if needed (first draw)
            if widget.ticker_scroll_x == 0 and text_width > 0:
                 widget.ticker_scroll_x = self.central_widget.width()

            x = widget.ticker_scroll_x
            y = pos[1] # Use the Y position from the config
            
            # Draw background strip for ticker
            strip_height = metrics.height() + 10
            painter.fillRect(0, int(y - strip_height/2), self.central_widget.width(), int(strip_height), QColor(0, 0, 0, 150))

            baseline_y = y + metrics.ascent() - metrics.height()/2
            
            painter.setPen(QColor(*self.config.get("text_shadow_color", [0, 0, 0])))
            painter.drawText(QPoint(int(x) + 2, int(baseline_y) + 2), text)
            painter.setPen(QColor(*self.config.get("text_color", [255, 255, 255])))
            painter.drawText(QPoint(int(x), int(baseline_y)), text)

        else:
            # Normal multi-line drawing logic
            lines = text.split("\n")
            max_width = max(metrics.horizontalAdvance(line) for line in lines)
            total_height = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5
            anchor = kwargs.get("anchor", "nw")

            x, y = self._get_top_left_for_anchor(anchor, pos, max_width, total_height)

            for i, line in enumerate(lines):
                line_y = y + i * (metrics.height() + 5)
                line_width = metrics.horizontalAdvance(line)
                line_x = x
                baseline_y = line_y + metrics.ascent()
                painter.setPen(QColor(*self.config.get("text_shadow_color", [0, 0, 0])))
                painter.drawText(QPoint(int(line_x) + 2, int(baseline_y) + 2), line)
                painter.setPen(QColor(*self.config.get("text_color", [255, 255, 255])))
                painter.drawText(QPoint(int(line_x), int(baseline_y)), line)

    def central_widget_mouse_press(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            for name in reversed(list(self.config["widget_positions"])):
                bbox = self.get_widget_bbox(name)
                if bbox and bbox.contains(event.position().toPoint()):
                    self.drag_data = {
                        "widget": name,
                        "start_pos": event.position().toPoint(),
                        "start_widget_pos": self.config["widget_positions"][name].copy(),
                    }
                    return

    def central_widget_mouse_move(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.buttons() & Qt.LeftButton:
            delta = event.position().toPoint() - self.drag_data["start_pos"]
            if self.central_widget.width() == 0 or self.central_widget.height() == 0:
                return
            new_x = self.drag_data["start_widget_pos"]["x"] + delta.x() / self.central_widget.width()
            new_y = self.drag_data["start_widget_pos"]["y"] + delta.y() / self.central_widget.height()
            self.config["widget_positions"][self.drag_data["widget"]]["x"] = max(0.0, min(1.0, new_x))
            self.config["widget_positions"][self.drag_data["widget"]]["y"] = max(0.0, min(1.0, new_y))
            self.central_widget.update()

    def central_widget_mouse_release(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.button() == Qt.LeftButton:
            self.drag_data["widget"] = None
            self.save_config()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.set_fullscreen(False)
        elif event.key() == Qt.Key_F11:
            self.set_fullscreen(not self.isFullScreen())
        elif event.key() == Qt.Key_E:
            self.edit_button.toggle()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if self.sender() == self.edit_button:
            dialog.tabs.setCurrentIndex(1)
        dialog.exec()

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        QMessageBox.information(self, "Edit Mode", f"Drag and drop is now {'enabled' if self.edit_mode else 'disabled'}.")

    def resizeEvent(self, event):
        self.settings_button.move(self.width() - self.settings_button.width() - 10, 10)
        self.edit_button.move(self.width() - self.edit_button.width() - 60, 10)
        super().resizeEvent(event)

    def show_error(self, message):
        self.error_message = message
        self.central_widget.update()

    def clear_error_message(self):
        self.error_message = ""
        self.central_widget.update()

    def after(self, ms, func):
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(func)
        t.start(ms)
        return t

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("resources/icon.png"))
    window = MagicMirrorApp()
    window.show()
    sys.exit(app.exec())
