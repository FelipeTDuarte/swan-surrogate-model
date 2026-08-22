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
    """Build every optional forcing-field context for the INPUT deck.

    swan_cfg["input_fields"] is a single list mixing two kinds of entries:

    - Spatially varying fields (kind in VALID_INPGRID_KINDS): rendered as
      INPGRID/READINP via the Jinja `inpgrid_block` macro (wind, current,
      water level, friction, plants, turbulence, mud, ice, spectral
      partitions). Bathymetry (BOTTOM) is structural and handled
      separately in build_grid_context.

    - Uniform scalar shortcuts (kind: WIND or kind: ICE): rendered as the
      standalone WIND [vel][dir] or ICE [aice][hice] command. These are
      dedicated pseudo-kinds distinct from WI/WX/WY and AICE/HICE, which
      always mean a spatial INPGRID field — per swan.edt, only wind and
      ice have a documented uniform command, so kind: WIND / kind: ICE
      unambiguously select that path with no extra flag needed.

    Everything here is optional: an empty/absent input_fields list simply
    produces no extra SWAN commands beyond the structural BOTTOM block.
    """
    VALID_INPGRID_KINDS = {
    "WLEV", "CUR", "VX", "VY", "FR", "WI", "WX", "WY",
    "NPLA", "TURB", "MUDL", "AICE", "HICE", "HSS", "TSS", "DSS",
    }
    UNIFORM_KIND_COMMANDS = {
    "WIND": ("WIND", ("vel", "dir")),
    "ICE": ("ICE", ("aice", "hice")),
    }

    raw_fields = swan_cfg.get("input_fields")
    if not raw_fields:
        return {}

    grid_fields = []
    uniform_ctx: dict[str, Any] = {}
    seen_uniform_kind: dict[str, str] = {}  # command -> kind that set it

    for field_cfg in raw_fields:
        if "kind" not in field_cfg:
            raise ValueError(f"Each input_fields entry needs 'kind'. Got: {field_cfg}")

        kind = str(field_cfg["kind"]).upper()

        if kind in UNIFORM_KIND_COMMANDS:
            command, param_names = UNIFORM_KIND_COMMANDS[kind]
            if command in seen_uniform_kind:
                raise ValueError(
                    f"Duplicate uniform '{kind}' entry. Only one kind: "
                    f"{kind} entry is allowed per run."
                )
            seen_uniform_kind[command] = kind

            missing = [p for p in param_names if p not in field_cfg]
            if missing:
                raise ValueError(
                    f"kind: {kind} entry is missing required parameter(s) "
                    f"{missing} for the {command} command."
                )

            if command == "WIND":
                uniform_ctx["wind_vel"] = field_cfg["vel"]
                uniform_ctx["wind_dir"] = field_cfg["dir"]
            else:
                uniform_ctx["ice_aice"] = field_cfg["aice"]
                uniform_ctx["ice_hice"] = field_cfg["hice"]

        elif kind in VALID_INPGRID_KINDS:
            if "file" not in field_cfg:
                raise ValueError(
                    f"input_fields entry with kind: {kind} needs 'file'. "
                    f"Got: {field_cfg}"
                )
            resolved = dict(field_cfg)
            resolved["kind"] = kind
            resolved["file"] = Path(field_cfg["file"]).name
            grid_fields.append(resolved)

        else:
            raise ValueError(
                f"Unknown input_fields kind '{kind}'. Valid kinds: "
                f"{sorted(VALID_INPGRID_KINDS)} for spatial fields, or "
                f"{sorted(UNIFORM_KIND_COMMANDS)} for uniform scalar forcing."
            )

    ctx: dict[str, Any] = dict(uniform_ctx)
    if grid_fields:
        ctx["input_fields"] = grid_fields
    return ctx

def build_boundary_context(swan_cfg: dict[str, Any], ss_row: pd.Series) -> dict[str, Any]:
    """Build the BOUN/BOUNDSPEC/BOUNDNEST context.

    Supports:
    - "side_par"    -> BOUN SHAPE ... + BOUN SIDE ... CON|VAR PAR (default,
                       single side or multiple sides via boundary.sides)
    - "segment_par" -> BOUNDSPEC SEGMENT XY <points> CON|VAR PAR
    - "segment_file"-> BOUNDSPEC SEGMENT XY <points> UNI|VAR FILE 'fname'
    - "nest"        -> BOUNDNEST1 NEST 'fname' CLOSED|OPEN
    - "wamnest"     -> BOUNDNEST2 WAMNEST 'fname' ...
    - "ww3nest"     -> BOUNDNEST3 WW3 'fname' ...

    Every spectral-shape parameter (shape, gamma, sigfr, d, peak_mean,
    dspr_mode) is optional and falls back to SWAN's own default via the
    template's `default(..., true)` filters if omitted here.
    """
    boundary_cfg = swan_cfg["boundary"]
    mode = boundary_cfg["mode"]

    ctx: dict[str, Any] = dict(boundary_mode=mode)

    if mode in {"segment_par", "segment_file"}:
        points = boundary_cfg.get("points")
        if not points:
            points = [
                dict(x=boundary_cfg["x1"], y=boundary_cfg["y1"]),
                dict(x=boundary_cfg["x2"], y=boundary_cfg["y2"]),
            ]
        ctx["bnd_points"] = points
        ctx["boundary_kind"] = boundary_cfg.get("kind")

        if mode == "segment_file":
            ctx["boundary_file"] = Path(boundary_cfg["file"]).name
            ctx["bnd_len"] = boundary_cfg.get("len", 1)
            if "seq" in boundary_cfg:
                ctx["bnd_seq"] = boundary_cfg["seq"]
        else:
            par_sets = boundary_cfg.get("par_sets")
            if not par_sets:
                par_sets = [dict(
                    len=0,
                    hs=ss_row.get("Hs"), per=ss_row.get("Tp"), dir=ss_row.get("Dir"),
                    dd=boundary_cfg.get("dspr"),
                )]
            ctx["bnd_par_sets"] = par_sets

    elif mode == "nest":
        ctx["nest_file"] = Path(boundary_cfg["nest_file"]).name
        ctx["nest_mode"] = boundary_cfg.get("nest_mode", "CLOSED")

    elif mode == "wamnest":
        ctx["nest_file"] = Path(boundary_cfg["nest_file"]).name
        ctx["nest_fmt"] = boundary_cfg.get("nest_fmt", "FREE")
        if "xgc" in boundary_cfg:
            ctx["xgc"] = boundary_cfg["xgc"]
            ctx["ygc"] = boundary_cfg["ygc"]
        if "lwdate" in boundary_cfg:
            ctx["lwdate"] = boundary_cfg["lwdate"]

    elif mode == "ww3nest":
        ctx["nest_file"] = Path(boundary_cfg["nest_file"]).name
        ctx["nest_fmt"] = boundary_cfg.get("nest_fmt", "FREE")
        ctx["nest_open_close"] = boundary_cfg.get("nest_open_close", "CLOSED")
        if "xgc" in boundary_cfg:
            ctx["xgc"] = boundary_cfg["xgc"]
            ctx["ygc"] = boundary_cfg["ygc"]

    else:  # side_par (default): single side, or multiple via boundary.sides
        sides_cfg = boundary_cfg.get("sides")
        if sides_cfg:
            ctx["boundary_sides"] = sides_cfg
        else:
            ctx["shape"] = boundary_cfg.get("shape", "JONSWAP")
            ctx["boundary_side"] = boundary_cfg.get("side", "W")
            ctx["boundary_rotation"] = boundary_cfg.get("rotation", "CCW")
            ctx["boundary_kind"] = boundary_cfg.get("kind", "CON")
            # Only add optional spectral-shape / side parameters if the
            # user actually set them — omitting the key (instead of
            # setting it to None) lets the template's `is defined` checks
            # and `default(..., true)` filters work correctly.
            for key in ("jonswap_gamma", "sigfr", "d", "peak_mean", "dspr_mode", "dspr"):
                if boundary_cfg.get(key) is not None:
                    ctx[key] = boundary_cfg[key]
            if boundary_cfg.get("k") is not None:
                ctx["boundary_k"] = boundary_cfg["k"]

    return ctx

def build_physics_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the full PHYSICS context (swan.edt): GEN1/GEN2/GEN3, SSWELL,
    NEGATINP, WCAP, QUADRUPL, BREAK, FRICTION, TRIAD, VEGETATION,
    TURBULENCE, MUD, SICE, OFF <process>, LIMITER, DIFFRAC.

    swan_cfg["physics"] mirrors the swan.edt command tree closely: each
    sub-command has its own dict of parameters, and every parameter is
    optional — anything left unset is omitted from the context, so the
    template's `is defined` checks skip that piece of the command and
    SWAN falls back to its own internal default.

    Backward compatible with the previous flat format
    (physics.gen3: "WESTHUYSEN", physics.wcap: "KOMEN", physics.breaking_alpha,
    physics.friction_cfjon, physics.diffraction) used by earlier swan.yaml files.
    """
    phys = swan_cfg.get("physics", {})
    ctx: dict[str, Any] = {}

    gen = phys.get("gen", {})
    if gen:
        ctx["gen_mode"] = gen.get("mode", "GEN3")
        for key in ("cf10", "cf20", "cf30", "cf40", "cf50", "cf60",
                    "edmlpm", "cdrag", "umin"):
            if gen.get(key) is not None:
                ctx[f"gen_{key}"] = gen[key]

        gen3 = gen.get("gen3", {})
        if gen3.get("formulation") is not None:
            ctx["gen3_formulation"] = gen3["formulation"]
        if all(k in gen3 for k in ("a1sds", "a2sds", "p1sds", "p2sds")):
            ctx["gen3_a1sds"] = gen3["a1sds"]
            ctx["gen3_a2sds"] = gen3["a2sds"]
            ctx["gen3_p1sds"] = gen3["p1sds"]
            ctx["gen3_p2sds"] = gen3["p2sds"]
        for key in ("cdsv", "feswell", "updown", "wind_input", "dbias", "agrow"):
            if gen3.get(key) is not None:
                ctx[f"gen3_{key}"] = gen3[key]
    else:
        if phys.get("gen3") is not None:
            ctx["gen3_formulation"] = phys["gen3"]

    sswell = phys.get("sswell", {})
    if sswell.get("formulation") is not None:
        ctx["sswell_formulation"] = sswell["formulation"]
        for key in ("cdsv", "feswell", "b1"):
            if sswell.get(key) is not None:
                ctx[f"sswell_{key}"] = sswell[key]

    if phys.get("negatinp_rdcoef") is not None:
        ctx["negatinp_rdcoef"] = phys["negatinp_rdcoef"]

    wcap_cfg = phys.get("wcap", {})
    if isinstance(wcap_cfg, str):
        wcap_formulation = wcap_cfg
        wcap_cfg = {}
    else:
        wcap_formulation = wcap_cfg.get("formulation")
    if wcap_formulation is not None:
        ctx["wcap_formulation"] = wcap_formulation
        for key in ("cds2", "stpm", "powst", "delta", "powk", "br", "current_cds3"):
            if wcap_cfg.get(key) is not None:
                ctx[f"wcap_{key}"] = wcap_cfg[key]

    if phys.get("disable_quadrupl"):
        ctx["disable_quadrupl"] = True
    else:
        quad = phys.get("quadrupl", {})
        for key in ("iquad", "lambda", "cnl4", "csh1", "csh2", "csh3"):
            if quad.get(key) is not None:
                ctx[f"quadrupl_{key}"] = quad[key]

    brk = phys.get("break", {})
    if brk.get("type") is not None or "breaking_alpha" in phys or "breaking_gamma" in phys:
        ctx["breaking_type"] = brk.get("type", "CON")
        ctx["breaking_alpha"] = brk.get("alpha", phys.get("breaking_alpha"))
        ctx["breaking_gamma"] = brk.get("gamma", phys.get("breaking_gamma"))
        for key in ("gammin", "gammax", "gamneg", "coeff1", "coeff2",
                    "a", "b", "gamma0", "a1", "a2", "a3", "npnts", "pown"):
            if brk.get(key) is not None:
                ctx[f"breaking_{key}"] = brk[key]

    fric = phys.get("friction", {})
    fric_cfjon = fric.get("cfjon", phys.get("friction_cfjon"))
    if fric.get("type") is not None or fric_cfjon is not None:
        ctx["friction_type"] = fric.get("type", "JONSWAP")
        if fric_cfjon is not None:
            ctx["friction_cfjon"] = fric_cfjon
        if fric.get("variable"):
            ctx["friction_variable"] = True
            for key in ("cfj1", "cfj2", "dsp1", "dsp2"):
                if fric.get(key) is not None:
                    ctx[f"friction_{key}"] = fric[key]
        for key in ("cfw", "cfc", "kn", "s", "d"):
            if fric.get(key) is not None:
                ctx[f"friction_{key}"] = fric[key]

    triad = phys.get("triad", {})
    if triad.get("enable"):
        ctx["enable_triad"] = True
        ctx["triad_type"] = triad.get("type", "DCTA")
        for key in ("trfac", "p", "biphase", "cutfr", "dint", "a", "b", "itriad"):
            if triad.get(key) is not None:
                ctx[f"triad_{key}"] = triad[key]

    veg = phys.get("vegetation", {})
    if veg.get("iveg") is not None:
        ctx["vegetation_iveg"] = veg["iveg"]
        ctx["vegetation_layers"] = veg.get("layers", [])

    turb = phys.get("turbulence", {})
    if turb.get("ctb") is not None:
        ctx["turbulence_ctb"] = turb["ctb"]
        if turb.get("tbcur") is not None:
            ctx["turbulence_tbcur"] = turb["tbcur"]

    mud = phys.get("mud", {})
    if mud.get("layer") is not None:
        ctx["mud_layer"] = mud["layer"]
        ctx["mud_rhom"] = mud["rhom"]
        ctx["mud_viscm"] = mud["viscm"]
        ctx["mud_rhow"] = mud["rhow"]
        ctx["mud_viscw"] = mud["viscw"]

    sice = phys.get("sice", {})
    if sice.get("type") is not None:
        ctx["sice_type"] = sice["type"]
        for key in ("c0", "c1", "c2", "c3", "c4", "c5", "c6", "chf", "npf"):
            if sice.get(key) is not None:
                ctx[f"sice_{key}"] = sice[key]

    limiter = phys.get("limiter", {})
    if limiter.get("ursell") is not None or limiter.get("qb") is not None \
            or phys.get("limiter_ursell") is not None or phys.get("limiter_qb") is not None:
        ctx["limiter_ursell"] = limiter.get("ursell", phys.get("limiter_ursell", 10))
        ctx["limiter_qb"] = limiter.get("qb", phys.get("limiter_qb", 1))
        
    surfbeat = phys.get("surfbeat", {})
    if surfbeat.get("df") is not None:
        ctx["surfbeat_df"] = surfbeat["df"]
        ctx["surfbeat_nmax"] = surfbeat.get("nmax")
        ctx["surfbeat_emin"] = surfbeat.get("emin")
        ctx["surfbeat_spacing"] = surfbeat.get("spacing", "UNIFORM")

    if phys.get("setup_supcor") is not None:
        ctx["setup_supcor"] = phys["setup_supcor"]

    if phys.get("diffraction"):
        ctx["diffraction"] = True
        diff = phys.get("diffraction_params", {})
        ctx["diffraction_idiffr"] = diff.get("idiffr", 1)
        ctx["diffraction_smpar"] = diff.get("smpar", phys.get("diffraction_smpar", 0.0))
        ctx["diffraction_smnum"] = diff.get("smnum", phys.get("diffraction_smnum", 1))
        ctx["diffraction_cgmod"] = diff.get("cgmod", phys.get("diffraction_cgmod", 1))

    off = phys.get("off", {})
    for flag_key, ctx_key in (
        ("wind_growth", "disable_wind_growth"),
        ("wcapping", "disable_wcapping"),
        ("breaking", "disable_breaking"),
        ("refrac", "disable_refrac"),
        ("fshift", "disable_fshift"),
        ("bndchk", "disable_bndchk"),
    ):
        if off.get(flag_key) or phys.get(ctx_key):
            ctx[ctx_key] = True

    prop = phys.get("prop", {})
    if prop.get("scheme") is not None:
        ctx["prop_scheme"] = prop["scheme"]
        if prop["scheme"] == "GSE":
            ctx["prop_waveage"] = prop.get("waveage")
            ctx["prop_waveage_unit"] = prop.get("waveage_unit", "HR")

    return ctx

def build_numerics_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the NUMERICS context (termination + iteration + optional sub-commands
    DIRIMPL, REFRLIM, SIGIMPL/SIGEXPL, CTHETA, CSIGMA, numeric SETUP).

    swan_cfg["numerics"] mirrors the swan.edt command tree; every field is
    optional and anything left unset is omitted from the context, letting
    the template's `is defined` checks skip that piece and SWAN fall back
    to its own internal default.
    """
    numeric = swan_cfg.get("numerics", {})
    ctx: dict[str, Any] = {}
    if numeric.get("termination") is not None or numeric.get("iteration_mode") is not None:
        ctx["numeric_termination"] = numeric.get("termination", "STOPC")
        if ctx["numeric_termination"] == "STOPC":
            for key in ("dabs", "drel", "curvat", "npnts", "dtabs", "curvt"):
                if numeric.get(key) is not None:
                    ctx[f"numeric_{key}"] = numeric[key]
        else:
            for key in ("drel", "dhoval", "dtoval", "npnts"):
                if numeric.get(key) is not None:
                    ctx[f"numeric_{key}"] = numeric[key]

        ctx["numeric_iteration_mode"] = numeric.get("iteration_mode", "STAT")
        if ctx["numeric_iteration_mode"] == "STAT":
            for key in ("mxitst", "alfa"):
                if numeric.get(key) is not None:
                    ctx[f"numeric_{key}"] = numeric[key]
        else:
            if numeric.get("mxitns") is not None:
                ctx["numeric_mxitns"] = numeric["mxitns"]
        if numeric.get("limiter") is not None:
            ctx["numeric_limiter"] = numeric["limiter"]

        if numeric.get("dirimpl_cdd") is not None:
            ctx["numeric_dirimpl_cdd"] = numeric["dirimpl_cdd"]
            ctx["numeric_dirimpl_mode"] = numeric.get("dirimpl_mode", "DEP")

        if numeric.get("refrlim_frlim") is not None:
            ctx["numeric_refrlim_frlim"] = numeric["refrlim_frlim"]
            ctx["numeric_refrlim_power"] = numeric.get("refrlim_power")

        if numeric.get("sigma_scheme") is not None:
            ctx["numeric_sigma_scheme"] = numeric["sigma_scheme"]
            if numeric["sigma_scheme"] == "SIGIMPL":
                for key in ("sigimpl_css", "sigimpl_eps2", "sigimpl_outp", "sigimpl_niter"):
                    if numeric.get(key) is not None:
                        ctx[f"numeric_{key}"] = numeric[key]
            else:
                for key in ("sigexpl_css", "sigexpl_cfl"):
                    if numeric.get(key) is not None:
                        ctx[f"numeric_{key}"] = numeric[key]

        if numeric.get("ctheta_cfl") is not None:
            ctx["numeric_ctheta_cfl"] = numeric["ctheta_cfl"]
        if numeric.get("csigma_cfl") is not None:
            ctx["numeric_csigma_cfl"] = numeric["csigma_cfl"]

        if numeric.get("setup_eps2") is not None:
            ctx["numeric_setup_eps2"] = numeric["setup_eps2"]
            ctx["numeric_setup_outp"] = numeric.get("setup_outp")
            ctx["numeric_setup_niter"] = numeric.get("setup_niter")

    return ctx

def build_output_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    
    """Build the OUTPUT context (swan.edt): FRAME/GROUP/CURVE/RAY/ISOLINE/
    POINTS/NGRID locations, QUANTITY overrides, OUTPUT OPTIONS, and output
    requests (BLOCK/TABLE/SPECOUT/NESTOUT).

    swan_cfg["output"] mirrors the swan.edt command tree; every sub-key is
    optional. Locations are referenced by name ("location:") from the
    output requests, so it's the caller's responsibility to keep 'sname'/
    'rname' values consistent between the two lists.
    """
    out_cfg = swan_cfg.get("output", {})
    ctx: dict[str, Any] = {}

    locations = out_cfg.get("locations")
    if locations:
        resolved_locs = []
        for i, loc in enumerate(locations):
            ltype = str(loc.get("type", "")).upper()
            if ltype not in {"FRAME", "GROUP", "CURVE", "RAY", "ISOLINE", "POINTS", "NGRID"}:
                raise ValueError(f"output.locations[{i}]: unknown type '{ltype}'.")

            if ltype in {"FRAME", "GROUP", "CURVE", "ISOLINE", "POINTS", "NGRID"} and not loc.get("sname"):
                raise ValueError(f"output.locations[{i}] ({ltype}) needs 'sname'.")
            if ltype == "RAY" and not loc.get("rname"):
                raise ValueError(f"output.locations[{i}] (RAY) needs 'rname'.")
            if ltype == "ISOLINE" and not loc.get("rname"):
                raise ValueError(f"output.locations[{i}] (ISOLINE) needs 'rname' referencing a RAY.")
            if ltype == "POINTS" and not loc.get("points") and not loc.get("file"):
                raise ValueError(f"output.locations[{i}] (POINTS) needs 'points' or 'file'.")

            resolved_locs.append({**loc, "type": ltype})
        ctx["locations"] = resolved_locs

    quantities = out_cfg.get("quantities")
    if quantities:
        ctx["quantities"] = quantities

    oo = out_cfg.get("output_options", {})
    if oo.get("comment") is not None:
        ctx["output_options_comment"] = oo["comment"]
        for key in ("table_field", "block_ndec", "block_len", "spec_ndec"):
            if oo.get(key) is not None:
                ctx[f"output_options_{key}"] = oo[key]

    requests = out_cfg.get("requests")
    if requests:
        resolved_reqs = []
        for i, r in enumerate(requests):
            rtype = str(r.get("type", "")).upper()
            if rtype not in {"BLOCK", "TABLE", "SPECOUT", "NESTOUT"}:
                raise ValueError(f"output.requests[{i}]: unknown type '{rtype}'.")
            if not r.get("location"):
                raise ValueError(f"output.requests[{i}] ({rtype}) needs 'location'.")
            if not r.get("file"):
                raise ValueError(f"output.requests[{i}] ({rtype}) needs 'file'.")
            if rtype in {"BLOCK", "TABLE"} and not r.get("quantities"):
                raise ValueError(f"output.requests[{i}] ({rtype}) needs 'quantities'.")
            if r.get("nonstationary") and (r.get("tbeg") is None or r.get("delt") is None):
                raise ValueError(
                    f"output.requests[{i}] ({rtype}): nonstationary requires 'tbeg' and 'delt'."
                )
            resolved_reqs.append({**r, "type": rtype})
        ctx["requests"] = resolved_reqs

    return ctx

def build_test_compute_context(swan_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the TEST / COMPUTE / HOTFILE context (swan.edt).

    TEST and HOTFILE are optional diagnostic/restart commands. COMPUTE is
    required by SWAN — if swan_cfg["compute"] is missing entirely, this
    falls back to a plain "COMPUTE STATIONARY" so the .swn file is still
    valid. Supports either a single compute command (mode/time or
    tbegc/deltc/tendc) or a list of staged COMPUTE calls via
    swan_cfg["compute"]["stages"].
    """
    ctx: dict[str, Any] = {}

    test = swan_cfg.get("test", {})
    if test.get("itest") is not None:
        ctx["test_itest"] = test["itest"]
        ctx["test_itrace"] = test.get("itrace", 0)

        mode = str(test.get("points_mode", "")).upper()
        if mode == "IJ":
            if not test.get("ij_points"):
                raise ValueError("test.points_mode: IJ needs 'ij_points'.")
            ctx["test_points_mode"] = "IJ"
            ctx["test_ij_points"] = test["ij_points"]
        elif mode == "K":
            if not test.get("k_points"):
                raise ValueError("test.points_mode: K needs 'k_points'.")
            ctx["test_points_mode"] = "K"
            ctx["test_k_points"] = test["k_points"]
        elif mode == "XY":
            if not test.get("xy_points"):
                raise ValueError("test.points_mode: XY needs 'xy_points'.")
            ctx["test_points_mode"] = "XY"
            ctx["test_xy_points"] = test["xy_points"]

        for key in ("par_file", "s1d_file", "s2d_file"):
            if test.get(key) is not None:
                ctx[f"test_{key}"] = test[key]

    compute = swan_cfg.get("compute", {"mode": "STATIONARY"})

    def _validate_stage(stage: dict[str, Any], where: str) -> None:
        mode = str(stage.get("mode", "STATIONARY")).upper()
        if mode not in {"STATIONARY", "NONSTATIONARY"}:
            raise ValueError(f"{where}: mode must be STATIONARY or NONSTATIONARY.")
        if mode == "NONSTATIONARY":
            for key in ("tbegc", "deltc"):
                if stage.get(key) is None:
                    raise ValueError(f"{where} (NONSTATIONARY) needs '{key}'.")

    stages = compute.get("stages")
    if stages:
        for i, s in enumerate(stages):
            _validate_stage(s, f"compute.stages[{i}]")
        ctx["compute_stages"] = stages
    else:
        _validate_stage(compute, "compute")
        ctx["compute_mode"] = compute.get("mode", "STATIONARY")
        if ctx["compute_mode"] == "STATIONARY":
            if compute.get("time") is not None:
                ctx["compute_time"] = compute["time"]
        else:
            ctx["compute_tbegc"] = compute.get("tbegc")
            ctx["compute_deltc"] = compute.get("deltc")
            ctx["compute_deltc_unit"] = compute.get("deltc_unit", "HR")
            if compute.get("tendc") is not None:
                ctx["compute_tendc"] = compute["tendc"]

    hotfile = swan_cfg.get("hotfile", {})
    if hotfile.get("file") is not None:
        ctx["hotfile_file"] = hotfile["file"]
        ctx["hotfile_fmt"] = hotfile.get("fmt", "FREE")

    return ctx

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
        (run_dir / "INPUT.swn").write_text(input_txt, encoding="utf-8")

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