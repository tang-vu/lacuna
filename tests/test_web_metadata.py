from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
SOCIAL_CARD = ROOT / "web" / "public" / "social-card.png"


def test_social_preview_is_wired_to_the_canonical_production_url():
    html = INDEX.read_text(encoding="utf-8")

    assert '<link rel="canonical" href="https://lacuna.tangvu.dev/"' in html
    assert (
        '<meta property="og:image" content="https://lacuna.tangvu.dev/social-card.png"'
        in html
    )
    assert '<meta name="twitter:card" content="summary_large_image"' in html
    assert "failed—and the evidence is public" in html


def test_social_preview_is_a_reasonably_sized_landscape_png():
    raw = SOCIAL_CARD.read_bytes()

    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (1536, 1024)
    assert len(raw) < 5 * 1024 * 1024


def test_core_contribution_issue_forms_are_present():
    issue_templates = ROOT / ".github" / "ISSUE_TEMPLATE"

    assert (ROOT / "CONTRIBUTING.md").is_file()
    assert (ROOT / "CITATION.cff").is_file()
    assert (issue_templates / "historical-source.yml").is_file()
    assert (issue_templates / "benchmark-case.yml").is_file()
    assert (issue_templates / "bug-report.yml").is_file()
