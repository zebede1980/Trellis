<script lang="ts">
  import { api } from '#lib/api';
  import { session } from '#lib/session.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';

  type U = { user_id: number; username: string; display_name: string; is_admin: number; disabled: number; entries: number; suggestions: number; created_at: string };
  type T = { trait_id: number; slug: string; name: string; facet: string; description: string | null; works: number };
  type Usage = { by_user_purpose: { username: string; purpose: string; model: string; calls: number; failed: number; prompt_tokens: number; completion_tokens: number; last: string }[]; daily: { day: string; calls: number; failed: number }[]; calls_today: number };
  type Pair = { from_id: number; from: string; into_id: number; into: string; why: string };

  let tab = $state<'users' | 'themes' | 'usage'>('users');
  let users = $state<U[]>([]);
  let themes = $state<T[]>([]);
  let usage = $state<Usage | null>(null);
  let filter = $state('');
  let nu = $state({ username: '', password: '', display_name: '', is_admin: false });
  let mergeFrom = $state(0);
  let mergeInto = $state(0);
  let pairs = $state<Pair[] | null>(null);
  let suggesting = $state(false);

  async function load() {
    try {
      if (tab === 'users') users = await api.get<U[]>('/api/admin/users');
      if (tab === 'themes') themes = await api.get<T[]>('/api/admin/themes');
      if (tab === 'usage') usage = await api.get<Usage>('/api/admin/usage');
    } catch (e) { errorToast(e); }
  }
  $effect(() => { tab; load(); });

  async function addUser(e: SubmitEvent) {
    e.preventDefault();
    try {
      await api.post('/api/admin/users', { ...nu, display_name: nu.display_name || null });
      toast(`Created ${nu.username}`);
      nu = { username: '', password: '', display_name: '', is_admin: false };
      load();
    } catch (err) { errorToast(err); }
  }

  async function patchUser(u: U, body: Record<string, unknown>) {
    try { await api.patch(`/api/admin/users/${u.user_id}`, body); toast('Saved'); load(); } catch (e) { errorToast(e); }
  }

  function resetPw(u: U) {
    const pw = prompt(`New password for ${u.username} (8+ characters)`);
    if (pw) patchUser(u, { password: pw });
  }

  async function rename(t: T) {
    const name = prompt('Rename theme', t.name);
    if (!name || name === t.name) return;
    try { await api.patch(`/api/admin/themes/${t.trait_id}`, { name }); load(); } catch (e) { errorToast(e); }
  }

  async function merge(from_id: number, into_id: number) {
    const f = themes.find((t) => t.trait_id === from_id)?.name, i = themes.find((t) => t.trait_id === into_id)?.name;
    if (!confirm(`Merge "${f}" into "${i}"? Every link moves to "${i}".`)) return;
    try {
      await api.post('/api/admin/themes/merge', { from_id, into_id });
      toast('Merged');
      if (pairs) pairs = pairs.filter((p) => p.from_id !== from_id);
      load();
    } catch (e) { errorToast(e); }
  }

  async function suggest() {
    suggesting = true;
    try {
      const { job_id } = await api.post<{ job_id: number }>('/api/admin/themes/suggest-merges');
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const j = await api.get<{ status: string; result: { pairs: Pair[] } | null; error: string | null }>(`/api/admin/jobs/${job_id}`);
        if (j.status === 'done') { pairs = j.result?.pairs ?? []; break; }
        if (j.status === 'failed') { errorToast(j.error ?? 'failed'); break; }
      }
    } catch (e) { errorToast(e); } finally { suggesting = false; }
  }

  const shownThemes = $derived(themes.filter((t) => !filter || t.name.includes(filter.toLowerCase()) || t.facet === filter));
</script>

{#if session.user?.is_admin}
<div class="page">
  <h1>Admin</h1>
  <div class="seg" role="tablist">
    {#each [['users', 'Users'], ['themes', 'Themes'], ['usage', 'AI usage']] as [v, l]}
      <button role="tab" aria-selected={tab === v} class:on={tab === v} onclick={() => (tab = v as typeof tab)}>{l}</button>
    {/each}
  </div>

  {#if tab === 'users'}
    <table>
      <thead><tr><th>User</th><th>Entries</th><th>Suggestions</th><th></th></tr></thead>
      <tbody>
        {#each users as u (u.user_id)}
          <tr class:off={u.disabled}>
            <td><strong>{u.username}</strong>{#if u.is_admin} <span class="badge">admin</span>{/if}{#if u.disabled} <span class="badge">disabled</span>{/if}<br /><span class="small muted">{u.display_name}</span></td>
            <td>{u.entries}</td><td>{u.suggestions}</td>
            <td class="acts">
              <button class="btn small" onclick={() => resetPw(u)}>Reset password</button>
              {#if u.user_id !== session.user?.user_id}
                <button class="btn small" onclick={() => patchUser(u, { disabled: !u.disabled })}>{u.disabled ? 'Enable' : 'Disable'}</button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <form class="card pad" onsubmit={addUser}>
      <h2>Add user</h2>
      <div class="grid2">
        <div><label for="nu">Username</label><input id="nu" type="text" bind:value={nu.username} required autocapitalize="none" /></div>
        <div><label for="nd">Display name</label><input id="nd" type="text" bind:value={nu.display_name} /></div>
        <div><label for="np">Temporary password</label><input id="np" type="password" autocomplete="new-password" minlength="8" bind:value={nu.password} required /></div>
        <div class="chk"><label><input type="checkbox" bind:checked={nu.is_admin} /> Admin</label></div>
      </div>
      <button class="btn primary" type="submit">Create</button>
      <p class="small muted">They get the five default boards and can change their password in Settings.</p>
    </form>
  {:else if tab === 'themes'}
    <div class="card pad">
      <div class="row wrap">
        <button class="btn" onclick={suggest} disabled={suggesting}>{suggesting ? 'Asking…' : 'Suggest merges (AI)'}</button>
        <span class="small muted">One cheap LLM call. You approve each merge.</span>
      </div>
      {#if pairs}
        {#if pairs.length === 0}<p class="small muted">No near-duplicates found.</p>{/if}
        {#each pairs as p}
          <div class="row wrap pair">
            <span><strong>{p.from}</strong> → <strong>{p.into}</strong> <span class="small muted">{p.why}</span></span>
            <span class="spacer"></span>
            <button class="btn small primary" onclick={() => merge(p.from_id, p.into_id)}>Merge</button>
            <button class="btn small" onclick={() => (pairs = pairs!.filter((x) => x !== p))}>Skip</button>
          </div>
        {/each}
      {/if}
      <h2>Manual merge</h2>
      <div class="row wrap">
        <select bind:value={mergeFrom}><option value={0}>Merge…</option>{#each themes as t}<option value={t.trait_id}>{t.name}</option>{/each}</select>
        <select bind:value={mergeInto}><option value={0}>…into</option>{#each themes as t}<option value={t.trait_id}>{t.name}</option>{/each}</select>
        <button class="btn" disabled={!mergeFrom || !mergeInto || mergeFrom === mergeInto} onclick={() => merge(mergeFrom, mergeInto)}>Merge</button>
      </div>
    </div>
    <input type="search" placeholder="Filter by name or facet" bind:value={filter} class="filter" />
    <table>
      <thead><tr><th>Theme</th><th>Facet</th><th>Works</th><th></th></tr></thead>
      <tbody>
        {#each shownThemes as t (t.trait_id)}
          <tr><td>{t.name}<br /><span class="small muted">{t.description ?? ''}</span></td><td>{t.facet}</td><td>{t.works}</td>
            <td><button class="btn small" onclick={() => rename(t)}>Rename</button></td></tr>
        {/each}
      </tbody>
    </table>
  {:else if usage}
    <p>Calls today: <strong>{usage.calls_today}</strong></p>
    <h2>Last 30 days by user and purpose</h2>
    <table>
      <thead><tr><th>User</th><th>Purpose</th><th>Model</th><th>Calls</th><th>Failed</th><th>Tokens in/out</th></tr></thead>
      <tbody>
        {#each usage.by_user_purpose as r}
          <tr><td>{r.username}</td><td>{r.purpose}</td><td class="small">{r.model}</td><td>{r.calls}</td><td>{r.failed}</td>
            <td class="small">{(r.prompt_tokens ?? 0).toLocaleString()} / {(r.completion_tokens ?? 0).toLocaleString()}</td></tr>
        {/each}
      </tbody>
    </table>
    <h2>By day</h2>
    <table><tbody>{#each usage.daily as d}<tr><td>{d.day}</td><td>{d.calls} calls</td><td>{d.failed} failed</td></tr>{/each}</tbody></table>
  {/if}
</div>
{:else}
  <div class="page"><p>Admins only.</p></div>
{/if}

<style>
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; margin-bottom: 1rem; }
  .seg button { min-height: 38px; padding: 0 0.9rem; border: 0; background: var(--surface); }
  .seg button.on { background: var(--accent); color: var(--accent-ink); }
  table { width: 100%; border-collapse: collapse; margin: 0.5rem 0 1rem; font-size: 0.92rem; }
  th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--line); vertical-align: top; }
  tr.off { opacity: 0.55; }
  .acts { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .pad { padding: 1rem; margin: 0.75rem 0; }
  .grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0 1rem; }
  .chk { display: flex; align-items: end; }
  .chk label { display: flex; gap: 0.4rem; align-items: center; color: var(--text); }
  form button { margin-top: 1rem; }
  .pair { padding: 0.4rem 0; border-bottom: 1px solid var(--line); }
  select { width: auto; }
  .filter { margin-top: 0.5rem; }
</style>
