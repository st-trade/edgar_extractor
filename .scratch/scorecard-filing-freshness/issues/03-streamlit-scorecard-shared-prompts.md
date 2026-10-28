# 03: Streamlit Scorecard alineado con scorecard_runner

**What to build:** La ejecución del scorecard en Streamlit (Gemini y Claude) usa los mismos `build_prompt`, `extract_score` y `agent_message_for_question` que el runner Cursor, de modo que vigencia EDGAR y metodología research sean idénticas en todos los caminos. El resultado de cada pregunta sigue persistiendo **únicamente** en `scorecard.db` (respuesta + score); no hay artefactos Markdown por pregunta.

**Blocked by:** 02: Prompts compartidos — vigencia 10-Q/10-K y preámbulo research

**Status:** ready-for-agent

- [x] La página Scorecard en `app.py` deja de duplicar lógica local de `_build_prompt` / `SCORE_SUFFIX` / `_extract_score` y importa desde `scorecard_runner`.
- [x] Las llamadas a Gemini y Claude usan `agent_message_for_question(prompt)` igual que Cursor.
- [x] Preguntas de Círculo de Competencia no reciben sufijo `CALIFICACION` (comportamiento del runner compartido).
- [x] Smoke manual documentado en el PR: ejecutar una categoría corta o una pregunta y confirmar que el prompt mostrado/guardado incluye vigencia 10-Q/10-K.
