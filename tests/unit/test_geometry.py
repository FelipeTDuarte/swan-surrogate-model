"""Unit tests for geometry validation."""
import numpy as np
import pytest
from src.layouts.geometry import validate_layout, canonical_order

DOMAIN = {"x": [0.0, 5000.0], "y": [0.0, 5000.0]}
N = 4
SPACING = 50.0


def _make_valid_layout():
    return np.array([[100., 100.], [200., 100.], [100., 200.], [200., 200.]])


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
    layout = np.array([[100., 100.], [100., 110.], [300., 300.], [400., 400.]])
    valid, errors = validate_layout(layout, N, SPACING, DOMAIN)
    assert not valid


def test_canonical_order():
    layout = np.array([[200., 100.], [100., 200.], [100., 100.], [200., 200.]])
    ordered = canonical_order(layout)
    assert ordered[0, 0] <= ordered[1, 0]
