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
- Publish a **read-only searchable web view + flat data exports (CSV/Parquet, Datasette-style)**.
- Run a **cheap monitoring loop** that detects register changes and queues only the delta for review.
- Provide **corrections**: private intake, append-only supersession, public corrections ledger.

## What v1 is not (deferred to v2+)

Company/ASIC ownership data · authoritative counterparty→company resolution · any published multi-hop connection · graph database & visualisation · MCP server · commercial tiers/SLAs.

## Prior art in this workspace (reuse, don't reinvent)

- `../register-watch`, the direct antecedent: canonical Postgres schema, AU data-sources map, change-detection, LLM usage, public-API, licensing strategy, Dagster scaffold.
- `../politico-coi-poc`, working Postgres + pgvector + FastAPI prototype with provenance and SQL conflict rules (the recursive-CTE engine is the **v2** connections layer).
- `../uk-ptp`, full-stack UK transparency platform; architectural reference for the eventual v2 shape.

## License

TBD, leaning toward an open data licence (e.g. CC BY 4.0) for the dataset/exports. See PRD "Open items".
