"""
main.py - Interactive Runner for our Custom Agent Framework.

Run:
    python main.py
or automated test mode:
    python main.py --demo
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from agent_brain import CustomAgentBrain
from tools import (
    get_live_weather,
    calculate_currency_or_math,
    save_report_file,
    unreliable_live_rates,
    generate_fusion360_cad,
    generate_ltspice_circuit,
    search_web_for_circuit_or_model,
)


def get_agent() -> CustomAgentBrain:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n" + "!" * 60)
        print("⚠️  GEMINI_API_KEY NOT FOUND!")
        print("!" * 60)
        print("To run the agent, you need your Gemini API key from Google AI Studio.")
        print("You can either:")
        print("  1. Create a file named .env with: GEMINI_API_KEY=your_key_here")
        print("  2. Or paste your key right now below.\n")
        user_key = input("Enter your Gemini API Key (or press Enter to exit): ").strip()
        if not user_key:
            print("Exiting. Please provide an API key to continue.")
            sys.exit(1)
        api_key = user_key
        # Automatically save it to .env for next time
        with open(".env", "w") as f:
            f.write(f"GEMINI_API_KEY={api_key}\n")
        print("Saved GEMINI_API_KEY to .env for future runs!\n")

    # Initialize our from-scratch agent brain (default max_steps=10)
    agent = CustomAgentBrain(api_key=api_key)

    # Register all 7 tools dynamically into our transparent registry
    agent.register_tools([
        get_live_weather,
        calculate_currency_or_math,
        save_report_file,
        unreliable_live_rates,
        generate_fusion360_cad,
        generate_ltspice_circuit,
        search_web_for_circuit_or_model,
    ])

    return agent


def run_demo_menu():
    print("""
==================================================================
  🧠 BUILD THE BRAIN, NOT THE PUPPET: CUSTOM AGENT FRAMEWORK
==================================================================
  Registered Tools:
    1. get_live_weather               (Real-world weather lookup)
    2. calculate_currency_or_math      (Safe AST calculator & ECB/Fed reference benchmark rates)
    3. save_report_file               (Local output/ folder file writer)
    4. unreliable_live_rates          (The Troublemaker: intentional 503 live gateway test)
    5. generate_fusion360_cad         (Autodesk Fusion 360 3D CAD script)
    6. generate_ltspice_circuit       (LTspice .asc schematic & netlist)
    7. search_web_for_circuit_or_model(Live web research for specs & pinouts)
==================================================================
""")
    
    agent = get_agent()

    demos = {
        "1": (
            "DEMO 1 — Single Tool Execution: Weather in Paris",
            "What is the weather in Paris?"
        ),
        "2": (
            "DEMO 2 — Multi-Tool Dynamic Chaining: Tokyo Weather + $1500 JPY Conversion + Report",
            "Check the weather in Tokyo, convert $1500 USD to JPY using the available rate mechanism, and save a travel report."
        ),
        "3": (
            "DEMO 3 — Autonomous Failure Recovery: $1500 USD -> JPY Live Outage & Fallback",
            "Get the USD/JPY rate and convert $1500."
        ),
        "4": (
            "Autodesk Fusion 360 3D CAD Generation",
            "Design a parametric sensor mounting bracket in Autodesk Fusion 360 with length 80mm, "
            "width 40mm, thickness 4mm, and two 5mm screw holes. Generate the script."
        ),
        "5": (
            "LTspice Circuit Schematic & Netlist Generation",
            "Design a passive low-pass RC filter circuit for LTspice with a target cutoff frequency of 1 kHz. "
            "Calculate component values and generate the .asc schematic and simulation netlist."
        ),
        "6": (
            "Live Web Research (Datasheets & Pinouts)",
            "Look up the pinout and function of the LM741 operational amplifier using web search, and write a summary."
        ),
    }

    while True:
        print("\nSelect a demonstration or action:")
        print("  1. DEMO 1: Single Tool Execution (Paris Weather)")
        print("  2. DEMO 2: Multi-Tool Dynamic Chaining (Tokyo Weather + $1500 Conversion + Report)")
        print("  3. DEMO 3: Autonomous Failure Recovery (Troublemaker Outage -> Benchmark Recovery)")
        print("  4. Autodesk Fusion 360 CAD Generation")
        print("  5. LTspice Circuit Schematic Generation (.asc)")
        print("  6. Live Web Research (IC Pinouts / CAD Specs)")
        print("  7. Enter custom prompt")
        print("  8. View Architecture Comparison (Custom Engine vs LangChain)")
        print("  Q. Quit")

        choice = input("\nEnter choice [1-8 or Q]: ").strip()

        if choice.upper() == "Q":
            print("Goodbye!")
            break
        elif choice in demos:
            title, prompt = demos[choice]
            print(f"\n---> Running: {title}")
            agent.run(prompt)
        elif choice == "7":
            prompt = input("\nEnter your custom prompt for the agent: ").strip()
            if prompt:
                agent.run(prompt)
        elif choice == "8":
            if os.path.exists("bonus_comparison.md"):
                with open("bonus_comparison.md", "r", encoding="utf-8") as f:
                    print("\n" + f.read())
            else:
                print("bonus_comparison.md not found.")
        else:
            print("Invalid choice, please select 1-8 or Q.")


if __name__ == "__main__":
    # Check if run with non-interactive CLI flag: e.g. python main.py --demo 1
    if len(sys.argv) > 1 and sys.argv[1].startswith("--demo"):
        target = sys.argv[2] if len(sys.argv) > 2 else (sys.argv[1].split("=")[1] if "=" in sys.argv[1] else "all")
        agent = get_agent()
        demo_dict = {
            "1": (
                "DEMO 1 — SINGLE TOOL (Paris Weather)",
                "What is the weather in Paris?"
            ),
            "2": (
                "DEMO 2 — MULTI TOOL (Tokyo Weather + $1500 JPY Conversion + Report)",
                "Check the weather in Tokyo, convert $1500 USD to JPY using the available rate mechanism, and save a travel report."
            ),
            "3": (
                "DEMO 3 — AUTONOMOUS FAILURE RECOVERY (Troublemaker Live Rate Failure -> Fallback)",
                "Get the USD/JPY rate and convert $1500."
            ),
        }
        if target in demo_dict:
            title, prompt = demo_dict[target]
            print(f"\n==================================================================")
            print(f"🚀 [RUNNING {title}]")
            print(f"==================================================================")
            agent.run(prompt)
        elif target == "all":
            for d_id in ["1", "2", "3"]:
                title, prompt = demo_dict[d_id]
                print(f"\n==================================================================")
                print(f"🚀 [RUNNING {title}]")
                print(f"==================================================================")
                agent.run(prompt)
        else:
            print(f"Unknown demo '{target}'. Available: 1, 2, 3, or all")
            sys.exit(1)
    else:
        run_demo_menu()
