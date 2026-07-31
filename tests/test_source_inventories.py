from __future__ import annotations

import hashlib
import json

import pytest

from pipeline.benchmark.source_inventories import (
    InventoryContractError,
    load_inventory_contract,
    parse_inventory_html,
)
from pipeline.benchmark.validate_sources import SOURCES_PATH

INVENTORIES_PATH = SOURCES_PATH.parent / "inventories.json"


def _reference() -> dict[str, str]:
    return {
        "path": "inventories.json",
        "sha256": hashlib.sha256(INVENTORIES_PATH.read_bytes()).hexdigest(),
    }


def test_committed_inventory_contract_pins_all_official_metadata_targets():
    contract = load_inventory_contract(
        SOURCES_PATH,
        _reference(),
        {2007, 2011, 2012, 2013},
    )

    assert [item.release_year for item in contract.releases] == [2007, 2011, 2012, 2013]
    assert [item.file_count for item in contract.releases] == [538, 653, 684, 717]
    assert [item.total_record_count for item in contract.releases] == [
        16_120_074,
        19_569_568,
        20_494_848,
        21_508_439,
    ]
    assert all(
        item.inventory_url.startswith("https://www.nlm.nih.gov/")
        for item in contract.releases
    )


def test_inventory_parser_sums_every_file_row_and_rejects_gaps():
    html = """
    <html><body>
      <p>The 2012 MEDLINE/PubMed baseline database contains 3 records and contains
      300 bytes, thus requiring disk space.</p>
      <table>
        <tr><th>File Name</th><th>Number of Records</th></tr>
        <tr><td>medline12n0002.xml</td><td>3</td></tr>
      </table>
      <table>
        <tr><th>Filename</th><th>Years</th><th>Uncompressed</th><th>Compressed</th></tr>
        <tr><td>medline12n0001.xml</td><td>2010</td><td>100</td><td>10</td></tr>
        <tr><td>medline12n0002.xml</td><td>2011</td><td>200</td><td>20</td></tr>
      </table>
    </body></html>
    """

    observed = parse_inventory_html(html, 2012, "https://www.nlm.nih.gov/example")

    assert observed.file_count == 2
    assert observed.last_file_record_count == 3
    assert observed.total_record_count == 3
    assert observed.total_uncompressed_bytes == 300
    assert observed.total_compressed_bytes == 30

    with pytest.raises(InventoryContractError, match="not contiguous"):
        parse_inventory_html(html.replace("n0002", "n0003"), 2012, observed.url)


def test_inventory_checksum_and_record_arithmetic_are_load_bearing(tmp_path):
    payload = json.loads(INVENTORIES_PATH.read_text(encoding="utf-8"))
    payload["releases"][0]["last_file_record_count"] += 1
    path = tmp_path / "inventories.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    reference = {
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    source_path = tmp_path / "sources.json"

    with pytest.raises(InventoryContractError, match="record total does not reconcile"):
        load_inventory_contract(source_path, reference)

    reference["sha256"] = "0" * 64
    with pytest.raises(InventoryContractError, match="checksum mismatch"):
        load_inventory_contract(source_path, reference)
