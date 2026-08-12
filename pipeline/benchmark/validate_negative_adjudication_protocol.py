"""Validate the frozen negative-control human-review protocol.

The protocol was written after the terminal BioASQ pilot result but before any metric-v3 formula
or human negative-control decision. It contributes no decisions or readiness.

Run: ``python -m pipeline.benchmark.validate_negative_adjudication_protocol``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.benchmark.metric_blind import find_forbidden_fields
from pipeline.benchmark.negative_controls import OUTPUT_PATH as QUEUE_PATH, PROTOCOL_PATH
from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

ADJUDICATION_PROTOCOL_PATH = REPO_ROOT / "benchmarks" / "v3" / "negative-adjudication-protocol.json"
EXPECTED_STATUS = "frozen_before_human_adjudication_after_bioasq_terminal_result"


class NegativeAdjudicationProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class NegativeAdjudicationProtocolAudit:
    status: str
    common_check_count: int
    hard_check_count: int
    distant_check_count: int
    metric_v3_blind: bool
    bioasq_output_disclosed: bool
    readiness_contribution: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NegativeAdjudicationProtocolError(message)


def _identity(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_payload(payload),
        "canonicalisation": "canonical-json-v1",
    }


def _text_list(value: object, context: str, *, minimum: int) -> list[str]:
    _require(isinstance(value, list), f"{context}: expected a list")
    _require(
        len(value) >= minimum
        and all(isinstance(item, str) and len(item.strip()) >= 20 for item in value),
        f"{context}: needs at least {minimum} substantive text entries",
    )
    return value


def audit_negative_adjudication_protocol(
    path: Path = ADJUDICATION_PROTOCOL_PATH,
    *,
    selection_path: Path = PROTOCOL_PATH,
    queue_path: Path = QUEUE_PATH,
) -> NegativeAdjudicationProtocolAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(payload.get("schema_version") == 1, "unsupported adjudication protocol schema")
    _require(payload.get("status") == EXPECTED_STATUS, "adjudication protocol status drifted")
    _require(payload.get("frozen_on") == "2026-08-12", "adjudication freeze date drifted")
    _require(payload.get("metric_v3_blind") is True, "protocol must remain metric-v3 blind")
    _require(payload.get("readiness_contribution") == 0, "protocol cannot add readiness")
    _require(not find_forbidden_fields(payload), "protocol contains metric output fields")
    _require(
        payload.get("inputs")
        == {
            "selection_protocol": _identity(selection_path),
            "candidate_queue": _identity(queue_path),
        },
        "adjudication protocol input identities drifted",
    )

    timing = payload.get("authoring_timing")
    _require(isinstance(timing, dict), "missing authoring timing")
    _require(
        timing.get("metric_v3_formula_or_outputs_seen") is False
        and timing.get("bioasq_v2_pilot_outputs_seen") is True
        and timing.get("human_negative_control_decisions_seen") is False,
        "authoring timing or BioASQ disclosure drifted",
    )
    disclosure = timing.get("disclosure")
    _require(
        isinstance(disclosure, str)
        and "does not claim" in disclosure
        and "blind" in disclosure
        and "no candidate-level decision" in disclosure,
        "BioASQ timing disclosure is incomplete",
    )

    blinding = payload.get("reviewer_blinding")
    _require(isinstance(blinding, dict), "missing reviewer blinding contract")
    _require(
        blinding.get("public_attestation_required") is True
        and "cannot prove" in str(blinding.get("enforcement_limit")),
        "reviewer blinding must disclose its enforcement limit",
    )
    forbidden_material = str(blinding.get("requirement"))
    for term in ("score", "rank", "ordering", "bridge", "BioASQ"):
        _require(term in forbidden_material, f"reviewer blinding omits {term}")

    query_contract = payload.get("literature_query_contract")
    _require(isinstance(query_contract, dict), "missing literature query contract")
    _require(
        query_contract.get("service_url") == "https://pubmed.ncbi.nlm.nih.gov/"
        and query_contract.get("documentation_url")
        == "https://pubmed.ncbi.nlm.nih.gov/help/#searching-by-a-specific-field",
        "PubMed provenance drifted",
    )
    _require(
        query_contract.get("mesh_pair_before_cutoff_template")
        == '"{label_a}"[mh:noexp] AND "{label_c}"[mh:noexp] AND '
        "1800/01/01:{cutoff_slash}[dp]"
        and query_contract.get("exact_phrase_pair_before_cutoff_template")
        == '"{label_a}"[tiab] AND "{label_c}"[tiab] AND '
        "1800/01/01:{cutoff_slash}[dp]",
        "literature query templates drifted",
    )
    limitations = _text_list(query_contract.get("limitations"), "query limitations", minimum=4)
    limitations_text = " ".join(limitations).lower()
    for phrase in (
        "maintained indexing",
        "do not reconstruct",
        "zero-result",
        "non-academic",
        "not persisted",
    ):
        _require(phrase in limitations_text, f"query limitations omit {phrase}")

    common = _text_list(payload.get("common_review_checks"), "common checks", minimum=5)
    checks = payload.get("kind_specific_review_checks")
    _require(
        isinstance(checks, dict) and set(checks) == {"hard_negative", "distant_negative"},
        "kind-specific checks must cover both cohorts",
    )
    hard = _text_list(checks["hard_negative"], "hard checks", minimum=3)
    distant = _text_list(checks["distant_negative"], "distant checks", minimum=3)
    _require(
        "relatedness alone is not a rejection" in " ".join(hard).lower(),
        "hard controls must not reuse the distant-control relatedness rule",
    )
    _require(
        "substantively distant" in " ".join(distant).lower()
        and "plausibly related" in " ".join(distant).lower(),
        "distant controls need a substantive-distance review rule",
    )

    decision = payload.get("decision_contract")
    _require(isinstance(decision, dict), "missing decision contract")
    _require(
        decision.get("allowed_decisions") == ["accept", "reject", "defer"],
        "decision vocabulary drifted",
    )
    requirements = _text_list(
        decision.get("acceptance_requires"), "acceptance requirements", minimum=5
    )
    requirements_text = " ".join(requirements).lower()
    for phrase in ("direct public", "attestation", "evidence url", "candidate id"):
        _require(phrase in requirements_text, f"acceptance requirements omit {phrase}")
    _require(
        "cannot substitute for expert judgment" in str(decision.get("validator_limit")),
        "validator claim boundary drifted",
    )
    claim_boundary = str(payload.get("claim_boundary"))
    for phrase in (
        "not human adjudication",
        "evidence of absent knowledge",
        "benchmark readiness",
        "replacement metric",
    ):
        _require(phrase in claim_boundary, f"claim boundary omits {phrase}")

    return NegativeAdjudicationProtocolAudit(
        status=payload["status"],
        common_check_count=len(common),
        hard_check_count=len(hard),
        distant_check_count=len(distant),
        metric_v3_blind=True,
        bioasq_output_disclosed=True,
        readiness_contribution=0,
    )


def main() -> None:
    audit = audit_negative_adjudication_protocol()
    print("negative adjudication protocol: structurally valid")
    print(f"status: {audit.status}")
    print(f"common checks: {audit.common_check_count}")
    print(f"hard/distant checks: {audit.hard_check_count}/{audit.distant_check_count}")
    print("metric-v3 blind: true")
    print("BioASQ output timing disclosed: true")
    print("readiness contribution: 0")


if __name__ == "__main__":
    main()
