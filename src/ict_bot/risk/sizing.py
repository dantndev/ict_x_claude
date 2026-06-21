"""Position sizing by SL distance + per-trade risk cap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Per-contract economics (NQ defaults)."""

    tick_size: float = 0.25
    tick_value_usd: float = 5.00      # $5 per tick = $20 per point
    point_value_usd: float = 20.00
    currency: str = "USD"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    per_trade_risk_pct: float = 0.5       # of equity
    max_quantity: int = 5                  # absolute cap per trade
    min_quantity: int = 1


def size_position(
    equity_usd: float,
    entry_price: float,
    stop_loss: float,
    *,
    instrument: InstrumentSpec | None = None,
    risk: RiskConfig | None = None,
) -> int:
    """Return the integer number of contracts to trade.

    Computation:
        risk_per_contract_usd = abs(entry - SL) / tick_size * tick_value_usd
        target_risk_usd       = equity * per_trade_risk_pct / 100
        qty                   = floor(target_risk / risk_per_contract)
                                clipped to [min_quantity, max_quantity]
    Returns 0 when the SL distance is zero or the per-contract risk exceeds
    the target — the engine must skip the setup in that case.
    """
    spec = instrument or InstrumentSpec()
    cfg = risk or RiskConfig()
    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return 0
    ticks = sl_distance / spec.tick_size
    risk_per_contract = ticks * spec.tick_value_usd
    target_risk = equity_usd * cfg.per_trade_risk_pct / 100.0
    if risk_per_contract > target_risk:
        return 0
    qty = int(target_risk // risk_per_contract)
    qty = max(cfg.min_quantity, min(cfg.max_quantity, qty))
    return qty
