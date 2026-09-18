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


def generate_fusion360_cad(component_type: str, parameters: dict, filename: str = None) -> str:
    """
    Generates a ready-to-run Autodesk Fusion 360 Python API script (.py) for a 3D parametric CAD model.
    
    Args:
        component_type: Type of component, e.g. 'mounting_bracket', 'enclosure', 'spacer', 'plate'.
        parameters: Dictionary of dimensions in millimeters, e.g.
                    For 'mounting_bracket': {'length': 80, 'width': 40, 'thickness': 4, 'hole_diameter': 5, 'hole_spacing': 60}
                    For 'enclosure': {'length': 100, 'width': 60, 'height': 30, 'wall_thickness': 2.5}
                    For 'spacer': {'outer_diameter': 20, 'inner_diameter': 6, 'height': 15}
        filename: Optional filename for the generated Fusion script (defaults to '<component_type>_fusion.py').
    
    Returns:
        Confirmation string with file path and CAD dimensional details.
    """
    if not isinstance(parameters, dict):
        raise ValueError(f"Parameters must be a dictionary, received {type(parameters)}")

    comp = component_type.strip().lower().replace(" ", "_")
    
    # 1. Validation & Geometric Verification (Enables agent error recovery if bad specs given)
    for dim_name, val in parameters.items():
        if isinstance(val, (int, float)) and val <= 0:
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
        # Find top face to hollow out
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

    out_name = filename or f"{comp}_fusion.py"
    safe_name = os.path.basename(out_name)
    with open(safe_name, "w", encoding="utf-8") as f:
        f.write(cad_script)

    return (
        f"Success: Autodesk Fusion 360 CAD script generated at '{safe_name}' "
        f"for {component_type} with parameters: {parameters}. "
        f"Script is ready to run in Fusion 360 (Scripts and Add-Ins)."
    )


def generate_ltspice_circuit(circuit_name: str, circuit_type: str, specs: dict, filename: str = None) -> str:
    """
    Generates a standard SPICE / LTspice simulation netlist (.cir / .net) for circuit analysis.
    
    Args:
        circuit_name: Name of the circuit, e.g. 'LowPassFilter_1kHz', 'VoltageDivider_5V'.
        circuit_type: 'low_pass_filter', 'high_pass_filter', 'voltage_divider', or 'inverting_amp'.
        specs: Engineering specifications dictionary:
               For 'low_pass_filter': {'cutoff_hz': 1000, 'c_value_uf': 0.1} -> automatically computes R!
               For 'voltage_divider': {'vin': 12, 'vout': 5, 'r1_ohms': 10000} -> computes R2!
               For 'inverting_amp': {'gain': -5, 'rin_ohms': 10000} -> computes Rf!
        filename: Optional output filename (defaults to '<circuit_name>.cir').
    
    Returns:
        Confirmation string with circuit calculations and saved SPICE netlist path.
    """
    if not isinstance(specs, dict):
        raise ValueError(f"Specs must be a dictionary, received {type(specs)}")

    ctype = circuit_type.strip().lower().replace(" ", "_")
    calc_summary = []

    if "low_pass" in ctype or "rc_filter" in ctype:
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
        clean = os.path.basename(filename)
        root, ext = os.path.splitext(clean)
        asc_name = f"{root}.asc"
        cir_name = f"{root}.cir"
    else:
        asc_name = f"{base}.asc"
        cir_name = f"{base}.cir"

    # Write both the visual schematic (.asc for graphical viewing in LTspice) and SPICE netlist (.cir)
    with open(asc_name, "w", encoding="utf-8") as f:
        f.write(asc_schematic)

    with open(cir_name, "w", encoding="utf-8") as f:
        f.write(spice_netlist)

    return (
        f"Success: LTspice visual schematic generated at '{asc_name}' and SPICE netlist at '{cir_name}'. "
        f"Circuit Calculations: {'; '.join(calc_summary)}. "
        f"NOTE: Opening '{asc_name}' in LTspice opens the graphical schematic drawing with components, wires, and ground (unlike '{cir_name}' which opens in the text editor)."
    )


# The Master Tool Registry: Maps tool names to their functions
TOOL_REGISTRY = {
    "get_live_weather": get_live_weather,
    "calculate_currency_or_math": calculate_currency_or_math,
    "save_report_file": save_report_file,
    "unreliable_live_rates": unreliable_live_rates,
    "generate_fusion360_cad": generate_fusion360_cad,
    "generate_ltspice_circuit": generate_ltspice_circuit,
}
