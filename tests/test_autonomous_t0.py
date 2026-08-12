from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date

import pytest

from pipeline.benchmark.autonomous_t0 import (
    REMOTE_INVENTORY_PATH,
    AutonomousT0Error,
    audit_remote_inventory,
    discover_remote_inventory,
    seal_local_t0,
    write_new_json,
)


def _mesh_bytes() -> bytes:
    xml = (
        "<DescriptorRecordSet><DescriptorRecord>"
        "<DescriptorUI>D000001</DescriptorUI>"
        "<DescriptorName><String>A</String></DescriptorName>"
        "</DescriptorRecord></DescriptorRecordSet>"
    ).encode()
    return gzip.compress(xml, mtime=0)


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _remote_fixture(*, omit_second_checksum_link: bool = False):
    files = {
        "pubmed26n0001.xml.gz": b"first transport",
        "pubmed26n0002.xml.gz": b"second transport",
    }
    links = []
    responses: dict[str, bytes] = {}
    base = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"
    for filename, content in files.items():
        links.append(f'<a href="{filename}">{filename}</a>')
        checksum_name = f"{filename}.md5"
        if not (omit_second_checksum_link and "0002" in filename):
            links.append(f'<a href="{checksum_name}">{checksum_name}</a>')
        responses[f"{base}{checksum_name}"] = (
            f"{hashlib.md5(content).hexdigest()}  {filename}\n".encode()
        )
    index = "<html><body>" + "".join(links) + "</body></html>"
    readme = """The PubMed Baseline Repository
Last Updated January 30, 2026
The complete baseline consists of files pubmed26n0001.xml through pubmed26n0002.xml.
"""
    responses[base] = index.encode()
    responses[f"{base}README.txt"] = readme.encode()
    mesh_url = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.gz"
    responses[mesh_url] = _mesh_bytes()

    def fetch(url, **_kwargs):
        return _Response(responses[url])

    return fetch, files


def test_remote_discovery_pins_complete_official_checksum_set_without_calling_it_t0():
    fetch, _files = _remote_fixture()

    inventory = discover_remote_inventory(
        release_year=2026,
        observed_on=date(2026, 8, 12),
        fetch=fetch,
        workers=2,
    )

    assert inventory["status"] == "remote_inventory_only_not_a_verified_t0"
    assert inventory["readiness_contribution"] == 0
    assert inventory["human_dependencies"] == []
    assert inventory["pubmed_baseline"]["expected_file_count"] == 2
    assert [item["filename"] for item in inventory["pubmed_baseline"]["files"]] == [
        "pubmed26n0001.xml.gz",
        "pubmed26n0002.xml.gz",
    ]
    assert all(len(item["official_md5"]) == 32 for item in inventory["pubmed_baseline"]["files"])
    assert len(inventory["mesh_descriptor"]["observed_transport_sha256"]) == 64


def test_committed_remote_inventory_is_complete_but_contributes_zero_readiness():
    audit = audit_remote_inventory()

    assert audit.path == REMOTE_INVENTORY_PATH
    assert audit.release_year == 2026
    assert audit.pubmed_file_count == 1334
    assert audit.mesh_descriptor_count == 31110
    assert audit.status == "remote_inventory_only_not_a_verified_t0"
    assert audit.readiness_contribution == 0


def test_remote_inventory_identity_is_line_ending_independent(tmp_path):
    payload = json.loads(REMOTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    crlf_path = tmp_path / "inventory.json"
    crlf_path.write_bytes(
        (json.dumps(payload, indent=2) + "\n").replace("\n", "\r\n").encode()
    )

    assert audit_remote_inventory(crlf_path).sha256 == audit_remote_inventory().sha256


def test_remote_discovery_rejects_an_incomplete_checksum_listing():
    fetch, _files = _remote_fixture(omit_second_checksum_link=True)

    with pytest.raises(AutonomousT0Error, match="checksum listing is incomplete"):
        discover_remote_inventory(
            release_year=2026,
            observed_on=date(2026, 8, 12),
            fetch=fetch,
            workers=2,
        )


def _write_pubmed_file(path, pmid: str) -> None:
    article = (
        "<PubmedArticle><MedlineCitation>"
        f"<PMID>{pmid}</PMID>"
        "<Article><Journal><JournalIssue><PubDate><Year>2025</Year>"
        "</PubDate></JournalIssue></Journal></Article>"
        "<MeshHeadingList><MeshHeading>"
        '<DescriptorName UI="D000001">A</DescriptorName>'
        "</MeshHeading></MeshHeadingList>"
        "</MedlineCitation></PubmedArticle>"
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(f"<PubmedArticleSet>{article}</PubmedArticleSet>")


def test_local_seal_requires_every_file_checks_hashes_and_refuses_overwrite(tmp_path):
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    first = baseline_dir / "pubmed26n0001.xml.gz"
    second = baseline_dir / "pubmed26n0002.xml.gz"
    _write_pubmed_file(first, "1")
    _write_pubmed_file(second, "2")
    mesh = tmp_path / "desc2026.gz"
    mesh.write_bytes(_mesh_bytes())

    fetch, _files = _remote_fixture()
    inventory = discover_remote_inventory(
        release_year=2026,
        observed_on=date(2026, 8, 12),
        fetch=fetch,
        workers=2,
    )
    for item, path in zip(inventory["pubmed_baseline"]["files"], (first, second), strict=True):
        item["official_md5"] = hashlib.md5(path.read_bytes()).hexdigest()

    inventory_path = tmp_path / "remote-inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    output = tmp_path / "sealed-t0.json"
    manifest = seal_local_t0(inventory_path, baseline_dir, mesh, output)

    assert manifest["status"] == "locally_verified_complete_t0"
    assert manifest["state_transition"] == {
        "from": "awaiting_t0_baseline",
        "to": "awaiting_frozen_metric",
    }
    assert manifest["total_record_count"] == 2
    assert all(len(item["sha256"]) == 64 for item in manifest["pubmed_baseline"]["files"])
    with pytest.raises(AutonomousT0Error, match="refusing to overwrite"):
        seal_local_t0(inventory_path, baseline_dir, mesh, output)


def test_local_seal_abstains_on_transport_drift_before_writing(tmp_path):
    fetch, _files = _remote_fixture()
    inventory = discover_remote_inventory(
        release_year=2026,
        observed_on=date(2026, 8, 12),
        fetch=fetch,
        workers=2,
    )
    inventory_path = tmp_path / "remote-inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    for index in (1, 2):
        (baseline_dir / f"pubmed26n{index:04d}.xml.gz").write_bytes(b"drift")
    mesh = tmp_path / "desc2026.gz"
    mesh.write_bytes(_mesh_bytes())
    output = tmp_path / "sealed-t0.json"

    with pytest.raises(AutonomousT0Error, match="official MD5 mismatch"):
        seal_local_t0(inventory_path, baseline_dir, mesh, output)

    assert not output.exists()


def test_exclusive_json_writer_never_replaces_prior_evidence(tmp_path):
    output = tmp_path / "evidence.json"
    write_new_json(output, {"first": True})

    with pytest.raises(AutonomousT0Error, match="refusing to overwrite"):
        write_new_json(output, {"first": False})

    assert json.loads(output.read_text(encoding="utf-8")) == {"first": True}
