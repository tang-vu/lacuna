import { el, formatNumber, provenanceChip } from '../dom';
import type { ProjectStatus } from '../types';

const REPOSITORY = 'https://github.com/tang-vu/lacuna';

function total(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function progress(value: number, max: number, label: string): HTMLElement {
  return el('div', { class: 'mission-progress' }, [
    el('progress', {
      value: String(value),
      max: String(max),
      'aria-label': label,
    }),
    el('span', {}, [`${formatNumber(value)} / ${formatNumber(max)}`]),
  ]);
}

function mission(
  number: string,
  status: string,
  title: string,
  detail: string,
  progressNode: HTMLElement,
  action: string,
  href: string,
): HTMLElement {
  return el('article', { class: 'mission-card' }, [
    el('div', { class: 'mission-heading' }, [
      el('span', { class: 'status-number' }, [number]),
      el('span', { class: 'mission-state' }, [status]),
    ]),
    el('h3', {}, [title]),
    el('p', {}, [detail]),
    progressNode,
    el('a', { class: 'mission-link', href }, [action, ' ↗']),
  ]);
}

export function renderContributionMissions(status: ProjectStatus): HTMLElement {
  const sourceStatuses = Object.entries(status.historical_sources.statuses).filter(
    ([kind]) => kind === 'historical_records' || kind === 'historical_vocabulary',
  );
  const pinnedSources = sourceStatuses.filter(
    ([, sourceStatus]) => sourceStatus === 'available_pinned',
  ).length;
  const minimumCases =
    status.benchmark.requirements.minimum_per_kind *
    Object.keys(status.benchmark.counts).length;
  const currentCases = total(status.benchmark.counts);
  const minimumHeldout =
    status.benchmark.requirements.minimum_heldout_per_kind *
    Object.keys(status.benchmark.heldout_counts).length;
  const currentHeldout = total(status.benchmark.heldout_counts);
  const proposed = status.candidate_intake.counts.proposed;

  return el('section', { class: 'contribution-missions', id: 'contribute' }, [
    el('div', { class: 'section-kicker' }, ['THE OPEN WORK']),
    el('div', { class: 'contribution-heading' }, [
      el('div', {}, [
        el('h2', {}, ['Three missions before another metric runs.']),
        el('p', { class: 'status-intro' }, [
          'These are not roadmap vibes. They are generated from the source and benchmark ' +
            'contracts that currently stop metric v3 from running.',
        ]),
      ]),
      provenanceChip('generated'),
    ]),
    el('div', { class: 'mission-grid' }, [
      mission(
        '01',
        'BLOCKED',
        'Recover the records',
        `${pinnedSources} of ${sourceStatuses.length} required historical source gates are pinned. ` +
          `The ${status.historical_sources.required_years.join(', ')} MEDLINE citation releases ` +
          'remain the missing half.',
        progress(
          pinnedSources,
          sourceStatuses.length,
          'Required historical source gates pinned',
        ),
        'Join source recovery issue #6',
        `${REPOSITORY}/issues/6`,
      ),
      mission(
        '02',
        'DRAFT',
        'Build the benchmark',
        `${currentCases} of ${minimumCases} minimum cases are accepted; ${currentHeldout} of ` +
          `${minimumHeldout} required held-out cases are recorded. Plausibility alone does not count.`,
        progress(currentCases, minimumCases, 'Minimum benchmark cases accepted'),
        'See the v3 readiness milestone',
        `${REPOSITORY}/milestone/1`,
      ),
      mission(
        '03',
        'OPEN',
        'Review the queue',
        `${proposed} proposed candidates contribute zero to readiness until their cutoffs, ` +
          'mappings, and independent evidence survive review.',
        progress(
          status.candidate_intake.counts.accepted,
          status.candidate_intake.counts.accepted + proposed,
          'Accepted candidates among accepted and proposed intake entries',
        ),
        'Join candidate review issue #7',
        `${REPOSITORY}/issues/7`,
      ),
    ]),
    el('div', { class: 'contract-provenance' }, [
      el('span', {}, ['contract fingerprints']),
      ...Object.values(status.inputs).map((source) =>
        el('a', { href: `${REPOSITORY}/blob/main/${source.path}` }, [
          `${source.path} · ${source.sha256.slice(0, 10)}`,
        ]),
      ),
    ]),
  ]);
}
