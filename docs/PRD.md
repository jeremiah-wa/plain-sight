# Plain Sight, Product Requirements Document

**Version:** 1.0
**Date:** 2026-07-05
**Status:** Ready for build (v1 scope)

---

## Problem Statement

From the perspective of a journalist, researcher, or engaged citizen who wants to hold Australian federal politicians accountable:

- Politicians' financial interests **are** disclosed, in the Register of Members' Interests and the Register of Senators' Interests, but they are published as **per-member scanned PDFs, frequently handwritten**, with no API, no structured export, and no way to compare a member over time or across members.
- The information is therefore **technically public but practically invisible**. The conflicts of interest a citizen would care about are, quite literally, hiding in plain sight.
- Existing efforts either go stale (media orgs' searchable databases have repeatedly gone defunct) or stop at the raw scan (OpenAustralia mirrors the PDFs but does not structure them).
- The genuinely valuable question, *"does this politician's household have a financial interest that conflicts with what they vote on or oversee?"*, cannot be answered without (a) structuring the disclosures and (b) eventually joining them to company ownership data. Company ownership data in Australia is **paywalled** (ASIC has no free public ownership API; there is no free beneficial-ownership register equivalent to the UK PSC register).

The user is a **solo builder** who wants to ship something honest and defensible, not a commercial-grade platform with staff.

## Solution

From the user's perspective:

**Plain Sight** is a public-accountability service that makes Australian federal politicians' declared interests **structured, searchable, sourced, and honest**.

For **v1**, Plain Sight:

- Ingests the per-member PDFs from the official registers, extracts each declared interest with a multimodal LLM, and **has a human confirm every claim before it is published**.
- Publishes only **mirrored facts** ("as declared by the member"), never inferred connections. It is a faithful mirror of the official record, not an accusation engine.
- Stores every claim as an **immutable, bitemporal declaration event** with **per-claim provenance** (source document + page + region + extraction method + confidence + who verified it and when).
- Presents the data as a **simple, read-only, searchable web view plus flat data exports (CSV/Parquet, Datasette-style)**, with a **source link and freshness dates on every claim**.
- Runs a **cheap, mostly-automated monitoring loop** that detects when a member's register changes and queues only the delta for human review.
- Provides a **corrections process**: a private intake channel, corrections applied as append-only supersession events, and a **public corrections ledger**.

Plain Sight is deliberately architected so that a **v2 connections layer** (join declared counterparties to real company/ownership records, detect multi-hop conflicts, expose an MCP server and a graph) can be added later **without re-modelling the core**. But none of that ships in v1.

---

## User Stories

### Discovery & search (public reader)

1. As a citizen, I want to look up a specific MP or Senator by name, so that I can see everything they have declared.
2. As a citizen, I want to search declared interests by keyword (e.g. a company or sector name), so that I can find which politicians declared something related.
3. As a journalist, I want to filter interests by category (shareholding, directorship, real estate, gift, sponsored travel, trust, liability, etc.), so that I can focus my investigation.
4. As a journalist, I want to filter by party and by chamber (House vs Senate), so that I can scope an analysis.
5. As a researcher, I want to see a politician's interests **as of a specific date**, so that I can check what they held at the time of a relevant vote or decision.
6. As a researcher, I want to see the full change history of a politician's declarations, so that I can see what was acquired or divested and when.
7. As a citizen, I want to see when an interest became effective and when it was recorded, so that I understand the timeline.

### Trust, provenance & freshness (public reader)

8. As a skeptical reader, I want every displayed claim to link to the exact source page/scan it came from, so that I can verify it myself.
9. As a reader, I want to see whether a claim was **human-verified or is still pending review**, so that I know how much to trust it.
10. As a reader, I want to see "source last checked", "source last changed", and "last verified by us" dates for each member, so that I know how current the data is.
11. As a reader, I want to see a confidence indication for machine-extracted-but-unverified claims, so that I can weigh them appropriately.
12. As a reader, I want a clear statement that Plain Sight mirrors the official record and does not assert connections, so that I understand what the data does and does not claim.

### Data access (power user / developer)

13. As a data journalist, I want to download the full dataset as CSV/Parquet, so that I can do my own analysis.
14. As a developer, I want a browsable structured-data view (Datasette-style), so that I can query the data ad hoc.
15. As an interoperability-minded user, I want the interest taxonomy to align with established categories (e.g. mySociety's), so that cross-jurisdiction comparison is possible later.

### Corrections & disputes (subject / public)

16. As an MP's staffer, I want a private channel to report that a claim was transcribed incorrectly, so that it can be fixed without airing sensitive details publicly.
17. As a subject, I want to dispute a claim I believe is wrong, so that the claim is publicly flagged as disputed while under review.
18. As a reader, I want to see a public corrections ledger of every correction ever made, so that I can trust that Plain Sight does not silently rewrite its own history.
19. As a subject whose official register entry is itself wrong, I want Plain Sight to faithfully mirror the official record and flag my dispute, rather than silently diverge from the source.
20. As a subject, I do not want a faithfully-mirrored public-record entry taken down merely on request, but I do want a documented, honest review of any factual dispute.

### Privacy (third parties)

21. As the spouse of a politician, I want the conflict-relevant signal published ("spouse holds shares in X") **without my name being independently searchable**, so that I am not doxxed by aggregation of an otherwise-obscure record.
22. As the parent of a dependent child named in a register, I want my child referred to by role only ("dependent child"), never by name or identifying detail.
23. As a reader, I still want to see household interests (spouse/dependent) because that is where real conflicts hide, just expressed as a role-based signal.
24. As an editor, I want the ability to consciously publish a family member's name **when that person's own public role (e.g. lobbyist, director) makes their identity materially in the public interest**, recorded as a logged editorial decision.

### Ingestion & operations (operator = the solo builder)

25. As the operator, I want the pipeline to detect when a member's register PDF has changed, so that I do not have to check manually.
26. As the operator, I want only the changed/new pages re-extracted and only the delta queued for review, so that ongoing effort stays near-zero per week.
27. As the operator, I want a verification UI that shows the source scan crop beside the extracted fields, so that I can confirm or correct a claim in seconds.
28. As the operator, I want to bulk-approve high-confidence extractions and spend attention only on low-confidence ones, so that the backfill and ongoing review stay tractable solo.
29. As the operator, I want extraction, ingestion, and diffing fully automated so that the only human step is the final confirm/correct.
30. As the operator, I want the pipeline to respect the source (rate limiting, backoff, bot identification, robots.txt), so that Plain Sight is not blocked.
31. As the operator, I want corrections and supersessions to be append-only, so that the audit trail can defend Plain Sight if a claim is challenged.
32. As the operator, I want the original source PDFs stored immutably, so that provenance always resolves even if the government site changes.

### Future-facing (explicitly v2+, captured so the core does not preclude them)

33. As an investigator, I want declared counterparty strings eventually resolved to real company records (with confidence + provenance + human confirmation), so that indirect conflicts can be surfaced.
34. As an investigator, I want to traverse multi-hop connections between a politician's household and a company, so that non-obvious conflicts become visible.
35. As an AI agent, I want to query Plain Sight through an MCP server that returns cited records, so that I can assist research without fabricating claims.
36. As a reader, I want an interactive graph visualisation of connections, so that I can explore the network.

---

## Implementation Decisions

### Product framing

- **Type A only in v1.** Plain Sight publishes **mirrored facts** ("as declared") and never publishes **inferred connections** (Type B). Inference may run internally as a private signal for editorial lead-generation, but nothing inferred is published in v1.
- **Jurisdiction:** Australia federal (House + Senate) for v1. The canonical schema is jurisdiction-agnostic (via a `jurisdiction` field and per-source adapters) so UK/state expansion is possible later, but only the AU adapter is built in v1.

### Data model (system of record)

- **Storage:** PostgreSQL as the single system of record, with **pgvector** for embeddings. **No graph database in v1.** A graph is a v2 concern and will be introduced as a *derived projection* built from Postgres, not as a second source of truth.
- **Append-only + bitemporal.** No destructive updates. Every fact is a `declaration_event` row that is never mutated. Corrections and changes are **new superseding events**.
- **Two time axes:** *valid time* (`valid_from` / `valid_to`, from the register's effective dates) and *record/transaction time* (`recorded_at` = filing date on the page; `ingested_at`, `verified_at`). "Current state" and "state as of date D" are **SQL views over the event log**, not stored tables.
- **Per-claim provenance.** Every `declaration_event` carries a provenance pointer: `{document_id, page, bbox?, extraction_method, extraction_confidence, fetch_timestamp}` plus verification metadata: `{verification_status, verified_by, verified_at}`. Provenance is per-claim, **not** per-document.
- **Temporal integrity constraint.** Use Postgres range types (`daterange`/`tstzrange`) and `EXCLUDE USING GIST` constraints to prevent overlapping validity per entity.
- **Opaque UUID primary keys**, never exposed sequential IDs, so the public API/exports are stable and non-enumerable.

### Entities & entity resolution

- **Politicians: hard resolution.** Parliamentarians are canonical `Person` entities linked to external authority IDs (Parliament member IDs, OpenAustralia IDs, Wikidata QIDs where available). `canonical_name` + `name_variants`. This enables "same member across parliaments" and future joins to voting records.
- **Declared counterparties: provisional strings only.** A company/trust/asset named in a declaration is stored as the **raw transcribed string + a normalised label**, grouped by **soft clustering**, and explicitly marked **unresolved/provisional**. Plain Sight does **not** assert a legal identity (e.g. an ACN) for a counterparty in v1, because there is no free authoritative register to verify against and asserting a specific legal entity would be an inference (Type B) with defamation risk. Display is always *"as declared: '<string>'"*.
- **Family members: canonical but private-internal by default.** Spouses/dependents are modelled as `Person` entities so the household→interest link is preserved for v2 tracing, but they are **not public** by default. Public display uses the **role + signal** ("spouse holds X"), never the name.
- **Authoritative counterparty resolution (declared string → real company, with confidence + provenance + human confirmation) is a defining v2 task**, modelled as an appended `resolution_event` so the audit trail extends naturally.

### Extraction pipeline

- **Corpus is small and bounded** (~227 federal members; low-thousands of pages per parliament). This is not a scale problem; it is a trust problem. Therefore:
- **Extraction = multimodal LLM over the scan image** (vision, not OCR-then-parse), because the sources are frequently handwritten. Extraction emits **candidate** `declaration_event`s with self-reported confidence and the page/region each field was read from.
- **Human verification on every published claim.** Only `verified` events become public. High-confidence candidates may be bulk-approved by a human skimming; low-confidence ones get careful attention.
- **Effective dates get special attention** in the verification UI, they are the most important and most error-prone field (often handwritten) and are what make "state as of date D" correct.
- **The verification UI is a first-class product**, not a script: source-scan crop shown beside extracted fields.
- **Candidates and corrections are retained** in the immutable log (enables later measurement of model accuracy and training on corrections).

### Retrieval

- **Vectors are for retrieval and entity-assist, not generation.** pgvector powers (a) semantic/fuzzy search over declaration text and (b) counterparty clustering/entity-resolution assist. Hybrid semantic + structured + temporal filtering happens in one SQL layer.
- **The system returns cited records, never generated prose that asserts new facts.** This is a hard rule: the whole value proposition is faithfulness, so no LLM-synthesised claims are surfaced as data.

### Ingestion & freshness

- **Sources:** House per-member register index and Senate tabled volumes on aph.gov.au; OpenAustralia's mirror as a documented fallback with attribution.
- **Change detection:** scheduled poll (daily-ish is ample; updates are ~monthly around sitting weeks). Store content hash + page count per member PDF; a hash change or page-count increase flags that member for re-extraction. Then diff at the **claim level** and produce **supersession events** for the delta.
- **Original PDFs stored immutably** as the provenance anchor.
- **Freshness is surfaced, not promised.** No freshness SLA. The public commitment is *honesty* ("we never publish an unverified claim; here is how stale each claim is"), not *speed*. Show "source last checked / source last changed / last verified" per member.
- **Source-respectful fetching:** cache, backoff, identify the bot, honour robots.txt.

### Corrections & disputes

- **Intake is private** (email + simple no-login web form) so subjects can report errors, including sensitive/family details or legal correspondence, without posting them publicly.
- **A `dispute` state on claims:** credible disputes are publicly flagged *"disputed, under review"* (with the nature of the dispute) rather than hidden. Transparency about uncertainty is the trust feature.
- **Corrections are supersession events, never deletions.** The prior (wrong) version stays in the log, marked superseded, with who/why/when. Plain Sight must never silently edit its own history.
- **Public corrections ledger:** every resolved correction is published (what was claimed, what changed, why, when). GitHub issues/repo is an acceptable home for *this public ledger*, but **not** for intake.
- **Source-error handling:** where the official register itself is wrong, Plain Sight **mirrors the error faithfully and flags the dispute**, rather than diverging from the source. Plain Sight is a mirror of the official record.
- **No takedown for faithful mirroring** of a public record on mere request; factual disputes get a documented, honest review. Correspondence is retained.

### Presentation (v1)

- **Read-only public web view:** search/filter by member, party, chamber, category; "as declared" strings; per-claim source links; verification status; freshness dates. Static-site-friendly; no login; no graph; no agent interface.
- **Flat data exports:** CSV/Parquet + a Datasette-style browsable read layer, mirroring mySociety's approach for credibility and interoperability.

### Explicitly deferred to v2+ (built so as not to preclude)

MCP server; ASIC/company ownership data; authoritative counterparty→company resolution; graph database and multi-hop path-finding; graph visualisation; any published inferred connection; commercial tiers / SLAs.

---

## Testing Decisions

### What makes a good test here

- Tests assert **external, observable behaviour**, the structured output of a pipeline stage, the contents of an API/export response, the result of a temporal query, **not** internal implementation details (not "this function called that function").
- **Provenance and temporality are behaviours, not implementation**, and must be tested directly: given a fixed source document, the emitted claim must carry the correct provenance pointer; given a sequence of declaration + alteration events, a "state as of date D" query must return the historically-correct set.
- Extraction correctness is tested against **fixed, checked-in source fixtures** (representative scanned pages, including at least one handwritten and one alteration page) with expected structured output, so extraction/verification logic is exercised without live network calls or live LLM nondeterminism (mock/stub the model boundary; assert the mapping/normalisation and provenance behaviour deterministically).

### Proposed seams (fewest, highest possible, for confirmation)

1. **Ingestion/extraction seam (primary):** `raw source document (fixture) → normalised candidate declaration_event[]`. This is the highest-value seam: a pure-ish function from a stored document to structured candidates with provenance, testable with fixtures and a mocked model boundary.
2. **Temporal/query seam:** `event log (seeded) → state-as-of-date view`. Test the bitemporal SQL views/queries directly against a seeded Postgres.
3. **Public read/export seam:** `seeded DB → CSV/Datasette/API response`. Assert that only `verified` claims are exposed, that family members appear as role-based signals (never names, except logged editorial overrides), that every claim carries a source link and freshness dates.
4. **Change-detection seam:** `(previous document hash/state, new document) → set of supersession events`. Assert that an appended alteration page yields the correct delta and supersession, and that an unchanged document yields no work.

Prefer these existing-style seams over new ones. The privacy rule (story 21–24) and the "verified-only" rule (story 9) are the highest-risk behaviours and must each have a dedicated test at the public read/export seam.

### Modules under test

Ingestion/extraction mapping; bitemporal query views; change-detection/supersession; public read/export layer (incl. privacy minimisation and verified-only gating). The verification UI is validated by exercising the read/write seam beneath it, not by UI snapshot tests.

---

## Out of Scope

- Any **published inferred/multi-hop connection** between a politician and a company (v2; internal-only lead signal at most).
- **Company / ASIC ownership ingestion** and **authoritative counterparty resolution** (v2, data is paywalled in AU).
- **Graph database, graph visualisation, and MCP server** (v2+).
- **State and territory** parliaments, and **non-AU** jurisdictions (schema supports them; adapters not built).
- **Commercial tiers, ARR targets, enterprise SLAs, 99.9% uptime**, explicitly rejected for v1 in favour of a solo-sustainable, honesty-not-speed posture.
- **Voting-record / committee correlation** (valuable, but a later enrichment once the core dataset exists).
- **Fully automated publication** (rejected, human verification on every published claim is a hard v1 constraint).

---

## Further Notes

### Design posture (the non-negotiables)

These are the principles that keep Plain Sight honest and solo-sustainable. Everything above serves them:

1. **Solo and cheap by design.** No commercial tiers, no ARR target, no uptime SLA. The design objective is to *minimise human-minutes per week*, not to maximise infrastructure guarantees. LLM extraction and Postgres are near-free; the only scarce resource is the operator's time, so the pipeline automates everything except the final human confirm.
2. **Mirrored facts only in v1.** Publish what a member declared; publish nothing inferred until it can be human-confirmed with provenance in v2.
3. **Counterparties stay provisional strings.** Do not resolve a declared name to a specific legal entity (e.g. an ACN) in v1; that is an inference with defamation risk and no free authoritative register to verify against.
4. **Privacy: minimise the person.** Publish the household conflict signal ("spouse holds X") with role, not the third party's name; role-only for minors; names only via a logged editorial override when the person's own public role is materially in the public interest.
5. **Never silently edit history.** Corrections are append-only supersessions; the audit trail is as much about auditing Plain Sight as auditing politicians. Private intake, public corrections ledger, mirror-the-source-error-and-flag-the-dispute, no takedown for faithful mirroring.

### Open items to resolve before launch (not blocking the build)

- **Licensing.** Lean toward an **open data licence (e.g. CC BY 4.0) for the dataset/exports** to maximise civic reuse. Confirm aph.gov.au copyright terms and OpenAustralia reuse terms for mirrored scans/links. (~20-min research task.)
- **Extraction QA metric.** Define how model accuracy is measured against accumulated human corrections; decides when (if ever) review could be relaxed. v2-ish.

### First build order (solo, ship-oriented)

1. Lock the **bitemporal event + provenance schema** first (expensive to retrofit).
2. Do **one member end-to-end** manually (download → extract → verify → store → display) before automating anything.
3. Build the **verification UI** (scan crop beside extracted fields), the trust factory.
4. **Backfill the 48th parliament**; publish read-only Datasette + CSV with source links and freshness dates.
5. **Then** turn on the cheap monitoring loop.
