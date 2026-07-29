# NLM historical MEDLINE baseline access request

**Status:** prepared, not sent  
**Prepared:** 2026-07-29  
**Owner action required:** add contact details and submit through the
[NLM Support Center](https://support.nlm.nih.gov/).

## Why this request is necessary

lacuna is an open-source, non-commercial bibliometrics project testing whether a literature-based
discovery method can reproduce historical cases without projecting today's indexing backward.
That requires the citation-to-MeSH assignments as they existed in a specific annual baseline, not
the current PubMed record filtered by publication year.

NLM documents static annual MEDLINE/PubMed baselines from 2002 onward. The original launch notice
also says raw FTP and query access were controlled for registered licensees. As checked on
2026-07-29:

- `mbr.nlm.nih.gov` and the HTTPS form of the former hidden `.medleasebaseline` FTP path returned
  404;
- the archived distribution-document index still lists 2006, 2010, 2011, and 2012 inventories;
- the linked 2006, 2010, and 2011 inventory pages returned 404;
- the live 2012 inventory lists 684 XML files, 20,494,848 records, and 11.9 GB compressed, but no
  raw download URL or file checksums;
- the separate BioNLP persistent-abstract service describes title/abstract snapshots, not the
  historical MeSH assignments needed here.

No raw record source has therefore been marked available. The project already has the matching
2006, 2010, 2011, and 2012 production-year MeSH descriptor archives pinned separately.

## Submission draft

**Subject:** Access to static 2006, 2010, 2011, and 2012 MEDLINE/PubMed baseline XML

Hello NLM Support,

I maintain an open-source, non-commercial bibliometrics project that is validating a
literature-based discovery method against historical MEDLINE indexing. We need the static annual
MEDLINE/PubMed baseline XML distributions for 2006, 2010, 2011, and 2012, including the MeSH
assignments present in each release.

The former MEDLINE Baseline Repository and hidden FTP paths no longer resolve for us. NLM's archive
of licensee documentation still identifies the annual distributions, and the 2012 file inventory
is still visible, but we could not find stable raw-file URLs or checksums.

Could you please confirm:

1. Whether the complete 2006, 2010, 2011, and 2012 baseline XML distributions remain obtainable.
2. The current access procedure, including whether a no-cost data license, registered IP address,
   or another approval is required.
3. Stable download locations for the exact historical releases, if available.
4. Original file manifests or checksums. If only legacy MD5 values exist, we can record those and
   add SHA-256 after downloading.
5. Which terms and conditions govern research use and whether publishing derived aggregate
   co-occurrence counts is permitted.
6. If the files are no longer distributed, whether NLM can identify an official archive or
   preservation contact that holds them.

We do not plan to redistribute citation records or abstracts. We intend to publish only aggregate
descriptor co-occurrence counts, input identities, and reproducible processing code.

Thank you,

`[name]`  
`[affiliation, if any]`  
`[contact email]`

## Evidence to include if support asks for URLs

- [NLM 2005 MBR launch notice](https://www.nlm.nih.gov/pubs/techbull/nd05/nd05_technote_mbr.html)
- [NLM historical distribution documentation index](https://www.nlm.nih.gov/bsd/licensee/archive_doc.html)
- [NLM 2012 baseline file inventory](https://www.nlm.nih.gov/bsd/licensee/2012_stats/baseline_med_filecount.html)
- [NLM MBR reference material](https://lhncbc.nlm.nih.gov/ii/information/MBR/MEDLINE_Baseline_Repository_Detail_2017.pdf)
- [NLM data terms and conditions](https://www.nlm.nih.gov/databases/download/terms_and_conditions.html)

## Acceptance checklist for any reply

Do not change `historical_records` to `available_pinned` merely because a support reply says the
data exists. For each required release:

- record the official source URL and access conditions;
- obtain the complete file inventory, not a convenient subset;
- record the compressed byte count and SHA-256 for every file;
- parse the release and reconcile its total record count with NLM's inventory;
- preserve the matching baseline year and MeSH archive checksum in every measurement;
- keep any personal support correspondence out of committed provenance.
