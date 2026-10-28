"""
Shared scorecard question loading, prompt building, and score parsing.
Used by run_scorecard_cursor.py (Cursor SDK runner).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scorecard_db import CATEGORY_WEIGHTS

_ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = _ROOT / "scorecard_questions.json"
DEFAULT_REFERENCE_TZ = "America/Mexico_City"

SCORE_SUFFIX = (
    "\n\n---\n"
    "INSTRUCCIÓN FINAL: Responde en español. "
    "Al final de tu respuesta, en una línea separada, escribe ÚNICAMENTE:\n"
    "CALIFICACION: [número entero entre 0 y 10]\n"
    "Incluye también una sección titulada exactamente:\n"
    "Fuentes terceras:\n"
    "Enumera 2–3 fuentes de terceros usadas (con etiqueta Alta, Media o Exploratoria) "
    "o declara explícitamente que el 10-Q/10-K bastó sin fuentes adicionales."
)

RESEARCH_SKILL_PATH = "skills/engineering/research/SKILL.md"

THIRD_PARTY_SOURCES_BLOCK = (
    "\n\n---\n"
    "FUENTES DE TERCEROS (complemento sistemático):\n"
    "Complementa el análisis con fuentes de terceros de calidad además del filing SEC; "
    "no las reserves solo para cuando el 10-Q/10-K sea insuficiente.\n"
    "Prioriza en este orden: (1) fuentes citadas en el 10-K/10-Q, "
    "(2) comunicados sectoriales o de reguladores, (3) prensa especializada reconocida.\n"
    "Busca 2–3 fuentes de terceros de calidad cuando existan.\n"
    "Considera también fuentes exploratorias (blogs, foros, redes) si aportan señal "
    "no obvia que no aparecería solo con EDGAR o prensa reconocida; "
    "etiquétalas como Exploratoria (menor confianza que Alta o Media).\n"
    "No uses fuentes exploratorias para establecer cifras materiales que deben anclarse "
    "en el 10-Q/10-K.\n"
)


def scorecard_reference_tz() -> ZoneInfo:
    name = os.environ.get("SCORECARD_REFERENCE_TZ", DEFAULT_REFERENCE_TZ).strip()
    if not name:
        name = DEFAULT_REFERENCE_TZ
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_REFERENCE_TZ)


def format_scorecard_reference_date(when: datetime | None = None) -> str:
    tz = scorecard_reference_tz()
    if when is None:
        when = datetime.now(tz)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    else:
        when = when.astimezone(tz)
    date_part = when.strftime("%Y-%m-%d")
    return f"Fecha de referencia del sistema: {date_part} ({tz.key})"


def filing_freshness_block(reference_line: str) -> str:
    return (
        "\n\n---\n"
        "VIGENCIA DE DATOS (SEC EDGAR):\n"
        f"{reference_line}\n"
        "Ancla hechos y cifras en el 10-Q y/o 10-K más recientes ya presentados en SEC EDGAR "
        "para el emisor analizado, usando la fecha de referencia anterior (no infieras otra fecha).\n"
        "Cuando cites métricas o hechos del periodo, incluye una línea explícita:\n"
        "Periodo base: [periodo fiscal / fecha del filing usado]\n"
    )


# Backward-compatible name for imports that expect a constant (tests/docs); prefer build-time block.
FILING_FRESHNESS_BLOCK = filing_freshness_block(format_scorecard_reference_date())

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
    reference_line = format_scorecard_reference_date()
    prompt = prompt + filing_freshness_block(reference_line)
    prompt = prompt + THIRD_PARTY_SOURCES_BLOCK
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
