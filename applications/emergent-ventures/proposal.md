# Proposal: Make computational claims fail honestly

## Personal story

**APPLICANT MUST REPLACE THIS PARAGRAPH IN THEIR OWN WORDS (150--250 WORDS):** Explain what led you
to build lacuna, a concrete moment when a result failed or provenance mattered, what you personally
built, how you have sustained the project, and why you are the right person to extract this toolkit.
Do not turn this into a credentials list. Do not claim discoveries or impact that did not occur.

## One mainstream view I agree with

**DRAFT -- APPLICANT MUST CONFIRM THIS IS TRUE:** I agree with the mainstream scientific norm that
claims should be backed by evidence that other people can inspect and reproduce. Reproducibility is
not bureaucratic overhead; it is how a community distinguishes a measurement from a story about a
measurement. My project is unusual not because it rejects that consensus, but because it treats a
failed test or a justified abstention as an output worth publishing as carefully as a success.

## The idea

Scientific software is good at producing numbers and weak at carrying the exact status of those
numbers. A plot or ranked list is easily separated from the source query, input bytes, code version,
bound or estimate, validation gate, and failed checks that give it meaning. That separation creates
a predictable failure mode: generated text becomes a fact, an unavailable file becomes an implied
reproduction, and a failed metric quietly becomes a discovery engine.

I want to build Lacuna Evidence Bundles: a small open format and verifier that travel with a
computational claim. A bundle will identify source bytes and queries, distinguish exact values from
bounds and estimates, separate measured, curated, and generated content, pin code and parameters,
and carry every required pass, fail, skip, and abstention state. A dependency-light command-line
tool will verify the bundle independently and render a static report that a human can inspect
without an account, proprietary service, or live backend.

The starting point is lacuna, an open-source attempt to map gaps in research. Its first two
OpenAlex metrics failed a pre-registered reproduction; the project publishes that failure and its
traceable measurements instead of calling them discoveries. Its replacement experiment has sealed
39,994,988 PubMed records and 7,310,895 candidate scores, but it remains unvalidated and explicitly
not ready until a 2027--2029 outcome window exists. A separate empirical track publishes narrowly
bounded replicated computational observations without claiming mechanism, causality, clinical
utility, novelty, or knowledge gaps.

That awkward mix is the advantage. Most provenance demonstrations start with a clean successful
workflow. Lacuna has exact counts, bounds, missing sources, failed metrics, sealed predictions,
future evidence that does not exist yet, and automatic abstention. If a format can represent those
states honestly, it can serve less unusual research pipelines too.

## What is new

This is not a new workflow engine, research database, ontology, or AI scientist. Existing systems
can describe provenance or rerun workflows. The missing product is a small verdict-bearing evidence
object with fail-closed semantics: a verifier must say exactly which level it checked, and missing
source, checksum, outcome, integrity, or power evidence can never silently become a pass.

The toolkit will use boring components: versioned JSON, JSON Schema, SHA-256, streaming reads,
deterministic canonicalisation, a Python CLI, small public fixtures, and static HTML. It will map to
existing provenance concepts where useful, but a maintainer should be able to adopt it without a
server, knowledge graph, or specialist team.

## Six-month plan

In months 1--2 I will specify the claim-state vocabulary, threat model, canonical bundle, and
verification levels, then extract the first verifier from lacuna. In months 3--4 I will add
property and conformance tests, safe streaming verification for large external files, deterministic
fixtures, and adapters for common tabular and JSON outputs. In month 5 I will ship a static report
renderer, packaging, migration documentation, and two example integrations. In month 6 I will run
a public hardening period, resolve portability and accessibility issues, publish a stable release,
and document what the toolkit does not prove.

Deliverables will be MIT-licensed source, a versioned specification and schema, installable CLI,
test corpus, static renderer, contributor and security documentation, and archived releases. The
active lacuna benchmark will remain machine-gated; community feedback will improve the software but
will not become a human adjudication dependency for its scientific verdict.

## Budget and commitment

I am requesting a draft total of USD 25,000 for six months of part-time work, approximately 20
hours per week. USD 20,000 covers 500 hours of engineering, testing, documentation, and release work
at USD 40/hour. USD 2,000 covers archival storage, build infrastructure, and cross-platform testing.
USD 1,500 covers accessibility and independent usability testing. USD 1,500 covers documentation,
community demonstrations, and dissemination. There are no committed project partners or other
funding sources in this draft; the applicant will correct that statement before submission if the
funding situation changes.

The grant would turn working but project-specific integrity machinery into a reusable public tool.
The near-term success criterion is not that lacuna discovers a scientific gap. It is that another
maintainer can produce a bundle, a separate machine can verify its exact evidence level, and both a
success and a failure remain legible after the original application is gone.
