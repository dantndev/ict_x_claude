"""Tests for the Quantower broker adapter (DOM2 + Lucid).

These tests stub httpx so no real network calls are made.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from ict_bot.execution.broker import BrokerError
from ict_bot.execution.quantower.broker import QuantowerBroker
from ict_bot.execution.quantower.dom2_client import DOM2Client
from ict_bot.execution.quantower.lucid_executor import LucidExecutor

# ───────────────────── DOM2 client ─────────────────────

_DOM2_SAMPLE: dict[str, Any] = {
    "microstructure": {
        "mid_price": 20000.5,
        "best_bid": 20000.25,
        "best_ask": 20000.75,
        "spread_pts": 0.5,
        "tick_velocity": 12.3,
    },
    "footprint": {"bid_vol": 100, "ask_vol": 120, "delta": 20},
    "dom": {
        "bids": [{"s": 10}, {"s": 20}, {"s": 30}, {"s": 5}, {"s": 5}],
        "asks": [{"size": 12}, {"size": 18}, {"size": 25}, {"size": 5}, {"size": 5}],
    },
}


def test_dom2_client_parses_snapshot(monkeypatch):
    client = DOM2Client(url="http://stub/dom2", timeout_sec=1.0)

    class _StubResp:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return _DOM2_SAMPLE

    def _stub_get(self, url: str, **kwargs):
        return _StubResp()

    monkeypatch.setattr(httpx.Client, "get", _stub_get)
    snap = client.leer()
    assert snap is not None
    assert snap.precio == 20000.5
    assert snap.best_bid == 20000.25
    assert snap.best_ask == 20000.75
    assert snap.spread_pts == 0.5
    assert snap.bid_top5 == 70
    assert snap.ask_top5 == 65
    assert snap.fp_bid_vol == 100
    assert snap.fp_ask_vol == 120
    assert snap.delta_acumulado == 20
    assert client.vivo()


def test_dom2_client_returns_none_on_404(monkeypatch):
    client = DOM2Client(url="http://stub/dom2", timeout_sec=1.0)

    class _Stub404:
        status_code = 404
        def json(self) -> dict[str, Any]:
            return {}

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: _Stub404())
    assert client.leer() is None


# ───────────────────── Lucid executor ─────────────────────

def test_lucid_executor_health_parses_capabilities(monkeypatch):
    ex = LucidExecutor(url_base="http://stub:6001", symbol="MNQM6")

    class _StubHealth:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return {
                "runner_support": True,
                "same_direction_adds_support": True,
                "multi_entry_safe": True,
                "max_net_qty": 5,
            }

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: _StubHealth())
    assert ex.inicializar() is True
    assert ex.capabilities.runner_support is True
    assert ex.capabilities.max_net_qty == 5


def test_lucid_executor_order_ok(monkeypatch):
    ex = LucidExecutor(url_base="http://stub:6001", symbol="MNQM6")

    class _StubResp:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return {"ok": True, "signal_id": "abc123", "fill_price": 20001.0,
                    "status": "filled"}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: _StubResp())
    res = ex.enviar_orden(direccion="LONG", sl_pts=15.0, tp_pts=15.0,
                           qty_override=2, etiqueta="t")
    assert res.exitoso
    assert res.ticket == "abc123"
    assert res.precio_entrada == 20001.0


def test_lucid_executor_order_rejected(monkeypatch):
    ex = LucidExecutor(url_base="http://stub:6001", symbol="MNQM6")

    class _StubReject:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return {"ok": False, "error": "risk_blocked"}

    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: _StubReject())
    res = ex.enviar_orden(direccion="SHORT", sl_pts=15.0, tp_pts=15.0)
    assert not res.exitoso
    assert "risk_blocked" in res.mensaje


def test_lucid_executor_dry_run_does_not_call_http():
    ex = LucidExecutor(url_base="http://stub:6001", symbol="MNQM6", dry_run=True)
    res = ex.enviar_orden(direccion="LONG", sl_pts=15.0, tp_pts=15.0)
    assert res.exitoso
    assert res.ticket.startswith("dryrun_")


# ───────────────────── QuantowerBroker wiring ─────────────────────

def test_quantower_broker_submit_translates_prices_to_points(monkeypatch):
    captured: dict[str, Any] = {}

    class _StubFeed:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return _DOM2_SAMPLE

    class _StubOrderResp:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return {"ok": True, "signal_id": "qt-1", "fill_price": 20000.5}

    def _stub_get(self, url: str, **kw):
        return _StubFeed()

    def _stub_post(self, url: str, json=None, **kw):
        captured["payload"] = json
        return _StubOrderResp()

    monkeypatch.setattr(httpx.Client, "get", _stub_get)
    monkeypatch.setattr(httpx.Client, "post", _stub_post)

    broker = QuantowerBroker(qty_default=2)
    broker.connect()
    ack = broker.submit_market(
        "MNQM6", "BUY", quantity=2, sl=19990.0, tp=20020.0,
    )
    assert ack.accepted
    payload = captured["payload"]
    # mid_price = 20000.5; sl=19990 → 10.5 pts; tp=20020 → 19.5 pts
    assert payload["side"] == "BUY"
    assert payload["qty"] == 2
    assert abs(payload["sl_pts"] - 10.5) < 1e-6
    assert abs(payload["tp_pts"] - 19.5) < 1e-6
    assert payload["symbol"] == "MNQM6"


def test_quantower_broker_rejects_wrong_symbol(monkeypatch):
    class _StubFeed:
        status_code = 200
        def json(self) -> dict[str, Any]:
            return _DOM2_SAMPLE

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: _StubFeed())

    broker = QuantowerBroker()
    broker.connect()
    with pytest.raises(BrokerError):
        broker.submit_market("ESM6", "BUY", 1, sl=99.0, tp=101.0)
