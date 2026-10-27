#!/usr/bin/env python3
"""
Run the Value Investing scorecard locally via Cursor Agent SDK.

One isolated research agent per question (Agent.prompt one-shot), results saved
to scorecard.db (+ GCS if configured). View runs in the Streamlit Scorecard page.

Requires:
  export CURSOR_API_KEY=...
  pip install cursor-sdk

Example:
  python3 run_scorecard_cursor.py AAPL --prompt-version v2
  python3 run_scorecard_cursor.py MSFT --categories Finance,MOAT Company
  python3 run_scorecard_cursor.py AAPL --fresh
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from scorecard_db import (
    compute_scores,
    create_run,
    finalize_run,
    gcs_download,
    get_answered_question_ids,
    get_answers,
    get_or_create_partial_run,
    get_sp500_list,
    init_db,
    save_answer,
    set_run_partial,
)
from scorecard_runner import (
    all_scored_categories,
    build_prompt,
    call_cursor_research_agent,
    company_info_for_ticker,
    extract_score,
    load_questions,
)

LLM_KEY = "cursor"


def _parse_categories(raw: str | None) -> tuple[bool, list[str]]:
    """Return (run_circulo, scored_category_names)."""
    if not raw or raw.lower() in ("all", "todas", "*"):
        return True, all_scored_categories()
    names = [c.strip() for c in raw.split(",") if c.strip()]
    run_circulo = any(c.lower().startswith("circulo") for c in names)
    scored = [c for c in names if not c.lower().startswith("circulo")]
    return run_circulo, scored


def run_scorecard(
    ticker: str,
    *,
    prompt_version: str,
    model: str,
    api_key: str,
    workspace: str,
    categories: str | None,
    fresh: bool,
    delay: float,
) -> int:
    ticker = ticker.upper().strip()
    prompt_version = prompt_version.lower()
    if prompt_version not in ("v1", "v2"):
        raise SystemExit("prompt-version must be v1 or v2")

    gcs_download()
    init_db()

    questions = load_questions()
    circulo_qs = [q for q in questions if q["categoria"] == "Circulo de Competencia"]
    scored_qs = [q for q in questions if q["categoria"] != "Circulo de Competencia"]
    all_q_ids = {q["id"] for q in questions}

    companies = get_sp500_list()
    co_info = company_info_for_ticker(ticker, companies)

    is_all_categories = categories is None
    run_circulo, selected_cats = _parse_categories(
        "all" if is_all_categories else categories
    )

    if fresh:
        run_id = create_run(ticker, LLM_KEY, prompt_version, model)
    elif not is_all_categories:
        run_id, _ = get_or_create_partial_run(ticker, LLM_KEY, prompt_version, model)
    else:
        run_id = create_run(ticker, LLM_KEY, prompt_version, model)

    already = get_answered_question_ids(run_id)
    to_circulo = [q for q in circulo_qs if q["id"] not in already] if run_circulo else []
    to_scored = [
        q
        for q in scored_qs
        if q["id"] not in already and q["categoria"] in selected_cats
    ]
    total = len(to_circulo) + len(to_scored)
    if total == 0:
        print("No pending questions for this run.")
    else:
        print(f"Run id={run_id} · {ticker} · cursor · {prompt_version} · {total} question(s)")
        done = 0
        errors: list[str] = []

        for q in to_circulo:
            done += 1
            label = f"[{done}/{total}] Contexto id={q['id']}"
            print(label, flush=True)
            prompt = build_prompt(q, ticker, prompt_version, co_info)
            try:
                ans = call_cursor_research_agent(
                    prompt, model=model, api_key=api_key, workspace=workspace
                )
            except Exception as e:
                ans = f"[Error: {e}]"
                errors.append(str(e))
            save_answer(
                run_id, q["id"], q["categoria"], q["pregunta"], None, ans, prompt_version
            )
            if delay > 0:
                time.sleep(delay)

        for q in to_scored:
            done += 1
            print(
                f"[{done}/{total}] {q['categoria']} id={q['id']}: {q['pregunta'][:60]}…",
                flush=True,
            )
            prompt = build_prompt(q, ticker, prompt_version, co_info)
            try:
                ans = call_cursor_research_agent(
                    prompt, model=model, api_key=api_key, workspace=workspace
                )
                score = extract_score(ans)
            except Exception as e:
                ans = f"[Error: {e}]"
                score = None
                errors.append(str(e))
            save_answer(
                run_id,
                q["id"],
                q["categoria"],
                q["pregunta"],
                score,
                ans,
                prompt_version,
            )
            if delay > 0:
                time.sleep(delay)

        if errors:
            print(f"Completed with {len(errors)} error(s).", file=sys.stderr)

    answered = get_answered_question_ids(run_id)
    if all_q_ids <= answered:
        answers = get_answers(run_id)
        cat_avgs, total_score = compute_scores(answers)
        finalize_run(run_id, cat_avgs, total_score)
        print(f"Scorecard complete · total {total_score:.2f} / 10 · run_id={run_id}")
    else:
        set_run_partial(run_id)
        remaining = len(all_q_ids - answered)
        print(f"Partial run saved · {remaining} question(s) remaining · run_id={run_id}")

    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scorecard via Cursor Agent SDK (local).")
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL")
    parser.add_argument(
        "--prompt-version",
        default="v2",
        help="Prompt set from scorecard_questions.json (default: v2)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("CURSOR_SCORECARD_MODEL", "composer-2.5"),
        help="Cursor model id (default: composer-2.5 or CURSOR_SCORECARD_MODEL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("CURSOR_API_KEY"),
        help="Cursor API key (default: CURSOR_API_KEY env)",
    )
    parser.add_argument(
        "--workspace",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Local cwd for the agent (default: repo root)",
    )
    parser.add_argument(
        "--categories",
        default="all",
        help='Comma-separated categories, or "all". Include "Circulo de Competencia" explicitly for context questions.',
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard prior run for this ticker/llm/prompt and start fresh",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between questions (rate limits)",
    )
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Set CURSOR_API_KEY or pass --api-key")

    cats = (
        None
        if args.categories.lower() in ("all", "todas", "*")
        else args.categories
    )
    run_scorecard(
        args.ticker,
        prompt_version=args.prompt_version,
        model=args.model,
        api_key=args.api_key,
        workspace=args.workspace,
        categories=cats,
        fresh=args.fresh,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
