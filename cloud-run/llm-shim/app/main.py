"""FastAPI entrypoint for the llm-shim service."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Path
from pydantic import BaseModel

from app import __version__
from app.auth import require_shared_secret
from app.cache import cache_key, get_or_compute
from app.config import settings
from app.rag import SearchRequest, SearchResponse, search
from app.translators import aistudio_response_to_vertex, vertex_request_to_aistudio

logger = logging.getLogger("llm-shim")
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="fan360-labs llm-shim", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# ---------------------------------------------------------------------------
# Vertex-compatible LLM proxy
# ---------------------------------------------------------------------------

VERTEX_PATH = "/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:predict"


@app.post(VERTEX_PATH, dependencies=[Depends(require_shared_secret)])
async def vertex_predict(
    project: str = Path(...),
    location: str = Path(...),
    model: str = Path(...),
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if body is None:
        raise HTTPException(400, "missing request body")
    try:
        aistudio_body = vertex_request_to_aistudio(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    target_model = _route_model(model)
    key = cache_key(target_model, body)

    def call_aistudio() -> dict[str, Any]:
        url = f"{settings.gemini_base_url}/models/{target_model}:generateContent"
        with httpx.Client(timeout=settings.request_timeout_seconds) as client:
            r = client.post(url, params={"key": settings.gemini_api_key}, json=aistudio_body)
            if r.status_code >= 400:
                logger.warning(
                    "ai-studio error model=%s status=%s body=%s",
                    target_model,
                    r.status_code,
                    r.text[:300],
                )
            r.raise_for_status()
            return r.json()

    aistudio_response = get_or_compute(key, call_aistudio)
    return aistudio_response_to_vertex(aistudio_response)


def _route_model(requested_model: str) -> str:
    """Map any incoming Vertex model name to a free AI Studio variant.

    Salesforce's Model Builder may pass model names like `gemini-1.5-flash`
    or vendor-specific aliases. We collapse them all to either the primary
    or the fallback free model.
    """
    name = requested_model.lower()
    if "lite" in name or "embedding" in name:
        return settings.fallback_model
    return settings.primary_model


# ---------------------------------------------------------------------------
# RAG search
# ---------------------------------------------------------------------------


class SearchRequestExternal(BaseModel):
    """OpenAPI-flavored body used by Agentforce External Service Action."""
    query: str
    k: int = 5
    entityType: str | None = None
    entitySlug: str | None = None


@app.post("/rag/search", dependencies=[Depends(require_shared_secret)])
def rag_search(body: SearchRequestExternal) -> SearchResponse:
    req = SearchRequest(
        query=body.query,
        k=body.k,
        entityType=body.entityType,
        entitySlug=body.entitySlug,
    )
    return search(req)
