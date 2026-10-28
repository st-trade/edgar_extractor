"""
Shared scorecard question loading, prompt building, and score parsing.
Used by run_scorecard_cursor.py (Cursor SDK runner).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from pathlib import Path

from scorecard_db import CATEGORY_WEIGHTS

_ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = _ROOT / "scorecard_questions.json"
RESEARCH_SKILL_PATH = _ROOT / "skills" / "engineering" / "research" / "SKILL.md"

FILING_CURRENCY_BLOCK = (
    "\n\n=== VIGENCIA DE DATOS (OBLIGATORIO) ===\n"
    "Antes de responder, localiza en fuentes primarias (SEC EDGAR) para la empresa:\n"
    "• El **10-Q más reciente ya presentado** (trimestre fiscal, cierre de periodo, fecha de filing).\n"
    "• El **10-K más reciente ya presentado** (año fiscal, cierre, fecha de filing).\n"
    "Usa esos documentos como base para hechos y cifras recientes. "
    "Compara con periodos anteriores solo como contexto.\n"
    "Si un dato no aparece en el último 10-Q/10-K, dilo explícitamente. "
    "Para temas cualitativos (competencia, management, marca, industria) puedes "
    "complementar con fuentes de terceros, citando fuente y fecha.\n"
    "Si citas métricas financieras o ratios, abre con una línea:\n"
    "Periodo base: … (10-Q/10-K filed YYYY-MM-DD)\n"
    "Fecha de referencia (hoy): {today}\n"
    "========================================\n"
)

RESEARCH_PREAMBLE = (
    "Tarea aislada del Scorecard de Value Investing (una sola pregunta).\n"
    "Metodología **/research** (skill research):\n"
    f"1. Lee y sigue `{RESEARCH_SKILL_PATH.relative_to(_ROOT)}` en este repositorio.\n"
    "2. Investiga con fuentes primarias (SEC EDGAR, documentos oficiales de la emisora). "
    "Verifica en el documento primario; no te quedes solo en resúmenes secundarios.\n"
    "3. Cita formulario, periodo fiscal y fecha de filing cuando uses cifras o hechos del reporte.\n"
    "Responde ÚNICAMENTE a la pregunta indicada abajo; no anticipes otras preguntas del scorecard.\n"
    "Si la pregunta pide una calificación numérica, sigue la instrucción CALIFICACION al final.\n"
    "Si es solo contexto (sin calificación), omite la línea CALIFICACION.\n\n"
)

SCORE_SUFFIX = (
    "\n\n---\n"
    "INSTRUCCIÓN FINAL: Responde en español. "
    "Al final de tu respuesta, en una línea separada, escribe ÚNICAMENTE:\n"
    "CALIFICACION: [número entero entre 0 y 10]"
)

def load_questions() -> list[dict]:
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_score(text: str) -> int | None:
    m = re.search(r"CALIFICACION\s*:\s*(\d+)", text, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        return max(0, min(10, v))
    nums = re.findall(r"\b(\d+)\b", text[-300:])
    for n in reversed(nums):
        if 0 <= int(n) <= 10:
            return int(n)
    return None


def build_prompt(
    q: dict,
    ticker: str,
    version: str,
    company_info: dict | None = None,
) -> str:
    raw = (
        q[f"prompt_{version}"]
        if f"prompt_{version}" in q and q[f"prompt_{version}"]
        else q["pregunta"]
    )
    prompt = raw.replace("[EMPRESA]", ticker).replace("[empresa]", ticker)
    if company_info:
        name = company_info.get("name", "")
        index = company_info.get("index_member", "")
        sector = company_info.get("sector", "")
        sic = company_info.get("sic_code", "")
        sic_d = company_info.get("sic_desc", "")
        sic_str = f"{sic} — {sic_d}" if sic and sic_d else sic or "N/D"
        header = (
            f"=== EMPRESA A ANALIZAR ===\n"
            f"Ticker: {ticker}  |  Nombre: {name}  |  Índice: {index}\n"
            f"Sector: {sector}  |  SIC: {sic_str}\n"
            f"==========================\n\n"
        )
        prompt = header + prompt
    prompt += FILING_CURRENCY_BLOCK.format(today=date.today().isoformat())
    scored = q["categoria"] != "Circulo de Competencia"
    return prompt + (SCORE_SUFFIX if scored else "")


def agent_message_for_question(prompt: str) -> str:
    """Full user message for Cursor (preamble + built question prompt)."""
    return RESEARCH_PREAMBLE + prompt


def company_info_for_ticker(ticker: str, companies: list[dict]) -> dict | None:
    t = ticker.upper()
    for row in companies:
        if row.get("ticker", "").upper() == t:
            return row
    return None


def call_cursor_research_agent(
    prompt: str,
    *,
    model: str,
    api_key: str,
    workspace: str,
    max_retries: int = 4,
    base_delay: float = 15.0,
) -> str:
    from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, RateLimitError

    message = agent_message_for_question(prompt)
    options = AgentOptions(
        model=model,
        api_key=api_key,
        local=LocalAgentOptions(cwd=workspace),
        mode="agent",
    )
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            result = Agent.prompt(message, options)
            if result.error_message:
                raise RuntimeError(result.error_message)
            return (result.result or "").strip()
        except RateLimitError as err:
            last_err = err
            wait = float(err.retry_after) if err.retry_after else base_delay * (2 ** attempt)
            time.sleep(wait)
        except CursorAgentError as err:
            last_err = err
            if not err.is_retryable or attempt >= max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f"Cursor agent failed after retries: {last_err}")


def all_scored_categories() -> list[str]:
    return list(CATEGORY_WEIGHTS.keys())
