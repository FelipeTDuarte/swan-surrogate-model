"""
07_train_model.py
Train a Fourier Neural Operator (FNO) surrogate on the WEC array dataset.

Architecture
------------
Input  : layout encoding (x, y coordinates → 2D density map on regular grid)
         + sea state scalars (Hs, Tp, Dir) broadcast as channels
Output : scalar targets — p_total_norm, hra_aoi_1_norm, hra_aoi_2_norm, hra_aoi_3_norm

Model: FNO2d from neuraloperator library
       with a scalar head on top (global average pool → MLP)

Training
--------
- Loss: weighted MSE (importance weight from sea-state sampler)
- Scheduler: OneCycleLR
- Early stopping: patience=20 epochs on val loss
- Checkpoints: models/best_model.pt  + models/last_model.pt
- Metrics logged to reports/logs/training_metrics.csv
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, Dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ──────────────────────────────────────────────────────────────────────────────
# Layout → density map encoder
# ──────────────────────────────────────────────────────────────────────────────

def coords_to_density(x_coords: list, y_coords: list,
                      xmin: float, xmax: float,
                      ymin: float, ymax: float,
                      grid_h: int = 64, grid_w: int = 64) -> np.ndarray:
    """Convert WEC (x,y) list to a 2-D normalised density map (H x W)."""
    density = np.zeros((grid_h, grid_w), dtype=np.float32)
    xs = np.clip((np.array(x_coords) - xmin) / (xmax - xmin), 0, 1)
    ys = np.clip((np.array(y_coords) - ymin) / (ymax - ymin), 0, 1)
    ix = np.floor(xs * (grid_w - 1)).astype(int)
    iy = np.floor(ys * (grid_h - 1)).astype(int)
    for i, j in zip(iy, ix):
        density[i, j] += 1.0
    if density.max() > 0:
        density /= density.max()
    return density


# ──────────────────────────────────────────────────────────────────────────────
# Dataset
# ──────────────────────────────────────────────────────────────────────────────

class WECDataset(Dataset):
    def __init__(self, df: pd.DataFrame, bounds: dict,
                 grid_h: int = 64, grid_w: int = 64):
        self.df = df.reset_index(drop=True)
        self.bounds = bounds
        self.grid_h = grid_h
        self.grid_w = grid_w
        self.targets = ["p_total_norm", "hra_aoi_1_norm", "hra_aoi_2_norm", "hra_aoi_3_norm"]

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        # Layout channel
        density = coords_to_density(
            row["x_coords"], row["y_coords"],
            self.bounds["xmin"], self.bounds["xmax"],
            self.bounds["ymin"], self.bounds["ymax"],
            self.grid_h, self.grid_w,
        )
        # Sea state channels (broadcast to same spatial grid)
        Hs_norm  = float(row["Hs"])  / 10.0   # rough normalisation
        Tp_norm  = float(row["Tp"])  / 20.0
        Dir_norm = float(row["Dir"]) / 360.0
        ss_map = np.stack([
            np.full((self.grid_h, self.grid_w), Hs_norm,  dtype=np.float32),
            np.full((self.grid_h, self.grid_w), Tp_norm,  dtype=np.float32),
            np.full((self.grid_h, self.grid_w), Dir_norm, dtype=np.float32),
        ])
        # (4, H, W) — 1 layout + 3 sea state channels
        x = torch.from_numpy(np.concatenate([[density], ss_map], axis=0))
        y = torch.tensor([float(row[t]) for t in self.targets], dtype=torch.float32)
        w = torch.tensor(float(row["weight"]), dtype=torch.float32)
        return x, y, w


# ──────────────────────────────────────────────────────────────────────────────
# Model — lightweight CNN surrogate (FNO backend optional)
# ──────────────────────────────────────────────────────────────────────────────

class FNOSurrogate(nn.Module):
    """
    Surrogate based on Fourier Neural Operator or plain CNN.
    Uses neuraloperator FNO2d if available, falls back to ConvNet.
    """
    def __init__(self, in_channels: int = 4, n_targets: int = 4,
                 grid_h: int = 64, grid_w: int = 64):
        super().__init__()
        self.use_fno = False
        try:
            from neuraloperator.models import FNO
            self.fno = FNO(n_modes=(16, 16), hidden_channels=64,
                           in_channels=in_channels, out_channels=32,
                           n_layers=4)
            self.use_fno = True
            log.info("Using FNO2d from neuraloperator")
        except ImportError:
            log.warning("neuraloperator not installed — using ConvNet fallback")
            self.fno = nn.Sequential(
                nn.Conv2d(in_channels, 32, 3, padding=1), nn.GELU(),
                nn.Conv2d(32, 64, 3, padding=1), nn.GELU(),
                nn.Conv2d(64, 64, 3, padding=1), nn.GELU(),
                nn.Conv2d(64, 32, 3, padding=1), nn.GELU(),
            )

        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(32, 64), nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(64, n_targets),
            nn.Sigmoid(),   # targets are normalised to [0,1]
        )

    def forward(self, x):
        feat = self.fno(x)
        return self.head(feat)


# ──────────────────────────────────────────────────────────────────────────────
# Training loop
# ──────────────────────────────────────────────────────────────────────────────

def weighted_mse(pred: torch.Tensor, target: torch.Tensor,
                 weight: torch.Tensor) -> torch.Tensor:
    loss = ((pred - target) ** 2).mean(dim=1)
    return (loss * weight / weight.sum()).sum()


def train_epoch(model, loader, optimiser):
    model.train()
    total_loss = 0.0
    for x, y, w in loader:
        x, y, w = x.to(DEVICE), y.to(DEVICE), w.to(DEVICE)
        optimiser.zero_grad()
        pred = model(x)
        loss = weighted_mse(pred, y, w)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimiser.step()
        total_loss += loss.item()
    return total_loss / len(loader)


@torch.no_grad()
def eval_epoch(model, loader):
    model.eval()
    total_loss = 0.0
    for x, y, w in loader:
        x, y, w = x.to(DEVICE), y.to(DEVICE), w.to(DEVICE)
        pred  = model(x)
        total_loss += weighted_mse(pred, y, w).item()
    return total_loss / len(loader)


def main():
    parser = argparse.ArgumentParser(description="Train WEC array surrogate")
    parser.add_argument("--problem",    default="config/problem.yaml")
    parser.add_argument("--paths",      default="config/paths.yaml")
    parser.add_argument("--epochs",     type=int, default=200)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr",         type=float, default=1e-3)
    parser.add_argument("--patience",   type=int, default=20)
    parser.add_argument("--grid_h",     type=int, default=64)
    parser.add_argument("--grid_w",     type=int, default=64)
    args = parser.parse_args()

    cfg  = yaml.safe_load(Path(args.problem).read_text())
    pths = yaml.safe_load(Path(args.paths).read_text())

    processed  = Path(pths["processed_dir"])
    models_dir = Path(pths["models_dir"])
    logs_dir   = Path(pths["logs_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(processed / "dataset.parquet")

    # Infer domain bounds from grid file at runtime
    from scripts_utils import domain_bounds_cached
    bounds = domain_bounds_cached(Path(pths["grid_file"]))

    df_train = df[df["split"] == "train"]
    df_val   = df[df["split"] == "val"]
    log.info("train=%d  val=%d", len(df_train), len(df_val))

    ds_train = WECDataset(df_train, bounds, args.grid_h, args.grid_w)
    ds_val   = WECDataset(df_val,   bounds, args.grid_h, args.grid_w)
    dl_train = DataLoader(ds_train, batch_size=args.batch_size, shuffle=True,
                          num_workers=4, pin_memory=True)
    dl_val   = DataLoader(ds_val,   batch_size=args.batch_size, shuffle=False,
                          num_workers=2, pin_memory=True)

    model = FNOSurrogate(in_channels=4, n_targets=4,
                         grid_h=args.grid_h, grid_w=args.grid_w).to(DEVICE)
    log.info("Model parameters: %d", sum(p.numel() for p in model.parameters()))

    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.lr, steps_per_epoch=len(dl_train), epochs=args.epochs)

    best_val  = float("inf")
    patience_counter = 0
    metrics   = []

    for epoch in range(1, args.epochs + 1):
        tr_loss  = train_epoch(model, dl_train, optimiser)
        val_loss = eval_epoch(model, dl_val)
        scheduler.step()
        lr_now = optimiser.param_groups[0]["lr"]

        metrics.append({"epoch": epoch, "train_loss": tr_loss,
                        "val_loss": val_loss, "lr": lr_now})
        if epoch % 10 == 0:
            log.info("Epoch %3d  train=%.5f  val=%.5f  lr=%.2e",
                     epoch, tr_loss, val_loss, lr_now)

        torch.save({"epoch": epoch, "model_state": model.state_dict(),
                    "val_loss": val_loss}, models_dir / "last_model.pt")

        if val_loss < best_val:
            best_val = val_loss
            patience_counter = 0
            torch.save({"epoch": epoch, "model_state": model.state_dict(),
                        "val_loss": val_loss}, models_dir / "best_model.pt")
            log.info("  ✓ New best val=%.5f at epoch %d", best_val, epoch)
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                log.info("Early stopping at epoch %d", epoch)
                break

    pd.DataFrame(metrics).to_csv(logs_dir / "training_metrics.csv", index=False)
    log.info("Training complete. Best val loss=%.5f", best_val)


if __name__ == "__main__":
    main()
