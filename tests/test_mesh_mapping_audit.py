from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from pipeline.benchmark.audit_mesh import audit_mappings, find_descriptors

SAMPLE_XML = b"""<?xml version="1.0"?>
<DescriptorRecordSet>
  <DescriptorRecord DescriptorClass="1">
    <DescriptorUI>D000001</DescriptorUI>
    <DescriptorName><String>Preferred Label</String></DescriptorName>
    <ConceptList>
      <Concept PreferredConceptYN="Y">
        <TermList>
          <Term ConceptPreferredTermYN="Y">
            <String>Preferred Label</String>
          </Term>
          <Term ConceptPreferredTermYN="N">
            <String>Historical Alias</String>
          </Term>
        </TermList>
      </Concept>
    </ConceptList>
  </DescriptorRecord>
</DescriptorRecordSet>
"""


def _fixture(tmp_path):
    cache_dir = tmp_path / "mesh"
    cache_dir.mkdir()
    archive = cache_dir / "desc2011.gz"
    with gzip.open(archive, "wb") as stream:
        stream.write(SAMPLE_XML)
    compressed = archive.read_bytes()
    sources = {
        "schema_version": 1,
        "sources": [
            {
                "kind": "historical_vocabulary",
                "files": [
                    {
                        "year": 2011,
                        "url": "https://example.test/desc2011.gz",
                        "sha256": hashlib.sha256(compressed).hexdigest(),
                        "bytes": len(compressed),
                        "descriptor_count": 1,
                    }
                ],
            }
        ],
    }
    sources_path = tmp_path / "sources.json"
    sources_path.write_text(json.dumps(sources), encoding="utf-8")
    return cache_dir, sources_path


def test_find_descriptors_matches_preferred_labels_and_entry_terms(tmp_path):
    cache_dir, _ = _fixture(tmp_path)

    hits = find_descriptors(
        cache_dir / "desc2011.gz",
        ["Preferred Label", "Historical Alias", "Missing"],
    )

    assert {(hit.query, hit.descriptor_ui, hit.match_basis) for hit in hits} == {
        ("Preferred Label", "D000001", "descriptor_label"),
        ("Historical Alias", "D000001", "entry_term"),
    }


def test_audit_verifies_pin_and_labels_unmatched_queries(tmp_path):
    cache_dir, sources_path = _fixture(tmp_path)

    result = audit_mappings(
        2011,
        ["Historical Alias", "Missing"],
        cache_dir=cache_dir,
        sources_path=sources_path,
    )

    assert result["mapping_basis"] == "pinned_production_year_mesh"
    assert result["hits"][0]["descriptor_ui"] == "D000001"
    assert result["unmatched_queries"] == ["Missing"]
    assert "cannot by themselves satisfy" in result["limitation"]


def test_audit_rejects_a_cache_that_differs_from_the_reviewed_pin(tmp_path):
    cache_dir, sources_path = _fixture(tmp_path)
    payload = json.loads(sources_path.read_text(encoding="utf-8"))
    payload["sources"][0]["files"][0]["sha256"] = "0" * 64
    sources_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum differs"):
        audit_mappings(
            2011,
            ["Preferred Label"],
            cache_dir=cache_dir,
            sources_path=sources_path,
        )
