# Architecture Decision Records

This is the append-only ledger of **why** things changed. The PRD and
`ARCHITECTURE.md` describe the current state (the "SQL views"); each record here
is the immutable, dated account of a decision that changed it (the "event log").
It is the doc-level twin of the product's own append-only supersession model.

## When to write one

Only when a change **reverses or materially alters** a product invariant or a
PRD/architecture commitment, the kind of thing where future-you asks "wait, why
did we change this?". Pure additions and clarifications are just doc edits, not
ADRs. (See the Workflow section of [`AGENTS.md`](../../AGENTS.md).)

## How

- Copy [`template.md`](template.md) to `NNNN-slug.md`, zero-padded, next number in sequence.
- Format is [MADR](https://adr.github.io/madr/). Fill the sections; delete none.
- **Also edit the canonical doc** (PRD / `ARCHITECTURE.md`) to reflect the new
  current state, and link it back here (`see ADR-NNNN`).
- Records are **append-only**. Never edit an `Accepted` record to reverse it.
  Write a new record that supersedes it, and set the old one's status to
  `Superseded by ADR-NNNN`.

| Status | Meaning |
|---|---|
| `Accepted` | In force. |
| `Superseded by ADR-NNNN` | Replaced; retained for the audit trail, never deleted. |
