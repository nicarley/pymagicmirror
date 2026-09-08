"""Desktop interaction regressions, with isolated config and no external I/O."""

import copy
import os
import unittest
from contextlib import ExitStack
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QComboBox

from Main import MagicMirrorApp, SettingsDialog, SPORTS_TEAM_CACHE
from widget_manager import WidgetManager


class DesktopRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        config = MagicMirrorApp.normalized_config({
            "background_mode": "None",
            "fullscreen": False,
            "web_server_enabled": False,
            "onboarding_completed": True,
            "snap_to_grid": False,
            "active_page": "default",
            "layout_pages": ["default", "other"],
            "widget_positions": {
                "sports_1": {"x": 0.1, "y": 0.2, "anchor": "nw", "page": "default"},
                "time_2": {"x": 0.65, "y": 0.65, "anchor": "nw", "page": "other"},
            },
            "widget_settings": {
                "sports_1": {"configs": [{"league": "NFL", "teams": []}],
                             "style": "Normal", "font_scale": 1.0, "timezone": "UTC"},
                "time_2": {"font_scale": 1.0},
            },
        })
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(MagicMirrorApp, "load_config",
                                        lambda app: setattr(app, "config", copy.deepcopy(config))))
        stack.enter_context(patch.object(MagicMirrorApp, "save_config"))
        stack.enter_context(patch.object(MagicMirrorApp, "detect_available_cameras", return_value=[]))
        stack.enter_context(patch.object(WidgetManager, "start_updates"))
        stack.enter_context(patch.object(SettingsDialog, "request_sports_teams"))
        stack.enter_context(patch.dict(SPORTS_TEAM_CACHE, {}, clear=True))
        self.window = MagicMirrorApp()
        self.window.resize(960, 640)
        self.window.central_widget.resize(960, 640)
        self.window.scene_scheduler_timer.stop()
        self.addCleanup(self.window.close)
        self.window.widget_manager.widgets["sports_1"].text = "NFL scores\nCHI 17 - GB 14\nFinal"
        self.window.widget_manager.widgets["time_2"].text = "HIDDEN PAGE WIDGET"

    def settings_dialog(self):
        dialog = SettingsDialog(self.window)
        self.addCleanup(dialog.deleteLater)
        for index in range(dialog.widget_list.count()):
            item = dialog.widget_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == "sports_1":
                dialog.widget_list.setCurrentItem(item)
                break
        return dialog

    def paint_widgets(self):
        image = QImage(self.window.central_widget.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.black)
        painter = QPainter(image)
        try:
            self.window.draw_all_widgets(painter)
        finally:
            painter.end()
        return image

    def mouse_event(self, event_type, point):
        button = Qt.MouseButton.NoButton if event_type == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
        buttons = Qt.MouseButton.NoButton if event_type == QEvent.Type.MouseButtonRelease else Qt.MouseButton.LeftButton
        return QMouseEvent(event_type, QPointF(point), QPointF(point), button, buttons,
                           Qt.KeyboardModifier.NoModifier)

    def drag(self, start, end):
        self.window.central_widget_mouse_press(self.mouse_event(QEvent.Type.MouseButtonPress, start))
        self.window.central_widget_mouse_move(self.mouse_event(QEvent.Type.MouseMove, end))
        self.window.central_widget_mouse_release(self.mouse_event(QEvent.Type.MouseButtonRelease, end))

    def test_changing_style_starts_and_stops_ticker_animation(self):
        dialog = self.settings_dialog()
        style = dialog.widget_settings_area.findChild(QComboBox, "style_combo")
        self.assertFalse(self.window.ticker_timer.isActive())
        style.setCurrentText("Ticker")
        self.assertTrue(self.window.ticker_timer.isActive())
        style.setCurrentText("Normal")
        self.assertFalse(self.window.ticker_timer.isActive())

    def test_switching_back_to_ticker_page_restarts_animation(self):
        self.window.config["widget_settings"]["sports_1"]["style"] = "Ticker"
        self.window.config["active_page"] = "other"
        self.window.configure_ticker_timer()
        dialog = self.settings_dialog()
        self.assertFalse(self.window.ticker_timer.isActive())
        dialog.active_page_combo.setCurrentText("default")
        self.assertTrue(self.window.ticker_timer.isActive())
        dialog.active_page_combo.setCurrentText("other")
        self.assertFalse(self.window.ticker_timer.isActive())

    def test_ticker_at_screen_bottom_has_full_width_visible_bounds(self):
        surface = self.window.central_widget
        rect = self.window.get_ticker_rect(surface.height(), "nw", 32)
        self.assertEqual((rect.left(), rect.width(), rect.height()), (0, surface.width(), 32))
        self.assertEqual(rect.bottom(), surface.height() - 1)
        self.assertEqual(self.window.get_ticker_rect(-20, "s", 32).top(), 0)

        self.window.config["widget_settings"]["sports_1"]["style"] = "Ticker"
        self.window.config["widget_positions"]["sports_1"].update(x=0.7, y=1.0)
        bbox = self.window.get_widget_bbox("sports_1")
        self.assertEqual((bbox.left(), bbox.width()), (0, surface.width()))
        self.assertLess(bbox.bottom(), surface.height())

    def test_ticker_text_is_visible_on_first_paint(self):
        self.window.config["widget_settings"]["sports_1"]["style"] = "Ticker"
        image = self.paint_widgets()
        bbox = self.window.get_widget_bbox("sports_1")
        bright_pixels = sum(
            image.pixelColor(x, y).red() > 180
            for y in range(bbox.top(), bbox.bottom() + 1)
            for x in range(bbox.left(), bbox.right() + 1)
        )
        self.assertGreater(bright_pixels, 20, "A new ticker should show its text immediately")

    def test_hidden_page_widgets_have_no_edit_controls_or_mouse_target(self):
        self.window.edit_mode = True
        self.paint_widgets()
        self.assertIn("sports_1", self.window.widget_delete_hitboxes)
        self.assertNotIn("time_2", self.window.widget_delete_hitboxes)
        self.assertNotIn("time_2", self.window.widget_resize_hitboxes)
        surface = self.window.central_widget
        point = QPointF(surface.width() * 0.65 + 5, surface.height() * 0.65 + 10)
        self.window.central_widget_mouse_press(self.mouse_event(QEvent.Type.MouseButtonPress, point))
        self.assertIsNone(self.window.drag_data["widget"])
        self.assertEqual(self.window.undo_stack, [])

    def test_move_undo_redo_restores_original_anchor_and_position(self):
        self.window.edit_mode = True
        self.window.config["widget_positions"]["sports_1"].update(x=0.5, y=0.4, anchor="ne")
        bbox = self.window.get_widget_bbox("sports_1")
        original = copy.deepcopy(self.window.config["widget_positions"]["sports_1"])
        start = QPointF(bbox.center())
        self.drag(start, start + QPointF(60, 35))
        changed = copy.deepcopy(self.window.config["widget_positions"]["sports_1"])
        self.assertNotEqual(changed, original)
        self.window.undo_layout_change()
        self.assertEqual(self.window.config["widget_positions"]["sports_1"], original)
        self.window.redo_layout_change()
        self.assertEqual(self.window.config["widget_positions"]["sports_1"], changed)

    def test_resize_undo_redo_restores_font_scale(self):
        self.window.edit_mode = True
        self.paint_widgets()
        start = QPointF(self.window.widget_resize_hitboxes["sports_1"].center())
        self.drag(start, start + QPointF(120, 80))
        changed_scale = self.window.config["widget_settings"]["sports_1"]["font_scale"]
        self.assertGreater(changed_scale, 1.0)
        self.window.undo_layout_change()
        self.assertEqual(self.window.config["widget_settings"]["sports_1"]["font_scale"], 1.0)
        self.window.redo_layout_change()
        self.assertEqual(self.window.config["widget_settings"]["sports_1"]["font_scale"], changed_scale)

    def test_queued_result_from_replaced_widget_cannot_overwrite_new_instance(self):
        old_widget = self.window.widget_manager.widgets["sports_1"]
        self.window.queue_widget_instance_text_update(old_widget, "Old request result")
        self.window.widget_manager.load_widgets()
        new_widget = self.window.widget_manager.widgets["sports_1"]
        self.assertIsNot(new_widget, old_widget)
        self.qt_app.processEvents()
        self.assertNotEqual(new_widget.text, "Old request result")
        self.window.queue_widget_instance_text_update(new_widget, "Current request result")
        self.qt_app.processEvents()
        self.assertEqual(new_widget.text, "Current request result")

    def test_team_response_preserves_typed_abbreviations_and_respects_league_change(self):
        dialog = self.settings_dialog()
        league = dialog.widget_settings_area.findChild(QComboBox, "sports_league_combo")
        team = dialog.widget_settings_area.findChild(QComboBox, "sports_team_combo")
        league.setCurrentIndex(league.findData("NFL"))
        team.setEditText("CHI, GB")
        dialog.on_sports_teams_loaded("NFL", [("CHI", "CHI - Chicago Bears")], True)
        self.assertEqual(team.currentText(), "CHI, GB")
        league.setCurrentIndex(league.findData("NBA"))
        self.assertEqual(team.currentText(), "All Teams")
        team.setEditText("BOS")
        dialog.on_sports_teams_loaded("NFL", [("GB", "GB - Green Bay Packers")], True)
        self.assertEqual(team.currentText(), "BOS")
        self.assertEqual(team.property("league"), "NBA")


if __name__ == "__main__":
    unittest.main()
