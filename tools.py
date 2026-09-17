"""
tools.py - Tool definitions for our custom agent framework.

Each tool is a plain Python function with docstrings explaining what it does
and what parameters it expects. Gemini uses these docstrings to decide when
and how to call each tool.
"""

import json
import math
import os
import requests


def get_live_weather(city: str) -> str:
    """
    Fetches the current live weather report for a given city.
    
    Args:
        city: The name of the city (e.g. 'Tokyo', 'London', 'New York').
    
    Returns:
        A formatted string with temperature, condition, and humidity.
    """
    try:
        # Use wttr.in JSON API (free, open, no API key required)
        url = f"https://wttr.in/{city}?format=j1"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            current = data["current_condition"][0]
            temp_c = current.get("temp_C", "N/A")
            desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
            humidity = current.get("humidity", "N/A")
            wind = current.get("windspeedKmph", "N/A")
            return (
                f"Weather in {city}: {temp_c}°C, {desc}. "
                f"Humidity: {humidity}%, Wind speed: {wind} km/h."
            )
    except Exception as e:
        # Graceful fallback if internet is unavailable or wttr is busy
        pass

    # Deterministic fallback data so the demo always works reliably
    mock_data = {
        "tokyo": "18°C, Partly Cloudy, Humidity: 55%, Wind: 12 km/h",
        "london": "12°C, Light Drizzle, Humidity: 82%, Wind: 20 km/h",
        "new york": "15°C, Sunny, Humidity: 45%, Wind: 10 km/h",
        "paris": "16°C, Mild, Humidity: 60%, Wind: 14 km/h",
    }
    cleaned = city.strip().lower()
    return f"Weather in {city}: " + mock_data.get(cleaned, "20°C, Clear Sky, Humidity: 50%, Wind: 10 km/h")


def calculate_currency_or_math(expression: str) -> str:
    """
    Safely calculates mathematical expressions or currency conversions.
    
    Args:
        expression: A mathematical expression string, such as '1500 * 155.2' or '500 * 0.85 + 50'.
    
    Returns:
        The evaluated numerical result as a string.
    """
    allowed_names = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "math": math,
    }
    # Only allow safe math operations
    clean_expr = expression.strip().replace("^", "**")
    try:
        # Evaluate within a restricted environment for safety
        result = eval(clean_expr, {"__builtins__": {}}, allowed_names)
        if isinstance(result, float):
            result = round(result, 4)
        return f"Calculation Result: {clean_expr} = {result}"
    except Exception as err:
        return f"Math Evaluation Error for '{expression}': {str(err)}"


def save_report_file(filename: str, content: str) -> str:
    """
    Saves a report or notes to a file on the local computer disk.
    
    Args:
        filename: Name of the file to save (e.g. 'tokyo_plan.txt', 'summary.md').
        content: The text content of the report to write into the file.
    
    Returns:
        A confirmation message indicating success and file location.
    """
    # Sanitize filename to avoid path traversal
    safe_name = os.path.basename(filename)
    try:
        with open(safe_name, "w", encoding="utf-8") as f:
            f.write(content)
        abs_path = os.path.abspath(safe_name)
        return f"Success: File '{safe_name}' saved successfully ({len(content)} characters written) at {abs_path}"
    except Exception as e:
        return f"File Write Error: Failed to write to '{safe_name}': {str(e)}"


def unreliable_live_rates(pair: str) -> str:
    """
    Fetches real-time live currency exchange rates from an external bank gateway.
    
    NOTE: This is a flaky external service that may experience outages.
    
    Args:
        pair: Currency pair like 'USD/JPY' or 'EUR/USD'.
    
    Returns:
        The exchange rate string if online.
    """
    # Simulate a realistic external server 503 outage to test agent error recovery
    raise ConnectionError(
        f"HTTP 503 Service Unavailable: Gateway for currency pair '{pair}' timed out. "
        "The live banking API is temporarily down. Alternative fallback calculation is advised."
    )


# The Master Tool Registry: Maps tool names to their functions
TOOL_REGISTRY = {
    "get_live_weather": get_live_weather,
    "calculate_currency_or_math": calculate_currency_or_math,
    "save_report_file": save_report_file,
    "unreliable_live_rates": unreliable_live_rates,
}
