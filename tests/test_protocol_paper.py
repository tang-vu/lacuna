from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
PAPER_DIR = ROOT / "papers" / "autonomous-prospective-protocol"


def test_protocol_paper_keeps_scientific_boundaries_visible() -> None:
    paper = (PAPER_DIR / "paper.tex").read_text(encoding="utf-8")

    assert "validated knowledge-gap pairs number zero" in paper
    assert "verdict is \\texttt{not\\_ready}" in paper
    assert re.search(r"readiness\s+contribution is zero", paper)
    assert "no T1 outcome has been inspected" in paper
    assert re.search(r"not\s+represented as a new preregistration", paper)
    assert re.search(r"not knowledge-gap\s+detection", paper)
    assert re.search(r"It was not\s+used to score, rank, filter, or label T0 candidates", paper)


def test_protocol_paper_counts_match_sealed_records() -> None:
    paper = (PAPER_DIR / "paper.tex").read_text(encoding="utf-8")

    for value in (
        "1,334",
        "54,267,874,919",
        "39,994,988",
        "31,110",
        "7,310,895",
        "7,310,826",
        "31,760,211",
        "51,128,229",
    ):
        assert value in paper


def test_protocol_paper_references_have_verified_dois() -> None:
    bibliography = (PAPER_DIR / "references.bib").read_text(encoding="utf-8")
    expected = {
        "10.1353/pbm.1986.0087",
        "10.1002/(SICI)1097-4571(199602)47:2<116::AID-ASI3>3.0.CO;2-1",
        "10.1002/asi.1104",
        "10.1186/s12859-017-1641-9",
        "10.1016/S0378-8733(03)00009-1",
        "10.1038/s41597-022-01710-x",
    }

    assert expected <= set(re.findall(r"(?m)^  doi = \{([^}]+)\}", bibliography))


def test_protocol_paper_leaves_submission_identity_fields_explicit() -> None:
    paper = (PAPER_DIR / "paper.tex").read_text(encoding="utf-8")

    assert paper.count("TO BE SUPPLIED BEFORE SUBMISSION") == 7
    assert not (PAPER_DIR / "paper.pdf").exists() or (PAPER_DIR / "paper.pdf").stat().st_size > 0
