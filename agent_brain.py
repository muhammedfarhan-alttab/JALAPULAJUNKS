"""
agent_brain.py - The Core Custom Agent Framework (Built from Scratch).

This module contains NO pre-packaged agent frameworks (No LangChain, CrewAI, AutoGen).
It directly implements the fundamental Agent Loop:
    PLAN -> ACT -> OBSERVE -> REPEAT
using the native Google GenAI SDK solely for raw LLM inference.
"""

import inspect
import os
import re
import sys
import time
from typing import Callable, Dict, List, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from google import genai
from google.genai import types


class CustomAgentBrain:
    """
    A transparent, from-scratch AI Agent implementation.
    
    Attributes:
        client: The Gemini API client (used solely for raw LLM inference).
        model_name: The Gemini model identifier.
        tool_functions: A dictionary mapping tool names to callable Python functions.
        max_steps: Guardrail against infinite loops.
    """

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "gemini-3.1-flash-lite",
        max_steps: int = 10,
        fallback_model: Optional[str] = "gemini-3.6-flash",
    ):
        if max_steps is not None and max_steps <= 0:
            raise ValueError(f"max_steps must be a positive integer, received: {max_steps}")

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set! Please provide it in .env or pass api_key."
            )

        self.api_key = key
        self.client = genai.Client(api_key=key)
        self.model_name = model_name
        self.max_steps = max_steps
        self.fallback_model = fallback_model
        self.tool_functions: Dict[str, Callable] = {}

    def register_tool(self, func: Callable):
        """Register a Python function as an agent tool in our transparent dictionary."""
        self.tool_functions[func.__name__] = func

    def register_tools(self, funcs: List[Callable]):
        """Register multiple Python functions as agent tools."""
        for f in funcs:
            self.register_tool(f)

    def _validate_arguments(self, func: Callable, args: Any) -> Optional[str]:
        """
        Guardrail: Validates that arguments match the function signature BEFORE execution.
        Rejects:
          - Non-dict argument payloads
          - Missing required arguments
          - Unexpected keyword arguments
          - Type mismatches for annotated parameters (e.g. str, dict, int, float)
        """
        if not isinstance(args, dict):
            return f"Arguments must be provided as a key-value dictionary, received {type(args).__name__}."

        try:
            sig = inspect.signature(func)
            bound = sig.bind(**args)
            bound.apply_defaults()

            for param_name, param_value in bound.arguments.items():
                param = sig.parameters.get(param_name)
                if param and param.annotation != inspect.Parameter.empty:
                    expected_type = param.annotation
                    if param_value is None and param.default is None:
                        continue
                    if isinstance(expected_type, type):
                        if expected_type is float:
                            if not isinstance(param_value, (int, float)) or isinstance(param_value, bool):
                                return f"Parameter '{param_name}' must be of type float or int, received {type(param_value).__name__}."
                        elif expected_type is int:
                            if not isinstance(param_value, int) or isinstance(param_value, bool):
                                return f"Parameter '{param_name}' must be of type int, received {type(param_value).__name__}."
                        elif expected_type is dict:
                            if not isinstance(param_value, dict):
                                return f"Parameter '{param_name}' must be of type dict, received {type(param_value).__name__}."
                        elif expected_type is str:
                            if not isinstance(param_value, str):
                                return f"Parameter '{param_name}' must be of type str, received {type(param_value).__name__}."

            return None
        except TypeError as te:
            return str(te)

    def _sanitize_error_message(self, text: str) -> str:
        """
        Guardrail: Sanitizes error messages before returning them in structured observations or logs.
        Scrubs:
          - Active API keys
          - Sensitive environment variable tokens (passwords, secrets, keys, credentials)
          - Full local filesystem paths and user directory layouts
          - Tracebacks and internal file paths
        """
        if not text:
            return ""

        sanitized = str(text)

        # 1. Redact API key
        if self.api_key and self.api_key in sanitized:
            sanitized = sanitized.replace(self.api_key, "[REDACTED_API_KEY]")

        # 2. Redact sensitive environment variables (tokens >= 6 chars)
        secret_keys = ("KEY", "TOKEN", "SECRET", "PASS", "AUTH", "CREDENTIAL", "PRIVATE")
        for env_k, env_v in os.environ.items():
            if any(s in env_k.upper() for s in secret_keys):
                if env_v and len(env_v) >= 6 and env_v in sanitized:
                    sanitized = sanitized.replace(env_v, f"[REDACTED_{env_k}]")

        # 3. Redact local user directory layout (e.g. C:\\Users\\Username\\... or /home/username/...)
        user_home = os.path.expanduser("~")
        if user_home and user_home in sanitized:
            sanitized = sanitized.replace(user_home, "[USER_HOME]")

        # 4. Replace Windows and Unix absolute paths with generic markers
        sanitized = re.sub(r"[A-Za-z]:\\[^:\n\r\t\"\'<>]+", "[LOCAL_PATH]", sanitized)
        sanitized = re.sub(r"/(?:home|usr|etc|var|tmp)/[^\s:\n\r\t\"\'<>]+", "[SYSTEM_PATH]", sanitized)

        return sanitized

    def run(
        self,
        user_prompt: str,
        image_bytes: Optional[bytes] = None,
        image_mime: Optional[str] = None,
        step_callback: Callable[[str, Dict[str, Any]], None] = None
    ) -> str:
        """
        Executes the Core Agent Loop:
          1. PLAN: Send history + tool schemas to Gemini.
          2. ACT: If Gemini issues tool calls, execute them in Python.
          3. OBSERVE: Capture the output (or catch the error) and feed it back.
          4. REPEAT: Loop until Gemini provides a final text answer or max steps reached.
          
        Args:
            user_prompt: The goal or instruction for the agent.
            image_bytes: Optional raw image bytes for multimodal input.
            image_mime: Optional MIME type for image (e.g. 'image/png', 'image/jpeg').
            step_callback: Optional callable for streaming steps to a web UI.
        """
        def emit(event_type: str, data: Dict[str, Any]):
            if step_callback:
                try:
                    step_callback(event_type, data)
                except Exception:
                    pass

        print("\n" + "=" * 65)
        print(f"🔵 USER REQUEST: \"{user_prompt}\"")
        if image_bytes:
            print(f"   📷 [MULTIMODAL ATTACHMENT]: {len(image_bytes)} bytes ({image_mime or 'image/jpeg'})")
        print("=" * 65)

        emit("start", {"prompt": user_prompt, "has_image": bool(image_bytes)})

        # System instructions guiding the agent's behavior
        system_instruction = (
            "You are an autonomous problem-solving AI agent. "
            "You have access to a suite of tools to retrieve data, perform calculations, "
            "save files, search the web for engineering specs, and generate Autodesk Fusion 360 3D CAD scripts and LTspice circuits.\n"
            "If the user provides an image (such as a photo of a physical part, dimension drawing, or circuit diagram) or asks to design/model something:\n"
            "- Carefully inspect its visual features, geometry, or electronic components.\n"
            "- Whenever you encounter unfamiliar ICs, circuit components, pinouts, or mechanical tolerances/standards, "
            "use the 'search_web_for_circuit_or_model' tool to verify datasheet specs, pin connections, or dimensional standards first.\n"
            "- Then use the appropriate engineering tool ('generate_fusion360_cad' or 'generate_ltspice_circuit') to model it accurately.\n"
            "RULES:\n"
            "1. Dynamically select the best tool for each step. Never guess what you can verify with a tool.\n"
            "2. IF A TOOL CALL FAILS or returns an error: Do NOT give up or crash! Observe the error message, "
            "explain what happened in your next reasoning step, and use an alternative tool or approach to complete the task.\n"
            "3. For currency conversions: If live rate retrieval ('unreliable_live_rates') fails due to a gateway outage, "
            "fall back to 'calculate_currency_or_math' using our documented static reference benchmark rates "
            "(e.g., USD/JPY = 155.20 from published ECB/Fed benchmarks). In your final synthesis, remain technically honest "
            "and explicitly state that a static reference/fallback benchmark rate was used, NOT a live rate.\n"
            "4. Once the entire task is complete, provide a comprehensive final response to the user."
        )

        # Configuration: Pass our Python functions as tools, but DISABLE automatic calling
        # so OUR code retains full control over the execution loop (The Brain, not the Puppet).
        tool_list = list(self.tool_functions.values())
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tool_list,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            temperature=0.2,
        )

        # Initialize conversation history with the user's prompt and optional image
        user_parts = []
        if image_bytes:
            mime = image_mime or "image/jpeg"
            user_parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        user_parts.append(types.Part.from_text(text=user_prompt))

        history: List[types.Content] = [
            types.Content(
                role="user",
                parts=user_parts,
            )
        ]

        step_counter = 0

        while step_counter < self.max_steps:
            step_counter += 1
            print(f"\n-------------------------------------------------------------")
            print(f"🧠 [STEP {step_counter}: PLAN] Consulting Gemini Brain...")
            print(f"-------------------------------------------------------------")
            emit("plan", {"step": step_counter, "message": "Analyzing context and planning next action..."})

            # Resilient API communication: Auto-retries on transient 503/429 spikes
            response = None
            candidate_models = [self.model_name]
            if self.fallback_model:
                candidate_models.append(self.fallback_model)
            last_err = None

            is_offline = False
            for model_candidate in candidate_models:
                for attempt in range(3):
                    try:
                        response = self.client.models.generate_content(
                            model=model_candidate,
                            contents=history,
                            config=config,
                        )
                        break
                    except Exception as api_err:
                        last_err = api_err
                        err_msg = str(api_err).lower()
                        if "getaddrinfo failed" in err_msg or "nodename nor servname provided" in err_msg:
                            # Machine is offline / DNS failed. Try once more quickly, then stop.
                            is_offline = True
                            if attempt == 0:
                                time.sleep(1.5)
                                continue
                            break

                        is_transient = any(k in err_msg for k in [
                            "503", "429", "unavailable", "high demand", 
                            "timeout", "connecterror"
                        ])
                        if is_transient:
                            wait_sec = 1.5 * (attempt + 1)
                            print(f"⏳ [CAPACITY RETRY] Model '{model_candidate}' busy. Retrying in {wait_sec}s...")
                            time.sleep(wait_sec)
                            continue
                        else:
                            break
                if response is not None or is_offline:
                    break

            if response is None:
                err_text = str(last_err)
                if "getaddrinfo failed" in err_text.lower():
                    friendly_msg = (
                        "Internet Disconnected: Your computer cannot reach Google servers. "
                        "Please verify your Wi-Fi or internet connection and try again."
                    )
                else:
                    friendly_msg = f"API Error: {err_text}"

                print(f"❌ [API ERROR] All attempts failed: {friendly_msg}")
                emit("error", {"message": friendly_msg})
                return f"Agent stopped: {friendly_msg}"

            candidate = response.candidates[0]
            model_content = candidate.content

            # Record model's thinking/response in history
            history.append(model_content)

            # Check if Gemini produced a direct answer without tool calls
            function_calls = response.function_calls

            if not function_calls:
                # No more tools needed: We reached the final answer!
                final_text = response.text or "(Task completed with no final text)"
                print(f"\n✅ [STEP {step_counter}: COMPLETE] Final synthesized output received after {step_counter} step(s):")
                print("=" * 65)
                print(final_text)
                print("=" * 65)
                emit("final_answer", {"step": step_counter, "answer": final_text})
                return final_text

            # ACT & OBSERVE: Gemini requested one or more tool calls
            for call in function_calls:
                func_name = call.name
                func_args = call.args or {}

                print(f"\n🛠️  [STEP {step_counter}: ACT] Python Framework executing requested tool: '{func_name}'")
                print(f"    Arguments: {dict(func_args)}")
                emit("act", {"step": step_counter, "tool": func_name, "args": dict(func_args)})

                # Explicit Control Boundary 1: Verify tool is registered in Python framework
                if func_name not in self.tool_functions:
                    raw_err = f"Tool '{func_name}' is not registered in framework. Available tools: {list(self.tool_functions.keys())}"
                    sanitized_err = self._sanitize_error_message(raw_err)
                    observation_payload = {
                        "tool": func_name,
                        "success": False,
                        "error_type": "ToolNotFoundError",
                        "error": sanitized_err,
                        "recovery_hint": "Please select from the available tools registered in the framework."
                    }
                    print(f"⚠️  [STEP {step_counter}: ERROR] Tool '{func_name}' does not exist.")
                    print(f"♻️  [STEP {step_counter}: RECOVERY] Feeding structured error back to Gemini for autonomous self-correction...")
                    emit("observe_error", {"step": step_counter, "tool": func_name, "error": sanitized_err})
                else:
                    tool_fn = self.tool_functions[func_name]
                    # Explicit Control Boundary 2: Validate arguments against Python signature before execution
                    validation_error = self._validate_arguments(tool_fn, func_args)
                    if validation_error:
                        sig = inspect.signature(tool_fn)
                        sanitized_val_err = self._sanitize_error_message(validation_error)
                        observation_payload = {
                            "tool": func_name,
                            "success": False,
                            "error_type": "ArgumentValidationError",
                            "error": f"Invalid arguments for '{func_name}': {sanitized_val_err}",
                            "recovery_hint": f"Expected parameters for '{func_name}': {list(sig.parameters.keys())}. Please fix the arguments."
                        }
                        print(f"⚠️  [STEP {step_counter}: ERROR] Argument validation failed for '{func_name}': {sanitized_val_err}")
                        print(f"♻️  [STEP {step_counter}: RECOVERY] Feeding structured error back to Gemini for autonomous self-correction...")
                        emit("observe_error", {"step": step_counter, "tool": func_name, "error": observation_payload["error"]})
                    else:
                        # Explicit Control Boundary 3: Execute tool inside safety net
                        try:
                            raw_result = tool_fn(**func_args)
                            observation_payload = {
                                "tool": func_name,
                                "success": True,
                                "result": raw_result,
                            }
                            print(f"👁️  [STEP {step_counter}: OBSERVE] Tool '{func_name}' executed successfully:")
                            print(f"    Result: {raw_result}")
                            emit("observe_success", {"step": step_counter, "tool": func_name, "result": str(raw_result)})
                        except Exception as tool_exc:
                            # ERROR RECOVERY: Intercept exception, sanitize secrets, package structured observation
                            safe_err_msg = self._sanitize_error_message(str(tool_exc))
                            observation_payload = {
                                "tool": func_name,
                                "success": False,
                                "error_type": type(tool_exc).__name__,
                                "error": safe_err_msg,
                                "recovery_hint": "Tool execution encountered an exception. Read the error message and choose an alternative tool or approach to complete the task."
                            }
                            print(f"⚠️  [STEP {step_counter}: ERROR] Tool '{func_name}' execution failed: {safe_err_msg}")
                            print(f"♻️  [STEP {step_counter}: RECOVERY] Feeding structured error back to Gemini for autonomous self-correction...")
                            emit("observe_error", {
                                "step": step_counter,
                                "tool": func_name,
                                "error": safe_err_msg,
                                "recovery_note": "Exception safely intercepted. Sending structured observation back to model for autonomous recovery."
                            })

                # REPEAT: Construct function response observation part for conversation history
                response_part = types.Part.from_function_response(
                    name=func_name,
                    response=observation_payload,
                )
                tool_content = types.Content(
                    role="user",
                    parts=[response_part],
                )
                history.append(tool_content)
                print(f"🔁 [STEP {step_counter}: REPEAT] Appended observation to history. Prompting Gemini for next action...")

        print(f"\n🛑 [STOPPED] Reached maximum allowed safety steps ({self.max_steps}).")
        emit("max_steps_reached", {"max_steps": self.max_steps})
        return f"Agent stopped: Reached maximum reasoning/action limit of {self.max_steps} steps without completing the task."
