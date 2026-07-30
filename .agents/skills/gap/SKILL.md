---
name: gap
description: Inspect one lacuna topic pair and print its raw co-occurrence evidence, expected count, exact-or-bounded status, strongest ABC bridges, and source queries. Use when the user names two OpenAlex topics, asks whether a particular pair is a gap, or wants to sanity-check one computed result.
---

# Inspect a gap

1. Read `AGENTS.md` and preserve the current failed-validation warning.
2. Resolve each argument as an OpenAlex topic ID or an unambiguous topic-name substring.
3. Run:

   ```bash
   python -m pipeline.inspect_gap "<topic A>" "<topic B>" --slice pre1986
   ```

4. Report the topic IDs and names; marginals; total works; observed count and whether it is exact
   or an upper bound; expected count; deficit probability; bridge score; combined score; strongest
   intermediate topics; source-row queries; exact verification query; and generalist exclusions.
5. Say explicitly that the current metric failed validation. Do not call the pair a discovery.
6. Do not generate a bridging hypothesis while the interpretation layer is gated off. If asked for
   one, distinguish the request from measured evidence and explain that generated hypotheses are
   not enabled.
7. If a topic is outside the fetched sweep, report that limitation instead of estimating it.
