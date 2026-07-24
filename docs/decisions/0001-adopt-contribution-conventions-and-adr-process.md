# 0001. Adopt contribution conventions and an ADR process

- **Status:** Accepted
- **Date:** 2026-07-24

## Context and problem statement

`AGENTS.md` was thin by design, but as implementer and reviewer work (done by a
human or an agent) scales up, the repo needs a clear, low-friction set of ground rules:
commit/branch/PR conventions, a review handover, and a way to record decisions
that change the PRD or architecture without silently editing history. The
question is where each rule lives so that nothing drifts or duplicates, given a
solo builder whose only readers are future-self and coding agents.

## Decision drivers

- Single source of truth: each convention has exactly one canonical home.
- Prefer mechanical enforcement (linters, templates GitHub renders, CI) over prose an agent may skim.
- Keep `AGENTS.md` thin; it is the imperative layer agents read before acting.
- Consistency with the product's own append-only, supersession model.
- Audience is you + agents only; no phantom external-contributor onboarding.

## Considered options

- A dedicated `CONTRIBUTING.md` holding all conventions.
- Expand `AGENTS.md` inline with everything.
- Split by artifact: mechanical rules to their enforcer, prose residue in `AGENTS.md`, decisions in an ADR ledger.

## Decision outcome

Chosen option: "Split by artifact", because it is the only option that keeps
`AGENTS.md` thin, gives every rule a single canonical home, and mirrors the
product's own doc-canonical / append-only-ledger structure.

Concretely:

- **No `CONTRIBUTING.md`.** Mechanical conventions go to their enforcer (`ruff`/`mypy` in `pyproject.toml`, the PR template GitHub auto-inserts); prose residue extends `AGENTS.md` House rules.
- **Invariants are two tiers.** The canonical rationale lives once in [`ARCHITECTURE.md` §Non-negotiable properties](../ARCHITECTURE.md#non-negotiable-properties-and-where-they-live); `AGENTS.md` restates each as a thin imperative tripwire that links back. This reconciled a prior drift (the two lists had diverged, 8 vs 5) and added "minimise the person", which was missing from the agent-facing file.
- **Commits:** Conventional Commits with a seam scope. **Branches:** `<type>/<issue#>-<slug>`. One closed seam vocabulary is reused as commit scope and `area:` label.
- **PRs:** a template carrying only the handover delta, including an "Invariants touched" pointer and a "Known unknowns" section consumed under a blind-first review.
- **Decisions:** doc-canonical, this `docs/decisions/` ledger (MADR) is the append-only record of why the canonical docs changed; an ADR is written only for a material reversal/change.
- **Tracking:** `area:` / `status:` / `type:` labels, `v1`/`v2` milestones, and a Projects board whose columns map to the `status:` labels.

### Consequences

- Good, because "what is true now" is a single read of the canonical doc, and "why it changed" is a single read of the superseding ADR.
- Good, because the implementer's self-certification (PR template) and the reviewer's checklist reference one shared invariant list, so they cannot drift.
- Bad, because a decision now costs two writes (the ADR plus the canonical-doc edit). Accepted: it is the same discipline the pipeline already imposes on data.

## Pros and cons of the options

### A dedicated `CONTRIBUTING.md`

- Good, because it is the conventional home a newcomer expects.
- Bad, because the audience is you + agents; agents reliably read `AGENTS.md`, and a second file is indirection with nothing enforced.

### Expand `AGENTS.md` inline

- Good, because everything is in one file agents already load.
- Bad, because it breaks "thin by design" and duplicates what GitHub, `ruff`, and the ADR ledger enforce or record natively.

### Split by artifact (chosen)

- Good, because single source of truth per rule, maximal mechanical enforcement, and structural consistency with the product's append-only model.
- Bad, because it is several small homes to keep pointed at each other, and two writes per decision.
