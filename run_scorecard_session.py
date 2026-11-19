#!/usr/bin/env python3
"""
Simplified scorecard: one LLM turn per ticker (all questions v2), compact context between tickers.

Examples:
  python3 run_scorecard_session.py --tickers ISRG,IDXX --provider gemini --model gemini-2.5-pro
  python3 run_scorecard_session.py --tickers ISRG --ingest /tmp/isrg_session.json
  python3 run_scorecard_session.py --tickers ISRG --build-prompt-only -o /tmp/isrg_prompt.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from scorecard_cloud import load_dotenv

load_dotenv()

from scorecard_db import (
    compute_scores,
    create_run,
    finalize_run,
    get_answers,
    get_sp500_list,
    gcs_download,
    init_db,
    save_answer,
)
from scorecard_runner import company_info_for_ticker, load_questions
from scorecard_session import (
    DEFAULT_REVIEW_TICKERS,
    build_one_turn_user_prompt,
    call_claude,
    call_cursor_one_shot,
    call_gemini,
    load_ingest_payload,
    parse_one_turn_response,
)

LLM_KEY = "session"
DEFAULT_GEMINI = "gemini-2.5-pro"
DEFAULT_CLAUDE = "claude-sonnet-4-20250514"
DEFAULT_CURSOR = "claude-sonnet-4-20250514"
MAX_OUTPUT_TOKENS = 65536


def persist_answers(
    run_id: int,
    rows: list[dict],
    prompt_version: str,
) -> None:
    for row in rows:
        save_answer(
            run_id,
            row["question_id"],
            row["categoria"],
            row["pregunta"],
            row["score"],
            row["answer_text"],
            prompt_version,
        )


def finalize_from_run(run_id: int) -> None:
    answers = get_answers(run_id)
    cat_scores, total = compute_scores(answers)
    circulo = "\n\n".join(
        a["answer_text"]
        for a in answers
        if a.get("categoria") == "Circulo de Competencia"
    )
    finalize_run(
        run_id,
        {
            "Fuerzas": cat_scores.get("Fuerzas"),
            "Industria": cat_scores.get("Industria"),
            "MOAT Company": cat_scores.get("MOAT Company"),
            "Management & Culture": cat_scores.get("Management & Culture"),
            "Brand": cat_scores.get("Brand"),
            "Finance": cat_scores.get("Finance"),
        },
        total,
        circulo_notes=circulo,
    )


def ingest_json(
    ticker: str,
    path: str,
    *,
    prompt_version: str,
    model_name: str,
) -> int:
    payload = load_ingest_payload(path)
    questions = load_questions()
    rows, summary = parse_one_turn_response(json.dumps(payload), questions)
    run_id = create_run(ticker.upper(), LLM_KEY, prompt_version, model_name)
    persist_answers(run_id, rows, prompt_version)
    finalize_from_run(run_id)
    print(
        f"Ingested {ticker.upper()} run_id={run_id} "
        f"(summary chars={len(summary)})",
        flush=True,
    )
    return run_id


def invoke_llm(provider: str, prompt: str, model: str) -> str:
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise SystemExit("GEMINI_API_KEY is not set")
        return call_gemini(key, model, prompt, max_output_tokens=MAX_OUTPUT_TOKENS)
    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY is not set")
        return call_claude(key, model, prompt, max_output_tokens=MAX_OUTPUT_TOKENS)
    if provider == "cursor":
        key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not key:
            raise SystemExit("CURSOR_API_KEY is not set")
        workspace = str(os.path.dirname(os.path.abspath(__file__)))
        return call_cursor_one_shot(
            prompt, model=model, api_key=key, workspace=workspace
        )
    raise SystemExit(f"Unknown provider: {provider}")


def run_session(
    tickers: list[str],
    *,
    provider: str,
    model: str,
    prompt_version: str,
    save_raw_dir: str | None,
) -> None:
    gcs_download()
    init_db()
    companies = get_sp500_list()
    questions = load_questions()
    prior_summaries: list[str] = []

    for i, ticker in enumerate(tickers):
        ticker = ticker.upper().strip()
        co_info = company_info_for_ticker(ticker, companies)
        print(f"\n[{i + 1}/{len(tickers)}] One-turn session for {ticker}...", flush=True)
        prompt = build_one_turn_user_prompt(
            ticker,
            prompt_version=prompt_version,
            company_info=co_info,
            prior_summaries=prior_summaries or None,
        )
        print(f"  Prompt size: {len(prompt):,} chars", flush=True)
        t0 = time.time()
        raw = invoke_llm(provider, prompt, model)
        elapsed = time.time() - t0
        print(f"  LLM response: {len(raw):,} chars in {elapsed:.1f}s", flush=True)

        if save_raw_dir:
            os.makedirs(save_raw_dir, exist_ok=True)
            raw_path = os.path.join(save_raw_dir, f"{ticker}_{prompt_version}_raw.txt")
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw)

        rows, summary = parse_one_turn_response(raw, questions)
        run_id = create_run(ticker, LLM_KEY, prompt_version, model)
        persist_answers(run_id, rows, prompt_version)
        finalize_from_run(run_id)

        if summary:
            prior_summaries.append(f"{ticker}: {summary}")
            print(f"  Context summary stored ({len(summary)} chars)", flush=True)

        answers = get_answers(run_id)
        _, total = compute_scores(answers)
        print(f"  run_id={run_id} total_score={total:.2f}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Single-turn scorecard session runner")
    p.add_argument(
        "--tickers",
        default=",".join(DEFAULT_REVIEW_TICKERS),
        help="Comma-separated tickers (default: en-revisión propuesta)",
    )
    p.add_argument("--prompt-version", default="v2", choices=("v1", "v2"))
    p.add_argument(
        "--provider",
        default="gemini",
        choices=("gemini", "claude", "cursor"),
    )
    p.add_argument("--model", default="", help="Override default model for provider")
    p.add_argument("--ingest", metavar="JSON", help="Ingest pre-generated session JSON")
    p.add_argument(
        "--build-prompt-only",
        action="store_true",
        help="Write mega-prompt for first ticker and exit",
    )
    p.add_argument("-o", "--output", help="Output path for --build-prompt-only")
    p.add_argument(
        "--save-raw-dir",
        default=".scratch/scorecard-session",
        help="Directory for raw LLM responses",
    )
    args = p.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        raise SystemExit("No tickers specified")

    default_models = {
        "gemini": DEFAULT_GEMINI,
        "claude": DEFAULT_CLAUDE,
        "cursor": DEFAULT_CURSOR,
    }
    model = args.model or default_models[args.provider]

    if args.build_prompt_only:
        gcs_download()
        init_db()
        companies = get_sp500_list()
        t = tickers[0].upper()
        prompt = build_one_turn_user_prompt(
            t,
            prompt_version=args.prompt_version,
            company_info=company_info_for_ticker(t, companies),
        )
        out = args.output or f".scratch/scorecard-session/{t}_prompt.txt"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"Wrote {len(prompt):,} chars to {out}")
        return

    if args.ingest:
        if len(tickers) != 1:
            raise SystemExit("--ingest requires exactly one ticker")
        gcs_download()
        init_db()
        ingest_json(tickers[0], args.ingest, prompt_version=args.prompt_version, model_name=model)
        return

    run_session(
        tickers,
        provider=args.provider,
        model=model,
        prompt_version=args.prompt_version,
        save_raw_dir=args.save_raw_dir,
    )


if __name__ == "__main__":
    main()