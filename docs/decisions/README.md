# Architecture Decision Records

This is the append-only ledger of **why** things changed. The PRD and
`ARCHITECTURE.md` describe the current state (the "SQL views"); each record here
is the dated account of a decision that changed it (the "event log"). It is the
doc-level twin of the product's own append-only supersession model, down to where
the append-only property starts: a record is a draft until it merges to `main`,
and immutable from that point on. Corrections after that supersede, they never
overwrite. See [How](#how).

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
- Records are **immutable once merged to `main`**. To change what a merged record
  says, write a new record that supersedes it, and set the old one's status to
  `Superseded by ADR-NNNN`. Until it lands on `main` it is a draft on its own
  branch: edit it freely, `Status` included. Immutability keys off the merge, not
  off the `Status` field, because nothing outside the branch has read it yet.

| Status | Meaning |
|---|---|
| `Accepted` | In force. |
| `Superseded by ADR-NNNN` | Replaced; retained for the audit trail, never deleted. |
