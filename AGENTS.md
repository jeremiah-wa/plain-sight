# AGENTS.md

Operating manual for coding agents in this repo. Thin by design: it defers all
conceptual content to the human docs and only states what those docs don't (how
to run things, invariants you must not break, house rules).

## Orientation

Plain Sight structures Australian federal politicians' declared interests, with a
source link and freshness date on every claim and a human confirming every
published fact. Early build: a walking skeleton runs one member end-to-end.

Read before changing anything:

- **[docs/PRD.md](docs/PRD.md)** — product scope, what v1 is and is not.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — module/seam layout, data model, deployment (with diagrams).
- **[docs/GLOSSARY.md](docs/GLOSSARY.md)** — the ubiquitous language. Use these terms in code, schema, commits, and messages.
- **[README.md](README.md)** — the short version.

## Commands

```bash
uv sync                                   # install (add --extra llm for the live extractor)
uv run plain-sight migrate                # apply hand-authored SQL migrations
uv run plain-sight ingest --member "Jane Doe" --pdf register.pdf --url <source-url>
uv run plain-sight confirm <event-id> --by "operator"
uv run plain-sight show --member "Jane Doe"
uv run pytest                             # deterministic; -m postgres needs PLAIN_SIGHT_TEST_DATABASE_URL
uv run ruff check --fix && uv run ruff format
uv run mypy                               # strict, whole tree
uv run pre-commit install                 # ruff + mypy share the uv.lock-pinned versions
```

## Invariants (do not break these)

Imperative tripwires, enforced structurally, not by convention. Breaking one is a bug even if tests pass. The **rationale lives in the linked docs, not here**; each line just states the line you must not cross and where to read why.

Product invariants (canonical list: [ARCHITECTURE §Non-negotiable properties](docs/ARCHITECTURE.md#non-negotiable-properties-and-where-they-live)):

- **Mirrored facts only.** Never publish anything inferred (a Type B connection). v1 mirrors the official record; it does not assert connections.
- **Counterparties stay provisional.** A declared company/asset is a `counterparty` row with `resolved = false`, referenced by UUID. Never assert a legal identity (e.g. an ACN) in v1.
- **Verified-only display.** Only `verified` claims reach a reader. The filter lives in the repository query / publish gate, never in a caller. Nothing `pending` is ever rendered or exported.
- **Minimise the person.** Publish household interests as role-based signals ("spouse holds X"), never a third party's name, except via a logged editorial override; role-only for minors.
- **Never silently edit history.** Never mutate or delete a `declaration_event`. Corrections **supersede**: append a successor, mark the predecessor superseded.
- **Per-claim provenance.** Every declaration event carries its `{document_id, page, extraction_method, extraction_confidence, fetch_timestamp, bbox?}`, attached at the mapping step, never fabricated.

Structural invariants (rationale in the linked ARCHITECTURE sections):

- **Raw SQL, no ORM.** Migrations are hand-authored SQL, applied in order. Postgres enforces integrity (e.g. the `EXCLUDE USING GIST` overlap constraint), not application code. ([§Data model](docs/ARCHITECTURE.md#data-model))
- **The Extractor seam is the only place a live model is consulted.** `anthropic` is behind the optional `llm` extra and **must never be imported by the test suite** — tests mock the boundary and assert mapping/normalisation/provenance deterministically. ([§Extraction](docs/ARCHITECTURE.md#extraction-why-a-multimodal-llm-behind-a-seam))
- **Module ↔ seam ↔ test ↔ issue line up.** The four seams (`sources/`, `extraction/`, `db/`, `publish/`) each have a real impl and a test double. Keep that one-to-one mapping; `domain/` types live at boundaries only, never as a persistence layer. ([§Modules and seams](docs/ARCHITECTURE.md#modules-and-seams))
- **Opaque UUID primary keys everywhere.** No sequential, publicly enumerable ids. ([§Data model](docs/ARCHITECTURE.md#data-model))

## House rules

- **No em dashes** in comments, docs, PR descriptions, or commit messages. Use commas, parentheses, or separate sentences.
- **uv, not poetry**, for all Python tooling.
- **Postgres is hosted on Supabase; there is no local Docker.** Never run the destructive Postgres test against it.
- **Use the GLOSSARY vocabulary** (declaration event, provenance, bitemporal, publish gate, minimise the person, supersession) consistently in code and prose.
- **Coding style is mechanised, not documented.** Formatting, imports, naming, and complexity are enforced by `ruff` and `mypy` (see `pyproject.toml`). There is deliberately no prose "coding conventions" list; a rule earns a written line only when it is genuinely non-obvious and load-bearing (the same bar as the invariants above).

## Workflow

The seam vocabulary (`sources`, `extraction`, `db`, `publish`, `domain`, `service`, `cli`, `migrations`, `infra`) is one closed set reused as commit scope and subsystem label, so issue, branch, commits, PR, and label all key off the same axis.

- **Commits.** Conventional Commits with a seam scope: `feat(extraction): map handwriting confidence onto candidates (#23)`. Omit the scope for genuinely cross-cutting changes (`refactor:`, `chore:`).
- **Branches.** `<type>/<issue#>-<slug>`, e.g. `feat/23-publish-gate`. A bare `<type>/<slug>` is allowed for issue-less chores.
- **Pull requests.** Fill `.github/PULL_REQUEST_TEMPLATE.md`. It carries only the **handover delta** — what the reviewer cannot get from the diff, this file, or the linked issue. Do not restate standing rules; link them.
- **Decisions (ADRs).** A change that **reverses or materially alters** a product invariant or a PRD/architecture commitment gets a MADR record in `docs/decisions/` **plus** an edit to the canonical doc, which links back to the ADR. Pure additions and clarifications are just doc edits. ADRs are immutable **once merged to `main`**: to change one after that, supersede it with a new record and set `Superseded by`. Before it lands on `main` it is a draft on its own branch, so edit it freely there, `Status` included.

## Reviewing

Run the `code-review` skill (full-diff Standards + Spec). Form your **own** risk read of the whole diff **first**, then:

- verify the PR's **Invariants touched** line against the diff (treat it as a claim to check, not a given);
- resolve each **Known unknown** the author declared, and note where your independent findings diverge from theirs. The divergence is the signal.
