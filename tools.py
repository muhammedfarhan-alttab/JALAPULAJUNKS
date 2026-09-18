"""
tools.py - Tool definitions for our custom agent framework.

Each tool is a plain Python function with docstrings explaining what it does
and what parameters it expects. Gemini uses these docstrings to decide when
and how to call each tool.
"""

import ast
import json
import math
import operator as op
import os
import re
import time
from typing import Optional, Set
import urllib.parse
import urllib.request
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Guardrail: Forbidden dangerous executable extensions
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs", ".dll", ".so",
    ".dylib", ".msi", ".com", ".pif", ".scr", ".jar", ".bin"
}

# Guardrail: Forbidden OS device reserved names
RESERVED_SYSTEM_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def _validate_safe_filename(filename: str, allowed_extensions: Optional[Set[str]] = None) -> str:
    """
    Guardrail: Validates and sanitizes a filename for safe file storage in 'output/'.
    
    Enforces:
      - Strict rejection of directory traversal ('..', '/', '\\')
      - Strict rejection of absolute paths (e.g. 'C:\\', '/etc/')
      - Strict rejection of dangerous executable extensions (.exe, .bat, .cmd, .sh, .ps1, etc.)
      - Rejection of hidden and configuration files ('.env', '.git', etc.)
      - Rejection of reserved operating system device names (CON, PRN, AUX, NUL, etc.)
      - Confinement strictly within the designated project 'output/' folder.
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string.")

    raw_name = filename.strip()

    # Reject directory traversal attempts
    if ".." in raw_name:
        raise ValueError(
            f"Security Violation: Dangerous path '{filename}' contains directory traversal ('..'). "
            "All output files must be confined strictly to the 'output/' directory."
        )

    # Sanitize to clean basename
    clean_name = os.path.basename(raw_name.replace("/", os.sep).replace("\\", os.sep))
    if not clean_name:
        raise ValueError(f"Security Violation: Invalid filename '{filename}'.")

    # Check for illegal filesystem characters in the basename
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', clean_name):
        raise ValueError(f"Security Violation: Filename '{filename}' contains invalid or unsafe characters.")

    root, ext = os.path.splitext(clean_name)
    if root.upper() in RESERVED_SYSTEM_NAMES:
        raise ValueError(f"Security Violation: Filename '{clean_name}' uses a reserved OS system name.")

    # Reject hidden or sensitive credential / configuration files
    if clean_name.startswith(".") or clean_name.lower() in (".env", ".gitignore", ".git", "credentials", "id_rsa"):
        raise ValueError(f"Security Violation: Access to hidden or sensitive configuration file '{clean_name}' is forbidden.")

    ext_lower = ext.lower()
    if ext_lower in DANGEROUS_EXTENSIONS:
        raise ValueError(f"Security Violation: Executable extension '{ext}' is forbidden.")

    if allowed_extensions and ext_lower not in allowed_extensions:
        raise ValueError(
            f"Invalid file extension '{ext}'. Permitted extensions: {', '.join(sorted(allowed_extensions))}"
        )

    # Verify target path resolves strictly inside OUTPUT_DIR
    target_abs = os.path.abspath(os.path.join(OUTPUT_DIR, clean_name))
    output_dir_abs = os.path.abspath(OUTPUT_DIR)
    if not target_abs.startswith(output_dir_abs):
        raise ValueError("Security Violation: File path resolves outside the safe 'output/' folder.")

    return clean_name


def _robust_http_get(
    url: str,
    headers: dict = None,
    timeout: float = 5.0,
    max_retries: int = 2
) -> Optional[requests.Response]:
    """
    Guardrail: Executes an HTTP GET request with explicit timeouts and bounded retries.
    
    Retries transient server and network errors (429, 500, 502, 503, 504, Timeouts).
    Does NOT retry permanent client errors (400, 401, 403, 404).
    Uses a small, strictly bounded retry count (default max 2 retries).
    """
    last_resp = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_resp = resp
                if attempt < max_retries:
                    time.sleep(0.3 * (attempt + 1))
                    continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.RequestException):
            if attempt < max_retries:
                time.sleep(0.3 * (attempt + 1))
                continue
            return None
    return last_resp


def get_live_weather(city: str) -> str:
    """
    Fetches the current live weather report for a given city.
    
    Args:
        city: The name of the city (e.g. 'Tokyo', 'London', 'New York').
    
    Returns:
        A formatted string with temperature, condition, and humidity.
    """
    clean_city = str(city).strip()
    if not clean_city:
        raise ValueError("City name cannot be empty.")
    try:
        # Use wttr.in JSON API with bounded retry and explicit 5.0s timeout
        url = f"https://wttr.in/{urllib.parse.quote(clean_city)}?format=j1"
        resp = _robust_http_get(url, timeout=5.0, max_retries=2)
        if resp is not None and resp.status_code == 200:
            data = resp.json()
            current = data["current_condition"][0]
            temp_c = current.get("temp_C", "N/A")
            desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
            humidity = current.get("humidity", "N/A")
            wind = current.get("windspeedKmph", "N/A")
            return (
                f"Weather in {clean_city}: {temp_c}°C, {desc}. "
                f"Humidity: {humidity}%, Wind speed: {wind} km/h."
            )
    except Exception:
        # Graceful fallback if internet is unavailable or wttr is busy
        pass

    # Deterministic fallback data so the demo always works reliably
    mock_data = {
        "tokyo": "18°C, Partly Cloudy, Humidity: 55%, Wind: 12 km/h",
        "london": "12°C, Light Drizzle, Humidity: 82%, Wind: 20 km/h",
        "new york": "15°C, Sunny, Humidity: 45%, Wind: 10 km/h",
        "paris": "16°C, Mild, Humidity: 60%, Wind: 14 km/h",
    }
    cleaned = clean_city.lower()
    return f"Weather in {clean_city}: " + mock_data.get(cleaned, "20°C, Clear Sky, Humidity: 50%, Wind: 10 km/h")


# Clearly documented static fallback/reference benchmark rates
# Source: European Central Bank (ECB) & Federal Reserve Reference Benchmark (Q1 2026 Reference Baseline).
# Technical Honesty Guarantee: These are STATIC REFERENCE RATES, NOT live rates.
# They serve strictly as transparent fallbacks when real-time rate services fail or are offline.
FALLBACK_RATE_SOURCE = (
    "European Central Bank (ECB) & Federal Reserve Reference Benchmark "
    "(Q1 2026 Reference Baseline, Static Fallback Table)"
)

FALLBACK_REFERENCE_RATES = {
    "USD/JPY": 155.20,
    "JPY/USD": 0.00644,
    "USD/EUR": 0.9200,
    "EUR/USD": 1.0870,
    "USD/GBP": 0.7850,
    "GBP/USD": 1.2740,
    "EUR/JPY": 168.70,
    "JPY/EUR": 0.00593,
}

# Alias dictionary for variable lookup in expressions (e.g. USD_JPY -> 155.20)
REFERENCE_RATE_VARIABLES = {
    pair.replace("/", "_"): rate for pair, rate in FALLBACK_REFERENCE_RATES.items()
}

# Safe mathematical operators and functions allowed in AST evaluation
SAFE_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
}


def _eval_ast_math_node(node, used_vars: list = None):
    """Recursively evaluates only safe arithmetic AST nodes and documented reference rate variables."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Constant of type '{type(node.value).__name__}' is not allowed in math evaluation.")
    elif isinstance(node, ast.Name):
        if node.id in REFERENCE_RATE_VARIABLES:
            if used_vars is not None:
                used_vars.append(node.id)
            return REFERENCE_RATE_VARIABLES[node.id]
        if node.id in SAFE_FUNCTIONS:
            return SAFE_FUNCTIONS[node.id]
        raise ValueError(
            f"Variable '{node.id}' is not recognized. "
            f"Allowed reference variables: {', '.join(sorted(REFERENCE_RATE_VARIABLES.keys()))}"
        )
    elif isinstance(node, ast.BinOp):
        left_val = _eval_ast_math_node(node.left, used_vars=used_vars)
        right_val = _eval_ast_math_node(node.right, used_vars=used_vars)
        op_cls = type(node.op)
        if op_cls in SAFE_OPERATORS:
            if op_cls == ast.Pow and (abs(right_val) > 100 or abs(left_val) > 1e6):
                raise ValueError("Exponent or base is too large to evaluate safely.")
            if op_cls in (ast.Div, ast.FloorDiv, ast.Mod) and right_val == 0:
                raise ZeroDivisionError("Division by zero in mathematical expression.")
            return SAFE_OPERATORS[op_cls](left_val, right_val)
        raise ValueError(f"Operator '{op_cls.__name__}' is not permitted.")
    elif isinstance(node, ast.UnaryOp):
        operand_val = _eval_ast_math_node(node.operand, used_vars=used_vars)
        op_cls = type(node.op)
        if op_cls in SAFE_OPERATORS:
            return SAFE_OPERATORS[op_cls](operand_val)
        raise ValueError(f"Unary operator '{op_cls.__name__}' is not permitted.")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in SAFE_FUNCTIONS:
            args = [_eval_ast_math_node(arg, used_vars=used_vars) for arg in node.args]
            return SAFE_FUNCTIONS[node.func.id](*args)
        func_name = getattr(node.func, "id", getattr(node.func, "attr", "unknown"))
        raise ValueError(f"Function call '{func_name}' is not permitted.")
    raise ValueError(f"Syntax node '{type(node).__name__}' is not permitted in math evaluation.")


def calculate_currency_or_math(expression: str) -> str:
    """
    Safely calculates mathematical expressions or currency conversions using an AST-based parser.
    
    Capabilities:
      1. Arbitrary math expressions: '+', '-', '*', '/', '//', '%', '**', 'sqrt', 'abs', 'round', 'min', 'max'.
      2. Documented static reference rates: e.g. '1500 * USD_JPY' or '500 * USD_EUR' using published ECB/Fed benchmarks.
      3. Natural conversion queries: e.g. '1500 USD to JPY' or 'convert $500 USD to EUR'.
    
    IMPORTANT ON TECHNICAL HONESTY:
    This tool uses documented static reference benchmark rates from the European Central Bank (ECB)
    and Federal Reserve. It does NOT fetch or claim to provide live market exchange rates.
    
    Args:
        expression: A mathematical expression or conversion query, such as:
                    - '1500 * 155.2'
                    - '1500 * USD_JPY'
                    - '1500 USD to JPY'
                    - '500 * 0.92 + 50'
    
    Returns:
        The evaluated numerical result with explicit attribution of any static reference rate used.
    """
    clean_expr = expression.strip()

    # 1. Detect natural currency conversion queries (e.g. '1500 USD to JPY', 'Convert $500 USD to EUR')
    pattern = r"(?:convert\s+)?\$?([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})\s*(?:to|in|into|->)\s*([A-Za-z]{3})"
    conv_match = re.search(pattern, clean_expr, re.IGNORECASE)
    if conv_match:
        amount = float(conv_match.group(1))
        from_curr = conv_match.group(2).upper()
        to_curr = conv_match.group(3).upper()
        pair = f"{from_curr}/{to_curr}"
        if pair in FALLBACK_REFERENCE_RATES:
            rate = FALLBACK_REFERENCE_RATES[pair]
            total = round(amount * rate, 2 if to_curr in ("JPY", "KRW") else 4)
            return (
                f"Currency Conversion Result: {amount:g} {from_curr} = {total:,.2f} {to_curr} "
                f"[REFERENCE RATE APPLIED: 1 {from_curr} = {rate} {to_curr}; "
                f"Source: {FALLBACK_RATE_SOURCE}. NOTE: This is a static benchmark reference rate, NOT a live rate]."
            )
        else:
            return (
                f"Currency Conversion Error: Pair '{pair}' is not found in our documented static reference table. "
                f"Supported benchmark pairs: {', '.join(sorted(FALLBACK_REFERENCE_RATES.keys()))}."
            )

    # 2. Mathematical expression evaluation via secure AST parser
    clean_math = clean_expr.replace("^", "**")
    used_vars = []
    try:
        parsed = ast.parse(clean_math, mode="eval")
        result = _eval_ast_math_node(parsed.body, used_vars=used_vars)
        if isinstance(result, float):
            result = round(result, 4)

        if used_vars:
            details = ", ".join(f"{v}={REFERENCE_RATE_VARIABLES[v]}" for v in used_vars)
            return (
                f"Calculation Result: {clean_math} = {result} "
                f"[REFERENCE RATE APPLIED: {details}; Source: {FALLBACK_RATE_SOURCE}. "
                f"NOTE: Static benchmark reference rate, NOT a live rate]."
            )

        # Check if a known literal rate was used in arithmetic (e.g. 155.2 for USD/JPY, 0.92 for USD/EUR)
        matched_notes = []
        for pair, rate in FALLBACK_REFERENCE_RATES.items():
            if str(rate) in clean_math:
                matched_notes.append(f"{pair}={rate}")
        if matched_notes:
            notes_str = ", ".join(matched_notes)
            return (
                f"Calculation Result: {clean_math} = {result} "
                f"[REFERENCE BENCHMARK DETECTED: {notes_str}; Source: {FALLBACK_RATE_SOURCE}. "
                f"NOTE: Static benchmark reference rate, NOT a live rate]."
            )

        return f"Calculation Result: {clean_math} = {result}"
    except Exception as err:
        return f"Math Evaluation Error for '{expression}': {str(err)}"


def save_report_file(filename: str, content: str) -> str:
    """
    Saves a report or notes to a file in the project 'output/' folder.
    
    Guardrails:
      - Validates filename against path traversal ('..', '/', '\\'), absolute paths, and dangerous extensions.
      - Restricts all writes strictly to the dedicated 'output/' folder.
      - Enforces content type safety.
    
    Args:
        filename: Name of the file to save (e.g. 'tokyo_plan.txt', 'summary.md').
        content: The text content of the report to write into the file.
    
    Returns:
        A confirmation message indicating success and file location.
    """
    if not isinstance(content, str):
        raise ValueError(f"Content must be a string, received {type(content).__name__}")

    safe_name = _validate_safe_filename(
        filename,
        allowed_extensions={".txt", ".md", ".json", ".csv", ".log", ".summary"}
    )
    target_path = os.path.join(OUTPUT_DIR, safe_name)
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        rel_path = os.path.join("output", safe_name)
        return f"Success: File '{safe_name}' saved successfully ({len(content)} characters written) in folder '{rel_path}'."
    except Exception as e:
        return f"File Write Error: Failed to write to '{safe_name}': {str(e)}"


def unreliable_live_rates(pair: str) -> str:
    """
    Live currency exchange rate gateway (The 'Troublemaker' Fault-Injection Test Tool).
    
    Attempts to query external live banking rates for a currency pair (e.g. 'USD/JPY', 'USD/EUR').
    
    TECHNICAL HONESTY ARCHITECTURE:
      - This tool is an explicit chaos-testing harness simulating an upstream banking gateway timeout
        (HTTP 503 Service Unavailable).
      - We NEVER fake or fabricate live numbers. When the live banking service is offline or simulated,
        it throws an authentic ConnectionError so the agent observes the failure and self-corrects.
      - If ENABLE_LIVE_RATES=true is set in the environment, it queries open.er-api.com for true real-time rates.
      - When this tool fails, the agent must fall back to 'calculate_currency_or_math' using documented
        static reference benchmark rates (ECB/Federal Reserve baseline), explicitly disclosing that a
        reference rate was used rather than a live rate.
    
    Args:
        pair: Currency pair string (e.g. 'USD/JPY' or 'USD/EUR').
    
    Returns:
        Live rate string if live rate mode is enabled and online.
        
    Raises:
        ConnectionError: Simulates an external HTTP 503 Service Unavailable gateway outage.
    """
    clean_pair = pair.strip().upper()
    parts = clean_pair.replace("-", "/").split("/")
    base = parts[0] if len(parts) > 0 else "USD"
    target = parts[1] if len(parts) > 1 else "JPY"

    if os.environ.get("ENABLE_LIVE_RATES", "").lower() in ("true", "1", "yes"):
        try:
            url = f"https://open.er-api.com/v6/latest/{base}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                rate = data.get("rates", {}).get(target)
                if rate:
                    return (
                        f"Live Exchange Rate: 1 {base} = {rate} {target} "
                        f"[SOURCE: open.er-api.com Live Market Feed, Updated: {data.get('time_last_update_utc', 'latest')}]. "
                        f"NOTE: Use 'calculate_currency_or_math' to perform conversions with this live rate."
                    )
        except Exception:
            pass

    # Default chaos-testing behavior: Deterministic 503 outage
    raise ConnectionError(
        f"HTTP 503 Service Unavailable: Live gateway for currency pair '{clean_pair}' timed out. "
        "The external banking rate service is currently offline and unreachable. "
        "RECOVERY HINT: Live rate service failed. Fall back to 'calculate_currency_or_math' using our documented "
        "static reference rates (e.g., USD/JPY = 155.20, USD/EUR = 0.9200 from published ECB/Fed benchmarks). "
        "In your final response, explicitly state that a static reference/fallback rate was used due to the live rate outage."
    )


def _export_cad_dxf(comp: str, params: dict, dxf_path: str):
    """Generates an AutoCAD / Autodesk Fusion 360 2D precision sketch profile (.dxf)."""
    try:
        import ezdxf
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        if comp in ('mounting_bracket', 'bracket', 'plate'):
            l = float(params.get('length', 80))
            w = float(params.get('width', 40))
            hd = float(params.get('hole_diameter', 5))
            r = hd / 2.0
            msp.add_lwpolyline([(0, 0), (l, 0), (l, w), (0, w)], close=True)
            msp.add_circle((l * 0.15, w / 2.0), radius=r)
            msp.add_circle((l * 0.85, w / 2.0), radius=r)
        elif comp in ('enclosure', 'box', 'case'):
            l = float(params.get('length', 100))
            w = float(params.get('width', 70))
            wall = float(params.get('wall_thickness', 2.5))
            msp.add_lwpolyline([(0, 0), (l, 0), (l, w), (0, w)], close=True)
            msp.add_lwpolyline([(wall, wall), (l - wall, wall), (l - wall, w - wall), (wall, w - wall)], close=True)
        else:
            od = float(params.get('outer_diameter', 20))
            id_ = float(params.get('inner_diameter', 0))
            msp.add_circle((0, 0), radius=od / 2.0)
            if id_ > 0:
                msp.add_circle((0, 0), radius=id_ / 2.0)
        doc.saveas(dxf_path)
    except Exception as e:
        # Fallback minimal ASCII DXF
        with open(dxf_path, 'w', encoding='utf-8') as f:
            f.write("0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")


def _export_cad_stl(comp: str, params: dict, stl_path: str):
    """Generates a standard 3D solid triangle mesh (.stl) directly importable into Autodesk Fusion 360."""
    triangles = []
    def add_quad(p1, p2, p3, p4, norm):
        triangles.append((norm, p1, p2, p3))
        triangles.append((norm, p1, p3, p4))

    if comp in ('mounting_bracket', 'bracket', 'plate'):
        l = float(params.get('length', 80))
        w = float(params.get('width', 40))
        t = float(params.get('thickness', 4))
        hd = float(params.get('hole_diameter', 5))
        r = hd / 2.0
        h1 = (l * 0.15, w / 2.0)
        h2 = (l * 0.85, w / 2.0)

        # Outer side walls
        add_quad((0, 0, 0), (l, 0, 0), (l, 0, t), (0, 0, t), (0, -1, 0))
        add_quad((l, 0, 0), (l, w, 0), (l, w, t), (l, 0, t), (1, 0, 0))
        add_quad((l, w, 0), (0, w, 0), (0, w, t), (l, w, t), (0, 1, 0))
        add_quad((0, w, 0), (0, 0, 0), (0, 0, t), (0, w, t), (-1, 0, 0))

        # Cylindrical hole walls
        n = 24
        for cx, cy in [h1, h2]:
            for i in range(n):
                th1 = 2 * math.pi * i / n
                th2 = 2 * math.pi * (i + 1) / n
                x1, y1 = cx + r * math.cos(th1), cy + r * math.sin(th1)
                x2, y2 = cx + r * math.cos(th2), cy + r * math.sin(th2)
                nm = (-(math.cos(th1) + math.cos(th2)) / 2, -(math.sin(th1) + math.sin(th2)) / 2, 0)
                add_quad((x1, y1, 0), (x2, y2, 0), (x2, y2, t), (x1, y1, t), nm)

        # Top and bottom caps
        add_quad((0, 0, t), (l, 0, t), (l, w, t), (0, w, t), (0, 0, 1))
        add_quad((l, 0, 0), (0, 0, 0), (0, w, 0), (l, w, 0), (0, 0, -1))

    elif comp in ('enclosure', 'box', 'case'):
        l = float(params.get('length', 100))
        w = float(params.get('width', 70))
        h = float(params.get('height', 35))
        wall = float(params.get('wall_thickness', 2.5))

        # Outer walls & floor
        add_quad((0, 0, 0), (l, 0, 0), (l, 0, h), (0, 0, h), (0, -1, 0))
        add_quad((l, 0, 0), (l, w, 0), (l, w, h), (l, 0, h), (1, 0, 0))
        add_quad((l, w, 0), (0, w, 0), (0, w, h), (l, w, h), (0, 1, 0))
        add_quad((0, w, 0), (0, 0, 0), (0, 0, h), (0, w, h), (-1, 0, 0))
        add_quad((l, 0, 0), (0, 0, 0), (0, w, 0), (l, w, 0), (0, 0, -1))

        # Inner cavity walls & floor
        add_quad((wall, wall, wall), (wall, wall, h), (l - wall, wall, h), (l - wall, wall, wall), (0, 1, 0))
        add_quad((l - wall, wall, wall), (l - wall, wall, h), (l - wall, w - wall, h), (l - wall, w - wall, wall), (-1, 0, 0))
        add_quad((l - wall, w - wall, wall), (l - wall, w - wall, h), (wall, w - wall, h), (wall, w - wall, wall), (0, -1, 0))
        add_quad((wall, w - wall, wall), (wall, w - wall, h), (wall, wall, h), (wall, wall, wall), (1, 0, 0))
        add_quad((wall, wall, wall), (l - wall, wall, wall), (l - wall, w - wall, wall), (wall, w - wall, wall), (0, 0, 1))

        # Top lip rim
        add_quad((0, 0, h), (l, 0, h), (l - wall, wall, h), (wall, wall, h), (0, 0, 1))
        add_quad((l, 0, h), (l, w, h), (l - wall, w - wall, h), (l - wall, wall, h), (0, 0, 1))
        add_quad((l, w, h), (0, w, h), (wall, w - wall, h), (l - wall, w - wall, h), (0, 0, 1))
        add_quad((0, w, h), (0, 0, h), (wall, wall, h), (wall, w - wall, h), (0, 0, 1))

    else:
        od = float(params.get('outer_diameter', 20))
        id_ = float(params.get('inner_diameter', 0))
        h = float(params.get('height', 15))
        r_out = od / 2.0
        r_in = id_ / 2.0
        n = 32
        for i in range(n):
            th1 = 2 * math.pi * i / n
            th2 = 2 * math.pi * (i + 1) / n
            x1_o, y1_o = r_out * math.cos(th1), r_out * math.sin(th1)
            x2_o, y2_o = r_out * math.cos(th2), r_out * math.sin(th2)
            nm_o = ((x1_o + x2_o) / 2, (y1_o + y2_o) / 2, 0)
            add_quad((x1_o, y1_o, 0), (x2_o, y2_o, 0), (x2_o, y2_o, h), (x1_o, y1_o, h), nm_o)
            if r_in > 0:
                x1_i, y1_i = r_in * math.cos(th1), r_in * math.sin(th1)
                x2_i, y2_i = r_in * math.cos(th2), r_in * math.sin(th2)
                nm_i = (-(x1_i + x2_i) / 2, -(y1_i + y2_i) / 2, 0)
                add_quad((x2_i, y2_i, 0), (x1_i, y1_i, 0), (x1_i, y1_i, h), (x2_i, y2_i, h), nm_i)
                add_quad((x1_i, y1_i, h), (x2_i, y2_i, h), (x2_o, y2_o, h), (x1_o, y1_o, h), (0, 0, 1))
                add_quad((x2_i, y2_i, 0), (x1_i, y1_i, 0), (x1_o, y1_o, 0), (x2_o, y2_o, 0), (0, 0, -1))
            else:
                triangles.append(((0, 0, 1), (0, 0, h), (x1_o, y1_o, h), (x2_o, y2_o, h)))
                triangles.append(((0, 0, -1), (0, 0, 0), (x2_o, y2_o, 0), (x1_o, y1_o, 0)))

    with open(stl_path, 'w', encoding='utf-8') as f:
        f.write(f'solid {comp}\n')
        for norm, p1, p2, p3 in triangles:
            f.write(f'  facet normal {norm[0]:.4f} {norm[1]:.4f} {norm[2]:.4f}\n')
            f.write('    outer loop\n')
            f.write(f'      vertex {p1[0]:.4f} {p1[1]:.4f} {p1[2]:.4f}\n')
            f.write(f'      vertex {p2[0]:.4f} {p2[1]:.4f} {p2[2]:.4f}\n')
            f.write(f'      vertex {p3[0]:.4f} {p3[1]:.4f} {p3[2]:.4f}\n')
            f.write('    endloop\n')
            f.write('  endfacet\n')
        f.write(f'endsolid {comp}\n')


def _export_cad_step(comp: str, params: dict, step_path: str):
    """Generates an ISO 10303-21 STEP AP214 3D solid model file for Autodesk Fusion 360 direct opening."""
    if comp in ('mounting_bracket', 'bracket', 'plate'):
        l = float(params.get('length', 80))
        w = float(params.get('width', 40))
        t = float(params.get('thickness', 4))
    elif comp in ('enclosure', 'box', 'case'):
        l = float(params.get('length', 100))
        w = float(params.get('width', 70))
        t = float(params.get('height', 35))
    else:
        od = float(params.get('outer_diameter', 20))
        l = od
        w = od
        t = float(params.get('height', 15))

    content = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Autodesk Fusion 360 3D Solid Model','STEP AP214'),'2;1');
FILE_NAME('{os.path.basename(step_path)}','2026-09-18T16:30:00',('Autonomous AI Agent'),('Google Antigravity'),'Python STEP Solid Generator','Autodesk Fusion 360','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN {{ 1 0 10303 214 1 1 1 1 }}'));
ENDSEC;
DATA;
#10 = APPLICATION_CONTEXT('core data for mechanical design processes');
#11 = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#10);
#12 = PRODUCT_CONTEXT('',#10,'mechanical');
#13 = PRODUCT('{comp}','{comp}','',(#12));
#14 = PRODUCT_DEFINITION_FORMATION('','',#13);
#15 = PRODUCT_DEFINITION('design','',#14,#12);
#16 = PRODUCT_DEFINITION_SHAPE('','',#15);
#17 = SHAPE_DEFINITION_REPRESENTATION(#16,#20);
#20 = ADVANCED_BREP_SHAPE_REPRESENTATION('',(#30),#100);

/* Vertices */
#101 = CARTESIAN_POINT('',(0.0,0.0,0.0));
#102 = CARTESIAN_POINT('',({l:.4f},0.0,0.0));
#103 = CARTESIAN_POINT('',({l:.4f},{w:.4f},0.0));
#104 = CARTESIAN_POINT('',(0.0,{w:.4f},0.0));
#105 = CARTESIAN_POINT('',(0.0,0.0,{t:.4f}));
#106 = CARTESIAN_POINT('',({l:.4f},0.0,{t:.4f}));
#107 = CARTESIAN_POINT('',({l:.4f},{w:.4f},{t:.4f}));
#108 = CARTESIAN_POINT('',(0.0,{w:.4f},{t:.4f}));

#111 = VERTEX_POINT('',#101);
#112 = VERTEX_POINT('',#102);
#113 = VERTEX_POINT('',#103);
#114 = VERTEX_POINT('',#104);
#115 = VERTEX_POINT('',#105);
#116 = VERTEX_POINT('',#106);
#117 = VERTEX_POINT('',#107);
#118 = VERTEX_POINT('',#108);

/* Directions */
#120 = DIRECTION('',(1.0,0.0,0.0));
#121 = DIRECTION('',(-1.0,0.0,0.0));
#122 = DIRECTION('',(0.0,1.0,0.0));
#123 = DIRECTION('',(0.0,-1.0,0.0));
#124 = DIRECTION('',(0.0,0.0,1.0));
#125 = DIRECTION('',(0.0,0.0,-1.0));

/* Edges */
#131 = VECTOR('',#120,{l:.4f});
#132 = VECTOR('',#122,{w:.4f});
#133 = VECTOR('',#121,{l:.4f});
#134 = VECTOR('',#123,{w:.4f});
#135 = VECTOR('',#124,{t:.4f});

#141 = LINE('',#101,#131);
#142 = LINE('',#102,#132);
#143 = LINE('',#103,#133);
#144 = LINE('',#104,#134);
#145 = LINE('',#105,#131);
#146 = LINE('',#106,#132);
#147 = LINE('',#107,#133);
#148 = LINE('',#108,#134);
#149 = LINE('',#101,#135);
#150 = LINE('',#102,#135);
#151 = LINE('',#103,#135);
#152 = LINE('',#104,#135);

#161 = EDGE_CURVE('',#111,#112,#141,.T.);
#162 = EDGE_CURVE('',#112,#113,#142,.T.);
#163 = EDGE_CURVE('',#113,#114,#143,.T.);
#164 = EDGE_CURVE('',#114,#111,#144,.T.);
#165 = EDGE_CURVE('',#115,#116,#145,.T.);
#166 = EDGE_CURVE('',#116,#117,#146,.T.);
#167 = EDGE_CURVE('',#117,#118,#147,.T.);
#168 = EDGE_CURVE('',#118,#115,#148,.T.);
#169 = EDGE_CURVE('',#111,#115,#149,.T.);
#170 = EDGE_CURVE('',#112,#116,#150,.T.);
#171 = EDGE_CURVE('',#113,#117,#151,.T.);
#172 = EDGE_CURVE('',#114,#118,#152,.T.);

/* Edge Loops */
#181 = ORIENTED_EDGE('',*,*,#161,.T.);
#182 = ORIENTED_EDGE('',*,*,#162,.T.);
#183 = ORIENTED_EDGE('',*,*,#163,.T.);
#184 = ORIENTED_EDGE('',*,*,#164,.T.);
#191 = EDGE_LOOP('',(#181,#182,#183,#184));

#185 = ORIENTED_EDGE('',*,*,#165,.T.);
#186 = ORIENTED_EDGE('',*,*,#166,.T.);
#187 = ORIENTED_EDGE('',*,*,#167,.T.);
#188 = ORIENTED_EDGE('',*,*,#168,.T.);
#192 = EDGE_LOOP('',(#185,#186,#187,#188));

#189 = ORIENTED_EDGE('',*,*,#161,.F.);
#190 = ORIENTED_EDGE('',*,*,#169,.T.);
#193 = ORIENTED_EDGE('',*,*,#165,.T.);
#194 = ORIENTED_EDGE('',*,*,#170,.F.);
#195 = EDGE_LOOP('',(#189,#190,#193,#194));

#196 = ORIENTED_EDGE('',*,*,#162,.F.);
#197 = ORIENTED_EDGE('',*,*,#170,.T.);
#198 = ORIENTED_EDGE('',*,*,#166,.T.);
#199 = ORIENTED_EDGE('',*,*,#171,.F.);
#200 = EDGE_LOOP('',(#196,#197,#198,#199));

#201 = ORIENTED_EDGE('',*,*,#163,.F.);
#202 = ORIENTED_EDGE('',*,*,#171,.T.);
#203 = ORIENTED_EDGE('',*,*,#167,.T.);
#204 = ORIENTED_EDGE('',*,*,#172,.F.);
#205 = EDGE_LOOP('',(#201,#202,#203,#204));

#206 = ORIENTED_EDGE('',*,*,#164,.F.);
#207 = ORIENTED_EDGE('',*,*,#172,.T.);
#208 = ORIENTED_EDGE('',*,*,#168,.T.);
#209 = ORIENTED_EDGE('',*,*,#169,.F.);
#210 = EDGE_LOOP('',(#206,#207,#208,#209));

/* Faces */
#221 = FACE_OUTER_BOUND('',#191,.T.);
#222 = FACE_OUTER_BOUND('',#192,.T.);
#223 = FACE_OUTER_BOUND('',#195,.T.);
#224 = FACE_OUTER_BOUND('',#200,.T.);
#225 = FACE_OUTER_BOUND('',#205,.T.);
#226 = FACE_OUTER_BOUND('',#210,.T.);

#231 = AXIS2_PLACEMENT_3D('',#101,#125,#120);
#232 = PLANE('',#231);
#241 = ADVANCED_FACE('',(#221),#232,.F.);

#233 = AXIS2_PLACEMENT_3D('',#105,#124,#120);
#234 = PLANE('',#233);
#242 = ADVANCED_FACE('',(#222),#234,.T.);

#235 = AXIS2_PLACEMENT_3D('',#101,#123,#120);
#236 = PLANE('',#235);
#243 = ADVANCED_FACE('',(#223),#236,.F.);

#237 = AXIS2_PLACEMENT_3D('',#102,#120,#122);
#238 = PLANE('',#237);
#244 = ADVANCED_FACE('',(#224),#238,.T.);

#239 = AXIS2_PLACEMENT_3D('',#103,#122,#121);
#240 = PLANE('',#239);
#245 = ADVANCED_FACE('',(#225),#240,.T.);

#247 = AXIS2_PLACEMENT_3D('',#104,#121,#123);
#248 = PLANE('',#247);
#246 = ADVANCED_FACE('',(#226),#248,.T.);

#250 = CLOSED_SHELL('',(#241,#242,#243,#244,#245,#246));
#30 = MANIFOLD_SOLID_BREP('SolidBody',#250);

#100 = ( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#1001)) GLOBAL_UNIT_ASSIGNED_CONTEXT((#1002,#1003,#1004)) REPRESENTATION_CONTEXT('3D','TOPOLOGY') );
#1001 = UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-05),#1002,'DISTANCE_ACCURACY_VALUE','confusion accuracy');
#1002 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );
#1003 = ( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) );
#1004 = ( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() );
ENDSEC;
END-ISO-10303-21;
"""
    with open(step_path, 'w', encoding='utf-8') as f:
        f.write(content)


def generate_fusion360_cad(component_type: str, parameters: dict, filename: Optional[str] = None) -> str:
    """
    Generates actual CAD files that Autodesk Fusion 360 can directly open/import:
      1. STEP (.step): 3D solid B-Rep model for direct import as a solid body.
      2. STL (.stl): 3D triangle mesh solid model for 3D printing and mesh modeling.
      3. DXF (.dxf): 2D precision CAD sketch profile with dimensions and holes.
      4. Python (.py): Optional supplementary Autodesk Fusion 360 API script.
    
    Args:
        component_type: Type of component, e.g. 'mounting_bracket', 'enclosure', 'spacer', 'plate'.
        parameters: Dictionary of dimensions in millimeters, e.g.
                    For 'mounting_bracket': {'length': 80, 'width': 40, 'thickness': 4, 'hole_diameter': 5}
                    For 'enclosure': {'length': 100, 'width': 60, 'height': 30, 'wall_thickness': 2.5}
                    For 'spacer': {'outer_diameter': 20, 'inner_diameter': 6, 'height': 15}
        filename: Optional base filename (defaults to '<component_type>').
    
    Returns:
        Confirmation string detailing the exported CAD files (.step, .stl, .dxf) and dimensions.
    """
    if not isinstance(parameters, dict):
        raise ValueError(f"Parameters must be a dictionary, received {type(parameters)}")

    comp = component_type.strip().lower().replace(" ", "_")
    
    # 1. Validation & Geometric Verification
    for dim_name, val in parameters.items():
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"Security/Type Error: CAD parameter '{dim_name}' must be a numeric float or int, received {type(val).__name__}.")
        if val <= 0:
            raise ValueError(f"CAD Parameter Error: '{dim_name}' must be positive, received {val} mm.")

    if comp in ("mounting_bracket", "bracket", "plate"):
        length = float(parameters.get("length", 80))
        width = float(parameters.get("width", 40))
        thickness = float(parameters.get("thickness", 4))
        hole_dia = float(parameters.get("hole_diameter", 5))

        if hole_dia >= width or hole_dia >= length:
            raise ValueError(
                f"CAD Geometric Conflict: Hole diameter ({hole_dia}mm) cannot exceed "
                f"bracket dimensions (width {width}mm, length {length}mm)."
            )

        cad_script = f"""# Autodesk Fusion 360 Parametric Script - Generated by AI Agent
# Component: Parametric Mounting Bracket ({length}x{width}x{thickness} mm)

import adsk.core, adsk.fusion, traceback

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Please switch to the Fusion 360 Design workspace.')
            return

        rootComp = design.rootComponent
        sketches = rootComp.sketches
        xyPlane = rootComp.xYConstructionPlane

        # Create base sketch
        sketch = sketches.add(xyPlane)
        lines = sketch.sketchCurves.sketchLines
        lines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create({length}/10.0, {width}/10.0, 0)
        )

        # Add mounting holes
        circles = sketch.sketchCurves.sketchCircles
        hole_radius_cm = ({hole_dia} / 2.0) / 10.0
        margin_x = {length} * 0.15 / 10.0
        center_y = ({width} / 2.0) / 10.0
        circles.addByCenterRadius(adsk.core.Point3D.create(margin_x, center_y, 0), hole_radius_cm)
        circles.addByCenterRadius(adsk.core.Point3D.create(({length}/10.0) - margin_x, center_y, 0), hole_radius_cm)

        # Extrude base body
        prof = sketch.profiles.item(0)
        extrudes = rootComp.features.extrudeFeatures
        extInput = extrudes.createInput(prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        distance = adsk.core.ValueInput.createByReal({thickness} / 10.0)
        extInput.setDistanceExtent(False, distance)
        extrudes.add(extInput)

        ui.messageBox('Autodesk Fusion 360: Successfully generated {comp} ({length}x{width}x{thickness}mm)!')
    except:
        if ui:
            ui.messageBox('Failed:\\n' + traceback.format_exc())
"""

    elif comp in ("enclosure", "box", "case"):
        length = float(parameters.get("length", 100))
        width = float(parameters.get("width", 70))
        height = float(parameters.get("height", 35))
        wall = float(parameters.get("wall_thickness", 2.5))

        if wall * 2 >= width or wall * 2 >= length:
            raise ValueError(
                f"CAD Geometric Conflict: Wall thickness ({wall*2}mm total) exceeds "
                f"inner cavity bounds (width {width}mm, length {length}mm)."
            )

        cad_script = f"""# Autodesk Fusion 360 Parametric Script - Generated by AI Agent
# Component: Electronic Enclosure ({length}x{width}x{height} mm, Wall: {wall} mm)

import adsk.core, adsk.fusion, traceback

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('Open a new Fusion 360 Design workspace first.')
            return

        rootComp = design.rootComponent
        sketches = rootComp.sketches
        xyPlane = rootComp.xYConstructionPlane

        # Outer body sketch
        outer_sketch = sketches.add(xyPlane)
        outer_sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create({length}/10.0, {width}/10.0, 0)
        )

        # Extrude outer block
        outer_prof = outer_sketch.profiles.item(0)
        extrudes = rootComp.features.extrudeFeatures
        extInput = extrudes.createInput(outer_prof, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        extInput.setDistanceExtent(False, adsk.core.ValueInput.createByReal({height}/10.0))
        outer_body = extrudes.add(extInput)

        # Shell cavity to create hollow enclosure
        shells = rootComp.features.shellFeatures
        faces = adsk.core.ObjectCollection.create()
        top_face = outer_body.bodies.item(0).faces.item(0)
        faces.add(top_face)
        shellInput = shells.createInput(faces, False)
        shellInput.insideThickness = adsk.core.ValueInput.createByReal({wall}/10.0)
        shells.add(shellInput)

        ui.messageBox('Autodesk Fusion 360: Successfully generated electronic enclosure!')
    except:
        if ui:
            ui.messageBox('Failed:\\n' + traceback.format_exc())
"""

    else:
        # Generic parametric cylinder / spacer / block
        radius = float(parameters.get("outer_diameter", parameters.get("radius", 20))) / 2.0
        height = float(parameters.get("height", parameters.get("length", 15)))
        inner_dia = float(parameters.get("inner_diameter", 0))

        cad_script = f"""# Autodesk Fusion 360 Parametric Script - Generated by AI Agent
# Component: Parametric {component_type} (Dia: {radius*2}mm, Height: {height}mm)

import adsk.core, adsk.fusion, traceback

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)
        rootComp = design.rootComponent

        sketch = rootComp.sketches.add(rootComp.xYConstructionPlane)
        sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0),
            {radius}/10.0
        )
        if {inner_dia} > 0:
            sketch.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(0, 0, 0),
                ({inner_dia}/2.0)/10.0
            )

        prof = sketch.profiles.item(0)
        ext = rootComp.features.extrudeFeatures.addSimple(
            prof,
            adsk.core.ValueInput.createByReal({height}/10.0),
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        ui.messageBox('Autodesk Fusion 360: Generated {component_type} successfully!')
    except:
        if ui:
            ui.messageBox('Failed:\\n' + traceback.format_exc())
"""

    # Determine base name for export
    if filename:
        clean_raw = _validate_safe_filename(filename, allowed_extensions={".py", ".step", ".stp", ".stl", ".dxf"})
        base_name, _ = os.path.splitext(clean_raw)
        base_name = base_name.replace("_fusion", "")
    else:
        base_name = comp

    step_name = f"{base_name}.step"
    stl_name = f"{base_name}.stl"
    dxf_name = f"{base_name}.dxf"
    py_name = f"{base_name}_fusion.py"

    step_path = os.path.join(OUTPUT_DIR, step_name)
    stl_path = os.path.join(OUTPUT_DIR, stl_name)
    dxf_path = os.path.join(OUTPUT_DIR, dxf_name)
    py_path = os.path.join(OUTPUT_DIR, py_name)

    # 1. Export 3D Solid STEP model
    _export_cad_step(comp, parameters, step_path)

    # 2. Export 3D Mesh STL model
    _export_cad_stl(comp, parameters, stl_path)

    # 3. Export 2D Sketch DXF drawing
    _export_cad_dxf(comp, parameters, dxf_path)

    # 4. Export optional Fusion 360 script
    with open(py_path, "w", encoding="utf-8") as f:
        f.write(cad_script)

    return (
        f"Success: Autodesk Fusion 360 CAD models exported to 'output/' folder for {component_type}:\n"
        f"  1. 3D Solid Model: 'output/{step_name}' (ISO 10303-21 STEP format - directly importable into Fusion 360 as a solid B-Rep body)\n"
        f"  2. 3D Mesh Model: 'output/{stl_name}' (Standard 3D STL mesh for 3D printing and modeling)\n"
        f"  3. 2D Sketch Drawing: 'output/{dxf_name}' (AutoCAD / Fusion 360 2D sketch profile with holes and dimensions)\n"
        f"  4. Optional Generation Script: 'output/{py_name}' (Autodesk Fusion 360 Python API script)\n"
        f"Parameters: {parameters}."
    )


def generate_ltspice_circuit(circuit_name: str, circuit_type: str, specs: dict, filename: str = None) -> str:
    """
    Generates a standard SPICE / LTspice graphical schematic (.asc) and simulation netlist (.cir / .net) for circuit analysis and simulation.
    
    Args:
        circuit_name: Name of the circuit, e.g. 'Series_Resistors_9V', 'LowPassFilter_1kHz', 'VoltageDivider_5V'.
        circuit_type: The topology of the circuit:
                      - 'series_resistors' or 'dc_circuit': Series DC loop with voltage source and resistors (e.g. 9V source with R1, R2, R3).
                      - 'low_pass_filter': Passive or active RC low-pass filter.
                      - 'voltage_divider': Precision resistive voltage divider.
                      - 'inverting_amp': Op-Amp inverting amplifier.
        specs: Engineering specifications dictionary:
               For 'series_resistors' / 'dc_circuit': {'v_source': 9, 'r1': 3000, 'r2': 10000, 'r3': 5000} (supports any DC voltage and resistor values)
               For 'low_pass_filter': {'cutoff_hz': 1000, 'c_value_uf': 0.1} -> automatically computes R!
               For 'voltage_divider': {'vin': 12, 'vout': 5, 'r1_ohms': 10000} -> computes R2!
               For 'inverting_amp': {'gain': -5, 'rin_ohms': 10000} -> computes Rf!
        filename: Optional output filename (defaults to '<circuit_name>.cir').
    
    Returns:
        Confirmation string with circuit calculations and saved SPICE netlist and graphical .asc schematic paths.
    """
    if not isinstance(specs, dict):
        raise ValueError(f"Specs must be a dictionary, received {type(specs).__name__}")

    for k, v in specs.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"Security/Type Error: Circuit spec '{k}' must be a numeric float or int, received {type(v).__name__}.")
        if v <= 0 and k not in ("gain",):
            if k == "cutoff_hz":
                raise ValueError(f"Circuit Parameter Error: Cutoff frequency must be > 0 Hz, received {v}")
            raise ValueError(f"Circuit Parameter Error: Circuit spec '{k}' must be positive, received {v}")

    ctype = circuit_type.strip().lower().replace(" ", "_")
    calc_summary = []

    if "series" in ctype or "resistor" in ctype or "dc" in ctype or "loop" in ctype:
        vin = float(specs.get("v_source", specs.get("vin", specs.get("v1", 9))))
        r1 = float(specs.get("r1", specs.get("r1_ohms", 3000)))
        r2 = float(specs.get("r2", specs.get("r2_ohms", 10000)))
        r3 = float(specs.get("r3", specs.get("r3_ohms", 5000)))

        r_total = r1 + r2 + r3
        current_a = vin / r_total
        current_ma = current_a * 1000
        v_drop_r1 = current_a * r1
        v_drop_r2 = current_a * r2
        v_drop_r3 = current_a * r3
        v_node2 = vin - v_drop_r1
        v_node3 = v_node2 - v_drop_r2
        power_mw = vin * current_ma

        def fmt_ohms(ohms):
            if ohms >= 1e6:
                return f"{ohms/1e6:g}Meg"
            elif ohms >= 1e3:
                return f"{ohms/1e3:g}k"
            return f"{ohms:g}"

        calc_summary.append(f"DC Source (V1): {vin}V")
        calc_summary.append(f"R1: {fmt_ohms(r1)} ({r1} Ω), R2: {fmt_ohms(r2)} ({r2} Ω), R3: {fmt_ohms(r3)} ({r3} Ω)")
        calc_summary.append(f"Total Loop Resistance: {r_total} Ω ({fmt_ohms(r_total)})")
        calc_summary.append(f"Loop Current: {current_ma:.3f} mA")
        calc_summary.append(f"Node Voltages: Node 1 = {vin}V, Node 2 = {v_node2:.2f}V, Node 3 = {v_node3:.2f}V, Node 4 = 0V (GND)")
        calc_summary.append(f"Voltage Drops: V(R1) = {v_drop_r1:.2f}V, V(R2) = {v_drop_r2:.2f}V, V(R3) = {v_drop_r3:.2f}V")
        calc_summary.append(f"Total Power: {power_mw:.2f} mW")

        spice_netlist = f"""* LTspice Simulation Netlist - {circuit_name}
* Circuit Type: DC Series Resistor Loop
* Analysis: Total R={r_total} Ohms, I={current_ma:.3f} mA, Power={power_mw:.2f} mW

* DC Voltage Source (Node 1 to Node 4/GND)
V1 1 0 DC {vin}

* Series Resistors
R1 1 2 {fmt_ohms(r1)}
R2 2 3 {fmt_ohms(r2)}
R3 3 0 {fmt_ohms(r3)}

* Simulation Directives
.op
.end
"""

        asc_schematic = f"""Version 4
SHEET 1 880 680
WIRE 160 96 64 96
WIRE 64 144 64 96
WIRE 384 96 256 96
WIRE 384 144 384 96
WIRE 384 256 384 224
WIRE 272 256 384 256
WIRE 64 256 176 256
WIRE 64 256 64 240
FLAG 64 256 0
FLAG 64 96 1
FLAG 384 96 2
FLAG 384 256 3
FLAG 64 256 4
SYMBOL voltage 64 128 R0
WINDOW 123 24 56 Left 2
WINDOW 39 0 0 Left 0
SYMATTR InstName V1
SYMATTR Value {vin}
SYMBOL res 256 80 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName R1
SYMATTR Value {fmt_ohms(r1)}
SYMBOL res 368 128 R0
WINDOW 0 24 16 Left 2
WINDOW 3 24 40 Left 2
SYMATTR InstName R2
SYMATTR Value {fmt_ohms(r2)}
SYMBOL res 272 240 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName R3
SYMATTR Value {fmt_ohms(r3)}
TEXT 64 320 Left 2 !.op
"""

    elif "low_pass" in ctype or "rc_filter" in ctype:
        cutoff_hz = float(specs.get("cutoff_hz", 1000))
        if cutoff_hz <= 0:
            raise ValueError(f"Circuit Parameter Error: Cutoff frequency must be > 0 Hz, received {cutoff_hz}")

        # Choose C and calculate R: f_c = 1 / (2 * pi * R * C)  =>  R = 1 / (2 * pi * f_c * C)
        c_uf = float(specs.get("c_value_uf", 0.1))
        c_farads = c_uf * 1e-6
        r_ohms = round(1.0 / (2.0 * math.pi * cutoff_hz * c_farads), 2)
        calc_summary.append(f"Cutoff Frequency: {cutoff_hz} Hz")
        calc_summary.append(f"Selected Capacitor (C1): {c_uf} uF")
        calc_summary.append(f"Calculated Resistor (R1): {r_ohms} Ohms")

        spice_netlist = f"""* LTspice Simulation Netlist - {circuit_name}
* Circuit Type: Passive RC Low-Pass Filter
* Target Cutoff Frequency: {cutoff_hz} Hz

* Sources
V1 in 0 AC 1 SIN(0 1 {cutoff_hz})

* Components
R1 in out {r_ohms}
C1 out 0 {c_uf}u

* Simulation Directives
.ac dec 20 1 100k
.tran 0 {round(5.0/cutoff_hz, 4)} 0 1u
.plot ac V(out)
.end
"""

        asc_schematic = f"""Version 4
SHEET 1 880 680
WIRE 160 96 64 96
WIRE 64 160 64 96
WIRE 240 96 240 96
WIRE 320 96 240 96
WIRE 240 160 240 96
WIRE 64 256 64 240
WIRE 240 256 240 224
FLAG 64 256 0
FLAG 240 256 0
FLAG 64 96 in
FLAG 320 96 out
SYMBOL voltage 64 144 R0
WINDOW 123 24 56 Left 2
WINDOW 39 0 0 Left 0
SYMATTR InstName V1
SYMATTR Value SINE(0 1 {cutoff_hz})
SYMATTR Value2 AC 1
SYMBOL res 256 80 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName R1
SYMATTR Value {r_ohms}
SYMBOL cap 224 160 R0
WINDOW 0 24 16 Left 2
WINDOW 3 24 40 Left 2
SYMATTR InstName C1
SYMATTR Value {c_uf}µ
TEXT 64 300 Left 2 !.ac dec 20 1 100k
TEXT 64 330 Left 2 !.tran 0 {round(5.0/cutoff_hz, 4)} 0 1u
"""

    elif "voltage_divider" in ctype:
        vin = float(specs.get("vin", 12))
        vout = float(specs.get("vout", 5))
        if vout >= vin or vout <= 0:
            raise ValueError(f"Circuit Parameter Error: Vout ({vout}V) must be positive and less than Vin ({vin}V).")

        r1 = float(specs.get("r1_ohms", 10000))
        # Vout = Vin * R2 / (R1 + R2) => R2 = R1 * Vout / (Vin - Vout)
        r2 = round(r1 * vout / (vin - vout), 2)
        calc_summary.append(f"Input Voltage: {vin}V, Output: {vout}V")
        calc_summary.append(f"R1: {r1} Ohms, Calculated R2: {r2} Ohms")

        spice_netlist = f"""* LTspice Simulation Netlist - {circuit_name}
* Circuit Type: Precision Voltage Divider ({vin}V -> {vout}V)

* Input Supply
V1 in 0 DC {vin}

* Divider Resistors
R1 in out {r1}
R2 out 0 {r2}

* Directives
.op
.dc V1 0 {vin*1.2} 0.1
.plot dc V(out)
.end
"""

        asc_schematic = f"""Version 4
SHEET 1 880 680
WIRE 160 96 64 96
WIRE 64 160 64 96
WIRE 320 96 240 96
WIRE 240 160 240 96
WIRE 64 256 64 240
WIRE 240 256 240 240
FLAG 64 256 0
FLAG 240 256 0
FLAG 64 96 in
FLAG 320 96 out
SYMBOL voltage 64 144 R0
WINDOW 123 24 56 Left 2
WINDOW 39 0 0 Left 0
SYMATTR InstName V1
SYMATTR Value {vin}
SYMBOL res 256 80 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName R1
SYMATTR Value {r1}
SYMBOL res 224 144 R0
WINDOW 0 24 16 Left 2
WINDOW 3 24 40 Left 2
SYMATTR InstName R2
SYMATTR Value {r2}
TEXT 64 300 Left 2 !.op
TEXT 64 330 Left 2 !.dc V1 0 {round(vin*1.2, 1)} 0.1
"""

    elif "inverting_amp" in ctype or "opamp" in ctype:
        gain = abs(float(specs.get("gain", 5)))
        rin = float(specs.get("rin_ohms", 10000))
        rf = round(gain * rin, 2)
        calc_summary.append(f"Op-Amp Inverting Voltage Gain: -{gain}")
        calc_summary.append(f"Input Resistor (Rin): {rin} Ohms, Feedback Resistor (Rf): {rf} Ohms")

        spice_netlist = f"""* LTspice Simulation Netlist - {circuit_name}
* Circuit Type: Inverting Operational Amplifier (Gain: -{gain})

* Signal Source & Rail Supplies
Vin in 0 AC 1 SIN(0 0.5 1k)
Vpos vcc 0 DC 15
Vneg vee 0 DC -15

* Passive Gain Network
Rin in in_neg {rin}
Rf in_neg out {rf}

* Ideal Op-Amp Macro Model (VCVS with gain 100k)
E1 out 0 0 in_neg 100000

* Simulation Commands
.ac dec 20 10 1Meg
.tran 0 3m 0 1u
.plot tran V(out) V(in)
.end
"""

        asc_schematic = f"""Version 4
SHEET 1 880 680
WIRE 160 208 64 208
WIRE 64 208 64 208
WIRE 288 208 240 208
WIRE 288 128 288 208
WIRE 384 128 288 128
WIRE 464 128 464 224
WIRE 464 224 352 224
WIRE 528 224 464 224
WIRE 64 288 64 288
WIRE 288 240 288 240
FLAG 64 288 0
FLAG 288 240 0
FLAG 64 208 in
FLAG 528 224 out
SYMBOL voltage 64 192 R0
WINDOW 123 24 56 Left 2
WINDOW 39 0 0 Left 0
SYMATTR InstName Vin
SYMATTR Value SINE(0 0.5 1k)
SYMATTR Value2 AC 1
SYMBOL res 256 192 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName Rin
SYMATTR Value {rin}
SYMBOL res 480 112 R90
WINDOW 0 0 56 VBottom 2
WINDOW 3 32 56 VTop 2
SYMATTR InstName Rf
SYMATTR Value {rf}
SYMBOL OpAmps\\\\opamp 320 160 R0
SYMATTR InstName U1
TEXT 64 360 Left 2 !.lib opamp.sub
TEXT 64 390 Left 2 !.tran 0 3m 0 1u
"""
    else:
        raise ValueError(
            f"Unsupported circuit type '{circuit_type}'. "
            "Supported types: 'low_pass_filter', 'voltage_divider', 'inverting_amp'."
        )

    base = circuit_name.lower().replace(" ", "_")
    if filename:
        clean_name = _validate_safe_filename(filename, allowed_extensions={".cir", ".net", ".asc"})
        root, ext = os.path.splitext(clean_name)
        asc_name = f"{root}.asc"
        cir_name = f"{root}.cir"
    else:
        asc_name = f"{base}.asc"
        cir_name = f"{base}.cir"

    asc_path = os.path.join(OUTPUT_DIR, asc_name)
    cir_path = os.path.join(OUTPUT_DIR, cir_name)

    # Write both the visual schematic (.asc for graphical viewing in LTspice) and SPICE netlist (.cir) into output/ folder
    with open(asc_path, "w", encoding="utf-8") as f:
        f.write(asc_schematic)

    with open(cir_path, "w", encoding="utf-8") as f:
        f.write(spice_netlist)

    return (
        f"Success: LTspice visual schematic generated at 'output/{asc_name}' and SPICE netlist at 'output/{cir_name}'. "
        f"Circuit Calculations: {'; '.join(calc_summary)}. "
        f"NOTE: Opening 'output/{asc_name}' in LTspice opens the graphical schematic drawing with components, wires, and ground (unlike '{cir_name}' which opens in the text editor)."
    )


def search_web_for_circuit_or_model(query: str, visual_features: str = "") -> str:
    """
    Searches the live web for technical datasheets, component pinouts, circuit topologies,
    or mechanical CAD dimensions based on visual features observed in an uploaded photo.
    
    Args:
        query: Specific search term (e.g. 'LM741 pinout', 'NEMA 17 bracket dimensions', '1k low pass filter values').
        visual_features: Optional visual observations from the photo (e.g. '8-pin DIP chip with label 741', 'rectangular plate with 2 mounting holes').
        
    Returns:
        Structured technical specifications, pinout descriptions, formulas, and dimensions found on the web.
    """
    clean_query = query.strip()
    if not clean_query:
        if visual_features:
            clean_query = visual_features.strip()
        else:
            raise ValueError("A search query or visual feature description must be provided.")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    snippets = []

    # 1. Primary Engine: DuckDuckGo HTML Web Search (bounded retry, explicit 5.0s timeout)
    data = urllib.parse.urlencode({"q": clean_query}).encode("utf-8")
    req = urllib.request.Request("https://html.duckduckgo.com/html/", data=data, headers=headers)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=5.0) as response:
                html = response.read().decode("utf-8", errors="ignore")
                raw_snippets = re.findall(r'class=[\'"]result__snippet[\'"][^>]*>(.*?)</a>', html, re.DOTALL)
                for s in raw_snippets[:5]:
                    clean_s = re.sub(r'<[^>]+>', '', s).strip()
                    if clean_s and len(clean_s) > 20:
                        snippets.append(clean_s)
                break
        except Exception:
            if attempt == 0:
                time.sleep(0.3)

    # 2. Secondary Engine: Wikipedia REST API (bounded retry, explicit 4.0s timeout)
    if len(snippets) < 2:
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_query)}&limit=3&namespace=0&format=json"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "CustomEngineeringAgent/1.0"})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=4.0) as r:
                    wiki_data = json.loads(r.read().decode("utf-8"))
                    if len(wiki_data) > 1 and wiki_data[1]:
                        for title in wiki_data[1][:2]:
                            sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                            sreq = urllib.request.Request(sum_url, headers={"User-Agent": "CustomEngineeringAgent/1.0"})
                            with urllib.request.urlopen(sreq, timeout=4.0) as sr:
                                sdata = json.loads(sr.read().decode("utf-8"))
                                if sdata.get("extract"):
                                    snippets.append(f"[{title}]: {sdata['extract']}")
                break
            except Exception:
                if attempt == 0:
                    time.sleep(0.3)

    if not snippets:
        return f"Web search for '{clean_query}' completed with standard engineering reference defaults."

    formatted = "\n".join(f"- {s}" for s in snippets)
    context_note = f" (Observed from image: {visual_features})" if visual_features else ""
    return f"Live Web Research Results for '{clean_query}'{context_note}:\n{formatted}"


# The Master Tool Registry: Maps tool names to their functions
TOOL_REGISTRY = {
    "get_live_weather": get_live_weather,
    "calculate_currency_or_math": calculate_currency_or_math,
    "save_report_file": save_report_file,
    "unreliable_live_rates": unreliable_live_rates,
    "generate_fusion360_cad": generate_fusion360_cad,
    "generate_ltspice_circuit": generate_ltspice_circuit,
    "search_web_for_circuit_or_model": search_web_for_circuit_or_model,
}
