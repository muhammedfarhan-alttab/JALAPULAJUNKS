"""
agent_brain.py - The Core Custom Agent Framework (Built from Scratch).

This module contains NO pre-packaged agent frameworks (No LangChain, CrewAI, AutoGen).
It directly implements the fundamental Agent Loop:
    PLAN -> ACT -> OBSERVE -> REPEAT
using the native Google GenAI SDK solely for raw LLM inference.
"""

import os
import sys
import time
from typing import Callable, Dict, List, Any

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
        client: The Gemini API client.
        model_name: The Gemini model identifier.
        tools: A dictionary of registered callable Python functions.
        max_steps: Guardrail against infinite loops.
    """

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "gemini-3.6-flash",
        max_steps: int = 8,
    ):
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set! Please provide it in .env or pass api_key."
            )

        self.client = genai.Client(api_key=key)
        self.model_name = model_name
        self.max_steps = max_steps
        self.tool_functions: Dict[str, Callable] = {}

    def register_tool(self, func: Callable):
        """Register a Python function as an agent tool."""
        self.tool_functions[func.__name__] = func

    def register_tools(self, funcs: List[Callable]):
        """Register multiple Python functions as agent tools."""
        for f in funcs:
            self.register_tool(f)

    def run(self, user_prompt: str, step_callback: Callable[[str, Dict[str, Any]], None] = None) -> str:
        """
        Executes the Core Agent Loop:
          1. PLAN: Send history + tool schemas to Gemini.
          2. ACT: If Gemini issues tool calls, execute them in Python.
          3. OBSERVE: Capture the output (or catch the error) and feed it back.
          4. REPEAT: Loop until Gemini provides a final text answer or max steps reached.
          
        Args:
            user_prompt: The goal or instruction for the agent.
            step_callback: Optional callable for streaming steps to a web UI.
        """
        def emit(event_type: str, data: Dict[str, Any]):
            if step_callback:
                try:
                    step_callback(event_type, data)
                except Exception:
                    pass

        print("\n" + "=" * 65)
        print("🚀 [AGENT STARTED] Solving Goal:")
        print(f"   \"{user_prompt}\"")
        print("=" * 65)

        emit("start", {"prompt": user_prompt})

        # System instructions guiding the agent's behavior
        system_instruction = (
            "You are an autonomous problem-solving AI agent. "
            "You have access to a suite of tools to retrieve data, perform calculations, "
            "and save files.\n"
            "RULES:\n"
            "1. Dynamically select the best tool for each step. Never guess what you can verify with a tool.\n"
            "2. IF A TOOL CALL FAILS or returns an error: Do NOT give up or crash! Observe the error message, "
            "explain what happened in your next reasoning step, and use an alternative tool or approach to complete the task.\n"
            "3. Once the entire task is complete, provide a comprehensive final response to the user."
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

        # Initialize conversation history with the user's prompt
        history: List[types.Content] = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_prompt)],
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
            # and automatically fails over to alternative flash models if needed
            response = None
            candidate_models = [self.model_name, "gemini-3.5-flash", "gemini-flash-latest"]
            last_err = None

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
                        err_msg = str(api_err)
                        if "503" in err_msg or "429" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
                            wait_sec = 1.5 * (attempt + 1)
                            print(f"⏳ [DEMAND SPIKE] Model '{model_candidate}' 503/429. Retrying in {wait_sec}s...")
                            time.sleep(wait_sec)
                            continue
                        else:
                            # Not a temporary capacity error, try next candidate or abort
                            break
                if response is not None:
                    break

            if response is None:
                print(f"❌ [API ERROR] All models unavailable: {last_err}")
                emit("error", {"message": f"API Error: {str(last_err)}"})
                return f"Agent stopped due to API Error: {last_err}"

            candidate = response.candidates[0]
            model_content = candidate.content

            # Record model's thinking/response in history
            history.append(model_content)

            # Check if Gemini produced a direct answer without tool calls
            function_calls = response.function_calls

            if not function_calls:
                # No more tools needed: We reached the final answer!
                final_text = response.text or "(Task completed with no final text)"
                print(f"\n🎯 [TASK COMPLETED] Agent formulated final answer after {step_counter} step(s).")
                print("=" * 65)
                print(final_text)
                print("=" * 65)
                emit("final_answer", {"step": step_counter, "answer": final_text})
                return final_text

            # ACT & OBSERVE: Gemini decided to use one or more tools
            for call in function_calls:
                func_name = call.name
                func_args = call.args or {}

                print(f"\n🛠️  [STEP {step_counter}: ACT] Agent chose tool: '{func_name}'")
                print(f"    Arguments: {dict(func_args)}")
                emit("act", {"step": step_counter, "tool": func_name, "args": dict(func_args)})

                # Check if the requested tool is registered in our framework
                if func_name not in self.tool_functions:
                    observation_payload = {
                        "error": f"Tool '{func_name}' does not exist. Available tools: {list(self.tool_functions.keys())}"
                    }
                    print(f"⚠️  [OBSERVE: UNKNOWN TOOL] {observation_payload['error']}")
                    emit("observe_error", {"step": step_counter, "tool": func_name, "error": observation_payload["error"]})
                else:
                    # Execute tool inside our safety net (Try / Except)
                    try:
                        tool_fn = self.tool_functions[func_name]
                        raw_result = tool_fn(**func_args)
                        observation_payload = {"result": raw_result}
                        print(f"👁️  [STEP {step_counter}: OBSERVE] Tool executed successfully:")
                        print(f"    Result: {raw_result}")
                        emit("observe_success", {"step": step_counter, "tool": func_name, "result": str(raw_result)})
                    except Exception as tool_exc:
                        # ERROR RECOVERY: The tool failed, but the agent framework catches it!
                        # We package the error message and feed it back so Gemini can reason and self-correct.
                        error_msg = f"ERROR: Tool '{func_name}' execution failed: {str(tool_exc)}"
                        observation_payload = {"error": error_msg}
                        print(f"⚠️  [STEP {step_counter}: OBSERVE - FAILURE DETECTED!]")
                        print(f"    Notice: {error_msg}")
                        print(f"    -> Feeding error back to Gemini so it can recover...")
                        emit("observe_error", {
                            "step": step_counter,
                            "tool": func_name,
                            "error": str(tool_exc),
                            "recovery_note": "Exception safely intercepted. Sending error back to model for autonomous recovery."
                        })

                # Construct function response part for the conversation
                response_part = types.Part.from_function_response(
                    name=func_name,
                    response=observation_payload,
                )
                tool_content = types.Content(
                    role="user",
                    parts=[response_part],
                )
                history.append(tool_content)

        print(f"\n🛑 [STOPPED] Reached maximum allowed safety steps ({self.max_steps}).")
        emit("max_steps_reached", {"max_steps": self.max_steps})
        return "Agent stopped: Maximum reasoning steps reached."
