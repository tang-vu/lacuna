# Autonomous prospective protocol paper

Status: **complete technical draft, not submitted and not peer reviewed**. It is not ready for
external submission until the identity fields and permanent links below are supplied.

This is a protocol paper, not an outcome paper. It describes the sealed 2026 T0 state and the
machine-verifiable evaluation that can run only after the complete 2027--2029 PubMed/MeSH release
window. It reports construction and integrity counts, but no prospective performance result.

## Low-cost publication route

1. Complete the Zenodo-backed `v0.2.0` software release and public OSF registration first.
2. Insert their permanent DOI/URLs in `paper.tex`; add the author's affiliation, ORCID, and
   correspondence address.
3. Build and read the PDF, then create a separate free Zenodo record with publication type
   **Preprint**. Do not reuse the software-release DOI for the paper.
4. Link the preprint to the software release and OSF registration in both directions.
5. Submit to a journal only if its scope, fees, and protocol-paper policy are acceptable. A later
   outcome paper must remain separate unless the full registered window has matured.

## Build

From this directory with MiKTeX installed:

```powershell
pdflatex -interaction=nonstopmode paper.tex
bibtex paper
pdflatex -interaction=nonstopmode paper.tex
pdflatex -interaction=nonstopmode paper.tex
```

The tracked `paper.pdf` is generated from `paper.tex` and `references.bib`. Auxiliary LaTeX files
are ignored. Before any external submission, replace every visible `TO BE SUPPLIED` marker and
rerun `python -m pytest tests/test_protocol_paper.py -q`.

OpenAI Codex assisted with this draft on 2026-08-25. Venue-specific disclosure may require the
author to retain or export additional interaction records.
