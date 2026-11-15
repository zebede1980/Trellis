<script lang="ts">
  import { api } from '#lib/api';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Suggestion } from '#lib/types';
  import Cover from './Cover.svelte';
  import Stars from './Stars.svelte';

  let { s, onacted, compact = false }: { s: Suggestion; onacted: (id: number, action: string) => void; compact?: boolean } = $props();
  let mode = $state<'idle' | 'dismiss' | 'done'>('idle');
  let rating = $state<number | null>(null);
  let busy = $state(false);

  async function act(action: string, extra: Record<string, unknown> = {}) {
    busy = true;
    try {
      await api.post(`/api/suggestions/${s.suggestion_id}/act`, { action, ...extra });
      toast(action === 'want' ? `${s.title} saved to try` : action === 'done' ? `${s.title} added` : 'Dismissed');
      onacted(s.suggestion_id, action);
    } catch (e) { errorToast(e); } finally { busy = false; }
  }
</script>

<article class="card sugg" class:compact style:--c={s.board_colour}>
  <div class="top">
    <div class="cov"><Cover src={s.cover_url} title={s.title} colour={s.board_colour} /></div>
    <div class="info">
      <span class="board small">{s.board_name}</span>
      <h3>{s.title}</h3>
      <p class="small muted">{[s.creators.join(', '), s.year].filter(Boolean).join(' · ')}</p>
      <div class="row wrap">
        {#if s.url}<a class="small" href={s.url} target="_blank" rel="noopener noreferrer">Details ↗</a>{/if}
        {#if !s.verified}<span class="badge" title="No catalogue or web source confirmed this">unverified</span>{/if}
        {#if s.new_branch}<span class="chip dashed small">new branch: {s.new_branch.name}</span>{/if}
      </div>
    </div>
  </div>
  <p class="reason">{s.reason}</p>
  {#if s.sources?.length || s.traits?.length}
    <div class="row wrap because small">
      {#each s.sources ?? [] as src}<a class="chip" href={`/entry/${src.entry_id}`}>↳ {src.title}</a>{/each}
      {#each s.traits ?? [] as t}<a class="chip" href={`/theme/${t.trait_id}`}>{t.name}</a>{/each}
    </div>
  {/if}

  {#if mode === 'idle'}
    <div class="actions">
      <button class="btn primary" disabled={busy} onclick={() => act('want')}>Want to try</button>
      <button class="btn" disabled={busy} onclick={() => (mode = 'done')}>Already tried</button>
      <button class="btn" disabled={busy} onclick={() => (mode = 'dismiss')}>Not now</button>
    </div>
  {:else if mode === 'dismiss'}
    <div class="actions wrap">
      {#each ['not for me', 'too similar', 'already tried it'] as r}
        <button class="btn small" disabled={busy} onclick={() => act('dismiss', { reason: r })}>{r}</button>
      {/each}
      <button class="btn small ghost" onclick={() => (mode = 'idle')}>Cancel</button>
    </div>
  {:else}
    <div class="rate">
      <span class="small muted">How was it?</span>
      <Stars bind:value={rating} />
      <div class="row">
        <button class="btn primary small" disabled={busy || !rating} onclick={() => act('done', { rating })}>Save</button>
        <button class="btn small ghost" onclick={() => (mode = 'idle')}>Cancel</button>
      </div>
    </div>
  {/if}
</article>

<style>
  .sugg { padding: 0.9rem; border-left: 4px solid var(--c); display: grid; gap: 0.6rem; }
  .top { display: grid; grid-template-columns: 84px 1fr; gap: 0.8rem; }
  .compact .top { grid-template-columns: 64px 1fr; }
  h3 { margin: 0.1rem 0; font-size: 1.05rem; }
  .info p { margin: 0 0 0.3rem; }
  .board { color: var(--c); font-weight: 600; }
  .reason { margin: 0; }
  .because { gap: 0.35rem; }
  .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .actions .btn:not(.small) { flex: 1; min-width: 6.5rem; }
  .rate { display: grid; gap: 0.4rem; }
</style>
