<script lang="ts">
  import { api } from '#lib/api';
  import { errorToast, toast } from '#lib/toast.svelte';
  import { session } from '#lib/session.svelte';
  import type { Board, Kind } from '#lib/types';
  import { KIND_LABEL } from '#lib/types';

  let boards = $state<Board[] | null>(null);
  let showNew = $state(false);
  let name = $state('');
  let kind = $state<Kind>('custom');
  let hint = $state('');

  async function load() {
    try {
      boards = await api.get<Board[]>('/api/boards');
    } catch (e) {
      errorToast(e);
    }
  }
  $effect(() => { load(); });

  async function create(e: SubmitEvent) {
    e.preventDefault();
    try {
      await api.post('/api/boards', { name, kind, custom_hint: kind === 'custom' ? hint : null });
      toast(`Created ${name}`);
      name = hint = '';
      showNew = false;
      load();
    } catch (err) {
      errorToast(err);
    }
  }
</script>

<div class="page">
  <header class="row">
    <h1>Hi {session.user?.display_name}</h1>
    <span class="spacer"></span>
    <button class="btn small" onclick={() => (showNew = !showNew)}>{showNew ? 'Cancel' : '+ Board'}</button>
  </header>

  {#if showNew}
    <form class="card newboard" onsubmit={create}>
      <label for="bn">Name</label>
      <input id="bn" type="text" bind:value={name} maxlength="60" required placeholder="e.g. Board games" />
      <label for="bk">Kind</label>
      <select id="bk" bind:value={kind}>
        {#each Object.entries(KIND_LABEL) as [k, l]}<option value={k}>{l}{k === 'custom' ? ' (anything else)' : ''}</option>{/each}
      </select>
      {#if kind === 'custom'}
        <label for="bh">What goes on this board?</label>
        <input id="bh" type="text" bind:value={hint} maxlength="200" required placeholder="e.g. tabletop board games, history podcasts" />
      {/if}
      <button class="btn primary" type="submit">Create board</button>
    </form>
  {/if}

  {#if boards && boards.every((b) => !b.n_done && !b.n_want)}
    <div class="card intro">
      <strong>Start here</strong>
      <p class="small">Open a board and add a few things you've loved (and one or two you didn't), with a star rating and a line on why.
        Trellis works out the themes that link them, draws your map, and once you've rated three or more, Discover can suggest what to try next.</p>
    </div>
  {/if}

  {#if boards === null}
    <div class="grid">{#each Array(5) as _}<div class="tile skeleton"></div>{/each}</div>
  {:else}
    <div class="grid">
      {#each boards as b (b.board_id)}
        <a class="tile card" href={`/board/${b.board_id}`} style:--c={b.colour}>
          {#if b.cover_url}<img src={b.cover_url} alt="" loading="lazy" />{/if}
          <div class="label">
            <strong>{b.name}</strong>
            <span class="small">{b.n_done ?? 0} done · {b.n_want ?? 0} to try</span>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; margin-top: 0.5rem; }
  .tile { position: relative; aspect-ratio: 4 / 3; overflow: hidden; border-top: 5px solid var(--c); display: flex; align-items: flex-end; color: var(--text); }
  .tile:hover { text-decoration: none; transform: translateY(-1px); }
  .tile img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; opacity: 0.35; }
  .tile .label { position: relative; padding: 0.75rem; display: grid; }
  .newboard { padding: 1rem; margin-bottom: 1rem; display: grid; }
  .newboard button { margin-top: 1rem; }
  header h1 { margin: 0; }
  header { margin-bottom: 0.75rem; }
  .intro { padding: 1rem; margin-bottom: 1rem; border-left: 4px solid var(--accent); }
  .intro p { margin: 0.3rem 0 0; }
</style>
