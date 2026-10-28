"""Tests for parallel scorecard question execution (mocked agents)."""

from __future__ import annotations

import io
import contextlib
import threading
import time
import unittest

import run_scorecard_cursor as rsc


class ParallelScorecardTests(unittest.TestCase):
    def test_clamp_workers_rejects_out_of_range(self):
        with self.assertRaises(SystemExit):
            rsc.clamp_workers(0)
        with self.assertRaises(SystemExit):
            rsc.clamp_workers(11)
        self.assertEqual(rsc.clamp_workers(3), 3)

    def test_run_parallel_phase_respects_worker_cap(self):
        active = 0
        peak = 0
        gate = threading.Lock()

        def fake_agent(*_args, **_kwargs):
            nonlocal active, peak
            with gate:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with gate:
                active -= 1
            return "ok answer CALIFICACION: 7"

        saved: list[int] = []
        persist_lock = threading.Lock()

        def fake_save(_run_id, qid, *_rest, **_kw):
            saved.append(qid)

        questions = [{"id": i, "categoria": "Finance", "pregunta": f"Q{i}"} for i in range(6)]

        errors: list[str] = []
        done = [0]
        rsc.run_parallel_phase(
            questions,
            phase_label="scored",
            total=6,
            run_id=1,
            ticker="X",
            prompt_version="v2",
            co_info=None,
            model="composer-2.5",
            api_key="k",
            workspace="/tmp",
            workers=2,
            stagger=0,
            scored=True,
            persist_lock=persist_lock,
            progress_lock=threading.Lock(),
            done_counter=done,
            errors=errors,
            errors_lock=threading.Lock(),
            agent_call=fake_agent,
            save_fn=fake_save,
        )

        self.assertEqual(len(saved), 6)
        self.assertLessEqual(peak, 2)
        self.assertEqual(done[0], 6)
        self.assertEqual(errors, [])

    def test_phases_run_circulo_before_scored(self):
        order: list[str] = []
        order_lock = threading.Lock()

        def fake_agent(*_args, **_kwargs):
            time.sleep(0.02)
            return "context"

        def fake_save(_run_id, qid, categoria, *_rest, **_kw):
            with order_lock:
                order.append(f"{categoria}:{qid}")

        persist_lock = threading.Lock()
        circulo = [
            {"id": 1, "categoria": "Circulo de Competencia", "pregunta": "c1"},
            {"id": 2, "categoria": "Circulo de Competencia", "pregunta": "c2"},
        ]
        scored = [
            {"id": 10, "categoria": "Finance", "pregunta": "f1"},
        ]
        errors: list[str] = []
        done = [0]
        kw = dict(
            total=3,
            run_id=1,
            ticker="X",
            prompt_version="v2",
            co_info=None,
            model="m",
            api_key="k",
            workspace="/tmp",
            workers=3,
            stagger=0,
            persist_lock=persist_lock,
            progress_lock=threading.Lock(),
            done_counter=done,
            errors=errors,
            errors_lock=threading.Lock(),
            agent_call=fake_agent,
            save_fn=fake_save,
        )

        rsc.run_parallel_phase(circulo, phase_label="circulo", scored=False, **kw)
        rsc.run_parallel_phase(scored, phase_label="scored", scored=True, **kw)

        self.assertTrue(all("Circulo" in x for x in order[:2]))
        self.assertEqual(order[-1], "Finance:10")

    def test_run_parallel_phase_prints_start_and_done_in_english(self):
        def fake_agent(*_args, **_kwargs):
            time.sleep(0.02)
            return "answer CALIFICACION: 8"

        saved: list[int] = []
        persist_lock = threading.Lock()

        def fake_save(_run_id, qid, *_rest, **_kw):
            saved.append(qid)

        questions = [
            {"id": 1, "categoria": "Finance", "pregunta": "Asset quality?"},
            {"id": 2, "categoria": "Finance", "pregunta": "Debt levels?"},
        ]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rsc.run_parallel_phase(
                questions,
                phase_label="scored",
                total=2,
                run_id=1,
                ticker="X",
                prompt_version="v2",
                co_info=None,
                model="m",
                api_key="k",
                workspace="/tmp",
                workers=2,
                stagger=0,
                scored=True,
                persist_lock=persist_lock,
                progress_lock=threading.Lock(),
                done_counter=[0],
                errors=[],
                errors_lock=threading.Lock(),
                agent_call=fake_agent,
                save_fn=fake_save,
                progress_ticker_interval=0.05,
            )
        out = buf.getvalue()
        self.assertIn("START scored id=1", out)
        self.assertIn("START scored id=2", out)
        self.assertIn("done", out.lower())
        self.assertIn("score=8", out)
        self.assertIn("[progress]", out)
        self.assertEqual(len(saved), 2)


if __name__ == "__main__":
    unittest.main()
