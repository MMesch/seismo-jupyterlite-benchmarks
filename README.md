# seismo-jupyterlite-benchmarks

Representative seismology education notebooks benchmarked across Local Jupyter, MyBinder, and JupyterLite.

The JupyterLite deployment uses a browser-side `xeus-python` kernel with ObsPy and related scientific packages preinstalled from emscripten-forge.

## Launch

- JupyterLite/GitHub Pages: https://lcbmann.github.io/seismo-jupyterlite-benchmarks/
- MyBinder: https://mybinder.org/v2/gh/lcbmann/seismo-jupyterlite-benchmarks/main?urlpath=lab/tree/notebooks/benchmarked
- GitHub repository: https://github.com/lcbmann/seismo-jupyterlite-benchmarks

## Notebooks

Use the benchmarked copies in `notebooks/benchmarked/`:

- `Inversion/el_hypocenter_solution.ipynb`
- `Noise/NoiseCorrelation.ipynb`
- `Noise/Probabilistic Power Spectral Densities.ipynb`
- `ObsPy/ObsPy_Basic_Example.ipynb`
- `Simulation/FD/W4_fd_ac2d_heterogeneous_solutions.ipynb`
- `Simulation/SE/W9_se_hetero_1d_solution.ipynb`

Original unmodified notebooks are kept in `notebooks/originals/`. The broader ObsPy Emscripten demo is in `notebooks/extras/` and is not part of the main benchmark table.

## Run Locally

```powershell
git clone https://github.com/lcbmann/seismo-jupyterlite-benchmarks.git
cd seismo-jupyterlite-benchmarks
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
jupyter lab
```

Then open a notebook from `notebooks/benchmarked/`.

## Collect Benchmark Data

For each notebook and environment, do one warmup run, then five measured runs.

Before each measured local run, set:

```powershell
$env:SEISMO_BENCH_ENV = "local"          # local, binder, or jupyterlite
$env:SEISMO_BENCH_BROWSER = "Chrome"
$env:SEISMO_BENCH_DEVICE = "machine/specs"
$env:SEISMO_BENCH_RUN_INDEX = "1"        # 1 through 5
$env:SEISMO_BENCH_PLATFORM_PEAK_MEMORY_MB = ""
$env:SEISMO_BENCH_NOTES = ""
```

In JupyterLite, edit the first benchmark control cell instead, because browser kernels usually do not receive OS environment variables.

Each run writes CSV and JSON files to `benchmark-results/` with:

```text
notebook, environment, browser, os, device, run_index, phase,
wall_time_s, python_peak_memory_mb, platform_peak_memory_mb, success, notes
```

`python_peak_memory_mb` is automatic when available. Fill `platform_peak_memory_mb` manually from browser task manager, OS task manager, or Binder/container memory observations.

## Notes

- Binder startup time should be recorded separately, not included in notebook runtime.
- Network-heavy phases, especially in the ObsPy notebook, should be noted because data center latency can dominate timing.
- To rebuild the benchmarked notebooks from a fresh `JLite/` source folder, run `python scripts/prepare_notebooks.py`.
- JupyterLite-specific compatibility changes are documented in `docs/jupyterlite-compatibility.md`.
