"""Cloud Run live-ingest service.

Receives webhook callbacks from API-Football and the FPL Bootstrap polling
job and persists normalized events to BigQuery.
"""

__version__ = "0.1.0"
