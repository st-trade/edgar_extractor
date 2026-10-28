"""
Shared scorecard question loading, prompt building, and score parsing.
Used by run_scorecard_cursor.py (Cursor SDK runner).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from scorecard_db import CATEGORY_WEIGHTS

_ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = _ROOT / "scorecard_questions.json"

SCORE_SUFFIX = (
    "\n\n---\n"
    "INSTRUCCIÓN FINAL: Responde en español. "
    "Al final de tu respuesta, en una línea separada, escribe ÚNICAMENTE:\n"
    "CALIFICACION: [número entero entre 0 y 10]"
)

RESEARCH_SKILL_PATH = "skills/engineering/research/SKILL.md"

FILING_FRESHNESS_BLOCK = (
    "\n\n---\n"
    "VIGENCIA DE DATOS (SEC EDGAR):\n"
    "Ancla hechos y cifras en el 10-Q y/o 10-K más recientes ya presentados en SEC EDGAR "
    "para el emisor analizado. Usa la fecha de hoy como referencia para identificar cuál es "
    "el filing más reciente; no te quedes en años fiscales anteriores si existe un periodo más nuevo.\n"
    "Cuando cites métricas o hechos del periodo, incluye una línea explícita:\n"
    "Periodo base: [periodo fiscal / fecha del filing usado]\n"
    "Complementa con fuentes de terceros solo cuando el filing no cubra lo necesario.\n"
)

RESEARCH_PREAMBLE = (
    "Tarea aislada del Scorecard de Value Investing (una sola pregunta).\n"
    f"Lee y aplica la metodología del skill research en `{RESEARCH_SKILL_PATH}` "
    "(fuentes primarias; sigue cada afirmación hasta su fuente). "
    "Realiza la investigación en este turno; integra los hallazgos solo en tu respuesta final "
    "— no generes un archivo Markdown aparte por esta pregunta.\n"
    "Responde ÚNICAMENTE a la pregunta indicada abajo; no anticipes otras preguntas del scorecard.\n"
    "Si la pregunta pide una calificación numérica, sigue la instrucción CALIFICACION al final.\n"
    "Si es solo contexto (sin calificación), omite la línea CALIFICACION.\n\n"
)


def agent_message_for_question(question_prompt: str) -> str:
    """Full agent message: research preámbulo + prompt construido por build_prompt."""
    return RESEARCH_PREAMBLE + question_prompt


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
    prompt = prompt + FILING_FRESHNESS_BLOCK
    scored = q["categoria"] != "Circulo de Competencia"
    return prompt + (SCORE_SUFFIX if scored else "")


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
    from scorecard_cursor_bridge_win32 import patch_cursor_sdk_bridge_on_windows

    patch_cursor_sdk_bridge_on_windows()
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
