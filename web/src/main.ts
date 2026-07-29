import './styles.css';
import { loadDataset } from './data';
import { el } from './dom';
import { renderComputed } from './views/computed';
import { renderCurated } from './views/curated';
import { renderTaxonomy } from './views/taxonomy';

function header(version: string): HTMLElement {
  return el('header', {}, [
    el('h1', {}, ['lacuna']),
    el('p', { class: 'tagline' }, ['A map of what humanity hasn’t figured out yet.']),
    el('p', { class: 'lede' }, [
      'Most knowledge maps show what we know. This one tries to show where knowledge stops. ' +
        'The tree is scaffolding; the holes are the product.',
    ]),
    el('p', { class: 'version' }, [`artifact ${version} · source: OpenAlex`]),
  ]);
}

async function main(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  try {
    const { manifest, taxonomy, curated, computed } = await loadDataset();
    app.replaceChildren(
      header(manifest.version),
      renderCurated(
        'Open problems',
        'Questions a field has explicitly acknowledged it cannot answer. Curated, and every entry cites a source.',
        curated.open,
      ),
      renderCurated(
        'Blocked questions',
        'Well-posed questions that nobody is short of ideas about. What stands in the way is an instrument, a cost, an ethical limit, or a timescale.',
        curated.blocked,
      ),
      renderComputed(computed),
      renderCurated(
        'What this map cannot see',
        'lacuna’s own blind spots, listed as first-class entries rather than caveats. A map of holes that hides its own is worse than no map.',
        curated['blind-spots'],
      ),
      renderTaxonomy(taxonomy),
    );
  } catch (error) {
    app.replaceChildren(
      el('div', { class: 'error' }, [
        el('h2', {}, ['Could not load the artifacts']),
        el('p', {}, [error instanceof Error ? error.message : String(error)]),
        el('p', {}, ['Run: python -m pipeline.export.build_artifacts']),
      ]),
    );
  }
}

void main();
