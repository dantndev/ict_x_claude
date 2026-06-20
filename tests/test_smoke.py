"""Smoke test for Phase 0 — verifies the package imports."""

import ict_bot


def test_package_version() -> None:
    assert isinstance(ict_bot.__version__, str)
    assert ict_bot.__version__.count(".") == 2
