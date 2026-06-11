"""Unit tests for geometry validation."""
import numpy as np
from src.layouts.geometry import canonical_order, validate_layout

DOMAIN = {"x": [0.0, 5000.0], "y": [0.0, 5000.0]}
N = 4
SPACING = 50.0


def _make_valid_layout():
    return np.array([[100.0, 100.0], [200.0, 100.0], [100.0, 200.0], [200.0, 200.0]])


def test_valid_layout():
    layout = _make_valid_layout()
    valid, errors = validate_layout(layout, N, SPACING, DOMAIN)
    assert valid, errors


def test_wrong_shape():
    layout = np.zeros((3, 2))
    valid, errors = validate_layout(layout, N, SPACING, DOMAIN)
    assert not valid


def test_out_of_bounds():
    layout = _make_valid_layout()
    layout[0, 0] = -10.0
    valid, errors = validate_layout(layout, N, SPACING, DOMAIN)
    assert not valid


def test_min_spacing_violation():
    layout = np.array([[100.0, 100.0], [100.0, 110.0], [300.0, 300.0], [400.0, 400.0]])
    valid, errors = validate_layout(layout, N, SPACING, DOMAIN)
    assert not valid


def test_canonical_order():
    layout = np.array([[200.0, 100.0], [100.0, 200.0], [100.0, 100.0], [200.0, 200.0]])
    ordered = canonical_order(layout)
    assert ordered[0, 0] <= ordered[1, 0]
