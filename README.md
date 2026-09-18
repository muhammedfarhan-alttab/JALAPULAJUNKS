# 🧠 Build the Brain, Not the Puppet: Custom AI Agent Framework

A transparent, lightweight AI agent framework built completely from scratch in Python using Google Gemini.

---

## 🎯 What Makes This Different?

Most AI agents rely on heavy frameworks like **LangChain**, **CrewAI**, or **AutoGen** that hide the agent's decision-making loop inside black-box code abstractions. 

In this project, **we built the brain ourselves**:
* **No Pre-Packaged Agent Loop**: The core cycle (**`Plan -> Act -> Observe -> Repeat`**) is written in ~100 lines of standard Python (`agent_brain.py`).
* **Raw LLM Only**: The official `google-genai` SDK is used *solely* to query the Gemini model; automatic tool execution is explicitly disabled (`disable=True`).
* **Zero Hardcoded `if/else` Routing**: Gemini inspects the registered tools and autonomously decides which tool to call and with what parameters.
* **Resilient Error Recovery**: When a tool encounters an outage or exception, our framework catches it, packages the failure into an observation, and feeds it back into Gemini. The agent notices the error and recovers using an alternative tool instead of crashing.
* **Transparent Observability**: Every step (Thinking, Calling Tool, Handling Errors, Observing Results) is printed live to the terminal.

---

## 🛠️ The 7 Registered Tools

All tools are stored in a transparent Python dictionary (`TOOL_REGISTRY`) and executed exclusively by our custom Python loop:

| Tool | Purpose | Real-World Behavior |
| :--- | :--- | :--- |
| `get_live_weather` | Real-time weather lookup | Fetches live weather conditions via wttr.in JSON API (with deterministic fallback). |
| `calculate_currency_or_math` | AST Calculator & Reference Rates | Evaluates math expressions and converts currency using documented **ECB & Federal Reserve static reference benchmarks** (e.g. USD/JPY=155.20). Explicitly labeled as static reference rates, never fake live data. |
| `save_report_file` | File writer / Note-taker | Writes reports directly into the dedicated `output/` folder with path sanitization. |
| `unreliable_live_rates` | **The Troublemaker** (Chaos Test) | Chaos testing tool simulating an external banking gateway timeout (`HTTP 503 Service Unavailable`) to test error interception and fallback recovery. (Can optionally query `open.er-api.com` if `ENABLE_LIVE_RATES=true`). |
| `generate_fusion360_cad` | 3D CAD Parametric Scripting | Generates ready-to-run Autodesk Fusion 360 Python API scripts (`_fusion.py`) with geometric conflict validation. |
| `generate_ltspice_circuit` | Circuit Schematic & Netlist | Generates LTspice graphical schematics (`.asc`) and SPICE netlists (`.cir`) with component value calculation. |
| `search_web_for_circuit_or_model` | Live Web Engineering Search | Queries DuckDuckGo and Wikipedia REST API for IC pinouts, datasheets, and fastener standards. |

---

## 💱 Currency Conversion & Technical Honesty Architecture

To maintain **100% technical honesty** during hackathon demonstrations:
1. **No Fake Live Data**: We never fabricate or invent real-time market numbers.
2. **Clear Conceptual Separation**:
   ```
   unreliable_live_rates()
       ↓
   external rate service fails (HTTP 503 Timeout)
       ↓
   framework intercepts exception & builds structured observation
       ↓
   Gemini observes failure payload & recovery hint
       ↓
   Gemini autonomously selects calculate_currency_or_math()
       ↓
   calculator applies documented static reference rate (USD_JPY = 155.20)
       ↓
   conversion succeeds with explicit benchmark attribution
   ```
3. **Reference Rate Authority**:
   - **Source**: *European Central Bank (ECB) & Federal Reserve Reference Benchmark (Q1 2026 Reference Baseline)*.
   - **Rates**: `USD/JPY = 155.20`, `USD/EUR = 0.9200`, `EUR/USD = 1.0870`, `USD/GBP = 0.7850`, `GBP/USD = 1.2740`.
   - Any conversion performed using these rates is explicitly tagged: `[REFERENCE RATE APPLIED / BENCHMARK DETECTED ... NOTE: Static benchmark reference rate, NOT a live rate]`.

---

## 🛡️ Built-In Framework Guardrails

1. **Explicit Control Boundary**: The Gemini model *never* executes Python code directly. It can only propose a tool call. Our Python loop checks registration, verifies arguments via `inspect.signature()`, and executes within a `try/except` sandbox.
2. **Structured Observations**: Every tool turn returns a structured dictionary (`tool`, `success: bool`, `result` or `error_type`, `error`, `recovery_hint`) so Gemini can reason and self-correct on failure.
3. **AST-Based Math Sandboxing**: Mathematical expressions are parsed into an Abstract Syntax Tree (AST) restricting execution to numbers and arithmetic operators (`+`, `-`, `*`, `/`, `**`, `sqrt`) and safe reference rate variables. Python object traversal (`.__class__`) is strictly blocked.
4. **Path Sanitization**: `os.path.basename` prevents directory traversal (`../../`), confining generated files to `output/`.
5. **Secret Redaction**: Error observations automatically strip API keys and sensitive tokens before transmitting state back to the model.
6. **Step Limit**: Default `max_steps = 10` prevents runaway infinite reasoning loops.
7. **Resilient API Retry**: 3-attempt exponential backoff on transient 503/429 spikes with automatic model fallback to `gemini-3.5-flash-lite`.

## 🚀 Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Your Gemini API Key
Create a `.env` file in the project folder (or run `python main.py` and paste it when prompted):
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```

### 3. Run the Web Interface (Simplistic Black Theme)
```bash
python server.py
```
Open your browser at **`http://localhost:8000`**. You can enter your API key, choose test tracks with one click, watch real-time `PLAN` -> `ACT` -> `OBSERVE` -> `REPEAT` steps, and inspect generated files.

### 4. Or Run via Terminal CLI
```bash
python main.py
```

You will see an interactive menu:
```
Select an action:
  1. Run Single-Tool Test (Weather)
  2. Run Multi-Tool Chain (Weather + Reference Rate + File Save)
  3. Run Error Recovery Test (The Troublemaker -> Reference Rate Fallback)
  4. Enter your own custom prompt
  5. View Bonus Comparison (Our Engine vs LangChain)
  Q. Quit
```

### 💡 Demo Tracks Explained

- **Track 1 (Weather Lookup)**: Demonstrates single-turn autonomous tool selection calling `get_live_weather`.
- **Track 2 (Tokyo Trip: Weather + Reference Rate Conversion + File Save)**: Demonstrates multi-tool chaining. Converts `$1500 USD` to Japanese Yen using our documented static reference benchmark rate (`155.20 JPY/USD` from ECB/Fed benchmark data), then writes a complete itinerary to `output/tokyo_plan.txt`.
- **Track 3 (The Troublemaker: Error Recovery & Fallback)**: Demonstrates autonomous self-correction. Attempts `unreliable_live_rates("USD/JPY")`, intercepts the simulated 503 gateway outage, observes the failure payload and recovery hint, falls back to `calculate_currency_or_math` with documented reference benchmark `USD_JPY = 155.20`, converts `$1500 USD` to `232,800 JPY`, and records an incident recovery log in `output/recovery_log.txt`.

---

## 🧪 Automated Testing

Run the comprehensive pytest suite verifying all tools and the full agent loop:
```bash
pytest test_framework.py -v
```

---

## 📊 Bonus Framework Comparison

Read [`bonus_comparison.md`](bonus_comparison.md) for an in-depth architectural and behavioral comparison between our custom engine and LangChain on identical tasks.
