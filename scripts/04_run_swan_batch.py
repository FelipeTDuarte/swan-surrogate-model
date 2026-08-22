"""
04_run_swan_batch.py
Run SNL-SWAN for each prepared run directory using a temporary execution
folder so that SWAN resolves grid / bottom / polygon files by relative name.

Strategy per run
----------------
1. Create a TemporaryDirectory (deleted automatically at exit).
2. Copy INPUT.swn + meta.json from the run_dir into the temp dir.
3. Copy all static support files (grid_file, bottom_file, swanrun if a real
   file, deployment_polygon_file, power_file) into the temp dir.
4. Execute `swan_executable INPUT.swn` with cwd=tmp_dir.
5. Copy back only the desired output patterns to exp.runs/<run_id>/.

This avoids duplicating large grid/bottom files into every run directory
while guaranteeing that SWAN finds them by the relative names written in
the INPUT deck by 03_build_swan_inputs.py.

Features
--------
- Parallel execution via ProcessPoolExecutor (--workers)
- Retry logic (--max_attempts, default 3)
- Progress logged every 10 %
- run_status.parquet written to exp.processed
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import tempfile
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
)
log = logging.getLogger(__name__)

TIMEOUT_S = 3600  # 1 h per run


# ──────────────────────────────────────────────────────────────────────────────
# Static-file resolution
# ──────────────────────────────────────────────────────────────────────────────

def resolve_static_files(pths: dict) -> list[Path]:
    """
    Collect all support files that must be present in the SWAN temp dir.

    Reads the following keys from paths.yaml (all optional except grid/bottom):
      grid_file               required — curvilinear or regular grid
      bottom_file             required — bathymetry
      swan_executable         copied only when it is an actual file path
                              (not just a bare command name like 'swanrun')
      deployment_polygon_file optional — SNL-SWAN .pol area file
      power_file              optional — SNL-SWAN power matrix (power.txt)
    """
    files: list[Path] = []

    for key in ("grid_file", "bottom_file"):
        p = Path(pths[key])
        if not p.is_file():
            raise FileNotFoundError(
                f"paths.yaml key '{key}' points to a missing file: {p}"
            )
        files.append(p)

    exec_path = Path(pths["swan_executable"])
    if exec_path.is_file():
        files.append(exec_path)

    for key in ("deployment_polygon_file", "power_file"):
        val = pths.get(key)
        if val:
            p = Path(val)
            if p.is_file():
                files.append(p)
            else:
                log.warning("Optional static file not found, skipping: %s (%s)", key, p)

    return files


# ──────────────────────────────────────────────────────────────────────────────
# Single-run execution
# ──────────────────────────────────────────────────────────────────────────────

def run_one_case(
    run_dir: Path,
    static_files: list[Path],
    swan_exec: str,
    keep_patterns: list[str],
    output_dir: Path,
    timeout: int = TIMEOUT_S,
) -> dict:
    """
    Execute one SWAN run inside a temporary directory.

    Returns a status dict: {run_id, status, wall_time_s, returncode}.
    """
    with tempfile.TemporaryDirectory(prefix="swanrun_") as tmp:
        tmp_dir = Path(tmp)

        # Copy INPUT deck + meta into temp dir
        for f in run_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, tmp_dir / f.name)

        # Copy static support files (grid, bottom, pol, power.txt, swanrun)
        for f in static_files:
            shutil.copy2(f, tmp_dir / f.name)

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                [swan_exec, "INPUT.swn"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            wall = round(time.perf_counter() - t0, 2)
            status = "ok" if proc.returncode == 0 else "failed"
            returncode = proc.returncode
            if status == "failed":
                (run_dir / "stderr.log").write_text(proc.stderr[-2000:], encoding="utf-8")
                log.warning("SWAN failed in %s (rc=%d):\n%s",
                             run_dir.name, returncode, proc.stderr[-400:])
        except subprocess.TimeoutExpired:
            wall = timeout
            status = "timeout"
            returncode = -1
        except Exception as exc:
            wall = round(time.perf_counter() - t0, 2)
            status = f"error:{exc}"
            returncode = -2

        # Copy back desired outputs to permanent run_dir
        for pattern in keep_patterns:
            for match in tmp_dir.glob(pattern):
                shutil.copy2(match, run_dir / match.name)

        # tmp_dir deleted automatically when `with` block exits

    return {"run_id": run_dir.name, "status": status,
            "wall_time_s": wall, "returncode": returncode}


def run_with_retry(
    run_dir: Path,
    static_files: list[Path],
    swan_exec: str,
    keep_patterns: list[str],
    output_dir: Path,
    max_attempts: int = 3,
) -> dict:
    """Wrap run_one_case with retry logic."""
    for attempt in range(1, max_attempts + 1):
        res = run_one_case(run_dir, static_files, swan_exec, keep_patterns, output_dir)
        if res["status"] == "ok":
            return res
        if attempt < max_attempts:
            log.warning("  Retry %d/%d for %s", attempt + 1, max_attempts, run_dir.name)
    return res


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run SNL-SWAN batch with temp-dir isolation")
    parser.add_argument("--problem",      default="config/problem.yaml")
    parser.add_argument("--paths",        default="config/paths.yaml")
    parser.add_argument("--workers",      type=int, default=None,
                        help="Number of parallel workers (default: n_workers from problem.yaml)")
    parser.add_argument("--max_attempts", type=int, default=3)
    parser.add_argument("--rerun_failed", action="store_true")
    parser.add_argument("--dry_run",      action="store_true")
    parser.add_argument(
        "--keep_outputs", nargs="+",
        default=["*Hs.mat", "*Tm01.mat", "*Dir.mat", "PRINT"],
        help="Glob patterns of files to copy back from temp dir after each run",
    )
    args = parser.parse_args()

    cfg      = yaml.safe_load(Path(args.problem).read_text())
    pths_cfg = yaml.safe_load(Path(args.paths).read_text())

    # ── Experiment tracking ──
    exp = load_current_experiment(get_paths())
    log.info("Experiment: %s", exp.slug)

    par_cfg   = cfg.get("parallelization", {})
    n_workers = args.workers if args.workers is not None else int(par_cfg.get("n_workers", 1))
    swan_exec = pths_cfg["swan_executable"]

    runs_dir  = exp.runs
    processed = exp.processed
    logs_dir  = exp.reports
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Attach file handler for persistent batch log
    fh = logging.FileHandler(logs_dir / "swan_batch.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(fh)

    static_files = resolve_static_files(pths_cfg)
    log.info("Static support files: %s", [str(f) for f in static_files])

    status_path = processed / "run_status.parquet"
    existing_ok: set[str] = set()
    if args.rerun_failed and status_path.exists():
        df_prev = pd.read_parquet(status_path)
        existing_ok = set(df_prev[df_prev["status"] == "ok"]["run_id"])

    run_dirs = sorted(
        p for p in runs_dir.iterdir()
        if p.is_dir() and (p / "INPUT.swn").exists()
    )
    if args.rerun_failed:
        run_dirs = [d for d in run_dirs if d.name not in existing_ok]

    log.info("Runs to execute: %d  (workers=%d)", len(run_dirs), n_workers)

    if args.dry_run:
        for d in run_dirs[:10]:
            log.info("  [dry_run] %s", d.name)
        return

    total   = len(run_dirs)
    results: list[dict] = []
    log_interval = max(1, total // 10)

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                run_with_retry,
                d, static_files, swan_exec,
                args.keep_outputs, runs_dir,
                args.max_attempts,
            ): d
            for d in run_dirs
        }
        for i, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            results.append(res)
            if i % log_interval == 0 or i == total:
                n_ok = sum(1 for r in results if r["status"] == "ok")
                log.info("Progress %d/%d  ok=%d", i, total, n_ok)

    df_new = pd.DataFrame(results)

    if args.rerun_failed and status_path.exists():
        df_old = pd.read_parquet(status_path)
        df_all = pd.concat(
            [df_old[df_old["run_id"].isin(existing_ok)], df_new],
            ignore_index=True,
        )
    else:
        df_all = df_new

    df_all.to_parquet(status_path, index=False)
    n_ok  = (df_all["status"] == "ok").sum()
    n_bad = len(df_all) - n_ok
    log.info("Batch complete: %d ok  %d failed/other  -> %s", n_ok, n_bad, status_path)


if __name__ == "__main__":
    main()
