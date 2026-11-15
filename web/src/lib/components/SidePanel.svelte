<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '#lib/api';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Selection, Tree } from '#lib/types';
  import Cover from './Cover.svelte';
  import Stars from './Stars.svelte';
  import SuggestionCard from './SuggestionCard.svelte';

  let { sel, tree, onclose, onchanged }: { sel: Selection; tree: Tree; onclose: () => void; onchanged: () => void } = $props();

  const entry = $derived(sel?.type === 'entry' ? tree.entries[String(sel.id)] : null);
  const sugg = $derived(sel?.type === 'suggestion' ? tree.suggestions[String(sel.id)] : null);
  const branch = $derived(sel?.type === 'theme' ? sel.branch : null);
  const themesOfEntry = $derived(entry ? tree.branches.filter((b) => b.entries.includes(entry.entry_id) && b.trait_id) : []);

  async function moreLikeThis(traitId: number) {
    try {
      await api.post('/api/recommend', { mode: 'trait', trait_id: traitId });
      toast('Looking for more… results will appear in Discover');
      goto('/discover?running=1');
    } catch (e) { errorToast(e); }
  }
</script>

<aside class="panel card" aria-label="Details">
  <button class="btn ghost small close" onclick={onclose} aria-label="Close">✕</button>
  {#if entry}
    <div class="cov"><Cover src={entry.cover_url} title={entry.title} colour={entry.board_colour} /></div>
    <span class="board small" style:color={entry.board_colour}>{entry.board_name}</span>
    <h2>{entry.title}</h2>
    <p class="small muted">{[entry.creators.join(', '), entry.year].filter(Boolean).join(' · ')}</p>
    {#if entry.state === 'done'}<Stars value={entry.rating} readonly size="1.1rem" />{:else}<span class="badge">to try</span>{/if}
    {#if entry.note}<p class="note">“{entry.note}”</p>{/if}
    {#if themesOfEntry.length}
      <div class="row wrap">{#each themesOfEntry as t}<a class="chip" href={`/theme/${t.trait_id}`}>{t.name}</a>{/each}</div>
    {/if}
    <a class="btn small" href={`/entry/${entry.entry_id}`}>Open</a>
  {:else if sugg}
    <SuggestionCard s={sugg} compact onacted={() => { onchanged(); onclose(); }} />
  {:else if branch}
    <span class="small muted">{branch.facet ?? 'board'}</span>
    <h2>{branch.name}</h2>
    {#if branch.description}<p class="small muted">{branch.description}</p>{/if}
    {#if branch.affinity !== undefined}
      <p class="small">Affinity <strong>{branch.affinity > 0 ? '+' : ''}{branch.affinity.toFixed(1)}</strong> across {branch.n} of your things</p>
    {/if}
    {#if branch.new_branch}<p class="small"><span class="chip dashed">new branch</span> A theme you haven't explored yet.</p>{/if}
    <div class="row wrap">
      {#if branch.trait_id}
        <a class="btn small" href={`/theme/${branch.trait_id}`}>Open theme</a>
        <button class="btn small primary" onclick={() => moreLikeThis(branch.trait_id!)}>Find more like this</button>
      {:else if branch.board_id}
        <a class="btn small" href={`/board/${branch.board_id}`}>Open board</a>
      {/if}
    </div>
  {/if}
</aside>

<style>
  .panel { position: relative; padding: 1rem; display: grid; gap: 0.5rem; align-content: start; overflow-y: auto; }
  .close { position: absolute; top: 4px; right: 4px; }
  .cov { width: 120px; }
  h2 { margin: 0; }
  p { margin: 0; }
  .note { font-style: italic; white-space: pre-line; }
  .board { font-weight: 600; }
</style>
