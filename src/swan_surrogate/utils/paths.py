from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    config: Path
    data: Path
    raw: Path
    processed: Path
    archive: Path

    runs: Path
    models: Path
    models_exported: Path
    models_splits: Path

    reports: Path
    logs: Path
    train_curves: Path
    validation_plots: Path

    src: Path
    tests: Path
    notebooks: Path
    scripts: Path
    docs: Path
    blueprints: Path

    @property
    def problem_yaml(self) -> Path:
        return self.config / "problem.yaml"

    @property
    def paths_yaml(self) -> Path:
        return self.config / "paths.yaml"

    def in_root(self, *parts: str | Path) -> Path:
        return self.root.joinpath(*map(Path, parts))

    def in_config(self, *parts: str | Path) -> Path:
        return self.config.joinpath(*map(Path, parts))

    def in_data(self, *parts: str | Path) -> Path:
        return self.data.joinpath(*map(Path, parts))

    def in_raw(self, *parts: str | Path) -> Path:
        return self.raw.joinpath(*map(Path, parts))

    def in_processed(self, *parts: str | Path) -> Path:
        return self.processed.joinpath(*map(Path, parts))

    def in_archive(self, *parts: str | Path) -> Path:
        return self.archive.joinpath(*map(Path, parts))

    def in_runs(self, *parts: str | Path) -> Path:
        return self.runs.joinpath(*map(Path, parts))

    def in_models(self, *parts: str | Path) -> Path:
        return self.models.joinpath(*map(Path, parts))

    def in_reports(self, *parts: str | Path) -> Path:
        return self.reports.joinpath(*map(Path, parts))

    def in_src(self, *parts: str | Path) -> Path:
        return self.src.joinpath(*map(Path, parts))

    def in_tests(self, *parts: str | Path) -> Path:
        return self.tests.joinpath(*map(Path, parts))

    def in_notebooks(self, *parts: str | Path) -> Path:
        return self.notebooks.joinpath(*map(Path, parts))

    def in_scripts(self, *parts: str | Path) -> Path:
        return self.scripts.joinpath(*map(Path, parts))

    def ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path


def find_repo_root(
    start: Path | None = None,
    markers: tuple[str, ...] = ("config", "data", "src"),
) -> Path:
    p = Path(start).resolve() if start else Path.cwd().resolve()

    for candidate in (p, *p.parents):
        if all((candidate / m).exists() for m in markers):
            return candidate

    raise FileNotFoundError(
        f"Could not find repository root from {p}. Expected markers: {markers}"
    )


def get_paths(start: Path | None = None) -> ProjectPaths:
    root = find_repo_root(start=start)

    config = root / "config"
    data = root / "data"
    raw = data / "raw"
    processed = data / "processed"
    archive = data / "archive"

    runs = root / "runs"

    models = root / "models"
    models_exported = models / "exported"
    models_splits = models / "splits"

    reports = root / "reports"
    logs = reports / "logs"
    train_curves = reports / "train_curves"
    validation_plots = reports / "validation_plots"

    src = root / "src"
    tests = root / "tests"
    notebooks = root / "notebooks"
    scripts = root / "scripts"
    docs = root / "docs"
    blueprints = docs / "blueprints"

    return ProjectPaths(
        root=root,
        config=config,
        data=data,
        raw=raw,
        processed=processed,
        archive=archive,
        runs=runs,
        models=models,
        models_exported=models_exported,
        models_splits=models_splits,
        reports=reports,
        logs=logs,
        train_curves=train_curves,
        validation_plots=validation_plots,
        src=src,
        tests=tests,
        notebooks=notebooks,
        scripts=scripts,
        docs=docs,
        blueprints=blueprints,
    )