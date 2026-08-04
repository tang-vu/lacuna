import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = 'https://lacuna.tangvu.dev';
const REPOSITORY = 'https://github.com/tang-vu/lacuna';
const SOCIAL_CARD = `${SITE}/social-card.png`;
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_ARTIFACT_ROOT = resolve(SCRIPT_DIR, '../../artifacts');
const DEFAULT_OUT_DIR = resolve(SCRIPT_DIR, '../dist');
const ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

class CanonicalNumber {
  constructor(value, source) {
    this.value = value;
    this.source = source;
  }
}

const LAYERS = {
  open: {
    label: 'curated open question',
    eyebrow: 'CURATED OPEN QUESTION',
    sourceFile: 'curated/open.json',
    accent: '#1d4e73',
  },
  blocked: {
    label: 'curated blocked question',
    eyebrow: 'CURATED BLOCKED QUESTION',
    sourceFile: 'curated/blocked.json',
    accent: '#8a3d12',
  },
  'blind-spots': {
    label: 'declared coverage blind spot',
    eyebrow: 'DECLARED COVERAGE BLIND SPOT',
    sourceFile: 'curated/blind-spots.json',
    accent: '#654875',
  },
};

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function jsonForHtml(value) {
  return JSON.stringify(value)
    .replaceAll('<', '\\u003c')
    .replaceAll('>', '\\u003e')
    .replaceAll('&', '\\u0026');
}

function canonicalJson(value) {
  if (value instanceof CanonicalNumber) {
    requireValue(Number.isFinite(value.value), 'canonical JSON cannot contain a non-finite number');
    requireValue(!/[eE]/.test(value.source), 'scientific notation is not supported by canonical-json-v1 in this builder');
    if (value.source.includes('.')) {
      return Number.isInteger(value.value) ? `${JSON.stringify(value.value)}.0` : JSON.stringify(value.value);
    }
    requireValue(Number.isSafeInteger(value.value), 'canonical JSON integer exceeds JavaScript safe range');
    return JSON.stringify(value.value);
  }
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

function sha256CanonicalJson(source) {
  const payload = JSON.parse(source, (key, value, context) => {
    if (typeof value !== 'number') return value;
    requireValue(
      context && typeof context.source === 'string',
      'Node.js with JSON.parse source context is required to verify canonical-json-v1',
    );
    return new CanonicalNumber(value, context.source);
  });
  return sha256Payload(payload);
}

function excerpt(value, maximum = 210) {
  const text = String(value).replace(/\s+/g, ' ').trim();
  if (text.length <= maximum) return text;
  const prefix = text.slice(0, maximum - 1);
  const boundary = prefix.lastIndexOf(' ');
  return `${prefix.slice(0, boundary > maximum * 0.7 ? boundary : undefined)}…`;
}

function sourceUrl(url) {
  return /^https:\/\//.test(url) ? url : `${REPOSITORY}/blob/main/${url}`;
}

function validateEntry(entry, layer, seen) {
  requireValue(entry && typeof entry === 'object', `${layer}: entry must be an object`);
  requireValue(typeof entry.id === 'string' && ID.test(entry.id), `${layer}: unsafe entry id`);
  requireValue(!seen.has(entry.id), `${entry.id}: duplicate curated id`);
  seen.add(entry.id);
  requireValue(typeof entry.title === 'string' && entry.title.trim(), `${entry.id}: missing title`);
  requireValue(
    typeof entry.summary === 'string' && entry.summary.trim(),
    `${entry.id}: missing summary`,
  );
  if (layer === 'open' || layer === 'blocked') {
    requireValue(
      Array.isArray(entry.sources) && entry.sources.length > 0,
      `${entry.id}: curated open/blocked entry needs sources`,
    );
  }
  if (entry.sources !== undefined) {
    requireValue(Array.isArray(entry.sources), `${entry.id}: sources must be an array`);
    for (const source of entry.sources) {
      requireValue(
        source && typeof source.label === 'string' && source.label.trim(),
        `${entry.id}: source missing label`,
      );
      requireValue(
        typeof source.url === 'string' && (/^https:\/\//.test(source.url) || !source.url.includes(':')),
        `${entry.id}: source URL must be HTTPS or repository-relative`,
      );
    }
  }
  if (entry.measured !== undefined) {
    requireValue(
      entry.measured &&
        typeof entry.measured === 'object' &&
        Object.values(entry.measured).every((value) => Number.isFinite(value)),
      `${entry.id}: measured context must contain finite numbers`,
    );
  }
  return { ...entry, layer };
}

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

async function loadEntries(artifactRoot) {
  const root = resolve(artifactRoot);
  const latest = await readJson(resolve(root, 'latest.json'));
  requireValue(
    typeof latest.version === 'string' && /^[0-9]{4}-[0-9]{2}-[0-9]{2}\/[a-z0-9-]+$/.test(latest.version),
    'latest artifact version is malformed',
  );
  const versionRoot = resolve(root, ...latest.version.split('/'));
  requireValue(
    versionRoot.startsWith(`${root}${sep}`),
    'latest artifact version escapes the artifact root',
  );
  const [manifest, curatedSource] = await Promise.all([
    readJson(resolve(versionRoot, 'manifest.json')),
    readFile(resolve(versionRoot, 'curated.json'), 'utf8'),
  ]);
  const curated = JSON.parse(curatedSource);
  requireValue(manifest.version === latest.version, 'latest and manifest versions differ');
  const curatedSha = manifest.files?.['curated.json']?.sha256;
  requireValue(
    typeof curatedSha === 'string' && /^[0-9a-f]{64}$/.test(curatedSha),
    'manifest does not pin curated.json with SHA-256',
  );
  requireValue(curated && typeof curated === 'object', 'curated artifact must be an object');
  const actualCuratedSha = sha256CanonicalJson(curatedSource);
  requireValue(
    actualCuratedSha === curatedSha,
    `curated.json SHA-256 mismatch (${actualCuratedSha} != ${curatedSha})`,
  );

  const seen = new Set();
  const entries = [];
  for (const layer of Object.keys(LAYERS)) {
    requireValue(Array.isArray(curated[layer]), `curated artifact missing ${layer}`);
    for (const entry of curated[layer]) entries.push(validateEntry(entry, layer, seen));
  }
  requireValue(entries.length > 0, 'curated artifact contains no shareable holes');
  return { entries, version: latest.version, curatedSha };
}

function pageStyles(accent = '#1d4e73') {
  return `
    :root{--bg:#fbfaf7;--fg:#1c1b19;--muted:#6b6862;--rule:#ddd9d0;--accent:${accent};--card:#fff;--measured:#1d4e73;--measured-bg:#eef4f9}
    @media(prefers-color-scheme:dark){:root{--bg:#16151a;--fg:#e9e6e0;--muted:#aaa49a;--rule:#3c3842;--card:#1e1d23;--measured:#8fc4ea;--measured-bg:#172733}}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.65 Charter,Georgia,serif}
    a{color:inherit}.shell{width:min(52rem,calc(100% - 2.5rem));margin:auto}.topbar{display:flex;justify-content:space-between;align-items:center;min-height:4.5rem;border-bottom:1px solid var(--rule);font:700 .78rem ui-monospace,monospace}.topbar a{text-decoration:none}.wordmark{font-size:1.2rem;letter-spacing:-.06em}.topbar nav{display:flex;gap:1rem}
    main{padding:clamp(4rem,10vw,7rem) 0 5rem}.eyebrow{margin:0 0 1rem;color:var(--accent);font:.72rem ui-monospace,monospace;letter-spacing:.14em}.provenance{display:inline-block;margin-bottom:1rem;padding:.2rem .55rem;border:1px solid var(--rule);border-radius:99px;color:var(--muted);font:.7rem ui-monospace,monospace}h1{max-width:48rem;margin:0;font-size:clamp(2.8rem,8vw,5.6rem);line-height:.96;letter-spacing:-.055em}.summary{max-width:46rem;margin:1.75rem 0;font-size:clamp(1.12rem,2.4vw,1.4rem);line-height:1.55}.honesty{margin:2rem 0;padding:1rem 1.1rem;border-left:4px solid var(--accent);background:var(--card);color:var(--muted)}
    .facts,.measured{display:grid;grid-template-columns:auto 1fr;gap:.25rem 1rem;width:max-content;max-width:100%;padding:1rem;border:1px solid var(--rule);background:var(--card);font:.78rem ui-monospace,monospace}.facts dt,.measured dt{color:var(--muted)}.facts dd,.measured dd{margin:0}.measured-context{margin-top:1rem}.measured-context>p{margin:0 0 .35rem;color:var(--measured);font:.66rem ui-monospace,monospace;letter-spacing:.1em}.measured{margin:0;color:var(--measured);background:var(--measured-bg);border-color:var(--measured)}
    .actions{display:flex;flex-wrap:wrap;gap:.6rem;margin:2rem 0}.button{border:1px solid var(--fg);border-radius:3px;padding:.65rem .85rem;background:transparent;color:var(--fg);font:.76rem ui-monospace,monospace;text-decoration:none;cursor:pointer}.button-primary{background:var(--fg);color:var(--bg)}.button:hover{border-color:var(--accent);color:var(--accent)}.button-primary:hover{background:var(--accent);color:var(--bg)}
    .evidence{margin-top:4rem;padding-top:2rem;border-top:1px solid var(--rule)}.evidence h2{font-size:1.5rem}.evidence li{margin:.55rem 0}.source-note{color:var(--muted)}footer{padding:1.5rem 0 3rem;border-top:1px solid var(--rule);color:var(--muted);font:.72rem ui-monospace,monospace}
    .atlas-list{display:grid;gap:.75rem;margin-top:2.5rem}.atlas-item{display:block;padding:1rem 1.1rem;border:1px solid var(--rule);border-left:4px solid var(--entry-accent);background:var(--card);text-decoration:none}.atlas-item strong{display:block;font-size:1.08rem}.atlas-item span{display:block;margin-top:.25rem;color:var(--muted);font-size:.92rem}.atlas-item small{color:var(--entry-accent);font:.65rem ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}
    @media(max-width:38rem){.topbar nav a:first-child{display:none}.facts,.measured{width:100%}h1{font-size:clamp(2.7rem,14vw,4rem)}}`;
}

function factsHtml(entry) {
  const facts = [];
  if (entry.posed) facts.push(['posed', entry.posed]);
  if (entry.blocker) facts.push(['blocked by', entry.blocker]);
  if (entry.severity) facts.push(['coverage severity', entry.severity]);
  if (!facts.length) return '';
  return `<dl class="facts">${facts
    .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`)
    .join('')}</dl>`;
}

function measuredHtml(entry) {
  if (!entry.measured) return '';
  return `<section class="measured-context"><p>MEASURED CONTEXT</p><dl class="measured">${Object.entries(entry.measured)
    .map(
      ([label, value]) =>
        `<dt>${escapeHtml(label.replaceAll('_', ' '))}</dt><dd>${Number(value).toLocaleString('en-US')}</dd>`,
    )
    .join('')}</dl></section>`;
}

function sourcesHtml(entry) {
  if (!entry.sources?.length) {
    return '<p class="source-note">No external source is attached to this declared project limitation; inspect the versioned source record below.</p>';
  }
  return `<ul>${entry.sources
    .map(
      (source) =>
        `<li><a href="${escapeHtml(sourceUrl(source.url))}" rel="noreferrer">${escapeHtml(source.label)} ↗</a></li>`,
    )
    .join('')}</ul>`;
}

function shellHeader() {
  return `<header class="shell topbar"><a class="wordmark" href="/">lacuna</a><nav aria-label="Project"><a href="/holes/">hole atlas</a><a href="${REPOSITORY}">GitHub ↗</a></nav></header>`;
}

function renderHolePage(entry, version, curatedSha) {
  const layer = LAYERS[entry.layer];
  const canonical = `${SITE}/holes/${entry.id}/`;
  const description = excerpt(entry.summary);
  const title = `${entry.title} — ${layer.label} | lacuna`;
  const sourceRecord = `${REPOSITORY}/blob/main/${layer.sourceFile}`;
  const structured = {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    '@id': canonical,
    url: canonical,
    name: entry.title,
    description: entry.summary,
    isPartOf: { '@id': `${SITE}/#website` },
    inLanguage: 'en',
    citation: (entry.sources ?? []).map((source) => sourceUrl(source.url)),
  };
  const sharePayload = jsonForHtml({ title: entry.title, text: description, url: canonical });
  const artifactUrl = `${SITE}/${version}/curated.json`;
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)}</title><meta name="description" content="${escapeHtml(description)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="${canonical}"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><meta name="theme-color" content="#fbfaf7">
<meta property="og:type" content="article"><meta property="og:site_name" content="lacuna"><meta property="og:title" content="${escapeHtml(entry.title)}"><meta property="og:description" content="${escapeHtml(description)}"><meta property="og:url" content="${canonical}"><meta property="og:image" content="${SOCIAL_CARD}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="A network of knowledge surrounding an empty lacuna.">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${escapeHtml(entry.title)}"><meta name="twitter:description" content="${escapeHtml(description)}"><meta name="twitter:image" content="${SOCIAL_CARD}"><script type="application/ld+json">${jsonForHtml(structured)}</script><style>${pageStyles(layer.accent)}</style></head>
<body>${shellHeader()}<main class="shell"><p class="eyebrow">${layer.eyebrow}</p><span class="provenance">written by a person · artifact ${escapeHtml(version)} · SHA-256 ${curatedSha.slice(0, 16)}…</span><h1>${escapeHtml(entry.title)}</h1><p class="summary">${escapeHtml(entry.summary)}</p>${factsHtml(entry)}${measuredHtml(entry)}<p class="honesty">This is a sourced, human-curated entry or a declared project limitation. It is not a computed discovery or an actionable hypothesis.</p><div class="actions"><a class="button button-primary" href="/#hole-${entry.id}">Open in the full map</a><button class="button" type="button" data-share>Share this hole</button><a class="button" href="${artifactUrl}">Inspect build input</a><a class="button" href="${sourceRecord}">Inspect source record ↗</a><a class="button" href="${REPOSITORY}/issues/new?template=curated-hole.yml">Propose a sourced hole ↗</a></div><section class="evidence"><h2>Trace the claim</h2>${sourcesHtml(entry)}</section></main><footer class="shell">Open source. Provenance first. Failed methods stay visible. <a href="${REPOSITORY}">Star or fork lacuna ↗</a></footer><script>const b=document.querySelector('[data-share]'),p=${sharePayload};b?.addEventListener('click',async()=>{try{if(navigator.share){await navigator.share(p);b.textContent='shared';return}await navigator.clipboard.writeText(p.url);b.textContent='link copied'}catch(e){if(e?.name!=='AbortError')b.textContent='share failed'}});</script></body></html>\n`;
}

function renderAtlas(entries, version, curatedSha) {
  const canonical = `${SITE}/holes/`;
  const groups = Object.keys(LAYERS)
    .map((layerName) => {
      const layer = LAYERS[layerName];
      const cards = entries
        .filter((entry) => entry.layer === layerName)
        .map(
          (entry) =>
            `<a class="atlas-item" style="--entry-accent:${layer.accent}" href="/holes/${entry.id}/"><small>${layer.label}</small><strong>${escapeHtml(entry.title)}</strong><span>${escapeHtml(excerpt(entry.summary, 150))}</span></a>`,
        )
        .join('');
      return `<section><h2>${escapeHtml(layer.eyebrow.toLowerCase())}</h2><div class="atlas-list">${cards}</div></section>`;
    })
    .join('');
  const structured = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: 'lacuna hole atlas',
    numberOfItems: entries.length,
    itemListElement: entries.map((entry, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      url: `${SITE}/holes/${entry.id}/`,
      name: entry.title,
    })),
  };
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The hole atlas — sourced unknowns | lacuna</title><meta name="description" content="Browse sourced open questions, blocked questions, and declared blind spots from lacuna's versioned artifacts."><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="${canonical}"><link rel="icon" href="/favicon.svg" type="image/svg+xml"><meta property="og:type" content="website"><meta property="og:site_name" content="lacuna"><meta property="og:title" content="The hole atlas — sourced unknowns"><meta property="og:description" content="Sourced open questions, blocked questions, and declared blind spots. No computed discoveries."><meta property="og:url" content="${canonical}"><meta property="og:image" content="${SOCIAL_CARD}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="The hole atlas — sourced unknowns"><meta name="twitter:description" content="Sourced open questions, blocked questions, and declared blind spots. No computed discoveries."><meta name="twitter:image" content="${SOCIAL_CARD}"><script type="application/ld+json">${jsonForHtml(structured)}</script><style>${pageStyles()}</style></head><body>${shellHeader()}<main class="shell"><p class="eyebrow">THE HOLE ATLAS</p><span class="provenance">${entries.length} versioned entries · artifact ${escapeHtml(version)} · SHA-256 ${curatedSha.slice(0, 16)}…</span><h1>What remains unknown?</h1><p class="summary">A crawlable, shareable index of lacuna's sourced open questions, blocked questions, and declared coverage limits. These entries are kept separate from the computed method that failed validation.</p><p class="honesty">Human-curated questions are not discoveries. Declared blind spots describe limits of the map, including academic coverage it cannot see.</p>${groups}<div class="actions"><a class="button button-primary" href="/">Open the full map</a><a class="button" href="${SITE}/${version}/curated.json">Inspect build input</a><a class="button" href="${REPOSITORY}">Star or fork on GitHub ↗</a><a class="button" href="${REPOSITORY}/issues/new?template=curated-hole.yml">Propose a sourced hole ↗</a></div></main><footer class="shell">Open source. Provenance first. Failed methods stay visible.</footer></body></html>\n`;
}

function renderSitemap(entries) {
  const urls = [`${SITE}/`, `${SITE}/holes/`, ...entries.map((entry) => `${SITE}/holes/${entry.id}/`)];
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls
    .map((url) => `  <url><loc>${url}</loc></url>`)
    .join('\n')}\n</urlset>\n`;
}

export async function buildSharePages({ artifactRoot = DEFAULT_ARTIFACT_ROOT, outDir = DEFAULT_OUT_DIR } = {}) {
  const { entries, version, curatedSha } = await loadEntries(artifactRoot);
  const output = resolve(outDir);
  await mkdir(resolve(output, 'holes'), { recursive: true });
  await writeFile(
    resolve(output, 'holes', 'index.html'),
    renderAtlas(entries, version, curatedSha),
    'utf8',
  );
  for (const entry of entries) {
    const directory = resolve(output, 'holes', entry.id);
    await mkdir(directory, { recursive: true });
    await writeFile(
      resolve(directory, 'index.html'),
      renderHolePage(entry, version, curatedSha),
      'utf8',
    );
  }
  await writeFile(resolve(output, 'sitemap.xml'), renderSitemap(entries), 'utf8');
  return { entries: entries.length, pages: entries.length + 1, version };
}

function argument(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await buildSharePages({
    artifactRoot: argument('--artifact-root', DEFAULT_ARTIFACT_ROOT),
    outDir: argument('--out-dir', DEFAULT_OUT_DIR),
  });
  console.log(`generated ${result.pages} share pages from ${result.entries} curated entries (${result.version})`);
}
