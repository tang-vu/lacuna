# OSF registration packet: autonomous prospective v1

Status: **prepared, not submitted**. No OSF DOI has been assigned.

This packet is for a public, immutable OSF Registration of a protocol and T0 prediction state
that were already sealed in August 2026. It must not be submitted as a new preregistration:
candidate scoring had already completed before this packet was written.

## Submission order

1. Publish the repository's `v0.2.0` release only after its Zenodo integration is enabled.
2. Replace the pending release reference in `registration.md` with the version DOI and archive URL.
3. Run `python -m pipeline.export.build_osf_registration_packet` and verify that only the expected
   DOI-related packet hashes changed.
4. Create a public OSF Registration, copy the registration text, and upload this directory plus
   the nine registered JSON records listed in `manifest.json`.
5. Record the OSF URL and DOI here in a follow-up repository commit. Do not edit the registered
   OSF record after submission; correct material mistakes with a new, linked registration.

The submission should remain public. An embargo would delay independent verification and is not
needed because all recorded scientific state is already public.

## Files

- `registration.md` is the copy-ready registration narrative.
- `manifest.json` is generated and pins every included small file by raw-byte SHA-256 and length.
- The large PubMed/MeSH source corpus and prediction binaries are not duplicated in this packet.
  Their exact filenames, lengths, counts, and hashes are pinned transitively by the registered
  repository records.

Regenerate, do not hand-edit, `manifest.json`.
