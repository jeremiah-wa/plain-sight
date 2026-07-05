# Plain Sight, Domain Glossary (Ubiquitous Language)

Use these terms consistently in code, schema, and docs.

| Term | Meaning |
|---|---|
| **Declaration event** | The atomic unit of the system of record: one immutable, append-only claim that a member *declared* one interest, carrying valid-time, record-time, provenance, and verification metadata. Never mutated. |
| **Mirrored fact (Type A)** | A claim that faithfully republishes an official disclosure ("as declared by the member"). The only thing v1 publishes. |
| **Inferred connection (Type B)** | A synthesised, multi-hop link no single source states (e.g. member → spouse → company → contract). Internal lead signal at most in v1; **never published** until v2 and human-confirmed. |
| **Per-claim provenance** | Every declaration event points to `{document_id, page, bbox?, extraction_method, extraction_confidence, fetch_timestamp}`. Provenance is per-claim, not per-document. |
| **Bitemporal** | Two independent time axes: **valid time** (`valid_from`/`valid_to`, when the interest was actually held per the register's effective dates) and **record time** (`recorded_at`, `ingested_at`, `verified_at`, when facts entered the record). Enables "state as of date D". |
| **Hard resolution** | Assigning a canonical identity to an entity by linking to an external authority (used for **politicians** only in v1). |
| **Provisional counterparty string** | A company/trust/asset named in a declaration, stored as raw + normalised string, soft-clustered, explicitly **unresolved**. v1 never asserts a legal identity (e.g. ACN) for it. |
| **Resolution event** | (v2) An appended, human-confirmed, provenance-carrying claim that a provisional counterparty string maps to a real company record. |
| **Supersession** | How change and correction are represented: a new declaration event that supersedes a prior one. The prior version is retained, marked superseded, never deleted. |
| **Verification status** | Per-claim state: `pending` (machine-extracted, not yet reviewed) or `verified` (human-confirmed). Only `verified` claims are published. |
| **Dispute state** | A claim credibly contested is publicly flagged "disputed, under review" rather than hidden. |
| **Corrections ledger** | The public, append-only record of every resolved correction (what changed, why, when). Distinct from the **private intake** channel. |
| **Freshness dates** | Per-member "source last checked / source last changed / last verified by us", surfaced, not promised via SLA. |
| **Minimise the person** | Privacy rule: publish the household conflict *signal* ("spouse holds X") with role, not the third party's name; role-only for minors; names only via a logged editorial override when the person's own public role is materially in the public interest. |
| **The monitoring loop** | The cheap, mostly-automated poll → hash/page-count diff → re-extract changed pages → claim-level delta → human-review-queue cycle that keeps data current with minimal human-minutes. |
| **Jurisdiction** | Canonical field (`AU:federal`, `UK:parliament`, …) enabling a jurisdiction-agnostic core with per-source adapters. v1 builds only the `AU:federal` adapter. |
