import logging

import numpy as np
import pandas as pd

import torch
from torch.utils.data import Dataset


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

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
