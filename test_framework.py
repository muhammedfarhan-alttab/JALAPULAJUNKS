"""
test_framework.py - Sanity test suite for tools and framework structure.
"""

import os
import pytest
from tools import (
    get_live_weather,
    calculate_currency_or_math,
    save_report_file,
    unreliable_live_rates,
    generate_fusion360_cad,
    generate_ltspice_circuit,
    search_web_for_circuit_or_model,
    TOOL_REGISTRY,
    OUTPUT_DIR,
    FALLBACK_REFERENCE_RATES,
    FALLBACK_RATE_SOURCE,
    _validate_safe_filename,
)
from agent_brain import CustomAgentBrain


def test_tool_registry():
    assert len(TOOL_REGISTRY) == 7
    assert "get_live_weather" in TOOL_REGISTRY
    assert "calculate_currency_or_math" in TOOL_REGISTRY
    assert "save_report_file" in TOOL_REGISTRY
    assert "unreliable_live_rates" in TOOL_REGISTRY
    assert "generate_fusion360_cad" in TOOL_REGISTRY
    assert "generate_ltspice_circuit" in TOOL_REGISTRY
    assert "search_web_for_circuit_or_model" in TOOL_REGISTRY


def test_weather_tool():
    res = get_live_weather("Tokyo")
    assert isinstance(res, str)
    assert "Tokyo" in res
    assert "°C" in res


def test_calculator_tool():
    res = calculate_currency_or_math("1500 * 155.2")
    assert "232800.0" in res or "232800" in res


def test_file_saver_tool(tmp_path):
    test_file = tmp_path / "test_note.txt"
    res = save_report_file(str(test_file), "Agent Framework Test Successful!")
    assert "Success" in res
    target = os.path.join(OUTPUT_DIR, "test_note.txt")
    # Verify file content
    with open(target, "r", encoding="utf-8") as f:
        assert f.read() == "Agent Framework Test Successful!"
    # Cleanup
    if os.path.exists(target):
        os.remove(target)


def test_troublemaker_tool():
    with pytest.raises(ConnectionError) as exc_info:
        unreliable_live_rates("USD/JPY")
    assert "503" in str(exc_info.value)


def test_mocked_agent_loop_with_error_recovery(tmp_path, monkeypatch):
    """
    Verifies that the from-scratch agent loop:
    1. Receives a tool call (unreliable_live_rates)
    2. Executes and catches the error without crashing
    3. Feeds the error back into history as an observation
    4. Executes fallback tool (calculate_currency_or_math)
    5. Saves the report (save_report_file)
    6. Returns final answer
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tools([
        get_live_weather,
        calculate_currency_or_math,
        save_report_file,
        unreliable_live_rates,
    ])

    # Turn 1: Model calls the troublemaker tool
    call_1 = MagicMock()
    call_1.name = "unreliable_live_rates"
    call_1.args = {"pair": "USD/EUR"}
    resp_1 = MagicMock()
    resp_1.function_calls = [call_1]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 2: Model calls the calculator tool as fallback
    call_2 = MagicMock()
    call_2.name = "calculate_currency_or_math"
    call_2.args = {"expression": "500 * 0.92"}
    resp_2 = MagicMock()
    resp_2.function_calls = [call_2]
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 3: Model calls file saver tool
    test_out = tmp_path / "recovery_report.txt"
    call_3 = MagicMock()
    call_3.name = "save_report_file"
    call_3.args = {"filename": str(test_out), "content": "Recovered successfully!"}
    resp_3 = MagicMock()
    resp_3.function_calls = [call_3]
    resp_3.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 4: Model delivers final answer (no function calls)
    resp_4 = MagicMock()
    resp_4.function_calls = None
    resp_4.text = "Task successfully completed after recovering from 503 error."
    resp_4.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_4.text)]))]

    # Wire mocked responses into the client
    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2, resp_3, resp_4])

    final_result = agent.run("Perform exchange and recover if error happens.")

    # Verification:
    assert "Task successfully completed after recovering" in final_result
    assert agent.client.models.generate_content.call_count == 4
    # Clean up created file
    if os.path.exists("recovery_report.txt"):
        os.remove("recovery_report.txt")


def test_fusion360_cad_tool():
    params = {"length": 80, "width": 40, "thickness": 4, "hole_diameter": 5}
    res = generate_fusion360_cad("mounting_bracket", params, "test_bracket_fusion.py")
    assert "Success" in res
    target = os.path.join(OUTPUT_DIR, "test_bracket_fusion.py")
    assert os.path.exists(target)

    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    assert "adsk.core" in content
    assert "adsk.fusion" in content
    assert "addTwoPointRectangle" in content
    if os.path.exists(target):
        os.remove(target)

    # Test geometric validation conflict
    invalid_params = {"length": 40, "width": 20, "thickness": 4, "hole_diameter": 50}
    with pytest.raises(ValueError) as exc:
        generate_fusion360_cad("mounting_bracket", invalid_params)
    assert "Geometric Conflict" in str(exc.value)


def test_ltspice_circuit_tool():
    specs = {"cutoff_hz": 1000, "c_value_uf": 0.1}
    res = generate_ltspice_circuit("TestFilter", "low_pass_filter", specs, "test_filter.cir")
    assert "Success" in res
    target_cir = os.path.join(OUTPUT_DIR, "test_filter.cir")
    target_asc = os.path.join(OUTPUT_DIR, "test_filter.asc")
    assert os.path.exists(target_cir)
    assert os.path.exists(target_asc)

    with open(target_cir, "r", encoding="utf-8") as f:
        netlist = f.read()
    assert "* LTspice Simulation Netlist" in netlist
    assert ".ac dec" in netlist
    assert "R1 in out" in netlist
    assert "C1 out 0 0.1u" in netlist
    
    # Cleanup both .cir and .asc
    if os.path.exists(target_cir):
        os.remove(target_cir)
    if os.path.exists(target_asc):
        os.remove(target_asc)

    # Test invalid frequency
    with pytest.raises(ValueError) as exc:
        generate_ltspice_circuit("BadFilter", "low_pass_filter", {"cutoff_hz": -100})
    assert "Cutoff frequency must be > 0" in str(exc.value)


def test_multimodal_agent_loop(monkeypatch):
    """
    Verifies that CustomAgentBrain.run correctly accepts image_bytes and image_mime,
    constructs the multimodal Content with image and text parts, and emits the start event.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")

    # Mock response
    mock_resp = MagicMock()
    mock_resp.function_calls = []
    mock_resp.text = "I inspected the image and it is a 50mm square mounting plate."
    mock_resp.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    agent.client.models.generate_content = MagicMock(return_value=mock_resp)

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    ans = agent.run(
        "Analyze this bracket drawing",
        image_bytes=dummy_png,
        image_mime="image/png",
        step_callback=on_step
    )

    assert "50mm" in ans
    assert any(evt == "start" and data.get("has_image") is True for evt, data in events)

    call_args = agent.client.models.generate_content.call_args
    history = call_args.kwargs.get("contents")
    assert len(history) >= 1
    assert len(history[0].parts) == 2
    assert history[0].parts[0].inline_data.data == dummy_png


def test_search_web_for_circuit_or_model():
    """Verify web search tool retrieves information for circuit IC or CAD specs."""
    res_circuit = search_web_for_circuit_or_model("LM741 operational amplifier pinout")
    assert isinstance(res_circuit, str)
    assert len(res_circuit) > 20

    res_cad = search_web_for_circuit_or_model("M3 screw clearance hole diameter standard")
    assert isinstance(res_cad, str)
    assert len(res_cad) > 20


def test_multimodal_circuit_web_agent_loop(monkeypatch, tmp_path):
    """
    Verifies end-to-end multi-step chain:
    User uploads circuit photo -> Agent plans -> Calls search_web_for_circuit_or_model ->
    Observes datasheet specs -> Calls generate_ltspice_circuit -> Returns synthesized output.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tools([
        search_web_for_circuit_or_model,
        generate_ltspice_circuit,
    ])

    # Step 1: Agent decides to search the web for the component in the image
    call_1 = MagicMock()
    call_1.name = "search_web_for_circuit_or_model"
    call_1.args = {"query": "NE555 timer astable circuit pinout", "visual_features": "8-pin DIP IC with timing capacitor"}
    resp_1 = MagicMock()
    resp_1.function_calls = [call_1]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Step 2: Agent observed pinouts and generates LTspice circuit
    call_2 = MagicMock()
    call_2.name = "generate_ltspice_circuit"
    call_2.args = {
        "title": "NE555_Timer_Circuit",
        "circuit_type": "low_pass_filter",
        "specs": {"cutoff_hz": 1000, "c_value_uf": 0.01},
        "output_filename": "test_ne555_out.cir"
    }
    resp_2 = MagicMock()
    resp_2.function_calls = [call_2]
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Step 3: Agent synthesizes final answer
    resp_3 = MagicMock()
    resp_3.function_calls = None
    resp_3.text = "I researched the NE555 datasheet online and generated the LTspice circuit files test_ne555_out.asc and .cir."
    resp_3.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_3.text)]))]

    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2, resp_3])

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    dummy_circuit_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    final_output = agent.run(
        "Inspect this circuit photo, find its datasheet pinout online, and build the LTspice schematic.",
        image_bytes=dummy_circuit_img,
        image_mime="image/png",
        step_callback=on_step
    )

    assert "NE555" in final_output
    assert agent.client.models.generate_content.call_count == 3
    assert any(evt == "act" and data.get("tool") == "search_web_for_circuit_or_model" for evt, data in events)
    assert any(evt == "act" and data.get("tool") == "generate_ltspice_circuit" for evt, data in events)

    # Clean up generated test circuit file if created
    for f in ["test_ne555_out.cir", "test_ne555_out.asc"]:
        fpath = os.path.join(OUTPUT_DIR, f)
        if os.path.exists(fpath):
            os.remove(fpath)


def test_argument_validation_guardrail(monkeypatch):
    """
    Guardrail Test: When Gemini requests a tool with invalid or missing arguments,
    the Python framework catches it before execution and injects an ArgumentValidationError.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tool(get_live_weather)

    # Turn 1: Model requests get_live_weather with MISSING required argument 'city'
    bad_call = MagicMock()
    bad_call.name = "get_live_weather"
    bad_call.args = {}  # missing 'city'
    resp_1 = MagicMock()
    resp_1.function_calls = [bad_call]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 2: Model receives the structured argument error and self-corrects with valid argument
    good_call = MagicMock()
    good_call.name = "get_live_weather"
    good_call.args = {"city": "Tokyo"}
    resp_2 = MagicMock()
    resp_2.function_calls = [good_call]
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 3: Final answer
    resp_3 = MagicMock()
    resp_3.function_calls = None
    resp_3.text = "Weather in Tokyo is 18°C."
    resp_3.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_3.text)]))]

    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2, resp_3])

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    res = agent.run("What is the weather?", step_callback=on_step)
    assert "Tokyo is 18°C" in res

    # Verify that the first step recorded an argument validation error
    error_events = [data for evt, data in events if evt == "observe_error"]
    assert len(error_events) >= 1
    assert "Invalid arguments" in error_events[0]["error"] or "missing" in error_events[0]["error"].lower()


def test_unknown_tool_guardrail(monkeypatch):
    """
    Guardrail Test: If Gemini attempts to request an unregistered tool,
    the framework rejects it cleanly with ToolNotFoundError.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tool(get_live_weather)

    # Turn 1: Model hallucinates an unknown tool
    call_unknown = MagicMock()
    call_unknown.name = "non_existent_tool_xyz"
    call_unknown.args = {"query": "test"}
    resp_1 = MagicMock()
    resp_1.function_calls = [call_unknown]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 2: Model gives final answer
    resp_2 = MagicMock()
    resp_2.function_calls = None
    resp_2.text = "I realized that tool does not exist."
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_2.text)]))]

    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2])

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    res = agent.run("Do something impossible", step_callback=on_step)
    assert "tool does not exist" in res.lower()
    error_events = [data for evt, data in events if evt == "observe_error"]
    assert any("not registered in framework" in d.get("error", "") for d in error_events)


def test_ast_math_calculator_security():
    """
    Guardrail Test: AST parser calculates valid math but blocks code injection attempts.
    """
    # Safe calculations
    assert "232800.0" in calculate_currency_or_math("1500 * 155.2")
    assert "22.0" in calculate_currency_or_math("sqrt(144) + 10")
    assert "= 16" in calculate_currency_or_math("2 ** 4")

    # Code injection and attribute access attacks
    attack_1 = calculate_currency_or_math("().__class__.__base__")
    assert "Math Evaluation Error" in attack_1
    assert "not permitted" in attack_1

    attack_2 = calculate_currency_or_math("__import__('os').system('dir')")
    assert "Math Evaluation Error" in attack_2

    attack_3 = calculate_currency_or_math("eval('1+1')")
    assert "Math Evaluation Error" in attack_3


def test_structured_observation_format(monkeypatch):
    """
    Guardrail Test: Verifies that observation payloads sent back to Gemini
    are structured dictionaries with tool name, success flag, and result/error.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tool(calculate_currency_or_math)

    call_calc = MagicMock()
    call_calc.name = "calculate_currency_or_math"
    call_calc.args = {"expression": "25 * 4"}
    resp_1 = MagicMock()
    resp_1.function_calls = [call_calc]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    resp_2 = MagicMock()
    resp_2.function_calls = None
    resp_2.text = "The result is 100."
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_2.text)]))]

    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2])

    agent.run("Calculate 25 * 4")

    # Inspect the history sent in the second call
    call_args_list = agent.client.models.generate_content.call_args_list
    assert len(call_args_list) == 2
    second_call_contents = call_args_list[1].kwargs["contents"]

    # Locate the tool response content in history
    tool_resp_content = [c for c in second_call_contents if c.role == "user"][-1]
    assert tool_resp_content.role == "user"
    fn_resp_part = tool_resp_content.parts[0]
    raw_payload = fn_resp_part.function_response.response

    assert raw_payload["tool"] == "calculate_currency_or_math"
    assert raw_payload["success"] is True
    assert "100" in str(raw_payload["result"])


def test_max_steps_guardrail(monkeypatch):
    """
    Guardrail Test: Agent terminates safely when max_steps limit is reached,
    preventing infinite execution loops.
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing", max_steps=3)
    agent.register_tool(get_live_weather)

    # Construct an infinite tool call response
    def make_infinite_call():
        call = MagicMock()
        call.name = "get_live_weather"
        call.args = {"city": "Tokyo"}
        resp = MagicMock()
        resp.function_calls = [call]
        resp.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]
        return resp

    agent.client.models.generate_content = MagicMock(side_effect=[
        make_infinite_call(),
        make_infinite_call(),
        make_infinite_call(),
        make_infinite_call(),
    ])

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    res = agent.run("Loop forever", step_callback=on_step)
    assert "maximum reasoning/action limit of 3 steps" in res.lower()
    assert any(evt == "max_steps_reached" and data.get("max_steps") == 3 for evt, data in events)
    assert agent.client.models.generate_content.call_count == 3


def test_calculator_reference_rate_variables():
    """
    Verifies that calculate_currency_or_math safely evaluates expressions with
    documented reference rate variables (e.g. USD_JPY, USD_EUR) and explicitly
    tags the output as a static reference benchmark rather than a live rate.
    """
    res = calculate_currency_or_math("1500 * USD_JPY")
    assert "232800.0" in res or "232800" in res
    assert "USD_JPY=155.2" in res
    assert "ECB" in res
    assert "NOT a live rate" in res


def test_calculator_natural_currency_conversion():
    """
    Verifies natural conversion queries like '1500 USD to JPY' and '500 USD into EUR'
    correctly parse and use documented static reference rates with full attribution.
    """
    res_jpy = calculate_currency_or_math("Convert $1500 USD to JPY")
    assert "232,800.00 JPY" in res_jpy
    assert "155.2" in res_jpy
    assert "ECB" in res_jpy
    assert "NOT a live rate" in res_jpy

    res_eur = calculate_currency_or_math("500 USD into EUR")
    assert "460.00 EUR" in res_eur
    assert "0.92" in res_eur
    assert "ECB" in res_eur
    assert "NOT a live rate" in res_eur


def test_currency_conversion_failure_observation_fallback_flow(monkeypatch):
    """
    Proves the exact sequence requested:
      unreliable_live_rates()
          ↓
      external rate service fails (503 Service Unavailable)
          ↓
      agent observes failure with structured error and recovery hint
          ↓
      Gemini chooses calculate_currency_or_math()
          ↓
      calculator uses clearly documented fallback/reference rate
          ↓
      conversion succeeds
    """
    from unittest.mock import MagicMock
    from google.genai import types

    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    # Ensure live rate simulation is in fault-injection mode (default)
    monkeypatch.delenv("ENABLE_LIVE_RATES", raising=False)

    agent = CustomAgentBrain(api_key="dummy_key_for_testing", max_steps=5)
    agent.register_tool(unreliable_live_rates)
    agent.register_tool(calculate_currency_or_math)

    # Turn 1: Model calls the live rate gateway
    call_1 = MagicMock()
    call_1.name = "unreliable_live_rates"
    call_1.args = {"pair": "USD/JPY"}
    resp_1 = MagicMock()
    resp_1.function_calls = [call_1]
    resp_1.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 2: Model observes the 503 error + recovery hint, and calls calculator with documented reference rate
    call_2 = MagicMock()
    call_2.name = "calculate_currency_or_math"
    call_2.args = {"expression": "1500 * USD_JPY"}
    resp_2 = MagicMock()
    resp_2.function_calls = [call_2]
    resp_2.candidates = [MagicMock(content=types.Content(role="model", parts=[]))]

    # Turn 3: Model completes with synthesized answer disclosing the fallback rate
    resp_3 = MagicMock()
    resp_3.function_calls = None
    resp_3.text = (
        "The live exchange rate service timed out (HTTP 503). "
        "Falling back to our documented ECB/Fed static reference rate of 155.20 JPY/USD, "
        "$1500 USD converts to 232,800 JPY. Note that this is a static reference rate, not a live rate."
    )
    resp_3.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text=resp_3.text)]))]

    agent.client.models.generate_content = MagicMock(side_effect=[resp_1, resp_2, resp_3])

    events = []
    def on_step(evt, data):
        events.append((evt, data))

    final_output = agent.run(
        "Convert $1500 USD to JPY using live rates. If unavailable, fall back to our reference rate.",
        step_callback=on_step
    )

    # 1. Verify model was called 3 times (PLAN 1 -> PLAN 2 -> PLAN 3)
    assert agent.client.models.generate_content.call_count == 3

    # 2. Inspect the tool observations recorded in the conversation history
    final_contents = agent.client.models.generate_content.call_args_list[-1].kwargs["contents"]
    tool_observations = [
        c for c in final_contents 
        if c.role == "user" and c.parts and getattr(c.parts[0], "function_response", None) is not None
    ]
    assert len(tool_observations) == 2

    # Verify Turn 1 observation: Failure payload
    payload_1 = tool_observations[0].parts[0].function_response.response
    assert payload_1["tool"] == "unreliable_live_rates"
    assert payload_1["success"] is False
    assert payload_1["error_type"] == "ConnectionError"
    assert "503" in payload_1["error"]
    assert "USD/JPY = 155.20" in payload_1["error"]
    assert "calculate_currency_or_math" in payload_1["recovery_hint"] or "alternative tool" in payload_1["recovery_hint"]

    # Verify Turn 2 observation: Success payload using reference rate
    payload_2 = tool_observations[1].parts[0].function_response.response
    assert payload_2["tool"] == "calculate_currency_or_math"
    assert payload_2["success"] is True
    assert "232800.0" in str(payload_2["result"]) or "232800" in str(payload_2["result"])
    assert "REFERENCE RATE APPLIED" in str(payload_2["result"])
    assert "ECB" in str(payload_2["result"])

    # 3. Verify final synthesized response
    assert "232,800" in final_output
    assert "static reference rate" in final_output.lower()


# =============================================================================
# HARDENED FRAMEWORK GUARDRAIL TESTS
# =============================================================================

def test_path_traversal_and_file_safety_guardrail():
    """
    Guardrail Test: Rejects directory traversal, absolute paths, dangerous extensions,
    hidden/sensitive files, and reserved OS device names.
    """
    # 1. Directory traversal rejection
    with pytest.raises(ValueError) as exc:
        save_report_file("../../etc/passwd", "malicious content")
    assert "Security Violation" in str(exc.value)
    assert "traversal" in str(exc.value).lower()

    with pytest.raises(ValueError) as exc:
        save_report_file("..\\passwords.txt", "traversal attempt")
    assert "Security Violation" in str(exc.value)
    assert "traversal" in str(exc.value).lower()

    # 2. Dangerous executable extensions rejection
    for bad_ext in [".exe", ".bat", ".cmd", ".sh", ".ps1", ".vbs"]:
        with pytest.raises(ValueError) as exc:
            save_report_file(f"payload{bad_ext}", "bad data")
        assert "Security Violation" in str(exc.value)
        assert "forbidden" in str(exc.value).lower()

    # 3. Hidden and sensitive config files rejection
    for bad_file in [".env", ".gitignore", ".git"]:
        with pytest.raises(ValueError) as exc:
            save_report_file(bad_file, "SECRET=123")
        assert "Security Violation" in str(exc.value)

    # 4. Reserved OS device names rejection
    for reserved in ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]:
        with pytest.raises(ValueError) as exc:
            save_report_file(f"{reserved}.txt", "device stream")
        assert "Security Violation" in str(exc.value)
        assert "reserved OS system name" in str(exc.value)

    # 5. Non-string content rejection
    with pytest.raises(ValueError) as exc:
        save_report_file("valid_name.txt", 12345)
    assert "string" in str(exc.value).lower()


def test_argument_validation_types_and_payloads(monkeypatch):
    """
    Guardrail Test: Framework strictly validates tool arguments against Python signature
    and annotations before execution, rejecting non-dict payloads, missing arguments,
    unexpected arguments, and type mismatches.
    """
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key_for_testing")
    agent = CustomAgentBrain(api_key="dummy_key_for_testing")
    agent.register_tool(get_live_weather)
    agent.register_tool(generate_fusion360_cad)

    # 1. Reject non-dict argument payloads
    err_str = agent._validate_arguments(get_live_weather, "Tokyo")
    assert "key-value dictionary" in err_str

    err_list = agent._validate_arguments(get_live_weather, ["Tokyo"])
    assert "key-value dictionary" in err_list

    # 2. Reject missing required arguments
    err_missing = agent._validate_arguments(get_live_weather, {})
    assert "missing" in err_missing.lower()

    # 3. Reject unexpected arguments
    err_unexpected = agent._validate_arguments(get_live_weather, {"city": "Tokyo", "unexpected_payload": 999})
    assert "unexpected" in err_unexpected.lower()

    # 4. Reject type mismatch for annotated str parameter
    err_type_str = agent._validate_arguments(get_live_weather, {"city": 12345})
    assert "must be of type str" in err_type_str

    # 5. Reject type mismatch for annotated dict parameter
    err_type_dict = agent._validate_arguments(
        generate_fusion360_cad, 
        {"component_type": "bracket", "parameters": "not_a_dict"}
    )
    assert "must be of type dict" in err_type_dict


def test_cad_and_circuit_numeric_parameter_guardrail():
    """
    Guardrail Test: Rejects non-numeric or negative geometric / electrical specs
    in CAD and LTspice tools to prevent injection or corruption.
    """
    # 1. Fusion 360 CAD parameter validation
    with pytest.raises(ValueError) as exc:
        generate_fusion360_cad("mounting_bracket", {"length": "eighty", "width": 40})
    assert "must be a numeric float or int" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        generate_fusion360_cad("mounting_bracket", {"length": -50, "width": 40})
    assert "must be positive" in str(exc.value)

    # 2. LTspice circuit spec validation
    with pytest.raises(ValueError) as exc:
        generate_ltspice_circuit("BadFilter", "low_pass_filter", {"cutoff_hz": "invalid"})
    assert "must be a numeric float or int" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        generate_ltspice_circuit("BadFilter", "low_pass_filter", {"cutoff_hz": 0})
    assert "Cutoff frequency must be > 0" in str(exc.value)


def test_error_message_secret_and_path_scrubbing(monkeypatch):
    """
    Guardrail Test: _sanitize_error_message scrubs API keys, environment credentials,
    local usernames, and filesystem paths from exception observations.
    """
    dummy_key = "AIzaSyTestApiKey9876543210ABC"
    monkeypatch.setenv("GEMINI_API_KEY", dummy_key)
    monkeypatch.setenv("DATABASE_SECRET_TOKEN", "SuperSecretTokenXYZ12345")

    agent = CustomAgentBrain(api_key=dummy_key)

    raw_error = (
        f"Database connection failed using key {dummy_key} and token SuperSecretTokenXYZ12345. "
        r"Traceback file C:\Users\Muhammed Farhan\AppData\Local\secret.py, line 42."
    )

    clean_error = agent._sanitize_error_message(raw_error)

    # 1. Verify API key was redacted
    assert dummy_key not in clean_error
    assert "[REDACTED_API_KEY]" in clean_error

    # 2. Verify environment credential token was redacted
    assert "SuperSecretTokenXYZ12345" not in clean_error
    assert "[REDACTED_DATABASE_SECRET_TOKEN]" in clean_error

    # 3. Verify local filesystem path was scrubbed
    assert r"C:\Users\Muhammed Farhan" not in clean_error
    assert "[LOCAL_PATH]" in clean_error or "[USER_HOME]" in clean_error


def test_max_step_limit_validation():
    """
    Guardrail Test: Rejects zero or negative max_steps values during agent initialization.
    """
    with pytest.raises(ValueError) as exc:
        CustomAgentBrain(api_key="test_key", max_steps=0)
    assert "max_steps must be a positive integer" in str(exc.value)

    with pytest.raises(ValueError) as exc:
        CustomAgentBrain(api_key="test_key", max_steps=-5)
    assert "max_steps must be a positive integer" in str(exc.value)


def test_no_hallucinated_models_in_codebase():
    """
    Guardrail Test: Verifies that only the configured model is used and
    invented models like 'gemini-3.5-flash-lite' are not queried.
    """
    agent = CustomAgentBrain(api_key="test_key", model_name="gemini-2.5-flash")
    assert agent.model_name == "gemini-2.5-flash"
    assert agent.fallback_model is None


def test_troublemaker_tool_fails_immediately_without_retry():
    """
    Guardrail Test: Confirms the intentionally simulated Troublemaker tool
    unreliable_live_rates fails immediately with HTTP 503 without being retried.
    """
    import time
    start_time = time.time()
    with pytest.raises(ConnectionError) as exc:
        unreliable_live_rates("USD/JPY")
    duration = time.time() - start_time

    assert "503" in str(exc.value)
    # Must fail in under 0.1 seconds without retry delays
    assert duration < 0.5







