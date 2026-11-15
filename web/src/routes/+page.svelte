<script lang="ts">
  let health = $state<string>('checking…');
  $effect(() => {
    fetch('/api/health').then((r) => r.json()).then((j) => (health = `ok, v${j.version}`)).catch(() => (health = 'down'));
  });
</script>

<h1>Trellis</h1>
<p>API: {health}</p>
