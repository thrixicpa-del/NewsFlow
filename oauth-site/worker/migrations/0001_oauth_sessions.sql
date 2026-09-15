CREATE TABLE IF NOT EXISTS oauth_sessions (
  id TEXT PRIMARY KEY NOT NULL,
  state_hash TEXT NOT NULL UNIQUE,
  poll_capability_hash TEXT NOT NULL,
  profile_id TEXT NOT NULL,
  include_monetary INTEGER NOT NULL,
  code_verifier_encrypted TEXT NOT NULL,
  credentials_encrypted TEXT,
  status TEXT NOT NULL,
  diagnostic_id TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS oauth_sessions_expires_at_idx ON oauth_sessions(expires_at);
