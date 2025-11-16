#!/usr/bin/env python3
from __future__ import annotations
import argparse

# Console-safe ticks/crosses on Windows/Linux
from core.console import enable_utf8_stdout, emit_ok, emit_fail, emit_info
enable_utf8_stdout()

# --- Scenario 1 (plant) ---
from .scenario1_overtemp import main as run_overtemp
from .scenario1_overpressure import main as run_overpressure

# --- Scenario 2 (drone) ---
from .scenario2_landing import main as run_landing

# --- Scenario 3 (desktop / AgentOS) ---
from .scenario3_agentos import main as run_desktop_agentos
from .scenario3_agentos_llm import main as run_desktop_agentos_llm


def main():
    parser = argparse.ArgumentParser(description="ISL-NANO unified runner")
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            # Scenario 1
            "overtemp", "overpressure",
            # Scenario 2
            "landing",
            # Scenario 3
            "desktop_agentos", "desktop_agentos_llm",
        ],
        help="Select which demo to run."
    )
    parser.add_argument(
        "--agentos-goals",
        default="ide_hello,web_search",
        help="Comma-separated list of goals for desktop_agentos modes."
    )
    args = parser.parse_args()

    if args.mode == "overtemp":
        emit_info("Running Scenario 1: Overtemperature control")
        run_overtemp()  # prints its own status/logs
    elif args.mode == "overpressure":
        emit_info("Running Scenario 1: Overpressure control")
        run_overpressure()  # prints its own status/logs
    elif args.mode == "landing":
        emit_info("Running Scenario 2: Drone landing")
        run_landing()  # prints its own status/logs
    elif args.mode == "desktop_agentos":
        emit_info("Running Scenario 3: AgentOS automation")
        goals = tuple(s.strip() for s in args.agentos_goals.split(",") if s.strip())
        run_desktop_agentos(goals=goals)
        emit_ok("AgentOS run complete. Log written to: runs/isl_nano_run_desktop_agentos.jsonl")
    elif args.mode == "desktop_agentos_llm":
        emit_info("Running Scenario 3: AgentOS + LLM reasoning")
        goals = tuple(s.strip() for s in args.agentos_goals.split(",") if s.strip())
        run_desktop_agentos_llm(goals=goals)
        emit_ok("AgentOS+LLM run complete. Log written to: runs/isl_nano_run_desktop_agentos_llm.jsonl")
    else:
        emit_fail(f"Unsupported mode: {args.mode}")

if __name__ == "__main__":
    main()
