# NLnet proposal draft: Lacuna Evidence Bundles

Prepared against the form visible at https://nlnet.nl/propose/ on 2026-08-25. Plain-text answers
should be copied without the Markdown headings. All amounts and personal commitments are drafts
until the applicant confirms them.

## Call

**TO BE SELECTED AFTER THE 2026-09-03 CALL-SCOPE REVIEW.**

## Applicant details

- Name: **TO BE SUPPLIED PRIVATELY**
- Email: **TO BE SUPPLIED PRIVATELY**
- Phone: **TO BE SUPPLIED PRIVATELY**
- Organisation: **TO BE CONFIRMED; MAY BE LEFT EMPTY**
- Country of residence: **TO BE SUPPLIED PRIVATELY**

## Project name

Lacuna Evidence Bundles

## Website

https://github.com/tang-vu/lacuna

## Abstract

Lacuna Evidence Bundles will turn the provenance and machine-abstention machinery already used in
an open bibliometric project into a small, reusable FOSS toolkit. A producer will emit a canonical
bundle containing source identities, exact or bounded measurements, code and parameter hashes,
claim status, and failed or skipped gates. An independent verifier will check the bundle without a
service account or proprietary backend and render a static human-readable report. We will publish
a versioned JSON schema, Python reference implementation and CLI, deterministic fixtures, property
and conformance tests, documentation, migration examples, and signed releases under the MIT
License. The toolkit will preserve distinctions between measured, curated, and generated content
and will fail closed when source, integrity, outcome, or power evidence is missing. It will not
claim that lacuna's failed or unvalidated research-gap metrics work. The expected outcome is boring,
auditable infrastructure that other open research tools can adopt without importing lacuna's
scientific domain or large datasets.

## Previous relevant experience

The applicant created and maintains lacuna, an MIT-licensed provenance-first research-software
project. The repository already contains deterministic JSON artifacts, canonical hashes, source
inventories, exact-count and bounded-value labels, refusal-to-overwrite seals, automatic abstention,
Python validators, a static TypeScript interface, and CI. It publicly preserves two failed
pre-registered OpenAlex metrics instead of relabelling their outputs as discoveries. A separate
prospective PubMed/MeSH experiment has sealed 39,994,988 records and 7,310,895 candidate scores but
correctly remains not ready until its 2027--2029 outcome window matures. A score-blind empirical
track publishes only narrowly bounded replicated computational observations. These existing
artifacts make lacuna a demanding real-world fixture for extracting a general verification format;
they are not evidence that its knowledge-gap detector has been validated.

## Requested amount

**EUR 36,000 -- DRAFT; APPLICANT MUST CONFIRM.**

## Budget explanation

The draft budget is 90 engineering and documentation days at an explicit EUR 400/day, over six
months:

- EUR 12,000: 30 days for the canonical evidence-bundle schema, claim-state vocabulary, hash rules,
  and verifier core.
- EUR 10,000: 25 days for adapters, deterministic public fixtures, property tests, and cross-version
  conformance tests.
- EUR 8,000: 20 days for a static report renderer, CLI packaging, reproducible-build guidance, and
  maintainer documentation.
- EUR 6,000: 15 days for threat modelling, security and privacy review, release engineering, example
  integrations, and adoption support.

No hardware, travel, cloud service, or proprietary API cost is requested. The work is proposed as
one maintainer's labour; no partner or subcontractor is currently committed. Past and present
funding, tax treatment, and the applicant's availability are **TO BE CONFIRMED BEFORE SUBMISSION**.

## Comparison with existing or historical efforts

Research workflows commonly publish a paper, a code repository, a data DOI, and logs as separate
objects. General provenance vocabularies can describe relationships among them, while workflow
engines can rerun a specified computation. This project targets a smaller missing layer: a portable
verdict-bearing bundle that lets a verifier answer whether the exact claimed source bytes, counts,
bounds, code identity, and required gates agree, including a first-class abstention state.

The work is not a new workflow engine, package registry, research database, LBD algorithm, or
general ontology. It will use plain versioned JSON, SHA-256, deterministic canonicalisation, and a
small command-line verifier. Its unusual input is a project with both failed and still-unvalidated
methods: the format has to preserve negative results and unavailable evidence, not merely describe
successful runs. The reference implementation will be independent of lacuna's UI and datasets, and
fixtures will be small enough for any contributor or CI runner. Existing W3C and research-software
provenance concepts will be mapped rather than replaced where they fit.

## Significant technical challenges

The first challenge is semantic: a hash can prove byte identity but not whether a number is exact,
bounded, estimated, generated, stale, or tied to the right query. The schema must make those states
machine-checkable without pretending that metadata proves scientific truth.

The second is transitive verification across small manifests and large external files. The verifier
must distinguish a clean-clone structural audit from a full byte-level replay and must never report
the latter when source files are unavailable. It also needs stable canonicalisation, path safety,
streaming hashes, schema evolution, and useful errors without retaining credentials.

The third is fail-closed composition. A missing source, checksum conflict, incomplete outcome window,
or underpowered evaluation must produce explicit abstention. No human click, generated explanation,
or best-effort fallback may silently convert missing evidence into a pass.

Finally, the toolkit must be easy to adopt. The project will keep the core dependency-light, ship
small deterministic fixtures, document threat and trust boundaries, test on major platforms, and
separate optional rendering from verification.

## Ecosystem and engagement

Primary users are maintainers and auditors of open research software, data pipelines, benchmarks,
and static evidence publications. The first integration will be lacuna itself, because its failed,
unvalidated, measured, curated, generated, exact, and bounded records exercise the full claim model.
That does not make lacuna's candidates scientific results.

Development will occur in public issues and pull requests. Deliverables will include a standalone
package, specification examples, contributor guide, migration guide, and short integration walk-
throughs. Feedback will be requested from research-software and reproducibility communities after a
working conformance fixture exists. Adoption is optional: no human reviewer, external organisation,
or hosted service becomes a dependency of lacuna's active scientific state machine. Releases and
documentation will use libre/open licences and open formats.

## Attachments

None required for the first-stage form. If a call guide asks for detail, attach a plain-text or PDF
milestone schedule derived from this proposal; keep the main form self-contained.
