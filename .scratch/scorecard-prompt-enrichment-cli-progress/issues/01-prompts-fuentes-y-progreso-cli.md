# 01: Scorecard — prompts enriquecidos (fecha, terceros) y progreso CLI informativo

**Blocked by:** None (can start immediately).

**Status:** done

---

## Problem Statement

Quien ejecuta el Value Investing Scorecard por terminal (Cursor CLI) recibe poco contexto sobre el avance de cada pregunta: solo un mensaje al terminar. Eso dificulta saber qué agentes están activos, cuánto llevan corriendo y cuándo podría acabar la corrida, sobre todo con workers en paralelo.

Los mensajes que recibe cada agente de investigación inducen vigencia de datos de forma implícita (“usa la fecha de hoy”), lo que deja al modelo inferir la fecha en lugar de anclarla a la del sistema. Además, las fuentes de terceros se presentan como un recurso de respaldo cuando el filing SEC no alcanza, en lugar de un complemento sistemático del análisis; no hay una rúbrica clara para mezclar fuentes reconocidas con señal exploratoria (blogs, foros) que a veces aparece al buscar y no sería obvia solo con EDGAR.

## Solution

Enriquecer los prompts compartidos del scorecard (mismos textos en CLI Cursor, Streamlit y cualquier camino que use el runner compartido) con: fecha de referencia inyectada al construir el mensaje; obligación de complementar con fuentes terceras de calidad; instrucción en **todas** las preguntas (Círculo y calificadas) para considerar fuentes exploratorias cuando aporten señal, sin usarlas para cifras materiales; etiquetas de confianza y sección `Fuentes terceras:` en respuestas calificadas.

Mejorar la consola del CLI Cursor con progreso en **inglés**: inicio y fin por pregunta, tiempo transcurrido mientras corre, resumen global periódico con contadores y ETA basado en promedios de la corrida actual, sin depender de streaming del SDK (Agent.prompt bloqueante).

El skill research vendido en el repo permanece sin modificaciones; Faith Scorecard queda fuera de alcance.

## User Stories

1. As a value investor running the scorecard locally, I want to see when each question **starts**, so that I know work has begun and which ids are in flight.
2. As a value investor running the scorecard locally, I want to see **elapsed time** for in-flight questions, so that I can judge whether a long-running agent is stuck or merely slow.
3. As a value investor running the scorecard locally, I want a **global summary** (running / pending / done) refreshed periodically, so that I can orient myself during parallel phases without reading dozens of lines.
4. As a value investor running the scorecard locally, I want an **estimated time remaining** for the current run based on completed question durations, so that I can plan around the batch finishing.
5. As a value investor running the scorecard locally, I want progress messages to stay in **English**, so that they match existing CLI conventions and logs I already grep.
6. As a value investor running the scorecard locally, I want progress reporting to remain **thread-safe** with multiple workers, so that parallel execution does not corrupt counters or interleave garbage on stdout.
7. As a value investor running the scorecard locally, I want to still see **score** (or context completion) when a question finishes, so that completion lines remain actionable.
8. As a value investor running the scorecard locally, I want **errors** on individual questions surfaced clearly in the progress output, so that partial runs are understandable without opening the database first.
9. As a researcher answering a scorecard question via Cursor, I want the prompt to include an explicit **system reference date** (not “infer today”), so that “most recent filing” is judged against a fixed anchor.
10. As a researcher answering a scorecard question via Cursor, I want that reference date to use a configurable **timezone** defaulting to America/Mexico_City, so that “today” matches the operator’s business calendar unless overridden.
11. As a researcher answering a scorecard question via Cursor, I want **10-Q/10-K** to remain the anchor for facts and **material numbers**, so that official filings stay authoritative.
12. As a researcher answering a scorecard question via Cursor, I want to be instructed to **complement** analysis with third-party sources proactively, not only when the filing is insufficient, so that industry context and external views are routine.
13. As a researcher answering a scorecard question via Cursor, I want a **quality hierarchy** for third parties (e.g. filings-cited sources, sector/regulator, reputable trade press), so that the agent prioritizes signal over noise.
14. As a researcher answering a scorecard question via Cursor, I want guidance to seek **2–3 quality third-party sources** when they exist, so that complement is concrete without pretending to exhaust the web.
15. As a researcher answering a scorecard question via Cursor, I want **every question** (including Círculo de Competencia) to invite **exploratory** sources (blogs, forums, etc.) when they reveal non-obvious signal, so that discovery is encouraged.
16. As a researcher answering a scorecard question via Cursor, I understand “random” exploratory hits as **what search may surface**, not a runner-side random toggle per question, so that behavior is predictable across runs.
17. As a researcher answering a scorecard question via Cursor, I want exploratory sources **labeled** as lower confidence and barred from replacing EDGAR-backed metrics, so that weak signal cannot masquerade as hard numbers.
18. As a researcher answering a scored question via Cursor, I want to always include a **`Fuentes terceras:`** section (list or explicit “filing only”), so that downstream readers see provenance at a glance.
19. As a researcher answering a Círculo question via Cursor, I want the same research rules in the prompt but **without** forcing `Fuentes terceras:` when there is no CALIFICACION line, so that context answers stay readable.
20. As a Streamlit scorecard user running Gemini or Claude, I want the **same prompt text** as the Cursor CLI for a given ticker and prompt version, so that methodology does not drift by channel.
21. As a cloud operator launching the scorecard on a VM, I want agents to receive the **same enriched prompts** as local CLI, so that cloud and local runs are comparable.
22. As a maintainer, I want the generic **research skill file** left unchanged, so that vendored skill updates remain mergeable.
23. As a maintainer, I want **automated checks** on constructed prompt text and mocked CLI progress, so that regressions in wording or worker progress do not require live API keys.
24. As a Faith Scorecard user, I accept that this work does **not** change Faith prompts or progress in this delivery, so that scope stays bounded.
25. As a Streamlit scorecard user, I accept that **rich progress UI** is not part of this delivery (only shared prompts), so that UI work can follow separately if needed.
26. As a resuming operator on a partial run, I want progress totals to reflect **only pending questions** in the current invocation, so that `[done/total]` stays meaningful.
27. As an operator setting infrastructure defaults, I want to override reference timezone via **`SCORECARD_REFERENCE_TZ`**, so that cloud VMs in UTC can still anchor “today” to the intended zone.
28. As a reader of scorecard answers in Spanish, I want agent **responses** to remain in Spanish per existing CALIFICACION rules, while CLI diagnostics stay English, so that user-facing analysis language is unchanged.

## Implementation Decisions

- **Shared prompt assembly** (existing scorecard runner module): extend the filing freshness block to inject a formatted reference date at prompt build time using `SCORECARD_REFERENCE_TZ` (default `America/Mexico_City`); replace vague “use today’s date” wording with explicit system date text.
- **Third-party policy** lives entirely in scorecard-specific prompt blocks and/or preamble fragments appended by the shared runner—not in the vendored research skill.
- **Complement, not fallback**: rewrite third-party guidance so agents routinely seek quality external sources in addition to EDGAR, while keeping numeric anchoring on latest 10-Q/10-K and retaining `Periodo base:` when citing period metrics.
- **Exploratory sources**: every question’s agent message includes instruction to consider blogs/forums/social when they add non-obvious signal; require confidence labels (`Alta` / `Media` / `Exploratoria`); forbid using exploratory tiers to establish material numbers that must come from filings.
- **Response contract (scored categories only)**: prompt requires a trailing `Fuentes terceras:` section always—either enumerated sources with trust tier or an explicit statement that third parties were not needed beyond the filing.
- **Círculo de Competencia**: same research instructions as scored questions; no mandatory `Fuentes terceras:` section in the response contract (no CALIFICACION suffix today).
- **Streamlit Value Scorecard page**: continues importing shared `build_prompt` / `agent_message_for_question`; no progress bar redesign in this change.
- **Cursor CLI runner**: enhance parallel phase execution to emit English lifecycle lines per question (`START`, periodic or final `RUNNING` with elapsed, `done` / error with score when applicable); add a lightweight background ticker (~5 s) printing aggregate `{running, pending, done, ETA}` for the active phase, coordinated with existing worker pool, stagger, persist lock, and error collection.
- **SDK constraint**: progress cannot rely on streaming partial agent output; elapsed/ETA derive from wall-clock timestamps around the existing blocking agent call.
- **Faith Scorecard**: no changes to faith tables, prompts, or UI in this spec.
- **Persistence**: unchanged—answers and scores still saved through existing scorecard database helpers; no Markdown memo per question.

### Testing seam (proposed — confirm before implementation)

Prefer **one primary seam** for prompt behavior: **constructed agent message text** exported by the shared runner (`build_prompt` + `agent_message_for_question`), asserting presence of injected date, EDGAR anchor, complement/third-party rubric, exploratory guidance on both Círculo and Finance samples, and scored-only `Fuentes terceras:` contract.

Use **one secondary seam** only where CLI behavior cannot be observed through prompts: **`run_parallel_phase` with injected agent callable**, capturing stdout to assert English START/done ordering, worker safety, and that the global summary ticker runs without crashing (timing assertions kept loose).

No new test seams in Streamlit or live Cursor SDK.

## Testing Decisions

- **Good tests** assert externally visible behavior: prompt string contents for representative questions from the loaded question bank; CLI log lines and counters under mocked agents—not internal private helpers or SDK wiring.
- **Modules under test**: shared scorecard runner (prompt tests extending prior filing-freshness checks); Cursor CLI runner parallel phase (extending prior parallel worker tests with stdout capture).
- **Prior art**: existing lightweight unittest module for scorecard prompts; existing parallel scorecard tests that mock agent and save callbacks without API keys.
- **Avoid**: integration tests requiring `CURSOR_API_KEY`; brittle exact ETA values (assert ETA line exists when ≥1 question completed instead).

## Out of Scope

- Faith Scorecard prompts, progress, or database flows.
- Rich progress UI on the Streamlit Scorecard page (progress bar redesign).
- Modifying the vendored engineering research skill markdown.
- Persisting historical duration metrics across runs for ETA (session-only averages).
- Runner-side randomization of which questions receive exploratory instructions (all questions receive them).
- Streaming or subscribing to in-agent tool events from the Cursor SDK.
- Changing scorecard question JSON copy in `prompt_v1` / `prompt_v2` per question (only shared appended blocks).

## Further Notes

- Design conversation settled: terminal language **English**; reference timezone default **America/Mexico_City**; exploratory “randomness” means **search discovery**, not probabilistic prompt injection.
- After implementation, operators should set `SCORECARD_REFERENCE_TZ` on cloud VMs if wall-clock UTC should not define “today” for filing freshness.
- Glossary/ADR files were not present in the repo; vocabulary follows existing scorecard domain terms (Círculo de Competencia, CALIFICACION, run_id, partial run, prompt version v1/v2).
