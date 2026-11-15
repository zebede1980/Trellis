<script lang="ts">
  import type { Core, ElementDefinition } from 'cytoscape';
  import type { Branch, Selection, Tree } from '#lib/types';

  let { tree, onselect }: { tree: Tree; onselect: (s: Selection) => void } = $props();

  const EXPANDED_BY_DEFAULT = 8;
  let el: HTMLDivElement | undefined = $state();
  let cy: Core | null = null;
  let expanded = $state<Set<string>>(new Set());
  let initialisedFor: Tree | null = null;

  function short(s: string, n = 26) {
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  function css(name: string) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function elements(t: Tree, open: Set<string>): ElementDefinition[] {
    const els: ElementDefinition[] = [{ data: { id: 'root', label: 'You', kind: 'root' } }];
    const maxAff = Math.max(1, ...t.branches.map((b) => Math.abs(b.affinity ?? 0)));
    const branches: Branch[] = [...t.branches];
    if (t.other.length) branches.push({ id: 'other', name: 'Other threads', entries: t.other, suggestions: [] });
    for (const b of branches) {
      const isOpen = open.has(b.id);
      const n = b.entries.length + b.suggestions.length;
      els.push({
        data: { id: b.id, label: `${short(b.name, 22)}${isOpen ? '' : `  (${n})`}`, kind: 'branch', colour: b.colour ?? '' },
        classes: [b.new_branch ? 'newb' : '', isOpen ? '' : 'collapsed', (b.affinity ?? 0) < 0 ? 'neg' : ''].join(' ')
      });
      const w = 1.5 + 6 * (Math.abs(b.affinity ?? 0) / maxAff);
      els.push({ data: { id: `root-${b.id}`, source: 'root', target: b.id, w }, classes: b.new_branch ? 'newb' : '' });
      if (!isOpen) continue;
      for (const id of b.entries) {
        const e = t.entries[String(id)];
        const nid = `${b.id}:e${id}`;
        els.push({ data: { id: nid, label: short(e.title), kind: 'entry', ref: id, colour: e.board_colour },
          classes: e.state === 'want' ? 'want' : '' });
        els.push({ data: { id: `${b.id}-${nid}`, source: b.id, target: nid, w: 1.2 } });
      }
      for (const id of b.suggestions) {
        const s = t.suggestions[String(id)];
        const nid = `${b.id}:s${id}`;
        els.push({ data: { id: nid, label: short(s.title), kind: 'suggestion', ref: id, colour: s.board_colour }, classes: 'sugg' });
        els.push({ data: { id: `${b.id}-${nid}`, source: b.id, target: nid, w: 1 }, classes: 'sugg' });
      }
    }
    return els;
  }

  async function render(t: Tree, open: Set<string>) {
    if (!el) return;
    const [{ default: cytoscape }, { default: dagre }] = await Promise.all([import('cytoscape'), import('cytoscape-dagre')]);
    try { cytoscape.use(dagre); } catch { /* already registered */ }
    const text = css('--text'), muted = css('--muted'), surface = css('--surface'), accent = css('--accent'), line = css('--line'), danger = css('--danger');
    cy?.destroy();
    cy = cytoscape({
      container: el,
      elements: elements(t, open),
      wheelSensitivity: 0.3,
      minZoom: 0.15,
      maxZoom: 2.5,
      style: [
        { selector: 'node', style: { label: 'data(label)', 'font-size': 11, color: text, 'text-valign': 'center', 'text-halign': 'right', 'text-margin-x': 6, width: 14, height: 14, 'background-color': 'data(colour)', 'border-width': 0 } },
        { selector: 'node[kind = "root"]', style: { width: 34, height: 34, 'background-color': accent, 'font-size': 14, 'font-weight': 'bold', 'text-halign': 'center', 'text-valign': 'bottom', 'text-margin-y': 6, 'text-margin-x': 0 } },
        { selector: 'node[kind = "branch"]', style: { shape: 'round-rectangle', width: 'label', height: 26, padding: '8px', 'background-color': surface, 'border-width': 1.5, 'border-color': accent, 'text-halign': 'center', 'text-margin-x': 0, 'font-size': 12, 'font-weight': 'bold' } },
        { selector: 'node.collapsed', style: { 'border-color': muted, color: muted } },
        { selector: 'node.newb', style: { 'border-style': 'dashed' } },
        { selector: 'node.neg', style: { 'border-color': danger } },
        { selector: 'node.want', style: { 'background-opacity': 0.45 } },
        { selector: 'node.sugg', style: { 'background-opacity': 0, 'border-width': 2, 'border-style': 'dashed', 'border-color': 'data(colour)', 'font-style': 'italic', color: muted } },
        { selector: 'node.hl', style: { 'border-width': 3, 'border-color': text, 'border-style': 'solid', width: 20, height: 20, 'font-weight': 'bold', 'z-index': 10 } },
        { selector: 'edge', style: { width: 'data(w)', 'line-color': line, 'curve-style': 'taxi', 'taxi-direction': 'rightward', 'taxi-turn': '40px' } },
        { selector: 'edge.newb, edge.sugg', style: { 'line-style': 'dashed' } }
      ],
      layout: { name: 'dagre', rankDir: 'LR', nodeSep: 6, rankSep: 90, edgeSep: 4 } as any
    });

    cy.on('tap', 'node', (evt) => {
      const n = evt.target;
      const kind = n.data('kind');
      cy!.nodes().removeClass('hl');
      if (kind === 'entry' || kind === 'suggestion') {
        const ref = n.data('ref');
        // the same item sits under several themes: highlight every copy
        cy!.nodes().filter((m) => m.data('kind') === kind && m.data('ref') === ref).addClass('hl');
        onselect({ type: kind, id: ref });
      } else if (kind === 'branch') {
        const id = n.id();
        const b = t.branches.find((x) => x.id === id);
        const next = new Set(expanded);
        if (next.has(id)) next.delete(id); else next.add(id);
        expanded = next;
        if (b) onselect({ type: 'theme', branch: b });
      }
    });
  }

  $effect(() => {
    if (tree !== initialisedFor) {
      initialisedFor = tree;
      expanded = new Set(tree.branches.slice(0, EXPANDED_BY_DEFAULT).map((b) => b.id));
    }
  });

  $effect(() => {
    render(tree, expanded);
  });

  $effect(() => () => { cy?.destroy(); cy = null; });

  export function fit() { cy?.fit(undefined, 30); }
</script>

<div class="map" bind:this={el}></div>

<style>
  .map { width: 100%; height: 100%; min-height: 500px; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
</style>
