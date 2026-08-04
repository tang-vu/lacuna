from __future__ import annotations

import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
PUBLIC = ROOT / "web" / "public"
SOCIAL_CARD = ROOT / "web" / "public" / "social-card.png"
PROJECT_STATUS = ROOT / "artifacts" / "project-status.json"


def png_dimensions(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", raw[16:24])


def test_search_and_social_metadata_are_wired_to_the_canonical_production_url():
    html = INDEX.read_text(encoding="utf-8")

    assert '<link rel="canonical" href="https://lacuna.tangvu.dev/"' in html
    assert 'name="robots"' in html
    assert "max-image-preview:large" in html
    assert (
        '<meta property="og:image" content="https://lacuna.tangvu.dev/social-card.png"'
        in html
    )
    assert '<meta property="og:image:width" content="1200"' in html
    assert '<meta property="og:image:height" content="630"' in html
    assert '<meta name="twitter:card" content="summary_large_image"' in html
    assert 'name="twitter:image:alt"' in html
    assert "failed metrics, evidence, and blind spots are public" in html
    assert '<link rel="manifest" href="/site.webmanifest"' in html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml"' in html


def test_structured_data_describes_the_visible_project_without_overclaiming():
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.DOTALL
    )

    assert match is not None
    data = json.loads(match.group(1))
    nodes = {node["@type"]: node for node in data["@graph"]}
    assert {"WebSite", "WebPage", "SoftwareSourceCode"} <= nodes.keys()
    assert nodes["WebSite"]["url"] == "https://lacuna.tangvu.dev/"
    assert (
        nodes["SoftwareSourceCode"]["codeRepository"]
        == "https://github.com/tang-vu/lacuna"
    )
    assert "failed pre-registered validation" in nodes["SoftwareSourceCode"]["description"]
    assert "discovery" not in nodes["SoftwareSourceCode"]["keywords"]


def test_initial_html_contains_meaningful_honest_content_without_javascript():
    html = INDEX.read_text(encoding="utf-8")

    assert '<main id="main-content">' in html
    assert "<h1>Map the edge of what we know.</h1>" in html
    assert "A public experiment, not a discovery engine." in html
    assert "Metric versions 1 and 2 failed their pre-registered benchmark" in html
    assert "Loading…" not in html
    assert "indigenous, oral, or other non-academic knowledge" in html


def test_social_preview_is_an_optimized_landscape_png():
    assert png_dimensions(SOCIAL_CARD) == (1200, 630)
    assert SOCIAL_CARD.stat().st_size < 2 * 1024 * 1024


def test_favicon_and_install_icons_are_complete_and_square():
    assert (PUBLIC / "favicon.svg").read_text(encoding="utf-8").startswith("<svg")
    assert (PUBLIC / "favicon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"

    expected_pngs = {
        "favicon-48x48.png": (48, 48),
        "apple-touch-icon.png": (180, 180),
        "icon-192.png": (192, 192),
        "icon-512.png": (512, 512),
        "icon-maskable-512.png": (512, 512),
    }
    for filename, dimensions in expected_pngs.items():
        assert png_dimensions(PUBLIC / filename) == dimensions

    manifest = json.loads((PUBLIC / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["start_url"] == "/"
    assert manifest["theme_color"] == "#fbfaf7"
    assert {icon["purpose"] for icon in manifest["icons"]} == {"any", "maskable"}


def test_crawler_files_are_valid_and_the_404_is_not_indexable():
    robots = (PUBLIC / "robots.txt").read_text(encoding="utf-8")
    sitemap = ET.parse(PUBLIC / "sitemap.xml")
    locations = sitemap.findall(
        ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
    )
    not_found = (PUBLIC / "404.html").read_text(encoding="utf-8")

    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Disallow:" not in robots
    assert "Sitemap: https://lacuna.tangvu.dev/sitemap.xml" in robots
    assert [location.text for location in locations] == ["https://lacuna.tangvu.dev/"]
    assert '<meta name="robots" content="noindex, follow"' in not_found


def test_core_contribution_issue_forms_are_present():
    issue_templates = ROOT / ".github" / "ISSUE_TEMPLATE"

    assert (ROOT / "CONTRIBUTING.md").is_file()
    assert (ROOT / "CITATION.cff").is_file()
    assert (issue_templates / "historical-source.yml").is_file()
    assert (issue_templates / "benchmark-case.yml").is_file()
    assert (issue_templates / "curated-hole.yml").is_file()
    assert (issue_templates / "bug-report.yml").is_file()


def test_generated_contribution_surface_reads_the_validated_status_artifact():
    data_source = (ROOT / "web" / "src" / "data.ts").read_text(encoding="utf-8")
    view_source = (ROOT / "web" / "src" / "views" / "contribute.ts").read_text(
        encoding="utf-8"
    )

    assert PROJECT_STATUS.is_file()
    assert "fetchJson<ProjectStatus>('/project-status.json')" in data_source
    assert "provenanceChip('generated')" in view_source
    assert "issues/6" in view_source
    assert "issues/7" in view_source
    assert "milestone/1" in view_source


def test_evidence_lab_keeps_failure_before_interaction_and_exports_provenance():
    view_source = (ROOT / "web" / "src" / "views" / "computed.ts").read_text(
        encoding="utf-8"
    )

    assert view_source.index("verdictBanner(computed)") < view_source.index(
        "explorer(computed)"
    )
    assert "failed validation—not candidate discoveries" in view_source
    assert "'observed_kind'" in view_source
    assert "'verification_query'" in view_source
    assert "gap.row_source_urls" in view_source


def test_candidate_review_desk_keeps_proposals_curated_and_out_of_readiness():
    view_source = (ROOT / "web" / "src" / "views" / "contribute.ts").read_text(
        encoding="utf-8"
    )

    assert "METRIC-BLIND REVIEW DESK" in view_source
    assert "provenanceChip('curated')" in view_source
    assert "proposed · 0 readiness" in view_source
    assert "proposals count as 0" in view_source
    assert "candidate.mapping_audit.limitation" in view_source
    assert "candidate.open_questions" in view_source
    assert "candidate.evidence.map" in view_source


def test_source_recovery_copy_keeps_preservation_metadata_out_of_raw_readiness():
    view_source = (ROOT / "web" / "src" / "views" / "contribute.ts").read_text(
        encoding="utf-8"
    )

    assert "historical MBR directory" in view_source
    assert "metadata is a target, not the records" in view_source


def test_shareable_hole_atlas_is_generated_from_versioned_curated_artifacts():
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    builder = (ROOT / "web" / "scripts" / "build-share-pages.mjs").read_text(
        encoding="utf-8"
    )
    curated_view = (ROOT / "web" / "src" / "views" / "curated.ts").read_text(
        encoding="utf-8"
    )

    assert "node scripts/build-share-pages.mjs" in package["scripts"]["build"]
    assert "latest.json" in builder
    assert "curated.json" in builder
    assert "written by a person" in builder
    assert "not a computed discovery or an actionable hypothesis" in builder
    assert "sitemap.xml" in builder
    assert "metric_blind" not in builder
    assert "navigator.share" in curated_view
    assert "share this hole" in curated_view
    assert "id: `hole-${entry.id}`" in curated_view
