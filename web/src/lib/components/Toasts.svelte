<script lang="ts">
  import { toasts } from '#lib/toast.svelte';
</script>

<div class="toasts" aria-live="polite">
  {#each toasts as t (t.id)}
    <div class="toast" class:error={t.kind === 'error'}>{t.text}</div>
  {/each}
</div>

<style>
  .toasts { position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(var(--tabbar-h) + 12px + env(safe-area-inset-bottom)); z-index: 100; display: grid; gap: 8px; width: min(92vw, 420px); }
  .toast { background: var(--text); color: var(--bg); padding: 0.7rem 1rem; border-radius: 10px; box-shadow: var(--shadow); font-size: 0.95rem; }
  .toast.error { background: var(--danger); color: #fff; }
  @media (min-width: 900px) { .toasts { bottom: 24px; } }
</style>
