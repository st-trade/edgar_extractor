# 02: Prompts compartidos — vigencia 10-Q/10-K y preámbulo research

**What to build:** Cada pregunta del scorecard (Cursor vía `run_scorecard_cursor.py`) recibe un mensaje que (a) obliga a anclar hechos y cifras en el **10-Q y/o 10-K más recientes ya presentados** en SEC EDGAR, con fecha de referencia “hoy” y línea `Periodo base:` cuando se citen métricas; (b) instruye seguir el skill research del ticket 01 leyéndolo desde el repo. La investigación ocurre **dentro del turno del agente**; al terminar, **solo** la respuesta en español (y `CALIFICACION` si aplica) se guarda en `scorecard.db` mediante el flujo existente `save_answer` — **sin** exigir ni generar un archivo Markdown por pregunta.

**Blocked by:** 01: Vendoring fiel del skill research

**Status:** ready-for-agent

- [x] `scorecard_runner.build_prompt` incluye el bloque de vigencia 10-Q/10-K para v1 y v2.
- [x] `RESEARCH_PREAMBLE` / `agent_message_for_question` referencian el skill del ticket 01; no duplican ni alteran el contenido del skill.
- [x] `call_cursor_research_agent` envía el mensaje completo (preámbulo + prompt construido).
- [x] Comprobación automatizada ligera (test o script) verifica presencia de 10-Q, 10-K y referencia al skill en el prompt generado para un ticker de ejemplo.
- [x] Ningún cambio introduce escritura obligatoria de memos Markdown por pregunta.
