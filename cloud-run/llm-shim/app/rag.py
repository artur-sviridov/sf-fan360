"""Vector RAG search backed by pgvector + Gemini gemini-embedding-001.

The Agentforce External Service Action `Semantic_Search_Knowledge` POSTs
to `/rag/search` with a natural-language `query` plus optional
`entityType` / `entitySlug` filters. We embed the query, run a cosine
similarity search against the `broadcast_knowledge` table, and return
top-k chunks with citations.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=20)
    entity_type: str | None = Field(default=None, alias="entityType")
    entity_slug: str | None = Field(default=None, alias="entitySlug")

    model_config = {"populate_by_name": True}


class SearchHit(BaseModel):
    chunk_id: str
    text: str
    title: str | None = None
    source_url: str
    entity_type: str | None = None
    entity_slug: str | None = None
    score: float


class SearchResponse(BaseModel):
    results: list[SearchHit]


def embed_query(text: str) -> list[float]:
    url = f"{settings.gemini_base_url}/models/{settings.embed_model}:embedContent"
    r = httpx.post(
        url,
        params={"key": settings.gemini_api_key},
        json={
            "model": f"models/{settings.embed_model}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": settings.embed_output_dimensions,
        },
        timeout=settings.request_timeout_seconds,
    )
    r.raise_for_status()
    return r.json()["embedding"]["values"]


def search(req: SearchRequest) -> SearchResponse:
    if not settings.pgvector_dsn:
        raise RuntimeError("pgvector DSN not configured")
    try:
        import psycopg
        from pgvector.psycopg import register_vector
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("install psycopg + pgvector") from exc

    vec = embed_query(req.query)

    with psycopg.connect(settings.pgvector_dsn) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            sql = f"""
                SELECT chunk_id, text, title, source_url, entity_type, entity_slug,
                       1 - (vector <=> %s::vector) AS score
                FROM {settings.pgvector_table}
                WHERE TRUE
                  {"AND entity_type = %s" if req.entity_type else ""}
                  {"AND entity_slug = %s" if req.entity_slug else ""}
                ORDER BY vector <=> %s::vector
                LIMIT %s
            """
            params: list[Any] = [vec]
            if req.entity_type:
                params.append(req.entity_type)
            if req.entity_slug:
                params.append(req.entity_slug)
            params.extend([vec, req.k])
            cur.execute(sql, params)
            rows = cur.fetchall()

    hits = [
        SearchHit(
            chunk_id=row[0],
            text=row[1],
            title=row[2],
            source_url=row[3],
            entity_type=row[4],
            entity_slug=row[5],
            score=float(row[6]),
        )
        for row in rows
    ]
    return SearchResponse(results=hits)
