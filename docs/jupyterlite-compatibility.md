# JupyterLite Compatibility Notes

This repository keeps the supplied notebooks unchanged in `notebooks/originals/`.
The benchmark copies in `notebooks/benchmarked/` add timing cells and a small
number of compatibility changes needed to run the same scientific examples in
Local Jupyter, MyBinder, and JupyterLite.

## Summary

Most failures encountered so far are specific to JupyterLite's browser-hosted
WebAssembly runtime, not to normal local Python or Binder containers.
JupyterLite runs Python in an Emscripten/WASM environment with browser file and
network APIs. That changes three practical things for these notebooks:

- packages must be available from an Emscripten-compatible channel;
- file access is not identical to POSIX file access;
- browser network requests are subject to browser/CORS/XHR behavior;
- the runtime has tighter memory/address-space limits than native Python.

The benchmark copies are still intended to represent the same notebook tasks.
When a compatibility change would alter normal Python behavior, it is guarded so
it only runs under Emscripten/JupyterLite.

## Repository-Level JupyterLite Setup

JupyterLite now uses `jupyterlite-xeus` rather than the default Pyodide kernel.
This was needed because ObsPy and some geoscience/scientific dependencies are
available through emscripten-forge for the xeus-python WebAssembly kernel.

Relevant files:

- `.github/build-environment.yml`: packages used by GitHub Actions to build the
  JupyterLite site.
- `environment.yml`: packages preinstalled into the browser-side xeus-python
  kernel, including `obspy`, `numpy`, `scipy`, `matplotlib`, `pandas`, and
  `cartopy`.
- `jupyter_lite_config.json`: includes `notebooks/benchmarked`,
  `notebooks/extras`, and `jupyterlite_contents` in the deployed site.

This setup is JupyterLite-only. Local and Binder runs use their normal Python
environments.

## Benchmark Instrumentation

All benchmarked notebooks receive added cells that:

- create a benchmark context;
- time labeled phases;
- record success/failure;
- write CSV and JSON result files.

This instrumentation is not a JupyterLite workaround. It is present in all
environments so Local, Binder, and JupyterLite produce the same schema.

## ObsPy MiniSEED File Reading

Problem observed in JupyterLite:

```text
OSError: [Errno 43] No such device
```

Cause:

ObsPy's MiniSEED reader uses `np.memmap`. In the browser-hosted Emscripten
filesystem, memory-mapped files are not available in the same way as native
Python, so the read failed even when the file existed.

Compatibility change:

The benchmarked ObsPy-dependent notebooks include a small shim that replaces
`np.memmap` with a normal file read into a NumPy array, but only when running
under Emscripten/JupyterLite.

Affected notebooks:

- `Noise/Probabilistic Power Spectral Densities.ipynb`
- `Noise/NoiseCorrelation.ipynb`
- `ObsPy/ObsPy_Basic_Example.ipynb`

Effect on Local/Binder:

None intended. The patch exits immediately unless the platform is Emscripten, so
native Python keeps the standard NumPy/ObsPy path.

## NoiseCorrelation Remote Data

Problem observed in JupyterLite:

```text
JsGenericError: NetworkError: Failed to execute 'send' on 'XMLHttpRequest'
```

Cause:

The notebook tried to load MiniSEED files directly from `raw.github.com` with
`obspy.read("https://...")`. In JupyterLite this goes through browser XHR via
`requests`/`pyodide-http`, which can fail because of browser network rules,
redirects, CORS behavior, or other fetch restrictions. Later cells then failed
with `NameError` for variables such as `stn` or `ste` because the data-loading
cell never completed.

Compatibility change:

The three MiniSEED files used by the notebook are bundled with the benchmark
content and the executable `obspy.read(...)` calls are rewritten to local
`data/...` paths:

- `data/noise.CI.MLAC.LHZ.2004.294.2005.017.mseed`
- `data/noise.CI.PHL.LHZ.2004.294.2005.017.mseed`
- `data/event.CI.PHL.LHZ.1998.196.1998.196.mseed`

The files are stored in `benchmark_assets/Noise/data/` and copied into
`notebooks/benchmarked/Noise/data/` by `scripts/prepare_notebooks.py`.

Effect on Local/Binder:

This change affects all environments, but intentionally reduces network
variability. The notebook measures the noise-correlation workflow rather than
GitHub raw-file latency. The original notebook with remote reads remains
unchanged in `notebooks/originals/`.

## PPSD Matplotlib PSD Calculation

Problem observed in JupyterLite:

```text
ValueError: array is too big; arr.size * arr.dtype.itemsize is larger than the maximum possible size
```

Cause:

ObsPy's `PPSD.add(...)` calls `matplotlib.mlab.psd(...)`. Recent Matplotlib
uses `numpy.lib.stride_tricks.sliding_window_view(...)` internally for this
calculation. In the browser/WASM runtime, creating the large virtual strided
array can exceed the maximum addressable array size even when native Python
would handle the operation.

Compatibility change:

For Emscripten/JupyterLite only, the compatibility shim replaces
`matplotlib.mlab.psd` with a loop-based implementation that computes the same
Welch-style periodogram without creating one large sliding-window view. The
notebook's ObsPy `PPSD` parameters are not reduced, and the cell still calls
`ppsd.add(tr)` and `ppsd.plot()` as before.

Effect on Local/Binder:

None intended. Local and Binder runs continue using the normal Matplotlib PSD
implementation because the patch exits outside Emscripten.

Paper note:

This should be reported as a JupyterLite compatibility workaround for
browser-memory/address-space limits, not as a notebook optimization.

## PPSD Precomputed NPZ Loading

Problem anticipated/handled:

ObsPy `PPSD.load_npz(...)` can require pickle support depending on the saved
file contents and NumPy version.

Compatibility change:

The benchmark notebook uses:

```python
PPSD.load_npz("data/PPSD_FUR_HHN.npz", allow_pickle=True)
```

Effect on Local/Binder:

This is compatible with native Python and Binder. It is a loading compatibility
setting, not a numerical change.

## What Remains Unchanged

The benchmarked notebooks do not intentionally change the scientific task:

- no FD/SE simulation parameter reduction has been made for benchmarking;
- the inversion notebook is not changed for JupyterLite compatibility;
- the core NoiseCorrelation workflow remains the same after data is loaded;
- the PPSD notebook still uses ObsPy `PPSD` and the same bundled input files.

The changes are either benchmark instrumentation, local data bundling to avoid
browser fetch failures, or Emscripten-only runtime patches.

## Data Collection Implication

Use the same `notebooks/benchmarked/` copies for all three environments. For
paper interpretation:

- compare timing and memory from the same benchmark phase labels;
- note that JupyterLite uses Emscripten-only compatibility patches;
- note that NoiseCorrelation uses bundled MiniSEED files in all environments to
  avoid measuring network variability;
- treat browser/container peak memory as an external observation, while
  `python_peak_memory_mb` is only populated where Python-level memory tracking
  is available.
