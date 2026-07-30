import { el, formatNumber, provenanceChip } from '../dom';
import type { ComputedLayer, Manifest } from '../types';

const REPOSITORY = 'https://github.com/tang-vu/lacuna';
const SITE = 'https://lacuna.tangvu.dev';

function actionLink(label: string, href: string, kind = 'primary'): HTMLElement {
  return el('a', { class: `button button-${kind}`, href }, [label]);
}

function shareButton(): HTMLButtonElement {
  const button = el(
    'button',
    { class: 'button button-secondary', type: 'button' },
    ['Share the experiment'],
  ) as HTMLButtonElement;
  const share = {
    title: 'lacuna',
    text:
      "An open-source attempt to map what humanity hasn't figured out yet. " +
      'Its first two methods failed—and the failures are public.',
    url: SITE,
  };

  button.addEventListener('click', async () => {
    try {
      if (navigator.share) {
        await navigator.share(share);
        return;
      }
      await navigator.clipboard.writeText(SITE);
      button.textContent = 'Link copied';
      window.setTimeout(() => {
        button.textContent = 'Share the experiment';
      }, 1800);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      button.textContent = 'Copy failed';
    }
  });
  return button;
}

export function renderProjectStatus(
  manifest: Manifest,
  computed: ComputedLayer,
): HTMLElement {
  const { validation, coverage } = computed;
  return el('section', { class: 'project-status', id: 'status' }, [
    el('div', { class: 'section-kicker' }, ['THE EXPERIMENT']),
    el('h2', {}, ['The hard part is still unsolved.']),
    el('p', { class: 'status-intro' }, [
      'lacuna is an open-source attempt to compute holes in knowledge without laundering ' +
        'plausible-looking pairs into discoveries. The first two methods failed their test. ' +
        'That failure is the starting point, not a footnote.',
    ]),
    el('div', { class: 'status-grid' }, [
      el('article', { class: 'status-card' }, [
        el('span', { class: 'status-number' }, ['01']),
        el('h3', {}, ['The goal']),
        el('p', {}, [
          'Find two literatures that are structurally connected but have not met—and expose every ' +
            'intermediate bridge and source query.',
        ]),
      ]),
      el('article', { class: 'status-card status-card-warning' }, [
        el('span', { class: 'status-number' }, ['02']),
        el('div', { class: 'chips' }, [
          provenanceChip('unvalidated'),
          el('span', { class: 'chip chip-verdict' }, [`v1 + v2: ${validation.verdict}`]),
        ]),
        el('h3', {}, ['The evidence']),
        el('p', {}, [
          `The canonical pair ranked at top ${validation.target_percentile}% of ` +
            `${formatNumber(coverage.pairs_scored)} pairs. The pre-registered bar was top ` +
            `${validation.required_percentile}%.`,
        ]),
      ]),
      el('article', { class: 'status-card' }, [
        el('span', { class: 'status-number' }, ['03']),
        el('h3', {}, ['The work now']),
        el('p', {}, [
          'Freeze a multi-case benchmark and recover period-appropriate MEDLINE records before ' +
            'another metric sees the held-out cases.',
        ]),
      ]),
    ]),
    el('div', { class: 'hero-actions' }, [
      actionLink('Explore the evidence', '#computed'),
      actionLink('Help build metric v3', `${REPOSITORY}/blob/main/CONTRIBUTING.md`, 'secondary'),
      shareButton(),
    ]),
    el('p', { class: 'status-meta' }, [
      `artifact ${manifest.version} · static, versioned, reproducible`,
    ]),
  ]);
}

export function renderFooter(): HTMLElement {
  return el('footer', {}, [
    el('p', { class: 'footer-statement' }, [
      'A map of holes should make its own holes impossible to miss.',
    ]),
    el('nav', { 'aria-label': 'Project links' }, [
      el('a', { href: REPOSITORY }, ['Source']),
      el('a', { href: `${REPOSITORY}/blob/main/CONTRIBUTING.md` }, ['Contribute']),
      el('a', { href: `${REPOSITORY}/issues` }, ['Issues']),
      el('a', { href: `${REPOSITORY}/blob/main/LICENSE` }, ['MIT license']),
    ]),
  ]);
}
