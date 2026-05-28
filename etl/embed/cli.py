"""Unified CLI for the embed pipeline.

etl-embed chunk    -> chunk Wikipedia documents
etl-embed embed    -> generate Gemini embeddings
etl-embed kb       -> upload chunks as Salesforce Knowledge articles
etl-embed pgvector -> upsert vectors to a fallback pgvector store
"""

from __future__ import annotations

import typer

from etl.embed import chunker, embed_gemini, upload_to_knowledge, upload_to_pgvector

app = typer.Typer(no_args_is_help=True, help="Embedding + RAG pipeline.")
app.add_typer(chunker.app, name="chunk")
app.add_typer(embed_gemini.app, name="embed")
app.add_typer(upload_to_knowledge.app, name="kb")
app.add_typer(upload_to_pgvector.app, name="pgvector")


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
