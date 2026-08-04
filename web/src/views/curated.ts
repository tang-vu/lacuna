import { el, formatNumber, provenanceChip } from '../dom';
import type { CuratedEntry, Source } from '../types';

const REPOSITORY = 'https://github.com/tang-vu/lacuna/blob/main/';

function shareUrl(entry: CuratedEntry): string {
  return new URL(`/holes/${encodeURIComponent(entry.id)}/`, window.location.origin).toString();
}

function shareButton(entry: CuratedEntry): HTMLButtonElement {
  const button = el(
    'button',
    {
      class: 'curated-share',
      type: 'button',
      'aria-label': `Share ${entry.title}`,
    },
    ['share this hole'],
  ) as HTMLButtonElement;
  button.addEventListener('click', async () => {
    const payload = {
      title: entry.title,
      text: entry.summary,
      url: shareUrl(entry),
    };
    try {
      if (navigator.share) {
        await navigator.share(payload);
        button.textContent = 'shared';
      } else {
        await navigator.clipboard.writeText(payload.url);
        button.textContent = 'link copied';
      }
      window.setTimeout(() => {
        button.textContent = 'share this hole';
      }, 1600);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      button.textContent = 'share failed';
    }
  });
  return button;
}

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
    el('div', { class: 'curated-actions' }, [
      el('a', { href: `/holes/${encodeURIComponent(entry.id)}/` }, ['open share page']),
      shareButton(entry),
    ]),
  ];

  return el(
    'article',
    { class: 'card card-curated', id: `hole-${entry.id}` },
    body.filter((n): n is HTMLElement => n !== null),
  );
}

export function renderCurated(
  id: string,
  title: string,
  blurb: string,
  entries: CuratedEntry[],
): HTMLElement {
  return el('section', { class: 'layer', id }, [
    el('h2', {}, [title]),
    el('p', { class: 'blurb' }, [blurb]),
    el('div', { class: 'cards' }, entries.map(entryCard)),
  ]);
}
