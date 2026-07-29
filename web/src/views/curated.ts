import { el, formatNumber, provenanceChip } from '../dom';
import type { CuratedEntry, Source } from '../types';

const REPOSITORY = 'https://github.com/tang-vu/lacuna/blob/main/';

function sourceUrl(url: string): string {
  return /^https?:\/\//.test(url) ? url : `${REPOSITORY}${url}`;
}

function sourceList(sources: Source[] | undefined): HTMLElement | null {
  if (!sources?.length) return null;
  return el(
    'ul',
    { class: 'sources' },
    sources.map((source) =>
      el('li', {}, [
        el('a', { href: sourceUrl(source.url), target: '_blank', rel: 'noreferrer' }, [source.label]),
      ]),
    ),
  );
}

function measuredList(measured: Record<string, number> | undefined): HTMLElement | null {
  if (!measured) return null;
  return el(
    'dl',
    { class: 'measured-values' },
    Object.entries(measured).flatMap(([key, value]) => [
      el('dt', {}, [key.replace(/_/g, ' ')]),
      el('dd', {}, [formatNumber(value)]),
    ]),
  );
}

function entryCard(entry: CuratedEntry): HTMLElement {
  const meta: HTMLElement[] = [provenanceChip('curated')];
  if (entry.blocker) {
    meta.push(el('span', { class: `chip chip-blocker` }, [`blocked by ${entry.blocker}`]));
  }
  if (entry.severity) {
    meta.push(el('span', { class: 'chip chip-severity' }, [`${entry.severity} blind spot`]));
  }
  if (entry.posed) {
    meta.push(el('span', { class: 'chip chip-year' }, [`posed ${entry.posed}`]));
  }

  const body: (HTMLElement | null)[] = [
    el('h3', {}, [entry.title]),
    el('div', { class: 'chips' }, meta),
    el('p', {}, [entry.summary]),
    measuredList(entry.measured),
    sourceList(entry.sources),
  ];

  return el('article', { class: 'card card-curated' }, body.filter((n): n is HTMLElement => n !== null));
}

export function renderCurated(
  title: string,
  blurb: string,
  entries: CuratedEntry[],
): HTMLElement {
  return el('section', { class: 'layer' }, [
    el('h2', {}, [title]),
    el('p', { class: 'blurb' }, [blurb]),
    el('div', { class: 'cards' }, entries.map(entryCard)),
  ]);
}
