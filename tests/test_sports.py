import copy
import unittest
from unittest.mock import Mock, patch

import pytz
import requests

from widget_manager import BaseWidget, SPORTS_API_URLS, SPORTS_REQUEST_HEADERS, SportsWidget, WidgetManager


def game(home="STL", away="SF", status="STATUS_FINAL", state="post", detail="Final/11", **overrides):
    event = {
        "id": f"{away}-{home}",
        "date": "2026-09-08T00:10Z",
        "competitions": [{
            "date": "2026-09-08T00:10Z",
            "status": {"type": {
                "name": status,
                "state": state,
                "completed": state == "post" and "FINAL" in status,
                "shortDetail": detail,
            }},
            "competitors": [
                {"homeAway": "home", "score": "5", "team": {"abbreviation": home, "displayName": "St. Louis Cardinals"}},
                {"homeAway": "away", "score": "4", "team": {"abbreviation": away}},
            ],
        }],
    }
    event["competitions"][0].update(overrides)
    return event


def widget(configs=None, style="Normal", timezone="US/Central"):
    return SportsWidget({"widget_settings": {"sports_1": {
        "configs": configs if configs is not None else [{"league": "MLB", "teams": ["STL"]}],
        "style": style,
        "timezone": timezone,
    }}}, "sports_1")


def response(events):
    result = Mock()
    result.json.return_value = {"events": events}
    return result


class SportsFeedTests(unittest.TestCase):
    @patch("widget_manager.SESSION.get")
    def test_espn_uses_accepted_http_client_headers_and_preserves_final_detail(self, get):
        get.return_value = response([game()])
        subject = widget()
        subject._update_text_worker(None)
        self.assertIn("SF 4 - STL 5 (Final/11)", subject.text)
        self.assertIn("Sep 07", subject.text)
        self.assertEqual(subject.last_error, "")
        self.assertIsNotNone(subject.last_updated)
        get.assert_called_once_with(SPORTS_API_URLS["mlb"], params={"limit": 1000}, headers=SPORTS_REQUEST_HEADERS, timeout=10)
        self.assertEqual(SPORTS_REQUEST_HEADERS["User-Agent"], requests.utils.default_user_agent())
        self.assertEqual(subject.get_refresh_interval(), 60000)

    @patch("widget_manager.SESSION.get")
    def test_college_duplicate_rows_fetch_once_and_louisville_alias_matches(self, get):
        get.return_value = response([game("UL", "AKR"), game("DUKE", "ARMY")])
        subject = widget([
            {"league": "NCAAMB", "teams": ["LOU"]},
            {"league": "Men's College Basketball", "teams": [" duke "]},
        ], style="Ticker")
        subject._update_text_worker(None)
        self.assertIn("UL 5", subject.text)
        self.assertIn("DUKE 5", subject.text)
        self.assertNotIn("No games", subject.text)
        self.assertNotIn("\n", subject.text)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"], {"limit": 1000, "groups": 50})

    @patch("widget_manager.SESSION.get")
    def test_network_failure_is_visible_in_both_styles_and_recovery_clears_it(self, get):
        for style in ("Normal", "Ticker"):
            with self.subTest(style=style):
                subject = widget(style=style)
                get.side_effect = requests.HTTPError("403 Forbidden")
                subject._update_text_worker(None)
                self.assertIn("Scores unavailable", subject.text)
                self.assertIn("MLB feed unavailable", subject.last_error)
                self.assertIsNone(subject.last_updated)
                self.assertEqual(subject.refresh_failures, 1)
                get.side_effect = None
                get.return_value = response([game()])
                subject._update_text_worker(None)
                self.assertEqual(subject.last_error, "")
                self.assertNotIn("unavailable", subject.text)

    @patch("widget_manager.SESSION.get")
    def test_last_good_scores_survive_failure_and_are_identified_as_cached(self, get):
        get.return_value = response([game()])
        subject = widget()
        subject._update_text_worker(None)
        last_updated = subject.last_updated
        get.side_effect = requests.Timeout()
        subject._update_text_worker(None)
        self.assertIn("SF 4 - STL 5", subject.text)
        self.assertIn("Cached scores from", subject.text)
        self.assertTrue(subject.last_error)
        self.assertEqual(subject.last_updated, last_updated)

    @patch("widget_manager.SESSION.get")
    def test_partial_outage_keeps_successful_leagues_and_reports_failed_league(self, get):
        get.side_effect = [response([game()]), requests.ConnectionError()]
        subject = widget([{"league": "MLB", "teams": []}, {"league": "NHL", "teams": []}])
        subject._update_text_worker(None)
        self.assertIn("SF 4 - STL 5", subject.text)
        self.assertIn("NHL: Scores unavailable", subject.text)
        self.assertIn("NHL feed unavailable", subject.last_error)

    @patch("widget_manager.SESSION.get")
    def test_invalid_payload_is_an_error_not_no_games(self, get):
        for payload in ({}, {"events": None}, ["unavailable"]):
            with self.subTest(payload=payload):
                get.return_value.json.return_value = payload
                subject = widget()
                subject._update_text_worker(None)
                self.assertTrue(subject.last_error)
                self.assertNotIn("No games", subject.text)

    @patch("widget_manager.SESSION.get")
    def test_empty_slate_and_missing_selected_teams_are_explained(self, get):
        get.return_value = response([game("DUKE", "ARMY")])
        subject = widget([{"league": "NCAAMB", "teams": ["DUKE", "LOU"]}], style="Ticker")
        subject._update_text_worker(None)
        self.assertIn("DUKE 5", subject.text)
        self.assertIn("No games for LOU", subject.text)
        self.assertEqual(subject.last_error, "")
        get.return_value = response([])
        subject._update_text_worker(None)
        self.assertIn("No games for DUKE, LOU", subject.text)

    @patch("widget_manager.SESSION.get")
    def test_all_teams_row_overrides_individual_filters(self, get):
        get.return_value = response([game("NY", "GS")])
        subject = widget([{"league": "NBA", "teams": ["BOS"]}, {"league": "NBA", "teams": []}])
        subject._update_text_worker(None)
        self.assertIn("GS 4 - NY 5", subject.text)
        self.assertNotIn("BOS", subject.text)
        self.assertEqual(get.call_count, 1)

    @patch("widget_manager.SESSION.get")
    def test_configuration_empty_and_unknown_league_remain_actionable(self, get):
        subject = widget([])
        subject._update_text_worker(None)
        self.assertIn("add a league or team", subject.text)
        self.assertEqual(subject.last_error, "")
        subject.config["widget_settings"]["sports_1"]["configs"] = [{"league": "bad", "teams": []}]
        subject._update_text_worker(None)
        self.assertIn("Unknown league: BAD", subject.text)
        self.assertIsNotNone(subject.last_updated)
        get.assert_not_called()

    @patch("widget_manager.SESSION.get")
    def test_invalid_timezone_is_reported_before_fetching(self, get):
        subject = widget(timezone="Invalid/Zone")
        subject._update_text_worker(None)
        self.assertIn("Unknown timezone", subject.last_error)
        get.assert_not_called()

    def test_team_aliases_labels_and_full_names_match(self):
        subject = widget()
        for selected in (["St. Louis Cardinals"], [" STL - St. Louis Cardinals "]):
            self.assertIn("STL 5", subject.format_scores({"events": [game()]}, "mlb", selected, pytz.utc))
        self.assertIn("GS 5", subject.format_scores({"events": [game("GS", "NY")]}, "nba", ["GSW"], pytz.utc))

    def test_malformed_event_and_duplicate_event_do_not_hide_good_scores(self):
        subject = widget()
        good = game()
        text = subject.format_scores({"events": [None, {}, {"competitions": [None]}, good, copy.deepcopy(good)]}, "mlb", [], pytz.utc)
        self.assertEqual(text.count("STL 5"), 1)


class SportsStatusTests(unittest.TestCase):
    def test_live_and_nonstandard_statuses_remain_visible(self):
        for status, state, detail, expected in (
            ("STATUS_HALFTIME", "in", "Halftime", "SF 4 - STL 5 (Halftime)"),
            ("STATUS_END_PERIOD", "in", "End of 3rd", "SF 4 - STL 5 (End of 3rd)"),
            ("STATUS_FINAL_OVERTIME", "post", "Final/OT", "SF 4 - STL 5 (Final/OT)"),
            ("STATUS_POSTPONED", "pre", "Postponed", "SF at STL (Postponed)"),
            ("STATUS_CANCELED", "post", "Canceled", "SF at STL (Canceled)"),
        ):
            with self.subTest(status=status):
                text = SportsWidget.parse_event(game(status=status, state=state, detail=detail), pytz.utc)
                self.assertIn(expected, text)

    def test_scheduled_games_include_correct_local_day_and_time(self):
        text = SportsWidget.parse_event(game(status="STATUS_SCHEDULED", state="pre", detail="Scheduled"), pytz.timezone("US/Central"))
        self.assertIn("SF at STL", text)
        self.assertIn("7:10 PM CDT", text)
        self.assertIn("Sep 07", text)

    def test_tbd_time_never_becomes_a_midnight_kickoff_or_previous_date(self):
        event = game(status="STATUS_SCHEDULED", state="pre", detail="TBD", date="2026-11-02T05:00Z", timeValid=False)
        text = SportsWidget.parse_event(event, pytz.timezone("US/Central"))
        self.assertIn("Time TBD", text)
        self.assertIn("Nov 02", text)
        self.assertNotIn("PM", text)

    def test_invalid_date_and_event_level_status_are_supported(self):
        event = game(status="STATUS_SCHEDULED", state="pre", detail="Scheduled", date="invalid")
        event["status"] = event["competitions"][0].pop("status")
        text = SportsWidget.parse_event(event, None)
        self.assertIn("SF at STL", text)
        self.assertIn("Time TBD", text)


class WidgetDeliveryTests(unittest.TestCase):
    def test_text_delivery_prefers_source_instance_to_prevent_old_worker_updates(self):
        app = Mock()
        for style in ("Normal", "Ticker"):
            with self.subTest(style=style):
                subject = widget(style=style)
                subject.set_text("Score", app)
                app.queue_widget_instance_text_update.assert_called_with(subject, "Score", style == "Ticker")
                app.queue_widget_text_update.assert_not_called()

    def test_text_delivery_keeps_legacy_app_compatibility(self):
        app = Mock(spec=["queue_widget_text_update"])
        subject = BaseWidget({}, "test_1")
        subject.set_text("Score", app)
        app.queue_widget_text_update.assert_called_once_with("test_1", "Score", False)

    def test_restarting_updates_restarts_ticker_animation(self):
        manager = WidgetManager.__new__(WidgetManager)
        manager.app = Mock()
        manager.stop_updates = Mock()
        manager.start_updates = Mock()
        manager.restart_updates()
        manager.stop_updates.assert_called_once()
        manager.start_updates.assert_called_once_with(manager.app)
        manager.app.configure_ticker_timer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
