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

## 🛠️ The 4 Built-In Tools

| Tool | Purpose | Real-world Behavior |
| :--- | :--- | :--- |
| `get_live_weather` | Real-time weather lookup | Fetches current live temperature and conditions for any city via wttr.in. |
| `calculate_currency_or_math` | Precision calculator | Evaluates mathematical expressions and currency calculations safely. |
| `save_report_file` | File writer / Note-taker | Writes real summary reports directly onto your hard drive. |
| `unreliable_live_rates` | **The Troublemaker** | Intentionally raises an `HTTP 503 Service Unavailable` error to test the agent's error detection and autonomous recovery. |

---

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
  2. Run Multi-Tool Chain (Weather + Math + File Save)
  3. Run Error Recovery Test (The Troublemaker -> Self-Correction)
  4. Enter your own custom prompt
  5. View Bonus Comparison (Our Engine vs LangChain)
  Q. Quit
```

---

## 🧪 Automated Testing

Run the comprehensive pytest suite verifying all tools and the full agent loop:
```bash
pytest test_framework.py -v
```

---

## 📊 Bonus Framework Comparison

Read [`bonus_comparison.md`](bonus_comparison.md) for an in-depth architectural and behavioral comparison between our custom engine and LangChain on identical tasks.
