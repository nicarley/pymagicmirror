import sys
import json
import os
import tempfile
import time
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QDialog, QVBoxLayout, QListWidget,
    QPushButton, QLineEdit, QCheckBox, QDialogButtonBox, QWidget, QHBoxLayout,
    QMessageBox, QSizePolicy, QTabWidget, QComboBox, QSlider, QColorDialog,
    QListWidgetItem, QScrollArea, QSplitter, QFrame, QGroupBox, QFormLayout,
    QInputDialog, QFileDialog
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics, QIcon, QFontDatabase, QBrush
from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QBuffer, QIODevice, QMutex, QMutexLocker, Signal
import cv2
import pytz
import certifi
from widget_manager import WidgetManager, WIDGET_CLASSES
import web_server

# ensure requests and feedparser see a CA bundle in a bundled app
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

CONFIG_FILE = "config.json"

THEME_PRESETS = {
    "Default": {
        "background_color": [0, 0, 0],
        "text_color": [255, 255, 255],
        "text_shadow_color": [0, 0, 0],
        "background_opacity": 0.0,
        "text_scale_multiplier": 1.0,
    },
    "Black Background": {
        "background_color": [0, 0, 0],
        "text_color": [240, 240, 240],
        "text_shadow_color": [0, 0, 0],
        "background_opacity": 0.35,
        "text_scale_multiplier": 1.0,
    },
    "High Contrast": {
        "background_color": [0, 0, 0],
        "text_color": [255, 255, 0],
        "text_shadow_color": [0, 0, 0],
        "background_opacity": 0.25,
        "text_scale_multiplier": 1.2,
    },
    "Soft Glass": {
        "background_color": [18, 24, 32],
        "text_color": [235, 245, 255],
        "text_shadow_color": [10, 10, 14],
        "background_opacity": 0.18,
        "text_scale_multiplier": 1.0,
    },
}

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
        bg = self.main_app.config.get("background_color", [0, 0, 0])
        background_color = QColor(bg[0], bg[1], bg[2])
        if self._pixmap.isNull() or not self.main_app.is_camera_active():
            painter.fillRect(self.rect(), background_color)
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

class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Welcome to Magic Mirror")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Quick setup"))

        form = QFormLayout()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEME_PRESETS.keys()))
        form.addRow("Theme:", self.theme_combo)

        self.fullscreen_check = QCheckBox("Start in fullscreen")
        self.fullscreen_check.setChecked(True)
        form.addRow("", self.fullscreen_check)

        self.background_combo = QComboBox()
        self.background_combo.addItems(["None", "Camera", "Image", "Video", "YouTube"])
        form.addRow("Background Mode:", self.background_combo)

        self.feed_combo = QComboBox()
        self.feed_combo.addItems(["15 Minutes", "30 Minutes", "1 Hour", "2 Hours"])
        self.feed_combo.setCurrentText("1 Hour")
        form.addRow("Feed Refresh:", self.feed_combo)

        self.template_combo = QComboBox()
        if self.parent and hasattr(self.parent, "get_available_template_names"):
            self.template_combo.addItems(self.parent.get_available_template_names())
        else:
            self.template_combo.addItems(["Minimal Clock", "Daily Dashboard", "News Wall"])
        form.addRow("Starter Template:", self.template_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self):
        if not self.parent:
            return
        cfg = self.parent.config
        theme = THEME_PRESETS.get(self.theme_combo.currentText(), THEME_PRESETS["Default"])
        for k, v in theme.items():
            cfg[k] = v
        cfg["fullscreen"] = self.fullscreen_check.isChecked()
        cfg["background_mode"] = self.background_combo.currentText()
        cfg["onboarding_completed"] = True
        feed_map = {
            "15 Minutes": 900000,
            "30 Minutes": 1800000,
            "1 Hour": 3600000,
            "2 Hours": 7200000,
        }
        cfg["feed_refresh_interval_ms"] = feed_map.get(self.feed_combo.currentText(), 3600000)
        self.parent.apply_template(self.template_combo.currentText())

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

        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["0°", "90°", "180°", "270°"])
        current_rot = int(self.config.get("video_rotation", 0)) % 4
        self.rotation_combo.setCurrentIndex(current_rot)
        self.rotation_combo.currentIndexChanged.connect(self.live_update_background_rotation)
        cam_layout.addRow("Background Rotation:", self.rotation_combo)
        
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

        layout.addWidget(app_group)

        # Themes Group
        theme_group = QGroupBox("Themes")
        theme_layout = QFormLayout(theme_group)

        colors_layout = QHBoxLayout()
        self.text_color_button = QPushButton("Text Color")
        self.text_color_button.clicked.connect(self.open_text_color_picker)
        colors_layout.addWidget(self.text_color_button)

        self.shadow_color_button = QPushButton("Shadow Color")
        self.shadow_color_button.clicked.connect(self.open_shadow_color_picker)
        colors_layout.addWidget(self.shadow_color_button)

        self.background_color_button = QPushButton("Background Color")
        self.background_color_button.clicked.connect(self.open_background_color_picker)
        colors_layout.addWidget(self.background_color_button)
        theme_layout.addRow("Theme Colors:", colors_layout)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEME_PRESETS.keys()))
        self.theme_combo.currentTextChanged.connect(self.live_update_theme_preset)
        theme_layout.addRow("Theme Preset:", self.theme_combo)

        self.accessibility_combo = QComboBox()
        self.accessibility_combo.addItems([
            "Standard",
            "Large Text",
            "High Contrast",
            "Large + High Contrast",
            "Night Mode",
            "Matrix Mode"
        ])
        self.accessibility_combo.currentTextChanged.connect(self.live_update_accessibility)
        theme_layout.addRow("Readability Preset:", self.accessibility_combo)
        layout.addWidget(theme_group)

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

        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["15", "24", "30", "60"])
        self.fps_combo.setCurrentText(str(self.config.get("camera_fps", 30)))
        self.fps_combo.currentTextChanged.connect(self.live_update_fps)
        sys_layout.addRow("Render FPS:", self.fps_combo)

        self.low_power_check = QCheckBox("Low Power Mode")
        self.low_power_check.setChecked(self.config.get("low_power_mode", False))
        self.low_power_check.stateChanged.connect(self.live_update_low_power)
        sys_layout.addRow("", self.low_power_check)

        self.snap_check = QCheckBox("Snap Widgets to Grid (Edit Mode)")
        self.snap_check.setChecked(self.config.get("snap_to_grid", True))
        self.snap_check.stateChanged.connect(self.live_update_snap_to_grid)
        sys_layout.addRow("", self.snap_check)

        layout.addWidget(sys_group)

        # Profiles / Backup Group
        profile_group = QGroupBox("Profiles")
        profile_layout = QFormLayout(profile_group)
        self.profile_name_input = QLineEdit(self.config.get("active_profile_name", "default"))
        profile_layout.addRow("Profile Name:", self.profile_name_input)
        profile_btns = QHBoxLayout()
        self.save_profile_btn = QPushButton("Save Profile")
        self.save_profile_btn.clicked.connect(self.save_profile)
        self.load_profile_btn = QPushButton("Load Profile")
        self.load_profile_btn.clicked.connect(self.load_profile)
        profile_btns.addWidget(self.save_profile_btn)
        profile_btns.addWidget(self.load_profile_btn)
        profile_layout.addRow("", profile_btns)
        layout.addWidget(profile_group)

        # Diagnostics Group
        diag_group = QGroupBox("Diagnostics")
        diag_layout = QVBoxLayout(diag_group)
        self.diag_label = QLabel()
        self.diag_label.setWordWrap(True)
        diag_layout.addWidget(self.diag_label)
        self.refresh_diag_btn = QPushButton("Refresh Diagnostics")
        self.refresh_diag_btn.clicked.connect(self.refresh_diagnostics)
        diag_layout.addWidget(self.refresh_diag_btn)
        layout.addWidget(diag_group)
        self.refresh_diagnostics()
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

    def open_background_color_picker(self):
        c = self.config.get("background_color", [0, 0, 0])
        current_color = QColor(c[0], c[1], c[2])
        color = QColorDialog.getColor(current_color, self)
        if color.isValid():
            self.config["background_color"] = [color.red(), color.green(), color.blue()]
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

    def live_update_background_rotation(self, index):
        self.config["video_rotation"] = int(index) % 4
        self.parent.central_widget.update()

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

    def live_update_theme_preset(self, name):
        preset = THEME_PRESETS.get(name)
        if not preset:
            return
        for k, v in preset.items():
            self.config[k] = v
        self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.parent.central_widget.update()

    def live_update_accessibility(self, name):
        if name == "Night Mode":
            self.config["text_scale_multiplier"] = 1.0
            self.config["text_color"] = [255, 80, 80]
            self.config["text_shadow_color"] = [0, 0, 0]
            self.config["background_opacity"] = max(0.2, self.config.get("background_opacity", 0.0))
            self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
            self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
            self.parent.central_widget.update()
            return
        if name == "Matrix Mode":
            self.config["text_scale_multiplier"] = 1.0
            self.config["text_color"] = [80, 255, 120]
            self.config["text_shadow_color"] = [0, 0, 0]
            self.config["background_opacity"] = max(0.25, self.config.get("background_opacity", 0.0))
            self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
            self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
            self.parent.central_widget.update()
            return
        if "Large" in name:
            self.config["text_scale_multiplier"] = 1.3
        else:
            self.config["text_scale_multiplier"] = 1.0
        if "High Contrast" in name:
            self.config["text_color"] = [255, 255, 0]
            self.config["text_shadow_color"] = [0, 0, 0]
            self.config["background_opacity"] = max(0.2, self.config.get("background_opacity", 0.0))
        self.opacity_slider.setValue(int(self.config.get("background_opacity", 0.0) * 100))
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.parent.central_widget.update()

    def live_update_fps(self, text):
        try:
            self.config["camera_fps"] = max(1, int(text))
        except ValueError:
            self.config["camera_fps"] = 30
        self.parent.apply_performance_settings()

    def live_update_low_power(self, state):
        self.config["low_power_mode"] = self.low_power_check.isChecked()
        self.parent.apply_performance_settings()

    def live_update_snap_to_grid(self, state):
        self.config["snap_to_grid"] = self.snap_check.isChecked()

    def _profiles_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE)), "profiles")

    def save_profile(self):
        name = (self.profile_name_input.text() or "default").strip()
        safe = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")).strip() or "default"
        os.makedirs(self._profiles_dir(), exist_ok=True)
        path = os.path.join(self._profiles_dir(), f"{safe}.json")
        self.config["active_profile_name"] = safe
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            QMessageBox.information(self, "Profile Saved", f"Saved profile: {safe}")
        except Exception as e:
            QMessageBox.warning(self, "Profile Error", f"Could not save profile:\n{e}")

    def load_profile(self):
        os.makedirs(self._profiles_dir(), exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Load Profile", self._profiles_dir(), "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.parent.config.update(loaded)
            self.parent.widget_manager.config = self.parent.config
            self.parent.widget_manager.load_widgets()
            self.parent.apply_performance_settings()
            self.parent.restart_camera()
            self.parent.central_widget.update()
            QMessageBox.information(self, "Profile Loaded", f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Profile Error", f"Could not load profile:\n{e}")

    def refresh_diagnostics(self):
        widget_count = len(self.parent.widget_manager.widgets)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fps = self.config.get("camera_fps", 30)
        low = self.config.get("low_power_mode", False)
        mode = self.config.get("background_mode", "Camera")
        lines = [
            f"Time: {now_str}",
            f"Widgets Loaded: {widget_count}",
            f"Background Mode: {mode}",
            f"Render FPS: {fps}",
            f"Low Power Mode: {'ON' if low else 'OFF'}",
            f"Web Management: {'ON' if self.config.get('web_server_enabled') else 'OFF'}",
        ]
        self.diag_label.setText("\n".join(lines))

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

        # Widget Actions Group
        actions_group = QGroupBox("Widget Actions")
        actions_layout = QVBoxLayout(actions_group)

        add_row = QHBoxLayout()
        self.widget_combo = QComboBox()
        visible_widget_types = [w for w in sorted(WIDGET_CLASSES.keys()) if w not in {"sunrise"}]
        self.widget_combo.addItems(visible_widget_types)
        add_row.addWidget(self.widget_combo, 1)
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_widget)
        add_row.addWidget(self.add_button)
        actions_layout.addLayout(add_row)

        btn_row = QHBoxLayout()
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_widget)
        btn_row.addWidget(self.remove_button)
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self.rename_widget)
        btn_row.addWidget(self.rename_button)
        actions_layout.addLayout(btn_row)

        controls_layout.addWidget(actions_group)

        self.widget_search = QLineEdit()
        self.widget_search.setPlaceholderText("Search widget types...")
        self.widget_search.textChanged.connect(self.filter_widget_types)
        controls_layout.addWidget(self.widget_search)

        # Templates Group
        template_group = QGroupBox("Templates")
        template_group_layout = QVBoxLayout(template_group)

        template_row = QHBoxLayout()
        self.template_combo = QComboBox()
        self.refresh_template_choices()
        template_row.addWidget(self.template_combo, 1)
        self.apply_template_btn = QPushButton("Apply Template")
        self.apply_template_btn.clicked.connect(self.apply_selected_template)
        template_row.addWidget(self.apply_template_btn)
        template_group_layout.addLayout(template_row)

        save_template_row = QHBoxLayout()
        self.save_template_btn = QPushButton("Save Current as Template")
        self.save_template_btn.clicked.connect(self.save_current_as_template)
        save_template_row.addWidget(self.save_template_btn)
        self.remove_template_btn = QPushButton("Remove Template")
        self.remove_template_btn.clicked.connect(self.remove_selected_template)
        save_template_row.addWidget(self.remove_template_btn)
        template_group_layout.addLayout(save_template_row)

        controls_layout.addWidget(template_group)
        
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

        current = self.widget_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.widget_list.currentItem() else None
        self.widget_list.clear()
        for name in sorted(self.config.get("widget_positions", {})):
            status = self.parent.get_widget_status(name)
            display = f"{name}  [{status}]"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.widget_list.addItem(item)
            if name == current:
                self.widget_list.setCurrentItem(item)
        
        if not self.widget_list.currentItem() and self.widget_list.count() > 0:
             self.widget_list.setCurrentRow(0)

    def add_widget(self):
        widget_type = self.widget_combo.currentText()
        widget_name = self.parent.add_widget_by_type(widget_type)
        if not widget_name:
            return
        self.refresh_widget_list()
        for i in range(self.widget_list.count()):
            it = self.widget_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == widget_name:
                self.widget_list.setCurrentItem(it)
                break

    def filter_widget_types(self, text):
        text = (text or "").strip().lower()
        visible_widget_types = [w for w in sorted(WIDGET_CLASSES.keys()) if w not in {"sunrise"}]
        if text:
            visible_widget_types = [w for w in visible_widget_types if text in w.lower()]
        self.widget_combo.clear()
        self.widget_combo.addItems(visible_widget_types)

    def apply_selected_template(self):
        self.parent.apply_template(self.template_combo.currentText())
        self.refresh_widget_list()

    def refresh_template_choices(self):
        current = self.template_combo.currentText() if hasattr(self, "template_combo") else ""
        self.template_combo.clear()
        self.template_combo.addItems(self.parent.get_available_template_names())
        if current:
            idx = self.template_combo.findText(current)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)

    def save_current_as_template(self):
        name, ok = QInputDialog.getText(self, "Save Template", "Template Name:")
        if not ok or not name.strip():
            return
        safe = self.parent.save_current_as_template(name.strip())
        self.refresh_template_choices()
        idx = self.template_combo.findText(safe)
        if idx >= 0:
            self.template_combo.setCurrentIndex(idx)

    def remove_selected_template(self):
        name = self.template_combo.currentText().strip()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Remove Template",
            f"Remove template '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if not self.parent.remove_saved_template(name):
            QMessageBox.warning(self, "Template", f"Could not remove template: {name}")
            return
        self.refresh_template_choices()

    def remove_widget(self):
        current_item = self.widget_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a widget to remove.")
            return
        widget_name = current_item.data(Qt.ItemDataRole.UserRole)
        if self.parent.remove_widget_by_name(widget_name, confirm=True):
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
        old_name = current_item.data(Qt.ItemDataRole.UserRole)
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
            self.widget_settings_area.setProperty("current_widget", new_name)
            self.settings_title.setText(f"Settings: {new_name}")
            self.parent.widget_manager.load_widgets()
            self.refresh_widget_list()
            for i in range(self.widget_list.count()):
                it = self.widget_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == new_name:
                    self.widget_list.setCurrentItem(it)
                    break

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

    def select_folder_for_entry(self, entry_widget):
        start_dir = entry_widget.text() if entry_widget.text() and os.path.isdir(entry_widget.text()) else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Photo Folder", start_dir)
        if folder:
            entry_widget.setText(folder)
            self.save_current_widget_ui_to_config()

    def select_image_for_entry(self, entry_widget):
        start_path = entry_widget.text() if entry_widget.text() else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Photo",
            start_path,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        if file_path:
            entry_widget.setText(file_path)
            self.save_current_widget_ui_to_config()

    def display_widget_settings(self, item):
        if not item:
            return

        new_widget_name = item.data(Qt.ItemDataRole.UserRole) or item.text()
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

        elif widget_type == "commute":
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
            add_row("iCal URLs (optional):", list_widget)

            btn_layout = QHBoxLayout()
            add_btn = QPushButton("+"); add_btn.clicked.connect(lambda: self.add_list_item(list_widget))
            rem_btn = QPushButton("-"); rem_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
            btn_layout.addWidget(add_btn); btn_layout.addWidget(rem_btn)
            self.widget_settings_layout.addLayout(btn_layout)

            entry = QLineEdit(); entry.setObjectName("commute_minutes_entry")
            entry.setText(str(settings.get("commute_minutes", 25)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Commute Minutes:", entry)

            entry = QLineEdit(); entry.setObjectName("prep_minutes_entry")
            entry.setText(str(settings.get("prep_minutes", 10)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Prep Minutes:", entry)

            entry = QLineEdit(); entry.setObjectName("lookahead_hours_entry")
            entry.setText(str(settings.get("lookahead_hours", 24)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Lookahead Hours:", entry)

        elif widget_type == "dailyagenda":
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
            add_row("iCal URLs (optional):", list_widget)

            btn_layout = QHBoxLayout()
            add_btn = QPushButton("+"); add_btn.clicked.connect(lambda: self.add_list_item(list_widget))
            rem_btn = QPushButton("-"); rem_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
            btn_layout.addWidget(add_btn); btn_layout.addWidget(rem_btn)
            self.widget_settings_layout.addLayout(btn_layout)

            combo = QComboBox(); combo.setObjectName("max_events_combo")
            combo.addItems([str(i) for i in range(1, 21)])
            combo.setCurrentText(str(settings.get("max_events", 6)))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Max Events:", combo)

            combo = QComboBox(); combo.setObjectName("days_ahead_combo")
            combo.addItems([str(i) for i in range(1, 15)])
            combo.setCurrentText(str(settings.get("days_ahead", 3)))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Days Ahead:", combo)

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

        elif widget_type == "photomemories":
            combo = QComboBox(); combo.setObjectName("photo_source_combo")
            combo.addItems(["Folder (Rotate)", "Single Photo"])
            source_mode = settings.get("source_mode", "folder")
            combo.setCurrentText("Single Photo" if source_mode == "single" else "Folder (Rotate)")
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Source:", combo)

            file_row = QHBoxLayout()
            file_entry = QLineEdit(); file_entry.setObjectName("photo_file_entry")
            file_entry.setText(settings.get("single_file", ""))
            file_entry.textChanged.connect(self.save_current_widget_ui_to_config)
            file_row.addWidget(file_entry)
            file_browse_btn = QPushButton("Browse...")
            file_browse_btn.clicked.connect(lambda _=False, e=file_entry: self.select_image_for_entry(e))
            file_row.addWidget(file_browse_btn)
            file_widget = QWidget()
            file_widget.setLayout(file_row)
            add_row("Single Photo:", file_widget)

            folder_row = QHBoxLayout()
            entry = QLineEdit(); entry.setObjectName("photo_folder_entry")
            entry.setText(settings.get("folder", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            folder_row.addWidget(entry)
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda _=False, e=entry: self.select_folder_for_entry(e))
            folder_row.addWidget(browse_btn)
            folder_widget = QWidget()
            folder_widget.setLayout(folder_row)
            add_row("Photo Folder:", folder_widget)

            refresh_combo = QComboBox(); refresh_combo.setObjectName("photo_refresh_combo")
            refresh_combo.addItems([str(i) for i in [1, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440]])
            refresh_combo.setEditable(True)
            refresh_combo.setCurrentText(str(settings.get("refresh_minutes", 60)))
            refresh_combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Folder Refresh (min):", refresh_combo)

            entry = QLineEdit(); entry.setObjectName("photo_name_chars_entry")
            entry.setText(str(settings.get("max_name_chars", 45)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Max Filename Chars:", entry)

            scale_slider = QSlider(Qt.Orientation.Horizontal); scale_slider.setObjectName("photo_scale_slider")
            scale_slider.setRange(10, 100)
            scale_slider.setValue(int(settings.get("image_scale", 0.35) * 100))
            scale_slider.valueChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Image Scale (% width):", scale_slider)

        elif widget_type == "flightboard":
            entry = QLineEdit(); entry.setObjectName("flight_number_entry")
            entry.setText(settings.get("flight_number", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Flight # (e.g. AA100):", entry)

            entry = QLineEdit(); entry.setObjectName("flight_api_key_entry")
            entry.setText(settings.get("api_key", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("AviationStack API Key:", entry)

        elif widget_type == "energyprice":
            combo = QComboBox(); combo.setObjectName("energy_mode_combo")
            combo.addItems(["manual", "url"])
            combo.setCurrentText(settings.get("mode", "manual"))
            combo.currentTextChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Mode:", combo)

            entry = QLineEdit(); entry.setObjectName("energy_manual_price_entry")
            entry.setText(str(settings.get("manual_price", 0.12)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Manual Price:", entry)

            entry = QLineEdit(); entry.setObjectName("energy_currency_entry")
            entry.setText(settings.get("currency_symbol", "$"))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Currency Symbol:", entry)

            entry = QLineEdit(); entry.setObjectName("energy_unit_entry")
            entry.setText(settings.get("unit", "kWh"))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Unit:", entry)

            entry = QLineEdit(); entry.setObjectName("energy_url_entry")
            entry.setText(settings.get("price_url", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Price JSON URL:", entry)

            entry = QLineEdit(); entry.setObjectName("energy_json_key_entry")
            entry.setText(settings.get("json_key", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("JSON Path (dot):", entry)

        elif widget_type == "package":
            entry = QLineEdit(); entry.setObjectName("package_company_entry")
            entry.setText(settings.get("company", "ups"))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Company Slug:", entry)

            entry = QLineEdit(); entry.setObjectName("package_tracking_entry")
            entry.setText(settings.get("tracking_number", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Tracking Number:", entry)

            entry = QLineEdit(); entry.setObjectName("package_api_key_entry")
            entry.setText(settings.get("api_key", ""))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("AfterShip API Key:", entry)

        elif widget_type in ("sunrise", "sunrisesunset"):
            entry = QLineEdit(); entry.setObjectName("sun_lat_entry")
            entry.setText(str(settings.get("lat", 38.624)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Latitude:", entry)

            entry = QLineEdit(); entry.setObjectName("sun_lon_entry")
            entry.setText(str(settings.get("lon", -90.184)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Longitude:", entry)

        elif widget_type == "astronomy":
            entry = QLineEdit(); entry.setObjectName("astro_lat_entry")
            entry.setText(str(settings.get("lat", 38.624)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Latitude:", entry)

            entry = QLineEdit(); entry.setObjectName("astro_lon_entry")
            entry.setText(str(settings.get("lon", -90.184)))
            entry.textChanged.connect(self.save_current_widget_ui_to_config)
            add_row("Longitude:", entry)

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
        elif widget_type == "commute":
            combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if combo: settings["timezone"] = combo.currentText()
            list_widget = self.widget_settings_area.findChild(QListWidget, "url_list")
            if list_widget:
                settings["urls"] = [list_widget.item(i).text() for i in range(list_widget.count())]
            entry = self.widget_settings_area.findChild(QLineEdit, "commute_minutes_entry")
            if entry:
                try: settings["commute_minutes"] = int(entry.text())
                except ValueError: pass
            entry = self.widget_settings_area.findChild(QLineEdit, "prep_minutes_entry")
            if entry:
                try: settings["prep_minutes"] = int(entry.text())
                except ValueError: pass
            entry = self.widget_settings_area.findChild(QLineEdit, "lookahead_hours_entry")
            if entry:
                try: settings["lookahead_hours"] = int(entry.text())
                except ValueError: pass
        elif widget_type == "dailyagenda":
            combo = self.widget_settings_area.findChild(QComboBox, "tz_combo")
            if combo: settings["timezone"] = combo.currentText()
            list_widget = self.widget_settings_area.findChild(QListWidget, "url_list")
            if list_widget:
                settings["urls"] = [list_widget.item(i).text() for i in range(list_widget.count())]
            combo = self.widget_settings_area.findChild(QComboBox, "max_events_combo")
            if combo:
                try: settings["max_events"] = int(combo.currentText())
                except ValueError: pass
            combo = self.widget_settings_area.findChild(QComboBox, "days_ahead_combo")
            if combo:
                try: settings["days_ahead"] = int(combo.currentText())
                except ValueError: pass
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
        elif widget_type == "photomemories":
            combo = self.widget_settings_area.findChild(QComboBox, "photo_source_combo")
            if combo:
                settings["source_mode"] = "single" if combo.currentText() == "Single Photo" else "folder"
            entry = self.widget_settings_area.findChild(QLineEdit, "photo_file_entry")
            if entry:
                settings["single_file"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "photo_folder_entry")
            if entry: settings["folder"] = entry.text()
            combo = self.widget_settings_area.findChild(QComboBox, "photo_refresh_combo")
            if combo:
                try:
                    settings["refresh_minutes"] = int(combo.currentText())
                except ValueError:
                    pass
            entry = self.widget_settings_area.findChild(QLineEdit, "photo_name_chars_entry")
            if entry:
                try: settings["max_name_chars"] = int(entry.text())
                except ValueError: pass
            slider = self.widget_settings_area.findChild(QSlider, "photo_scale_slider")
            if slider:
                settings["image_scale"] = slider.value() / 100.0
            # Apply photo setting changes immediately without waiting for the next timer tick.
            widget = self.parent.widget_manager.widgets.get(widget_name)
            if widget and hasattr(widget, "_update_text"):
                try:
                    widget._update_text()
                except Exception as e:
                    print(f"Photo widget immediate update error: {e}")
        elif widget_type == "flightboard":
            entry = self.widget_settings_area.findChild(QLineEdit, "flight_number_entry")
            if entry: settings["flight_number"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "flight_api_key_entry")
            if entry: settings["api_key"] = entry.text()
        elif widget_type == "energyprice":
            combo = self.widget_settings_area.findChild(QComboBox, "energy_mode_combo")
            if combo: settings["mode"] = combo.currentText()
            entry = self.widget_settings_area.findChild(QLineEdit, "energy_manual_price_entry")
            if entry:
                try: settings["manual_price"] = float(entry.text())
                except ValueError: pass
            entry = self.widget_settings_area.findChild(QLineEdit, "energy_currency_entry")
            if entry: settings["currency_symbol"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "energy_unit_entry")
            if entry: settings["unit"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "energy_url_entry")
            if entry: settings["price_url"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "energy_json_key_entry")
            if entry: settings["json_key"] = entry.text()
        elif widget_type == "package":
            entry = self.widget_settings_area.findChild(QLineEdit, "package_company_entry")
            if entry: settings["company"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "package_tracking_entry")
            if entry: settings["tracking_number"] = entry.text()
            entry = self.widget_settings_area.findChild(QLineEdit, "package_api_key_entry")
            if entry: settings["api_key"] = entry.text()
        elif widget_type in ("sunrise", "sunrisesunset"):
            entry = self.widget_settings_area.findChild(QLineEdit, "sun_lat_entry")
            if entry:
                try: settings["lat"] = float(entry.text())
                except ValueError: pass
            entry = self.widget_settings_area.findChild(QLineEdit, "sun_lon_entry")
            if entry:
                try: settings["lon"] = float(entry.text())
                except ValueError: pass
        elif widget_type == "astronomy":
            entry = self.widget_settings_area.findChild(QLineEdit, "astro_lat_entry")
            if entry:
                try: settings["lat"] = float(entry.text())
                except ValueError: pass
            entry = self.widget_settings_area.findChild(QLineEdit, "astro_lon_entry")
            if entry:
                try: settings["lon"] = float(entry.text())
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
    remote_config_update_requested = Signal()

    def __init__(self):
        super().__init__()
        self.edit_mode = False
        self.drag_data = {"widget": None, "start_pos": None, "start_widget_pos": None}
        self.widget_delete_hitboxes = {}
        self.add_widget_button_rect = None
        self.undo_stack = []
        self.redo_stack = []
        self.alignment_guides = []
        self.error_message = ""
        self.config_mutex = QMutex()
        self.web_server = None
        self.preview_image_data = None
        self.preview_image_mutex = QMutex()
        self.remote_config_update_requested.connect(self.apply_remote_config, Qt.ConnectionType.QueuedConnection)
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
        self.apply_performance_settings()
        
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
        self.show_onboarding_if_needed()

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

    def get_default_widget_settings(self, widget_type):
        defaults = {
            "ical": {"urls": [], "timezone": "US/Central"},
            "commute": {"urls": [], "timezone": "US/Central", "commute_minutes": 25, "prep_minutes": 10, "lookahead_hours": 24},
            "dailyagenda": {"urls": [], "timezone": "US/Central", "max_events": 6, "days_ahead": 3},
            "photomemories": {
                "source_mode": "folder",
                "single_file": "",
                "folder": "",
                "refresh_minutes": 60,
                "max_name_chars": 45,
                "image_scale": 0.35
            },
            "rss": {"urls": [], "style": "Normal", "title": "", "article_count": 5},
            "weatherforecast": {"location": "Salem, IL", "style": "Normal"},
            "worldclock": {"timezone": "UTC"},
            "sports": {"configs": [], "style": "Normal", "timezone": "UTC"},
            "stock": {"symbols": ["AAPL", "GOOG"], "api_key": self.config.get("FMP_API_KEY", ""), "style": "Normal"},
            "date": {"format": "%A, %B %d, %Y"},
            "countdown": {"name": "New Event", "datetime": ""},
            "history": {"max_width_chars": 50},
            "flightboard": {"flight_number": "", "api_key": ""},
            "energyprice": {"mode": "manual", "manual_price": 0.12, "currency_symbol": "$", "unit": "kWh", "price_url": "", "json_key": ""},
            "package": {"company": "ups", "tracking_number": "", "api_key": ""},
            "sunrise": {"lat": 38.624, "lon": -90.184},
            "sunrisesunset": {"lat": 38.624, "lon": -90.184},
            "astronomy": {"lat": 38.624, "lon": -90.184}
        }
        return dict(defaults.get(widget_type, {}))

    def add_widget_by_type(self, widget_type):
        if "widget_positions" not in self.config:
            self.config["widget_positions"] = {}
        if "widget_settings" not in self.config:
            self.config["widget_settings"] = {}
        i = 1
        while f"{widget_type}_{i}" in self.config["widget_positions"]:
            i += 1
        widget_name = f"{widget_type}_{i}"
        self.config["widget_positions"][widget_name] = {"x": 0.5, "y": 0.5, "anchor": "center"}
        self.config["widget_settings"][widget_name] = self.get_default_widget_settings(widget_type)
        self.widget_manager.load_widgets()
        self.central_widget.update()
        self.save_config()
        return widget_name

    def remove_widget_by_name(self, widget_name, confirm=True):
        if widget_name not in self.config.get("widget_positions", {}):
            return False
        if confirm:
            reply = QMessageBox.question(
                self,
                "Confirm",
                f"Remove {widget_name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        self.config["widget_positions"].pop(widget_name, None)
        self.config["widget_settings"].pop(widget_name, None)
        self.widget_manager.load_widgets()
        self.central_widget.update()
        self.save_config()
        return True

    def get_widget_status(self, widget_name):
        settings = self.config.get("widget_settings", {}).get(widget_name, {})
        widget_type = widget_name.split("_")[0]
        required = {
            "ical": ["urls"],
            "rss": ["urls"],
            "commute": ["urls"],
            "dailyagenda": ["urls"],
            "stock": ["api_key"],
            "flightboard": ["flight_number", "api_key"],
            "package": ["company", "tracking_number", "api_key"],
            "photomemories": ["folder"],
        }
        needed = required.get(widget_type, [])
        for key in needed:
            value = settings.get(key)
            if widget_type == "photomemories" and key == "folder":
                if settings.get("source_mode", "folder") == "single":
                    value = settings.get("single_file")
            if isinstance(value, list) and len(value) == 0:
                return "Needs Setup"
            if value in ("", None):
                return "Needs Setup"
        return "OK"

    def get_builtin_template_map(self):
        return {
            "Minimal Clock": ["time", "date"],
            "Daily Dashboard": ["time", "date", "weatherforecast", "dailyagenda", "commute"],
            "News Wall": ["time", "date", "rss"],
        }

    def _templates_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(CONFIG_FILE)), "templates")

    def get_available_template_names(self):
        disabled = set(self.config.get("disabled_builtin_templates", []))
        names = [n for n in self.get_builtin_template_map().keys() if n not in disabled]
        try:
            os.makedirs(self._templates_dir(), exist_ok=True)
            for fn in sorted(os.listdir(self._templates_dir())):
                if fn.lower().endswith(".json"):
                    names.append(os.path.splitext(fn)[0])
        except Exception:
            pass
        return names

    def save_current_as_template(self, template_name):
        safe = "".join(ch for ch in template_name if ch.isalnum() or ch in (" ", "-", "_")).strip() or "Template"
        path = os.path.join(self._templates_dir(), f"{safe}.json")
        os.makedirs(self._templates_dir(), exist_ok=True)
        payload = {
            "widget_positions": self.config.get("widget_positions", {}),
            "widget_settings": self.config.get("widget_settings", {}),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return safe

    def remove_saved_template(self, template_name):
        # Built-ins are removable from the picker by marking them disabled.
        if template_name in self.get_builtin_template_map():
            disabled = set(self.config.get("disabled_builtin_templates", []))
            disabled.add(template_name)
            self.config["disabled_builtin_templates"] = sorted(disabled)
            self.save_config()
            return True
        safe = "".join(ch for ch in template_name if ch.isalnum() or ch in (" ", "-", "_")).strip()
        if not safe:
            return False
        path = os.path.join(self._templates_dir(), f"{safe}.json")
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
            return True
        except Exception:
            return False

    def apply_template(self, template_name):
        # Built-in templates are additive safety presets; custom templates restore exact saved set.
        template_map = self.get_builtin_template_map()
        if template_name in self.config.get("disabled_builtin_templates", []):
            return
        if template_name not in template_map:
            path = os.path.join(self._templates_dir(), f"{template_name}.json")
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.config["widget_positions"] = data.get("widget_positions", {})
                    self.config["widget_settings"] = data.get("widget_settings", {})
                    self.widget_manager.load_widgets()
                    self.central_widget.update()
                    self.save_config()
                    return
                except Exception as e:
                    QMessageBox.warning(self, "Template Error", f"Could not load template '{template_name}':\n{e}")
                    return

        for idx, wtype in enumerate(template_map.get(template_name, []), start=1):
            existing = [name for name in self.config.get("widget_positions", {}) if name.startswith(f"{wtype}_")]
            if existing:
                continue
            name = self.add_widget_by_type(wtype)
            if name:
                col = (idx - 1) % 3
                row = (idx - 1) // 3
                self.config["widget_positions"][name]["x"] = 0.2 + col * 0.3
                self.config["widget_positions"][name]["y"] = 0.2 + row * 0.25
                self.config["widget_positions"][name]["anchor"] = "nw"
        self.widget_manager.load_widgets()
        self.central_widget.update()
        self.save_config()

    def show_onboarding_if_needed(self):
        if self.config.get("onboarding_completed", False):
            return
        dialog = OnboardingDialog(self)
        if dialog.exec():
            dialog.apply()
            self.apply_performance_settings()
            self.widget_manager.load_widgets()
            self.restart_camera()
            self.set_fullscreen(self.config.get("fullscreen", True))
            self.save_config()

    def apply_performance_settings(self):
        fps = int(self.config.get("camera_fps", 30))
        if self.config.get("low_power_mode", False):
            fps = min(fps, 15)
            self.config["feed_refresh_interval_ms"] = max(3600000, int(self.config.get("feed_refresh_interval_ms", 3600000)))
        interval_ms = max(1, int(1000 / max(1, fps)))
        if hasattr(self, "timer") and self.timer:
            self.timer.start(interval_ms)
        if hasattr(self, "preview_capture_timer") and self.preview_capture_timer:
            self.preview_capture_timer.start(200 if self.config.get("low_power_mode", False) else 100)
        if hasattr(self, "ticker_timer") and self.ticker_timer:
            self.ticker_timer.start(50 if self.config.get("low_power_mode", False) else 30)

    def push_undo_snapshot(self):
        snapshot = json.loads(json.dumps(self.config.get("widget_positions", {})))
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 100:
            self.undo_stack = self.undo_stack[-100:]
        self.redo_stack.clear()

    def undo_layout_change(self):
        if not self.undo_stack:
            return
        current = json.loads(json.dumps(self.config.get("widget_positions", {})))
        self.redo_stack.append(current)
        self.config["widget_positions"] = self.undo_stack.pop()
        self.widget_manager.load_widgets()
        self.central_widget.update()
        self.save_config()

    def redo_layout_change(self):
        if not self.redo_stack:
            return
        current = json.loads(json.dumps(self.config.get("widget_positions", {})))
        self.undo_stack.append(current)
        self.config["widget_positions"] = self.redo_stack.pop()
        self.widget_manager.load_widgets()
        self.central_widget.update()
        self.save_config()

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
            "background_color": [0, 0, 0],
            "FMP_API_KEY": "YOUR_FMP_API_KEY",
            "font_family": "Helvetica",
            "background_opacity": 0.0,
            "web_server_enabled": False,
            "camera_fps": 30,
            "low_power_mode": False,
            "snap_to_grid": True,
            "grid_size": 0.01,
            "onboarding_completed": False,
            "active_profile_name": "default",
            "disabled_builtin_templates": []
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
        try:
            current_grid = float(self.config.get("grid_size", 0.01))
        except (TypeError, ValueError):
            current_grid = 0.01
        # keep snapping fine-grained by default
        if current_grid > 0.01:
            self.config["grid_size"] = 0.01
        self.save_config()

    def save_config(self):
        with QMutexLocker(self.config_mutex):
            tmp_path = None
            try:
                config_dir = os.path.dirname(os.path.abspath(CONFIG_FILE)) or "."
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=config_dir,
                    prefix="config.",
                    suffix=".tmp",
                    delete=False
                ) as tmp:
                    tmp_path = tmp.name
                    json.dump(self.config, tmp, indent=4)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_path, CONFIG_FILE)
            except IOError as e:
                print(f"Error saving config: {e}")
            except OSError as e:
                print(f"Error saving config: {e}")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

    def setup_camera(self):
        mode = self.config.get("background_mode", "Camera")
        had_error = False
        
        if hasattr(self, "cap") and self.cap and self.cap.isOpened():
            self.cap.release()
        self.cap = None
        self.static_image = None

        if mode == "None":
            self.central_widget.set_pixmap(QPixmap())
            # Stop timer? Or keep it for widgets?
            # The timer calls update_camera_feed which calls central_widget.update() if no camera.
            # So widgets are drawn.
            self.clear_error_message()
            return

        if mode == "Camera":
            index = self.config.get("camera_index", 0)
            self.cap = cv2.VideoCapture(index)
            if not self.cap.isOpened():
                self.show_error(f"Could not open Camera {index}")
                had_error = True
        
        elif mode == "Video":
            path = self.config.get("background_file", "")
            if os.path.exists(path):
                self.cap = cv2.VideoCapture(path)
                if not self.cap.isOpened():
                    self.show_error(f"Could not open video: {path}")
                    had_error = True
            else:
                self.show_error(f"Video file not found: {path}")
                had_error = True

        elif mode == "Image":
            path = self.config.get("background_file", "")
            if os.path.exists(path):
                self.static_image = cv2.imread(path)
                if self.static_image is None:
                    self.show_error(f"Could not load image: {path}")
                    had_error = True
            else:
                self.show_error(f"Image file not found: {path}")
                had_error = True
        
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
                            had_error = True
                except ImportError:
                    self.show_error("yt_dlp not installed. Run: pip install yt_dlp")
                    had_error = True
                except Exception as e:
                    self.show_error(f"YouTube Error: {e}")
                    had_error = True
            else:
                self.show_error("No YouTube URL provided")
                had_error = True

        # Ensure timer is running
        if not hasattr(self, "timer") or not self.timer.isActive():
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_camera_feed)
            fps = max(1, int(self.config.get("camera_fps", 30)))
            self.timer.start(max(1, int(1000 / fps)))
            
        if not had_error:
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
            self.widget_delete_hitboxes = {}
            self.add_widget_button_rect = None
            self.widget_manager.draw_all(painter, self)
            if self.edit_mode:
                painter.setPen(QColor(0, 255, 0, 200))
                painter.setBrush(QColor(0, 255, 0, 50))
                for guide in self.alignment_guides:
                    painter.setPen(QColor(255, 220, 0, 180))
                    if guide.get("axis") == "x":
                        x = int(guide["value"])
                        painter.drawLine(x, 0, x, self.central_widget.height())
                    else:
                        y = int(guide["value"])
                        painter.drawLine(0, y, self.central_widget.width(), y)
                painter.setPen(QColor(0, 255, 0, 200))
                for name in self.config["widget_positions"]:
                    bbox = self.get_widget_bbox(name)
                    if bbox:
                        painter.drawRect(bbox)
                        btn_size = 20
                        btn_rect = QRect(bbox.right() - btn_size + 1, bbox.top(), btn_size, btn_size)
                        self.widget_delete_hitboxes[name] = btn_rect
                        painter.setBrush(QColor(220, 40, 40, 220))
                        painter.setPen(QColor(255, 255, 255))
                        painter.drawRect(btn_rect)
                        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "X")

                plus_size = 30
                plus_rect = QRect(self.central_widget.width() - plus_size - 15, 65, plus_size, plus_size)
                self.add_widget_button_rect = plus_rect
                painter.setBrush(QColor(40, 160, 60, 220))
                painter.setPen(QColor(255, 255, 255))
                painter.drawEllipse(plus_rect)
                painter.drawText(plus_rect, Qt.AlignmentFlag.AlignCenter, "+")

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
        widget_type = widget_name.split("_")[0]

        if widget_type in ("photomemories",):
            settings = self.config.get("widget_settings", {}).get(widget_name, {})
            try:
                default_scale = 0.35 if widget_type == "photomemories" else 0.3
                scale = float(settings.get("image_scale", default_scale))
            except (TypeError, ValueError):
                scale = default_scale
            scale = max(0.1, min(1.0, scale))

            base_width = max(120, int(self.central_widget.width() * scale))
            path = getattr(widget, "current_photo_path", "")
            pixmap = QPixmap(path) if path and os.path.exists(path) else QPixmap()

            if not pixmap.isNull() and pixmap.width() > 0:
                text_width = base_width
                text_height = int(base_width * pixmap.height() / pixmap.width())
            else:
                text_width = base_width
                text_height = int(base_width * 0.6)

            max_h = int(self.central_widget.height() * 0.8)
            if text_height > max_h:
                ratio = max_h / max(1, text_height)
                text_height = max_h
                text_width = int(text_width * ratio)

            pos = self.config["widget_positions"][widget_name]
            anchor_x = int(pos["x"] * self.central_widget.width())
            anchor_y = int(pos["y"] * self.central_widget.height())
            anchor = pos.get("anchor", "nw")
            x0, y0 = self._get_top_left_for_anchor(anchor, (anchor_x, anchor_y), text_width, text_height)
            return QRect(int(x0), int(y0), int(text_width) + 2, int(text_height) + 2)

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

    def draw_photo_widget(self, painter, widget_name, photo_path, pos, anchor):
        if not photo_path or not os.path.exists(photo_path):
            self.draw_text(painter, "Photo unavailable", pos, 0.9, anchor=anchor, widget_name=widget_name)
            return

        settings = self.config.get("widget_settings", {}).get(widget_name, {})
        try:
            scale = float(settings.get("image_scale", 0.35))
        except (TypeError, ValueError):
            scale = 0.35
        scale = max(0.1, min(1.0, scale))

        pixmap = QPixmap(photo_path)
        if pixmap.isNull() or pixmap.width() <= 0:
            self.draw_text(painter, "Photo unavailable", pos, 0.9, anchor=anchor, widget_name=widget_name)
            return

        target_w = max(120, int(self.central_widget.width() * scale))
        target_h = int(target_w * pixmap.height() / pixmap.width())
        max_h = int(self.central_widget.height() * 0.8)
        if target_h > max_h:
            ratio = max_h / max(1, target_h)
            target_h = max_h
            target_w = int(target_w * ratio)

        x, y = self._get_top_left_for_anchor(anchor, pos, target_w, target_h)
        rect = QRect(int(x), int(y), int(target_w), int(target_h))
        scaled = pixmap.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(rect, scaled)

    def central_widget_mouse_press(self, event):
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            click_point = event.position().toPoint()
            if self.add_widget_button_rect and self.add_widget_button_rect.contains(click_point):
                self.add_widget_from_edit_overlay()
                return
            for name, rect in list(self.widget_delete_hitboxes.items()):
                if rect.contains(click_point):
                    self.remove_widget_by_name(name, confirm=True)
                    self.widget_delete_hitboxes = {}
                    self.central_widget.update()
                    return
            with QMutexLocker(self.config_mutex):
                for name in reversed(list(self.config["widget_positions"])):
                    bbox = self.get_widget_bbox(name)
                    if bbox and bbox.contains(click_point):
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
                        self.push_undo_snapshot()
                        return

    def add_widget_from_edit_overlay(self):
        widget_types = [w for w in sorted(WIDGET_CLASSES.keys()) if w not in {"sunrise"}]
        widget_type, ok = QInputDialog.getItem(
            self,
            "Add Widget",
            "Widget Type:",
            widget_types,
            0,
            False
        )
        if not ok or not widget_type:
            return
        widget_name = self.add_widget_by_type(widget_type)
        self.open_settings_dialog(widget_name=widget_name, widget_tab=True)

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
                    if self.config.get("snap_to_grid", True):
                        g = float(self.config.get("grid_size", 0.05))
                        if g > 0:
                            new_x = round(new_x / g) * g
                            new_y = round(new_y / g) * g
                    self.config["widget_positions"][self.drag_data["widget"]]["x"] = max(0.0, min(1.0, new_x))
                    self.config["widget_positions"][self.drag_data["widget"]]["y"] = max(0.0, min(1.0, new_y))
                    self.alignment_guides = []
                    center_tol = 0.02
                    if abs(new_x - 0.5) <= center_tol:
                        self.alignment_guides.append({"axis": "x", "value": self.central_widget.width() * 0.5})
                    if abs(new_y - 0.5) <= center_tol:
                        self.alignment_guides.append({"axis": "y", "value": self.central_widget.height() * 0.5})
                self.central_widget.update()

    def central_widget_mouse_release(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.button() == Qt.MouseButton.LeftButton:
            self.drag_data["widget"] = None
            self.alignment_guides = []
            self.save_config()

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z:
            self.undo_layout_change()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Y:
            self.redo_layout_change()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.set_fullscreen(False)
        elif event.key() == Qt.Key.Key_F11:
            self.set_fullscreen(not self.isFullScreen())
        elif event.key() == Qt.Key.Key_E:
            self.edit_button.toggle()

    def open_settings_dialog(self, widget_name=None, widget_tab=False):
        dialog = SettingsDialog(self)
        if widget_tab or self.sender() == self.edit_button:
            dialog.tabs.setCurrentIndex(1)
        if widget_name:
            dialog.refresh_widget_list()
            for i in range(dialog.widget_list.count()):
                it = dialog.widget_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == widget_name:
                    dialog.widget_list.setCurrentItem(it)
                    break
        dialog.exec()

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        if not self.edit_mode:
            self.widget_delete_hitboxes = {}
            self.add_widget_button_rect = None
        self.central_widget.update()
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
        # Called from the web server thread; queued signal marshals work to the UI thread.
        self.remote_config_update_requested.emit()

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

    def closeEvent(self, event):
        self.stop_web_server()

        if hasattr(self, "ticker_timer") and self.ticker_timer.isActive():
            self.ticker_timer.stop()
        if hasattr(self, "preview_capture_timer") and self.preview_capture_timer.isActive():
            self.preview_capture_timer.stop()
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, "cap") and self.cap and self.cap.isOpened():
            self.cap.release()

        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("resources/icon.png"))
    window = MagicMirrorApp()
    window.show()
    sys.exit(app.exec())
