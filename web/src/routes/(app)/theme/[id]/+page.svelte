<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api } from '#lib/api';
  import Cover from '#lib/components/Cover.svelte';
  import Stars from '#lib/components/Stars.svelte';
  import SuggestionCard from '#lib/components/SuggestionCard.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Suggestion, TreeEntry } from '#lib/types';

  type Theme = {
    trait_id: number; name: string; facet: string; description: string | null; affinity: number;
    entries: (TreeEntry & { weight: number })[]; suggestions: Suggestion[];
    related: { trait_id: number; name: string; facet: string; n: number }[];
  };

  const id = $derived(Number(page.params.id));
  let t = $state<Theme | null>(null);
  let busy = $state(false);

  async function load() {
    try { t = await api.get<Theme>(`/api/themes/${id}`); } catch (e) { errorToast(e); }
  }
  $effect(() => { id; load(); });

  async function more() {
    busy = true;
    try {
      await api.post('/api/recommend', { mode: 'trait', trait_id: id });
      toast('Looking for more… results will appear in Discover');
      goto('/discover?running=1');
    } catch (e) { errorToast(e); } finally { busy = false; }
  }
</script>

{#if t}
  <div class="page">
    <span class="small muted facet">{t.facet}</span>
    <h1>{t.name}</h1>
    {#if t.description}<p class="muted">{t.description}</p>{/if}
    <p class="small">Affinity <strong>{t.affinity > 0 ? '+' : ''}{t.affinity.toFixed(1)}</strong> · {t.entries.length} of your things</p>
    <button class="btn primary" onclick={more} disabled={busy}>Find more like this</button>

    {#if t.entries.length}
      <h2>Yours</h2>
      <div class="grid">
        {#each t.entries as e (e.entry_id)}
          <a class="item" href={`/entry/${e.entry_id}`}>
            <Cover src={e.cover_url} title={e.title} colour={e.board_colour} />
            <span class="t">{e.title}</span>
            <span class="small" style:color={e.board_colour}>{e.board_name}</span>
            {#if e.state === 'done'}<Stars value={e.rating} readonly size="0.8rem" />{:else}<span class="badge">to try</span>{/if}
          </a>
        {/each}
      </div>
    {/if}

    {#if t.suggestions.length}
      <h2>Suggested</h2>
      <div class="suggs">
        {#each t.suggestions as s (s.suggestion_id)}
          <SuggestionCard {s} onacted={load} />
        {/each}
      </div>
    {/if}

    {#if t.related.length}
      <h2>Often alongside</h2>
      <div class="row wrap">{#each t.related as r}<a class="chip" href={`/theme/${r.trait_id}`}>{r.name} <span class="muted">{r.n}</span></a>{/each}</div>
    {/if}
  </div>
{/if}

<style>
  .facet { text-transform: uppercase; letter-spacing: 0.05em; }
  h1 { margin-top: 0.1rem; }
  h2 { margin-top: 1.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 14px 10px; }
  .item { display: grid; gap: 3px; color: var(--text); }
  .item:hover { text-decoration: none; }
  .t { font-size: 0.85rem; font-weight: 600; line-height: 1.2; }
  .suggs { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
</style>
