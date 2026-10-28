---
name: research
description: Investigate a question against high-trust primary sources and capture findings as Markdown when useful. Used by the Value Investing scorecard per-question agents.
---

# Research (scorecard)

Follow this workflow **before** answering a scorecard question:

1. Investigate against **primary sources** (SEC EDGAR filings, issuer IR, official docs/APIs). Do not rely on secondary summaries without verifying the primary document.
2. Trace material claims to the source that owns them; cite filing form, period, and filing date where applicable.
3. Optional: for your own notes, you may write a short Markdown memo under `research/scorecard-notes/` (create the folder if needed). The **user-facing answer** is still the scorecard response in Spanish.

## Filing currency (required for scorecard)

For the company under analysis:

- Identify the **most recent filed 10-Q** (fiscal quarter + period end + filing date on EDGAR).
- Identify the **most recent filed 10-K** (fiscal year + period end + filing date).
- Base **financial metrics and recent factual claims** on those documents first; use third-party sources only to complement (strategy, industry, news), with source and date.

When the question involves numbers or Finance KPIs, start the answer with one line:

`Periodo base: <Q/FY> (10-Q/10-K filed YYYY-MM-DD)`
