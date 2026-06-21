"""Optional ML confirmation layer (Phase 8).

This is a *filter* on rule-based signals: train a model on historical
signals + L2 microstructure features, then at inference time the model
gates each Signal with `P(win) >= threshold`.

Use:
    from ict_bot.ml.features import features_for_signal
    from ict_bot.ml.filter_model import SignalFilter, train_filter

    rows = [(features_for_signal(sig, ticks, bars), int(trade.pnl_usd > 0))
            for sig, trade in training_pairs]
    model = train_filter(rows)
    accepted = [s for s in signals if model.accept(features_for_signal(s, ticks, bars))]
"""

from ict_bot.ml.features import features_for_signal
from ict_bot.ml.filter_model import SignalFilter, train_filter

__all__ = ["SignalFilter", "features_for_signal", "train_filter"]
