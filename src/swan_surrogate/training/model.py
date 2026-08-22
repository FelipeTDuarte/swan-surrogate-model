import logging
import torch.nn as nn
from neuralop.models import FNO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

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