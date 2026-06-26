import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://api.airlabs.co/api/v9/schedules"

def fetch_data(settings):
    """
    Main entry point for the FiestaBoard plugin.
    Processes settings, fetches flight data from AirLabs, and formats the output.
    """
    # 1. Initialize empty variables matching manifest schema
    variables = {
        "airport": settings.get("airport_name", "SFO").upper()[:3],
        "flights": []
    }

    # If the plugin is disabled or missing an API key, return early
    if not settings.get("enabled", False) or not settings.get("api_key"):
        logger.warning("Flight Board plugin is disabled or missing API Key.")
        return variables

    api_key = settings["api_key"]
    airport_code = settings.get("airport_name", "SFO").upper()
    flight_to_track = settings.get("flight", "").strip().upper()

    # 2. Build the API query parameters
    params = {
        "api_key": api_key
    }

    if flight_to_track:
        # If tracking a specific flight (e.g., UA2200)
        params["flight_iata"] = flight_to_track
    else:
        # Default to showing departures from the specified airport
        params["dep_iata"] = airport_code

    # 3. Execute request
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        logger.error(f"Error fetching data from AirLabs API: {e}")
        return variables

    # Check for API-side error responses
    if "error" in data:
        logger.error(f"AirLabs API returned an error: {data['error'].get('message')}")
        return variables

    raw_flights = data.get("response", [])
    
    # If it's a single dict response instead of a list, wrap it
    if isinstance(raw_flights, dict):
        raw_flights = [raw_flights]

    # 4. Map and sanitize response fields to match manifest variables
    processed_flights = []
    for f in raw_flights:
        # Safely convert delay fields to strings, defaulting to "0" if None
        dep_delay = str(f.get("dep_delayed") or f.get("dep_delay") or 0)
        arr_delay = str(f.get("arr_delayed") or f.get("arr_delay") or 0)

        flight_entry = {
            "name": f"{f.get('airline_iata', '')}{f.get('flight_number', '')}".strip() or "UNKNOWN",
            "airline_iata": str(f.get("airline_iata", ""))[:2],
            "flight_number": str(f.get("flight_number", ""))[:4],
            "dep_airport": str(f.get("dep_iata", ""))[:3],
            "dep_terminal": str(f.get("dep_terminal") or "")[:3],
            "dep_time": format_time(f.get("dep_time")),
            "dep_delayed_mins": dep_delay[:4],  # Fixed spelling here
            "dep_gate": str(f.get("dep_gate") or "")[:3],
            "arr_airport": str(f.get("arr_iata", ""))[:3],
            "arr_terminal": str(f.get("arr_terminal") or "")[:3],
            "arr_time": format_time(f.get("arr_time")),
            "arr_delayed_mins": arr_delay[:4],
            "arr_gate": str(f.get("arr_gate") or "")[:3],
            "arr_baggage": str(f.get("arr_baggage") or "")[:3],
            "status": str(f.get("status", "scheduled"))[:15]
        }
        processed_flights.append(flight_entry)

    variables["flights"] = processed_flights
    return variables


def format_time(time_str):
    """
    Helper to cleanly format typical ISO/AirLabs timestamps to fit the 16 char max.
    Converts '2026-06-26 18:30' -> '06/26 18:30'
    """
    if not time_str:
        return ""
    try:
        # AirLabs typically returns "YYYY-MM-DD HH:MM"
        dt = datetime.strptime(time_str.split(".")[0], "%Y-%m-%d %H:%M")
        return dt.strftime("%m/%d %H:%M")
    except ValueError:
        # Fallback to truncated string if parsing fails
        return str(time_str)[:16]
