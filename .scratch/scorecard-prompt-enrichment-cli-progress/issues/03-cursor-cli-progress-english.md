# 03: CLI Cursor — progreso informativo en inglés

**What to build:** Al ejecutar el scorecard por `run_scorecard_cursor.py`, la consola muestra avance útil por pregunta y a nivel de fase sin depender de streaming del SDK: al lanzar cada agente, línea de inicio en inglés con identificador de pregunta (y categoría o contexto cuando aplique); mientras el agente bloqueante corre, visibilidad de tiempo transcurrido (al completar o mediante actualización acordada al diseño); al terminar, línea de cierre en inglés con score cuando la pregunta es calificada, o equivalente para contexto del Círculo; errores por pregunta visibles en la salida sin abrir la base de datos. Un resumen global periódico (~5 s) reporta cuántas preguntas van en curso, pendientes y listas, más ETA estimado a partir del promedio de duraciones ya completadas en la invocación actual. Los contadores `[done/total]` reflejan solo las preguntas pendientes en esa corrida (reanudación parcial coherente). Todo thread-safe con workers y stagger existentes. Mensajes de progreso en inglés; respuestas del agente siguen en español. Streamlit no recibe barra enriquecida en este ticket.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Cada pregunta emitida en la fase paralela imprime un evento de inicio reconocible en inglés antes de la llamada al agente.
- [ ] Cada finalización imprime done o error en inglés; preguntas calificadas incluyen score cuando se extrajo.
- [ ] Existe resumen global periódico con running / pending / done y ETA de sesión (sin exigir valor exacto de ETA en tests).
- [ ] El progreso no corrompe contadores bajo concurrencia (comportamiento cubierto por tests con agente mockeado).
- [ ] `total` y contadores de done corresponden al lote pendiente de la invocación, no al JSON completo si hay reanudación.
- [ ] Tests automatizados capturan stdout de la fase paralela mockeada y verifican presencia de START/done y que el ticker global no rompe la ejecución.
- [ ] No se requiere `CURSOR_API_KEY` para los tests.
