import logging
import requests
from datetime import datetime

# Import the core components required by FiestaBoard
from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

BASE_URL = "https://airlabs.co/api/v9/schedules"

class FlightBoardPlugin(PluginBase):
    """
    Airport Flight Board plugin for FiestaBoard.
    Queries the AirLabs.co schedules API to populate departure/arrival variables.
    """
    
    @property
    def plugin_id(self) -> str:
        """Return the plugin ID - must match manifest.json 'id' field."""
        return "flightboard"

    def fetch_data(self) -> PluginResult:
        """
        The main data extraction method required by FiestaBoard.
        Returns a PluginResult instance containing the template variables.
        """
        # 1. Initialize variables mapping to manifest schema
        variables = {
            "airport": self.config.get("airport_name", "SFO").upper()[:3],
            "flights": []
        }

        # Check configuration parameters
        if not self.config.get("enabled", False):
            return PluginResult(available=False, error="Plugin is disabled.", data=variables)

        api_key = self.config.get("api_key")
        if not api_key:
            return PluginResult(available=False, error="Missing AirLabs API Key.", data=variables)

        airport_code = self.config.get("airport_name", "SFO").upper()
        flight_to_track = self.config.get("flight", "").strip().upper()
        board_type = self.config.get("board_type", "departures").lower()

        # 2. Build the API query parameters
        params = {
            "api_key": api_key
        }

        if flight_to_track:
            # Route to filter by specific flight if provided (e.g., UA2200)
            params["flight_iata"] = flight_to_track
        else:
            # Dynamically alternate parameter based on manifest UI dropdown select
            if board_type == "arrivals":
                params["arr_iata"] = airport_code
            else:
                params["dep_iata"] = airport_code

        # 3. Execute request
        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching data from AirLabs API: {e}")
            return PluginResult(available=False, error=str(e), data=variables)

        # Handle API-side errors gracefully
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown API error")
            logger.error(f"AirLabs API returned an error: {error_msg}")
            return PluginResult(available=False, error=error_msg, data=variables)

        raw_flights = data.get("response", [])
        
        # Wrap single-item dictionary responses in a list if necessary
        if isinstance(raw_flights, dict):
            raw_flights = [raw_flights]

        # 4. Process and format results to match manifest.json exactly
        processed_flights = []
        for f in raw_flights:
            dep_delay = str(f.get("dep_delayed") or f.get("dep_delay") or 0)
            arr_delay = str(f.get("arr_delayed") or f.get("arr_delay") or 0)

            flight_entry = {
                "name": f"{f.get('airline_iata', '')}{f.get('flight_number', '')}".strip() or "UNKNOWN",
                "airline_iata": str(f.get("airline_iata", ""))[:2],
                "flight_number": str(f.get("flight_number", ""))[:4],
                "dep_airport": str(f.get("dep_iata", ""))[:3],
                "dep_terminal": str(f.get("dep_terminal") or "")[:3],
                "dep_time": self._format_time(f.get("dep_time")),
                "dep_delayed_mins": dep_delay[:4],  
                "dep_gate": str(f.get("dep_gate") or "")[:3],
                "arr_airport": str(f.get("arr_iata", ""))[:3],
                "arr_terminal": str(f.get("arr_terminal") or "")[:3],
                "arr_time": self._format_time(f.get("arr_time")),
                "arr_delayed_mins": arr_delay[:4],
                "arr_gate": str(f.get("arr_gate") or "")[:3],
                "arr_baggage": str(f.get("arr_baggage") or "")[:3],
                "status": str(f.get("status", "scheduled"))[:15]
            }
            processed_flights.append(flight_entry)

        variables["flights"] = processed_flights
        
        # Return successful result back to FiestaBoard framework
        return PluginResult(available=True, data=variables)

    def validate_config(self, config: dict) -> list:
        """
        Optional validation hook. Returns a list of error strings if invalid.
        """
        errors = []
        if not config.get("airport_name"):
            errors.append("Airport Name is required.")
        return errors

    def _format_time(self, time_str):
        """Helper to safely format timestamps down to 16 char max constraint."""
        if not time_str:
            return ""
        try:
            dt = datetime.strptime(time_str.split(".")[0], "%Y-%m-%d %H:%M")
            return dt.strftime("%m/%d %H:%M")
        except ValueError:
            return str(time_str)[:16]
