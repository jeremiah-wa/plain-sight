-- Walking-skeleton schema: the minimal system of record for one member,
-- end to end. Hand-authored (no ORM, no autogenerate). Later slices grow this:
-- valid_from/valid_to are plain columns here, to become bitemporal range types
-- with EXCLUDE USING GIST constraints; counterparty gains an embedding; etc.
--
-- Every primary key is an opaque UUID supplied by the application. There are no
-- sequential, publicly enumerable ids.

CREATE TABLE person (
    id             uuid PRIMARY KEY,
    canonical_name text NOT NULL,
    name_variants  text[] NOT NULL DEFAULT '{}',
    external_ids   jsonb NOT NULL DEFAULT '{}',
    chamber        text,
    jurisdiction   text NOT NULL DEFAULT 'AU:federal'
);

-- Hard resolution: one canonical member per name in the skeleton.
CREATE UNIQUE INDEX person_canonical_name_key ON person (canonical_name);

-- The immutable source PDF: the provenance anchor. Content-addressed by hash.
CREATE TABLE source_document (
    id             uuid PRIMARY KEY,
    member_id      uuid NOT NULL REFERENCES person (id),
    content_sha256 text NOT NULL,
    storage_path   text NOT NULL,
    page_count     integer NOT NULL,
    source_url     text,
    fetched_at     timestamptz NOT NULL,
    jurisdiction   text NOT NULL DEFAULT 'AU:federal'
);

CREATE UNIQUE INDEX source_document_content_sha256_key ON source_document (content_sha256);

-- A declared company/trust/asset: a first-class, explicitly-provisional entity.
-- Referenced by declaration_event.counterparty_id, never inlined as a string.
CREATE TABLE counterparty (
    id               uuid PRIMARY KEY,
    raw_string       text NOT NULL,
    normalised_label text NOT NULL,
    resolved         boolean NOT NULL DEFAULT false
);

-- The atomic unit of record. Immutable claim content; verification is a state
-- transition on the row. Provenance is per claim, carried inline here.
CREATE TABLE declaration_event (
    id                    uuid PRIMARY KEY,
    member_id             uuid NOT NULL REFERENCES person (id),
    counterparty_id       uuid NOT NULL REFERENCES counterparty (id),
    category              text NOT NULL,
    description           text,
    valid_from            date,
    valid_to              date,
    -- per-claim provenance ------------------------------------------------
    document_id           uuid NOT NULL REFERENCES source_document (id),
    page                  integer NOT NULL,
    extraction_method     text NOT NULL,
    extraction_confidence double precision NOT NULL,
    fetch_timestamp       timestamptz NOT NULL,
    bbox                  double precision[],
    -- verification --------------------------------------------------------
    verification_status   text NOT NULL DEFAULT 'pending',
    verified_by           text,
    verified_at           timestamptz,
    ingested_at           timestamptz NOT NULL,
    CONSTRAINT declaration_event_verification_status_check
        CHECK (verification_status IN ('pending', 'verified'))
);

CREATE INDEX declaration_event_member_id_idx ON declaration_event (member_id);
