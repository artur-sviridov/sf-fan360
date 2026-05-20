# Phase 4 - Knowledge + Vector RAG

**Goal.** Wikipedia narratives chunked, embedded, and queryable by semantic
search from inside Agentforce. Same chunks also indexed in Salesforce
Knowledge for native citation rendering.

**Time budget.** ~2 hours.

**Prerequisites.** Phase 3 exit gate. Knowledge enabled on the org:

> SF: Setup -> Quick Find "Knowledge" -> ensure Lightning Knowledge is on.

Custom fields shipped via SFDX (see `force-app/main/default/objects/Knowledge__kav/fields/`):

- `Summary__c`, `Body__c`, `SourceUrl__c`, `EntityType__c`, `EntitySlug__c`.

Deploy them:

```powershell
sf project deploy start -o s7dev `
    -d force-app/main/default/objects/Knowledge__kav
```

---

## Step 1. Chunk the Wikipedia documents

```powershell
python -m etl.embed.chunker `
    --parquet data/wikipedia/documents `
    --out data/chunks/wikipedia.jsonl
```

Expect ~1,500 chunks for the seed seed lists (~80 entities x ~20 chunks
each). Sanity check:

```powershell
Get-Content data/chunks/wikipedia.jsonl | Measure-Object -Line
```

---

## Step 2. Embed via free Gemini API

```powershell
python -m etl.embed.embed_gemini `
    --jsonl data/chunks/wikipedia.jsonl `
    --out data/embeddings/wikipedia.parquet `
    --sleep-seconds 0.25
```

`text-embedding-004` free tier limit ~1,500 RPD; 1,500 chunks fits in one
day with 0.25 s sleep (~6 req/s, well under burst limits). If you hit a 429,
let the tenacity retry handle it.

---

## Step 3a. Primary path - Data Cloud Vector DB

Check whether your DE has Vector DB enabled:

> SF: Data Cloud -> Setup -> Vector Database -> Get Started.

If the page exists, follow the wizard:

1. Source DMO: `BroadcastKnowledge__dlm` (create via the wizard if not
   already mapped).
2. Map column `vector` -> embedding vector field.
3. Map column `text` -> chunk text.
4. Map columns `entity_slug`, `entity_type` -> metadata filters.
5. Use built-in `e5-large-v2` embedding (regenerate-on-upsert). Reuses
   our pre-computed vectors as fallback when external embedding is set.
6. Run "Index Now". First index takes ~3 min for 1,500 chunks.

**EVIDENCE.** Screenshot the Vector DB index status ->
`docs/trust-layer-evidence/04-vector-db.png`.

---

## Step 3b. Fallback path - pgvector on Supabase

Only if Vector DB is gated in your DE org.

1. Create a free Supabase project at <https://supabase.com>. Get the
   connection string (settings -> database -> connection string).
2. Enable pgvector extension:
   ```
   create extension if not exists vector;
   ```
3. Export `PGVECTOR_DSN` in your environment:
   ```
   $env:PGVECTOR_DSN = "postgres://...supabase.co:5432/postgres"
   ```
4. Upload:
   ```powershell
   python -m etl.embed.upload_to_pgvector `
       --parquet data/embeddings/wikipedia.parquet
   ```
5. The Phase 5 agent's External Service Action `SemanticSearchKnowledge`
   points at the llm-shim's `/rag/search` endpoint, which queries this
   table.

---

## Step 4. Upload chunks as Salesforce Knowledge articles

```powershell
pip install simple-salesforce
python -m etl.embed.upload_to_knowledge `
    --jsonl data/chunks/wikipedia.jsonl
```

Verify in Setup -> Knowledge Articles: ~1,500 draft articles. Publish them
in bulk via Knowledge Settings -> "Publish All Drafts" (or via SOQL).

---

## EXIT GATE

- Semantic search for "Pep Guardiola false nine" returns top-5 chunks all
  belonging to `entity_type=manager` and `entity_slug` containing "guardiola".
- Semantic search for "Klopp gegenpressing" returns Liverpool-related
  chunks with `entity_type` in `{manager, club}`.
- Both queries return clickable `source_url` citations.

Proceed to [phase5-agent-build.md](phase5-agent-build.md).
