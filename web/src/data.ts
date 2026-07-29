import type { ComputedLayer, Curated, Manifest, Taxonomy } from './types';

export interface Dataset {
  manifest: Manifest;
  taxonomy: Taxonomy;
  curated: Curated;
  computed: ComputedLayer;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`could not load ${path} (${response.status})`);
  }
  return (await response.json()) as T;
}

/** Resolve the current artifact version, then load that version's files.
 *
 * The indirection through latest.json means the site always reads a complete, self-consistent
 * set: publishing a new version never leaves the page mixing files from two sweeps. */
export async function loadDataset(): Promise<Dataset> {
  const { version } = await fetchJson<{ version: string }>('/latest.json');
  const [manifest, taxonomy, curated, computed] = await Promise.all([
    fetchJson<Manifest>(`/${version}/manifest.json`),
    fetchJson<Taxonomy>(`/${version}/taxonomy.json`),
    fetchJson<Curated>(`/${version}/curated.json`),
    fetchJson<ComputedLayer>(`/${version}/computed-gaps.json`),
  ]);
  if (manifest.version !== version) {
    throw new Error(`artifact version mismatch: latest=${version}, manifest=${manifest.version}`);
  }
  if (computed.method.version !== manifest.metric.version) {
    throw new Error(
      `metric version mismatch: manifest=${manifest.metric.version}, computed=${computed.method.version}`,
    );
  }
  return { manifest, taxonomy, curated, computed };
}
