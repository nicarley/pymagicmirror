
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

        scaled_pixmap = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled_pixmap.width()) / 2
        y = (self.height() - scaled_pixmap.height()) / 2
        
        painter.drawPixmap(x, y, scaled_pixmap)
        self.main_app.draw_all_widgets(painter)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings & Widgets")
        self.config = json.loads(json.dumps(parent.config))  # Deep copy for editing
        self.parent = parent
        self.setMinimumSize(500, 400)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # General Settings Tab
        self.general_tab = QWidget()
        self.general_layout = QVBoxLayout(self.general_tab)
        self.tabs.addTab(self.general_tab, "General")
        self.setup_general_tab()

        # Widget Management Tab
        self.widget_tab = QWidget()
        self.widget_layout = QVBoxLayout(self.widget_tab)
        self.tabs.addTab(self.widget_tab, "Widgets")
        self.setup_widget_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def setup_general_tab(self):
        self.general_layout.addWidget(QLabel("Weather Location (e.g., 'City, ST' or 'City, Country'):"))
        self.location_entry = QLineEdit(self.config.get("weather_location", ""))
        self.general_layout.addWidget(self.location_entry)

        self.mirror_video_check = QCheckBox("Mirror Video")
        self.mirror_video_check.setChecked(self.config.get("mirror_video", False))
        self.general_layout.addWidget(self.mirror_video_check)

        self.rotate_button = QPushButton("Rotate Video 90°")
        self.rotate_button.clicked.connect(lambda: self.parent.rotate_video(self.config))
        self.general_layout.addWidget(self.rotate_button)

        self.general_layout.addWidget(QLabel("Global Text Size:"))
        self.text_size_slider = QSlider(Qt.Horizontal)
        self.text_size_slider.setRange(50, 200) # e.g., 50% to 200%
        self.text_size_slider.setValue(int(self.config.get("text_scale_multiplier", 1.0) * 100))
        self.general_layout.addWidget(self.text_size_slider)

    def setup_widget_tab(self):
        add_remove_layout = QHBoxLayout()
        self.widget_combo = QComboBox()
        self.widget_combo.addItems(sorted(WIDGET_CLASSES.keys()))
        add_remove_layout.addWidget(self.widget_combo)

        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.add_widget)
        add_remove_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_widget)
        add_remove_layout.addWidget(self.remove_button)
        self.widget_layout.addLayout(add_remove_layout)

        self.widget_list = QListWidget()
        self.widget_list.itemClicked.connect(self.display_widget_settings)
        self.widget_layout.addWidget(self.widget_list)

        self.widget_settings_area = QWidget()
        self.widget_settings_area.setObjectName("settings_area")
        self.widget_settings_layout = QVBoxLayout(self.widget_settings_area)
        self.widget_layout.addWidget(self.widget_settings_area)

        self.refresh_widget_list()

    def refresh_widget_list(self):
        self.widget_list.clear()
        for name in sorted(self.config.get("widget_positions", {})):
            self.widget_list.addItem(name)

    def add_widget(self):
        widget_type = self.widget_combo.currentText()
        i = 1
        while f"{widget_type}_{i}" in self.config["widget_positions"]:
            i += 1
        widget_name = f"{widget_type}_{i}"

        self.config["widget_positions"][widget_name] = {"x": 0.5, "y": 0.5, "anchor": "center"}
        if widget_type in ["ical", "rss"]:
            self.config["widget_settings"][widget_name] = {"urls": []}
        
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
        reply = QMessageBox.question(self, "Confirm", f"Are you sure you want to remove '{widget_name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            if widget_name in self.config["widget_positions"]: del self.config["widget_positions"][widget_name]
            if widget_name in self.config["widget_settings"]: del self.config["widget_settings"][widget_name]
            self.refresh_widget_list()
            self.clear_layout(self.widget_settings_layout)

    def display_widget_settings(self, item):
        self.save_current_widget_ui_to_config()
        self.clear_layout(self.widget_settings_layout)

        widget_name = item.text()
        self.widget_settings_area.setProperty("current_widget", widget_name)
        widget_type = widget_name.split('_')[0]
        settings = self.config.get("widget_settings", {}).get(widget_name, {})

        if widget_type == "time":
            self.widget_settings_layout.addWidget(QLabel("Time Format:"))
            combo = QComboBox(); combo.setObjectName("time_format_combo")
            combo.addItems(["24h", "12h"])
            combo.setCurrentText(settings.get("format", "24h"))
            self.widget_settings_layout.addWidget(combo)
        elif widget_type in ["ical", "rss"]:
            self.widget_settings_layout.addWidget(QLabel(f"{widget_type.upper()} Feed URLs:"))
            url_list = QListWidget(); url_list.setObjectName("url_list")
            url_list.addItems(settings.get("urls", []))
            self.widget_settings_layout.addWidget(url_list)
            
            add_url_button = QPushButton("Add URL"); remove_url_button = QPushButton("Remove Selected URL")
            add_url_button.clicked.connect(self.add_url)
            remove_url_button.clicked.connect(self.remove_url)
            self.widget_settings_layout.addWidget(add_url_button)
            self.widget_settings_layout.addWidget(remove_url_button)

    def add_url(self):
        url, ok = QInputDialog.getText(self, "Add URL", "Enter the new URL:")
        if ok and url:
            url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
            if url_list: url_list.addItem(url)

    def remove_url(self):
        url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
        if url_list and url_list.currentItem():
            url_list.takeItem(url_list.row(url_list.currentItem()))

    def save_current_widget_ui_to_config(self):
        widget_name = self.widget_settings_area.property("current_widget")
        if not widget_name: return

        widget_type = widget_name.split('_')[0]
        if widget_name not in self.config["widget_settings"]: self.config["widget_settings"][widget_name] = {}

        if widget_type == "time":
            combo = self.widget_settings_area.findChild(QComboBox, "time_format_combo")
            if combo: self.config["widget_settings"][widget_name]["format"] = combo.currentText()
        elif widget_type in ["ical", "rss"]:
            url_list = self.widget_settings_area.findChild(QListWidget, "url_list")
            if url_list: self.config["widget_settings"][widget_name]["urls"] = [url_list.item(i).text() for i in range(url_list.count())]

    def accept(self):
        self.config["weather_location"] = self.location_entry.text()
        self.config["mirror_video"] = self.mirror_video_check.isChecked()
        self.config["text_scale_multiplier"] = self.text_size_slider.value() / 100.0
        self.save_current_widget_ui_to_config()

        self.parent.config = self.config
        self.parent.save_config()
        self.parent.widget_manager.config = self.config
        self.parent.widget_manager.load_widgets()
        super().accept()

    def reject(self):
        super().reject()

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()

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

    def load_config(self):
        default_config = {
            "weather_location": "New York, US",
            "video_rotation": 0, "mirror_video": False, "text_scale_multiplier": 1.0,
            "widget_positions": {
                "time_1": {"x": 0.5, "y": 0.1, "anchor": "n"},
                "date_1": {"x": 0.5, "y": 0.18, "anchor": "n"},
                "weather_1": {"x": 0.05, "y": 0.1, "anchor": "nw"},
                "ical_1": {"x": 0.05, "y": 0.9, "anchor": "sw"},
                "rss_1": {"x": 0.95, "y": 0.9, "anchor": "se"}
            },
            "widget_settings": {
                "time_1": {"format": "24h"},
                "ical_1": {"urls": []},
                "rss_1": {"urls": []}
            }
        }
        if not os.path.exists(CONFIG_FILE):
            self.config = default_config
        else:
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
            
            # Clean up old news api key
            if "news_api_key" in self.config:
                del self.config["news_api_key"]
            
            # Ensure all default keys are present
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value

            # Old URL migration
            for name in list(self.config.get("widget_positions", {})):
                if name.startswith("ical") or name.startswith("rss"):
                    if self.config.get("widget_settings", {}).get(name, {}).get("url"):
                        old_url = self.config["widget_settings"][name]["url"]
                        if "urls" not in self.config["widget_settings"][name]:
                            self.config["widget_settings"][name]["urls"] = [old_url]
                        del self.config["widget_settings"][name]["url"]
        
        self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f: json.dump(self.config, f, indent=4)

    def setup_camera(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.show_error("Error: Could not open video device.")
            return
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_camera_feed)
        self.timer.start(30)

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
        # Add 2px padding for the shadow
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

    def rotate_video(self, config_ref):
        config_ref["video_rotation"] = (config_ref.get("video_rotation", 0) + 1) % 4

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
