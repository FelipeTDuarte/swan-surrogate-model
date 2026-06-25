"""
01_generate_layouts.py
Generate WEC array layouts for the SNL-SWAN surrogate dataset.

Grid:
1. Build SWAN grid as set at problem.yaml
2. Reads SWAN grid to infer domain bounds automatically.
Produces a parquet file: data/processed/layouts.parquet
"""

import argparse
import logging
import random
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Grid parser — reads SNL-SWAN grid file and returns x/y coordinate arrays
# ──────────────────────────────────────────────────────────────────────────────

def parse_swan_grid(grid_file: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (x_coords, y_coords) as 1-D arrays from a SNL-SWAN grid file."""
    x_vals, y_vals = [], []
    section = None
    with open(grid_file, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("$"):
                continue
            low = stripped.lower()
            if "x-coordinates" in low:
                section = "x"
                continue
            if "y-coordinates" in low:
                section = "y"
                continue
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
    if not x_vals or not y_vals:
        raise ValueError(f"Could not parse x/y coordinates from {grid_file}")
    return np.array(x_vals), np.array(y_vals)


def domain_bounds(grid_file: Path) -> dict:
    """Infer domain bounds, shape and cell size from grid file."""
    xs, ys = parse_swan_grid(grid_file)
    bounds = dict(
        xmin=float(xs.min()), xmax=float(xs.max()),
        ymin=float(ys.min()), ymax=float(ys.max()),
        nx=len(xs), ny=len(ys),
        dx=float(np.median(np.diff(np.unique(np.sort(xs))))),
        dy=float(np.median(np.diff(np.unique(np.sort(ys))))),
    )
    log.info("Domain: x=[%(xmin).1f, %(xmax).1f]  y=[%(ymin).1f, %(ymax).1f]  "
             "nx=%(nx)d  ny=%(ny)d  dx=%(dx).1f m  dy=%(dy).1f m", bounds)
    return bounds


# ──────────────────────────────────────────────────────────────────────────────
# Layout generators
# ──────────────────────────────────────────────────────────────────────────────

def _valid(pts: np.ndarray, bounds: dict, margin: float) -> np.ndarray:
    """Filter points that are inside domain with margin."""
    x, y = pts[:, 0], pts[:, 1]
    return pts[
        (x >= bounds["xmin"] + margin) & (x <= bounds["xmax"] - margin) &
        (y >= bounds["ymin"] + margin) & (y <= bounds["ymax"] - margin)
    ]


def _enforce_spacing(pts: np.ndarray, min_spacing: float, rng: np.random.Generator) -> np.ndarray:
    """Greedy sequential spacing filter (O(n²) — acceptable for n≤200)."""
    idx = rng.permutation(len(pts))
    selected = []
    for i in idx:
        p = pts[i]
        if not selected:
            selected.append(p)
            continue
        arr = np.array(selected)
        if np.min(np.hypot(arr[:, 0] - p[0], arr[:, 1] - p[1])) >= min_spacing:
            selected.append(p)
    return np.array(selected)


def gen_random_sparse(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    candidates = np.column_stack([
        rng.uniform(bounds["xmin"], bounds["xmax"], n * 20),
        rng.uniform(bounds["ymin"], bounds["ymax"], n * 20),
    ])
    pts = _enforce_spacing(candidates, spacing, rng)
    return pts[:n] if len(pts) >= n else pts


def gen_grid_like(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    cols = max(1, int(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    jitter = spacing * 0.25
    xs = np.linspace(bounds["xmin"] + spacing, bounds["xmax"] - spacing, cols)
    ys = np.linspace(bounds["ymin"] + spacing, bounds["ymax"] - spacing, rows)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    pts += rng.uniform(-jitter, jitter, pts.shape)
    return pts[:n]


def gen_row_aligned(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    n_rows = max(1, rng.integers(3, 8))
    per_row = int(np.ceil(n / n_rows))
    row_ys = np.linspace(bounds["ymin"] + spacing * 2, bounds["ymax"] - spacing * 2, n_rows)
    pts = []
    for ry in row_ys:
        xs = np.linspace(bounds["xmin"] + spacing, bounds["xmax"] - spacing, per_row)
        xs += rng.uniform(-spacing * 0.1, spacing * 0.1, per_row)
        pts.extend(zip(xs, [ry] * per_row))
    pts = np.array(pts[:n])
    return pts


def gen_diagonal(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    angle = rng.uniform(-45, 45)
    t = np.linspace(0, 1, n)
    cx = bounds["xmin"] + t * (bounds["xmax"] - bounds["xmin"])
    cy = bounds["ymin"] + t * (bounds["ymax"] - bounds["ymin"])
    noise = spacing * 0.3
    pts = np.column_stack([cx + rng.uniform(-noise, noise, n),
                           cy + rng.uniform(-noise, noise, n)])
    return pts


def gen_compact(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    cx = rng.uniform(bounds["xmin"] + spacing * 5, bounds["xmax"] - spacing * 5)
    cy = rng.uniform(bounds["ymin"] + spacing * 5, bounds["ymax"] - spacing * 5)
    radius = spacing * np.sqrt(n) * 0.6
    angles = rng.uniform(0, 2 * np.pi, n * 4)
    radii  = np.sqrt(rng.uniform(0, 1, n * 4)) * radius
    pts = np.column_stack([cx + radii * np.cos(angles),
                           cy + radii * np.sin(angles)])
    pts = _enforce_spacing(pts, spacing, rng)
    return pts[:n] if len(pts) >= n else pts


def gen_dispersed(n: int, bounds: dict, spacing: float, rng: np.random.Generator) -> np.ndarray:
    return gen_random_sparse(n, bounds, spacing * 2.5, rng)


GENERATORS = {
    "random_sparse": gen_random_sparse,
    "grid_like":     gen_grid_like,
    "row_aligned":   gen_row_aligned,
    "diagonal":      gen_diagonal,
    "compact":       gen_compact,
    "dispersed":     gen_dispersed,
}


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate WEC array layouts")
    parser.add_argument("--problem", default="config/problem.yaml")
    parser.add_argument("--paths",   default="config/paths.yaml")
    parser.add_argument("--seed",    type=int, default=None)
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    rng_seed = args.seed if args.seed is not None else cfg["training"]["random_seed"]
    rng = np.random.default_rng(rng_seed)

    grid_file    = Path(pths["grid_file"])
    bounds       = domain_bounds(grid_file)
    n_wecs       = cfg["n_wecs"]
    min_spacing  = cfg["layouts"]["min_spacing_m"]
    families     = cfg["layouts"]["families"]
    margin       = min_spacing * 2

    records = []
    layout_id = 0

    for family, count in families.items():
        gen_fn = GENERATORS[family]
        log.info("Generating %d layouts — family: %s", count, family)
        generated = 0
        attempts   = 0
        while generated < count and attempts < count * 10:
            attempts += 1
            pts = gen_fn(n_wecs, bounds, min_spacing, rng)
            pts = _valid(pts, bounds, margin)
            if len(pts) < n_wecs:
                continue
            pts = pts[:n_wecs]
            records.append({
                "layout_id": layout_id,
                "family":    family,
                "x_coords":  pts[:, 0].tolist(),
                "y_coords":  pts[:, 1].tolist(),
                "n_wecs":    n_wecs,
            })
            layout_id += 1
            generated += 1

        log.info("  → produced %d / %d for family '%s'", generated, count, family)

    df = pd.DataFrame(records)
    out_dir = Path(pths["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "layouts.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Saved %d layouts to %s", len(df), out_path)


if __name__ == "__main__":
    main()
