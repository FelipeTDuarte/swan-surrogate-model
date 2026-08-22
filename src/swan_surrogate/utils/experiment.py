"""experiment.py
Experiment tracking for the swan-surrogate pipeline.

Design contract
---------------
* ``start_new_experiment`` is called **once**, by the pipeline entry-point
  (01_layout_generator.py).  It resolves a unique, non-destructive slug,
  creates the four mirrored experiment sub-directories, and writes a lock
  file to ``.experiments/current.json``.

* ``load_current_experiment`` is called by every downstream script (02-10).
  It reads the lock file and returns an ``ExperimentPaths`` object so every
  stage writes to the same experiment folder set — no suffix drift.

Slug format
-----------
    YYYY-MM-DD_<problem_id>          # base, no suffix
    YYYY-MM-DD_<problem_id>(1)       # first collision
    YYYY-MM-DD_<problem_id>(2)       # second collision, etc.

Collision logic
---------------
A slug is considered "colliding" when it already exists as a sub-directory
in **any** of the four base directories (runs/, data/processed/, reports/,
models/).  The same suffix is applied to all four simultaneously, so the
mirroring is always 1-to-1 — even if only one base dir has a conflict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

from .paths import ProjectPaths


# ---------------------------------------------------------------------------
# Public dataclass returned to callers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExperimentPaths:
    """Typed paths for a single experiment, resolved from the lock file."""

    slug: str
    """Full experiment slug, e.g. '2026-08-22_esposende_foz'."""

    runs: Path
    """runs/<slug> — temporary SWAN execution trees live here."""

    processed: Path
    """data/processed/<slug> — parquet outputs, dataset.parquet."""

    reports: Path
    """reports/<slug> — training metrics, validation figures, logs."""

    models: Path
    """models/<slug> — best_model.pt, last_model.pt, exported bundle."""

    def ensure_all(self) -> "ExperimentPaths":
        """Create all four directories if they do not exist yet."""
        for p in (self.runs, self.processed, self.reports, self.models):
            p.mkdir(parents=True, exist_ok=True)
        return self


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LOCK_DIR = ".experiments"
_LOCK_FILE = "current.json"


def _lock_file(root: Path) -> Path:
    return root / _LOCK_DIR / _LOCK_FILE


def _base_slug(problem_id: str, run_date: str | None = None) -> str:
    """Return the un-suffixed slug: YYYY-MM-DD_problem_id."""
    date_str = run_date or _date.today().isoformat()
    return f"{date_str}_{problem_id}"


def _collides(slug: str, pths: ProjectPaths) -> bool:
    """True when *slug* already exists under ANY of the four base dirs."""
    candidates = [
        pths.runs / slug,
        pths.processed / slug,
        pths.reports / slug,
        pths.models / slug,
    ]
    return any(c.exists() for c in candidates)


def _resolve_slug(problem_id: str, pths: ProjectPaths,
                  run_date: str | None = None) -> str:
    """Return the first non-colliding slug, appending (1),(2)…(n) as needed."""
    base = _base_slug(problem_id, run_date)
    if not _collides(base, pths):
        return base
    n = 1
    while _collides(f"{base}({n})", pths):
        n += 1
    return f"{base}({n})"


def _build_experiment_paths(slug: str, pths: ProjectPaths) -> ExperimentPaths:
    return ExperimentPaths(
        slug=slug,
        runs=pths.runs / slug,
        processed=pths.processed / slug,
        reports=pths.reports / slug,
        models=pths.models / slug,
    )


def _write_lock(root: Path, exp: ExperimentPaths) -> None:
    lock_dir = root / _LOCK_DIR
    lock_dir.mkdir(exist_ok=True)
    payload = {
        "experiment_slug": exp.slug,
        "paths": {
            "runs": str(exp.runs),
            "processed": str(exp.processed),
            "reports": str(exp.reports),
            "models": str(exp.models),
        },
    }
    _lock_file(root).write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_new_experiment(
    pths: ProjectPaths,
    problem_id: str,
    run_date: str | None = None,
) -> ExperimentPaths:
    """Resolve a fresh, collision-safe experiment slug and create all dirs.

    Called **only** by the pipeline entry-point (01_layout_generator.py).
    Writes ``.experiments/current.json`` so downstream scripts can reuse
    the same slug via :func:`load_current_experiment`.

    Parameters
    ----------
    pths:
        ``ProjectPaths`` instance from :func:`~swan_surrogate.utils.paths.get_paths`.
    problem_id:
        Value of ``problem_id`` read from ``config/problem.yaml``.
    run_date:
        ISO date string ``YYYY-MM-DD``.  Defaults to today.

    Returns
    -------
    ExperimentPaths
        Fully populated and already created on disk.
    """
    slug = _resolve_slug(problem_id, pths, run_date)
    exp = _build_experiment_paths(slug, pths)
    exp.ensure_all()
    _write_lock(pths.root, exp)
    return exp


def load_current_experiment(pths: ProjectPaths) -> ExperimentPaths:
    """Load the experiment started by the most recent call to
    :func:`start_new_experiment`.

    Called by every script **after** 01 in the pipeline (02 through 10).
    Uses the lock file written by ``start_new_experiment`` so all stages
    share the same experiment folder set — no slug re-resolution happens
    here, preventing the suffix-drift bug.

    Raises
    ------
    FileNotFoundError
        If ``.experiments/current.json`` does not exist, meaning
        ``01_layout_generator.py`` has not been run yet.
    """
    lf = _lock_file(pths.root)
    if not lf.exists():
        raise FileNotFoundError(
            f"No active experiment lock found at '{lf}'.\n"
            "Run 01_layout_generator.py first to start a new experiment."
        )
    data = json.loads(lf.read_text())
    slug = data["experiment_slug"]
    p = data["paths"]
    return ExperimentPaths(
        slug=slug,
        runs=Path(p["runs"]),
        processed=Path(p["processed"]),
        reports=Path(p["reports"]),
        models=Path(p["models"]),
    )


def reuse_experiment(
    pths: ProjectPaths,
    experiment_slug: str,
) -> ExperimentPaths:
    """Pin the current experiment to an *existing* slug from a past run.

    Use this when you want scripts 02-10 to write into a previously created
    experiment (e.g. to reuse layouts from surrogate_1 with new sea states).
    Overwrites the lock file with the given slug.

    Parameters
    ----------
    pths:
        ``ProjectPaths`` from :func:`~swan_surrogate.utils.paths.get_paths`.
    experiment_slug:
        Full slug of an existing experiment,
        e.g. ``'2026-08-22_esposende_foz'``.

    Raises
    ------
    FileNotFoundError
        If the slug does not correspond to an existing directory in at least
        one of the four base dirs (basic sanity check).
    """
    exp = _build_experiment_paths(experiment_slug, pths)
    existing = [p for p in (exp.runs, exp.processed, exp.reports, exp.models)
                if p.exists()]
    if not existing:
        raise FileNotFoundError(
            f"Experiment slug '{experiment_slug}' was not found under any of "
            "runs/, data/processed/, reports/, or models/. "
            "Check the slug spelling."
        )
    exp.ensure_all()   # create any dirs that were missing (e.g. models/ not yet created)
    _write_lock(pths.root, exp)
    return exp
