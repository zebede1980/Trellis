<script lang="ts">
  import { page } from '$app/state';
  import { api } from '#lib/api';
  import { session } from '#lib/session.svelte';
  import type { User } from '#lib/types';

  let { children } = $props();
  let ready = $state(false);

  $effect(() => {
    if (session.user) {
      ready = true;
      return;
    }
    api.get<User>('/api/me').then((u) => {
      session.user = u;
      ready = true;
    }).catch(() => {});
  });

  const tabs = [
    { href: '/', label: 'Home', icon: '⌂' },
    { href: '/map', label: 'Map', icon: '❦' },
    { href: '/discover', label: 'Discover', icon: '✦' },
    { href: '/settings', label: 'Settings', icon: '⚙' }
  ];

  function active(href: string): boolean {
    const p = page.url.pathname;
    return href === '/' ? p === '/' || p.startsWith('/board') || p.startsWith('/entry') : p.startsWith(href);
  }
</script>

{#if ready}
  <div class="shell">
    <nav class="side" aria-label="Main">
      <a class="brand" href="/"><span aria-hidden="true">❦</span> Trellis</a>
      {#each tabs as t}
        <a href={t.href} class:active={active(t.href)}><span class="ic" aria-hidden="true">{t.icon}</span>{t.label}</a>
      {/each}
      {#if session.user?.is_admin}
        <a href="/admin" class:active={page.url.pathname.startsWith('/admin')}><span class="ic" aria-hidden="true">☷</span>Admin</a>
      {/if}
    </nav>
    <main class="content">
      {@render children()}
    </main>
    <nav class="tabbar" aria-label="Main">
      {#each tabs as t}
        <a href={t.href} class:active={active(t.href)}><span class="ic" aria-hidden="true">{t.icon}</span><span>{t.label}</span></a>
      {/each}
    </nav>
  </div>
{/if}

<style>
  .shell { min-height: 100dvh; }
  .content { padding-bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + 12px); padding-top: env(safe-area-inset-top); }
  .side { display: none; }
  .tabbar { position: fixed; bottom: 0; left: 0; right: 0; height: calc(var(--tabbar-h) + env(safe-area-inset-bottom)); padding-bottom: env(safe-area-inset-bottom); display: grid; grid-template-columns: repeat(4, 1fr); background: var(--surface); border-top: 1px solid var(--line); z-index: 50; }
  .tabbar a { display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 0.72rem; color: var(--muted); gap: 2px; }
  .tabbar a:hover { text-decoration: none; }
  .tabbar .ic { font-size: 1.3rem; line-height: 1; }
  .tabbar a.active { color: var(--accent); font-weight: 600; }
  @media (min-width: 900px) {
    .shell { display: grid; grid-template-columns: 200px 1fr; }
    .tabbar { display: none; }
    .content { padding-bottom: 2rem; min-width: 0; }
    .side { display: flex; flex-direction: column; gap: 2px; position: sticky; top: 0; height: 100dvh; padding: 1rem 0.75rem; border-right: 1px solid var(--line); background: var(--surface); }
    .side a { display: flex; align-items: center; gap: 0.6rem; padding: 0.55rem 0.75rem; border-radius: 8px; color: var(--text); }
    .side a:hover { background: var(--surface-2); text-decoration: none; }
    .side a.active { background: var(--surface-2); color: var(--accent); font-weight: 600; }
    .side .brand { font-weight: 700; font-size: 1.2rem; margin-bottom: 1rem; color: var(--accent); }
    .side .ic { width: 1.2em; text-align: center; }
  }
</style>
