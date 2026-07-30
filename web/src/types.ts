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
    statuses: Record<string, string>;
    readiness_blockers: string[];
  };
  candidate_intake: {
    counts: { accepted: number; proposed: number; rejected: number };
    accepted_benchmark_links: number;
    readiness_contribution: string;
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
