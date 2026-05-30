"""Small benchmark helpers designed to work in CPython and JupyterLite.

The helpers intentionally avoid platform-specific dependencies. If psutil is
available, Python process memory is recorded. In JupyterLite/Pyodide that value
is often unavailable, so the CSV keeps a separate manual platform memory field.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional


RESULT_FIELDS = [
    "notebook",
    "environment",
    "browser",
    "os",
    "device",
    "run_index",
    "phase",
    "wall_time_s",
    "python_peak_memory_mb",
    "platform_peak_memory_mb",
    "success",
    "notes",
]


@dataclass
class BenchmarkContext:
    notebook: str
    environment: str = "unset"
    browser: str = "unset"
    device: str = "unset"
    run_index: int = 0
    platform_peak_memory_mb: Optional[float] = None
    notes: str = ""
    results_dir: str = "benchmark-results"


class BenchmarkRun:
    """Collects phase timings for one notebook execution."""

    def __init__(self, context: BenchmarkContext):
        self.context = context
        self.rows = []
        Path(context.results_dir).mkdir(parents=True, exist_ok=True)

    @contextmanager
    def phase(self, name: str, notes: str = "") -> Iterator[None]:
        tracemalloc.start()
        start = time.perf_counter()
        success = True
        error_note = ""
        try:
            yield
        except Exception as exc:
            success = False
            error_note = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            wall_time_s = time.perf_counter() - start
            _, traced_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            python_peak = max(_process_rss_mb() or 0.0, traced_peak / 1024 / 1024)
            combined_notes = "; ".join(
                part for part in [self.context.notes, notes, error_note] if part
            )
            self.rows.append(
                {
                    "notebook": self.context.notebook,
                    "environment": self.context.environment,
                    "browser": self.context.browser,
                    "os": platform.platform(),
                    "device": self.context.device,
                    "run_index": self.context.run_index,
                    "phase": name,
                    "wall_time_s": round(wall_time_s, 6),
                    "python_peak_memory_mb": round(python_peak, 3) if python_peak else "",
                    "platform_peak_memory_mb": _blank_if_none(
                        self.context.platform_peak_memory_mb
                    ),
                    "success": success,
                    "notes": combined_notes,
                }
            )

    def record_manual_phase(
        self,
        name: str,
        wall_time_s: float,
        success: bool = True,
        notes: str = "",
    ) -> None:
        self.rows.append(
            {
                "notebook": self.context.notebook,
                "environment": self.context.environment,
                "browser": self.context.browser,
                "os": platform.platform(),
                "device": self.context.device,
                "run_index": self.context.run_index,
                "phase": name,
                "wall_time_s": round(wall_time_s, 6),
                "python_peak_memory_mb": _blank_if_none(_process_rss_mb()),
                "platform_peak_memory_mb": _blank_if_none(
                    self.context.platform_peak_memory_mb
                ),
                "success": success,
                "notes": "; ".join(part for part in [self.context.notes, notes] if part),
            }
        )

    def save(self) -> tuple[Path, Path]:
        base = _safe_name(
            f"{self.context.notebook}_{self.context.environment}_run{self.context.run_index}"
        )
        csv_path = Path(self.context.results_dir) / f"{base}.csv"
        json_path = Path(self.context.results_dir) / f"{base}.json"

        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)

        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "context": asdict(self.context),
                    "fields": RESULT_FIELDS,
                    "rows": self.rows,
                },
                fh,
                indent=2,
            )

        return csv_path, json_path


def make_context(
    notebook: str,
    environment: str = "unset",
    browser: str = "unset",
    device: str = "unset",
    run_index: int = 0,
    platform_peak_memory_mb: Optional[float] = None,
    notes: str = "",
    results_dir: str = "benchmark-results",
) -> BenchmarkContext:
    """Create a benchmark context with spreadsheet-compatible defaults."""

    return BenchmarkContext(
        notebook=notebook,
        environment=environment,
        browser=browser,
        device=device,
        run_index=run_index,
        platform_peak_memory_mb=platform_peak_memory_mb,
        notes=notes,
        results_dir=results_dir,
    )


def start_run(context: BenchmarkContext) -> BenchmarkRun:
    return BenchmarkRun(context)


def _process_rss_mb() -> Optional[float]:
    try:
        import psutil  # type: ignore

        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except Exception:
        return None


def _blank_if_none(value: Optional[float]) -> str | float:
    return "" if value is None else round(float(value), 3)


def _safe_name(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in "._-" else "_")
    return "".join(keep)

