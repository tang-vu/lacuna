---
name: honest
description: Audit lacuna changes for claims that present estimates, generated text, bounds, incomplete samples, or failed metrics as stronger measured results. Use before a release, after changing artifacts or UI copy, or when the user asks what is being presented as fact without sufficient evidence.
---

# Audit honesty

1. Read `AGENTS.md`, the latest validation report, and the current manifest.
2. Inspect the latest Git diff. If there is no diff, inspect the latest commit.
3. Check every changed claim for an upper bound labelled as an observation; an incomplete sweep
   described as representative or complete; a failed metric described as a discovery tool;
   generated interpretation styled as measured evidence; a number without reproducible inputs; a
   modern ontology described as historical; or absent non-academic knowledge treated as evidence
   of no knowledge.
4. Follow links and artifact fields far enough to verify that provenance is usable, not merely
   present.
5. Return exactly one sentence naming the most serious place where the change outruns the evidence.
6. If none exists, return exactly: `No changed claim outruns the evidence I could verify.`
