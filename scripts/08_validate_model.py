"""
08_validate_model.py
Evaluate the trained surrogate on the test split.

Outputs
-------
- reports/validation_metrics.json   — RMSE, MAE, R² per target
- reports/validation_scatter.csv    — predicted vs true for all test samples
- reports/logs/validation.log
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

from scripts_07_train_model import WECDataset, FNOSurrogate

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
TARGETS = ["p_total_norm", "hra_aoi_1_norm", "hra_aoi_2_norm", "hra_aoi_3_norm"]


def load_model(checkpoint_path: Path) -> FNOSurrogate:
    ckpt  = torch.load(checkpoint_path, map_location=DEVICE)
    model = FNOSurrogate(in_channels=4, n_targets=4).to(DEVICE)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    log.info("Loaded model from %s  (epoch=%d, val_loss=%.5f)",
             checkpoint_path, ckpt["epoch"], ckpt["val_loss"])
    return model


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    metrics = {}
    for i, tgt in enumerate(TARGETS):
        yt = y_true[:, i]
        yp = y_pred[:, i]
        rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
        mae  = float(np.mean(np.abs(yt - yp)))
        ss_res = np.sum((yt - yp) ** 2)
        ss_tot = np.sum((yt - yt.mean()) ** 2)
        r2   = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
        metrics[tgt] = {"RMSE": rmse, "MAE": mae, "R2": r2}
        log.info("  %-20s  RMSE=%.4f  MAE=%.4f  R²=%.4f", tgt, rmse, mae, r2)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Validate surrogate on test set")
    parser.add_argument("--problem",    default="config/problem.yaml")
    parser.add_argument("--paths",      default="config/paths.yaml")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--batch_size", type=int, default=64)
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    processed  = Path(pths["processed_dir"])
    models_dir = Path(pths["models_dir"])
    reports    = Path(pths["reports_dir"])
    reports.mkdir(parents=True, exist_ok=True)

    ckpt_path = Path(args.checkpoint) if args.checkpoint else models_dir / "best_model.pt"
    model = load_model(ckpt_path)

    df      = pd.read_parquet(processed / "dataset.parquet")
    df_test = df[df["split"] == "test"].reset_index(drop=True)
    log.info("Test set: %d samples", len(df_test))

    from scripts_utils import domain_bounds_cached
    bounds = domain_bounds_cached(Path(pths["grid_file"]))
    ds_test = WECDataset(df_test, bounds)
    loader  = torch.utils.data.DataLoader(
        ds_test, batch_size=args.batch_size, shuffle=False, num_workers=2)

    all_pred, all_true = [], []
    with torch.no_grad():
        for x, y, _ in loader:
            pred = model(x.to(DEVICE)).cpu().numpy()
            all_pred.append(pred)
            all_true.append(y.numpy())

    y_pred = np.vstack(all_pred)
    y_true = np.vstack(all_true)

    metrics = compute_metrics(y_true, y_pred)
    (reports / "validation_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8")

    scatter = df_test[["run_id", "layout_id", "sea_state_id"]].copy()
    for i, tgt in enumerate(TARGETS):
        scatter[f"{tgt}_true"] = y_true[:, i]
        scatter[f"{tgt}_pred"] = y_pred[:, i]
    scatter.to_csv(reports / "validation_scatter.csv", index=False)
    log.info("Validation complete → %s", reports)


if __name__ == "__main__":
    main()
