-- Shared vocabulary of themes.
CREATE TABLE trait (
  trait_id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  facet TEXT NOT NULL CHECK (facet IN ('theme','tone','setting','style','genre','medium')),
  description TEXT,
  merged_into_id INTEGER REFERENCES trait,
  created_at TEXT NOT NULL
);

CREATE TABLE work_trait (
  work_id INTEGER NOT NULL REFERENCES work ON DELETE CASCADE,
  trait_id INTEGER NOT NULL REFERENCES trait,
  weight REAL NOT NULL,
  PRIMARY KEY (work_id, trait_id)
);
CREATE INDEX ix_work_trait_trait ON work_trait(trait_id);

CREATE TABLE job (
  job_id INTEGER PRIMARY KEY,
  user_id INTEGER,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  result TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX ix_job_status ON job(status, job_id);
CREATE INDEX ix_job_user ON job(user_id, job_id);

CREATE TABLE llm_call (
  call_id INTEGER PRIMARY KEY,
  user_id INTEGER,
  purpose TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  duration_ms INTEGER,
  ok INTEGER NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_llm_call_created ON llm_call(created_at);
