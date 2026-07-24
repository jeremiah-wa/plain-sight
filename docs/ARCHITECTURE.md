# Plain Sight, Architecture

How Plain Sight is put together, and why. This document describes both the **v1 target architecture** (specified in [PRD.md](PRD.md)) and the **walking skeleton** that exists in the code today. Where they differ, the difference is called out.

For product scope and rationale, read [PRD.md](PRD.md). For the vocabulary used throughout (declaration event, provenance, bitemporal, publish gate, minimise the person), read [GLOSSARY.md](GLOSSARY.md).

---

## The shape of the system

Plain Sight is a **private pipeline plus a one-way publish step to a static public site**. There is no public-facing backend. The Postgres system of record and the operator UI are never reachable by readers; the public only ever sees pre-rendered artifacts produced by the publish gate.

```mermaid
flowchart LR
    subgraph src["Sources (external)"]
        aph["aph.gov.au registers\n(per-member scanned PDFs)"]
    end

    subgraph private["Private pipeline (operator-only)"]
        ingest["Ingest & extract\n(multimodal LLM)"]
        db[("Postgres\nsystem of record\n+ pgvector")]
        verify["Verification UI\n(FastAPI + HTMX, local)"]
        monitor["Monitoring loop\n(GitHub Actions cron)"]
    end

    subgraph public["Public (static, read-only)"]
        gate{{"Publish gate\nverified-only + minimise-the-person"}}
        site["Static site\n(HTML + Pagefind search)"]
        exports["Data exports\n(SQLite / CSV / Parquet)"]
    end

    aph --> ingest --> db
    db --> verify --> db
    monitor --> aph
    monitor --> ingest
    db --> gate --> site
    gate --> exports

    reader(["Public reader"]) --> site
    reader --> exports
```

The design objective is to **minimise human-minutes per week**. Everything is automated except the one irreducible human step: confirming or correcting each extracted claim before it can be published.

---

## Non-negotiable properties, and where they live

These six properties from the PRD are the reason the architecture looks the way it does. Each one is anchored to a specific place in the system, so it is enforced structurally rather than by convention. **This table is the canonical list of product invariants.** `AGENTS.md` restates each as an imperative tripwire that links back here; the rationale lives only in this document (and, once a decision changes, in the superseding record under `docs/decisions/`).

| Property | Where it is enforced |
|---|---|
| **Mirrored facts only** (nothing inferred is published in v1) | The data model stores only declared claims; no Type B connection reaches the publish gate. |
| **Counterparties stay provisional** | A declared company/trust/asset is a `counterparty` row with `resolved = false`, referenced by UUID. v1 never asserts a legal identity (e.g. an ACN); display is always "as declared". |
| **Verified-only display** | The **publish gate**: unverified rows are *physically absent* from the public artifacts, not merely filtered by a query. |
| **Minimise the person** | Also the publish gate: household interests published as role-based signals ("spouse holds X"), names only via a logged editorial override. |
| **Never silently edit history** | Append-only, bitemporal event log; corrections are supersession events, the prior version is retained and marked superseded. |
| **Per-claim provenance** | Every declaration event carries a `{document_id, page, extraction_method, extraction_confidence, fetch_timestamp, bbox?}` pointer, attached at the mapping step. |

---

## Modules and seams

The system is a **single installable Python package** (`plain_sight`), not a multi-package monorepo. Modules mirror the test seams one-to-one, so *module ↔ seam ↔ test ↔ issue* line up.

```mermaid
flowchart TD
    cli["cli.py\ncrude operator CLI\n(stands in for the verification UI)"]
    service["service.py\napplication services\n(ingest / confirm / render)"]

    subgraph seams["The four test seams"]
        sources["sources/\nimmutable document store"]
        extraction["extraction/\nExtractor seam + mapping"]
        dbmod["db/\nRepository seam (memory + Postgres)"]
        publishmod["publish/  (planned)\nthe publish gate"]
    end

    domain["domain/\nPydantic types at the boundaries"]
    config["config.py\nenv-resolved settings"]

    cli --> service
    service --> sources
    service --> extraction
    service --> dbmod
    service -.-> publishmod
    sources --> domain
    extraction --> domain
    dbmod --> domain
    cli --> config
```

Each seam is a narrow interface with two implementations (a real one and a test double), so the whole flow can be driven deterministically in tests and against live infrastructure in the CLI:

- **`sources/` — the document store.** Content-addressed, write-once storage for source PDFs (named by SHA-256, never overwritten). The immutable source is the provenance anchor.
- **`extraction/` — the `Extractor` seam plus mapping.** The one place a live multimodal model is consulted, behind a `Protocol` (model id is config-driven). `StubExtractor` returns a fixed result so tests assert normalisation and provenance without a network or LLM nondeterminism. `map_candidates` is a pure function: candidates → counterparties + declaration events, where provenance is attached and a declared counterparty becomes a first-class UUID-referenced entity.
- **`db/` — the `Repository` seam.** A `Protocol` with an in-memory implementation (deterministic tests) and a `psycopg` v3 + raw SQL implementation (the real system of record). The verified-only display rule is asserted against the in-memory repo and checked against Postgres under the `postgres` mark.
- **`publish/` — the publish gate (planned).** Reads Postgres and emits the sanitised static artifacts in one pass. The single enforcement point for verified-only and minimise-the-person.

`domain/` holds the Pydantic types used **at the boundaries only** (extractor output, CLI input, rows crossing back into the application), never as a persistence layer. `config.py` is the one place the model id and Postgres URL are read from the environment.

---

## The end-to-end flow (walking skeleton, as built)

The code today implements a **walking skeleton**: one member, end to end, with a crude CLI confirm standing in for the real verification UI. The four CLI commands (`migrate`, `ingest`, `confirm`, `show`) exercise the whole spine.

```mermaid
sequenceDiagram
    actor Op as Operator
    participant CLI as cli.py
    participant Svc as service.py
    participant Store as DocumentStore
    participant Ext as Extractor
    participant Map as map_candidates
    participant Repo as Repository (Postgres)

    Op->>CLI: ingest --member --pdf
    CLI->>Svc: ingest(...)
    Svc->>Repo: get / add Person
    Svc->>Store: store(pdf_bytes)  (content-addressed, write-once)
    Store-->>Svc: SourceDocument
    Svc->>Repo: add_source_document
    Svc->>Ext: extract(document, bytes)
    Ext-->>Svc: ExtractionResult (candidates)
    Svc->>Map: map_candidates(document, result)
    Map-->>Svc: counterparties + pending DeclarationEvents
    Svc->>Repo: add_counterparty / add_declaration_event
    Svc-->>Op: pending claim ids

    Op->>CLI: confirm <event_id> --by
    CLI->>Svc: confirm(...)
    Svc->>Repo: verify_event (pending -> verified)

    Op->>CLI: show --member
    CLI->>Svc: render_member_interests
    Svc->>Repo: verified_events_for_member
    Repo-->>Svc: verified claims only
    Svc-->>Op: "as declared" text, with provenance
```

Every extracted claim starts `pending`. Only `confirm` transitions a claim to `verified`, and `show` renders **verified claims only**, the verified-only filter lives in the repository query so nothing pending can reach the reader.

---

## Data model

PostgreSQL is the single system of record. The core is **append-only and bitemporal**: facts are never mutated, and two independent time axes ("when the interest was held" vs "when it entered the record") make "state as of date D" answerable.

```mermaid
erDiagram
    person ||--o{ source_document : "files"
    person ||--o{ declaration_event : "declares"
    counterparty ||--o{ declaration_event : "named by"
    source_document ||--o{ declaration_event : "provenance anchor"

    person {
        uuid id PK
        text canonical_name
        text_array name_variants
        jsonb external_ids
        text chamber
        text jurisdiction
    }
    source_document {
        uuid id PK
        uuid member_id FK
        text content_sha256
        text storage_path
        int page_count
        timestamptz fetched_at
    }
    counterparty {
        uuid id PK
        text raw_string
        text normalised_label
        bool resolved
    }
    declaration_event {
        uuid id PK
        uuid member_id FK
        uuid counterparty_id FK
        text category
        daterange validity
        uuid superseded_by FK
        uuid document_id FK
        int page
        float extraction_confidence
        text verification_status
        text verified_by
        timestamptz verified_at
    }
```

Key modelling decisions:

- **`declaration_event` is the atomic unit of record.** Immutable claim content; verification is a state transition on the row. Provenance is carried per-claim, inline on the event.
- **Valid time is a single half-open `daterange` (`validity`), guarded by a database constraint.** An `EXCLUDE USING GIST` constraint (`declaration_event_no_active_overlap`) makes it *impossible* for two active events to claim overlapping validity for the same `(member, counterparty, category)`, enforced by Postgres rather than application code. The constraint is partial on `superseded_by IS NULL` (superseded versions do not participate) and `DEFERRABLE INITIALLY IMMEDIATE` so a correction can append a successor and mark its predecessor superseded in one transaction. See migration `0002_temporal_integrity.sql`.
- **Corrections supersede, never overwrite.** `superseded_by` points at the successor that replaced a row; `NULL` means active/current. The prior version is retained and marked superseded, never deleted.
- **Opaque UUID primary keys everywhere.** No sequential, publicly enumerable ids, so exports stay stable and non-enumerable.
- **Counterparties are first-class but provisional.** A declared company/trust/asset is a `counterparty` row referenced by UUID, explicitly `resolved = false`. v1 never asserts a legal identity (e.g. an ACN); the UUID is the anchor v2 resolution attaches to.
- **Politicians are hard-resolved.** `canonical_name` + `name_variants` + `external_ids` (Parliament / OpenAustralia / Wikidata) enable tracking the same member across parliaments.

### Skeleton vs v1 target

The migrations (`0001_walking_skeleton.sql`, then `0002_temporal_integrity.sql`, then `0003_bitemporal_query_views.sql`) start minimal and grow toward the full v1 target **without re-modelling the core**:

| Concern | Skeleton (today) | v1 target |
|---|---|---|
| Valid time | ✅ half-open `daterange` (`validity`) with `EXCLUDE USING GIST` preventing overlapping validity per active `(member, counterparty, category)` (migration 0002) | `tstzrange` record axis added when system-time "as of" views exist |
| Corrections | `superseded_by` supersession pointer in place; deferrable constraint lets a correction append + supersede atomically (migration 0002) | full append-only **supersession** workflow + corrections ledger |
| "State as of date D" | ✅ SQL **views** over the event log (`current_interest`, `active_interest`), sliced by valid time; supersession honoured, no stored snapshots (migration 0003) | `tstzrange` record-axis travel ("as the record stood at T") added alongside the record range |
| Counterparty similarity | not yet | **pgvector** embedding + similarity at query time (no materialised clusters) |
| Family members | not modelled | `Person` entities + private household→member edge; public display is role-based signal only |

---

## Deployment

Cheap and mostly-serverless. No always-on server of our own, and no public-facing backend.

```mermaid
flowchart TB
    subgraph gha["GitHub Actions (cron)"]
        loop["Monitoring loop:\npoll -> hash/page-count diff\n-> re-extract changed pages\n-> queue delta"]
    end

    subgraph managed["Managed Postgres (Supabase)"]
        pg[("System of record\n+ pgvector")]
    end

    subgraph local["Operator's machine"]
        ui["Verification UI\n(FastAPI + HTMX, local)"]
        pub["Publish step\n(Jinja2 + Pagefind)"]
    end

    subgraph host["Free static host"]
        static["Static site + exports\n(no runtime backend)"]
    end

    aph["aph.gov.au"] --> loop
    loop --> pg
    ui <--> pg
    pg --> pub --> static
```

- **Managed Postgres with pgvector** is the durable, cloud-reachable system of record. It is hosted on **Supabase**; there is no local Docker Postgres.
- **GitHub Actions cron** drives the monitoring loop (daily-ish is ample; the registers update ~monthly around sitting weeks).
- **The verification UI runs locally** against that Postgres, operator-only.
- **The publish step pushes static artifacts to a free static host.** Public data is as fresh as the last publish run, consistent with "freshness surfaced, not promised".

---

## Extraction: why a multimodal LLM behind a seam

The corpus is small and bounded (~227 federal members; low-thousands of pages per parliament), so this is a **trust problem, not a scale problem**. The sources are frequently handwritten, so extraction is **vision over the scan image**, not OCR-then-parse. Because accuracy dominates and the corpus is tiny, premium per-page model cost is negligible: optimise accuracy, not cost.

The live model (Claude Opus, via the optional `llm` extra) lives **only** behind the `Extractor` `Protocol`, with the model id in config. Consequences:

- Tests mock the boundary and assert mapping, normalisation, and provenance **deterministically**, with no live network and no LLM nondeterminism. The `anthropic` SDK is never imported by the test suite.
- Structured output / tool-use forces the candidate schema; there is no free-text parsing downstream.
- `bbox` provenance is optional and operator-assisted: the model returns the page it read a field from, but never fabricates pixel coordinates.

---

## What v1 defers (built so as not to preclude)

The architecture is deliberately shaped so a **v2 connections layer** can attach without re-modelling the core:

- The stable **counterparty UUID** is the anchor for v2 authoritative resolution (declared string → real company), modelled as an appended `resolution_event`.
- The private **household→member edge** preserves the MP → household → counterparty chain for v2 tracing.
- A **graph** is a v2 concern, introduced as a *derived projection* over Postgres, never a second source of truth.

Explicitly out of v1: MCP server, ASIC/company ownership data, authoritative counterparty resolution, graph database and visualisation, any published inferred connection, commercial tiers/SLAs.
