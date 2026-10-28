# 01: Scorecard Cursor CLI en paralelo (workers + stagger)

**What to build:** Al ejecutar el scorecard por Cursor (un agente Composer por pregunta), varias preguntas pueden correr a la vez dentro de cada fase: primero todo el Círculo de Competencia en paralelo, luego las preguntas calificadas en paralelo. Un tope configurable limita cuántos agentes viven simultáneamente; un arranque escalonado opcional espacia los lanzamientos. Las respuestas siguen guardándose en `scorecard.db` (y GCS si aplica) con el mismo comportamiento de reanudación, errores por pregunta y corridas parciales que hoy. La consola muestra progreso al terminar cada pregunta (orden no necesariamente el del JSON). Streamlit y otros LLM quedan fuera de alcance.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] El CLI acepta concurrencia con default sensato (3 workers) y variable de entorno equivalente; valida un rango acotado (1–10).
- [ ] El CLI acepta stagger con default corto (1 s) y permite 0 para máxima agresividad.
- [ ] Se elimina el throttle antiguo basado en pausa fija entre cada pregunta (`--delay`).
- [ ] Fase Círculo: preguntas pendientes en paralelo respetando workers/stagger; luego fase calificada igual.
- [ ] Persistencia (respuesta + upload) serializada bajo concurrencia; reintentos por rate limit por pregunta sin abortar el lote.
- [ ] Una pregunta que falle tras reintentos guarda error como hoy; la corrida puede quedar partial si falta cobertura.
- [ ] Comprobación automatizada (mock del agente, sin API real) demuestra que se respetan workers y el orden de fases.
