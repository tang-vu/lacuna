import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import test from 'node:test';

import { buildSharePages } from './build-share-pages.mjs';

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function sha256Payload(value) {
  return createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex');
}

async function fixture(curated) {
  const root = await mkdtemp(resolve(tmpdir(), 'lacuna-share-'));
  const artifacts = resolve(root, 'artifacts');
  const versionRoot = resolve(artifacts, '2026-08-04', 'fixture');
  const outDir = resolve(root, 'dist');
  await mkdir(versionRoot, { recursive: true });
  await writeFile(resolve(artifacts, 'latest.json'), JSON.stringify({ version: '2026-08-04/fixture' }));
  await writeFile(
    resolve(versionRoot, 'manifest.json'),
    JSON.stringify({
      version: '2026-08-04/fixture',
      files: { 'curated.json': { sha256: sha256Payload(curated) } },
    }),
  );
  await writeFile(resolve(versionRoot, 'curated.json'), JSON.stringify(curated));
  return { root, artifacts, outDir };
}

const curated = {
  open: [
    {
      id: 'question-a',
      title: 'Can A be < B & “C”?',
      summary: 'A sourced question with characters that must stay text, not markup.',
      sources: [{ label: 'Primary <source>', url: 'https://example.test/evidence' }],
      posed: 2024,
    },
  ],
  blocked: [
    {
      id: 'blocked-b',
      title: 'A blocked question',
      summary: 'The experiment is well posed, but the instrument does not exist.',
      blocker: 'instrumentation',
      sources: [{ label: 'Instrument source', url: 'https://example.test/instrument' }],
    },
  ],
  'blind-spots': [
    {
      id: 'blind-c',
      title: 'A declared blind spot',
      summary: 'The map cannot observe this source of knowledge.',
      severity: 'total',
      measured: { covered_items: 0 },
    },
  ],
};

test('generates escaped, crawlable hole pages and a complete sitemap', async () => {
  const paths = await fixture(curated);
  try {
    const result = await buildSharePages({ artifactRoot: paths.artifacts, outDir: paths.outDir });
    assert.deepEqual(result, { entries: 3, pages: 4, version: '2026-08-04/fixture' });
    const page = await readFile(resolve(paths.outDir, 'holes', 'question-a', 'index.html'), 'utf8');
    assert.match(page, /<link rel="canonical" href="https:\/\/lacuna\.tangvu\.dev\/holes\/question-a\/">/);
    assert.match(page, /Can A be &lt; B &amp; “C”\?/);
    assert.doesNotMatch(page, /Can A be < B/);
    assert.match(
      page,
      new RegExp(
        `written by a person · artifact 2026-08-04/fixture · SHA-256 ${sha256Payload(curated).slice(0, 16)}…`,
      ),
    );
    assert.match(page, /not a computed discovery or an actionable hypothesis/);
    assert.match(page, /\/2026-08-04\/fixture\/curated\.json/);
    assert.match(page, /data-share/);
    assert.match(page, /Primary &lt;source&gt;/);
    const atlas = await readFile(resolve(paths.outDir, 'holes', 'index.html'), 'utf8');
    assert.match(atlas, /3 versioned entries/);
    assert.match(atlas, /These entries are kept separate from the computed method that failed validation/);
    const sitemap = await readFile(resolve(paths.outDir, 'sitemap.xml'), 'utf8');
    assert.equal((sitemap.match(/<url>/g) ?? []).length, 5);
    assert.match(sitemap, /https:\/\/lacuna\.tangvu\.dev\/holes\/blind-c\//);
    const blind = await readFile(resolve(paths.outDir, 'holes', 'blind-c', 'index.html'), 'utf8');
    assert.match(blind, /MEASURED CONTEXT/);
    assert.match(blind, /--measured:#1d4e73/);
  } finally {
    await rm(paths.root, { recursive: true, force: true });
  }
});

test('rejects a curated artifact that no longer matches its manifest', async () => {
  const paths = await fixture(curated);
  try {
    const artifact = resolve(paths.artifacts, '2026-08-04', 'fixture', 'curated.json');
    const changed = structuredClone(curated);
    changed.open[0].summary = 'Changed after the manifest was pinned.';
    await writeFile(artifact, JSON.stringify(changed));
    await assert.rejects(
      buildSharePages({ artifactRoot: paths.artifacts, outDir: paths.outDir }),
      /curated\.json SHA-256 mismatch/,
    );
  } finally {
    await rm(paths.root, { recursive: true, force: true });
  }
});

test('rejects unsourced open questions and duplicate ids', async () => {
  const unsourced = structuredClone(curated);
  unsourced.open[0].sources = [];
  let paths = await fixture(unsourced);
  try {
    await assert.rejects(
      buildSharePages({ artifactRoot: paths.artifacts, outDir: paths.outDir }),
      /needs sources/,
    );
  } finally {
    await rm(paths.root, { recursive: true, force: true });
  }

  const duplicated = structuredClone(curated);
  duplicated.blocked[0].id = duplicated.open[0].id;
  paths = await fixture(duplicated);
  try {
    await assert.rejects(
      buildSharePages({ artifactRoot: paths.artifacts, outDir: paths.outDir }),
      /duplicate curated id/,
    );
  } finally {
    await rm(paths.root, { recursive: true, force: true });
  }
});
