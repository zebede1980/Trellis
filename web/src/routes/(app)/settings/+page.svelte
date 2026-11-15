<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '#lib/api';
  import { session } from '#lib/session.svelte';
  import { errorToast, toast } from '#lib/toast.svelte';

  let current = $state('');
  let next = $state('');
  let next2 = $state('');

  async function changePw(e: SubmitEvent) {
    e.preventDefault();
    if (next !== next2) { errorToast('New passwords do not match'); return; }
    try {
      await api.post('/api/me/password', { current, new: next });
      toast('Password changed');
      current = next = next2 = '';
    } catch (err) { errorToast(err); }
  }

  async function logout() {
    await api.post('/api/logout');
    session.user = null;
    goto('/login');
  }
</script>

<div class="page narrow">
  <h1>Settings</h1>
  <p class="muted">Signed in as <strong>{session.user?.username}</strong></p>

  <section class="card pad">
    <h2>Change password</h2>
    <form onsubmit={changePw}>
      <label for="cur">Current password</label>
      <input id="cur" type="password" autocomplete="current-password" bind:value={current} required />
      <label for="new">New password (8+ characters)</label>
      <input id="new" type="password" autocomplete="new-password" minlength="8" bind:value={next} required />
      <label for="new2">New password again</label>
      <input id="new2" type="password" autocomplete="new-password" minlength="8" bind:value={next2} required />
      <button class="btn primary" type="submit">Change password</button>
    </form>
  </section>

  <section class="card pad">
    <h2>Your data</h2>
    <p class="small muted">Download everything you've added, with ratings and notes, as JSON.</p>
    <a class="btn" href="/api/export" download="trellis-export.json">Export my data</a>
  </section>

  <section class="card pad">
    <button class="btn" onclick={logout}>Sign out</button>
  </section>

  <section class="card pad about" id="about">
    <h2>About</h2>
    <p class="small">Trellis tracks what you've read, watched, played and listened to, links them by shared themes, and suggests what to try next.</p>
    <p class="small">Catalogue data from
      <a href="https://openlibrary.org" target="_blank" rel="noopener">Open Library</a>,
      <a href="https://musicbrainz.org" target="_blank" rel="noopener">MusicBrainz</a> and the
      <a href="https://coverartarchive.org" target="_blank" rel="noopener">Cover Art Archive</a>,
      <a href="https://www.tvmaze.com" target="_blank" rel="noopener">TVmaze</a>,
      <a href="https://www.wikidata.org" target="_blank" rel="noopener">Wikidata</a> and
      <a href="https://www.wikipedia.org" target="_blank" rel="noopener">Wikipedia</a>,
      and <a href="https://www.igdb.com" target="_blank" rel="noopener">IGDB</a>.
    </p>
    <div class="tmdb">
      <a href="https://www.themoviedb.org" target="_blank" rel="noopener"><strong>The Movie Database (TMDB)</strong></a>
      <p class="small">This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
    </div>
  </section>
</div>

<style>
  .narrow { max-width: 640px; }
  .pad { padding: 1rem; margin-top: 1rem; }
  .pad h2 { margin-bottom: 0.25rem; }
  form button { margin-top: 1rem; }
  .tmdb { margin-top: 0.75rem; }
</style>
