"""Tests for the Vertex <-> AI Studio shape translators."""

from __future__ import annotations

import sys
from pathlib import Path

SVC_ROOT = Path(__file__).resolve().parents[1]
if str(SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(SVC_ROOT))

import pytest

from app.translators import (  # noqa: E402
    aistudio_response_to_vertex,
    vertex_request_to_aistudio,
)


def test_vertex_request_to_aistudio_basic():
    vertex = {
        "instances": [
            {
                "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 50},
            }
        ]
    }
    ai = vertex_request_to_aistudio(vertex)
    assert ai["contents"][0]["parts"][0]["text"] == "ping"
    assert ai["generationConfig"]["temperature"] == 0.1
    assert ai["safetySettings"] == []


def test_vertex_request_to_aistudio_rejects_batch():
    vertex = {"instances": [{}, {}]}
    with pytest.raises(ValueError, match="batch"):
        vertex_request_to_aistudio(vertex)


def test_vertex_request_to_aistudio_rejects_empty():
    with pytest.raises(ValueError, match="missing"):
        vertex_request_to_aistudio({})


def test_aistudio_response_to_vertex_wraps_candidates():
    ai = {
        "candidates": [
            {
                "content": {"parts": [{"text": "pong"}], "role": "model"},
                "finishReason": "STOP",
                "safetyRatings": [],
            }
        ],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        "modelVersion": "gemini-2.5-flash",
    }
    vertex = aistudio_response_to_vertex(ai)
    assert "predictions" in vertex
    pred = vertex["predictions"][0]
    assert pred["candidates"][0]["content"]["parts"][0]["text"] == "pong"
    assert pred["modelVersion"] == "gemini-2.5-flash"
    assert pred["usageMetadata"]["promptTokenCount"] == 3


def test_aistudio_response_to_vertex_handles_empty():
    vertex = aistudio_response_to_vertex({})
    assert vertex == {
        "predictions": [{"candidates": [], "usageMetadata": {}, "modelVersion": None}]
    }
