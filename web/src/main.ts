import './styles.css';
import { loadDataset } from './data';
import { el } from './dom';
import { renderComputed } from './views/computed';
import { renderContributionMissions } from './views/contribute';
import { renderCurated } from './views/curated';
import { renderFooter, renderProjectStatus } from './views/project';
import { renderTaxonomy } from './views/taxonomy';
import type { ComputedLayer, Manifest } from './types';

function orbit(): HTMLElement {
  return el('div', { class: 'hero-orbit', 'aria-hidden': 'true' }, [
    el('span', { class: 'orbit-ring orbit-ring-outer' }),
    el('span', { class: 'orbit-ring orbit-ring-inner' }),
    el('span', { class: 'orbit-node orbit-node-a' }),
    el('span', { class: 'orbit-node orbit-node-b' }),
    el('span', { class: 'orbit-node orbit-node-c' }),
    el('span', { class: 'orbit-node orbit-node-d' }),
    el('span', { class: 'orbit-hole' }, [
      el('span', { class: 'orbit-hole-label' }, ['unknown']),
    ]),
  ]);
}

function header(manifest: Manifest, computed: ComputedLayer): HTMLElement {
  return el('header', {}, [
    el('a', { class: 'skip-link', href: '#main-content' }, ['Skip to content']),
    el('nav', { class: 'topbar', 'aria-label': 'Primary navigation' }, [
      el('a', { class: 'wordmark', href: '/' }, ['lacuna']),
      el('div', {}, [
        el('a', { href: '/holes/' }, ['Hole atlas']),
        el('a', { href: '#status' }, ['Status']),
        el('a', { href: '#contribute' }, ['Contribute']),
        el('a', { href: '#computed' }, ['Evidence lab']),
        el('a', { href: 'https://github.com/tang-vu/lacuna' }, ['GitHub ↗']),
      ]),
    ]),
    el('div', { class: 'hero' }, [
      el('div', { class: 'hero-copy' }, [
        el('p', { class: 'eyebrow' }, ['OPEN-SOURCE KNOWLEDGE-GAP OBSERVATORY']),
        el('h1', {}, ['Map the edge of what we know.']),
        el('p', { class: 'tagline' }, [
          'Most knowledge maps show what humanity has figured out. lacuna is trying to measure ' +
            'where the connections stop.',
        ]),
        el('p', { class: 'lede' }, [
          'The knowledge tree is scaffolding. The holes are the product.',
        ]),
        el('div', { class: 'hero-actions' }, [
          el('a', { class: 'button button-primary', href: '/holes/' }, ['Browse sourced holes']),
          el('a', { class: 'button button-secondary', href: '#computed' }, ['Audit the failed method']),
          el(
            'a',
            {
              class: 'button button-secondary',
              href: 'https://github.com/tang-vu/lacuna',
            },
            ['View source ↗'],
          ),
        ]),
      ]),
      orbit(),
      el('dl', { class: 'hero-ledger', 'aria-label': 'Current project status' }, [
        el('div', {}, [
          el('dt', {}, ['methods tested']),
          el('dd', {}, ['2']),
        ]),
        el('div', {}, [
          el('dt', {}, ['validated gap pairs']),
          el('dd', {}, ['0']),
        ]),
        el('div', {}, [
          el('dt', {}, ['pairs scored']),
          el('dd', {}, [computed.coverage.pairs_scored.toLocaleString('en-US')]),
        ]),
        el('div', {}, [
          el('dt', {}, ['artifact']),
          el('dd', {}, [manifest.version]),
        ]),
      ]),
    ]),
  ]);
}

async function main(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  try {
    const { manifest, taxonomy, curated, computed, projectStatus } = await loadDataset();
    app.replaceChildren(
      header(manifest, computed),
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
    const targetId = decodeURIComponent(window.location.hash.slice(1));
    if (targetId) {
      window.requestAnimationFrame(() => {
        document.getElementById(targetId)?.scrollIntoView();
      });
    }
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
