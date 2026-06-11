"""Geometry validation for WEC layouts — source of truth for the GA."""
from __future__ import annotations

import numpy as np


def validate_layout(
    layout: np.ndarray,
    n_wecs: int,
    min_spacing: float,
    domain_bounds: dict,
) -> tuple[bool, list[str]]:
    """
    Validate a WEC layout array of shape (n_wecs, 2).

    Returns (is_valid, list_of_violation_messages).
    This function is the single source of geometric truth for the project.
    """
    errors: list[str] = []
    if layout.shape != (n_wecs, 2):
        errors.append(f"Layout shape {layout.shape} != ({n_wecs}, 2)")
        return False, errors

    x_min, x_max = domain_bounds["x"]
    y_min, y_max = domain_bounds["y"]
    if np.any(layout[:, 0] < x_min) or np.any(layout[:, 0] > x_max):
        errors.append("One or more WECs outside x domain bounds")
    if np.any(layout[:, 1] < y_min) or np.any(layout[:, 1] > y_max):
        errors.append("One or more WECs outside y domain bounds")

    for i in range(n_wecs):
        for j in range(i + 1, n_wecs):
            dist = float(np.linalg.norm(layout[i] - layout[j]))
            if dist < min_spacing:
                errors.append(f"WEC {i} and {j} violate min spacing ({dist:.1f} < {min_spacing})")

    return len(errors) == 0, errors


def canonical_order(layout: np.ndarray) -> np.ndarray:
    """Sort WECs by x then y for canonical representation."""
    idx = np.lexsort((layout[:, 1], layout[:, 0]))
    return layout[idx]
