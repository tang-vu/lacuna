from __future__ import annotations

import random
import shutil
import struct
import subprocess
from array import array
from decimal import Decimal

import numpy as np
import pytest

from pipeline.benchmark.bioasq_v2_development import (
    CORPUS_HEADER,
    CORPUS_MAGIC,
    DOCUMENT_HEADER,
    EDGE_DTYPE,
    EDGE_HEADER,
    EDGE_MAGIC,
    NATIVE_SOURCE_PATH,
    SCORE_BOUNDS_SOURCE_PATH,
    BioasqDevelopmentError,
    EdgeGraph,
    NodeIndex,
    _read_edge_header,
    _write_new_json,
    decimal_jaccard,
    load_development_cases,
    load_edge_graph,
    score_seed,
    score_seed_with_bounds,
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


def test_executor_loads_only_the_frozen_development_population():
    cases = load_development_cases()

    assert len(cases) == 11
    assert {int(case.cutoff[:4]) for case in cases} == {2011, 2012}
    assert sum(case.kind == "source_labeled_positive" for case in cases) == 3
    assert sum(case.kind == "hard_negative" for case in cases) == 4
    assert sum(case.kind == "distant_negative" for case in cases) == 4
    assert all("heldout" not in case.id for case in cases)


def test_decimal_jaccard_uses_exact_integer_counts():
    assert decimal_jaccard(5, 10, 10) == Decimal(
        "0.3333333333333333333333333333333333333333"
    )

    with pytest.raises(BioasqDevelopmentError, match="exceeds descriptor support"):
        decimal_jaccard(11, 10, 10)


def test_score_seed_implements_sum_of_jaccard_path_minima_and_worst_tie_rank(tmp_path):
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

    lower_support = score_seed(
        graph,
        seed_id=0,
        target_id=3,
        threshold=5,
        node_index=_node_index(),
    )
    primary = score_seed(
        graph,
        seed_id=0,
        target_id=3,
        threshold=10,
        node_index=_node_index(),
    )

    assert lower_support["target_persisted_score"] == "0.403846153846154"
    assert lower_support["direct_ac_article_count"] == 1
    assert lower_support["eligible_candidate_count"] == 4
    assert lower_support["target_worst_tie_rank"] == 1
    assert lower_support["target_top_5_percent"] is False
    assert lower_support["target_bridge_count"] == 2
    assert [item["descriptor_ui"] for item in lower_support["top_target_bridges"]] == [
        "D000002",
        "D000003",
    ]
    assert primary["target_persisted_score"] == "0.250000000000000"
    assert primary["eligible_candidate_count"] == 3
    assert primary["target_bridge_count"] == 1


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_integer_bounds_screener_matches_decimal_oracle_on_small_graph(tmp_path):
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
    executable = _compile_bounds_helper(tmp_path)

    expected = score_seed(
        graph,
        seed_id=0,
        target_id=3,
        threshold=5,
        node_index=_node_index(),
    )
    measured = score_seed_with_bounds(
        graph,
        executable=executable,
        seed_id=0,
        target_id=3,
        threshold=5,
        node_index=_node_index(),
    )

    assert {key: measured[key] for key in expected} == expected
    assert measured["rank_proof"] == {
        "method": "exact_integer_rational_bounds_then_python_decimal_refinement",
        "bound_scale_exponent": 21,
        "decimal_guard_scaled_units": 1_000_000,
        "zero_target_nonnegative_shortcut": False,
        "bound_proven_at_or_above_count": 0,
        "bound_proven_below_count": 3,
        "exact_decimal_refinement_count": 1,
        "exact_decimal_at_or_above_count": 1,
        "partition_candidate_count": 4,
    }


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_integer_bounds_screener_proves_zero_target_rank_from_nonnegative_scores(tmp_path):
    graph = _write_edge_graph(
        tmp_path / "edges.bin",
        cutoff=2011,
        supports=[10, 10, 10, 10, 10],
        edges=[(0, 1, 5), (1, 2, 4), (2, 3, 3)],
    )
    executable = _compile_bounds_helper(tmp_path)

    expected = score_seed(
        graph,
        seed_id=0,
        target_id=4,
        threshold=10,
        node_index=_node_index(),
    )
    measured = score_seed_with_bounds(
        graph,
        executable=executable,
        seed_id=0,
        target_id=4,
        threshold=10,
        node_index=_node_index(),
    )

    assert {key: measured[key] for key in expected} == expected
    assert measured["target_persisted_score"] == "0.000000000000000"
    assert measured["target_worst_tie_rank"] == 4
    assert measured["rank_proof"]["zero_target_nonnegative_shortcut"] is True
    assert measured["rank_proof"]["bound_proven_at_or_above_count"] == 3


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_integer_bounds_screener_matches_decimal_oracle_on_deterministic_random_graphs(
    tmp_path,
):
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

        expected = score_seed(
            graph,
            seed_id=0,
            target_id=target_id,
            threshold=10,
            node_index=node_index,
        )
        measured = score_seed_with_bounds(
            graph,
            executable=executable,
            seed_id=0,
            target_id=target_id,
            threshold=10,
            node_index=node_index,
        )

        assert {key: measured[key] for key in expected} == expected


def test_edge_header_rejects_truncated_artifacts(tmp_path):
    path = tmp_path / "broken.bin"
    path.write_bytes(EDGE_HEADER.pack(EDGE_MAGIC, 5, 2011, 2))

    with pytest.raises(BioasqDevelopmentError, match="byte length mismatch"):
        _read_edge_header(path)


def test_review_output_refuses_overwrite(tmp_path):
    path = tmp_path / "review.json"
    _write_new_json(path, {"status": "first"})

    with pytest.raises(BioasqDevelopmentError, match="refusing to overwrite"):
        _write_new_json(path, {"status": "second"})


@pytest.mark.skipif(shutil.which("g++") is None, reason="g++ is unavailable")
def test_native_pair_counter_builds_cumulative_case_blind_graphs(tmp_path):
    executable = tmp_path / "counter.exe"
    subprocess.run(
        [
            shutil.which("g++"),
            "-O2",
            "-std=c++20",
            str(NATIVE_SOURCE_PATH),
            "-o",
            str(executable),
        ],
        check=True,
    )
    corpus = tmp_path / "corpus.bin"
    with corpus.open("wb") as stream:
        stream.write(CORPUS_HEADER.pack(CORPUS_MAGIC, 5, 2, 2011, 2012))
        for _ in range(5):
            stream.write(DOCUMENT_HEADER.pack(0, 3))
            array("H", [0, 1, 3]).tofile(stream)
        for _ in range(5):
            stream.write(DOCUMENT_HEADER.pack(1, 3))
            array("H", [0, 2, 3]).tofile(stream)
    first_path = tmp_path / "edges-2011.bin"
    second_path = tmp_path / "edges-2012.bin"

    subprocess.run(
        [str(executable), str(corpus), str(first_path), str(second_path)],
        check=True,
    )
    first = load_edge_graph(first_path, 2011)
    second = load_edge_graph(second_path, 2012)

    assert first.support.tolist() == [5, 5, 0, 5, 0]
    assert first.edge_count == 3
    assert first.edges.tolist() == [(0, 1, 5), (0, 3, 5), (1, 3, 5)]
    assert second.support.tolist() == [10, 5, 5, 10, 0]
    assert second.edge_count == 5
    assert second.edges.tolist() == [
        (0, 1, 5),
        (0, 2, 5),
        (0, 3, 10),
        (1, 3, 5),
        (2, 3, 5),
    ]
