# lacuna — architecture plan

**Status:** proposed, awaiting approval
**Date:** 2026-07-27
**Research inputs:** `plans/reports/researcher-260727-1126-*.md` (3 reports)
**Verification:** all numbers below marked ✅ were measured live against `api.openalex.org` /
`openalex.s3.amazonaws.com` on 2026-07-27, not taken from the reports. Three report claims were
wrong; see §7.

---

## 1. What is actually being built

A pipeline that computes **structural gaps** between research areas, plus two curated layers
(`open`, `blocked`) that ride on the same taxonomy. The computed layer is the project; the
curated layers are content.

Definition used throughout: a gap is a pair (A, C) that is **bibliometrically distant**
(they rarely appear on the same work) *and* **structurally close** (they keep the same company —
both associate strongly with a common set of B's). That conjunction is Swanson's ABC model, stated
as a property of a co-occurrence matrix.

Distance alone is not a gap — most pairs are distant and unrelated. Closeness alone is not a gap —
that is just similarity, which Connected Papers already does. Only the conjunction is interesting.

---

## 2. Granularity — the decision that determines whether this works

**Decision: topics (4,516), not subfields (252).**

The brief assumed subfields. I tested that assumption against the canonical Swanson case and it
fails. Pre-1986 works, grouped by subfield ✅:

| Raynaud's literature | n | Fish-oil / EPA literature | n |
|---|---|---|---|
| Pathology & Forensic Medicine | 402 | Nutrition & Dietetics | 310 |
| Genetics | 274 | Biochemistry | 229 |
| **Molecular Biology** | 221 | **Molecular Biology** | 128 |
| Surgery | 177 | Pharmacology | 91 |
| **Physiology** | 171 | **Physiology** | 66 |

The two literatures **share two of their top five subfields**. At subfield granularity the canonical
gap is not a gap — it is a high-co-occurrence pair. Subfields are also internally incoherent:
subfield 2739 holds 4.3M works across 54 topics spanning malaria, palliative care, opioid treatment
and medical education ✅. Any metric averaged over that has nothing left to measure.

Topics (4,516, mean ~70k works) are the coarsest level with a plausible chance of carrying signal.
This is still unproven — see §7, assumption 1.

---

## 3. Data acquisition — REST, not the snapshot

The OpenAlex research report recommended downloading a ~330 GB snapshot. That recommendation is
based on a missed API capability. **`filter` and `group_by` compose**, which returns an entire row
of the co-occurrence matrix in a single call ✅:

```
/works?filter=topics.id:T10102&group_by=topics.id&per-page=200
→ 200 groups, one call, 1 credit
```

So the full matrix costs **4,516 calls**, not the 31,752 the report calculated, and not a snapshot
download. Time-slicing is the same cost per slice — just add `to_publication_date` to the filter,
which is what the validation suite needs.

**Truncation, and why it is survivable.** `per-page` caps at 200 ✅ (201 → `Pagination error`), so
each row returns only its top 200 of 4,516 partners. For gap-hunting we care about the *small*
cells, which are exactly the ones truncated. The saving detail: the 200th group's count is a hard
ceiling on every unseen cell in that row. For topic T10102 that ceiling is **77** ✅. So unobserved
cells are not unknown — they are bounded, `c ≤ 77`. Substituting the ceiling yields a *conservative*
gap score (a lower bound). Any pair that scores as a gap under the ceiling is a gap under the true
value. Exact counts for shortlisted pairs come from a targeted two-filter call, which also works ✅
(`filter=topics.subfield.id:2739,topics.subfield.id:1314` → 11,389).

**Rate limits — corrected.** Anonymous requests today return `X-RateLimit-Limit: 1000`,
`X-RateLimit-Credits-Used: 1` per list call, reset in ~19h ✅. The report claimed 100 anonymous /
100,000 with a free key; the anonymous figure is off by 10× and a list call costs 1 credit, not 10.
At 1,000/day a full matrix takes ~5 days unattended. Registering a free API key is the first task
of phase 1 — the report's "100,000 credits/day" claim is **unverified** and the whole schedule
depends on it.

Fallback if the key tier disappoints: `s3://openalex/data/parquet/` exists ✅ and is Hive-partitioned
by `updated_date` (>188 GB in the first 1,000 keys alone, listing truncated — so materially larger
than the 330 GB the report cited). Because it is columnar, DuckDB can project just
`id, publication_year, topics` over S3 and skip abstracts, authorship and references entirely. That
is the escape hatch, not the default.

---

## 4. The gap metric

Notation: `N` works total, `s_i` works on topic *i*, `c_ij` co-occurrence, `e_ij = s_i·s_j/N`
expected under independence.

**Candidate 1 — association strength / lift.** `AS = c_ij / e_ij`, gap when `AS ≪ 1`. This is Van
Eck & Waltman's measure and is the bibliometric standard. Rejected as the primary: it is unstable
exactly where we look. When `e_ij < 1` the ratio is noise, and gaps live in the low-expectation
corner.

**Candidate 2 — deficit significance.** `p_ij = P(X ≤ c_ij)` under `Hypergeometric(N, s_i, s_j)`.
This handles the size problem correctly *in the direction that matters for gaps*. Note the brief's
concern inverts here: for similarity, raw counts over-rank big fields; for **gaps**, raw counts
over-rank *small* fields, because two tiny topics trivially never co-occur. Significance-of-deficit
fixes that — zero co-occurrence between two 200-work topics is unremarkable, zero between two
100k-work topics is not. Still incomplete: it ranks unrelated pairs as highly as related ones.

**Candidate 3 — ABC second-order structure. ← recommended**

```
a_i          = association vector of topic i over all topics (NPMI, or AS)
S_ij         = cosine(a_i, a_j)  with the i,j components masked out
D_ij         = deficit significance from Candidate 2
GapScore_ij  = S_ij · D_ij
```

Masking the direct `i,j` term is not cosmetic — without it the "closeness" signal is partly the
co-occurrence we are claiming is absent, and the metric becomes circular. With it, the statement is
precisely Swanson's: *A and C keep the same company but never meet.*

Guards, all mandatory: minimum support `s_i, s_j ≥ 1,000`; minimum expected count `e_ij ≥ 5` (below
this the deficit is unmeasurable and the pair is dropped, not scored); same-subfield pairs kept but
flagged. Candidates 1 and 2 are computed and published alongside as diagnostics so a reader can see
the raw counts behind any claim.

---

## 5. Storage — precomputed static artifacts, no database

| Artifact | Approx size | Notes |
|---|---|---|
| `taxonomy.json` | <2 MB | 4,800 nodes, all four levels |
| `marginals.json` | ~200 KB | `s_i` per topic, per time slice |
| `cooccurrence.parquet` | ~15 MB | sparse triplets, ≤903k observed cells + per-row ceiling |
| `gaps.json` | ~20 MB | top-N scored pairs with full provenance |

No database in production. DuckDB in the pipeline only. Artifacts are versioned by
`{snapshot_date}/{metric_version}` so an old map stays reproducible after the metric changes.

**Traceability** (a stated non-negotiable): every row in `gaps.json` carries `s_i`, `s_j`, `c_ij`
or its ceiling, `e_ij`, each sub-score, the metric version, and the literal API query URLs that
produced the counts. A gap the reader cannot re-derive by clicking a link does not ship.

---

## 6. Stack and layout

Python for the pipeline (DuckDB, pyarrow, scipy sparse — this is where the ecosystem is, and the
S3-parquet fallback needs DuckDB regardless). TypeScript + Vite for the frontend, static build,
reads the artifacts directly. No server.

```
lacuna/
├── pipeline/            # python
│   ├── ingest/          # taxonomy, co-occurrence rows, time slices
│   ├── metric/          # association, deficit, abc scoring
│   ├── validate/        # the test suite from §7 — load-bearing
│   └── export/          # versioned artifacts
├── curated/             # open/*.yaml, blocked/*.yaml, blind-spots/*.yaml
├── artifacts/{version}/ # generated, committed
├── web/                 # typescript, static
└── docs/
```

**Blind spots as data, not prose.** `curated/blind-spots/` is a typed registry rendered as part of
the map: `coverage-humanities` (~70% reference linkage vs ~95% STEM), `coverage-pre-1970`,
`coverage-non-english`, `coverage-non-academic` (craft, practitioner, indigenous — absent entirely),
and `ontology-anachronism` (see below). These render as regions of the map marked unmeasurable,
which is the honest presentation: lacuna cannot see them, and that is itself a lacuna.

---

## 7. Critique of this plan — the two weakest assumptions

**Assumption 1: OpenAlex topics are fine-grained enough to carry Swanson-type signal.**

This is the load-bearing assumption and it is currently unproven. I have already falsified the
*subfield* version of it (§2) — which means the failure mode is real and demonstrated one level up,
not hypothetical. Topics are 18× finer, but Swanson worked at the level of individual MeSH terms
("Raynaud's disease", "eicosapentaenoic acid"), which is finer still. There may be no granularity in
OpenAlex's taxonomy at which the canonical result reproduces.

There is a second defect underneath it. OpenAlex topics are assigned by a model trained on the
*modern* corpus and applied retroactively to old works. A `to_publication_date:1985-12-31` filter
therefore does **not** reconstruct the 1986 literature — it projects today's ontology backwards onto
it. Swanson's result came from 1986's MeSH indexing. So the "pre-1986 reproduction" the brief
demands is not the experiment it appears to be, and a pass would be weaker evidence than it looks.

*Falsifies it:* run the ABC scorer at topic level on pre-1986 data and check whether the
Raynaud's-dominant and EPA-dominant topics surface as a flagged pair. If they do not, the computed
layer has no demonstrated validity and the honest move is to publish the negative result rather than
ship a plausible-looking map. **This test should run in the first week, before any frontend work** —
it is the cheapest available kill-shot and the plan should be structured to take it early.

**Assumption 2: absence of co-occurrence indicates absence of a knowledge connection.**

At least four other things produce the same signal: the bridging work exists in a venue OpenAlex
does not index; it exists under terminology the topic model splits differently; the connection is
obvious to practitioners and therefore never written down; or the pair is genuinely unrelated and
the second-order similarity is an artifact of both associating with some hub topic. Under any of
these, the metric measures indexing artifacts and calls them holes in human knowledge — precisely
the "plausible-sounding nonsense with extra steps" the brief rules out.

*Falsifies it:* hand-audit a random (not cherry-picked) sample of ~30 top-scoring gaps against
Google Scholar and, where possible, a domain expert. If a substantial fraction have existing
bridging literature, the metric is measuring OpenAlex's coverage rather than the world's. This audit
needs a pre-registered pass threshold agreed **before** the numbers are seen, or it will rationalise
whatever comes out.

**Third, smaller:** the prior-art report concluded no direct competitor exists. I did not
independently verify that and it is the kind of conclusion that is pleasant to reach. Worth one
sceptical pass before any public claim of novelty.

---

## 8. Phases

1. **Taxonomy + API key** — ingest all four levels, assert counts (4/26/252/4,516 ✅), confirm the
   real credit ceiling. Blocks everything.
2. **Co-occurrence rows** — 4,516 group-by calls, current slice + pre-1986 slice, with ceilings
   recorded per row.
3. **Metric + validation** — implement §4; then the §7 tests. **Gate: if assumption 1 fails here,
   stop and reassess rather than continue to frontend.**
4. **Artifacts + thin frontend** — taxonomy navigation, gaps overlaid, one pair-detail view.
5. **Curated layers** — `open`, `blocked`, `blind-spots`.

Phase files get written at implementation start (Prompt 2), not now.

---

## Unresolved questions

1. **Free API key ceiling** — is it really 100,000 credits/day? Unverified; phase 2's schedule
   (hours vs 5 days) depends on it entirely.
2. **Pre-registered pass threshold for the expert audit** — what fraction of sampled gaps must
   survive scrutiny for the metric to count as validated? This is a judgement call and should be
   yours, fixed before results exist.
3. **What happens if assumption 1 fails?** Options: drop to per-topic-pair analysis on a single
   domain where terminology is dense enough; abandon the computed layer and ship curated only; or
   publish the negative result as the project's first finding. Worth deciding the posture now,
   while it is still cheap to be honest about.
4. **Topic reassignment stability** — OpenAlex re-runs classification as its model improves, so
   historical gap artifacts may not reproduce across snapshots. Pin snapshot version per artifact
   (planned), but reproducibility across versions is not guaranteed.
