<script lang="ts">
  import type { Branch, Selection, Tree } from '#lib/types';
  import Stars from './Stars.svelte';

  let { tree, onselect, selected = null }: { tree: Tree; onselect: (s: Selection) => void; selected?: Selection } = $props();

  const maxAff = $derived(Math.max(1, ...tree.branches.map((b) => Math.abs(b.affinity ?? 0))));
  const selEntry = $derived(selected?.type === 'entry' ? selected.id : null);

  function width(b: Branch) {
    return `${Math.round((Math.abs(b.affinity ?? 0) / maxAff) * 100)}%`;
  }
</script>

<div class="tree">
  {#each tree.branches as b, i (b.id)}
    <details open={i < 3} class:newb={b.new_branch} style:--c={b.colour ?? 'var(--accent)'}>
      <summary>
        <span class="name">{b.name}</span>
        {#if b.facet}<span class="facet">{b.facet}</span>{/if}
        {#if b.new_branch}<span class="chip dashed small">new</span>{/if}
        <span class="spacer"></span>
        <span class="count small muted">{b.entries.length}{b.suggestions.length ? ` +${b.suggestions.length}` : ''}</span>
        {#if b.affinity !== undefined}
          <span class="aff" title={`affinity ${b.affinity.toFixed(1)}`}><span class:neg={(b.affinity ?? 0) < 0} style:width={width(b)}></span></span>
        {/if}
      </summary>
      <ul>
        {#each b.entries as id (id)}
          {@const e = tree.entries[String(id)]}
          <li>
            <button class="item" class:hl={selEntry === id} onclick={() => onselect({ type: 'entry', id })}>
              <span class="dot" style:background={e.board_colour} aria-hidden="true"></span>
              <span class="t">{e.title}</span>
              {#if e.state === 'done'}<Stars value={e.rating} readonly size="0.75rem" />{:else}<span class="badge">to try</span>{/if}
            </button>
          </li>
        {/each}
        {#each b.suggestions as id (id)}
          {@const s = tree.suggestions[String(id)]}
          <li>
            <button class="item sugg" onclick={() => onselect({ type: 'suggestion', id })}>
              <span class="dot" style:border-color={s.board_colour} aria-hidden="true"></span>
              <span class="t">{s.title}</span>
              <span class="badge">suggested</span>
            </button>
          </li>
        {/each}
        {#if b.trait_id || b.board_id}
          <li><button class="item more small" onclick={() => onselect({ type: 'theme', branch: b })}>About this {b.trait_id ? 'theme' : 'board'} →</button></li>
        {/if}
      </ul>
    </details>
  {/each}
  {#if tree.other.length}
    <details>
      <summary><span class="name">Other threads</span><span class="spacer"></span><span class="count small muted">{tree.other.length}</span></summary>
      <ul>
        {#each tree.other as id (id)}
          {@const e = tree.entries[String(id)]}
          <li>
            <button class="item" class:hl={selEntry === id} onclick={() => onselect({ type: 'entry', id })}>
              <span class="dot" style:background={e.board_colour} aria-hidden="true"></span>
              <span class="t">{e.title}</span>
              {#if e.state === 'done'}<Stars value={e.rating} readonly size="0.75rem" />{/if}
            </button>
          </li>
        {/each}
      </ul>
    </details>
  {/if}
</div>

<style>
  .tree { display: grid; gap: 8px; }
  details { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
  details.newb { border-style: dashed; }
  summary { display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 0.9rem; cursor: pointer; min-height: 48px; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: '▸'; color: var(--muted); transition: transform 0.15s; }
  details[open] > summary::before { transform: rotate(90deg); }
  .name { font-weight: 600; }
  .facet { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .aff { width: 48px; height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; }
  .aff span { display: block; height: 100%; background: var(--accent); }
  .aff span.neg { background: var(--danger); }
  ul { list-style: none; margin: 0; padding: 0 0.5rem 0.5rem 1.6rem; }
  .item { display: flex; align-items: center; gap: 0.5rem; width: 100%; min-height: 40px; padding: 0.3rem 0.5rem; text-align: left; background: none; border: 0; border-radius: 8px; }
  .item:hover, .item.hl { background: var(--surface-2); }
  .t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .sugg .dot { background: transparent; border: 2px dashed; }
  .sugg .t { font-style: italic; }
  .more { color: var(--accent); }
</style>
