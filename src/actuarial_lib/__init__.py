"""Shared actuarial kernels for the Life & Pension Actuarial Workbench demo.

Plain Python / NumPy / statsmodels — the same code runs in a notebook, inside a Spark
UDF (applyInPandas / mapInPandas), inside a Ray task, or on a laptop test. That's the
point: the maths is portable; Databricks orchestrates and scales it.
"""
from . import glm, projection, stochastic  # noqa: F401

__version__ = "1.0.0"
