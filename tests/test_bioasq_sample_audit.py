from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

from pipeline.benchmark.bioasq_sample_audit import audit_public_sample


def _write_mesh(path: Path) -> Path:
    path.write_bytes(
        gzip.compress(
            b"""<DescriptorRecordSet>
<DescriptorRecord><DescriptorUI>D1</DescriptorUI><DescriptorName><String>Alpha</String></DescriptorName></DescriptorRecord>
<DescriptorRecord><DescriptorUI>D2</DescriptorUI><DescriptorName><String>Beta</String></DescriptorName></DescriptorRecord>
</DescriptorRecordSet>"""
        )
    )
    return path


def test_public_sample_audit_keeps_current_comparison_bounded(tmp_path: Path):
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "articles": [
                    {
                        "abstractText": "text",
                        "journal": "journal",
                        "meshMajor": ["Alpha", "Beta"],
                        "pmid": "1",
                        "title": "title",
                        "year": "2013",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pubmed = tmp_path / "pubmed.xml"
    pubmed.write_text(
        """<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>1</PMID><MeshHeadingList>
<MeshHeading><DescriptorName MajorTopicYN="Y">Alpha</DescriptorName></MeshHeading>
</MeshHeadingList></MedlineCitation></PubmedArticle></PubmedArticleSet>""",
        encoding="utf-8",
    )
    sample_bytes = sample.read_bytes()

    audit = audit_public_sample(
        sample,
        pubmed,
        mesh_path=_write_mesh(tmp_path / "mesh.gz"),
        observed_on=date(2026, 8, 11),
        expected_sample_sha256=hashlib.sha256(sample_bytes).hexdigest(),
        expected_sample_bytes=len(sample_bytes),
        verify_pinned_mesh=False,
    )

    comparison = audit["maintained_current_pubmed_comparison"]
    assert audit["status"] == "bounded_public_sample_audit"
    assert audit["readiness_contribution"] == 0
    assert comparison["sample_assignments"] == 2
    assert comparison["matched_current_all_descriptor_assignments"] == 1
    assert comparison["matched_current_major_topic_assignments"] == 1
    assert comparison["sample_only_labels_by_pmid"] == {"1": ["Beta"]}
