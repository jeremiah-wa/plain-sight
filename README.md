# Plain Sight

**Australian federal politicians' declared interests, structured, searchable, sourced, and honest.**

Politicians' financial interests *are* disclosed, as per-member scanned (often handwritten) PDFs with no API and no structured export. They are technically public but practically invisible. Plain Sight makes them legible, with a source link and freshness date on every claim, and a human confirming every published fact.

> Plain Sight is a **faithful mirror of the official record**. In v1 it publishes only what a member *declared*, never inferred connections.

## Status

Early build. A **walking skeleton** runs one member end-to-end (download → store → extract → confirm → display) via a crude operator CLI. The v1 scope, data model, and decisions are specified in **[docs/PRD.md](docs/PRD.md)**; how the system is put together (with diagrams) is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**; supporting terminology is in **[docs/GLOSSARY.md](docs/GLOSSARY.md)**.

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

For the module/seam layout, data model, and deployment (with mermaid diagrams), see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Running the skeleton

The code is a single installable package (`plain_sight`) with a crude operator CLI that stands in for the real verification UI. It needs a reachable Postgres (`PLAIN_SIGHT_DATABASE_URL`); extraction runs against the live model only with the `llm` extra installed and an Anthropic key, otherwise the `Extractor` seam is stubbed in tests.

```bash
uv sync                                   # install (add --extra llm for the live extractor)
uv run plain-sight migrate                # apply hand-authored SQL migrations
uv run plain-sight ingest --member "Jane Doe" --pdf register.pdf --url <source-url>
uv run plain-sight confirm <event-id> --by "operator"
uv run plain-sight show --member "Jane Doe"
uv run pytest                             # deterministic tests; -m postgres needs PLAIN_SIGHT_TEST_DATABASE_URL
```

Every extracted claim starts `pending`; only `confirm` makes it `verified`, and `show` renders verified claims only.

## License

TBD, leaning toward an open data licence (e.g. CC BY 4.0) for the dataset/exports. See PRD "Open items".
