---
name: validate
description: Run lacuna's complete validation workflow and report metric drift, skipped gates, artifact integrity, and frontend build status. Use when the user asks to validate the metric, run all tests, check whether the Swanson result moved, prepare a release, or verify a pipeline change.
---

# Validate lacuna

1. Read `AGENTS.md`, `docs/metric-validation-preregistration.md`, and the latest validation report.
2. Run the curated-content validator:

   ```bash
   python -m pipeline.export.validate_curated
   ```

3. Run fast tests:

   ```bash
   python -m pytest -m "not slow"
   ```

4. If `data/cooccurrence/pre1986/` exists, run the full suite and validation report:

   ```bash
   python -m pytest
   python -m pipeline.validate.validate_swanson
   ```

5. Rebuild artifacts and verify the frontend:

   ```bash
   python -m pipeline.export.build_artifacts
   npm --prefix web run build
   ```

6. Compare the Swanson target percentile, negative controls, sweep coverage, artifact version, and
   excluded-topic list with the committed report and manifest.
7. Report every skipped test or unavailable dependency. Never summarize a skipped validation as a
   pass.
8. Treat a suddenly improved target rank as drift requiring investigation, not proof of success.
