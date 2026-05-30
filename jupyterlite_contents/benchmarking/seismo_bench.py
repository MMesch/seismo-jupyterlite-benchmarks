"""Compatibility wrapper for benchmark helpers inside JupyterLite.

JupyterLite flattens the repository-level ``benchmarking`` content directory to
``seismo_bench.py``. This wrapper preserves the package import path used by
older benchmark notebooks: ``benchmarking.seismo_bench``.
"""

from seismo_bench import *  # noqa: F401,F403

