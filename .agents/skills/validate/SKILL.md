---
name: validate
description: Run lacuna's complete validation workflow and report metric drift, skipped gates, artifact integrity, and frontend build status. Use when the user asks to validate the metric, run all tests, check whether the Swanson result moved, prepare a release, or verify a pipeline change.
---

# Validate lacuna

1. Read `AGENTS.md`, `docs/metric-validation-preregistration.md`, the latest validation report,
   `plans/metric-v3-validation-plan.md`, and `benchmarks/v3/cases.json`.
2. Run the curated-content validator:

   ```bash
   python -m pipeline.export.validate_curated
   ```

3. Validate the v3 benchmark contract, then run its readiness gate separately:

   ```bash
   python -m pipeline.benchmark.validate_v3
   python -m pipeline.benchmark.validate_v3 --require-ready
   ```

   The second command is expected to fail while the benchmark is a draft. Record its blockers and
   exit code; never turn the draft flag off merely to make the workflow green.
4. Run fast tests:

   ```bash
   python -m pytest -m "not slow"
   ```

5. If `data/cooccurrence/pre1986/` exists, run the full suite and validation report:

   ```bash
   python -m pytest
   python -m pipeline.validate.validate_swanson
   ```

6. Rebuild artifacts, verify their pinned content hashes, and verify the frontend:

   ```bash
   python -m pipeline.export.build_artifacts
   python -m pipeline.export.verify_artifacts
   npm --prefix web run build
   ```

7. Compare the Swanson target percentile, negative controls, sweep coverage, artifact version,
   input fingerprints, and excluded-topic list with the committed report and manifest.
8. Report v3 case counts by kind, held-out counts, mapping statuses, and every readiness blocker.
9. Report every skipped test or unavailable dependency. Never summarize a skipped validation as a
   pass.
10. Treat a suddenly improved target rank as drift requiring investigation, not proof of success.
