import unittest

from Main import MagicMirrorApp


class ConfigValidationTests(unittest.TestCase):
    def test_professional_defaults_do_not_enable_camera_or_web_server(self):
        config = MagicMirrorApp.get_default_config()

        self.assertEqual(config["background_mode"], "None")
        self.assertFalse(config["web_server_enabled"])
        self.assertEqual(config["font_family"], "Segoe UI")

    def test_normalization_clamps_layout_and_performance_values(self):
        config = MagicMirrorApp.normalized_config(
            {
                "camera_fps": 500,
                "background_blur": -2,
                "widget_positions": {
                    "time_1": {"x": -1, "y": 4, "width": 5, "height": 0}
                },
                "widget_settings": {},
                "layout_pages": [],
            }
        )

        layout = config["widget_positions"]["time_1"]
        self.assertEqual(config["camera_fps"], 60)
        self.assertEqual(config["background_blur"], 0)
        self.assertEqual((layout["x"], layout["y"]), (0.0, 1.0))
        self.assertEqual((layout["width"], layout["height"]), (1.0, 0.08))
        self.assertIn("default", config["layout_pages"])


if __name__ == "__main__":
    unittest.main()
