# swan-surrogate-model

Surrogate model for WEC array layout optimisation using SNL-SWAN.

## Overview

This repository implements a complete surrogate modelling pipeline that replaces
SNL-SWAN simulations in the inner loop of a Genetic Algorithm (GA) optimiser for
Wave Energy Converter (WEC) array layouts.

The surrogate is trained on SNL-SWAN simulation data and provides near-real-time
predictions of total absorbed power (`P_total`) and Hydrodynamic Relative
Availability (HRA) for arbitrary WEC layouts and sea states, maintaining physical
consistency and generalisability.

## Modes

| Mode | Target | Use case |
|------|--------|----------|
| **B** | Scalar `P_total` + HRA vector | Baseline GA integration, fast optimisation |
| **C** | Full `Hs` field + `P_total` | Spatial analysis, flexible HRA post-processing |

## Pipeline Stages

```
01_generate_layouts   →  generate valid WEC layout candidates
02_build_swan_inputs  →  render SNL-SWAN input files per case
03_run_swan_batch     →  execute SNL-SWAN batch with resume support
04_parse_outputs      →  extract P_total, Hs field, HRA; classify B/C
05_build_dataset      →  freeze and version datasets B and C
06_train_model        →  train surrogate (XGBoost baseline for B, field model for C)
07_validate_model     →  validate ranking, top-10%, local sensitivity, dynamic recheck
08_export_surrogate   →  package approved model as versioned inference bundle
09_use_in_ga          →  integrate bundle into GA fitness evaluation loop
```

## Repository Structure

```
swan-surrogate-model/
├── config/                    # problem.yaml, paths.yaml
├── data/
│   ├── raw/                   # scatter diagrams, bathymetry, BCs
│   ├── processed/             # candidates, parsed outputs, frozen datasets
│   └── archive/               # .mat fields, case archives
├── runs/                      # per-case SNL-SWAN run directories
├── models/
│   ├── exported/              # versioned inference bundles
│   └── splits/                # frozen train/val/test splits by case_id
├── reports/
│   ├── logs/                  # per-stage operational logs
│   ├── train_curves/          # training metric plots
│   └── validation_plots/      # validation metric plots
├── src/
│   ├── config/                # config loaders and validators
│   ├── layouts/               # layout generation, geometry validation
│   ├── swan_inputs/           # SNL-SWAN input file rendering
│   ├── runner/                # batch execution, resume, status tracking
│   ├── parser/                # output parsing, P_total, Hs field, HRA
│   ├── dataset/               # dataset assembly, versioning, registry
│   ├── training/              # model training, scalers, bundles
│   ├── validation/            # holdout, ranking, dynamic recheck
│   ├── export/                # bundle packaging and manifest
│   ├── ga_integration/        # surrogate fitness interface for GA
│   └── utils/                 # logging, io helpers, physical checks
├── tests/
│   ├── unit/
│   └── integration/
├── notebooks/                 # exploratory analysis and examples
├── scripts/                   # CLI entry points
├── docs/
│   └── blueprints/            # full blueprint specification documents
└── .github/workflows/         # CI configuration
```

## Quick Start

```bash
# 1. Create environment
conda env create -f environment.yml
conda activate swan-surrogate

# 2. Configure your problem
cp config/problem.yaml.template config/problem.yaml
cp config/paths.yaml.template config/paths.yaml
# Edit both files for your case

# 3. Generate layouts
python scripts/01_generate_layouts.py

# 4. Build SWAN inputs
python scripts/02_build_swan_inputs.py

# 5. Run SWAN batch
python scripts/03_run_swan_batch.py

# 6. Parse outputs
python scripts/04_parse_outputs.py

# 7. Build dataset
python scripts/05_build_dataset.py

# 8. Train model
python scripts/06_train_model.py --mode B

# 9. Validate model
python scripts/07_validate_model.py --mode B

# 10. Export surrogate
python scripts/08_export_surrogate.py --mode B

# 11. Use in GA
# See src/ga_integration/ for usage examples
```

## Physical Validity Rules

- Geometric constraints are enforced **before** any surrogate inference
- Invalid layouts are rejected, never penalised post-inference
- Canonical WEC ordering is applied before feature vector construction
- Fitness normalisation uses frozen min-max bounds from the training bundle

## Documentation

Full blueprint specifications are in `docs/blueprints/`.

## Requirements

- Python 3.10+
- PyTorch ≥ 2.0
- scikit-learn ≥ 1.3
- xgboost ≥ 2.0
- numpy, scipy, pandas, pyyaml, netCDF4, jinja2

See `environment.yml` and `pyproject.toml` for full dependency list.

## License

MIT License — see `LICENSE`.
