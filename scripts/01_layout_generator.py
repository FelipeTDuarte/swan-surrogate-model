"""
layout_generator.py

WEC layout generator for surrogate-model datasets.

This script reads project configuration from YAML files, builds valid WEC layouts
inside a deployment polygon with optional exclusion zones, and exports the result
as flat CSV/parquet tables. It supports two export modes:

- segments: full WEC segment geometry for line-based models
- centers: only WEC centers for models that use point representations

"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Any

import numpy as np
import pandas as pd
import shapely
import yaml
from shapely.affinity import translate
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ExportMode = Literal["segments", "centers"]


@dataclass(frozen=True)
class WECGeometry:
    """Physical representation of one WEC."""

    length: float
    transverse_length: float


@dataclass(frozen=True)
class DatasetSpec:
    """Global dataset-generation settings."""

    num_layouts: int
    num_wecs: int
    min_dist: float
    geometry: WECGeometry
    angle_range_deg: tuple[float, float] = (180.0, 360.0)
    max_attempts_per_layout: int = 100_000
    random_seed: int | None = None


@dataclass(frozen=True)
class FamilySpec:
    """Definition of one layout family."""

    name: str
    weight: float
    fixed_angle_deg: float | None = None
    center_bias: float = 0.0
    edge_bias: float = 0.0
    jitter_std: float = 0.0
    row_strength: float = 0.0
    diagonal_strength: float = 0.0
    compactness: float = 0.0


DEFAULT_FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec(name="random_sparse", weight=0.22),
    FamilySpec(name="aligned", weight=0.18, fixed_angle_deg=308.0, row_strength=0.55),
    FamilySpec(name="grid_like", weight=0.16, fixed_angle_deg=308.0, row_strength=0.75),
    FamilySpec(name="diagonal", weight=0.12, fixed_angle_deg=308.0, diagonal_strength=0.90),
    FamilySpec(name="compact", weight=0.14, fixed_angle_deg=308.0, center_bias=0.55, compactness=0.75),
    FamilySpec(name="dispersed", weight=0.10, edge_bias=0.35),
    FamilySpec(name="staggered", weight=0.08, fixed_angle_deg=308.0, row_strength=0.65, jitter_std=0.18),
)


# -----------------------------------------------------------------------------
# Geometry utilities
# -----------------------------------------------------------------------------


def load_poly_from_csv(
    csv_path: str | Path,
    close_polygon: bool = True,
    tol: float = 1e-6,
    centralize: bool = False,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> tuple[pd.DataFrame, Polygon, list[Point], list[Polygon]]:
    """Load one or more polygons from CSV and return the valid union."""
    df = pd.read_csv(csv_path)

    if not {"X", "Y", "ID"}.issubset(df.columns):
        if len(df.columns) == 2:
            df.columns = ["X", "Y"]
            df["ID"] = 0
        elif len(df.columns) == 3:
            df.columns = ["X", "Y", "ID"]
        else:
            raise ValueError("CSV must contain X, Y, ID or have 2/3 unnamed columns.")

    polygons: list[Polygon] = []
    centroids: list[Point] = []

    for poly_id in df["ID"].unique():
        coords_df = df.loc[df["ID"] == poly_id, ["X", "Y"]]
        coords = list(zip(coords_df["X"], coords_df["Y"]))

        if close_polygon and coords[0] != coords[-1]:
            coords.append(coords[0])

        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)

        if poly.is_empty or poly.area <= tol:
            continue

        centroid = poly.centroid
        if centralize:
            poly = translate(poly, xoff=center_x - centroid.x, yoff=center_y - centroid.y)
            centroid = poly.centroid

        polygons.append(poly)
        centroids.append(centroid)

    if not polygons:
        raise ValueError(f"No valid polygons were found in {csv_path}.")

    union_poly = unary_union(polygons)
    union_poly = make_valid(union_poly)
    union_poly = union_poly.buffer(0)

    return df, union_poly, centroids, polygons



def centers_to_circular_exclusions(
    centers: Iterable[tuple[float, float]],
    radius: float,
) -> list[Polygon]:
    """Create circular exclusion zones from center coordinates."""
    return [Point(x, y).buffer(radius) for x, y in centers]



def build_deploy_area(
    outside_polygon: Polygon,
    exclusion_areas: Iterable[Polygon] | Polygon | None = None,
    tol: float = 1e-6,
) -> tuple[Polygon, int]:
    """Subtract exclusion areas from outer polygon and return deploy area."""
    if exclusion_areas is None:
        exclusion_list: list[Polygon] = []
    elif hasattr(exclusion_areas, "geoms"):
        exclusion_list = list(exclusion_areas.geoms)
    elif isinstance(exclusion_areas, (list, tuple)):
        exclusion_list = list(exclusion_areas)
    else:
        exclusion_list = [exclusion_areas]

    if not exclusion_list:
        return outside_polygon, 0

    exclusion_union = unary_union(exclusion_list)
    deploy_area = outside_polygon.difference(exclusion_union)

    if not deploy_area.is_valid:
        deploy_area = make_valid(deploy_area)
    deploy_area = deploy_area.buffer(0)

    n_exc_areas = 0
    if deploy_area.geom_type == "Polygon" and deploy_area.area > tol:
        n_exc_areas = len(deploy_area.interiors)
    elif deploy_area.geom_type == "MultiPolygon":
        n_exc_areas = sum(len(poly.interiors) for poly in deploy_area.geoms if poly.area > tol)
    elif deploy_area.geom_type == "GeometryCollection":
        n_exc_areas = sum(
            len(geom.interiors)
            for geom in deploy_area.geoms
            if geom.geom_type == "Polygon" and geom.area > tol
        )

    return deploy_area, n_exc_areas



def segment_from_center(center: Point, length: float, angle_deg: float) -> LineString:
    """Create a segment from center, length, and Cartesian angle."""
    theta = np.radians(angle_deg)
    dx = 0.5 * length * np.cos(theta)
    dy = 0.5 * length * np.sin(theta)
    return LineString([(center.x - dx, center.y - dy), (center.x + dx, center.y + dy)])



def sample_point_uniform(polygon: Polygon, rng: np.random.Generator) -> Point:
    """Uniform rejection sampling inside polygon bounding box."""
    minx, miny, maxx, maxy = polygon.bounds
    while True:
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if shapely.contains_xy(polygon, x, y):
            return Point(x, y)



def sample_point_biased(
    polygon: Polygon,
    rng: np.random.Generator,
    center_bias: float = 0.0,
    edge_bias: float = 0.0,
) -> Point:
    """Sample a point in polygon with optional center and edge bias."""
    centroid = polygon.centroid
    minx, miny, maxx, maxy = polygon.bounds
    diag = np.hypot(maxx - minx, maxy - miny)

    while True:
        point = sample_point_uniform(polygon, rng)

        if center_bias > 0.0:
            point2 = Point(
                point.x + center_bias * rng.uniform(0.0, 1.0) * (centroid.x - point.x),
                point.y + center_bias * rng.uniform(0.0, 1.0) * (centroid.y - point.y),
            )
            if shapely.contains_xy(polygon, point2.x, point2.y):
                point = point2

        if abs(edge_bias) > 0.0:
            dist_edge = polygon.boundary.distance(point)
            normalized = dist_edge / max(diag, 1e-12)
            u = rng.uniform(0.0, 1.0)
            if edge_bias > 0.0 and u > min(1.0, 8.0 * normalized):
                continue
            if edge_bias < 0.0 and u > min(1.0, 8.0 * (1.0 - normalized)):
                continue

        return point



def segment_exclusion_zone(segment: LineString, transverse_length: float, min_dist: float) -> Polygon:
    """Anisotropic footprint for a WEC segment plus safety offset."""
    return (
        segment.buffer(
            transverse_length / 2.0,
            cap_style="flat",
            join_style="mitre",
        ).buffer(
            min_dist,
            cap_style="flat",
            join_style="mitre",
        )
    )



def validate_segment(
    candidate: LineString,
    accepted_segments: list[LineString],
    deploy_area: Polygon,
    geometry: WECGeometry,
    min_dist: float,
) -> bool:
    """Check containment and anisotropic spacing against accepted segments."""
    if not deploy_area.covers(candidate):
        return False

    exclusion = segment_exclusion_zone(candidate, geometry.transverse_length, min_dist)
    for existing in accepted_segments:
        if not exclusion.disjoint(existing):
            return False
    return True



def validate_center(
    center: Point,
    accepted_centers: list[Point],
    deploy_area: Polygon,
    min_dist: float,
) -> bool:
    """Check center-only spacing for point-based models."""
    if not deploy_area.covers(center):
        return False
    for existing in accepted_centers:
        if center.distance(existing) < min_dist:
            return False
    return True



def poisson_disc_centers(
    polygon: Polygon,
    n_points: int,
    min_dist: float,
    rng: np.random.Generator,
    max_attempts: int,
    center_bias: float = 0.0,
    edge_bias: float = 0.0,
) -> list[Point]:
    """Greedy center generation with minimum-distance enforcement."""
    centers: list[Point] = []
    attempts = 0

    while len(centers) < n_points:
        point = sample_point_biased(polygon, rng, center_bias=center_bias, edge_bias=edge_bias)
        if validate_center(point, centers, polygon, min_dist):
            centers.append(point)

        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(
                f"Failed to place {n_points} centers after {max_attempts} attempts."
            )

    return centers



def order_centers_for_family(
    centers: list[Point],
    family: FamilySpec,
    polygon: Polygon,
) -> list[Point]:
    """Impose macro-structure on a valid set of centers."""
    arr = np.array([(p.x, p.y) for p in centers])
    centroid = polygon.centroid

    if family.name in {"aligned", "grid_like", "staggered"}:
        order = np.lexsort((arr[:, 0], arr[:, 1]))
        return [centers[i] for i in order]

    if family.name == "diagonal":
        score = arr[:, 0] + arr[:, 1]
        order = np.argsort(score)
        return [centers[i] for i in order]

    if family.name == "compact":
        dist = np.hypot(arr[:, 0] - centroid.x, arr[:, 1] - centroid.y)
        order = np.argsort(dist)
        return [centers[i] for i in order]

    if family.name == "dispersed":
        dist = np.hypot(arr[:, 0] - centroid.x, arr[:, 1] - centroid.y)
        order = np.argsort(-dist)
        return [centers[i] for i in order]

    return centers



def assign_angles(
    centers: list[Point],
    family: FamilySpec,
    spec: DatasetSpec,
    polygon: Polygon,
    rng: np.random.Generator,
) -> list[float]:
    """Assign segment orientations according to family logic."""
    if family.fixed_angle_deg is not None and family.name != "diagonal":
        base = [family.fixed_angle_deg] * len(centers)
    else:
        base = list(rng.uniform(spec.angle_range_deg[0], spec.angle_range_deg[1], len(centers)))

    if family.name == "diagonal":
        minx, miny, maxx, maxy = polygon.bounds
        domain_angle = np.degrees(np.arctan2(maxy - miny, maxx - minx))
        base = [domain_angle] * len(centers)

    if family.name == "staggered":
        base = [
            (family.fixed_angle_deg if family.fixed_angle_deg is not None else angle) + rng.uniform(-10.0, 10.0)
            for angle in base
        ]

    return [float(angle % 360.0) for angle in base]



def generate_candidate_centers(
    deploy_area: Polygon,
    spec: DatasetSpec,
    family: FamilySpec,
    rng: np.random.Generator,
) -> list[Point]:
    """Generate center locations using family-specific spatial bias."""
    center_bias = family.center_bias + family.compactness * 0.35
    edge_bias = family.edge_bias

    min_dist = spec.min_dist
    if family.name == "dispersed":
        min_dist = spec.min_dist * 1.35
    if family.name == "compact":
        min_dist = spec.min_dist * 0.90

    centers = poisson_disc_centers(
        polygon=deploy_area,
        n_points=spec.num_wecs,
        min_dist=min_dist,
        rng=rng,
        max_attempts=spec.max_attempts_per_layout,
        center_bias=center_bias,
        edge_bias=edge_bias,
    )
    return order_centers_for_family(centers, family, deploy_area)



def build_segments_from_centers(
    centers: list[Point],
    angles: list[float],
    deploy_area: Polygon,
    spec: DatasetSpec,
    family: FamilySpec,
    rng: np.random.Generator,
) -> list[LineString]:
    """Convert valid centers into valid segments with family-controlled orientation."""
    accepted: list[LineString] = []

    for center, angle in zip(centers, angles):
        segment = segment_from_center(center, spec.geometry.length, angle)

        if family.jitter_std > 0.0:
            jitter_scale = family.jitter_std * spec.geometry.transverse_length
            accepted_segment = None
            for _ in range(20):
                c2 = Point(
                    center.x + rng.uniform(-jitter_scale, jitter_scale),
                    center.y + rng.uniform(-jitter_scale, jitter_scale),
                )
                s2 = segment_from_center(c2, spec.geometry.length, angle)
                if validate_segment(s2, accepted, deploy_area, spec.geometry, spec.min_dist):
                    accepted_segment = s2
                    break
            if accepted_segment is not None:
                segment = accepted_segment

        if not validate_segment(segment, accepted, deploy_area, spec.geometry, spec.min_dist):
            repaired = False
            for _ in range(60):
                local_angle = angle + rng.uniform(-45.0, 45.0)
                local_center = Point(
                    center.x + rng.uniform(-spec.min_dist, spec.min_dist),
                    center.y + rng.uniform(-spec.min_dist, spec.min_dist),
                )
                candidate = segment_from_center(local_center, spec.geometry.length, local_angle)
                if validate_segment(candidate, accepted, deploy_area, spec.geometry, spec.min_dist):
                    segment = candidate
                    repaired = True
                    break
            if not repaired:
                raise RuntimeError(
                    f"Could not convert valid centers into valid segments for family '{family.name}'."
                )

        accepted.append(segment)

    return accepted


# -----------------------------------------------------------------------------
# Dataset assembly
# -----------------------------------------------------------------------------


def allocate_layouts_to_families(num_layouts: int, families: Iterable[FamilySpec]) -> list[FamilySpec]:
    """Allocate layouts to families from family weights."""
    families = list(families)
    weights = np.array([family.weight for family in families], dtype=float)
    weights = weights / weights.sum()

    raw = weights * num_layouts
    counts = np.floor(raw).astype(int)
    remainder = num_layouts - counts.sum()

    if remainder > 0:
        order = np.argsort(-(raw - counts))
        for idx in order[:remainder]:
            counts[idx] += 1

    assigned: list[FamilySpec] = []
    for family, count in zip(families, counts):
        assigned.extend([family] * count)
    return assigned



def center_record(layout_id: int, wec_id: int, family: str, center: Point) -> dict[str, Any]:
    """Flat center-only record."""
    return {
        "layout_id": layout_id,
        "wec_id": wec_id,
        "family": family,
        "center_x": center.x,
        "center_y": center.y,
    }



def segment_record(layout_id: int, wec_id: int, family: str, segment: LineString) -> dict[str, Any]:
    """Flat segment record with center and endpoint geometry."""
    (x0, y0), (x1, y1) = segment.coords[:]
    return {
        "layout_id": layout_id,
        "wec_id": wec_id,
        "family": family,
        "center_x": 0.5 * (x0 + x1),
        "center_y": 0.5 * (y0 + y1),
        "start_x": x0,
        "start_y": y0,
        "end_x": x1,
        "end_y": y1,
        "length": segment.length,
        "angle_deg": float(np.degrees(np.arctan2(y1 - y0, x1 - x0)) % 360.0),
    }



def layout_summary(
    layout_id: int,
    family: str,
    centers: list[Point],
    deploy_area: Polygon,
) -> dict[str, Any]:
    """Layout-level summary for metadata and later feature engineering."""
    arr = np.array([(p.x, p.y) for p in centers])
    centroid = arr.mean(axis=0)
    spread_x = float(np.std(arr[:, 0]))
    spread_y = float(np.std(arr[:, 1]))
    bbox_area = float((arr[:, 0].max() - arr[:, 0].min()) * (arr[:, 1].max() - arr[:, 1].min()))

    if len(arr) > 1:
        dist = np.sqrt(((arr[:, None, :] - arr[None, :, :]) ** 2).sum(axis=2))
        dist[dist == 0.0] = np.nan
        min_spacing = float(np.nanmin(dist))
        mean_spacing = float(np.nanmean(dist))
    else:
        min_spacing = np.nan
        mean_spacing = np.nan

    return {
        "layout_id": layout_id,
        "family": family,
        "n_wecs": len(centers),
        "deploy_area_m2": float(deploy_area.area),
        "layout_centroid_x": float(centroid[0]),
        "layout_centroid_y": float(centroid[1]),
        "spread_x": spread_x,
        "spread_y": spread_y,
        "bbox_area": bbox_area,
        "min_center_spacing": min_spacing,
        "mean_center_spacing": mean_spacing,
    }



def generate_layout_dataset(
    deploy_area: Polygon,
    spec: DatasetSpec,
    families: Iterable[FamilySpec],
    export_mode: ExportMode,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a surrogate-ready layout dataset."""
    rng = np.random.default_rng(spec.random_seed)
    assignments = allocate_layouts_to_families(spec.num_layouts, families)
    rng.shuffle(assignments)

    wec_records: list[dict[str, Any]] = []
    summary_records: list[dict[str, Any]] = []

    for layout_id, family in enumerate(assignments):
        centers = generate_candidate_centers(deploy_area, spec, family, rng)
        summary_records.append(layout_summary(layout_id, family.name, centers, deploy_area))

        if export_mode == "centers":
            for wec_id, center in enumerate(centers):
                wec_records.append(center_record(layout_id, wec_id, family.name, center))
            continue

        angles = assign_angles(centers, family, spec, deploy_area, rng)
        segments = build_segments_from_centers(centers, angles, deploy_area, spec, family, rng)
        for wec_id, segment in enumerate(segments):
            wec_records.append(segment_record(layout_id, wec_id, family.name, segment))

    return pd.DataFrame(wec_records), pd.DataFrame(summary_records)



def to_swan_obstacle_lines(wec_df: pd.DataFrame, transmission: float = 0.0) -> dict[int, list[str]]:
    """Convert segment dataframe to SWAN obstacle lines grouped by layout."""
    required = {"start_x", "start_y", "end_x", "end_y"}
    if not required.issubset(wec_df.columns):
        raise ValueError("SWAN obstacle export requires segment data with start/end coordinates.")

    grouped: dict[int, list[str]] = {}
    for layout_id, group in wec_df.groupby("layout_id"):
        lines = []
        for _, row in group.sort_values("wec_id").iterrows():
            lines.append(
                f"OBST	TRANS	{transmission:g}	LIN "
                f"{row.start_x:.3f} {row.start_y:.3f} {row.end_x:.3f} {row.end_y:.3f}"
            )
        grouped[int(layout_id)] = lines
    return grouped



def save_layout_dataset(
    wec_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    output_dir: Path,
    export_mode: ExportMode,
    prefix: str = "layouts",
) -> dict[str, Path]:
    """Save layouts and summary tables as CSV and parquet."""
    output_dir.mkdir(parents=True, exist_ok=True)

    entity_name = "wecs_segments" if export_mode == "segments" else "wecs_centers"
    wec_csv = output_dir / f"{prefix}_{entity_name}.csv"
    summary_csv = output_dir / f"{prefix}_summary.csv"
    wec_parquet = output_dir / f"{prefix}_{entity_name}.parquet"
    summary_parquet = output_dir / f"{prefix}_summary.parquet"

    wec_df.to_csv(wec_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)
    wec_df.to_parquet(wec_parquet, index=False)
    summary_df.to_parquet(summary_parquet, index=False)

    return {
        "wec_csv": wec_csv,
        "summary_csv": summary_csv,
        "wec_parquet": wec_parquet,
        "summary_parquet": summary_parquet,
    }


# -----------------------------------------------------------------------------
# Config parsing
# -----------------------------------------------------------------------------


def load_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file with safe loading."""
    return yaml.safe_load(path.read_text())



def build_families_from_config(cfg: dict[str, Any]) -> list[FamilySpec]:
    """Build family list from config, or use defaults if not provided."""
    families_cfg = cfg.get("layouts", {}).get("families")

    if families_cfg is None:
        return list(DEFAULT_FAMILIES)

    if isinstance(families_cfg, dict):
        total = float(sum(families_cfg.values()))
        if total <= 0:
            raise ValueError("Family counts/weights must sum to a positive value.")
        return [
            FamilySpec(name=name, weight=float(value) / total)
            for name, value in families_cfg.items()
        ]

    if isinstance(families_cfg, list):
        families: list[FamilySpec] = []
        for item in families_cfg:
            families.append(
                FamilySpec(
                    name=item["name"],
                    weight=float(item.get("weight", 1.0)),
                    fixed_angle_deg=item.get("fixed_angle_deg"),
                    center_bias=float(item.get("center_bias", 0.0)),
                    edge_bias=float(item.get("edge_bias", 0.0)),
                    jitter_std=float(item.get("jitter_std", 0.0)),
                    row_strength=float(item.get("row_strength", 0.0)),
                    diagonal_strength=float(item.get("diagonal_strength", 0.0)),
                    compactness=float(item.get("compactness", 0.0)),
                )
            )
        total = sum(f.weight for f in families)
        return [FamilySpec(**{**f.__dict__, "weight": f.weight / total}) for f in families]

    raise TypeError("layouts.families must be a dict or a list.")



def build_dataset_spec(problem_cfg: dict[str, Any], seed_override: int | None = None) -> DatasetSpec:
    """Build dataset specification from problem.yaml."""
    layouts_cfg = problem_cfg["layouts"]

    if isinstance(layouts_cfg.get("families"), dict):
        num_layouts = int(sum(layouts_cfg["families"].values()))
    else:
        num_layouts = int(layouts_cfg.get("num_layouts", problem_cfg.get("num_layouts", 0)))

    if num_layouts <= 0:
        raise ValueError("Could not infer a positive num_layouts from problem.yaml.")

    seed = seed_override
    if seed is None:
        seed = problem_cfg.get("training", {}).get("random_seed")

    geometry = WECGeometry(
        length=float(problem_cfg["wec_length_m"]),
        transverse_length=float(layouts_cfg.get("wec_transverse_length_m", layouts_cfg.get("transverse_length_m", 1.0))),
    )

    angle_range = layouts_cfg.get("angle_range_deg", [180.0, 360.0])

    return DatasetSpec(
        num_layouts=num_layouts,
        num_wecs=int(problem_cfg["n_wecs"]),
        min_dist=float(layouts_cfg["min_spacing_m"]),
        geometry=geometry,
        angle_range_deg=(float(angle_range[0]), float(angle_range[1])),
        max_attempts_per_layout=int(layouts_cfg.get("max_attempts_per_layout", 100_000)),
        random_seed=None if seed is None else int(seed),
    )



def load_deploy_area(problem_cfg: dict[str, Any], paths_cfg: dict[str, Any]) -> tuple[Polygon, int]:
    """Build deploy area from polygon and optional exclusions defined in config."""
    polygon_path = paths_cfg.get("deployment_polygon_file") or paths_cfg.get("out_poly_path")
    if polygon_path is None:
        raise ValueError("paths.yaml must define deployment_polygon_file or out_poly_path.")

    _, outer_polygon, _, _ = load_poly_from_csv(Path(polygon_path))

    layouts_cfg = problem_cfg.get("layouts", {})
    exclusions_cfg = layouts_cfg.get("exclusions", {})

    exclusion_areas = []
    centers_file = paths_cfg.get("exclusion_centers_file") or exclusions_cfg.get("centers_file")
    radius = exclusions_cfg.get("radius_m")

    if centers_file is not None and radius is not None:
        centers_df = pd.read_csv(centers_file, header=None)
        centers = [tuple(row[:2]) for row in centers_df.values.tolist()]
        exclusion_areas = centers_to_circular_exclusions(centers, float(radius))

    return build_deploy_area(outer_polygon, exclusion_areas)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Generate WEC layouts for surrogate datasets")
    parser.add_argument("--problem", default="config/problem.yaml", help="Path to problem.yaml")
    parser.add_argument("--paths", default="config/paths.yaml", help="Path to paths.yaml")
    parser.add_argument("--seed", type=int, default=None, help="Override random seed")
    parser.add_argument(
        "--export-mode",
        choices=["segments", "centers"],
        default=None,
        help="Override export mode from config or use explicit mode",
    )
    parser.add_argument(
        "--prefix",
        default="layouts",
        help="Prefix for output files",
    )
    args = parser.parse_args()

    problem_cfg = load_yaml(Path(args.problem))
    paths_cfg = load_yaml(Path(args.paths))

    export_mode = args.export_mode
    if export_mode is None:
        export_mode = problem_cfg.get("layouts", {}).get("export_mode", "segments")
    export_mode = str(export_mode)

    families = build_families_from_config(problem_cfg)
    spec = build_dataset_spec(problem_cfg, seed_override=args.seed)
    deploy_area, n_exc_areas = load_deploy_area(problem_cfg, paths_cfg)

    log.info("Deploy area built successfully: area=%.2f m², exclusion_areas=%d", deploy_area.area, n_exc_areas)
    log.info(
        "Generating %d layouts with %d WECs each in %s mode",
        spec.num_layouts,
        spec.num_wecs,
        export_mode,
    )

    wec_df, summary_df = generate_layout_dataset(
        deploy_area=deploy_area,
        spec=spec,
        families=families,
        export_mode=export_mode,
    )

    output_dir = Path(paths_cfg.get("processed_dir", "data/processed"))
    saved = save_layout_dataset(
        wec_df=wec_df,
        summary_df=summary_df,
        output_dir=output_dir,
        export_mode=export_mode,
        prefix=args.prefix,
    )

    log.info("Saved WEC table to %s", saved["wec_parquet"])
    log.info("Saved summary table to %s", saved["summary_parquet"])
    log.info("Done")


if __name__ == "__main__":
    main()
