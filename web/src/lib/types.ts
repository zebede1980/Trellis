export type Kind = 'book' | 'film' | 'tv' | 'game' | 'music' | 'custom';

export interface User {
  user_id: number;
  username: string;
  display_name: string;
  is_admin: boolean;
}

export interface Board {
  board_id: number;
  name: string;
  kind: Kind;
  custom_hint: string | null;
  colour: string;
  sort_order: number;
  n_done?: number;
  n_want?: number;
  cover_url?: string | null;
}

export interface Candidate {
  source: string;
  source_id: string;
  title: string;
  creators: string[];
  year: number | null;
  cover_url: string | null;
  url: string | null;
  verified: boolean;
  blurb?: string | null;
}

export interface Trait {
  trait_id: number;
  slug: string;
  name: string;
  facet: string;
  weight?: number;
}

export interface Entry {
  entry_id: number;
  board_id: number;
  work_id: number;
  state: 'done' | 'want';
  rating: number | null;
  note: string | null;
  consumed_on: string | null;
  created_at: string;
  updated_at: string;
  title: string;
  creators: string[];
  year: number | null;
  cover_url: string | null;
  summary?: string | null;
  url: string | null;
  source: string;
  verified: boolean;
  kind: Kind;
  tagged: boolean;
  traits?: Trait[];
  board_name?: string;
  board_colour?: string;
}

export const KIND_LABEL: Record<Kind, string> = {
  book: 'Books', film: 'Films', tv: 'TV', game: 'Games', music: 'Music', custom: 'Custom'
};
export const KIND_NOUN: Record<Kind, string> = {
  book: 'book', film: 'film', tv: 'series', game: 'game', music: 'album', custom: 'thing'
};

export interface TreeEntry {
  entry_id: number;
  work_id: number;
  title: string;
  year: number | null;
  creators: string[];
  cover_url: string | null;
  state: 'done' | 'want';
  rating: number | null;
  note: string | null;
  board_id: number;
  board_name: string;
  board_colour: string;
  kind: Kind;
}

export interface Suggestion {
  suggestion_id: number;
  work_id: number;
  title: string;
  year: number | null;
  creators: string[];
  cover_url: string | null;
  reason: string;
  score: number;
  board_id: number;
  board_name: string;
  board_colour: string;
  kind: Kind;
  url: string | null;
  verified: boolean;
  is_new_branch: boolean;
  traits?: { trait_id: number; name: string; facet: string }[];
  sources?: { entry_id: number; title: string }[];
  new_branch?: { trait_id: number; name: string; facet: string; description: string | null } | null;
  status?: string;
}

export interface Branch {
  id: string;
  name: string;
  trait_id?: number;
  board_id?: number;
  facet?: string;
  description?: string | null;
  colour?: string;
  affinity?: number;
  n?: number;
  new_branch?: boolean;
  entries: number[];
  suggestions: number[];
}

export interface Tree {
  group: 'theme' | 'board';
  branches: Branch[];
  other: number[];
  entries: Record<string, TreeEntry>;
  suggestions: Record<string, Suggestion>;
  boards: { board_id: number; name: string; kind: Kind; colour: string }[];
}

export type Selection =
  | { type: 'entry'; id: number }
  | { type: 'suggestion'; id: number }
  | { type: 'theme'; branch: Branch }
  | null;
