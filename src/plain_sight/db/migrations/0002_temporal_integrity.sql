-- Bitemporal integrity: make overlapping validity for the same member + interest
-- impossible at the database level, not merely discouraged in application code.
--
-- Migrates the walking skeleton's plain `valid_from`/`valid_to` date columns to a
-- single half-open `daterange` and adds an `EXCLUDE USING GIST` constraint that
-- rejects two *active* declaration events claiming overlapping validity for the
-- same (member, counterparty, category). Hand-authored and versioned: an ORM's
-- autogenerate cannot see GIST exclusion constraints. Applies on top of 0001.

-- Scope: this migration ranges *valid time* only. Record time stays as the
-- discrete `timestamptz` stamps the skeleton already carries (`ingested_at`,
-- `verified_at`, `fetch_timestamp`): they are points at which facts entered the
-- record, not intervals, and no query yet asks "as the record stood at time T".
-- A `tstzrange` record axis is only appropriate once system-time "as of" views
-- exist, and is added then rather than left unused now.

-- `=` on uuid/text columns inside a GIST index (needed to key the exclusion on
-- member + interest identity alongside the range `&&`) is provided by btree_gist.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Supersession pointer, per docs/GLOSSARY.md: a correction is a *new* event that
-- supersedes a prior one; the prior version is retained and marked superseded,
-- never deleted. NULL means active/current; non-NULL points at the successor that
-- replaced this row. Only active rows participate in the overlap constraint.
ALTER TABLE declaration_event
    ADD COLUMN superseded_by uuid REFERENCES declaration_event (id);

-- Valid time becomes one half-open `[from, to)` range. Half-open is what makes
-- adjacency non-overlapping: `[2020-01-01, 2021-01-01)` and
-- `[2021-01-01, 2022-01-01)` meet without overlapping, so a continuous holding
-- recorded as consecutive periods is accepted. NULL bounds are unbounded
-- (open-ended validity); two fully-unbounded ranges cover all time and overlap.
ALTER TABLE declaration_event
    ADD COLUMN validity daterange;

UPDATE declaration_event
    SET validity = daterange(valid_from, valid_to, '[)');

ALTER TABLE declaration_event DROP COLUMN valid_from;
ALTER TABLE declaration_event DROP COLUMN valid_to;

-- The temporal integrity constraint. Partial on `superseded_by IS NULL` so a
-- superseded prior version never blocks the event that supersedes it.
--
-- DEFERRABLE INITIALLY IMMEDIATE: overlaps are rejected the instant they are
-- written in normal operation (zero change to the common path), but the
-- append-only supersession pattern the PRD mandates (corrections are new
-- superseding events, never edits) needs to append a successor and mark its
-- predecessor superseded in one atomic transaction, and a correction usually
-- overlaps the version it corrects. Such a transaction runs `SET CONSTRAINTS
-- ... DEFERRED` so the check runs once at commit, by which point exactly one of
-- the pair is active. The constraint's shape is fixed here rather than
-- retrofitted, because the bitemporal schema is expensive to change later.
ALTER TABLE declaration_event
    ADD CONSTRAINT declaration_event_no_active_overlap
    EXCLUDE USING gist (
        member_id WITH =,
        counterparty_id WITH =,
        category WITH =,
        validity WITH &&
    )
    WHERE (superseded_by IS NULL)
    DEFERRABLE INITIALLY IMMEDIATE;
