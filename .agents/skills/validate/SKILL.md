---
name: validate
description: Run lacuna's complete validation workflow and report metric drift, skipped gates, artifact integrity, and frontend build status. Use when the user asks to validate the metric, run all tests, check whether the Swanson result moved, prepare a release, or verify a pipeline change.
---

# Validate lacuna

1. Read `AGENTS.md`, `docs/metric-validation-preregistration.md`, the latest validation report,
   `plans/metric-v3-validation-plan.md`, `benchmarks/v3/sources.json`,
   `benchmarks/v3/candidates.json`, and `benchmarks/v3/cases.json`.
2. Run the curated-content validator:

   ```bash
   python -m pipeline.export.validate_curated
   ```

3. Validate historical source access, metric-blind candidate intake, and the v3 benchmark
   contract, then run their readiness gates separately:

   ```bash
   python -m pipeline.benchmark.source_inventories
   python -m pipeline.benchmark.mbr_capture
   python -m pipeline.benchmark.validate_sources
   python -m pipeline.benchmark.validate_sources --require-ready
   python -m pipeline.benchmark.validate_candidates
   python -m pipeline.benchmark.validate_v3
   python -m pipeline.benchmark.validate_v3 --require-ready
   ```

   When network access is available, replay both preservation probes and report reachability or
   drift separately from scientific readiness:

   ```bash
   python -m pipeline.benchmark.source_inventories --probe --require-match
   python -m pipeline.benchmark.mbr_capture --probe --require-match
   ```

   The MBR capture preserves repository directory metadata only. A successful replay contributes
   zero raw record releases; an unreachable archive is a skipped live check, not evidence of drift.

   Both `--require-ready` commands are expected to fail while historical inputs are unavailable
   and the benchmark is a draft. Record their blockers and exit codes; never change a status merely
   to make the workflow green. Proposed and rejected intake entries contribute zero cases to
   readiness.
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
8. Report historical source statuses, candidate counts by status, then v3 case counts by kind,
   held-out counts, mapping statuses, and every readiness blocker.
9. Report every skipped test or unavailable dependency. Never summarize a skipped validation as a
   pass.
10. Treat a suddenly improved target rank as drift requiring investigation, not proof of success.
