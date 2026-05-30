# seismo-jupyterlite-benchmarks

Representative seismology education notebooks benchmarked across Local Jupyter, MyBinder, and JupyterLite.

## Repository layout

- `notebooks/originals/`: exact copies of the supplied notebooks and required helper/data files, excluding checkpoints and bytecode caches.
- `notebooks/benchmarked/`: primary benchmark notebooks with added benchmark control cells and cleared outputs.
- `notebooks/extras/`: broader compatibility material that is useful for discussion but excluded from the main timing table.
- `benchmarking/seismo_bench.py`: shared timing, memory, CSV, and JSON result helpers.
- `results/schema.csv`: spreadsheet import schema.
- `scripts/prepare_notebooks.py`: rebuilds the notebook layout from a supplied `JLite/` source tree.

## Primary benchmark notebooks

The main paper table should use these six benchmarked notebooks:

- `notebooks/benchmarked/Simulation/FD/W4_fd_ac2d_heterogeneous_solutions.ipynb`
- `notebooks/benchmarked/Simulation/SE/W9_se_hetero_1d_solution.ipynb`
- `notebooks/benchmarked/Noise/Probabilistic Power Spectral Densities.ipynb`
- `notebooks/benchmarked/Noise/NoiseCorrelation.ipynb`
- `notebooks/benchmarked/Inversion/el_hypocenter_solution.ipynb`
- `notebooks/benchmarked/ObsPy/ObsPy_Basic_Example.ipynb`

`notebooks/extras/ObsPy/Obspy_Emscripten_Demo.ipynb` is kept as compatibility evidence and should not be included in the main timing table.

## Benchmark protocol

Use one warmup run plus five measured runs for each notebook/environment/device combination.

For each measured run, set these environment variables before opening or executing the notebook:

```powershell
$env:SEISMO_BENCH_ENV = "local"          # local, binder, or jupyterlite
$env:SEISMO_BENCH_BROWSER = "Chrome 126" # browser/version used for the run
$env:SEISMO_BENCH_DEVICE = "Laptop model or VM description"
$env:SEISMO_BENCH_RUN_INDEX = "1"        # 1 through 5 for measured runs
$env:SEISMO_BENCH_PLATFORM_PEAK_MEMORY_MB = ""
$env:SEISMO_BENCH_NOTES = ""
```

For JupyterLite, where OS environment variables may not be available inside the browser kernel, edit the benchmark context cell at the top of the notebook before running the measured pass.

Each benchmarked notebook writes CSV and JSON files under `benchmark-results/` with these columns:

```text
notebook, environment, browser, os, device, run_index, phase, wall_time_s,
python_peak_memory_mb, platform_peak_memory_mb, success, notes
```

Use `platform_peak_memory_mb` for manual browser/container peak memory from the browser task manager, OS task manager, Binder container stats, or comparable observation method. The `python_peak_memory_mb` field is recorded automatically when available.

## Local execution

Create an environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
jupyter lab
```

Open one notebook from `notebooks/benchmarked/`, run all cells once as a warmup, restart the kernel, then run five measured passes with `SEISMO_BENCH_RUN_INDEX` set to `1` through `5`.

## Binder execution

Binder uses `binder/environment.yml`. Launch the repository in Binder, open the same notebook path under `notebooks/benchmarked/`, and follow the same warmup plus five measured run protocol.

Record Binder startup time separately if it is relevant, but do not include startup time in notebook wall-clock phases.

## JupyterLite execution

The JupyterLite build configuration is in `jupyter_lite_config.json`, following the documented `LiteBuildConfig.contents` and `output_dir` format from the [JupyterLite configuration docs](https://jupyterlite.readthedocs.io/en/stable/howto/configure/config_files.html). With JupyterLite installed, build the static site with:

```powershell
jupyter lite build
```

Serve `dist/` with a local static server or deploy it with GitHub Pages. In the browser, open the benchmarked notebooks, run one warmup pass, then five measured passes. Record browser or tab peak memory manually in `platform_peak_memory_mb`.

Network-heavy cells, especially in `ObsPy_Basic_Example.ipynb`, should be annotated in `notes` because data center latency can dominate those phases.

## Regenerating notebooks

If a fresh source bundle is placed in `JLite/`, rebuild the clean notebook layout with:

```powershell
python scripts/prepare_notebooks.py
```

The script replaces `notebooks/`, preserves exact originals under `notebooks/originals/`, clears outputs only in `notebooks/benchmarked/`, and injects benchmark control cells around existing code cells.
