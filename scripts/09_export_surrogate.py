"""
09_export_surrogate.py
Export the trained PyTorch surrogate to TorchScript and ONNX.

Outputs
-------
- models/<experiment>/surrogate_<problem_id>.pt      (TorchScript)
- models/<experiment>/surrogate_<problem_id>.onnx    (ONNX opset 17)
- models/<experiment>/surrogate_metadata.json        (input/output specs)
"""

import argparse
import json
import logging
from pathlib import Path

import torch
import yaml

from swan_surrogate.training import FNOSurrogate
from swan_surrogate.utils import load_current_experiment
from swan_surrogate.utils.paths import get_paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Export surrogate to TorchScript & ONNX")
    parser.add_argument("--problem",    default="config/problem.yaml")
    parser.add_argument("--paths",      default="config/paths.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--grid_h",     type=int, default=64)
    parser.add_argument("--grid_w",     type=int, default=64)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.problem).read_text())

    # ── Experiment tracking ──
    exp = load_current_experiment(get_paths())
    log.info("Experiment: %s", exp.slug)

    models_dir = exp.models
    models_dir.mkdir(parents=True, exist_ok=True)

    ckpt_path = Path(args.checkpoint) if args.checkpoint else models_dir / "best_model.pt"
    ckpt      = torch.load(ckpt_path, map_location="cpu")
    model     = FNOSurrogate(in_channels=4, n_targets=4,
                              grid_h=args.grid_h, grid_w=args.grid_w)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    dummy      = torch.randn(1, 4, args.grid_h, args.grid_w)
    problem_id = cfg["problem_id"]

    ts_path  = models_dir / f"surrogate_{problem_id}.pt"
    scripted = torch.jit.trace(model, dummy)
    scripted.save(str(ts_path))
    log.info("TorchScript saved → %s", ts_path)

    onnx_path = models_dir / f"surrogate_{problem_id}.onnx"
    torch.onnx.export(
        model, dummy, str(onnx_path),
        input_names=["layout_sea_state"],
        output_names=["p_total_norm", "hra_aoi_1_norm", "hra_aoi_2_norm", "hra_aoi_3_norm"],
        dynamic_axes={"layout_sea_state": {0: "batch_size"}},
        opset_version=17,
    )
    log.info("ONNX saved → %s", onnx_path)

    meta = {
        "problem_id":  problem_id,
        "experiment_slug": exp.slug,
        "n_wecs":      cfg["n_wecs"],
        "wec_type":    cfg["wec_type"],
        "input_shape": [1, 4, args.grid_h, args.grid_w],
        "input_channels": {
            "0": "layout_density_map",
            "1": "Hs_broadcast",
            "2": "Tp_broadcast",
            "3": "Dir_broadcast",
        },
        "outputs": ["p_total_norm", "hra_aoi_1_norm", "hra_aoi_2_norm", "hra_aoi_3_norm"],
        "fitness_bounds": cfg["fitness"],
        "checkpoint_epoch": ckpt.get("epoch"),
        "val_loss": ckpt.get("val_loss"),
    }
    (models_dir / "surrogate_metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    log.info("Metadata saved → %s", models_dir / "surrogate_metadata.json")


if __name__ == "__main__":
    main()
