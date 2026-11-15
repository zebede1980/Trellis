<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api } from '#lib/api';
  import Cover from '#lib/components/Cover.svelte';
  import Stars from '#lib/components/Stars.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';
  import type { Entry } from '#lib/types';

  const id = $derived(Number(page.params.id));
  let e = $state<Entry | null>(null);
  let rating = $state<number | null>(null);
  let note = $state('');
  let consumed = $state('');
  let dirty = $state(false);
  let saving = $state(false);
  let polls = 0;

  async function load() {
    try {
      e = await api.get<Entry>(`/api/entries/${id}`);
      rating = e.rating;
      note = e.note ?? '';
      consumed = e.consumed_on ?? '';
      dirty = false;
    } catch (err) { errorToast(err); }
  }
  $effect(() => { id; polls = 0; load(); });

  // Themes arrive from a background job a few seconds after adding.
  $effect(() => {
    if (!e || e.tagged || polls > 30) return;
    const t = setTimeout(async () => {
      polls++;
      try {
        const fresh = await api.get<Entry>(`/api/entries/${id}`);
        if (e && fresh.tagged) { e.tagged = true; e.traits = fresh.traits; } else if (e) { e = { ...e }; }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearTimeout(t);
  });

  async function patch(body: Record<string, unknown>) {
    saving = true;
    try {
      e = await api.patch<Entry>(`/api/entries/${id}`, body);
      rating = e.rating;
      dirty = false;
    } catch (err) { errorToast(err); } finally { saving = false; }
  }

  function saveAll() { patch({ rating, note, consumed_on: consumed || null }); }

  async function remove() {
    if (!e || !confirm(`Remove "${e.title}" from your board?`)) return;
    try {
      await api.del(`/api/entries/${id}`);
      toast(`Removed ${e.title}`);
      goto(`/board/${e.board_id}`);
    } catch (err) { errorToast(err); }
  }

  const facetOrder = ['theme', 'tone', 'setting', 'style', 'genre', 'medium'];
</script>

{#if e}
  <div class="page">
    <a class="small" href={`/board/${e.board_id}`}>← {e.board_name}</a>
    <div class="top">
      <div class="cov"><Cover src={e.cover_url} title={e.title} colour={e.board_colour} /></div>
      <div class="info">
        <h1>{e.title}</h1>
        <p class="muted">{[e.creators.join(', '), e.year].filter(Boolean).join(' · ')}</p>
        <div class="row wrap">
          {#if e.url}<a class="small" href={e.url} target="_blank" rel="noopener noreferrer">View on {e.source === 'ai' ? 'the web' : e.source} ↗</a>{/if}
          {#if !e.verified}<span class="badge">unverified</span>{/if}
        </div>
        <div class="seg" role="group" aria-label="State">
          <button class:on={e.state === 'done'} onclick={() => patch({ state: 'done' })}>Done it</button>
          <button class:on={e.state === 'want'} onclick={() => patch({ state: 'want' })}>Want to try</button>
        </div>
        {#if e.state === 'done'}
          <Stars bind:value={rating} />
          {#if rating !== e.rating}<button class="btn small primary" onclick={saveAll} disabled={saving}>Save rating</button>{/if}
        {/if}
      </div>
    </div>

    <section>
      <label for="note">{e.state === 'done' ? 'What did you think?' : 'Why does it appeal?'}</label>
      <textarea id="note" bind:value={note} oninput={() => (dirty = true)} maxlength="4000"></textarea>
      {#if e.state === 'done'}
        <label for="when">When</label>
        <input id="when" type="date" bind:value={consumed} oninput={() => (dirty = true)} />
      {/if}
      {#if dirty}<button class="btn primary small savebtn" onclick={saveAll} disabled={saving}>Save</button>{/if}
    </section>

    <section>
      <h2>Themes</h2>
      {#if !e.tagged}
        <p class="muted small">Finding themes…</p>
      {:else if e.traits?.length}
        <div class="row wrap">
          {#each [...e.traits].sort((a, b) => facetOrder.indexOf(a.facet) - facetOrder.indexOf(b.facet) || (b.weight ?? 0) - (a.weight ?? 0)) as t}
            <a class="chip" href={`/theme/${t.trait_id}`} title={t.facet}><span class="facet">{t.facet}</span>{t.name}</a>
          {/each}
        </div>
      {:else}
        <p class="muted small">No themes.</p>
      {/if}
    </section>

    {#if e.summary}
      <section><h2>About</h2><p class="summary">{e.summary}</p></section>
    {/if}

    <section class="danger-zone"><button class="btn danger small" onclick={remove}>Remove from board</button></section>
  </div>
{/if}

<style>
  .top { display: grid; grid-template-columns: 120px 1fr; gap: 1rem; margin-top: 0.75rem; align-items: start; }
  @media (min-width: 700px) { .top { grid-template-columns: 180px 1fr; } }
  .info h1 { margin-bottom: 0.2rem; }
  .info p { margin: 0 0 0.4rem; }
  .seg { display: inline-grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin: 0.75rem 0 0.25rem; }
  .seg button { min-height: 38px; padding: 0 0.8rem; border: 0; background: var(--surface); }
  .seg button.on { background: var(--accent); color: var(--accent-ink); font-weight: 600; }
  section { margin-top: 1.25rem; }
  .facet { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .summary { white-space: pre-line; color: var(--muted); }
  .savebtn { margin-top: 0.5rem; }
  .danger-zone { margin-top: 2rem; }
</style>
