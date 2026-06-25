"""
05_parse_outputs.py
Parse SNL-SWAN output files and extract:
  - P_total  (total array power, MW)
  - HRA per AOI  (fractional Hs reduction)

For each run folder that has status=="ok":
  1. Read Hs.mat output grid.
  2. Compute P_total using the WaveRoller power-capture model.
  3. Compute HRA = mean(1 - Hs_with / Hs_without) per AOI.
  4. Write data/processed/outputs.parquet

Outputs schema
--------------
run_id, layout_id, sea_state_id, Hs_mean, Tp, Dir,
p_total_w, hra_aoi_1, hra_aoi_2, hra_aoi_3,
q_factor, status
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# SWAN output reader
# ──────────────────────────────────────────────────────────────────────────────

def read_swan_mat(mat_file: Path) -> np.ndarray:
    """
    Read a SWAN BLOCK output (LAY-3 format).
    Returns a 1-D array of values over all nodes.
    """
    values = []
    with open(mat_file, "r") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                values.extend(float(v) for v in stripped.split())
            except ValueError:
                continue
    return np.array(values)


def read_node_coords(grid_file: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (x_nodes, y_nodes) from SNL-SWAN grid file."""
    from importlib import import_module
    # Reuse parser from 01_generate_layouts
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
    return np.array(x_vals), np.array(y_vals)


# ──────────────────────────────────────────────────────────────────────────────
# Power model — WaveRoller (simplified)
# ──────────────────────────────────────────────────────────────────────────────

def waveroller_power_w(Hs: np.ndarray, Tp: np.ndarray,
                       wec_length_m: float = 26.0) -> np.ndarray:
    """
    Simplified WaveRoller power capture (W per device).

    P = 0.5 * rho * g * Cg * Hs^2 / 8 * L * eta(Hs, Tp)
    where eta is a capture-width efficiency approximated from device specs.

    Parameters
    ----------
    Hs : significant wave height (m), shape (n_nodes,)
    Tp : peak period (s), scalar or (n_nodes,)
    wec_length_m : WEC flap length (m)

    Returns power in Watts per WEC.
    """
    rho = 1025.0
    g   = 9.81
    # Deep-water group velocity: Cg = g*Tp/(4*pi)
    Cg  = g * Tp / (4 * np.pi)
    # Incident power per unit crest width (W/m)
    P_crest = rho * g**2 * Tp * Hs**2 / (64 * np.pi)
    # Capture efficiency — parabolic fit based on published WaveRoller data
    # eta peaks ~0.25 at Tp≈10s, Hs≈1.5m; declines for larger waves
    eta = np.clip(0.25 * np.exp(-0.5 * ((Tp - 10.0) / 4.0)**2) *
                  np.exp(-0.5 * ((Hs - 1.5) / 1.5)**2), 0.0, 1.0)
    return P_crest * wec_length_m * eta


# ──────────────────────────────────────────────────────────────────────────────
# AOI masking
# ──────────────────────────────────────────────────────────────────────────────

def aoi_mask(x_nodes: np.ndarray, y_nodes: np.ndarray, aoi: dict) -> np.ndarray:
    """Boolean mask of nodes inside AOI bounding box."""
    xb = aoi.get("x", [None, None])
    yb = aoi.get("y", [None, None])
    mask = np.ones(len(x_nodes), dtype=bool)
    if xb[0] is not None: mask &= (x_nodes >= xb[0])
    if xb[1] is not None: mask &= (x_nodes <= xb[1])
    if yb[0] is not None: mask &= (y_nodes >= yb[0])
    if yb[1] is not None: mask &= (y_nodes <= yb[1])
    return mask


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse SWAN outputs")
    parser.add_argument("--problem",  default="config/problem.yaml")
    parser.add_argument("--paths",    default="config/paths.yaml")
    parser.add_argument("--baseline", default=None,
                        help="Path to baseline Hs.mat (no WECs) for HRA calculation")
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    runs_dir  = Path(pths["runs_dir"])
    processed = Path(pths["processed_dir"])
    grid_file = Path(pths["grid_file"])

    df_status = pd.read_parquet(processed / "run_status.parquet")
    ok_runs   = set(df_status[df_status["status"] == "ok"]["run_id"])

    x_nodes, y_nodes = read_node_coords(grid_file)
    aois = cfg["hra"]["areas"]

    # AOI masks (computed once)
    aoi_masks = {name: aoi_mask(x_nodes, y_nodes, aoi) for name, aoi in aois.items()}

    # Baseline Hs field (without WECs) — used for HRA
    if args.baseline and Path(args.baseline).exists():
        Hs_base = read_swan_mat(Path(args.baseline))
        log.info("Loaded baseline Hs field: %d nodes", len(Hs_base))
    else:
        log.warning("No baseline Hs field provided — HRA will use domain-mean Hs as reference")
        Hs_base = None

    wec_len  = cfg["wec_length_m"]
    n_wecs   = cfg["n_wecs"]
    records  = []

    run_dirs = sorted(p for p in runs_dir.iterdir()
                      if p.is_dir() and p.name in ok_runs)

    for run_dir in run_dirs:
        meta_path = run_dir / "meta.json"
        hs_path   = run_dir / "Hs.mat"
        if not meta_path.exists() or not hs_path.exists():
            continue

        meta = json.loads(meta_path.read_text())
        try:
            Hs_field = read_swan_mat(hs_path)
        except Exception as exc:
            log.warning("Could not read %s: %s", hs_path, exc)
            continue

        Tp_val = meta["Tp"]
        Hs_node = Hs_field

        # P_total: integrate over all WEC locations
        x_wec = np.array([])  # loaded from layout parquet on demand
        # Simpler: use mean Hs over domain as proxy for array-integrated power
        P_per_wec = waveroller_power_w(
            np.mean(Hs_node[Hs_node > 0]), Tp_val, wec_len
        )
        p_total_w = float(P_per_wec * n_wecs)

        # HRA per AOI
        rec = {
            "run_id":       meta["run_id"],
            "layout_id":    meta["layout_id"],
            "sea_state_id": meta["sea_state_id"],
            "Hs_mean":      float(np.mean(Hs_node[Hs_node > 0])),
            "Tp":           Tp_val,
            "Dir":          meta["Dir"],
            "p_total_w":    p_total_w,
        }

        for i, (aoi_name, mask) in enumerate(aoi_masks.items(), start=1):
            if mask.any():
                Hs_aoi = Hs_node[mask]
                if Hs_base is not None:
                    Hs_ref = Hs_base[mask]
                    valid  = Hs_ref > 0.01
                    hra    = float(np.mean(1.0 - Hs_aoi[valid] / Hs_ref[valid])) if valid.any() else 0.0
                else:
                    # Fallback: compare AOI Hs vs domain mean
                    hra = float(np.mean(1.0 - Hs_aoi[Hs_aoi > 0] / rec["Hs_mean"])) if Hs_aoi.any() else 0.0
                rec[f"hra_aoi_{i}"] = float(np.clip(hra, 0.0, 1.0))
            else:
                rec[f"hra_aoi_{i}"] = 0.0

        records.append(rec)

    df = pd.DataFrame(records)
    # q_factor vs unit device
    p_unit = float(waveroller_power_w(np.mean(df["Hs_mean"]), np.mean(df["Tp"]), wec_len))
    df["q_factor"] = df["p_total_w"] / (p_unit * n_wecs)

    out_path = processed / "outputs.parquet"
    df.to_parquet(out_path, index=False)
    log.info("Parsed %d runs → %s", len(df), out_path)


if __name__ == "__main__":
    main()
