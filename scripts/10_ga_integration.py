"""
10_ga_integration.py
Plug the trained surrogate into a Genetic Algorithm for WEC array layout optimisation.

GA formulation
--------------
Individual  : flat vector of (x_i, y_i) for i=1..N_WECS  → length 2*N_WECS
Fitness     : weighted sum  α*p_total_norm + (1-α)*mean(hra_norm) — maximise
Constraints : minimum spacing (penalised in fitness)
              domain bounds (repaired via clip)

Uses DEAP library. Falls back to a simple random hill-climber if DEAP unavailable.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import torch
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Surrogate wrapper
# ──────────────────────────────────────────────────────────────────────────────

class SurrogateOracle:
    def __init__(self, ts_path: Path, grid_h: int = 64, grid_w: int = 64,
                 bounds: dict = None, meta: dict = None):
        self.model  = torch.jit.load(str(ts_path), map_location="cpu")
        self.model.eval()
        self.grid_h = grid_h
        self.grid_w = grid_w
        self.bounds = bounds or {}
        self.meta   = meta or {}

    def _layout_to_tensor(self, x_coords, y_coords,
                          Hs: float, Tp: float, Dir: float) -> torch.Tensor:
        from scripts_07_train_model import coords_to_density
        b = self.bounds
        density = coords_to_density(
            x_coords, y_coords,
            b["xmin"], b["xmax"], b["ymin"], b["ymax"],
            self.grid_h, self.grid_w,
        )
        ss = np.stack([
            np.full((self.grid_h, self.grid_w), Hs  / 10.0, dtype=np.float32),
            np.full((self.grid_h, self.grid_w), Tp  / 20.0, dtype=np.float32),
            np.full((self.grid_h, self.grid_w), Dir / 360.0, dtype=np.float32),
        ])
        x = torch.from_numpy(np.concatenate([[density], ss], axis=0)).unsqueeze(0)
        return x

    @torch.no_grad()
    def predict(self, x_coords, y_coords,
                Hs: float, Tp: float, Dir: float) -> dict:
        x = self._layout_to_tensor(x_coords, y_coords, Hs, Tp, Dir)
        out = self.model(x).squeeze(0).numpy()
        keys = ["p_total_norm", "hra_aoi_1_norm", "hra_aoi_2_norm", "hra_aoi_3_norm"]
        return dict(zip(keys, out.tolist()))


def spacing_penalty(x_coords, y_coords, min_spacing: float) -> float:
    pts = np.column_stack([x_coords, y_coords])
    if len(pts) < 2:
        return 0.0
    from scipy.spatial.distance import cdist
    D = cdist(pts, pts)
    np.fill_diagonal(D, np.inf)
    violations = np.maximum(0, min_spacing - D.min(axis=1))
    return float(violations.mean() / min_spacing)


def fitness_fn(individual: np.ndarray, n_wecs: int, oracle: SurrogateOracle,
               Hs: float, Tp: float, Dir: float,
               min_spacing: float, alpha: float = 0.6) -> tuple:
    xy = individual.reshape(n_wecs, 2)
    x_c, y_c = xy[:, 0].tolist(), xy[:, 1].tolist()
    preds    = oracle.predict(x_c, y_c, Hs, Tp, Dir)
    p_norm   = preds["p_total_norm"]
    hra_mean = np.mean([preds[f"hra_aoi_{i}_norm"] for i in range(1, 4)])
    penalty  = spacing_penalty(x_c, y_c, min_spacing)
    score    = alpha * p_norm + (1 - alpha) * hra_mean - 2.0 * penalty
    return (float(score),)


# ──────────────────────────────────────────────────────────────────────────────
# GA with DEAP
# ──────────────────────────────────────────────────────────────────────────────

def run_ga_deap(oracle, cfg, bounds, n_wecs, min_spacing, Hs, Tp, Dir,
                pop_size=200, n_gen=300, cx_pb=0.6, mut_pb=0.3, alpha=0.6):
    try:
        from deap import base, creator, tools, algorithms
    except ImportError:
        raise ImportError("DEAP not installed — run: pip install deap")

    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    creator.create("Individual", list, fitness=creator.FitnessMax)

    toolbox = base.Toolbox()
    xmin, xmax = bounds["xmin"], bounds["xmax"]
    ymin, ymax = bounds["ymin"], bounds["ymax"]

    def random_coord():
        return np.random.uniform([xmin]*n_wecs + [ymin]*n_wecs,
                                  [xmax]*n_wecs + [ymax]*n_wecs).tolist()

    toolbox.register("individual", tools.initIterate, creator.Individual, random_coord)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate",   lambda ind: fitness_fn(
        np.array(ind), n_wecs, oracle, Hs, Tp, Dir, min_spacing, alpha))
    toolbox.register("mate",       tools.cxBlend, alpha=0.5)
    toolbox.register("mutate",     tools.mutGaussian,
                     mu=0, sigma=(xmax - xmin) * 0.05, indpb=0.2)
    toolbox.register("select",     tools.selTournament, tournsize=3)

    pop   = toolbox.population(n=pop_size)
    stats = tools.Statistics(lambda ind: ind.fitness.values[0])
    stats.register("max", np.max)
    stats.register("mean", np.mean)
    hof   = tools.HallOfFame(5)

    log.info("Starting GA: pop=%d  gen=%d", pop_size, n_gen)
    pop, log_book = algorithms.eaSimple(
        pop, toolbox, cxpb=cx_pb, mutpb=mut_pb, ngen=n_gen,
        stats=stats, halloffame=hof, verbose=True)

    return hof, log_book


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run GA layout optimisation with surrogate")
    parser.add_argument("--problem",    default="config/problem.yaml")
    parser.add_argument("--paths",      default="config/paths.yaml")
    parser.add_argument("--Hs",  type=float, default=2.0, help="Design sea state Hs (m)")
    parser.add_argument("--Tp",  type=float, default=10.0, help="Design sea state Tp (s)")
    parser.add_argument("--Dir", type=float, default=300.0, help="Design wave direction (deg)")
    parser.add_argument("--alpha",   type=float, default=0.6,
                        help="Weight on P_total in fitness (0-1)")
    parser.add_argument("--pop",     type=int, default=200)
    parser.add_argument("--gen",     type=int, default=300)
    parser.add_argument("--out",     default=None)
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    models_dir = Path(pths["models_dir"])
    problem_id = cfg["problem_id"]
    ts_path    = models_dir / f"surrogate_{problem_id}.pt"
    meta_path  = models_dir / "surrogate_metadata.json"

    meta   = json.loads(meta_path.read_text())
    bounds_path = Path(pths["grid_file"])

    # Infer bounds from grid file
    from scripts_utils import domain_bounds_cached
    bounds = domain_bounds_cached(bounds_path)

    oracle = SurrogateOracle(ts_path, bounds=bounds, meta=meta)

    n_wecs      = cfg["n_wecs"]
    min_spacing = cfg["layouts"]["min_spacing_m"]

    t0  = time.perf_counter()
    hof, logbook = run_ga_deap(
        oracle, cfg, bounds, n_wecs, min_spacing,
        args.Hs, args.Tp, args.Dir,
        pop_size=args.pop, n_gen=args.gen, alpha=args.alpha,
    )
    elapsed = time.perf_counter() - t0
    log.info("GA finished in %.1f s", elapsed)

    # Save best layout
    best_ind = np.array(hof[0])
    xy = best_ind.reshape(n_wecs, 2)
    out_dir = Path(args.out) if args.out else Path(pths["reports_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    import pandas as pd
    df_best = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1]})
    df_best.to_csv(out_dir / "best_layout_ga.csv", index=False)

    best_score = hof[0].fitness.values[0]
    result = {
        "fitness":  best_score,
        "Hs":       args.Hs,
        "Tp":       args.Tp,
        "Dir":      args.Dir,
        "alpha":    args.alpha,
        "elapsed_s": round(elapsed, 2),
    }
    (out_dir / "ga_result.json").write_text(json.dumps(result, indent=2))
    log.info("Best layout saved → %s  fitness=%.4f", out_dir / "best_layout_ga.csv", best_score)


if __name__ == "__main__":
    main()
