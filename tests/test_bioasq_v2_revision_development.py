from __future__ import annotations

import random
import shutil
import subprocess
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

import numpy as np
import pytest

from pipeline.benchmark.bioasq_v2_development import (
    EDGE_DTYPE,
    EDGE_HEADER,
    EDGE_MAGIC,
    DECIMAL_PRECISION,
    FORMULA_QUANTUM,
    SCORE_BOUNDS_SOURCE_PATH,
    NodeIndex,
    decimal_jaccard,
    load_edge_graph,
)
from pipeline.benchmark.bioasq_v2_revision_development import (
    BioasqRevisionDevelopmentError,
    _gate_decision,
    _revised_decimal,
    score_seed_revision,
)


def _write_edge_graph(path, *, cutoff, supports, edges):
    with path.open("wb") as stream:
        stream.write(EDGE_HEADER.pack(EDGE_MAGIC, len(supports), cutoff, len(edges)))
        stream.write(np.asarray(supports, dtype="<u4").tobytes())
        stream.write(np.asarray(edges, dtype=EDGE_DTYPE).tobytes())
    return load_edge_graph(path, cutoff)


def _node_index():
    uis = ("D000001", "D000002", "D000003", "D000004", "D000005")
    labels = ("A", "B1", "B2", "C", "D")
    return NodeIndex(
        uis=uis,
        labels=labels,
        normalised_label_to_id={label.casefold(): index for index, label in enumerate(labels)},
        ui_to_id={ui: index for index, ui in enumerate(uis)},
    )


def _compile_bounds_helper(tmp_path):
    executable = tmp_path / "bounds.exe"
    subprocess.run(
        [
            shutil.which("g++"),
            "-O2",
            "-std=c++20",
            str(SCORE_BOUNDS_SOURCE_PATH),
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


def test_revision_decimal_divides_once_after_the_indirect_sum():
    assert _revised_decimal(Decimal("1.151138480117359"), 17) == Decimal(
        "0.06771402824219758823529411764705882352941"
    )

    with pytest.raises(BioasqRevisionDevelopmentError, match="positive integer"):
        _revised_decimal(Decimal("1"), 0)


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_revision_scorer_applies_direct_penalty_and_exact_rank_proof(tmp_path):
    graph = _write_edge_graph(
        tmp_path / "edges.bin",
        cutoff=2011,
        supports=[10, 10, 5, 10, 10],
        edges=[
            (0, 1, 5),
            (0, 2, 2),
            (0, 3, 1),
            (1, 3, 4),
            (1, 4, 1),
            (2, 3, 5),
        ],
    )
    measured = score_seed_revision(
        graph,
        executable=_compile_bounds_helper(tmp_path),
        seed_id=0,
        target_id=3,
        threshold=5,
        node_index=_node_index(),
    )

    assert measured["direct_ac_article_count"] == 1
    assert measured["target_direct_penalty"] == 2
    assert measured["target_indirect_decimal_score"] == (
        "0.4038461538461538461538461538461538461538"
    )
    assert measured["target_revised_decimal_before_quantization"] == (
        "0.2019230769230769230769230769230769230769"
    )
    assert measured["target_persisted_revised_score"] == "0.201923076923077"
    assert measured["target_worst_tie_rank"] == 1
    assert measured["rank_proof"]["partition_candidate_count"] == 4
    assert measured["rank_proof"]["exact_decimal_at_or_above_count"] == 1


def _brute_revision(graph, *, seed_id, target_id, threshold):
    adjacency = [dict() for _ in range(graph.node_count)]
    for left, right, count in graph.edges.tolist():
        adjacency[left][right] = count
        adjacency[right][left] = count
    eligible = [int(value) >= threshold for value in graph.support]
    persisted = {}
    indirect_scores = {}
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        for candidate_id in range(graph.node_count):
            if not eligible[candidate_id] or candidate_id == seed_id:
                continue
            indirect = Decimal(0)
            for bridge_id in range(graph.node_count):
                if (
                    bridge_id in (seed_id, candidate_id)
                    or not eligible[bridge_id]
                    or bridge_id not in adjacency[seed_id]
                    or bridge_id not in adjacency[candidate_id]
                ):
                    continue
                jaccard_ab = decimal_jaccard(
                    adjacency[seed_id][bridge_id],
                    int(graph.support[seed_id]),
                    int(graph.support[bridge_id]),
                )
                jaccard_bc = decimal_jaccard(
                    adjacency[bridge_id][candidate_id],
                    int(graph.support[bridge_id]),
                    int(graph.support[candidate_id]),
                )
                indirect += min(jaccard_ab, jaccard_bc)
            revised = indirect / Decimal(1 + adjacency[seed_id].get(candidate_id, 0))
            indirect_scores[candidate_id] = indirect
            persisted[candidate_id] = revised.quantize(
                FORMULA_QUANTUM, rounding=ROUND_HALF_EVEN
            )
    return {
        "indirect": indirect_scores[target_id],
        "persisted": persisted[target_id],
        "rank": sum(score >= persisted[target_id] for score in persisted.values()),
        "candidate_count": len(persisted),
    }


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_revision_bounds_match_brute_decimal_on_deterministic_random_graphs(tmp_path):
    executable = _compile_bounds_helper(tmp_path)
    generator = random.Random(20260812)
    node_count = 12
    node_index = NodeIndex(
        uis=tuple(f"D{node:06d}" for node in range(node_count)),
        labels=tuple(f"node-{node}" for node in range(node_count)),
        normalised_label_to_id={f"node-{node}": node for node in range(node_count)},
        ui_to_id={f"D{node:06d}": node for node in range(node_count)},
    )
    for trial in range(12):
        supports = [generator.randint(10, 60) for _ in range(node_count)]
        edges = []
        for left in range(node_count):
            for right in range(left + 1, node_count):
                if generator.random() < 0.38:
                    edges.append(
                        (left, right, generator.randint(1, min(supports[left], supports[right])))
                    )
        graph = _write_edge_graph(
            tmp_path / f"random-{trial}.bin",
            cutoff=2011,
            supports=supports,
            edges=edges,
        )
        target_id = 1 + trial % (node_count - 1)

        expected = _brute_revision(
            graph,
            seed_id=0,
            target_id=target_id,
            threshold=10,
        )
        measured = score_seed_revision(
            graph,
            executable=executable,
            seed_id=0,
            target_id=target_id,
            threshold=10,
            node_index=node_index,
        )

        assert Decimal(measured["target_indirect_decimal_score"]) == expected["indirect"]
        assert Decimal(measured["target_persisted_revised_score"]) == expected["persisted"]
        assert measured["target_worst_tie_rank"] == expected["rank"]
        assert measured["eligible_candidate_count"] == expected["candidate_count"]


def _summary(positive, hard, distant):
    return {
        str(threshold): {
            "source_labeled_positive": {
                "case_count": 3,
                "top_5_percent_count": positive,
                "below_median_count": 0,
            },
            "hard_negative": {
                "case_count": 4,
                "top_5_percent_count": hard,
                "below_median_count": 0,
            },
            "distant_negative": {
                "case_count": 4,
                "top_5_percent_count": 0,
                "below_median_count": distant,
            },
        }
        for threshold in (10, 5)
    }


def test_revision_gate_passes_only_the_frozen_all_requirements_pattern():
    decision = _gate_decision(_summary(positive=2, hard=0, distant=4))

    assert decision["pre_registered_gate_passed"] is True
    assert decision["mechanical_action"] == "freeze_exact_revision_as_final_before_heldout"
    assert decision["readiness_contribution"] == 0


@pytest.mark.parametrize(
    ("positive", "hard", "distant"),
    [(1, 0, 4), (2, 1, 4), (2, 0, 3)],
)
def test_revision_gate_failure_mechanically_terminates_before_heldout(
    positive,
    hard,
    distant,
):
    decision = _gate_decision(_summary(positive=positive, hard=hard, distant=distant))

    assert decision["pre_registered_gate_passed"] is False
    assert decision["mechanical_action"] == "terminate_pilot_before_heldout"
    assert decision["readiness_contribution"] == 0
