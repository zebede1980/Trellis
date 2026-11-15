<script lang="ts">
  import { api, ApiError } from '#lib/api';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Board, Candidate, Entry } from '#lib/types';
  import { KIND_NOUN } from '#lib/types';
  import Cover from './Cover.svelte';
  import Stars from './Stars.svelte';

  type Cand = Candidate & { have: { entry_id: number; state: string } | null };

  let { board, onclose, onsaved, initialState = 'done' }: {
    board: Board; onclose: () => void; onsaved: (e: Entry) => void; initialState?: 'done' | 'want';
  } = $props();

  const custom = $derived(board.kind === 'custom');
  let q = $state('');
  let results = $state<Cand[] | null>(null);
  let searching = $state(false);
  let searchError = $state('');
  let picked = $state<Cand | null>(null);
  let manual = $state(false);
  let entryState = $state<'done' | 'want'>((() => initialState)());
  let rating = $state<number | null>(null);
  let note = $state('');
  let consumed = $state('');
  let saving = $state(false);
  let mTitle = $state('');
  let mCreator = $state('');
  let mYear = $state('');
  let seq = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let input: HTMLInputElement | undefined = $state();

  $effect(() => { input?.focus(); });

  async function search() {
    const term = q.trim();
    if (term.length < 2) { results = null; return; }
    const my = ++seq;
    searching = true;
    searchError = '';
    try {
      const r = await api.get<Cand[]>(`/api/lookup?board_id=${board.board_id}&q=${encodeURIComponent(term)}`);
      if (my === seq) results = r;
    } catch (e) {
      if (my === seq) searchError = e instanceof Error ? e.message : String(e);
    } finally {
      if (my === seq) searching = false;
    }
  }

  function onInput() {
    if (custom) return;   // AI lookups cost money: search on Enter / button only
    clearTimeout(timer);
    timer = setTimeout(search, 350);
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); search(); }
  }

  function pick(c: Cand) {
    if (c.have) { toast('Already on your boards'); return; }
    picked = c;
    manual = false;
  }

  function startManual() {
    manual = true;
    picked = null;
    mTitle = q.trim();
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    saving = true;
    const body: Record<string, unknown> = {
      board_id: board.board_id, state: entryState, rating: entryState === 'done' ? rating : null,
      note: note.trim() || null, consumed_on: consumed || null
    };
    if (manual) {
      body.manual = { title: mTitle.trim(), creators: mCreator.trim() ? [mCreator.trim()] : [], year: mYear ? Number(mYear) : null };
    } else if (picked) {
      body.source = picked.source;
      body.source_id = picked.source_id;
    }
    try {
      const entry = await api.post<Entry>('/api/entries', body);
      toast(entryState === 'done' ? `Added ${entry.title}` : `${entry.title} saved to try`);
      onsaved(entry);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) toast('Already on your boards');
      else errorToast(err);
    } finally {
      saving = false;
    }
  }
</script>

<div class="backdrop" role="presentation" onclick={onclose}></div>
<div class="sheet card" role="dialog" aria-modal="true" aria-label={`Add to ${board.name}`}>
  <header class="row">
    <strong>Add to {board.name}</strong>
    <span class="spacer"></span>
    <button class="btn ghost small" onclick={onclose} aria-label="Close">✕</button>
  </header>

  {#if !picked && !manual}
    <div class="row">
      <input bind:this={input} type="search" bind:value={q} oninput={onInput} onkeydown={onKey}
        placeholder={custom ? `Search for a ${board.custom_hint ?? 'thing'}…` : `Search for a ${KIND_NOUN[board.kind]}…`}
        autocomplete="off" enterkeyhint="search" />
      {#if custom}<button class="btn primary" onclick={search} disabled={searching || q.trim().length < 2}>Search</button>{/if}
    </div>
    {#if searching}
      <div class="list">{#each Array(3) as _}<div class="cand"><div class="skeleton thumb"></div><div class="skeleton line"></div></div>{/each}</div>
    {:else if searchError}
      <p class="muted">{searchError}</p>
    {:else if results}
      <div class="list">
        {#each results as c (c.source + c.source_id)}
          <button class="cand" onclick={() => pick(c)} class:have={!!c.have}>
            <div class="thumb"><Cover src={c.cover_url} title={c.title} colour={board.colour} /></div>
            <div class="meta">
              <strong>{c.title}</strong>
              <span class="small muted">{[c.creators.join(', '), c.year].filter(Boolean).join(' · ')}</span>
              {#if c.blurb}<span class="small muted blurb">{c.blurb}</span>{/if}
              <span class="row wrap">
                {#if c.have}<span class="badge">on your {c.have.state === 'want' ? 'to-try list' : 'board'}</span>{/if}
                {#if !c.verified}<span class="badge">unverified</span>{/if}
              </span>
            </div>
          </button>
        {:else}
          <p class="muted">Nothing found.</p>
        {/each}
      </div>
    {/if}
    {#if custom && (results || q.trim().length > 1)}
      <button class="btn small ghost manual" onclick={startManual}>+ Add exactly “{q.trim()}”</button>
    {/if}
  {:else}
    <form onsubmit={save}>
      {#if picked}
        <div class="chosen">
          <div class="thumb big"><Cover src={picked.cover_url} title={picked.title} colour={board.colour} /></div>
          <div>
            <strong>{picked.title}</strong>
            <div class="small muted">{[picked.creators.join(', '), picked.year].filter(Boolean).join(' · ')}</div>
            <button type="button" class="btn small ghost" onclick={() => (picked = null)}>Change</button>
          </div>
        </div>
      {:else}
        <label for="mt">Title</label>
        <input id="mt" type="text" bind:value={mTitle} required maxlength="200" />
        <div class="row">
          <div class="spacer"><label for="mc">By (optional)</label><input id="mc" type="text" bind:value={mCreator} maxlength="100" /></div>
          <div style="width: 7rem"><label for="my">Year</label><input id="my" type="text" inputmode="numeric" pattern={'[0-9]{4}'} bind:value={mYear} /></div>
        </div>
        <button type="button" class="btn small ghost" onclick={() => (manual = false)}>Back to search</button>
      {/if}

      <div class="seg" role="group" aria-label="State">
        <button type="button" class:on={entryState === 'done'} onclick={() => (entryState = 'done')}>Done it</button>
        <button type="button" class:on={entryState === 'want'} onclick={() => (entryState = 'want')}>Want to try</button>
      </div>

      {#if entryState === 'done'}
        <Stars bind:value={rating} />
        <label for="note">What did you think?</label>
        <textarea id="note" bind:value={note} maxlength="4000" placeholder="What worked, what didn't. This shapes your suggestions."></textarea>
        <label for="when">When (optional)</label>
        <input id="when" type="date" bind:value={consumed} />
      {:else}
        <label for="note2">Why does it appeal? (optional)</label>
        <textarea id="note2" bind:value={note} maxlength="4000"></textarea>
      {/if}
      <button class="btn primary save" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </form>
  {/if}
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); z-index: 60; }
  .sheet { position: fixed; z-index: 61; left: 0; right: 0; bottom: 0; max-height: 92dvh; overflow-y: auto; border-radius: 16px 16px 0 0; padding: 1rem 1rem calc(1rem + env(safe-area-inset-bottom)); }
  @media (min-width: 700px) { .sheet { left: 50%; top: 8vh; bottom: auto; transform: translateX(-50%); width: 560px; border-radius: 16px; max-height: 84vh; } }
  header { margin-bottom: 0.75rem; }
  .list { display: grid; gap: 6px; margin-top: 0.75rem; }
  .cand { display: grid; grid-template-columns: 52px 1fr; gap: 0.75rem; text-align: left; padding: 0.5rem; border-radius: 10px; border: 1px solid transparent; background: none; align-items: start; }
  .cand:hover, .cand:focus-visible { background: var(--surface-2); border-color: var(--line); }
  .cand.have { opacity: 0.6; }
  .thumb { width: 52px; }
  .thumb.big { width: 90px; }
  .skeleton.thumb { height: 78px; }
  .skeleton.line { height: 1.2rem; width: 70%; }
  .meta { display: grid; gap: 2px; }
  .blurb { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .chosen { display: grid; grid-template-columns: 90px 1fr; gap: 1rem; align-items: start; margin-bottom: 0.5rem; }
  .seg { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin: 1rem 0 0.75rem; }
  .seg button { min-height: 42px; border: 0; background: var(--surface); }
  .seg button.on { background: var(--accent); color: var(--accent-ink); font-weight: 600; }
  .save { width: 100%; margin-top: 1rem; }
  .manual { margin-top: 0.5rem; }
</style>
