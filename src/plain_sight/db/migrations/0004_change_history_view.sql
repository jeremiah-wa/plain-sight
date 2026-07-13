-- Change-history view: the full chronological record of a member's declarations,
-- reconstructed from the event log. Where 0003's views answer a point-in-time
-- question ("what did the member hold as of date D") by returning only the current
-- version of each record, this answers the *timeline* question: the sequence of
-- changes (acquisitions, divestments, and the corrections that supersede them).
-- Applies on top of 0003.
--
-- The defining difference from `active_interest` is that this view keeps every
-- version, superseded ones included. A correction appends a superseding event and
-- marks its predecessor superseded; 0003's views drop that predecessor, but here it
-- is retained and flagged, so the history is a complete, auditable trail that never
-- silently loses a fact.
--
-- Both bitemporal axes are surfaced on each row (see docs/GLOSSARY.md, "Bitemporal"):
--
--   * valid time (the `validity` daterange): when the interest was actually held,
--     i.e. when it was acquired and (if closed) divested.
--   * record time (`ingested_at`): when the fact entered the record. Ordering the
--     history by record time reproduces the chronological sequence in which the
--     register's declarations and corrections were learned.
--
-- `superseded` is a derived marker, not a filter: callers order by record time and
-- read the flag, so a superseded original stays in the timeline alongside the
-- correction that replaced it.
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
    (de.superseded_by IS NOT NULL) AS superseded,
    c.raw_string       AS counterparty_raw_string,
    c.normalised_label AS counterparty_normalised_label,
    c.resolved         AS counterparty_resolved
FROM declaration_event de
JOIN counterparty c ON c.id = de.counterparty_id;
