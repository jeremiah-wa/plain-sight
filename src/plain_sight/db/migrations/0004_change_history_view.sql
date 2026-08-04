-- Change-history view: a per-member *timeline* over the event log, the full
-- chronological record of what was acquired and divested and when. Where the
-- state views of 0003 answer a point-in-time question ("what did the member hold
-- as of date D"), this answers the timeline question: the sequence of changes
-- across a member's declarations. A view over the log, never a stored snapshot,
-- so it can never drift from the events. Applies on top of 0003.
--
-- The defining difference from `active_interest`: this view does NOT filter on
-- `superseded_by IS NULL`. A superseded event stays *visible* here, carrying the
-- `superseded_by` pointer as its marker, so the record of a later correction is
-- part of the history rather than erased by it. That is the whole point of a
-- change history: a reader must see that a fact was declared, then corrected.
--
-- Both time axes (see docs/GLOSSARY.md, "Bitemporal") are surfaced per row:
--
--   * valid time (the `validity` daterange): `lower(validity)` is when the
--     interest was acquired, `upper(validity)` when it was divested (NULL upper =
--     still held). One row is one holding period, both endpoints in view.
--   * record time (the discrete stamps `ingested_at`, `verified_at`,
--     `fetch_timestamp`): when the fact entered / was confirmed in the record.
--
-- No ordering is baked into the view (SQL views are unordered sets); callers
-- impose the timeline order at query time. See PostgresRepository.
CREATE VIEW member_change_history AS
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
    c.raw_string       AS counterparty_raw_string,
    c.normalised_label AS counterparty_normalised_label,
    c.resolved         AS counterparty_resolved
FROM declaration_event de
JOIN counterparty c ON c.id = de.counterparty_id;
