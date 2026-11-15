-- Shared across users: the canonical thing, fetched once.
CREATE TABLE work (
  work_id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,          -- openlibrary | tmdb | igdb | musicbrainz | tvmaze | wikidata | ai | manual
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  creators TEXT,                 -- JSON array of names
  year INTEGER,
  cover_url TEXT,
  summary TEXT,
  url TEXT,
  raw_tags TEXT,                 -- JSON array: genres/keywords/subjects straight from the catalogue
  verified INTEGER NOT NULL DEFAULT 1,
  tagged_at TEXT,
  fetched_at TEXT NOT NULL,
  UNIQUE (source, source_id)
);
CREATE INDEX ix_work_kind_title ON work(kind, title);

CREATE TABLE entry (
  entry_id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES app_user ON DELETE CASCADE,
  board_id INTEGER NOT NULL REFERENCES board ON DELETE CASCADE,
  work_id INTEGER NOT NULL REFERENCES work,
  state TEXT NOT NULL CHECK (state IN ('done','want')),
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  note TEXT,
  consumed_on TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (user_id, work_id)
);
CREATE INDEX ix_entry_user_board ON entry(user_id, board_id);
CREATE INDEX ix_entry_board ON entry(board_id);
CREATE INDEX ix_entry_work ON entry(work_id);
