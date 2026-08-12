from __future__ import annotations

import gzip
import hashlib
import json

import numpy as np
import pytest

from pipeline.benchmark.autonomous_candidate_index import (
    PAIR_DTYPE,
    CandidateIndexError,
    read_vocabulary,
    scan_source_file,
)


def _mesh(tmp_path):
    path = tmp_path / "desc2026.gz"
    xml = """<DescriptorRecordSet>
    <DescriptorRecord DescriptorClass="1"><DescriptorUI>D000001</DescriptorUI>
      <DescriptorName><String>Alpha</String></DescriptorName>
      <TreeNumberList><TreeNumber>A01.100</TreeNumber></TreeNumberList>
      <ConceptList><Concept><TermList><Term><String>Shared term</String></Term></TermList></Concept></ConceptList>
    </DescriptorRecord>
    <DescriptorRecord DescriptorClass="2"><DescriptorUI>D000002</DescriptorUI>
      <DescriptorName><String>Beta</String></DescriptorName>
      <TreeNumberList><TreeNumber>A01.100.200</TreeNumber></TreeNumberList>
      <ConceptList><Concept><TermList><Term><String> SHARED   TERM </String></Term></TermList></Concept></ConceptList>
    </DescriptorRecord>
    <DescriptorRecord DescriptorClass="1"><DescriptorUI>D000003</DescriptorUI>
      <DescriptorName><String>Gamma</String></DescriptorName>
      <TreeNumberList><TreeNumber>C01.300</TreeNumber></TreeNumberList>
      <ConceptList><Concept><TermList><Term><String>Third</String></Term></TermList></Concept></ConceptList>
    </DescriptorRecord>
    </DescriptorRecordSet>"""
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(xml)
    return path


def _article(pmid: str, descriptors: list[str]) -> str:
    headings = "".join(
        f'<MeshHeading><DescriptorName UI="{ui}" MajorTopicYN="N">{ui}</DescriptorName></MeshHeading>'
        for ui in descriptors
    )
    return (
        "<PubmedArticle><MedlineCitation>"
        f"<PMID>{pmid}</PMID><MeshHeadingList>{headings}</MeshHeadingList>"
        "</MedlineCitation></PubmedArticle>"
    )


def _source(tmp_path, articles: list[str]):
    path = tmp_path / "pubmed26n0001.xml.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>")
    raw = path.read_bytes()
    return path, {
        "filename": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "total_record_count": len(articles),
    }


def test_vocabulary_keeps_all_classes_stable_order_trees_and_normalised_terms(tmp_path):
    path = _mesh(tmp_path)
    audit = read_vocabulary(
        path,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        expected_count=3,
    )

    assert [item.ui for item in audit.descriptors] == ["D000001", "D000002", "D000003"]
    assert audit.descriptors[0].tree_numbers == ("A01.100",)
    assert audit.descriptors[0].terms == ("shared term",)
    assert audit.descriptors[1].terms == ("shared term",)


def test_source_scan_writes_exact_support_pair_and_pmid_shards_then_reuses(tmp_path):
    mesh = _mesh(tmp_path)
    vocabulary = read_vocabulary(
        mesh,
        expected_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest(),
        expected_count=3,
    )
    ui_to_index = {item.ui: index for index, item in enumerate(vocabulary.descriptors)}
    source_path, source = _source(
        tmp_path,
        [
            _article("1", ["D000001", "D000002", "D000002"]),
            _article("2", ["D000001", "D000002", "D000003"]),
            _article("3", []),
        ],
    )
    shard_dir = tmp_path / "shard"

    measured = scan_source_file(
        source_path,
        source,
        shard_dir,
        ui_to_index=ui_to_index,
        vocabulary_sha256=vocabulary.sha256,
        contract_sha256="a" * 64,
    )

    assert measured.parsed_record_count == 3
    assert measured.records_without_mesh == 1
    assert measured.descriptor_assignments == 5
    assert measured.positive_pair_rows == 3
    assert measured.pair_observations == 4
    supports = np.fromfile(shard_dir / "supports.bin", dtype="<u4")
    assert supports.tolist() == [2, 2, 1]
    pmids = np.fromfile(shard_dir / "pmids.bin", dtype="<u8")
    assert pmids.tolist() == [1, 2, 3]
    pairs = np.fromfile(shard_dir / "pairs.bin", dtype=PAIR_DTYPE)
    assert pairs["key"].tolist() == [1, 2, 5]
    assert pairs["count"].tolist() == [2, 1, 1]
    checkpoint = json.loads((shard_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["readiness_contribution"] == 0
    assert "Score-free" in checkpoint["claim_boundary"]

    reused = scan_source_file(
        source_path,
        source,
        shard_dir,
        ui_to_index=ui_to_index,
        vocabulary_sha256=vocabulary.sha256,
        contract_sha256="a" * 64,
    )
    assert reused.status == "reused"


def test_source_scan_abstains_on_unknown_descriptor_or_duplicate_pmid(tmp_path):
    mesh = _mesh(tmp_path)
    vocabulary = read_vocabulary(
        mesh,
        expected_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest(),
        expected_count=3,
    )
    ui_to_index = {item.ui: index for index, item in enumerate(vocabulary.descriptors)}
    source_path, source = _source(tmp_path, [_article("1", ["D999999"])])
    with pytest.raises(CandidateIndexError, match="absent from sealed vocabulary"):
        scan_source_file(
            source_path,
            source,
            tmp_path / "unknown",
            ui_to_index=ui_to_index,
            vocabulary_sha256=vocabulary.sha256,
            contract_sha256="b" * 64,
        )
    assert not (tmp_path / "unknown" / "checkpoint.json").exists()

    source_path, source = _source(
        tmp_path,
        [_article("1", ["D000001"]), _article("1", ["D000002"])],
    )
    with pytest.raises(CandidateIndexError, match="duplicate PMID"):
        scan_source_file(
            source_path,
            source,
            tmp_path / "duplicate",
            ui_to_index=ui_to_index,
            vocabulary_sha256=vocabulary.sha256,
            contract_sha256="b" * 64,
        )
    assert not (tmp_path / "duplicate" / "checkpoint.json").exists()


def test_source_scan_refuses_checkpoint_or_complete_shard_drift(tmp_path):
    mesh = _mesh(tmp_path)
    vocabulary = read_vocabulary(
        mesh,
        expected_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest(),
        expected_count=3,
    )
    mapping = {item.ui: index for index, item in enumerate(vocabulary.descriptors)}
    source_path, source = _source(tmp_path, [_article("1", ["D000001"])])
    shard_dir = tmp_path / "shard"
    shard_dir.mkdir()
    (shard_dir / "pairs.bin").write_bytes(b"conflict")

    with pytest.raises(CandidateIndexError, match="refuses overwrite"):
        scan_source_file(
            source_path,
            source,
            shard_dir,
            ui_to_index=mapping,
            vocabulary_sha256=vocabulary.sha256,
            contract_sha256="c" * 64,
        )


def test_source_scan_revalidates_checkpoint_binary_invariants(tmp_path):
    mesh = _mesh(tmp_path)
    vocabulary = read_vocabulary(
        mesh,
        expected_sha256=hashlib.sha256(mesh.read_bytes()).hexdigest(),
        expected_count=3,
    )
    mapping = {item.ui: index for index, item in enumerate(vocabulary.descriptors)}
    source_path, source = _source(
        tmp_path,
        [_article("1", ["D000001", "D000002"]), _article("2", ["D000001"])],
    )
    shard_dir = tmp_path / "shard"
    kwargs = {
        "ui_to_index": mapping,
        "vocabulary_sha256": vocabulary.sha256,
        "contract_sha256": "d" * 64,
    }
    scan_source_file(source_path, source, shard_dir, **kwargs)

    supports = np.fromfile(shard_dir / "supports.bin", dtype="<u4")
    supports[0] = 0
    supports.tofile(shard_dir / "supports.bin")
    checkpoint_path = shard_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["outputs"]["supports"]["sha256"] = hashlib.sha256(
        (shard_dir / "supports.bin").read_bytes()
    ).hexdigest()
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(CandidateIndexError, match="shard invariants drifted"):
        scan_source_file(source_path, source, shard_dir, **kwargs)
