"""Fan360 Labs ETL package.

Loaders for free EPL data sources, normalizers, and BigQuery / Salesforce
sinks. Each source module exposes a `fetch()` and `to_parquet()` callable.
The `run_full` module orchestrates a full refresh.
"""

from etl.config import settings

__all__ = ["settings"]
__version__ = "0.1.0"
