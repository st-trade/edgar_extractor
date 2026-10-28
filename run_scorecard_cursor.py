#!/usr/bin/env python3
"""
Run the Value Investing scorecard via Cursor Agent SDK (local machine or cloud VM).

One isolated research agent per question (Agent.prompt one-shot), results saved
to scorecard.db (+ GCS if configured). View runs in the Streamlit Scorecard page.

Requires:
  export CURSOR_API_KEY=...
  pip install cursor-sdk

Example:
  python3 run_scorecard_cursor.py AAPL --prompt-version v2
  python3 run_scorecard_cursor.py MSFT --categories Finance,MOAT Company --workers 4
  python3 run_scorecard_cursor.py AAPL --fresh --stagger 0
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from scorecard_cloud import load_dotenv

load_dotenv()

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

MIN_WORKERS = 1
MAX_WORKERS = 10
DEFAULT_WORKERS = 3
DEFAULT_STAGGER = 1.0


def clamp_workers(n: int) -> int:
    if n < MIN_WORKERS or n > MAX_WORKERS:
        raise SystemExit(
            f"--workers must be between {MIN_WORKERS} and {MAX_WORKERS} (got {n})"
        )
    return n


def resolve_workers(cli_workers: int | None) -> int:
    if cli_workers is not None:
        return clamp_workers(cli_workers)
    env = os.environ.get("CURSOR_SCORECARD_WORKERS", "").strip()
    if env:
        try:
            return clamp_workers(int(env))
        except ValueError:
            raise SystemExit(f"Invalid CURSOR_SCORECARD_WORKERS: {env!r}")
    return DEFAULT_WORKERS


def run_parallel_phase(
    questions: list[dict],
    *,
    phase_label: str,
    total: int,
    run_id: int,
    ticker: str,
    prompt_version: str,
    co_info: dict | None,
    model: str,
    api_key: str,
    workspace: str,
    workers: int,
    stagger: float,
    scored: bool,
    persist_lock: threading.Lock,
    progress_lock: threading.Lock,
    done_counter: list[int],
    errors: list[str],
    errors_lock: threading.Lock,
    agent_call: Callable[..., str] = call_cursor_research_agent,
    save_fn: Callable[..., None] = save_answer,
    progress_ticker_interval: float = 5.0,
) -> None:
    if not questions:
        return

    running_lock = threading.Lock()
    running_count = [0]
    durations_lock = threading.Lock()
    completed_durations: list[float] = []
    ticker_stop = threading.Event()

    def _progress_ticker() -> None:
        while not ticker_stop.is_set():
            with progress_lock:
                done = done_counter[0]
            with running_lock:
                running = running_count[0]
            pending = total - done
            eta_s: float | None = None
            with durations_lock:
                if completed_durations and pending > 0:
                    avg = sum(completed_durations) / len(completed_durations)
                    eta_s = avg * pending
            eta_part = f" ETA~{eta_s:.0f}s" if eta_s is not None else ""
            print(
                f"[progress] phase={phase_label} running={running} "
                f"pending={pending} done={done}/{total}{eta_part}",
                flush=True,
            )
            if ticker_stop.wait(progress_ticker_interval):
                break

    ticker_thread = threading.Thread(target=_progress_ticker, daemon=True)
    ticker_thread.start()

    def _run_one(q: dict) -> None:
        qid = q["id"]
        cat = q.get("categoria", "")
        if phase_label == "circulo":
            print(f"START {phase_label} id={qid} (context)", flush=True)
        else:
            print(
                f"START {phase_label} id={qid} category={cat}",
                flush=True,
            )
        with running_lock:
            running_count[0] += 1
        t0 = time.monotonic()
        prompt = build_prompt(q, ticker, prompt_version, co_info)
        score = None
        err_msg: str | None = None
        try:
            ans = agent_call(
                prompt, model=model, api_key=api_key, workspace=workspace
            )
            if scored:
                score = extract_score(ans)
        except Exception as e:
            err_msg = str(e)
            ans = f"[Error: {e}]"
            with errors_lock:
                errors.append(err_msg)
        elapsed = time.monotonic() - t0
        with durations_lock:
            completed_durations.append(elapsed)
        with running_lock:
            running_count[0] -= 1
        with persist_lock:
            save_fn(
                run_id,
                q["id"],
                q["categoria"],
                q["pregunta"],
                score,
                ans,
                prompt_version,
            )
        with progress_lock:
            done_counter[0] += 1
            d = done_counter[0]
            if err_msg:
                print(
                    f"[{d}/{total}] ERROR {phase_label} id={qid} "
                    f"after {elapsed:.1f}s: {err_msg}",
                    flush=True,
                )
            elif phase_label == "circulo":
                print(
                    f"[{d}/{total}] Context id={qid} done "
                    f"(elapsed={elapsed:.1f}s)",
                    flush=True,
                )
            else:
                print(
                    f"[{d}/{total}] {cat} id={qid}: "
                    f"{q['pregunta'][:60]}… done "
                    f"(elapsed={elapsed:.1f}s, score={score})",
                    flush=True,
                )

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for i, q in enumerate(questions):
                if i > 0 and stagger > 0:
                    time.sleep(stagger)
                futures.append(pool.submit(_run_one, q))
            for fut in as_completed(futures):
                fut.result()
    finally:
        ticker_stop.set()
        ticker_thread.join(timeout=2.0)


def run_scorecard(
    ticker: str,
    *,
    prompt_version: str,
    model: str,
    api_key: str,
    workspace: str,
    categories: str | None,
    fresh: bool,
    workers: int,
    stagger: float,
) -> int:
    ticker = ticker.upper().strip()
    prompt_version = prompt_version.lower()
    if prompt_version not in ("v1", "v2"):
        raise SystemExit("prompt-version must be v1 or v2")

    workers = clamp_workers(workers)
    if stagger < 0:
        raise SystemExit("--stagger must be >= 0")

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
        print(
            f"Run id={run_id} · {ticker} · cursor · {prompt_version} · "
            f"{total} question(s) · workers={workers} · stagger={stagger}s",
            flush=True,
        )
        done_counter = [0]
        errors: list[str] = []
        persist_lock = threading.Lock()
        progress_lock = threading.Lock()
        errors_lock = threading.Lock()

        phase_kw = dict(
            total=total,
            run_id=run_id,
            ticker=ticker,
            prompt_version=prompt_version,
            co_info=co_info,
            model=model,
            api_key=api_key,
            workspace=workspace,
            workers=workers,
            stagger=stagger,
            persist_lock=persist_lock,
            progress_lock=progress_lock,
            done_counter=done_counter,
            errors=errors,
            errors_lock=errors_lock,
        )

        run_parallel_phase(
            to_circulo,
            phase_label="circulo",
            scored=False,
            **phase_kw,
        )
        run_parallel_phase(
            to_scored,
            phase_label="scored",
            scored=True,
            **phase_kw,
        )

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


def _parse_categories(raw: str | None) -> tuple[bool, list[str]]:
    """Return (run_circulo, scored_category_names)."""
    if not raw or raw.lower() in ("all", "todas", "*"):
        return True, all_scored_categories()
    names = [c.strip() for c in raw.split(",") if c.strip()]
    run_circulo = any(c.lower().startswith("circulo") for c in names)
    scored = [c for c in names if not c.lower().startswith("circulo")]
    return run_circulo, scored


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run scorecard via Cursor Agent SDK. Questions run in parallel "
            f"(default {DEFAULT_WORKERS} workers, max {MAX_WORKERS})."
        ),
    )
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
        "--workers",
        type=int,
        default=None,
        help=(
            f"Max concurrent question agents (default: {DEFAULT_WORKERS} or "
            "CURSOR_SCORECARD_WORKERS; max 10)"
        ),
    )
    parser.add_argument(
        "--stagger",
        type=float,
        default=DEFAULT_STAGGER,
        help="Seconds between starting each new agent (default: 1; use 0 for none)",
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
        workers=resolve_workers(args.workers),
        stagger=args.stagger,
    )


if __name__ == "__main__":
    main()
