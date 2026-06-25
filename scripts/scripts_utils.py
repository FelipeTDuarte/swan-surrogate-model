"""
scripts_utils.py
Shared utility functions used across pipeline scripts.
"""

from functools import lru_cache
from pathlib import Path
import numpy as np


@lru_cache(maxsize=4)
def domain_bounds_cached(grid_file: Path) -> dict:
    """
    Parse SNL-SWAN grid file and return domain bounds dict.
    Result is cached so the file is read only once per process.
    """
    x_vals, y_vals = [], []
    section = None
    with open(grid_file, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("$"):
                continue
            low = stripped.lower()
            if "x-coordinates" in low:
                section = "x"; continue
            if "y-coordinates" in low:
                section = "y"; continue
            if section == "x":
                try:
                    x_vals.extend(float(v) for v in stripped.split())
                except ValueError:
                    section = None
            elif section == "y":
                try:
                    y_vals.extend(float(v) for v in stripped.split())
                except ValueError:
                    section = None

    xs, ys = np.array(x_vals), np.array(y_vals)
    return dict(
        xmin=float(xs.min()), xmax=float(xs.max()),
        ymin=float(ys.min()), ymax=float(ys.max()),
        nx=len(xs), ny=len(ys),
        dx=float(np.median(np.diff(np.unique(np.sort(xs))))),
        dy=float(np.median(np.diff(np.unique(np.sort(ys))))),
    )
