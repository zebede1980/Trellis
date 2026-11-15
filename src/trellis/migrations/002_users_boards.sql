CREATE TABLE app_user (
  user_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  pw_hash TEXT NOT NULL,
  display_name TEXT,
  is_admin INTEGER NOT NULL DEFAULT 0,
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE board (
  board_id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES app_user ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('book','film','tv','game','music','custom')),
  custom_hint TEXT,
  colour TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_board_user ON board(user_id, sort_order);
