import { el, formatNumber, provenanceChip } from '../dom';
import type { ComputedLayer, Gap } from '../types';

const PAGE_SIZE = 12;
const REPOSITORY = 'https://github.com/tang-vu/lacuna/blob/main/';

type CountFilter = 'all' | Gap['observed_kind'];
type SortKey = 'rank' | 'deficit' | 'closeness';

function observedLabel(gap: Gap): string {
  return `${gap.observed_kind === 'upper_bound' ? '≤' : ''}${formatNumber(gap.observed)}`;
}

function ratio(gap: Gap): number {
  return gap.expected > 0 ? gap.observed / gap.expected : 0;
}

function csvCell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(gaps: Gap[], ranks: Map<Gap, number>): void {
  const header = [
    'rank',
    'topic_a_id',
    'topic_a',
    'topic_b_id',
    'topic_b',
    'observed',
    'observed_kind',
    'expected',
    'observed_expected_ratio',
    'closeness',
    'gap_score',
    'verification_query',
  ];
  const rows = gaps.map((gap) => [
    ranks.get(gap) ?? '',
    gap.topic_a,
    gap.name_a,
    gap.topic_b,
    gap.name_b,
    gap.observed,
    gap.observed_kind,
    gap.expected,
    ratio(gap),
    gap.similarity,
    gap.gap_score,
    gap.verify_url,
  ]);
  const csv = [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = el('a', { href: url, download: 'lacuna-failed-metric-measurements.csv' });
  anchor.click();
  URL.revokeObjectURL(url);
}

/** The banner is not decoration and must render before any pair does.
 *
 * These rows look exactly like a discovery feed — ranked pairs, scores, big numbers — and a reader
 * who scrolls past them without the verdict will read them as findings. The metric failed its
 * pre-registered test, so the failure travels at the top of the section, not in a footnote. */
function verdictBanner(computed: ComputedLayer): HTMLElement {
  const { validation, coverage } = computed;
  const controls =
    validation.negative_controls_status === 'partial'
      ? `Negative controls were only partly evaluated (${validation.negative_controls_evaluated} of ${validation.negative_controls_planned}).`
      : `Negative controls ${validation.negative_controls_pass ? 'passed' : 'failed'}.`;
  return el('div', { class: 'verdict' }, [
    el('div', { class: 'chips' }, [
      provenanceChip('unvalidated'),
      el('span', { class: 'chip chip-verdict' }, [`verdict: ${validation.verdict}`]),
    ]),
    el('p', {}, [validation.summary]),
    el('p', { class: 'verdict-detail' }, [
      `The canonical test pair ranked at top ${validation.target_percentile}% of ` +
        `${formatNumber(coverage.pairs_scored)} scored pairs. The bar fixed in advance was top ` +
        `${validation.required_percentile}%. ${controls}`,
    ]),
    el('ul', { class: 'sources' }, [
      el('li', {}, [el('a', { href: `${REPOSITORY}${validation.preregistration}` }, [
        'Pre-registered criteria, committed before any score existed',
      ])]),
      el('li', {}, [el('a', { href: `${REPOSITORY}${validation.report}` }, [
        'Full validation report, including what did reproduce',
      ])]),
    ]),
  ]);
}

function provenanceLink(label: string, href: string): HTMLElement {
  return el('a', { href, target: '_blank', rel: 'noreferrer', class: 'audit-link' }, [
    label,
    ' ↗',
  ]);
}

function gapCard(gap: Gap, rank: number): HTMLElement {
  const observedExpectedRatio = ratio(gap);
  const meter = el('span', { class: 'evidence-meter-fill' });
  meter.style.width = `${Math.min(observedExpectedRatio * 100, 100)}%`;

  const copyButton = el(
    'button',
    { class: 'audit-copy', type: 'button', title: 'Copy a link to this measurement' },
    ['copy link'],
  ) as HTMLButtonElement;
  copyButton.addEventListener('click', async () => {
    const url = new URL(window.location.href);
    url.searchParams.set('pair', `${gap.topic_a}--${gap.topic_b}`);
    url.hash = 'computed';
    try {
      await navigator.clipboard.writeText(url.toString());
      copyButton.textContent = 'copied';
      window.setTimeout(() => {
        copyButton.textContent = 'copy link';
      }, 1600);
    } catch {
      copyButton.textContent = 'copy failed';
    }
  });

  return el('article', { class: 'evidence-card' }, [
    el('div', { class: 'evidence-rank' }, [
      el('span', {}, [`#${String(rank).padStart(3, '0')}`]),
      el('span', {}, [gap.observed_kind === 'upper_bound' ? 'BOUNDED' : 'EXACT']),
    ]),
    el('div', { class: 'evidence-pair' }, [
      el('p', {}, [gap.name_a]),
      el('span', { class: 'evidence-gap-mark', 'aria-hidden': 'true' }, ['×']),
      el('p', {}, [gap.name_b]),
    ]),
    el('div', { class: 'evidence-values' }, [
      el('div', {}, [
        el('span', {}, ['observed']),
        el('strong', {}, [observedLabel(gap)]),
      ]),
      el('div', {}, [
        el('span', {}, ['expected']),
        el('strong', {}, [gap.expected.toFixed(1)]),
      ]),
      el('div', {}, [
        el('span', {}, ['obs / exp']),
        el('strong', {}, [observedExpectedRatio.toFixed(2)]),
      ]),
      el('div', {}, [
        el('span', {}, ['closeness']),
        el('strong', {}, [gap.similarity.toFixed(3)]),
      ]),
    ]),
    el('div', { class: 'evidence-meter', title: 'Observed divided by expected co-occurrence' }, [
      meter,
    ]),
    el('details', { class: 'evidence-audit' }, [
      el('summary', {}, ['Open audit trail']),
      el('div', { class: 'audit-grid' }, [
        el('div', {}, [
          el('span', {}, ['topic IDs']),
          el('code', {}, [`${gap.topic_a} × ${gap.topic_b}`]),
        ]),
        el('div', {}, [
          el('span', {}, ['deficit bits']),
          el('code', {}, [gap.deficit_bits.toFixed(3)]),
        ]),
        el('div', {}, [
          el('span', {}, ['gap score']),
          el('code', {}, [gap.gap_score.toFixed(6)]),
        ]),
        el('div', {}, [
          el('span', {}, ['count status']),
          el('code', {}, [gap.observed_kind.replace('_', ' ')]),
        ]),
      ]),
      el('p', { class: 'audit-note' }, [
        gap.observed_kind === 'upper_bound'
          ? 'The reported count is a conservative API-derived ceiling, not an observation of exactly this many papers.'
          : 'The exported count is exact for the pinned input rows.',
      ]),
      el('div', { class: 'audit-actions' }, [
        provenanceLink('Verify pair count', gap.verify_url),
        provenanceLink('Inspect topic A row', gap.row_source_urls[0] ?? gap.verify_url),
        provenanceLink('Inspect topic B row', gap.row_source_urls[1] ?? gap.verify_url),
        copyButton,
      ]),
    ]),
  ]);
}

function controlButton(label: string, value: CountFilter): HTMLButtonElement {
  return el(
    'button',
    {
      class: 'filter-button',
      type: 'button',
      'data-value': value,
      'aria-pressed': value === 'all' ? 'true' : 'false',
    },
    [label],
  ) as HTMLButtonElement;
}

function explorer(computed: ComputedLayer): HTMLElement {
  const ranks = new Map(computed.gaps.map((gap, index) => [gap, index + 1]));
  const params = new URLSearchParams(window.location.search);
  const pairParam = params.get('pair')?.toLowerCase() ?? '';
  const initialQuery = params.get('q') ?? pairParam.replace('--', ' ');

  const search = el('input', {
    class: 'evidence-search',
    type: 'search',
    value: initialQuery,
    placeholder: `Search ${formatNumber(computed.gaps.length)} exported pairs or topic IDs…`,
    'aria-label': 'Search measured topic pairs',
    autocomplete: 'off',
  }) as HTMLInputElement;
  const sort = el('select', { class: 'evidence-sort', 'aria-label': 'Sort measurements' }, [
    el('option', { value: 'rank' }, ['metric rank']),
    el('option', { value: 'deficit' }, ['lowest obs / exp']),
    el('option', { value: 'closeness' }, ['highest closeness']),
  ]) as HTMLSelectElement;
  const filterButtons = [
    controlButton('all counts', 'all'),
    controlButton('exact only', 'exact'),
    controlButton('bounds only', 'upper_bound'),
  ];
  const resultCount = el('p', { class: 'evidence-result-count', 'aria-live': 'polite' });
  const list = el('div', { class: 'evidence-list' });
  const empty = el('div', { class: 'evidence-empty', hidden: '' }, [
    el('p', {}, ['No exported measurement matches this search.']),
    el('button', { class: 'button button-secondary', type: 'button' }, ['Clear filters']),
  ]);
  const more = el(
    'button',
    { class: 'button button-secondary evidence-more', type: 'button' },
    ['Show 12 more'],
  ) as HTMLButtonElement;
  const exportButton = el(
    'button',
    { class: 'button button-secondary', type: 'button' },
    ['Export filtered CSV'],
  ) as HTMLButtonElement;
  let countFilter: CountFilter = 'all';
  let sortKey: SortKey = 'rank';
  let shown = PAGE_SIZE;
  let current: Gap[] = [];

  function syncUrl(): void {
    const url = new URL(window.location.href);
    url.searchParams.delete('pair');
    if (search.value.trim()) url.searchParams.set('q', search.value.trim());
    else url.searchParams.delete('q');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function update(): void {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    current = computed.gaps.filter((gap) => {
      if (countFilter !== 'all' && gap.observed_kind !== countFilter) return false;
      const haystack =
        `${gap.name_a} ${gap.name_b} ${gap.topic_a} ${gap.topic_b}`.toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
    current.sort((a, b) => {
      if (sortKey === 'deficit') return ratio(a) - ratio(b);
      if (sortKey === 'closeness') return b.similarity - a.similarity;
      return (ranks.get(a) ?? 0) - (ranks.get(b) ?? 0);
    });

    list.replaceChildren(
      ...current.slice(0, shown).map((gap) => gapCard(gap, ranks.get(gap) ?? 0)),
    );
    resultCount.textContent =
      `${formatNumber(current.length)} measurements match · showing ` +
      `${formatNumber(Math.min(shown, current.length))}`;
    empty.hidden = current.length > 0;
    more.hidden = shown >= current.length;
  }

  search.addEventListener('input', () => {
    shown = PAGE_SIZE;
    syncUrl();
    update();
  });
  sort.addEventListener('change', () => {
    sortKey = sort.value as SortKey;
    shown = PAGE_SIZE;
    update();
  });
  for (const button of filterButtons) {
    button.addEventListener('click', () => {
      countFilter = button.dataset.value as CountFilter;
      shown = PAGE_SIZE;
      for (const peer of filterButtons) {
        peer.setAttribute('aria-pressed', String(peer === button));
      }
      update();
    });
  }
  more.addEventListener('click', () => {
    shown += PAGE_SIZE;
    update();
  });
  exportButton.addEventListener('click', () => downloadCsv(current, ranks));
  (empty.querySelector('button') as HTMLButtonElement).addEventListener('click', () => {
    search.value = '';
    countFilter = 'all';
    shown = PAGE_SIZE;
    for (const button of filterButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.value === 'all'));
    }
    syncUrl();
    update();
    search.focus();
  });

  const node = el('div', { class: 'evidence-explorer' }, [
    el('div', { class: 'evidence-toolbar' }, [
      search,
      el('div', { class: 'evidence-filter', 'aria-label': 'Filter by count status' }, filterButtons),
      sort,
    ]),
    el('div', { class: 'evidence-toolbar-meta' }, [
      resultCount,
      exportButton,
    ]),
    list,
    empty,
    more,
  ]);
  update();
  return node;
}

export function renderComputed(computed: ComputedLayer): HTMLElement {

  return el('section', { class: 'layer layer-computed', id: 'computed' }, [
    el('div', { class: 'section-kicker' }, ['THE EVIDENCE LAB']),
    el('h2', {}, ['Interrogate the failed method.']),
    el('p', { class: 'blurb' }, [
      'Search, filter, export, and trace every published pair back to its OpenAlex queries. ' +
        'These are outputs from a method that failed validation—not candidate discoveries.',
    ]),
    verdictBanner(computed),
    el('div', { class: 'method-strip' }, [
      el('p', { class: 'method' }, [computed.method.description]),
      el('p', { class: 'method' }, [
        `Coverage: ${formatNumber(computed.coverage.topics_swept)} of ` +
          `${formatNumber(computed.coverage.topics_in_analysis_set)} topics. ` +
          computed.coverage.note,
      ]),
      el('p', { class: 'method' }, [
        'The ≤ symbol marks an API-derived upper bound, not an observed count.',
      ]),
    ]),
    el('div', { class: 'chips' }, [provenanceChip('measured')]),
    explorer(computed),
  ]);
}
