<script lang="ts">
  import { page } from '$app/state';
  import { api } from '#lib/api';
  import SuggestionCard from '#lib/components/SuggestionCard.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Board, Suggestion } from '#lib/types';

  type Job = { job_id: number; status: string; error: string | null; result: any };
  type Status = { runs_today: number; cap: number; active: Job | null; last: Job | null };
  type MyTheme = { trait_id: number; name: string; affinity: number; n: number };

  let suggestions = $state<Suggestion[] | null>(null);
  let boards = $state<Board[]>([]);
  let themes = $state<MyTheme[]>([]);
  let status = $state<Status | null>(null);
  let boardFilter = $state<number | 0>(0);
  let mode = $state<'all' | 'explore' | 'board' | 'trait'>('all');
  let modeBoard = $state<number>(0);
  let modeTrait = $state<number>(0);
  let deckIndex = $state(0);
  let wide = $state(false);
  let lastResult = $state<any>(null);

  $effect(() => {
    const mq = matchMedia('(min-width: 900px)');
    wide = mq.matches;
    const on = () => (wide = mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  });

  async function load() {
    try {
      [suggestions, boards, themes, status] = await Promise.all([
        api.get<Suggestion[]>('/api/suggestions'), api.get<Board[]>('/api/boards'),
        api.get<MyTheme[]>('/api/themes'), api.get<Status>('/api/recommend/status')
      ]);
      deckIndex = 0;
    } catch (e) { errorToast(e); }
  }
  $effect(() => { load(); });

  // Poll while a run is in progress.
  $effect(() => {
    if (!status?.active) return;
    const t = setInterval(async () => {
      const s = await api.get<Status>('/api/recommend/status').catch(() => null);
      if (!s) return;
      if (!s.active) {
        clearInterval(t);
        lastResult = s.last;
        if (s.last?.status === 'failed') errorToast(`Suggestion run failed: ${s.last.error ?? 'unknown error'}`);
        else toast(`${s.last?.result?.kept ?? 0} new suggestions`);
        load();
      } else {
        status = s;
      }
    }, 3000);
    return () => clearInterval(t);
  });

  async function run() {
    const body: Record<string, unknown> = { mode };
    if (mode === 'board') body.board_id = modeBoard;
    if (mode === 'trait') body.trait_id = modeTrait;
    try {
      await api.post('/api/recommend', body);
      status = await api.get<Status>('/api/recommend/status');
    } catch (e) { errorToast(e); }
  }

  const shown = $derived((suggestions ?? []).filter((s) => !boardFilter || s.board_id === boardFilter));
  const current = $derived(shown[deckIndex] ?? null);

  function acted(id: number) {
    if (!suggestions) return;
    suggestions = suggestions.filter((s) => s.suggestion_id !== id);
    if (deckIndex >= shown.length) deckIndex = Math.max(0, shown.length - 1);
  }

  // swipe as an enhancement on the deck: left = next, right = previous
  let x0 = 0;
  function touchStart(e: TouchEvent) { x0 = e.touches[0].clientX; }
  function touchEnd(e: TouchEvent) {
    const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) < 60) return;
    if (dx < 0 && deckIndex < shown.length - 1) deckIndex++;
    if (dx > 0 && deckIndex > 0) deckIndex--;
  }

  const running = $derived(!!status?.active || page.url.searchParams.has('running') && status === null);
</script>

<div class="page">
  <header class="row wrap">
    <h1>Discover</h1>
    <span class="spacer"></span>
    {#if status}<span class="small muted">{status.runs_today}/{status.cap} runs today</span>{/if}
  </header>

  <section class="card runner">
    <div class="row wrap">
      <select bind:value={mode} aria-label="What to look for">
        <option value="all">Balanced, across my boards</option>
        <option value="explore">Explore new branches</option>
        <option value="board">More for one board</option>
        <option value="trait">More of one theme</option>
      </select>
      {#if mode === 'board'}
        <select bind:value={modeBoard} aria-label="Board">
          <option value={0} disabled>Choose a board</option>
          {#each boards as b}<option value={b.board_id}>{b.name}</option>{/each}
        </select>
      {:else if mode === 'trait'}
        <select bind:value={modeTrait} aria-label="Theme">
          <option value={0} disabled>Choose a theme</option>
          {#each themes.filter((t) => t.affinity > 0) as t}<option value={t.trait_id}>{t.name}</option>{/each}
        </select>
      {/if}
      <button class="btn primary" onclick={run}
        disabled={running || (mode === 'board' && !modeBoard) || (mode === 'trait' && !modeTrait)}>
        {running ? 'Thinking…' : 'Get suggestions'}
      </button>
    </div>
    {#if running}<p class="small muted">Asking the AI, then checking every title against the catalogues. Takes about a minute.</p>{/if}
    {#if lastResult?.result && !running}
      <p class="small muted">Last run: {lastResult.result.returned} ideas, {lastResult.result.kept} kept,
        {lastResult.result.unmatched?.length ?? 0} dropped as unverifiable, {lastResult.result.already_have} already known.</p>
    {/if}
  </section>

  {#if suggestions === null}
    <div class="skeleton" style="height: 260px"></div>
  {:else if suggestions.length === 0}
    <div class="empty">
      <p>No suggestions waiting.</p>
      <p class="small">Rate a few things on your boards, then press <strong>Get suggestions</strong>.</p>
    </div>
  {:else}
    <div class="row wrap filters">
      <button class="chip" class:sel={!boardFilter} onclick={() => { boardFilter = 0; deckIndex = 0; }}>All {suggestions.length}</button>
      {#each boards.filter((b) => suggestions!.some((s) => s.board_id === b.board_id)) as b}
        <button class="chip" class:sel={boardFilter === b.board_id} onclick={() => { boardFilter = b.board_id; deckIndex = 0; }}>
          <span class="dot" style:background={b.colour}></span>{b.name} {suggestions.filter((s) => s.board_id === b.board_id).length}
        </button>
      {/each}
    </div>

    {#if wide}
      <div class="list">
        {#each shown as s (s.suggestion_id)}<SuggestionCard {s} onacted={acted} />{/each}
      </div>
    {:else if current}
      <div class="deck" role="group" aria-label="Suggestion deck" ontouchstart={touchStart} ontouchend={touchEnd}>
        {#key current.suggestion_id}<SuggestionCard s={current} onacted={acted} />{/key}
      </div>
      <div class="row nav">
        <button class="btn small" disabled={deckIndex === 0} onclick={() => deckIndex--}>‹ Prev</button>
        <span class="spacer small muted center">{deckIndex + 1} of {shown.length}</span>
        <button class="btn small" disabled={deckIndex >= shown.length - 1} onclick={() => deckIndex++}>Next ›</button>
      </div>
    {/if}
  {/if}
</div>

<style>
  header h1 { margin: 0; }
  header { margin-bottom: 0.75rem; }
  .runner { padding: 0.9rem; margin-bottom: 1rem; }
  .runner select { width: auto; flex: 1; min-width: 12rem; }
  .runner p { margin: 0.5rem 0 0; }
  .filters { margin-bottom: 0.75rem; gap: 0.4rem; }
  .chip { cursor: pointer; }
  .chip.sel { border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .list { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }
  .deck { touch-action: pan-y; }
  .nav { margin-top: 0.75rem; }
  .center { text-align: center; }
</style>
