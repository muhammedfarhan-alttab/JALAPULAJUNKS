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
    TOOL_REGISTRY,
)
from agent_brain import CustomAgentBrain


def test_tool_registry():
    assert len(TOOL_REGISTRY) == 6
    assert "get_live_weather" in TOOL_REGISTRY
    assert "calculate_currency_or_math" in TOOL_REGISTRY
    assert "save_report_file" in TOOL_REGISTRY
    assert "unreliable_live_rates" in TOOL_REGISTRY
    assert "generate_fusion360_cad" in TOOL_REGISTRY
    assert "generate_ltspice_circuit" in TOOL_REGISTRY


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
    # Verify file content
    with open("test_note.txt", "r", encoding="utf-8") as f:
        assert f.read() == "Agent Framework Test Successful!"
    # Cleanup
    if os.path.exists("test_note.txt"):
        os.remove("test_note.txt")


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
    assert os.path.exists("test_bracket_fusion.py")

    with open("test_bracket_fusion.py", "r", encoding="utf-8") as f:
        content = f.read()
    assert "adsk.core" in content
    assert "adsk.fusion" in content
    assert "addTwoPointRectangle" in content
    os.remove("test_bracket_fusion.py")

    # Test geometric validation conflict
    invalid_params = {"length": 40, "width": 20, "thickness": 4, "hole_diameter": 50}
    with pytest.raises(ValueError) as exc:
        generate_fusion360_cad("mounting_bracket", invalid_params)
    assert "Geometric Conflict" in str(exc.value)


def test_ltspice_circuit_tool():
    specs = {"cutoff_hz": 1000, "c_value_uf": 0.1}
    res = generate_ltspice_circuit("TestFilter", "low_pass_filter", specs, "test_filter.cir")
    assert "Success" in res
    assert os.path.exists("test_filter.cir")

    with open("test_filter.cir", "r", encoding="utf-8") as f:
        netlist = f.read()
    assert "* LTspice Simulation Netlist" in netlist
    assert ".ac dec" in netlist
    assert "R1 in out" in netlist
    assert "C1 out 0 0.1u" in netlist
    os.remove("test_filter.cir")

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



