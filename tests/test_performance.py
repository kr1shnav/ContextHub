from pathlib import Path

import pytest

from context_hub.performance import TimedOperation, _copy_repository, percentile, timing_stats, validate_repeats


def test_percentile_uses_nearest_rank_for_small_samples():
    assert percentile([3.0], 95) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
    assert timing_stats([]).median_seconds is None


def test_repeat_validation():
    assert validate_repeats(3, 1) == (3, 1)
    with pytest.raises(ValueError): validate_repeats(0, 0)
    with pytest.raises(ValueError): validate_repeats(101, 0)
    with pytest.raises(ValueError): validate_repeats(1, 21)


def test_empty_and_failure_timing_inputs_are_safe():
    assert percentile([], 95) is None
    assert timing_stats([0.1, 0.3]).median_seconds == pytest.approx(0.2)
    operation = TimedOperation(operation="search", stats=timing_stats([]), failures=["RuntimeError: unavailable"])
    assert operation.failures


def test_benchmark_fixture_copy_isolated_from_real_index(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / ".context-hub").mkdir()
    (source / ".context-hub" / "index.db").write_text("real", encoding="utf-8")
    (source / "module.py").write_text("value = 1\n", encoding="utf-8")
    target = tmp_path / "target"
    _copy_repository(source, target)
    assert not (target / ".context-hub").exists()
    assert (source / ".context-hub" / "index.db").read_text(encoding="utf-8") == "real"
