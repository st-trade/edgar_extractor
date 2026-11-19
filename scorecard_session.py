"""
Single-turn scorecard session: one LLM call per ticker for all v2 questions.

Output is structured JSON; optional context_summary is carried to the next ticker.
"""

from __future__ import annotations

import json
import re
from typing import Any

from scorecard_runner import (
    build_prompt,
    extract_score,
    format_scorecard_reference_date,
    load_questions,
)

DEFAULT_REVIEW_TICKERS = ("ISRG", "IDXX", "PANW", "CRWD", "PLTR")

SESSION_PREAMBLE = """\
Eres el analista del Value Investing Scorecard (versión 2).
Responde en español. Una sola respuesta para TODAS las preguntas listadas abajo.

Reglas:
- Ancla hechos en el 10-Q/10-K SEC EDGAR más reciente; línea «Periodo base: …» cuando cites cifras.
- Preguntas con id 0–1 (Círculo de Competencia): respuesta narrativa, sin CALIFICACION.
- Resto: análisis breve pero sustantivo (4–8 oraciones), KPIs si aplica, «¿Por qué no más bajo/alto?»,
  sección «Fuentes terceras:» (2–3 fuentes etiquetadas), y línea «CALIFICACION: [0-10]».
- Formato de salida: ÚNICAMENTE un objeto JSON válido (sin markdown ni texto fuera del JSON):

{
  "ticker": "[TICKER]",
  "context_summary": "≤400 palabras: hechos clave de la empresa para reutilizar en otras evaluaciones",
  "answers": [
    {"id": 0, "answer_text": "..."},
    {"id": 2, "score": 8, "answer_text": "..."}
  ]
}

Incluye un elemento en answers por cada id listado (todos los ids).
"""


def question_catalog(questions: list[dict], version: str) -> str:
    lines = []
    for q in questions:
        scored = q["categoria"] != "Circulo de Competencia"
        label = q.get("pregunta", "")[:120]
        lines.append(
            f"- id={q['id']} | {q['categoria']} | "
            f"{'[score]' if scored else '[contexto]'} | {label}"
        )
    return "\n".join(lines)


def build_one_turn_user_prompt(
    ticker: str,
    *,
    prompt_version: str = "v2",
    company_info: dict | None = None,
    prior_summaries: list[str] | None = None,
) -> str:
    questions = load_questions()
    ref = format_scorecard_reference_date()
    parts = [
        SESSION_PREAMBLE.replace("[TICKER]", ticker.upper()),
        f"\n=== TICKER: {ticker.upper()} ===\n{ref}\n",
    ]
    if prior_summaries:
        parts.append(
            "=== CONTEXTO COMPRIMIDO (empresas ya evaluadas en esta sesión) ===\n"
            + "\n---\n".join(prior_summaries)
            + "\n"
        )
    parts.append("=== CATÁLOGO DE PREGUNTAS (responde todas por id) ===\n")
    parts.append(question_catalog(questions, prompt_version))
    parts.append("\n=== TEXTO COMPLETO DE CADA PREGUNTA ===\n")
    for q in questions:
        body = build_prompt(q, ticker, prompt_version, company_info)
        parts.append(f"\n--- id={q['id']} ---\n{body}\n")
    return "\n".join(parts)


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_one_turn_response(text: str, questions: list[dict]) -> tuple[list[dict], str]:
    """Return (normalized answers, context_summary)."""
    raw = json.loads(_strip_json_fence(text))
    summary = (raw.get("context_summary") or "").strip()
    by_id = {int(a["id"]): a for a in raw.get("answers", [])}
    q_by_id = {q["id"]: q for q in questions}
    out: list[dict] = []
    for qid, q in sorted(q_by_id.items()):
        a = by_id.get(qid)
        if not a:
            raise ValueError(f"Missing answer for question id={qid}")
        answer_text = (a.get("answer_text") or "").strip()
        if not answer_text:
            raise ValueError(f"Empty answer_text for id={qid}")
        scored = q["categoria"] != "Circulo de Competencia"
        score = a.get("score")
        if score is None and scored:
            score = extract_score(answer_text)
        elif score is not None:
            score = max(0, min(10, int(score)))
        if not scored:
            score = None
        out.append(
            {
                "question_id": qid,
                "categoria": q["categoria"],
                "pregunta": q["pregunta"],
                "score": score,
                "answer_text": answer_text,
            }
        )
    return out, summary


def call_gemini(api_key: str, model: str, prompt: str, *, max_output_tokens: int) -> str:
    import google.genai as genai

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"max_output_tokens": max_output_tokens},
    )
    return (resp.text or "").strip()


def call_claude(api_key: str, model: str, prompt: str, *, max_output_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_output_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def call_cursor_one_shot(
    prompt: str,
    *,
    model: str,
    api_key: str,
    workspace: str,
) -> str:
    from scorecard_runner import call_cursor_research_agent

    return call_cursor_research_agent(
        prompt,
        model=model,
        api_key=api_key,
        workspace=workspace,
    )


def load_ingest_payload(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)