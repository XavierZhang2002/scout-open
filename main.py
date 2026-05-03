#!/usr/bin/env python3
"""
Scout — CLI Entry Point

Usage:
    # Interactive mode
    python main.py

    # Single query mode
    python main.py --query "What is the main finding?" --cwd /path/to/docs

    # With custom config
    python main.py --config /path/to/config.yaml --model "venus,claude-4-5-sonnet-20250929"
"""

import argparse
import os
import sys

import anyio


def main():
    parser = argparse.ArgumentParser(
        description="Scout — Active Information Foraging Agent for Long-Text Understanding"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml (default: auto-discover)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model override (e.g. 'venus,deepseek-v3.1-terminus')",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Working directory containing documents to read",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Query to run (omit for interactive mode)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Maximum agent turns (default: from config)",
    )
    parser.add_argument(
        "--no-planner",
        action="store_true",
        help="Disable Planner SubAgent",
    )
    parser.add_argument(
        "--no-evaluator",
        action="store_true",
        help="Disable Evaluator SubAgent",
    )

    args = parser.parse_args()

    # Load config
    from scout.config import load_config

    overrides = {}
    if args.model:
        overrides["model"] = args.model
    if args.cwd:
        overrides["cwd"] = args.cwd
    if args.max_turns:
        overrides["max_turns"] = args.max_turns
    if args.no_planner:
        overrides["use_planner_agent"] = False
    if args.no_evaluator:
        overrides["use_evaluator_agent"] = False

    config = load_config(args.config, **overrides)

    # Ensure cwd exists
    if config.cwd:
        os.makedirs(config.cwd, exist_ok=True)

    from scout.agent import query_agent

    if args.query:
        # Single query mode
        result, tiktoken_usages, api_usage, num_turns, tool_usage = anyio.run(
            query_agent,
            args.query,
            None,  # model
            None,  # server
            None,  # cache_path
            config,
        )
        print(f"\n{'=' * 60}")
        print(f"Result: {result}")
        print(f"Turns: {num_turns}")
        print(f"Tiktoken Usage: {tiktoken_usages}")
        print(f"API Usage: {api_usage}")
        print(f"Tool Usage: {tool_usage}")
    else:
        # Interactive mode
        print("Scout — Long Text Reading Agent (Interactive Mode)")
        print(f"Model: {config.model}")
        print(f"API:   {config.base_url}")
        print("Type 'exit' or 'quit' to stop.\n")

        while True:
            try:
                user_input = input(">>> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye.")
                break

            try:
                result, *_ = anyio.run(
                    query_agent,
                    user_input,
                    None,
                    None,
                    None,
                    config,
                )
                print(f"\nResult: {result}\n")
            except Exception as e:
                print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
