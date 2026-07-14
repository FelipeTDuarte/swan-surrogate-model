"""
03_build_swan_inputs.py

Build one SNL-SWAN INPUT file per (layout, sea_state) pair.

Configuration is split by responsibility:
- problem.yaml         -> surrogate-modeling problem definition
                           (n_wecs, layout families, spacing, training seed)
- swan.yaml             -> project-specific SWAN/SNL-SWAN run configuration
                           (grid, forcing fields, boundary, physics, numerics)
- swan_defaults.yaml    -> pipeline-internal fallback values, used to fill in
                           anything the user's swan.yaml does not set

Reads:
- data/processed/layouts_wecs_segments.parquet (or layouts.parquet, legacy)
- data/processed/sea_states.parquet
- config/problem.yaml
- config/swan.yaml
- config/paths.yaml
- config/swan_defaults.yaml
- docs/templates/INPUT.swn.j2 (Jinja2 template)

Writes:
- runs/<run_id>/INPUT   (SWAN input deck)
- runs/<run_id>/meta.json
- data/processed/run_index.parquet
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RUN_ID_FMT = "run_{layout_id:06d}_{ss_id:06d}"


# -----------------------------------------------------------------------------
# Config loading — problem.yaml + swan.yaml + swan_defaults.yaml
# -----------------------------------------------------------------------------


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict.

    Scalars and lists in override replace the corresponding value in base.
    Nested dicts are merged key by key instead of being replaced wholesale.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_swan_config(swan_path: Path, defaults_path: Path) -> dict[str, Any]:
    """Load swan.yaml and fill in any missing fields from swan_defaults.yaml."""
    defaults = yaml.safe_load(defaults_path.read_text()) or {}
    user_cfg = yaml.safe_load(swan_path.read_text()) or {}
    merged = deep_merge(defaults, user_cfg)
    log.info("Loaded SWAN config: %s (defaults: %s)", swan_path, defaults_path)
    return merged


# -----------------------------------------------------------------------------
# WEC obstacle block
# -----------------------------------------------------------------------------


def build_wec_block_from_segments(layout_row: pd.Series, trcoef: float) -> str:
    """Build OBSTACLE lines from full segment geometry (start/end points).

    Expected columns on the layouts table: start_x, start_y, end_x, end_y.
    Preferred path when layouts were generated with export_mode='segments'.
    """
    lines = []
    for x0, y0, x1, y1 in zip(
        layout_row["start_x"], layout_row["start_y"],
        layout_row["end_x"], layout_row["end_y"],
    ):
        lines.append(f"OBSTACLE TRANSM {trcoef:g} LINE {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f}")
    return "\n".join(lines)

def build_wec_block_from_centers(
    layout_row: pd.Series, wec_length: float, angle_deg: float, trcoef: float,
) -> str:
    """Build OBSTACLE lines from centers only, using a fixed length/angle.

    Expected columns on the layouts table: center_x, center_y.
    Used when layouts were generated with export_mode='centers'.
    angle_deg follows the Cartesian convention (0 = east, 90 = north).
    """
    theta = np.radians(angle_deg)
    dx = 0.5 * wec_length * np.cos(theta)
    dy = 0.5 * wec_length * np.sin(theta)

    lines = []
    for x, y in zip(layout_row["center_x"], layout_row["center_y"]):
        x0, y0, x1, y1 = x - dx, y - dy, x + dx, y + dy
        lines.append(f"OBSTACLE TRANSM {trcoef:g} LINE {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f}")
    return "\n".join(lines)

def nautical_to_cartesian_deg(nautical_deg: float) -> float:
    """Convert a nautical bearing (0=N, clockwise) to a Cartesian angle
    (0=E, counter-clockwise).
    """
    return (90.0 - nautical_deg) % 360.0

def resolve_wec_segment_angle_deg(layouts_cfg: dict[str, Any]) -> float:
    """Resolve the WEC segment orientation from the user-facing normal angle.

    wec_angle_deg in swan.yaml represents the direction the WEC faces
    (i.e. the wave direction it is designed to be perpendicular to — the
    array's normal), not the segment's own direction. The segment itself
    is built perpendicular to that normal, so the obstacle line lies along
    the local wave front.
    """
    normal_deg = float(layouts_cfg["wec_angle_deg"])
    convention = layouts_cfg.get("wec_angle_convention", "cartesian").lower()

    if convention == "nautical":
        normal_cartesian = nautical_to_cartesian_deg(normal_deg)
    elif convention == "cartesian":
        normal_cartesian = normal_deg
    else:
        raise ValueError(
            f"Unknown wec_angle_convention '{convention}'. Use 'nautical' or 'cartesian'."
        )

    # Segment lies perpendicular to the normal (rotate 90°).
    return (normal_cartesian + 90.0) % 360.0


def build_wec_block(layout_row: pd.Series, swan_cfg: dict[str, Any]) -> str:
    """Dispatch WEC block construction based on available geometry columns."""
    layouts_cfg = swan_cfg["layouts"]
    trcoef = float(layouts_cfg["transmission_coef"])

    if all(k in layout_row.index for k in ("start_x", "start_y", "end_x", "end_y")):
        return build_wec_block_from_segments(layout_row, trcoef=trcoef)

    if all(k in layout_row.index for k in ("center_x", "center_y")):
        wec_length = float(layouts_cfg["wec_length_m"])
        segment_angle_deg = resolve_wec_segment_angle_deg(layouts_cfg)
        return build_wec_block_from_centers(
            layout_row, wec_length=wec_length, angle_deg=segment_angle_deg, trcoef=trcoef
        )

    raise ValueError(
        "Layout row has neither segment columns (start_x/start_y/end_x/end_y) "
        "nor center columns (center_x/center_y)."
    )


# -----------------------------------------------------------------------------
# Template context — all built from swan_cfg (problem_cfg only supplies IDs)
# -----------------------------------------------------------------------------


def build_grid_context(swan_cfg: dict[str, Any], pths: dict[str, Any]) -> dict[str, Any]:
    """Build CGRID/INPGRID context from swan.yaml (merged with defaults)."""
    grid_cfg = swan_cfg["grid"]
    grid_type = grid_cfg["type"]

    ctx: dict[str, Any] = dict(
        grid_type=grid_type,
        mdc=grid_cfg["mdc"],
        flow=grid_cfg["flow"],
        fhigh=grid_cfg["fhigh"],
        msc=grid_cfg["msc"],
        exc_value=grid_cfg["exc_value"],
        grid_file=Path(pths["grid_file"]).name,
        bottom_file=Path(pths["bottom_file"]).name,
    )

    if grid_type == "regular":
        ctx.update(
            xpc=grid_cfg["xpc"], ypc=grid_cfg["ypc"], alpc=grid_cfg["alpc"],
            xlenc=grid_cfg["xlenc"], ylenc=grid_cfg["ylenc"],
            mxc=grid_cfg["mxc"], myc=grid_cfg["myc"],
            dxinp=grid_cfg.get("dxinp", grid_cfg["xlenc"] / grid_cfg["mxc"]),
            dyinp=grid_cfg.get("dyinp", grid_cfg["ylenc"] / grid_cfg["myc"]),
        )
    elif grid_type == "curvilinear":
        ctx.update(
            mxc=grid_cfg["mxc"], myc=grid_cfg["myc"],
            xexc=grid_cfg.get("xexc", 9.999e3), yexc=grid_cfg.get("yexc", 9.999e3),
        )

    return ctx


def build_optional_fields_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build optional forcing field context (wind, current, water level)."""
    fields_cfg = swan_cfg.get("input_fields", {})
    ctx: dict[str, Any] = {}

    for key in ("wind_file", "current_file", "wlev_file"):
        if fields_cfg.get(key):
            ctx[key] = Path(fields_cfg[key]).name

    if ctx:
        ctx.setdefault("tbeginp", fields_cfg.get("tbeginp", "20260101.000000"))
        ctx.setdefault("deltinp", fields_cfg.get("deltinp", 1))
        ctx.setdefault("delt_unit", fields_cfg.get("delt_unit", "HR"))
        ctx.setdefault("tendinp", fields_cfg.get("tendinp", "20260102.000000"))

    return ctx


def build_boundary_context(swan_cfg: dict[str, Any], ss_row: pd.Series) -> dict[str, Any]:
    """Build boundary condition context."""
    boundary_cfg = swan_cfg["boundary"]
    mode = boundary_cfg["mode"]

    ctx: dict[str, Any] = dict(
        boundary_mode=mode,
        jonswap_gamma=boundary_cfg["jonswap_gamma"],
        boundary_side=boundary_cfg["side"],
        dspr=boundary_cfg["dspr"],
    )

    if mode in {"segment_par", "segment_file"}:
        ctx.update(
            bnd_x1=boundary_cfg["x1"], bnd_y1=boundary_cfg["y1"],
            bnd_x2=boundary_cfg["x2"], bnd_y2=boundary_cfg["y2"],
        )
        if mode == "segment_file":
            ctx["boundary_file"] = Path(boundary_cfg["file"]).name
            ctx["bnd_len"] = boundary_cfg.get("len", 1)

    if mode == "nest":
        ctx["nest_file"] = Path(boundary_cfg["nest_file"]).name

    return ctx


def build_physics_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build physics context."""
    physics_cfg = swan_cfg["physics"]
    return dict(
        gen3_formulation=physics_cfg["gen3"],
        wcap_formulation=physics_cfg["wcap"],
        breaking_alpha=physics_cfg["breaking_alpha"],
        breaking_gamma=physics_cfg["breaking_gamma"],
        friction_cfjon=physics_cfg["friction_cfjon"],
        diffraction=physics_cfg["diffraction"],
        diffraction_smpar=physics_cfg["diffraction_smpar"],
        diffraction_smnum=physics_cfg["diffraction_smnum"],
        diffraction_cgmod=physics_cfg["diffraction_cgmod"],
    )


def build_numerics_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build numerics context."""
    numerics_cfg = swan_cfg["numerics"]
    return dict(
        num_drel=numerics_cfg["drel"], num_dhoval=numerics_cfg["dhoval"],
        num_dtoval=numerics_cfg["dtoval"], num_npnts=numerics_cfg["npnts"],
    )


def build_run_context(
    problem_cfg: dict[str, Any],
    swan_cfg: dict[str, Any],
    pths: dict[str, Any],
    layout_row: pd.Series,
    ss_row: pd.Series,
    run_id: str,
) -> dict[str, Any]:
    """Assemble the full Jinja2 context for one (layout, sea_state) run.

    problem_cfg only contributes identifiers (problem_id); every physical
    and numerical parameter comes from swan_cfg (already merged with
    swan_defaults.yaml).
    """
    mode = swan_cfg["mode"].upper()

    ctx: dict[str, Any] = dict(
        problem_id=problem_cfg["problem_id"],
        run_id=run_id,
        layout_id=int(layout_row["layout_id"]),
        family=str(layout_row.get("family", "unknown")),
        sea_state_id=int(ss_row["sea_state_id"]),
        Hs=float(ss_row["Hs"]),
        Tp=float(ss_row["Tp"]),
        Dir=float(ss_row["Dir"]),
        mode=mode,
        coordinate_system=swan_cfg["coordinate_system"],
        water_level=swan_cfg["water_level"],
        obcase=swan_cfg["layouts"]["obcase"],
        output_prefix=run_id,
        wec_block=build_wec_block(layout_row, swan_cfg),
    )

    ctx.update(build_grid_context(swan_cfg, pths))
    ctx.update(build_optional_fields_context(swan_cfg))
    ctx.update(build_boundary_context(swan_cfg, ss_row))
    ctx.update(build_physics_context(swan_cfg))
    ctx.update(build_numerics_context(swan_cfg))

    if mode == "NONSTATIONARY":
        nonstat_cfg = swan_cfg["nonstationary"]
        ctx.update(
            tbegc=nonstat_cfg["tbegc"], deltc=nonstat_cfg["deltc"],
            deltc_unit=nonstat_cfg["deltc_unit"], tendc=nonstat_cfg["tendc"],
        )

    return ctx


def render_input(template_env: Environment, ctx: dict[str, Any]) -> str:
    """Render the INPUT.swn.j2 template with the given context."""
    tmpl = template_env.get_template("INPUT.swn.j2")
    return tmpl.render(**ctx)


# -----------------------------------------------------------------------------
# Layout loading (supports segments and centers export modes)
# -----------------------------------------------------------------------------


def load_layouts(processed_dir: Path) -> pd.DataFrame:
    """Load the WEC layout table, preferring the new layout_generator.py outputs."""
    candidates = [
        processed_dir / "layouts_wecs_segments.parquet",
        processed_dir / "layouts_wecs_centers.parquet",
        processed_dir / "layouts.parquet",
    ]
    for path in candidates:
        if path.exists():
            log.info("Loading layouts from %s", path)
            return group_layouts(pd.read_parquet(path))

    raise FileNotFoundError(f"No layout parquet file found among: {[str(p) for p in candidates]}")


def group_layouts(wec_df: pd.DataFrame) -> pd.DataFrame:
    """Group a flat per-WEC table into one row per layout_id with list columns."""
    if "wec_id" not in wec_df.columns:
        return wec_df  # legacy layouts.parquet already has one row per layout

    geometry_cols = [
        c for c in ("start_x", "start_y", "end_x", "end_y", "center_x", "center_y")
        if c in wec_df.columns
    ]
    agg = {c: list for c in geometry_cols}
    agg["family"] = "first"
    return wec_df.groupby("layout_id").agg(agg).reset_index()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build SWAN INPUT files")
    parser.add_argument("--problem", default="config/problem.yaml",
                         help="Surrogate-modeling problem definition")
    parser.add_argument("--swan", default="config/swan.yaml",
                         help="Project-specific SWAN run configuration")
    parser.add_argument("--swan-defaults", default="config/swan_defaults.yaml",
                         help="Pipeline-internal SWAN fallback values")
    parser.add_argument("--paths", default="config/paths.yaml")
    parser.add_argument("--max_runs", type=int, default=None,
                         help="Cap total runs (useful for dry-run tests)")
    args = parser.parse_args()

    problem_cfg = yaml.safe_load(Path(args.problem).read_text())
    swan_cfg = load_swan_config(Path(args.swan), Path(args.swan_defaults))
    pths = yaml.safe_load(Path(args.paths).read_text())

    processed_dir = Path(pths["processed_dir"])
    runs_dir = Path(pths["runs_dir"])
    runs_dir.mkdir(parents=True, exist_ok=True)

    layouts = load_layouts(processed_dir)
    sea_states = pd.read_parquet(processed_dir / "sea_states.parquet")

    template_path = Path(pths.get("swan_input_template", "templates/INPUT.swn.j2"))
    tmpl_env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    n_layouts, n_ss = len(layouts), len(sea_states)
    pairs = [(i, i % n_ss) for i in range(n_layouts)]
    if args.max_runs:
        pairs = pairs[: args.max_runs]

    index_records = []
    for layout_idx, ss_idx in pairs:
        lr = layouts.iloc[layout_idx]
        ssr = sea_states.iloc[ss_idx]

        run_id = RUN_ID_FMT.format(layout_id=int(lr["layout_id"]), ss_id=int(ssr["sea_state_id"]))
        run_dir = runs_dir / run_id
        run_dir.mkdir(exist_ok=True)

        ctx = build_run_context(problem_cfg, swan_cfg, pths, lr, ssr, run_id)
        input_txt = render_input(tmpl_env, ctx)
        (run_dir / "INPUT").write_text(input_txt, encoding="utf-8")

        meta = dict(
            run_id=run_id, layout_id=int(lr["layout_id"]), sea_state_id=int(ssr["sea_state_id"]),
            family=str(lr.get("family", "unknown")), Hs=float(ssr["Hs"]), Tp=float(ssr["Tp"]),
            Dir=float(ssr["Dir"]), weight=float(ssr.get("weight", 1.0)),
        )
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        index_records.append(meta)

    df_index = pd.DataFrame(index_records)
    df_index.to_parquet(processed_dir / "run_index.parquet", index=False)
    log.info("Built %d SWAN INPUT files -> %s", len(index_records), runs_dir)


if __name__ == "__main__":
    main()