"""Build the benchmark notebook layout from the supplied JLite notebooks.

This script copies source files from JLite into notebooks/originals without
editing them, creates benchmarked notebook copies with added timing cells, and
places the broader ObsPy Emscripten demo in notebooks/extras.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
JLITE_SOURCE = ROOT / "JLite"
NOTEBOOKS = ROOT / "notebooks"
ORIGINALS = NOTEBOOKS / "originals"
BENCHMARKED = NOTEBOOKS / "benchmarked"
EXTRAS = NOTEBOOKS / "extras"
TEMP_SOURCE = ROOT / ".prepare_notebooks_source_tmp"
BENCHMARK_ASSETS = ROOT / "benchmark_assets"

EXCLUDED_DIRS = {".ipynb_checkpoints", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc"}

PRIMARY_NOTEBOOKS = {
    Path("Simulation/FD/W4_fd_ac2d_heterogeneous_solutions.ipynb"): [
        "setup/imports",
        "setup/model",
        "main compute",
        "plotting/rendering",
        "plotting/rendering",
        "unused/blank",
    ],
    Path("Simulation/SE/W9_se_hetero_1d_solution.ipynb"): [
        "setup/imports",
        "setup/model",
        "setup/model",
        "plotting/rendering",
        "main compute",
        "main compute",
        "main compute",
        "main compute",
        "plotting/rendering",
        "plotting/rendering",
        "unused/blank",
    ],
    Path("Noise/Probabilistic Power Spectral Densities.ipynb"): [
        "setup/imports",
        "data loading",
        "main compute",
        "data loading",
        "plotting/rendering",
        "main compute",
        "main compute",
        "main compute",
        "unused/blank",
    ],
    Path("Noise/NoiseCorrelation.ipynb"): [
        "setup/imports",
        "data loading/download",
        "data loading",
        "setup/functions",
        "main compute",
        "main compute",
        "plotting/rendering",
        "data loading/download",
        "main compute",
        "plotting/rendering",
    ],
    Path("Inversion/el_hypocenter_solution.ipynb"): [
        "setup/imports",
        "setup/model",
        "main compute",
        "plotting/rendering",
    ],
    Path("ObsPy/ObsPy_Basic_Example.ipynb"): [
        "setup/imports",
        "setup/imports",
        "setup/model",
        "data loading/download",
        "data loading/download",
        "main compute",
    ],
}

EXTRA_NOTEBOOKS = {Path("ObsPy/Obspy_Emscripten_Demo.ipynb")}


def main() -> None:
    source = JLITE_SOURCE if JLITE_SOURCE.exists() else ORIGINALS
    if not source.exists():
        raise SystemExit(
            f"Missing source directory: expected {JLITE_SOURCE} or {ORIGINALS}"
        )

    using_existing_originals = source == ORIGINALS
    try:
        if using_existing_originals:
            if TEMP_SOURCE.exists():
                shutil.rmtree(TEMP_SOURCE)
            copy_clean_tree(ORIGINALS, TEMP_SOURCE)
            source = TEMP_SOURCE

        if NOTEBOOKS.exists():
            shutil.rmtree(NOTEBOOKS)

        copy_clean_tree(source, ORIGINALS)
        copy_benchmarked_inputs()
        copy_benchmark_assets()
        copy_extras()
        instrument_primary_notebooks()
    finally:
        if TEMP_SOURCE.exists():
            shutil.rmtree(TEMP_SOURCE)


def copy_clean_tree(src: Path, dst: Path) -> None:
    for path in iter_clean_files(src):
        relative = path.relative_to(src)
        target = dst / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def copy_benchmarked_inputs() -> None:
    wanted_roots = [
        Path("Simulation/FD"),
        Path("Simulation/SE"),
        Path("Noise"),
        Path("Inversion"),
        Path("ObsPy"),
    ]
    for relative_root in wanted_roots:
        src_root = ORIGINALS / relative_root
        if not src_root.exists():
            continue
        for path in iter_clean_files(src_root):
            relative = path.relative_to(ORIGINALS)
            if relative in EXTRA_NOTEBOOKS:
                continue
            target = BENCHMARKED / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def copy_benchmark_assets() -> None:
    if not BENCHMARK_ASSETS.exists():
        return
    copy_clean_tree(BENCHMARK_ASSETS, BENCHMARKED)


def copy_extras() -> None:
    for relative in EXTRA_NOTEBOOKS:
        source = ORIGINALS / relative
        if source.exists():
            target = EXTRAS / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def instrument_primary_notebooks() -> None:
    for relative, phases in PRIMARY_NOTEBOOKS.items():
        notebook_path = BENCHMARKED / relative
        with notebook_path.open("r", encoding="utf-8") as fh:
            notebook = json.load(fh)

        clear_outputs(notebook)
        apply_compatibility_patches(relative, notebook)
        notebook["cells"] = instrument_cells(
            notebook["cells"],
            notebook_name=str(relative).replace("\\", "/"),
            phases=phases,
        )

        with notebook_path.open("w", encoding="utf-8") as fh:
            json.dump(notebook, fh, indent=1, ensure_ascii=False)
            fh.write("\n")


def instrument_cells(cells: list[dict], notebook_name: str, phases: list[str]) -> list[dict]:
    instrumented = [make_setup_cell(notebook_name)]
    code_index = 0
    for cell in cells:
        if cell.get("cell_type") == "code":
            phase = phases[code_index] if code_index < len(phases) else "unclassified"
            code_index += 1
            if phase != "unused/blank" and source_text(cell).strip():
                instrumented.append(make_phase_start_cell(phase))
        instrumented.append(cell)
    instrumented.append(make_save_cell())
    return instrumented


def clear_outputs(notebook: dict) -> None:
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None


def apply_compatibility_patches(relative: Path, notebook: dict) -> None:
    """Apply narrow JupyterLite/WASM compatibility patches to benchmark copies."""

    if relative == Path("Noise/NoiseCorrelation.ipynb"):
        patch_noise_correlation_sources(notebook)

    if relative not in {
        Path("Noise/Probabilistic Power Spectral Densities.ipynb"),
        Path("Noise/NoiseCorrelation.ipynb"),
        Path("ObsPy/ObsPy_Basic_Example.ipynb"),
    }:
        return

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        text = source_text(cell)
        if "import matplotlib" in text or "pyodide_http.patch_all()" in text:
            if "_seismo_patch_obspy_wasm_io" not in text:
                set_source(cell, OBS_PY_WASM_COMPAT + "\n" + text)
            return


def patch_noise_correlation_sources(notebook: dict) -> None:
    replacements = {
        "https://raw.github.com/ashimrijal/NoiseCorrelation/master/data/noise.CI.MLAC.LHZ.2004.294.2005.017.mseed": (
            "data/noise.CI.MLAC.LHZ.2004.294.2005.017.mseed"
        ),
        "https://raw.github.com/ashimrijal/NoiseCorrelation/master/data/noise.CI.PHL.LHZ.2004.294.2005.017.mseed": (
            "data/noise.CI.PHL.LHZ.2004.294.2005.017.mseed"
        ),
        "https://raw.github.com/ashimrijal/NoiseCorrelation/master/data/event.CI.PHL.LHZ.1998.196.1998.196.mseed": (
            "data/event.CI.PHL.LHZ.1998.196.1998.196.mseed"
        ),
    }

    for cell in notebook.get("cells", []):
        text = source_text(cell)
        updated = text
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != text:
            set_source(cell, updated)


OBS_PY_WASM_COMPAT = """# JupyterLite/emscripten compatibility for ObsPy file readers.
# ObsPy's MiniSEED reader uses np.memmap, which is unavailable in the browser
# filesystem. Copy file bytes into an ndarray instead.
import numpy as np

def _seismo_patch_obspy_wasm_io():
    def _seismo_fake_memmap(filename, dtype=np.uint8, mode=None, offset=0, shape=None, order=None):
        with open(filename, "rb") as f:
            f.seek(offset)
            data = np.fromfile(f, dtype=dtype)
        if shape is not None:
            data = data[:int(np.prod(shape))].reshape(shape, order=order or "C")
        return data

    np.memmap = _seismo_fake_memmap

    try:
        import pyodide_http
        pyodide_http.patch_all()
    except Exception:
        pass

_seismo_patch_obspy_wasm_io()
"""


def iter_clean_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        yield path


def make_setup_cell(notebook_name: str) -> dict:
    return make_code_cell(
        f"""# seismo-benchmark-control
import os as _seismo_bench_os
import sys as _seismo_bench_sys
import time as _seismo_bench_time
from pathlib import Path as _SeismoBenchPath

_seismo_bench_here = _SeismoBenchPath.cwd()
for _seismo_bench_root in [_seismo_bench_here, *_seismo_bench_here.parents]:
    if (
        (_seismo_bench_root / "benchmarking" / "seismo_bench.py").exists()
        or (_seismo_bench_root / "seismo_bench.py").exists()
    ):
        if str(_seismo_bench_root) not in _seismo_bench_sys.path:
            _seismo_bench_sys.path.insert(0, str(_seismo_bench_root))
        break

try:
    from benchmarking.seismo_bench import make_context as _seismo_bench_make_context
    from benchmarking.seismo_bench import start_run as _seismo_bench_start_run
except ModuleNotFoundError:
    from seismo_bench import make_context as _seismo_bench_make_context
    from seismo_bench import start_run as _seismo_bench_start_run

def _seismo_bench_float_from_env(name):
    value = _seismo_bench_os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None

_SEISMO_BENCH_CONTEXT = _seismo_bench_make_context(
    notebook="{notebook_name}",
    environment=_seismo_bench_os.environ.get("SEISMO_BENCH_ENV", "unset"),
    browser=_seismo_bench_os.environ.get("SEISMO_BENCH_BROWSER", "unset"),
    device=_seismo_bench_os.environ.get("SEISMO_BENCH_DEVICE", "unset"),
    run_index=int(_seismo_bench_os.environ.get("SEISMO_BENCH_RUN_INDEX", "0")),
    platform_peak_memory_mb=_seismo_bench_float_from_env("SEISMO_BENCH_PLATFORM_PEAK_MEMORY_MB"),
    notes=_seismo_bench_os.environ.get("SEISMO_BENCH_NOTES", ""),
)
_SEISMO_BENCH_RUN = _seismo_bench_start_run(_SEISMO_BENCH_CONTEXT)
_SEISMO_BENCH_TOTAL_T0 = _seismo_bench_time.perf_counter()
_SEISMO_BENCH_PENDING_PHASE = None
_SEISMO_BENCH_PENDING_T0 = None

def _seismo_bench_start_phase(phase):
    global _SEISMO_BENCH_PENDING_PHASE, _SEISMO_BENCH_PENDING_T0
    _SEISMO_BENCH_PENDING_PHASE = phase
    _SEISMO_BENCH_PENDING_T0 = _seismo_bench_time.perf_counter()

def _seismo_bench_save_silently():
    try:
        _SEISMO_BENCH_RUN.save()
    except Exception as exc:
        print(f"Benchmark save failed: {{exc}}")

def _seismo_bench_post_run_cell(result):
    global _SEISMO_BENCH_PENDING_PHASE, _SEISMO_BENCH_PENDING_T0
    if _SEISMO_BENCH_PENDING_PHASE is None:
        return
    if _SEISMO_BENCH_PENDING_T0 is None:
        _SEISMO_BENCH_PENDING_PHASE = None
        return
    raw_cell = getattr(getattr(result, "info", None), "raw_cell", "")
    if "seismo-benchmark-control" in raw_cell:
        return
    elapsed = _seismo_bench_time.perf_counter() - _SEISMO_BENCH_PENDING_T0
    error = getattr(result, "error_in_exec", None) or getattr(result, "error_before_exec", None)
    success = error is None and bool(getattr(result, "success", True))
    notes = ""
    if error is not None:
        notes = f"{{type(error).__name__}}: {{error}}"
    _SEISMO_BENCH_RUN.record_manual_phase(
        _SEISMO_BENCH_PENDING_PHASE,
        elapsed,
        success=success,
        notes=notes,
    )
    _SEISMO_BENCH_PENDING_PHASE = None
    _SEISMO_BENCH_PENDING_T0 = None
    _seismo_bench_save_silently()

_seismo_bench_ip = get_ipython()
try:
    _seismo_bench_old_callback = getattr(
        _seismo_bench_ip, "_seismo_bench_post_run_cell_callback", None
    )
    if _seismo_bench_old_callback is not None:
        _seismo_bench_ip.events.unregister("post_run_cell", _seismo_bench_old_callback)
except Exception:
    pass
_seismo_bench_ip.events.register("post_run_cell", _seismo_bench_post_run_cell)
_seismo_bench_ip._seismo_bench_post_run_cell_callback = _seismo_bench_post_run_cell
print("Benchmark context ready:", _SEISMO_BENCH_CONTEXT)
"""
    )


def make_phase_start_cell(phase: str) -> dict:
    return make_code_cell(
        f"""# seismo-benchmark-control
_seismo_bench_start_phase({phase!r})
"""
    )


def make_save_cell() -> dict:
    return make_code_cell(
        """# seismo-benchmark-control
_SEISMO_BENCH_RUN.record_manual_phase(
    "full notebook total",
    _seismo_bench_time.perf_counter() - _SEISMO_BENCH_TOTAL_T0,
)
_seismo_bench_csv_path, _seismo_bench_json_path = _SEISMO_BENCH_RUN.save()
print("Benchmark results written:", _seismo_bench_csv_path, _seismo_bench_json_path)
"""
    )


def make_code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"tags": ["seismo-benchmark-control"]},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def set_source(cell: dict, source: str) -> None:
    cell["source"] = source.splitlines(keepends=True)


if __name__ == "__main__":
    main()
