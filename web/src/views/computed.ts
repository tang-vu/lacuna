import { el, formatNumber, provenanceChip } from '../dom';
import type { ComputedLayer, Gap } from '../types';

const GAPS_SHOWN = 60;
const REPOSITORY = 'https://github.com/tang-vu/lacuna/blob/main/';

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

function gapRow(gap: Gap, rank: number): HTMLElement {
  const ratio = gap.expected > 0 ? gap.observed / gap.expected : 0;
  const observed = `${gap.observed_kind === 'upper_bound' ? '≤' : ''}${formatNumber(gap.observed)}`;
  return el('tr', {}, [
    el('td', { class: 'rank' }, [String(rank)]),
    el('td', {}, [
      el('div', { class: 'pair' }, [gap.name_a]),
      el('div', { class: 'pair' }, [gap.name_b]),
    ]),
    el('td', { class: 'num', title: gap.observed_kind.replace('_', ' ') }, [observed]),
    el('td', { class: 'num' }, [gap.expected.toFixed(1)]),
    el('td', { class: 'num' }, [ratio.toFixed(2)]),
    el('td', { class: 'num' }, [gap.similarity.toFixed(3)]),
    el('td', {}, [
      el('a', { href: gap.verify_url, target: '_blank', rel: 'noreferrer', class: 'verify' }, [
        'check',
      ]),
    ]),
  ]);
}

export function renderComputed(computed: ComputedLayer): HTMLElement {
  const header = ['#', 'topic pair', 'observed', 'expected', 'obs/exp', 'closeness', 'query'];

  return el('section', { class: 'layer layer-computed' }, [
    el('h2', {}, ['Computed pairs']),
    el('p', { class: 'blurb' }, [
      'Topic pairs that co-occur less than chance predicts while sharing intermediate topics. ' +
        'This is the layer lacuna was built to produce, and it does not work yet.',
    ]),
    verdictBanner(computed),
    el('p', { class: 'method' }, [computed.method.description]),
    el('p', { class: 'method' }, [
      `Swept ${formatNumber(computed.coverage.topics_swept)} of ` +
        `${formatNumber(computed.coverage.topics_in_analysis_set)} topics. ${computed.coverage.note}`,
    ]),
    el('p', { class: 'method' }, [
      'The ≤ symbol marks an API-derived upper bound, not an observed count.',
    ]),
    el('div', { class: 'chips' }, [provenanceChip('measured')]),
    el('div', { class: 'table-scroll' }, [
      el('table', {}, [
        el('thead', {}, [el('tr', {}, header.map((label) => el('th', {}, [label])))]),
        el(
          'tbody',
          {},
          computed.gaps.slice(0, GAPS_SHOWN).map((gap, index) => gapRow(gap, index + 1)),
        ),
      ]),
    ]),
  ]);
}
