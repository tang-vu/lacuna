/** Shapes written by pipeline/export/build_artifacts.py. Kept in one place so a pipeline change
 * that reshapes an artifact fails typechecking here rather than rendering blank panels. */

export interface TaxonomyNode {
  id: string;
  display_name: string;
  works_count: number;
  domain?: string;
  field?: string;
  subfield?: string;
  description?: string;
}

export interface Taxonomy {
  domains: TaxonomyNode[];
  fields: TaxonomyNode[];
  subfields: TaxonomyNode[];
  topics: TaxonomyNode[];
}

export interface Source {
  label: string;
  url: string;
}

export interface CuratedEntry {
  id: string;
  title: string;
  summary: string;
  sources?: Source[];
  topics?: string[];
  posed?: number;
  /** blocked only: what stands in the way, given the question is already well-posed. */
  blocker?: 'instrumentation' | 'cost' | 'ethics' | 'timescale';
  /** blind-spots only. */
  severity?: 'partial' | 'total' | 'structural';
  measured?: Record<string, number>;
}

export interface Curated {
  open: CuratedEntry[];
  blocked: CuratedEntry[];
  'blind-spots': CuratedEntry[];
}

/** One scored topic pair. Every field here is measured or derived from measurement — none of it
 * is written by a person or a model, which is why it renders in the measured style. */
export interface Gap {
  topic_a: string;
  topic_b: string;
  name_a: string;
  name_b: string;
  observed: number;
  observed_kind: 'exact' | 'upper_bound';
  expected: number;
  s_a: number;
  s_b: number;
  similarity: number;
  p_value: number;
  deficit_bits: number;
  gap_score: number;
  /** The literal OpenAlex query a reader can run to check the count themselves. */
  verify_url: string;
  row_source_urls: string[];
}

export interface Validation {
  verdict: string;
  preregistration: string;
  report: string;
  target_pair: string[];
  target_percentile: number;
  required_percentile: number;
  negative_controls_pass: boolean | null;
  negative_controls_status: 'pass' | 'fail' | 'partial';
  negative_controls_evaluated: number;
  negative_controls_planned: number;
  summary: string;
}

export interface ComputedLayer {
  schema_version: number;
  status: string;
  validation: Validation;
  method: {
    version: string;
    closeness: string;
    bridge_k: number;
    slice: string;
    description: string;
  };
  coverage: {
    topics_swept: number;
    topics_in_analysis_set: number;
    pairs_scored: number;
    complete: boolean;
    note: string;
  };
  provenance: {
    inputs: InputFingerprints;
    total_works_query: string;
  };
  excluded_topics: { id: string; display_name: string; reason: string }[];
  gaps: Gap[];
}

export interface InputFingerprint {
  sha256: string;
  canonicalisation: string;
  rows?: number;
}

export interface InputFingerprints {
  taxonomy: InputFingerprint;
  cooccurrence_rows: InputFingerprint;
}

export interface Manifest {
  version: string;
  schema_version: number;
  source: string;
  snapshot: {
    date: string;
    slice: string;
    to_publication_date: string;
    total_works: number;
    inputs: InputFingerprints;
  };
  files: Record<string, InputFingerprint>;
  source_queries: {
    total_works: string;
    taxonomy_counts: Record<string, string>;
  };
  metric: { version: string; closeness: string; bridge_k: number };
  counts: Record<string, number>;
  computed_layer_status: string;
  computed_layer_verdict: string;
}

export interface ProjectStatus {
  schema_version: number;
  status: 'ready' | 'not_ready';
  inputs: Record<
    string,
    { path: string; sha256: string; canonicalisation: 'canonical-json-v1' }
  >;
  historical_sources: {
    ready: boolean;
    required_years: number[];
    inventory_metadata: {
      available: number;
      required: number;
      years: number[];
      scope: 'official inventory metadata only';
    };
    raw_record_releases: {
      pinned: number;
      required: number;
      years: number[];
    };
    preservation_metadata: {
      available: number;
      required: number;
      years: number[];
      scope: 'preserved repository directory metadata only';
    };
    statuses: Record<string, string>;
    provider_confirmation: {
      provider: 'NLM Support';
      received_on: string;
      scope: string;
    };
    readiness_blockers: string[];
  };
  source_alternatives: {
    status: 'no_equivalent_replacement_pinned';
    recommended_id: string;
    counts: Record<string, number>;
    readiness_contribution: 0;
    entries: Array<{
      id: string;
      label: string;
      status:
        | 'audited_scope_mismatch'
        | 'candidate_requires_acquisition_audit'
        | 'engineering_only'
        | 'rejected_for_historical_gate';
      readiness_contribution: 0;
      can_replace_original_gate: false;
      potential_role: string;
      blockers: string[];
      next_action: string;
      declared_snapshot?: {
        version_year: number;
        article_count: number;
        mesh_label_count: number;
      };
      semantics_protocol?: {
        path: string;
        sha256: string;
      };
      successor_semantics_protocol?: {
        path: string;
        sha256: string;
      };
      semantics_audit?: {
        path: string;
        sha256: string;
      };
      pilot_protocol?: {
        path: string;
        sha256: string;
      };
      snapshot_audit?: {
        path: string;
        sha256: string;
      };
    }>;
    bioasq_snapshot: {
      status: 'measured_unmatched_input';
      readiness_contribution: 0;
      input: {
        sha256: string;
        bytes: number;
      };
      measured: {
        article_count: number;
        mesh_assignment_count: number;
        distinct_mesh_label_count: number;
        publication_year_min: number;
        publication_year_max: number;
        publication_year_counts: Record<string, number>;
        noncanonical_year_count: number;
        unparseable_year_count: number;
      };
      declared_comparison: {
        articles_before_declared_publication_scope: number;
        articles_after_snapshot_version: number;
        matches_published_aggregate_counts: boolean;
        matches_published_publication_scope: boolean;
        passes_declared_snapshot_gate: boolean;
      };
    };
    bioasq_successor_protocol: {
      status: 'frozen_after_source_audit_before_semantics_selection';
      sampling: {
        total_sample_size: number;
        strata: Array<{
          id: string;
          year_min: number;
          year_max: number;
          sample_size: number;
        }>;
      };
      decision_rule: {
        readiness_contribution: 0;
      };
    };
    bioasq_semantics_audit: {
      status: 'bounded_corpus_semantics_audit';
      classification:
        | 'sample_consistent_with_all_assigned_descriptors'
        | 'semantics_unresolved';
      readiness_contribution: 0;
      sample: {
        selected_records: number;
      };
      maintained_current_pubmed_comparison: {
        records_requested: number;
        records_returned: number;
        record_return_fraction: number;
        overall: {
          records: number;
          bioasq_assignments: number;
          matched_current_all_descriptor_assignments: number;
          matched_current_major_topic_assignments: number;
          all_descriptor_assignment_match_fraction: number;
          major_topic_assignment_match_fraction: number;
        };
      };
      decision_checks: {
        passed: boolean;
      };
    };
    bioasq_pilot_protocol: {
      status: 'frozen_before_bioasq_pilot_metric';
      claim_boundary: {
        readiness_contribution: 0;
      };
      freeze_timing: {
        case_endpoint_support_counts_seen: false;
        bioasq_pilot_metric_formula_seen: false;
        bioasq_pilot_scores_or_ranks_seen: false;
      };
      case_population: {
        total_cases: number;
        split_counts: {
          development: number;
          heldout: number;
        };
        positives: {
          count: number;
        };
        controls: {
          counts: {
            hard_negative: { development: number; heldout: number };
            distant_negative: { development: number; heldout: number };
          };
        };
      };
      source_compatibility_gate: {
        required_case_count: number;
        failure_outcome: 'pilot_inconclusive_source_coverage';
      };
      heldout_decision_rule: {
        readiness_contribution: 0;
      };
    };
    bioasq_pilot_compatibility_audit: {
      status: 'primary_source_compatible_but_sensitivity_20_unevaluable';
      readiness_contribution: 0;
      measurement: {
        count_scope: 'exact_within_pinned_secondary_snapshot';
        article_count_scanned: number;
        mesh_assignment_count_scanned: number;
        cases: Array<{
          id: string;
          kind: string;
          split: 'development' | 'heldout';
          endpoint_a: { article_support: number };
          target_c: { article_support: number };
          direct_ac_article_count: number;
        }>;
      };
      decision: {
        primary_source_gate_status: 'source_compatible_for_separately_frozen_formula_contract';
        all_21_cases_primary_source_compatible: true;
        heldout_sensitivity_evaluable: Record<'5' | '10' | '20', boolean>;
        heldout_sensitivity_blockers: Record<'5' | '10' | '20', string[]>;
        frozen_heldout_rule_can_still_pass: false;
        metric_work_authorized_by_this_audit: false;
        readiness_contribution: 0;
      };
    };
    bioasq_pilot_successor_protocol: {
      status: 'frozen_after_source_compatibility_before_metric_formula';
      claim_boundary: { readiness_contribution: 0 };
      freeze_timing: {
        case_endpoint_support_counts_seen: true;
        bioasq_pilot_metric_formula_seen: false;
        bioasq_pilot_development_scores_or_ranks_seen: false;
        bioasq_pilot_heldout_scores_or_ranks_seen: false;
      };
      case_population: {
        total_cases: 21;
        split_counts: { development: 11; heldout: 10 };
      };
      source_compatibility: {
        primary_minimum_support_articles: 10;
        support_sensitivity_articles: [5];
        predecessor_support_20_blocker_ids: string[];
      };
    };
    bioasq_initial_formula_contract: {
      status: 'frozen_initial_before_development_metric_output';
      claim_boundary: {
        formula_class: 'article_level_mesh_jaccard_sum_of_path_minima';
        readiness_contribution: 0;
      };
      freeze_timing: {
        bioasq_development_metric_outputs_seen: false;
        bioasq_heldout_metric_outputs_seen: false;
      };
      edge_weight: { name: 'article_jaccard' };
      path_and_candidate_score: {
        path_formula: string;
        candidate_formula: string;
      };
      graph_contract: {
        threshold_runs: Array<{ name: string; minimum_support_articles: number }>;
      };
      execution_isolation: { revision_budget: 1 };
    };
  };
  candidate_intake: {
    counts: { accepted: number; proposed: number; rejected: number };
    accepted_benchmark_links: number;
    readiness_contribution: string;
    purpose: string;
    policy: {
      metric_blind: true;
      accepted_only_enters_benchmark: true;
      acceptance_requires_independent_replication: true;
    };
    entries: CandidateEntry[];
  };
  negative_candidate_queue: {
    counts: Record<NegativeCandidate['kind'], number>;
    heldout_counts: Record<NegativeCandidate['kind'], number>;
    readiness_contribution: 0;
    protocol_status: 'frozen_before_v3_metric';
    warning: string;
    context_warning: string;
    entries: NegativeCandidate[];
  };
  benchmark: {
    ready: boolean;
    requirements: {
      minimum_per_kind: number;
      minimum_heldout_per_kind: number;
      minimum_period_appropriate_heldout_cutoffs: number;
    };
    counts: {
      positive: number;
      hard_negative: number;
      distant_negative: number;
    };
    heldout_counts: {
      positive: number;
      hard_negative: number;
      distant_negative: number;
    };
    mapping_counts: Record<string, number>;
    period_appropriate_heldout_cutoffs: string[];
    readiness_blockers: string[];
  };
}

export interface NegativeCandidate {
  id: string;
  kind: 'hard_negative' | 'distant_negative';
  status: 'proposed';
  proposed_split: 'development' | 'heldout';
  selection_stage: 'pre_metric';
  cutoff: string;
  baseline_release_year: number;
  mapping_basis: 'pinned_production_year_vocabulary_candidate';
  concepts: {
    a: { descriptor_ui: string; descriptor_label: string; tree_number: string };
    c: { descriptor_ui: string; descriptor_label: string; tree_number: string };
  };
  selection_evidence: {
    shared_parent?: string;
    sibling_group_size?: number;
    branch_stratum?: [string, string];
  };
  negative_rationale: string;
  review_required: string[];
  review_context: {
    concepts: {
      a: NegativeConceptContext;
      c: NegativeConceptContext;
    };
    shared_parent?: {
      descriptor_ui: string;
      descriptor_label: string;
      tree_number: string;
    };
  };
}

export interface NegativeConceptContext {
  descriptor_ui: string;
  descriptor_label: string;
  tree_numbers: string[];
  entry_terms: string[];
  scope_notes: string[];
  annotations: string[];
}

export interface CandidateEvidence {
  role: string;
  label: string;
  url: string;
}

export interface CandidateMapping {
  descriptor_ui: string;
  descriptor_label: string;
  matched_term: string;
  match_basis: 'descriptor_label' | 'entry_term';
}

export interface CandidateEntry {
  id: string;
  proposed_kind: 'positive' | 'hard_negative' | 'distant_negative';
  status: 'accepted' | 'proposed' | 'rejected';
  selection_stage: 'pre_metric';
  candidate_cutoff?: string;
  source_time_window?: string;
  source_discovery_year?: number;
  source_cutoff_year?: number;
  source_baseline_release_year?: number;
  concepts: {
    a: { label: string; source_entity_id?: string };
    c: { label: string; source_entity_id?: string };
  };
  bridge?: { label: string; source_entity_id: string };
  mapping_audit?: {
    status: 'production_year_candidate';
    vocabulary_year: number;
    source_sha256: string;
    mappings: Record<string, CandidateMapping>;
    limitation: string;
  };
  evidence: CandidateEvidence[];
  open_questions?: string[];
  adjudication: {
    decision: CandidateEntry['status'];
    decided_on?: string;
    rationale: string;
  };
}
