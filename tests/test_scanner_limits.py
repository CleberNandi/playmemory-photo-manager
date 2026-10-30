"""Budgets must bound enumeration itself, including entries never statted."""

import os
from pathlib import PurePosixPath

import pytest

from playmemories_photo_manager.evidence import StructuralValidation, evaluate
from playmemories_photo_manager.scanner import (
    ScanLimits,
    ScanOptions,
    ScanResourceLimitError,
    ScanStatus,
    scan,
    service,
)


@pytest.fixture(params=[False, True], ids=["descriptor", "fallback"])
def walk_mode(request, monkeypatch):
    if request.param:
        monkeypatch.setattr(service, "_descriptor_walk_supported", lambda: False)


@pytest.mark.parametrize("value", [-1, True, 1.5, "2000", None])
def test_invalid_limit_values(value):
    with pytest.raises(ValueError):
        ScanLimits(max_entries=value)
    with pytest.raises(ValueError):
        ScanLimits(max_depth=value)


def test_options_require_typed_limits():
    with pytest.raises(TypeError):
        ScanOptions(limits={"max_entries": 2})


def test_zero_budget_allows_only_empty_root(tmp_path, walk_mode):
    assert scan(tmp_path, ScanOptions(limits=ScanLimits(0, 0))).is_complete
    (tmp_path / "file").touch()
    with pytest.raises(ScanResourceLimitError) as caught:
        scan(tmp_path, ScanOptions(limits=ScanLimits(0, 0)))
    assert caught.value.reason == "max_entries"
    assert caught.value.observed_count == 1
    assert str(caught.value) == "resource_limit"
    assert str(tmp_path) not in repr(caught.value)


def test_2000_boundary_and_no_result_on_2001(tmp_path, walk_mode):
    for i in range(2000):
        (tmp_path / f"{i:04}.jpg").touch()
    result = scan(tmp_path, ScanOptions(limits=ScanLimits()))
    assert len(result.entries) == 2000
    assert result.is_complete
    assert evaluate(result).structural_validation is StructuralValidation.VALID
    (tmp_path / "last").touch()
    with pytest.raises(ScanResourceLimitError) as caught:
        scan(tmp_path, ScanOptions(limits=ScanLimits()))
    assert caught.value.observed_count == 2001


def test_stops_before_sort_stat_and_unbounded_materialization(tmp_path, monkeypatch, walk_mode):
    class Child:
        @property
        def name(self):
            # First name access is allowed for computing depth, not for sorting.
            self.calls += 1
            assert self.calls == 1
            return "synthetic"

        def __init__(self):
            self.calls = 0

    class Enumeration:
        consumed = 0
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.closed = True

        def __iter__(self):
            return self

        def __next__(self):
            self.consumed += 1
            assert self.consumed <= 4, "enumeration must stop at budget + sentinel"
            return Child()

    iterator = Enumeration()
    # _descriptor_walk_supported tests scandir membership, so pin before replacing it.
    descriptor = service._descriptor_walk_supported()
    monkeypatch.setattr(service, "_descriptor_walk_supported", lambda: descriptor)
    monkeypatch.setattr(service.os, "scandir", lambda _root: iterator)
    monkeypatch.setattr(service, "_stat_entry", lambda _entry: pytest.fail("no stat before limit"))
    before = set(os.listdir("/proc/self/fd")) if descriptor else None
    with pytest.raises(ScanResourceLimitError):
        scan(tmp_path, ScanOptions(limits=ScanLimits(3, 32)))
    assert iterator.consumed == 4
    assert iterator.closed
    if before is not None:
        assert set(os.listdir("/proc/self/fd")) == before


def test_global_budget_counts_directories_links_other_and_failed_stat(
    tmp_path, monkeypatch, walk_mode
):
    (tmp_path / "a-directory").mkdir()
    (tmp_path / "a-directory" / "child").touch()
    (tmp_path / "link").symlink_to("a-directory", target_is_directory=True)
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "vanished").touch()
    original = service._stat_entry

    def stat_entry(entry):
        if entry.name == "vanished":
            raise FileNotFoundError
        return original(entry)

    monkeypatch.setattr(service, "_stat_entry", stat_entry)
    with pytest.raises(ScanResourceLimitError) as caught:
        scan(tmp_path, ScanOptions(limits=ScanLimits(4, 32)))
    assert caught.value.observed_count == 5
    result = scan(tmp_path, ScanOptions(limits=ScanLimits(5, 32)))
    assert result.status is ScanStatus.PARTIAL
    assert len(result.entries) == 4
    assert len(result.failures) == 1
    assert evaluate(result).structural_validation is StructuralValidation.VALID


def test_depth_32_empty_is_complete_and_child_at_33_exhausts(tmp_path, walk_mode):
    directory = tmp_path
    for _ in range(32):
        directory /= "nested"
        directory.mkdir()
    result = scan(tmp_path, ScanOptions(limits=ScanLimits()))
    assert len(result.entries) == 32
    assert result.is_complete
    assert evaluate(result).structural_validation is StructuralValidation.VALID
    (directory / "child").touch()
    with pytest.raises(ScanResourceLimitError) as caught:
        scan(tmp_path, ScanOptions(limits=ScanLimits()))
    assert caught.value.reason == "max_depth"
    assert caught.value.depth == 33
    assert caught.value.observed_count == 33


def test_cancellation_during_enumeration_closes_iterator(tmp_path, monkeypatch, walk_mode):
    for i in range(10):
        (tmp_path / str(i)).touch()
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 4

    result = scan(tmp_path, ScanOptions(limits=ScanLimits(), cancellation_requested=cancelled))
    assert result.status is ScanStatus.CANCELLED
    assert result.entries == ()
    assert result.covered_directories == ()
    assert evaluate(result).structural_validation is StructuralValidation.VALID


def test_budget_is_not_shared_between_scans(tmp_path, walk_mode):
    (tmp_path / "entry").touch()
    options = ScanOptions(limits=ScanLimits(1, 1))
    assert scan(tmp_path, options).is_complete
    assert scan(tmp_path, options).is_complete
    assert len(PurePosixPath(".").parts) == 0
