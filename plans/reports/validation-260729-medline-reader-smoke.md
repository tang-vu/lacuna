# MEDLINE baseline reader: current-file smoke test

**Date:** 2026-07-29  
**Scope:** parser compatibility only  
**Historical source gate:** unchanged, `unavailable`

## Input

- URL:
  `https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/pubmed26n0001.xml.gz`
- compressed bytes: `19,683,003`
- NLM-published MD5: `fb7c05737f47f7e07245f0c064c6e00a`
- locally computed SHA-256:
  `ff52cc95450982f0910e16ae2e5042236abeba8ebddb7e47091db42230e62890`

The MD5 in `pubmed26n0001.xml.gz.md5` matched the downloaded transport bytes before parsing.

## Result

`pipeline.benchmark.medline_baseline.iter_medline_records` streamed the complete gzip file:

| measurement | value |
|---|---:|
| parsed `PubmedArticle` records | 30,000 |
| records without a parsed publication year | 0 |
| records without a valid MeSH descriptor UI | 0 |

The result is consistent with NLM's current baseline convention of 30,000 citations per regular
file. It exercises a real PubMed DOCTYPE and citation shape rather than only the synthetic unit-test
fixture.

## What this does not establish

- The file is from the maintained-current 2026 PubMed baseline, not an archived 2006, 2010, 2011,
  or 2012 release.
- It does not test older DTD differences.
- It does not show that the historical baseline files remain obtainable.
- It does not make any mapping period-appropriate and contributes no case to metric v3 readiness.
- The current baseline directory is a moving distribution location. The URL is input provenance
  for this dated smoke test, not a permanent historical archive.

The downloaded file remains in ignored local pipeline state and is not redistributed by this
repository.
