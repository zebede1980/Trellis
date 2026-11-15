<script lang="ts">
  let { value = $bindable(null), readonly = false, size = '1.6rem' }: { value?: number | null; readonly?: boolean; size?: string } = $props();
  const labels = ['Hated it', 'Not for me', 'It was OK', 'Liked it', 'Loved it'];
</script>

{#if readonly}
  <span class="stars ro" style:font-size={size} aria-label={value ? `${value} of 5` : 'Not rated'}>
    {#each [1, 2, 3, 4, 5] as n}<span class:on={(value ?? 0) >= n}>★</span>{/each}
  </span>
{:else}
  <div class="stars" role="radiogroup" aria-label="Rating" style:font-size={size}>
    {#each [1, 2, 3, 4, 5] as n}
      <button type="button" role="radio" aria-checked={value === n} aria-label={labels[n - 1]} class:on={(value ?? 0) >= n}
        onclick={() => (value = value === n ? null : n)}>★</button>
    {/each}
    {#if value}<span class="lbl small muted">{labels[value - 1]}</span>{/if}
  </div>
{/if}

<style>
  .stars { display: inline-flex; align-items: center; gap: 2px; line-height: 1; }
  .stars span, .stars button { color: var(--line); }
  .stars .on { color: var(--star); }
  button { background: none; border: 0; padding: 4px 2px; font-size: inherit; min-width: 36px; min-height: 40px; }
  .lbl { font-size: 0.85rem; margin-left: 0.5rem; }
</style>
