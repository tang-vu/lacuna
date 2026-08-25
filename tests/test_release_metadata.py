from __future__ import annotations

import re
import tomllib
from datetime import date
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_release_metadata_agrees_on_version_and_date() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = ROOT / "docs" / "releases" / f"v{version}.md"

    assert re.search(rf"(?m)^version: {re.escape(version)}$", citation)
    released = re.search(r"(?m)^date-released: (\d{4}-\d{2}-\d{2})$", citation)
    assert released is not None
    date.fromisoformat(released.group(1))
    assert f"## [{version}]" in changelog
    assert release_notes.is_file()


def test_release_notes_keep_scientific_boundaries_visible() -> None:
    notes = (ROOT / "docs" / "releases" / "v0.2.0.md").read_text(encoding="utf-8")

    assert "Validated knowledge-gap pairs: zero." in notes
    assert "remains `not_ready` with zero readiness contribution" in notes
    assert "predictions from an unvalidated method, not discoveries" in notes
    assert "They are not claims of causality" in notes
    assert re.search(r"byte-level\s+replay requires those pinned local\s+files", notes)
