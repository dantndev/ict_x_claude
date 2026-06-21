"""Tests for the Telegram notifier + commander (no real network)."""

from __future__ import annotations

from ict_bot.notifications.telegram import EMOJI, TelegramNotifier
from ict_bot.notifications.telegram_commander import KNOWN_COMMANDS, TelegramCommander


def test_notifier_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    n = TelegramNotifier()
    assert not n.activo
    # enviar() must be a no-op when disabled — no exceptions
    n.enviar("trade_enviado", "should be silently dropped")


def test_notifier_filters_by_category():
    n = TelegramNotifier(token="t", chat_id="c", categorias_activas={"trade_enviado"})
    # Active category
    assert "trade_enviado" in n.activas
    # Filter does NOT raise on unknown category
    n.enviar("nonexistent_category", "ignored")


def test_emoji_table_has_known_keys():
    for k in ("sistema_inicio", "trade_enviado", "killswitch", "flatten"):
        assert k in EMOJI


def test_commander_inactive_without_credentials():
    c = TelegramCommander(token=None, chat_id=None)
    assert not c.activo
    c.start()  # no-op
    assert c.poll_commands() == []


def test_commander_known_commands_table():
    for cmd in ("status", "pause", "resume", "stop", "flatten", "restart", "help"):
        assert cmd in KNOWN_COMMANDS


def test_commander_drains_queue(monkeypatch):
    c = TelegramCommander(token="t", chat_id="42")
    # Manually push to the queue (simulating a received command)
    c._queue.append("status")
    c._queue.append("pause")
    drained = c.poll_commands()
    assert drained == ["status", "pause"]
    assert c.poll_commands() == []  # queue empty after drain
