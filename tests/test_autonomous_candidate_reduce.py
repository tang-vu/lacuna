from __future__ import annotations

import hashlib

import numpy as np
import pytest

from pipeline.benchmark.autonomous_candidate_index import PAIR_DTYPE, CandidateIndexError, VocabularyDescriptor
from pipeline.benchmark.autonomous_candidate_reduce import (
    GLOBAL_PAIR_DTYPE,
    RunArtifact,
    audit_candidate_stream,
    build_exclusions,
    merge_run_group,
    reduce_supports,
    write_candidate_stream,
)


def _run(path, array, format):
    array.tofile(path)
    raw = path.read_bytes()
    return RunArtifact(
        path=path,
        format=format,
        rows=int(array.size),
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
    )


def _pairs(rows, dtype=PAIR_DTYPE):
    result = np.empty(len(rows), dtype=dtype)
    result["key"] = [row[0] for row in rows]
    result["count"] = [row[1] for row in rows]
    return result


def test_pmid_merge_is_sorted_checkpointed_reused_and_rejects_cross_file_duplicate(tmp_path):
    left = _run(tmp_path / "left.bin", np.array([1, 4], dtype="<u8"), "pmid-u64-v1")
    right = _run(tmp_path / "right.bin", np.array([2, 3], dtype="<u8"), "pmid-u64-v1")
    output = tmp_path / "merged.bin"

    merged = merge_run_group(
        [left, right],
        output,
        kind="pmids",
        contract_sha256="a" * 64,
        vocabulary_size=5,
        denominator=4,
    )
    assert np.fromfile(output, dtype="<u8").tolist() == [1, 2, 3, 4]
    assert merge_run_group(
        [left, right],
        output,
        kind="pmids",
        contract_sha256="a" * 64,
        vocabulary_size=5,
        denominator=4,
    ) == merged

    duplicate = _run(tmp_path / "duplicate.bin", np.array([4, 5], dtype="<u8"), "pmid-u64-v1")
    with pytest.raises(CandidateIndexError, match="duplicate PMID"):
        merge_run_group(
            [left, duplicate],
            tmp_path / "duplicate-output.bin",
            kind="pmids",
            contract_sha256="a" * 64,
            vocabulary_size=5,
            denominator=10,
        )


def test_pair_merge_sums_equal_keys_exactly(tmp_path):
    left = _run(
        tmp_path / "left-pairs.bin",
        _pairs([(1, 2), (6, 1)]),
        "pair-u64-u32-v1",
    )
    right = _run(
        tmp_path / "right-pairs.bin",
        _pairs([(1, 3), (11, 2)]),
        "pair-u64-u32-v1",
    )
    output = tmp_path / "pairs.bin"

    merged = merge_run_group(
        [left, right],
        output,
        kind="pairs",
        contract_sha256="b" * 64,
        vocabulary_size=4,
        denominator=10,
    )

    assert merged.format == "pair-u64-u64-v1"
    pairs = np.fromfile(output, dtype=GLOBAL_PAIR_DTYPE)
    assert pairs["key"].tolist() == [1, 6, 11]
    assert pairs["count"].tolist() == [5, 1, 2]


def test_support_reduce_uses_uint64_and_checks_shape_and_denominator(tmp_path):
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    np.array([2, 0, 1], dtype="<u4").tofile(first)
    np.array([3, 1, 1], dtype="<u4").tofile(second)
    output = tmp_path / "supports.bin"

    reduced = reduce_supports(
        [first, second],
        output,
        vocabulary_size=3,
        denominator=5,
    )
    assert reduced.bytes == 24
    assert np.fromfile(output, dtype="<u8").tolist() == [5, 1, 2]

    with pytest.raises(CandidateIndexError, match="shape drifted"):
        reduce_supports([first], tmp_path / "bad.bin", vocabulary_size=4, denominator=5)


def test_exclusions_and_candidate_stream_apply_only_frozen_zero_count_gates(tmp_path):
    vocabulary = (
        VocabularyDescriptor("D000001", "One", ("A01",), ("one",)),
        VocabularyDescriptor("D000002", "Two", ("A01.100",), ("two",)),
        VocabularyDescriptor("D000003", "Three", ("C01",), ("shared",)),
        VocabularyDescriptor("D000004", "Four", ("D01",), ("shared",)),
        VocabularyDescriptor("D000005", "Low", ("E01",), ("low",)),
    )
    exclusions = build_exclusions(vocabulary)
    assert exclusions[0].tolist() == [1]
    assert exclusions[1].tolist() == [0]
    assert exclusions[2].tolist() == [3]
    assert exclusions[3].tolist() == [2]
    supports = tmp_path / "supports.bin"
    np.array([100, 100, 100, 100, 50], dtype="<u8").tofile(supports)
    positives = tmp_path / "positive.bin"
    _pairs([(2, 1)], dtype=GLOBAL_PAIR_DTYPE).tofile(positives)  # key 0 * 5 + 2
    output = tmp_path / "candidates.bin"

    result = write_candidate_stream(
        supports,
        positives,
        output,
        vocabulary=vocabulary,
        denominator=1000,
    )

    assert result.rows == 3
    assert np.fromfile(output, dtype="<u8").tolist() == [3, 7, 8]
    assert audit_candidate_stream(
        supports,
        positives,
        output,
        vocabulary=vocabulary,
        denominator=1000,
    ) == result

    np.array([3, 7], dtype="<u8").tofile(output)
    with pytest.raises(CandidateIndexError, match="not exhaustive"):
        audit_candidate_stream(
            supports,
            positives,
            output,
            vocabulary=vocabulary,
            denominator=1000,
        )
