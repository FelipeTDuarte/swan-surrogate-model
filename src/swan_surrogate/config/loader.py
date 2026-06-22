"""Config loader and validator for problem.yaml and paths.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_problem(path: str | Path = "config/problem.yaml") -> dict:
    """Load and return the problem configuration dict."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    _validate_problem(cfg)
    return cfg


def load_paths(path: str | Path = "config/paths.yaml") -> dict:
    """Load and return the paths configuration dict."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg


def _validate_problem(cfg: dict) -> None:
    required = ["problem_id", "n_wecs", "hra", "fitness", "training"]
    for key in required:
        if key not in cfg:
            raise ValueError(f"Missing required key in problem.yaml: {key}")
    if cfg["n_wecs"] < 1:
        raise ValueError("n_wecs must be >= 1")
