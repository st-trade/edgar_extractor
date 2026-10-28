# 02: Launcher cloud alineado con workers y stagger

**What to build:** Quien lance el scorecard con el agente orquestador en la nube puede pasar los mismos controles de paralelismo que el CLI local: el comando que ejecuta la VM ya no usa la pausa fija entre preguntas y en su lugar reenvía workers y stagger al runner del ticket 01. La ayuda/ejemplos del launcher reflejan los flags nuevos.

**Blocked by:** 01: Scorecard Cursor CLI en paralelo (workers + stagger)

**Status:** ready-for-agent

- [ ] El launcher cloud expone workers y stagger (defaults alineados con el CLI) y deja de exponer `--delay`.
- [ ] El prompt/comando que corre en la VM invoca el runner con workers y stagger, no delay.
- [ ] Documentación inline del launcher (help/docstring) actualizada para describir paralelismo y límites, sin mencionar delay como throttle principal.
