import './styles.css';
import { loadDataset } from './data';
import { el } from './dom';
import { renderComputed } from './views/computed';
import { renderContributionMissions } from './views/contribute';
import { renderCurated } from './views/curated';
import { renderFooter, renderProjectStatus } from './views/project';
import { renderTaxonomy } from './views/taxonomy';

function header(version: string): HTMLElement {
  return el('header', {}, [
    el('a', { class: 'skip-link', href: '#main-content' }, ['Skip to content']),
    el('nav', { class: 'topbar', 'aria-label': 'Primary navigation' }, [
      el('a', { class: 'wordmark', href: '/' }, ['lacuna']),
      el('div', {}, [
        el('a', { href: '#status' }, ['Status']),
        el('a', { href: '#contribute' }, ['Contribute']),
        el('a', { href: '#computed' }, ['Evidence']),
        el('a', { href: 'https://github.com/tang-vu/lacuna' }, ['GitHub ↗']),
      ]),
    ]),
    el('div', { class: 'hero' }, [
      el('p', { class: 'eyebrow' }, ['OPEN-SOURCE KNOWLEDGE-GAP RESEARCH']),
      el('h1', {}, ['Map the edge of what we know.']),
      el('p', { class: 'tagline' }, [
        'Most knowledge maps show what humanity has figured out. lacuna is trying to measure ' +
          'where the connections stop.',
      ]),
      el('p', { class: 'lede' }, [
        'The knowledge tree is scaffolding. The holes are the product.',
      ]),
      el('p', { class: 'version' }, [`artifact ${version} · source: OpenAlex`]),
    ]),
  ]);
}

async function main(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  try {
    const { manifest, taxonomy, curated, computed, projectStatus } = await loadDataset();
    app.replaceChildren(
      header(manifest.version),
      el('main', { id: 'main-content' }, [
        renderProjectStatus(manifest, computed),
        renderContributionMissions(projectStatus),
        renderCurated(
          'open-problems',
          'Open problems',
          'Questions a field has explicitly acknowledged it cannot answer. Curated, and every entry cites a source.',
          curated.open,
        ),
        renderCurated(
          'blocked-questions',
          'Blocked questions',
          'Well-posed questions that nobody is short of ideas about. What stands in the way is an instrument, a cost, an ethical limit, or a timescale.',
          curated.blocked,
        ),
        renderComputed(computed),
        renderCurated(
          'blind-spots',
          'What this map cannot see',
          'lacuna’s own blind spots, listed as first-class entries rather than caveats. A map of holes that hides its own is worse than no map.',
          curated['blind-spots'],
        ),
        renderTaxonomy(taxonomy),
      ]),
      renderFooter(),
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
