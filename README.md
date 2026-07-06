# Plain Sight

**Australian federal politicians' declared interests, structured, searchable, sourced, and honest.**

Politicians' financial interests *are* disclosed, as per-member scanned (often handwritten) PDFs with no API and no structured export. They are technically public but practically invisible. Plain Sight makes them legible, with a source link and freshness date on every claim, and a human confirming every published fact.

> Plain Sight is a **faithful mirror of the official record**. In v1 it publishes only what a member *declared*, never inferred connections.

## Status

Pre-build. The v1 scope, data model, and decisions are specified in **[docs/PRD.md](docs/PRD.md)**.
Supporting terminology is in **[docs/GLOSSARY.md](docs/GLOSSARY.md)**.

## What v1 is

- Ingest the House and Senate registers of interests (aph.gov.au).
- Extract each declared interest with a multimodal LLM; **a human verifies every claim before publication**.
- Store claims as **immutable, bitemporal declaration events** with **per-claim provenance**.
- Publish a **static, read-only searchable web view + flat data exports (CSV/Parquet)**, produced by a one-way publish step (Datasette browse deferred).
- Run a **cheap monitoring loop** that detects register changes and queues only the delta for review.
- Provide **corrections**: private intake, append-only supersession, public corrections ledger.

## What v1 is not (deferred to v2+)

Company/ASIC ownership data · authoritative counterparty→company resolution · any published multi-hop connection · graph database & visualisation · MCP server · commercial tiers/SLAs.

## How it's built (v1)

**Built with:** Python 3.12 · FastAPI + minimal HTMX (operator-only verification UI) · Postgres + pgvector (private system of record, raw SQL, no ORM) · Claude Opus (multimodal extraction, behind a mockable seam) · a one-way publish step (Jinja2 + Pagefind) to a free static host · GitHub Actions cron for the monitoring loop. No public-facing backend; the static site is as fresh as the last publish run.

## License

TBD, leaning toward an open data licence (e.g. CC BY 4.0) for the dataset/exports. See PRD "Open items".
