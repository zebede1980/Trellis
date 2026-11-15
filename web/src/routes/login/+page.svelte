<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { api, safeNext } from '#lib/api';
  import { session } from '#lib/session.svelte';
  import type { User } from '#lib/types';

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let busy = $state(false);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    error = '';
    try {
      session.user = await api.post<User>('/api/login', { username, password });
      await goto(safeNext(page.url.searchParams.get('next')), { replaceState: true });
    } catch (err) {
      error = err instanceof Error ? err.message : 'Login failed';
    } finally {
      busy = false;
    }
  }
</script>

<main class="login">
  <form class="card" onsubmit={submit}>
    <h1><span class="logo" aria-hidden="true">❦</span> Trellis</h1>
    <p class="muted small">Track what you've loved. Find what's next.</p>
    <label for="u">Username</label>
    <input id="u" type="text" autocomplete="username" autocapitalize="none" bind:value={username} required />
    <label for="p">Password</label>
    <input id="p" type="password" autocomplete="current-password" bind:value={password} required />
    {#if error}<p class="err">{error}</p>{/if}
    <button class="btn primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
  </form>
</main>

<style>
  .login { min-height: 100dvh; display: grid; place-items: center; padding: 1rem; }
  form { width: min(100%, 360px); padding: 1.5rem; }
  .logo { color: var(--accent); }
  button { width: 100%; margin-top: 1.25rem; }
  .err { color: var(--danger); margin: 0.75rem 0 0; }
</style>
