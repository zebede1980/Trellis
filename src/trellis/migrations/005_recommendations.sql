CREATE TABLE rec_run (
  run_id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES app_user ON DELETE CASCADE,
  scope TEXT NOT NULL,            -- JSON: {"mode":"all"|"trait"|"board"|"explore","trait_id":..,"board_id":..}
  model TEXT,
  status TEXT NOT NULL,
  stats TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX ix_rec_run_user ON rec_run(user_id, started_at);

CREATE TABLE suggestion (
  suggestion_id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES app_user ON DELETE CASCADE,
  work_id INTEGER NOT NULL REFERENCES work,
  board_id INTEGER NOT NULL REFERENCES board ON DELETE CASCADE,
  run_id INTEGER REFERENCES rec_run ON DELETE SET NULL,
  reason TEXT NOT NULL,
  score REAL NOT NULL,
  is_new_branch INTEGER NOT NULL DEFAULT 0,
  new_branch_trait_id INTEGER REFERENCES trait,
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','want','dismissed','done')),
  dismiss_reason TEXT,
  created_at TEXT NOT NULL,
  acted_at TEXT,
  UNIQUE (user_id, work_id)
);
CREATE INDEX ix_suggestion_user_status ON suggestion(user_id, status);
CREATE INDEX ix_suggestion_board ON suggestion(board_id);

CREATE TABLE suggestion_trait (
  suggestion_id INTEGER NOT NULL REFERENCES suggestion ON DELETE CASCADE,
  trait_id INTEGER NOT NULL REFERENCES trait,
  PRIMARY KEY (suggestion_id, trait_id)
);
CREATE INDEX ix_suggestion_trait_trait ON suggestion_trait(trait_id);

CREATE TABLE suggestion_source (
  suggestion_id INTEGER NOT NULL REFERENCES suggestion ON DELETE CASCADE,
  entry_id INTEGER NOT NULL REFERENCES entry ON DELETE CASCADE,
  PRIMARY KEY (suggestion_id, entry_id)
);
