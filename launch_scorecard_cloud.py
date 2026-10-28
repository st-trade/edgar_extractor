#!/usr/bin/env python3
"""
Start ONE Cursor Cloud Agent that runs `run_scorecard_cursor.py` in a remote VM.

Run from your laptop (with repo access + API key). The cloud agent clones the
GitHub repo, installs deps, and executes the scorecard CLI (~74 research agents
in parallel with configurable workers).

Prerequisites:
  - Cursor API key (Dashboard → API Keys)
  - GitHub repo connected in Cursor (for Cloud Agents)
  - Optional: GCS_BUCKET + GCS_CREDENTIALS_JSON for Streamlit sync

Setup wizard (optional):
  ./scripts/scorecard_cloud_wizard.sh

Example:
  export CURSOR_API_KEY=...
  python3 launch_scorecard_cloud.py AAPL --ref main
  python3 launch_scorecard_cloud.py AAPL --no-wait   # print agent id and exit
"""

from __future__ import annotations

import argparse
import os
import sys

from scorecard_cloud import (
    build_orchestrator_prompt,
    cloud_env_vars_for_scorecard,
    default_repo_url,
    load_dotenv,
)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Launch a Cursor Cloud Agent to run the scorecard CLI in a VM."
    )
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--repo-url",
        default=default_repo_url(),
        help="GitHub repo URL (default: git remote origin, or SCORECARD_REPO_URL)",
    )
    parser.add_argument(
        "--ref",
        default=os.environ.get("SCORECARD_REPO_REF", "main"),
        help="Git ref to clone (branch, tag, or SHA). Use your feature branch until merged.",
    )
    parser.add_argument("--prompt-version", default="v2")
    parser.add_argument(
        "--model",
        default=os.environ.get("CURSOR_SCORECARD_MODEL", "composer-2.5"),
        help="Model for both the orchestrator and per-question runs in the VM",
    )
    parser.add_argument("--categories", default="all")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Max concurrent question agents in VM (default: CLI default / CURSOR_SCORECARD_WORKERS)",
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=1.0,
        help="Seconds between starting each agent in VM (default: 1; 0 = none)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CURSOR_API_KEY"),
        help="Cursor API key (default: CURSOR_API_KEY)",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Start the cloud agent and exit without waiting for completion",
    )
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Set CURSOR_API_KEY or pass --api-key")
    if not args.repo_url:
        raise SystemExit(
            "Could not detect repo URL. Pass --repo-url https://github.com/org/repo"
        )

    env_vars = cloud_env_vars_for_scorecard()
    if not env_vars.get("CURSOR_API_KEY"):
        env_vars["CURSOR_API_KEY"] = args.api_key

    from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, CloudRepository

    from run_scorecard_cursor import DEFAULT_STAGGER, resolve_workers

    workers = resolve_workers(args.workers)
    stagger = args.stagger
    if stagger < 0:
        raise SystemExit("--stagger must be >= 0")

    prompt = build_orchestrator_prompt(
        args.ticker,
        prompt_version=args.prompt_version,
        model=args.model,
        categories=args.categories,
        fresh=args.fresh,
        workers=workers,
        stagger=stagger,
    )

    ticker = args.ticker.upper()
    options = AgentOptions(
        model=args.model,
        api_key=args.api_key,
        mode="agent",
        cloud=CloudAgentOptions(
            repos=[CloudRepository(url=args.repo_url, starting_ref=args.ref)],
            auto_create_pr=False,
            env_vars=env_vars,
            metadata={
                "workflow": "scorecard",
                "ticker": ticker,
                "prompt_version": args.prompt_version,
            },
        ),
    )

    print(f"Starting cloud agent · repo={args.repo_url} · ref={args.ref} · ticker={ticker}")
    if args.no_wait:
        with Agent.create(options) as agent:
            run = agent.send(prompt)
            print(f"Cloud agent id: {agent.agent_id}")
            print(f"Run id: {run.id}")
            print(f"Monitor: https://cursor.com/agents/{agent.agent_id}")
            print("The VM will run run_scorecard_cursor.py; check the agent log for progress.")
        return

    with Agent.create(options) as agent:
        print(f"Cloud agent id: {agent.agent_id}")
        print(f"Monitor: https://cursor.com/agents/{agent.agent_id}")
        result = agent.send(prompt).wait()
        text = (result.result or "").strip()
        if text:
            print("\n--- Agent report ---\n")
            print(text)
        if result.error_message:
            print(f"\nError: {result.error_message}", file=sys.stderr)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
