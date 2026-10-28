# 02: Prompts compartidos — fecha, terceros y exploratorio

**What to build:** Cualquier ejecución del Value Investing Scorecard que use el ensamblador compartido de prompts (CLI Cursor, Streamlit con Gemini/Claude, agente en nube) debe enviar a cada agente un mensaje con vigencia y metodología de fuentes alineadas al spec padre: fecha de referencia del sistema inyectada al construir el prompt (no inferida por el modelo), configurable vía `SCORECARD_REFERENCE_TZ` con default America/Mexico_City; ancla numérica y de hechos en el 10-Q/10-K más reciente en EDGAR con línea `Periodo base:` cuando corresponda; complemento sistemático con fuentes terceras de calidad (jerarquía y orientación a 2–3 fuentes cuando existan); en todas las preguntas (Círculo de Competencia y calificadas), invitación a fuentes exploratorias (blogs, foros, etc.) cuando aporten señal no obvia, con etiquetas de confianza Alta/Media/Exploratoria y prohibición de usar exploratorias para cifras materiales que deban salir del filing; en preguntas calificadas, contrato de respuesta que exige sección `Fuentes terceras:` siempre (lista o declaración explícita de filing suficiente). El skill research vendido del repo no se modifica. Faith Scorecard queda fuera.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] El prompt construido incluye una fecha de referencia explícita derivada del reloj del sistema y del timezone configurado; no depende de la frase vaga “usa la fecha de hoy” sin valor concreto.
- [x] `SCORECARD_REFERENCE_TZ` sobreescribe el timezone; sin variable, default America/Mexico_City.
- [x] Se mantiene anclaje 10-Q/10-K y `Periodo base:` para métricas del periodo.
- [x] Las instrucciones de terceros piden complementar el análisis de forma rutinaria, no solo cuando el filing sea insuficiente.
- [x] Círculo y categorías calificadas comparten reglas de terceros y exploratorio en el mensaje del agente.
- [x] Solo las preguntas calificadas exigen `Fuentes terceras:` en la respuesta; Círculo no añade ese contrato obligatorio.
- [x] Streamlit y CLI importan el mismo ensamblador; no hay duplicación local de bloques de vigencia.
- [x] Tests automatizados (sin API) verifican el texto del mensaje para al menos una pregunta Finance y una Círculo: fecha inyectada, EDGAR, complemento/terceros, exploratorio, y contrato `Fuentes terceras:` solo en calificadas.
