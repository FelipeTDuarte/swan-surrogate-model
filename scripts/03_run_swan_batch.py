"""
03_run_swan_batch.py — CLI entry point for the surrogate pipeline.
See docs/blueprints/ for the full specification.
"""
import click
from src.utils.logging import get_logger

log = get_logger(__name__)


@click.command()
@click.option("--config", default="config/problem.yaml", help="Problem config file.")
@click.option("--paths", default="config/paths.yaml", help="Paths config file.")
@click.option("--mode", default="B", type=click.Choice(["B", "C", "both"]), help="Surrogate mode.")
def main(config: str, paths: str, mode: str) -> None:
    """Run stage: 03_run_swan_batch.py"""
    log.info("Starting 03_run_swan_batch.py | mode=%s | config=%s | paths=%s", mode, config, paths)
    raise NotImplementedError("Not yet implemented — see docs/blueprints/BLUEPRINT_03_RUN.md")


if __name__ == "__main__":
    main()
