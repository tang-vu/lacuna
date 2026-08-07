# Historical MEDLINE public-source follow-up

**Date:** 2026-08-07  
**Scope:** public-path discovery only  
**Historical-record source gate:** unchanged, `unavailable`

## Result

No raw 2007, 2011, 2012, or 2013 MEDLINE/PubMed baseline release was acquired. These checks add no
record release, checksum, or period-appropriate mapping to metric v3 readiness.

## Checks

- The current NCBI PubMed baseline `README.txt` remains reachable and directs data questions to
  `info@ncbi.nlm.nih.gov`. It documents the current rolling baseline, not retained historical
  release paths:
  `https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/README.txt`.
- Dated HEAD requests to plausible public NCBI archive layouts all returned HTTP 404, including
  `/pubmed/baseline/2012/`, `/pubmed/baseline-2012/`, `/pubmed/archive/2012/`, and direct current-tree
  guesses for `medline12n0001.xml.gz` and `pubmed12n0001.xml.gz`. These probes are failed path
  guesses, not evidence that NLM no longer holds the release.
- Exact and prefix queries against the `CC-MAIN-2018-51` Common Crawl index returned no record for
  `https://mbr.nlm.nih.gov/Download/Baselines/2012`. The already pinned homepage capture remains
  valid and still establishes directory metadata only.
- NLM's Persistent PubMed Abstracts page still describes year-specific snapshots from 2002 through
  2016, but explicitly limits each citation file to title and abstract. It therefore cannot supply
  the historical MeSH assignments required here:
  `https://bionlp.nlm.nih.gov/persistentAbstracts.html`.
- Requests to two documented-style `bionlp.nlm.nih.gov/base/2012/{PMID}` paths returned HTTP 404 on
  this date. Reachability aside, that service's documented content would remain scientifically
  unsuitable for the historical-indexing gate.

## Consequence

The prepared support request in `plans/requests/nlm-historical-medline-access.md` remains the next
external action. The current NCBI README provides a direct public contact in addition to the NLM
Support Center, but owner contact details and submission are still required. Do not turn a support
reply, directory listing, title/abstract snapshot, or current PubMed export into
`available_pinned`; complete release files must pass the pinned inventory and manifest workflow.

