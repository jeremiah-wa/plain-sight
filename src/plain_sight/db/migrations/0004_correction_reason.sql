-- Correction reason: the who/why/when of an operator correction, captured on the
-- *superseding* event so the append-only log carries the justification for every
-- change. A correction (see docs/GLOSSARY.md and migration 0002) appends a new
-- event that supersedes a prior one; this column records why. It is NULL on
-- machine candidates and on confirmed-as-is events, which correct nothing.
--
-- The correction actor and timestamp reuse the existing `verified_by` /
-- `verified_at` columns: a correction is a confirmation with edits, so the person
-- and moment that settled the claim are the person and moment that corrected it.
-- Only the reason needs a new column. Applies on top of 0003.

ALTER TABLE declaration_event
    ADD COLUMN correction_reason text;

-- Recreate the bitemporal views so the current version of a record carries its
-- supersession pointer and correction reason too. `active_interest` already
-- filters to `superseded_by IS NULL`, so the pointer is always NULL here; it is
-- exposed only to keep every row that crosses back into the application uniform
-- (one row shape, one mapper). `correction_reason` is meaningful: a *current*
-- corrected interest is the superseding event, and it carries its own reason.
-- `current_interest` depends on `active_interest`, so both are dropped and rebuilt.
DROP VIEW current_interest;
DROP VIEW active_interest;

CREATE VIEW active_interest AS
SELECT
    de.id,
    de.member_id,
    de.counterparty_id,
    de.category,
    de.description,
    de.validity,
    de.document_id,
    de.page,
    de.extraction_method,
    de.extraction_confidence,
    de.fetch_timestamp,
    de.bbox,
    de.verification_status,
    de.verified_by,
    de.verified_at,
    de.ingested_at,
    de.superseded_by,
    de.correction_reason,
    c.raw_string       AS counterparty_raw_string,
    c.normalised_label AS counterparty_normalised_label,
    c.resolved         AS counterparty_resolved
FROM declaration_event de
JOIN counterparty c ON c.id = de.counterparty_id
WHERE de.superseded_by IS NULL;

CREATE VIEW current_interest AS
SELECT * FROM active_interest
WHERE validity @> CURRENT_DATE;
