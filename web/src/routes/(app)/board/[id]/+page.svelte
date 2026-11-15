<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api } from '#lib/api';
  import AddSheet from '#lib/components/AddSheet.svelte';
  import Cover from '#lib/components/Cover.svelte';
  import Stars from '#lib/components/Stars.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Board, Entry } from '#lib/types';
  import { KIND_LABEL } from '#lib/types';

  const id = $derived(Number(page.params.id));
  let board = $state<Board | null>(null);
  let entries = $state<Entry[] | null>(null);
  let filter = $state<'all' | 'done' | 'want'>('all');
  let sort = $state<'recent' | 'rating' | 'title' | 'year'>('recent');
  let adding = $state(false);
  let editing = $state(false);
  let name = $state('');
  let hint = $state('');
  let colour = $state('#000000');

  async function load() {
    try {
      board = await api.get<Board>(`/api/boards/${id}`);
      const qs = new URLSearchParams({ sort });
      if (filter !== 'all') qs.set('state', filter);
      entries = await api.get<Entry[]>(`/api/boards/${id}/entries?${qs}`);
    } catch (e) {
      errorToast(e);
    }
  }
  $effect(() => { id; filter; sort; load(); });

  function startEdit() {
    if (!board) return;
    name = board.name;
    hint = board.custom_hint ?? '';
    colour = board.colour;
    editing = true;
  }

  async function saveEdit(e: SubmitEvent) {
    e.preventDefault();
    try {
      board = await api.patch<Board>(`/api/boards/${id}`, { name, colour, ...(board?.kind === 'custom' ? { custom_hint: hint } : {}) });
      editing = false;
    } catch (err) { errorToast(err); }
  }

  async function remove() {
    if (!board || !confirm(`Delete "${board.name}" and everything on it? This can't be undone.`)) return;
    try {
      await api.del(`/api/boards/${id}`);
      toast(`Deleted ${board.name}`);
      goto('/');
    } catch (err) { errorToast(err); }
  }

  async function toggle(e: Entry, ev: MouseEvent) {
    ev.preventDefault();
    ev.stopPropagation();
    const next = e.state === 'done' ? 'want' : 'done';
    try {
      await api.patch(`/api/entries/${e.entry_id}`, { state: next });
      load();
    } catch (err) { errorToast(err); }
  }
</script>

{#if board}
  <div class="page">
    <header class="row wrap" style:--c={board.colour}>
      <span class="dot" aria-hidden="true"></span>
      <h1>{board.name}</h1>
      <span class="badge">{KIND_LABEL[board.kind]}</span>
      <span class="spacer"></span>
      <button class="btn small" onclick={startEdit}>Edit</button>
      <button class="btn small primary" onclick={() => (adding = true)}>+ Add</button>
    </header>
    {#if board.kind === 'custom' && board.custom_hint}<p class="muted small">{board.custom_hint}</p>{/if}

    {#if editing}
      <form class="card edit" onsubmit={saveEdit}>
        <label for="n">Name</label><input id="n" type="text" bind:value={name} maxlength="60" required />
        {#if board.kind === 'custom'}<label for="h">What goes on this board?</label><input id="h" type="text" bind:value={hint} maxlength="200" />{/if}
        <label for="c">Colour</label><input id="c" type="color" bind:value={colour} />
        <div class="row">
          <button class="btn primary" type="submit">Save</button>
          <button class="btn" type="button" onclick={() => (editing = false)}>Cancel</button>
          <span class="spacer"></span>
          <button class="btn danger" type="button" onclick={remove}>Delete board</button>
        </div>
      </form>
    {/if}

    <div class="row controls">
      <div class="seg" role="group" aria-label="Filter">
        {#each [['all', 'All'], ['done', 'Done'], ['want', 'To try']] as [v, l]}
          <button class:on={filter === v} onclick={() => (filter = v as typeof filter)}>{l}</button>
        {/each}
      </div>
      <span class="spacer"></span>
      <select bind:value={sort} aria-label="Sort">
        <option value="recent">Recent</option><option value="rating">Rating</option>
        <option value="title">Title</option><option value="year">Year</option>
      </select>
    </div>

    {#if entries === null}
      <div class="grid">{#each Array(6) as _}<div class="skeleton" style="aspect-ratio: 2/3"></div>{/each}</div>
    {:else if entries.length === 0}
      <div class="empty">
        <p>Nothing here yet.</p>
        <button class="btn primary" onclick={() => (adding = true)}>Add your first</button>
      </div>
    {:else}
      <div class="grid">
        {#each entries as e (e.entry_id)}
          <a class="item" href={`/entry/${e.entry_id}`}>
            <Cover src={e.cover_url} title={e.title} colour={board.colour} />
            <div class="cap">
              <span class="t">{e.title}</span>
              {#if e.state === 'done'}
                <Stars value={e.rating} readonly size="0.85rem" />
              {:else}
                <span class="badge">to try</span>
              {/if}
              {#if !e.tagged}<span class="small muted">tagging…</span>{/if}
            </div>
            <button class="flip" title={e.state === 'done' ? 'Move to “to try”' : 'Mark done'} onclick={(ev) => toggle(e, ev)}>
              {e.state === 'done' ? '↺' : '✓'}
            </button>
          </a>
        {/each}
      </div>
    {/if}
  </div>
  <button class="fab btn primary" onclick={() => (adding = true)} aria-label="Add">+</button>
  {#if adding}
    <AddSheet {board} initialState={filter === 'want' ? 'want' : 'done'} onclose={() => (adding = false)}
      onsaved={() => { adding = false; load(); }} />
  {/if}
{/if}

<style>
  header h1 { margin: 0; }
  .dot { width: 14px; height: 14px; border-radius: 50%; background: var(--c); }
  .controls { margin: 0.75rem 0; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
  .seg button { min-height: 36px; padding: 0 0.8rem; border: 0; background: var(--surface); }
  .seg button.on { background: var(--accent); color: var(--accent-ink); }
  select { width: auto; min-height: 36px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 14px 10px; }
  @media (min-width: 900px) { .grid { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); } }
  .item { position: relative; color: var(--text); display: grid; gap: 4px; }
  .item:hover { text-decoration: none; }
  .cap { display: grid; gap: 2px; }
  .t { font-size: 0.85rem; font-weight: 600; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .flip { position: absolute; top: 4px; right: 4px; width: 30px; height: 30px; border-radius: 50%; border: 0; background: rgb(0 0 0 / 0.55); color: #fff; font-size: 0.9rem; }
  .edit { padding: 1rem; margin: 0.75rem 0; }
  .edit .row { margin-top: 1rem; }
  input[type='color'] { width: 60px; height: 40px; border: 1px solid var(--line); border-radius: 8px; background: none; }
  .fab { position: fixed; right: 18px; bottom: calc(var(--tabbar-h) + 18px + env(safe-area-inset-bottom)); width: 56px; height: 56px; border-radius: 50%; font-size: 1.8rem; padding: 0; box-shadow: var(--shadow); z-index: 40; }
  @media (min-width: 900px) { .fab { display: none; } }
</style>
