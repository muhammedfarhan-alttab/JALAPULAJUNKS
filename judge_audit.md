# 🔬 Hackathon Judge Audit — "Build the Brain, Not the Puppet"

> **Stance**: Skeptical judge. No modifications made. Evidence from code only.

---

## Part 1 — 25 Technical Questions

---

### Q1. Where is the PLAN step?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | [`CustomAgentBrain.run()`](file:///d:/JALAPULAJUNKS/agent_brain.py#L146-L233), lines 230–235 |
| **Code** | `while step_counter < self.max_steps:` … `print(f"🧠 [STEP {step_counter}: PLAN] Consulting Gemini Brain...")` |
| **What it does** | Every iteration of the `while` loop is a PLAN step. The current `history` list (full conversation context) is passed to `client.models.generate_content()`. |
| **Genuine?** | ✅ Yes. The loop is hand-written Python. No framework drives it. |

---

### Q2. Where does Gemini make the tool decision?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 248–252 |
| **Code** | `response = self.client.models.generate_content(model=model_candidate, contents=history, config=config)` |
| **What it does** | The raw Gemini response is returned. Gemini inspects the tool schemas it was given and embeds a `function_calls` object in the response if it wants a tool. Our Python code then reads that object. |
| **Genuine?** | ✅ Yes. The model decision is contained entirely inside `response.function_calls`, which our code inspects. |

---

### Q3. Where is the ACT step?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 312–355 |
| **Code** | `for call in function_calls:` … `func_name = call.name` … `tool_fn = self.tool_functions[func_name]` … `raw_result = tool_fn(**func_args)` |
| **What it does** | Our Python code reads `call.name` and `call.args`, performs three explicit validation checks (registry lookup, argument type check, execution sandbox), then calls the Python function directly. |
| **Genuine?** | ✅ Yes. It is a plain `dict` lookup followed by a `func(**args)` Python call. No hidden dispatcher. |

---

### Q4. Where does Python execute the selected function?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Line 355 |
| **Code** | `raw_result = tool_fn(**func_args)` |
| **What it does** | `tool_fn` is a direct Python callable retrieved from `self.tool_functions` (a plain `dict`). This is ordinary Python function invocation. |
| **Genuine?** | ✅ Yes. Zero indirection through any framework. |

---

### Q5. Where is the OBSERVE step?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 356–381 |
| **Code** | `observation_payload = {"tool": func_name, "success": True, "result": raw_result}` on success; `observation_payload = {"tool": func_name, "success": False, "error_type": ..., "error": ..., "recovery_hint": ...}` on exception |
| **What it does** | The result (or sanitized error) is packaged into a structured Python `dict`. |
| **Genuine?** | ✅ Yes. Hand-coded `dict` construction. |

---

### Q6. Where is the tool result inserted back into conversation history?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 384–392 |
| **Code** | `response_part = types.Part.from_function_response(name=func_name, response=observation_payload)` → `history.append(tool_content)` |
| **What it does** | The observation dict is wrapped in a Gemini-format `Content` object (role=`"user"`) and appended to the `history` list in-memory. On the next iteration, the entire updated `history` is sent back to Gemini. |
| **Genuine?** | ✅ Yes. The `history` variable is an ordinary Python `list` our code owns and mutates manually. |

---

### Q7. Where does the REPEAT happen?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Line 393 + the `while` loop guard at line 230 |
| **Code** | `print(f"🔁 [STEP {step_counter}: REPEAT] Appended observation to history...")` then the loop continues with `step_counter += 1` and another `generate_content` call |
| **What it does** | After appending the observation, the `while` loop simply continues to the next iteration. The history now includes the observation, so Gemini sees it on the next PLAN step. |
| **Genuine?** | ✅ Yes. A Python `while` loop. |

---

### Q8. What causes the loop to terminate?

Two conditions, both in `agent_brain.py`:

1. **Gemini returns no tool calls** (line 302): `if not function_calls:` → the final text is extracted and returned immediately.
2. **`max_steps` is exhausted** (line 395): the `while` condition fails and a "stopped" message is returned.

**Genuine?** ✅ Yes. Both are plain Python control flow.

---

### Q9. What prevents infinite loops?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 43, 46–47, 230 |
| **Code** | `max_steps: int = 10` as constructor default; validated at init with `if max_steps <= 0: raise ValueError(...)` |
| **Test coverage** | `test_max_steps_guardrail` in `test_framework.py` (line 455) explicitly proves the loop terminates at exactly `max_steps=3` |
| **Genuine?** | ✅ Yes. Tested and implemented. |

---

### Q10. Can Gemini directly execute Python?

**No.** The critical configuration is at lines 205–212:

```python
config = types.GenerateContentConfig(
    system_instruction=...,
    tools=tool_list,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    temperature=0.2,
)
```

`disable=True` explicitly turns off the SDK's automatic function calling. Gemini can only *propose* a call via `function_calls` in the response object. Python code decides whether and how to execute it.

**Genuine?** ✅ Yes. This is the most important single line for hackathon compliance and it is present and correct.

---

### Q11. What happens when a tool throws an exception?

| Item | Answer |
|---|---|
| **File** | `agent_brain.py` |
| **Location** | Lines 364–381 |
| **Code** | `except Exception as tool_exc:` → `safe_err_msg = self._sanitize_error_message(str(tool_exc))` → structured `observation_payload` with `"success": False` |
| **What it does** | The exception is caught, secrets are scrubbed via `_sanitize_error_message`, and a structured observation dict is inserted into history for Gemini to reason about. The loop does NOT crash. |
| **Genuine?** | ✅ Yes. Tested in `test_mocked_agent_loop_with_error_recovery`. |

---

### Q12. How does the Troublemaker recovery work?

Full flow, verified by code:

1. **`unreliable_live_rates("USD/JPY")`** — `tools.py` line 424: `raise ConnectionError("HTTP 503 Service Unavailable...")`.
2. **Exception caught** — `agent_brain.py` line 364: our `except` block fires.
3. **Observation built** — `{"tool": "unreliable_live_rates", "success": False, "error_type": "ConnectionError", "error": "HTTP 503...", "recovery_hint": "Fall back to calculate_currency_or_math..."}`.
4. **Appended to history** — Gemini now sees the failure on its next PLAN step.
5. **Gemini replans** — proposes `calculate_currency_or_math("1500 * USD_JPY")`.
6. **ACT** — `tools.py` line 295 evaluates `1500 * 155.20 = 232800` with explicit `[REFERENCE RATE APPLIED / ECB / NOT a live rate]` annotation.

The Troublemaker is intentionally **not retried** — it is not called via `_robust_http_get`, so the retry loop in `tools.py` lines 98–126 does not apply.

**Genuine?** ✅ Yes. Proven by `test_currency_conversion_failure_observation_fallback_flow` (line 525).

---

### Q13. Is tool selection hardcoded?

**No.** The agent loop sends *all* registered tool schemas to Gemini every PLAN step. Gemini reads them and picks. Proof: in `main.py` Demo 2 (line 99), the prompt just says "Check weather… convert… save a report." No code in the loop says "first call weather, then calculator, then file writer." Gemini decides the sequence dynamically.

**Genuine?** ✅ Not hardcoded.

---

### Q14. Is the tool registry ours?

| Item | Answer |
|---|---|
| **File** | `tools.py` lines 961–970 |
| **Code** | `TOOL_REGISTRY = {"get_live_weather": get_live_weather, ...}` — a plain Python `dict` |
| **Agent side** | `agent_brain.py` line 64: `self.tool_functions[func.__name__] = func` — another plain Python `dict` |
| **Genuine?** | ✅ Yes. No framework involved. |

---

### Q15. Are LangChain / CrewAI / AutoGen used?

**`requirements.txt`** contains exactly three packages:
```
google-genai>=1.0.0
python-dotenv>=1.0.0
requests>=2.31.0
```

No LangChain, CrewAI, AutoGen, or Google ADK. The `google-genai` SDK is used solely for `client.models.generate_content()` (raw inference) and `types.Content/Part` (structured message formatting).

**Genuine?** ✅ Confirmed absent.

---

### Q16. Is automatic function calling enabled?

**No.** Line 208–210 of `agent_brain.py`:
```python
automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
```

**Genuine?** ✅ Confirmed disabled.

---

### Q17. Where are tool arguments validated?

Three layers, all in `agent_brain.py`:

1. **Registry check** (line 322): `if func_name not in self.tool_functions` → `ToolNotFoundError`.
2. **Signature check** (lines 71–108): `_validate_arguments()` uses `inspect.signature().bind(**args)` to reject missing required args, unexpected kwargs, and type mismatches for annotated parameters (`str`, `int`, `float`, `dict`).
3. **Execution sandbox** (line 354): `try/except Exception` catches anything that slips through.

**Genuine?** ✅ Yes. Tested by `test_argument_validation_guardrail` and `test_argument_validation_types_and_payloads`.

---

### Q18. Can Gemini execute arbitrary code?

**No.** Gemini cannot call Python, read files, or access the network. It can only produce text or a `function_calls` list in its response. Our Python code alone decides whether to execute anything. The math sandbox (`_eval_ast_math_node`) additionally prevents code injection via the calculator tool by only allowing numeric AST nodes and declared constants.

**Genuine?** ✅ Architecturally and technically impossible for Gemini to execute arbitrary code.

---

### Q19. How is file writing secured?

`tools.py` `_validate_safe_filename()` (lines 39–95) enforces:

- Rejects `..` (path traversal)
- Strips to `os.path.basename()`
- Rejects filesystem special chars via regex
- Rejects reserved OS names (`CON`, `PRN`, `NUL`, etc.)
- Rejects hidden/sensitive files (`.env`, `.git`, `id_rsa`)
- Rejects dangerous extensions (`.exe`, `.bat`, `.ps1`, etc.)
- Final `os.path.abspath()` check ensures the resolved path is strictly inside `output/`

**Genuine?** ✅ Tested by `test_path_traversal_and_file_safety_guardrail` (line 625).

---

### Q20. Where does the currency exchange rate come from?

`tools.py` lines 172–195:

```python
FALLBACK_RATE_SOURCE = "European Central Bank (ECB) & Federal Reserve Reference Benchmark (Q1 2026 Reference Baseline, Static Fallback Table)"

FALLBACK_REFERENCE_RATES = {
    "USD/JPY": 155.20,
    "USD/EUR": 0.9200,
    ...
}
```

These are **static constants** hardcoded in the source file, labelled with their source.

**Genuine?** ✅ Yes — and technically honest about being static.

---

### Q21. Is the rate actually live?

**No.** By default, `unreliable_live_rates` always raises `ConnectionError` (line 424). Live mode is only activated by setting `ENABLE_LIVE_RATES=true` in the environment, which is not the default demo configuration. Every conversion result from `calculate_currency_or_math` includes the explicit tag `"NOTE: Static benchmark reference rate, NOT a live rate"`.

**Genuine?** ✅ Honest. The code enforces the disclaimer programmatically.

---

### Q22. Are retries actually implemented?

**Yes — for real HTTP calls.** `_robust_http_get()` in `tools.py` (lines 98–126) retries up to 2 times with `0.3s * (attempt+1)` backoff for status codes `{429, 500, 502, 503, 504}` and network exceptions. Used by `get_live_weather`.

**Intentionally NOT applied to** `unreliable_live_rates` — the Troublemaker raises a Python `ConnectionError` exception directly (not via HTTP), so `_robust_http_get` is never invoked for it.

**Genuine?** ✅ Implemented and architecturally correct.

---

### Q23. Is alternative model fallback actually implemented?

**Yes.** `agent_brain.py` lines 239–277:
```python
candidate_models = [self.model_name]  # e.g. "gemini-3.1-flash-lite"
if self.fallback_model:
    candidate_models.append(self.fallback_model)  # "gemini-flash-latest"
for model_candidate in candidate_models:
    for attempt in range(3):
        ...  # retry with backoff
    if response is not None:
        break
```

**Genuine?** ✅ Yes. If the primary model fails all 3 attempts, the loop moves to the fallback.

---

### Q24. Does localhost:8000 actually work?

The server daemon (task `task-1652`) has been running since the previous session. `server.py` implements a raw Python `http.server.BaseHTTPRequestHandler` with a `ThreadingMixIn`. Verified endpoints:

| Endpoint | Method | Status |
|---|---|---|
| `GET /` | HTML frontend | ✅ Served from `web/index.html` |
| `GET /api/status` | JSON tool list | ✅ Returns 7 tools |
| `GET /api/files` | JSON file list | ✅ Lists `output/` contents |
| `GET /api/file?name=X` | File content | ✅ With filename validation |
| `POST /api/run` | Agent execution | ✅ Calls `CustomAgentBrain.run()` |
| `POST /api/key` | Set API key | ✅ Writes `.env` |

**Test coverage**: `test_server.py` starts a live server on port 8999 and verifies all these endpoints.

> ⚠️ **One honest caveat**: `test_server_serves_html` (line 27) checks for `"agent / core-loop"` or `"the-brain"` in the HTML. This test may be brittle depending on the exact content of `web/index.html`. If the test is in the "33/33 passed" claim, this should be verified live.

---

### Q25. Can you reproduce the entire demo from a clean environment?

**Steps (from `requirements.txt` and `main.py`):**
```bash
git clone <repo>
cd JALAPULAJUNKS
pip install -r requirements.txt         # 3 packages only
echo "GEMINI_API_KEY=your_key" > .env
python main.py --demo 1                 # Single tool
python main.py --demo 2                 # Multi-tool
python main.py --demo 3                 # Error recovery
python server.py                        # Web UI at localhost:8000
pytest -v                               # 33 tests
```

**Genuine?** ✅ Yes — with one honest dependency: a valid `GEMINI_API_KEY` is required for live runs. Tests use `monkeypatch` mocking so they pass without a real key.

---

## Part 2 — Critical Judge Risks

> [!CAUTION]
> These are the real vulnerabilities a skeptical judge will probe.

### RISK 1 — `generate_content` is still from the SDK
The Google GenAI SDK is used for `client.models.generate_content()`. A hostile judge may argue "you're using Google's SDK which could have agent logic inside." **Counter**: The SDK is used purely as an HTTP transport to the Gemini REST API. The `automatic_function_calling=disable=True` flag makes this provable. No orchestration logic runs inside the SDK call.

### RISK 2 — Tool schemas are generated by the SDK from Python docstrings
When `tool_list = list(self.tool_functions.values())` is passed to `GenerateContentConfig(tools=...)`, the SDK converts Python functions to `FunctionDeclaration` JSON schemas using their docstrings. **Counter**: Schema generation is a serialization concern, not agent orchestration. Our code owns the loop, the dispatch, and the observation.

### RISK 3 — "33/33 tests" claim needs live verification
All tests use `MagicMock` for `generate_content`. They prove the *framework's control flow* works but do not prove Gemini actually chooses the right tool in real conditions. A judge will ask to run the demo live.

### RISK 4 — Model name `gemini-3.1-flash-lite` may not exist
This is a specific risk. Google's public model catalog does not include `gemini-3.1-flash-lite` in any stable or preview announcement visible as of mid-2026. The fallback is `gemini-flash-latest` which is a valid alias. If the primary model is invalid, every real demo goes through the fallback — which works, but requires explaining.

### RISK 5 — The `ENABLE_LIVE_RATES` flag creates a hidden live-rate mode
If a judge sets `ENABLE_LIVE_RATES=true`, `unreliable_live_rates` will query `open.er-api.com`. In the default demo it is not set. But the README does not clearly document this flag, which could confuse judges about what the "Troublemaker" really does.

### RISK 6 — LTspice path is hardcoded to one user's machine
`server.py` line 208: `ltspice_exe = r"C:\Users\Muhammed Farhan\AppData\Local\Programs\LTspice.exe"`. This will silently fail on any other machine. The tool falls back to `os.startfile()` so it is not a crash, but it leaks a personal username in the code and is not reproducible cross-machine.

---

## Part 3 — Technical Questions You Must Be Ready For

1. **"Show me the line where Python calls the tool — not a framework."** → `agent_brain.py` line 355: `raw_result = tool_fn(**func_args)`.
2. **"What is `automatic_function_calling=disable=True` and why did you write it?"** → SDK would otherwise execute tools silently. `disable=True` ensures our loop owns all execution.
3. **"How do you know Gemini chose the tool and not your code?"** → `response.function_calls` is read-only output from the Gemini API. Our code reads it; it doesn't set it.
4. **"Is `history` a LangChain memory object?"** → No. It is `history: List[types.Content] = [...]` — a plain Python list declared at line 221.
5. **"What happens if Gemini hallucinates a tool name that doesn't exist?"** → Line 322: `if func_name not in self.tool_functions` → structured `ToolNotFoundError` observation is returned. Tested in `test_unknown_tool_guardrail`.
6. **"Your demo relies on the Troublemaker failing — couldn't you just hardcode that failure?"** → You could — but the failure is a real Python `raise ConnectionError` in the tool function. Gemini doesn't know the tool will fail. It chooses to call it, sees the structured error, and picks the fallback itself. That replanning is real.
7. **"Is your rate actually from ECB?"** → No. It is a static constant *labelled* as an ECB reference benchmark. It is not fetched from ECB at runtime. The README and code both say "static reference benchmark." This is the honest answer.
8. **"Can I see `TOOL_REGISTRY`?"** → `tools.py` line 962: it is a 7-entry Python dict. Point to it.

---

## Part 4 — Claims in the PPT That Must Be Removed

> [!WARNING]
> Remove or rephrase these before presenting.

| ❌ Claim | Reason |
|---|---|
| **"33/33 tests pass"** stated as proof of real-world correctness | All agent loop tests use `MagicMock`. They test *framework control flow*, not real Gemini behavior. Reframe: "33 unit + integration tests verify the framework structure and guardrails." |
| **"Live exchange rate"** in any slide | `unreliable_live_rates` always fails by default. The conversion always uses a static benchmark. Remove any implication that you show a live rate. |
| **"gemini-3.1-flash-lite"** as if it's a well-known model | This model identifier is not in Google's standard public catalog. The fallback `gemini-flash-latest` is real. Don't lead with an unverifiable model name. |
| Any mention of **ECB rate as dynamically fetched** | The ECB rate is a Python `float` constant in `tools.py`. It is never fetched at runtime. |

---

## Part 5 — Claims That Must Be Reworded

| ⚠️ Current Wording | ✅ Safer Wording |
|---|---|
| "Real-time weather lookup" | "Live weather via `wttr.in` with deterministic fallback for offline environments" |
| "Static ECB reference rate" | "Documented Q1 2026 static benchmark rate, labelled as non-live in every tool output" |
| "The Troublemaker simulates a live gateway failure" | "The Troublemaker tool raises a deterministic `ConnectionError` to demonstrate agent recovery — it does not make any outbound HTTP request in default mode" |
| "Gemini chooses the tools autonomously" | "Gemini proposes tools from the schema we provide. Our Python code validates and executes them." |
| "localhost:8000 HTTP interface" | "Minimal HTTP server built on Python's stdlib `http.server` exposing 5 REST endpoints. No web framework provides agent orchestration." |

---

## Part 6 — Features That Should Be Demonstrated Live

> [!IMPORTANT]
> A judge who doubts the custom loop will ask for a live terminal demo.

**Demonstrate these in order:**

1. **`python main.py --demo 1`** — Show terminal output line by line:
   - `🧠 [STEP 1: PLAN]` — proving the loop started
   - `🛠️ [STEP 1: ACT] Python Framework executing requested tool: 'get_live_weather'` — proving Python chose to execute
   - `👁️ [STEP 1: OBSERVE]` — proving our code captured the result
   - `🧠 [STEP 2: PLAN]` — proving it looped
   - `✅ [STEP 2: COMPLETE]` — proving it terminated naturally
   - **Point to `agent_brain.py` on a second screen** and walk through the loop live.

2. **`python main.py --demo 3`** (Troublemaker) — Show:
   - `⚠️ [STEP 1: ERROR] Tool 'unreliable_live_rates' execution failed: HTTP 503...`
   - `♻️ [STEP 1: RECOVERY] Feeding structured error back to Gemini...`
   - `🛠️ [STEP 2: ACT] Python Framework executing: 'calculate_currency_or_math'`
   - `👁️ [STEP 2: OBSERVE] ... 232800 JPY [REFERENCE RATE APPLIED / NOT a live rate]`
   - **Point to the `except Exception as tool_exc` block in `agent_brain.py` line 364** and explain it.

3. **Open `agent_brain.py` in editor** — show the judge the 12-line loop core (lines 230–393) and point out there is no import of LangChain/CrewAI/AutoGen anywhere in the file.

4. **Show `requirements.txt`** — three lines. No agent framework.

5. **Show `automatic_function_calling=disable=True`** at line 208 — "Gemini cannot run our tools. Only our code can."

6. **Run `pytest -v`** live — 33 tests must pass. Be prepared for `test_server_serves_html` to fail if `web/index.html` content doesn't match the string check.

---

*Audit completed. No code was modified.*
