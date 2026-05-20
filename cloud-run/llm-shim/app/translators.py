"""Translate between Vertex AI Gemini Predict and Gemini AI Studio shapes.

Vertex `:predict` request shape (simplified):
    {
      "instances": [
        {
          "contents": [
            {"role": "user", "parts": [{"text": "..."}]}
          ],
          "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400}
        }
      ]
    }

Gemini AI Studio `:generateContent` shape:
    {
      "contents": [
        {"role": "user", "parts": [{"text": "..."}]}
      ],
      "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400}
    }

We strip `instances[]`, post to AI Studio, then wrap the response back into
Vertex's `predictions[]` envelope so Salesforce's model contract sees the
expected shape.
"""

from __future__ import annotations

from typing import Any


def vertex_request_to_aistudio(vertex_body: dict[str, Any]) -> dict[str, Any]:
    instances = vertex_body.get("instances") or []
    if not instances:
        raise ValueError("missing 'instances' in Vertex request")
    if len(instances) > 1:
        raise ValueError("shim does not batch; send one instance at a time")
    inst = instances[0]
    return {
        "contents": inst.get("contents") or [],
        "generationConfig": inst.get("generationConfig") or {},
        "safetySettings": inst.get("safetySettings") or [],
        "systemInstruction": inst.get("systemInstruction"),
    }


def aistudio_response_to_vertex(aistudio_body: dict[str, Any]) -> dict[str, Any]:
    candidates = aistudio_body.get("candidates") or []
    return {
        "predictions": [
            {
                "candidates": [
                    {
                        "content": c.get("content"),
                        "finishReason": c.get("finishReason"),
                        "safetyRatings": c.get("safetyRatings", []),
                    }
                    for c in candidates
                ],
                "usageMetadata": aistudio_body.get("usageMetadata", {}),
                "modelVersion": aistudio_body.get("modelVersion"),
            }
        ]
    }
