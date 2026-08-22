"""
10_ga_integration.py
Plug the trained surrogate into a Genetic Algorithm for WEC array layout optimisation.

GA formulation
--------------
Individual  : flat vector of (x_i, y_i) for i=1..N_WECS  → length 2*N_WECS
Fitness     : weighted sum  α*p_total_norm + (1-α)*mean(hra_norm) — maximise
Constraints : minimum spacing (penalised in fitness)
              domain bounds (repaired via clip)

Uses DEAP library. Falls back to a simple random hill-climber if DEAP unavailable.
"""

import argparse
import json
import logging
import time
from pathlib import Path

import numpy 