<script lang="ts">
  let { src, title, colour = 'var(--accent)', ratio = '2 / 3' }: { src: string | null | undefined; title: string; colour?: string; ratio?: string } = $props();
  let broken = $state(false);
</script>

<div class="cover" style:aspect-ratio={ratio} style:--c={colour}>
  {#if src && !broken}
    <img {src} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={() => (broken = true)} />
  {:else}
    <span class="ph">{title}</span>
  {/if}
</div>

<style>
  .cover { position: relative; width: 100%; border-radius: 8px; overflow: hidden; background: color-mix(in srgb, var(--c) 22%, var(--surface-2)); }
  img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .ph { position: absolute; inset: 0; display: grid; place-items: center; padding: 0.5rem; text-align: center; font-weight: 600; font-size: 0.85rem; color: var(--text); overflow: hidden; }
</style>
