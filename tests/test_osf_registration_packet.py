from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pipeline.export.build_osf_registration_packet import (
    OUTPUT,
    PACKET_FILES,
    REGISTERED_FILES,
    ROOT,
    build_manifest,
)


def test_registration_manifest_is_current_and_complete() -> None:
    expected = build_manifest()
    stored = json.loads(OUTPUT.read_text(encoding="utf-8"))

    assert stored == expected
    assert set(stored["packet_files"]) == set(PACKET_FILES)
    assert set(stored["registered_files"]) == set(REGISTERED_FILES)
    assert stored["submission_status"] == "prepared_not_submitted"
    assert stored["not_a_new_preregistration"] is True
    assert stored["release_doi"] is None

    for relative_path, record in {
        **stored["packet_files"],
        **stored["registered_files"],
    }.items():
        raw = (ROOT / relative_path).read_bytes()
        assert record["bytes"] == len(raw)
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()


def test_registration_keeps_claim_and_timing_boundaries_visible() -> None:
    text = (Path(ROOT) / "registrations/autonomous-prospective-v1/registration.md").read_text(
        encoding="utf-8"
    )

    assert "registration of prior sealed state" in text
    assert "not a claim of prospective preregistration made today" in text
    assert "Validated knowledge-gap pairs: zero." in text
    assert "verdict is `not_ready`" in text
    assert re.search(r"readiness\s+contribution is zero", text)
    assert "No T1 outcomes have been inspected." in text
    assert "It would not\nvalidate a general knowledge-gap detector" in text
