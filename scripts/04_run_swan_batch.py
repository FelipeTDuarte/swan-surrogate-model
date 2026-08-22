"""
04_run_swan_batch.py
Execute SNL-SWAN for every run folder produced by 03_build_swan_inputs.py.

Features
--------
- Parallel execution via concurrent.futures.ProcessPoolExecutor
- Retry logic (up to 3 attempts per run)
- Progress logging to reports/<experiment>/swan_batch.log
- Writes a status parquet: data/processed/<experiment>/run_status.parquet
  columns: run_id, status (ok|failed|skipped), wall_time_s, attempts
"""

import argparse
import logging
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import yaml

from swan_surrogate.utils import load_current_experiment
from swan_surrogate.utils.paths import get_paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(stream=open("/dev/stdout", "w", encoding="utf-8"))],
)
log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
TIMEOUT_S    = 3600  # 1 hour per run


def run_one(run_dir: Path, swan_exec: str, n_threads: int, attempt: int = 1) -> dict:
    t0 = time.perf_counter()
    result = dict(run_id=run_dir.name, status="failed", wall_time_s=0.0, attempts=attempt)
    try:
        cmd = [swan_exec, "-input", "INPUT.swn"]
        if n_threads > 1:
            cmd += ["-omp", str(n_threads)]
        proc = subprocess.run(
            cmd,
            cwd=run_dir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
        wall = time.perf_counter() - t0
        result["wall_time_s"] = round(wall, 2)
        if proc.returncode == 0:
            result["status"] = "ok"
        else:
            (run_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")
            result["status"] = "failed"
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["wall_time_s"] = TIMEOUT_S
    except Exception as exc:
        result["status"] = f"error:{exc}"
    return result

def run_with_retry(run_dir: Path, swan_exec: str, n_threads: int) -> dict:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        res = run_one(run_dir, swan_exec, n_threads, attempt)
        if res["status"] == "ok":
            return res
        if attempt < MAX_ATTEMPTS:
            log.warning("  Retry %d/%d for %s", attempt + 1, MAX_ATTEMPTS, run_dir.name)
    return res

def main():
    parser = argparse.ArgumentParser(description="Run SNL-SWAN batch")
    parser.add_argument("--problem",  default="config/problem.yaml")
    parser.add_argument("--paths",    default="config/paths.yaml")
    parser.add_argument("--workers",  type=int, default=None)
    parser.add_argument("--threads",  type=int, default=None)
    parser.add_argument("--rerun_failed", action="store_true")
    parser.add_argument("--dry_run",  action="store_true")
    args = parser.parse_args()

    cfg      = yaml.safe_load(Path(args.problem).read_text())
    pths_cfg = yaml.safe_load(Path(args.paths).read_text())

    # ── Experiment tracking ──
    exp = load_current_experiment(get_paths())
    log.info("Experiment: %s", exp.slug)

    par_cfg   = cfg.get("parallelization", {})
    n_workers = args.workers if args.workers is not None else int(par_cfg.get("n_workers", 1))
    n_threads = args.threads if args.threads is not None else int(par_cfg.get("n_threads_per_worker", 1))

    runs_dir  = exp.runs
    processed = exp.processed
    logs_dir  = exp.reports
    logs_dir.mkdir(parents=True, exist_ok=True)
    swan_exec = str(Path(pths_cfg["swan_executable"]).resolve())

    fh = logging.FileHandler(logs_dir / "swan_batch.log")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)

    status_path = processed / "run_status.parquet"
    existing_ok = set()
    if args.rerun_failed and status_path.exists():
        df_status = pd.read_parquet(status_path)
        existing_ok = set(df_status[df_status["status"] == "ok"]["run_id"])

    run_dirs = sorted(p for p in runs_dir.iterdir()
                      if p.is_dir() and (p / "INPUT").exists())
    if args.rerun_failed:
        run_dirs = [d for d in run_dirs if d.name not in existing_ok]

    log.info("Total runs to execute: %d  (workers=%d) (threads=%d)", len(run_dirs), n_workers, n_threads)

    if args.dry_run:
        for d in run_dirs[:10]:
            log.info("  [dry] %s", d.name)
        return

    results = []
    completed = 0
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(run_with_retry, d, swan_exec, n_threads): d for d in run_dirs}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            completed += 1
            if 100 * completed % len(run_dirs) == 0:
                n_ok = sum(1 for r in results if r["status"] == "ok")
                log.info("Progress: %d / %d   ok=%d", completed, len(run_dirs), n_ok)

    df_new = pd.DataFrame(results)

    if args.rerun_failed and status_path.exists():
        df_old = pd.read_parquet(status_path)
        df_all = pd.concat([df_old[df_old["run_id"].isin(existing_ok)], df_new])
    else:
        df_all = df_new

    df_all.to_parquet(status_path, index=False)
    n_ok  = (df_all["status"] == "ok").sum()
    n_bad = len(df_all) - n_ok
    log.info("Batch complete: %d ok  %d failed/other  -> %s", n_ok, n_bad, status_path)


if __name__ == "__main__":
    main()
