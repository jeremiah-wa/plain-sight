-- Bitemporal query views: reconstruct queryable state from the append-only event
-- log. These are *views over the log*, never stored or materialised snapshots, so
-- history is always derived from events and can never drift from them. Hand-
-- authored and versioned, because an ORM's autogenerate cannot see views (nor the
-- range containment they lean on). Applies on top of 0002.
--
-- Two independent time axes meet here (see docs/GLOSSARY.md, "Bitemporal"):
--
--   * record time (supersession). `superseded_by IS NULL` selects the *current
--     version* of the record. A correction appends a superseding event and marks
--     its predecessor superseded; the predecessor is retained but drops out of
--     these views, so a superseded event is invisible to reconstructed state.
--   * valid time (the `validity` daterange): when the interest was actually
--     held. Slicing it by a date answers "what did the member hold as of date D".
--
-- Record time is not yet a range (0002 keeps it as discrete stamps), so there is
-- no "as the record stood at time T" travel yet: these views read the best-known
-- truth (all corrections applied) and travel only along valid time. That is
-- exactly what the PRD asks of "state as of date D": it is driven by the
-- register's effective (valid-time) dates.

-- The base view: every member's *current version of the record*, one row per
-- active (non-superseded) declaration event, joined to the counterparty it names.
-- Both query shapes below are valid-time slices of this. Verification status is
-- carried through as a column, not filtered here: these views reconstruct temporal
-- state, and the verified-only rule is enforced downstream at the publish gate,
-- not conflated into the temporal seam.
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
    c.raw_string       AS counterparty_raw_string,
    c.normalised_label AS counterparty_normalised_label,
    c.resolved         AS counterparty_resolved
FROM declaration_event de
JOIN counterparty c ON c.id = de.counterparty_id
WHERE de.superseded_by IS NULL;

-- Current state: the active interests a member holds *now*. The valid-time slice
-- at today's date. `daterange @> date` is element containment; an open-ended
-- (unbounded-upper) holding contains every future date and so stays current until
-- an alteration closes its period. "State as of date D" is the same slice at an
-- arbitrary D, expressed at query time as `active_interest WHERE validity @> D`.
CREATE VIEW current_interest AS
SELECT * FROM active_interest
WHERE validity @> CURRENT_DATE;
