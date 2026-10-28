# 01: Vendoring fiel del skill research

**What to build:** El repositorio incluye el skill `research` de mattpocock **sin modificaciones** (mismo frontmatter y mismo cuerpo que el original), en una ruta estable dentro del workspace para que los agentes del scorecard en Cloud y local puedan leerlo. No se añade texto de scorecard, filings ni rutas de notas dentro de ese archivo.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [x] `skills/engineering/research/SKILL.md` existe y coincide con el skill original (nombre, descripción y tres pasos del job).
- [x] No hay secciones extra (scorecard, 10-Q, Periodo base, etc.) en el skill vendored.
- [ ] Documentación mínima en el ticket de implementación o commit message indica que las reglas de vigencia EDGAR viven en los prompts del scorecard, no en el skill.
