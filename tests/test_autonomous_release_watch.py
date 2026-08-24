from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date

import pytest

from pipeline.benchmark.autonomous_release_watch import (
    AutonomousReleaseWatchError,
    EXPECTED_RELEASES,
    audit_release_inventory,
    audit_release_watch_contract,
    audit_release_window,
    discover_release_inventory,
    probe_next_release,
)
from pipeline.benchmark.autonomous_t0 import write_new_json


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _mesh_bytes() -> bytes:
    xml = (
        "<DescriptorRecordSet><DescriptorRecord>"
        "<DescriptorUI>D000001</DescriptorUI>"
        "<DescriptorName><String>A</String></DescriptorName>"
        "</DescriptorRecord></DescriptorRecordSet>"
    ).encode()
    return gzip.compress(xml, mtime=0)


def _release_fixture(year: int):
    suffix = str(year)[-2:]
    files = {
        f"pubmed{suffix}n0001.xml.gz": b"first transport",
        f"pubmed{suffix}n0002.xml.gz": b"second transport",
    }
    base = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"
    responses: dict[str, bytes] = {}
    links = []
    for filename, content in files.items():
        links.extend(
            (
                f'<a href="{filename}">{filename}</a>',
                f'<a href="{filename}.md5">{filename}.md5</a>',
            )
        )
        responses[f"{base}{filename}.md5"] = (
            f"{hashlib.md5(content).hexdigest()}  {filename}\n".encode()
        )
    responses[base] = ("<html><body>" + "".join(links) + "</body></html>").encode()
    responses[f"{base}README.txt"] = (
        "The PubMed Baseline Repository\n"
        f"Last Updated January 30, {year}\n"
        f"The complete baseline consists of files pubmed{suffix}n0001.xml through "
        f"pubmed{suffix}n0002.xml.\n"
    ).encode()
    responses[
        f"https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc{year}.gz"
    ] = _mesh_bytes()

    def fetch(url, **_kwargs):
        return _Response(responses[url])

    return fetch


def _write_release(release_dir, year: int):
    payload = discover_release_inventory(
        release_year=year,
        observed_on=date(year, 2, 1),
        fetch=_release_fixture(year),
        workers=2,
    )
    path = release_dir / f"pubmed-{year}-remote-inventory.json"
    write_new_json(path, payload)
    return path


def test_committed_release_watch_is_frozen_no_human_and_zero_readiness():
    payload = audit_release_watch_contract()

    assert payload["required_release_years"] == list(EXPECTED_RELEASES)
    assert payload["human_dependencies"] == []
    assert payload["readiness_contribution"] == 0
    assert payload["schedule"]["manual_approval_or_labeling"] is False


def test_empty_window_waits_for_all_three_releases_without_human_dependency(tmp_path):
    audit = audit_release_window(tmp_path / "not-created")

    assert audit.state == "predictions_sealed_waiting_for_outcome"
    assert audit.verdict == "not_ready"
    assert audit.observed_releases == ()
    assert audit.missing_releases == EXPECTED_RELEASES
    assert audit.human_dependency_count == 0
    assert audit.readiness_contribution == 0


def test_release_inventory_is_official_trace_only_not_an_outcome(tmp_path):
    release_dir = tmp_path / "releases"
    path = _write_release(release_dir, 2027)
    audit = audit_release_inventory(path, as_of=date(2027, 2, 1))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert audit.release_year == 2027
    assert audit.pubmed_file_count == 2
    assert audit.mesh_descriptor_count == 1
    assert audit.readiness_contribution == 0
    assert payload["status"] == "remote_release_identity_only_not_a_verified_t1"
    assert "not a verified T1 source" in payload["claim_boundary"]
    assert "not a discovery" in payload["claim_boundary"]


def test_probe_waits_normally_before_next_release_exists(tmp_path):
    window, written = probe_next_release(
        tmp_path / "releases",
        observed_on=date(2026, 8, 24),
        fetch=_release_fixture(2026),
        workers=2,
    )

    assert written is None
    assert window.verdict == "not_ready"
    assert window.missing_releases == EXPECTED_RELEASES


def test_probe_pins_only_next_release_and_advances_machine_state(tmp_path):
    release_dir = tmp_path / "releases"
    window, written = probe_next_release(
        release_dir,
        observed_on=date(2027, 2, 1),
        fetch=_release_fixture(2027),
        workers=2,
    )

    assert written == release_dir / "pubmed-2027-remote-inventory.json"
    assert written.is_file()
    assert window.observed_releases == (2027,)
    assert window.missing_releases == (2028, 2029)
    assert window.verdict == "not_ready"


def test_complete_sequential_window_advances_only_to_awaiting_t1_source(tmp_path):
    release_dir = tmp_path / "releases"
    for year in EXPECTED_RELEASES:
        _write_release(release_dir, year)

    audit = audit_release_window(release_dir, as_of=date(2029, 2, 1))

    assert audit.identifiers_complete is True
    assert audit.state == "awaiting_t1_baseline"
    assert audit.verdict == "not_ready"
    assert audit.blockers == (
        "the complete official 2029 T1 source is not locally checksum-verified",
    )


def test_out_of_order_or_missed_release_abstains_instead_of_backfilling(tmp_path):
    release_dir = tmp_path / "releases"
    _write_release(release_dir, 2028)

    audit = audit_release_window(release_dir, as_of=date(2028, 2, 1))

    assert audit.state == "abstained"
    assert audit.verdict == "abstained"
    assert "out of order" in audit.blockers[0]

    empty_dir = tmp_path / "empty"
    missed, written = probe_next_release(
        empty_dir,
        observed_on=date(2028, 2, 1),
        fetch=_release_fixture(2028),
        workers=2,
    )
    assert written is None
    assert missed.verdict == "abstained"
    assert "before release 2027 was pinned" in missed.blockers[0]


def test_release_inventory_refuses_overwrite_and_claim_drift(tmp_path):
    release_dir = tmp_path / "releases"
    path = _write_release(release_dir, 2027)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["readiness_contribution"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomousReleaseWatchError, match="readiness drifted"):
        audit_release_inventory(path)

    with pytest.raises(Exception, match="refusing to overwrite"):
        _write_release(release_dir, 2027)
