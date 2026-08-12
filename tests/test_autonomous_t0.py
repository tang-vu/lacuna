from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date

import pytest
import requests

from pipeline.benchmark.autonomous_t0 import (
    REMOTE_INVENTORY_PATH,
    AutonomousT0Error,
    _download_verified_transport,
    _promote_verified_part,
    audit_remote_inventory,
    audit_sealed_t0,
    discover_remote_inventory,
    download_t0_sources,
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


class _StreamResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]

    def close(self) -> None:
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


def _download_fixture(tmp_path):
    discovery_fetch, files = _remote_fixture()
    inventory = discover_remote_inventory(
        release_year=2026,
        observed_on=date(2026, 8, 12),
        fetch=discovery_fetch,
        workers=2,
    )
    inventory_path = tmp_path / "remote-inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    resources = {
        item["url"]: files[item["filename"]]
        for item in inventory["pubmed_baseline"]["files"]
    }
    resources[inventory["mesh_descriptor"]["url"]] = _mesh_bytes()
    requests_seen: list[tuple[str, str | None]] = []

    def fetch(url, *, headers, **_kwargs):
        range_header = headers.get("Range")
        requests_seen.append((url, range_header))
        content = resources[url]
        if range_header:
            offset = int(range_header.removeprefix("bytes=").removesuffix("-"))
            return _StreamResponse(
                content[offset:],
                status_code=206,
                headers={"Content-Range": f"bytes {offset}-{len(content) - 1}/{len(content)}"},
            )
        return _StreamResponse(content)

    return inventory_path, inventory, resources, fetch, requests_seen


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


def test_downloader_acquires_every_transport_on_destination_and_reuses_verified_files(tmp_path):
    inventory_path, inventory, resources, fetch, _requests_seen = _download_fixture(tmp_path)
    baseline_dir = tmp_path / "storage" / "baseline"
    mesh_path = tmp_path / "storage" / "mesh" / "desc2026.gz"

    first = download_t0_sources(
        inventory_path,
        baseline_dir,
        mesh_path,
        workers=2,
        minimum_free_bytes=0,
        fetch=fetch,
    )

    assert first.transport_count == 3
    assert first.downloaded_count == 3
    assert first.reused_count == 0
    assert first.readiness_contribution == 0
    assert first.verified_bytes == sum(len(content) for content in resources.values())
    for item in inventory["pubmed_baseline"]["files"]:
        assert (baseline_dir / item["filename"]).read_bytes() == resources[item["url"]]
        assert not (baseline_dir / f"{item['filename']}.part").exists()
    assert mesh_path.read_bytes() == _mesh_bytes()

    def no_network(_url, **_kwargs):
        raise AssertionError("verified complete transports must not hit the network")

    second = download_t0_sources(
        inventory_path,
        baseline_dir,
        mesh_path,
        workers=2,
        minimum_free_bytes=0,
        fetch=no_network,
    )
    assert second.downloaded_count == 0
    assert second.reused_count == 3


def test_downloader_resumes_part_file_with_an_http_range(tmp_path):
    inventory_path, inventory, resources, fetch, requests_seen = _download_fixture(tmp_path)
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    first = inventory["pubmed_baseline"]["files"][0]
    prefix = resources[first["url"]][:5]
    (baseline_dir / f"{first['filename']}.part").write_bytes(prefix)
    mesh_path = tmp_path / "mesh" / "desc2026.gz"

    result = download_t0_sources(
        inventory_path,
        baseline_dir,
        mesh_path,
        workers=1,
        minimum_free_bytes=0,
        fetch=fetch,
    )

    assert result.downloaded_count == 3
    assert (first["url"], "bytes=5-") in requests_seen
    assert (baseline_dir / first["filename"]).read_bytes() == resources[first["url"]]


def test_transport_resumes_after_an_interrupted_response(tmp_path):
    content = b"a transport that survives a dropped connection"
    destination = tmp_path / "transport.gz"
    requests_seen: list[str | None] = []

    class InterruptedResponse(_StreamResponse):
        def iter_content(self, chunk_size: int):
            yield self.content[:11]
            raise requests.ConnectionError("connection dropped")

    def fetch(_url, *, headers, **_kwargs):
        range_header = headers.get("Range")
        requests_seen.append(range_header)
        if range_header is None:
            return InterruptedResponse(content)
        assert range_header == "bytes=11-"
        return _StreamResponse(
            content[11:],
            status_code=206,
            headers={"Content-Range": f"bytes 11-{len(content) - 1}/{len(content)}"},
        )

    outcome, size = _download_verified_transport(
        url="https://example.test/transport.gz",
        destination=destination,
        algorithm="sha256",
        expected_digest=hashlib.sha256(content).hexdigest(),
        expected_bytes=len(content),
        fetch=fetch,
    )

    assert (outcome, size) == ("downloaded", len(content))
    assert requests_seen == [None, "bytes=11-"]
    assert destination.read_bytes() == content
    assert not destination.with_name("transport.gz.part").exists()


def test_downloader_refuses_conflicting_complete_file_without_overwriting(tmp_path):
    inventory_path, inventory, _resources, fetch, _requests_seen = _download_fixture(tmp_path)
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    first = inventory["pubmed_baseline"]["files"][0]
    conflict = baseline_dir / first["filename"]
    conflict.write_bytes(b"do not replace")

    with pytest.raises(AutonomousT0Error, match="refusing to overwrite conflicting"):
        download_t0_sources(
            inventory_path,
            baseline_dir,
            tmp_path / "mesh" / "desc2026.gz",
            workers=1,
            minimum_free_bytes=0,
            fetch=fetch,
        )

    assert conflict.read_bytes() == b"do not replace"


def test_downloader_keeps_final_bad_part_and_never_promotes_it(tmp_path):
    destination = tmp_path / "transport.gz"

    def corrupt_fetch(_url, **_kwargs):
        return _StreamResponse(b"corrupt")

    with pytest.raises(AutonomousT0Error, match="checksum or byte count mismatch"):
        _download_verified_transport(
            url="https://example.test/transport.gz",
            destination=destination,
            algorithm="sha256",
            expected_digest=hashlib.sha256(b"expected").hexdigest(),
            expected_bytes=len(b"expected"),
            fetch=corrupt_fetch,
        )

    assert not destination.exists()
    assert destination.with_name("transport.gz.part").read_bytes() == b"corrupt"


def test_promotion_refuses_a_destination_that_appears_after_download(tmp_path):
    part = tmp_path / "transport.gz.part"
    destination = tmp_path / "transport.gz"
    part.write_bytes(b"verified bytes")
    destination.write_bytes(b"concurrent evidence")

    with pytest.raises(AutonomousT0Error, match="refusing to replace a file that appeared"):
        _promote_verified_part(part, destination)

    assert destination.read_bytes() == b"concurrent evidence"
    assert part.read_bytes() == b"verified bytes"


def test_downloader_checks_free_space_before_network_or_source_writes(tmp_path):
    inventory_path, _inventory, _resources, _fetch, _requests_seen = _download_fixture(tmp_path)

    with pytest.raises(AutonomousT0Error, match="insufficient free space"):
        download_t0_sources(
            inventory_path,
            tmp_path / "baseline",
            tmp_path / "mesh" / "desc2026.gz",
            minimum_free_bytes=10**30,
            fetch=lambda *_args, **_kwargs: pytest.fail("network must not be called"),
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
    progress = []
    manifest = seal_local_t0(
        inventory_path,
        baseline_dir,
        mesh,
        output,
        workers=2,
        progress=lambda completed, total, filename: progress.append(
            (completed, total, filename)
        ),
    )

    assert manifest["status"] == "locally_verified_complete_t0"
    assert manifest["state_transition"] == {
        "from": "awaiting_t0_baseline",
        "to": "awaiting_frozen_metric",
    }
    assert manifest["total_record_count"] == 2
    assert [item["filename"] for item in manifest["pubmed_baseline"]["files"]] == [
        "pubmed26n0001.xml.gz",
        "pubmed26n0002.xml.gz",
    ]
    assert progress == [
        (1, 2, "pubmed26n0001.xml.gz"),
        (2, 2, "pubmed26n0002.xml.gz"),
    ]
    assert all(len(item["sha256"]) == 64 for item in manifest["pubmed_baseline"]["files"])
    audit = audit_sealed_t0(output, inventory_path)
    assert audit.pubmed_file_count == 2
    assert audit.pubmed_record_count == 2
    assert audit.pubmed_bytes == first.stat().st_size + second.stat().st_size
    assert audit.mesh_descriptor_count == 1
    assert audit.state == "awaiting_frozen_metric"
    assert audit.readiness_contribution == 0
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


def test_local_seal_rejects_an_unsafe_worker_count_before_writing(tmp_path):
    output = tmp_path / "sealed-t0.json"

    with pytest.raises(AutonomousT0Error, match="seal workers must be between 1 and 8"):
        seal_local_t0(
            tmp_path / "missing-inventory.json",
            tmp_path / "missing-baseline",
            tmp_path / "missing-mesh.gz",
            output,
            workers=9,
        )

    assert not output.exists()


def test_sealed_t0_audit_rejects_record_count_drift(tmp_path):
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
    seal_local_t0(inventory_path, baseline_dir, mesh, output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["pubmed_baseline"]["files"][0]["total_record_count"] = 2
    output.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomousT0Error, match="record subtotal drifted"):
        audit_sealed_t0(output, inventory_path)


def test_exclusive_json_writer_never_replaces_prior_evidence(tmp_path):
    output = tmp_path / "evidence.json"
    write_new_json(output, {"first": True})

    with pytest.raises(AutonomousT0Error, match="refusing to overwrite"):
        write_new_json(output, {"first": False})

    assert json.loads(output.read_text(encoding="utf-8")) == {"first": True}
