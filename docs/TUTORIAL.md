# Building and using a SWAN WEC-layout surrogate

Run these commands from the repository root. This guide follows the scripts
that are currently implemented.

## 1. Configure the project

```powershell
Copy-Item config/problem.yaml.template config/problem.yaml
Copy-Item config/paths.yaml.template config/paths.yaml
```

Set the site-specific `null` values, then ensure that `swan_executable` points
to SNL-SWAN. `problem.yaml` specifies WEC geometry, layout rules, HRA areas and
training policy; `paths.yaml` locates project inputs; `swan.yaml` sets SWAN
physics and outputs. Request `Hs.mat`, as the parser needs it.

## 2. Generate and accept layouts

```powershell
python scripts/01_layout_generator.py
python scripts/02_check_layouts.py
```

The checker creates `reports/layout_checks/layout_metrics.csv`,
`layout_summary.json`, a contact-sheet of layouts, and a spacing histogram.
Proceed only when it reports zero invalid layouts. Invalid means a centre is
outside the deployment polygon or a pair is closer than `min_spacing_m`.

## 3. Sample sea states

```powershell
python scripts/02_sea_states_sampling.py --n_samples 100
```

Review `data/processed/sea_states_coverage_stats.csv`. The sampled Hs, Tp and
direction ranges should cover your operating range and include the intended
extreme-event tail.

## 4. Build and check SWAN cases

```powershell
python scripts/03_build_swan_inputs.py --max_runs 10
python scripts/04_run_swan_batch.py --dry_run
```

Open a generated `runs/<run_id>/INPUT`: check its grid, boundary sea state,
WEC obstacle lines and requested output. Ensure `run_index.parquet` has one row
per run folder. The current input builder pairs layouts and sea states by index,
not their complete Cartesian product.

## 5. Execute and parse SWAN

```powershell
python scripts/04_run_swan_batch.py --workers 4
python scripts/05_parse_outputs.py --baseline path/to/no_wec/Hs.mat
```

Check `reports/logs/swan_batch.log` and `run_status.parquet`; investigate failed
cases via `runs/<run_id>/stderr.log`. The parser writes `outputs.parquet` with
power, HRA and sea-state metadata. A no-WEC baseline is strongly recommended:
without it, HRA uses only a domain-mean fallback.

Before training, ensure targets are finite, `p_total_w` is positive, HRA lies
in `[0, 1]`, and rows can be traced to `run_id`.

## 6. Train, validate and export (target workflow)

Mode B joins layout features, sea state and targets (`p_total_w`, `hra_aoi_*`)
into a scalar dataset. Freeze disjoint train/validation/test **case IDs** before
fitting. Store the model with its feature order, scalers, target bounds,
configuration hash and validation report.

Mode C predicts the full Hs field plus power. `scripts/07_train_model.py` is an
experimental neural-field prototype. The clean CLI stages from dataset building
to GA use are architecture stubs today and raise `NotImplementedError`; do not
yet treat them as a repeatable production training pipeline.

Validate on an untouched test split with error, ranking correlation, top-layout
overlap, local-sensitivity checks, and direct SWAN rechecks of predicted best
layouts. Export only an approved model bundle.

## 7. Use an exported surrogate in a GA

For every GA candidate: validate geometry, apply canonical WEC ordering, build
features in the bundle's stored order, infer, unscale targets with the bundle's
frozen bounds, and calculate fitness. Reject invalid layouts before inference.
`scripts/10_ga_integration.py` demonstrates the experimental field-model path,
not a production bundle interface.

## End-to-end acceptance checklist

1. All configuration paths resolve to the intended site data.
2. Layout checking reports zero invalid layouts.
3. Sea-state output is populated and has sensible coverage.
4. Rendered SWAN inputs show the correct boundary and WEC geometry.
5. Every non-successful SWAN case is explained or corrected.
6. Parsed targets are finite, physically plausible and traceable.
7. Dataset splits have no overlapping case IDs.
8. Validation includes independent SWAN rechecks.
9. The GA uses the bundle's geometry constraints and frozen normalisation.
