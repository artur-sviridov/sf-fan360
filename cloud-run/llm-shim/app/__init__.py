"""Cloud Run LLM shim.

Two responsibilities:

1. **Vertex-shape LLM proxy** (`/v1/projects/{p}/locations/{l}/publishers/google/models/{m}:predict`).
   Accepts a Vertex AI Gemini Predict request, translates it to the free
   Gemini AI Studio `/v1beta/models/<model>:generateContent` shape, returns
   a Vertex-shaped response. Salesforce Model Builder talks to this URL
   thinking it is a real Vertex endpoint.

2. **Vector RAG search** (`/rag/search`). Backed by pgvector + Gemini
   embeddings, called by the Agentforce External Service Action
   `Semantic_Search_Knowledge`.
"""

__version__ = "0.1.0"
