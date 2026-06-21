"""Signal-filter classifier (gradient boosting / random forest).

Trained on (feature_vector, was_winner) pairs. At inference, the model
returns P(win) for each new signal; signals with P(win) >= threshold pass
the filter, the rest are skipped.

scikit-learn is loaded lazily — installable via `pip install -e '.[ml]'`.
If unavailable, `train_filter` raises ImportError with the install hint.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

from ict_bot.ml.features import FEATURE_KEYS, features_to_vector


@dataclass
class SignalFilter:
    """Wraps a trained sklearn classifier."""

    model: object
    threshold: float = 0.55

    def predict_proba(self, features: dict[str, float]) -> float:
        v = [features_to_vector(features)]
        proba = self.model.predict_proba(v)  # type: ignore[attr-defined]
        return float(proba[0][1])

    def accept(self, features: dict[str, float]) -> bool:
        return self.predict_proba(features) >= self.threshold

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"model": self.model, "threshold": self.threshold,
                         "feature_keys": FEATURE_KEYS}, f)

    @classmethod
    def load(cls, path: Path) -> SignalFilter:
        with path.open("rb") as f:
            obj = pickle.load(f)
        return cls(model=obj["model"], threshold=obj["threshold"])


def train_filter(
    rows: list[tuple[dict[str, float], int]],
    *,
    threshold: float = 0.55,
    n_estimators: int = 200,
    max_depth: int | None = 6,
    random_state: int = 42,
) -> SignalFilter:
    """Train a gradient-boosting filter on (features, win_label) pairs.

    Requires scikit-learn (install via `.[ml]` extra).
    """
    try:
        from sklearn.ensemble import GradientBoostingClassifier
    except ImportError as e:
        msg = "scikit-learn missing — install with `pip install -e '.[ml]'`"
        raise ImportError(msg) from e

    if len(rows) < 20:
        msg = f"Need at least 20 training rows, got {len(rows)}"
        raise ValueError(msg)

    X = [features_to_vector(f) for f, _ in rows]
    y = [label for _, label in rows]
    model = GradientBoostingClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
    )
    model.fit(X, y)
    return SignalFilter(model=model, threshold=threshold)
