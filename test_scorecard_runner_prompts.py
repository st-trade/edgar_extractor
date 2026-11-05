"""Light checks for scorecard prompt construction (filing freshness + research skill)."""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scorecard_runner import (
    RESEARCH_SKILL_PATH,
    agent_message_for_question,
    build_prompt,
    format_scorecard_reference_date,
    load_questions,
)


class ScorecardPromptTests(unittest.TestCase):
    def test_build_prompt_includes_edgar_and_skill_path_in_agent_message(self):
        questions = load_questions()
        finance_q = next(q for q in questions if q["categoria"] == "Finance")
        prompt = build_prompt(finance_q, "BKNG", "v2", company_info=None)
        self.assertIn("10-Q", prompt)
        self.assertIn("10-K", prompt)
        self.assertIn("Periodo base:", prompt)

        message = agent_message_for_question(prompt)
        self.assertIn(RESEARCH_SKILL_PATH, message)
        self.assertIn("10-Q", message)

    def test_circulo_prompt_has_no_calificacion_suffix(self):
        questions = load_questions()
        circulo_q = next(q for q in questions if q["categoria"] == "Circulo de Competencia")
        prompt = build_prompt(circulo_q, "AAPL", "v1")
        self.assertNotIn("CALIFICACION:", prompt)
        self.assertIn("10-K", prompt)

    @patch("scorecard_runner.datetime")
    def test_build_prompt_injects_explicit_reference_date(self, mock_dt):
        fixed = datetime(2026, 3, 15, 12, 0, tzinfo=ZoneInfo("America/Mexico_City"))
        mock_dt.now.return_value = fixed
        questions = load_questions()
        finance_q = next(q for q in questions if q["categoria"] == "Finance")
        prompt = build_prompt(finance_q, "BKNG", "v2")
        expected = format_scorecard_reference_date(fixed)
        self.assertIn(expected, prompt)
        self.assertNotIn("Usa la fecha de hoy como referencia", prompt)

    @patch("scorecard_runner.datetime")
    def test_reference_date_respects_scorecard_reference_tz_env(self, mock_dt):
        fixed = datetime(2026, 1, 2, 8, 0, tzinfo=ZoneInfo("UTC"))
        mock_dt.now.return_value = fixed
        questions = load_questions()
        finance_q = next(q for q in questions if q["categoria"] == "Finance")
        with patch.dict(os.environ, {"SCORECARD_REFERENCE_TZ": "UTC"}):
            prompt = build_prompt(finance_q, "X", "v2")
        self.assertIn("Fecha de referencia del sistema: 2026-01-02 (UTC)", prompt)

    def test_finance_v2_inventory_has_no_hardcoded_fiscal_year_examples(self):
        """Year-specific freshness belongs in build_prompt injection, not the inventory."""
        stale = "no uses datos de 2024 si hoy es 2026"
        questions = load_questions()
        finance = [q for q in questions if q["categoria"] == "Finance"]
        for q in finance:
            raw_v2 = q.get("prompt_v2") or ""
            self.assertNotIn(stale, raw_v2, msg=f"question id={q['id']}")
            self.assertNotRegex(raw_v2, r"\b20\d{2}\b", msg=f"question id={q['id']}")

    def test_finance_built_prompt_uses_injected_filing_freshness_not_inventory_years(self):
        questions = load_questions()
        finance_q = next(q for q in questions if q["id"] == 64)
        prompt = build_prompt(finance_q, "AAPL", "v2")
        self.assertIn("VIGENCIA DE DATOS", prompt)
        self.assertNotIn("no uses datos de 2024", prompt)
        self.assertIn("Fecha de referencia del sistema:", prompt)

    def test_scored_prompt_requires_fuentes_terceras_and_third_party_complement(self):
        questions = load_questions()
        finance_q = next(q for q in questions if q["categoria"] == "Finance")
        circulo_q = next(q for q in questions if q["categoria"] == "Circulo de Competencia")
        scored = build_prompt(finance_q, "BKNG", "v2")
        circulo = build_prompt(circulo_q, "AAPL", "v1")
        for prompt in (scored, circulo):
            self.assertIn("complement", prompt.lower())
            self.assertIn("Exploratoria", prompt)
            self.assertIn("Alta", prompt)
            self.assertIn("10-Q", prompt)
            self.assertIn("Periodo base:", prompt)
        self.assertIn("Fuentes terceras:", scored)
        self.assertNotIn("Fuentes terceras:", circulo)


if __name__ == "__main__":
    unittest.main()
