"""Inspect generated WEC layouts with validity metrics and diagnostic plots.

Run after ``01_layout_generator.py``. Writes a CSV, JSON summary, and figures
under ``reports/layout_checks`` by default. It exits with code 1 if a layout is
outside the deployment polygon or violates the configured centre spacing.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
import pandas as pd
import yaml
from shapely.geometry import Point, Polygon

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def load_polygon(path: Path) -> Polygon:
    frame = pd.read_csv(path)
    if not {"X", "Y"}.issubset(frame.columns):
        raise ValueError(f"{path} must contain X and Y columns.")
    polygon = Polygon(frame[["X", "Y"]].to_numpy())
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        raise ValueError(f"Deployment polygon from {path} is empty.")
    return polygon


def locate_layout_file(processed_dir: Path, specified: str | None) -> Path:
    if specified:
        path = Path(specified)
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    for name in ("layouts_wecs_segments.parquet", "layouts_wecs_centers.parquet", "layouts.parquet"):
        path = processed_dir / name
        if path.exists():
            return path
    raise FileNotFoundError(f"No layout parquet found in {processed_dir}")


def pairwise_distances(points: np.ndarray) -> np.ndarray:
    if len(points) < 2:
        return np.array([], dtype=float)
    delta = points[:, None, :] - points[None, :, :]
    return np.sqrt(np.sum(delta * delta, axis=2))[np.triu_indices(len(points), k=1)]


def inspect_layout(layout_id: int, frame: pd.DataFrame, polygon: Polygon, min_spacing: float) -> dict:
    points = frame[["center_x", "center_y"]].to_numpy(dtype=float)
    distances = pairwise_distances(points)
    inside = np.array([polygon.covers(Point(x, y)) for x, y in points])
    minimum = float(distances.min()) if len(distances) else float("nan")
    return {
        "layout_id": layout_id,
        "family": str(frame["family"].iloc[0]) if "family" in frame else "unknown",
        "n_wecs": len(frame),
        "inside_count": int(inside.sum()),
        "outside_count": int((~inside).sum()),
        "min_center_spacing_m": minimum,
        "mean_center_spacing_m": float(distances.mean()) if len(distances) else float("nan"),
        "spacing_violations": int((distances < min_spacing).sum()),
        "is_valid": bool(inside.all() and (not len(distances) or minimum >= min_spacing)),
    }


def draw_layout(ax, frame: pd.DataFrame, polygon: Polygon, spacing: float, title: str) -> None:
    x, y = polygon.exterior.xy
    ax.plot(x, y, color="black", lw=1.2)
    centers = frame[["center_x", "center_y"]].to_numpy(dtype=float)
    if {"start_x", "start_y", "end_x", "end_y"}.issubset(frame.columns):
        for row in frame.itertuples():
            ax.plot([row.start_x, row.end_x], [row.start_y, row.end_y], color="tab:blue", lw=2)
    ax.scatter(centers[:, 0], centers[:, 1], s=20, color="tab:orange", zorder=3)
    for x0, y0 in centers:
        ax.add_patch(Circle((x0, y0), spacing / 2, color="tab:red", alpha=0.08))
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    ax.ticklabel_format(style="plain", axis="both", useOffset=False)


def save_figures(layouts: pd.DataFrame, metrics: pd.DataFrame, polygon: Polygon, spacing: float,
                 output_dir: Path, max_plots: int) -> None:
    selected = metrics.sort_values(["is_valid", "min_center_spacing_m"], ascending=[True, True]).head(max_plots)
    cols = min(3, len(selected))
    rows = int(np.ceil(len(selected) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 4.5 * rows), squeeze=False)
    for ax, row in zip(axes.flat, selected.itertuples()):
        draw_layout(ax, layouts[layouts["layout_id"] == row.layout_id], polygon, spacing,
                    f"Layout {row.layout_id} | valid={row.is_valid}")
    for ax in axes.flat[len(selected):]:
        ax.remove()
    fig.tight_layout()
    fig.savefig(output_dir / "layout_examples.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    values = metrics["min_center_spacing_m"].dropna()
    ax.hist(values, bins=min(30, max(5, len(values))), color="tab:blue", edgecolor="white")
    ax.axvline(spacing, color="tab:red", ls="--", label=f"minimum: {spacing:g} m")
    ax.set(xlabel="Minimum centre-to-centre spacing (m)", ylabel="Layouts", title="Layout spacing distribution")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "minimum_spacing_distribution.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check generated WEC layouts and create diagnostic plots")
    parser.add_argument("--problem", default="config/problem.yaml")
    parser.add_argument("--paths", default="config/paths.yaml")
    parser.add_argument("--layouts", help="Optional explicit layouts parquet path")
    parser.add_argument("--output-dir", default="reports/layout_checks")
    parser.add_argument("--max-plots", type=int, default=12)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    problem = yaml.safe_load(Path(args.problem).read_text(encoding="utf-8"))
    paths = yaml.safe_load(Path(args.paths).read_text(encoding="utf-8"))
    layout_path = locate_layout_file(Path(paths["processed_dir"]), args.layouts)
    polygon = load_polygon(Path(paths["deployment_polygon_file"]))
    layouts = pd.read_parquet(layout_path)
    required = {"layout_id", "center_x", "center_y"}
    missing = required - set(layouts.columns)
    if missing:
        raise ValueError(f"{layout_path} lacks required columns: {sorted(missing)}")

    spacing = float(problem["layouts"]["min_spacing_m"])
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(
        inspect_layout(int(layout_id), group, polygon, spacing)
        for layout_id, group in layouts.groupby("layout_id", sort=True)
    )
    metrics.to_csv(output_dir / "layout_metrics.csv", index=False)
    summary = {
        "source": str(layout_path), "layouts": len(metrics), "wec_rows": len(layouts),
        "valid_layouts": int(metrics["is_valid"].sum()),
        "invalid_layouts": int((~metrics["is_valid"]).sum()),
        "minimum_required_spacing_m": spacing,
        "dataset_minimum_spacing_m": float(metrics["min_center_spacing_m"].min()),
    }
    (output_dir / "layout_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not args.no_plots:
        save_figures(layouts, metrics, polygon, spacing, output_dir, args.max_plots)
    log.info("Checked %d layouts: %d valid, %d invalid. Results: %s", summary["layouts"], summary["valid_layouts"], summary["invalid_layouts"], output_dir)
    if summary["invalid_layouts"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
