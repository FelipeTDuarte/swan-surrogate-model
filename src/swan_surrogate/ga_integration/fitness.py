"""
Surrogate fitness interface for the GA.

This module is the only entry point the GA should use to evaluate a layout.
It enforces geometric validity before inference and uses frozen normalisation
bounds from the exported bundle.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.layouts.geometry import canonical_order, validate_layout
from src.utils.logging import get_logger

log = get_logger(__name__)

SENTINEL_FITNESS = -1e9   # returned for invalid layouts — never enter GA selection


class SurrogateFitness:
    """Wraps an exported surrogate bundle for safe use inside a GA loop."""

    def __init__(self, bundle_path: str | Path, problem_cfg: dict):
        self.bundle_path = Path(bundle_path)
        self.cfg = problem_cfg
        self._model = None
        self._scaler = None
        self._manifest = None
        self._loaded = False

    def load(self) -> None:
        """Load the bundle once — call outside the GA loop."""
        raise NotImplementedError("Implement bundle loading in src/export/bundle.py")

    def evaluate(
        self,
        layout: np.ndarray,
        sea_state: list[float],
        alpha: float,
        beta: float,
    ) -> dict:
        """
        Evaluate a single layout under one sea state.

        Returns dict with keys: fitness, p_total, hra, valid, warnings, mode.
        If layout is geometrically invalid, returns SENTINEL_FITNESS without inference.
        """
        if not self._loaded:
            raise RuntimeError("Call .load() before .evaluate()")

        is_valid, violations = validate_layout(
            layout,
            n_wecs=self.cfg["n_wecs"],
            min_spacing=self.cfg["layouts"]["min_spacing"],
            domain_bounds=self.cfg["layouts"]["domain_bounds"],
        )
        if not is_valid:
            log.debug("Invalid layout rejected: %s", violations)
            return {
                "fitness": SENTINEL_FITNESS,
                "valid": False,
                "warnings": violations,
                "p_total": None,
                "hra": None,
                "mode": None,
            }

        layout_ordered = canonical_order(layout)
        features = self._build_features(layout_ordered, sea_state)
        prediction = self._infer(features)
        p_norm, hra_norm = self._normalise(prediction)
        fitness = alpha * p_norm + beta * hra_norm

        return {
            "fitness": float(fitness),
            "p_total": float(prediction["p_total"]),
            "hra": prediction["hra"],
            "p_norm": float(p_norm),
            "hra_norm": float(hra_norm),
            "valid": True,
            "warnings": [],
            "mode": self._manifest["mode"] if self._manifest else "B",
        }

    def _build_features(self, layout: np.ndarray, sea_state: list[float]) -> np.ndarray:
        coords = layout.flatten()
        return np.concatenate([coords, sea_state])

    def _infer(self, features: np.ndarray) -> dict:
        raise NotImplementedError("Implement inference in bundle loader")

    def _normalise(self, prediction: dict) -> tuple[float, float]:
        raise NotImplementedError("Implement normalisation using frozen bounds from bundle")

    @staticmethod
    def _minmax_01(x: float, xmin: float, xmax: float) -> float:
        if xmax == xmin:
            return 0.01
        z = max(0.0, min(1.0, (x - xmin) / (xmax - xmin)))
        return 0.01 + 0.99 * z
