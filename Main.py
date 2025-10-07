
import sys
import json
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QDialog, QVBoxLayout, QListWidget, 
    QPushButton, QLineEdit, QCheckBox, QDialogButtonBox, QWidget, QHBoxLayout, 
    QMessageBox, QSizePolicy, QTabWidget, QComboBox, QInputDialog, QSlider
)
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QFontMetrics
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
import cv2
from widget_manager import WidgetManager, WIDGET_CLASSES

CONFIG_FILE = "config.json"

class VideoLabel(QLabel):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self._pixmap = QPixmap()

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()  # Schedules a repaint

    def paintEvent(self, event):
        painter = QPainter(self)
        if self._pixmap.isNull():
            painter.fillRect(self.rect(), Qt.black)
            self.main_app.draw_all_widgets(painter)
            return

        scaled_pixmap = self._pixmap.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(self.rect(), scaled_pixmap)
        self.main_app.draw_all_widgets(painter)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings & Widgets")
        self.parent = parent
        self.original_config = json.loads(json.dumps(parent.config)) # For cancel
        self.config = parent.config # Work on the live config
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
        # Webcam Selector
        self.general_layout.addWidget(QLabel("Webcam Device:"))
        self.camera_combo = QComboBox()
        self.available_cameras = self.parent.detect_available_cameras()
        self.camera_combo.addItems([f"Camera {i}" for i in self.available_cameras])
        current_cam_index = self.config.get("camera_index", 0)
        if current_cam_index in self.available_cameras:
            self.camera_combo.setCurrentIndex(self.available_cameras.index(current_cam_index))
        self.camera_combo.currentIndexChanged.connect(self.live_update_camera)
        self.general_layout.addWidget(self.camera_combo)

        self.general_layout.addWidget(QLabel("Weather Location (e.g., 'City, ST' or 'City, Country'):"))
        self.location_entry = QLineEdit(self.config.get("weather_location", ""))
        self.location_entry.textChanged.connect(self.live_update_location)
        self.general_layout.addWidget(self.location_entry)

        self.mirror_video_check = QCheckBox("Mirror Video")
        self.mirror_video_check.setChecked(self.config.get("mirror_video", False))
        self.mirror_video_check.stateChanged.connect(self.live_update_mirror_video)
        self.general_layout.addWidget(self.mirror_video_check)

        self.rotate_button = QPushButton("Rotate Video 90°")
        self.rotate_button.clicked.connect(lambda: self.parent.rotate_video())
        self.general_layout.addWidget(self.rotate_button)

        self.general_layout.addWidget(QLabel("Global Text Size:"))
        self.text_size_slider = QSlider(Qt.Horizontal)
        self.text_size_slider.setRange(50, 200)
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.text_size_slider.valueChanged.connect(self.live_update_text_size)
        self.general_layout.addWidget(self.text_size_slider)

        self.general_layout.addWidget(QLabel("Feed Refresh Interval:"))
        self.refresh_interval_combo = QComboBox()
        self.refresh_intervals = {
            "15 Minutes": 900000, "30 Minutes": 1800000, "1 Hour": 3600000,
            "2 Hours": 7200000, "6 Hours": 21600000, "12 Hours": 43200000, "24 Hours": 86400000
        }
        self.refresh_interval_combo.addItems(self.refresh_intervals.keys())
        current_interval_ms = self.config.get("feed_refresh_interval_ms", 3600000)
        for name, ms in self.refresh_intervals.items():
            if ms == current_interval_ms: self.refresh_interval_combo.setCurrentText(name)
        self.refresh_interval_combo.currentTextChanged.connect(self.live_update_refresh_interval)
        self.general_layout.addWidget(self.refresh_interval_combo)

    # --- Live Update Handlers ---
    def live_update_camera(self, index):
        selected_camera_index = self.available_cameras[index]
        if self.config.get("camera_index") != selected_camera_index:
            self.config["camera_index"] = selected_camera_index
            self.parent.restart_camera()

    def live_update_location(self, text):
        self.config["weather_location"] = text
        self.parent.widget_manager.restart_updates()

    def live_update_mirror_video(self, state):
        self.config["mirror_video"] = self.mirror_video_check.isChecked()

    def live_update_text_size(self, value):
        self.config["text_scale_multiplier"] = value / 100.0

    def live_update_refresh_interval(self, text):
        self.config["feed_refresh_interval_ms"] = self.refresh_intervals[text]
        self.parent.widget_manager.restart_updates()

    def setup_widget_tab(self):
        # ... (widget tab setup remains the same)
        pass

    def accept(self):
        self.save_current_widget_ui_to_config()
        self.parent.save_config()
        super().accept()

    def reject(self):
        self.parent.config.clear()
        self.parent.config.update(self.original_config)
        self.parent.restart_camera()
        self.parent.widget_manager.config = self.parent.config
        self.parent.widget_manager.load_widgets()
        super().reject()

class MagicMirrorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.edit_mode = False
        self.drag_data = {"widget": None, "start_pos": None, "start_widget_pos": None}
        self.load_config()

        self.setWindowTitle("Magic Mirror")
        self.central_widget = VideoLabel(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setAlignment(Qt.AlignCenter)
        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.central_widget.setMouseTracking(True)
        self.central_widget.mousePressEvent = self.central_widget_mouse_press
        self.central_widget.mouseMoveEvent = self.central_widget_mouse_move
        self.central_widget.mouseReleaseEvent = self.central_widget_mouse_release

        self.widget_manager = WidgetManager(self, self.config)
        self.setup_camera()
        self.setup_overlay()
        self.showFullScreen()

    def detect_available_cameras(self):
        available_cameras = []
        for i in range(10):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available_cameras.append(i)
                cap.release()
        return available_cameras

    def load_config(self):
        default_config = {
            "camera_index": 0,
            "weather_location": "New York, US",
            "video_rotation": 0, 
            "mirror_video": False, 
            "text_scale_multiplier": 1.0,
            "feed_refresh_interval_ms": 3600000, # 1 hour
            "widget_positions": { # ... default widgets ... 
            },
            "widget_settings": { # ... default settings ... 
            }
        }
        if not os.path.exists(CONFIG_FILE):
            self.config = default_config
        else:
            with open(CONFIG_FILE, 'r') as f: self.config = json.load(f)
            if "news_api_key" in self.config: del self.config["news_api_key"]
            for key, value in default_config.items():
                if key not in self.config: self.config[key] = value
        self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f: json.dump(self.config, f, indent=4)

    def setup_camera(self, camera_index=None):
        if camera_index is None:
            camera_index = self.config.get("camera_index", 0)
        
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()

        self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.show_error(f"Error: Could not open camera {camera_index}.")
            return
        
        if not hasattr(self, 'timer'):
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_camera_feed)
            self.timer.start(30)

    def restart_camera(self):
        self.setup_camera()

    def rotate_video(self):
        self.config["video_rotation"] = (self.config.get("video_rotation", 0) + 1) % 4

    # ... (rest of the app, drawing, mouse events, etc. remain largely the same) ...
    def setup_overlay(self):
        self.settings_button = QPushButton("⚙️", self)
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.settings_button.setStyleSheet("background-color: rgba(0,0,0,0.5); color: white; border: none; font-size: 24px; padding: 5px;")
        self.settings_button.setFixedSize(40, 40)

        self.edit_button = QPushButton("E", self)
        self.edit_button.setCheckable(True)
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        self.edit_button.setStyleSheet("background-color: rgba(0,0,0,0.5); color: white; border: 1px solid white; font-size: 18px;")
        self.edit_button.setFixedSize(40, 40)

    def update_camera_feed(self):
        ret, frame = self.cap.read()
        if not ret:
            self.central_widget.update()
            return

        if self.config.get("mirror_video", False): frame = cv2.flip(frame, 1)
        rot = self.config.get("video_rotation", 0)
        if rot != 0: frame = cv2.rotate(frame, [cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE][rot - 1])

        h, w, ch = frame.shape
        q_img = QImage(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        self.central_widget.set_pixmap(pixmap)

    def draw_all_widgets(self, painter):
        self.widget_manager.draw_all(painter)
        if self.edit_mode:
            painter.setPen(QColor(0, 255, 0, 200))
            painter.setBrush(QColor(0, 255, 0, 50))
            for name in self.config["widget_positions"]:
                bbox = self.get_widget_bbox(name)
                if bbox: painter.drawRect(bbox)

    def _get_top_left_for_anchor(self, anchor, anchor_point, width, height):
        x, y = anchor_point
        if 'e' in anchor:
            x -= width
        elif 'w' not in anchor:  # Center horizontal
            x -= width / 2
        if 's' in anchor:
            y -= height
        elif 'n' not in anchor:  # Center vertical
            y -= height / 2
        return x, y

    def get_widget_bbox(self, widget_name):
        widget = self.widget_manager.widgets.get(widget_name)
        if not widget: return None

        scale_multiplier = self.config.get("text_scale_multiplier", 1.0)
        final_scale = widget.params['scale'] * scale_multiplier

        font = QFont("Helvetica"); font.setPointSizeF(final_scale * 10)
        metrics = QFontMetrics(font)
        text_content = widget.text if hasattr(widget, 'text') and widget.text else f"({widget_name})"
        lines = text_content.split('\n')
        if not lines: return None

        text_width = max(metrics.horizontalAdvance(line) for line in lines) if lines else 0
        text_height = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5

        pos = self.config["widget_positions"][widget_name]
        anchor_x = int(pos['x'] * self.central_widget.width())
        anchor_y = int(pos['y'] * self.central_widget.height())
        anchor = pos.get('anchor', 'nw')

        x0, y0 = self._get_top_left_for_anchor(anchor, (anchor_x, anchor_y), text_width, text_height)
        return QRect(int(x0), int(y0), int(text_width) + 2, int(text_height) + 2)

    def draw_text(self, painter, text, pos, font_scale, color, **kwargs):
        if not text: return
        font = QFont("Helvetica"); font.setPointSizeF(font_scale * 10)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        lines = text.split('\n')
        
        max_width = max(metrics.horizontalAdvance(line) for line in lines)
        total_height = sum(metrics.height() for _ in lines) + (len(lines) - 1) * 5
        anchor = kwargs.get('anchor', 'nw')
        
        x, y = self._get_top_left_for_anchor(anchor, pos, max_width, total_height)

        for i, line in enumerate(lines):
            line_y = y + i * (metrics.height() + 5)
            line_width = metrics.horizontalAdvance(line)
            line_x = x
            if 'w' not in anchor and 'e' not in anchor: # Center-align line
                 line_x = x + (max_width - line_width) / 2

            baseline_y = line_y + metrics.ascent()

            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QPoint(int(line_x) + 2, int(baseline_y) + 2), line)
            
            painter.setPen(QColor(*color))
            painter.drawText(QPoint(int(line_x), int(baseline_y)), line)

    def central_widget_mouse_press(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            for name in reversed(list(self.config["widget_positions"])):
                bbox = self.get_widget_bbox(name)
                if bbox and bbox.contains(event.position().toPoint()):
                    self.drag_data = {"widget": name, "start_pos": event.position().toPoint(), "start_widget_pos": self.config["widget_positions"][name].copy()}
                    return

    def central_widget_mouse_move(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.buttons() & Qt.LeftButton:
            delta = event.position().toPoint() - self.drag_data['start_pos']
            if self.central_widget.width() == 0 or self.central_widget.height() == 0: return
            new_x = self.drag_data['start_widget_pos']['x'] + delta.x() / self.central_widget.width()
            new_y = self.drag_data['start_widget_pos']['y'] + delta.y() / self.central_widget.height()
            self.config["widget_positions"][self.drag_data['widget']]['x'] = max(0.0, min(1.0, new_x))
            self.config["widget_positions"][self.drag_data['widget']]['y'] = max(0.0, min(1.0, new_y))
            self.central_widget.update()

    def central_widget_mouse_release(self, event):
        if self.edit_mode and self.drag_data["widget"] and event.button() == Qt.LeftButton:
            self.drag_data["widget"] = None
            self.save_config()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen(): self.showNormal()
        elif event.key() == Qt.Key_F11: self.showFullScreen() if not self.isFullScreen() else self.showNormal()
        elif event.key() == Qt.Key_E: self.edit_button.toggle()

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        if self.sender() == self.edit_button:
             dialog.tabs.setCurrentIndex(1)
        dialog.exec()

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        QMessageBox.information(self, "Edit Mode", f"Drag-and-drop is now {'enabled' if self.edit_mode else 'disabled'}.")

    def resizeEvent(self, event):
        self.settings_button.move(self.width() - self.settings_button.width() - 10, 10)
        self.edit_button.move(self.width() - self.edit_button.width() - 60, 10)
        super().resizeEvent(event)

    def show_error(self, message):
        self.central_widget.setPixmap(QPixmap())
        error_label = QLabel(message, self)
        error_label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(error_label)

    def after(self, ms, func): QTimer.singleShot(ms, func)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MagicMirrorApp()
    window.show()
    sys.exit(app.exec())
