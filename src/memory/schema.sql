-- Memory schema for Autonomous Red Teaming.
--
-- Design note: every row that can enter model context carries authorization_id
-- so retrieval can be scoped to the current engagement. A finding from target X
-- must never leak into target Y's context (fail-closed isolation).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Append-only event log for a single engagement (episodic memory).
CREATE TABLE IF NOT EXISTS episodic_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id    TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    ts               TEXT NOT NULL,                    -- ISO-8601 UTC
    event_type       TEXT NOT NULL,                    -- action|decision|observation|tool_output|finding|note
    salience         TEXT NOT NULL DEFAULT 'salient',  -- ephemeral|salient|pinned
    content          TEXT NOT NULL,
    content_hash     TEXT NOT NULL,
    token_cost       INTEGER NOT NULL DEFAULT 0,
    evidence_ref     INTEGER,                          -- -> evidence_refs.id
    FOREIGN KEY (evidence_ref) REFERENCES evidence_refs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_episodic_engagement   ON episodic_events(engagement_id);
CREATE INDEX IF NOT EXISTS idx_episodic_auth         ON episodic_events(authorization_id);
CREATE INDEX IF NOT EXISTS idx_episodic_hash         ON episodic_events(content_hash);
CREATE INDEX IF NOT EXISTS idx_episodic_salience_ts  ON episodic_events(salience, ts);

-- Durable, cross-session knowledge (semantic memory): skills, findings, patterns.
-- authorization_id is NULL for globally reusable items (e.g. generic skills) and
-- REQUIRED for target-specific items (findings, target profiles).
CREATE TABLE IF NOT EXISTS semantic_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT NOT NULL,                    -- skill|finding|pattern|target_profile
    authorization_id TEXT,                             -- NULL => global/reusable
    external_id      TEXT,                             -- e.g. "web.missing_security_headers"
    title            TEXT NOT NULL,
    content          TEXT NOT NULL,                    -- JSON payload
    content_hash     TEXT NOT NULL,
    tags             TEXT NOT NULL DEFAULT '[]',
    source           TEXT NOT NULL DEFAULT 'manual-seed',  -- manual-seed|distilled|imported
    status           TEXT NOT NULL DEFAULT 'active',        -- active|superseded|pending_review
    embedding        BLOB,                             -- reserved for sqlite-vec (semantic dedup, phase 2)
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_semantic_auth ON semantic_items(authorization_id);
CREATE INDEX IF NOT EXISTS idx_semantic_kind ON semantic_items(kind);
CREATE INDEX IF NOT EXISTS idx_semantic_hash ON semantic_items(content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_semantic_external
    ON semantic_items(kind, external_id) WHERE external_id IS NOT NULL;

-- Exact-dedup registry: normalized content hash -> first occurrence.
CREATE TABLE IF NOT EXISTS dedup_hashes (
    content_hash TEXT NOT NULL,
    scope        TEXT NOT NULL,                        -- episodic|semantic
    ref_id       INTEGER,
    first_seen   TEXT NOT NULL,
    hit_count    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (content_hash, scope)
);

-- Pointers to raw evidence blobs kept on disk (never loaded into context).
CREATE TABLE IF NOT EXISTS evidence_refs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id    TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    path             TEXT NOT NULL,
    sha256           TEXT NOT NULL,
    media_type       TEXT,
    bytes            INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_engagement ON evidence_refs(engagement_id);
