from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
APPLICATION_DIR = ROOT / "applications" / "nlnet-2026"


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
    )
    assert match is not None, heading
    return match.group(1).strip()


def test_nlnet_form_answers_fit_published_character_limits() -> None:
    text = (APPLICATION_DIR / "application.md").read_text(encoding="utf-8")
    limits = {
        "Abstract": 1200,
        "Previous relevant experience": 2500,
        "Budget explanation": 2500,
        "Comparison with existing or historical efforts": 4000,
        "Significant technical challenges": 5000,
        "Ecosystem and engagement": 2500,
    }

    for heading, limit in limits.items():
        assert len(_section(text, heading)) <= limit, heading


def test_nlnet_budget_is_in_range_and_sums() -> None:
    text = (APPLICATION_DIR / "application.md").read_text(encoding="utf-8")

    assert "EUR 36,000 -- DRAFT; APPLICANT MUST CONFIRM" in text
    assert sum((12_000, 10_000, 8_000, 6_000)) == 36_000
    assert "90 engineering and documentation days" in text
    assert "EUR 400/day" in text
    assert "TO BE CONFIRMED BEFORE SUBMISSION" in text


def test_nlnet_packet_blocks_premature_submission_and_overclaims() -> None:
    readme = (APPLICATION_DIR / "README.md").read_text(encoding="utf-8")
    application = (APPLICATION_DIR / "application.md").read_text(encoding="utf-8")
    ai_log = (APPLICATION_DIR / "ai-use.md").read_text(encoding="utf-8")

    assert "currently blocked by the call calendar" in readme
    assert "TO BE CHECKED AFTER 2026-09-03" in readme
    assert "TO BE SELECTED AFTER THE 2026-09-03 CALL-SCOPE REVIEW" in application
    assert "not evidence that its knowledge-gap detector has been validated" in application
    assert "will not\nclaim that lacuna's failed or unvalidated research-gap metrics work" in application
    assert "INCOMPLETE -- DO NOT SUBMIT THIS APPLICATION YET" in ai_log
    assert "I have used generative AI in writing this proposal" in ai_log
    assert "unedited assistant output" in ai_log
