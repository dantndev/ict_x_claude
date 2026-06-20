"""Tests for killzones / news block / lunch / force-flatten (concept 13)."""

from __future__ import annotations

from datetime import datetime

from ict_bot.sessions.killzones import (
    force_flat,
    kz_active,
    lunch,
    new_entries_allowed,
    news_block,
    silver_bullet_am,
)
from ict_bot.utils.tz import NY


def _ny(hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 6, 20, hh, mm, tzinfo=NY)


def test_london_kz_active():
    assert kz_active(_ny(2, 30)) is True


def test_ny_am_kz_active():
    assert kz_active(_ny(9, 0)) is True


def test_idle_outside_kz():
    assert kz_active(_ny(6, 0)) is False
    assert kz_active(_ny(17, 0)) is False


def test_news_block():
    assert news_block(_ny(8, 30)) is True
    assert news_block(_ny(8, 34)) is True
    assert news_block(_ny(8, 35)) is False


def test_lunch():
    assert lunch(_ny(12, 30)) is True
    assert lunch(_ny(13, 0)) is False


def test_force_flat():
    assert force_flat(_ny(16, 30)) is True
    assert force_flat(_ny(16, 29)) is False


def test_silver_bullet_am():
    assert silver_bullet_am(_ny(10, 30)) is True
    assert silver_bullet_am(_ny(11, 0)) is False


def test_new_entries_allowed_during_news_block_disabled():
    assert new_entries_allowed(_ny(8, 31)) is False


def test_new_entries_allowed_during_lunch_disabled():
    assert new_entries_allowed(_ny(12, 30)) is False


def test_new_entries_allowed_during_ny_am():
    assert new_entries_allowed(_ny(9, 30)) is True
