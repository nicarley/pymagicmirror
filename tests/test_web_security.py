import json
import unittest

from web_server import REDACTED_VALUE, _redact_config, _restore_redacted_values


class WebConfigSecurityTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "web_server_token": "server-secret",
            "FMP_API_KEY": "market-secret",
            "widget_positions": {},
            "widget_settings": {
                "ical_1": {
                    "feeds": [{"name": "Home", "url": "https://calendar.example/private"}]
                },
                "commute_1": {"urls": ["https://calendar.example/commute"]},
                "rss_1": {"urls": ["https://news.example/feed"]},
                "package_1": {"api_key": "package-secret", "tracking_number": "TRACK-123"},
            },
        }

    def test_browser_config_redacts_credentials_and_private_calendars(self):
        safe = _redact_config(self.config)
        serialized = json.dumps(safe)

        self.assertNotIn("server-secret", serialized)
        self.assertNotIn("market-secret", serialized)
        self.assertNotIn("calendar.example/private", serialized)
        self.assertNotIn("TRACK-123", serialized)
        self.assertEqual(safe["web_server_token"], REDACTED_VALUE)
        self.assertEqual(safe["widget_settings"]["rss_1"]["urls"][0], "https://news.example/feed")

    def test_redacted_values_survive_a_browser_save(self):
        safe = _redact_config(self.config)
        safe["background_mode"] = "None"

        restored = _restore_redacted_values(safe, self.config)

        self.assertEqual(restored["web_server_token"], "server-secret")
        self.assertEqual(restored["FMP_API_KEY"], "market-secret")
        self.assertEqual(
            restored["widget_settings"]["ical_1"]["feeds"][0]["url"],
            "https://calendar.example/private",
        )
        self.assertEqual(restored["background_mode"], "None")


if __name__ == "__main__":
    unittest.main()
