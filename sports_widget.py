
import requests
from datetime import datetime, timedelta, timezone

# Using the free, public ESPN APIs
API_URLS = {
    "nfl": "http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "nba": "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
    "mlb": "http://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
}

class SportsWidget:
    def __init__(self, config, widget_config):
        self.params = {**config, **widget_config}
        self.league = self.params.get("league", "nfl")
        self.teams = [team.lower() for team in self.params.get("teams", [])]
        self.text = "Loading scores..."

    def update(self):
        try:
            url = API_URLS.get(self.league.lower())
            if not url:
                self.text = f"Unknown league: {self.league}"
                return

            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            
            self.text = self.format_scores(data)

        except requests.exceptions.RequestException as e:
            self.text = f"Error fetching scores: {e}"
        except Exception as e:
            self.text = f"An error occurred: {e}"

    def format_scores(self, data):
        output = []
        events = data.get("events", [])
        
        # Filter for games involving selected teams if any are specified
        if self.teams:
            filtered_events = []
            for event in events:
                for competition in event.get("competitions", []):
                    for competitor in competition.get("competitors", []):
                        if competitor.get("team", {}).get("abbreviation", "").lower() in self.teams:
                            filtered_events.append(event)
                            break
                    else:
                        continue
                    break
            events = filtered_events

        if not events:
            return f"No {self.league.upper()} games today."

        for event in events:
            game_info = self.parse_event(event)
            if game_info:
                output.append(game_info)
        
        return "\n".join(output) if output else f"No {self.league.upper()} games for selected teams."

    def parse_event(self, event):
        competitions = event.get("competitions", [])
        if not competitions:
            return None
            
        competition = competitions[0]
        status = competition.get("status", {}).get("type", {}).get("name", "STATUS_UNKNOWN")
        
        competitors = competition.get("competitors", [])
        if len(competitors) != 2:
            return None

        team1 = competitors[0].get("team", {})
        team2 = competitors[1].get("team", {})
        
        score1 = competitors[0].get("score", "0")
        score2 = competitors[1].get("score", "0")

        team1_name = team1.get("abbreviation", "TBD")
        team2_name = team2.get("abbreviation", "TBD")

        if status == "STATUS_FINAL":
            return f"{team1_name} {score1} - {team2_name} {score2} (Final)"
        elif status == "STATUS_IN_PROGRESS":
            detail = competition.get("status", {}).get("type", {}).get("detail", "In Progress")
            return f"{team1_name} {score1} - {team2_name} {score2} ({detail})"
        elif status == "STATUS_SCHEDULED":
            game_time_utc = datetime.fromisoformat(competition.get("date").replace("Z", "+00:00"))
            # This is a naive conversion, doesn't account for user's timezone from config
            game_time_local = game_time_utc.astimezone(timezone.utc).strftime("%I:%M %p UTC")
            return f"{team1_name} vs {team2_name} at {game_time_local}"
        
        return None
