#!/usr/bin/env python3
"""Export a scorecard run from scorecard.db to Excel and Markdown."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from scorecard_db import get_answers, get_conn, get_run, get_sp500_list
from scorecard_runner import build_prompt, company_info_for_ticker, load_questions

CATEGORY_ORDER = [
    "Circulo de Competencia",
    "Fuerzas",
    "Industria",
    "MOAT Company",
    "Management & Culture",
    "Brand",
    "Finance",
]

RUN_SCORE_KEYS = {
    "Fuerzas": "score_fuerzas",
    "Industria": "score_industria",
    "MOAT Company": "score_moat",
    "Management & Culture": "score_mgmt",
    "Brand": "score_brand",
    "Finance": "score_finance",
}


def get_run_by_id(run_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scorecard_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None


def resolve_run(
    run_id: int | None,
    ticker: str | None,
    llm: str | None,
    prompt_version: str | None,
) -> dict:
    if run_id is not None:
        run = get_run_by_id(run_id)
        if not run:
            raise SystemExit(f"No run with run_id={run_id}")
        return run
    if not ticker or not llm or not prompt_version:
        raise SystemExit("Provide --run-id or (--ticker, --llm, --prompt-version)")
    run = get_run(ticker.upper(), llm.lower(), prompt_version.lower())
    if not run:
        raise SystemExit(
            f"No run for {ticker}/{llm}/{prompt_version}"
        )
    return run


def build_export_df(answers, run, questions_lookup, co_info=None) -> pd.DataFrame:
    rows = []
    for a in answers:
        q_data = questions_lookup.get(a["question_id"])
        pver = a.get("prompt_used", run["prompt_version"])
        full_prompt = (
            build_prompt(q_data, run["ticker"], pver, company_info=co_info)
            if q_data
            else ""
        )
        rows.append(
            {
                "Categoria": a["categoria"],
                "Pregunta": a["pregunta"],
                "Score": a["score"],
                "Prompt_Usado": pver.upper(),
                "Prompt_Completo": full_prompt,
                "Respuesta": a.get("answer_text", ""),
            }
        )
    return pd.DataFrame(rows)


def summary_row(run: dict) -> dict:
    return {
        "Empresa": run["ticker"],
        "LLM": run["llm"].capitalize(),
        "Prompt Version": run["prompt_version"].upper(),
        "Modelo": run.get("model_name", ""),
        "Fecha": (run.get("run_date") or "")[:10],
        "Score Total": run.get("total_score"),
        "Score Fuerzas": run.get("score_fuerzas"),
        "Score Industria": run.get("score_industria"),
        "Score MOAT": run.get("score_moat"),
        "Score Mgmt": run.get("score_mgmt"),
        "Score Brand": run.get("score_brand"),
        "Score Finance": run.get("score_finance"),
    }


def base_name(run: dict) -> str:
    date = (run.get("run_date") or "")[:10]
    return f"scorecard_{run['ticker']}_{run['llm']}_{run['prompt_version']}_{date}"


def write_excel(path: Path, run: dict, exp_df: pd.DataFrame) -> None:
    summary = pd.DataFrame([summary_row(run)])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Resumen", index=False)
        exp_df.to_excel(writer, sheet_name="Prompts y Respuestas", index=False)


def _fmt_score(score) -> str:
    if score is None:
        return "—"
    return str(score)


def write_markdown(path: Path, run: dict, answers: list[dict]) -> None:
    s = summary_row(run)
    lines: list[str] = [
        f"# Scorecard — {run['ticker']}",
        "",
        f"**Total:** {s['Score Total']:.2f} / 10" if s["Score Total"] is not None else "",
        f"**Run ID:** {run['run_id']} · **LLM:** {run['llm']} · **Prompt:** {run['prompt_version']} · **Model:** {run.get('model_name', '')}",
        f"**Fecha:** {s['Fecha']} · **Estado:** {run.get('status', '')}",
        "",
        "## Resumen por categoría",
        "",
        "| Categoría | Score |",
        "| --- | ---: |",
    ]
    for cat in CATEGORY_ORDER:
        if cat == "Circulo de Competencia":
            continue
        key = RUN_SCORE_KEYS.get(cat)
        val = run.get(key) if key else None
        if val is not None:
            lines.append(f"| {cat} | {val:.2f} |")
    lines.append("")

    circulo = (run.get("circulo_notes") or "").strip()
    if circulo:
        lines.extend(["## Notas — Círculo de Competencia", "", circulo, ""])

    by_cat: dict[str, list] = {}
    for a in answers:
        by_cat.setdefault(a["categoria"], []).append(a)

    for cat in CATEGORY_ORDER:
        ans_list = by_cat.get(cat)
        if not ans_list:
            continue
        cat_key = RUN_SCORE_KEYS.get(cat)
        cat_avg = run.get(cat_key) if cat_key else None
        header = f"## {cat}"
        if cat_avg is not None:
            header += f" (promedio {cat_avg:.2f})"
        lines.extend(["", header, ""])
        for a in ans_list:
            if a["score"] is None:
                lines.append(f"### {a['pregunta']}")
            else:
                lines.append(f"### Score {a['score']} — {a['pregunta']}")
            lines.append("")
            body = (a.get("answer_text") or "").strip()
            lines.append(body if body else "_Sin respuesta._")
            lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Export scorecard run to Excel and Markdown")
    p.add_argument("--run-id", type=int, help="scorecard_runs.run_id")
    p.add_argument("--ticker", help="Ticker (with --llm and --prompt-version)")
    p.add_argument("--llm", default="cursor")
    p.add_argument("--prompt-version", default="v2")
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("exports"),
        help="Directory for output files (default: exports/)",
    )
    args = p.parse_args()

    run = resolve_run(args.run_id, args.ticker, args.llm, args.prompt_version)
    answers = get_answers(run["run_id"])
    q_lookup = {q["id"]: q for q in load_questions()}
    co_info = company_info_for_ticker(run["ticker"], get_sp500_list())
    exp_df = build_export_df(answers, run, q_lookup, co_info=co_info)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = base_name(run)
    xlsx_path = out_dir / f"{stem}.xlsx"
    md_path = out_dir / f"{stem}.md"

    write_excel(xlsx_path, run, exp_df)
    write_markdown(md_path, run, answers)

    print(f"Wrote {xlsx_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
