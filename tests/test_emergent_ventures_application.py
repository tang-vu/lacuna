from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
APPLICATION_DIR = ROOT / "applications" / "emergent-ventures"


def _visible_word_count(markdown: str) -> int:
    without_headings = re.sub(r"(?m)^#+\s+", "", markdown)
    return len(re.findall(r"\b[\w'-]+\b", without_headings))


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        text,
    )
    assert match is not None, heading
    return match.group(1).strip()


def test_emergent_ventures_proposal_fits_word_limit() -> None:
    proposal = (APPLICATION_DIR / "proposal.md").read_text(encoding="utf-8")

    assert _visible_word_count(proposal) <= 1500
    assert "APPLICANT MUST REPLACE THIS PARAGRAPH IN THEIR OWN WORDS" in proposal
    assert "DRAFT -- APPLICANT MUST CONFIRM THIS IS TRUE" in proposal


def test_emergent_ventures_budget_and_tweet_fit_form() -> None:
    fields = (APPLICATION_DIR / "form-fields.md").read_text(encoding="utf-8")
    tweet = _section(fields, "Idea in a tweet")

    assert len(tweet) <= 295
    assert _section(fields, "Estimated budget") == "25000"
    assert sum((20_000, 2_000, 1_500, 1_500)) == 25_000
    assert "USD 40/hour" in fields
    assert "No certification or consent has been given" in fields


def test_emergent_ventures_packet_does_not_overclaim_or_submit() -> None:
    readme = (APPLICATION_DIR / "README.md").read_text(encoding="utf-8")
    proposal = (APPLICATION_DIR / "proposal.md").read_text(encoding="utf-8")

    assert "not submitted" in readme
    assert "Submission confirmation: **NONE**" in readme
    assert "remains unvalidated and explicitly\nnot ready" in proposal
    assert "instead of calling them discoveries" in proposal
    assert "not that lacuna discovers a scientific gap" in proposal
    assert "not a new workflow engine, research database, ontology, or AI scientist" in proposal
