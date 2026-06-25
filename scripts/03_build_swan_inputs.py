"""
03_build_swan_inputs.py
Build one SNL-SWAN INPUT file per (layout, sea_state) pair.

Reads:
  - data/processed/layouts.parquet
  - data/processed/sea_states.parquet
  - config/problem.yaml  (grid/bottom file paths, WEC params)
  - config/paths.yaml
  - src/swan_inputs/templates/INPUT.swn.j2  (Jinja2 template)

Writes:
  - runs/<run_id>/INPUT        (SWAN input deck)
  - runs/<run_id>/meta.json    (layout_id, sea_state_id, Hs, Tp, Dir)
  - data/processed/run_index.parquet  (master index of all runs)
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RUN_ID_FMT = "run_{layout_id:06d}_{ss_id:06d}"


def build_wec_block(x_coords: list, y_coords: list, wec_length: float) -> str:
    """
    Return the OBSTACLE block lines for all WECs in the array.
    Each WEC is a line obstacle of length wec_length centred at (x, y),
    oriented perpendicular to the mean wave direction (simplified: N-S).
    """
    lines = []
    half = wec_length / 2.0
    for x, y in zip(x_coords, y_coords):
        lines.append(
            f"OBSTACLE TRANSM 0.0 LINE {x:.2f},{y - half:.2f} {x:.2f},{y + half:.2f}"
        )
    return "\n".join(lines)


def render_input(template_env: Environment,
                 layout_row: pd.Series,
                 ss_row: pd.Series,
                 cfg: dict,
                 pths: dict) -> str:
    tmpl = template_env.get_template("INPUT.swn.j2")
    ctx = dict(
        # Grid & bathymetry
        grid_file   = Path(pths["grid_file"]).name,
        bottom_file = Path(pths["bottom_file"]).name,
        # Sea state
        Hs  = float(ss_row["Hs"]),
        Tp  = float(ss_row["Tp"]),
        Dir = float(ss_row["Dir"]),
        # WEC array
        wec_block = build_wec_block(
            layout_row["x_coords"],
            layout_row["y_coords"],
            cfg["wec_length_m"],
        ),
        n_wecs      = cfg["n_wecs"],
        problem_id  = cfg["problem_id"],
        layout_id   = int(layout_row["layout_id"]),
        sea_state_id= int(ss_row["sea_state_id"]),
    )
    return tmpl.render(**ctx)


def main():
    parser = argparse.ArgumentParser(description="Build SWAN INPUT files")
    parser.add_argument("--problem", default="config/problem.yaml")
    parser.add_argument("--paths",   default="config/paths.yaml")
    parser.add_argument("--max_runs", type=int, default=None,
                        help="Cap total runs (useful for dry-run tests)")
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    processed_dir = Path(pths["processed_dir"])
    runs_dir      = Path(pths["runs_dir"])
    runs_dir.mkdir(parents=True, exist_ok=True)

    layouts    = pd.read_parquet(processed_dir / "layouts.parquet")
    sea_states = pd.read_parquet(processed_dir / "sea_states.parquet")

    template_path = Path(pths.get("swan_input_template",
                                  "src/swan_inputs/templates/INPUT.swn.j2"))
    tmpl_env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        keep_trailing_newline=True,
    )

    # Paired assignment: each layout gets one sea state (round-robin if needed)
    n_layouts = len(layouts)
    n_ss      = len(sea_states)
    pairs     = [(i, i % n_ss) for i in range(n_layouts)]
    if args.max_runs:
        pairs = pairs[: args.max_runs]

    index_records = []
    for layout_idx, ss_idx in pairs:
        lr  = layouts.iloc[layout_idx]
        ssr = sea_states.iloc[ss_idx]
        run_id = RUN_ID_FMT.format(
            layout_id=int(lr["layout_id"]),
            ss_id=int(ssr["sea_state_id"]),
        )
        run_dir = runs_dir / run_id
        run_dir.mkdir(exist_ok=True)

        input_txt = render_input(tmpl_env, lr, ssr, cfg, pths)
        (run_dir / "INPUT").write_text(input_txt, encoding="utf-8")

        meta = dict(
            run_id       = run_id,
            layout_id    = int(lr["layout_id"]),
            sea_state_id = int(ssr["sea_state_id"]),
            family       = str(lr["family"]),
            Hs           = float(ssr["Hs"]),
            Tp           = float(ssr["Tp"]),
            Dir          = float(ssr["Dir"]),
            weight       = float(ssr["weight"]),
        )
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        index_records.append(meta)

    df_index = pd.DataFrame(index_records)
    df_index.to_parquet(processed_dir / "run_index.parquet", index=False)
    log.info("Built %d SWAN INPUT files → %s", len(index_records), runs_dir)


if __name__ == "__main__":
    main()
