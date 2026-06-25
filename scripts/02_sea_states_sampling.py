"""
02_sea_states_sampling.py
Sample representative sea states from 60-year hourly hindcast.

Strategy
--------
1. Load CSV (Hs, Tp, Dir).
2. Fit a non-parametric joint KDE on (Hs, Tp, Dir) to estimate density.
3. Build a 3-D scatter diagram by binning the data.
4. Sample sea states using importance weighting:
   - weight = occurrence_frequency / proposal_density
   - This ensures rare but energetic states are represented.
5. Add extreme-event supplement: top 1% Hs states sampled uniformly.
6. Save to data/processed/sea_states.parquet with weights column.
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import gaussian_kde

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def load_wave_data(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Normalise column names — accept any capitalisation
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {}
    for col in df.columns:
        if col.startswith("hs"):  rename[col] = "Hs"
        elif col.startswith("tp"): rename[col] = "Tp"
        elif col.startswith("dir") or col.startswith("dp"): rename[col] = "Dir"
    df = df.rename(columns=rename)[["Hs", "Tp", "Dir"]]
    df = df.dropna()
    df = df[df["Hs"] > 0]
    log.info("Loaded %d records from %s", len(df), csv_path)
    log.info("  Hs:  %.2f – %.2f m   (mean=%.2f)", df["Hs"].min(), df["Hs"].max(), df["Hs"].mean())
    log.info("  Tp:  %.2f – %.2f s   (mean=%.2f)", df["Tp"].min(), df["Tp"].max(), df["Tp"].mean())
    log.info("  Dir: %.1f – %.1f deg (mean=%.1f)", df["Dir"].min(), df["Dir"].max(), df["Dir"].mean())
    return df


def circular_encode(dir_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Encode direction as (sin, cos) to handle circularity in KDE."""
    rad = np.deg2rad(dir_deg)
    return np.sin(rad), np.cos(rad)


def build_scatter_bins(df: pd.DataFrame,
                       n_hs: int = 20, n_tp: int = 20, n_dir: int = 12
                       ) -> tuple[np.ndarray, np.ndarray]:
    """Return bin-centre grid and occurrence frequencies (normalised)."""
    hs_edges  = np.linspace(df["Hs"].min(),  df["Hs"].max(),  n_hs  + 1)
    tp_edges  = np.linspace(df["Tp"].min(),  df["Tp"].max(),  n_tp  + 1)
    dir_edges = np.linspace(df["Dir"].min(), df["Dir"].max(), n_dir + 1)

    H, _ = np.histogramdd(
        df[["Hs", "Tp", "Dir"]].values,
        bins=[hs_edges, tp_edges, dir_edges]
    )
    freq = H / H.sum()

    # Grid of bin centres
    hs_c  = 0.5 * (hs_edges[:-1]  + hs_edges[1:])
    tp_c  = 0.5 * (tp_edges[:-1]  + tp_edges[1:])
    dir_c = 0.5 * (dir_edges[:-1] + dir_edges[1:])
    gg = np.array(np.meshgrid(hs_c, tp_c, dir_c, indexing="ij")).reshape(3, -1).T
    ff = freq.ravel()

    # Keep only populated bins
    mask = ff > 0
    return gg[mask], ff[mask]


def importance_sample(df: pd.DataFrame,
                      n_samples: int,
                      rng: np.random.Generator,
                      extreme_frac: float = 0.05) -> pd.DataFrame:
    """
    Draw n_samples sea states using importance sampling over the scatter diagram.

    Parameters
    ----------
    extreme_frac : fraction of n_samples dedicated to extreme events (top-1% Hs)
    """
    log.info("Fitting joint KDE on (Hs, Tp, sin_Dir, cos_Dir) …")
    sin_d, cos_d = circular_encode(df["Dir"].values)
    X = np.column_stack([df["Hs"].values, df["Tp"].values, sin_d, cos_d])
    # Subsample for KDE speed if dataset is very large
    if len(X) > 50_000:
        idx = rng.choice(len(X), 50_000, replace=False)
        X_kde = X[idx]
    else:
        X_kde = X
    kde = gaussian_kde(X_kde.T, bw_method="scott")

    # --- Scatter-diagram bins as proposal candidates ---
    grid_pts, freqs = build_scatter_bins(df)
    sin_g, cos_g = circular_encode(grid_pts[:, 2])
    X_grid = np.column_stack([grid_pts[:, 0], grid_pts[:, 1], sin_g, cos_g])
    proposal_density = kde(X_grid.T)
    proposal_density = np.maximum(proposal_density, 1e-12)

    # Importance weights: proportional to occurrence / proposal density
    weights = freqs / proposal_density
    weights /= weights.sum()

    n_main    = int(n_samples * (1 - extreme_frac))
    n_extreme = n_samples - n_main

    # Main importance-weighted draw from scatter bins
    chosen_bins = rng.choice(len(grid_pts), size=n_main, replace=True, p=weights)
    main_pts    = grid_pts[chosen_bins]

    # Jitter within bin widths (half-bin size)
    bin_half = np.array([
        (df["Hs"].max()  - df["Hs"].min())  / (2 * 20),
        (df["Tp"].max()  - df["Tp"].min())  / (2 * 20),
        (df["Dir"].max() - df["Dir"].min()) / (2 * 12),
    ])
    main_pts += rng.uniform(-bin_half, bin_half, main_pts.shape)

    # --- Extreme supplement ---
    hs_99 = np.percentile(df["Hs"].values, 99)
    extreme_mask = df["Hs"].values >= hs_99
    extreme_pool = df[extreme_mask][["Hs", "Tp", "Dir"]].values
    extreme_idx  = rng.choice(len(extreme_pool), size=n_extreme, replace=True)
    extreme_pts  = extreme_pool[extreme_idx]

    all_pts = np.vstack([main_pts, extreme_pts])

    # Re-compute occurrence weight for each sampled state via KDE
    sin_a, cos_a = circular_encode(all_pts[:, 2])
    X_all = np.column_stack([all_pts[:, 0], all_pts[:, 1], sin_a, cos_a])
    occurrence_weight = kde(X_all.T)
    occurrence_weight /= occurrence_weight.sum()

    result = pd.DataFrame({
        "sea_state_id":  np.arange(len(all_pts)),
        "Hs":            all_pts[:, 0],
        "Tp":            all_pts[:, 1],
        "Dir":           all_pts[:, 2],
        "weight":        occurrence_weight,
        "source":        ["importance"] * n_main + ["extreme"] * n_extreme,
    })
    result = result.clip(lower={"Hs": 0.01, "Tp": 1.0})
    return result


def diagnostics(df_raw: pd.DataFrame, df_sampled: pd.DataFrame, out_dir: Path):
    """Save a CSV summary of coverage statistics."""
    stats = {}
    for col in ["Hs", "Tp", "Dir"]:
        for fn, label in [(np.min, "min"), (np.max, "max"), (np.mean, "mean"), (np.std, "std")]:
            stats[f"{col}_{label}_raw"]     = fn(df_raw[col].values)
            stats[f"{col}_{label}_sampled"] = fn(df_sampled[col].values)
    pd.DataFrame([stats]).to_csv(out_dir / "sea_states_coverage_stats.csv", index=False)
    log.info("Coverage diagnostics saved.")


def main():
    parser = argparse.ArgumentParser(description="Sea-state importance sampling")
    parser.add_argument("--problem",   default="config/problem.yaml")
    parser.add_argument("--paths",     default="config/paths.yaml")
    parser.add_argument("--n_samples", type=int, default=None,
                        help="Override number of sea states to sample")
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    rng = np.random.default_rng(cfg["training"]["random_seed"])

    csv_path  = Path(pths["scatter_csv"])
    out_dir   = Path(pths["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    df_raw = load_wave_data(csv_path)

    # Default n_samples: one sea state per layout (total_target in problem.yaml)
    n_ss = args.n_samples or cfg["layouts"]["total_target"]
    log.info("Sampling %d sea states …", n_ss)

    df_sampled = importance_sample(df_raw, n_samples=n_ss, rng=rng)

    out_path = out_dir / "sea_states.parquet"
    df_sampled.to_parquet(out_path, index=False)
    log.info("Saved %d sea states to %s", len(df_sampled), out_path)

    diagnostics(df_raw, df_sampled, out_dir)


if __name__ == "__main__":
    main()
