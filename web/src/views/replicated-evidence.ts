import { el, formatNumber, provenanceChip } from '../dom';
import type { ReplicatedEvidence, ReplicatedEvidenceObservation } from '../types';

const PAGE_SIZE = 12;
const REPOSITORY = 'https://github.com/tang-vu/lacuna/blob/main/';
const PROTOCOL_PATH = 'benchmarks/evidence-v1.json';

type DirectionFilter = 'all' | ReplicatedEvidenceObservation['direction'];
type SortKey = 'rank' | 'strength' | 'agreement';

function csvCell(value: string | number): string {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(observations: ReplicatedEvidenceObservation[]): void {
  const header = [
    'rank',
    'gene_a_symbol',
    'gene_a_entrez_id',
    'gene_b_symbol',
    'gene_b_entrez_id',
    'direction',
    'tcga_samples',
    'tcga_spearman_rho',
    'tcga_bh_q_conservative',
    'metabric_samples',
    'metabric_spearman_rho',
    'metabric_bh_q_conservative',
    'status',
    'claim_scope',
  ];
  const rows = observations.map((observation) => [
    observation.rank,
    observation.entities.a.symbol,
    observation.entities.a.entrez_gene_id,
    observation.entities.b.symbol,
    observation.entities.b.entrez_gene_id,
    observation.direction,
    observation.tcga.samples,
    observation.tcga.spearman_rho,
    observation.tcga.benjamini_hochberg_q_conservative,
    observation.metabric.samples,
    observation.metabric.spearman_rho,
    observation.metabric.benjamini_hochberg_q_conservative,
    observation.status,
    observation.claim_scope,
  ]);
  const csv = [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = el('a', { href: url, download: 'lacuna-replicated-observations-v1.csv' });
  anchor.click();
  URL.revokeObjectURL(url);
}

function scientific(value: number): string {
  return value < 0.001 ? value.toExponential(2) : value.toFixed(4);
}

function strength(observation: ReplicatedEvidenceObservation): number {
  return Math.min(
    Math.abs(observation.tcga.spearman_rho),
    Math.abs(observation.metabric.spearman_rho),
  );
}

function agreementDistance(observation: ReplicatedEvidenceObservation): number {
  return Math.abs(
    Math.abs(observation.tcga.spearman_rho) - Math.abs(observation.metabric.spearman_rho),
  );
}

function cohortMeasurement(
  label: string,
  measurement: ReplicatedEvidenceObservation['tcga'],
): HTMLElement {
  return el('div', { class: 'replication-cohort' }, [
    el('p', { class: 'replication-cohort-name' }, [label]),
    el('dl', {}, [
      el('div', {}, [el('dt', {}, ['samples']), el('dd', {}, [formatNumber(measurement.samples)])]),
      el('div', {}, [
        el('dt', {}, ['Spearman rho']),
        el('dd', {}, [measurement.spearman_rho.toFixed(4)]),
      ]),
      el('div', {}, [
        el('dt', {}, ['BH q, conservative']),
        el('dd', {}, [scientific(measurement.benjamini_hochberg_q_conservative)]),
      ]),
    ]),
  ]);
}

function observationCard(observation: ReplicatedEvidenceObservation): HTMLElement {
  const copyButton = el(
    'button',
    { class: 'audit-copy', type: 'button', title: 'Copy a link to this observation' },
    ['copy link'],
  ) as HTMLButtonElement;
  copyButton.addEventListener('click', async () => {
    const url = new URL(window.location.href);
    url.searchParams.set(
      'observation',
      `${observation.entities.a.symbol}--${observation.entities.b.symbol}`,
    );
    url.hash = 'replicated-evidence';
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

  return el('article', { class: 'replication-card' }, [
    el('div', { class: 'replication-card-header' }, [
      el('span', {}, [`#${String(observation.rank).padStart(3, '0')}`]),
      el('span', { class: `direction direction-${observation.direction}` }, [
        `${observation.direction} association`,
      ]),
    ]),
    el('div', { class: 'replication-pair' }, [
      el('div', {}, [
        el('strong', {}, [observation.entities.a.symbol]),
        el('span', {}, [`Entrez ${observation.entities.a.entrez_gene_id}`]),
      ]),
      el('span', { class: 'replication-link', 'aria-hidden': 'true' }, ['↔']),
      el('div', {}, [
        el('strong', {}, [observation.entities.b.symbol]),
        el('span', {}, [`Entrez ${observation.entities.b.entrez_gene_id}`]),
      ]),
    ]),
    el('div', { class: 'replication-cohorts' }, [
      cohortMeasurement('TCGA BRCA', observation.tcga),
      cohortMeasurement('METABRIC', observation.metabric),
    ]),
    el('details', { class: 'evidence-audit replication-audit' }, [
      el('summary', {}, ['Audit this observation']),
      el('div', { class: 'replication-claim' }, [
        el('div', { class: 'chips' }, [provenanceChip('generated')]),
        el('p', {}, [observation.generated_claim]),
        el('p', { class: 'audit-note' }, [`Scope: ${observation.claim_scope}.`]),
      ]),
      el('div', { class: 'audit-actions' }, [copyButton]),
    ]),
  ]);
}

function filterButton(label: string, value: DirectionFilter): HTMLButtonElement {
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

function explorer(evidence: ReplicatedEvidence): HTMLElement {
  const params = new URLSearchParams(window.location.search);
  const pairParam = params.get('observation')?.replace('--', ' ') ?? '';
  const search = el('input', {
    class: 'evidence-search',
    type: 'search',
    value: pairParam,
    placeholder: `Search ${formatNumber(evidence.counts.published_observations)} published observations…`,
    'aria-label': 'Search replicated observations by gene symbol or Entrez ID',
    autocomplete: 'off',
  }) as HTMLInputElement;
  const sort = el('select', { class: 'evidence-sort', 'aria-label': 'Sort observations' }, [
    el('option', { value: 'rank' }, ['frozen rank']),
    el('option', { value: 'strength' }, ['strongest minimum rho']),
    el('option', { value: 'agreement' }, ['closest cohort agreement']),
  ]) as HTMLSelectElement;
  const buttons = [
    filterButton('all directions', 'all'),
    filterButton('positive', 'positive'),
    filterButton('negative', 'negative'),
  ];
  const resultCount = el('p', { class: 'evidence-result-count', 'aria-live': 'polite' });
  const list = el('div', { class: 'replication-list' });
  const empty = el('div', { class: 'evidence-empty', hidden: '' }, [
    el('p', {}, ['No published observation matches this search.']),
    el('button', { class: 'button button-secondary', type: 'button' }, ['Clear filters']),
  ]);
  const more = el(
    'button',
    { class: 'button button-secondary evidence-more', type: 'button' },
    [`Show ${PAGE_SIZE} more`],
  ) as HTMLButtonElement;
  const exportButton = el(
    'button',
    { class: 'button button-secondary', type: 'button' },
    ['Export filtered CSV'],
  ) as HTMLButtonElement;
  let direction: DirectionFilter = 'all';
  let sortKey: SortKey = 'rank';
  let shown = PAGE_SIZE;
  let current: ReplicatedEvidenceObservation[] = [];

  function syncUrl(): void {
    const url = new URL(window.location.href);
    if (search.value.trim()) url.searchParams.set('observation', search.value.trim());
    else url.searchParams.delete('observation');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function update(): void {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    current = evidence.observations.filter((observation) => {
      if (direction !== 'all' && observation.direction !== direction) return false;
      const haystack = [
        observation.entities.a.symbol,
        observation.entities.a.entrez_gene_id,
        observation.entities.b.symbol,
        observation.entities.b.entrez_gene_id,
      ].join(' ').toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
    current.sort((a, b) => {
      if (sortKey === 'strength') return strength(b) - strength(a);
      if (sortKey === 'agreement') return agreementDistance(a) - agreementDistance(b);
      return a.rank - b.rank;
    });
    list.replaceChildren(...current.slice(0, shown).map(observationCard));
    resultCount.textContent =
      `${formatNumber(current.length)} observations match · showing ` +
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
  for (const button of buttons) {
    button.addEventListener('click', () => {
      direction = button.dataset.value as DirectionFilter;
      shown = PAGE_SIZE;
      for (const peer of buttons) peer.setAttribute('aria-pressed', String(peer === button));
      update();
    });
  }
  more.addEventListener('click', () => {
    shown += PAGE_SIZE;
    update();
  });
  exportButton.addEventListener('click', () => downloadCsv(current));
  (empty.querySelector('button') as HTMLButtonElement).addEventListener('click', () => {
    search.value = '';
    direction = 'all';
    shown = PAGE_SIZE;
    for (const button of buttons) {
      button.setAttribute('aria-pressed', String(button.dataset.value === 'all'));
    }
    syncUrl();
    update();
    search.focus();
  });

  const node = el('div', { class: 'evidence-explorer replication-explorer' }, [
    el('div', { class: 'evidence-toolbar' }, [
      search,
      el('div', { class: 'evidence-filter', 'aria-label': 'Filter by direction' }, buttons),
      sort,
    ]),
    el('div', { class: 'evidence-toolbar-meta' }, [resultCount, exportButton]),
    list,
    empty,
    more,
  ]);
  update();
  return node;
}

function metricCard(label: string, value: string, note: string): HTMLElement {
  return el('div', { class: 'replication-metric' }, [
    el('strong', {}, [value]),
    el('span', {}, [label]),
    el('p', {}, [note]),
  ]);
}

function gate(label: string, status: 'passed'): HTMLElement {
  return el('div', {}, [
    el('span', {}, [label]),
    el('strong', {}, [status]),
  ]);
}

export function renderReplicatedEvidence(
  evidence: ReplicatedEvidence,
  projectStatus: 'ready' | 'not_ready',
): HTMLElement {
  const tcga = evidence.cohorts[0];
  const metabric = evidence.cohorts[1];
  const sourceManifestPath = evidence.source_manifest.path.replace(/^\.\.\//, '');
  return el('section', { class: 'layer layer-replicated', id: 'replicated-evidence' }, [
    el('div', { class: 'section-kicker' }, ['REPLICATED EMPIRICAL EVIDENCE · V1']),
    el('h2', {}, ['Measured twice. Claimed narrowly.']),
    el('p', { class: 'blurb' }, [
      `The same frozen association gates passed for ${formatNumber(evidence.counts.replicated_pairs)} ` +
        `of ${formatNumber(evidence.counts.tested_pairs)} presealed gene pairs in two pinned ` +
        `breast-tumour expression cohorts. The strongest ${formatNumber(evidence.counts.published_observations)} ` +
        'observations are published below.',
    ]),
    el('div', { class: 'chips replication-chips' }, [
      provenanceChip('measured'),
      el('span', { class: 'chip chip-automated' }, [
        `${evidence.human_dependencies.length} human dependencies`,
      ]),
      el('span', { class: 'chip chip-automated' }, [
        evidence.llm_interpretation_used ? 'LLM interpretation used' : 'LLM interpretation off',
      ]),
      el('span', { class: 'chip chip-automated' }, [
        evidence.manual_override_used ? 'manual override used' : 'manual override off',
      ]),
      el('span', { class: 'chip chip-generated' }, [
        `gap detector: ${projectStatus.replace('_', ' ')}`,
      ]),
    ]),
    el('div', { class: 'replication-metrics', 'aria-label': 'Evidence protocol results' }, [
      metricCard('pairs tested', formatNumber(evidence.counts.tested_pairs), 'all pairs in the sealed gene subset'),
      metricCard('passed both cohorts', formatNumber(evidence.counts.replicated_pairs), 'same direction and frozen thresholds'),
      metricCard('published here', formatNumber(evidence.counts.published_observations), 'highest frozen ranks'),
      metricCard(
        'permuted-null passes',
        formatNumber(evidence.gates.null_pass_count),
        `registered ceiling: ${formatNumber(evidence.gates.maximum_null_pass_count)}`,
      ),
    ]),
    el('div', { class: 'replication-gates', 'aria-label': 'Machine gate status' }, [
      gate('source integrity', evidence.gates.source_integrity),
      gate('sample independence', evidence.gates.sample_independence),
      gate('power', evidence.gates.power),
      gate('null calibration', evidence.gates.null_calibration),
    ]),
    el('div', { class: 'replication-boundary' }, [
      el('div', {}, [
        el('p', { class: 'section-kicker' }, ['CLAIM BOUNDARY']),
        el('h3', {}, ['What this result can say']),
        el('p', {}, [`Only ${evidence.claim_boundary.allowed_claim}.`]),
      ]),
      el('div', {}, [
        el('h3', {}, ['What it cannot say']),
        el('ul', {}, evidence.claim_boundary.not_a_claim_of.map((claim) => el('li', {}, [claim]))),
      ]),
    ]),
    el('div', { class: 'replication-provenance' }, [
      el('div', {}, [
        el('span', {}, ['cohort 01']),
        el('strong', {}, [tcga?.study_id ?? 'TCGA BRCA']),
        el('p', {}, [
          tcga
            ? `${formatNumber(tcga.sample_count)} samples · ${formatNumber(tcga.analyzable_gene_count)} analyzable genes · ${tcga.platform}`
            : 'Pinned cohort metadata unavailable.',
        ]),
      ]),
      el('div', {}, [
        el('span', {}, ['cohort 02']),
        el('strong', {}, [metabric?.study_id ?? 'METABRIC']),
        el('p', {}, [
          metabric
            ? `${formatNumber(metabric.sample_count)} samples · ${formatNumber(metabric.analyzable_gene_count)} analyzable genes · ${metabric.platform}`
            : 'Pinned cohort metadata unavailable.',
        ]),
      ]),
      el('div', {}, [
        el('span', {}, ['byte-level replay']),
        el('strong', {}, [evidence.full_pair_table.committed ? 'committed' : 'local artifact required']),
        el('p', {}, [
          `${formatNumber(evidence.full_pair_table.row_count)} rows · SHA-256 ${evidence.full_pair_table.sha256}`,
        ]),
      ]),
    ]),
    el('div', { class: 'replication-actions' }, [
      el('a', { class: 'button button-primary', href: '/evidence-v1.json' }, [
        'Download versioned evidence JSON',
      ]),
      el('a', { class: 'button button-secondary', href: `${REPOSITORY}${PROTOCOL_PATH}` }, [
        'Inspect frozen protocol ↗',
      ]),
      el('a', { class: 'button button-secondary', href: `${REPOSITORY}${sourceManifestPath}` }, [
        'Inspect source manifest ↗',
      ]),
    ]),
    el('p', { class: 'replication-numeric-note' }, [
      `Numeric bound: ${evidence.numeric_bounds.policy}. Displayed BH q-values retain their ` +
        'conservative exported values.',
    ]),
    explorer(evidence),
    el('details', { class: 'replication-limitations' }, [
      el('summary', {}, ['Read all registered limitations']),
      el('ul', {}, evidence.limitations.map((limitation) => el('li', {}, [limitation]))),
    ]),
  ]);
}
