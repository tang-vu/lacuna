"""Build one review-approved v3 negative-case fragment from the frozen proposal queue.

The command does not edit ``cases.json`` and does not perform human adjudication. It only removes
error-prone transcription after a reviewer has published a direct decision in issue #3 or #4.

Run:
    python -m pipeline.benchmark.build_negative_case \
      --candidate-id generated-hard-2012-01-d001174-d014143 \
      --adjudication-url https://github.com/tang-vu/lacuna/issues/4#issuecomment-123 \
      --review-evidence-url https://pubmed.ncbi.nlm.nih.gov/EXAMPLE/ \
      --attest-no-metric-output \
      --negative-rationale "Reviewer-authored rationale"
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.benchmark.negative_controls import OUTPUT_PATH, audit_queue
from pipeline.benchmark.validate_v3 import NEGATIVE_QUEUE_PUBLIC_URL

ISSUES = {"hard_negative": 4, "distant_negative": 3}


class NegativeCaseBuildError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NegativeCaseBuildError(message)


def _validate_adjudication_url(url: str, kind: str) -> None:
    parts = urlsplit(url)
    expected_path = f"/tang-vu/lacuna/issues/{ISSUES[kind]}"
    _require(
        parts.scheme == "https"
        and parts.hostname == "github.com"
        and parts.path == expected_path
        and bool(re.fullmatch(r"issuecomment-\d+", parts.fragment)),
        f"{kind}: adjudication URL must link directly to a comment in issue #{ISSUES[kind]}",
    )


def _validate_review_evidence_urls(urls: list[str], adjudication_url: str) -> list[str]:
    cleaned = [url.strip() for url in urls]
    _require(bool(cleaned), "at least one public review evidence URL is required")
    _require(
        all(cleaned) and len(cleaned) == len(set(cleaned)),
        "review evidence URLs must be non-empty and unique",
    )
    for url in cleaned:
        parts = urlsplit(url)
        _require(
            parts.scheme == "https" and bool(parts.netloc),
            "review evidence URLs must use HTTPS",
        )
        _require(
            url not in {adjudication_url, NEGATIVE_QUEUE_PUBLIC_URL},
            "review evidence must be separate from the decision and frozen queue links",
        )
    return cleaned


def build_negative_case(
    candidate_id: str,
    *,
    adjudication_url: str,
    negative_rationale: str,
    review_evidence_urls: list[str],
    metric_output_blind_attestation: bool,
    queue_path: Path = OUTPUT_PATH,
) -> dict:
    """Return a validator-ready case without changing the benchmark."""
    audit_queue(queue_path)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    matches = [item for item in payload["candidates"] if item["id"] == candidate_id]
    _require(len(matches) == 1, f"unknown frozen negative proposal: {candidate_id}")
    proposal = matches[0]
    kind = proposal["kind"]
    _validate_adjudication_url(adjudication_url, kind)
    _require(
        metric_output_blind_attestation is True,
        "reviewer must explicitly attest that no candidate metric output was inspected",
    )
    evidence_urls = _validate_review_evidence_urls(review_evidence_urls, adjudication_url)
    rationale = negative_rationale.strip()
    _require(
        len(rationale) >= 40,
        "negative rationale must be reviewer-authored and at least 40 characters",
    )

    mapping_note = (
        "The descriptor is present in the pinned production-year MeSH vocabulary, but the "
        "matching historical MEDLINE citation release is not pinned; period-appropriate "
        "assignment evidence remains unavailable."
    )
    return {
        "id": candidate_id.replace("generated-", "reviewed-", 1),
        "kind": kind,
        "split": proposal["proposed_split"],
        "cutoff": proposal["cutoff"],
        "selection_stage": "pre_metric",
        "selection_candidate_id": candidate_id,
        "selection_rationale": (
            "Promoted from the frozen metric-blind proposal after the cited public review."
        ),
        "negative_rationale": rationale,
        "evidence": [
            {
                "role": "negative_selection_source",
                "label": "Frozen metric-blind negative-control queue",
                "url": NEGATIVE_QUEUE_PUBLIC_URL,
            },
            {
                "role": "metric_blind_adjudication",
                "label": "Public metric-blind review decision",
                "url": adjudication_url,
                "metric_output_blind_attestation": True,
            },
            *[
                {
                    "role": "review_evidence",
                    "label": f"Reviewer-supplied public evidence {index}",
                    "url": url,
                }
                for index, url in enumerate(evidence_urls, start=1)
            ],
        ],
        "concepts": {
            role: {
                "label": proposal["concepts"][role]["descriptor_label"],
                "mapping": {
                    "status": "unavailable",
                    "descriptor_ui": proposal["concepts"][role]["descriptor_ui"],
                    "descriptor_label": proposal["concepts"][role]["descriptor_label"],
                    "vocabulary_year": proposal["baseline_release_year"],
                    "note": mapping_note,
                },
            }
            for role in ("a", "c")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--adjudication-url", required=True)
    parser.add_argument("--review-evidence-url", action="append", default=[])
    parser.add_argument("--attest-no-metric-output", action="store_true")
    parser.add_argument("--negative-rationale", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="write a new JSON fragment; stdout is used when omitted",
    )
    args = parser.parse_args()
    try:
        case = build_negative_case(
            args.candidate_id,
            adjudication_url=args.adjudication_url,
            negative_rationale=args.negative_rationale,
            review_evidence_urls=args.review_evidence_url,
            metric_output_blind_attestation=args.attest_no_metric_output,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    rendered = json.dumps(case, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite existing case fragment: {args.output}") from None


if __name__ == "__main__":
    main()
