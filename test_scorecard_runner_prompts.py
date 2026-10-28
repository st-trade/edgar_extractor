"""Light checks for scorecard prompt construction (filing freshness + research skill)."""

from __future__ import annotations

import unittest

from scorecard_runner import (
    RESEARCH_SKILL_PATH,
    agent_message_for_question,
    build_prompt,
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


if __name__ == "__main__":
    unittest.main()
