import { el, formatNumber, provenanceChip } from '../dom';
import type { CandidateEntry, NegativeCandidate, ProjectStatus } from '../types';

const REPOSITORY = 'https://github.com/tang-vu/lacuna';
type CandidateStatus = CandidateEntry['status'];
type NegativeKind = NegativeCandidate['kind'];

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

function candidatePath(candidate: CandidateEntry): HTMLElement {
  return el('div', { class: 'candidate-path', 'aria-label': 'Proposed literature path' }, [
    el('span', {}, [
      el('small', {}, ['A']),
      candidate.concepts.a.label,
    ]),
    el('span', { class: 'candidate-path-link', 'aria-hidden': 'true' }, ['→']),
    el('span', { class: 'candidate-bridge' }, [
      el('small', {}, ['B · bridge']),
      candidate.bridge?.label ?? 'not yet specified',
    ]),
    el('span', { class: 'candidate-path-link', 'aria-hidden': 'true' }, ['→']),
    el('span', {}, [
      el('small', {}, ['C']),
      candidate.concepts.c.label,
    ]),
  ]);
}

function copyCandidateButton(candidate: CandidateEntry): HTMLButtonElement {
  const button = el(
    'button',
    { class: 'candidate-copy', type: 'button' },
    ['copy review link'],
  ) as HTMLButtonElement;
  button.addEventListener('click', async () => {
    const url = new URL(window.location.href);
    url.searchParams.set('candidate', candidate.id);
    url.hash = 'review-desk';
    try {
      await navigator.clipboard.writeText(url.toString());
      button.textContent = 'link copied';
      window.setTimeout(() => {
        button.textContent = 'copy review link';
      }, 1600);
    } catch {
      button.textContent = 'copy failed';
    }
  });
  return button;
}

function candidateCard(candidate: CandidateEntry, selected: boolean): HTMLElement {
  const meta: HTMLElement[] = [
    provenanceChip('curated'),
    el('span', { class: `chip chip-candidate-${candidate.status}` }, [
      candidate.status === 'proposed'
        ? 'proposed · 0 readiness'
        : candidate.status,
    ]),
    el('span', { class: 'chip' }, [candidate.proposed_kind.replace('_', ' ')]),
  ];
  if (candidate.mapping_audit) {
    meta.push(
      el('span', { class: 'chip chip-mapping' }, [
        `${candidate.mapping_audit.vocabulary_year} vocabulary candidate`,
      ]),
    );
  }

  const timeline = candidate.candidate_cutoff
    ? `cutoff ${candidate.candidate_cutoff}`
    : candidate.source_cutoff_year
      ? `source-defined cutoff ${candidate.source_cutoff_year}`
      : candidate.source_time_window
        ? `source window ${candidate.source_time_window}`
        : 'cutoff unresolved';

  const body: HTMLElement[] = [
    el('div', { class: 'chips' }, meta),
    candidatePath(candidate),
    el('div', { class: 'candidate-meta' }, [
      el('span', {}, [timeline]),
      el('span', {}, [`selected ${candidate.selection_stage.replace('_', '-')}`]),
      el('span', {}, [`${candidate.evidence.length} evidence source(s)`]),
    ]),
  ];

  if (candidate.mapping_audit) {
    body.push(
      el('div', { class: 'candidate-mapping' }, [
        el('p', {}, [
          el('strong', {}, ['Mapping audit · ']),
          candidate.mapping_audit.limitation,
        ]),
        el(
          'dl',
          {},
          Object.entries(candidate.mapping_audit.mappings).flatMap(([role, mapping]) => [
            el('dt', {}, [role.toUpperCase()]),
            el('dd', {}, [`${mapping.descriptor_ui} · ${mapping.descriptor_label}`]),
          ]),
        ),
        el('code', {}, [
          `vocabulary SHA-256 ${candidate.mapping_audit.source_sha256.slice(0, 16)}…`,
        ]),
      ]),
    );
  }

  body.push(
    el('div', { class: 'candidate-evidence' }, [
      el('h4', {}, ['Evidence on record']),
      el(
        'ul',
        {},
        candidate.evidence.map((source) =>
          el('li', {}, [
            el('span', {}, [source.role.replace(/_/g, ' ')]),
            el('a', { href: source.url, target: '_blank', rel: 'noreferrer' }, [
              source.label,
              ' ↗',
            ]),
          ]),
        ),
      ),
    ]),
  );

  if (candidate.open_questions?.length) {
    body.push(
      el('div', { class: 'candidate-questions' }, [
        el('h4', {}, ['What review must settle']),
        el(
          'ol',
          {},
          candidate.open_questions.map((question) => el('li', {}, [question])),
        ),
      ]),
    );
  }

  body.push(
    el('div', { class: 'candidate-decision' }, [
      el('p', {}, [
        el('strong', {}, [`Current decision: ${candidate.adjudication.decision}. `]),
        candidate.adjudication.rationale,
      ]),
      el('div', { class: 'candidate-actions' }, [
        copyCandidateButton(candidate),
        el(
          'a',
          {
            href: `${REPOSITORY}/issues/7`,
            target: '_blank',
            rel: 'noreferrer',
          },
          ['Review in issue #7 ↗'],
        ),
      ]),
    ]),
  );

  return el('details', {
    class: 'candidate-card',
    id: `candidate-${candidate.id}`,
    ...(selected ? { open: '' } : {}),
  }, [
    el('summary', {}, [
      el('span', { class: 'candidate-index' }, [candidate.id]),
      el('span', { class: 'candidate-title' }, [
        candidate.concepts.a.label,
        el('span', { 'aria-hidden': 'true' }, [' × ']),
        candidate.concepts.c.label,
      ]),
      el('span', { class: `candidate-state candidate-state-${candidate.status}` }, [
        candidate.status,
      ]),
    ]),
    el('div', { class: 'candidate-body' }, body),
  ]);
}

function statusButton(
  status: CandidateStatus,
  count: number,
  active: boolean,
): HTMLButtonElement {
  return el(
    'button',
    {
      type: 'button',
      class: 'candidate-filter',
      'data-status': status,
      'aria-pressed': String(active),
    },
    [`${status} · ${formatNumber(count)}`],
  ) as HTMLButtonElement;
}

function renderCandidateDesk(status: ProjectStatus): HTMLElement {
  const selectedId = new URLSearchParams(window.location.search).get('candidate');
  const selected = status.candidate_intake.entries.find((entry) => entry.id === selectedId);
  let activeStatus: CandidateStatus = selected?.status ?? 'proposed';
  const search = el('input', {
    type: 'search',
    class: 'candidate-search',
    placeholder: 'Search concepts, bridges, IDs, or open questions…',
    'aria-label': 'Search benchmark intake candidates',
  }) as HTMLInputElement;
  const filters = (['proposed', 'accepted', 'rejected'] as const).map((candidateStatus) =>
    statusButton(
      candidateStatus,
      status.candidate_intake.counts[candidateStatus],
      candidateStatus === activeStatus,
    ),
  );
  const resultCount = el('p', { class: 'candidate-result-count', 'aria-live': 'polite' });
  const list = el('div', { class: 'candidate-list' });
  const empty = el('p', { class: 'candidate-empty', hidden: '' }, [
    'No intake record matches this search.',
  ]);

  function update(): void {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matching = status.candidate_intake.entries
      .filter((candidate) => candidate.status === activeStatus)
      .filter((candidate) => {
        const haystack = [
          candidate.id,
          candidate.concepts.a.label,
          candidate.concepts.c.label,
          candidate.bridge?.label ?? '',
          ...(candidate.open_questions ?? []),
        ]
          .join(' ')
          .toLowerCase();
        return terms.every((term) => haystack.includes(term));
      })
      .sort((a, b) => {
        if (a.id === selectedId) return -1;
        if (b.id === selectedId) return 1;
        return a.id.localeCompare(b.id);
      });
    list.replaceChildren(
      ...matching.map((candidate) => candidateCard(candidate, candidate.id === selectedId)),
    );
    resultCount.textContent =
      `${formatNumber(matching.length)} ${activeStatus} intake record` +
      `${matching.length === 1 ? '' : 's'}`;
    empty.hidden = matching.length > 0;
  }

  search.addEventListener('input', update);
  for (const button of filters) {
    button.addEventListener('click', () => {
      activeStatus = button.dataset.status as CandidateStatus;
      for (const peer of filters) {
        peer.setAttribute('aria-pressed', String(peer === button));
      }
      update();
    });
  }

  const node = el('section', { class: 'candidate-desk', id: 'review-desk' }, [
    el('div', { class: 'candidate-desk-heading' }, [
      el('div', {}, [
        el('div', { class: 'section-kicker' }, ['METRIC-BLIND REVIEW DESK']),
        el('h3', {}, ['Open the candidate ledger.']),
        el('p', {}, [
          status.candidate_intake.purpose,
        ]),
      ]),
      el('div', { class: 'chips' }, [
        provenanceChip('curated'),
        el('span', { class: 'chip chip-candidate-proposed' }, [
          'proposals count as 0',
        ]),
      ]),
    ]),
    el('div', { class: 'candidate-controls' }, [
      search,
      el('div', { class: 'candidate-filters', role: 'group', 'aria-label': 'Candidate status' }, filters),
    ]),
    resultCount,
    list,
    empty,
  ]);
  update();
  return node;
}

function negativeCard(candidate: NegativeCandidate, selected: boolean): HTMLElement {
  const evidence = candidate.kind === 'hard_negative'
    ? `shared parent ${candidate.selection_evidence.shared_parent} · ` +
      `${candidate.selection_evidence.sibling_group_size} eligible siblings`
    : `fixed branch stratum ${candidate.selection_evidence.branch_stratum?.join(' × ')}`;
  const issue = candidate.kind === 'hard_negative' ? 4 : 3;

  return el('details', {
    class: 'candidate-card negative-card',
    id: `control-${candidate.id}`,
    ...(selected ? { open: '' } : {}),
  }, [
    el('summary', {}, [
      el('span', { class: 'candidate-index' }, [candidate.id]),
      el('span', { class: 'candidate-title' }, [
        candidate.concepts.a.descriptor_label,
        el('span', { 'aria-hidden': 'true' }, [' × ']),
        candidate.concepts.c.descriptor_label,
      ]),
      el('span', { class: 'candidate-state candidate-state-proposed' }, [
        candidate.kind.replace('_', ' '),
      ]),
    ]),
    el('div', { class: 'candidate-body' }, [
      el('div', { class: 'chips' }, [
        provenanceChip('generated'),
        el('span', { class: 'chip chip-candidate-proposed' }, ['proposed · 0 readiness']),
        el('span', { class: 'chip' }, [candidate.proposed_split]),
        el('span', { class: 'chip chip-mapping' }, [
          `${candidate.baseline_release_year} vocabulary candidate`,
        ]),
      ]),
      el('div', { class: 'candidate-path negative-path', 'aria-label': 'Generated descriptor pair' }, [
        el('span', {}, [
          el('small', {}, [`A · ${candidate.concepts.a.descriptor_ui}`]),
          candidate.concepts.a.descriptor_label,
          el('code', {}, [candidate.concepts.a.tree_number]),
        ]),
        el('span', { class: 'candidate-path-link', 'aria-hidden': 'true' }, ['×']),
        el('span', {}, [
          el('small', {}, [`C · ${candidate.concepts.c.descriptor_ui}`]),
          candidate.concepts.c.descriptor_label,
          el('code', {}, [candidate.concepts.c.tree_number]),
        ]),
      ]),
      el('div', { class: 'candidate-meta' }, [
        el('span', {}, [`cutoff ${candidate.cutoff}`]),
        el('span', {}, [evidence]),
        el('span', {}, ['selected pre-metric']),
      ]),
      el('div', { class: 'candidate-questions' }, [
        el('h4', {}, ['Why it entered the review queue']),
        el('p', {}, [candidate.negative_rationale]),
        el('h4', {}, ['Human review required']),
        el('ol', {}, candidate.review_required.map((item) => el('li', {}, [item]))),
      ]),
      el('details', { class: 'candidate-context' }, [
        el('summary', {}, ['Inspect pinned MeSH review context']),
        el('p', { class: 'candidate-context-warning' }, [
          'Generated vocabulary context; zero readiness; not human adjudication.',
        ]),
        ...(['a', 'c'] as const).map((role) => {
          const context = candidate.review_context.concepts[role];
          return el('div', { class: 'candidate-context-concept' }, [
            el('h4', {}, [`${role.toUpperCase()} · ${context.descriptor_label}`]),
            ...context.scope_notes.map((note) => el('p', {}, [note])),
            context.entry_terms.length
              ? el('p', { class: 'candidate-context-terms' }, [
                  `Entry terms: ${context.entry_terms.join('; ')}`,
                ])
              : null,
            context.annotations.length
              ? el('p', { class: 'candidate-context-terms' }, [
                  `MeSH annotation: ${context.annotations.join(' · ')}`,
                ])
              : null,
          ].filter((node): node is HTMLElement => node !== null));
        }),
        candidate.review_context.shared_parent
          ? el('p', { class: 'candidate-context-parent' }, [
              `Shared parent: ${candidate.review_context.shared_parent.descriptor_label} · ${candidate.review_context.shared_parent.tree_number}`,
            ])
          : null,
      ].filter((node): node is HTMLElement => node !== null)),
      el('div', { class: 'candidate-decision' }, [
        el('p', {}, [
          el('strong', {}, ['Generated proposal · ']),
          'This record is not in the benchmark and makes no absence claim.',
        ]),
        el('div', { class: 'candidate-actions' }, [
          el('a', {
            href: `${REPOSITORY}/issues/${issue}`,
            target: '_blank',
            rel: 'noreferrer',
          }, [`Review in issue #${issue} ↗`]),
        ]),
      ]),
    ]),
  ]);
}

function renderNegativeQueue(status: ProjectStatus): HTMLElement {
  const selectedId = new URLSearchParams(window.location.search).get('control');
  const selected = status.negative_candidate_queue.entries.find((entry) => entry.id === selectedId);
  let activeKind: NegativeKind = selected?.kind ?? 'hard_negative';
  const search = el('input', {
    type: 'search',
    class: 'candidate-search',
    placeholder: 'Search generated concepts, IDs, or tree numbers…',
    'aria-label': 'Search generated negative-control proposals',
  }) as HTMLInputElement;
  const kinds = (['hard_negative', 'distant_negative'] as const);
  const filters = kinds.map((kind) =>
    el('button', {
      type: 'button',
      class: 'candidate-filter',
      'data-kind': kind,
      'aria-pressed': String(kind === activeKind),
    }, [`${kind.replace('_', ' ')} · ${status.negative_candidate_queue.counts[kind]}`]) as HTMLButtonElement,
  );
  const resultCount = el('p', { class: 'candidate-result-count', 'aria-live': 'polite' });
  const list = el('div', { class: 'candidate-list' });
  const empty = el('p', { class: 'candidate-empty', hidden: '' }, [
    'No generated proposal matches this search.',
  ]);

  function update(): void {
    const terms = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matching = status.negative_candidate_queue.entries
      .filter((candidate) => candidate.kind === activeKind)
      .filter((candidate) => {
        const haystack = [
          candidate.id,
          candidate.concepts.a.descriptor_ui,
          candidate.concepts.a.descriptor_label,
          candidate.concepts.a.tree_number,
          candidate.concepts.c.descriptor_ui,
          candidate.concepts.c.descriptor_label,
          candidate.concepts.c.tree_number,
          candidate.negative_rationale,
        ].join(' ').toLowerCase();
        return terms.every((term) => haystack.includes(term));
      })
      .sort((a, b) => {
        if (a.id === selectedId) return -1;
        if (b.id === selectedId) return 1;
        return a.id.localeCompare(b.id);
      });
    list.replaceChildren(
      ...matching.map((candidate) => negativeCard(candidate, candidate.id === selectedId)),
    );
    resultCount.textContent = `${matching.length} generated ${activeKind.replace('_', ' ')} proposals`;
    empty.hidden = matching.length > 0;
  }

  search.addEventListener('input', update);
  for (const button of filters) {
    button.addEventListener('click', () => {
      activeKind = button.dataset.kind as NegativeKind;
      for (const peer of filters) peer.setAttribute('aria-pressed', String(peer === button));
      update();
    });
  }

  const node = el('section', { class: 'candidate-desk negative-desk', id: 'control-desk' }, [
    el('div', { class: 'candidate-desk-heading' }, [
      el('div', {}, [
        el('div', { class: 'section-kicker' }, ['METRIC-BLIND CONTROL QUEUE']),
        el('h3', {}, ['Review generated negatives before they count.']),
        el('p', {}, [status.negative_candidate_queue.warning]),
      ]),
      el('div', { class: 'chips' }, [
        provenanceChip('generated'),
        el('span', { class: 'chip chip-candidate-proposed' }, ['16 proposals · 0 readiness']),
      ]),
    ]),
    el('div', { class: 'candidate-controls' }, [
      search,
      el('div', { class: 'candidate-filters', role: 'group', 'aria-label': 'Negative-control kind' }, filters),
    ]),
    resultCount,
    list,
    empty,
  ]);
  update();
  return node;
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
  const recommendedAlternative = status.source_alternatives.entries.find(
    (entry) => entry.id === status.source_alternatives.recommended_id,
  );
  const snapshot = status.source_alternatives.bioasq_snapshot;
  const successorProtocol = status.source_alternatives.bioasq_successor_protocol;
  const semanticsAudit = status.source_alternatives.bioasq_semantics_audit;
  const semanticsOverall = semanticsAudit.maintained_current_pubmed_comparison.overall;
  const pilot = status.source_alternatives.bioasq_pilot_protocol;
  const compatibility = status.source_alternatives.bioasq_pilot_compatibility_audit;
  const pilotV2 = status.source_alternatives.bioasq_pilot_successor_protocol;
  const initialFormula = status.source_alternatives.bioasq_initial_formula_contract;
  const sensitivityBlockerId = compatibility.decision.heldout_sensitivity_blockers['20'][0];
  const sensitivityBlocker = compatibility.measurement.cases.find(
    (entry) => entry.id === sensitivityBlockerId,
  );

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
        'OPEN',
        'Resolve the dated snapshot',
        `NLM confirmed on ${status.historical_sources.provider_confirmation.received_on} that ` +
          'previous annual baselines are unavailable. ' +
          `${status.historical_sources.inventory_metadata.available} of ` +
          `${status.historical_sources.inventory_metadata.required} official file inventories are ` +
          `pinned; ${status.historical_sources.raw_record_releases.pinned} of ` +
          `${status.historical_sources.raw_record_releases.required} raw citation releases are. ` +
          `${status.historical_sources.preservation_metadata.available} historical MBR directory ` +
          'rows are preserved; metadata is a target, not the records. ' +
          `${recommendedAlternative?.label ?? 'The recommended secondary snapshot'} is pinned ` +
          `at ${snapshot.measured.article_count.toLocaleString()} records. Its three published ` +
          'aggregate counts match, but ' +
          `${snapshot.declared_comparison.articles_before_declared_publication_scope.toLocaleString()} ` +
          'records predate the reported post-1949 scope and ' +
          `${snapshot.measured.noncanonical_year_count.toLocaleString()} year values use an ` +
          'explicit non-YYYY normalization rule. ' +
          `A separately named ${successorProtocol.sampling.total_sample_size.toLocaleString()}-record ` +
          'successor protocol retained the original thresholds. Its bounded maintained-current ' +
          `comparison returned ${semanticsAudit.maintained_current_pubmed_comparison.records_returned} of ` +
          `${semanticsAudit.maintained_current_pubmed_comparison.records_requested} records: ` +
          `${semanticsOverall.matched_current_all_descriptor_assignments.toLocaleString()} of ` +
          `${semanticsOverall.bioasq_assignments.toLocaleString()} assignments matched all ` +
          'descriptors, versus ' +
          `${semanticsOverall.matched_current_major_topic_assignments.toLocaleString()} major-topic ` +
          `matches. The frozen sample rule ${semanticsAudit.decision_checks.passed ? 'passed' : 'did not pass'}, ` +
          'but this is neither population-weighted nor period-appropriate. A separate ' +
          `${pilot.case_population.total_cases}-case pilot is now frozen with ` +
          `${pilot.case_population.split_counts.development} development and ` +
          `${pilot.case_population.split_counts.heldout} held-out cases before support counts or ` +
          'formula selection. Its LION targets are source-labelled and its controls remain ' +
          'ontology-generated proposals. The full score-free scan found all 21 cases eligible at ' +
          'the primary support of 10, but held-out hard control ' +
          `${sensitivityBlockerId ?? 'unknown'} has target support ` +
          `${sensitivityBlocker?.target_c.article_support ?? 'unknown'} and is therefore ineligible ` +
          'at sensitivity 20. The predecessor cannot pass and its audit does not authorize metric ' +
          'work. A separately named source-informed successor preserves all 21 cases, discloses ' +
          'the known source counts, and uses primary support ' +
          `${pilotV2.source_compatibility.primary_minimum_support_articles} plus sensitivity ` +
          `${pilotV2.source_compatibility.support_sensitivity_articles.join(', ')}. Its initial ` +
          `formula is now frozen as ${initialFormula.edge_weight.name} edge weights, minimum ` +
          'A–B–C path aggregation, and sum accumulation across B. The next permitted run is the ' +
          '11 development cases only; held-out output remains prohibited until a final formula ' +
          'freeze. No metric output exists, and every BioASQ layer still contributes zero readiness.',
        progress(
          pinnedSources,
          sourceStatuses.length,
          'Required historical source gates pinned',
        ),
        'Join source redesign issue #6',
        `${REPOSITORY}/issues/6`,
      ),
      mission(
        '02',
        'DRAFT',
        'Build the benchmark',
        `${currentCases} of ${minimumCases} minimum cases are accepted; ${currentHeldout} of ` +
          `${minimumHeldout} required held-out cases are recorded. The generated negative queue ` +
          `contains ${total(status.negative_candidate_queue.counts)} proposals and contributes zero.`,
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
    renderNegativeQueue(status),
    renderCandidateDesk(status),
  ]);
}
