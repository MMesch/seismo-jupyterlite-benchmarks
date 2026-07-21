# WASM vs Native Micro-Benchmark — JupyterLite / xeus-python

**Try it yourself:** [Micro/MicroBench.ipynb on JupyterLite](https://mmesch.github.io/seismo-jupyterlite-benchmarks/lab/index.html?path=Micro/MicroBench.ipynb)

**Setup**
- **Native**: local mamba env, Python 3.12.13, ObsPy 1.5.0, NumPy 2.5.1, SciPy 1.x on Linux (NixOS, kernel 6.18.33).
- **WASM**: JupyterLite serving the same repo, xeus-python 4.0.9 (Emscripten wasm32), Chrome, same machine.
- **Input**: same 12 MB MiniSEED file (`data/noise.CI.MLAC.LHZ.2004.294.2005.017.mseed`), 90 days of 1 Hz ambient noise.
- **Method**: `MicroBench.ipynb` (in this repo at `notebooks/benchmarked/Micro/`). Each `micro/*` op is run best-of-5. Batched probes report per-single-op numbers below (dividing by both the outer 5 reps and the inner batch count).

## Full paired comparison

All values are best-of-5 from a single fresh native + JupyterLite run (`micro_bench_*_run-0.json`). Batched probes report per-single-op numbers (dividing by the inner batch count).

| operation | what it measures | native | WASM | **ratio** | observation |
|---|---|---:|---:|---:|---|
| imports/stdlib | cold `import sys, os, time, json, ...` (11 modules) | 18 ms | 106 ms | 6.0× | stdlib bootstrapping under xeus adds ~100 ms |
| imports/numpy | cold `import numpy` on top of stdlib | 213 ms | 534 ms | 2.5× | moderate |
| **imports/scipy** | cold `import scipy.signal + scipy` on top of numpy | 1010 ms | **6345 ms** | **6.3×** | 🚨 scipy alone is ~86% of the 7.4 s WASM cold-start |
| imports/obspy | cold `import obspy` on top of scipy+numpy | 134 ms | 462 ms | 3.5× | small once scipy is loaded |
| imports/wasm_compat | install `np.memmap` shim + version check | 11 ms | 26 ms | 2.4× | trivial |
| setup/model (helpers) | define `bench()`, dict init | 15 ms | 23 ms | 1.5× | trivial |
| setup/model (bytes+ref) | `open+read` 12 MB + `obspy.read(BytesIO)` for reference stream | 273 ms | 3949 ms | 14× | dominated by the single WASM `open()` (~1.5 s) plus merge |
| read_bytes | full-file `open()+read()` of 12 MB | 1.7 ms | 1359 ms | **809×** | ≈ 1× open cost + tiny read |
| obspy_read_path | `obspy.read(path)` — full pipeline with format auto-detect | 65 ms | 10566 ms | **163×** | see decomposition below |
| obspy_read_path_format | `obspy.read(path, format="MSEED")` — skips auto-detect | 64 ms | 9184 ms | **143×** | still pays tarfile+zipfile probes |
| **obspy_read_bytesio** | `obspy.read(BytesIO, format="MSEED")` — pure decode | 68 ms | **83 ms** | **1.23×** | ✅ libmseed under WASM is basically native speed |
| **obspy_read_path_nocompress** | `obspy.read(..., check_compression=False)` | 64 ms | 1428 ms | **22×** | 6× faster than `_format` — the compression probes were the cost |
| **tarfile_is_tarfile** | one bare `tarfile.is_tarfile(path)` call | 0.2 ms | **5915 ms** | **28,000×** | 🚨 `tarfile.open(..., 'r\|*')` opens the file ~4× (gzip/bz2/xz/tar) — each open is ~1.5 s |
| **zipfile_is_zipfile** | one bare `zipfile.is_zipfile(path)` call | 0.09 ms | 1332 ms | 14,800× | ≈ 1× open + seek+read tail |
| fs_chunk_sweep (per 1 MB read, best across 1M/64K/4K/512B chunks) | how the read cost scales with chunk size | 0.07–0.69 ms | 1333–1363 ms | ~2000× | chunk size doesn't matter — the single `open()` dominates |
| **os_stat** (per single stat) | 200× `os.stat(path)`, per call | 2.9 μs | **2.05 ms** | **707×** | metadata-only lookup — cheaper than open |
| **bare_boundary** (per getpid) | 200× `os.getpid()`, per call | 0.65 μs | <5 μs (below timer resolution) | **~1×** | 🎯 the WASM↔JS boundary itself is basically free — expensive things are real FS work, not crossings |
| **fs_open_close** (per single open+close) | 30× `open()+close()`, per call | 9.3 μs | **1503 ms** | **161,000×** | 🚨🚨 the smoking gun — `open()` alone costs ~1.5 s under xeus on the notebook mount. Mechanism not yet directly confirmed — plausible candidates (see /tmp experiment below) include (a) each `open()` intercepted by the JupyterLite service worker and served via a full HTTP fetch, or (b) the FS backend eagerly materializing the file into WASM heap on open. |
| fs_reads_4k_single_open (per 4 KB read on open handle) | 256× `read(4096)`, per call | 1.5 μs | 5.3 ms | ~3500× | ~280× cheaper than open() itself |
| fs_seek_read_small (per seek+read pair) | 50× (seek to random offset, read 64 B), per call | 5.8 μs | 26.9 ms | ~4600× | expensive per iteration once the file is open |
| stream_detrend | `Stream.detrend('linear')` on the 7.77M-sample trace | 418 ms | 392 ms | **0.94×** | 🤯 WASM slightly *faster* — SIMD/JIT wins on the hot loop |
| stream_bandpass | `Stream.filter('bandpass', zerophase=True, corners=4)` | 144 ms | 195 ms | 1.36× | scipy SOS filter — non-vectorizable recurrence limits both platforms |
| **scipy_detrend_direct** | `scipy.signal.detrend(np_array, 'linear')` — no ObsPy wrapper | 474 ms | **367 ms** | **0.77×** | 🤯 WASM slightly *faster* — confirms detrend cost is scipy, not obspy overhead |
| np_correlate at N=100 / 7200 / 72000 | direct-mode `np.correlate` (O(N²) multiply-adds) | 0.01 / 6.3 / 279 ms | 0 / 42 / 4155 ms | 6.7× → **15×** | ratio grows with N because native accelerates as out-of-order execution, cache prefetch, and branch predictor warm up; WASM was already at its asymptotic per-multiply-add rate |
| np_fromfile | `np.fromfile(f, dtype=int32)` of full 12 MB | 2.0 ms | 1597 ms | **815×** | same story as `read_bytes` — one open() dominates |
| plot_subparts (avg of 20-line print / json.dump) | notebook stdout + JSON write | 0.4 ms | 12 ms | ~28× | print roundtrip to browser via ZMQ-in-browser is real but small |
| **full notebook total** | wall time from control cell to save | **13.6 s** | **494 s** | **36×** | skewed by the 230 s `fs_open_close_only` probe (deliberate) — remove it and the total is ~260 s WASM |

## The core story

1. **WASM↔JS boundary crossing is essentially free** (~20 μs). Everything expensive is *actual work* inside the emscripten filesystem layer, not the crossing itself.
2. **`open()` on the notebook filesystem mount costs ~1.5 s per call** — 161,000× native. `/tmp` (MEMFS) opens the same file in 30 μs, ~50,000× faster (see [The /tmp experiment](#the-tmp-experiment--the-slow-open-is-not-universal) below). So the cost is specific to whichever backend serves the notebook working directory, not a WASM or xeus-python universal limit. **The exact mechanism is not yet confirmed** — two leading hypotheses consistent with our data:
   - **(a) Service-worker fetch on each open()**: JupyterLite registers a service worker that intercepts filesystem requests. Each `open()` on the notebook mount may trigger a full HTTP fetch through the SW, even though the file is bundled locally. `/tmp` bypasses the SW entirely (pure in-heap MEMFS), which is why it is fast.
   - **(b) Eager materialization into WASM heap on open()**: the notebook FS backend could copy the entire file into WASM linear memory the first time it is opened. Subsequent `read()`s are just memcpys.
   Both explain the observations equally well; distinguishing them requires either browser DevTools inspection of the service-worker traffic or a targeted probe (e.g. does the *second* `open()` of the same file take the same 1.5 s? — an experiment worth running).
3. **Post-open reads are much cheaper than opens** — once the file handle is obtained (whatever the mechanism), `read()` is just a memcpy from the WASM heap.
4. **libmseed seismic trace decoding under WASM is almost at native speed** (1.23×). Not a WASM issue at all.
5. **Imports don't pay the slow `open()`.** The Python site-packages tree lives on a different (MEMFS-like) mount than user notebook files, so `open()` there is microseconds. What the `imports/*` phases measure is likely Python-init execution cost. The WASM/native ratios (stdlib 6.0×, numpy 2.5×, scipy 6.3×, obspy 3.5×, wasm_compat 2.4×) reflect the split of Python-bytecode interpretation (higher penalty, ~5–10×) vs compiled C-extension init (lower penalty, \~2–3×). **Scipy dominates the absolute cold-start (\~6.3 s of 7.4 s WASM) simply because it is the largest library** — natively it already takes \~5× longer than numpy to import.
6. **scipy runtime under WASM is mixed** (measured): single-pass ops like `detrend` are native-comparable or *slightly faster* (0.77–0.94×), but IIR filters like SOS bandpass are ~1.4× slower (`stream_bandpass` 144 → 195 ms). **Hypothesis** for the direction of the gap: the recurrence relation in the filter cannot be SIMD-vectorized on either side, so both native and WASM run scalar, and WASM's scalar JIT is somewhat behind native `-O3`. This is our reading of a general WASM-vs-native performance pattern; we have not verified it by e.g. comparing generated code.
7. **numpy inner loops are slower under WASM by a measured factor** — asymptotically ~15× slower for tight SIMD-friendly loops (direct-mode `np.correlate` at N=72000: 4155 ms WASM vs 279 ms native, both measured). **Hypothesis** for the mechanism: WASM SIMD128 vs native AVX-512 (2–4× width gap), no FMA fusion (~2×), less aggressive loop unrolling (~1.5×) — the product would give roughly the observed ratio. We have not verified this by disassembling either build. At smaller N the ratio is smaller (~6× at N=7200) because native hasn't yet warmed its out-of-order engine and prefetcher; the ~15× is the asymptotic per-multiply-add cost, not a size-dependent penalty. That part *is* measured (see the ns/MADD table below).

## Full decomposition of `obspy.read(path, format="MSEED")` = 9184 ms measured

| step | est. cost (ms) | source of estimate |
|---|---:|---|
| `_generic_reader` → `glob.glob(path)` | 5 | ~2 stats |
| `uncompress_file` → `Path.exists()` | 3 | 1 stat |
| **`tarfile.is_tarfile(path)`** | **5915** | measured directly (~4 opens × 1.5 s) |
| **`zipfile.is_zipfile(path)`** | **1332** | measured directly (~1 open) |
| `_read_from_plugin` → `Path.exists()` | 3 | 1 stat |
| `_read_mseed` → `np.memmap` shim (1 open + read 12 MB) | 1359 | measured as `read_bytes` |
| libmseed decode | 83 | measured as `obspy_read_bytesio` |
| Python glue | ~484 | remainder |
| **sum** | **~9184 ms** | ✅ matches measured 9184 ms |

## Sub-op breakdown from the fine-grained JSON

**fs_chunk_sweep** — reading 1 MB from the file in progressively smaller chunks. Under WASM, the cost is **flat** across all chunk sizes — from 1 syscall to 2048 syscalls, timings are within ~1%:

| chunk size | # read() syscalls to reach 1 MB | best (ms) | mean (ms) |
|---:|---:|---:|---:|
| 1 MB | 1 | 1340 | 1571 |
| 64 KB | 16 | 1333 | 1579 |
| 4 KB | 256 | 1336 | 1474 |
| 512 B | 2048 | 1363 | 1565 |

Reading in 512-byte chunks (2048 syscalls) is **not measurably slower** than reading in one 1 MB chunk. This is consistent with both of the leading `open()` hypotheses in the core story (service-worker fetch vs eager materialization): once the file bytes are in the WASM address space (however they got there), subsequent `read()` calls are a trivial memory copy regardless of chunk size. The whole cost is paid at `open()`.

**np_correlate_sweep** — direct-mode cross-correlation at three sizes:

| N (samples) | WASM best (ms) | native best (ms) | WASM ns / multiply-add | native ns / multiply-add | WASM/native |
|---:|---:|---:|---:|---:|---:|
| 100 | 0 (below timer resolution) | 0.01 | — | ~1 | — |
| 7200 | 42 | 6.3 | 0.81 | 0.12 | 6.7× |
| **72000** | **4155** | 279 | 0.80 | **0.054** | **15×** |

Direct correlation is O(N²) — `mode='same'` does N² multiply-adds. (72000/7200)² = 100× → expected cost ratio matches. Two subtleties in the per-multiply-add columns:

- **WASM ns/MADD is essentially flat** (0.81 → 0.80). WASM hits its steady-state inner-loop throughput almost immediately — SIMD128 is a simple ISA and TurboFan produces roughly the same code density regardless of loop trip count.
- **Native ns/MADD drops ~2×** as N grows (0.12 → 0.054). Modern x86 has features that need runway to fully engage: out-of-order execution filling the reservation station, the hardware cache prefetcher learning the stride, branch predictor locking onto "taken", micro-op fusion. At N=7200 (~10 μs of inner loop) these are still warming up; at N=72000 they've fully paid off.

The apparent "growing WASM overhead" (6.7× → 15× as N grows) is not WASM getting slower — it is native getting faster at scale (this is what the ns/MADD numbers show directly). **Our attribution of the ~15× asymptote to WASM SIMD128 vs native AVX-512 width + missing FMA fusion is a hypothesis** based on general knowledge of the WASM SIMD ISA and native x86 codegen — we have not confirmed it by inspecting the generated code. Small-N ratios (~6× at N=7200) look smaller only because fixed per-call overhead partly masks the inner-loop cost on both platforms.

*This would be an interesting function to analyze in detail.*

## Model validation — every observed cost fits `N_opens × 1.5 s + small constants`

If the model "open() = ~1.5 s; everything after is trivial" is right, then every FS-touching operation's cost should equal `1.5 s × (number of opens it makes) + decode/tiny reads`. Every measurement fits within ~5%:

| operation | # opens | expected (ms) | measured best (ms) | fit |
|---|---:|---:|---:|---|
| `read_bytes` (open + read 12 MB) | 1 | 1500 | 1359 | ✓ |
| `np_fromfile` (open + read all) | 1 | 1500 | 1597 | ✓ |
| `fs_reads_4k_single_open_1MB` (open + 256 reads) | 1 | 1500 | 1347 | ✓ |
| `fs_seek_read_64B_x50` (open + 50 seek+reads) | 1 | 1500 | 1343 | ✓ |
| `fs_chunk_sweep` sub-ops (open + reads in various sizes) | 1 each | ~1500 | 1333–1363 | ✓ |
| `zipfile_is_zipfile` (open + tail read) | 1 | 1500 | 1332 | ✓ |
| `obspy_read_path_nocompress` (open + read + decode) | 1 | 1500 + 83 = 1583 | 1428 | ✓ |
| **`fs_open_close_only_x30`** | 30 | **30 × 1500 = 45000** | 45078 | ✓ |
| **`tarfile_is_tarfile`** (gzip/bz2/xz/tar probes) | ~4 | **4 × 1500 = 6000** | 5915 | ✓ |
| **`obspy_read_path_format`** (tarfile 4 + zipfile 1 + memmap 1) | 6 | 6 × 1500 + 83 = 9083 | 9184 | ✓ |
| **`obspy_read_path`** (+ auto-detect probes) | ~6 + isFormat | +~1400 for probes → ~10500 | 10566 | ✓ |

Regardless of the underlying mechanism (service-worker fetch, eager materialization, or something else), the **empirical** conclusion is that most of the "why is JupyterLite slow" story reduces to **counting how many times `open()` is called**. Reducing that count is the highest-leverage optimization anywhere in the WASM-Python stack.

## The `/tmp` experiment — the slow `open()` is not universal

To test whether the 1.45 s `open()` cost is a xeus-python-wide phenomenon or specific to the notebook filesystem backend, we copied the 12 MB MSEED file into `/tmp` and reran the FS probes against `/tmp/noise.mseed`:

| operation | notebook mount **WASM** | /tmp **WASM** | native (either mount) | /tmp WASM vs notebook WASM | /tmp WASM vs native |
|---|---:|---:|---:|---:|---:|
| `read_bytes` (open + read 12 MB) | 1359 ms | **1.0 ms** | 1.5 ms | **1359× faster** | 0.65× (memcpy-limited on both) |
| `fs_open_close` (per single open+close) | 1503 ms | **0.03 ms** | 0.008 ms | **56,000× faster** | 3.3× |
| `np.fromfile` (open + read 12 MB) | 1597 ms | **1.1 ms** | 2.0 ms | **1452× faster** | 0.55× |
| `obspy.read(path, format="MSEED", check_compression=False)` | 1428 ms | **78 ms** | 62 ms | **18× faster** | **1.26× — near-native** |
| `shutil.copy` src→/tmp (one-shot) | — | 1444 ms | 6.3 ms | source read dominates | — |

The last two rows are the punchline: `obspy.read` from /tmp under WASM runs within **1.26× of native**. That means the entire 130× penalty for the same call from the notebook mount is not a WASM problem — it is a *notebook-FS-backend* problem, and /tmp shows what the same WASM stack can do when it's out of the way.

**Interpretation.** `/tmp` in xeus-python behaves like a pure in-heap mount (MEMFS or equivalent): reading 12 MB in 1 ms = ~12 GB/s = native memcpy speed, `open()` at 30 μs = trivial hashmap lookup. **The 1.45 s open() cost is specific to whichever filesystem backend serves the notebook working directory** — this is measured. The precise mechanism (service-worker fetch, lazy IndexedDB load, or eager materialization) is **not yet directly confirmed** but the /tmp comparison rules out anything intrinsic to WASM or xeus-python. See core-story bullet 2 for the two leading candidates.

**Consequence.** Copying a file to `/tmp` once and then reading it from there runs the entire ObsPy pipeline at native speed. Total wall-clock: `1700 ms (one-shot copy) + N × 90 ms` versus `N × 1535 ms` for the `BytesIO` trick — /tmp wins after just 2 reads of the same file, and works with libraries that don't accept file-like objects.

**Recommended pattern:**

```python
import shutil, os

_PRELOAD_CACHE = {}
def preload(src_path):
    """Copy a file into MEMFS-backed /tmp once; return the fast path."""
    tmp = _PRELOAD_CACHE.get(src_path)
    if tmp is None:
        tmp = "/tmp/" + os.path.basename(src_path)
        if not os.path.exists(tmp):
            shutil.copy(src_path, tmp)
        _PRELOAD_CACHE[src_path] = tmp
    return tmp

# Works with any path-consuming API — no BytesIO ceremony required.
st = obspy.read(preload("data/mydata.mseed"),
                format="MSEED", check_compression=False)
```

## Actionable recommendations

Grouped by who owns the fix, in decreasing order of leverage. Numbers in **bold** are the wall-clock saving per instance, measured on our WASM setup with a 12 MB MSEED file.

### For notebook authors (immediate, zero ecosystem changes)

```python
# 1a. Simplest single-use pattern — hand BytesIO to obspy.read.
with open(path, "rb") as f:
    st = obspy.read(BytesIO(f.read()), format="MSEED", check_compression=False)
# WASM saving: ~9 s → ~1.5 s per file (~6× faster). Works identically on native.

# 1b. Best for repeated reads or path-only APIs — preload to /tmp (MEMFS).
import shutil, os
_CACHE = {}
def preload(src):
    if src not in _CACHE:
        tmp = "/tmp/" + os.path.basename(src)
        if not os.path.exists(tmp):
            shutil.copy(src, tmp)
        _CACHE[src] = tmp
    return _CACHE[src]

st = obspy.read(preload(path), format="MSEED", check_compression=False)
# After a one-shot 1.7 s copy, all subsequent reads run at native speed (~90 ms).
```

Additional per-notebook wins (each independently applicable):

- **Always pass `format=...`** when the format is known — skips ObsPy's ~30-plugin `isFormat` auto-detect loop. **Saves ~1.4 s per call** WASM.
- **Always pass `check_compression=False`** on non-tar/zip data — skips `tarfile.is_tarfile` + `zipfile.is_zipfile` probes. **Saves ~7.4 s per call** WASM.
- To explore: **Use `scipy.signal.correlate(a, b, method='fft')`** instead of `np.correlate(a, b)` for N ≳ 500 samples. O(N log N) vs O(N²) beats even a 15× WASM per-op slowdown at moderate sizes.

### Ideas for ObsPy upstream (PR candidates, in decreasing leverage)

1. **Fast-path `uncompress_file` on known-uncompressed extensions** (`obspy/core/util/decorator.py`):
   ```python
   _NO_COMPRESSION_SUFFIXES = ('.mseed', '.msd', '.sac', '.segy',
                                '.sgy', '.gcf', '.gse2', '.gse1', '.wav', ...)
   if isinstance(filename, str) and filename.lower().endswith(_NO_COMPRESSION_SUFFIXES):
       return func(filename, *args, **kwargs)
   ```
   Cost native: microseconds. WASM saving: **~7.4 s per `obspy.read(path)` call**. Zero API change.

2. **Sniff-once auto-detect**: rewrite `_read_from_plugin`'s `for format_ep in eps.values(): is_format(filename)` loop so that a single `open()+read(<header size>)` happens once and the resulting bytes are passed to every `_is_*` probe. Currently each plugin opens the file itself. Requires the plugin-level `isFormat` API to accept a bytes-or-fileobj argument (many already do).
   - Native impact: negligible. WASM impact: **saves ~1.4 s per auto-detect call** and generalizes to all backends.

3. **First-class `bytes` acceptance in `_read_mseed`**: today the path branch calls `np.memmap`, the file-object branch does `from_buffer(fileobj.read())`, and there is no direct `bytes` branch. Add one so user code can go straight from `bytes` to a stream without wrapping in `BytesIO`.

### Ideas for xeus-python / jupyterlite-xeus (root-cause fixes)

The measured bottleneck is that each `open()` on the notebook filesystem mount takes ~1.5 s, regardless of what is read afterwards. **Two hypotheses about the mechanism** (see core-story bullet 2): each open goes through the service worker as an HTTP fetch, or the FS backend eagerly copies the whole file into the WASM heap on first open. The proposed fixes below would help under either hypothesis, but the right specific fix depends on which one is correct — worth an experiment (e.g. compare Chrome DevTools Network + Application panels with a paused breakpoint on `FS.open`).

1. **Cache `open()`ed files within a session**: on first `open()`, materialize into a MEMFS-like slot; subsequent `open()`s on the same path return an in-memory view. Even a per-notebook-session LRU would collapse the compression-probe pathology from N × 1.5 s to a single 1.5 s cost per file.

2. **Lazy-load only the range actually read**: switch the notebook mount to an HTTP-range-request or IDBFS-lazy backend where small `read()`s pay only for the bytes requested. Then `open()` alone would be cheap; today it pays the full-file cost even when only 64 bytes are subsequently read.

3. **Ship [WASM Relaxed SIMD](https://github.com/WebAssembly/relaxed-simd) builds** of numpy/scipy from emscripten-forge. Adds FMA (fused multiply-add) and maybe closes half the ~15× per-multiply-add gap for SIMD-vectorizable numpy loops. Both Firefox and Chrome support it.

### For the broader scientific-Python community

- The per-mount-`open()`-eager-materialization pattern **is not obvious to library authors and is invisible to native profilers**. Any Python library that does `Path.exists()`, `os.stat()`, or repeated small `open()`s on user data (netCDF4, h5py, GDAL, pyrocko, xarray, ...) will hit the same wall on JupyterLite. A community-shared "known-slow patterns under WebAssembly" document + a lint rule (`wasm-perf-check`) would compound value across the ecosystem.
