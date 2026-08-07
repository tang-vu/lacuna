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
    readiness_blockers: string[];
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
