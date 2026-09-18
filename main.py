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

    # Initialize our from-scratch agent brain
    agent = CustomAgentBrain(api_key=api_key)

    # Register all 6 tools dynamically
    agent.register_tools([
        get_live_weather,
        calculate_currency_or_math,
        save_report_file,
        unreliable_live_rates,
        generate_fusion360_cad,
        generate_ltspice_circuit,
    ])

    return agent


def run_demo_menu():
    print("""
==================================================================
  🧠 BUILD THE BRAIN, NOT THE PUPPET: CUSTOM AGENT FRAMEWORK
==================================================================
  Tools Loaded:
    1. get_live_weather          (Real-world weather lookup)
    2. calculate_currency_or_math (Safe precision calculator)
    3. save_report_file          (Local hard-drive file writer)
    4. unreliable_live_rates     (The Troublemaker: intentional 503)
==================================================================
""")
    
    agent = get_agent()

    demos = {
        "1": (
            "Single-Tool Test: Weather Lookup",
            "What is the current weather in Tokyo?"
        ),
        "2": (
            "Multi-Tool Chaining: Weather + Math + File Saving",
            "Check the weather in Tokyo. Convert $1500 USD into Japanese Yen at 155.2 JPY/USD. "
            "Then write a complete travel summary report into 'tokyo_plan.txt'."
        ),
        "3": (
            "Error Recovery (The Troublemaker Test)",
            "Fetch the live exchange rate for USD/EUR using the unreliable_live_rates tool. "
            "If that service fails or errors out, observe the error, don't give up, and instead "
            "use calculate_currency_or_math with rate 0.92 to convert $500 USD into Euros. "
            "Finally, save an incident report into 'recovery_log.txt'."
        ),
    }

    while True:
        print("\nSelect an action:")
        print("  1. Run Single-Tool Test (Weather)")
        print("  2. Run Multi-Tool Chain (Weather + Math + File Save)")
        print("  3. Run Error Recovery Test (The Troublemaker -> Self-Correction)")
        print("  4. Enter your own custom prompt")
        print("  5. View Bonus Comparison (Our Engine vs LangChain)")
        print("  Q. Quit")

        choice = input("\nEnter choice [1-5 or Q]: ").strip()

        if choice.upper() == "Q":
            print("Goodbye!")
            break
        elif choice in demos:
            title, prompt = demos[choice]
            print(f"\n---> Running: {title}")
            agent.run(prompt)
        elif choice == "4":
            prompt = input("\nEnter your custom prompt for the agent: ").strip()
            if prompt:
                agent.run(prompt)
        elif choice == "5":
            if os.path.exists("bonus_comparison.md"):
                with open("bonus_comparison.md", "r", encoding="utf-8") as f:
                    print("\n" + f.read())
            else:
                print("bonus_comparison.md not found.")
        else:
            print("Invalid choice, please select 1-5 or Q.")


if __name__ == "__main__":
    # Check if run with non-interactive flag
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        agent = get_agent()
        print("\n[AUTOMATED DEMO] Running Error Recovery Test...")
        agent.run(
            "Fetch the live exchange rate for USD/EUR using unreliable_live_rates. "
            "If it fails, recover and use calculate_currency_or_math to convert 500 * 0.92, "
            "and save the outcome into 'demo_output.txt'."
        )
    else:
        run_demo_menu()
