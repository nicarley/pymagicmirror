import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QDialog, QVBoxLayout, QListWidget,
    QPushButton, QLineEdit, QCheckBox, QDialogButtonBox, QWidget, QHBoxLayout,
    QMessageBox, QSizePolicy, QTabWidget, QComboBox, QSlider, QColorDialog,
    QListWidgetItem, QScrollArea, QSplitter, QFrame, QGroupBox, QFormLayout,
    QInputDialog, QFileDialog
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics, QIcon, QFontDatabase, QBrush
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QBuffer, QIODevice, QMutex, QMutexLocker
import cv2
import pytz
import certifi
from widget_manager import WidgetManager, WIDGET_CLASSES
import web_server

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
            painter.fillRect(self.rect(), Qt.GlobalColor.black)
        else:
            scaled = self._pixmap.scaled(self.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
        self.setMinimumSize(900, 600)

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

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def setup_general_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        self.general_layout.addWidget(scroll)

        # Camera & Display Group
        cam_group = QGroupBox("Camera & Display")
        cam_layout = QFormLayout(cam_group)
        
        self.background_mode_combo = QComboBox()
        self.background_mode_combo.addItem("None")
        self.background_mode_combo.addItem("Camera")
        self.background_mode_combo.addItem("Image")
        self.background_mode_combo.addItem("Video")
        self.background_mode_combo.addItem("YouTube")
        
        # Add available cameras
        self.available_cameras = self.parent.detect_available_cameras()
        for i in self.available_cameras:
            self.background_mode_combo.addItem(f"Camera {i}")

        current_mode = self.config.get("background_mode", "Camera")
        current_cam_index = self.config.get("camera_index", 0)
        
        # Set initial selection
        if current_mode == "None":
            self.background_mode_combo.setCurrentText("None")
        elif current_mode == "Image":
            self.background_mode_combo.setCurrentText("Image")
        elif current_mode == "Video":
            self.background_mode_combo.setCurrentText("Video")
        elif current_mode == "YouTube":
            self.background_mode_combo.setCurrentText("YouTube")
        elif current_mode == "Camera":
            if current_cam_index in self.available_cameras:
                self.background_mode_combo.setCurrentText(f"Camera {current_cam_index}")
            else:
                self.background_mode_combo.setCurrentText("Camera") # Fallback

        self.background_mode_combo.currentIndexChanged.connect(self.live_update_background_mode)
        cam_layout.addRow("Background Mode:", self.background_mode_combo)

        # File selection for Image/Video
        file_layout = QHBoxLayout()
        self.background_file_input = QLineEdit()
        self.background_file_input.setText(self.config.get("background_file", ""))
        self.background_file_input.textChanged.connect(self.live_update_background_file)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.select_background_file)
        file_layout.addWidget(self.background_file_input)
        file_layout.addWidget(self.browse_button)
        
        self.file_row_label = QLabel("File Path / URL:")
        self.file_row_widget = QWidget()
        self.file_row_widget.setLayout(file_layout)
        cam_layout.addRow(self.file_row_label, self.file_row_widget)

        self.mirror_video_check = QCheckBox("Mirror Video")
        self.mirror_video_check.setChecked(self.config.get("mirror_video", False))
        self.mirror_video_check.stateChanged.connect(self.live_update_mirror_video)
        cam_layout.addRow("", self.mirror_video_check)

        self.fullscreen_check = QCheckBox("Start in Fullscreen")
        self.fullscreen_check.setChecked(self.config.get("fullscreen", True))
        self.fullscreen_check.stateChanged.connect(self.live_update_fullscreen)
        cam_layout.addRow("", self.fullscreen_check)

        self.rotate_button = QPushButton("Rotate Video 90°")
        self.rotate_button.clicked.connect(lambda: self.parent.rotate_video())
        cam_layout.addRow("Rotation:", self.rotate_button)
        
        layout.addWidget(cam_group)
        
        # Initial UI state update
        self.update_background_ui_state()

        # Appearance Group
        app_group = QGroupBox("Appearance")
        app_layout = QFormLayout(app_group)

        self.font_combo = QComboBox()
        self.font_combo.addItems(QFontDatabase.families())
        self.font_combo.setCurrentText(self.config.get("font_family", "Helvetica"))
        self.font_combo.currentTextChanged.connect(self.live_update_font)
        app_layout.addRow("Font Family:", self.font_combo)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
        self.opacity_slider.valueChanged.connect(self.live_update_opacity)
        app_layout.addRow("Background Dimming:", self.opacity_slider)

        self.text_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_size_slider.setRange(50, 200)
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.text_size_slider.valueChanged.connect(self.live_update_text_size)
        app_layout.addRow("Global Text Size:", self.text_size_slider)

        colors_layout = QHBoxLayout()
        self.text_color_button = QPushButton("Text Color")
        self.text_color_button.clicked.connect(self.open_text_color_picker)
        colors_layout.addWidget(self.text_color_button)

        self.shadow_color_button = QPushButton("Shadow Color")
        self.shadow_color_button.clicked.connect(self.open_shadow_color_picker)
        colors_layout.addWidget(self.shadow_color_button)
        app_layout.addRow("Colors:", colors_layout)

        layout.addWidget(app_group)

        # System Group
        sys_group = QGroupBox("System")
        sys_layout = QFormLayout(sys_group)

        self.refresh_interval_combo = QComboBox()
        self.refresh_intervals = {
            "15 Minutes": 900000, "30 Minutes": 1800000, "1 Hour": 3600000,
            "2 Hours": 7200000, "6 Hours": 21600000, "12 Hours": 43200000, "24 Hours": 86400000,
        }
        self.refresh_interval_combo.addItems(list(self.refresh_intervals.keys()))
        current_interval_ms = self.config.get("feed_refresh_interval_ms", 3600000)
        for name, ms in self.refresh_intervals.items():
            if ms == current_interval_ms:
                self.refresh_interval_combo.setCurrentText(name)
        self.refresh_interval_combo.currentTextChanged.connect(self.live_update_refresh_interval)
        sys_layout.addRow("Feed Refresh:", self.refresh_interval_combo)
        
        self.web_server_check = QCheckBox("Enable Web Management")
        self.web_server_check.setChecked(self.config.get("web_server_enabled", False))
        self.web_server_check.stateChanged.connect(self.live_update_web_server)
        sys_layout.addRow("", self.web_server_check)

        layout.addWidget(sys_group)
        layout.addStretch()

    def open_text_color_picker(self):
        c = self.config.get("text_color", [255, 255, 255])
        current_color = QColor(c[0], c[1], c[2])
        color = QColorDialog.getColor(current_color, self)
        if color.isValid():
            self.config["text_color"] = [color.red(), color.green(), color.blue()]
            self.parent.central_widget.update()

    def open_shadow_color_picker(self):
        c = self.config.get("text_shadow_color", [0, 0, 0])
        current_color = QColor(c[0], c[1], c[2])
        color = QColorDialog.getColor(current_color, self)
        if color.isValid():
            self.config["text_shadow_color"] = [color.red(), color.green(), color.blue()]
            self.parent.central_widget.update()

    def live_update_camera(self, index):
        self.live_update_background_mode(index)

    def live_update_background_mode(self, index):
        text = self.background_mode_combo.currentText()
        
        if text == "None":
            self.config["background_mode"] = "None"
        elif text == "Image":
            self.config["background_mode"] = "Image"
        elif text == "Video":
            self.config["background_mode"] = "Video"
        elif text == "YouTube":
            self.config["background_mode"] = "YouTube"
        elif text.startswith("Camera"):
            self.config["background_mode"] = "Camera"
            try:
                cam_idx = int(text.split(" ")[1])
                self.config["camera_index"] = cam_idx
            except (IndexError, ValueError):
                pass
        
        self.update_background_ui_state()
        self.parent.restart_camera()

    def update_background_ui_state(self):
        mode = self.config.get("background_mode", "Camera")
        show_file = mode in ["Image", "Video", "YouTube"]
        self.file_row_label.setVisible(show_file)
        self.file_row_widget.setVisible(show_file)
        self.browse_button.setVisible(mode != "YouTube") # No browse for YouTube
        
        if mode == "YouTube":
            self.background_file_input.setPlaceholderText("Enter YouTube URL")
        else:
            self.background_file_input.setPlaceholderText("Path to file")

    def select_background_file(self):
        mode = self.config.get("background_mode", "Image")
        if mode == "Image":
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        elif mode == "Video":
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Videos (*.mp4 *.avi *.mkv *.mov)")
        else:
            return

        if file_path:
            self.background_file_input.setText(file_path)
            self.config["background_file"] = file_path
            self.parent.restart_camera()

    def live_update_background_file(self, text):
        self.config["background_file"] = text
        # Only restart if it's a valid path or URL to avoid constant restarting while typing
        if os.path.exists(text) or (self.config.get("background_mode") == "YouTube" and len(text) > 10):
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

    def live_update_web_server(self, state):
        is_enabled = self.web_server_check.isChecked()
        self.config["web_server_enabled"] = is_enabled
        if is_enabled:
            self.parent.start_web_server()
        else:
            self.parent.stop_web_server()

    def setup_widget_tab(self):
        # Use existing layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.widget_layout.addWidget(splitter)

        # Left Panel: Widget List
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("Active Widgets:"))
        self.widget_list = QListWidget()
        self.widget_list.currentItemChanged.connect(self.display_widget_settings)
        left_layout.addWidget(self.widget_list)
        
        # Add/Remove Controls
        controls_group = QGroupBox("Manage Widgets")
        controls_layout = QVBoxLayout(controls_group)
        
        add_row = QHBoxLayout()
        self.widget_combo = QComboBox()
        self.widget_combo.addItems(sorted(WIDGET_CLASSES.keys()))
        add_row.addWidget(self.widget_combo, 1)
        
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_widget)
        add_row.addWidget(self.add_button)
        controls_layout.addLayout(add_row)
        
        btn_row = QHBoxLayout()
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self.rename_widget)
        btn_row.addWidget(self.rename_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_widget)
        btn_row.addWidget(self.remove_button)
        controls_layout.addLayout(btn_row)
        
        left_layout.addWidget(controls_group)
        splitter.addWidget(left_widget)

        # Right Panel: Settings
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        self.settings_title = QLabel("Widget Settings")
        font = self.settings_title.font()
        font.setPointSize(12)
        font.setBold(True)
        self.settings_title.setFont(font)
        right_layout.addWidget(self.settings_title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.widget_settings_area = QWidget()
        self.widget_settings_layout = QVBoxLayout(self.widget_settings_area)
        self.widget_settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.widget_settings_area)
        
        right_layout.addWidget(self.scroll_area)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([250, 550])
        self.refresh_widget_list()

    def refresh_widget_list(self):
        # Save current settings before clearing!
        if self.widget_settings_area.property("current_widget"):
             self.save_current_widget_ui_to_config()
             self.widget_settings_area.setProperty("current_widget", None)

        current = self.widget_list.currentItem().text() if self.widget_list.currentItem() else None
        self.widget_list.clear()
        for name in sorted(self.config.get("widget_positions", {})):
            self.widget_list.addItem(name)
            if name == current:
                items = self.widget_list.findItems(name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.widget_list.setCurrentItem(items[0])
        
        if not self.widget_list.currentItem() and self.widget_list.count() > 0:
             self.widget_list.setCurrentRow(0)

    def add_widget(self):
        widget_type = self.widget_combo.currentText()
        i = 1
        while f"{widget_type}_{i}" in self.config["widget_positions"]:
            i += 1
        widget_name = f"{widget_type}_{i}"

        self.config["widget_positions"][widget_name] = {"x": 0.5, "y": 0.5, "anchor": "center"}
        # Default settings
        defaults = {
            "ical": {"urls": [], "timezone": "US/Central"},
            "rss": {"urls": [], "style": "Normal", "title": "", "article_count": 5},
            "weatherforecast": {"location": "Salem, IL", "style": "Normal"},
            "worldclock": {"timezone": "UTC"},
            "sports": {"configs": [], "style": "Normal", "timezone": "UTC"},
            "stock": {"symbols": ["AAPL", "GOOG"], "api_key": self.config.get("FMP_API_KEY", ""), "style": "Normal"},
            "date": {"format": "%A, %B %d, %Y"},
            "countdown": {"name": "New Event", "datetime": ""},
            "history": {"max_width_chars": 50}
        }
        self.config["widget_settings"][widget_name] = defaults.get(widget_type, {})

        self.parent.widget_manager.load_widgets()
        self.refresh_widget_list()
        items = self.widget_list.findItems(widget_name, Qt.MatchFlag.MatchExactly)
        if items:
            self.widget_list.setCurrentItem(items[0])

    def remove_widget(self):
        current_item = self.widget_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a widget to remove.")
            return
        widget_name = current_item.text()
        reply = QMessageBox.question(self, "Confirm", f"Remove {widget_name}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.config["widget_positions"].pop(widget_name, None)
            self.config["widget_settings"].pop(widget_name, None)
            self.parent.widget_manager.load_widgets()
            self.refresh_widget_list()
            # Clear settings area
            new_container = QWidget()
            new_layout = QVBoxLayout(new_container)
            new_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.scroll_area.setWidget(new_container)
            self.widget_settings_area = new_container
            self.widget_settings_layout = new_layout
            self.settings_title.setText("Widget Settings")

    def rename_widget(self):
        current_item = self.widget_list.currentItem()
        if not current_item:
            return
        old_name = current_item.text()
        new_name, ok = QInputDialog.getText(self, "Rename Widget", "New Name:", text=old_name)
        if ok and new_name and new_name != old_name:
            if new_name in self.config["widget_positions"]:
                QMessageBox.warning(self, "Error", "Name already exists.")
                return
            
            # Save current settings first
            self.save_current_widget_ui_to_config()
            
            # Move config
            self.config["widget_positions"][new_name] = self.config["widget_positions"].pop(old_name)
            self.config["widget_settings"][new_name] = self.config["widget_settings"].pop(old_name)
            
            # Update UI
            current_item.setText(new_name)
            self.widget_settings_area.setProperty("current_widget", new_name)
            self.settings_title.setText(f"Settings: {new_name}")
            
            self.parent.widget_manager.load_widgets()

    def add_list_item(self, list_widget):
        item = QListWidgetItem("New Item")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        list_widget.addItem(item)
        list_widget.setCurrentItem(item)
        list_widget.editItem(item)
        self.save_current_widget_ui_to_config()

    def remove_list_item(self, list_widget):
        list_widget.takeItem(list_widget.currentRow())
        self.save_current_widget_ui_to_config()

    def add_sport_config(self, list_widget, league_input, teams_input):
        l = league_input.text()
        t = teams_input.text()
        if l:
            list_widget.addItem(f"{l}: {t}")
            league_input.clear()
            teams_input.clear()
            self.save_current_widget_ui_to_config()

    def display_widget_settings(self, item):
        if not item:
            return

        new_widget_name = item.text()
        current_widget_name = self.widget_settings_area.property("current_widget")

        # Save previous settings if any
        if current_widget_name and current_widget_name != new_widget_name:
             try:
                 self.save_current_widget_ui_to_config()
             except Exception as e:
                 print(f"Error saving settings for {current_widget_name}: {e}")
        
        # Create new container to replace the old one (clean slate)
        new_container = QWidget()
        new_layout = QVBoxLayout(new_container)
        new_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.widget_settings_area = new_container
        self.widget_settings_layout = new_layout
        self.widget_settings_area.setProperty("current_widget", new_widget_name)
        self.scroll_area.setWidget(new_container)

        self.settings_title.setText(f"Settings: {new_widget_name}")
        
        widget_type = new_widget_name.split("_")[0]
        settings = self.config.get("widget_settings", {}).get(new_widget_name, {})

        # Helper to add rows
        def add_row(label_text, widget):
            self.widget_settings_layout.addWidget(QLabel(label_text))
            self.widget_settings_layout.addWidget(widget)

        # Add per-widget font size slider
        font_slider = QSlider(Qt.Orientation.Horizontal)
        font_slider.setObjectName("font_size_slider")
        font_slider.setRange(50, 200)
        font_slider.setValue(int(settings.get("font_scale", 1.0) * 100))
        font_slider.valueChanged.connect(self.save_current_widget_ui_to_config)
        add_row("Widget Font Scale:", font_slider)

        if widget_type == "time":
            combo = QComboBox(); combo.setObjectName("time_format_combo")
            combo.addItems(["24h", "12h"])
            combo.setCurrentText(settings.get("format", "24h"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Time Format:", combo)
            
        elif widget_type == "date":
            combo = QComboBox(); combo.setObjectName("date_format_combo")
            formats = ["%A, %B %d, %Y", "%a, %b %d, %Y", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%d"]
            combo.addItems(formats)
            combo.setEditable(True)
            combo.setCurrentText(settings.get("format", "%A, %B %d, %Y"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Date Format:", combo)
            
        elif widget_type == "worldclock":
            combo = QComboBox(); combo.setObjectName("tz_combo")
            combo.addItems(pytz.all_timezones)
            combo.setCurrentText(settings.get("timezone", "UTC"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Timezone:", combo)
            
            entry = QLineEdit(); entry.setObjectName("display_name_entry")
            entry.setText(settings.get("display_name", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Display Name (optional):", entry)

        elif widget_type == "weatherforecast":
            entry = QLineEdit(); entry.setObjectName("location_entry")
            entry.setText(settings.get("location", "Salem, IL"))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Location:", entry)
            
            combo = QComboBox(); combo.setObjectName("style_combo")
            combo.addItems(["Normal", "Small", "Large"])
            combo.setCurrentText(settings.get("style", "Normal"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Style:", combo)

        elif widget_type == "ical":
            combo = QComboBox(); combo.setObjectName("tz_combo")
            combo.addItems(pytz.all_timezones)
            combo.setCurrentText(settings.get("timezone", "US/Central"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Timezone:", combo)
            
            list_widget = QListWidget(); list_widget.setObjectName("url_list")
            for url in settings.get("urls", []):
                item = QListWidgetItem(url)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                list_widget.addItem(item)
            list_widget.itemChanged.connect(self.save_current_widget_ui_to_config)
            add_row("iCal URLs:", list_widget)
            
            btn_layout = QHBoxLayout()
            add_btn = QPushButton("+"); add_btn.clicked.connect(lambda: self.add_list_item(list_widget))
            rem_btn = QPushButton("-"); rem_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
            btn_layout.addWidget(add_btn); btn_layout.addWidget(rem_btn)
            self.widget_settings_layout.addLayout(btn_layout)

        elif widget_type == "rss":
            entry = QLineEdit(); entry.setObjectName("title_entry")
            entry.setText(settings.get("title", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Feed Title:", entry)
            
            list_widget = QListWidget(); list_widget.setObjectName("url_list")
            for url in settings.get("urls", []):
                item = QListWidgetItem(url)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                list_widget.addItem(item)
            list_widget.itemChanged.connect(self.save_current_widget_ui_to_config)
            add_row("RSS URLs:", list_widget)
            
            btn_layout = QHBoxLayout()
            add_btn = QPushButton("+"); add_btn.clicked.connect(lambda: self.add_list_item(list_widget))
            rem_btn = QPushButton("-"); rem_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
            btn_layout.addWidget(add_btn); btn_layout.addWidget(rem_btn)
            self.widget_settings_layout.addLayout(btn_layout)
            
            combo = QComboBox(); combo.setObjectName("style_combo")
            combo.addItems(["Normal", "Ticker"])
            combo.setCurrentText(settings.get("style", "Normal"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Style:", combo)
            
            combo = QComboBox(); combo.setObjectName("article_count_combo")
            combo.addItems([str(i) for i in range(1, 21)])
            combo.setCurrentText(str(settings.get("article_count", 5)))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Article Count:", combo)
            
            entry = QLineEdit(); entry.setObjectName("max_width_entry")
            entry.setText(str(settings.get("max_width_chars", 50)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Max Width (chars):", entry)

        elif widget_type == "sports":
            list_widget = QListWidget(); list_widget.setObjectName("sports_config_list")
            for config in settings.get("configs", []):
                teams = ", ".join(config.get("teams", [])) if config.get("teams") else "All"
                list_widget.addItem(f"{config.get('league')}: {teams}")
            list_widget.itemChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Sports Configs:", list_widget)
            
            input_layout = QHBoxLayout()
            league_input = QLineEdit(); league_input.setPlaceholderText("League (e.g. NFL)")
            teams_input = QLineEdit(); teams_input.setPlaceholderText("Teams (comma sep or 'All')")
            add_btn = QPushButton("Add")
            add_btn.clicked.connect(lambda: self.add_sport_config(list_widget, league_input, teams_input))
            input_layout.addWidget(league_input); input_layout.addWidget(teams_input); input_layout.addWidget(add_btn)
            self.widget_settings_layout.addLayout(input_layout)
            
            rem_btn = QPushButton("Remove Selected")
            rem_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
            self.widget_settings_layout.addWidget(rem_btn)

            combo = QComboBox(); combo.setObjectName("tz_combo")
            combo.addItems(pytz.all_timezones)
            combo.setCurrentText(settings.get("timezone", "UTC"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Timezone:", combo)
            
            combo = QComboBox(); combo.setObjectName("style_combo")
            combo.addItems(["Normal", "Ticker"])
            combo.setCurrentText(settings.get("style", "Normal"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Style:", combo)

        elif widget_type == "stock":
            entry = QLineEdit(); entry.setObjectName("api_key_entry")
            entry.setText(settings.get("api_key", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("FMP API Key:", entry)
            
            entry = QLineEdit(); entry.setObjectName("symbols_entry")
            entry.setText(", ".join(settings.get("symbols", [])))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Symbols (comma sep):", entry)
            
            combo = QComboBox(); combo.setObjectName("style_combo")
            combo.addItems(["Normal", "Ticker"])
            combo.setCurrentText(settings.get("style", "Normal"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Style:", combo)

        elif widget_type == "countdown":
            entry = QLineEdit(); entry.setObjectName("countdown_name_entry")
            entry.setText(settings.get("name", "New Event"))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Event Name:", entry)
            
            entry = QLineEdit(); entry.setObjectName("countdown_datetime_entry")
            entry.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
            entry.setText(settings.get("datetime", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Target Date/Time:", entry)

        elif widget_type == "history":
            entry = QLineEdit(); entry.setObjectName("max_width_entry")
            entry.setText(str(settings.get("max_width_chars", 50)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Max Width (chars):", entry)

    def save_current_widget_ui_to_config(self, *args): # Modified to accept *args
        widget_name = self.widget_settings_area.property("current_widget")
        if not widget_name:
            return
        
        if "widget_settings" not in self.config:
            self.config["widget_settings"] = {}
        if widget_name not in self.config["widget_settings"]:
            self.config["widget_settings"][widget_name] = {}
            
        settings = self.config["widget_settings"][widget_name]
        widget_type = widget_name.split("_")[0]

        # Common settings
        slider = self.widget_settings_area.findChild(QSlider, "font_size_slider")
        if slider:
             settings["font_scale"] = slider.value() / 100.0

        if widget_type == "time":
            combo = self.widget_settings_area.findChild(QComboBox, "time_format_combo")
            if combo: settings["format"] = combo.currentText()
        elif widget_type == "date":
            combo = self.widget_settings_area.findChild(QComboBox, "date_format_combo")
            if combo: settings["format"] = combo.currentText()
        elif widget_type == "worldclock":
            combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if combo: settings["timezone"] = combo.currentText()
            entry = self.widget_settings_area.findChild(QLineEdit, "display_name_entry")
            if entry: settings["display_name"] = entry.text()
        elif widget_type == "weatherforecast":
            entry = self.widget_settings_area.findChild(QLineEdit, "location_entry")
            if entry: settings["location"] = entry.text()
            combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if combo: settings["style"] = combo.currentText()
        elif widget_type == "ical":
            combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if combo: settings["timezone"] = combo.currentText()
            list_widget = self.widget_settings_area.findChild(QListWidget, "url_list")
            if list_widget:
                settings["urls"] = [list_widget.item(i).text() for i in range(list_widget.count())]
        elif widget_type == "rss":
            entry = self.widget_settings_area.findChild(QLineEdit, "title_entry")
            if entry: settings["title"] = entry.text()
            list_widget = self.widget_settings_area.findChild(QListWidget, "url_list")
            if list_widget:
                settings["urls"] = [list_widget.item(i).text() for i in range(list_widget.count())]
            combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if combo: settings["style"] = combo.currentText()
            combo = self.widget_settings_area.findChild(QComboBox, "article_count_combo")
            if combo: settings["article_count"] = int(combo.currentText())
            entry = self.widget_settings_area.findChild(QLineEdit, "max_width_entry")
            if entry:
                try: settings["max_width_chars"] = int(entry.text())
                except ValueError: pass
        elif widget_type == "sports":
            list_widget = self.widget_settings_area.findChild(QListWidget, "sports_config_list")
            if list_widget:
                configs = []
                for i in range(list_widget.count()):
                    text = list_widget.item(i).text()
                    parts = text.split(":", 1)
                    if len(parts) == 2:
                        league = parts[0].strip()
                        teams_str = parts[1].strip()
                        teams = [t.strip() for t in teams_str.split(",")] if teams_str.lower() != 'all' and teams_str else []
                        configs.append({"league": league, "teams": teams})
                settings["configs"] = configs
            combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if combo: settings["timezone"] = combo.currentText()
            combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if combo: settings["style"] = combo.currentText()
        elif widget_type == "stock":
            entry = self.widget_settings_area.findChild(QLineEdit, "api_key_entry")
            if entry: settings["api_key"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "symbols_entry")
            if entry: settings["symbols"] = [s.strip() for s in entry.text().split(",")]
            combo = self.widget_settings_area.findChild(QComboBox, "style_combo")
            if combo: settings["style"] = combo.currentText()
        elif widget_type == "countdown":
            entry = self.widget_settings_area.findChild(QLineEdit, "countdown_name_entry")
            if entry: settings["name"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "countdown_datetime_entry")
            if entry: settings["datetime"] = entry.text()
        elif widget_type == "history":
            entry = self.widget_settings_area.findChild(QLineEdit, "max_width_entry")
            if entry:
                try: settings["max_width_chars"] = int(entry.text())
                except ValueError: pass
        
        self.parent.central_widget.update()

    def accept(self):
        self.save_current_widget_ui_to_config()
        self.parent.save_config()
        self.parent.widget_manager.restart_updates() # Restart updates only on save
        self.parent.restart_camera() # Ensure camera/background changes are applied
        super().accept()

    def reject(self):
        self.parent.config.clear()
        self.parent.config.update(self.original_config)
        self.parent.set_fullscreen(self.parent.config.get("fullscreen", True))
        self.parent.restart_camera()
        self.parent.widget_manager.config = self.parent.config
        self.parent.widget_manager.load_widgets()
        if self.original_config.get("web_server_enabled"):
            self.parent.start_web_server()
        else:
            self.parent.stop_web_server()
        super().reject()

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
                child.widget().deleteLater()
            elif child.layout():
                self.clear_layout(child.layout())

class MagicMirrorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.edit_mode = False
        self.drag_data = {"widget": None, "start_pos": None, "start_widget_pos": None}
        self.error_message = ""
        self.config_mutex = QMutex()
        self.web_server = None
        self.preview_image_data = None
        self.preview_image_mutex = QMutex()
        self.load_config()

        self.setWindowTitle("Magic Mirror")
        self.central_widget = VideoLabel(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.central_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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

        # Preview capture timer for thread-safe streaming
        self.preview_capture_timer = QTimer(self)
        self.preview_capture_timer.timeout.connect(self.update_preview_image)
        self.preview_capture_timer.start(100) # Capture at 10 FPS

        # Start Web Server if enabled
        if self.config.get("web_server_enabled", False):
            self.start_web_server()

    @staticmethod
    def detect_available_cameras():
        available = []
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()
        return available

    def is_camera_active(self):
        # Renaming might be too much refactoring, let's just update logic
        mode = self.config.get("background_mode", "Camera")
        if mode == "None": return False
        if mode == "Image": return self.static_image is not None
        if mode in ["Camera", "Video", "YouTube"]: return hasattr(self, "cap") and self.cap is not None and self.cap.isOpened()
        return False

    def load_config(self):
        default_config = {
            "camera_index": 0,
            "background_mode": "Camera",
            "background_file": "",
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
            "background_opacity": 0.0,
            "web_server_enabled": False
        }
        if not os.path.exists(CONFIG_FILE):
            self.config = default_config
        else:
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config = json.load(f)
                for k, v in default_config.items():
                    if k not in self.config:
                        self.config[k] = v
            except (json.JSONDecodeError, IOError):
                self.config = default_config
        self.save_config()

    def save_config(self):
        with QMutexLocker(self.config_mutex):
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self.config, f, indent=4)
            except IOError as e:
                print(f"Error saving config: {e}")

    def setup_camera(self):
        mode = self.config.get("background_mode", "Camera")
        
        if hasattr(self, "cap") and self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None
        self.static_image = None

        if mode == "None":
            self.central_widget.set_pixmap(QPixmap())
            # Stop timer? Or keep it for widgets?
            # The timer calls update_camera_feed which calls central_widget.update() if no camera.
            # So widgets are drawn.
            return

        if mode == "Camera":
            index = self.config.get("camera_index", 0)
            self.cap = cv2.VideoCapture(index)
            if not self.cap.isOpened():
                self.show_error(f"Could not open Camera {index}")
        
        elif mode == "Video":
            path = self.config.get("background_file", "")
            if os.path.exists(path):
                self.cap = cv2.VideoCapture(path)
                if not self.cap.isOpened():
                    self.show_error(f"Could not open video: {path}")
            else:
                self.show_error(f"Video file not found: {path}")

        elif mode == "Image":
            path = self.config.get("background_file", "")
            if os.path.exists(path):
                self.static_image = cv2.imread(path)
                if self.static_image is None:
                    self.show_error(f"Could not load image: {path}")
            else:
                self.show_error(f"Image file not found: {path}")
        
        elif mode == "YouTube":
            url = self.config.get("background_file", "")
            if url:
                try:
                    import yt_dlp
                    ydl_opts = {'format': 'best'}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        video_url = info['url']
                        self.cap = cv2.VideoCapture(video_url)
                        if not self.cap.isOpened():
                            self.show_error(f"Could not open YouTube stream")
                except ImportError:
                    self.show_error("yt_dlp not installed. Run: pip install yt_dlp")
                except Exception as e:
                    self.show_error(f"YouTube Error: {e}")
            else:
                self.show_error("No YouTube URL provided")

        # Ensure timer is running
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
        mode = self.config.get("background_mode", "Camera")
        
        frame = None
        
        if mode == "None":
            self.central_widget.update()
            return

        if mode == "Image":
            if self.static_image is not None:
                frame = self.static_image.copy()
        
        elif mode in ["Camera", "Video", "YouTube"]:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if not ret:
                    if mode in ["Video", "YouTube"]:
                        # Loop video
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self.cap.read()
                        
                        # If still no frame (e.g. YouTube stream ended and seek failed), try re-opening
                        if not ret and mode == "YouTube":
                             self.cap.release()
                             self.setup_camera()
                             if self.cap and self.cap.isOpened():
                                 ret, frame = self.cap.read()
                
                if not ret or frame is None:
                    # Failed to read
                    self.central_widget.update()
                    return
            else:
                self.central_widget.update()
                return

        if frame is not None:
            # Apply mirror/rotation
            if self.config.get("mirror_video", False):
                frame = cv2.flip(frame, 1)
            rot = self.config.get("video_rotation", 0)
            if rot != 0:
                frame = cv2.rotate(frame, [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE][rot - 1])

            h, w, ch = frame.shape
            q_img = QImage(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)
            self.central_widget.set_pixmap(pixmap)
        else:
            self.central_widget.update()

    def update_tickers(self):
        needs_update = False
        with QMutexLocker(self.config_mutex):
            for widget_name, widget in self.widget_manager.widgets.items():
                settings = self.config.get("widget_settings", {}).get(widget_name, {})
                if settings.get("style") == "Ticker":
                    widget.ticker_scroll_x -= 2  # Scroll speed
                    needs_update = True
        
        if needs_update:
            self.central_widget.update()

    def draw_all_widgets(self, painter):
        with QMutexLocker(self.config_mutex):
            self.widget_manager.draw_all(painter, self)
            if self.edit_mode:
                painter.setPen(QColor(0, 255, 0, 200))
                painter.setBrush(QColor(0, 255, 0, 50))
                for name in self.config["widget_positions"]:
                    bbox = self.get_widget_bbox(name)
                    if bbox:
                        painter.drawRect(bbox)

    @staticmethod
    def _get_top_left_for_anchor(anchor, anchor_point, width, height):
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
        # Apply per-widget font scale
        widget_settings = self.config.get("widget_settings", {}).get(widget_name, {})
        widget_scale = widget_settings.get("font_scale", 1.0)
        
        final_scale = widget.params["scale"] * scale_multiplier * widget_scale
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
        
        # Apply per-widget font scale
        widget_scale = settings.get("font_scale", 1.0)
        final_font_scale = font_scale * widget_scale

        font = QFont(self.config.get("font_family", "Helvetica")); font.setPointSizeF(final_font_scale * 10)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        if is_ticker:
            # Ticker drawing logic
            text_width = metrics.horizontalAdvance(text)
            widget = self.widget_manager.widgets.get(widget_name)
            
            # Initialize scroll if needed (first draw)
            if not getattr(widget, "ticker_initialized", False):
                 widget.ticker_scroll_x = self.central_widget.width()
                 widget.ticker_initialized = True

            x = widget.ticker_scroll_x
            y = pos[1] # Use the Y position from the config
            anchor = kwargs.get("anchor", "nw")
            
            strip_height = metrics.height() + 10
            
            # Adjust y to be the vertical center of the strip
            if "n" in anchor:
                y += strip_height / 2
            elif "s" in anchor:
                y -= strip_height / 2
            
            # Draw background strip for ticker
            painter.fillRect(0, int(y - strip_height/2), self.central_widget.width(), int(strip_height), QColor(0, 0, 0, 150))

            baseline_y = y + metrics.ascent() - metrics.height()/2
            
            c_shadow = self.config.get("text_shadow_color", [0, 0, 0])
            painter.setPen(QColor(c_shadow[0], c_shadow[1], c_shadow[2]))
            painter.drawText(QPoint(int(x) + 2, int(baseline_y) + 2), text)
            
            c_text = self.config.get("text_color", [255, 255, 255])
            painter.setPen(QColor(c_text[0], c_text[1], c_text[2]))
            painter.drawText(QPoint(int(x), int(baseline_y)), text)
            
            # Draw the text again if it's scrolling off the screen to create a seamless loop
            gap = 50
            if x + text_width < self.central_widget.width():
                x2 = x + text_width + gap
                painter.setPen(QColor(c_shadow[0], c_shadow[1], c_shadow[2]))
                painter.drawText(QPoint(int(x2) + 2, int(baseline_y) + 2), text)
                painter.setPen(QColor(c_text[0], c_text[1], c_text[2]))
                painter.drawText(QPoint(int(x2), int(baseline_y)), text)
                
                # Reset scroll logic for infinite loop
                if x < -text_width:
                     widget.ticker_scroll_x += (text_width + gap)

        else:
            # Normal multi-line drawing logic
            lines = text.split("\n")
            max_width = max(metrics.horizontalAdvance(line) for line in lines)
            total_height = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5
            anchor = kwargs.get("anchor", "nw")

            x, y = self._get_top_left_for_anchor(anchor, pos, max_width, total_height)

            # Glassmorphism background
            # We draw a rounded rect behind the text block
            bg_rect = QRect(int(x) - 10, int(y) - 5, int(max_width) + 20, int(total_height) + 10)
            painter.setBrush(QBrush(QColor(0, 0, 0, 100))) # Semi-transparent black
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 10, 10)

            for i, line in enumerate(lines):
                line_y = y + i * (metrics.height() + 5)
                line_width = metrics.horizontalAdvance(line)
                line_x = x
                baseline_y = line_y + metrics.ascent()
                
                # Visual Hierarchy: Make the first line bold if it's a multi-line widget
                if i == 0 and len(lines) > 1:
                    font.setBold(True)
                    painter.setFont(font)
                else:
                    font.setBold(False)
                    painter.setFont(font)

                c_shadow = self.config.get("text_shadow_color", [0, 0, 0])
                painter.setPen(QColor(c_shadow[0], c_shadow[1], c_shadow[2]))
                painter.drawText(QPoint(int(line_x) + 2, int(baseline_y) + 2), line)
                
                c_text = self.config.get("text_color", [255, 255, 255])
                painter.setPen(QColor(c_text[0], c_text[1], c_text[2]))
                painter.drawText(QPoint(int(line_x), int(baseline_y)), line)

    def central_widget_mouse_press(self, event):
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            with QMutexLocker(self.config_mutex):
                for name in reversed(list(self.config["widget_positions"])):
                    bbox = self.get_widget_bbox(name)
                    if bbox and bbox.contains(event.position().toPoint()):
                        # Switch anchor to 'nw' to keep top-left corner in spot
                        pos_config = self.config["widget_positions"][name]
                        if pos_config.get("anchor") != "nw":
                            new_x = bbox.x() / self.central_widget.width()
                            new_y = bbox.y() / self.central_widget.height()
                            pos_config["anchor"] = "nw"
                            pos_config["x"] = new_x
                            pos_config["y"] = new_y
                            self.central_widget.update()

                        self.drag_data = {
                            "widget": name,
                            "start_pos": event.position().toPoint(),
                            "start_widget_pos": self.config["widget_positions"][name].copy(),
                        }
                        return

    def central_widget_mouse_move(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.position().toPoint() - self.drag_data["start_pos"]
            if self.central_widget.width() == 0 or self.central_widget.height() == 0:
                return
            
            # Check if start_widget_pos is available
            if self.drag_data.get("start_widget_pos"):
                with QMutexLocker(self.config_mutex):
                    new_x = self.drag_data["start_widget_pos"]["x"] + delta.x() / self.central_widget.width()
                    new_y = self.drag_data["start_widget_pos"]["y"] + delta.y() / self.central_widget.height()
                    self.config["widget_positions"][self.drag_data["widget"]]["x"] = max(0.0, min(1.0, new_x))
                    self.config["widget_positions"][self.drag_data["widget"]]["y"] = max(0.0, min(1.0, new_y))
                self.central_widget.update()

    def central_widget_mouse_release(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.button() == Qt.MouseButton.LeftButton:
            self.drag_data["widget"] = None
            self.save_config()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.set_fullscreen(False)
        elif event.key() == Qt.Key.Key_F11:
            self.set_fullscreen(not self.isFullScreen())
        elif event.key() == Qt.Key.Key_E:
            self.edit_button.toggle()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if self.sender() == self.edit_button:
            dialog.tabs.setCurrentIndex(1)
        dialog.exec()

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        # Removed the popup message
        # QMessageBox.information(self, "Edit Mode", f"Drag and drop is now {'enabled' if self.edit_mode else 'disabled'}.")

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

    def update_preview_image(self):
        if not self.central_widget:
            return
        
        pixmap = self.central_widget.grab()
        byte_array = QBuffer()
        byte_array.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(byte_array, "JPG")
        
        with QMutexLocker(self.preview_image_mutex):
            self.preview_image_data = byte_array.data().data()

    def get_preview_image(self):
        with QMutexLocker(self.preview_image_mutex):
            return self.preview_image_data

    def handle_remote_config_update(self):
        # Called from the web server thread when config is updated
        # We need to signal the main thread to update UI
        # Since we are in a different thread, we should use signals/slots or QTimer.singleShot
        # But for simplicity in this context, we can try to schedule an update.
        # Note: Direct UI updates from another thread are unsafe in Qt.
        # We'll use QTimer.singleShot with a lambda that runs in the main thread (if the timer is created in main thread context? No, timer needs to be thread-safe).
        # Actually, QMetaObject.invokeMethod is the proper way, or signals.
        # Let's use a simple approach: set a flag or just call update() and hope for the best (risky).
        # Better: The web server is running in a thread. We should use a signal.
        # Since I can't easily add a signal to the class definition dynamically without re-instantiating,
        # I will use QTimer.singleShot(0, self.apply_remote_config) which posts an event to the main loop.
        QTimer.singleShot(0, self.apply_remote_config)

    def apply_remote_config(self):
        with QMutexLocker(self.config_mutex):
            self.set_fullscreen(self.config.get("fullscreen", True))
            self.restart_camera()
            self.widget_manager.config = self.config
            self.widget_manager.load_widgets()
        self.central_widget.update()

    def start_web_server(self):
        if self.web_server is None:
            try:
                self.web_server = web_server.start_server(self, port=815)
                print("Web server started on port 815.")
            except Exception as e:
                print(f"Failed to start web server: {e}")
                self.web_server = None

    def stop_web_server(self):
        if self.web_server:
            self.web_server.shutdown()
            self.web_server = None
            print("Web server stopped.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("resources/icon.png"))
    window = MagicMirrorApp()
    window.show()
    sys.exit(app.exec())
