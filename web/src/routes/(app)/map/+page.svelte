<script lang="ts">
  import { api } from '#lib/api';
  import MapCanvas from '#lib/components/MapCanvas.svelte';
  import SidePanel from '#lib/components/SidePanel.svelte';
  import TreeAccordion from '#lib/components/TreeAccordion.svelte';
  import { errorToast } from '#lib/toast.svelte';
  import type { Selection, Tree } from '#lib/types';

  let tree = $state<Tree | null>(null);
  let group = $state<'theme' | 'board'>('theme');
  let sel = $state<Selection>(null);
  let wide = $state(false);
  let view = $state<'map' | 'list'>('map');

  $effect(() => {
    const mq = matchMedia('(min-width: 900px)');
    wide = mq.matches;
    const on = () => (wide = mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  });

  async function load() {
    try {
      tree = await api.get<Tree>(`/api/tree?group=${group}`);
    } catch (e) { errorToast(e); }
  }
  $effect(() => { group; sel = null; load(); });

  const empty = $derived(tree && Object.keys(tree.entries).length === 0);
  const untagged = $derived(tree && !empty && tree.branches.length === 0 && group === 'theme');
</script>

<div class="page wide">
  <header class="row wrap">
    <h1>Your map</h1>
    <span class="spacer"></span>
    <div class="seg" role="group" aria-label="Group by">
      <button class:on={group === 'theme'} onclick={() => (group = 'theme')}>Themes</button>
      <button class:on={group === 'board'} onclick={() => (group = 'board')}>Boards</button>
    </div>
    {#if wide}
      <div class="seg" role="group" aria-label="View">
        <button class:on={view === 'map'} onclick={() => (view = 'map')}>Map</button>
        <button class:on={view === 'list'} onclick={() => (view = 'list')}>List</button>
      </div>
    {/if}
  </header>

  {#if tree === null}
    <div class="skeleton" style="height: 60vh"></div>
  {:else if empty}
    <div class="empty"><p>Your map grows as you add things you've tried.</p><a class="btn primary" href="/">Go to your boards</a></div>
  {:else}
    {#if untagged}<p class="muted small">Themes are still being worked out for your entries; check back in a minute.</p>{/if}
    <div class="layout" class:withpanel={wide && sel}>
      <div class="main">
        {#if wide && view === 'map'}
          <div class="canvas"><MapCanvas {tree} onselect={(s) => (sel = s)} /></div>
          <p class="small muted legend">Tap a theme to expand or collapse it. Dashed = suggestions and unexplored branches. Colour = board.</p>
        {:else}
          <TreeAccordion {tree} selected={sel} onselect={(s) => (sel = s)} />
        {/if}
      </div>
      {#if sel && wide}
        <div class="side"><SidePanel {sel} {tree} onclose={() => (sel = null)} onchanged={load} /></div>
      {/if}
    </div>
    <div class="legend-boards row wrap small">
      {#each tree.boards as b}<span class="row"><span class="dot" style:background={b.colour}></span>{b.name}</span>{/each}
    </div>
  {/if}
</div>

{#if sel && !wide && tree}
  <div class="backdrop" role="presentation" onclick={() => (sel = null)}></div>
  <div class="sheet"><SidePanel {sel} {tree} onclose={() => (sel = null)} onchanged={load} /></div>
{/if}

<style>
  .wide { max-width: 1500px; }
  header h1 { margin: 0; }
  header { margin-bottom: 0.75rem; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
  .seg button { min-height: 36px; padding: 0 0.8rem; border: 0; background: var(--surface); }
  .seg button.on { background: var(--accent); color: var(--accent-ink); }
  .layout { display: grid; gap: 1rem; }
  .layout.withpanel { grid-template-columns: 1fr 340px; }
  .canvas { height: calc(100dvh - 170px); }
  .side { position: sticky; top: 1rem; max-height: calc(100dvh - 2rem); display: grid; }
  .legend { margin: 0.4rem 0 0; }
  .legend-boards { margin-top: 0.75rem; gap: 0.9rem; color: var(--muted); }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .backdrop { position: fixed; inset: 0; background: rgb(0 0 0 / 0.35); z-index: 60; }
  .sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 61; max-height: 80dvh; display: grid; padding-bottom: env(safe-area-inset-bottom); background: var(--surface); border-radius: 16px 16px 0 0; }
</style>
